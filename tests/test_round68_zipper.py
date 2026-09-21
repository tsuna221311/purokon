"""round68: 縫う順番は「ファスナーを付ける」と言うのに、買い物メモに無かった。

生地屋の店先でこのページを見て買う、というつもりで買い物メモを読んだ。
載っていたのは**表地・接着芯・裏地**の3つ。ところが同じ型紙の縫う順番には

    前開きファスナーを付ける
      中心前の裁ち割りにファスナーを付け、見返しを重ねて始末します。

とある。**ファスナーは買い物メモに一度も出てこない。** 生地と接着芯だけ
買って帰ることになり、しかも何cmのものが要るかも分からない。

【実測】縫う順番に出てくる「買わないと作れない物」を、買い物メモと
突き合わせた(構成7通り × 裏地あり/なし = 14通り)。

```
    接着芯   出てくる12通りすべてで、メモに載っている
    裏地     出てくる7通りすべてで、メモに載っている
    ファスナー 出てくる4通りすべてで、**メモに載っていない**
```

抜けていたのはファスナーだけだった。

直し方: 開き寸法を**型紙の中心前を実測して**出す
(`engine/pipeline.py`の`_front_opening_length_cm`)。長さの数え方と
詰め方は出典のある事実だけを書く。**どの製品を買えとは言わない**
——市販の長さの刻みに出典が見つからなかったため。

このファイルが見張るのは:

  1. 縫う順番が「付けろ」と言う物が、買い物メモから漏れる
  2. 開き寸法が型紙とずれる(手で書いた数字に戻る)
  3. 同じ数字が画面・紙・注記で違う丸めになる(round61と同じ形)
  4. 出典の無い「何cmのものを買え」が紛れ込む
  5. 前開きでない型紙にファスナーの話が出る
"""

import re
import subprocess
from pathlib import Path

import pytest

import engine.pipeline as P
from engine.fabric import (ZIP_LENGTH_SOURCE_URL, ZIP_SHORTEN_SOURCE_URL,
                           front_opening_note)
from engine.measurements import Measurements
from engine.pipeline import PatternForgePipeline, build_garment_spec

ROOT = Path(__file__).resolve().parents[1]
APP_JS = (ROOT / "web" / "static" / "app.js").read_text(encoding="utf-8")

STANDARD = Measurements(bust=88, waist=68, hip=95, height=163,
                        sleeve_length=58, shoulder_width=39)

#: 「買わないと作れない物」の呼び名。縫う順番の文と買い物メモの両方を
#: この語彙で突き合わせる。物が増えたら**ここに足す**——足した物が
#: メモから漏れていれば、下のテストが落ちる。
PURCHASABLE = ("ファスナー", "接着芯", "裏地", "ゴム", "ボタン",
               "スナップ", "ホック", "面ファスナー")

CONFIGS = {
    "前開き": dict(skirt_style="flare", front_zip=True),
    "衿": dict(skirt_style="flare", include_collar=True),
    "カフス": dict(skirt_style="flare", include_cuffs=True),
    "ウエストバンド": dict(skirt_style="flare", include_waistband=True),
    "パンツ": dict(skirt_style=None, include_pants=True),
    "前開き+全部": dict(skirt_style="flare", front_zip=True, include_collar=True,
                        include_cuffs=True, include_waistband=True),
}
CASES = [(c, lining) for c in CONFIGS for lining in (False, True)]


@pytest.fixture(scope="module")
def pipe(tmp_path_factory):
    return PatternForgePipeline(output_dir=str(tmp_path_factory.mktemp("r68")))


def _generate(pipe, config: str, lining: bool):
    spec = build_garment_spec(**CONFIGS[config])
    return pipe.generate_from_selection(spec, STANDARD, skip_export=True,
                                        lining=lining)


def _memo_text(summary: dict) -> str:
    """買い物メモに出ている文字すべて(画面にも紙にも同じものが出る)。"""
    memo = summary["shopping_list"] or {}
    parts = list(memo.get("notes", []))
    parts += [s.get("text", "") for s in memo.get("suggestions", [])]
    if memo.get("interfacing_length_cm"):
        parts.append("接着芯")
    if memo.get("lining_widths"):
        parts.append("裏地")
    if memo.get("front_opening_cm"):
        parts.append("ファスナー")
    return " ".join(parts)


