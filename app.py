"""app.py — PatternForge のFlask API + 簡易フロントエンド。

エンジン部分(engine/)とは完全に分離してあるので、Flaskを別のフレームワーク
(FastAPIなど)に差し替えたい場合もengine配下のコードは変更不要。

エンドポイント:
  GET  /                       — 採寸入力・パーツ選択フォーム(UI本体)
  POST /api/generate           — 型紙生成本体。JSON {ok, ...summary...} を返す
  POST /api/custom-panel/trace  — アップロード画像から輪郭を自動抽出（round10で追加）
  GET  /download/<job_id>/<fmt> — 生成したSVG/PDFのダウンロード(fmt: svg|pdf)
  GET  /healthz                 — 動作確認用
  GET  /favicon.ico              — favicon（ブラウザが自動リクエストするため常時提供）
  GET/POST /signup, /login      — アカウント登録・ログイン
  POST /logout                  — ログアウト
  GET  /verify/<token>           — メールアドレス確認
  POST /account/resend-verification — 確認メールの再送
  GET/POST /forgot-password      — パスワード再設定メールの送信
  GET/POST /reset-password/<token> — パスワードの再設定
  GET  /account                 — マイページ（利用状況・プラン・生成履歴・採寸プロフィール）
  POST /account/upgrade|downgrade — プラン切り替え
  POST /api/profiles             — 採寸プロフィールの保存（JSON API、ログイン必須）
  POST /account/profiles/<id>/delete — 採寸プロフィールの削除
  POST /account/jobs/<job_id>/regenerate — 生成履歴からの再生成（round8で追加）
  GET  /account/export           — 自分のデータ一式をJSONでダウンロード（round8で追加）
  GET/POST /account/delete       — 退会（パスワード再確認の上でアカウント削除。round8で追加）
  POST /account/api-keys          — APIキーの発行（round8で追加）
  POST /account/api-keys/<id>/revoke — APIキーの失効（round8で追加）
  POST /api/v1/generate           — プログラマティックAPI（APIキー認証。round8で追加）
  POST /org/create                — 組織の作成（round8で追加）
  POST /org/invite                — 組織メンバーの招待（round8で追加）
  GET  /org/invites/<token>       — 招待の確認画面（round8で追加）
  POST /org/invites/<token>/accept — 招待の受諾（round8で追加）
  POST /org/members/<id>/remove   — メンバーを外す・自主退会（round8で追加）
  POST /org/disband               — 組織の解散（round8で追加）
  POST /billing/webhook          — Stripe Webhook（Stripe未設定時は404）
  GET  /pricing                 — 料金ページ
  GET  /guide                   — 使い方ガイド（操作マニュアル）
  GET  /terms, /privacy, /legal — 利用規約・プライバシーポリシー・運営者情報
                                   （公開前に実際の事業者情報へ差し替えが必要。README参照）

商用サービス化にあたって追加した機能と、正直な実装レベルの注記:
  - ジョブの所有権チェック（本物）: 生成したパターンは、生成したブラウザ
    セッション（未ログイン時はセッションに紐づく匿名visitor_id、ログイン時は
    ユーザーID）以外からはダウンロードできない。store.py にSQLiteで永続化。
  - 認証（本物）: パスワードはwerkzeug.securityでハッシュ化して保存し、
    セッションもFlaskの署名付きセッションで管理する。メールアドレス確認・
    パスワード再設定も、使い捨てトークン(store.py)+メール送信(mailer.py)で
    実際に機能する（ただしConsoleMailerが既定のため、SMTP環境変数を設定
    しない限り実際にはメールは届かず、代わりに開発用としてリンクを画面に
    表示する。下記mailer.py参照）。
  - 決済（設定次第で本物）: `STRIPE_SECRET_KEY` と `STRIPE_PRICE_ID` を
    設定すると、実際にStripeのCheckout Session(サブスクリプション)を作成し、
    Webhook(`/billing/webhook`)で支払い確定/解約を受け取ってplanを更新する
    (billing.py参照)。未設定の場合はこれまで通り、DB上のplan列を
    テストモードで即座に切り替えるだけのモックにフォールバックする。
  - 利用回数の上限（本物）: プランごとの1日あたり生成回数をSQLiteで
    強制する。読み取り→判定→書き込みは `BEGIN IMMEDIATE` で直列化しており、
    並行リクエストによる上限のすり抜けを防いでいる（store.py参照）。
    短い時間窓のレート制限(下記_RateLimiter)も、round6で同じSQLite
    (`store.py`の`check_rate_limit`)に切り替えたため、複数ワーカー/
    複数プロセス構成でも正しく共有される。

第2回セキュリティ監査（認証・並行性・新機能の攻撃面）で見つかった問題と対応:
  - パスワード再設定後のセッション無効化（本物）: `users.session_version`を
    パスワード変更のたびにインクリメントし、`_current_user()`で現在の値と
    セッションに埋め込んだ値を比較する。不一致（＝再設定前の古いセッション
    Cookie）ならその場でログアウト扱いにする。
  - スキーママイグレーションの並行性（修正済み）: 複数ワーカーが同時に
    `Store()`を構築しても`_migrate()`が"duplicate column name"で落ちない
    よう、`BEGIN IMMEDIATE`での直列化と重複エラーの無害化を追加した
    （store.py参照）。
  - メール確認・パスワード再設定エンドポイントのレート制限（本物）:
    IPベースの制限(`_email_send_rate_limiter`)に加え、同一ユーザー・
    同一目的への短時間の連続発行をDB側でも防ぐ(`store.seconds_since_last_token`)。
    IPローテーションを使った分散的なメール爆撃対策。
  - CSRF対策（round6で完全実装、README参照）: `SESSION_COOKIE_SAMESITE=Lax`に
    加え、状態変更リクエスト(GET/HEAD/OPTIONS以外)全体を対象にした
    トークン方式のCSRF対策を導入した(下記`_csrf_protect`参照)。第2回監査で
    「部分的な対策」として既知の制約に挙げていたものを、round6で解消した。
  - Stripe Webhookの防御的処理（本物）: `client_reference_id`が数値でない
    ・該当ユーザーが存在しない場合も例外で500にせず、警告ログを残した上で
    200を返しStripe側の再送ループを防ぐ。
  - `/account/upgrade`の冪等性（本物）: 既にProプランのユーザーが誤って
    連打しても、二重にCheckout Session/サブスクリプションを作らない。
  - メール確認は実装済みだが機能ゲートには使っていない（正直な限界。
    README参照）。

運用面の注意:
  - 開発サーバ(`python app.py`)は検証用。実運用では `gunicorn wsgi:app` 等の
    WSGIサーバを使うこと（wsgi.py参照）。
  - `generated/` に生成物が溜まり続けないよう、バックグラウンドスレッドで
    古いファイル(_cleanup_old_outputs)とjobsテーブルの古い行を掃除する
    簡易TTLクリーンアップを入れている。以前はリクエストごとに同期実行
    していたため、生成物が増えるほど毎リクエストのレイテンシが悪化する
    問題があった。今は最短実行間隔(_CLEANUP_MIN_INTERVAL_SECONDS)を
    設けたうえでバックグラウンドスレッドに投げるようにしている。
  - 同時多発リクエストからサーバを守るための最小限のレート制限を実装している
    (_RateLimiter)。round6より前は単一プロセスのメモリ(dequeベース)のみの
    簡易実装で、複数ワーカー/複数インスタンス構成では実質的な上限がワーカー
    数倍に緩んでいたが、round6でstore.pyのSQLite(`check_rate_limit`)に
    切り替え、複数ワーカー/複数プロセス間で共有されるようにした。
  - SECRET_KEY を環境変数で設定しないと、起動ごと・ワーカーごとにランダムな
    鍵を生成する。複数ワーカー構成ではワーカー間でセッションの署名鍵が
    揃わず、ログイン状態や匿名ジョブの所有権が正しく機能しないため、
    本番では必ず環境変数で固定値を設定すること。
"""

from __future__ import annotations
import hmac
import json
import logging
import math
import os
import re
import secrets
import time
import uuid
from functools import wraps
from threading import Lock, Thread

from flask import (
    Flask, Response, flash, g, jsonify, redirect, render_template, request, send_from_directory,
    session, url_for,
)
from PIL import Image, ImageOps
from werkzeug.exceptions import RequestEntityTooLarge
from werkzeug.middleware.proxy_fix import ProxyFix

import billing
import labels
import mailer
import store
from engine.custom_panel import (
    CustomPanelError,
    CustomPanelSpec,
    MAX_CUSTOM_PANELS_PER_REQUEST,
    calibrate_points_to_cm,
    resolve_reference_cm,
    validate_label,
    validate_quantity,
)
from engine.measurements import Measurements, STANDARD_SIZE_GRADE_CM, validate_custom_grade_cm
from engine.pipeline import (
    COLLAR_STYLES,
    CUFFS_STYLES,
    NECKLINES,
    PANTS_STYLES,
    SKIRT_STYLES,
    SLEEVE_STYLES,
    WAISTBAND_STYLES,
    GarmentSpec,
    PatternForgePipeline,
    DEFAULT_SEAM_ALLOWANCE_CM,
    STANDARD_SIZE_ORDER,
    build_custom_panel_requests,
    build_garment_spec,
)
from engine.segmentation import SimpleSilhouetteSegmenter

# モジュールレベルで最低限のロギングを設定する。`logging.basicConfig` は
# root loggerにハンドラが無い場合のみ効くため、gunicorn配下で既にログ設定が
# されている場合は何もしない(no-op)。以前はこの呼び出しが `if __name__ ==
# "__main__":` の中にしか無く、本番のエントリポイントである wsgi.py 経由
# (`gunicorn wsgi:app`)ではその分岐を通らないため、app.logger.exception(...)
# が一切のハンドラ無しで実行され、最初の本番障害を追跡できない状態だった。
logging.basicConfig(
    level=os.environ.get("PATTERNFORGE_LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

# round8で追加: エラー監視(Sentry等)の任意統合。
#
# それまでは想定外の例外(app.logger.exception呼び出し箇所)がファイル/
# 標準出力のログにしか残らず、運用担当者がログを能動的に見に行かない限り
# 障害に気付けない(healthzによるプロセス生存確認とは別の、個々のリクエスト
# 単位のエラーを能動的に通知してくれる仕組みが無かった)という既知の限界が
# あった。`SENTRY_DSN`環境変数が設定されている場合のみ`sentry_sdk`を
# 初期化する。未設定時(デフォルト)は、これまで通りログのみの挙動を一切
# 変えない(既存の`app.logger.exception`呼び出しは、Sentry初期化後は
# FlaskIntegration経由で自動的にもSentryへ送られるが、初期化していなければ
# 何も変わらない)。
#
# 正直な限界: `sentry-sdk`パッケージ自体はrequirements.txtの必須依存には
# 含めていない(全ての利用者がSentryを使うとは限らないため、未使用機能の
# ためだけに依存を強制したくない)。`SENTRY_DSN`を設定したのに
# `sentry-sdk`が未インストールの場合は、起動時に警告ログを出した上で
# 通常通り起動を続ける(エラー監視が使えないだけで、サービス自体は落とさ
# ない)。実際に`pip install sentry-sdk`せずに`SENTRY_DSN`だけを設定して
# 起動し、ImportErrorが握りつぶされて通常通り動くことを確認済み。
_SENTRY_DSN = os.environ.get("SENTRY_DSN")
if _SENTRY_DSN:
    try:
        import sentry_sdk
        from sentry_sdk.integrations.flask import FlaskIntegration

        sentry_sdk.init(
            dsn=_SENTRY_DSN,
            integrations=[FlaskIntegration()],
            environment=os.environ.get("SENTRY_ENVIRONMENT", "production"),
            # パフォーマンストレース(traces_sample_rate)は既定でオフ。
            # エラー監視(例外の捕捉・通知)だけが目的で、リクエストごとの
            # 詳細なパフォーマンストレースはSentry側の追加コスト・データ量
            # 増加を伴うため、必要な場合のみ明示的に有効化させる。
            traces_sample_rate=float(os.environ.get("SENTRY_TRACES_SAMPLE_RATE", "0.0")),
        )
        logging.getLogger(__name__).info("Sentry error monitoring initialized (DSN configured).")
    except ImportError:
        logging.getLogger(__name__).warning(
            "SENTRY_DSN is set but the 'sentry-sdk' package is not installed. "
            "Run `pip install sentry-sdk` to enable error monitoring. "
            "Continuing without it (errors will still be logged normally)."
        )

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.environ.get("PATTERNFORGE_OUTPUT_DIR", os.path.join(BASE_DIR, "generated"))
DB_PATH = os.environ.get("PATTERNFORGE_DB_PATH", os.path.join(BASE_DIR, "patternforge.db"))
_JOB_ID_RE = re.compile(r"^[0-9a-f]{6,32}$")

# 生成物の保存期間。ディスクを無制限に肥大化させないため、
# 既定では1時間で掃除する（ダウンロードし忘れてもしばらくは残る想定）。
OUTPUT_TTL_SECONDS = int(os.environ.get("PATTERNFORGE_OUTPUT_TTL_SECONDS", 3600))

# アップロード画像の最大ピクセル数（幅×高さ）。MAX_CONTENT_LENGTH(下記)は
# バイト数の上限だが、圧縮率の高いPNG(単色に近いイラスト等)は数百KBのまま
# 数千万〜億単位のピクセル数に展開できてしまう。SimpleSilhouetteSegmenterは
# 画像全体をnumpy配列に複数回コピーするため、対策無しだと数百MB〜数GBの
# メモリを1リクエストで確保してしまい、gunicornワーカーをOOM停止させ、
# 同じワーカーで処理中の他の顧客のリクエストまで巻き添えにする恐れがある。
# Image.open() 自体は多くの形式でヘッダのみ読み画素バッファは確保しないため、
# open()直後・load()より前にサイズを検査することで、実際のデコードコストを
# 払わずに拒否できる。
MAX_UPLOAD_IMAGE_PIXELS = int(os.environ.get("PATTERNFORGE_MAX_IMAGE_PIXELS", 25_000_000))

# Pillow自身も「解凍爆弾」対策として既定でMAX_IMAGE_PIXELS(約1.79億px)超の
# 画像をImage.open()の時点でDecompressionBombErrorとして例外にする。これが
# 有効なままだと、上のMAX_UPLOAD_IMAGE_PIXELS(2500万px)判定に到達する前に
# open()自体が失敗し、_load_uploaded_image()の広いexceptで「画像を読み込め
# ませんでした。対応形式(PNG/JPEG等)かご確認ください」という的外れな
# メッセージになってしまう(実際に手元で1.5万x1.5万pxのPNGを送って確認した
# 実バグ)。今回の上限は既にPillowの既定閾値よりずっと厳しく、かつ
# open()直後・load()より前にサイズだけ検査しているため、Pillow側の
# チェックは不要かつ有害。無効化して、常に上のwidth*height判定を
# 「解像度が大きすぎます」という正しい案内文で行わせる。
Image.MAX_IMAGE_PIXELS = None

# レート制限のクライアント識別に X-Forwarded-For を使うかどうか。
# このヘッダーはクライアントが自由に送れるため、信頼できるリバースプロキシの
# 背後で動かしていない限り、既定では無視して request.remote_addr のみを使う
# （そうしないと、ヘッダー値をリクエストごとに変えるだけでレート制限を
# 無条件に迂回できてしまう）。実際にnginx等のプロキシ配下で動かし、
# プロキシが正しくX-Forwarded-Forを設定し直している場合のみ、
# 環境変数で明示的に有効化すること。
TRUST_PROXY_HEADERS = os.environ.get("PATTERNFORGE_TRUST_PROXY_HEADERS") == "1"

os.makedirs(OUTPUT_DIR, exist_ok=True)

app = Flask(
    __name__,
    template_folder=os.path.join(BASE_DIR, "web", "templates"),
    static_folder=os.path.join(BASE_DIR, "web", "static"),
)
app.config["MAX_CONTENT_LENGTH"] = 12 * 1024 * 1024  # 12MB（イラスト画像アップロード上限）
# SameSite=Lax: 他サイトからの自動送信フォーム(クロスサイトPOST)にセッション
# Cookieを付与しないようブラウザ側で防ぐ、実効性のあるCSRF対策の第一層。
# （第2回監査 指摘: 状態変更エンドポイント全体を保護する完全なCSRFトークン
# 方式ではないため、既存テストへの影響が大きいことを理由に当時は見送っていた
# が、round6で下記`_csrf_protect`のトークン方式を追加し、この制限を解消した。
# SameSite=Laxは、トークン方式の実装に不備があった場合の多層防御として
# 引き続き有効にしておく）。
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
# HTTPS配下で運用する場合はPATTERNFORGE_FORCE_HTTPS=1を設定してSecure属性を
# 付与すること。既定でオフなのは、ローカル開発(HTTP)でログインできなくなる
# のを避けるため。
app.config["SESSION_COOKIE_SECURE"] = os.environ.get("PATTERNFORGE_FORCE_HTTPS") == "1"

# 実際にnginx等のリバースプロキシ配下を想定し、`X-Forwarded-Proto: https`・
# `X-Forwarded-Host`付きのリクエストを実際に(開発用サーバへ)送って見つかった
# 実バグの修正: 本番でよくある構成(プロキシがTLSを終端し、アプリへは平文
# HTTPで転送する)では、Flask/Werkzeugはリクエストがどの経路で来たかを
# 生のソケット接続だけで判断するため、`request.is_secure`は常にFalseになり、
# `url_for(..., _external=True)`が生成するURLは常に`http://`のまま、かつ
# ホスト名も外部向けのドメインではなくアプリが直接bindしている内部アドレス
# になってしまう。これはメール本文に載せる確認/パスワード再設定リンク
# (`_send_verification_email`・`/forgot-password`)にそのまま使われており、
# `PATTERNFORGE_FORCE_HTTPS=1`を設定していても、実際に上記ヘッダー付きで
# `/forgot-password`にPOSTしたところ、メールに載る再設定URLが
# `http://127.0.0.1:5000/reset-password/...`のような、外部の利用者からは
# アクセスできない/HTTPSの意図に反するリンクになることを確認した。
# `PATTERNFORGE_TRUST_PROXY_HEADERS=1`(信頼できる単一のリバースプロキシ
# 配下で動かしている場合のみ有効化する、既存のフラグ。上のX-Forwarded-For
# 対応と同じ前提)が立っている場合のみ、Werkzeug標準の`ProxyFix`で
# `X-Forwarded-Proto`/`X-Forwarded-Host`を1段分信頼してスキーム・ホスト名を
# 補正する(`x_for`はレート制限側の`_client_key()`で個別に、末尾値の抽出まで
# 含めて既に正しく扱っているため、ここでは重複させないよう`x_for=0`にする)。
if TRUST_PROXY_HEADERS:
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=0, x_proto=1, x_host=1, x_port=0, x_prefix=0)

_SECRET_KEY_ENV = os.environ.get("SECRET_KEY")
if not _SECRET_KEY_ENV:
    logging.getLogger(__name__).warning(
        "SECRET_KEY が未設定のため、起動ごとにランダムな鍵を生成しています。"
        "複数ワーカー/複数プロセス構成では各プロセスで鍵が異なり、"
        "セッション(ログイン状態・匿名ジョブの所有権)が正しく機能しません。"
        "本番運用では環境変数 SECRET_KEY に固定の秘密値を設定してください"
        "（例: python -c \"import secrets; print(secrets.token_hex(32))\"）。"
    )
app.secret_key = _SECRET_KEY_ENV or secrets.token_hex(32)

# CSRF検証(下記`_csrf_protect`)を適用しないエンドポイント。billing_webhookは
# ブラウザセッションを経由しない(Stripeサーバーからの直接呼び出し)ため
# セッションCookieを持たず、そもそもCSRFトークンを検証する前提が成立しない。
# 代わりにStripe側の署名検証(`Stripe-Signature`ヘッダー)で保護している。
_CSRF_EXEMPT_ENDPOINTS = {"billing_webhook", "api_v1_generate"}

pipeline = PatternForgePipeline(output_dir=OUTPUT_DIR)
db = store.Store(DB_PATH)
mail = mailer.get_default_mailer()
payment_provider = billing.get_default_provider()


@app.after_request
def _set_security_headers(response):
    """すべてのレスポンスに最低限のセキュリティヘッダーを付与する。

    setdefaultを使っているのは、/download のようにレスポンス側で個別に
    もっと厳しいヘッダー(例: SVGへのContent-Security-Policy: sandbox)を
    設定している場合に、ここで上書きしてしまわないようにするため。
    """
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; object-src 'none'; base-uri 'self'; frame-ancestors 'none'",
    )
    return response


