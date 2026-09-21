"""audit_dart_note.py — 画面の「ダーツが入ったパーツ」が、実物と合っているか。round65で追加。

【なぜ要るか】ダーツはV字の切り込みで、裁つ前に「どのパーツのどこを見るか」
の話である。round64まで、この説明はHTMLに**手書き**してあった——

    「身頃のウエスト/脇ダーツ、タイトスカートのウエストダーツなど」

14通りで実測すると、この文が出る11通りのうち10通りで、挙げたパーツに
ダーツは1本も入っていなかった（標準体型ではタイトスカートにも入らない。
パンツに8本入っても文はパンツに触れない）。

この台本は、**画面に描かれた文**と**パーツ一覧の[ダーツN本]**を
突き合わせる。サーバの応答ではなく、実際に描かれた文字を読む
（応答が正しくても、画面が別の物を描いていたら意味がない）。

    python3 app.py &
    python3 scripts/audit_dart_note.py --base http://127.0.0.1:5000

判定: 説明が挙げたパーツの集合と、一覧で[ダーツN本]が付いたパーツの
集合がずれていたら落とす。本数も突き合わせる。
"""

from __future__ import annotations

import argparse
import asyncio
import pathlib
import re
import sys

from playwright.async_api import async_playwright

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from engine.part_names import PART_TYPE_LABELS_JA   # noqa: E402

_NARROW = {"bust": "88", "waist": "60", "hip": "100", "height": "163",
           "sleeve_length": "56", "shoulder_width": "39"}
_PLAIN = {"bust": "88", "waist": "70", "hip": "94", "height": "163",
          "sleeve_length": "56", "shoulder_width": "39"}

#: 試す構成。「文が出るのにパーツ名が合わない」形を拾えるよう、
#: スカートにダーツが入る体型と入らない体型の両方を通す。
#: 最後の1つは**ダーツが1本も入らない**構成で、説明が出ないことを見る
#: (伸びる生地の型紙はダーツを入れない。engine/part_specs.pyのis_stretch)。
CASES = (
    ("標準体型・サーキュラースカート", _PLAIN, "circle", False, None),
    ("標準体型・タイトスカート", _PLAIN, "tight", False, None),
    ("ウエストが細い・タイトスカート", _NARROW, "tight", False, None),
    ("ウエストが細い・パンツ", _NARROW, None, True, None),
    ("伸びる生地（ダーツは入らない）", _NARROW, "tight", False, "stretch"),
)

#: パーツ一覧のチップに付く「 [ダーツ4本]」。
CHIP_DART = re.compile(r"^(?P<name>.+?)\s*\[ダーツ(?P<n>\d+)本\]$")
#: 説明の行「前身頃（ラウンドネック） — 4本」。
NOTE_ROW = re.compile(r"^(?P<name>.+?)\s*—\s*(?P<n>\d+)本$")


async def _one(page, base: str, values: dict, skirt: str | None, pants: bool,
               fit: str | None):
    await page.goto(base, wait_until="networkidle")
    for field, value in values.items():
        await page.fill(f"#field-{field}", value)
    if fit:
        await page.select_option("#fit", fit)
        if fit == "stretch":
            # 伸びる生地は伸縮率が必須(未入力だと400で止まる)。
            await page.fill("input[name='stretch_percent']", "50")
    if skirt:
        await page.click(f"label:has(input[name='skirt_style'][value='{skirt}'])")
    else:
        await page.click("label:has(input[name='skirt_style'][value=''])")
    if pants:
        box = page.locator("input[name='include_pants']")
        if await box.count():
            await box.first.check()
    await page.click("button.primary[type=submit]")
    await page.wait_for_selector("#result-content:not(.hidden)", timeout=600000)
    await page.wait_for_timeout(1200)
    return await page.evaluate("""() => {
      const note = document.getElementById("dart-note");
      const shown = note && !note.classList.contains("hidden");
      const rows = shown
        ? [...note.querySelectorAll("#dart-note-list li")].map(li => li.textContent.trim())
        : [];
      const chips = [...document.querySelectorAll("#parts-chip-list .part-chip-name")]
        .map(el => el.textContent.trim());
      const total = shown
        ? Number(document.getElementById("dart-count").textContent) : 0;
      // 一覧の外に書かれている文(=手書きの説明)だけを取り出す。
      // パーツ名は一覧から来るものだけであるべきで、地の文に
      // 「タイトスカートの…」のような例示が戻ったらここに現れる。
      let prose = "";
      if (shown) {
        const clone = note.cloneNode(true);
        const ul = clone.querySelector("#dart-note-list");
        if (ul) ul.remove();
        prose = clone.innerText.replace(/\\s+/g, " ").trim();
      }
      return {shown, rows, chips, total, prose};
    }""")


