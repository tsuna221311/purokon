import json
import multiprocessing
import threading
import time
from contextlib import closing

import pytest

import store as store_module


# multiprocessing.Process のターゲットにするため、モジュールトップレベルに
# 置く(pickle化できる必要があるため、クロージャ/ネストした関数は使えない)。
# 実際にgunicorn -w 4(本物の複数OSプロセス)を起動してcurlで再現・確認した
# 検証(下のtest_usage_counter_never_exceeds_limit_under_true_multiprocess_concurrency
# 等参照)を、別々のPythonインタプリタ・別々のOSプロセスを使う自動テストとして
# 固定化するためのヘルパー。

def _mp_usage_attempt(db_path, owner_key, limit, day, queue):
    db = store_module.Store(db_path)
    allowed, _ = db.check_and_increment_usage(owner_key, limit, day)
    queue.put(allowed)


def _mp_rate_limit_attempt(db_path, bucket, key, max_requests, window_seconds, queue):
    db = store_module.Store(db_path)
    allowed = db.check_rate_limit(bucket, key, max_requests, window_seconds)
    queue.put(allowed)


def _mp_profile_attempt(db_path, user_id, name, queue):
    db = store_module.Store(db_path)
    try:
        db.create_measurement_profile(user_id, name, 84, 68, 92, 160, 54, 37)
        queue.put(True)
    except ValueError:
        queue.put(False)


def _mp_apply_billing_event(db_path, user_id, created_at, plan, barrier, queue):
    db = store_module.Store(db_path)
    barrier.wait()  # 2つのプロセスができるだけ同時にapply_billing_event()を呼ぶようにする
    applied = db.apply_billing_event(user_id, created_at, plan)
    queue.put((created_at, applied))


def _mp_email_token_attempt(db_path, user_id, purpose, cooldown_seconds, ttl_seconds, barrier, queue):
    db = store_module.Store(db_path)
    barrier.wait()  # 複数プロセスができるだけ同時にtry_create_email_token_with_cooldown()を呼ぶようにする
    token = db.try_create_email_token_with_cooldown(user_id, purpose, cooldown_seconds, ttl_seconds)
    queue.put(token)


@pytest.fixture()
def db(tmp_path):
    return store_module.Store(str(tmp_path / "test.db"))


def test_create_user_and_authenticate(db):
    user_id = db.create_user("Person@Example.com", "password123")
    user = db.authenticate("person@example.com", "password123")  # 大文字小文字を無視して一致
    assert user is not None
    assert user.id == user_id
    assert user.plan == "free"


def test_authenticate_rejects_wrong_password(db):
    db.create_user("person@example.com", "password123")
    assert db.authenticate("person@example.com", "wrong-password") is None


def test_authenticate_rejects_unknown_email(db):
    assert db.authenticate("nobody@example.com", "password123") is None


def test_authenticate_does_not_leak_account_existence_via_timing(db):
    # 実際にwerkzeug.security.check_password_hash(意図的に遅いscrypt由来の
    # 検証)を使って実測したところ、実在するメールアドレス宛の誤った
    # パスワードでの認証は平均約93ms、実在しないメールアドレスの場合
    # (以前はDB検索がヒットしない時点で即returnしていた)は平均約0.2msと、
    # 応答時間に約430倍もの差があった。これは/loginの応答時間を計測する
    # だけで、パスワードを知らなくても「そのメールアドレスが登録済みか」を
    # 外部から判定できてしまう、実際に悪用可能なタイミングサイドチャネル
    # だった。実在しない場合でもダミーハッシュで同じ検証コストをかけて
    # 応答時間を揃える修正(`store._dummy_password_hash`)を行った。
    # ここでは実際に両パターンを計測し、比率が明らかな漏洩を示す水準
    # (実測で430倍)まで開かないことを確認する。CI環境のノイズを考慮し、
    # 「10倍以上遅い」という緩めの閾値で判定する（修正前は430倍だったため、
    # 修正が機能していれば十分に余裕を持って通る一方、リグレッションで
    # 再び即returnするようになれば確実に引っかかる）。
    db.create_user("existing.user@example.com", "correct-password-123")

    def _time_n(fn, n=30):
        start = time.perf_counter()
        for _ in range(n):
            fn()
        return time.perf_counter() - start

    existing_elapsed = _time_n(
        lambda: db.authenticate("existing.user@example.com", "wrong-password")
    )
    nonexistent_elapsed = _time_n(
        lambda: db.authenticate("nobody.at.all@example.com", "wrong-password")
    )

    assert nonexistent_elapsed > 0
    assert existing_elapsed / nonexistent_elapsed < 10.0


def test_create_user_rejects_duplicate_email(db):
    db.create_user("person@example.com", "password123")
    with pytest.raises(store_module.EmailAlreadyRegisteredError):
        db.create_user("person@example.com", "password123")


def test_create_user_rejects_short_password(db):
    with pytest.raises(ValueError):
        db.create_user("person@example.com", "short")


def test_create_user_rejects_invalid_email(db):
    with pytest.raises(ValueError):
        db.create_user("not-an-email", "password123")


@pytest.mark.parametrize(
    "bad_email",
    [
        "abc@",
        "@example.com",
        "a@b",
        "a b@example.com",
        "山田太郎@example.com",
        "a@@b.com",
        "  @  ",
    ],
)
def test_create_user_rejects_malformed_email_formats(db, bad_email):
    # 実際に本物のSMTP送信(aiosmtpd)を使ってテストした際に見つかった問題:
    # 以前は "@" が含まれているかだけしかチェックしておらず、上記のような
    # 明らかに不正な(配送不可能な)アドレスまで登録できてしまっていた。
    # 特にローカルパートにマルチバイト文字を含むアドレスは、そのまま
    # mailer.SMTPMailer.send() の "To" ヘッダーに生のUTF-8バイト列として
    # 出力され、SMTPUTF8拡張に対応しないメールサーバーでは配送に失敗する。
    with pytest.raises(ValueError):
        db.create_user(bad_email, "password123")


def test_create_user_rejects_email_over_the_rfc_practical_length_limit(db):
    # 実際にサーバーを起動して/signupへ100,000文字の「メールアドレス」を
    # POSTしたところ、200で受理されアカウントが作成されてしまう実バグを発見
    # した(修正前は_EMAIL_REが文字種・形式だけを見ており、長さの上限が無いため
    # `+`が無制限にマッチしていた)。RFC 5321の実務上の上限(254文字)を超える
    # ものは拒否することを固定する。
    too_long_local_part = "a" * 250
    huge_email = f"{too_long_local_part}@example.com"
    assert len(huge_email) > store_module.MAX_EMAIL_LENGTH
    with pytest.raises(ValueError):
        db.create_user(huge_email, "password123")


def test_create_user_accepts_email_exactly_at_the_length_limit(db):
    # ちょうど上限(254文字)のメールアドレスは、境界値として拒否されない
    # ことを確認する(off-by-oneの回帰防止)。
    domain = "@example.com"
    local_part = "a" * (store_module.MAX_EMAIL_LENGTH - len(domain))
    email = f"{local_part}{domain}"
    assert len(email) == store_module.MAX_EMAIL_LENGTH
    user_id = db.create_user(email, "password123")
    assert db.get_user(user_id) is not None


@pytest.mark.parametrize(
    "good_email",
    [
        "person@example.com",
        "user.name+tag@sub.example.co.jp",
        "a@b.co",
        "test_user-1@my-domain.com",
    ],
)
def test_create_user_accepts_realistic_email_formats(db, good_email):
    user_id = db.create_user(good_email, "password123")
    assert db.get_user(user_id) is not None


def test_set_plan_persists(db):
    user_id = db.create_user("person@example.com", "password123")
    db.set_plan(user_id, "pro")
    assert db.get_user(user_id).plan == "pro"


def test_job_ownership_round_trip(db):
    db.record_job("abc123", "anon:visitor-1")
    assert db.get_job_owner("abc123") == "anon:visitor-1"
    assert db.get_job_owner("does-not-exist") is None


def test_reassign_jobs_moves_ownership(db):
    db.record_job("abc123", "anon:visitor-1")
    moved = db.reassign_jobs("anon:visitor-1", "user:1")
    assert moved == 1
    assert db.get_job_owner("abc123") == "user:1"


