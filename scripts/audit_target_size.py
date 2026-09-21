"""audit_target_size.py — 実際に描かれた「押せる範囲」の大きさを測る。round44で追加。

CSSに書いてある値ではなく、ブラウザで`getBoundingClientRect()`を呼んで
**画面に出ている矩形**を見る。CSSを読むだけでは、
「チェックボックスは13pxだが、囲っている<label>が24pxあるので指では当たる」
という関係が分からない。round44の実測でも、input単体で測ると222件、
labelまで見ると97件と、2倍以上ずれた。

判定は WCAG 2.2 SC 2.5.8 Target Size (Minimum) — Level AA:
    押せる範囲は 24×24 CSS px 以上であること。
    https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum.html

同SCの例外のうち、この台本が当てはめているのは **Inline** だけである:

    文章の流れの中にあるリンク(出典のURL、「アカウントをお持ちでない方は
    〈無料登録〉」など)は対象外。本文の行間まで広げると、かえって読みにくい。

「段落にぽつんと1つだけ置かれたリンク」は文章の中ではないので**対象**に
数える(例: ログイン画面の「パスワードをお忘れですか？」)。

結果パネル(ダウンロードの並び、パーツの一覧)はJSで作られるので、ページを
開いただけでは存在しない。`--after-generate` を付けると、型紙を1回生成して
から測り直す。

使い方:
    python -m flask --app app run --port 5001 &    # 先にアプリを起動
    python scripts/audit_target_size.py --base http://127.0.0.1:5001
    python scripts/audit_target_size.py --base http://127.0.0.1:5001 --after-generate

`tests/test_round44_ui.py`は、ここで見つけた不足に対して当てたCSSの規則が
消えていないことを、ブラウザ無しで確かめるものである。
**画面や部品を足したときは、この台本を動かし直すこと。**
"""

import argparse
import asyncio
import json

MIN_TARGET_PX = 24.0

PAGES = ["/", "/pricing", "/guide", "/signup", "/login", "/terms", "/privacy",
         "/legal", "/forgot-password"]
WIDTHS = [390, 1440]

JS = r"""
(minPx) => {
  const SELECTOR = 'a[href], button, input:not([type=hidden]), select, textarea,'
                 + ' summary, [tabindex]:not([tabindex="-1"])';
  const out = [];
  document.querySelectorAll(SELECTOR).forEach(el => {
    const r = el.getBoundingClientRect();
    if (r.width === 0 || r.height === 0) return;
    const cs = getComputedStyle(el);
    if (cs.visibility === 'hidden' || cs.display === 'none') return;

    // 押せる範囲で測る。input/select が <label> に包まれている場合、
    // 押して反応するのは label なので、そちらの矩形を使う。
    let box = r;
    const label = el.closest('label');
    if (label && (el.tagName === 'INPUT' || el.tagName === 'SELECT')) {
      const lr = label.getBoundingClientRect();
      if (lr.width >= r.width && lr.height >= r.height) box = lr;
    }
    if (box.width >= minPx && box.height >= minPx) return;

    // SC 2.5.8 の Inline 例外: 文章の流れの中にあるリンク。
    // 「段落にリンクが1つだけ」は文章の中ではないので例外にしない。
    let inlineException = false;
    if (el.tagName === 'A') {
      const p = el.closest('p, li, td, h1, h2, h3, h4, figcaption');
      if (p) {
        const onlyChild = p.children.length === 1 && p.children[0] === el
                          && p.textContent.trim() === el.textContent.trim();
        inlineException = !onlyChild;
      }
    }
    out.push({
      tag: el.tagName,
      type: el.getAttribute('type') || '',
      id: el.id || '',
      name: el.getAttribute('name') || '',
      text: (el.textContent || '').trim().slice(0, 30),
      w: Math.round(box.width), h: Math.round(box.height),
      inlineException,
    });
  });
  return out;
}
"""


#: 生成を1回通してから測るときの待ち先。結果パネルはJSで作られるので、
#: ページを開いただけでは存在せず、上のPAGESを回るだけでは測れない。
RESULT_READY = "#result-content:not(.hidden)"
SUBMIT = '#generate-form button[type="submit"]'


async def audit(base: str, after_generate: bool = False) -> list[dict]:
    from playwright.async_api import async_playwright

    rows = []
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(args=["--no-sandbox"])
        for path in PAGES:
            for width in WIDTHS:
                page = await browser.new_page(
                    viewport={"width": width, "height": 900})
                await page.goto(base + path, wait_until="networkidle")
                await page.wait_for_timeout(120)
                for row in await page.evaluate(JS, MIN_TARGET_PX):
                    row["path"] = path
                    row["width"] = width
                    rows.append(row)
                await page.close()

        # round56: カスタムパーツ(マント・翼・装甲プレート)のカードは、
        # 「＋ カスタムパーツを追加」を押すまでDOMに**存在しない**。
        # そのため、この検査はコスプレ向けのいちばん特徴的な画面を
        # 一度も測っていなかった。実測すると、そこに24px未満の
        # 押せる範囲が残っていた(「左右反転パーツも作る」の高さ18px)。
        for width in WIDTHS:
            page = await browser.new_page(viewport={"width": width, "height": 900})
            await page.goto(base + "/", wait_until="networkidle")
            await page.click("#custom-panel-section > summary")
            await page.click("#add-custom-panel-btn")
            await page.wait_for_timeout(300)
            for row in await page.evaluate(JS, MIN_TARGET_PX):
                row["path"] = "/ (カスタムパーツを1つ追加した状態)"
                row["width"] = width
                rows.append(row)
            await page.close()

        if after_generate:
            for width in WIDTHS:
                page = await browser.new_page(
                    viewport={"width": width, "height": 900})
                await page.goto(base + "/", wait_until="networkidle")
                await page.click(SUBMIT)
                # 生成はサーバー側で数十秒かかることがある。
                await page.wait_for_selector(RESULT_READY, timeout=180_000)
                await page.wait_for_timeout(500)
                for row in await page.evaluate(JS, MIN_TARGET_PX):
                    row["path"] = "/ (生成後の結果パネル)"
                    row["width"] = width
                    rows.append(row)
                await page.close()

        await browser.close()
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:5000")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--after-generate", action="store_true",
                        help="型紙を1回生成してから、結果パネルの中も測る")
    args = parser.parse_args()

    rows = asyncio.run(audit(args.base, after_generate=args.after_generate))
    failures = [r for r in rows if not r["inlineException"]]
    exempt = [r for r in rows if r["inlineException"]]

    if args.json:
        print(json.dumps({"failures": failures, "exempt": exempt},
                          ensure_ascii=False, indent=2))
        return 1 if failures else 0

    if failures:
        print(f"WCAG 2.2 SC 2.5.8 (24×24px) を満たさない押せる範囲: {len(failures)}件\n")
        for r in failures:
            label = r["id"] or r["name"] or r["text"]
            print(f"  {r['path']} @{r['width']}px  {r['tag']}{('/' + r['type']) if r['type'] else ''}"
                  f"  {r['w']}×{r['h']}px  {label}")
    else:
        print("WCAG 2.2 SC 2.5.8 (24×24px): 満たさない押せる範囲はありません。")
    print(f"\n文章の中のリンク(Inline例外)として数えなかったもの: {len(exempt)}件")
    # round56: 見つけても終了コード0を返していたので、**自動で回しても
    # 気づけなかった**。他の監査(audit_print_sheets.py等)と同じく、
    # 問題があれば1を返す。
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