def _client_key() -> str:
    if TRUST_PROXY_HEADERS:
        # 実際にPATTERNFORGE_TRUST_PROXY_HEADERS=1を有効にした状態でサーバを
        # 起動し、`/login`へ間違ったパスワードで15回連続POSTしたところ、
        # 毎回異なる値(例: "10.0.0.1, 203.0.113.9"、"10.0.0.2, 203.0.113.9"...)
        # をX-Forwarded-Forに付けるだけで一度も429にならず、レート制限が
        # 完全に無効化されることを確認した(同じ値を毎回送った場合は正しく
        # 11回目以降429になることも確認済み)。
        #
        # 原因: X-Forwarded-Forはクライアントが自由に最初のエントリを名乗れる
        # ヘッダーで、単一の信頼できるリバースプロキシ経由の場合、プロキシは
        # クライアントが送ってきた値の末尾に「実際に接続してきたIP」を追記する
        # (例: クライアントが"fake, spoofed"と送ると、プロキシ通過後は
        # "fake, spoofed, 実際のIP"になる)。以前はヘッダー値全体をそのまま
        # レート制限の鍵に使っていたため、クライアントが自由に書ける先頭部分
        # を変えるだけで毎回別の鍵として扱われ、TRUST_PROXY_HEADERSを有効化
        # したこと自体が既定(無効時)より安全性を下げてしまっていた
        # (無効時にこの迂回ができないことは
        # test_rate_limit_cannot_be_bypassed_by_spoofing_forwarded_for_header
        # で既にテスト済みだったが、有効時の同じ迂回は未検証だった)。
        #
        # 修正: ヘッダーをカンマ区切りで分解し、末尾(信頼できる直近のプロキシ
        # 自身が追記した部分)だけを鍵に使う。単一のプロキシがX-Forwarded-For
        # を正しく追記モードで運用している前提であり、複数段のプロキシを
        # 経由する構成では、末尾から数えて「信頼できるプロキシの段数」分だけ
        # 遡って取る必要がある(現状は1段のみ対応。将来複数段プロキシ構成に
        # 対応する場合は、信頼するプロキシの段数を別途環境変数化すること)。
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            parts = [p.strip() for p in forwarded.split(",") if p.strip()]
            if parts:
                return parts[-1]
        return request.remote_addr or "unknown"
    return request.remote_addr or "unknown"


@app.template_filter("datetime")
def _format_datetime(epoch_seconds: float) -> str:
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(epoch_seconds))


# round9で追加: index.htmlのプルダウン(ネックライン・袖の形等)の表示テキストを
# 内部識別子のまま出さず、日本語ラベルに変換するためのフィルタ
# (labels.pyのdocstring「実際に開発用サーバーを起動し...見つけた実バグ」参照)。
@app.template_filter("style_label")
def _style_label_filter(value: str | None) -> str:
    return labels.style_label(value)


def _today_str() -> str:
    """UTC日付の文字列(YYYY-MM-DD)。利用回数カウンタの区切り単位。"""
    return time.strftime("%Y-%m-%d", time.gmtime())


def _get_or_create_visitor_id() -> str:
    """未ログインユーザーのジョブ所有権を追跡するための匿名ID。

    Flaskの署名付きセッションクッキーに保存するため、クライアント側で
    値を書き換えて他人のジョブを装うことはできない。
    """
    vid = session.get("visitor_id")
    if not vid:
        vid = secrets.token_hex(16)
        session["visitor_id"] = vid
    return vid


def _get_or_create_csrf_token() -> str:
    """CSRFトークンをセッションから取得し、無ければ発行する。

    `_get_or_create_visitor_id`と同じ発想: Flaskの署名付きセッションCookie
    に保存するため、クライアント側で値を書き換えることはできない。ログイン
    有無にかかわらず(匿名で型紙生成する利用者もいるため)発行する。
    """
    token = session.get("csrf_token")
    if not token:
        token = secrets.token_hex(32)
        session["csrf_token"] = token
    return token


@app.before_request
def _csrf_protect():
    """状態変更リクエスト全体を対象にしたCSRFトークン検証(round6で追加)。

    それまでは`SESSION_COOKIE_SAMESITE=Lax`のみに頼っており、第2回監査で
    「他サイトの自動送信フォームによる強制実行」は防げるが完全なCSRF対策
    ではないと指摘されていた既知の制約。ここでは、GET/HEAD/OPTIONS以外の
    全リクエストに対して、セッションに保存済みのトークンとリクエストに
    含まれるトークン(フォームの`csrf_token`フィールド、またはJSON/AJAX
    向けの`X-CSRFToken`ヘッダー)が一致することを検証する。

    ひとつの`before_request`フックで全エンドポイントを一括保護する設計に
    したのは、各POSTエンドポイントに個別デコレータを付け忘れるリスクを
    無くすため(実際、今回洗い出した時点で状態変更エンドポイントは10個以上
    あり、手動での付け忘れは現実的なリスクだった)。Stripe Webhook
    (`/billing/webhook`)だけは例外(`_CSRF_EXEMPT_ENDPOINTS`)で、そもそも
    ブラウザセッションを経由しない(Stripeサーバーからの直接呼び出しで
    セッションCookie自体を持たない)上、署名検証(`Stripe-Signature`)という
    CSRFより強い方式で保護されているため対象外にしている。
    """
    if request.method in ("GET", "HEAD", "OPTIONS", "TRACE"):
        return None
    if request.endpoint is None or request.endpoint in _CSRF_EXEMPT_ENDPOINTS:
        # endpoint未解決(存在しないパスへのPOST等)はこの後どのみち404に
        # なるため、CSRF検証をする意味が無く素通しする。
        return None

    expected = session.get("csrf_token")
    submitted = request.form.get("csrf_token") or request.headers.get("X-CSRFToken", "")
    if not expected or not submitted or not hmac.compare_digest(expected, submitted):
        app.logger.warning(
            "CSRF token mismatch or missing (endpoint=%s, path=%s)",
            request.endpoint, request.path,
        )
        message = "セキュリティ確認に失敗しました。ページを再読み込みしてからもう一度お試しください。"
        if request.path.startswith("/api/") or request.accept_mimetypes["application/json"] > request.accept_mimetypes["text/html"]:
            return jsonify({"ok": False, "error": message}), 400
        # 第2回監査で見つけた`_login_required`の実バグ(下記参照)と同じ罠を
        # ここでも踏まないよう、あえて`flash()`(=session書き込み)を使わない。
        # SameSite=Laxにより、他サイトからの偽装クロスサイトPOSTはそもそも
        # 本物のセッションCookieを伴わずに届く(=このリクエストのsessionは
        # 空)。この状態で`flash()`を呼ぶと、Flaskは空の新規セッションに
        # フラッシュメッセージを書き込んで`modified`扱いにし、302応答に
        # Set-Cookieを付与してしまう。ログイン中の利用者のブラウザは
        # これを同一オリジンからの正当な応答として受け取り保存するため、
        # 本来のログイン済みセッションCookieが空の新規セッションで
        # 上書きされ、利用者が何もしていないのに強制ログアウトされる
        # (`_login_required`のコメント、および`tests/test_app.py`の
        # `test_login_required_redirect_does_not_touch_session_cookie`参照)。
        # 代わりに`login_required=1`と同じ考え方で、セッションを一切
        # 変更しないクエリ文字列(`csrf_error=1`)だけでエラー状態を伝える。
        # リダイレクト先も`request.referrer`(攻撃者ページである可能性が
        # あり、そこへ誘導するとオープンリダイレクトになりうる)は使わず、
        # 常に固定の安全なページ(トップページ)にする。
        return redirect(url_for("index", csrf_error="1"))
    return None


def _current_user() -> "store.User | None":
    """ログイン中のユーザーを返す。session_versionが一致しない場合は無効化する。

    パスワード再設定時にDB側のsession_versionをインクリメントする(store.py
    set_password参照)ことで、再設定前に発行済みの署名付きセッションCookieを
    「盗まれていても」無効化できる（第2回監査 指摘#1）。ログイン時に
    session["session_version"]へ現在の値を保存しておき、リクエストの度に
    DB上の最新値と比較する。不一致（＝パスワード再設定後の古いCookie）なら
    セッションをその場でクリアし、未ログイン扱いにする。
    """
    if "_current_user_cache" not in g.__dict__:
        user_id = session.get("user_id")
        user = db.get_user(user_id) if user_id else None
        if user is not None and session.get("session_version") != user.session_version:
            session.pop("user_id", None)
            session.pop("session_version", None)
            user = None
        g._current_user_cache = user
    return g._current_user_cache


def _login_session_start(user: "store.User") -> None:
    """ログイン/サインアップ成功時に呼ぶ。session_versionもあわせて保存する。"""
    session["user_id"] = user.id
    session["session_version"] = user.session_version


def _current_org() -> dict | None:
    """ログイン中ユーザーが所属する組織(round8で追加)。未ログイン、または
    どの組織にも所属していない場合はNone。

    リクエストごとに何度も呼ばれる(_current_owner_key/_current_plan_name
    両方から)ため、`_current_user`と同様`g`にキャッシュしてリクエスト内で
    DBへの問い合わせを1回に抑える。
    """
    if "_current_org_cache" not in g.__dict__:
        user = _current_user()
        g._current_org_cache = db.get_org_for_user(user.id) if user else None
    return g._current_org_cache


def _current_owner_key() -> str:
    """生成物の所有権キー。組織に所属するユーザーは`org:<org_id>`を返す。

    これにより、同じ組織のメンバーは互いの生成履歴・利用回数プールを
    共有する(README「組織アカウント」の節、store.pyの該当コメント参照。
    複数人のチームで顧客の型紙を共同管理するという実務ニーズに応える
    ための意図的な設計)。
    """
    org = _current_org()
    if org:
        return f"org:{org['id']}"
    user = _current_user()
    if user:
        return f"user:{user.id}"
    return f"anon:{_get_or_create_visitor_id()}"


def _current_plan_name() -> str:
    """組織に所属するユーザーは組織のプランに従う(個人のplan列は無視する)。"""
    org = _current_org()
    if org:
        return org["plan"]
    user = _current_user()
    return user.plan if user else "anon"


def _daily_limit_for_plan(plan_name: str) -> int | None:
    return store.DEFAULT_DAILY_LIMITS.get(plan_name, store.DEFAULT_DAILY_LIMITS["free"])


