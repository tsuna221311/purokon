import pytest

import mailer as mailer_module


def test_console_mailer_does_not_raise_and_is_marked_console(caplog):
    m = mailer_module.ConsoleMailer()
    assert m.is_console is True
    with caplog.at_level("INFO"):
        m.send("person@example.com", "件名", "本文")
    assert any("ConsoleMailer" in record.message for record in caplog.records)


def test_get_default_mailer_defaults_to_console(monkeypatch):
    monkeypatch.delenv("PATTERNFORGE_MAIL_BACKEND", raising=False)
    assert isinstance(mailer_module.get_default_mailer(), mailer_module.ConsoleMailer)


def test_get_default_mailer_falls_back_to_console_when_smtp_host_missing(monkeypatch, caplog):
    monkeypatch.setenv("PATTERNFORGE_MAIL_BACKEND", "smtp")
    monkeypatch.delenv("SMTP_HOST", raising=False)
    with caplog.at_level("WARNING"):
        result = mailer_module.get_default_mailer()
    assert isinstance(result, mailer_module.ConsoleMailer)
    assert any("SMTP_HOST" in record.message for record in caplog.records)


def test_get_default_mailer_builds_smtp_mailer_when_configured(monkeypatch):
    monkeypatch.setenv("PATTERNFORGE_MAIL_BACKEND", "smtp")
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_PORT", "2525")
    monkeypatch.setenv("SMTP_FROM_ADDRESS", "noreply@example.com")
    result = mailer_module.get_default_mailer()
    assert isinstance(result, mailer_module.SMTPMailer)
    assert result.host == "smtp.example.com"
    assert result.port == 2525
    assert result.is_console is False


class _FakeSMTP:
    """smtplib.SMTPの代わりに使う、実際には接続しないフェイク実装。"""

    instances = []

    def __init__(self, host, port, timeout=10):
        self.host = host
        self.port = port
        self.started_tls = False
        self.login_args = None
        self.sent_messages = []
        _FakeSMTP.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def starttls(self):
        self.started_tls = True

    def login(self, username, password):
        self.login_args = (username, password)

    def send_message(self, message):
        self.sent_messages.append(message)


def test_smtp_mailer_sends_via_smtplib(monkeypatch):
    _FakeSMTP.instances.clear()
    monkeypatch.setattr(mailer_module.smtplib, "SMTP", _FakeSMTP)
    m = mailer_module.SMTPMailer(
        host="smtp.example.com", port=587, username="user", password="pw",
        from_address="noreply@example.com", use_tls=True,
    )
    m.send("to@example.com", "件名", "本文")

    assert len(_FakeSMTP.instances) == 1
    fake = _FakeSMTP.instances[0]
    assert fake.started_tls is True
    assert fake.login_args == ("user", "pw")
    assert len(fake.sent_messages) == 1
    sent = fake.sent_messages[0]
    assert sent["To"] == "to@example.com"
    assert sent["Subject"] == "件名"


class _FakeSMTPSSL:
    """smtplib.SMTP_SSLの代わりに使う、実際には接続しないフェイク実装。

    暗黙的TLS(SMTPS)経路が本当に`smtplib.SMTP_SSL`を使っている
    (=`smtplib.SMTP`+`starttls()`ではない)ことを確認するための専用フェイク。
    """

    instances = []

    def __init__(self, host, port, timeout=10):
        self.host = host
        self.port = port
        self.login_args = None
        self.sent_messages = []
        _FakeSMTPSSL.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def starttls(self):  # pragma: no cover - 呼ばれたら実バグ(下のテストで検出)
        raise AssertionError("暗黙的TLS接続でstarttls()が呼ばれてはならない")

    def login(self, username, password):
        self.login_args = (username, password)

    def send_message(self, message):
        self.sent_messages.append(message)


def test_smtp_mailer_uses_implicit_tls_via_smtp_ssl_not_starttls(monkeypatch):
    """実際に自前のTLS終端テストサーバ(暗黙的TLS。通常ポート465相当)へ接続して
    見つかった実バグの回帰テスト。以前は`implicit_tls`という区別が無く、常に
    `smtplib.SMTP`で平文接続してから(必要なら)`starttls()`する経路しか無かった
    ため、暗黙的TLSしか提供しないSMTPサーバー相手には接続直後のTLSハンド
    シェイクがタイムアウトし、`smtplib.SMTPServerDisconnected`で送信が
    毎回失敗していた(検証・パスワード再設定メールが利用者に一切届かない)。
    `implicit_tls=True`の場合は`smtplib.SMTP`ではなく`smtplib.SMTP_SSL`を
    使う(=`starttls()`を呼ばない)ことをここで確認する。
    """
    _FakeSMTP.instances.clear()
    _FakeSMTPSSL.instances.clear()
    monkeypatch.setattr(mailer_module.smtplib, "SMTP", _FakeSMTP)
    monkeypatch.setattr(mailer_module.smtplib, "SMTP_SSL", _FakeSMTPSSL)
    m = mailer_module.SMTPMailer(
        host="smtp.example.com", port=465, username="user", password="pw",
        from_address="noreply@example.com", use_tls=True, implicit_tls=True,
    )
    m.send("to@example.com", "件名", "本文")

    assert _FakeSMTP.instances == []  # 平文SMTP経路は一切使われていない
    assert len(_FakeSMTPSSL.instances) == 1
    fake = _FakeSMTPSSL.instances[0]
    assert fake.login_args == ("user", "pw")
    assert len(fake.sent_messages) == 1


def test_get_default_mailer_auto_detects_implicit_tls_for_port_465(monkeypatch):
    monkeypatch.setenv("PATTERNFORGE_MAIL_BACKEND", "smtp")
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_PORT", "465")
    monkeypatch.delenv("SMTP_IMPLICIT_TLS", raising=False)
    result = mailer_module.get_default_mailer()
    assert result.implicit_tls is True


def test_get_default_mailer_does_not_assume_implicit_tls_for_port_587(monkeypatch):
    monkeypatch.setenv("PATTERNFORGE_MAIL_BACKEND", "smtp")
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_PORT", "587")
    monkeypatch.delenv("SMTP_IMPLICIT_TLS", raising=False)
    result = mailer_module.get_default_mailer()
    assert result.implicit_tls is False


def test_get_default_mailer_allows_overriding_implicit_tls_autodetection(monkeypatch):
    # ポート465でも明示的にSMTP_IMPLICIT_TLS=0にすれば暗黙的TLSにしない
    # (465番で平文/STARTTLSしか話さない独自プロキシ等の稀な構成向け)。
    monkeypatch.setenv("PATTERNFORGE_MAIL_BACKEND", "smtp")
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_PORT", "465")
    monkeypatch.setenv("SMTP_IMPLICIT_TLS", "0")
    assert mailer_module.get_default_mailer().implicit_tls is False

    # 逆に、標準以外のポートで暗黙的TLSを使うプロバイダ向けに明示的に1にできる。
    monkeypatch.setenv("SMTP_PORT", "2465")
    monkeypatch.setenv("SMTP_IMPLICIT_TLS", "1")
    assert mailer_module.get_default_mailer().implicit_tls is True