def _steps_text(summary: dict) -> str:
    return " ".join(s.get("title", "") + " " + s.get("detail", "")
                    for s in summary["assembly_steps"])


# --- 1. 縫う順番と買い物メモの突き合わせ -------------------------------------

@pytest.mark.parametrize("config,lining", CASES)
def test_everything_the_steps_tell_you_to_attach_is_on_the_shopping_list(
        pipe, config, lining):
    """「付けろ」と言われた物が、買い物メモに出てくること。

    これが round68 で見つけた不具合そのものである。縫う順番は
    ファスナーを付けろと言い、買い物メモはそれに触れなかった。
    """
    summary = _generate(pipe, config, lining).summary()
    steps = _steps_text(summary)
    memo = _memo_text(summary)
    for item in PURCHASABLE:
        if item in steps:
            assert item in memo, (
                f"{config}{'+裏地' if lining else ''}: 縫う順番は「{item}」を"
                "付けろと言っていますが、買い物メモに出てきません。")


@pytest.mark.parametrize("config,lining", CASES)
def test_the_shopping_list_does_not_invent_things_the_steps_never_mention(
        pipe, config, lining):
    """逆に、縫わない物を買わせないこと。"""
    summary = _generate(pipe, config, lining).summary()
    steps = _steps_text(summary)
    memo = summary["shopping_list"] or {}
    if memo.get("front_opening_cm"):
        assert "ファスナー" in steps, (config, lining)


# --- 2. 開き寸法は型紙から測る ------------------------------------------------

def _measured_opening(result) -> float:
    """テストの側で、型紙から独立に測り直す。"""
    for finalized, scaled in zip(result.finalized_parts, result.scaled_parts):
        if finalized.part_type != "front_bodice_zip_panel":
            continue
        cf_x = P._anchor_x(scaled, "cf")
        points = P._closed_points_from_segments(scaled.segments)
        extent = P._y_extent_at_x(points, cf_x)
        return extent[1] - extent[0]
    raise AssertionError("前開きのパネルがありません")


BODIES = {
    "小柄": Measurements(bust=78, waist=58, hip=84, height=152,
                          sleeve_length=50, shoulder_width=35),
    "標準": STANDARD,
    "大きい": Measurements(bust=104, waist=92, hip=112, height=170,
                            sleeve_length=58, shoulder_width=42),
}


@pytest.mark.parametrize("body", list(BODIES))
def test_the_opening_length_is_measured_from_the_pattern(pipe, body):
    """メモの数字が、型紙を測った値と一致すること(手で書かない)。"""
    spec = build_garment_spec(skirt_style="flare", front_zip=True)
    result = pipe.generate_from_selection(spec, BODIES[body], skip_export=True)
    memo = result.summary()["shopping_list"]
    assert memo["front_opening_cm"] == pytest.approx(
        _measured_opening(result), abs=0.05), body


def test_the_opening_length_follows_the_body(pipe):
    """体型が変われば開き寸法も変わること(固定値が紛れていないか)。"""
    lengths = []
    for body in ("小柄", "標準", "大きい"):
        spec = build_garment_spec(skirt_style="flare", front_zip=True)
        result = pipe.generate_from_selection(spec, BODIES[body],
                                              skip_export=True)
        lengths.append(result.summary()["shopping_list"]["front_opening_cm"])
    assert lengths[0] < lengths[1] < lengths[2], lengths


@pytest.mark.parametrize("config,expected", [
    (dict(skirt_style="flare", front_zip=True), "waist"),
    (dict(skirt_style=None, include_pants=True, front_zip=True), "waist"),
    (dict(skirt_style=None, sleeve_style=None, front_zip=True), "hem"),
])
def test_the_bottom_of_the_opening_matches_the_pattern(pipe, config, expected):
    """開きの下端が、型紙の作りと合っていること。"""
    result = pipe.generate_from_selection(
        build_garment_spec(**config), STANDARD, skip_export=True)
    assert result.summary()["shopping_list"]["front_opening_bottom"] == expected


