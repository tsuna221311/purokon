"""store.py — 商用サービス化のための最小限の永続化層(SQLite)。

有料サービスとして提供するには最低限、

  1) 生成したジョブが誰の所有物かを追跡し、他人がダウンロードできないようにする
     （以前は job_id を知っているだけで誰でもダウンロードできてしまっていた）。
  2) （任意の）アカウントでログインし、プランを永続化する。
  3) プランごとの1日あたりの生成回数上限を強制する。
  4) メールアドレス確認・パスワード再設定用の使い捨てトークンを管理する。
  5) Stripe連携時の顧客ID・サブスクリプションIDを保持する。

の5つが必要になる。ここではSQLite1ファイルで済む最小実装を用意した。

正直な注記（本物の実装とモック実装の区別）:
  - パスワードのハッシュ化(werkzeug.security)・セッション管理・利用回数の
    上限強制・メール確認/パスワード再設定用トークンの発行と検証は「本物」の
    実装（実際にセキュリティ上の効果がある）。
  - メール送信自体は mailer.py 経由（既定はConsoleMailerで実際には送信
    しない。SMTP環境変数を設定すれば本物のメールが飛ぶ）。
  - 決済は billing.py 経由（STRIPE_SECRET_KEY / STRIPE_PRICE_ID が未設定
    ならDB上のplan列をテストモードで即時切り替えるだけのモック。設定時は
    実際にStripeのCheckout Sessionを作成する）。
  - SQLiteはこの規模のサービスには十分だが、複数サーバーに水平分散する構成には
    そのままでは向かない（将来PostgreSQL等に置き換えることを想定した薄い層に
    している。SQL文が他モジュールに漏れないよう、このファイルだけを差し替えれば
    済むようにしてある）。
  - 接続は呼び出しごとに開いて閉じる単純な実装。低トラフィックのサービス規模
    では十分だが、高頻度アクセスが増えた場合は接続プールへの置き換えを検討する。
"""

from __future__ import annotations
import hashlib
import json
import re
import secrets
import sqlite3
import time
from contextlib import closing
from dataclasses import dataclass

from werkzeug.security import check_password_hash, generate_password_hash

# メールアドレスの形式チェック用。
#
# 正直な注記: RFC 5321/5322 準拠の完全なメールアドレス構文（コメント、
# 引用文字列ローカルパート、IPアドレスドメインリテラル等）は網羅していない、
# 実用目的の簡易パターン。以前は "@" が含まれているかだけしかチェックして
# おらず、'abc@' や '@example.com' 、空白を含むアドレス、ローカルパートに
# マルチバイト文字を含むアドレス（'山田太郎@example.com' 等）まで通ってしまって
# いた。マルチバイト文字を含むアドレスがそのまま mailer.py 経由で送信されると、
# SMTPUTF8 拡張に対応していないメールサーバー相手には無効なヘッダーとして
# 配送に失敗する恐れがある。ここでは「空白を含まない」「@がちょうど1個」
# 「ローカルパート・ドメインパートが半角英数字と一部の記号のみ」「ドメイン部に
# ドットが1つ以上ある」ことを最低限強制する。
_EMAIL_RE = re.compile(
    r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?"
    r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?)+$"
)

# 実際にサーバーを起動して`/signup`へ100,000文字の「メールアドレス」を
# 送ってみたところ、200で受理されアカウントが作成されてしまうことを確認した
# 実バグの修正。上の`_EMAIL_RE`は文字種・形式だけを見ており、長さの上限が
# 無いため`+`が無制限にマッチしてしまう。RFC 5321 4.5.3.1.3のメールアドレス
# 全体の実務上の上限(254文字)を明記の上、この長さを超えるものは形式チェック
# より前に拒否する。長さを制限する理由は2つ: (1) SMTP送信を実際に設定した
# 運用では、RFC上限を超えるアドレスを受け付けるメールサーバーは無いため、
# 「アカウントは作成できたのに確認メールが永遠に届かない」という気付きにくい
# 詰みを防ぐ、(2) 1リクエストあたり最大`MAX_CONTENT_LENGTH`(12MB)までの
# 任意長の文字列を`email`カラムに書き込めてしまう、実質無制限のDB容量消費を
# 防ぐ。
MAX_EMAIL_LENGTH = 254

DEFAULT_DAILY_LIMITS: dict[str, int | None] = {
    # 匿名利用（ログインなし）。ログイン済みfreeより厳しくして、
    # 無料アカウント作成へのそれなりの誘導にする。
    "anon": 3,
    "free": 10,
    # None = 無制限（Pro。Stripe連携済みなら実際の課金、未設定ならテストモード）。
    "pro": None,
}

#: メール確認トークンの有効期限。
EMAIL_VERIFY_TOKEN_TTL_SECONDS = 24 * 3600
#: パスワード再設定トークンの有効期限（漏洩時の被害を抑えるため短めにする）。
PASSWORD_RESET_TOKEN_TTL_SECONDS = 3600
#: 1ユーザーが保存できる採寸プロフィールの上限（無制限のディスク消費・
#: 迷惑目的の大量作成を防ぐための安全弁。複数顧客管理という通常の用途では
#: 十分な件数）。
MAX_MEASUREMENT_PROFILES_PER_USER = 50

# round7で追加: アカウント単位のログイン総当たり対策(check_account_lockout
# 参照)。IPベースのレート制限(app.py の _login_rate_limiter、round6で追加)
# だけでは、多数のIPを使い分けて1つのメールアドレスを狙う分散的な
# パスワード総当たり(1つのIPあたりの試行回数は制限内に収まる)を防げない
# という限界があった。これに対応するため、メールアドレス単位でも失敗回数を
# 記録し、一定回数を超えたら段階的に長くなるロックアウトをかける。
#: この秒数より古い失敗記録は「もう関係ない」とみなして数えない
#: (ローリングウィンドウ)。
ACCOUNT_LOCKOUT_WINDOW_SECONDS = 15 * 60
#: この回数の失敗が(ウィンドウ内に)溜まったらロックアウトを開始する。
ACCOUNT_LOCKOUT_THRESHOLD = 5
#: ロックアウト開始直後の待機秒数。閾値を超えるたびに倍々に増えていく
#: (指数バックオフ)。
ACCOUNT_LOCKOUT_BASE_SECONDS = 30.0
#: ロックアウト秒数の上限(指数バックオフが際限なく伸びないようにする)。
ACCOUNT_LOCKOUT_MAX_SECONDS = 15 * 60.0

# authenticate()が「メールアドレスが登録されているかどうか」を応答時間の
# 差で外部に漏らさないようにするためだけのダミーハッシュ(実際の認証には
# 一切使わない)。詳細はauthenticate()内のコメント参照。generate_password_hash
# 自体もscrypt由来でそれなりに時間がかかるため、モジュール読み込み時では
# なく初回に必要になった時点で1回だけ計算してキャッシュする。
_DUMMY_PASSWORD_HASH: str | None = None


def _dummy_password_hash() -> str:
    global _DUMMY_PASSWORD_HASH
    if _DUMMY_PASSWORD_HASH is None:
        _DUMMY_PASSWORD_HASH = generate_password_hash(secrets.token_hex(16))
    return _DUMMY_PASSWORD_HASH


@dataclass(frozen=True)
class User:
    id: int
    email: str
    plan: str
    created_at: float
    email_verified: bool = False
    stripe_customer_id: str | None = None
    stripe_subscription_id: str | None = None
    session_version: int = 1
    last_billing_event_at: float | None = None


class EmailAlreadyRegisteredError(ValueError):
    pass


