"""scripts/check_production_readiness.py (round7で追加) のテスト。

本番公開前チェックスクリプトが、実際に問題のある設定パターン
(未設定・開発用プレースホルダーのまま等)を正しく検出し、逆に正しく
設定された場合には誤検出(false positive)しないことを確認する。
"""
import os

import scripts.check_production_readiness as readiness_module
from scripts.check_production_readiness import (
    CRITICAL,
    WARNING,
    check_production_readiness,
)


def _write_clean_legal_templates(template_dir):
    """`legal-placeholder`マーカーを含まない、差し替え済み想定のテンプレート
    一式を作る(このモジュール自身のテストが、実際のリポジトリの
    web/templates/*.html の中身に左右されないようにするため)。
    """
    os.makedirs(template_dir, exist_ok=True)
    for filename in ("terms.html", "privacy.html", "legal.html"):
        with open(os.path.join(template_dir, filename), "w", encoding="utf-8") as f:
            f.write("<html><body>株式会社サンプル (実データ差し替え済み)</body></html>")


def _keys(findings):
    return {f.key for f in findings}


def _levels_by_key(findings):
    return {f.key: f.level for f in findings}


GOOD_ENV = {
    "SECRET_KEY": "a" * 64,
    "FLASK_DEBUG": "0",
    "PATTERNFORGE_FORCE_HTTPS": "1",
    "PATTERNFORGE_MAIL_BACKEND": "smtp",
    "SMTP_HOST": "smtp.example-corp.jp",
    "SMTP_FROM_ADDRESS": "noreply@example-corp.jp",
    "STRIPE_SECRET_KEY": "sk_live_abc123",
    "STRIPE_PRICE_ID": "price_abc123",
    "STRIPE_WEBHOOK_SECRET": "whsec_abc123",
}


def test_fully_configured_production_env_has_no_findings(tmp_path, monkeypatch):
    # 法的表示ページのプレースホルダー差し替え済みも合わせて再現し、
    # 「本当に何も問題がない状態」でfindingsが空になることを確認する。
    _write_clean_legal_templates(tmp_path / "web" / "templates")
    monkeypatch.setattr(readiness_module, "_REPO_ROOT", str(tmp_path))

    findings = check_production_readiness(GOOD_ENV)
    assert findings == []


def test_legal_placeholder_pages_are_flagged_as_warnings(tmp_path, monkeypatch):
    template_dir = tmp_path / "web" / "templates"
    os.makedirs(template_dir, exist_ok=True)
    (template_dir / "terms.html").write_text(
        '<span class="legal-placeholder">[事業者名を入力]</span>', encoding="utf-8")
    (template_dir / "privacy.html").write_text(
        '<span class="legal-placeholder">[事業者名を入力]</span>', encoding="utf-8")
    (template_dir / "legal.html").write_text(
        '<span class="legal-placeholder">[事業者名を入力]</span>', encoding="utf-8")
    monkeypatch.setattr(readiness_module, "_REPO_ROOT", str(tmp_path))

    findings = check_production_readiness(GOOD_ENV)
    levels = _levels_by_key(findings)
    assert levels["legal_placeholder_terms"] == WARNING
    assert levels["legal_placeholder_privacy"] == WARNING
    assert levels["legal_placeholder_legal"] == WARNING


def test_legal_pages_without_placeholder_marker_are_not_flagged(tmp_path, monkeypatch):
    _write_clean_legal_templates(tmp_path / "web" / "templates")
    monkeypatch.setattr(readiness_module, "_REPO_ROOT", str(tmp_path))

    findings = check_production_readiness(GOOD_ENV)
    keys = _keys(findings)
    assert "legal_placeholder_terms" not in keys
    assert "legal_placeholder_privacy" not in keys
    assert "legal_placeholder_legal" not in keys


def test_missing_legal_template_file_is_not_flagged_by_this_check(tmp_path, monkeypatch):
    # テンプレート自体が見つからない場合はアプリ起動時に別の形で失敗する
    # はずで、この静的チェックの責務ではないため、単に無視されることを
    # 確認する(誤って例外で落ちたり、誤検出したりしないことの回帰テスト)。
    os.makedirs(tmp_path / "web" / "templates", exist_ok=True)
    monkeypatch.setattr(readiness_module, "_REPO_ROOT", str(tmp_path))

    findings = check_production_readiness(GOOD_ENV)
    keys = _keys(findings)
    assert not any(k.startswith("legal_placeholder_") for k in keys)


def test_real_repository_legal_pages_are_currently_detected_as_placeholders():
    """このリポジトリは出荷時点では法的表示ページを実データに差し替えて
    いない(README「公開前チェックリスト」参照)ため、このチェックが実際に
    その状態を検出できることを、モックを使わず実物のテンプレートに対して
    確認する。将来実際にサービスを立ち上げる際に事業者情報を差し替えると、
    このテストは失敗するようになる — それはこのチェック自体が正しく
    機能している証拠であり、その時点でこのテストを削除して構わない。
    """
    findings = check_production_readiness(GOOD_ENV)
    keys = _keys(findings)
    assert "legal_placeholder_terms" in keys
    assert "legal_placeholder_privacy" in keys
    assert "legal_placeholder_legal" in keys


def test_empty_env_flags_secret_key_as_critical():
    findings = check_production_readiness({})
    levels = _levels_by_key(findings)
    assert levels["secret_key_missing"] == CRITICAL


