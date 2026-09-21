#!/usr/bin/env python3
"""round58: サイズ展開の画面から、作られた型紙が**全部取れる**かを測る。

【なぜこの検査を足したか】サイズ展開の1サイズぶんのダウンロード行は
SVG/PDF/DXFの3本が直書きされていた。裏地・2種類目の生地・まとめPDF・
プロジェクター投影用は、サーバが作って応答にも入れているのに、
画面には出ていなかった。**作ったのに渡していない**ので、pytestでは
見つからない(応答は正しい)。実際に画面を開いて、押せるリンクを
数えるしかない。

使い方:

    python3 scripts/audit_multi_size_downloads.py --base http://127.0.0.1:5075

不足があれば終了コード1で、何が取れないかを並べる。
"""
from __future__ import annotations

import argparse
import sys

from playwright.sync_api import sync_playwright


MEASUREMENTS = {"bust": "84", "waist": "68", "hip": "92",
                 "height": "160", "sleeve_length": "54", "shoulder_width": "37"}


def audit(base: str, headless: bool = True) -> int:
    with sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--no-sandbox"], headless=headless)
        page = browser.new_page(viewport={"width": 1440, "height": 1100})
        # 応答そのものを控えておく(画面側に検査用のコードを足さないため)。
        payloads: list[dict] = []

        def _remember(response):
            if "/api/generate" in response.url and response.status == 200:
                try:
                    payloads.append(response.json())
                except Exception:  # pragma: no cover - JSON以外は無視
                    pass

        page.on("response", _remember)
        page.goto(base, wait_until="networkidle")
        page.click('input[name="mode"][value="multi_size"]')
        page.wait_for_timeout(200)
        for name, value in MEASUREMENTS.items():
            page.fill(f"#field-{name}", value)
        for size in ("S", "M"):
            box = page.query_selector(f'input[name="sizes"][value="{size}"]')
            if box and not box.is_checked():
                box.click()
        for section in page.query_selector_all(".optional-section:not(.hidden)"):
            section.evaluate("e => e.open = true")
        page.wait_for_timeout(200)
        # 裏地あり・生地2種類——コスプレでいちばんありがちな組み合わせ。
        lining = page.query_selector("#field-lining")
        if lining:
            lining.check()
        sleeve_fabric = page.query_selector('input[name="fabric_sleeve"]')
        if sleeve_fabric:
            sleeve_fabric.fill("紺サテン")
        # round58: 手持ちの生地の判定も、サイズごとに出るかを一緒に見る。
        for field, value in (("stash_width_cm", "110"), ("stash_length_cm", "130")):
            box = page.query_selector(f'input[name="{field}"]')
            if box:
                box.fill(value)
        page.click('button[type="submit"]')
        page.wait_for_selector(
            "#multi-size-result-content:not(.hidden), #form-error:not(.hidden)",
            timeout=300_000)
        if not page.query_selector("#form-error.hidden"):
            error = page.inner_text("#form-error").strip()
            if error:
                print(f"生成に失敗しました: {error}")
                browser.close()
                return 1
        page.wait_for_timeout(1500)

        # サーバが返したリンクと、画面に出ているリンクを突き合わせる。
        offered = page.evaluate("""() => {
            const boxes = document.querySelectorAll("#multi-size-list > .field-box");
            return Array.from(boxes).map(b => ({
                heading: b.querySelector("h3").textContent.trim(),
                text: b.innerText,
                hrefs: Array.from(b.querySelectorAll("a[href]"))
                           .map(a => a.getAttribute("href").split("?")[0]),
            }));
        }""")
        browser.close()

    if not payloads:
        print("生成の応答を捉えられませんでした。")
        return 1
    results = payloads[-1].get("results") or {}
    missing_total = 0
    for box in offered:
        size = box["heading"].replace("サイズ", "").strip()
        shown = set(box["hrefs"])
        expected = set((results.get(size) or {}).get("download", {}).values())
        missing = sorted(expected - shown)
        print(f"{box['heading']}: 画面に{len(shown)}本 / 応答に{len(expected)}本")
        for href in missing:
            print(f"    取れない: {href}")
        missing_total += len(missing)
        # 手持ちの判定が、そのサイズの箱に文字として出ているか。
        verdict = (results.get(size) or {}).get("stash_verdict")
        if verdict and "手持ちの生地" not in box["text"]:
            print("    手持ちの判定が画面に出ていません")
            missing_total += 1
    if not offered:
        print("サイズごとの結果が1つも出ていません。")
        return 1
    if missing_total:
        print(f"\n作ったのに画面から取れない型紙: {missing_total}件")
        return 1
    print("\n作った型紙は全部、画面から取れます。")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="http://127.0.0.1:5075")
    parser.add_argument("--headed", action="store_true")
    args = parser.parse_args()
    return audit(args.base, headless=not args.headed)


if __name__ == "__main__":
    sys.exit(main())
