"""audit_measure_guide.py — 採寸中に「測り方」が本当に見えているかを測る。round64で追加。

【なぜ要るか】round34は採寸図と測り方の文を用意し、狭い画面では図を
採寸欄の下へ移すところまでやった。それでも round64 で実際にスマホ幅で
使ってみると、**6つの必須採寸欄のどれにフォーカスしても、図も文も
見えている高さが0px**だった。図そのものが390px幅で523pxあり、文は
さらにその下にあるためである。

「置いた」ことと「見えている」ことは別なので、置いた場所ではなく
**見えている高さ**を測る。

    python3 app.py &
    python3 scripts/audit_measure_guide.py --base http://127.0.0.1:5000

見る画面の大きさ:

    390x844   iPhone 14 相当。キーボードを出していない状態。
    390x508   同じ端末で**ソフトキーボードを出した**状態。数値を打つので
              採寸中はほぼこちら。844 - 336(キーボードの高さの実測相当)。
    1440x900  広い画面。ここでは図の説明(measure-caption)が見えていれば
              よく、欄の下の案内は出さない(二重になる)。

判定:
  * 狭い画面で、どれか1欄でも案内の見えている高さが0pxなら **落とす**。
  * 広い画面で、図の説明が0pxなら **落とす**。
  * 広い画面で欄の下の案内が出ていたら **落とす**(二重表示)。

見えている高さが「案内の全体」に届かない欄は、警告として数字を出す。
キーボードを出した状態では、いちばん上の行(バスト・ウエスト)の案内は
3行ぶん下にあるので最後まで入りきらないことがある——これは
**隠れている**のではなく、指1本ぶんスクロールすれば読める状態である。
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from playwright.async_api import async_playwright

#: 案内を出す対象(`.grid-measurements` の必須6項目)。
FIELDS = ("bust", "waist", "hip", "height", "sleeve_length", "shoulder_width")

#: (幅, 高さ, 説明, 狭い画面か)
VIEWPORTS = (
    (390, 844, "スマホ(キーボード無し)", True),
    (390, 508, "スマホ(キーボードあり)", True),
    (1440, 900, "広い画面", False),
)

MEASURE_JS = r"""
(field) => {
  const vh = window.innerHeight;
  const visible = (r) =>
    Math.round(Math.max(0, Math.min(r.bottom, vh) - Math.max(r.top, 0)));
  const box = document.getElementById("measure-inline-guide");
  const fig = document.getElementById("measure-figure");
  const cap = fig ? fig.querySelector(".measure-caption") : null;
  const input = document.getElementById("field-" + field);
  const shown = box && !box.classList.contains("hidden")
                && getComputedStyle(box).display !== "none";
  const br = box.getBoundingClientRect();
  const cr = cap.getBoundingClientRect();
  return {
    field,
    guideShown: !!shown,
    guideVisible: shown ? visible(br) : 0,
    guideHeight: shown ? Math.round(br.height) : 0,
    captionVisible: visible(cr),
    captionHeight: Math.round(cr.height),
    describedby: input ? input.getAttribute("aria-describedby") : null,
    horizontalOverflow:
      document.documentElement.scrollWidth > window.innerWidth,
  };
}
"""


async def _look(browser, base: str, width: int, height: int, narrow: bool):
    page = await browser.new_page(viewport={"width": width, "height": height})
    await page.goto(base, wait_until="networkidle")
    rows = []
    for field in FIELDS:
        # 実機では、欄を触るとブラウザがその欄を見える位置へ運んでくる。
        # 中央へ寄せるのがいちばん近い(端に貼り付けると実機より甘くなる)。
        await page.evaluate(
            "(f) => { const i = document.getElementById('field-' + f);"
            " i.scrollIntoView({block: 'center'}); i.focus(); }", field)
        await page.wait_for_timeout(120)
        rows.append(await page.evaluate(MEASURE_JS, field))
    await page.close()
    return rows


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:5000")
    base = parser.parse_args().base.rstrip("/") + "/"
    print(f"接続先: {base}")

    failures: list[str] = []
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(args=["--no-sandbox"])
        for width, height, label, narrow in VIEWPORTS:
            rows = await _look(browser, base, width, height, narrow)
            print(f"\n=== {label} {width}x{height} ===")
            for r in rows:
                if narrow:
                    state = "出ていない" if not r["guideShown"] else (
                        "全部見える" if r["guideVisible"] >= r["guideHeight"] - 1
                        else f"途中まで({r['guideVisible']}/{r['guideHeight']}px)")
                    print(f"  {r['field']:<15} 欄の下の案内 "
                          f"{r['guideVisible']:>4}px / {r['guideHeight']:>4}px  {state}"
                          f"   図の説明 {r['captionVisible']:>4}px")
                    if not r["guideShown"] or r["guideVisible"] <= 0:
                        failures.append(
                            f"{label}: {r['field']} の測り方が見えていません"
                            f"(案内 {r['guideVisible']}px / 図の説明 "
                            f"{r['captionVisible']}px)")
                    elif r["describedby"] != "measure-inline-guide":
                        failures.append(
                            f"{label}: {r['field']} に aria-describedby が"
                            f"付いていません({r['describedby']!r})")
                else:
                    print(f"  {r['field']:<15} 図の説明 {r['captionVisible']:>4}px"
                          f" / {r['captionHeight']:>4}px"
                          f"   欄の下の案内 {'出ている' if r['guideShown'] else '出さない'}")
                    if r["captionVisible"] <= 0:
                        failures.append(
                            f"{label}: {r['field']} で図の説明が見えていません")
                    if r["guideShown"]:
                        failures.append(
                            f"{label}: {r['field']} で案内が二重に出ています")
                    # 広い画面では案内をCSSで隠している。読み上げの
                    # aria-describedby が**隠れた要素**を指したままだと、
                    # 画面には出ていないのに読み上げだけ二重になる。
                    if r["describedby"]:
                        failures.append(
                            f"{label}: {r['field']} の aria-describedby が"
                            f"隠れている案内を指しています({r['describedby']!r})")
                if r["horizontalOverflow"]:
                    failures.append(f"{label}: {r['field']} で横にはみ出しています")
        await browser.close()

    print()
    if failures:
        print(f"不足 {len(failures)}件:")
        for line in failures:
            print("  -", line)
        return 1
    print("すべての採寸欄で、測り方が見えています。")
    return 0


sys.exit(asyncio.run(main()))
