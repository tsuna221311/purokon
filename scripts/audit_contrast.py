"""audit_contrast.py — 実際にレンダリングした画面のコントラスト比を測る。round37で追加。

CSSに書いてある値ではなく、ブラウザで`getComputedStyle`を呼んで
**実際に描かれている色**を見る(親から継承した背景・半透明の重なり込み)。
CSSを読むだけでは、`--muted`のような変数がどの背景の上に載るのかが
分からないので、色付きの箱の中だけ足りていない、という形の不足を見逃す。
round37では実際にそれで3組が見つかった。

判定は WCAG 2.1 AA:
  * SC 1.4.3 通常の文字 4.5:1 / 大きい文字(24px以上、または18.66px以上の太字) 3:1
    https://www.w3.org/WAI/WCAG21/Understanding/contrast-minimum.html
  * 意味を持つ図・UI部品は 3:1 (SC 1.4.11) だが、この台本は文字だけを見る。
    図は tests/test_contrast.py 側で個別に固定している。

使い方:
    python app.py &                       # 先にアプリを起動しておく
    python scripts/audit_contrast.py

`tests/test_contrast.py`は、ここで観測した「どの文字色がどの背景に載るか」の
組を写して、ブラウザ無しで速く回せるようにしたものである。
**配色や画面を足したときは、この台本を動かし直してテスト側へ反映すること。**
"""

import asyncio, json
from playwright.async_api import async_playwright

JS = r"""
() => {
  function parseRGB(s) {
    const m = s.match(/rgba?\(([\d.]+),\s*([\d.]+),\s*([\d.]+)(?:,\s*([\d.]+))?\)/);
    if (!m) return null;
    return [ +m[1], +m[2], +m[3], m[4] === undefined ? 1 : +m[4] ];
  }
  function blend(fg, bg) {           // fgをbgの上に重ねた実効色
    const a = fg[3];
    return [ fg[0]*a + bg[0]*(1-a), fg[1]*a + bg[1]*(1-a), fg[2]*a + bg[2]*(1-a), 1 ];
  }
  function effectiveBg(el) {         // 透明を遡って、実際に見える背景色
    let acc = null;
    let node = el;
    while (node && node.nodeType === 1) {
      const c = parseRGB(getComputedStyle(node).backgroundColor);
      if (c && c[3] > 0) acc = acc === null ? c : blend(acc, c);
      if (acc && acc[3] >= 1) return acc;
      node = node.parentElement;
    }
    return acc && acc[3] >= 1 ? acc : [255,255,255,1];   // 最終的には白の紙
  }
  function lum(c) {
    const f = v => { v /= 255; return v <= 0.03928 ? v/12.92 : Math.pow((v+0.055)/1.055, 2.4); };
    return 0.2126*f(c[0]) + 0.7152*f(c[1]) + 0.0722*f(c[2]);
  }
  const out = [];
  const seen = new Set();
  document.querySelectorAll('*').forEach(el => {
    if (!el.offsetParent && getComputedStyle(el).position !== 'fixed') return;
    // 直接の子テキストを持つ要素だけを見る(親に文字色を継承させない)
    const own = Array.from(el.childNodes)
      .filter(n => n.nodeType === 3 && n.textContent.trim())
      .map(n => n.textContent.trim()).join(' ');
    if (!own) return;
    const cs = getComputedStyle(el);
    if (cs.visibility === 'hidden' || +cs.opacity === 0) return;
    const fgRaw = parseRGB(cs.color);
    if (!fgRaw) return;
    const bg = effectiveBg(el);
    const fg = fgRaw[3] < 1 ? blend(fgRaw, bg) : fgRaw;
    const L1 = lum(fg), L2 = lum(bg);
    const ratio = (Math.max(L1,L2) + 0.05) / (Math.min(L1,L2) + 0.05);
    const px = parseFloat(cs.fontSize);
    const weight = parseInt(cs.fontWeight, 10) || 400;
    const large = px >= 24 || (px >= 18.66 && weight >= 700);
    const need = large ? 3.0 : 4.5;
    const key = cs.color + '|' + bg.join(',') + '|' + px + '|' + weight;
    if (seen.has(key)) return;
    seen.add(key);
    out.push({
      text: own.slice(0, 45), tag: el.tagName.toLowerCase(),
      cls: (el.className && el.className.toString().slice(0,40)) || '',
      id: el.id || '', color: cs.color,
      bg: 'rgb(' + bg.slice(0,3).map(v=>Math.round(v)).join(',') + ')',
      px, weight, large, ratio: Math.round(ratio*100)/100, need,
      pass: ratio >= need,
    });
  });
  return out;
}
"""

async def audit(pg, label, results):
    rows = await pg.evaluate(JS)
    fails = [r for r in rows if not r["pass"]]
    results.append((label, len(rows), fails))

# round53: 接続先を引数で指定できるようにした。
#
# それまで "http://127.0.0.1:5000/" が4か所に直接書いてあり、`--base` を
# 付けても**黙って無視して5000番を見ていた**。round53に実際にやらかした:
# 5075番で動かした新しいビルドを調べたつもりで、5000番に残っていた
# 古いサーバーの画面を測って「問題なし」と書きかけた。
# round70: OSの「暗い画面」設定にも追従するようになったので、**両方**測る。
#
# 明るい側だけ測っていると、暗い側は誰も見ていないのと同じである。実際に
# round70で、色を16進で直接書いていた注記(濃い茶色の文字)が暗い地に
# そのまま乗っていた。`--scheme both` が既定で、明暗の両方を順に測る。
def _args():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:5000")
    parser.add_argument("--scheme", default="both",
                        choices=("light", "dark", "both"))
    ns = parser.parse_args()
    return ns.base.rstrip("/") + "/", ns.scheme


