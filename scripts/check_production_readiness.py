"""check_production_readiness.py — 本番公開前チェックスクリプト(round7で追加)。

これまでの各ラウンドで、本番運用時に設定すべき環境変数(SECRET_KEY・
PATTERNFORGE_FORCE_HTTPS・STRIPE_*・SMTP_*等)についての注意書きが、
app.py/mailer.py/billing.pyのコメントやREADMEに散らばって蓄積してきた。
しかしこれらは「読んで気を付ける」以上の強制力を持たず、実際に環境変数を
設定し忘れたまま(または開発用のプレースホルダー値のまま)本番に公開して
しまう事故を防げない。

このスクリプトは、実際にプロセスへ読み込まれた環境変数、および
web/templates/{terms,privacy,legal}.html の実データ差し替え状況を検査し、
「設定されているが実質的に無効化されている/プレースホルダーのままの
設定」や「未設定のまま公開すると起きる具体的な不具合」を、起動前に
一括で洗い出すためのものである。

使い方:
    python3 scripts/check_production_readiness.py

    本番相当の環境変数を実際にexportした状態(または .env を読み込んだ
    状態)のシェルから実行する。CRITICAL判定が1件でもあれば終了コード1、
    無ければ0を返すため、デプロイスクリプト等のゲートとしても使える
    (WARNING/INFOのみの場合は終了コード0のまま、内容は標準出力に表示する)。

正直な限界(誇張しないための明記):
  - これは環境変数の値だけを見る**静的**チェックであり、実際にSMTPサーバー
    へ接続できるか、Stripeの鍵が有効か、DBファイルへ実際に書き込めるか
    といった**外部疎通確認は行わない**(接続を試みて誤った理由で失敗した
    場合に「設定ミス」と誤診断してしまうことを避けるため。既存の
    正直な文書化方針に合わせ、確認できないことを確認できるかのように
    見せない)。
  - 環境変数のみを見るため、`.env`ファイル等このプロセスの環境に実際に
    読み込まれていない設定は見えない。このスクリプトは、対象の本番環境
    (または本番相当の環境変数を読み込んだシェル)で直接実行すること。
  - 「CRITICAL/WARNING/INFO」の分類は、各項目が実際に引き起こす不具合の
    深刻度についてのこのプロジェクトの判断であり、運用方針によっては
    許容できるWARNINGも当然あり得る(例: 意図的にSMTPを未設定にし、
    メール送信機能を使わない運用にする場合など)。機械的な合否判定では
    なく、人が最終判断するためのチェックリストとして使うことを想定している。
"""

from __future__ import annotations
import os
import sys
from dataclasses import dataclass
from typing import Mapping

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

CRITICAL = "CRITICAL"
WARNING = "WARNING"
INFO = "INFO"

# mailer.py の既定値と完全に一致させておく(片方だけ変更されて検知が
# ズレる事故を防ぐため、値を直接importはせず、コメントで一致を明記する
# 簡易な文字列比較にとどめている: mailer.pyの`get_default_mailer`参照)。
_DEFAULT_SMTP_FROM_ADDRESS = "noreply@example.com"


@dataclass(frozen=True)
class Finding:
    level: str  # CRITICAL / WARNING / INFO
    key: str  # 短い識別子(テストや自動処理から参照しやすいように)
    message: str


def _check_secret_key(env: Mapping[str, str]) -> list[Finding]:
    if not env.get("SECRET_KEY"):
        return [Finding(
            CRITICAL, "secret_key_missing",
            "SECRET_KEY が未設定です。app.pyは未設定の場合プロセス起動ごとに"
            "ランダムな鍵を生成するため、複数ワーカー/複数プロセス構成では"
            "各プロセスで鍵が異なり、セッション(ログイン状態・匿名ジョブの"
            "所有権)が正しく機能しません。固定の秘密値を設定してください"
            "(例: python -c \"import secrets; print(secrets.token_hex(32))\")。",
        )]
    return []