_PLAN_DISPLAY_NAMES = {"anon": "未ログイン", "free": "Free", "pro": "Pro"}


def _plan_display_name(plan_name: str) -> str:
    return _PLAN_DISPLAY_NAMES.get(plan_name, plan_name)


def _login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not _current_user():
            # 実際にPlaywright経由の本物のブラウザで、無関係な別オリジンの
            # ページから、ログイン中の利用者のブラウザでこのデコレータ付きの
            # POSTエンドポイント(例:/account/profiles/<id>/delete)へ
            # 自動送信フォームを送るCSRFを実行して見つかった実バグ(修正済み)。
            #
            # SESSION_COOKIE_SAMESITE=Lax(上記コメント参照)により、この
            # クロスサイトPOSTには本物のセッションCookieが付与されず、この
            # if分岐に落ちて保護対象の操作自体は実行されない(実際に
            # プロフィールが削除されていないことをDBで確認済み)。しかし、
            # 以前はここで`flash()`を呼んでいたため、Cookie無しの真新しい
            # 匿名セッションが作られ、そこにフラッシュメッセージが書き込まれて
            # 「変更あり」になり、302応答に新しいSet-Cookieが付与されて
            # いた。ブラウザは(Cookieを送る/送らないの制限とは別に)この
            # Set-Cookieを同一オリジンからの応答として素直に受け取って
            # 保存するため、たとえ本来のログイン済みセッションCookieが
            # ブラウザ側にまだ残っていても、同じCookie名(session)で
            # 上書きされてしまい、利用者が何もしていないのに強制的に
            # ログアウトさせられる(実際にPlaywrightでCookie値の変化を
            # 追跡して確認した)。
            #
            # 対処として、ここでは`flash()`(=session書き込み)を使わず、
            # クエリ文字列でログイン画面に理由を伝える。これでこの
            # リダイレクト応答はセッションを一切変更せずSet-Cookieヘッダーを
            # 出さないため、ブラウザ側の既存Cookie(ログイン済みでも未ログイン
            # でも)をこの分岐が壊すことはなくなる。
            return redirect(url_for("login", login_required="1"))
        return view(*args, **kwargs)
    return wrapped


@app.context_processor
def _inject_template_globals():
    return {
        "current_user": _current_user(),
        "current_year": time.strftime("%Y", time.gmtime()),
        "csrf_token": _get_or_create_csrf_token(),
        # `_csrf_protect`からのリダイレクトの目印(session書き込みを避けて
        # いるため、`show_login_required_notice`と同じクエリ文字列方式)。
        "show_csrf_error_notice": request.args.get("csrf_error") == "1",
    }


# ---------------------------------------------------------------------------
# 生成物・ジョブレコードのバックグラウンド掃除
# ---------------------------------------------------------------------------

_cleanup_lock = Lock()
_last_cleanup_at = 0.0
_CLEANUP_MIN_INTERVAL_SECONDS = 60.0


def _cleanup_old_outputs(max_age_seconds: int = OUTPUT_TTL_SECONDS) -> None:
    """generated/ 内の古いSVG/PDF/DXF/ZIPと、jobsテーブルの古い行を削除する。

    round5でDXF(.dxf、単体ジョブ)とZIP(.zip、複数サイズ一括生成の束ね
    ファイル)を`generated/`に書き出すようになったが、この掃除処理の対象
    拡張子リストに追加するのを忘れており、実際に`export_pattern`/
    `export_multi_size_bundle`が書き出したファイルが1時間経っても一切
    削除されずに残り続ける実バグがあった(生成のたびにディスク使用量が
    増え続ける)。追記して修正。
    """
    now = time.time()
    try:
        for name in os.listdir(OUTPUT_DIR):
            if not name.endswith((".svg", ".pdf", ".dxf", ".zip")):
                continue
            path = os.path.join(OUTPUT_DIR, name)
            try:
                if now - os.path.getmtime(path) > max_age_seconds:
                    os.remove(path)
            except OSError:
                pass  # 他プロセスが同時に消していた等は無視して良い
    except OSError:
        pass  # OUTPUT_DIRが読めない状況でもリクエスト処理自体は継続する
    try:
        db.delete_jobs_older_than(now - max_age_seconds)
    except Exception:  # pragma: no cover - DB掃除の失敗でリクエスト処理を止めない
        app.logger.exception("job cleanup failed")
    try:
        # レート制限(round6でSQLite共有化、_RateLimiter参照)のヒット記録も
        # 同じ掃除サイクルでまとめて古い行を削除する。全バケット中最も長い
        # ウィンドウ幅(現状60秒)より十分大きいmax_age_secondsを使っている
        # ため、アクティブに使われていないバケット/キーの行も取りこぼさない。
        db.delete_rate_limit_hits_older_than(now - max_age_seconds)
    except Exception:  # pragma: no cover - DB掃除の失敗でリクエスト処理を止めない
        app.logger.exception("rate limit hit cleanup failed")
    try:
        # アカウント単位のログイン失敗記録(round7で追加、store.check_account_lockout
        # 参照)も同じ掃除サイクルでまとめて古い行を削除する。
        # ACCOUNT_LOCKOUT_WINDOW_SECONDS(15分)より十分大きいmax_age_secondsを
        # 使っているため、二度とログインを試みないメールアドレスの行も
        # 取りこぼさない。
        db.delete_login_failures_older_than(now - max_age_seconds)
    except Exception:  # pragma: no cover - DB掃除の失敗でリクエスト処理を止めない
        app.logger.exception("login failure record cleanup failed")


def _cleanup_old_outputs_throttled() -> None:
    """掃除を毎リクエストではなく最短間隔を空けて、バックグラウンドで実行する。

    以前は _cleanup_old_outputs() を毎リクエストの先頭で同期的に呼んでいた。
    generated/ に溜まるファイルが増えるほど os.listdir + 各ファイルの
    os.path.getmtime が線形に増え、複数ワーカーが同じディレクトリに対して
    重複した掃除処理を行うことになる。ここでは(a)前回実行から
    _CLEANUP_MIN_INTERVAL_SECONDS以内なら何もしない、(b)実行する場合も
    レスポンスを止めないようバックグラウンドスレッドに投げる、の2点で
    リクエストのレイテンシから掃除コストを切り離している。
    """
    global _last_cleanup_at
    now = time.time()
    with _cleanup_lock:
        if now - _last_cleanup_at < _CLEANUP_MIN_INTERVAL_SECONDS:
            return
        _last_cleanup_at = now
    Thread(target=_cleanup_old_outputs, daemon=True).start()


class _RateLimiter:
    """スライディングウィンドウ方式のレート制限。実体はSQLite(store.py)で、
    複数ワーカー/複数プロセス構成でも共有される(round6で実装)。

    以前はプロセス内メモリ(dequeベース)のみで動いており、複数ワーカー
    (`gunicorn -w N`等)構成では各ワーカーが別々にカウントするため、実際の
    上限が実質N倍緩んでいた。プランごとの1日あたり利用回数上限は既に
    store.pyのSQLiteで複数ワーカー間で共有されていたのに、より短い時間窓の
    こちらのレート制限だけ取り残されていたのは一貫性を欠くと判断し、
    `db.check_rate_limit()`(`check_and_increment_usage()`と同じ
    `BEGIN IMMEDIATE`直列化パターン)に置き換えた。

    `db`はこのモジュールのグローバル変数を実行時に参照する(テストで
    `monkeypatch.setattr(app_module, "db", ...)`により差し替えられた場合も
    追従するようにするため、コンストラクタでの束縛はしない)。
    """

    def __init__(self, bucket: str, max_requests: int, window_seconds: float):
        self.bucket = bucket
        self.max_requests = max_requests
        self.window_seconds = window_seconds

    def allow(self, key: str) -> bool:
        return db.check_rate_limit(self.bucket, key, self.max_requests, self.window_seconds)


_generate_rate_limiter = _RateLimiter("generate", max_requests=20, window_seconds=60.0)
# ダウンロードは生成直後にプレビュー表示・SVG/PDFの取得で複数回叩かれるのが
# 正常系なので、生成本体より緩めの上限にする（不特定多数からの連打防止が目的）。
_download_rate_limiter = _RateLimiter("download", max_requests=90, window_seconds=60.0)
# メール送信系(確認メール再送・パスワード再設定)専用のIPベースレート制限。
# 第2回監査で「これらのエンドポイントに何の制限も無く、他人のメール
# アドレスへの迷惑メール爆撃に悪用できる」と指摘された(指摘#3)。
_email_send_rate_limiter = _RateLimiter("email_send", max_requests=5, window_seconds=60.0)
# ログイン試行専用のIPベースレート制限。
#
# 実際にサーバを起動し、同一アカウント宛に間違ったパスワードで60回連続
# ログインを試したところ、全て400（通常の認証失敗）としてそのまま処理され、
# 429やロックアウトが一切発生しないことを確認した（総当たり攻撃が無制限に
# 可能な状態だった）。/api/generate等の他エンドポイントには既にIPベースの
# レート制限があるのに、/loginにだけ無かったのは見落としと判断し、他の
# 限定と同じ`_RateLimiter`パターンで追加する。
#
# 正直な限界: 他のIPベース制限と同様、単一IPを前提にした安全弁であり(round6
# でプロセス間の共有には対応したが)、IPをローテーションする分散的な
# パスワードスプレー攻撃までは防げない。特定アカウントを狙った本格的な
# 総当たり対策としては、将来的にアカウント単位の失敗回数カウント(CAPTCHA
# 表示や段階的な遅延)への拡張を検討する必要がある。
_login_rate_limiter = _RateLimiter("login", max_requests=10, window_seconds=60.0)
# IPベースの制限だけでは、IPをローテーションする分散的な迷惑メール送信
# （同一の被害者アドレスを狙い撃ちにするケース)を防げないため、
# ユーザー単位・目的単位でのクールダウンもDB側で強制する(store.py参照)。
_EMAIL_TOKEN_COOLDOWN_SECONDS = 60

# /forgot-password の応答時間を一定以上に揃えるための下限(秒)。
#
# 実際にaiosmtpdでローカルSMTPシンクを立て、PATTERNFORGE_MAIL_BACKEND=smtp
# (本番で推奨している構成)で実際にサーバを起動して計測したところ、実在する
# メールアドレスへのリクエストは実際にメール送信を行う分平均約20ms、実在
# しないメールアドレスの場合はメール送信処理自体をスキップするため平均約
# 10msと、応答時間に約2倍の差があることを確認した(ConsoleMailerの既定
# 構成でも約1.5msの差が実測された)。実際のSMTPプロバイダ(Gmail/SES等)を
# 使う本番構成では、TLSハンドシェイク・認証を含む本物のネットワーク往復が
# 発生するため、この差はさらに大きくなる(数百ms単位になりうる)。これは
# ログイン応答時間の件(store.pyのauthenticate()参照)と同種の、実際に
# 悪用可能なタイミングサイドチャネルだった。表示文言は既に「常に同じ」に
# 揃えてあった(既存コメント参照)が、応答時間までは揃っていなかった。
#
# 対策として、リクエスト全体の処理時間がこの下限を下回っていた場合は
# 残り時間分だけ待ってから応答する(どちらの分岐でも下限以上の一定時間を
# 必ずかける)。パスワード認証のダミーハッシュ検証(store.py参照)と違い、
# メール送信のネットワーク往復時間そのものを事前に予測してCPU側だけで
# 再現することはできないため、この「下限まで待つ」方式を採用している。
# 正直な限界として、実際のSMTP送信がこの下限を超えて掛かった場合は、
# その回だけ応答時間差が残ってしまう(下限値は環境に応じて調整すること)。
# テストではPATTERNFORGE_FORGOT_PASSWORD_MIN_SECONDS=0相当に短縮している
# (conftest.py参照)。
_FORGOT_PASSWORD_MIN_RESPONSE_SECONDS = float(
    os.environ.get("PATTERNFORGE_FORGOT_PASSWORD_MIN_SECONDS", "0.3")
)


def _pad_to_min_response_time(start_time: float) -> None:
    remaining = _FORGOT_PASSWORD_MIN_RESPONSE_SECONDS - (time.time() - start_time)
    if remaining > 0:
        time.sleep(remaining)


@app.get("/")
def index():
    plan_name = _current_plan_name()
    limit = _daily_limit_for_plan(plan_name)
    used = db.usage_today(_current_owner_key(), _today_str())
    user = _current_user()
    profiles = db.list_measurement_profiles(user.id) if user else []
    return render_template(
        "index.html",
        necklines=sorted(NECKLINES),
        sleeve_styles=sorted(SLEEVE_STYLES),
        skirt_styles=sorted(SKIRT_STYLES),
        collar_styles=sorted(s for s in COLLAR_STYLES if s),
        cuffs_styles=sorted(s for s in CUFFS_STYLES if s),
        pants_styles=sorted(s for s in PANTS_STYLES if s),
        waistband_styles=sorted(s for s in WAISTBAND_STYLES if s),
        standard_sizes=list(STANDARD_SIZE_ORDER),
        usage={"plan": plan_name, "used_today": used, "daily_limit": limit},
        profiles=profiles,
        # round9で追加: AIパーツ判定ログ表(app.js)がラベル辞書を参照できる
        # よう、data-*属性経由でJSONを渡す(labels.pyのdocstring参照。
        # CSPのscript-src 'self'によりインラインscriptでは渡せないため)。
        variation_labels_json=json.dumps(labels.VARIATION_LABELS_JA, ensure_ascii=False),
        part_type_labels_json=json.dumps(labels.PART_TYPE_LABELS_JA, ensure_ascii=False),
    )


@app.get("/healthz")
def healthz():
    """動作確認用。

    実際にpatternforge.dbのファイルを壊れた内容(SQLiteヘッダを持たない
    テキスト)に置き換えた状態でサーバーを起動して確認した実バグの修正:
    以前はDBに一切触れず常に200 {"ok": true}を返していたため、DBが壊れて
    signup/login等の中核機能が実際には500エラーになっている状況でも、
    ロードバランサ/オーケストレータのヘルスチェックだけは「正常」と判定
    し続け、障害に気付けない・トラフィックを振り分け続けてしまう監視上の
    盲点があった(store.Store.ping()参照)。DBへの軽い到達確認を行い、
    失敗時は503を返す。プロセス自体は生きているが依存先が壊れている状態を
    正しく「異常」として報告できるようにした。
    """
    try:
        db.ping()
    except Exception:
        app.logger.exception("healthz: database ping failed")
        return jsonify({"ok": False, "error": "database unavailable"}), 503
    return jsonify({"ok": True})


@app.get("/favicon.ico")
def favicon():
    # 実際にブラウザで動かして見つけた不具合の修正: ブラウザは各テンプレートの
    # <link rel="icon"> の有無に関係なく、サイトルートの /favicon.ico を毎回
    # 自動的にリクエストする。これまでファイルが無く全ページで404が発生していた
    # （タブにもアイコンが表示されず、コンソールにもエラーが出る）。
    # web/static/favicon.ico を返すことで解消する。
    return send_from_directory(
        os.path.join(BASE_DIR, "web", "static"), "favicon.ico",
        mimetype="image/vnd.microsoft.icon",
    )


# 一般公開する実サービスとしてテストして見つかった不備の修正: robots.txt/
# sitemap.xmlが存在せず、検索エンジンのクローラが巡回時に404を受け取っていた。
# ログイン必須のマイページ・ダウンロード・パスワード再設定等は検索結果に出す
# 意味がないどころか、トークン付きURLが漏れる懸念もあるため明示的に除外し、
# 公開してよいマーケティング系のページだけをサイトマップに列挙する。
_PUBLIC_SITEMAP_ENDPOINTS = (
    "index", "guide", "pricing", "signup", "login", "terms", "privacy", "legal_notice",
)


