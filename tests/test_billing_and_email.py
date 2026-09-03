import re
import threading
import time

import stripe

import app as app_module
import billing as billing_module
from tests.conftest import TEST_CSRF_TOKEN


def _signup(client, email="user@example.com", password="password123"):
    return client.post("/signup", data={"email": email, "password": password}, follow_redirects=True)


def _extract_url(body: str, path_prefix: str) -> str:
    match = re.search(rf"(https?://\S*{re.escape(path_prefix)}\S*)", body)
    assert match, f"{path_prefix} を含むURLがメール本文に見つかりません: {body!r}"
    return match.group(1)


def _path_only(url: str) -> str:
    # test_clientはホスト名を無視して問題なくpathだけのリクエストとして送れる。
    return "/" + url.split("/", 3)[3]


# ---------------------------------------------------------------------------
# メールアドレス確認
# ---------------------------------------------------------------------------

def test_signup_sends_verification_email(client):
    _signup(client)
    assert len(app_module.mail.sent) == 1
    message = app_module.mail.sent[0]
    assert message["to"] == "user@example.com"
    assert "確認" in message["subject"]


def test_verify_link_marks_email_verified(client):
    _signup(client)
    verify_path = _path_only(_extract_url(app_module.mail.sent[0]["body"], "/verify/"))

    assert app_module.db.get_user_by_email("user@example.com").email_verified is False
    account_before = client.get("/account")
    assert "確認メールを再送する".encode() in account_before.data

    response = client.get(verify_path, follow_redirects=True)
    assert response.status_code == 200
    assert app_module.db.get_user_by_email("user@example.com").email_verified is True

    account_after = client.get("/account")
    assert "確認メールを再送する".encode() not in account_after.data


def test_verify_link_cannot_be_reused(client):
    _signup(client)
    verify_path = _path_only(_extract_url(app_module.mail.sent[0]["body"], "/verify/"))
    client.get(verify_path)
    second_use = client.get(verify_path, follow_redirects=True)
    # 2回目は「無効」エラーになる(ページ自体は200で表示されるが、確認済みのまま変化は無い)
    assert second_use.status_code == 200
    assert app_module.db.get_user_by_email("user@example.com").email_verified is True


def test_invalid_verify_token_shows_error_not_crash(client):
    response = client.get("/verify/this-token-does-not-exist", follow_redirects=True)
    assert response.status_code == 200


def test_verify_link_still_shows_success_after_automated_prefetch_uses_it_first(client, monkeypatch):
    """実際に見つかった不具合の回帰テスト(store.Store.peek_verify_token_user_id
    のdocstring・app.pyのverify_email参照)。

    企業のメールセキュリティゲートウェイ(Microsoft Defender for Office 365の
    Safe Links等)は、利用者が実際にクリックする前にメール内のリンクを
    自動的に「事前アクセス」してマルウェア検査を行うことが広く知られている。
    `/verify/<token>`はGETだけでトークンを消費する設計のため、以前はこの
    自動prefetchが先にトークンを使用済みにしてしまい、利用者本人が後から
    同じリンクを開くと、実際には確認が完了しているにもかかわらず
    「リンクが無効、または有効期限が切れています」という誤った失敗表示に
    なっていた。実際に(1.本人とは別のクライアントが先にGET
    2.本人が同じリンクを開く)という手順で再現・確認した上で修正した。
    """
    _signup(client)
    verify_path = _path_only(_extract_url(app_module.mail.sent[0]["body"], "/verify/"))

    # 1. 企業のメールセキュリティゲートウェイが、利用者より先に自動でこの
    #    URLへアクセスする(Cookieを持たない別クライアントとしてシミュレート)。
    scanner_client = app_module.app.test_client()
    scanner_response = scanner_client.get(verify_path, follow_redirects=True)
    assert scanner_response.status_code == 200
    assert app_module.db.get_user_by_email("user@example.com").email_verified is True

    # 2. 利用者本人が実際にリンクをクリックする。修正前はここで
    #    「無効、または有効期限が切れています」という誤ったエラーになった。
    user_response = client.get(verify_path, follow_redirects=True)
    body = user_response.get_data(as_text=True)
    assert "確認しました" in body
    assert "無効、または有効期限が切れています" not in body


def test_resend_verification_requires_login(client):
    response = client.post("/account/resend-verification")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_resend_verification_is_rate_limited_immediately_after_signup(client):
    # サインアップ直後は既に確認メールを送っているため、間を置かずに再送
    # しようとした場合はクールダウン(store.py: seconds_since_last_token)に
    # よってブロックされ、2通目は送られない(第2回監査 指摘#3への対応)。
    _signup(client)
    assert len(app_module.mail.sent) == 1
    response = client.post("/account/resend-verification", follow_redirects=True)
    assert len(app_module.mail.sent) == 1
    assert "しばらく" in response.get_data(as_text=True)


