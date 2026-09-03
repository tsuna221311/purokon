import stripe

import billing as billing_module


def test_get_default_provider_is_mock_when_secret_key_missing(monkeypatch):
    monkeypatch.delenv("STRIPE_SECRET_KEY", raising=False)
    monkeypatch.setenv("STRIPE_PRICE_ID", "price_123")
    provider = billing_module.get_default_provider()
    assert isinstance(provider, billing_module.MockPaymentProvider)
    assert provider.is_mock is True


def test_get_default_provider_is_mock_when_price_id_missing(monkeypatch):
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_123")
    monkeypatch.delenv("STRIPE_PRICE_ID", raising=False)
    provider = billing_module.get_default_provider()
    assert isinstance(provider, billing_module.MockPaymentProvider)


def test_get_default_provider_builds_stripe_provider_when_both_configured(monkeypatch):
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_123")
    monkeypatch.setenv("STRIPE_PRICE_ID", "price_123")
    provider = billing_module.get_default_provider()
    assert isinstance(provider, billing_module.StripeCheckoutProvider)
    assert provider.is_mock is False
    assert provider.price_id == "price_123"


def test_mock_provider_start_checkout_returns_success_url_unchanged():
    provider = billing_module.MockPaymentProvider()

    class _FakeUser:
        id = 1
        email = "person@example.com"
        stripe_customer_id = None

    url = provider.start_checkout(_FakeUser(), "https://example.com/success", "https://example.com/cancel")
    assert url == "https://example.com/success"


# ---------------------------------------------------------------------------
# cancel_subscription() — 実際に本物のstripeライブラリの例外クラスを使い、
# 「Stripe側では既にサブスクリプションが存在しない状態でキャンセルを試みる」
# ケースを再現する(round30で発見・修正した実バグ。app.pyの/account/downgrade
# 経由のend-to-endテストはtest_billing_and_email.pyにある)。
# ---------------------------------------------------------------------------

def _make_provider(monkeypatch, cancel_side_effect):
    provider = billing_module.StripeCheckoutProvider(secret_key="sk_test_fake", price_id="price_fake")
    monkeypatch.setattr(stripe.Subscription, "cancel", staticmethod(cancel_side_effect))
    return provider


def test_cancel_subscription_treats_resource_missing_as_already_cancelled(monkeypatch):
    """Stripeダッシュボードから既に手動キャンセルされていた等、実際には
    サブスクリプションがStripe側にもう存在しない状態(本物のstripeライブラリが
    投げる`InvalidRequestError(code="resource_missing")`で再現)では、
    キャンセルの目的(=サブスクリプションが無効な状態にすること)は既に
    達成されているとみなし、例外を伝播させずに正常終了すること。
    """
    def _raise_resource_missing(subscription_id, **kwargs):
        raise stripe.InvalidRequestError(
            f"No such subscription: '{subscription_id}'", param="subscription", code="resource_missing",
        )

    provider = _make_provider(monkeypatch, _raise_resource_missing)
    provider.cancel_subscription("sub_alreadygone")  # 例外を投げなければ成功


def test_cancel_subscription_still_raises_for_other_invalid_request_errors(monkeypatch):
    """resource_missing以外のInvalidRequestError(例: パラメータ不正等)は、
    本当にキャンセルできていない可能性があるため、これまで通り呼び出し元に
    伝播させる(=フェイルセーフを壊さないことの確認)。
    """
    def _raise_other(subscription_id, **kwargs):
        raise stripe.InvalidRequestError("bad request", param="subscription_id", code="parameter_invalid")

    provider = _make_provider(monkeypatch, _raise_other)
    try:
        provider.cancel_subscription("sub_x")
    except stripe.InvalidRequestError as exc:
        assert exc.code == "parameter_invalid"
    else:
        raise AssertionError("resource_missing以外のInvalidRequestErrorは再送出されるべき")


def test_cancel_subscription_still_raises_for_network_errors(monkeypatch):
    """ネットワーク障害等、キャンセルが実際に成功したか不明な例外はそのまま
    伝播させ、ローカルのplanを不用意にfreeへ更新しない安全側の挙動を維持する。
    """
    def _raise_network_error(subscription_id, **kwargs):
        raise stripe.APIConnectionError("network error")

    provider = _make_provider(monkeypatch, _raise_network_error)
    try:
        provider.cancel_subscription("sub_y")
    except stripe.APIConnectionError:
        pass
    else:
        raise AssertionError("ネットワーク障害は再送出されるべき")
