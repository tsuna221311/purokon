#!/usr/bin/env python3
"""説明文をたたむ処理(round32)が、強調を落としていないか実ブラウザで確かめる。

round32で入れた`collapseLongHints()`は、長い`p.hint`を
`<details><summary>一文目</summary><p>残り</p></details>`に作り替える。
このとき中身を`textContent`で入れ直していたため、**元のマークアップが
消えていた**。

round52の実測(1440px, 説明文57件・たたまれたもの17件):

    画面の強調(<strong>)17か所のうち **7か所が失われていた**
      ・上下の向き
      ・それで作れるか
      ・実際に測った余り・不足
      ・足していません          ← 否定の強調が消える
      ・出来上がりの長さ        ← 「裁断線の長さ」と読み違える
      ・縫わずに線の上で切る
      ・0

強調は飾りではなく「ここを読み違えると寸法を間違える」という印なので、
たたんだ時だけ消えるのは開示をやめるのに近い。特に「足していません」の
ような否定文は、強調が無いと肯定と読み違えても気づけない。

使い方:
    python3 scripts/audit_hint_collapse.py --url http://127.0.0.1:5075/

終了コード 1 で「強調が失われている」。
"""

import argparse
import asyncio
import re
import sys
import urllib.request


async def _rendered_emphasis(url: str, width: int) -> list[str]:
    from playwright.async_api import async_playwright

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(args=["--no-sandbox"])
        page = await browser.new_page(viewport={"width": width, "height": 900})
        errors: list[str] = []
        page.on("pageerror", lambda exc: errors.append(str(exc)))
        await page.goto(url, wait_until="networkidle")
        found = await page.evaluate(
            """() => [...document.querySelectorAll("strong")].map(s => s.textContent)"""
        )
        collapsed = await page.evaluate(
            """() => document.querySelectorAll("details.hint-collapsible").length"""
        )
        await browser.close()
    if errors:
        print("JSエラー:", errors, file=sys.stderr)
    print(f"  幅{width}px: たたんだ説明文 {collapsed}件")
    return found


def _source_emphasis(url: str) -> list[str]:
    html = urllib.request.urlopen(url).read().decode("utf-8")
    return re.findall(r"<strong>(.*?)</strong>", html, re.S)


def _normalize(values: list[str]) -> list[str]:
    return [re.sub(r"\s+", "", value) for value in values]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:5075/")
    parser.add_argument("--width", type=int, default=1440)
    args = parser.parse_args()

    before = _normalize(_source_emphasis(args.url))
    after = _normalize(asyncio.run(_rendered_emphasis(args.url, args.width)))

    lost = [value for value in before if value not in after]
    print(f"  サーバの強調 {len(before)}か所 / 表示後 {len(after)}か所")
    if lost:
        print(f"★ たたんだせいで消えた強調が {len(lost)} か所あります:")
        for value in lost:
            print("   ・", value)
        return 1
    print("  強調は全部残っています。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