@app.get("/robots.txt")
def robots_txt():
    lines = [
        "User-agent: *",
        "Disallow: /account",
        "Disallow: /api/",
        "Disallow: /download/",
        "Disallow: /verify/",
        "Disallow: /reset-password/",
        "Disallow: /forgot-password",
        f"Sitemap: {url_for('sitemap_xml', _external=True)}",
        "",
    ]
    return Response("\n".join(lines), mimetype="text/plain")


@app.get("/sitemap.xml")
def sitemap_xml():
    urls = "".join(
        f"<url><loc>{url_for(endpoint, _external=True)}</loc></url>"
        for endpoint in _PUBLIC_SITEMAP_ENDPOINTS
    )
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">' + urls + "</urlset>"
    )
    return Response(xml, mimetype="application/xml")


def _parse_measurements(form) -> Measurements:
    fields = ("bust", "waist", "hip", "height", "sleeve_length", "shoulder_width")
    try:
        values = {name: float(form[name]) for name in fields}
    except KeyError as exc:
        raise ValueError(f"採寸項目が不足しています: {exc}") from exc
    except (TypeError, ValueError) as exc:
        raise ValueError(f"採寸値は数値で入力してください: {exc}") from exc
    return Measurements(**values)


def _bool_field(form, name: str) -> bool:
    return form.get(name) in ("on", "true", "1", "True")


def _bool_field_default(form, name: str, default: bool) -> bool:
    """`_bool_field`と違い、フィールドが送られていない場合はdefaultを返す。

    round10で追加したinclude_body_garment(本体パーツを含めるかどうか)用。
    通常のチェックボックス(`_bool_field`)は「未送信=false」という
    HTMLの標準挙動を前提にしているが、こちらは「未指定なら従来通りTrue
    (本体パーツを含める)」という、既定値がTrue側にある設定のため別関数にした。
    """
    raw = form.get(name)
    if raw is None:
        return default
    return raw in ("on", "true", "1", "True")


# round5で追加した「縫い代を辺ごとに設定可能に」のUI側の許容範囲。
# 下限は「縫い代が細すぎてミシンで扱えない」実用上の目安、上限は
# 「入力ミスで桁を間違えた極端な値を弾く」ための緩い上限であり、
# 縫製上の"正しい"縫い代幅を規定するものではない。
MIN_SEAM_ALLOWANCE_CM = 0.3
MAX_SEAM_ALLOWANCE_CM = 3.0
MIN_HEM_SEAM_ALLOWANCE_CM = 0.3
MAX_HEM_SEAM_ALLOWANCE_CM = 8.0


def _parse_seam_allowance_fields(form) -> tuple[float, float | None]:
    """`seam_allowance_cm`(通常の縫い代)と`hem_seam_allowance_cm`
    (裾だけ別幅にしたい場合。空欄なら通常の縫い代と同じ=従来通り)を
    フォームから読み取り、範囲チェックする。

    どちらも未入力(空文字列)を許容する任意項目にしてある。未入力時は
    seam_allowance_cmはDEFAULT_SEAM_ALLOWANCE_CM(1.0cm)、
    hem_seam_allowance_cmはNone(=通常縫い代と同じ)を返す。
    """
    raw_seam = (form.get("seam_allowance_cm") or "").strip()
    raw_hem = (form.get("hem_seam_allowance_cm") or "").strip()

    if raw_seam:
        try:
            seam_cm = float(raw_seam)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"縫い代は数値で入力してください: {raw_seam!r}") from exc
        if not (MIN_SEAM_ALLOWANCE_CM <= seam_cm <= MAX_SEAM_ALLOWANCE_CM):
            raise ValueError(
                f"縫い代は{MIN_SEAM_ALLOWANCE_CM}〜{MAX_SEAM_ALLOWANCE_CM}cmの範囲で指定してください: {seam_cm}cm"
            )
    else:
        seam_cm = DEFAULT_SEAM_ALLOWANCE_CM

    hem_cm: float | None = None
    if raw_hem:
        try:
            hem_cm = float(raw_hem)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"裾の縫い代は数値で入力してください: {raw_hem!r}") from exc
        if not (MIN_HEM_SEAM_ALLOWANCE_CM <= hem_cm <= MAX_HEM_SEAM_ALLOWANCE_CM):
            raise ValueError(
                f"裾の縫い代は{MIN_HEM_SEAM_ALLOWANCE_CM}〜{MAX_HEM_SEAM_ALLOWANCE_CM}cmの範囲で指定してください: {hem_cm}cm"
            )

    return seam_cm, hem_cm


def _parse_custom_grade_cm(form) -> dict[str, float] | None:
    """カスタムグレーディングルール(round7で追加)をフォームから読み取る。

    フィールド名は`grade_<部位名>`(例: `grade_bust`)で、`STANDARD_SIZE_GRADE_CM`
    の項目のうち入力があったものだけを辞書に含める。全て空欄ならNoneを返し
    (=呼び出し側で完全に既定値のまま扱われる)、1つでも入力があれば
    部分的な上書き用の辞書を返す(`engine.pipeline.PatternForgePipeline.
    generate_multi_size`のdocstring参照。指定しなかった項目は既定値の
    ままになる)。値の範囲チェック自体は`engine.measurements.
    validate_custom_grade_cm()`に委ねる(このアプリのUIから来た値も、
    将来APIを直接叩く利用者の値も、同じ検証を必ず通るようにするため)。
    """
    raw: dict[str, float] = {}
    for field_name in STANDARD_SIZE_GRADE_CM:
        value = (form.get(f"grade_{field_name}") or "").strip()
        if not value:
            continue
        try:
            raw[field_name] = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"カスタムグレーディングルール(grade_{field_name})は数値で入力してください: {value!r}"
            ) from exc
    if not raw:
        return None
    return validate_custom_grade_cm(raw)


def _load_uploaded_image(uploaded) -> Image.Image:
    """アップロードされたイラストを検証しつつ読み込む。

    Image.open() 自体は(多くの形式で)ヘッダのみ読み、画素バッファはまだ
    確保しない。load()を呼ぶ前に幅×高さを検査することで、法外な解像度の
    画像に対して実際のデコード・メモリ確保コストを払わずに拒否できる
    （詳細はMAX_UPLOAD_IMAGE_PIXELSの定義コメントを参照）。

    実際のスマートフォン写真でテストして見つかった不具合の修正: 多くの
    スマホカメラはJPEGを「そのままのセンサー向き」のピクセル配列で保存し、
    表示時にどれだけ回転すべきかをEXIFのOrientationタグ(0x0112)に記録する
    （縦向きで撮った写真が横向きのピクセル配列で保存されているケースが多い）。
    Image.open()はこのタグを見て自動回転はしてくれないため、対策しないと
    「見た目は縦長の服の写真」を実際には90度回転した状態でパーツ分割してしまい、
    ネックライン・裾の位置判定が全てずれる。ImageOps.exif_transpose()で
    見た目通りの向きに正規化してから以降の処理に渡す。
    """
    try:
        image = Image.open(uploaded.stream)
    except Exception as exc:
        raise ValueError("画像を読み込めませんでした。対応形式(PNG/JPEG等)かご確認ください。") from exc

    width, height = image.size
    if width * height > MAX_UPLOAD_IMAGE_PIXELS:
        raise ValueError(
            f"アップロードされた画像の解像度が大きすぎます({width}x{height}px)。"
            "目安として長辺5000px程度以下に縮小してから再度お試しください。"
        )
    try:
        image.load()
        image = ImageOps.exif_transpose(image)
    except Exception as exc:
        raise ValueError("画像を読み込めませんでした。ファイルが破損している可能性があります。") from exc
    return image


def _parse_custom_panels(raw_json: str, measurements: Measurements) -> list[CustomPanelSpec]:
    """`custom_panels_json`フォームフィールド(JSON文字列)を解析し、校正済み
    (cm単位)のCustomPanelSpecのリストに変換する(round10で追加)。

    期待するJSON形式は以下のようなオブジェクトの配列:
      [{"label": "マント", "points": [[x,y], ...],
        "ref_point_a": [x,y], "ref_point_b": [x,y],
        "reference_cm": 40.0,             # または "measurement_field": "shoulder_width"
        "quantity": 1, "mirror": false}, ...]
    座標(points/ref_point_a/ref_point_b)は同じ単位系(通常はアップロード画像の
    ピクセル座標、または手動トレースUIのcanvas座標)であれば何でもよい。
    校正(ピクセル距離→実寸cm)自体は`engine.custom_panel.calibrate_points_to_cm`
    に委譲し、ここでは「JSONとして正しいか」「1リクエストあたりの上限」
    「どのパーツ(何番目/ラベル)が失敗したか分かるメッセージにする」という
    HTTP層固有の関心事だけを扱う。
    """
    try:
        raw_panels = json.loads(raw_json)
    except (TypeError, ValueError) as exc:
        raise ValueError("custom_panels_jsonの形式が不正です(JSONとして解析できませんでした)。") from exc
    if not isinstance(raw_panels, list):
        raise ValueError("custom_panels_jsonはパーツの配列(リスト)にしてください。")
    if len(raw_panels) > MAX_CUSTOM_PANELS_PER_REQUEST:
        raise ValueError(
            f"カスタムパーツは1リクエストあたり{MAX_CUSTOM_PANELS_PER_REQUEST}個までです"
            f"（現在{len(raw_panels)}個）。"
        )

    specs: list[CustomPanelSpec] = []
    for idx, raw in enumerate(raw_panels):
        panel_no = idx + 1
        if not isinstance(raw, dict):
            raise ValueError(f"カスタムパーツ{panel_no}番目の形式が不正です。")
        panel_label_for_error = raw.get("label") if isinstance(raw.get("label"), str) else f"{panel_no}番目"
        try:
            label = validate_label(raw.get("label"))
            quantity = validate_quantity(raw.get("quantity", 1))
            resolved_cm = resolve_reference_cm(
                raw.get("reference_cm"), raw.get("measurement_field"), measurements,
            )
            points_cm = calibrate_points_to_cm(
                raw.get("points"), raw.get("ref_point_a"), raw.get("ref_point_b"), resolved_cm,
            )
            mirror = bool(raw.get("mirror", False))
        except CustomPanelError as exc:
            raise ValueError(f"カスタムパーツ「{panel_label_for_error}」: {exc}") from exc
        specs.append(CustomPanelSpec(label=label, points_cm=points_cm, quantity=quantity, mirror=mirror))
    return specs


def _custom_panel_specs_to_requests(specs: list[CustomPanelSpec]) -> list:
    """校正済みのCustomPanelSpecのリストを、GarmentSpec.partsに追加できる
    PartRequestのリストに変換する(mirror指定のパーツは2枚分に展開される)。
    """
    requests = []
    for spec in specs:
        requests.extend(build_custom_panel_requests(
            spec.label, spec.points_cm, quantity=spec.quantity, mirror=spec.mirror,
        ))
    return requests


_custom_panel_trace_rate_limiter = _RateLimiter("custom_panel_trace", max_requests=20, window_seconds=60.0)


@app.post("/api/custom-panel/trace")
def api_custom_panel_trace():
    """アップロードされたイラスト画像から輪郭を自動抽出する(round10で追加)。

    「アニメ画像からのコスプレ生成」要望に対応するcustom_panel機能
    (engine/custom_panel.py参照)の入力補助エンドポイント。フロントエンドの
    手動トレースUI(round10、web/static/app.js予定)は、まずここに画像を
    送って自動抽出した輪郭を初期値として表示し、利用者はその後クリックで
    頂点を追加・削除・ドラッグ調整できる(「自動抽出＋手動調整の両方」という
    round10のAskUserQuestion回答に対応)。

    実際に型紙を生成する`/api/generate`とは違い、これは輪郭候補を返すだけの
    補助APIのため、1日あたりの生成回数上限(daily usage)は消費しない
    （課金対象は実際にパターンを生成する/api/generateのみ、という既存の
    設計方針を踏襲）。ただし画像処理コスト自体は無視できないため、IPベースの
    レート制限(_custom_panel_trace_rate_limiter)は別途適用する。
    """
    if not _custom_panel_trace_rate_limiter.allow(_client_key()):
        return jsonify({"ok": False, "error": "リクエストが多すぎます。しばらく待って再試行してください。"}), 429
    try:
        uploaded = request.files.get("image")
        if not (uploaded and uploaded.filename):
            raise ValueError("画像がアップロードされていません。")
        image = _load_uploaded_image(uploaded)
        # auto_trace_outlineはSimpleSilhouetteSegmenter固有のメソッド(round9で
        # 追加)。イラストモード本体のパーツ判定に使うget_default_segmenter()
        # (AI判定込みのSAMSegmenter等になりうる)とは無関係に、常にこの
        # 単純な画像処理ベースの輪郭抽出を使う(輪郭トレースはAIのパーツ種
        # 判定とは別の、幾何学的な処理のため)。
        points = SimpleSilhouetteSegmenter().auto_trace_outline(image)
        if points is None:
            return jsonify({
                "ok": False,
                "error": "画像から輪郭を自動抽出できませんでした。背景と衣装の境目がはっきりした"
                          "画像でお試しいただくか、手動で頂点をクリックして輪郭を指定してください。",
            }), 422
        width, height = image.size
        return jsonify({
            "ok": True,
            "points": [[round(x, 1), round(y, 1)] for x, y in points],
            "image_width": width,
            "image_height": height,
        })
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except RequestEntityTooLarge:
        max_mb = app.config["MAX_CONTENT_LENGTH"] / (1024 * 1024)
        return jsonify({"ok": False, "error": f"アップロードされた画像が大きすぎます（上限{max_mb:.0f}MB）。"}), 413
    except Exception:
        error_id = uuid.uuid4().hex[:8]
        app.logger.exception("custom panel auto trace failed [error_id=%s]", error_id)
        return jsonify({
            "ok": False,
            "error": f"内部エラーが発生しました（エラーID: {error_id}）。しばらく待って再試行してください。",
        }), 500


