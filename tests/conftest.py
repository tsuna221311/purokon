"""conftest.py — テスト間で共有するfixture。

`client` fixtureはFlaskアプリのテストクライアントを作る。生成物の出力先・
ユーザー/ジョブDB・メール送信をすべてテストごとに隔離された一時的な実装に
差し替えるため、複数のテストファイル(test_app.py, test_billing_and_email.py等)
から共通で使う。
"""

import pytest

import app as app_module
import store as store_module

# round6でapp.pyにCSRFトークン検証(`_csrf_protect`)を追加したことに伴い、
# テストクライアントのPOSTリクエストにも有効なトークンが必要になった。
# 個々のテスト(100件以上)を1つずつ書き換える代わりに、下の`client` fixtureで
# セッションに固定トークンを埋め込み、`client.post`をラップして
# `data`辞書に自動で補うことで、既存テストへの影響を最小化している。
# CSRF検証自体をテストするテスト(test_appのCSRF関連テスト参照)は、
# このトークンをわざと省略・改ざんして`client.post(..., data={...})`を
# 直接呼べば、自動補完(setdefault)により上書きされないため検証できる。
TEST_CSRF_TOKEN = "test-fixed-csrf-token-do-not-use-in-production"


def _with_csrf_token(data):
    """POSTの`data`にCSRFトークンを補う(既に指定されていれば上書きしない)。

    data未指定(None)ならトークンのみのdictを、dictならコピーした上で
    setdefaultする。bytes/str(例: /billing/webhookの生JSONペイロード)は
    フォームフィールドを持たないため、そのまま素通しする。
    """
    if data is None:
        return {"csrf_token": TEST_CSRF_TOKEN}
    if isinstance(data, dict):
        merged = dict(data)
        merged.setdefault("csrf_token", TEST_CSRF_TOKEN)
        return merged
    return data


class RecordingMailer:
    """テスト用のフェイクメーラー。実際には送信せず、送信内容を記録するだけ。"""

    is_console = False  # 画面へのURL表示に頼らず、実際に送信された本文からURLを取り出す

    def __init__(self):
        self.sent = []

    def send(self, to, subject, body):
        self.sent.append({"to": to, "subject": subject, "body": body})


@pytest.fixture()
def client(tmp_path, monkeypatch):
    # 生成物は一時ディレクトリに書き出す（本物のgenerated/を汚さない）。
    monkeypatch.setattr(app_module, "OUTPUT_DIR", str(tmp_path))
    monkeypatch.setattr(app_module.pipeline, "output_dir", str(tmp_path))
    # ユーザー/ジョブ所有権/利用回数のDBも、本物のpatternforge.dbを汚さず
    # テスト間で状態を共有しないよう、テストごとに新しいSQLiteファイルを使う。
    monkeypatch.setattr(app_module, "db", store_module.Store(str(tmp_path / "test.db")))
    # メールは実際に送信せず、内容をテストから検証できるように差し替える。
    monkeypatch.setattr(app_module, "mail", RecordingMailer())
    # round6より前はレート制限がプロセス内メモリ(dequeベース)だけで動いて
    # いたため、テスト間で状態を共有しないようここで明示的にクリアして
    # いた。round6でstore.pyのSQLite(`db.check_rate_limit`)に切り替えた
    # ことで、上のdb差し替え(テストごとに新しい一時DBファイル)自体が
    # レート制限のヒット記録もテスト間で隔離するため、このクリア処理は
    # 不要になった。
    # /forgot-passwordの応答時間の下限(_FORGOT_PASSWORD_MIN_RESPONSE_SECONDS)は
    # タイミングサイドチャネル対策の待機だが、大半のテストはそれ自体を検証
    # 対象にしていないため、既定では0にしてテスト全体の実行時間を不必要に
    # 延ばさない。この下限の効果自体を検証するテストでは、個別に
    # monkeypatchで正の値に戻す。
    monkeypatch.setattr(app_module, "_FORGOT_PASSWORD_MIN_RESPONSE_SECONDS", 0.0)
    app_module.app.config["TESTING"] = True
    with app_module.app.test_client() as c:
        with c.session_transaction() as sess:
            sess["csrf_token"] = TEST_CSRF_TOKEN
        _original_post = c.post

        def _post_with_csrf(*args, **kwargs):
            kwargs["data"] = _with_csrf_token(kwargs.get("data"))
            return _original_post(*args, **kwargs)

        c.post = _post_with_csrf
        yield c