async def sweep(b, base, scheme, results):
    """1つの配色(明/暗)で、画面5通りを測る。"""
    def new_page(**kw):
        return b.new_page(color_scheme=scheme, **kw)

    pg = await new_page(viewport={"width": 1440, "height": 1000})
    await pg.goto(base, wait_until="networkidle")
    await pg.evaluate("()=>{document.querySelectorAll('details').forEach(d=>d.open=true)}")
    await pg.wait_for_timeout(500)
    await audit(pg, f"[{scheme}] 入力画面", results)

    # 警告・注記が出ている状態も見る(赤・青・橙の箱)
    for f, v in [("bust","84"),("waist","68"),("hip","150"),("height","160")]:
        await pg.fill(f"#field-{f}", v)
    await pg.click("label:has(input[name='skirt_style'][value='circle'])")
    await pg.click("button.primary[type=submit]")
    await pg.wait_for_selector("#design-note", timeout=150000)
    await pg.wait_for_timeout(2000)
    await audit(pg, f"[{scheme}] 生成結果(警告・注記あり)", results)

    # --- サイズ展開(赤・青の箱がサイズごとに出る) ---
    pg2 = await new_page(viewport={"width": 1440, "height": 1000})
    await pg2.goto(base, wait_until="networkidle")
    await pg2.check("input[name='mode'][value='multi_size']")
    await pg2.wait_for_timeout(400)
    for f, v in [("bust","100"),("waist","90"),("hip","138"),
                  ("height","165"),("sleeve_length","56"),("shoulder_width","40")]:
        await pg2.fill(f"#field-{f}", v)
    await pg2.click("label:has(input[name='skirt_style'][value='circle'])")
    await pg2.click("label:has(input[name='sleeve_style'][value=''])")
    for v in ("M","L","XL"):
        await pg2.locator(f"input[name='sizes'][value='{v}']").check()
    await pg2.click("button.primary[type=submit]")
    await pg2.wait_for_selector("#multi-size-list .field-box", timeout=180000)
    await pg2.wait_for_timeout(1800)
    await audit(pg2, f"[{scheme}] サイズ展開(警告あり)", results)
    await pg2.close()

    # --- 入力エラーの表示 ---
    pg3 = await new_page(viewport={"width": 1440, "height": 1000})
    await pg3.goto(base, wait_until="networkidle")
    await pg3.evaluate("()=>{document.querySelectorAll('details').forEach(d=>d.open=true)}")
    await pg3.click("#add-custom-panel-btn")   # 輪郭を描かずに送信 -> エラー
    await pg3.wait_for_timeout(300)
    await pg3.click("button.primary[type=submit]")
    await pg3.wait_for_timeout(3000)
    await audit(pg3, f"[{scheme}] 入力エラー表示", results)
    await pg3.close()

    # --- 狭い画面 ---
    pg4 = await new_page(viewport={"width": 390, "height": 900})
    await pg4.goto(base, wait_until="networkidle")
    await pg4.evaluate("()=>{document.querySelectorAll('details').forEach(d=>d.open=true)}")
    # round64: 採寸欄の下に出る測り方(#measure-inline-guide)は、
    # 狭い画面でしか出ない**うえに**フォーカスするまで隠れている。
    # 出しておかないと、この配色は一度も測られない。注意書きのある
    # 肩幅を選ぶと、見出し・本文・注意書きの3色が同時に出る。
    await pg4.focus("#field-shoulder_width")
    # round67: 同時に選べない組み合わせの理由(#zip-princess-conflict)も、
    # 片方を選ぶまで隠れている。出しておかないと一度も測られない
    # (round64の測り方の案内とまったく同じ形)。
    zip_box = pg4.locator("#opt-front-zip")
    if await zip_box.count():
        await zip_box.check()
    await pg4.wait_for_timeout(500)
    await audit(pg4, f"[{scheme}] 390px 入力画面", results)
    await pg4.close()
    await pg.close()


async def main():
    base, scheme = _args()
    schemes = ("light", "dark") if scheme == "both" else (scheme,)
    print(f"接続先: {base} / 配色: {'・'.join(schemes)}")
    results = []
    async with async_playwright() as pw:
        b = await pw.chromium.launch(args=["--no-sandbox"])
        for one in schemes:
            await sweep(b, base, one, results)
        await b.close()

    total_fail = 0
    for label, total, fails in results:
        total_fail += len(fails)
        print(f"\n=== {label}: {total}組を検査 / 不足 {len(fails)}件 ===")
        for r in sorted(fails, key=lambda x: x["ratio"]):
            print(f"  {r['ratio']:5.2f}:1 (要 {r['need']}) {r['px']:.0f}px w{r['weight']} "
                  f"{r['color']} on {r['bg']}")
            print(f"        <{r['tag']} id={r['id']!r} class={r['cls']!r}> {r['text']!r}")
    print(f"\n合計 不足 {total_fail}件")
    return 1 if total_fail else 0

raise SystemExit(asyncio.run(main()))