@app.post("/api/generate")
def api_generate():
    if not _generate_rate_limiter.allow(_client_key()):
        return jsonify({"ok": False, "error": "リクエストが多すぎます。しばらく待って再試行してください。"}), 429

    _cleanup_old_outputs_throttled()

    # 生成処理(イラストモードのAI判定・ネスティング等)が失敗した場合に、
    # 既に加算した利用回数を取り消す(refund)必要があるかどうかの目印。
    # 実際に見つかった不具合(store.Store.refund_usageのdocstring参照)の
    # 修正で使う: 以前はcheck_and_increment_usage()が実際の生成処理より前に
    # 呼ばれているため、生成そのものが失敗しても利用回数は減らなかった。
    _usage_owner_key: str | None = None
    _usage_day: str | None = None
    try:
        measurements = _parse_measurements(request.form)
        mode = request.form.get("mode", "manual")
        allow_rotation = _bool_field(request.form, "allow_rotation")
        seam_allowance_cm, hem_seam_allowance_cm = _parse_seam_allowance_fields(request.form)

        image = None
        spec = None
        sizes: list[str] | None = None
        custom_grade_cm: dict[str, float] | None = None
        # round10で追加: 「定型に当てはまらない自由形状パーツ」(custom_panel、
        # engine/custom_panel.py参照)関連の状態。illustration/multi_sizeの
        # 分岐では使わない(未対応、下記参照)ため既定値のまま。
        include_body_garment = True
        custom_panel_specs: list[CustomPanelSpec] = []
        if mode == "illustration":
            uploaded = request.files.get("illustration")
            if not (uploaded and uploaded.filename):
                # イラストモードを選んだのにファイルが無い場合、手動モードの
                # デフォルト選択で黙って生成してしまうと「イラストを見て
                # くれなかった」ことに利用者が気づけない。明確なエラーにする。
                raise ValueError("イラストモードが選択されていますが、画像がアップロードされていません。")
            image = _load_uploaded_image(uploaded)
            if (request.form.get("custom_panels_json") or "").strip():
                # 正直な既知の制約(README参照): custom_panelはround10で
                # 追加したばかりで、AIパーツ判定(イラストモード)側との
                # 組み合わせはまだ検証していない。曖昧に無視するのではなく、
                # 明確なエラーで伝える(カフス+袖なしの既存の扱いと同じ方針)。
                raise ValueError("カスタムパーツ(自由形状)は現在、イラストモードでは併用できません。")
        else:
            # round8で追加: 生成履歴からの再生成機能のため、build_garment_spec
            # に渡す引数をそのままJSONに保存できる辞書として先に組み立てる
            # (下のdb.record_job呼び出し参照)。イラストモードはアップロード
            # 画像自体を保持しないため対象外(この辞書はmode!="illustration"
            # の場合にのみ構築される)。
            garment_spec_kwargs = {
                "neckline": request.form.get("neckline", "round_neck"),
                "sleeve_style": (request.form.get("sleeve_style") or None),
                "skirt_style": (request.form.get("skirt_style") or None),
                "front_zip": _bool_field(request.form, "front_zip"),
                "include_pants": _bool_field(request.form, "include_pants"),
                "pants_style": request.form.get("pants_style", ""),
                "include_collar": _bool_field(request.form, "include_collar"),
                "collar_style": request.form.get("collar_style", ""),
                "include_cuffs": _bool_field(request.form, "include_cuffs"),
                "cuffs_style": request.form.get("cuffs_style", ""),
                "include_waistband": _bool_field(request.form, "include_waistband"),
                "waistband_style": request.form.get("waistband_style", ""),
            }
            raw_custom_panels_json = (request.form.get("custom_panels_json") or "").strip()
            if mode == "multi_size":
                if raw_custom_panels_json:
                    # サイズ展開(グレーディング)はbust/height等の採寸比率で
                    # 各パーツを再スケーリングする仕組みだが、custom_panelは
                    # 校正済みの実寸cmを一切スケーリングしない設計
                    # (PART_SCALE_RULES["custom_panel"]参照)のため、
                    # 「サイズ展開したら小道具だけサイズが変わらない」という
                    # 分かりにくい挙動になる。現時点では明確なエラーにする。
                    raise ValueError("カスタムパーツ(自由形状)は現在、サイズ展開モードでは併用できません。")
                spec = build_garment_spec(**garment_spec_kwargs)
                sizes = request.form.getlist("sizes")
                if not sizes:
                    raise ValueError(
                        "サイズ展開モードでは、生成するサイズを1つ以上選択してください。"
                    )
                # round7で追加。空欄なら従来通り既定のグレーディングルール
                # (STANDARD_SIZE_GRADE_CM)のまま生成する。
                custom_grade_cm = _parse_custom_grade_cm(request.form)
            else:
                # round10で追加: 「体にフィットする本体パーツ(身頃等)」を
                # 含めるかどうか。未指定(既定)なら従来通りTrue(含める)。
                # マント・翼・装甲プレートのような小道具だけをカスタムパーツ
                # として作りたい場合(本体の服は別に用意する/既に持っている)
                # にFalseを指定する(round10のAskUserQuestion「両方お願い」
                # ＝標準の本体パーツとの併用も、カスタムパーツ単独も両方
                # 対応する、という回答に基づく)。
                include_body_garment = _bool_field_default(request.form, "include_body_garment", True)
                spec = build_garment_spec(**garment_spec_kwargs) if include_body_garment else GarmentSpec(parts=[])
                if raw_custom_panels_json:
                    custom_panel_specs = _parse_custom_panels(raw_custom_panels_json, measurements)
                    spec.parts.extend(_custom_panel_specs_to_requests(custom_panel_specs))
                if not spec.parts:
                    raise ValueError(
                        "生成するパーツがありません。本体パーツを含めるか、"
                        "カスタムパーツを1つ以上追加してください。"
                    )

        # 入力検証(採寸値・パーツ構成の組み合わせ・画像の妥当性)を通過した
        # リクエストだけを1回分の利用回数として数える。単純な入力ミスで
        # 400になったリクエストまで課金対象にすると利用者体験が悪い。
        owner_key = _current_owner_key()
        plan_name = _current_plan_name()
        daily_limit = _daily_limit_for_plan(plan_name)
        allowed, used_today = db.check_and_increment_usage(owner_key, daily_limit, _today_str())
        if not allowed:
            return jsonify({
                "ok": False,
                "error": f"本日の生成回数の上限（{daily_limit}回/日、{_plan_display_name(plan_name)}）"
                          "に達しました。プランをアップグレードすると上限が上がります。",
                "upgrade_url": url_for("pricing"),
            }), 429
        # ここまで到達した時点で利用回数は加算済み。これより下で失敗した場合は
        # except側でrefund_usage()を呼んで取り消す必要があるため記録しておく。
        _usage_owner_key, _usage_day = owner_key, _today_str()

        if mode == "illustration":
            result = pipeline.generate_from_illustration(
                image, measurements, allow_rotation=allow_rotation,
                seam_allowance_cm=seam_allowance_cm, hem_seam_allowance_cm=hem_seam_allowance_cm,
            )

            payload = result.summary()
            db.record_job(result.job_id, owner_key, part_count=payload["part_count"],
                          waste_ratio=payload["waste_ratio"])
            payload["download"] = {
                "svg": f"/download/{result.job_id}/svg",
                "pdf": f"/download/{result.job_id}/pdf",
                "dxf": f"/download/{result.job_id}/dxf",
            }
            payload["classification_log"] = [
                {"part_type": c.part_type, "variation": c.variation, "confidence": round(c.confidence, 2),
                 "mode": (c.raw or {}).get("mode", "claude")}
                for c in result.classification_log
            ]
            payload["usage"] = {"plan": plan_name, "used_today": used_today, "daily_limit": daily_limit}
            return jsonify({"ok": True, "mode": mode, **payload})
        elif mode == "multi_size":
            # round5で追加。サイズごとの内訳(採寸の範囲チェック・パーツ構成の
            # 妥当性)は既にbuild_garment_spec/graded_measurements/
            # Measurements側で検証済みのため、ここでは複数回分の生成を
            # まとめて行うだけ。利用回数(check_and_increment_usage)は
            # サイズ数に関わらずこのリクエスト1回分としてのみ課金する
            # (3サイズ生成したら3回分課金する、という設計にはしていない。
            # 正直な仕様として明記しておく)。
            multi = pipeline.generate_multi_size(
                spec, measurements, sizes, allow_rotation=allow_rotation,
                seam_allowance_cm=seam_allowance_cm, hem_seam_allowance_cm=hem_seam_allowance_cm,
                custom_grade_cm=custom_grade_cm,
            )
            total_parts = sum(r.summary()["part_count"] for r in multi.results.values())
            regen_spec = {
                "mode": "multi_size",
                "measurements": measurements.as_dict(),
                "garment_spec": garment_spec_kwargs,
                "sizes": sizes,
                "custom_grade_cm": custom_grade_cm,
                "allow_rotation": allow_rotation,
                "seam_allowance_cm": seam_allowance_cm,
                "hem_seam_allowance_cm": hem_seam_allowance_cm,
            }
            db.record_job(multi.bundle_job_id, owner_key, part_count=total_parts, waste_ratio=None,
                          spec_json=json.dumps(regen_spec))

            results_payload = {}
            for size, result in multi.results.items():
                size_payload = result.summary()
                db.record_job(result.job_id, owner_key, part_count=size_payload["part_count"],
                              waste_ratio=size_payload["waste_ratio"])
                size_payload["download"] = {
                    "svg": f"/download/{result.job_id}/svg",
                    "pdf": f"/download/{result.job_id}/pdf",
                    "dxf": f"/download/{result.job_id}/dxf",
                }
                results_payload[size] = size_payload

            return jsonify({
                "ok": True,
                "mode": mode,
                "sizes": multi.sizes,
                "bundle_job_id": multi.bundle_job_id,
                "base_measurements": multi.base_measurements.as_dict(),
                "results": results_payload,
                "size_consistency_warnings": multi.size_consistency_warnings(),
                "grading_precision_notes": multi.grading_precision_notes(),
                "grade_cm_used": multi.effective_grade_cm(),
                "custom_grade_cm_applied": bool(multi.custom_grade_cm),
                "download": {"zip": f"/download/{multi.bundle_job_id}/zip"},
                "usage": {"plan": plan_name, "used_today": used_today, "daily_limit": daily_limit},
            })
        else:
            result = pipeline.generate_from_selection(
                spec, measurements, allow_rotation=allow_rotation,
                seam_allowance_cm=seam_allowance_cm, hem_seam_allowance_cm=hem_seam_allowance_cm,
            )

            payload = result.summary()
            regen_spec = {
                "mode": "manual",
                "measurements": measurements.as_dict(),
                "garment_spec": garment_spec_kwargs,
                # round10で追加。既存(round10より前)の生成履歴にはこの2キーが
                # 無いが、regenerate_job側は.get()で既定値(True/[])を補うため、
                # 過去の生成履歴の再生成には影響しない。
                "include_body_garment": include_body_garment,
                "custom_panels": [
                    {
                        "label": s.label,
                        "points_cm": [list(p) for p in s.points_cm],
                        "quantity": s.quantity,
                        "mirror": s.mirror,
                    }
                    for s in custom_panel_specs
                ],
                "allow_rotation": allow_rotation,
                "seam_allowance_cm": seam_allowance_cm,
                "hem_seam_allowance_cm": hem_seam_allowance_cm,
            }
            db.record_job(result.job_id, owner_key, part_count=payload["part_count"],
                          waste_ratio=payload["waste_ratio"], spec_json=json.dumps(regen_spec))
            payload["download"] = {
                "svg": f"/download/{result.job_id}/svg",
                "pdf": f"/download/{result.job_id}/pdf",
                "dxf": f"/download/{result.job_id}/dxf",
            }
            payload["classification_log"] = [
                {"part_type": c.part_type, "variation": c.variation, "confidence": round(c.confidence, 2),
                 "mode": (c.raw or {}).get("mode", "claude")}
                for c in result.classification_log
            ]
            payload["usage"] = {"plan": plan_name, "used_today": used_today, "daily_limit": daily_limit}
            return jsonify({"ok": True, "mode": mode, **payload})
    except ValueError as exc:
        # 実際に見つかった不具合の修正(store.Store.refund_usageのdocstring
        # 参照): イラストからパーツ領域/パーツ種を判定できなかった場合等、
        # 利用回数の加算より後で発生するValueErrorも「単純な入力ミス」と
        # 同じ理由で課金対象にすべきでないため、加算済みなら取り消す。
        if _usage_owner_key is not None:
            db.refund_usage(_usage_owner_key, _usage_day)
        return jsonify({"ok": False, "error": str(exc)}), 400
    except RequestEntityTooLarge:
        # アップロード画像が大きすぎるのはクライアント側の入力ミスであり、
        # 「内部エラー」として500を返すのは誤解を招く。413で明確に伝える。
        # (この例外は_load_uploaded_imageより前、Flask自体のリクエスト
        # サイズ制限で発生するため、この時点では利用回数はまだ加算されていない。)
        max_mb = app.config["MAX_CONTENT_LENGTH"] / (1024 * 1024)
        return jsonify({"ok": False, "error": f"アップロードされた画像が大きすぎます（上限{max_mb:.0f}MB）。"}), 413
    except Exception as exc:  # 想定外の例外もJSONで返し、フロント側で表示できるようにする
        if _usage_owner_key is not None:
            db.refund_usage(_usage_owner_key, _usage_day)
        # 以前は str(exc) をそのままクライアントに返していたため、ライブラリ
        # 内部のエラー文字列やファイルパスが有料顧客に漏れる恐れがあった上、
        # 全ての異なるバグが同一の汎用メッセージに潰れ、サポート側がログと
        # 紐付けられなかった。エラーIDを発行してサーバー側ログにはフルの
        # 例外情報を残し、クライアントにはIDだけを返す。
        error_id = uuid.uuid4().hex[:8]
        app.logger.exception("pattern generation failed [error_id=%s]", error_id)
        return jsonify({
            "ok": False,
            "error": f"内部エラーが発生しました（エラーID: {error_id}）。"
                      "しばらく待って再試行するか、このIDをサポートにお伝えください。",
        }), 500


@app.get("/download/<job_id>/<fmt>")
def download(job_id: str, fmt: str):
    if not _download_rate_limiter.allow(_client_key()):
        return jsonify({"ok": False, "error": "リクエストが多すぎます。しばらく待って再試行してください。"}), 429
    if not _JOB_ID_RE.match(job_id) or fmt not in ("svg", "pdf", "dxf", "zip"):
        return jsonify({"ok": False, "error": "invalid request"}), 400

    # 以前はjob_id(12桁16進数)を知っているだけで誰でもダウンロードできた。
    # job_idはプレビューリンクのReferer等で漏れうるうえ、body測定値から
    # 生成された個人性のあるファイルなので、生成したセッション/アカウント
    # 以外からはアクセスできないようにする。存在しない場合と所有者が違う
    # 場合を同じ404にすることで、他人のjob_idが存在するかどうかを外部から
    # 探索できないようにしている。
    job_owner = db.get_job_owner(job_id)
    if job_owner is None or job_owner != _current_owner_key():
        return jsonify({"ok": False, "error": "not found"}), 404

    filename = f"{job_id}.{fmt}"
    if not os.path.isfile(os.path.join(OUTPUT_DIR, filename)):
        return jsonify({"ok": False, "error": "not found"}), 404

    response = send_from_directory(OUTPUT_DIR, filename, as_attachment=(fmt in ("pdf", "dxf", "zip")))
    # 顧客の身体測定値に由来するファイルなので、共有プロキシ/CDN等に
    # キャッシュされて別の利用者に渡ってしまうことを防ぐ。
    response.headers["Cache-Control"] = "private, no-store"
    if fmt == "svg":
        # SVGはブラウザで直接開くと埋め込みscriptを実行できてしまう。今は
        # SVG内に利用者が持ち込んだ自由文字列は含まれないため実害は無いが、
        # 将来自由入力欄が増えたときのために、このレスポンスに対する
        # スクリプト実行・フォーム送信等を無効化しておく。
        response.headers["Content-Security-Policy"] = "sandbox"
    return response


# ---------------------------------------------------------------------------
# アカウント・プラン（テスト実装。モジュールdocstring参照）
# ---------------------------------------------------------------------------

@app.get("/signup")
def signup():
    if _current_user():
        return redirect(url_for("account"))
    return render_template("signup.html")


@app.post("/signup")
def signup_submit():
    email = request.form.get("email", "")
    password = request.form.get("password", "")
    try:
        user_id = db.create_user(email, password)
    except (ValueError, store.EmailAlreadyRegisteredError) as exc:
        flash(str(exc), "error")
        return render_template("signup.html", email=email), 400

    _adopt_anonymous_jobs_into_account(user_id)
    _login_session_start(db.get_user(user_id))
    flash("登録しました。", "success")
    _send_verification_email(user_id, email)
    return redirect(url_for("account"))