def _check_debug_mode(env: Mapping[str, str]) -> list[Finding]:
    if env.get("FLASK_DEBUG") == "1":
        return [Finding(
            CRITICAL, "flask_debug_enabled",
            "FLASK_DEBUG=1 が設定されています。Flask/Werkzeugのデバッガーは"
            "任意のPythonコードを実行できてしまうため、本番公開時に"
            "有効なままだと深刻なリモートコード実行のリスクになります。"
            "本番では必ず未設定(またはFLASK_DEBUG=0)にしてください。",
        )]
    return []


def _check_https(env: Mapping[str, str]) -> list[Finding]:
    if env.get("PATTERNFORGE_FORCE_HTTPS") != "1":
        return [Finding(
            WARNING, "force_https_disabled",
            "PATTERNFORGE_FORCE_HTTPS が未設定(または1以外)です。この場合"
            "セッションCookieにSecure属性が付かず、HTTP経由でも送信され得ます。"
            "実際にHTTPS配下で公開する場合はPATTERNFORGE_FORCE_HTTPS=1を"
            "設定してください(ローカル開発等、意図的にHTTPのみで運用する"
            "場合はこの警告は無視して構いません)。",
        )]
    return []


def _check_trust_proxy_headers(env: Mapping[str, str]) -> list[Finding]:
    if env.get("PATTERNFORGE_TRUST_PROXY_HEADERS") == "1":
        return [Finding(
            INFO, "trust_proxy_headers_enabled",
            "PATTERNFORGE_TRUST_PROXY_HEADERS=1 が設定されています。信頼できる"
            "単一のリバースプロキシ(X-Forwarded-Forを正しく追記モードで運用)"
            "配下で動かしている場合のみ有効化してください。そうでない構成で"
            "有効化すると、クライアントがX-Forwarded-Forを自由に詐称する"
            "だけでレート制限・ログイン総当たり対策(IPベース)を回避できて"
            "しまいます(app.pyの_client_key()のコメント参照)。",
        )]
    return []


def _check_mail(env: Mapping[str, str]) -> list[Finding]:
    findings: list[Finding] = []
    backend = env.get("PATTERNFORGE_MAIL_BACKEND", "console").lower()
    if backend != "smtp":
        findings.append(Finding(
            WARNING, "mail_backend_console",
            "PATTERNFORGE_MAIL_BACKEND が未設定またはconsoleのため、"
            "会員登録確認・パスワード再設定メールは実際には送信されず、"
            "サーバーログに出力されるだけです。利用者にメールが届く運用に"
            "するにはPATTERNFORGE_MAIL_BACKEND=smtpとSMTP_*系の環境変数を"
            "設定してください。",
        ))
        return findings

    smtp_host = env.get("SMTP_HOST")
    if not smtp_host:
        findings.append(Finding(
            CRITICAL, "smtp_host_missing",
            "PATTERNFORGE_MAIL_BACKEND=smtp ですがSMTP_HOSTが未設定です。"
            "mailer.get_default_mailer()はこの場合、意図に反して無言で"
            "ConsoleMailer(実際には送信しない)にフォールバックします"
            "(smtpを指定したつもりが実際には送られない、という気付きにくい"
            "設定ミスになるため、CRITICAL扱いにしています)。SMTP_HOSTを"
            "設定してください。",
        ))

    from_address = env.get("SMTP_FROM_ADDRESS", _DEFAULT_SMTP_FROM_ADDRESS)
    if from_address == _DEFAULT_SMTP_FROM_ADDRESS:
        findings.append(Finding(
            WARNING, "smtp_from_address_placeholder",
            f"SMTP_FROM_ADDRESSが未設定のため、既定のプレースホルダー"
            f"({_DEFAULT_SMTP_FROM_ADDRESS})のまま送信されます。この"
            "ドメインは実在するテスト用ドメインであり、SPF/DKIM等の送信"
            "ドメイン認証が自組織のものと一致しないため、受信側で迷惑メール"
            "判定・拒否される可能性が高いです。実際に送信に使うドメインの"
            "アドレスをSMTP_FROM_ADDRESSに設定してください。",
        ))
    return findings


