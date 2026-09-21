#!/usr/bin/env python3
"""印刷枚数の案内が、実ブラウザで本当に出ているかを確かめる(round53)。

pytestからはJavaScriptを動かせないので、「app.jsに文字列がある」ことしか
見られない。実際に関数が呼ばれて画面に文字が出たかは、ブラウザで動かす。

確かめること:
  1. 生成後に「A4分割PDFは、実寸の型紙が○枚と…」が画面に出る
  2. その○が、APIが返した`pdf_sheet_count`と同じ数である
  3. 390px幅でも横スクロールを生まない
  4. JSエラーが出ない

使い方:
    python3 scripts/audit_print_sheets.py --base http://127.0.0.1:5075

終了コード 1 で「出ていない/数が違う」。
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
                except Exception:  # pragma: no cover - 応答が JSON でない場合
                    pass

        page.on("response", capture)
        await page.goto(base, wait_until="networkidle")
        for name, value in MEASUREMENTS:
            await page.fill(f'[name="{name}"]', value)
        await page.click('button[type="submit"]')
        await page.wait_for_selector("#result-heading", timeout=90000)

        text = ""
        for _ in range(60):
            text = await page.inner_text("#pdf-sheet-hint")
            if text.strip():
                break
            await page.wait_for_timeout(500)

        if not text.strip():
            problems.append(f"幅{width}px: 印刷枚数の案内が出ていません")
        else:
            print(f"  幅{width}px: {text}")
            shown = re.search(r"型紙が(\d+)枚", text)
            expected = api.get("pdf_sheet_count")
            if not shown:
                problems.append(f"幅{width}px: 枚数が読み取れません: {text!r}")
            elif expected is not None and int(shown.group(1)) != int(expected):
                problems.append(
                    f"幅{width}px: 画面は{shown.group(1)}枚、APIは{expected}枚——食い違っています")

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
    print("  印刷枚数の案内は、どちらの幅でもAPIと同じ数で出ています。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