def _deliver_verification_email(email: str, token: str) -> None:
    """既に発行済みのverifyトークンでメールを送る(送信部分のみ)。

    サインアップ直後(クールダウン確認不要、常に新規トークンを発行)と、
    再送(`/account/resend-verification`。クールダウン確認込みでトークンを
    発行する必要がある)の両方から、トークン発行の方法だけを差し替えて
    使えるように送信部分だけを分離している。
    """
    verify_url = url_for("verify_email", token=token, _external=True)
    try:
        mail.send(
            email,
            "PatternForge — メールアドレスの確認",
            f"以下のURLをクリックしてメールアドレスを確認してください（{store.EMAIL_VERIFY_TOKEN_TTL_SECONDS // 3600}時間有効）:\n{verify_url}",
        )
    except Exception:  # pragma: no cover - メール送信基盤の障害でサインアップ自体は失敗させない
        app.logger.exception("failed to send verification email")
    if mail.is_console:
        # 開発時のフォールバック: SMTPが未設定のため実際にはメールが届かない。
        # フローを最後まで試せるよう、確認用URLを画面にも表示する。
        flash(f"[開発用] 確認メールは送信されていません。このURLで確認できます: {verify_url}", "success")


def _send_verification_email(user_id: int, email: str) -> None:
    """サインアップ直後に呼ぶ。クールダウン確認は不要(初回発行なので常に許可)。"""
    token = db.create_email_token(user_id, "verify", store.EMAIL_VERIFY_TOKEN_TTL_SECONDS)
    _deliver_verification_email(email, token)


@app.get("/verify/<token>")
def verify_email(token: str):
    user_id = db.consume_email_token(token, "verify")
    if user_id is None:
        # 実際に見つかった不具合の修正(store.Store.peek_verify_token_user_id
        # のdocstring参照): 企業のメールセキュリティゲートウェイ(Microsoft
        # Defender for Office 365のSafe Links等)が、利用者が実際にクリック
        # する前にメール内のリンクを自動的に「事前アクセス」してマルウェア
        # 検査を行うことが広く知られている。このURLはGETだけでトークンを
        # 消費するため、その自動prefetchが先にトークンを使用済みにしてしまい、
        # 利用者本人が後から同じリンクを開くと以前は無条件に「リンクが無効、
        # または期限切れ」と表示していた。実際には確認自体は(prefetchの時点で)
        # 完了しているため、これは実害のあるユーザー体験上の不具合だった
        # (実際に「別クライアントが先にGET→本人が同じリンクを開く」という
        # 手順で再現して確認した)。既に確認済みであれば、エラーではなく
        # 成功として案内する。
        fallback_user_id = db.peek_verify_token_user_id(token)
        fallback_user = db.get_user(fallback_user_id) if fallback_user_id else None
        if fallback_user and fallback_user.email_verified:
            flash("メールアドレスを確認しました。", "success")
            return redirect(url_for("account") if _current_user() else url_for("login"))
        flash("確認用リンクが無効、または有効期限が切れています。マイページから再送してください。", "error")
        return redirect(url_for("index"))
    db.mark_email_verified(user_id)
    flash("メールアドレスを確認しました。", "success")
    if _current_user():
        return redirect(url_for("account"))
    return redirect(url_for("login"))


@app.post("/account/resend-verification")
@_login_required
def resend_verification():
    user = _current_user()
    if user.email_verified:
        flash("既に確認済みです。", "success")
        return redirect(url_for("account"))
    if not _email_send_rate_limiter.allow(_client_key()):
        flash("リクエストが多すぎます。しばらく待って再試行してください。", "error")
        return redirect(url_for("account"))
    # クールダウン確認とトークン発行を1つのDBトランザクションで行う
    # (store.Store.try_create_email_token_with_cooldownのdocstring参照。
    # 以前は確認と発行が別のDB呼び出しに分かれており、実際に真の並行リクエスト
    # で試したところ20回中18回もクールダウンをすり抜けてしまう実バグがあった)。
    token = db.try_create_email_token_with_cooldown(
        user.id, "verify", _EMAIL_TOKEN_COOLDOWN_SECONDS, store.EMAIL_VERIFY_TOKEN_TTL_SECONDS,
    )
    if token is None:
        flash("確認メールを送信済みです。しばらく待ってから再度お試しください。", "error")
        return redirect(url_for("account"))
    _deliver_verification_email(user.email, token)
    flash("確認メールを再送しました。", "success")
    return redirect(url_for("account"))


@app.get("/login")
def login():
    if _current_user():
        return redirect(url_for("account"))
    # login_required=1は_login_requiredデコレータからのリダイレクトの目印。
    # session(flash)を経由せずクエリ文字列だけで伝える理由は、
    # _login_requiredのコメント参照(セッションを書き換えて既存Cookieを
    # 上書きする副作用を避けるため)。
    show_login_required_notice = request.args.get("login_required") == "1"
    return render_template("login.html", show_login_required_notice=show_login_required_notice)


@app.post("/login")
def login_submit():
    if not _login_rate_limiter.allow(_client_key()):
        flash("ログイン試行が多すぎます。しばらく待ってから再試行してください。", "error")
        return render_template("login.html", email=request.form.get("email", "")), 429

    email = request.form.get("email", "")
    password = request.form.get("password", "")

    # round7で追加: 上のIPベースの制限とは別に、アカウント(メールアドレス)
    # 単位でも総当たりを防ぐ。多数のIP/ボットネットを使い分けて1つの
    # メールアドレスのパスワードを狙う分散的な総当たりは、IPベースの制限
    # だけでは防げないため(store.check_account_lockout()のdocstring参照)。
    # ロック中はdb.authenticate()(bcrypt/scrypt相当のコストがかかる実際の
    # パスワード照合)自体を呼ばない。実在しないメールアドレスでも同じ
    # ロック判定を行う(存在有無をロックの有無から推測させないため)。
    lockout_remaining = db.check_account_lockout(email)
    if lockout_remaining > 0:
        wait_minutes = max(1, math.ceil(lockout_remaining / 60))
        flash(
            f"試行回数が多すぎるため、このアカウントへのログインを一時的に"
            f"制限しています。約{wait_minutes}分後に再度お試しください。",
            "error",
        )
        return render_template("login.html", email=email), 429

    user = db.authenticate(email, password)
    if not user:
        db.record_login_failure(email)
        flash("メールアドレスまたはパスワードが正しくありません。", "error")
        return render_template("login.html", email=email), 400

    db.clear_login_failures(email)
    _adopt_anonymous_jobs_into_account(user.id)
    _login_session_start(user)
    flash("ログインしました。", "success")
    return redirect(url_for("account"))


def _adopt_anonymous_jobs_into_account(user_id: int) -> None:
    """未ログインで生成したジョブの所有権を、ログイン/登録後の本人に引き継ぐ。

    先にログイン後の所有権キーへ引き継いでからsession["user_id"]をセット
    すること(呼び出し側の順序に注意)。visitor_idが無い(初回訪問がそのまま
    サインアップだった)場合は何もしない。
    """
    vid = session.get("visitor_id")
    if vid:
        db.reassign_jobs(f"anon:{vid}", f"user:{user_id}")


@app.post("/logout")
def logout():
    session.pop("user_id", None)
    session.pop("session_version", None)
    flash("ログアウトしました。", "success")
    return redirect(url_for("index"))


@app.get("/forgot-password")
def forgot_password():
    if _current_user():
        return redirect(url_for("account"))
    return render_template("forgot_password.html")


@app.post("/forgot-password")
def forgot_password_submit():
    start_time = time.time()
    email = request.form.get("email", "")
    # IPベースのレート制限。ただしここで429等を返して早期リターンすると、
    # 「このIPは制限されているが、他の応答は常に同じ文言」という違いから
    # 間接的に情報が漏れるわけではない(単に迷惑行為の抑止が目的)ため、
    # 制限にかかった場合も後続と同じ画面に遷移させて構わない。
    allowed_by_ip = _email_send_rate_limiter.allow(_client_key())
    user = db.get_user_by_email(email)
    if user and allowed_by_ip:
        # ユーザー単位のクールダウン(store.py参照)。IPローテーションを使った
        # 分散的なメール爆撃を防ぐため、IP制限とは別にDB側でも強制する。
        # クールダウン確認とトークン発行を1つのDBトランザクションで行う
        # (store.Store.try_create_email_token_with_cooldownのdocstring参照。
        # 以前は`seconds_since_last_token()`で確認してから別途
        # `create_email_token()`を呼ぶ2段構えで、実際に真の並行リクエストで
        # 試したところ20回中18回もクールダウンをすり抜けてしまう実バグが
        # あった)。
        token = db.try_create_email_token_with_cooldown(
            user.id, "reset", _EMAIL_TOKEN_COOLDOWN_SECONDS, store.PASSWORD_RESET_TOKEN_TTL_SECONDS,
        )
        if token is not None:
            reset_url = url_for("reset_password", token=token, _external=True)
            try:
                mail.send(
                    user.email,
                    "PatternForge — パスワードの再設定",
                    f"以下のURLからパスワードを再設定してください（{store.PASSWORD_RESET_TOKEN_TTL_SECONDS // 60}分有効）:\n{reset_url}",
                )
            except Exception:  # pragma: no cover
                app.logger.exception("failed to send password reset email")
            if mail.is_console:
                flash(f"[開発用] 再設定メールは送信されていません。このURLで再設定できます: {reset_url}", "success")
    # メールアドレスが登録されているかどうか・レート制限にかかったかどうかで
    # 文言を変えると、そのメールアドレスが登録済みかどうかを外部から探索
    # できてしまう(user enumeration)ため、常に同じ文言を表示する。
    #
    # 文言だけでなく応答時間も揃える(_FORGOT_PASSWORD_MIN_RESPONSE_SECONDS
    # のコメント参照)。実際にメール送信を行った分岐は既にこの下限に近い/
    # 超えている場合が多く、その場合はここでの追加待機はほぼ発生しない。
    _pad_to_min_response_time(start_time)
    flash("そのメールアドレスが登録されている場合、パスワード再設定用のメールを送信しました。", "success")
    return redirect(url_for("login"))


@app.get("/reset-password/<token>")
def reset_password(token: str):
    return render_template("reset_password.html", token=token)


@app.post("/reset-password/<token>")
def reset_password_submit(token: str):
    password = request.form.get("password", "")
    # 以前は db.consume_email_token(token, "reset") でトークンを先に消費し、
    # その後 db.set_password() を呼んでいたため、パスワードの検証(8文字未満)
    # で失敗した場合でもトークンは既に使用済みになり、利用者が正しい
    # パスワードで再送信しても「リンクが無効/期限切れ」という誤解を招く
    # エラーになってしまう不具合があった(実際に再現・修正済み。詳細は
    # store.Store.reset_password_with_token のdocstring参照)。
    # トークンの検証・消費とパスワード変更を1つのDBトランザクションに
    # まとめた db.reset_password_with_token() を使うことで、パスワードが
    # 無効な場合はトークンが消費されず、同じリンクで再試行できるようにした。
    try:
        user_id = db.reset_password_with_token(token, password)
    except ValueError as exc:
        flash(str(exc), "error")
        return render_template("reset_password.html", token=token), 400
    if user_id is None:
        flash("再設定用リンクが無効、または有効期限が切れています。もう一度お試しください。", "error")
        return redirect(url_for("forgot_password"))
    flash("パスワードを再設定しました。新しいパスワードでログインしてください。", "success")
    return redirect(url_for("login"))


@app.get("/account")
@_login_required
def account():
    user = _current_user()
    org = _current_org()
    plan_name = _current_plan_name()
    owner_key = _current_owner_key()
    limit = _daily_limit_for_plan(plan_name)
    used = db.usage_today(owner_key, _today_str())
    jobs = db.list_jobs_for_owner(owner_key)
    profiles = db.list_measurement_profiles(user.id)
    api_keys = db.list_api_keys(user.id)
    org_members = db.list_org_members(org["id"]) if org else []
    return render_template(
        "account.html", user=user, limit=limit, used=used, jobs=jobs, profiles=profiles,
        max_profiles=store.MAX_MEASUREMENT_PROFILES_PER_USER,
        is_mock_billing=payment_provider.is_mock,
        org=org, org_members=org_members, plan_display=_plan_display_name(plan_name),
        api_keys=api_keys, max_api_keys=store.Store.MAX_API_KEYS_PER_USER,
    )


# ---------------------------------------------------------------------------
# 採寸プロフィール（複数顧客・家族分の採寸値を名前付きで保存・呼び出し）
# ---------------------------------------------------------------------------

@app.post("/api/profiles")
@_login_required
def create_measurement_profile():
    """トップページの生成フォームから、現在入力中の採寸値を名前付きで保存する。

    fetch(AJAX)で呼ばれる想定のJSON API。生成結果を保持したまま(ページ
    遷移なしで)保存できるようにするため、/account/profiles とは別に用意
    している（そちらはマイページからの削除用フォームPOSTで使う）。
    """
    user = _current_user()
    try:
        measurements = _parse_measurements(request.form)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    name = request.form.get("name", "")
    try:
        profile_id = db.create_measurement_profile(
            user.id, name, measurements.bust, measurements.waist, measurements.hip,
            measurements.height, measurements.sleeve_length, measurements.shoulder_width,
        )
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    profile = db.get_measurement_profile(profile_id, user.id)
    return jsonify({"ok": True, "profile": profile})


@app.post("/account/profiles/<int:profile_id>/delete")
@_login_required
def delete_measurement_profile(profile_id: int):
    user = _current_user()
    if db.delete_measurement_profile(profile_id, user.id):
        flash("プロフィールを削除しました。", "success")
    else:
        flash("プロフィールが見つかりませんでした。", "error")
    return redirect(url_for("account"))


# ---------------------------------------------------------------------------
# APIキー(round8で追加: B2B向けプログラマティックAPI)
# ---------------------------------------------------------------------------

@app.post("/account/api-keys")
@_login_required
def create_api_key():
    user = _current_user()
    name = request.form.get("name", "")
    try:
        _key_id, raw_key = db.create_api_key(user.id, name)
    except ValueError as exc:
        flash(str(exc), "error")
        return redirect(url_for("account"))
    # 生の鍵はこの応答でしか見られない(DBにはハッシュしか残らない)ため、
    # 目立つ形でその場に表示する。flash()はセッションに一時保存されるだけ
    # で外部に送信されないため、ここで表示すること自体に問題は無い
    # (ただしブラウザの「戻る」でキャッシュされたページに残る可能性がある
    # 共有端末での利用には注意が必要。この点はガイド/READMEに明記する)。
    flash(
        f"APIキーを発行しました。この鍵は今だけ表示されます。安全な場所に保存してください: {raw_key}",
        "success",
    )
    return redirect(url_for("account"))


@app.post("/account/api-keys/<int:key_id>/revoke")
@_login_required
def revoke_api_key(key_id: int):
    user = _current_user()
    if db.revoke_api_key(key_id, user.id):
        flash("APIキーを失効させました。", "success")
    else:
        flash("APIキーが見つかりませんでした。", "error")
    return redirect(url_for("account"))


def _require_api_key() -> "store.User | None":
    """`Authorization: Bearer <key>`ヘッダーからAPIキー認証する。B2B向け
    プログラマティックAPI(/api/v1/*)専用。ブラウザセッション(Cookie)による
    認証とは完全に別経路であり、CSRFトークンの検証対象にもしていない
    (ブラウザのセッションCookieを一切使わないため、そもそもCSRFが成立しない。
    _CSRF_EXEMPT_ENDPOINTSに`api_v1_generate`を追加しているのはこのため)。
    """
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return None
    raw_key = auth_header[len("Bearer "):].strip()
    return db.authenticate_api_key(raw_key)