def _check(label: str, data: dict, failures: list[str]) -> None:
    from_chips: dict[str, int] = {}
    for chip in data["chips"]:
        m = CHIP_DART.match(chip)
        if m:
            from_chips[m.group("name")] = int(m.group("n"))
    from_note: dict[str, int] = {}
    for row in data["rows"]:
        m = NOTE_ROW.match(row)
        if m:
            from_note[m.group("name")] = int(m.group("n"))
        else:
            failures.append(f"{label}: 説明の行が読めません: {row!r}")

    print(f"\n=== {label} ===")
    print(f"  一覧で[ダーツN本]が付いたパーツ: {from_chips or '（無し）'}")
    print(f"  説明が挙げたパーツ            : {from_note or '（説明は出ていない）'}")

    # 一覧の外の地の文にパーツ名が現れたら、それは手書きの例示である。
    # round64まではここに「身頃のウエスト/脇ダーツ、タイトスカートの
    # ウエストダーツなど」と書いてあり、11通り中10通りで外れていた。
    for name in sorted(set(PART_TYPE_LABELS_JA.values())):
        if name and name in data.get("prose", ""):
            failures.append(
                f"{label}: 説明の地の文に「{name}」と書かれています"
                "（パーツ名は一覧から来るものだけにしてください）")

    if not from_chips:
        if data["shown"]:
            failures.append(f"{label}: ダーツが1本も無いのに説明が出ています")
        return
    if not data["shown"]:
        failures.append(f"{label}: ダーツが入っているのに説明が出ていません")
        return
    missing = set(from_chips) - set(from_note)
    extra = set(from_note) - set(from_chips)
    if missing:
        failures.append(f"{label}: 説明に出てこないのにダーツが入っている: {sorted(missing)}")
    if extra:
        failures.append(f"{label}: 説明が挙げているのにダーツが入っていない: {sorted(extra)}")
    for name, count in from_note.items():
        if name in from_chips and from_chips[name] != count:
            failures.append(
                f"{label}: {name} の本数がずれています"
                f"(説明 {count}本 / 一覧 {from_chips[name]}本)")
    if data["total"] != sum(from_chips.values()):
        failures.append(
            f"{label}: 合計がずれています"
            f"(説明 {data['total']}本 / 一覧 {sum(from_chips.values())}本)")


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:5000")
    base = parser.parse_args().base.rstrip("/") + "/"
    print(f"接続先: {base}")

    failures: list[str] = []
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(args=["--no-sandbox"])
        for label, values, skirt, pants, fit in CASES:
            page = await browser.new_page(viewport={"width": 1440, "height": 900})
            try:
                data = await _one(page, base, values, skirt, pants, fit)
            finally:
                await page.close()
            _check(label, data, failures)
        await browser.close()

    print()
    if failures:
        print(f"不足 {len(failures)}件:")
        for line in failures:
            print("  -", line)
        return 1
    print("どの構成でも、説明が挙げるパーツと実際にダーツが入ったパーツは一致しています。")
    return 0


sys.exit(asyncio.run(main()))