def test_no_zipper_entry_without_a_front_zip(pipe):
    """前開きでない型紙にファスナーの話を出さないこと。"""
    result = pipe.generate_from_selection(
        build_garment_spec(skirt_style="flare"), STANDARD, skip_export=True)
    memo = result.summary()["shopping_list"]
    assert memo["front_opening_cm"] is None
    assert memo["front_opening_bottom"] == ""
    assert not any("ファスナー" in n for n in memo["notes"])


# --- 3. 同じ数字を、同じ丸めで出す ------------------------------------------

def test_the_same_number_appears_everywhere_with_the_same_rounding(pipe):
    """注記の中の数字が、フィールドの値と同じ丸めであること。

    round61の教訓: 同じ数字を2か所に違う丸めで書くと、必ずどちらかが
    嘘になる。
    """
    spec = build_garment_spec(skirt_style="flare", front_zip=True)
    result = pipe.generate_from_selection(spec, STANDARD, skip_export=True)
    memo = result.summary()["shopping_list"]
    value = memo["front_opening_cm"]
    note = next(n for n in memo["notes"] if "ファスナー" in n)
    numbers = set(re.findall(r"(\d+\.\d)cm", note))
    assert numbers == {f"{value:.1f}"}, (numbers, value)


def test_the_screen_shows_the_engine_value_without_re_rounding():
    """画面が、受け取った値をそのまま小数第1位で出していること。"""
    start = APP_JS.index("const zipper = document.getElementById")
    block = APP_JS[start:start + 900]
    assert "memo.front_opening_cm" in block
    assert "toFixed(1)" in block


# --- 4. 出典 -----------------------------------------------------------------

def test_the_note_cites_its_sources():
    """長さの数え方と詰め方に、出典が付いていること。"""
    note = front_opening_note(58.6, "waist")
    assert ZIP_LENGTH_SOURCE_URL in note
    assert ZIP_SHORTEN_SOURCE_URL in note


def test_the_sourced_note_reaches_the_memo(pipe):
    """出典付きの文が、**実際の買い物メモに入っていること**。

    `front_opening_note`を単体で見るだけでは、それが呼ばれずに
    捨てられていても気づけない(round68で実際に空振りした)。
    """
    spec = build_garment_spec(skirt_style="flare", front_zip=True)
    result = pipe.generate_from_selection(spec, STANDARD, skip_export=True)
    notes = result.summary()["shopping_list"]["notes"]
    zipper_notes = [n for n in notes if "ファスナー" in n]
    assert zipper_notes, notes
    assert any(ZIP_LENGTH_SOURCE_URL in n for n in zipper_notes)
    assert any(ZIP_SHORTEN_SOURCE_URL in n for n in zipper_notes)


def test_the_note_does_not_invent_a_product_length():
    """出典の無い「何cmのものを買え」を書かないこと。

    市販のファスナーの長さの刻みは、出典が見つからなかった。
    見つからないものを、それらしく書かない。
    """
    note = front_opening_note(58.6, "waist")
    for invented in ("60cmのもの", "5cm刻み", "10cm刻み", "5cm長い", "次に長い"):
        assert invented not in note, invented
    # 言ってよいのは「開き寸法以上」だけ。
    assert "58.6cm以上" in note


# --- 5. 紙にも出る -----------------------------------------------------------

def test_the_printed_memo_has_the_zipper(tmp_path):
    """買い物メモのページ(PDF)に、ファスナーが出ていること。

    このページを見るのは生地屋の店先なので、画面だけでは足りない。
    """
    pipe = PatternForgePipeline(output_dir=str(tmp_path))
    spec = build_garment_spec(skirt_style="flare", front_zip=True)
    result = pipe.generate_from_selection(spec, STANDARD)
    text = subprocess.run(["pdftotext", "-layout", result.output_files["pdf"], "-"],
                          capture_output=True, text=True, check=True).stdout
    page = next(p for p in text.split("\f") if "買い物メモ" in p)
    assert "ファスナー" in page
    assert "前中心の開き" in page
    opening = result.summary()["shopping_list"]["front_opening_cm"]
    assert f"{opening:.1f}cm" in page