def test_resend_verification_sends_another_email_after_cooldown(client, monkeypatch):
    _signup(client)
    assert len(app_module.mail.sent) == 1
    # 実際に60秒待たずに、クールダウン経過後の挙動だけを検証する。
    monkeypatch.setattr(app_module, "_EMAIL_TOKEN_COOLDOWN_SECONDS", 0)
    client.post("/account/resend-verification")
    assert len(app_module.mail.sent) == 2


def test_resend_verification_ip_rate_limit(client, monkeypatch):
    # ユーザー単位のクールダウンを無効化しても、短時間に大量に叩けば
    # IPベースのレート制限(_email_send_rate_limiter)で止まることを確認する。
    _signup(client)
    monkeypatch.setattr(app_module, "_EMAIL_TOKEN_COOLDOWN_SECONDS", 0)
    for _ in range(10):
        client.post("/account/resend-verification")
    assert len(app_module.mail.sent) < 11  # どこかでIPレート制限に引っかかっている


def test_resend_verification_cooldown_holds_under_concurrent_requests(client, monkeypatch):
    """実際に本物のスレッドで`/account/resend-verification`へ20並行でPOSTして
    見つかった実バグの回帰テスト(HTTP経路でのエンドツーエンド確認)。

    以前は`store.Store.seconds_since_last_token()`(単純なSELECT)でクール
    ダウンを確認してから、別途`create_email_token()`(単純なINSERT)で
    トークンを発行する2段構えだったため、ほぼ同時に届いた並行リクエストの
    多くが「まだ誰も新しいトークンを発行していない」時点の古い確認結果を
    見てしまい、20回中18回もクールダウンをすり抜けてメールを送信してしまう
    (第2回監査 指摘#3で要求された、同一被害者へのメール爆撃防止が並行
    リクエストの下では実質的に機能していなかった)ことを実際に確認した。
    `store.Store.try_create_email_token_with_cooldown()`でクールダウン確認と
    トークン発行を1つのDBトランザクションにまとめて修正した。
    """
    _signup(client)
    assert len(app_module.mail.sent) == 1  # サインアップ直後の確認メール1件
    # ログイン状態はセッションCookieに載っているため、他スレッドからも
    # 同じ「ログイン済みユーザー」として振る舞わせるにはCookieを引き継いだ
    # 別のテストクライアントを使う(Flaskのテストクライアントはコンテキスト
    # スタックを内部で管理しており、1つのインスタンスを複数スレッドから
    # 同時にopen()するとcontextvarsが壊れるため、スレッドごとに新しい
    # クライアントを作る)。
    session_cookie = client.get_cookie("session")
    assert session_cookie is not None

    def attempt():
        thread_client = app_module.app.test_client()
        thread_client.set_cookie("session", session_cookie.value)
        # round6で追加したCSRF検証: session_cookieは`client`(このfixtureの
        # postラッパー経由でTEST_CSRF_TOKENがセッションに書き込まれた)から
        # コピーしたものなので、フォーム側にも同じ固定トークンを含める。
        thread_client.post("/account/resend-verification", data={"csrf_token": TEST_CSRF_TOKEN})

    threads = [threading.Thread(target=attempt) for _ in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # サインアップ時の1件 + 再送クールダウンをすり抜けずに済んだ場合の
    # 最大1件 = 合計2件以下(実際には1件になるはずだが、レート制限等の
    # タイミングでゼロになる可能性も許容する)。
    assert len(app_module.mail.sent) <= 2


# ---------------------------------------------------------------------------
# パスワード再設定
# ---------------------------------------------------------------------------

def test_forgot_password_sends_reset_email_for_known_user(client):
    _signup(client)
    app_module.mail.sent.clear()
    response = client.post("/forgot-password", data={"email": "user@example.com"}, follow_redirects=True)
    assert response.status_code == 200
    assert len(app_module.mail.sent) == 1
    assert "再設定" in app_module.mail.sent[0]["subject"]


def test_forgot_password_cooldown_holds_under_concurrent_requests(client, monkeypatch):
    """`test_resend_verification_cooldown_holds_under_concurrent_requests`と
    同じ実バグ・同じ修正の、`/forgot-password`側での回帰テスト。以前は
    `seconds_since_last_token()`→`create_email_token()`の2段構えだった
    ため、同一メールアドレスへの並行リクエストでクールダウンをすり抜けて
    複数の再設定メールが送られてしまっていた。
    """
    _signup(client)
    app_module.mail.sent.clear()
    # IPベースのレート制限(_email_send_rate_limiter、60秒に5回)に邪魔されず
    # クールダウン自体の並行性を検証するため、ここでは無効化する。
    monkeypatch.setattr(app_module, "_email_send_rate_limiter",
                         app_module._RateLimiter("email_send", max_requests=10_000, window_seconds=60.0))

    def attempt():
        # Flaskのテストクライアントは内部でコンテキストスタックを管理して
        # いるため、1つのインスタンスを複数スレッドから同時にopen()すると
        # contextvarsが壊れる(スレッドごとに新しいクライアントを作る)。
        # round6で追加したCSRF検証に対応するため、各クライアントのセッションに
        # テスト専用の固定トークンを直接書き込んでからフォームにも含める
        # (実ブラウザなら事前にGET /forgot-passwordでトークンを受け取るのと
        # 等価だが、20スレッド分のGETで無駄なノイズを増やしたくないため
        # ここではセッションへ直接書き込む簡略化を行っている)。
        fresh_client = app_module.app.test_client()
        with fresh_client.session_transaction() as sess:
            sess["csrf_token"] = TEST_CSRF_TOKEN
        fresh_client.post("/forgot-password", data={
            "email": "user@example.com", "csrf_token": TEST_CSRF_TOKEN,
        })

    threads = [threading.Thread(target=attempt) for _ in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(app_module.mail.sent) == 1


def test_forgot_password_does_not_leak_whether_email_exists(client):
    # 存在しないメールアドレスでも、存在する場合と同じ200+同じ文言になる
    # (メールアドレスが登録済みかどうかを外部から探索できないようにするため)。
    known = client.post("/forgot-password", data={"email": "nobody@example.com"}, follow_redirects=True)
    assert known.status_code == 200
    assert len(app_module.mail.sent) == 0  # 実際には送っていないが、レスポンス文言は変えない
    assert "送信しました".encode() in known.data


def test_forgot_password_does_not_leak_whether_email_exists_via_timing(client, monkeypatch):
    # 実際にaiosmtpdでローカルSMTPシンクを立て、PATTERNFORGE_MAIL_BACKEND=smtp
    # (本番で推奨している構成)で実際にサーバを起動して計測したところ、実在する
    # メールアドレスへのリクエストは実際にメール送信を行う分平均約20ms、実在
    # しないメールアドレスの場合は平均約10msと、表示文言は同じでも応答時間に
    # 約2倍の差があることを確認した実バグ(本物のSMTPプロバイダ相手ではこの
    # 差はさらに大きくなりうる)。`_FORGOT_PASSWORD_MIN_RESPONSE_SECONDS`で
    # 応答時間に下限を設け、どちらの分岐でも最低その時間がかかるようにする
    # ことで応答時間からの探索を防ぐ。ここでは下限を有効にした状態で、
    # 存在するメールアドレス・存在しないメールアドレスの両方の応答時間が
    # 下限とほぼ一致する(=分岐による差がほぼ消える)ことを確認する。
    monkeypatch.setattr(app_module, "_FORGOT_PASSWORD_MIN_RESPONSE_SECONDS", 0.2)
    _signup(client)

    def _elapsed(email):
        start = time.perf_counter()
        client.post("/forgot-password", data={"email": email})
        return time.perf_counter() - start

    existing_elapsed = _elapsed("user@example.com")
    nonexistent_elapsed = _elapsed("nobody.at.all@example.com")

    for elapsed in (existing_elapsed, nonexistent_elapsed):
        assert elapsed >= 0.2
        assert elapsed < 0.2 + 0.15  # 下限+ゆとり。実処理コストの分岐差はこの範囲に収まる


def test_reset_password_flow_end_to_end(client):
    _signup(client)
    app_module.mail.sent.clear()
    client.post("/forgot-password", data={"email": "user@example.com"})
    reset_path = _path_only(_extract_url(app_module.mail.sent[0]["body"], "/reset-password/"))

    client.post("/logout")
    response = client.post(reset_path, data={"password": "new-password-123"}, follow_redirects=True)
    assert response.status_code == 200

    old_login = client.post("/login", data={"email": "user@example.com", "password": "password123"})
    assert old_login.status_code == 400

    new_login = client.post("/login", data={"email": "user@example.com", "password": "new-password-123"},
                             follow_redirects=True)
    assert new_login.status_code == 200


def test_reset_password_token_cannot_be_reused(client):
    _signup(client)
    app_module.mail.sent.clear()
    client.post("/forgot-password", data={"email": "user@example.com"})
    reset_path = _path_only(_extract_url(app_module.mail.sent[0]["body"], "/reset-password/"))

    client.post(reset_path, data={"password": "first-new-password"})
    second_attempt = client.post(reset_path, data={"password": "second-new-password"}, follow_redirects=True)
    assert second_attempt.status_code == 200

    login_with_second = client.post("/login", data={"email": "user@example.com", "password": "second-new-password"})
    assert login_with_second.status_code == 400  # 2回目は無効なトークンとして拒否されている


def test_password_reset_invalidates_other_existing_sessions(client):
    # 第2回監査 指摘#1: パスワード再設定前に発行されたセッションCookieが
    # (例えば盗まれて)残っていても、再設定後はそのCookieでログイン状態を
    # 維持できてはならない。store.py の session_version をパスワード変更の
    # たびにインクリメントし、app.py の _current_user() で不一致を検出して
    # 無効化することで防いでいる。
    _signup(client)
    stale_session_cookie = client.get_cookie("session").value
    assert stale_session_cookie is not None

    app_module.mail.sent.clear()
    client.post("/forgot-password", data={"email": "user@example.com"})
    reset_path = _path_only(_extract_url(app_module.mail.sent[0]["body"], "/reset-password/"))
    client.post("/logout")
    client.post(reset_path, data={"password": "new-password-123"})

    with app_module.app.test_client() as attacker_client:
        attacker_client.set_cookie("session", stale_session_cookie)
        response = attacker_client.get("/account", follow_redirects=False)
        # session_versionが不一致になっているため、ログイン必須ページに
        # アクセスすると未ログイン扱いでリダイレクトされる。
        assert response.status_code == 302
        assert "/login" in response.headers["Location"]


def test_reset_password_rejects_short_password(client):
    _signup(client)
    app_module.mail.sent.clear()
    client.post("/forgot-password", data={"email": "user@example.com"})
    reset_path = _path_only(_extract_url(app_module.mail.sent[0]["body"], "/reset-password/"))
    response = client.post(reset_path, data={"password": "short"})
    assert response.status_code == 400


def test_reset_password_link_survives_a_failed_short_password_attempt(client):
    """実際にサーバーを起動しcurlで手順を再現して見つけた不具合の回帰テスト。

    上の test_reset_password_rejects_short_password は「短いパスワードは
    400で拒否される」ことしか確認していなかったため、その後にトークンが
    まだ使えるかどうかは検証しておらず、以前の実装(トークンを先に消費して
    からパスワードを検証する)が持っていた不具合をこのテストスイートは
    見つけられなかった。以前の実装では、この関数がやっているのと全く同じ
    手順(短いパスワードで1回失敗させた直後に、同じリンクで有効な
    パスワードを送る)を実行すると、2回目が「リンクが無効、または期限切れ」
    という誤ったエラーになり、実際にはパスワードは変更されない
    (旧パスワードでログインできてしまう)ままだった。
    """
    _signup(client)
    app_module.mail.sent.clear()
    client.post("/forgot-password", data={"email": "user@example.com"})
    reset_path = _path_only(_extract_url(app_module.mail.sent[0]["body"], "/reset-password/"))

    # 1回目: 短すぎるパスワードで失敗する。
    first_attempt = client.post(reset_path, data={"password": "short"})
    assert first_attempt.status_code == 400

    # 2回目: 同じリンクで、今度は有効なパスワードを送ると成功するはず。
    second_attempt = client.post(reset_path, data={"password": "valid-password-2"}, follow_redirects=True)
    assert second_attempt.status_code == 200
    assert "リンクが無効" not in second_attempt.get_data(as_text=True)

    # 実際にパスワードが変更されていること(旧パスワードは無効に、新しい
    # パスワードで実際にログインできる)を確認する。
    old_login = client.post("/login", data={"email": "user@example.com", "password": "password123"})
    assert old_login.status_code == 400
    new_login = client.post("/login", data={"email": "user@example.com", "password": "valid-password-2"})
    assert new_login.status_code == 302


# ---------------------------------------------------------------------------
# Stripe連携（実際のネットワーク呼び出しはせず、フェイクプロバイダで検証）
# ---------------------------------------------------------------------------

class _FakeStripeProvider:
    is_mock = False

    def __init__(self):
        self.checkout_calls = []
        self.cancel_calls = []
        self._next_event = None

    def start_checkout(self, user, success_url, cancel_url):
        self.checkout_calls.append((user.id, success_url, cancel_url))
        return "https://checkout.stripe.example/session/abc123"

    def cancel_subscription(self, subscription_id):
        self.cancel_calls.append(subscription_id)

    def construct_webhook_event(self, payload, sig_header, webhook_secret):
        assert webhook_secret == "whsec_test"
        return self._next_event

    def queue_event(self, event):
        self._next_event = event


def test_account_upgrade_redirects_to_stripe_checkout_when_configured(client, monkeypatch):
    fake_provider = _FakeStripeProvider()
    monkeypatch.setattr(app_module, "payment_provider", fake_provider)
    _signup(client)
    response = client.post("/account/upgrade")
    assert response.status_code == 302
    assert response.headers["Location"] == "https://checkout.stripe.example/session/abc123"
    assert len(fake_provider.checkout_calls) == 1
    # モック実装と違って、リダイレクトの時点ではまだplanを切り替えていない
    # (正式な確定はWebhook側で行う設計)。
    assert app_module.db.get_user_by_email("user@example.com").plan == "free"


def test_billing_webhook_returns_404_when_billing_not_configured(client):
    response = client.post("/billing/webhook", data=b"{}", content_type="application/json")
    assert response.status_code == 404


def test_billing_webhook_upgrades_plan_on_checkout_completed(client, monkeypatch):
    fake_provider = _FakeStripeProvider()
    monkeypatch.setattr(app_module, "payment_provider", fake_provider)
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test")
    _signup(client)
    user = app_module.db.get_user_by_email("user@example.com")

    fake_provider.queue_event({
        "type": "checkout.session.completed",
        "created": 1000,
        "data": {"object": {
            "client_reference_id": str(user.id),
            "customer": "cus_123",
            "subscription": "sub_456",
        }},
    })
    response = client.post("/billing/webhook", data=b"{}", content_type="application/json",
                            headers={"Stripe-Signature": "t=1,v1=fake"})
    assert response.status_code == 200
    updated = app_module.db.get_user(user.id)
    assert updated.plan == "pro"
    assert updated.stripe_customer_id == "cus_123"
    assert updated.stripe_subscription_id == "sub_456"


def test_billing_webhook_downgrades_plan_on_subscription_deleted(client, monkeypatch):
    fake_provider = _FakeStripeProvider()
    monkeypatch.setattr(app_module, "payment_provider", fake_provider)
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test")
    _signup(client)
    user = app_module.db.get_user_by_email("user@example.com")
    app_module.db.set_stripe_ids(user.id, "cus_123", "sub_456")
    app_module.db.set_plan(user.id, "pro")

    fake_provider.queue_event({
        "type": "customer.subscription.deleted",
        "created": 1000,
        "data": {"object": {"customer": "cus_123"}},
    })
    response = client.post("/billing/webhook", data=b"{}", content_type="application/json",
                            headers={"Stripe-Signature": "t=1,v1=fake"})
    assert response.status_code == 200
    assert app_module.db.get_user(user.id).plan == "free"


def test_billing_webhook_downgrades_plan_on_subscription_past_due(client, monkeypatch):
    # 実際に本物のstripeライブラリ・本物のHMAC署名でWebhookイベントを構築し、
    # 支払い失敗(invoice.payment_failed)後にサブスクリプションがpast_due状態
    # になる(customer.subscription.updated)という実際のStripeの流れをサーバに
    # 送ったところ、以前はこのイベント種別を一切処理しておらず、支払いが
    # 失敗してもplanが"pro"のままで無制限に生成し続けられる状態だった実バグ。
    # Stripeは支払い失敗の直後にcustomer.subscription.deletedを送るわけでは
    # なく(リトライ期間があり、設定によっては自動キャンセルされずunpaidの
    # まま残ることもある)、代わりにこのイベントのstatusで状態変化を追う
    # 必要があった。
    fake_provider = _FakeStripeProvider()
    monkeypatch.setattr(app_module, "payment_provider", fake_provider)
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test")
    _signup(client)
    user = app_module.db.get_user_by_email("user@example.com")
    app_module.db.set_stripe_ids(user.id, "cus_123", "sub_456")
    app_module.db.set_plan(user.id, "pro")

    fake_provider.queue_event({
        "type": "customer.subscription.updated",
        "created": 1000,
        "data": {"object": {"customer": "cus_123", "id": "sub_456", "status": "past_due"}},
    })
    response = client.post("/billing/webhook", data=b"{}", content_type="application/json",
                            headers={"Stripe-Signature": "t=1,v1=fake"})
    assert response.status_code == 200
    assert app_module.db.get_user(user.id).plan == "free"


def test_billing_webhook_restores_plan_when_subscription_becomes_active_again(client, monkeypatch):
    # 支払いが復旧してサブスクリプションがactiveに戻った場合、同じイベント
    # 種別で自動的にproへ復帰することも確認する(past_dueで一度free化した
    # ユーザーが、リトライ課金の成功後もfreeに固定されてしまう回帰を防ぐ)。
    fake_provider = _FakeStripeProvider()
    monkeypatch.setattr(app_module, "payment_provider", fake_provider)
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test")
    _signup(client)
    user = app_module.db.get_user_by_email("user@example.com")
    app_module.db.set_stripe_ids(user.id, "cus_123", "sub_456")
    app_module.db.set_plan(user.id, "free")

    fake_provider.queue_event({
        "type": "customer.subscription.updated",
        "created": 1000,
        "data": {"object": {"customer": "cus_123", "id": "sub_456", "status": "active"}},
    })
    response = client.post("/billing/webhook", data=b"{}", content_type="application/json",
                            headers={"Stripe-Signature": "t=1,v1=fake"})
    assert response.status_code == 200
    assert app_module.db.get_user(user.id).plan == "pro"


def test_billing_webhook_does_not_downgrade_plan_on_stale_out_of_order_event(client, monkeypatch):
    """実際にサーバーを起動し、本物のstripeライブラリ・本物のHMAC署名で
    2つの`customer.subscription.updated`イベントを構築してcurlで送り、
    再現・確認した実バグの回帰テスト(このテストではHTTP経路をエンドツー
    エンドで確認するためフェイクプロバイダを使う)。

    Stripeの実際のタイムライン: 支払いが失敗して生成時刻t1の"past_due"
    イベントが作られ(A)、その後リトライ課金が成功して生成時刻t2(>t1)の
    "active"イベントが作られる(B)。ネットワークの遅延や再送によって、
    実際にはBがサーバに先に届き、Aが(古い再送として)後から届くという
    配信順序の逆転がStripeでは公式に許容されている。以前はどちらのイベント
    が先に届いたかだけでplanが決まってしまい、この手順ではBの後にAが処理
    されて誤ってplanが"free"に固定される実バグがあった。
    """
    fake_provider = _FakeStripeProvider()
    monkeypatch.setattr(app_module, "payment_provider", fake_provider)
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test")
    _signup(client)
    user = app_module.db.get_user_by_email("user@example.com")
    app_module.db.set_stripe_ids(user.id, "cus_123", "sub_456")
    app_module.db.apply_billing_event(user.id, 500, "pro")

    # B: 新しい(生成時刻が新しい)イベント。実際の直近状態を表す。
    fake_provider.queue_event({
        "type": "customer.subscription.updated",
        "created": 900,
        "data": {"object": {"customer": "cus_123", "id": "sub_456", "status": "active"}},
    })
    response_b = client.post("/billing/webhook", data=b"{}", content_type="application/json",
                              headers={"Stripe-Signature": "t=1,v1=fake"})
    assert response_b.status_code == 200
    assert app_module.db.get_user(user.id).plan == "pro"

    # A: 古い(生成時刻が古い)イベントが、Bより後にサーバへ届く(再送/遅延を想定)。
    fake_provider.queue_event({
        "type": "customer.subscription.updated",
        "created": 600,
        "data": {"object": {"customer": "cus_123", "id": "sub_456", "status": "past_due"}},
    })
    response_a = client.post("/billing/webhook", data=b"{}", content_type="application/json",
                              headers={"Stripe-Signature": "t=1,v1=fake"})
    assert response_a.status_code == 200  # Stripe向けには200を返し続ける(再送を止める)

    # 古いイベントによってplanが巻き戻っていないこと(実際の直近状態=proのまま)。
    assert app_module.db.get_user(user.id).plan == "pro"


def test_account_downgrade_updates_last_billing_event_at_so_stale_webhook_cannot_revert_it(client, monkeypatch):
    """実際に/account/downgradeへPOSTし、その直後に古いWebhookイベントを
    送って再現・確認した実バグの回帰テスト。

    以前は/account/downgradeの「即時反映」がdb.set_plan()を直接呼んでおり、
    last_billing_event_at(round21で追加したWebhook配信順序保護の基準値)を
    更新しなかった。このため、利用者がキャンセル操作をした直後に、
    キャンセルより前の時点で生成された(=時系列としては古いが、以前の
    last_billing_event_atよりは新しい)active系Webhookイベントが遅延配信
    されると、apply_billing_event()の古さ判定をすり抜けてplanが意図せず
    "pro"に巻き戻ってしまうことを、実際にこの手順(1.Webhookでpro化
    2./account/downgradeでキャンセル 3.キャンセル前に生成された古い
    activeイベントを送信)で確認した。修正後は/account/downgradeも
    apply_billing_event()を通して現在時刻でlast_billing_event_atを
    更新するため、この古いイベントは正しく無視される。
    """
    fake_provider = _FakeStripeProvider()
    monkeypatch.setattr(app_module, "payment_provider", fake_provider)
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test")
    _signup(client)
    user = app_module.db.get_user_by_email("user@example.com")
    app_module.db.set_stripe_ids(user.id, "cus_123", "sub_456")

    # 1. 決済成功Webhook(生成時刻100)でpro化。
    app_module.db.apply_billing_event(user.id, 100, "pro")
    assert app_module.db.get_user(user.id).plan == "pro"

    # 2. 利用者が/account/downgradeでキャンセル操作をする(実際のHTTP経路)。
    response = client.post("/account/downgrade", follow_redirects=True)
    assert response.status_code == 200
    assert app_module.db.get_user(user.id).plan == "free"
    assert fake_provider.cancel_calls == ["sub_456"]

    # 3. キャンセル操作より前(生成時刻150)に作られていたactiveイベントが、
    #    Stripe側の配信遅延で今になって届く。修正前はこれによりplanが
    #    "pro"へ巻き戻ってしまっていた。
    fake_provider.queue_event({
        "type": "customer.subscription.updated",
        "created": 150,
        "data": {"object": {"customer": "cus_123", "id": "sub_456", "status": "active"}},
    })
    response = client.post("/billing/webhook", data=b"{}", content_type="application/json",
                            headers={"Stripe-Signature": "t=1,v1=fake"})
    assert response.status_code == 200

    # planはキャンセル操作の結果である"free"のまま保たれる。
    assert app_module.db.get_user(user.id).plan == "free"


def test_account_downgrade_still_lets_a_later_genuine_cancellation_webhook_confirm_free(client, monkeypatch):
    """/account/downgradeの即時反映後に、正式なcustomer.subscription.deleted
    Webhook(生成時刻が即時反映より新しい)が届く、本来の正常経路が
    問題なく動作することも確認する(古いイベントを無視するようにした
    修正が、新しいイベントまで誤って無視してしまう回帰がないことの確認)。
    """
    fake_provider = _FakeStripeProvider()
    monkeypatch.setattr(app_module, "payment_provider", fake_provider)
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test")
    _signup(client)
    user = app_module.db.get_user_by_email("user@example.com")
    app_module.db.set_stripe_ids(user.id, "cus_123", "sub_456")
    app_module.db.apply_billing_event(user.id, 100, "pro")

    response = client.post("/account/downgrade", follow_redirects=True)
    assert response.status_code == 200
    assert app_module.db.get_user(user.id).plan == "free"

    # 即時反映(生成時刻=リクエスト実行時のtime.time())より後に生成された、
    # 正式なsubscription.deleted Webhookが確定として届く場合。
    fake_provider.queue_event({
        "type": "customer.subscription.deleted",
        "created": time.time() + 10,
        "data": {"object": {"customer": "cus_123", "id": "sub_456"}},
    })
    response = client.post("/billing/webhook", data=b"{}", content_type="application/json",
                            headers={"Stripe-Signature": "t=1,v1=fake"})
    assert response.status_code == 200
    assert app_module.db.get_user(user.id).plan == "free"


def test_account_downgrade_succeeds_even_when_stripe_subscription_is_already_gone(client, monkeypatch):
    """実際に本物のstripeライブラリ(`billing.StripeCheckoutProvider`)を使い、
    Stripeダッシュボードから既に手動キャンセルされていた等、対象の
    サブスクリプションがStripe側にもう存在しない状態
    (`stripe.InvalidRequestError(code="resource_missing")`)で
    `/account/downgrade`を呼んだ場合の挙動を検証する(round30で発見・修正
    した実バグの回帰テスト)。

    修正前は`Subscription.cancel()`のこの例外がそのまま`except Exception`
    まで伝播し、「解約処理に失敗しました」という汎用エラーになって処理が
    中断されていた。ローカルDBのplanは"pro"のまま更新されず、しかも
    再試行しても全く同じ理由で必ず失敗するため、利用者はUIから永久に
    Freeプランへ戻れなくなっていた(実際に本物のstripe.InvalidRequestError
    を`Subscription.cancel`から発生させ、2回連続で試行してどちらも
    "pro"のまま変わらないことを確認して再現した)。
    """
    provider = billing_module.StripeCheckoutProvider(secret_key="sk_test_fake", price_id="price_fake")
    monkeypatch.setattr(app_module, "payment_provider", provider)

    def _raise_resource_missing(subscription_id, **kwargs):
        raise stripe.InvalidRequestError(
            f"No such subscription: '{subscription_id}'", param="subscription", code="resource_missing",
        )

    monkeypatch.setattr(stripe.Subscription, "cancel", staticmethod(_raise_resource_missing))

    _signup(client)
    user = app_module.db.get_user_by_email("user@example.com")
    app_module.db.apply_billing_event(
        user.id, 100.0, "pro", stripe_customer_id="cus_123", stripe_subscription_id="sub_alreadygone",
    )

    response = client.post("/account/downgrade", follow_redirects=True)
    assert response.status_code == 200
    assert "解約処理に失敗しました" not in response.get_data(as_text=True)
    assert app_module.db.get_user(user.id).plan == "free"


def test_account_downgrade_still_reports_failure_for_genuine_stripe_errors(client, monkeypatch):
    """resource_missing以外の失敗(ネットワーク障害・認証エラー等、本当に
    キャンセルできたか分からない場合)では、これまで通りエラーを表示し、
    ローカルのplanを不用意にfreeへ更新しない安全側の挙動を維持することの
    確認(上のテストの修正がフェイルセーフ自体を壊していないことの確認)。
    """
    provider = billing_module.StripeCheckoutProvider(secret_key="sk_test_fake", price_id="price_fake")
    monkeypatch.setattr(app_module, "payment_provider", provider)

    def _raise_network_error(subscription_id, **kwargs):
        raise stripe.APIConnectionError("network error contacting Stripe")

    monkeypatch.setattr(stripe.Subscription, "cancel", staticmethod(_raise_network_error))

    _signup(client)
    user = app_module.db.get_user_by_email("user@example.com")
    app_module.db.apply_billing_event(
        user.id, 100.0, "pro", stripe_customer_id="cus_123", stripe_subscription_id="sub_real_active",
    )

    response = client.post("/account/downgrade", follow_redirects=True)
    assert response.status_code == 200
    assert "解約処理に失敗しました" in response.get_data(as_text=True)
    assert app_module.db.get_user(user.id).plan == "pro"


def test_billing_webhook_subscription_updated_ignores_unknown_customer(client, monkeypatch):
    fake_provider = _FakeStripeProvider()
    monkeypatch.setattr(app_module, "payment_provider", fake_provider)
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test")

    fake_provider.queue_event({
        "type": "customer.subscription.updated",
        "created": 1000,
        "data": {"object": {"customer": "cus_does_not_exist", "id": "sub_x", "status": "past_due"}},
    })
    response = client.post("/billing/webhook", data=b"{}", content_type="application/json",
                            headers={"Stripe-Signature": "t=1,v1=fake"})
    assert response.status_code == 200


def test_billing_webhook_rejects_invalid_signature(client, monkeypatch):
    class _BadSigProvider(_FakeStripeProvider):
        def construct_webhook_event(self, payload, sig_header, webhook_secret):
            raise ValueError("invalid signature")

    monkeypatch.setattr(app_module, "payment_provider", _BadSigProvider())
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test")
    response = client.post("/billing/webhook", data=b"{}", content_type="application/json",
                            headers={"Stripe-Signature": "bad"})
    assert response.status_code == 400


def test_billing_webhook_works_with_real_stripe_object_not_just_plain_dict(client, monkeypatch):
    # 実際に本物のstripeライブラリでWebhookイベントを構築して見つかった実バグの
    # 再発防止テスト。上の一連のテストは`construct_webhook_event`を素の
    # dictを返すモックに置き換えていたため、本物のstripeライブラリが実際に
    # 返す`stripe._stripe_object.StripeObject`(`__getitem__`は使えるが
    # `.get()`は実装されていない)との不整合に気付けなかった。実際に
    # `billing.StripeCheckoutProvider`を本物のsecret_keyで構築し、本物の
    # HMAC署名を計算してPOSTすることで、本番のStripe連携と同じ経路
    # (本物のイベントオブジェクトの型)を通す。以前はここで
    # 「'get' is a dict method, but a StripeObject is not a dict」という
    # AttributeErrorになり500を返していた(=支払い確定Webhookが実際には
    # 一度も成功しない状態だった)。
    import hashlib
    import hmac
    import json
    import time

    provider = billing_module.StripeCheckoutProvider(secret_key="sk_test_fake", price_id="price_fake")
    monkeypatch.setattr(app_module, "payment_provider", provider)
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_realtest")

    _signup(client)
    user = app_module.db.get_user_by_email("user@example.com")

    timestamp = int(time.time())
    payload = json.dumps({
        "id": "evt_real_test",
        "type": "checkout.session.completed",
        "created": timestamp,
        "data": {"object": {
            "client_reference_id": str(user.id),
            "customer": "cus_real123",
            "subscription": "sub_real456",
        }},
    }).encode()
    signature = hmac.new(
        b"whsec_realtest", f"{timestamp}.".encode() + payload, hashlib.sha256
    ).hexdigest()

    response = client.post(
        "/billing/webhook", data=payload, content_type="application/json",
        headers={"Stripe-Signature": f"t={timestamp},v1={signature}"},
    )
    assert response.status_code == 200
    updated = app_module.db.get_user(user.id)
    assert updated.plan == "pro"
    assert updated.stripe_customer_id == "cus_real123"
    assert updated.stripe_subscription_id == "sub_real456"


def test_get_default_provider_falls_back_to_mock_without_config(monkeypatch):
    monkeypatch.delenv("STRIPE_SECRET_KEY", raising=False)
    monkeypatch.delenv("STRIPE_PRICE_ID", raising=False)
    provider = billing_module.get_default_provider()
    assert provider.is_mock is True