@app.post("/api/v1/generate")
def api_v1_generate():
    """プログラマティックAPI(B2B向け)。ブラウザのCookie/CSRFトークンでは
    なく、`Authorization: Bearer pf_live_...`ヘッダーのAPIキーで認証する。

    正直な実装レベルの注記(スコープの限界): 既存の/api/generate(ブラウザ
    フォームからの利用)にある、イラストモード・サイズ展開モードは今回は
    対応しない。B2Bの利用シナリオ(自社システムから採寸値とパーツ構成を
    渡して型紙を得る)で最も必要になる「手動選択モード」のみを最小構成で
    提供する(今後の拡張候補としてREADMEに明記する)。リクエストボディは
    `/api/generate`と同じフォームフィールド(multipart/form-data、または
    application/x-www-form-urlencoded)を受け付ける。

    利用回数上限・レート制限は、鍵の持ち主のプラン・所有権キー
    (`user:<id>`、組織所属時は`org:<id>`)にそのまま従う(ブラウザ経由の
    利用と共有のプールになる。API専用の別枠は用意していない)。
    """
    if not _generate_rate_limiter.allow(_client_key()):
        return jsonify({"ok": False, "error": "リクエストが多すぎます。しばらく待って再試行してください。"}), 429

    user = _require_api_key()
    if user is None:
        return jsonify({"ok": False, "error": "無効なAPIキーです。Authorization: Bearer <key> ヘッダーを確認してください。"}), 401

    org = db.get_org_for_user(user.id)
    owner_key = f"org:{org['id']}" if org else f"user:{user.id}"
    plan_name = org["plan"] if org else user.plan
    daily_limit = _daily_limit_for_plan(plan_name)

    _usage_owner_key: str | None = None
    try:
        measurements = _parse_measurements(request.form)
        allow_rotation = _bool_field(request.form, "allow_rotation")
        seam_allowance_cm, hem_seam_allowance_cm = _parse_seam_allowance_fields(request.form)
        garment_spec_kwargs = {
            "neckline": request.form.get("neckline", "round_neck"),
            "sleeve_style": (request.form.get("sleeve_style") or None),
            "skirt_style": (request.form.get("skirt_style") or None),
            "front_zip": _bool_field(request.form, "front_zip"),
            "include_pants": _bool_field(request.form, "include_pants"),
            "pants_style": request.form.get("pants_style", ""),
            "include_collar": _bool_field(request.form, "include_collar"),
            "collar_style": request.form.get("collar_style", ""),
            "include_cuffs": _bool_field(request.form, "include_cuffs"),
            "cuffs_style": request.form.get("cuffs_style", ""),
            "include_waistband": _bool_field(request.form, "include_waistband"),
            "waistband_style": request.form.get("waistband_style", ""),
        }
        spec = build_garment_spec(**garment_spec_kwargs)

        allowed, used_today = db.check_and_increment_usage(owner_key, daily_limit, _today_str())
        if not allowed:
            return jsonify({
                "ok": False,
                "error": f"本日の生成回数の上限（{daily_limit}回/日）に達しました。",
            }), 429
        _usage_owner_key = owner_key

        result = pipeline.generate_from_selection(
            spec, measurements, allow_rotation=allow_rotation,
            seam_allowance_cm=seam_allowance_cm, hem_seam_allowance_cm=hem_seam_allowance_cm,
        )
        payload = result.summary()
        regen_spec = {
            "mode": "manual",
            "measurements": measurements.as_dict(),
            "garment_spec": garment_spec_kwargs,
            "allow_rotation": allow_rotation,
            "seam_allowance_cm": seam_allowance_cm,
            "hem_seam_allowance_cm": hem_seam_allowance_cm,
        }
        db.record_job(result.job_id, owner_key, part_count=payload["part_count"],
                      waste_ratio=payload["waste_ratio"], spec_json=json.dumps(regen_spec))
        payload["download"] = {
            "svg": f"/download/{result.job_id}/svg",
            "pdf": f"/download/{result.job_id}/pdf",
            "dxf": f"/download/{result.job_id}/dxf",
        }
        payload["usage"] = {"used_today": used_today, "daily_limit": daily_limit}
        return jsonify({"ok": True, **payload})
    except ValueError as exc:
        if _usage_owner_key is not None:
            db.refund_usage(_usage_owner_key, _today_str())
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception:
        if _usage_owner_key is not None:
            db.refund_usage(_usage_owner_key, _today_str())
        error_id = uuid.uuid4().hex[:8]
        app.logger.exception("api v1 generation failed [error_id=%s]", error_id)
        return jsonify({
            "ok": False,
            "error": f"内部エラーが発生しました（エラーID: {error_id}）。",
        }), 500


# ---------------------------------------------------------------------------
# 組織アカウント(round8で追加: 最小構成のチーム機能。store.pyの
# 「組織アカウント」節のコメントに、スコープの限界を含めて詳しく記載)
# ---------------------------------------------------------------------------

@app.post("/org/create")
@_login_required
def org_create():
    user = _current_user()
    name = request.form.get("name", "")
    try:
        db.create_organization(user.id, name)
    except ValueError as exc:
        flash(str(exc), "error")
        return redirect(url_for("account"))
    flash("組織を作成しました。", "success")
    return redirect(url_for("account"))


@app.post("/org/invite")
@_login_required
def org_invite():
    user = _current_user()
    org = _current_org()
    if not org:
        flash("組織に所属していません。", "error")
        return redirect(url_for("account"))
    if org["owner_user_id"] != user.id:
        flash("メンバーの招待はオーナーのみ行えます。", "error")
        return redirect(url_for("account"))
    if not _email_send_rate_limiter.allow(_client_key()):
        flash("リクエストが多すぎます。しばらく待って再試行してください。", "error")
        return redirect(url_for("account"))
    email = request.form.get("email", "")
    try:
        token = db.create_org_invite(org["id"], email, user.id)
    except ValueError as exc:
        flash(str(exc), "error")
        return redirect(url_for("account"))
    invite_url = url_for("org_accept_invite", token=token, _external=True)
    try:
        mail.send(
            email.strip().lower(),
            f"PatternForge — 「{org['name']}」への招待",
            f"「{org['name']}」チームに招待されました。以下のURLから参加してください"
            f"（{store.Store.ORG_INVITE_TOKEN_TTL_SECONDS // 86400}日間有効）:\n{invite_url}",
        )
    except Exception:  # pragma: no cover - メール送信基盤の障害で招待発行自体は失敗させない
        app.logger.exception("failed to send org invite email")
    if mail.is_console:
        flash(f"[開発用] 招待メールは送信されていません。このURLで参加できます: {invite_url}", "success")
    flash(f"{email} を招待しました。", "success")
    return redirect(url_for("account"))


@app.get("/org/invites/<token>")
def org_accept_invite_page(token: str):
    invite = db.get_org_invite(token)
    if invite is None:
        flash("招待リンクが無効です。", "error")
        return redirect(url_for("index"))
    org = db.get_organization(invite["org_id"])
    return render_template("org_invite.html", invite=invite, org=org, token=token)


@app.post("/org/invites/<token>/accept")
@_login_required
def org_accept_invite(token: str):
    user = _current_user()
    try:
        org_id = db.accept_org_invite(token, user.id)
    except ValueError as exc:
        flash(str(exc), "error")
        return redirect(url_for("account"))
    if org_id is None:
        flash(
            "招待を受諾できませんでした（リンクが無効・期限切れ、または"
            "招待先メールアドレスとログイン中のアカウントが一致しません）。",
            "error",
        )
        return redirect(url_for("index"))
    flash("組織に参加しました。", "success")
    return redirect(url_for("account"))


@app.post("/org/members/<int:member_user_id>/remove")
@_login_required
def org_remove_member(member_user_id: int):
    user = _current_user()
    org = _current_org()
    if not org:
        flash("組織に所属していません。", "error")
        return redirect(url_for("account"))
    # オーナー本人か、自分自身(自主退会)のみ許可する。
    if org["owner_user_id"] != user.id and member_user_id != user.id:
        flash("他のメンバーを外せるのはオーナーのみです。", "error")
        return redirect(url_for("account"))
    if member_user_id == org["owner_user_id"]:
        flash("オーナーは組織から外せません。組織を解散する場合は「組織を解散」を使ってください。", "error")
        return redirect(url_for("account"))
    if db.remove_org_member(org["id"], member_user_id):
        flash("メンバーを外しました。" if member_user_id != user.id else "組織から抜けました。", "success")
    else:
        flash("メンバーが見つかりませんでした。", "error")
    return redirect(url_for("account"))


@app.post("/org/disband")
@_login_required
def org_disband():
    user = _current_user()
    org = _current_org()
    if not org:
        flash("組織に所属していません。", "error")
        return redirect(url_for("account"))
    try:
        db.disband_organization(org["id"], user.id)
    except ValueError as exc:
        flash(str(exc), "error")
        return redirect(url_for("account"))
    flash("組織を解散しました。", "success")
    return redirect(url_for("account"))


# ---------------------------------------------------------------------------
# アカウント削除・データエクスポート(round8で追加)
# ---------------------------------------------------------------------------

@app.get("/account/export")
@_login_required
def account_export():
    """自分のデータ一式をJSONファイルとしてダウンロードする。

    個人情報保護法(APPI)の開示請求への対応、およびサービス移行・記録保持
    のためのデータポータビリティ手段として提供する。パスワードハッシュ・
    APIキーの秘密値は含めない(store.Store.export_user_dataのdocstring
    参照)。
    """
    user = _current_user()
    data = db.export_user_data(user.id)
    body = json.dumps(data, ensure_ascii=False, indent=2)
    response = Response(body, mimetype="application/json")
    response.headers["Content-Disposition"] = (
        f'attachment; filename="patternforge_data_{user.id}_{_today_str()}.json"'
    )
    response.headers["Cache-Control"] = "private, no-store"
    return response


@app.get("/account/delete")
@_login_required
def account_delete_confirm():
    """退会の確認画面(パスワード再入力を要求する)。"""
    org = _current_org()
    return render_template("account_delete.html", org=org)


@app.post("/account/delete")
@_login_required
def account_delete_submit():
    """アカウントを完全に削除する(退会)。

    実際に動かして見つかった設計上の考慮点: ログイン済みセッションを
    乗っ取られた状態(例えばXSS等で盗まれたセッションCookie)からの誤操作・
    悪用による取り返しのつかない削除を防ぐため、パスワード確認フォーム
    ログインパスワードそのものを要求する(単なる「削除」ボタンのクリック
    だけでは実行できないようにする)。
    """
    user = _current_user()
    password = request.form.get("password", "")
    if not db.authenticate(user.email, password):
        flash("パスワードが正しくないため、削除できませんでした。", "error")
        return redirect(url_for("account_delete_confirm"))

    if not payment_provider.is_mock and user.stripe_subscription_id:
        try:
            payment_provider.cancel_subscription(user.stripe_subscription_id)
        except Exception:
            app.logger.exception(
                "failed to cancel stripe subscription during account deletion for user_id=%s", user.id
            )
            flash(
                "サブスクリプションの解約に失敗したため削除できませんでした。"
                "しばらくしてから再度お試しいただくか、サポートにご連絡ください。",
                "error",
            )
            return redirect(url_for("account_delete_confirm"))

    try:
        db.delete_user_account(user.id)
    except ValueError as exc:
        flash(str(exc), "error")
        return redirect(url_for("account"))

    session.pop("user_id", None)
    session.pop("session_version", None)
    flash("アカウントを削除しました。ご利用ありがとうございました。", "success")
    return redirect(url_for("index"))


@app.post("/account/jobs/<job_id>/regenerate")
@_login_required
def regenerate_job(job_id: str):
    """生成履歴の1件を、保存済みの入力(spec_json)から再生成する(round8で追加)。

    実際に動かして見つかった既存の制約への対応: 生成物(SVG/PDF/DXF)自体は
    OUTPUT_TTL_SECONDS(既定1時間)で自動削除されるため、それより後に
    マイページから再ダウンロードしようとしても失敗していた。入力
    (採寸値・パーツ構成等)さえ`jobs.spec_json`に残っていれば、同じ設定で
    型紙を作り直せるようにする。通常の/api/generateと同じ利用回数上限・
    レート制限を適用する(タダで無制限に再生成できると上限の意味が無くなる
    ため)。イラストモードで生成した履歴はアップロード画像自体を保持して
    いないため再生成できない(正直な限界。README参照)。
    """
    if not _generate_rate_limiter.allow(_client_key()):
        flash("リクエストが多すぎます。しばらく待って再試行してください。", "error")
        return redirect(url_for("account"))
    if not _JOB_ID_RE.match(job_id):
        flash("不正なリクエストです。", "error")
        return redirect(url_for("account"))

    owner_key = _current_owner_key()
    regen_spec = db.get_job_regeneration_spec(job_id, owner_key)
    if regen_spec is None:
        flash(
            "この生成履歴は再生成できません（イラストモードから生成された、"
            "または他のバージョンで生成されたため入力データが保存されていません）。",
            "error",
        )
        return redirect(url_for("account"))

    plan_name = _current_plan_name()
    daily_limit = _daily_limit_for_plan(plan_name)
    allowed, _used_today = db.check_and_increment_usage(owner_key, daily_limit, _today_str())
    if not allowed:
        flash(
            f"本日の生成回数の上限（{daily_limit}回/日、{_plan_display_name(plan_name)}）に達しました。",
            "error",
        )
        return redirect(url_for("account"))

    try:
        measurements = Measurements(**regen_spec["measurements"])
        garment_spec_kwargs = regen_spec["garment_spec"]
        # round10で追加: include_body_garment/custom_panelsは古い(round10より
        # 前の)生成履歴のspec_jsonには存在しないため、.get()で既定値
        # (True/空リスト=従来通り本体パーツのみ)を補う。これにより、
        # round10より前に生成された履歴の再生成は一切挙動が変わらない。
        include_body_garment = regen_spec.get("include_body_garment", True)
        spec = build_garment_spec(**garment_spec_kwargs) if include_body_garment else GarmentSpec(parts=[])
        for panel in regen_spec.get("custom_panels", []):
            spec.parts.extend(build_custom_panel_requests(
                panel["label"],
                [tuple(p) for p in panel["points_cm"]],
                quantity=panel.get("quantity", 1),
                mirror=panel.get("mirror", False),
            ))
        allow_rotation = regen_spec.get("allow_rotation", False)
        seam_allowance_cm = regen_spec.get("seam_allowance_cm", DEFAULT_SEAM_ALLOWANCE_CM)
        hem_seam_allowance_cm = regen_spec.get("hem_seam_allowance_cm")

        if regen_spec["mode"] == "multi_size":
            sizes = regen_spec["sizes"]
            custom_grade_cm = regen_spec.get("custom_grade_cm")
            multi = pipeline.generate_multi_size(
                spec, measurements, sizes, allow_rotation=allow_rotation,
                seam_allowance_cm=seam_allowance_cm, hem_seam_allowance_cm=hem_seam_allowance_cm,
                custom_grade_cm=custom_grade_cm,
            )
            total_parts = sum(r.summary()["part_count"] for r in multi.results.values())
            db.record_job(multi.bundle_job_id, owner_key, part_count=total_parts, waste_ratio=None,
                          spec_json=json.dumps(regen_spec))
            for size, result in multi.results.items():
                size_payload = result.summary()
                db.record_job(result.job_id, owner_key, part_count=size_payload["part_count"],
                              waste_ratio=size_payload["waste_ratio"])
            flash(f"再生成しました。ダウンロード: /download/{multi.bundle_job_id}/zip （ZIP一括）", "success")
        else:
            result = pipeline.generate_from_selection(
                spec, measurements, allow_rotation=allow_rotation,
                seam_allowance_cm=seam_allowance_cm, hem_seam_allowance_cm=hem_seam_allowance_cm,
            )
            payload = result.summary()
            db.record_job(result.job_id, owner_key, part_count=payload["part_count"],
                          waste_ratio=payload["waste_ratio"], spec_json=json.dumps(regen_spec))
            flash(
                f"再生成しました。ダウンロード: /download/{result.job_id}/svg （SVG） "
                f"/download/{result.job_id}/pdf （PDF）",
                "success",
            )
        return redirect(url_for("account"))
    except Exception:
        db.refund_usage(owner_key, _today_str())
        error_id = uuid.uuid4().hex[:8]
        app.logger.exception("regeneration failed [error_id=%s]", error_id)
        flash(f"再生成に失敗しました（エラーID: {error_id}）。", "error")
        return redirect(url_for("account"))


