"""audit_failure_paths.py — わざと失敗させて、画面に何が出るかを読む。round45で追加。

この製品のテストは長らく「うまくいったとき」しか通っていなかった。
ここでは通信を切る・壊れた応答を返す・応答を返さない、をブラウザの側で
再現して、**利用者の画面に実際に表示された文字**をそのまま書き出す。

round45の実測(直す前):

    通信が切れた    → 「Failed to fetch」
    502(HTMLが返る) → 「Unexpected token '<', "<html><bod"... is not valid JSON」
    応答が来ない     → 60秒待ってもボタンは「生成中です…」のまま disabled

見るもの:

  * 送信ボタンが押せる状態に戻るか(戻らないと、再読み込みしか手が無く、
    再読み込みすると入力した採寸値が全部消える)
  * 画面に出た文言が日本語か
  * 読み上げ領域(round44)に、失敗したことが入るか
  * 連打しても送信が1回に収まるか

使い方:
    python -m flask --app app run --port 5001 &
    python scripts/audit_failure_paths.py --base http://127.0.0.1:5001

`--timeout-ms` を渡すと、待ち時間の上限だけを短い値に差し替えて
(app.jsを配信時に書き換えて)、上限の仕組みそのものを数秒で確かめられる。
既定の2分をそのまま待つ必要は無い。
"""

import argparse
import asyncio
import json
import pathlib
import re

SUBMIT = '#generate-form button[type="submit"]'

SNAP = """() => {
  const q = s => document.querySelector(s);
  const cls = (s, c) => { const e = q(s); return e ? e.classList.contains(c) : null; };
  const btn = q('#generate-form button[type=submit]');
  return {
    ボタンが押せない: btn.disabled,
    ボタンの文字: btn.textContent.trim(),
    エラー文: (q('#form-error')?.textContent || '').trim(),
    読み上げ: (q('#result-status')?.textContent || '').trim(),
    結果が出ている: cls('#result-content', 'hidden') === false,
    バストの入力値: q('#field-bust')?.value,
  };
}"""

# 日本語が1文字も無ければ、利用者に読めない文言が出ている。
_JA = re.compile(r"[ぁ-んァ-ヶ一-龠]")


async def _case(browser, base, name, setup, wait_ms):
    page = await browser.new_page(viewport={"width": 1440, "height": 1200})
    # 差し替えと横取りは**開く前**に登録する。開いた後だと app.js は
    # もう読み込まれてしまっていて、差し替えが効かない
    # (round45でこれを踏み、「上限が効いていない」と誤って読んだ)。
    if setup:
        await setup(page)
    await page.goto(base + "/", wait_until="networkidle")
    await page.click(SUBMIT)
    await page.wait_for_timeout(wait_ms)
    snap = await page.evaluate(SNAP)
    await page.close()
    return name, snap


async def audit(base: str, timeout_ms: int | None) -> list:
    from playwright.async_api import async_playwright

    patched = None
    if timeout_ms:
        src = (pathlib.Path(__file__).resolve().parent.parent
               / "web" / "static" / "app.js").read_text(encoding="utf-8")
        patched = re.sub(r"const GENERATE_TIMEOUT_MS = \d+;",
                         f"const GENERATE_TIMEOUT_MS = {timeout_ms};", src, count=1)

    async def maybe_patch(page):
        if patched:
            # round48: 静的ファイルのURLに版(?v=...)が付くようになったので、
            # 末尾に * を付けないと差し替えが効かない。実際にこれで
            # 「応答が返ってこない」の検査だけが素通りし、直したはずの
            # 上限が効いていないように見えた。
            await page.route("**/static/app.js*", lambda r: r.fulfill(
                status=200, content_type="application/javascript; charset=utf-8",
                body=patched))

    def fulfil(status, content_type, body):
        async def setup(page):
            await maybe_patch(page)
            await page.route("**/api/generate", lambda r: r.fulfill(
                status=status, content_type=content_type, body=body))
        return setup

    async def cut(page):
        await maybe_patch(page)
        await page.route("**/api/generate", lambda r: r.abort())

    async def never_answer(page):
        await maybe_patch(page)

        async def hang(route):
            await asyncio.sleep(600)
        await page.route("**/api/generate", hang)

    cases = [
        ("通信が切れた", cut, 6000),
        ("500 (JSONは返る)", fulfil(500, "application/json",
                                  '{"ok": false, "error": "内部エラーです"}'), 4000),
        ("502 (HTMLが返る)", fulfil(502, "text/html", "<html>Bad Gateway</html>"), 4000),
        ("504 (本文が空)", fulfil(504, "application/json", ""), 4000),
        ("429 (上限)", fulfil(429, "application/json",
                            '{"ok": false, "error": "本日の上限です",'
                            ' "upgrade_url": "/pricing"}'), 4000),
        ("応答が返ってこない", never_answer, (timeout_ms or 120000) + 4000),
    ]

    rows = []
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(args=["--no-sandbox"])
        for name, setup, wait in cases:
            rows.append(await _case(browser, base, name, setup, wait))

        # 連打しても送信は1回に収まるか
        page = await browser.new_page(viewport={"width": 1440, "height": 1200})
        await page.goto(base + "/", wait_until="networkidle")
        await page.evaluate("""() => { window.__n = 0; const f = window.fetch;
            window.fetch = function(...a) {
              if ((a[0] + '').includes('/api/generate')) window.__n++;
              return f.apply(this, a); }; }""")
        for _ in range(6):
            await page.click(SUBMIT, force=True)
            await page.wait_for_timeout(60)
        await page.wait_for_timeout(1200)
        rows.append(("連打6回", {"送信した回数": await page.evaluate("() => window.__n")}))
        await page.close()
        await browser.close()
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:5000")
    parser.add_argument("--timeout-ms", type=int, default=None,
                        help="待ち時間の上限を差し替えて、仕組みだけを短時間で見る")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    rows = asyncio.run(audit(args.base, args.timeout_ms))
    if args.json:
        print(json.dumps(dict(rows), ensure_ascii=False, indent=2))
        return

    problems = 0
    for name, snap in rows:
        print(f"\n【{name}】")
        for key, value in snap.items():
            print(f"   {key}: {value}")
        message = snap.get("エラー文", "")
        if snap.get("ボタンが押せない"):
            print("   ★ 送信ボタンが押せないままです(再読み込みしか手がありません)")
            problems += 1
        if message and not _JA.search(message):
            print("   ★ 日本語でない文言が出ています")
            problems += 1
        if message and "生成しています" in snap.get("読み上げ", ""):
            print("   ★ 失敗したのに、読み上げは「生成中」のままです")
            problems += 1
        if snap.get("送信した回数", 1) > 1:
            print("   ★ 連打で二重に送信されています")
            problems += 1

    print(f"\n見つかった問題: {problems}件")


if __name__ == "__main__":
    main()
