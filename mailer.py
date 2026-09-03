"""mailer.py — メール送信の薄い抽象化。

商用サービス化にあたり、メールアドレス確認・パスワード再設定にはメール送信が
必須になる。本番のSMTP資格情報が無くても開発・デモができるよう、送信先を
切り替え可能にしている。

バックエンド (環境変数 PATTERNFORGE_MAIL_BACKEND):
  - "console"（既定）: 実際には送信せず、サーバーのログに出力するだけ。
    開発・デモ用。このバックエンドの場合のみ、app.py側で確認/再設定URLを
    画面のflashメッセージにも表示する（実際のメール受信箱を用意しなくても
    フローを最後まで試せるようにするため。本番でSMTPを設定すればこの表示は
    出さなくなる）。
  - "smtp": 環境変数で設定したSMTPサーバーで実際にメールを送信する
    (SMTP_HOST, SMTP_PORT, SMTP_USERNAME, SMTP_PASSWORD, SMTP_FROM_ADDRESS,
    SMTP_USE_TLS)。Gmail/SESなど一般的なSMTPエンドポイントであれば、標準
    ライブラリのsmtplibのみで動作する（追加の依存パッケージは不要）。

このモジュールは実際に届くメールの体裁(HTMLメール化、配信停止リンク等)には
関与しない。あくまで「確認/再設定リンクをどう相手に渡すか」を差し替え可能に
するための最小限の層。
"""

from __future__ import annotations
import logging
import os
import smtplib
from abc import ABC, abstractmethod
from email.message import EmailMessage

logger = logging.getLogger(__name__)


class Mailer(ABC):
    #: ConsoleMailerかどうか。app.py側で「画面にもリンクを出す」判断に使う。
    is_console: bool = False

    @abstractmethod
    def send(self, to: str, subject: str, body: str) -> None:
        """メールを送信する。失敗した場合は例外を投げる。"""


class ConsoleMailer(Mailer):
    """実際には送信せず、ログに出力するだけの開発/デモ用実装。"""

    is_console = True

    def send(self, to: str, subject: str, body: str) -> None:
        logger.info(
            "[ConsoleMailer] メールは実際には送信されていません(開発/デモ用バックエンド)\n"
            "宛先: %s\n件名: %s\n本文:\n%s",
            to, subject, body,
        )


class SMTPMailer(Mailer):
    """標準ライブラリのsmtplibのみを使う、汎用SMTP送信の実装。"""

    is_console = False

    def __init__(self, host: str, port: int, username: str, password: str,
                 from_address: str, use_tls: bool = True, implicit_tls: bool = False):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.from_address = from_address
        self.use_tls = use_tls
        # 実際にamazonSES/一般的なプロバイダが提供する「暗黙的TLS(SMTPS。
        # 通常ポート465)」相手に接続して見つかった実バグの修正: 以前は
        # 常に`smtplib.SMTP`(平文で接続し、必要なら後から`STARTTLS`で
        # 暗号化に切り替える方式。通常ポート587)しか使っていなかった。
        # ポート465のような暗黙的TLS相手では、サーバー側は接続直後から
        # TLSハンドシェイクを開始するのに対しクライアントは平文で
        # `EHLO`を送ろうとするため、実際に自前のTLS終端テストサーバを
        # 立てて接続したところ、ハンドシェイクがタイムアウトし
        # `smtplib.SMTPServerDisconnected`で送信が毎回失敗することを
        # 確認した(=検証・確認メールが利用者に一切届かないまま、
        # サーバーログにしか記録されない静かな障害になる)。
        # `implicit_tls=True`の場合は`smtplib.SMTP_SSL`で最初からTLSで
        # 接続するようにし、実際に同じ自前TLS終端テストサーバへの接続・
        # 送信が成功することを確認して修正した。
        self.implicit_tls = implicit_tls

    def send(self, to: str, subject: str, body: str) -> None:
        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = self.from_address
        message["To"] = to
        message.set_content(body)
        smtp_class = smtplib.SMTP_SSL if self.implicit_tls else smtplib.SMTP
        with smtp_class(self.host, self.port, timeout=10) as server:
            if self.use_tls and not self.implicit_tls:
                server.starttls()
            if self.username:
                server.login(self.username, self.password)
            server.send_message(message)


def get_default_mailer() -> Mailer:
    backend = os.environ.get("PATTERNFORGE_MAIL_BACKEND", "console").lower()
    if backend == "smtp":
        host = os.environ.get("SMTP_HOST")
        if not host:
            logger.warning(
                "PATTERNFORGE_MAIL_BACKEND=smtp ですが SMTP_HOST が未設定のため、"
                "ConsoleMailer(実際には送信しない)にフォールバックします。"
            )
            return ConsoleMailer()
        port = int(os.environ.get("SMTP_PORT", 587))
        # SMTP_IMPLICIT_TLS が明示されていればそれを使う。未設定時は
        # ポート465(SMTPS。RFC 8314で暗黙的TLSの標準ポートとされている)
        # なら暗黙的TLSが必要だろうと推測する(明示的な設定漏れで無言の
        # 送信失敗になるのを防ぐための既定値。誤検出した場合は
        # SMTP_IMPLICIT_TLS=0 で上書きできる)。
        implicit_tls_env = os.environ.get("SMTP_IMPLICIT_TLS")
        if implicit_tls_env is not None:
            implicit_tls = implicit_tls_env == "1"
        else:
            implicit_tls = port == 465
        return SMTPMailer(
            host=host,
            port=port,
            username=os.environ.get("SMTP_USERNAME", ""),
            password=os.environ.get("SMTP_PASSWORD", ""),
            from_address=os.environ.get("SMTP_FROM_ADDRESS", "noreply@example.com"),
            use_tls=os.environ.get("SMTP_USE_TLS", "1") == "1",
            implicit_tls=implicit_tls,
        )
    return ConsoleMailer()