@app.post("/account/upgrade")
@_login_required
def account_upgrade():
    user = _current_user()
    org = _current_org()
    if org:
        # round8で追加: 組織に所属する場合はプランを組織単位で切り替える
        # (個人のplan列は無視する。_current_plan_name参照)。実際のStripe
        # 連携での組織単位請求は未実装(正直な限界。store.pyの組織関連の
        # コメント、READMEの既知の制約を参照)なので、モックモード以外では
        # 実行させず案内だけ表示する。
        if org["owner_user_id"] != user.id:
            flash("プランの変更は組織のオーナーのみ行えます。", "error")
            return redirect(url_for("account"))
        if org["plan"] == "pro":
            flash("既にProプランです。", "success")
            return redirect(url_for("account"))
        if not payment_provider.is_mock:
            flash(
                "組織プランでの実際の決済連携は現在未対応です。個人アカウントでの"
                "アップグレードのみStripe連携に対応しています。",
                "error",
            )
            return redirect(url_for("account"))
        db.set_org_plan(org["id"], "pro")
        flash("テストモードで組織をPro相当に切り替えました（実際の決済は発生していません）。", "success")
        return redirect(url_for("account"))
    if user.plan == "pro":
        # 二重クリック・フォーム再送信でStripe側に重複したCheckout
        # Session/サブスクリプションを作らないためのガード(第2回監査 指摘#7)。
        flash("既にProプランです。", "success")
        return redirect(url_for("account"))
    if payment_provider.is_mock:
        db.set_plan(user.id, "pro")
        flash("テストモードでPro相当に切り替えました（実際の決済は発生していません）。", "success")
        return redirect(url_for("account"))

    checkout_url = payment_provider.start_checkout(
        user,
        success_url=url_for("account", upgraded=1, _external=True),
        cancel_url=url_for("pricing", _external=True),
    )
    return redirect(checkout_url)


@app.post("/account/downgrade")
@_login_required
def account_downgrade():
    user = _current_user()
    org = _current_org()
    if org:
        if org["owner_user_id"] != user.id:
            flash("プランの変更は組織のオーナーのみ行えます。", "error")
            return redirect(url_for("account"))
        db.set_org_plan(org["id"], "free")
        flash("組織をFreeプランに戻しました。", "success")
        return redirect(url_for("account"))
    if not payment_provider.is_mock and user.stripe_subscription_id:
        try:
            payment_provider.cancel_subscription(user.stripe_subscription_id)
        except Exception:
            app.logger.exception("failed to cancel stripe subscription for user_id=%s", user.id)
            flash("解約処理に失敗しました。しばらくしてから再度お試しください。", "error")
            return redirect(url_for("account"))
        # 実際のplan更新はWebhook(customer.subscription.deleted)側で確定させる
        # のが正式な経路だが、解約操作をした利用者に即座にUI上で反映するため
        # ここでも先行して更新する(Webhookが後から来ても同じ状態に収束する)。
    #
    # 実際に動かして見つかった不具合(修正済み): 以前はここで単純に
    # db.set_plan(user.id, "free") を呼んでいたため、users.last_billing_event_at
    # (round21で追加したWebhook配信順序保護の基準値)がこの「即時反映」の
    # 際に更新されなかった。この状態で、キャンセル操作より前に生成された
    # (=時系列としては古いが、last_billing_event_atよりは新しいcreatedを
    # 持つ)Webhookイベント――例えば、キャンセル直前の決済成功で発生した
    # customer.subscription.updated(status=active)がStripe側の配信遅延で
    # 今になって届く場合――が後から処理されると、db.apply_billing_event()の
    # 古さ判定をすり抜けてplanが"pro"に巻き戻ってしまうことを、実際に
    # (1)決済成功Webhookを適用→pro、(2)このエンドポイントでfreeへ即時反映
    # (旧実装のset_plan相当)、(3)キャンセル前に生成された古いactive
    # Webhookを適用、という手順を直接実行して確認した(3の適用後、意図せず
    # planがproへ戻ってしまった)。この即時反映も
    # db.apply_billing_event()を通し、現在時刻をcreatedとして
    # last_billing_event_atを更新するようにすることで、キャンセル操作より
    # 前に生成された古いWebhookが後から届いても無視されるようにした
    # (実際に正しいcustomer.subscription.deletedのWebhookが確定として
    # 届く分には、その`created`は当然この即時反映より新しいため問題無く
    # 適用される)。
    db.apply_billing_event(user.id, time.time(), "free")
    flash("Freeプランに戻しました。", "success")
    return redirect(url_for("account"))


@app.post("/billing/webhook")
def billing_webhook():
    """Stripe Webhook。支払い確定/解約をここで正式に確定させる。

    アップグレード操作直後のリダイレクト(success_url)だけを頼りにplanを
    更新すると、利用者がリダイレクトを中断した場合に支払い済みなのに
    planが更新されないままになりうる。Webhookで確定させることで、
    ブラウザ側の状態に関係なく正しいplanに収束させる。
    """
    if payment_provider.is_mock:
        return jsonify({"ok": False, "error": "billing not configured"}), 404

    webhook_secret = os.environ.get("STRIPE_WEBHOOK_SECRET")
    if not webhook_secret:
        app.logger.error("Stripe webhook received but STRIPE_WEBHOOK_SECRET is not set")
        return jsonify({"ok": False, "error": "webhook secret not configured"}), 500

    payload = request.get_data()
    sig_header = request.headers.get("Stripe-Signature", "")
    try:
        event = payment_provider.construct_webhook_event(payload, sig_header, webhook_secret)
    except Exception:
        app.logger.exception("invalid stripe webhook signature")
        return jsonify({"ok": False, "error": "invalid signature"}), 400

    event_type = event["type"]
    obj = event["data"]["object"]
    # 実際に本物のStripeライブラリ(stripe-python)でWebhookイベントを構築して
    # 見つかった実バグの修正: construct_webhook_event()が返す`obj`は素の
    # dictではなく`stripe._stripe_object.StripeObject`で、`__getitem__`は
    # 使えるが`.get()`は実装されていない(呼ぶと
    # 「'get' is a dict method, but a StripeObject is not a dict」という
    # AttributeErrorになる)。以前のテストは`construct_webhook_event`自体を
    # 素のdictを返すモックに置き換えていたため、この不整合に気付けず、
    # 本物のStripe連携ではWebhookが来るたびに毎回500エラーになり、
    # 支払い確定(plan更新)が一度も成功しない状態だった。`.to_dict()`で
    # 素のdictに変換してから`.get()`を使うようにする。
    if hasattr(obj, "to_dict"):
        obj = obj.to_dict()

    # 実際に本物のstripeライブラリ・本物のHMAC署名で「支払い失敗
    # (past_due, 生成時刻t1) → リトライで復旧(active, 生成時刻t2>t1)」の
    # 2つのイベントを構築し、Stripeの公式ドキュメントが明記している
    # 「Webhookイベントの配信順序は保証されない」仕様通りに、新しいイベント
    # (active)を先に、古いイベント(past_due、再送/遅延で後から届いた)を
    # 後にサーバへ届けたところ、以前はどのイベントも受信した順にそのまま
    # planを上書きしていたため、実際には直近の状態が"active"(pro)である
    # にもかかわらず、後から届いた古い"past_due"イベントによってplanが
    # "free"へ巻き戻され、そのまま固定されてしまう実バグを確認した(詳細は
    # store.Store.apply_billing_event のdocstring参照)。イベントの
    # `created`(発生時刻)を`db.apply_billing_event()`に渡し、既に適用済みの
    # イベントより古い場合は無視するようにして、配信順序に依存せず常に
    # 最新の内容へ収束するように修正した。
    event_created_at = event["created"]

    if event_type == "checkout.session.completed":
        user_id_raw = obj.get("client_reference_id")
        # client_reference_id はStripe側の設定ミスや、こちらの実装変更・
        # 手動テスト等で数値以外や存在しないuser_idが来る可能性がある。
        # ここで例外を握りつぶさずに500を返すと、Stripeが同じイベントを
        # 再送し続けてログを埋め尽くすため、不正な形式は警告ログを残した上で
        # 200を返し「処理済み」としてStripe側の再送を止める(第2回監査 指摘#6)。
        if user_id_raw:
            try:
                user_id = int(user_id_raw)
            except (TypeError, ValueError):
                app.logger.warning(
                    "stripe webhook: client_reference_id is not an integer: %r", user_id_raw
                )
            else:
                if db.get_user(user_id) is None:
                    app.logger.warning(
                        "stripe webhook: checkout.session.completed for unknown user_id=%s", user_id
                    )
                else:
                    db.apply_billing_event(
                        user_id, event_created_at, "pro",
                        stripe_customer_id=obj.get("customer"),
                        stripe_subscription_id=obj.get("subscription"),
                    )
        else:
            app.logger.warning("stripe webhook: checkout.session.completed missing client_reference_id")
    elif event_type == "customer.subscription.deleted":
        customer_id = obj.get("customer")
        user = db.get_user_by_stripe_customer_id(customer_id) if customer_id else None
        if user:
            db.apply_billing_event(user.id, event_created_at, "free")
    elif event_type == "customer.subscription.updated":
        # 実際に本物のstripeライブラリ・本物のHMAC署名でWebhookイベントを
        # 構築し、支払い失敗(invoice.payment_failed)→サブスクリプションが
        # past_due状態になる(customer.subscription.updated)という実際の
        # Stripeの流れを再現してサーバに送ったところ、以前はこのイベント
        # 種別を一切処理しておらず、支払いが失敗してもplanが"pro"のまま
        # 変わらず、無制限に生成し続けられる状態だった(既存のテストは
        # checkout.session.completedとcustomer.subscription.deletedしか
        # 検証しておらず、この抜けに気付けなかった)。Stripeは支払い失敗時、
        # 通常はリトライ期間中はcustomer.subscription.deletedを送らず
        # (Stripe側のSmart Retries設定によっては、リトライを使い切っても
        # 自動キャンセルされずunpaidのまま残ることもある)、代わりに
        # このイベントのstatusフィールドでpast_due/unpaid等の状態変化を
        # 通知してくるため、statusを見て追従する必要がある。
        # active/trialingは支払いが正常な状態としてpro維持、それ以外
        # (past_due/unpaid/incomplete_expired/paused等)はpro機能を無制限に
        # 使わせるべきではないためfreeに戻す。リトライで支払いが復旧して
        # 再びactiveに戻った場合も、同じイベントで自動的にproへ復帰する。
        customer_id = obj.get("customer")
        status = obj.get("status")
        user = db.get_user_by_stripe_customer_id(customer_id) if customer_id else None
        if user:
            db.apply_billing_event(
                user.id, event_created_at, "pro" if status in ("active", "trialing") else "free",
            )

    return jsonify({"ok": True})


@app.get("/pricing")
def pricing():
    return render_template(
        "pricing.html", limits=store.DEFAULT_DAILY_LIMITS, is_mock_billing=payment_provider.is_mock,
    )


@app.get("/guide")
def guide():
    """使い方ガイド（操作マニュアル）。

    アカウント登録の有無に関わらず内容を読めるよう、ログイン必須にはしない。
    """
    return render_template(
        "guide.html", limits=store.DEFAULT_DAILY_LIMITS,
        max_profiles=store.MAX_MEASUREMENT_PROFILES_PER_USER,
    )


# ---------------------------------------------------------------------------
# 法的表示（利用規約・プライバシーポリシー・運営者情報）
# ---------------------------------------------------------------------------
#
# アカウント登録・メール送信・決済(Stripe)を扱う以上、これらのページは
# 実際に一般公開する前に必須。ただし事業者名・所在地・連絡先といった
# 実際の情報はこのリポジトリには含められないため、テンプレート内に
# 「[事業者名を入力]」のようなプレースホルダーを残している。公開前に
# 必ず実際の情報に差し替えること（README「公開前チェックリスト」参照）。

@app.get("/terms")
def terms():
    return render_template("terms.html")


@app.get("/privacy")
def privacy():
    return render_template("privacy.html")


@app.get("/legal")
def legal_notice():
    return render_template("legal.html")


# ---------------------------------------------------------------------------
# エラーページ
# ---------------------------------------------------------------------------

@app.errorhandler(RequestEntityTooLarge)
def _handle_request_entity_too_large(exc):
    """アップロードサイズ超過(413)を一貫したJSON/HTMLで返す。

    round6でCSRF検証(`_csrf_protect`)を追加したことで、multipart
    フォームのボディ解析(`request.form`へのアクセス)がbefore_requestの
    時点で発生するようになった。これにより、以前は`/api/generate`の
    view関数内のtry/exceptで捕まえていた`RequestEntityTooLarge`が、
    view関数に到達する前(before_requestの中)で送出されるケースが生まれた
    (実際にテストで確認: CSRF検証追加前は`/api/generate`のtry/exceptが
    捕捉していたため413+JSONを返せていたが、追加後はFlask標準の
    HTML形式の413ページになってしまっていた)。ここでグローバルな
    エラーハンドラを追加することで、view到達前後どちらで発生しても
    一貫したレスポンスになるようにする。
    """
    if request.path.startswith("/api/") or request.accept_mimetypes["application/json"] > request.accept_mimetypes["text/html"]:
        max_mb = app.config["MAX_CONTENT_LENGTH"] / (1024 * 1024)
        return jsonify({"ok": False, "error": f"アップロードされた画像が大きすぎます（上限{max_mb:.0f}MB）。"}), 413
    return render_template("500.html", error_id="413"), 413


@app.errorhandler(404)
def _handle_not_found(exc):
    if request.path.startswith("/api/") or request.accept_mimetypes["application/json"] > request.accept_mimetypes["text/html"]:
        return jsonify({"ok": False, "error": "not found"}), 404
    return render_template("404.html"), 404


@app.errorhandler(500)
def _handle_server_error(exc):
    # 想定外の例外の詳細はログにのみ残し、利用者にはIDだけを返す
    # (/api/generate の例外ハンドリングと同じ方針)。
    error_id = uuid.uuid4().hex[:8]
    app.logger.exception("unhandled server error [error_id=%s]", error_id)
    if request.path.startswith("/api/") or request.accept_mimetypes["application/json"] > request.accept_mimetypes["text/html"]:
        return jsonify({"ok": False, "error": f"internal error (id: {error_id})"}), 500
    return render_template("500.html", error_id=error_id), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=os.environ.get("FLASK_DEBUG") == "1")
