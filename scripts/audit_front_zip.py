"""audit_front_zip.py — 前開きファスナーの型紙が「縫えない」と言われないか。round66で追加。

【なぜ要るか】前開きファスナーは、コスプレでいちばんよく使う開き方の1つ
(軍服・制服・変身ヒロインの衣装…)。round65まで、これを選ぶと**必ず**
赤い⚠が出ていた。

    前身頃の脇線の長さ(合計154.5cm)と、後ろ身頃の脇線の長さ(合計70.4cm)が
    84.1cm一致していません。……そのままでは縫えません。

    身頃の首ぐりの長さ(前+後で15.6cm)に対し、衿の首ぐり側の辺が42.4cmで、
    26.8cm一致していません。……そのままでは付けられません。

どちらも**型紙ではなく測り方の誤り**だった(round66のREADME参照)。
「そのままでは縫えません」と言われた型紙を、人は作らない。

この台本は、画面に出た⚠の中身を読む。サーバの応答ではなく、実際に
描かれた文字を見る。あわせて読み上げ用の一文が、画面に出ている⚠と
同じ件数を言っているかも見る(round66でここもずれていた)。

    python3 app.py &
    python3 scripts/audit_front_zip.py --base http://127.0.0.1:5000

round67で2つ足した。

  * **ウエストの警告**。前開きの型紙は、パネルにウエストダーツが1本も
    入らないまま出ていた(実測: 出来上がりのウエストが採寸+ゆとりより
    14〜21cm大きい)。しかも警告の助言は「切り替え(プリンセスライン)の
    あるデザインにする」で、前開きとは**同時に指定できない**組み合わせ
    だった。できないことを勧めていないかも見る。
  * **同時に選べない組み合わせ**。画面で前開きと切り替え線の両方を
    押せてしまい、「生成する」を押してからエラーで戻されていた。
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from playwright.async_api import async_playwright

_M = {"bust": "88", "waist": "68", "hip": "95", "height": "163",
      "sleeve_length": "58", "shoulder_width": "39"}
_BIG = {"bust": "104", "waist": "92", "hip": "112", "height": "170",
        "sleeve_length": "58", "shoulder_width": "42"}

#: (説明, 採寸, 前開きにするか, 衿を付けるか)
CASES = (
    ("前開きだけ", _M, True, False),
    ("前開き+衿", _M, True, True),
    ("前開き+衿（大きい体型）", _BIG, True, True),
    ("前開きなし+衿（比較用）", _M, False, True),
)

READ_JS = """
() => {
  const box = document.getElementById("compatibility-warning");
  const shown = box && !box.classList.contains("hidden");
  const items = shown
    ? [...box.querySelectorAll("li")].map(li => li.textContent.trim())
    : [];
  const visibleWarnings = [...document.querySelectorAll("#result-panel .field-box")]
    .filter(el => !el.classList.contains("hidden")
                  && (el.innerText || "").includes("⚠"))
    .length;
  const spoken = (document.getElementById("result-status") || {}).textContent || "";
  const notes = [...document.querySelectorAll("#design-note-list li")]
    .map(li => li.textContent.trim());
  // round68: 買い物メモのファスナー欄と、その注記。
  const zipEl = document.getElementById("shopping-zipper");
  const zipper = (zipEl && !zipEl.classList.contains("hidden"))
    ? zipEl.textContent.trim() : "";
  const shoppingNotes = [...document.querySelectorAll("#shopping-notes li")]
    .map(li => li.textContent.trim());
  // round67: 採寸と型紙の食い違い(ウエストの絞りきれなさ等)。
  const measureWarnings = [...document.querySelectorAll(
      "#measurement-clamp-warning-list li")]
    .map(li => li.textContent.trim());
  return {shown, items, visibleWarnings, spoken, notes, measureWarnings,
          zipper, shoppingNotes};
}
"""

#: round67: 前開きの型紙では選べない組み合わせ。押せてしまわないことを見る。
CONFLICT_JS = """
() => {
  const zip = document.getElementById("opt-front-zip");
  const princess = document.getElementById("opt-princess-line");
  const note = document.getElementById("zip-princess-conflict");
  if (!zip || !princess || !note) return {missing: true};
  const read = () => ({
    zipDisabled: zip.disabled, princessDisabled: princess.disabled,
    noteShown: !note.classList.contains("hidden"),
    noteText: note.textContent.trim(),
  });
  const before = read();
  zip.checked = true; zip.dispatchEvent(new Event("change"));
  const afterZip = read();
  zip.checked = false; zip.dispatchEvent(new Event("change"));
  princess.checked = true; princess.dispatchEvent(new Event("change"));
  const afterPrincess = read();
  princess.checked = false; princess.dispatchEvent(new Event("change"));
  return {missing: false, before, afterZip, afterPrincess, cleared: read()};
}
"""


async def _one(page, base: str, values: dict, zip_: bool, collar: bool):
    await page.goto(base, wait_until="networkidle")
    for field, value in values.items():
        await page.fill(f"#field-{field}", value)
    await page.click("label:has(input[name='skirt_style'][value='flare'])")
    if zip_:
        await page.locator("input[name='front_zip']").first.check()
    if collar:
        await page.locator("input[name='include_collar']").first.check()
    await page.wait_for_timeout(300)
    await page.click("button.primary[type=submit]")
    await page.wait_for_selector("#result-content:not(.hidden)", timeout=600000)
    await page.wait_for_timeout(1500)
    return await page.evaluate(READ_JS)


def _spoken_count(text: str) -> int | None:
    """読み上げ文の「注意が N 件あります」から N を取り出す。無ければ0。"""
    import re
    if "注意が" not in text:
        return 0
    m = re.search(r"注意が(\d+)件", text)
    return int(m.group(1)) if m else None


def _check(label: str, data: dict, failures: list[str],
           needs_zip: bool = False) -> None:
    print(f"\n=== {label} ===")
    print(f"  縫い合わせの⚠: {len(data['items'])}件")
    for item in data["items"]:
        print(f"    - {item[:100]}")
    print(f"  画面に出ている⚠の箱: {data['visibleWarnings']}個")
    print(f"  読み上げ: {data['spoken'][:120]}")
    for note in data["notes"]:
        print(f"  注記: {note[:100]}")

    if data["items"]:
        failures.append(
            f"{label}: 「そのままでは縫えません」と言われています"
            f"（{len(data['items'])}件）")

    for warning in data.get("measureWarnings", []):
        print(f"  採寸との食い違い: {warning[:110]}")
        if "出来上がりのウエスト" in warning:
            failures.append(
                f"{label}: ウエストが絞りきれていません（{warning[:60]}…）")
        if "プリンセスライン" in warning and "前開き" in label:
            failures.append(
                f"{label}: 前開きの型紙に、同時に指定できない"
                "「切り替え(プリンセスライン)」を勧めています")

    # round68: 縫う順番が「ファスナーを付ける」と言うなら、買い物メモにも
    # ファスナーが出ていること。round67まで一度も出ていなかった。
    # 「前開きかどうか」は**その場の構成から**受け取る。ラベルの文字で
    # 判定すると「前開きなし+衿」まで前開き扱いになる(実際にそうなった)。
    print(f"  買い物メモのファスナー: {data.get('zipper') or '（無し）'}")
    if needs_zip:
        if not data.get("zipper"):
            failures.append(
                f"{label}: 前開きなのに、買い物メモにファスナーが出ていません")
        elif "前中心の開き" not in data["zipper"]:
            failures.append(
                f"{label}: ファスナーの開き寸法が出ていません: {data['zipper']!r}")
        sourced = [n for n in data.get("shoppingNotes", []) if "ファスナー" in n]
        if not sourced:
            failures.append(f"{label}: ファスナーの注記が出ていません")
        elif not any("出典" in n for n in sourced):
            failures.append(f"{label}: ファスナーの注記に出典がありません")
    elif data.get("zipper"):
        failures.append(f"{label}: 前開きでないのにファスナーが出ています")

    spoken = _spoken_count(data["spoken"])
    if spoken is None:
        failures.append(f"{label}: 読み上げの件数が読めません: {data['spoken'][:60]!r}")
    elif spoken != data["visibleWarnings"]:
        failures.append(
            f"{label}: 読み上げは{spoken}件と言っていますが、画面には"
            f"⚠が{data['visibleWarnings']}個出ています")


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:5000")
    base = parser.parse_args().base.rstrip("/") + "/"
    print(f"接続先: {base}")

    failures: list[str] = []
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(args=["--no-sandbox"])
        for label, values, zip_, collar in CASES:
            page = await browser.new_page(viewport={"width": 1440, "height": 900})
            try:
                data = await _one(page, base, values, zip_, collar)
            finally:
                await page.close()
            _check(label, data, failures, needs_zip=zip_)

        # round67: 同時に選べない組み合わせを、押す前に止めているか。
        page = await browser.new_page(viewport={"width": 1440, "height": 900})
        try:
            await page.goto(base, wait_until="networkidle")
            conflict = await page.evaluate(CONFLICT_JS)
        finally:
            await page.close()
        await browser.close()

    print("\n=== 前開き × 切り替え線（同時に選べない組み合わせ） ===")
    if conflict.get("missing"):
        failures.append("同時に選べない組み合わせの見張りが画面にありません")
    else:
        print(f"  最初          : {conflict['before']}")
        print(f"  前開きを選ぶと: {conflict['afterZip']}")
        print(f"  切替を選ぶと  : {conflict['afterPrincess']}")
        if not conflict["afterZip"]["princessDisabled"]:
            failures.append("前開きを選んでも、切り替え線が押せてしまいます")
        if not conflict["afterPrincess"]["zipDisabled"]:
            failures.append("切り替え線を選んでも、前開きが押せてしまいます")
        if not conflict["afterZip"]["noteShown"]:
            failures.append("押せない理由が画面に出ていません")
        if conflict["before"]["noteShown"] or conflict["cleared"]["noteShown"]:
            failures.append("どちらも選んでいないのに理由が出ています")
        if (conflict["cleared"]["zipDisabled"]
                or conflict["cleared"]["princessDisabled"]):
            failures.append("チェックを外しても押せないままです")

    print()
    if failures:
        print(f"不足 {len(failures)}件:")
        for line in failures:
            print("  -", line)
        return 1
    print("前開きの型紙は「縫えない」と言われず、読み上げの件数も画面と合っています。")
    return 0


sys.exit(asyncio.run(main()))