def _check_billing(env: Mapping[str, str]) -> list[Finding]:
    findings: list[Finding] = []
    secret_key = env.get("STRIPE_SECRET_KEY")
    price_id = env.get("STRIPE_PRICE_ID")

    if not secret_key or not price_id:
        findings.append(Finding(
            WARNING, "billing_mock_provider",
            "STRIPE_SECRET_KEY と STRIPE_PRICE_ID の少なくとも一方が未設定の"
            "ため、billing.get_default_provider()はMockPaymentProvider"
            "(実際の決済を行わない、即座にプラン切り替えするだけの"
            "テスト用実装)にフォールバックします。実際に課金する運用には"
            "両方を設定してください。",
        ))
        return findings

    if secret_key.startswith("sk_test_"):
        findings.append(Finding(
            WARNING, "stripe_test_mode_key",
            "STRIPE_SECRET_KEY がテストモードの鍵(sk_test_...)です。この"
            "ままでは実際の課金は発生しません。本番で実際に課金する場合は"
            "本番用の鍵(sk_live_...)に置き換えてください(意図的に"
            "テストモードで運用する場合はこの警告は無視して構いません)。",
        ))
    elif not secret_key.startswith("sk_live_"):
        findings.append(Finding(
            WARNING, "stripe_key_unexpected_format",
            "STRIPE_SECRET_KEY が sk_test_/sk_live_ のどちらの接頭辞でも"
            "ないため、プレースホルダー文字列(例: \"your-stripe-secret-key\")"
            "が誤って設定されている可能性があります。実際のStripeの鍵か"
            "確認してください。",
        ))

    if not price_id.startswith("price_"):
        findings.append(Finding(
            WARNING, "stripe_price_id_unexpected_format",
            "STRIPE_PRICE_ID が price_ で始まっていないため、プレースホル"
            "ダー文字列が誤って設定されている可能性があります。Stripe"
            "ダッシュボードの実際のPrice IDか確認してください。",
        ))

    if not env.get("STRIPE_WEBHOOK_SECRET"):
        findings.append(Finding(
            CRITICAL, "stripe_webhook_secret_missing",
            "STRIPE_SECRET_KEY/STRIPE_PRICE_IDが設定済み(実際の決済が有効)"
            "にもかかわらず、STRIPE_WEBHOOK_SECRETが未設定です。この場合"
            "app.pyの/billing/webhookは全てのWebhookイベントを500で拒否し"
            "続けます(実際にコードを確認済み)。つまり、利用者が支払い直後の"
            "リダイレクトを完了できなかった場合(ブラウザを閉じる・通信断等)、"
            "支払い済みなのにプランがproに更新されないまま復旧する手段が"
            "無くなります。STRIPE_WEBHOOK_SECRETを設定してください。",
        ))
    return findings


def _check_legal_pages(env: Mapping[str, str]) -> list[Finding]:
    """`/terms`・`/privacy`・`/legal`の実データ差し替え漏れを検出する。

    web/templates/{terms,privacy,legal}.html は、事業者名・所在地・連絡先
    などを`class="legal-placeholder"`でマークしたプレースホルダーのまま
    出荷している(画面上もオレンジ色のバッジで分かるようにしてある。上記
    「公開前チェックリスト」参照)。このクラスが残っているテンプレートが
    1つでもあれば、有料プランを実際に販売する前に差し替えるべき項目が
    残っていることを検出できる。
    """
    findings: list[Finding] = []
    template_dir = os.path.join(_REPO_ROOT, "web", "templates")
    targets = {
        "terms.html": "利用規約",
        "privacy.html": "プライバシーポリシー",
        "legal.html": "運営者情報・特定商取引法に基づく表示",
    }
    for filename, label in targets.items():
        path = os.path.join(template_dir, filename)
        try:
            with open(path, encoding="utf-8") as f:
                content = f.read()
        except OSError:
            # テンプレート自体が見つからない場合は、この検査の対象外
            # (アプリ起動時に別の形で失敗するはずなので、ここでは無視する)。
            continue
        if 'legal-placeholder' in content:
            findings.append(Finding(
                WARNING, f"legal_placeholder_{filename.replace('.html', '')}",
                f"{filename}({label})に、事業者名・所在地・連絡先等の"
                "プレースホルダー(`class=\"legal-placeholder\"`)が"
                "残っています。有料プランを実際に販売する前に、実在する"
                "事業者情報に差し替えてください。",
            ))
    return findings


