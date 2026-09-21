"""conftest.py — テスト間で共有するfixture。

`client` fixtureはFlaskアプリのテストクライアントを作る。生成物の出力先・
ユーザー/ジョブDB・メール送信をすべてテストごとに隔離された一時的な実装に
差し替えるため、複数のテストファイル(test_app.py, test_billing_and_email.py等)
から共通で使う。
"""

import pathlib

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


def bodice_width_at_bust_cm(scaled_or_finalized) -> float:
    """身頃の**バストの高さ**での幅(cm)を返す(round26で追加)。

    round25まで身頃は上から下まで同じ幅だったので、外接矩形の幅がそのまま
    「出来上がりの胴回り」だった。round26で裾をヒップに合わせて開かせた
    ため、外接矩形の幅は**裾(ヒップ)の幅**になる。着用ゆとり(バストの
    ゆとり)を測りたいテストは、バストの高さで測る必要がある。

    バストの高さは「脇線がいちばん上で始まる高さ(脇の下)」そのもの。

    round70までは、そこから0.5cm下で測っていた——脇の下ちょうどだと
    袖ぐりカーブの端点と重なって不安定だから、という理由である。
    round71でダーツの脚を揃える(`engine/darts.py`の`_equalise_legs`)ように
    したところ、**脇の下のすぐ下で脇線が縦でなくなった**(口が脇線から
    少し外れるため)。0.5cm下で測ると、その傾きのぶんを胴回りとして
    数えてしまう。実測:

        バスト   バストラインちょうど   0.5cm下     差
          60          68.000cm         68.152    +0.152
          83          91.000cm         91.219    +0.219
          88          96.000cm         96.237    +0.237

    バストラインちょうどの値は**きっかりバスト＋ゆとり**になる。
    0.5cmずらす理由(不安定さ)は実測では起きておらず、ずらす方が
    誤差を生んでいた。
    """
    from engine.compatibility import _closed_points, side_seam_edges, _x_range_at_y
    from engine.svgpath import segments_to_polyline

    line = getattr(scaled_or_finalized, "stitch_line", None)
    if line is None:
        line = segments_to_polyline(scaled_or_finalized.segments, curve_steps=200)
    points = _closed_points(line)
    # round29: 辺の集め方はエンジンと同じ`side_seam_edges`を使う。ここだけ
    # 独自に集めていると、胸ぐせダーツの口の上に残る短い断片を取りこぼし、
    # 「脇線の上端」がダーツの口の下まで下がる。すると裾へ向かって開いた
    # 分だけ幅を多く測ってしまう(実測: バスト60で68.00→68.23cm)。
    tops = [min(a[1], b[1]) for _i, _side, a, b in side_seam_edges(points)]
    if not tops:
        return 0.0
    span = _x_range_at_y(points, min(tops))
    return (span[1] - span[0]) if span else 0.0


@pytest.fixture(autouse=True)
def _keep_the_source_tree_clean():
    """テストがリポジトリの中へ生成物を書いていないか、1件ずつ見張る。

    【round48で見つけたこと】`PatternForgePipeline()` の出力先の既定は
    `"generated"`——**カレントディレクトリからの相対パス**である。
    `client` fixtureはOUTPUT_DIRを一時ディレクトリへ差し替えるが、
    パイプラインを直に作るテストはその外にいる。実際に
    `tests/test_nesting.py` が `skip_export` を付けずに6回生成しており、
    走らせるたびに **6.4MB**(56ファイル)が作業ツリーの `generated/` に
    残っていた。`.gitignore` に入っているのでgit statusにも出ず、
    気づかないまま溜まり続けていた(配布用のzipが3.2MB→5.2MBに増えて発覚)。

    **セッション単位ではなくテスト単位**にしてある。セッション単位だと
    後片付けが最後に1回走るだけなので、pytestは失敗を「最後に動いていた
    テスト」に付けてしまい、**書いた本人とは別のテストの名前が出る**
    (round48で実際にそうなり、無関係なテストを疑った)。

    ここでは消さない——消すと「書いている」ことが隠れてしまう。
    増えていたら、そのテストの名前で失敗させる。
    """
    generated = pathlib.Path(app_module.BASE_DIR) / "generated"
    before = set(generated.iterdir()) if generated.is_dir() else set()
    yield
    after = set(generated.iterdir()) if generated.is_dir() else set()
    leaked = sorted(p.name for p in after - before)
    assert leaked == [], (
        "このテストがリポジトリの中(generated/)へ生成物を書きました: "
        f"{leaked[:8]}{'…' if len(leaked) > 8 else ''}\n"
        "パイプラインを直に作るテストは output_dir=str(tmp_path) を渡すか、"
        "出力が要らないなら skip_export=True を付けてください。")
