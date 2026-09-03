"""billing.py — 決済プロバイダの抽象化。

環境変数 STRIPE_SECRET_KEY と STRIPE_PRICE_ID が両方設定されている場合のみ、
実際にStripeのCheckout Session(サブスクリプション)を作成する本物の決済フロー
(`StripeCheckoutProvider`)が有効になる。どちらか一方でも未設定なら、これまで
通りDB上のplan列を即座に切り替えるだけのモック実装(`MockPaymentProvider`)に
フォールバックする。app.py・pricing.html・account.html は、どちらが有効かを
`provider.is_mock` で判定してUI上に明示する。

このモジュール自体がクレジットカード番号などの決済情報を扱うことは無い。
実際の入力はStripeがホストするCheckout画面で行われ、このアプリのサーバーは
一切経由しない(Stripeが推奨する標準的な連携方式で、PCI DSSの適用範囲を
最小化できる)。STRIPE_SECRET_KEY に `sk_test_...` を設定すればテストモード
（実際の課金は発生しない）、`sk_live_...` を設定すれば本番モードになる
（これはStripe側の鍵の種類で決まり、このコードでは判別・強制していない
ため、本番投入時は鍵の管理に注意すること）。

Webhook(`/billing/webhook`, app.py参照)で `checkout.session.completed` と
`customer.subscription.deleted` を受け取り、実際の支払い確定/解約に応じて
DBのplan列を更新する。成功時のリダイレクト先(success_url)だけを頼りに
アップグレードを確定させると、ユーザーがリダイレクトを中断した場合に
支払い済みなのにplanが更新されないままになりうるため、正式な確定は
Webhook側で行う設計にしている。
"""

from __future__ import annotations
import os
from abc import ABC, abstractmethod
from typing import Any


class PaymentProvider(ABC):
    is_mock: bool = True

    @abstractmethod
    def start_checkout(self, user: Any, success_url: str, cancel_url: str) -> str:
        """アップグレード開始用のリダイレクト先URLを返す。"""


class MockPaymentProvider(PaymentProvider):
    """決済ゲートウェイ無しの、テストモードの即時切り替え。"""

    is_mock = True

    def start_checkout(self, user: Any, success_url: str, cancel_url: str) -> str:
        # 実際の決済を経由しない。呼び出し側(app.py)がこのURLへのPOSTを
        # 受けてすぐにplanを切り替える(既存の /account/upgrade の挙動)。
        return success_url


class StripeCheckoutProvider(PaymentProvider):
    """実際にStripeのCheckout Session(サブスクリプション)を作成する実装。"""

    is_mock = False

    def __init__(self, secret_key: str, price_id: str):
        import stripe  # 遅延importにして、未設定時にstripeパッケージが無くても動くようにする
        self._stripe = stripe
        self._stripe.api_key = secret_key
        self.price_id = price_id

    def start_checkout(self, user: Any, success_url: str, cancel_url: str) -> str:
        kwargs = {
            "mode": "subscription",
            "line_items": [{"price": self.price_id, "quantity": 1}],
            "success_url": success_url,
            "cancel_url": cancel_url,
            "client_reference_id": str(user.id),
        }
        if user.stripe_customer_id:
            kwargs["customer"] = user.stripe_customer_id
        else:
            kwargs["customer_email"] = user.email
        session = self._stripe.checkout.Session.create(**kwargs)
        return session.url

    def construct_webhook_event(self, payload: bytes, sig_header: str, webhook_secret: str):
        return self._stripe.Webhook.construct_event(payload, sig_header, webhook_secret)

    def cancel_subscription(self, subscription_id: str) -> None:
        # 実際に本物のstripeライブラリの例外クラス(stripe.InvalidRequestError,
        # code="resource_missing")を使って再現・確認した実バグの修正:
        # Stripeダッシュボードから利用者やサポートが直接キャンセルした場合や、
        # 支払いリトライを使い切ってStripe側で既に失効している場合など、
        # 何らかの理由でサブスクリプションがStripe側に既に存在しない状態で
        # `/account/downgrade`が呼ばれると、以前は`Subscription.cancel()`の
        # 例外がそのままapp.py側の`except Exception`まで伝播し、「解約処理に
        # 失敗しました」という汎用エラーになって処理を中断していた。この結果、
        # ローカルDBのplanは"pro"のまま更新されず、しかも再試行しても全く同じ
        # 理由で必ず失敗するため、利用者はUIから永久にFreeプランへ戻れなくなる
        # (サポートへの問い合わせが必須になる)ことを、本物の
        # stripe.InvalidRequestErrorを`Subscription.cancel`から発生させて確認した。
        # 呼び出し元の意図は「このサブスクリプションが有効でない状態にする」こと
        # であり、"resource_missing"(=対象が既に存在しない)は既にその目的が
        # 達成されている状態を意味するため、失敗ではなく冪等な成功として扱う。
        # それ以外の例外(認証エラー・ネットワーク障害等、実際にキャンセルできて
        # いない可能性がある場合)は、これまで通りそのまま呼び出し元に伝播させ、
        # ローカルのplanを不用意にfreeへ更新しない安全側の挙動を維持する。
        try:
            self._stripe.Subscription.cancel(subscription_id)
        except self._stripe.InvalidRequestError as exc:
            if getattr(exc, "code", None) != "resource_missing":
                raise


def get_default_provider() -> PaymentProvider:
    secret_key = os.environ.get("STRIPE_SECRET_KEY")
    price_id = os.environ.get("STRIPE_PRICE_ID")
    if secret_key and price_id:
        return StripeCheckoutProvider(secret_key, price_id)
    return MockPaymentProvider()
