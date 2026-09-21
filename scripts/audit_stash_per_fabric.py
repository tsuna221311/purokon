#!/usr/bin/env python3
"""手持ち生地の判定が、生地ごとに画面へ出ているかを実ブラウザで確かめる(round55)。

pytestからはJavaScriptを動かせないので、「app.jsに文字列がある」ことしか
見られない。実際に描かれたかはブラウザで見る。

確かめること:
  1. 生地を分けた生成で、生地ごとの判定が画面に出る
  2. その内容がAPIの`stash_verdicts_by_fabric`と一致する
     (足りる/足りないと、必要な長さ)
  3. 390px幅でも横スクロールを生まない / JSエラーが出ない

【なぜ要るか — round55の実害】
手持ちの端切れは1種類の生地なのに、全パーツを1枚に詰めた長さで判定して
いた。「白い身頃＋紺のスカート」の紺だけを110×130cm持っている人に
「117cm足りません」と答えていた——紺のぶんは124cmで、実際には収まって
いた。持っている生地を使わせ損ねる、いちばん困る間違え方である。

使い方:
    python3 scripts/audit_stash_per_fabric.py --base http://127.0.0.1:5075
"""

import argparse
import asyncio
import re
import sys


MEASUREMENTS = [("bust", "84"), ("waist", "68"), ("hip", "92"), ("height", "160"),
                ("sleeve_length", "54"), ("shoulder_width", "37")]


async def _check(base: str, width: int) -> list[str]:
    from playwright.async_api import async_playwright

    problems: list[str] = []
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(args=["--no-sandbox"])
        page = await browser.new_page(viewport={"width": width, "height": 900})
        errors: list[str] = []
        page.on("pageerror", lambda exc: errors.append(str(exc)))
        page.on("console",
                lambda msg: errors.append("console: " + msg.text) if msg.type == "error" else None)

        api: dict = {}

        async def capture(response):
            if "/api/generate" in response.url:
                try:
                    api.update(await response.json())
                except Exception:  # pragma: no cover - 応答がJSONでない場合
                    pass

        page.on("response", capture)
        await page.goto(base, wait_until="networkidle")
        await page.click("#fabric-group-section > summary")
        await page.fill("#field-fabric-skirt", "紺サテン")
        for name, value in MEASUREMENTS:
            await page.fill(f'[name="{name}"]', value)
        # 手持ち生地の欄は折りたたみの中にある。
        await page.evaluate("""() => {
          const el = document.querySelector('[name="stash_width_cm"]');
          let n = el; while (n) { if (n.tagName === 'DETAILS') n.open = true; n = n.parentElement; }
        }""")
        await page.fill('[name="stash_width_cm"]', "110")
        await page.fill('[name="stash_length_cm"]', "130")
        await page.click('button[type="submit"]')
        await page.wait_for_selector("#result-heading", timeout=120000)

        text = ""
        for _ in range(90):
            text = await page.inner_text("#stash-verdict")
            if text.strip():
                break
            await page.wait_for_timeout(500)

        expected = api.get("stash_verdicts_by_fabric") or []
        if not expected:
            problems.append(f"幅{width}px: APIが生地ごとの判定を返していません")
        elif not text.strip():
            problems.append(f"幅{width}px: 手持ち生地の判定が画面に出ていません")
        else:
            print(f"  幅{width}px:")
            for line in text.strip().splitlines():
                if line.strip():
                    print("    " + line.strip())
            for verdict in expected:
                name = verdict["fabric_name"]
                if name not in text:
                    problems.append(f"幅{width}px: 「{name}」の行が画面にありません")
                    continue
                row = next((l for l in text.splitlines() if l.startswith(name)), "")
                shown = re.search(r"要([\d.]+)cm", row)
                if not shown:
                    problems.append(f"幅{width}px: 「{name}」の必要な長さが読めません: {row!r}")
                elif abs(float(shown.group(1)) - float(verdict["needed_length_cm"])) > 0.05:
                    problems.append(
                        f"幅{width}px: 「{name}」は画面{shown.group(1)}cm / "
                        f"API{verdict['needed_length_cm']}cm——食い違っています")
                fits_on_screen = "足ります" in row
                if fits_on_screen != bool(verdict["fits"]):
                    problems.append(
                        f"幅{width}px: 「{name}」の足りる/足りないが逆です: {row!r}")

        overflow = await page.evaluate(
            "document.documentElement.scrollWidth - document.documentElement.clientWidth")
        if overflow > 0:
            problems.append(f"幅{width}px: 横スクロールが {overflow}px 出ています")
        if errors:
            problems.append(f"幅{width}px: JSエラー {errors}")
        await browser.close()
    return problems


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:5075")
    args = parser.parse_args()

    problems: list[str] = []
    for width in (390, 1440):
        problems.extend(asyncio.run(_check(args.base, width)))

    if problems:
        print("見つかった問題:", len(problems), "件", file=sys.stderr)
        for problem in problems:
            print("  ★", problem, file=sys.stderr)
        return 1
    print("  生地ごとの判定は、どちらの幅でもAPIと同じ内容で出ています。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