class Store:
    """users / jobs / usage_counters / email_tokens を保持する薄いSQLiteラッパー。"""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=5.0)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        return conn

    def _init_schema(self) -> None:
        with closing(self._connect()) as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    plan TEXT NOT NULL DEFAULT 'free',
                    created_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS jobs (
                    job_id TEXT PRIMARY KEY,
                    owner_key TEXT NOT NULL,
                    created_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS usage_counters (
                    owner_key TEXT NOT NULL,
                    day TEXT NOT NULL,
                    count INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (owner_key, day)
                );
                CREATE TABLE IF NOT EXISTS email_tokens (
                    token TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    purpose TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    expires_at REAL NOT NULL,
                    used_at REAL
                );
                CREATE TABLE IF NOT EXISTS measurement_profiles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    bust REAL NOT NULL,
                    waist REAL NOT NULL,
                    hip REAL NOT NULL,
                    height REAL NOT NULL,
                    sleeve_length REAL NOT NULL,
                    shoulder_width REAL NOT NULL,
                    created_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS rate_limit_hits (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    bucket TEXT NOT NULL,
                    rl_key TEXT NOT NULL,
                    ts REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS login_failures (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email_key TEXT NOT NULL,
                    ts REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS api_keys (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    key_hash TEXT UNIQUE NOT NULL,
                    key_prefix TEXT NOT NULL,
                    name TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    last_used_at REAL,
                    revoked_at REAL
                );
                CREATE TABLE IF NOT EXISTS organizations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    owner_user_id INTEGER NOT NULL,
                    plan TEXT NOT NULL DEFAULT 'free',
                    created_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS org_members (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    org_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    role TEXT NOT NULL DEFAULT 'member',
                    joined_at REAL NOT NULL,
                    UNIQUE(user_id)
                );
                CREATE TABLE IF NOT EXISTS org_invites (
                    token TEXT PRIMARY KEY,
                    org_id INTEGER NOT NULL,
                    email TEXT NOT NULL,
                    invited_by_user_id INTEGER NOT NULL,
                    created_at REAL NOT NULL,
                    expires_at REAL NOT NULL,
                    accepted_at REAL
                );
                CREATE INDEX IF NOT EXISTS idx_jobs_owner_key ON jobs(owner_key);
                CREATE INDEX IF NOT EXISTS idx_email_tokens_user_id ON email_tokens(user_id);
                CREATE INDEX IF NOT EXISTS idx_measurement_profiles_user_id ON measurement_profiles(user_id);
                CREATE INDEX IF NOT EXISTS idx_rate_limit_hits_bucket_key_ts
                    ON rate_limit_hits(bucket, rl_key, ts);
                CREATE INDEX IF NOT EXISTS idx_login_failures_email_key_ts
                    ON login_failures(email_key, ts);
                CREATE INDEX IF NOT EXISTS idx_api_keys_user_id ON api_keys(user_id);
                CREATE INDEX IF NOT EXISTS idx_org_members_org_id ON org_members(org_id);
                CREATE INDEX IF NOT EXISTS idx_org_invites_org_id ON org_invites(org_id);
                CREATE INDEX IF NOT EXISTS idx_org_invites_email ON org_invites(email);
                """
            )
            conn.commit()
            self._migrate(conn)

    def _migrate(self, conn: sqlite3.Connection) -> None:
        """後から追加した列を、既存のDBファイルに対して安全に追加する。

        SQLiteの CREATE TABLE IF NOT EXISTS は既存テーブルへの列追加はしない
        ため、開発の途中でスキーマが増えても既存の patternforge.db を壊さず
        （作り直さず）に済むよう、無ければ ALTER TABLE で追加する簡易マイグ
        レーション。本格的な運用では Alembic 等のマイグレーションツールに
        置き換えることを推奨するが、この規模ではこれで十分。

        並行性についての注記（第2回監査で指摘・修正）: gunicorn等で複数ワーカー
        プロセスを同時起動すると、各ワーカーが起動時に Store() を作り、この
        _migrate() をほぼ同時に実行しうる。PRAGMA table_info での読み取りと
        ALTER TABLE の実行の間に他プロセスが割り込むと、(a) 二重に同じ列を
        追加しようとして "duplicate column name" エラーになる、(b) 稀に
        テーブル定義の読み取りが不整合になる、といった問題が起こりうる。
        BEGIN IMMEDIATE で書き込みロックを取得してから読み取り→ALTERを行う
        ことで他プロセスとの直列化を保証しつつ、万一 duplicate column の
        エラーが出ても「既に他プロセスが追加済み」として無害に無視する。
        """
        conn.execute("BEGIN IMMEDIATE")
        try:
            existing_columns = {row[1] for row in conn.execute("PRAGMA table_info(users)")}
            migrations = [
                ("email_verified", "ALTER TABLE users ADD COLUMN email_verified INTEGER NOT NULL DEFAULT 0"),
                ("stripe_customer_id", "ALTER TABLE users ADD COLUMN stripe_customer_id TEXT"),
                ("stripe_subscription_id", "ALTER TABLE users ADD COLUMN stripe_subscription_id TEXT"),
                ("session_version", "ALTER TABLE users ADD COLUMN session_version INTEGER NOT NULL DEFAULT 1"),
                ("last_billing_event_at", "ALTER TABLE users ADD COLUMN last_billing_event_at REAL"),
            ]
            for column_name, ddl in migrations:
                if column_name not in existing_columns:
                    self._safe_alter(conn, ddl)

            job_columns = {row[1] for row in conn.execute("PRAGMA table_info(jobs)")}
            job_migrations = [
                ("part_count", "ALTER TABLE jobs ADD COLUMN part_count INTEGER"),
                ("waste_ratio", "ALTER TABLE jobs ADD COLUMN waste_ratio REAL"),
                # round8で追加: 生成履歴からの再生成機能用に、生成時の入力
                # (採寸値・パーツ構成・サイズ展開設定等)をJSON文字列で保存する。
                # イラストモードはアップロード画像自体を保持していないため
                # spec_jsonはNoneのままになる(再生成不可。README/このファイルの
                # get_job_regeneration_specのdocstring参照)。
                ("spec_json", "ALTER TABLE jobs ADD COLUMN spec_json TEXT"),
            ]
            for column_name, ddl in job_migrations:
                if column_name not in job_columns:
                    self._safe_alter(conn, ddl)
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    @staticmethod
    def _safe_alter(conn: sqlite3.Connection, ddl: str) -> None:
        """ALTER TABLE ADD COLUMN を実行するが、他プロセスが既に追加済み
        (duplicate column name)の場合はエラーにせず無視する。"""
        try:
            conn.execute(ddl)
        except sqlite3.OperationalError as exc:
            if "duplicate column name" not in str(exc):
                raise

    # -- users ---------------------------------------------------------

    def create_user(self, email: str, password: str) -> int:
        email = email.strip().lower()
        if not email or len(email) > MAX_EMAIL_LENGTH or not _EMAIL_RE.match(email):
            raise ValueError("メールアドレスの形式が正しくありません。")
        if len(password) < 8:
            raise ValueError("パスワードは8文字以上にしてください。")
        password_hash = generate_password_hash(password)
        with closing(self._connect()) as conn:
            try:
                cur = conn.execute(
                    "INSERT INTO users(email, password_hash, plan, created_at, email_verified) "
                    "VALUES (?, ?, 'free', ?, 0)",
                    (email, password_hash, time.time()),
                )
                conn.commit()
                return cur.lastrowid
            except sqlite3.IntegrityError as exc:
                raise EmailAlreadyRegisteredError(
                    "このメールアドレスは既に登録されています。"
                ) from exc

    _USER_COLUMNS = (
        "id, email, plan, created_at, email_verified, stripe_customer_id, stripe_subscription_id, "
        "session_version, last_billing_event_at"
    )

    @staticmethod
    def _row_to_user(row) -> User:
        (user_id, email, plan, created_at, email_verified, stripe_customer_id, stripe_subscription_id,
         session_version, last_billing_event_at) = row
        return User(
            id=user_id, email=email, plan=plan, created_at=created_at,
            email_verified=bool(email_verified),
            stripe_customer_id=stripe_customer_id,
            stripe_subscription_id=stripe_subscription_id,
            session_version=session_version,
            last_billing_event_at=last_billing_event_at,
        )

    def authenticate(self, email: str, password: str) -> User | None:
        email = email.strip().lower()
        with closing(self._connect()) as conn:
            row = conn.execute(
                f"SELECT {self._USER_COLUMNS}, password_hash FROM users WHERE email=?",
                (email,),
            ).fetchone()
        if row is None:
            # 実際にwerkzeug.security.check_password_hash(意図的に遅い
            # scrypt/pbkdf2ベースの検証)を使って計測したところ、実在する
            # メールアドレス宛の誤ったパスワードでの認証は平均約93ms、
            # 実在しないメールアドレスの場合(以前はここで即returnしていた)
            # は平均約0.2msと、応答時間に約430倍の差があることを確認した。
            # これは/loginの応答時間を計測するだけで、パスワードを知らなくても
            # 「そのメールアドレスが登録済みかどうか」を外部から判定できて
            # しまう、実際に悪用可能なタイミングサイドチャネルだった。
            # 実在しない場合でも同じ検証コストをかけて応答時間の差を埋める
            # (検証結果自体は使わず、CPU時間を合わせることだけが目的)。
            check_password_hash(_dummy_password_hash(), password)
            return None
        *user_fields, password_hash = row
        if not check_password_hash(password_hash, password):
            return None
        return self._row_to_user(user_fields)

    def get_user(self, user_id: int) -> User | None:
        with closing(self._connect()) as conn:
            row = conn.execute(
                f"SELECT {self._USER_COLUMNS} FROM users WHERE id=?", (user_id,)
            ).fetchone()
        return self._row_to_user(row) if row else None

    def get_user_by_email(self, email: str) -> User | None:
        email = email.strip().lower()
        with closing(self._connect()) as conn:
            row = conn.execute(
                f"SELECT {self._USER_COLUMNS} FROM users WHERE email=?", (email,)
            ).fetchone()
        return self._row_to_user(row) if row else None

    def get_user_by_stripe_customer_id(self, stripe_customer_id: str) -> User | None:
        with closing(self._connect()) as conn:
            row = conn.execute(
                f"SELECT {self._USER_COLUMNS} FROM users WHERE stripe_customer_id=?",
                (stripe_customer_id,),
            ).fetchone()
        return self._row_to_user(row) if row else None

    def set_plan(self, user_id: int, plan: str) -> None:
        with closing(self._connect()) as conn:
            conn.execute("UPDATE users SET plan=? WHERE id=?", (plan, user_id))
            conn.commit()

    def set_password(self, user_id: int, new_password: str) -> None:
        """パスワードを変更し、同時に session_version をインクリメントする。

        session_version を上げることで、変更前に発行された全てのセッション
        Cookie（＝古いパスワードでログインしたブラウザ）を無効化する
        （第2回監査 指摘#1: パスワード再設定後も、攻撃者が事前に盗んだ
        セッションCookieが有効なままログイン状態を保てる問題への対応）。
        """
        if len(new_password) < 8:
            raise ValueError("パスワードは8文字以上にしてください。")
        with closing(self._connect()) as conn:
            conn.execute(
                "UPDATE users SET password_hash=?, session_version = session_version + 1 WHERE id=?",
                (generate_password_hash(new_password), user_id),
            )
            conn.commit()

    def mark_email_verified(self, user_id: int) -> None:
        with closing(self._connect()) as conn:
            conn.execute("UPDATE users SET email_verified=1 WHERE id=?", (user_id,))
            conn.commit()

    def set_stripe_ids(self, user_id: int, customer_id: str | None, subscription_id: str | None) -> None:
        with closing(self._connect()) as conn:
            conn.execute(
                "UPDATE users SET stripe_customer_id=?, stripe_subscription_id=? WHERE id=?",
                (customer_id, subscription_id, user_id),
            )
            conn.commit()

    def apply_billing_event(
        self, user_id: int, event_created_at: float, plan: str,
        stripe_customer_id: str | None = None, stripe_subscription_id: str | None = None,
    ) -> bool:
        """Stripe Webhookイベントの内容をplanへ適用する。ただし、既に
        適用済みのイベントより`created`(イベント発生時刻)が古いイベントは
        無視する(=書き込まない)。

        実際に本物のstripeライブラリ・本物のHMAC署名でイベントを構築し、
        「支払い失敗(past_due, 生成時刻t1) → リトライで復旧(active, 生成
        時刻t2>t1)」という現実の時系列を再現した上で、**Stripe公式ドキュ
        メントが明記している「Webhookイベントの配信順序は保証されない」**
        という仕様通りに、新しいイベント(active, t2)を先に、古いイベント
        (past_due, t1、何らかの理由で再送/遅延して後から届いた)を後に
        サーバへ届けたところ、以前の実装(`app.py`が`created`を一切見ずに
        受信した順にそのまま`db.set_plan()`を呼ぶだけ)では、実際には
        直近の状態が"active"(pro)であるにもかかわらず、後から届いた古い
        "past_due"イベントによってplanが"free"へ巻き戻され、そのまま
        固定されてしまう実バグを確認した。Stripeの再送(リトライ)やネット
        ワークの遅延は実運用で普通に起こりうるため、これは理論上の懸念
        ではなく実際に発生しうる不具合である。

        `users.last_billing_event_at`に最後に適用したイベントの`created`を
        記録し、次に来たイベントの`created`がそれより古い場合は
        「既に更新済みの状態より古い情報」として無視することで、配信順序に
        依存せず常に最新の(生成時刻が最も新しい)イベントの内容へ収束する
        ようにした。stripe_customer_id/stripe_subscription_idは
        `checkout.session.completed`でのみ渡され、Noneの場合は既存値を
        変更しない。

        戻り値: 実際に適用された(=最新のイベントとして書き込まれた)か、
        古いイベントとして無視されたか。
        """
        with closing(self._connect()) as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                row = conn.execute(
                    "SELECT last_billing_event_at FROM users WHERE id=?", (user_id,)
                ).fetchone()
                if row is None:
                    conn.commit()  # トランザクション/ロックを閉じるだけで、書き込みは無し
                    return False
                last_at = row[0]
                if last_at is not None and event_created_at < last_at:
                    conn.commit()  # 同上(古いイベントなので何も書き込まない)
                    return False
                conn.execute(
                    "UPDATE users SET plan=?, last_billing_event_at=?, "
                    "stripe_customer_id=COALESCE(?, stripe_customer_id), "
                    "stripe_subscription_id=COALESCE(?, stripe_subscription_id) "
                    "WHERE id=?",
                    (plan, event_created_at, stripe_customer_id, stripe_subscription_id, user_id),
                )
                conn.commit()
                return True
            except Exception:
                conn.rollback()
                raise

    # -- email / password-reset tokens ------------------------------------

    def create_email_token(self, user_id: int, purpose: str, ttl_seconds: int) -> str:
        """purposeは 'verify'（メール確認）または 'reset'（パスワード再設定）。"""
        token = secrets.token_urlsafe(32)
        now = time.time()
        with closing(self._connect()) as conn:
            conn.execute(
                "INSERT INTO email_tokens(token, user_id, purpose, created_at, expires_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (token, user_id, purpose, now, now + ttl_seconds),
            )
            conn.commit()
        return token

    def seconds_since_last_token(self, user_id: int, purpose: str) -> float | None:
        """指定ユーザー・目的の最後のトークン発行からの経過秒数。

        まだ一度も発行していなければ None。IPベースのレート制限だけでは
        IPローテーションを使った分散的なメール爆撃（同一被害者のメール
        アドレスに大量の確認/再設定メールを送りつける嫌がらせ）を防げない
        ため、DB側でもユーザー単位のクールダウンを設けられるようにする
        （第2回監査 指摘#3）。

        正直な限界: この関数単体は読み取りのみで、クールダウン判定と
        トークン発行を分けて呼ぶと以下の`try_create_email_token_with_cooldown`
        で修正したのと同種のレース条件になる。呼び出し側で「まだクール
        ダウン中か」だけを表示目的で確認する場合を除き、実際にトークンを
        発行する経路は必ず`try_create_email_token_with_cooldown`を使うこと。
        """
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT created_at FROM email_tokens WHERE user_id=? AND purpose=? "
                "ORDER BY created_at DESC LIMIT 1",
                (user_id, purpose),
            ).fetchone()
        if row is None:
            return None
        return time.time() - row[0]

    def try_create_email_token_with_cooldown(
        self, user_id: int, purpose: str, cooldown_seconds: float, ttl_seconds: int,
    ) -> str | None:
        """クールダウン確認とトークン発行を1つのトランザクションで行う。

        実際に本物のスレッド(GILがSQLite I/O中に解放される、真の並行実行)で
        同一ユーザーに対して20並行で`/forgot-password`相当の処理を実行した
        ところ、以前は`seconds_since_last_token()`(単純なSELECT)で経過秒数を
        確認し、クールダウンを超えていれば別途`create_email_token()`
        (単純なINSERT)を呼ぶという2段構えだったため、ほぼ同時に来た
        リクエストの多くが「まだ誰も新しいトークンを発行していない」時点の
        古いSELECT結果を見てしまい、20回中18回もクールダウンをすり抜けて
        トークンを発行(=メールを送信)してしまうことを確認した
        (`check_and_increment_usage`・`create_measurement_profile`で
        以前見つけた既知のレースと同種のバグ)。第2回監査 指摘#3で要求された
        「同一被害者へのメール爆撃を防ぐDB側のユーザー単位クールダウン」が、
        並行リクエストの下では実質的に機能していなかったことになる。

        `BEGIN IMMEDIATE`で書き込みロックを先に取得してからクールダウン確認
        →トークン発行を行うことで、同じユーザー・同じpurposeへの並行
        リクエストはSQLiteが直列化し、最初の1件だけがトークンを発行する
        (残りは`None`を受け取り、何も送信しない)。クールダウン中は`None`を
        返す。
        """
        now = time.time()
        with closing(self._connect()) as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                row = conn.execute(
                    "SELECT created_at FROM email_tokens WHERE user_id=? AND purpose=? "
                    "ORDER BY created_at DESC LIMIT 1",
                    (user_id, purpose),
                ).fetchone()
                if row is not None and now - row[0] < cooldown_seconds:
                    conn.commit()  # トランザクション/ロックを閉じるだけで、書き込みは無し
                    return None
                token = secrets.token_urlsafe(32)
                conn.execute(
                    "INSERT INTO email_tokens(token, user_id, purpose, created_at, expires_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (token, user_id, purpose, now, now + ttl_seconds),
                )
                conn.commit()
                return token
            except Exception:
                conn.rollback()
                raise

    def consume_email_token(self, token: str, purpose: str) -> int | None:
        """トークンを検証し、有効なら使用済みにしてuser_idを返す。

        有効期限切れ・使用済み・目的(purpose)不一致・存在しないトークンは
        すべて None を返す(呼び出し側にどれが原因かを教えない。パスワード
        再設定トークンの場合、理由を細かく返すと総当たり攻撃の助けになる)。
        """
        now = time.time()
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT user_id, purpose, expires_at, used_at FROM email_tokens WHERE token=?",
                (token,),
            ).fetchone()
            if row is None:
                return None
            user_id, token_purpose, expires_at, used_at = row
            if token_purpose != purpose or used_at is not None or expires_at < now:
                return None
            conn.execute("UPDATE email_tokens SET used_at=? WHERE token=?", (now, token))
            conn.commit()
            return user_id

    def peek_verify_token_user_id(self, token: str) -> int | None:
        """"verify"用トークンが指しているuser_idを、消費状態(used_at)や
        有効期限に関わらず返す(存在しない、またはpurposeが違う場合はNone)。

        実際に見つかった不具合の修正で使う: 企業のメールセキュリティ
        ゲートウェイ(Microsoft Defender for Office 365のSafe Links等)が、
        利用者が実際にクリックする前にメール内のリンクを自動的に
        「事前アクセス」してマルウェア検査を行うことが広く知られている。
        `/verify/<token>`はGETリクエストだけでトークンを消費する設計の
        ため、この自動prefetch自体が先にトークンを使用済みにしてしまい、
        利用者本人が後から同じリンクを開くと`consume_email_token()`が
        「使用済み」としてNoneを返し、実際には確認が完了しているにも
        関わらず「リンクが無効、または期限切れ」という誤った失敗表示に
        なることを、実際に(1.別クライアントで先にGET 2.本人が同じリンクを
        開く)という手順で再現して確認した。呼び出し側(`verify_email`)は、
        `consume_email_token`がNoneを返した場合にこのメソッドで
        user_idを求め、そのユーザーが既に`email_verified`済みであれば
        (=既に確認は完了している)、エラーではなく成功として案内する
        フォールバックに使う。used_at/expires_atを見ないのは、
        「既に確認済みかどうか」というその後の状態だけを見て成功/失敗を
        判断すれば十分で、トークン自体の状態を見る必要が無いため
        (このメソッド自体は何もmarkしない読み取り専用の問い合わせであり、
        新たに確認状態を進める副作用は一切無い)。
        """
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT user_id FROM email_tokens WHERE token=? AND purpose='verify'", (token,),
            ).fetchone()
        return row[0] if row else None

    def reset_password_with_token(self, token: str, new_password: str) -> int | None:
        """パスワード再設定トークンの検証・消費と、実際のパスワード変更を
        1つのDBトランザクションで行う。

        実際に動かして見つかった不具合（修正済み）: 以前は
        `consume_email_token(token, "reset")` でトークンを先に使用済みに
        してから `set_password()` を呼んでいた。利用者が再設定フォームに
        8文字未満の短いパスワードを入力すると `set_password()` が
        `ValueError` を投げてフォームにエラーを表示する一方、その時点で
        トークンは既に使用済みになっている。利用者が同じ画面で今度は正しい
        （8文字以上の）パスワードを入力し直しても、リンクはもう使えず
        「リンクが無効、または有効期限が切れています」という、あたかも
        リンクの期限切れが原因であるかのような誤解を招くエラーになり、
        最初から（パスワード再設定メールの再送から）やり直すしかなくなる。
        実際にサーバーを起動し、この手順（短いパスワード→有効なパスワード
        を同じリンクで再送信）を実行して再現・確認した上で、トークンの
        検証・消費とパスワード変更を同一トランザクション内で行うように
        修正した。パスワードが短すぎる場合はROLLBACKされ、トークンは
        「未使用」のまま温存されるため、利用者は同じリンクで再試行できる。

        戻り値: 成功時はuser_id。トークンが無効/期限切れ/使用済み/目的
        不一致の場合はNone（consume_email_token同様、理由は区別して返さない）。
        パスワードが短すぎる場合は ValueError を投げる(トークンは消費されない)。
        """
        if len(new_password) < 8:
            # トークンへ触れる前に検証する。これにより、検証に失敗した
            # リクエストではDBへの書き込み(トークンの消費)が一切発生しない。
            raise ValueError("パスワードは8文字以上にしてください。")
        now = time.time()
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT user_id, purpose, expires_at, used_at FROM email_tokens WHERE token=?",
                (token,),
            ).fetchone()
            if row is None:
                return None
            user_id, token_purpose, expires_at, used_at = row
            if token_purpose != "reset" or used_at is not None or expires_at < now:
                return None
            conn.execute(
                "UPDATE users SET password_hash=?, session_version = session_version + 1 WHERE id=?",
                (generate_password_hash(new_password), user_id),
            )
            conn.execute("UPDATE email_tokens SET used_at=? WHERE token=?", (now, token))
            conn.commit()
            return user_id

    # -- jobs ------------------------------------------------------------

    def record_job(self, job_id: str, owner_key: str, part_count: int | None = None,
                    waste_ratio: float | None = None, spec_json: str | None = None) -> None:
        with closing(self._connect()) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO jobs(job_id, owner_key, created_at, part_count, waste_ratio, spec_json) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (job_id, owner_key, time.time(), part_count, waste_ratio, spec_json),
            )
            conn.commit()

    def get_job_owner(self, job_id: str) -> str | None:
        with closing(self._connect()) as conn:
            row = conn.execute("SELECT owner_key FROM jobs WHERE job_id=?", (job_id,)).fetchone()
        return row[0] if row else None

    def list_jobs_for_owner(self, owner_key: str, limit: int = 20) -> list[dict]:
        """マイページの生成履歴表示用。新しい順。

        `can_regenerate`は`spec_json`が保存されているか(=手動/サイズ展開
        モードで生成され、再生成に必要な入力を保持しているか)を示す真偽値。
        テンプレート側で「この設定で再生成」ボタンの表示可否に使う。
        """
        with closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT job_id, created_at, part_count, waste_ratio, spec_json FROM jobs "
                "WHERE owner_key=? ORDER BY created_at DESC LIMIT ?",
                (owner_key, limit),
            ).fetchall()
        return [
            {
                "job_id": job_id, "created_at": created_at, "part_count": part_count,
                "waste_ratio": waste_ratio, "can_regenerate": spec_json is not None,
            }
            for job_id, created_at, part_count, waste_ratio, spec_json in rows
        ]

    def get_job_regeneration_spec(self, job_id: str, owner_key: str) -> dict | None:
        """再生成に必要な入力(spec_json)を、所有者一致を確認した上で返す。

        イラストモードで生成したジョブ、または(旧バージョンで生成された等の
        理由で)spec_jsonが保存されていないジョブはNoneを返す(再生成不可。
        呼び出し側でその旨を案内する)。所有者が一致しない場合もNone
        (他人の生成履歴を再生成できないようにするため。他のジョブ関連
        メソッド同様、存在しない場合と所有者不一致の場合を区別しない)。
        """
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT owner_key, spec_json FROM jobs WHERE job_id=?", (job_id,)
            ).fetchone()
        if row is None:
            return None
        job_owner_key, spec_json = row
        if job_owner_key != owner_key or spec_json is None:
            return None
        try:
            return json.loads(spec_json)
        except (ValueError, TypeError):
            return None

    def reassign_jobs(self, old_owner_key: str, new_owner_key: str) -> int:
        """匿名セッションで生成したジョブを、ログイン/登録直後の本人に引き継ぐ。

        未ログインで型紙を作った直後にアカウント登録した場合、その型紙への
        アクセス権を失ってしまう(ジョブ所有者キーが anon:<visitor_id> のまま)
        のを防ぐための移行処理。
        """
        with closing(self._connect()) as conn:
            cur = conn.execute(
                "UPDATE jobs SET owner_key=? WHERE owner_key=?", (new_owner_key, old_owner_key)
            )
            conn.commit()
            return cur.rowcount

    def delete_jobs_older_than(self, cutoff_epoch: float) -> int:
        """generated/ のファイル掃除(_cleanup_old_outputs)と対になる、jobsテーブル側の掃除。"""
        with closing(self._connect()) as conn:
            cur = conn.execute("DELETE FROM jobs WHERE created_at < ?", (cutoff_epoch,))
            conn.commit()
            return cur.rowcount

    # -- 採寸プロフィール ---------------------------------------------------
    #
    # パタンナー・仕立て業を営む利用者は、1人の顧客だけでなく複数の顧客・
    # 家族分の採寸値を繰り返し使うことが多い。毎回6項目を入力し直す手間を
    # 省き、名前付きで保存・呼び出しできるようにする（ログイン済みユーザー
    # 向け機能。有用性の観点でも、複数顧客管理という実務ニーズに直結する）。

    def create_measurement_profile(
        self, user_id: int, name: str, bust: float, waist: float, hip: float,
        height: float, sleeve_length: float, shoulder_width: float,
    ) -> int:
        name = name.strip()
        if not name:
            raise ValueError("プロフィール名を入力してください。")
        if len(name) > 50:
            raise ValueError("プロフィール名は50文字以内にしてください。")
        # 実際に20並行スレッドから同じユーザーで保存を試すテストで見つかった
        # 実バグの修正: 以前は素朴なSELECT COUNT(*)→(上限未満なら)INSERTだった
        # ため、複数リクエストがほぼ同時に来ると、どちらもCOUNTの時点では
        # まだ上限未満に見えてしまい、両方がINSERTを通過して上限
        # (MAX_MEASUREMENT_PROFILES_PER_USER)を超えるプロフィールが保存され
        # うる不具合があった(利用回数カウンタ check_and_increment_usage で
        # 以前修正した既知のレースと同種のバグ)。`BEGIN IMMEDIATE`で書き込み
        # ロックを先に取得してから件数確認→INSERTを行うことで、同じユーザーの
        # 並行リクエストはSQLiteが直列化する(2つ目以降は最初の1つが
        # コミットするまで待たされる)ため、上限をすり抜けられない。
        with closing(self._connect()) as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                existing = conn.execute(
                    "SELECT COUNT(*) FROM measurement_profiles WHERE user_id=?", (user_id,)
                ).fetchone()[0]
                if existing >= MAX_MEASUREMENT_PROFILES_PER_USER:
                    conn.commit()  # トランザクション/ロックを閉じるだけで、書き込みは無し
                    raise ValueError(
                        f"保存できるプロフィールは{MAX_MEASUREMENT_PROFILES_PER_USER}件までです。"
                        "不要なプロフィールを削除してから保存してください。"
                    )
                cur = conn.execute(
                    "INSERT INTO measurement_profiles"
                    "(user_id, name, bust, waist, hip, height, sleeve_length, shoulder_width, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (user_id, name, bust, waist, hip, height, sleeve_length, shoulder_width, time.time()),
                )
                conn.commit()
                return cur.lastrowid
            except Exception:
                conn.rollback()
                raise

    _PROFILE_COLUMNS = "id, name, bust, waist, hip, height, sleeve_length, shoulder_width, created_at"

    @staticmethod
    def _row_to_profile(row) -> dict:
        profile_id, name, bust, waist, hip, height, sleeve_length, shoulder_width, created_at = row
        return {
            "id": profile_id, "name": name, "bust": bust, "waist": waist, "hip": hip,
            "height": height, "sleeve_length": sleeve_length, "shoulder_width": shoulder_width,
            "created_at": created_at,
        }

    def list_measurement_profiles(self, user_id: int) -> list[dict]:
        """マイページ・生成フォームでの選択用。新しい順。"""
        with closing(self._connect()) as conn:
            rows = conn.execute(
                f"SELECT {self._PROFILE_COLUMNS} FROM measurement_profiles "
                "WHERE user_id=? ORDER BY created_at DESC",
                (user_id,),
            ).fetchall()
        return [self._row_to_profile(row) for row in rows]

    def get_measurement_profile(self, profile_id: int, user_id: int) -> dict | None:
        """他人のプロフィールを読めないよう、user_idも合わせて絞り込む。"""
        with closing(self._connect()) as conn:
            row = conn.execute(
                f"SELECT {self._PROFILE_COLUMNS} FROM measurement_profiles WHERE id=? AND user_id=?",
                (profile_id, user_id),
            ).fetchone()
        return self._row_to_profile(row) if row else None

    def delete_measurement_profile(self, profile_id: int, user_id: int) -> bool:
        """他人のプロフィールを削除できないよう、user_idも合わせて絞り込む。"""
        with closing(self._connect()) as conn:
            cur = conn.execute(
                "DELETE FROM measurement_profiles WHERE id=? AND user_id=?", (profile_id, user_id)
            )
            conn.commit()
            return cur.rowcount > 0

    # -- usage / plan limits ---------------------------------------------

    def check_and_increment_usage(self, owner_key: str, limit: int | None, day: str) -> tuple[bool, int]:
        """本日の利用回数を確認し、上限内であればカウントを1増やす。

        Returns:
            (allowed, used_count_after_this_call_if_allowed_else_current_count)

        `BEGIN IMMEDIATE` で書き込みロックを即座に取得してから読み取り→判定→
        書き込みを行うため、同じowner_keyから並行してリクエストが来ても、
        SQLiteが2つ目以降のトランザクションを最初の1つが完了するまで待たせる
        （＝read-then-writeの間に割り込まれない）。以前は素朴なSELECT→
        INSERT/UPDATEで、極めて近いタイミングの並行リクエストだと上限を
        1〜2回分超えうる既知のレースがあったが、これで解消している。
        """
        with closing(self._connect()) as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                row = conn.execute(
                    "SELECT count FROM usage_counters WHERE owner_key=? AND day=?",
                    (owner_key, day),
                ).fetchone()
                current = row[0] if row else 0
                if limit is not None and current >= limit:
                    conn.commit()  # トランザクション/ロックを閉じるだけで、書き込みは無し
                    return False, current
                conn.execute(
                    "INSERT INTO usage_counters(owner_key, day, count) VALUES (?, ?, 1) "
                    "ON CONFLICT(owner_key, day) DO UPDATE SET count = count + 1",
                    (owner_key, day),
                )
                conn.commit()
                return True, current + 1
            except Exception:
                conn.rollback()
                raise

    def refund_usage(self, owner_key: str, day: str) -> None:
        """`check_and_increment_usage()`で加算した1回分を取り消す（下限0）。

        実際に見つかった不具合の修正で使う: `/api/generate`は「単純な入力
        ミスで400になったリクエストまで課金対象にすると利用者体験が悪い」
        という理由で、採寸値・パーツ構成・画像の妥当性チェックを通過した
        後にのみ利用回数を加算する設計だった。ただし加算のタイミングが
        実際の生成処理(イラストモードのAI判定・ネスティング等)より前に
        あるため、実際にAI判定が失敗する画像(領域を検出できない・パーツ種を
        判定できない等、実際のClaude API呼び出しやセグメンテーションの
        結果次第で起こりうる)や、生成処理中の想定外の例外で失敗した場合も、
        利用者は型紙を1件も受け取れないまま本日の利用回数を1回消費させられて
        いた。これは「単純な入力ミス」と同じ理由(=利用者に何の成果物も
        渡せていないリクエストを課金対象にするべきではない)で修正が必要な
        実害のある不具合であり、実際に(1.領域を検出できない画像で生成失敗
        2.usage_today()を確認)という手順で再現して確認した。

        `check_and_increment_usage()`と同様`BEGIN IMMEDIATE`で直列化し、
        並行リクエストによる二重減算・負値化を防ぐ。該当行が無い場合は
        何もしない(既に0、または該当日に一度も加算されていない)。
        """
        with closing(self._connect()) as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                conn.execute(
                    "UPDATE usage_counters SET count = MAX(count - 1, 0) "
                    "WHERE owner_key=? AND day=?",
                    (owner_key, day),
                )
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    def usage_today(self, owner_key: str, day: str) -> int:
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT count FROM usage_counters WHERE owner_key=? AND day=?",
                (owner_key, day),
            ).fetchone()
        return row[0] if row else 0

    def check_rate_limit(self, bucket: str, key: str, max_requests: int, window_seconds: float) -> bool:
        """スライディングウィンドウ方式のレート制限を、複数プロセス間で共有する。

        round6で追加(既知の制約の解消): それまでapp.pyの`_RateLimiter`は
        プロセス内メモリ(dequeベースのスライディングウィンドウ)だけで
        カウントしており、`gunicorn -w N`のような複数ワーカー構成では
        各ワーカーが別々にカウントするため、実際の上限が実質N倍緩む
        （例えばworker数2なら「60秒に20回」の制限が実質40回まで通って
        しまう）という既知の制約があった。プランごとの1日あたり利用回数
        上限(`check_and_increment_usage`)は既にSQLiteで共有されているのに、
        より短い時間窓のレート制限だけこの問題を抱えたままだったのは一貫性を
        欠くと判断し、同じ`BEGIN IMMEDIATE`直列化パターンをここでも使う
        ことで解消した。

        `bucket`はエンドポイント種別(例: "generate"・"download"・
        "email_send"・"login")を区別するための名前空間で、`key`は
        `_client_key()`が返すIP等の識別子。同じ(bucket, key)の組に対して
        ウィンドウ内のヒット数を数え、上限未満なら新しいヒットを1件記録
        して許可する。

        呼び出しのたびに対象(bucket, key)のウィンドウ外の古い行を掃除する
        ため、アクティブなキーについては行数が際限なく増えることはない。
        ただし一度だけアクセスして以降静止したキー(例: 二度と来ない攻撃元
        IP)の行は、そのキー自身への次のアクセスが無い限りここでは掃除
        されないため、別途`delete_rate_limit_hits_older_than()`を
        バックグラウンドの定期掃除(app.pyの`_cleanup_old_outputs`)から
        呼び、テーブル全体の古い行を掃除している。
        """
        now = time.time()
        cutoff = now - window_seconds
        with closing(self._connect()) as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                conn.execute(
                    "DELETE FROM rate_limit_hits WHERE bucket=? AND rl_key=? AND ts<?",
                    (bucket, key, cutoff),
                )
                row = conn.execute(
                    "SELECT COUNT(*) FROM rate_limit_hits WHERE bucket=? AND rl_key=?",
                    (bucket, key),
                ).fetchone()
                current = row[0] if row else 0
                if current >= max_requests:
                    conn.commit()  # ロックを閉じるだけで、新しいヒットは記録しない
                    return False
                conn.execute(
                    "INSERT INTO rate_limit_hits(bucket, rl_key, ts) VALUES (?, ?, ?)",
                    (bucket, key, now),
                )
                conn.commit()
                return True
            except Exception:
                conn.rollback()
                raise

    def delete_rate_limit_hits_older_than(self, cutoff: float) -> None:
        """`rate_limit_hits`の古い行をまとめて削除する(定期バックグラウンド掃除用)。

        `check_rate_limit()`自体もアクセスの都度その場でウィンドウ外の
        行を削除するが、それは実際にアクセスがあった(bucket, key)に限られる。
        二度とアクセスが来ないキー(例: 単発の攻撃元IP)の行が残り続けるのを
        防ぐため、全レート制限バケットの中で最も長いウィンドウ幅より
        十分大きいcutoffを渡して定期的に呼ぶことを想定している。
        """
        with closing(self._connect()) as conn:
            conn.execute("DELETE FROM rate_limit_hits WHERE ts < ?", (cutoff,))
            conn.commit()

    # -- アカウント単位のログイン総当たり対策(round7で追加) --------------

    def record_login_failure(self, email: str) -> None:
        """ログイン失敗を、メールアドレス単位で記録する。

        実在しないメールアドレスに対しても同じように記録する(authenticate()
        が実在有無に関わらず同じ応答時間になるようにしているのと同じ理由で、
        ロックアウトの有無からアカウントの実在を推測できないようにするため)。
        """
        key = email.strip().lower()
        with closing(self._connect()) as conn:
            conn.execute(
                "INSERT INTO login_failures(email_key, ts) VALUES (?, ?)",
                (key, time.time()),
            )
            conn.commit()

    def clear_login_failures(self, email: str) -> None:
        """ログイン成功時に、そのメールアドレスの失敗記録を消す。"""
        key = email.strip().lower()
        with closing(self._connect()) as conn:
            conn.execute("DELETE FROM login_failures WHERE email_key = ?", (key,))
            conn.commit()

    def check_account_lockout(self, email: str, now: float | None = None) -> float:
        """指定メールアドレスが現在ロックアウト中かどうかを、残り秒数で返す。

        ロックアウト中でなければ0.0を返す。IPベースの`check_rate_limit`
        (`_login_rate_limiter`、round6で追加)と役割を分けている: IPベースは
        「同じ接続元からの高頻度な試行」を抑止するのに対し、これは「同じ
        アカウントを狙った試行」を、試行元のIPが分散していても抑止する
        (多数のIP/ボットネットを使い分けて1つのメールアドレスのパスワードを
        総当たりする攻撃は、IPベースの制限だけでは防げないため)。

        判定方法: `ACCOUNT_LOCKOUT_WINDOW_SECONDS`より古い失敗記録をまず
        掃除し(`check_rate_limit`と同様、アクセスの都度その場で掃除する)、
        残った失敗回数が`ACCOUNT_LOCKOUT_THRESHOLD`未満ならロックしない。
        以上ならば、最後の失敗時刻を基準に指数バックオフ
        (`ACCOUNT_LOCKOUT_BASE_SECONDS`から倍々に増え、
        `ACCOUNT_LOCKOUT_MAX_SECONDS`で頭打ち)でロック秒数を決め、その
        残り時間を返す。

        呼び出し側(app.py)は、ロック中はパスワード照合(`authenticate()`)
        自体を行わずにこの結果だけで拒否する設計を想定している。これにより
        (1)ロック中の無駄なbcrypt/scrypt計算コストを避けられる、
        (2)ロック中に本当のパスワードを送っても弾かれるだけになり、正解の
        パスワードを知っている攻撃者が「たまたま通った試行」で検知を逃れる
        余地がなくなる、という2つの利点がある。
        """
        if now is None:
            now = time.time()
        key = email.strip().lower()
        cutoff = now - ACCOUNT_LOCKOUT_WINDOW_SECONDS
        with closing(self._connect()) as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                conn.execute(
                    "DELETE FROM login_failures WHERE email_key = ? AND ts < ?",
                    (key, cutoff),
                )
                rows = conn.execute(
                    "SELECT ts FROM login_failures WHERE email_key = ? ORDER BY ts",
                    (key,),
                ).fetchall()
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        count = len(rows)
        if count < ACCOUNT_LOCKOUT_THRESHOLD:
            return 0.0
        last_failure_ts = rows[-1][0]
        lockout_seconds = min(
            ACCOUNT_LOCKOUT_MAX_SECONDS,
            ACCOUNT_LOCKOUT_BASE_SECONDS * (2 ** (count - ACCOUNT_LOCKOUT_THRESHOLD)),
        )
        remaining = (last_failure_ts + lockout_seconds) - now
        return max(0.0, remaining)

    def delete_login_failures_older_than(self, cutoff: float) -> None:
        """`login_failures`の古い行をまとめて削除する(定期バックグラウンド掃除用)。

        `delete_rate_limit_hits_older_than()`と同じ理由(二度とログインを
        試みない=もう`check_account_lockout()`が呼ばれないメールアドレスの
        行は、そのままでは掃除されない)で、定期掃除から呼ぶ。
        """
        with closing(self._connect()) as conn:
            conn.execute("DELETE FROM login_failures WHERE ts < ?", (cutoff,))
            conn.commit()

    # -- APIキー(round8で追加: B2B向けプログラマティックAPI) ----------------
    #
    # アパレルブランド等の法人顧客がPatternForgeを自社システムに組み込んで
    # 呼び出せるようにするための、ブラウザセッションに依存しない認証手段。
    # パスワードと同様「秘密」を扱うため、生の鍵はDBに保存せず
    # SHA-256ハッシュのみを保存する(パスワードにwerkzeug.security.
    # generate_password_hashを使わないのは、あちらは意図的に低速な
    # scrypt/pbkdf2で「オフライン総当たり耐性」を狙ったものだが、APIキーは
    # パスワードよりずっと高いエントロピー(secrets.token_urlsafe(24)の
    # 実質192ビット)を持つランダム値であり、生の鍵の値自体を知らない限り
    # 一致するハッシュを探索することは実質不可能なため、低速化は不要かつ
    # 高頻度なAPI呼び出しのたびに毎回scryptを計算するコストの方が実害になる)。
    #
    # 生の鍵は発行の瞬間にしか呼び出し元へ返さない(その後は`key_prefix`
    # (先頭16文字)のみを一覧表示に使う。パスワード再設定同様、生の鍵を
    # 後から画面に表示する手段は用意しない)。

    #: 1ユーザーが同時に保持できる有効なAPIキーの上限(無制限な発行による
    #: 誤用・管理不能な乱立を防ぐ安全弁)。
    MAX_API_KEYS_PER_USER = 10
    #: APIキーの接頭辞。誤って他のサービスの鍵と混同されないようにする。
    API_KEY_PREFIX = "pf_live_"

    def create_api_key(self, user_id: int, name: str) -> tuple[int, str]:
        """新しいAPIキーを発行する。戻り値は(key_id, 生の鍵)。

        生の鍵はこの呼び出しの戻り値でしか取得できない(DBにはハッシュしか
        残らないため、後から`list_api_keys`等で再取得することはできない)。
        """
        name = name.strip() or "無題のキー"
        if len(name) > 50:
            raise ValueError("キー名は50文字以内にしてください。")
        with closing(self._connect()) as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                existing = conn.execute(
                    "SELECT COUNT(*) FROM api_keys WHERE user_id=? AND revoked_at IS NULL",
                    (user_id,),
                ).fetchone()[0]
                if existing >= self.MAX_API_KEYS_PER_USER:
                    conn.commit()  # トランザクション/ロックを閉じるだけで、書き込みは無し
                    raise ValueError(
                        f"発行できる有効なAPIキーは{self.MAX_API_KEYS_PER_USER}件までです。"
                        "不要なキーを失効させてから発行してください。"
                    )
                raw_key = self.API_KEY_PREFIX + secrets.token_urlsafe(24)
                key_hash = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
                key_prefix = raw_key[:16]
                cur = conn.execute(
                    "INSERT INTO api_keys(user_id, key_hash, key_prefix, name, created_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (user_id, key_hash, key_prefix, name, time.time()),
                )
                conn.commit()
                return cur.lastrowid, raw_key
            except Exception:
                conn.rollback()
                raise

    def authenticate_api_key(self, raw_key: str) -> User | None:
        """`Authorization: Bearer <key>`で渡された鍵を検証し、持ち主を返す。

        失効済み・存在しない鍵はNone。副作用として`last_used_at`を更新する
        (利用者が「このキーは実際に使われているか」をマイページで確認できる
        ようにするため)。
        """
        if not raw_key or not raw_key.startswith(self.API_KEY_PREFIX):
            return None
        key_hash = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT id, user_id, revoked_at FROM api_keys WHERE key_hash=?", (key_hash,)
            ).fetchone()
            if row is None:
                return None
            key_id, user_id, revoked_at = row
            if revoked_at is not None:
                return None
            conn.execute("UPDATE api_keys SET last_used_at=? WHERE id=?", (time.time(), key_id))
            conn.commit()
        return self.get_user(user_id)

    def list_api_keys(self, user_id: int) -> list[dict]:
        """マイページでのAPIキー一覧表示用。ハッシュは含めない(表示不要かつ、
        誤って画面やログに漏らすリスクを避けるため取得自体しない)。"""
        with closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT id, key_prefix, name, created_at, last_used_at, revoked_at FROM api_keys "
                "WHERE user_id=? ORDER BY created_at DESC",
                (user_id,),
            ).fetchall()
        return [
            {
                "id": key_id, "key_prefix": key_prefix, "name": name, "created_at": created_at,
                "last_used_at": last_used_at, "revoked_at": revoked_at,
            }
            for key_id, key_prefix, name, created_at, last_used_at, revoked_at in rows
        ]

    def revoke_api_key(self, key_id: int, user_id: int) -> bool:
        """他人のAPIキーを失効させられないよう、user_idも合わせて絞り込む。"""
        with closing(self._connect()) as conn:
            cur = conn.execute(
                "UPDATE api_keys SET revoked_at=? WHERE id=? AND user_id=? AND revoked_at IS NULL",
                (time.time(), key_id, user_id),
            )
            conn.commit()
            return cur.rowcount > 0

    # -- 組織アカウント(round8で追加: 最小構成のチーム機能) ------------------
    #
    # 正直な注記(スコープの限界): これは「アパレルブランドのチームでプランと
    # 利用回数上限を共有したい」という最小限のニーズに応える、意図的に
    # 単純化した実装であり、Slack/Notion等が持つような本格的なマルチ
    # テナント機能(1アカウントが複数組織に所属する、組織ごとに請求先を
    # 分ける、権限のきめ細かい管理等)ではない。具体的な制約:
    #   - 1ユーザーは同時に1つの組織にしか所属できない(org_membersの
    #     UNIQUE(user_id)制約で強制)。個人アカウントと組織を併用したい
    #     利用者は、別のメールアドレスで別アカウントを作る必要がある。
    #   - 組織のプランは(個人プラン同様)Stripe未設定時のモック切り替えのみ
    #     対応している。実際のStripe連携での組織単位請求は未実装
    #     (今後の課題)。
    #   - オーナーの権限移譲機能は無い。オーナーが退会したい場合、他に
    #     メンバーがいなければそのまま退会できるが、メンバーがいる間は
    #     先に組織を解散する(disband_organization)必要がある
    #     (delete_user_accountのdocstring参照)。
    #
    # 組織に所属するユーザーは、生成の利用回数上限とプランを組織単位で
    # 共有する(app.py の`_current_owner_key`/`_current_plan_name`参照)。
    # 生成物の所有権キーも`org:<org_id>`になるため、同じ組織のメンバーは
    # 互いの生成履歴・ダウンロードにアクセスできる(顧客の型紙を複数人の
    # チームで共同編集・確認するという実務ニーズに対応するための意図的な
    # 設計であり、バグではない。README/該当テストに明記する)。

    #: 招待リンクの有効期限。パスワード再設定等より長め(社内メールの
    #: 確認・承認に日数がかかる法人利用を想定)。
    ORG_INVITE_TOKEN_TTL_SECONDS = 7 * 24 * 3600

    def create_organization(self, owner_user_id: int, name: str) -> int:
        name = name.strip()
        if not name:
            raise ValueError("組織名を入力してください。")
        if len(name) > 100:
            raise ValueError("組織名は100文字以内にしてください。")
        with closing(self._connect()) as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                existing = conn.execute(
                    "SELECT org_id FROM org_members WHERE user_id=?", (owner_user_id,)
                ).fetchone()
                if existing is not None:
                    conn.commit()
                    raise ValueError(
                        "既にいずれかの組織に所属しているため、新しい組織を作成できません"
                        "（1アカウントにつき所属できる組織は1つまでです）。"
                    )
                now = time.time()
                cur = conn.execute(
                    "INSERT INTO organizations(name, owner_user_id, plan, created_at) "
                    "VALUES (?, ?, 'free', ?)",
                    (name, owner_user_id, now),
                )
                org_id = cur.lastrowid
                conn.execute(
                    "INSERT INTO org_members(org_id, user_id, role, joined_at) VALUES (?, ?, 'owner', ?)",
                    (org_id, owner_user_id, now),
                )
                conn.commit()
                return org_id
            except Exception:
                conn.rollback()
                raise

    def get_org_for_user(self, user_id: int) -> dict | None:
        """ログイン中ユーザーが所属する組織(無ければNone)。マイページ・
        利用回数/プラン判定の両方から使う。"""
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT o.id, o.name, o.owner_user_id, o.plan, o.created_at, m.role "
                "FROM org_members m JOIN organizations o ON o.id = m.org_id WHERE m.user_id=?",
                (user_id,),
            ).fetchone()
        if row is None:
            return None
        org_id, name, owner_user_id, plan, created_at, role = row
        return {
            "id": org_id, "name": name, "owner_user_id": owner_user_id, "plan": plan,
            "created_at": created_at, "role": role,
        }

    def get_organization(self, org_id: int) -> dict | None:
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT id, name, owner_user_id, plan, created_at FROM organizations WHERE id=?",
                (org_id,),
            ).fetchone()
        if row is None:
            return None
        org_id_, name, owner_user_id, plan, created_at = row
        return {"id": org_id_, "name": name, "owner_user_id": owner_user_id, "plan": plan, "created_at": created_at}

    def list_org_members(self, org_id: int) -> list[dict]:
        with closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT u.id, u.email, m.role, m.joined_at FROM org_members m "
                "JOIN users u ON u.id = m.user_id WHERE m.org_id=? ORDER BY m.joined_at",
                (org_id,),
            ).fetchall()
        return [
            {"user_id": user_id, "email": email, "role": role, "joined_at": joined_at}
            for user_id, email, role, joined_at in rows
        ]

    def create_org_invite(self, org_id: int, email: str, invited_by_user_id: int) -> str:
        email = email.strip().lower()
        if not email or len(email) > MAX_EMAIL_LENGTH or not _EMAIL_RE.match(email):
            raise ValueError("メールアドレスの形式が正しくありません。")
        existing_user = self.get_user_by_email(email)
        if existing_user is not None:
            current_org = self.get_org_for_user(existing_user.id)
            if current_org is not None and current_org["id"] == org_id:
                raise ValueError("このメールアドレスは既にこの組織のメンバーです。")
        token = secrets.token_urlsafe(32)
        now = time.time()
        with closing(self._connect()) as conn:
            conn.execute(
                "INSERT INTO org_invites(token, org_id, email, invited_by_user_id, created_at, expires_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (token, org_id, email, invited_by_user_id, now, now + self.ORG_INVITE_TOKEN_TTL_SECONDS),
            )
            conn.commit()
        return token

    def get_org_invite(self, token: str) -> dict | None:
        """招待の中身を(受諾せずに)確認する。招待受諾ページの表示用。"""
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT org_id, email, expires_at, accepted_at FROM org_invites WHERE token=?",
                (token,),
            ).fetchone()
        if row is None:
            return None
        org_id, email, expires_at, accepted_at = row
        return {"org_id": org_id, "email": email, "expires_at": expires_at, "accepted_at": accepted_at}

    def accept_org_invite(self, token: str, user_id: int) -> int | None:
        """招待を受諾し、組織に加入する。成功時は加入したorg_id。

        実際にログイン中のユーザーのメールアドレスが招待先メールアドレスと
        一致することを確認する(招待トークン自体は32バイトのランダム値で
        秘匿されているが、多層防御として招待先メールアドレスと受諾者の
        メールアドレスの一致も必ず確認する。例えば招待メールが誤って
        転送された場合でも、本人以外は受諾できない)。

        既に何らかの組織に所属しているユーザーはValueErrorになる
        (1ユーザー1組織の制約。create_organizationと同じ理由)。
        """
        now = time.time()
        with closing(self._connect()) as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                row = conn.execute(
                    "SELECT org_id, email, expires_at, accepted_at FROM org_invites WHERE token=?",
                    (token,),
                ).fetchone()
                if row is None:
                    conn.commit()
                    return None
                org_id, invite_email, expires_at, accepted_at = row
                if accepted_at is not None or expires_at < now:
                    conn.commit()
                    return None
                user_row = conn.execute("SELECT email FROM users WHERE id=?", (user_id,)).fetchone()
                if user_row is None or user_row[0] != invite_email:
                    conn.commit()
                    return None
                already_in_org = conn.execute(
                    "SELECT org_id FROM org_members WHERE user_id=?", (user_id,)
                ).fetchone()
                if already_in_org is not None:
                    conn.commit()
                    raise ValueError(
                        "既にいずれかの組織に所属しているため、この招待を受諾できません。"
                    )
                conn.execute(
                    "INSERT INTO org_members(org_id, user_id, role, joined_at) VALUES (?, ?, 'member', ?)",
                    (org_id, user_id, now),
                )
                conn.execute("UPDATE org_invites SET accepted_at=? WHERE token=?", (now, token))
                conn.commit()
                return org_id
            except Exception:
                conn.rollback()
                raise

    def remove_org_member(self, org_id: int, target_user_id: int) -> bool:
        """組織からメンバーを1名外す(オーナー自身は対象外。オーナーを外す
        操作はdisband_organizationで組織ごと解散する設計にしている)。

        呼び出し側(app.py)で、実行者が組織のオーナー本人か、対象ユーザー
        自身(自主退会)であることを事前に確認すること(このメソッド自体は
        役割による権限チェックを行わない、単純な削除操作)。
        """
        with closing(self._connect()) as conn:
            cur = conn.execute(
                "DELETE FROM org_members WHERE org_id=? AND user_id=? AND role != 'owner'",
                (org_id, target_user_id),
            )
            conn.commit()
            return cur.rowcount > 0

    def disband_organization(self, org_id: int, requesting_user_id: int) -> bool:
        """組織を解散する(オーナーのみ実行可能)。メンバー全員がその場で
        個人プラン/個人の利用回数プールに戻る(org_membersの行を消すだけで、
        `get_org_for_user`が以降Noneを返すようになるため)。"""
        with closing(self._connect()) as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                row = conn.execute(
                    "SELECT owner_user_id FROM organizations WHERE id=?", (org_id,)
                ).fetchone()
                if row is None:
                    conn.commit()
                    return False
                if row[0] != requesting_user_id:
                    conn.commit()
                    raise ValueError("組織を解散できるのはオーナーのみです。")
                conn.execute("DELETE FROM org_members WHERE org_id=?", (org_id,))
                conn.execute("DELETE FROM org_invites WHERE org_id=?", (org_id,))
                conn.execute("DELETE FROM organizations WHERE id=?", (org_id,))
                conn.commit()
                return True
            except Exception:
                conn.rollback()
                raise

    def set_org_plan(self, org_id: int, plan: str) -> None:
        with closing(self._connect()) as conn:
            conn.execute("UPDATE organizations SET plan=? WHERE id=?", (plan, org_id))
            conn.commit()

    # -- アカウント削除・データエクスポート(round8で追加) -------------------
    #
    # 個人情報保護法(APPI)が求める開示請求・削除請求への対応、および
    # 利用者がサービスを離れる際に自分のデータを一括で確認・保存できる
    # ようにするための機能。実サービスとして個人情報(メールアドレス・
    # 身体測定値)を扱う以上、退会・データポータビリティの手段を提供する
    # ことは利用規約/プライバシーポリシー(README「公開前チェックリスト」
    # 参照)の実効性にも関わる。

    def export_user_data(self, user_id: int) -> dict | None:
        """アカウントに紐づく全データをJSONに変換しやすい辞書で返す。

        含めないもの(正直な注記): パスワードハッシュ(仮に漏洩しても
        パスワードそのものではないが、含める理由が無い)、APIキーの
        ハッシュ値(list_api_keysが元々ハッシュを取得しない)、既に
        `generated/`から自動削除された可能性が高い生成物そのもの
        (ダウンロードURLだけを`generation_history`に含める。1時間の
        TTLを過ぎている場合はダウンロードできない旨をREADME/ガイドで
        案内している)。
        """
        user = self.get_user(user_id)
        if user is None:
            return None
        return {
            "account": {
                "email": user.email,
                "plan": user.plan,
                "email_verified": user.email_verified,
                "created_at": user.created_at,
            },
            "measurement_profiles": self.list_measurement_profiles(user_id),
            "generation_history": self.list_jobs_for_owner(f"user:{user_id}", limit=1_000_000),
            "api_keys": self.list_api_keys(user_id),
            "organization": self.get_org_for_user(user_id),
        }

    def delete_user_account(self, user_id: int) -> bool:
        """アカウント本体と関連データを完全に削除する(退会)。

        実際に削除するもの: users本体、保存済み採寸プロフィール全件、
        生成ジョブの所有権レコード(owner_key='user:<id>')、発行済みの
        メール確認/パスワード再設定トークン、当日以降の利用回数カウンタ
        (owner_key='user:<id>')、発行済みAPIキー、組織メンバーシップ。

        削除しないもの(正直な注記):
          - `login_failures`はメールアドレス文字列のみをキーにしており
            user_idと直接紐付いていないため、ここでは触れない。同じ
            メールアドレスで再登録した場合に退会前の失敗履歴が引き継がれる
            可能性があるが、ACCOUNT_LOCKOUT_WINDOW_SECONDS(15分)経過後は
            自然に無効化されるため実害は小さい。
          - Stripeの顧客/サブスクリプション自体はStripe側に残る。実運用
            では本メソッド呼び出し前に、billing.py経由でサブスクリプション
            の解約(cancel_subscription)を別途行うこと(app.py側で実施)。
          - 過去にダウンロードされ利用者の手元に保存されたファイルそのもの
            は当然削除できない。

        オーナーとして組織に他のメンバーを抱えたまま退会しようとした場合は
        ValueErrorにする(組織が宙に浮いた状態になるのを防ぐ。先に組織を
        解散するか、他のメンバーに抜けてもらう必要がある)。

        外部キー制約(FOREIGN KEY)をスキーマ上定義していない(store.py冒頭の
        正直な注記の通り、複数テーブルへ手動でSQLを発行する薄い層のため)
        ため、全ての関連テーブルへの削除を1つのトランザクションで明示的に
        行う。途中で失敗した場合に一部だけ削除された不整合な状態を残さない
        ため。

        戻り値: 該当ユーザーが実際に存在し削除されたか(存在しなければFalse)。
        """
        with closing(self._connect()) as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                row = conn.execute("SELECT id FROM users WHERE id=?", (user_id,)).fetchone()
                if row is None:
                    conn.commit()
                    return False
                org_row = conn.execute(
                    "SELECT id FROM organizations WHERE owner_user_id=?", (user_id,)
                ).fetchone()
                if org_row is not None:
                    other_members = conn.execute(
                        "SELECT COUNT(*) FROM org_members WHERE org_id=? AND user_id != ?",
                        (org_row[0], user_id),
                    ).fetchone()[0]
                    if other_members > 0:
                        conn.commit()  # ロックを閉じるだけで、書き込みは無し
                        raise ValueError(
                            "組織のオーナーは、他のメンバーがいる間は退会できません。"
                            "先に組織を解散してから退会してください。"
                        )
                owner_key = f"user:{user_id}"
                conn.execute("DELETE FROM measurement_profiles WHERE user_id=?", (user_id,))
                conn.execute("DELETE FROM jobs WHERE owner_key=?", (owner_key,))
                conn.execute("DELETE FROM email_tokens WHERE user_id=?", (user_id,))
                conn.execute("DELETE FROM usage_counters WHERE owner_key=?", (owner_key,))
                conn.execute("DELETE FROM api_keys WHERE user_id=?", (user_id,))
                conn.execute("DELETE FROM org_members WHERE user_id=?", (user_id,))
                if org_row is not None:
                    conn.execute("DELETE FROM org_invites WHERE org_id=?", (org_row[0],))
                    conn.execute("DELETE FROM organizations WHERE id=?", (org_row[0],))
                conn.execute("DELETE FROM users WHERE id=?", (user_id,))
                conn.commit()
                return True
            except Exception:
                conn.rollback()
                raise

    def ping(self) -> None:
        """DBへ実際に到達できることを確認する。/healthzで使う。

        実際にpatternforge.dbを壊れたファイル(SQLiteヘッダを持たない
        テキストファイル)に置き換えた状態でサーバーを動かして確認した
        実バグの修正: 以前の/healthzはDBに一切触れず常に200 {"ok": true}
        を返していたため、DBが壊れて signup/login 等が実際には500に
        なっている状況でも、ロードバランサ/オーケストレータのヘルスチェック
        だけは「正常」と判定し続けてしまう監視上の盲点があった。ここでは
        実際に軽いクエリ(SELECT 1)を投げて、失敗したら例外をそのまま
        呼び出し元(app.py の /healthz)に伝える。
        """
        with closing(self._connect()) as conn:
            conn.execute("SELECT 1").fetchone()
