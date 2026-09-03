"""test_proxy_headers.py — リバースプロキシ配下でのURL生成(スキーム/ホスト)の回帰テスト。

実際にPATTERNFORGE_FORCE_HTTPS=1・PATTERNFORGE_TRUST_PROXY_HEADERS=1を設定して
開発用サーバを起動し、本番でよくある構成(nginx等がTLSを終端し、アプリへは
平文HTTPで転送する)を想定して`X-Forwarded-Proto: https`・
`X-Forwarded-Host: real-service.example.com`付きで`/forgot-password`へ実際に
POSTしたところ、メール本文に載る再設定URLが`http://127.0.0.1:5000/...`という、
外部の利用者からはアクセスできない/HTTPSの意図に反するリンクになる実バグを
見つけた(`app.py`参照)。`werkzeug.middleware.proxy_fix.ProxyFix`を
`PATTERNFORGE_TRUST_PROXY_HEADERS=1`のときだけ適用することで修正した。
"""

from werkzeug.middleware.proxy_fix import ProxyFix

import app as app_module


def _extract_reset_url(body: str) -> str:
    import re
    match = re.search(r"(https?://\S+/reset-password/\S+)", body)
    assert match, f"reset-password URLがメール本文に見つかりません: {body!r}"
    return match.group(1)


def test_reset_link_uses_forwarded_https_scheme_and_host_when_trust_proxy_headers_enabled(
    client, monkeypatch
):
    """PATTERNFORGE_TRUST_PROXY_HEADERS=1相当(ProxyFix適用)のとき、信頼できる
    単一のリバースプロキシが付けたX-Forwarded-Proto/X-Forwarded-Hostに従って
    外部向けのURL(スキーム・ホスト名)が正しく生成されることを確認する
    (実際にこのヘッダー無しでは"http://127.0.0.1:5000/..."のような、外部の
    利用者には無意味なリンクになっていた実バグの回帰テスト)。
    """
    original_wsgi_app = app_module.app.wsgi_app
    monkeypatch.setattr(
        app_module.app, "wsgi_app",
        ProxyFix(original_wsgi_app, x_for=0, x_proto=1, x_host=1, x_port=0, x_prefix=0),
    )

    client.post("/signup", data={"email": "proxyuser@example.com", "password": "password123"})
    app_module.mail.sent.clear()
    client.post(
        "/forgot-password",
        data={"email": "proxyuser@example.com"},
        headers={
            "X-Forwarded-Proto": "https",
            "X-Forwarded-Host": "real-service.example.com",
        },
    )
    assert len(app_module.mail.sent) == 1
    reset_url = _extract_reset_url(app_module.mail.sent[0]["body"])
    assert reset_url.startswith("https://real-service.example.com/reset-password/")


def test_reset_link_ignores_forwarded_headers_when_trust_proxy_headers_disabled(client):
    """PATTERNFORGE_TRUST_PROXY_HEADERS未設定(既定)の場合、ProxyFixは適用
    されていないため、クライアントが自由に送れるX-Forwarded-Proto/Hostを
    そのまま信用してURLのスキーム/ホストを書き換えたりはしない
    (信頼できるプロキシを経由していない環境で、これらのヘッダーを鵜呑みに
    すると外部から偽装されうるため)。既定構成でのテストクライアントの
    ホスト("localhost")のままであることを確認する。
    """
    client.post("/signup", data={"email": "notrust@example.com", "password": "password123"})
    app_module.mail.sent.clear()
    client.post(
        "/forgot-password",
        data={"email": "notrust@example.com"},
        headers={
            "X-Forwarded-Proto": "https",
            "X-Forwarded-Host": "attacker-controlled.example.com",
        },
    )
    assert len(app_module.mail.sent) == 1
    reset_url = _extract_reset_url(app_module.mail.sent[0]["body"])
    assert "attacker-controlled.example.com" not in reset_url