def test_usage_counter_increments_and_enforces_limit(db):
    day = "2026-08-19"
    allowed1, used1 = db.check_and_increment_usage("anon:visitor-1", 2, day)
    allowed2, used2 = db.check_and_increment_usage("anon:visitor-1", 2, day)
    allowed3, used3 = db.check_and_increment_usage("anon:visitor-1", 2, day)
    assert (allowed1, used1) == (True, 1)
    assert (allowed2, used2) == (True, 2)
    assert (allowed3, used3) == (False, 2)  # 上限到達後はカウントを増やさない


def test_usage_counter_is_scoped_per_day(db):
    db.check_and_increment_usage("anon:visitor-1", 1, "2026-08-19")
    allowed_next_day, used_next_day = db.check_and_increment_usage("anon:visitor-1", 1, "2026-08-20")
    assert allowed_next_day is True
    assert used_next_day == 1


def test_usage_counter_none_limit_means_unlimited(db):
    for _ in range(5):
        allowed, _ = db.check_and_increment_usage("user:1", None, "2026-08-19")
        assert allowed is True


def test_usage_today_reads_without_incrementing(db):
    db.check_and_increment_usage("anon:visitor-1", None, "2026-08-19")
    db.check_and_increment_usage("anon:visitor-1", None, "2026-08-19")
    assert db.usage_today("anon:visitor-1", "2026-08-19") == 2
    assert db.usage_today("anon:visitor-1", "2026-08-19") == 2  # 読むだけでは増えない


def test_refund_usage_decrements_the_counter(db):
    db.check_and_increment_usage("anon:visitor-1", None, "2026-08-19")
    db.check_and_increment_usage("anon:visitor-1", None, "2026-08-19")
    assert db.usage_today("anon:visitor-1", "2026-08-19") == 2
    db.refund_usage("anon:visitor-1", "2026-08-19")
    assert db.usage_today("anon:visitor-1", "2026-08-19") == 1


def test_refund_usage_does_not_go_below_zero(db):
    # 該当日の行が存在しない場合や、既に0の場合にrefundしても負値化しない
    # (二重にrefundが呼ばれるような想定外の呼び出し順でも安全なようにする)。
    db.refund_usage("anon:never-used", "2026-08-19")
    assert db.usage_today("anon:never-used", "2026-08-19") == 0

    db.check_and_increment_usage("anon:visitor-1", None, "2026-08-19")
    db.refund_usage("anon:visitor-1", "2026-08-19")
    db.refund_usage("anon:visitor-1", "2026-08-19")
    assert db.usage_today("anon:visitor-1", "2026-08-19") == 0


def test_refund_usage_is_scoped_to_owner_and_day(db):
    db.check_and_increment_usage("anon:visitor-1", None, "2026-08-19")
    db.check_and_increment_usage("anon:visitor-2", None, "2026-08-19")
    db.check_and_increment_usage("anon:visitor-1", None, "2026-08-20")

    db.refund_usage("anon:visitor-1", "2026-08-19")
    assert db.usage_today("anon:visitor-1", "2026-08-19") == 0
    assert db.usage_today("anon:visitor-2", "2026-08-19") == 1  # 他のownerには影響しない
    assert db.usage_today("anon:visitor-1", "2026-08-20") == 1  # 他の日にも影響しない