def _check_output_paths(env: Mapping[str, str]) -> list[Finding]:
    findings: list[Finding] = []
    base_dir = _REPO_ROOT
    output_dir = env.get("PATTERNFORGE_OUTPUT_DIR", os.path.join(base_dir, "generated"))
    db_path = env.get("PATTERNFORGE_DB_PATH", os.path.join(base_dir, "patternforge.db"))

    output_parent = output_dir if os.path.isdir(output_dir) else os.path.dirname(output_dir) or "."
    if not os.path.isdir(output_parent) or not os.access(output_parent, os.W_OK):
        findings.append(Finding(
            CRITICAL, "output_dir_not_writable",
            f"生成物の保存先 PATTERNFORGE_OUTPUT_DIR={output_dir!r} の親"
            "ディレクトリへ書き込めません(存在しないか権限不足)。型紙の"
            "生成が全て失敗します。ディレクトリを作成し、実行ユーザーに"
            "書き込み権限を付与してください。",
        ))

    db_parent = os.path.dirname(os.path.abspath(db_path)) or "."
    if not os.path.isdir(db_parent) or not os.access(db_parent, os.W_OK):
        findings.append(Finding(
            CRITICAL, "db_dir_not_writable",
            f"DBファイルの保存先 PATTERNFORGE_DB_PATH={db_path!r} の親"
            "ディレクトリへ書き込めません(存在しないか権限不足)。会員登録・"
            "ログイン・型紙生成履歴などが全て失敗します。ディレクトリを"
            "作成し、実行ユーザーに書き込み権限を付与してください。",
        ))
    return findings


# 実行順は「アプリ全体が起動不能/著しく壊れる項目」→「機能単位で壊れる
# 項目」の順にしてあり、上から順に読めば深刻度の高いものから確認できる。
_ALL_CHECKS = (
    _check_secret_key,
    _check_debug_mode,
    _check_output_paths,
    _check_https,
    _check_trust_proxy_headers,
    _check_mail,
    _check_billing,
    _check_legal_pages,
)


def check_production_readiness(env: Mapping[str, str] | None = None) -> list[Finding]:
    """現在(または指定された)環境変数を検査し、Findingのリストを返す。

    `env`を明示的に渡せるようにしているのは、テストから`os.environ`を
    汚さずに任意の設定パターンを検証できるようにするため。
    """
    if env is None:
        env = os.environ
    findings: list[Finding] = []
    for check in _ALL_CHECKS:
        findings.extend(check(env))
    return findings


def _print_report(findings: list[Finding]) -> None:
    order = {CRITICAL: 0, WARNING: 1, INFO: 2}
    findings = sorted(findings, key=lambda f: order[f.level])
    counts = {CRITICAL: 0, WARNING: 0, INFO: 0}
    for f in findings:
        counts[f.level] += 1

    print("=" * 70)
    print("PatternForge 本番公開前チェック")
    print("=" * 70)
    if not findings:
        print("検出された問題はありません(ただしこのスクリプトの「正直な限界」")
        print("に記載の通り、外部疎通確認は行っていません)。")
        return

    for f in findings:
        print(f"\n[{f.level}] {f.key}")
        print(f"  {f.message}")

    print()
    print("-" * 70)
    print(f"CRITICAL: {counts[CRITICAL]}件 / WARNING: {counts[WARNING]}件 / "
          f"INFO: {counts[INFO]}件")
    if counts[CRITICAL]:
        print("CRITICALな項目が残っている間は本番公開しないことを強く推奨します。")


def main() -> int:
    findings = check_production_readiness()
    _print_report(findings)
    return 1 if any(f.level == CRITICAL for f in findings) else 0


if __name__ == "__main__":
    raise SystemExit(main())