def test_flask_debug_enabled_is_critical():
    env = dict(GOOD_ENV, FLASK_DEBUG="1")
    findings = check_production_readiness(env)
    levels = _levels_by_key(findings)
    assert levels["flask_debug_enabled"] == CRITICAL


def test_force_https_disabled_is_a_warning_not_critical():
    env = dict(GOOD_ENV)
    del env["PATTERNFORGE_FORCE_HTTPS"]
    findings = check_production_readiness(env)
    levels = _levels_by_key(findings)
    assert levels["force_https_disabled"] == WARNING


def test_trust_proxy_headers_enabled_is_informational():
    from scripts.check_production_readiness import INFO

    env = dict(GOOD_ENV, PATTERNFORGE_TRUST_PROXY_HEADERS="1")
    findings = check_production_readiness(env)
    levels = _levels_by_key(findings)
    assert levels["trust_proxy_headers_enabled"] == INFO


def test_default_mail_backend_console_is_flagged():
    env = dict(GOOD_ENV)
    del env["PATTERNFORGE_MAIL_BACKEND"]
    findings = check_production_readiness(env)
    assert "mail_backend_console" in _keys(findings)
    # console backendの場合、SMTP関連の項目は無関係なので出ないはず。
    assert "smtp_host_missing" not in _keys(findings)
    assert "smtp_from_address_placeholder" not in _keys(findings)


def test_smtp_backend_without_host_is_critical_because_it_silently_falls_back():
    env = dict(GOOD_ENV)
    del env["SMTP_HOST"]
    findings = check_production_readiness(env)
    levels = _levels_by_key(findings)
    assert levels["smtp_host_missing"] == CRITICAL


def test_smtp_from_address_placeholder_default_is_flagged():
    env = dict(GOOD_ENV)
    del env["SMTP_FROM_ADDRESS"]
    findings = check_production_readiness(env)
    assert "smtp_from_address_placeholder" in _keys(findings)


def test_smtp_from_address_explicit_real_domain_is_not_flagged():
    findings = check_production_readiness(GOOD_ENV)
    assert "smtp_from_address_placeholder" not in _keys(findings)


def test_billing_unconfigured_falls_back_to_mock_and_is_a_warning():
    env = dict(GOOD_ENV)
    del env["STRIPE_SECRET_KEY"]
    del env["STRIPE_PRICE_ID"]
    del env["STRIPE_WEBHOOK_SECRET"]
    findings = check_production_readiness(env)
    levels = _levels_by_key(findings)
    assert levels["billing_mock_provider"] == WARNING
    # is_mockにフォールバックする場合、webhook必須チェックは無意味なので
    # 出ないはず。
    assert "stripe_webhook_secret_missing" not in levels


def test_stripe_test_mode_key_is_flagged():
    env = dict(GOOD_ENV, STRIPE_SECRET_KEY="sk_test_abc123")
    findings = check_production_readiness(env)
    assert "stripe_test_mode_key" in _keys(findings)


def test_stripe_key_placeholder_string_is_flagged():
    env = dict(GOOD_ENV, STRIPE_SECRET_KEY="your-stripe-secret-key-here")
    findings = check_production_readiness(env)
    assert "stripe_key_unexpected_format" in _keys(findings)


def test_stripe_price_id_placeholder_string_is_flagged():
    env = dict(GOOD_ENV, STRIPE_PRICE_ID="my-plan")
    findings = check_production_readiness(env)
    assert "stripe_price_id_unexpected_format" in _keys(findings)


def test_stripe_configured_without_webhook_secret_is_critical():
    """billing.pyのwebhook必須ロジック(app.pyの/billing/webhook)と合わせ、
    実際の決済が有効なのにWebhook検証鍵が無い状態は、支払い確定手段が
    完全に失われる重大な設定漏れなのでCRITICAL扱いにする。
    """
    env = dict(GOOD_ENV)
    del env["STRIPE_WEBHOOK_SECRET"]
    findings = check_production_readiness(env)
    levels = _levels_by_key(findings)
    assert levels["stripe_webhook_secret_missing"] == CRITICAL


def test_output_dir_not_writable_is_critical(tmp_path):
    unwritable_parent = tmp_path / "does" / "not" / "exist"
    env = dict(GOOD_ENV, PATTERNFORGE_OUTPUT_DIR=str(unwritable_parent / "generated"))
    findings = check_production_readiness(env)
    levels = _levels_by_key(findings)
    assert levels["output_dir_not_writable"] == CRITICAL


def test_output_dir_writable_is_not_flagged(tmp_path):
    env = dict(GOOD_ENV, PATTERNFORGE_OUTPUT_DIR=str(tmp_path / "generated"))
    findings = check_production_readiness(env)
    assert "output_dir_not_writable" not in _keys(findings)


def test_db_dir_not_writable_is_critical(tmp_path):
    unwritable_parent = tmp_path / "does" / "not" / "exist"
    env = dict(GOOD_ENV, PATTERNFORGE_DB_PATH=str(unwritable_parent / "patternforge.db"))
    findings = check_production_readiness(env)
    levels = _levels_by_key(findings)
    assert levels["db_dir_not_writable"] == CRITICAL


def test_main_exits_nonzero_only_when_a_critical_finding_exists(monkeypatch, capsys):
    from scripts.check_production_readiness import main

    monkeypatch.setattr(os, "environ", dict(GOOD_ENV))
    assert main() == 0
    capsys.readouterr()

    monkeypatch.setattr(os, "environ", {})
    assert main() == 1
    out = capsys.readouterr().out
    assert "secret_key_missing" in out