def test_usage_counter_never_exceeds_limit_under_concurrent_requests(db):
    # 以前はSELECT→INSERT/UPDATEの間に競合状態があり、同じowner_keyから
    # 極めて近いタイミングで並行リクエストが来ると上限をすり抜けることが
    # あった。BEGIN IMMEDIATEで直列化した後は、並行実行しても上限
    # (ここでは5)を超えないことを確認する。
    limit = 5
    results = []
    lock = threading.Lock()

    def _attempt():
        allowed, _ = db.check_and_increment_usage("anon:concurrent-visitor", limit, "2026-08-19")
        with lock:
            results.append(allowed)

    threads = [threading.Thread(target=_attempt) for _ in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert results.count(True) == limit
    assert db.usage_today("anon:concurrent-visitor", "2026-08-19") == limit


def test_measurement_profile_limit_never_exceeded_under_concurrent_requests(db, monkeypatch):
    # 実際に20並行スレッドから同じユーザーで保存を試すテストで見つかった
    # 実バグの再発防止テスト。以前のcreate_measurement_profile()は
    # 素朴なSELECT COUNT(*)→(上限未満なら)INSERTだったため、上限
    # ちょうど手前の状態から並行して保存すると、複数のリクエストが
    # ほぼ同時にCOUNTを読んでどちらも「まだ上限未満」と判定してしまい、
    # 上限(50件)を超えるプロフィールが保存されてしまっていた(実際に
    # 49件保存済みの状態から20並行リクエストを送ると、本来1件しか
    # 通らないはずが8件通って57件になることを確認して発見した)。
    # 利用回数カウンタ(check_and_increment_usage)で以前修正した既知の
    # レースと同種のバグで、同じ`BEGIN IMMEDIATE`による直列化で修正した。
    monkeypatch.setattr(store_module, "MAX_MEASUREMENT_PROFILES_PER_USER", 5)
    user_id = db.create_user("racer@example.com", "password123")
    for i in range(4):  # 上限(5件)のちょうど1件手前まで埋めておく
        db.create_measurement_profile(user_id, f"pre{i}", 84, 68, 92, 160, 54, 37)

    results = []
    lock = threading.Lock()

    def _attempt(i):
        try:
            db.create_measurement_profile(user_id, f"race{i}", 84, 68, 92, 160, 54, 37)
            ok = True
        except ValueError:
            ok = False
        with lock:
            results.append(ok)

    threads = [threading.Thread(target=_attempt, args=(i,)) for i in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert results.count(True) == 1
    assert len(db.list_measurement_profiles(user_id)) == 5


def test_usage_counter_never_exceeds_limit_under_true_multiprocess_concurrency(tmp_path):
    """実際にgunicorn -w 4(python3 app.pyの開発用サーバではなく、本番運用で
    推奨している本物の複数OSプロセス構成)を起動し、ログイン済みユーザーの
    本物のセッションCookieで日次上限(freeプランの10回)近くまで、25並行の
    curlリクエストを実際にHTTPで送って検証したところ、正しく「成功10件・
    残りは429」に収まり、'database is locked'等の500エラーも一切
    発生しないことを確認した。

    その過程で分かった重要な事実(正直な記録): `python3 app.py`で起動する
    開発用サーバは既定で`threaded=False, processes=1`(Flask/Werkzeugの
    デフォルト)であり、実際には**1リクエストずつ完全に直列処理**している。
    実際に大きめのフルセット型紙生成リクエストを5〜8並行でcurl送信し、
    個々のリクエスト完了時刻を計測したところ、単体では約0.24秒で完了する
    処理が、並行送信時には後続のリクエストほど完了までの時間が線形に
    伸びる(キューで待たされる)ことを実測し、真の並行処理ではなく直列
    処理であることを確認した。つまり、これまでの各ラウンドで「実際に
    サーバを起動してN並行のcurlリクエストを送って再現・確認した」という
    記述の多くは、`python3 app.py`だけを指している場合、実際にはHTTPレベル
    での真の並行アクセスを起こせていない可能性がある(一方でpytestの
    threading テスト自体は同一プロセス内の本物のPythonスレッドを使っており、
    これは有効な検証である)。本番で実際に使われるgunicornの複数ワーカーは
    互いに独立したOSプロセス(別々のPythonインタプリタ・別々のメモリ空間・
    別々のGIL)であり、スレッドだけの検証では捉えられない種類の不具合
    (例: プロセス内メモリ状態への暗黙の依存)が理論上ありうる。

    このテストは、既存のtest_usage_counter_never_exceeds_limit_under_
    concurrent_requests(同一プロセス内のスレッド並行)を補完し、
    `multiprocessing.Process`で実際に別々のOSプロセス・別々のPython
    インタプリタを起動して同じ検証を自動テスト化したもの。
    """
    db_path = str(tmp_path / "mp_usage_test.db")
    store_module.Store(db_path)  # スキーマを先に作っておく

    limit = 5
    queue = multiprocessing.Queue()
    procs = [
        multiprocessing.Process(
            target=_mp_usage_attempt,
            args=(db_path, "anon:mp-visitor", limit, "2026-08-19", queue),
        )
        for _ in range(20)
    ]
    for p in procs:
        p.start()
    for p in procs:
        p.join(timeout=30)
    for p in procs:
        assert p.exitcode == 0  # 'database is locked'等の未処理例外で落ちていないこと

    results = [queue.get() for _ in range(20)]
    assert results.count(True) == limit

    final_db = store_module.Store(db_path)
    assert final_db.usage_today("anon:mp-visitor", "2026-08-19") == limit


def test_check_rate_limit_allows_up_to_the_limit_then_denies(db):
    for _ in range(3):
        assert db.check_rate_limit("generate", "1.2.3.4", max_requests=3, window_seconds=60.0) is True
    assert db.check_rate_limit("generate", "1.2.3.4", max_requests=3, window_seconds=60.0) is False


def test_check_rate_limit_is_scoped_per_bucket_and_key(db):
    # 同じキーでもバケットが違えば別カウント、同じバケットでもキーが
    # 違えば別カウントになる(app.pyの_generate_rate_limiter・
    # _download_rate_limiter等が互いに干渉しないこと)。
    for _ in range(2):
        assert db.check_rate_limit("generate", "1.1.1.1", max_requests=2, window_seconds=60.0) is True
    assert db.check_rate_limit("generate", "1.1.1.1", max_requests=2, window_seconds=60.0) is False
    # 別バケット(download)なら同じIPでも独立してカウントされる。
    assert db.check_rate_limit("download", "1.1.1.1", max_requests=2, window_seconds=60.0) is True
    # 別キー(別IP)なら同じバケットでも独立してカウントされる。
    assert db.check_rate_limit("generate", "2.2.2.2", max_requests=2, window_seconds=60.0) is True


def test_check_rate_limit_resets_after_the_window_elapses(db):
    # 実時間を待つ代わりに、記録済みヒットのtsを「ウィンドウより前」に
    # 直接書き換える(test_try_create_email_token_with_cooldown_allows_
    # after_cooldown_elapsesと同じ手法)。
    assert db.check_rate_limit("login", "9.9.9.9", max_requests=1, window_seconds=10.0) is True
    assert db.check_rate_limit("login", "9.9.9.9", max_requests=1, window_seconds=10.0) is False
    import sqlite3
    with sqlite3.connect(db.db_path) as conn:
        conn.execute(
            "UPDATE rate_limit_hits SET ts = ts - 11 WHERE bucket='login' AND rl_key='9.9.9.9'",
        )
        conn.commit()
    assert db.check_rate_limit("login", "9.9.9.9", max_requests=1, window_seconds=10.0) is True


def test_delete_rate_limit_hits_older_than_prunes_stale_rows(db):
    assert db.check_rate_limit("generate", "3.3.3.3", max_requests=1, window_seconds=1_000_000.0) is True
    # ウィンドウが極端に長いので、そのままでは2回目は拒否されるはず。
    assert db.check_rate_limit("generate", "3.3.3.3", max_requests=1, window_seconds=1_000_000.0) is False

    import sqlite3
    with sqlite3.connect(db.db_path) as conn:
        conn.execute("UPDATE rate_limit_hits SET ts = ts - 3600 WHERE bucket='generate' AND rl_key='3.3.3.3'")
        conn.commit()
    # cutoffを3600秒前より新しい時刻にして掃除すると、上のヒットが消える。
    db.delete_rate_limit_hits_older_than(time.time() - 60)
    # 掃除後はヒット記録が無くなっているため、ウィンドウが極端に長い設定でも
    # 再度1回だけ許可される。
    assert db.check_rate_limit("generate", "3.3.3.3", max_requests=1, window_seconds=1_000_000.0) is True


def test_check_rate_limit_never_exceeds_limit_under_true_multiprocess_concurrency(tmp_path):
    """round6で追加: レート制限を単一プロセスのメモリからSQLite共有に
    切り替えたこと(既知の制約の解消)自体を、上の
    test_usage_counter_never_exceeds_limit_under_true_multiprocess_concurrency
    と全く同じ手法(`multiprocessing.Process`による本物の別OSプロセス)で
    検証する。もし切り替えが不完全で実はプロセス内メモリに残っている
    実装だったら、このテストは20回のうち20回とも許可されてしまい
    (=各プロセスが自分のメモリで独立にカウントするため)失敗するはずで、
    実際に複数プロセス間で共有されていることの直接的な証拠になる。
    """
    db_path = str(tmp_path / "mp_rate_limit_test.db")
    store_module.Store(db_path)  # スキーマを先に作っておく

    max_requests = 5
    queue = multiprocessing.Queue()
    procs = [
        multiprocessing.Process(
            target=_mp_rate_limit_attempt,
            args=(db_path, "generate", "mp-client-ip", max_requests, 60.0, queue),
        )
        for _ in range(20)
    ]
    for p in procs:
        p.start()
    for p in procs:
        p.join(timeout=30)
    for p in procs:
        assert p.exitcode == 0  # 'database is locked'等の未処理例外で落ちていないこと

    results = [queue.get() for _ in range(20)]
    assert results.count(True) == max_requests


# --- round7: アカウント単位のログイン総当たり対策 --------------------------

def test_check_account_lockout_is_not_locked_before_threshold(db, monkeypatch):
    monkeypatch.setattr(store_module, "ACCOUNT_LOCKOUT_THRESHOLD", 5)
    for _ in range(4):
        db.record_login_failure("victim@example.com")
    assert db.check_account_lockout("victim@example.com") == 0.0


def test_check_account_lockout_locks_after_threshold_and_backs_off(db, monkeypatch):
    monkeypatch.setattr(store_module, "ACCOUNT_LOCKOUT_THRESHOLD", 5)
    monkeypatch.setattr(store_module, "ACCOUNT_LOCKOUT_BASE_SECONDS", 30.0)
    monkeypatch.setattr(store_module, "ACCOUNT_LOCKOUT_MAX_SECONDS", 900.0)
    for _ in range(5):
        db.record_login_failure("victim@example.com")
    remaining = db.check_account_lockout("victim@example.com")
    # ちょうど閾値と同数なので、指数バックオフの初回(BASE_SECONDS)相当。
    assert 0.0 < remaining <= 30.0

    db.record_login_failure("victim@example.com")  # 6回目
    remaining_after_one_more = db.check_account_lockout("victim@example.com")
    # 失敗が積み重なるほどロック時間が指数的に伸びる(倍々)。
    assert remaining_after_one_more > remaining


def test_check_account_lockout_caps_at_the_maximum(db, monkeypatch):
    monkeypatch.setattr(store_module, "ACCOUNT_LOCKOUT_THRESHOLD", 5)
    monkeypatch.setattr(store_module, "ACCOUNT_LOCKOUT_BASE_SECONDS", 30.0)
    monkeypatch.setattr(store_module, "ACCOUNT_LOCKOUT_MAX_SECONDS", 60.0)
    for _ in range(20):  # 指数的に増やせばBASE_SECONDS * 2^15は上限を大幅に超える
        db.record_login_failure("victim@example.com")
    remaining = db.check_account_lockout("victim@example.com")
    assert remaining <= 60.0


def test_check_account_lockout_is_scoped_per_email(db, monkeypatch):
    monkeypatch.setattr(store_module, "ACCOUNT_LOCKOUT_THRESHOLD", 5)
    for _ in range(5):
        db.record_login_failure("victim@example.com")
    assert db.check_account_lockout("victim@example.com") > 0.0
    assert db.check_account_lockout("someone-else@example.com") == 0.0


def test_check_account_lockout_is_case_insensitive_on_email(db, monkeypatch):
    monkeypatch.setattr(store_module, "ACCOUNT_LOCKOUT_THRESHOLD", 5)
    for _ in range(5):
        db.record_login_failure("Victim@Example.com")
    assert db.check_account_lockout("victim@example.com") > 0.0


def test_clear_login_failures_resets_the_lockout(db, monkeypatch):
    monkeypatch.setattr(store_module, "ACCOUNT_LOCKOUT_THRESHOLD", 5)
    for _ in range(5):
        db.record_login_failure("victim@example.com")
    assert db.check_account_lockout("victim@example.com") > 0.0

    db.clear_login_failures("victim@example.com")
    assert db.check_account_lockout("victim@example.com") == 0.0


def test_check_account_lockout_ignores_failures_outside_the_window(db, monkeypatch):
    monkeypatch.setattr(store_module, "ACCOUNT_LOCKOUT_THRESHOLD", 5)
    monkeypatch.setattr(store_module, "ACCOUNT_LOCKOUT_WINDOW_SECONDS", 10.0)
    for _ in range(5):
        db.record_login_failure("victim@example.com")
    assert db.check_account_lockout("victim@example.com") > 0.0

    import sqlite3
    with sqlite3.connect(db.db_path) as conn:
        conn.execute("UPDATE login_failures SET ts = ts - 11 WHERE email_key='victim@example.com'")
        conn.commit()
    # ウィンドウ(10秒)より古い失敗はもうカウントされない。
    assert db.check_account_lockout("victim@example.com") == 0.0


def test_delete_login_failures_older_than_prunes_stale_rows(db, monkeypatch):
    monkeypatch.setattr(store_module, "ACCOUNT_LOCKOUT_THRESHOLD", 5)
    for _ in range(5):
        db.record_login_failure("victim@example.com")
    assert db.check_account_lockout("victim@example.com") > 0.0

    import sqlite3
    with sqlite3.connect(db.db_path) as conn:
        conn.execute("UPDATE login_failures SET ts = ts - 3600 WHERE email_key='victim@example.com'")
        conn.commit()
    db.delete_login_failures_older_than(time.time() - 60)
    assert db.check_account_lockout("victim@example.com") == 0.0


def test_account_lockout_never_exceeds_effective_threshold_under_true_multiprocess_concurrency(tmp_path, monkeypatch):
    """上のレート制限版と同じ観点(本物の複数OSプロセスの並行アクセス)で、
    ログイン失敗の記録が競合状態を起こさず、全プロセス分の失敗が正しく
    1件ずつ記録されることを確認する。"""
    monkeypatch.setattr(store_module, "ACCOUNT_LOCKOUT_THRESHOLD", 1000)  # ロック閾値に達しないようにする
    db_path = str(tmp_path / "mp_login_failure_test.db")
    store_module.Store(db_path)  # スキーマを先に作っておく

    def _mp_record_failure(db_path, email, queue):
        db = store_module.Store(db_path)
        db.record_login_failure(email)
        queue.put(True)

    queue = multiprocessing.Queue()
    procs = [
        multiprocessing.Process(target=_mp_record_failure, args=(db_path, "victim@example.com", queue))
        for _ in range(20)
    ]
    for p in procs:
        p.start()
    for p in procs:
        p.join(timeout=30)
    for p in procs:
        assert p.exitcode == 0

    final_db = store_module.Store(db_path)
    import sqlite3
    with sqlite3.connect(db_path) as conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM login_failures WHERE email_key='victim@example.com'"
        ).fetchone()[0]
    assert count == 20
    assert final_db.check_account_lockout("victim@example.com") == 0.0  # 閾値未満


def test_measurement_profile_limit_never_exceeded_under_true_multiprocess_concurrency(tmp_path, monkeypatch):
    """上のusage_counter版と同じ観点で、採寸プロフィールの上限保護
    (create_measurement_profile)についても、本物の複数OSプロセスの並行
    アクセスに対して安全であることを確認する回帰テスト。"""
    monkeypatch.setattr(store_module, "MAX_MEASUREMENT_PROFILES_PER_USER", 5)
    db_path = str(tmp_path / "mp_profile_test.db")
    db = store_module.Store(db_path)
    user_id = db.create_user("mpracer@example.com", "password123")
    for i in range(4):  # 上限(5件)のちょうど1件手前まで埋めておく
        db.create_measurement_profile(user_id, f"pre{i}", 84, 68, 92, 160, 54, 37)

    queue = multiprocessing.Queue()
    procs = [
        multiprocessing.Process(
            target=_mp_profile_attempt, args=(db_path, user_id, f"race{i}", queue),
        )
        for i in range(20)
    ]
    for p in procs:
        p.start()
    for p in procs:
        p.join(timeout=30)
    for p in procs:
        assert p.exitcode == 0

    results = [queue.get() for _ in range(20)]
    assert results.count(True) == 1
    assert len(db.list_measurement_profiles(user_id)) == 5


def test_apply_billing_event_ordering_holds_under_true_multiprocess_concurrency(tmp_path):
    """round21で修正したStripe Webhook配信順序の不具合
    (apply_billing_eventのdocstring参照)を、真の複数OSプロセスの並行アクセス
    に対しても再確認する回帰テスト。

    実際に`gunicorn -w 4`を起動し、本物のstripeライブラリ・本物のHMAC署名で
    「古い(生成時刻が古い)past_dueイベント」と「新しい(生成時刻が新しい)
    activeイベント」を、Pythonのthreadingで**本当に同時に**(どちらのHTTP
    リクエストがどのgunicornワーカープロセスに割り振られるかは制御できない
    状態で)20ラウンドPOSTしたところ、割り振られたワーカーの組み合わせに
    関係なく毎回正しく新しい方(active/pro)の内容に収束し、'database is
    locked'等の500エラーも一切発生しないことを確認した。round21時点では
    この配信順序保護は単一の開発用サーバへの順序付きcurl呼び出しでしか
    検証していなかった(round22で判明した通り、開発用サーバは実際には
    直列処理のため、真の同時アクセスにはなっていなかった可能性がある)。

    このテストは`multiprocessing.Process`+`multiprocessing.Barrier`で、
    実際に別々のOSプロセスから可能な限り同時に`apply_billing_event()`を
    呼び出し、同じ保証を自動テスト化したもの。
    """
    db_path = str(tmp_path / "mp_billing_test.db")
    db = store_module.Store(db_path)
    user_id = db.create_user("mpbilling@example.com", "password123")
    db.apply_billing_event(user_id, 500.0, "pro")  # 事前の基準状態

    t1, t2 = 600.0, 900.0  # t1: 古い(past_due相当), t2: 新しい(active相当)
    barrier = multiprocessing.Barrier(2)
    queue = multiprocessing.Queue()
    procs = [
        multiprocessing.Process(
            target=_mp_apply_billing_event, args=(db_path, user_id, t1, "free", barrier, queue),
        ),
        multiprocessing.Process(
            target=_mp_apply_billing_event, args=(db_path, user_id, t2, "pro", barrier, queue),
        ),
    ]
    for p in procs:
        p.start()
    for p in procs:
        p.join(timeout=30)
    for p in procs:
        assert p.exitcode == 0  # 未処理例外で落ちていないこと

    results = dict(queue.get() for _ in range(2))
    assert results[t2] is True  # 新しいイベントは常に適用される
    # 古いイベントがどちらの順で処理されても、最終的に新しい方の内容が残る。
    final = db.get_user(user_id)
    assert final.plan == "pro"
    assert final.last_billing_event_at == t2


def test_try_create_email_token_with_cooldown_allows_first_call(db):
    user_id = db.create_user("cooldown@example.com", "password123")
    token = db.try_create_email_token_with_cooldown(user_id, "reset", 60, 3600)
    assert token is not None


def test_try_create_email_token_with_cooldown_blocks_immediate_second_call(db):
    user_id = db.create_user("cooldown2@example.com", "password123")
    first = db.try_create_email_token_with_cooldown(user_id, "reset", 60, 3600)
    second = db.try_create_email_token_with_cooldown(user_id, "reset", 60, 3600)
    assert first is not None
    assert second is None


def test_try_create_email_token_with_cooldown_allows_after_cooldown_elapses(db, monkeypatch):
    user_id = db.create_user("cooldown3@example.com", "password123")
    db.try_create_email_token_with_cooldown(user_id, "reset", 60, 3600)
    # 発行直後のcreated_atをクールダウンより前の時刻に書き換えて、
    # 「クールダウンが経過した後」の状態を作る(実時間を60秒待つ代わり)。
    import sqlite3
    with sqlite3.connect(db.db_path) as conn:
        conn.execute(
            "UPDATE email_tokens SET created_at = created_at - 61 WHERE user_id=? AND purpose='reset'",
            (user_id,),
        )
        conn.commit()
    token = db.try_create_email_token_with_cooldown(user_id, "reset", 60, 3600)
    assert token is not None


def test_try_create_email_token_with_cooldown_purposes_and_users_are_independent(db):
    user_a = db.create_user("cooldown-a@example.com", "password123")
    user_b = db.create_user("cooldown-b@example.com", "password123")
    assert db.try_create_email_token_with_cooldown(user_a, "reset", 60, 3600) is not None
    # 同じユーザーでもpurposeが違えば独立してクールダウンする
    # (パスワード再設定を要求した直後でも、メール確認の再送は別枠で許可される)。
    assert db.try_create_email_token_with_cooldown(user_a, "verify", 60, 3600) is not None
    # ユーザーが違えば当然独立している。
    assert db.try_create_email_token_with_cooldown(user_b, "reset", 60, 3600) is not None


def test_try_create_email_token_with_cooldown_only_one_winner_under_true_thread_concurrency(db):
    """実際に本物のスレッド(SQLite I/O中にGILが解放される、真の並行実行)で
    同一ユーザー・同一purposeに20並行でアクセスして見つかった実バグの回帰
    テスト。

    以前は`seconds_since_last_token()`(単純なSELECT)でクールダウンを確認し、
    経過していれば別途`create_email_token()`(単純なINSERT)を呼ぶという
    2段構えだったため、ほぼ同時に来たリクエストの多くが「まだ誰も新しい
    トークンを発行していない」時点の古いSELECT結果を見てしまい、20回中18回も
    クールダウンをすり抜けてトークンを発行(=メールを送信)してしまうことを
    実際に確認した(第2回監査 指摘#3で要求された、同一被害者へのメール爆撃を
    防ぐDB側のユーザー単位クールダウンが、並行リクエストの下では実質的に
    機能していなかったことになる)。`BEGIN IMMEDIATE`でクールダウン確認と
    トークン発行を1つのトランザクションにまとめたことで、並行呼び出しの
    うち winner は必ず1件だけになることを確認する。
    """
    user_id = db.create_user("thread-race@example.com", "password123")
    results = []
    lock = threading.Lock()
    barrier = threading.Barrier(20)

    def attempt():
        barrier.wait()
        token = db.try_create_email_token_with_cooldown(user_id, "reset", 60, 3600)
        if token is not None:
            with lock:
                results.append(token)

    threads = [threading.Thread(target=attempt) for _ in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(results) == 1
    assert len(set(results)) == 1  # 発行されたトークンも1つだけ


def test_try_create_email_token_with_cooldown_only_one_winner_under_true_multiprocess_concurrency(tmp_path):
    """上のスレッドテストと同じ保証を、実際に別々のOSプロセスから可能な限り
    同時に呼び出して確認する(gunicorn -w 4のような複数ワーカー構成を
    より忠実に再現する)。
    """
    db_path = str(tmp_path / "mp_email_token_test.db")
    db = store_module.Store(db_path)
    user_id = db.create_user("mp-email-race@example.com", "password123")

    n = 12
    barrier = multiprocessing.Barrier(n)
    queue = multiprocessing.Queue()
    procs = [
        multiprocessing.Process(
            target=_mp_email_token_attempt, args=(db_path, user_id, "reset", 60, 3600, barrier, queue),
        )
        for _ in range(n)
    ]
    for p in procs:
        p.start()
    for p in procs:
        p.join(timeout=30)
    for p in procs:
        assert p.exitcode == 0

    tokens = [queue.get() for _ in range(n)]
    sent = [t for t in tokens if t is not None]
    assert len(sent) == 1


def test_migration_adds_new_columns_to_pre_existing_db_file(tmp_path):
    # 新しい列(email_verified等)を追加する前に作られたDBファイルでも、
    # Storeを開き直すだけで安全に列が追加され、既存の行は壊れないことを
    # 確認する(store.py の _migrate 参照)。
    import sqlite3
    from contextlib import closing

    db_path = str(tmp_path / "legacy.db")
    with closing(sqlite3.connect(db_path)) as conn:
        conn.executescript(
            """
            CREATE TABLE users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                plan TEXT NOT NULL DEFAULT 'free',
                created_at REAL NOT NULL
            );
            CREATE TABLE jobs (
                job_id TEXT PRIMARY KEY,
                owner_key TEXT NOT NULL,
                created_at REAL NOT NULL
            );
            """
        )
        conn.execute(
            "INSERT INTO users(email, password_hash, plan, created_at) VALUES (?, ?, 'free', ?)",
            ("legacy@example.com", "not-a-real-hash", 0.0),
        )
        conn.commit()

    migrated = store_module.Store(db_path)
    user = migrated.get_user_by_email("legacy@example.com")
    assert user is not None
    assert user.email_verified is False
    assert user.stripe_customer_id is None


def test_email_token_round_trip_for_verification(db):
    user_id = db.create_user("person@example.com", "password123")
    token = db.create_email_token(user_id, "verify", ttl_seconds=3600)
    assert db.consume_email_token(token, "verify") == user_id


def test_email_token_cannot_be_reused(db):
    user_id = db.create_user("person@example.com", "password123")
    token = db.create_email_token(user_id, "verify", ttl_seconds=3600)
    db.consume_email_token(token, "verify")
    assert db.consume_email_token(token, "verify") is None


def test_email_token_rejects_wrong_purpose(db):
    user_id = db.create_user("person@example.com", "password123")
    token = db.create_email_token(user_id, "verify", ttl_seconds=3600)
    assert db.consume_email_token(token, "reset") is None


def test_email_token_rejects_expired_token(db):
    user_id = db.create_user("person@example.com", "password123")
    token = db.create_email_token(user_id, "reset", ttl_seconds=-1)  # 発行直後に期限切れ
    assert db.consume_email_token(token, "reset") is None


def test_email_token_rejects_unknown_token(db):
    assert db.consume_email_token("no-such-token", "verify") is None


def test_peek_verify_token_user_id_returns_user_id_regardless_of_used_or_expired_state(db):
    """app.pyのverify_emailが「自動prefetchで既に消費された後、本人が同じ
    リンクを開いても既に確認済みなら成功と案内する」フォールバックに使う
    (round32で発見・修正した実バグ)。used_at・expires_atに関わらず
    user_idを返す設計であることを確認する。
    """
    user_id = db.create_user("person@example.com", "password123")
    token = db.create_email_token(user_id, "verify", ttl_seconds=3600)
    assert db.peek_verify_token_user_id(token) == user_id

    db.consume_email_token(token, "verify")
    # 消費済みでも(=used_atがセットされていても)引き続きuser_idを返す。
    assert db.peek_verify_token_user_id(token) == user_id


def test_peek_verify_token_user_id_returns_none_for_unknown_or_wrong_purpose_token(db):
    user_id = db.create_user("person@example.com", "password123")
    reset_token = db.create_email_token(user_id, "reset", ttl_seconds=3600)
    assert db.peek_verify_token_user_id(reset_token) is None
    assert db.peek_verify_token_user_id("no-such-token") is None


def test_mark_email_verified(db):
    user_id = db.create_user("person@example.com", "password123")
    assert db.get_user(user_id).email_verified is False
    db.mark_email_verified(user_id)
    assert db.get_user(user_id).email_verified is True


def test_set_password_updates_hash_and_rejects_short_password(db):
    user_id = db.create_user("person@example.com", "password123")
    db.set_password(user_id, "brand-new-password")
    assert db.authenticate("person@example.com", "brand-new-password") is not None
    assert db.authenticate("person@example.com", "password123") is None
    with pytest.raises(ValueError):
        db.set_password(user_id, "short")


def test_set_password_bumps_session_version(db):
    # session_versionが上がることで、変更前に発行済みのセッションCookieを
    # app.py側で無効化できる(第2回監査 指摘#1への対応)。
    user_id = db.create_user("person@example.com", "password123")
    assert db.get_user(user_id).session_version == 1
    db.set_password(user_id, "brand-new-password")
    assert db.get_user(user_id).session_version == 2
    db.set_password(user_id, "another-new-password")
    assert db.get_user(user_id).session_version == 3


def test_reset_password_with_token_succeeds_and_consumes_token(db):
    user_id = db.create_user("resetme@example.com", "password123")
    token = db.create_email_token(user_id, "reset", ttl_seconds=3600)
    returned_id = db.reset_password_with_token(token, "brand-new-password")
    assert returned_id == user_id
    assert db.authenticate("resetme@example.com", "brand-new-password") is not None
    assert db.authenticate("resetme@example.com", "password123") is None
    # トークンは使用済みになり、同じトークンでの再利用は拒否される。
    assert db.reset_password_with_token(token, "another-password") is None


def test_reset_password_with_token_rejects_invalid_or_wrong_purpose_token(db):
    user_id = db.create_user("resetme2@example.com", "password123")
    verify_token = db.create_email_token(user_id, "verify", ttl_seconds=3600)
    assert db.reset_password_with_token(verify_token, "brand-new-password") is None
    assert db.reset_password_with_token("no-such-token", "brand-new-password") is None
    # 元のパスワードのまま変更されていないこと。
    assert db.authenticate("resetme2@example.com", "password123") is not None


def test_reset_password_with_token_does_not_burn_token_on_invalid_password(db):
    """実際に動かして見つかった不具合の再現・回帰テスト。

    以前の実装(db.consume_email_token()を先に呼んでからdb.set_password()
    を呼ぶ2段階の処理)では、短すぎるパスワードでの再設定リクエストが
    ValueErrorで失敗した時点でトークンは既に使用済みになっており、
    利用者が続けて正しいパスワードで同じリンクを再送信しても
    「リンクが無効、または期限切れです」という誤ったエラーになって
    しまっていた(実際にサーバーを起動しcurlでこの手順を再現して確認)。
    reset_password_with_token()はパスワードの長さチェックを、トークンの
    消費(email_tokens.used_atの更新)より前に行うことで、検証失敗時には
    トークンが一切消費されないようにしている。このテストは、その順序が
    再び壊れて「先に消費してから検証する」実装に戻ってしまった場合に
    確実に失敗するように、失敗後の同一トークンでの再試行が成功することを
    直接確認する。
    """
    user_id = db.create_user("resetme3@example.com", "password123")
    token = db.create_email_token(user_id, "reset", ttl_seconds=3600)

    # 1回目: 短すぎるパスワードで失敗する。
    with pytest.raises(ValueError):
        db.reset_password_with_token(token, "short")

    # 2回目: 同じトークンで、今度は有効なパスワードを送ると成功するはず
    # (トークンが1回目の失敗で消費されていれば、ここはNoneになってしまう)。
    returned_id = db.reset_password_with_token(token, "valid-new-password")
    assert returned_id == user_id
    assert db.authenticate("resetme3@example.com", "valid-new-password") is not None
    assert db.authenticate("resetme3@example.com", "password123") is None


def test_reset_password_with_token_rejects_expired_token(db):
    user_id = db.create_user("resetme4@example.com", "password123")
    token = db.create_email_token(user_id, "reset", ttl_seconds=-1)  # 発行直後から期限切れ
    assert db.reset_password_with_token(token, "brand-new-password") is None
    assert db.authenticate("resetme4@example.com", "password123") is not None


def test_apply_billing_event_applies_first_event(db):
    user_id = db.create_user("billing1@example.com", "password123")
    applied = db.apply_billing_event(
        user_id, 1000.0, "pro", stripe_customer_id="cus_1", stripe_subscription_id="sub_1"
    )
    assert applied is True
    user = db.get_user(user_id)
    assert user.plan == "pro"
    assert user.stripe_customer_id == "cus_1"
    assert user.stripe_subscription_id == "sub_1"
    assert user.last_billing_event_at == 1000.0


def test_apply_billing_event_ignores_unknown_user(db):
    assert db.apply_billing_event(999999, 1000.0, "pro") is False


def test_apply_billing_event_rejects_stale_out_of_order_event(db):
    """実際に本物のstripeライブラリ・本物のHMAC署名でWebhookイベントを構築し、
    サーバへ実際にHTTPリクエストとして送って再現・確認した実バグの回帰テスト。

    Stripe公式ドキュメントは「Webhookイベントの配信順序は保証されない」と
    明記している。実際に、生成時刻t1の"past_due"(支払い失敗)イベントより
    後に生成された、生成時刻t2(>t1)の"active"(リトライ成功)イベントを
    *先に*サーバへ届け、その後で古い"past_due"イベントを届ける
    (=何らかの理由での再送・配信遅延を想定)、という手順を実際に
    `/billing/webhook`へcurlで送って再現した。以前は`app.py`がイベントの
    `created`を一切見ずに受信した順にそのまま`db.set_plan()`を呼んでいた
    ため、直近の実際の状態は"active"(pro)であるにもかかわらず、後から
    届いた古い"past_due"イベントによってplanが"free"に巻き戻され、そのまま
    固定されてしまっていた。このテストは、その巻き戻りが起きないことを
    `apply_billing_event`単体で直接確認する。
    """
    user_id = db.create_user("billing2@example.com", "password123")
    db.apply_billing_event(user_id, 500.0, "pro", stripe_customer_id="cus_2", stripe_subscription_id="sub_2")

    t1, t2 = 600.0, 900.0  # t1: 支払い失敗(生成が古い), t2: リトライ成功(生成が新しい)

    # 新しいイベント(active, t2)を先に届ける。
    applied_new = db.apply_billing_event(user_id, t2, "pro")
    assert applied_new is True
    assert db.get_user(user_id).plan == "pro"

    # その後、古いイベント(past_due, t1)が(再送等で)遅れて届く。
    applied_stale = db.apply_billing_event(user_id, t1, "free")
    assert applied_stale is False  # 古いイベントとして無視されたことが分かる
    # 巻き戻らず、実際の最新状態(pro)のまま維持されていること。
    user = db.get_user(user_id)
    assert user.plan == "pro"
    assert user.last_billing_event_at == t2  # 古いイベントのt1では上書きされていない


def test_apply_billing_event_applies_events_in_correct_chronological_order(db):
    # 逆に、正しい順序(t1→t2)で届いた場合は最新のt2の内容が正しく反映される。
    user_id = db.create_user("billing3@example.com", "password123")
    db.apply_billing_event(user_id, 500.0, "pro")

    t1, t2 = 600.0, 900.0
    assert db.apply_billing_event(user_id, t1, "free") is True
    assert db.get_user(user_id).plan == "free"
    assert db.apply_billing_event(user_id, t2, "pro") is True
    assert db.get_user(user_id).plan == "pro"


def test_apply_billing_event_preserves_existing_stripe_ids_when_not_provided(db):
    user_id = db.create_user("billing4@example.com", "password123")
    db.apply_billing_event(
        user_id, 100.0, "pro", stripe_customer_id="cus_keep", stripe_subscription_id="sub_keep"
    )
    # customer.subscription.updated/deletedはstripe_customer_id等を渡さない
    # (checkout.session.completedでのみ渡る)ため、既存の値が消えないこと。
    db.apply_billing_event(user_id, 200.0, "free")
    user = db.get_user(user_id)
    assert user.plan == "free"
    assert user.stripe_customer_id == "cus_keep"
    assert user.stripe_subscription_id == "sub_keep"


def test_seconds_since_last_token_tracks_most_recent_issue(db):
    user_id = db.create_user("person@example.com", "password123")
    assert db.seconds_since_last_token(user_id, "reset") is None
    db.create_email_token(user_id, "reset", ttl_seconds=3600)
    elapsed = db.seconds_since_last_token(user_id, "reset")
    assert elapsed is not None and elapsed >= 0
    # 別のpurposeには影響しない。
    assert db.seconds_since_last_token(user_id, "verify") is None


def test_migrate_tolerates_concurrent_duplicate_column_attempts(tmp_path):
    # 複数ワーカーが同時に同じ新規DBファイルに対してStoreを構築しても
    # (=それぞれが_migrate()でALTER TABLEを試みても)、後発側が
    # "duplicate column name" エラーで落ちないことを確認する
    # (第2回監査 指摘#2: 以前は無条件にconn.execute(ddl)していたため、
    # 2プロセス目が必ずクラッシュしていた)。
    db_path = str(tmp_path / "concurrent.db")
    first = store_module.Store(db_path)
    user_id = first.create_user("person@example.com", "password123")
    # 2回目のStore()構築が、1回目が既に追加した列に対してもう一度
    # ALTER TABLEしようとする状況を再現する。例外にならず、データも壊れない。
    second = store_module.Store(db_path)
    user = second.get_user(user_id)
    assert user is not None
    assert user.session_version == 1
    assert user.email_verified is False


def test_stripe_ids_round_trip(db):
    user_id = db.create_user("person@example.com", "password123")
    db.set_stripe_ids(user_id, "cus_1", "sub_1")
    user = db.get_user(user_id)
    assert user.stripe_customer_id == "cus_1"
    assert user.stripe_subscription_id == "sub_1"
    assert db.get_user_by_stripe_customer_id("cus_1").id == user_id


def test_list_jobs_for_owner_orders_newest_first(db):
    db.record_job("job-a", "user:1", part_count=3, waste_ratio=0.2)
    time.sleep(0.01)
    db.record_job("job-b", "user:1", part_count=5, waste_ratio=0.1)
    jobs = db.list_jobs_for_owner("user:1")
    assert [j["job_id"] for j in jobs] == ["job-b", "job-a"]
    assert jobs[0]["part_count"] == 5


def test_list_jobs_for_owner_only_returns_own_jobs(db):
    db.record_job("job-a", "user:1")
    db.record_job("job-b", "user:2")
    jobs = db.list_jobs_for_owner("user:1")
    assert [j["job_id"] for j in jobs] == ["job-a"]


def test_measurement_profile_round_trip(db):
    user_id = db.create_user("person@example.com", "password123")
    profile_id = db.create_measurement_profile(
        user_id, "田中様", bust=84, waist=68, hip=92, height=160,
        sleeve_length=54, shoulder_width=37,
    )
    profile = db.get_measurement_profile(profile_id, user_id)
    assert profile["name"] == "田中様"
    assert profile["bust"] == 84
    assert profile["shoulder_width"] == 37


def test_measurement_profile_rejects_blank_name(db):
    user_id = db.create_user("person@example.com", "password123")
    with pytest.raises(ValueError):
        db.create_measurement_profile(
            user_id, "   ", bust=84, waist=68, hip=92, height=160,
            sleeve_length=54, shoulder_width=37,
        )


def test_list_measurement_profiles_orders_newest_first_and_scoped_to_user(db):
    user_a = db.create_user("a@example.com", "password123")
    user_b = db.create_user("b@example.com", "password123")
    db.create_measurement_profile(user_a, "1人目", bust=84, waist=68, hip=92, height=160,
                                   sleeve_length=54, shoulder_width=37)
    time.sleep(0.01)
    db.create_measurement_profile(user_a, "2人目", bust=90, waist=72, hip=96, height=165,
                                   sleeve_length=56, shoulder_width=39)
    db.create_measurement_profile(user_b, "他人のプロフィール", bust=80, waist=64, hip=88, height=155,
                                   sleeve_length=50, shoulder_width=35)

    profiles = db.list_measurement_profiles(user_a)
    assert [p["name"] for p in profiles] == ["2人目", "1人目"]


def test_get_measurement_profile_does_not_leak_other_users_profile(db):
    user_a = db.create_user("a@example.com", "password123")
    user_b = db.create_user("b@example.com", "password123")
    profile_id = db.create_measurement_profile(user_a, "本人用", bust=84, waist=68, hip=92, height=160,
                                                 sleeve_length=54, shoulder_width=37)
    assert db.get_measurement_profile(profile_id, user_b) is None


def test_delete_measurement_profile_only_deletes_own_profile(db):
    user_a = db.create_user("a@example.com", "password123")
    user_b = db.create_user("b@example.com", "password123")
    profile_id = db.create_measurement_profile(user_a, "本人用", bust=84, waist=68, hip=92, height=160,
                                                 sleeve_length=54, shoulder_width=37)

    assert db.delete_measurement_profile(profile_id, user_b) is False
    assert db.get_measurement_profile(profile_id, user_a) is not None

    assert db.delete_measurement_profile(profile_id, user_a) is True
    assert db.get_measurement_profile(profile_id, user_a) is None


def test_measurement_profile_limit_per_user_is_enforced(db, monkeypatch):
    monkeypatch.setattr(store_module, "MAX_MEASUREMENT_PROFILES_PER_USER", 2)
    user_id = db.create_user("person@example.com", "password123")
    db.create_measurement_profile(user_id, "1人目", bust=84, waist=68, hip=92, height=160,
                                   sleeve_length=54, shoulder_width=37)
    db.create_measurement_profile(user_id, "2人目", bust=84, waist=68, hip=92, height=160,
                                   sleeve_length=54, shoulder_width=37)
    with pytest.raises(ValueError):
        db.create_measurement_profile(user_id, "3人目", bust=84, waist=68, hip=92, height=160,
                                       sleeve_length=54, shoulder_width=37)


def test_ping_succeeds_against_a_healthy_database(db):
    db.ping()  # 例外を投げなければOK


# -- round8で追加: APIキー ------------------------------------------------

def test_create_and_authenticate_api_key(db):
    user_id = db.create_user("apikey@example.com", "password123")
    key_id, raw_key = db.create_api_key(user_id, "本番用")
    assert raw_key.startswith(store_module.Store.API_KEY_PREFIX)
    user = db.authenticate_api_key(raw_key)
    assert user is not None
    assert user.id == user_id

    keys = db.list_api_keys(user_id)
    assert len(keys) == 1
    assert keys[0]["id"] == key_id
    assert keys[0]["name"] == "本番用"
    # 生の鍵の値やハッシュは一覧に含まれない(store.pyのlist_api_keys参照)。
    assert "key_hash" not in keys[0]
    assert keys[0]["last_used_at"] is not None  # authenticate_api_keyが更新した


def test_authenticate_api_key_rejects_unknown_or_malformed_keys(db):
    assert db.authenticate_api_key("") is None
    assert db.authenticate_api_key("totally-not-a-key") is None
    assert db.authenticate_api_key("pf_live_doesnotexist") is None


def test_revoke_api_key_prevents_further_authentication(db):
    user_id = db.create_user("revoke@example.com", "password123")
    key_id, raw_key = db.create_api_key(user_id, "テストキー")
    assert db.authenticate_api_key(raw_key) is not None
    assert db.revoke_api_key(key_id, user_id) is True
    assert db.authenticate_api_key(raw_key) is None
    # 二重失効はFalse(既に失効済み)
    assert db.revoke_api_key(key_id, user_id) is False


def test_revoke_api_key_cannot_revoke_someone_elses_key(db):
    owner_id = db.create_user("owner@example.com", "password123")
    other_id = db.create_user("other@example.com", "password123")
    key_id, raw_key = db.create_api_key(owner_id, "テストキー")
    assert db.revoke_api_key(key_id, other_id) is False
    assert db.authenticate_api_key(raw_key) is not None  # 失効していない


def test_create_api_key_enforces_per_user_limit(db):
    user_id = db.create_user("limit@example.com", "password123")
    for i in range(store_module.Store.MAX_API_KEYS_PER_USER):
        db.create_api_key(user_id, f"key{i}")
    with pytest.raises(ValueError):
        db.create_api_key(user_id, "one too many")


# -- round8で追加: 組織アカウント -----------------------------------------

def test_create_organization_and_get_org_for_user(db):
    owner_id = db.create_user("orgowner@example.com", "password123")
    org_id = db.create_organization(owner_id, "テスト株式会社")
    org = db.get_org_for_user(owner_id)
    assert org is not None
    assert org["id"] == org_id
    assert org["name"] == "テスト株式会社"
    assert org["role"] == "owner"
    assert org["plan"] == "free"


def test_a_user_cannot_belong_to_two_organizations(db):
    # 1ユーザー1組織の制約(store.pyの「組織アカウント」節、スコープの限界
    # 参照)。オーナーとして2つ目の組織を作ろうとしても、既存メンバーとして
    # 招待を受諾しようとしても拒否されることの両方を確認する。
    user_id = db.create_user("onlyone@example.com", "password123")
    db.create_organization(user_id, "組織A")
    with pytest.raises(ValueError):
        db.create_organization(user_id, "組織B")

    other_owner_id = db.create_user("otherowner@example.com", "password123")
    org_b_id = db.create_organization(other_owner_id, "組織B")
    token = db.create_org_invite(org_b_id, "onlyone@example.com", other_owner_id)
    with pytest.raises(ValueError):
        db.accept_org_invite(token, user_id)


def test_org_invite_accept_requires_matching_email(db):
    owner_id = db.create_user("inviter@example.com", "password123")
    org_id = db.create_organization(owner_id, "招待テスト組織")
    invited_user_id = db.create_user("invited@example.com", "password123")
    someone_else_id = db.create_user("someoneelse@example.com", "password123")

    token = db.create_org_invite(org_id, "invited@example.com", owner_id)
    # 招待先と違うメールアドレスのユーザーは受諾できない(招待メールが
    # 誤って転送された場合等の想定。store.Store.accept_org_inviteのdocstring参照)。
    assert db.accept_org_invite(token, someone_else_id) is None
    # 本人は受諾できる。
    assert db.accept_org_invite(token, invited_user_id) == org_id
    # 一度使った招待は再利用できない。
    yet_another_id = db.create_user("yetanother@example.com", "password123")
    assert db.accept_org_invite(token, yet_another_id) is None


def test_org_invite_expires(db):
    # accept_org_inviteは現在時刻(time.time())を基準に有効期限を判定する
    # ため、monkeypatchでtime.time()自体を差し替える代わりに、
    # 発行済みトークンのexpires_atを直接過去の時刻に書き換えることで
    # 「期限切れの招待」を再現する。
    owner_id = db.create_user("expireowner@example.com", "password123")
    org_id = db.create_organization(owner_id, "期限切れテスト組織")
    invited_id = db.create_user("expireinvited@example.com", "password123")
    token = db.create_org_invite(org_id, "expireinvited@example.com", owner_id)

    with closing(db._connect()) as conn:
        conn.execute("UPDATE org_invites SET expires_at=? WHERE token=?", (time.time() - 1, token))
        conn.commit()

    assert db.accept_org_invite(token, invited_id) is None
    assert db.get_org_for_user(invited_id) is None


def test_disband_organization_only_by_owner_and_removes_all_members(db):
    owner_id = db.create_user("disbandowner@example.com", "password123")
    org_id = db.create_organization(owner_id, "解散テスト組織")
    member_id = db.create_user("disbandmember@example.com", "password123")
    token = db.create_org_invite(org_id, "disbandmember@example.com", owner_id)
    db.accept_org_invite(token, member_id)

    with pytest.raises(ValueError):
        db.disband_organization(org_id, member_id)  # オーナー以外は解散できない

    assert db.disband_organization(org_id, owner_id) is True
    assert db.get_org_for_user(owner_id) is None
    assert db.get_org_for_user(member_id) is None
    # 解散後は同じユーザーが新しい組織を作れる(1ユーザー1組織の制約が解けている)。
    db.create_organization(owner_id, "新しい組織")


def test_remove_org_member_cannot_remove_the_owner(db):
    owner_id = db.create_user("keepowner@example.com", "password123")
    org_id = db.create_organization(owner_id, "オーナー保護テスト組織")
    assert db.remove_org_member(org_id, owner_id) is False
    assert db.get_org_for_user(owner_id) is not None


# -- round8で追加: 生成履歴からの再生成 ------------------------------------

def test_record_job_with_spec_json_and_regeneration_spec_roundtrip(db):
    owner_key = "user:1"
    spec = {"mode": "manual", "measurements": {"bust": 84}, "garment_spec": {"neckline": "round_neck"}}
    db.record_job("abc123", owner_key, part_count=3, waste_ratio=0.1, spec_json=json.dumps(spec))
    fetched = db.get_job_regeneration_spec("abc123", owner_key)
    assert fetched == spec


def test_get_job_regeneration_spec_returns_none_for_wrong_owner(db):
    db.record_job("job1", "user:1", spec_json=json.dumps({"mode": "manual"}))
    assert db.get_job_regeneration_spec("job1", "user:2") is None


def test_get_job_regeneration_spec_returns_none_when_not_stored(db):
    # イラストモードの生成等、spec_jsonを保存しなかったジョブ(honest limitation)。
    db.record_job("job2", "user:1")
    assert db.get_job_regeneration_spec("job2", "user:1") is None


def test_list_jobs_for_owner_exposes_can_regenerate_flag(db):
    db.record_job("regenerable", "user:1", spec_json=json.dumps({"mode": "manual"}))
    db.record_job("not-regenerable", "user:1")
    jobs = {j["job_id"]: j for j in db.list_jobs_for_owner("user:1")}
    assert jobs["regenerable"]["can_regenerate"] is True
    assert jobs["not-regenerable"]["can_regenerate"] is False


# -- round8で追加: アカウント削除・データエクスポート ----------------------

def test_export_user_data_contains_expected_sections(db):
    user_id = db.create_user("export@example.com", "password123")
    db.create_measurement_profile(user_id, "顧客A", 84, 68, 92, 160, 54, 37)
    db.record_job("exportjob", f"user:{user_id}", part_count=5, waste_ratio=0.2,
                  spec_json=json.dumps({"mode": "manual"}))
    db.create_api_key(user_id, "エクスポート確認用キー")

    data = db.export_user_data(user_id)
    assert data["account"]["email"] == "export@example.com"
    assert len(data["measurement_profiles"]) == 1
    assert len(data["generation_history"]) == 1
    assert len(data["api_keys"]) == 1
    assert "key_hash" not in data["api_keys"][0]
    assert data["organization"] is None


def test_export_user_data_returns_none_for_unknown_user(db):
    assert db.export_user_data(999999) is None


def test_delete_user_account_removes_all_related_data(db):
    user_id = db.create_user("deleteme@example.com", "password123")
    db.create_measurement_profile(user_id, "顧客B", 84, 68, 92, 160, 54, 37)
    db.record_job("deletejob", f"user:{user_id}")
    key_id, _raw = db.create_api_key(user_id, "削除確認用")
    db.check_and_increment_usage(f"user:{user_id}", 10, "2024-01-01")

    assert db.delete_user_account(user_id) is True

    assert db.get_user(user_id) is None
    assert db.list_measurement_profiles(user_id) == []
    assert db.get_job_owner("deletejob") is None
    assert db.usage_today(f"user:{user_id}", "2024-01-01") == 0
    assert db.list_api_keys(user_id) == []  # user_idでの照会自体は空リストを返す


def test_delete_user_account_returns_false_for_unknown_user(db):
    assert db.delete_user_account(999999) is False


def test_delete_user_account_refuses_when_org_owner_has_other_members(db):
    owner_id = db.create_user("orgdeleteowner@example.com", "password123")
    org_id = db.create_organization(owner_id, "削除拒否テスト組織")
    member_id = db.create_user("orgdeletemember@example.com", "password123")
    token = db.create_org_invite(org_id, "orgdeletemember@example.com", owner_id)
    db.accept_org_invite(token, member_id)

    with pytest.raises(ValueError):
        db.delete_user_account(owner_id)
    # 削除は実行されていない(ロールバックされている)ことを確認する。
    assert db.get_user(owner_id) is not None
    assert db.get_org_for_user(owner_id) is not None


def test_delete_user_account_as_sole_org_owner_also_removes_the_organization(db):
    owner_id = db.create_user("soleowner@example.com", "password123")
    org_id = db.create_organization(owner_id, "単独オーナー組織")
    assert db.delete_user_account(owner_id) is True
    assert db.get_organization(org_id) is None


def test_ping_raises_when_database_file_is_corrupted(tmp_path):
    # /healthzで実際にDB破損を検知できることの回帰テスト(app.pyのhealthz
    # 参照)。実際にpatternforge.dbをSQLite形式ではないテキストファイルに
    # 置き換えた状態でサーバーを起動し、/healthzが常に200を返し続けて
    # しまう実バグを見つけて修正した。ping()はこの「DBに実際に到達できる
    # か」を確認する役割そのものなので、壊れたファイルに対しては例外を
    # 伝播させる(黒塗りせず呼び出し元で捕捉させる)ことを直接検証する。
    db_path = tmp_path / "corrupted.db"
    db_path.write_text("これはSQLiteファイルではありません", encoding="utf-8")
    corrupted_db = store_module.Store.__new__(store_module.Store)
    corrupted_db.db_path = str(db_path)
    with pytest.raises(Exception):
        corrupted_db.ping()
