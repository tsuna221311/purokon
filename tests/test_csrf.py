"""test_csrf.py — CSRFトークン検証(round6で追加、app.pyの`_csrf_protect`)のテスト。

第2回セキュリティ監査では`SESSION_COOKIE_SAMESITE=Lax`のみの部分的な対策
だったが、round6で状態変更リクエスト全体を対象にした完全なトークン方式を
追加した。ここでは:
  - 正常系(実際のHTML内のトークンをそのまま使えば通る)
  - 異常系(トークン無し・不一致・別セッションのトークン)
  - 例外(GET等の安全なメソッドは対象外、/billing/webhookは対象外)
を確認する。

他のテストファイル(test_app.py等)のPOSTはすべて`tests/conftest.py`の
`client` fixtureが自動でテスト専用の固定トークン(`TEST_CSRF_TOKEN`)を
補っているため、このファイルではCSRF検証そのものを狙って、あえて
`client`のPOSTラッパーを経由しない生の`app_module.app.test_client()`や、
`data`に明示的な`csrf_token`キーを与えることで自動補完(setdefault)を
上書きするテストを書く。
"""

import re

import app as app_module
from tests.conftest import TEST_CSRF_TOKEN, _with_csrf_token


def _extract_meta_csrf_token(html: str) -> str:
    match = re.search(r'<meta name="csrf-token" content="([^"]*)">', html)
    assert match, "csrf-token metaタグがHTMLに見つかりません"
    return match.group(1)


def test_index_page_embeds_a_csrf_token_meta_tag(client):
    body = client.get("/").get_data(as_text=True)
    token = _extract_meta_csrf_token(body)
    assert token  # 空文字ではない実際のトークンが埋め込まれている


def test_generate_form_hidden_input_matches_the_meta_tag(client):
    # #generate-formはJSのnew FormData(form)で自動的に送信されるため、
    # metaタグと同じ値がhidden inputにも入っている必要がある。
    body = client.get("/").get_data(as_text=True)
    meta_token = _extract_meta_csrf_token(body)
    hidden_input_match = re.search(
        r'<form id="generate-form">\s*<input type="hidden" name="csrf_token" value="([^"]*)">',
        body,
    )
    assert hidden_input_match, "generate-form内にcsrf_tokenのhidden inputが見つかりません"
    assert hidden_input_match.group(1) == meta_token


def test_csrf_token_is_stable_across_requests_within_the_same_session(client):
    first = _extract_meta_csrf_token(client.get("/").get_data(as_text=True))
    second = _extract_meta_csrf_token(client.get("/pricing").get_data(as_text=True))
    assert first == second


def test_a_real_browser_style_flow_using_the_actual_page_token_succeeds(
        tmp_path, monkeypatch):
    # conftestの固定トークンに頼らず、実際にGETでページを取得し、そこに
    # 埋め込まれたトークンをそのままフォームに使う、実ブラウザに近い経路を
    # 確認する。
    #
    # round48: 出力先を一時ディレクトリへ向ける。このテストは`client`
    # fixtureをあえて使わない(本物のトークンが要るため)ので、その
    # fixtureがやっている出力先の差し替えも効いていなかった。
    # そのため本当に型紙を生成し、**リポジトリの中**の`generated/`へ
    # 4ファイル書いていた(conftestの`_keep_the_source_tree_clean`が検出)。
    monkeypatch.setattr(app_module, "OUTPUT_DIR", str(tmp_path))
    monkeypatch.setattr(app_module.pipeline, "output_dir", str(tmp_path))
    fresh_client = app_module.app.test_client()
    body = fresh_client.get("/").get_data(as_text=True)
    token = _extract_meta_csrf_token(body)
    form = {
        "bust": "84", "waist": "68", "hip": "92", "height": "160",
        "sleeve_length": "54", "shoulder_width": "37",
        "mode": "manual", "neckline": "round_neck",
        "sleeve_style": "straight", "skirt_style": "flare",
        "csrf_token": token,
    }
    response = fresh_client.post("/api/generate", data=form)
    assert response.status_code == 200
    assert response.get_json()["ok"] is True


def test_post_without_csrf_token_is_rejected_with_400_json_for_api_paths():
    fresh_client = app_module.app.test_client()
    fresh_client.get("/")  # セッション(と正規のトークン)を発行させる
    form = {
        "bust": "84", "waist": "68", "hip": "92", "height": "160",
        "sleeve_length": "54", "shoulder_width": "37",
        "mode": "manual", "neckline": "round_neck",
        "sleeve_style": "straight", "skirt_style": "flare",
        # csrf_tokenをあえて含めない
    }
    response = fresh_client.post("/api/generate", data=form)
    assert response.status_code == 400
    body = response.get_json()
    assert body["ok"] is False
    assert "セキュリティ確認" in body["error"]


def test_post_with_wrong_csrf_token_is_rejected(client):
    # `client` fixtureのセッションには`TEST_CSRF_TOKEN`が入っているが、
    # 明示的に別の値を指定すると自動補完(setdefault)は上書きしないため、
    # 実際に不一致のトークンで検証できる。
    form = {
        "bust": "84", "waist": "68", "hip": "92", "height": "160",
        "sleeve_length": "54", "shoulder_width": "37",
        "mode": "manual", "neckline": "round_neck",
        "sleeve_style": "straight", "skirt_style": "flare",
        "csrf_token": "this-is-not-the-right-token",
    }
    response = client.post("/api/generate", data=form)
    assert response.status_code == 400
    assert response.get_json()["ok"] is False


def test_post_with_another_sessions_token_is_rejected():
    # セッションAで発行されたトークンを、無関係のセッションBのフォームに
    # 貼り付けても通らないことを確認する(トークンがセッションに紐づいている
    # ことの確認)。
    client_a = app_module.app.test_client()
    token_a = _extract_meta_csrf_token(client_a.get("/").get_data(as_text=True))

    client_b = app_module.app.test_client()
    client_b.get("/")  # セッションBを発行させる(トークンはA用とは別物のはず)
    form = {
        "bust": "84", "waist": "68", "hip": "92", "height": "160",
        "sleeve_length": "54", "shoulder_width": "37",
        "mode": "manual", "neckline": "round_neck",
        "sleeve_style": "straight", "skirt_style": "flare",
        "csrf_token": token_a,
    }
    response = client_b.post("/api/generate", data=form)
    assert response.status_code == 400
    assert response.get_json()["ok"] is False


def test_login_post_without_csrf_token_redirects_via_query_param_not_flash():
    # /api/以外のフォームPOST(ログイン画面)では、JSONの代わりにリダイレクト
    # でエラーを伝える。ただし`flash()`(セッション書き込み)は使わず、
    # `login_required=1`と同じ考え方でクエリ文字列(`csrf_error=1`)だけを
    # 使う(下の`test_csrf_failure_redirect_does_not_set_a_new_session_cookie`
    # 参照: セッションを書き換えるとCookie無しで届いたリクエストへの応答が
    # 新規セッションのSet-Cookieを持ってしまい、ログイン中の利用者の本物の
    # セッションCookieを上書きしかねない)。
    fresh_client = app_module.app.test_client()
    fresh_client.get("/login")
    response = fresh_client.post(
        "/login", data={"email": "user@example.com", "password": "whatever"},
    )
    assert response.status_code == 302
    assert "csrf_error=1" in response.headers["Location"]


def test_csrf_failure_redirect_does_not_set_a_new_session_cookie():
    # _login_requiredで過去に発見・修正した実バグ(session書き込みを伴う
    # flash()が、Cookie無しで届いたクロスサイトPOSTへの応答に真新しい
    # セッションのSet-Cookieを付与し、それをブラウザが同一オリジンからの
    # 正当な応答として受け取って保存することで、ログイン中の利用者の本物の
    # セッションCookieを上書きしてしまう=強制ログアウト)と、全く同じ罠に
    # `_csrf_protect`が陥っていないことを確認する回帰テスト。
    #
    # SameSite=Laxにより、他サイトからの自動送信フォームによるクロスサイト
    # POSTはそもそも本物のセッションCookieを伴わずに届く。ここではCookie無し
    # の`fresh_client`でその状況を再現し、CSRF検証に失敗した応答が
    # Set-Cookieを一切含まないこと(=セッションを変更していないこと)を確認する。
    fresh_client = app_module.app.test_client()
    response = fresh_client.post(
        "/login", data={"email": "user@example.com", "password": "whatever"},
    )
    assert response.status_code == 302
    assert "Set-Cookie" not in response.headers
    assert "csrf_error=1" in response.headers["Location"]


def test_csrf_error_notice_is_shown_via_query_param_without_using_session(client):
    # `login_required=1`と同じパターン: クエリ文字列だけで通知を出し、
    # flash()(session書き込み)は使わない。
    body = client.get("/?csrf_error=1").get_data(as_text=True)
    assert "セキュリティ確認に失敗しました" in body


def test_get_requests_are_never_csrf_checked(client):
    # 安全なメソッド(GET/HEAD/OPTIONS)はそもそもCSRFの対象ではない。
    # トークンを一切渡さなくても、通常通りページが取得できることを確認する。
    fresh_client = app_module.app.test_client()
    response = fresh_client.get("/")
    assert response.status_code == 200
    response = fresh_client.get("/pricing")
    assert response.status_code == 200


def test_billing_webhook_is_exempt_from_csrf_even_without_any_session():
    # StripeサーバーからのWebhook呼び出しはブラウザセッションを経由しない
    # (セッションCookie自体を持たない)ため、CSRFトークンの概念が成立しない。
    # 署名検証(Stripe-Signature)が代わりに保護する(test_billing_and_email.py
    # 参照)。ここでは、webhook自体の正常系検証はそちらに任せ、CSRF検証で
    # 弾かれていない(=exempt扱いされている)ことだけを確認する。少なくとも
    # CSRF由来の400(「セキュリティ確認に失敗しました」)にはならないはず。
    fresh_client = app_module.app.test_client()
    response = fresh_client.post(
        "/billing/webhook", data=b"{}", content_type="application/json",
    )
    body = response.get_json()
    if body is not None and "error" in body:
        assert "セキュリティ確認" not in body["error"]


def test_with_csrf_token_helper_does_not_override_explicit_value():
    # conftestの自動補完ヘルパー自体の単体テスト: 既にcsrf_tokenが
    # 指定されている場合は上書きしない(setdefaultの意図通り)。
    merged = _with_csrf_token({"csrf_token": "explicit-value", "other": "x"})
    assert merged == {"csrf_token": "explicit-value", "other": "x"}


def test_with_csrf_token_helper_fills_in_when_missing():
    merged = _with_csrf_token({"other": "x"})
    assert merged == {"other": "x", "csrf_token": TEST_CSRF_TOKEN}


def test_with_csrf_token_helper_handles_none_data():
    assert _with_csrf_token(None) == {"csrf_token": TEST_CSRF_TOKEN}


def test_with_csrf_token_helper_leaves_raw_bytes_payload_untouched():
    # /billing/webhookのような生JSONペイロード(bytes/str)はフォーム
    # フィールドを持たないため、そのまま返す(補完しようとしない)。
    assert _with_csrf_token(b"{}") == b"{}"
