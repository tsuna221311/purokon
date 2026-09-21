"""round67: 前開きの型紙は、ウエストで11cm体に合っていなかった。

round66で前開きファスナーの誤警告を消したので、今度は同じ型紙を
最後まで読んだ。残っていた1つの⚠がこれだった。

    出来上がりのウエストは約89cmで、採寸68cm+ゆとり2cmより19cmゆるく
    なります(1枚の身頃にダーツで摘める量の上限に達したため)。
    ウエストをぴったりさせたい場合は、切り替え(プリンセスライン)のある
    デザインにするか、ウエストベルトで押さえてください。

**この助言は実行できない。** 前開きファスナーと切り替え線は同時に
指定できず、`build_garment_spec`がはっきり断る。そして実測すると、
この警告が出ていたのは**前開きを選んだときだけ**だった
(体型5通り × 前開きで5/5、前開き以外の10通りでは0)。

測った結果、原因は2つ重なっていた。

【1】**前開きのパネルにはウエストダーツが1本も入っていなかった。**
`waist_diamond_dart_lines`は「左右対称なパーツの真ん中が中心前」と
みなし、輪郭の全幅の半分を「半幅」として`compute_diamond_dart_plan`へ
渡す。前開きのパネルは半身ぶんなので、その値は実測14.45cm。
狙いの半幅((68+2)/4 = 17.5cm)より小さいため、毎回「摘む余りが無い」と
判断され、**ダーツは0本**だった(ふつうの前身頃は7.99cm摘んでいる)。

【2】**見返し(折り返し代)を胴回りとして数えていた。** 前開きのパネルは
輪郭に見返し4.0cmを含む。見返しは折って裏へ回るので出来上がりの
胴回りには入らないが、`_waist_slack_notes`は輪郭の幅をそのまま
足していた。左右2枚で**8.0cm**の幽霊が胴回りに乗っていた。

【実測】出来上がりのウエスト(採寸+ゆとりとの差)

```
    体型            狙い    ふつう     前開き(前)   前開き(後)
    標準M相当        66.0    66.1      +21.0cm      +1.9cm
    round66の体型    70.0    70.0      +18.6cm      +1.6cm
    くびれ強め       62.0    62.0      +21.0cm      +1.7cm
    ずん胴           82.0    82.0      +14.0cm      +1.3cm
    大きい           94.0    94.1      +16.0cm      +1.8cm
    小柄・細い       60.0    60.0         —         +1.2cm
```

このファイルが見張るのは:

  1. 前開きのパネルからウエストダーツが消える
  2. 見返しが胴回りとして数え直される
  3. 左右対称なパーツの数え方が変わる(=直したつもりで壊す)
  4. できないこと(切り替え線)を勧める文が戻る
  5. 画面で前開きと切り替え線を同時に押せてしまう
"""

from pathlib import Path

import pytest

import engine.pipeline as P
from engine.measurements import Measurements
from engine.pipeline import (PatternForgePipeline, build_garment_spec,
                             _facing_width_cm, _half_panel_anchors,
                             _waist_slack_message)

ROOT = Path(__file__).resolve().parents[1]
APP_JS = (ROOT / "web" / "static" / "app.js").read_text(encoding="utf-8")
INDEX = (ROOT / "web" / "templates" / "index.html").read_text(encoding="utf-8")

BODIES = {
    "標準M相当": Measurements(bust=83, waist=64, hip=91, height=158,
                               sleeve_length=52, shoulder_width=37),
    "round66の体型": Measurements(bust=88, waist=68, hip=95, height=163,
                                   sleeve_length=58, shoulder_width=39),
    "くびれ強め": Measurements(bust=88, waist=60, hip=95, height=163,
                                sleeve_length=58, shoulder_width=39),
    "ずん胴": Measurements(bust=88, waist=80, hip=95, height=163,
                            sleeve_length=58, shoulder_width=39),
    "大きい": Measurements(bust=104, waist=92, hip=112, height=170,
                            sleeve_length=58, shoulder_width=42),
    "小柄・細い": Measurements(bust=78, waist=58, hip=84, height=152,
                                sleeve_length=50, shoulder_width=35),
}

#: ウエストの絞りが「合っている」とみなす範囲(cm)。
#: 開示のしきい値(WAIST_SLACK_DISCLOSURE_CM = 3.0)より内側に入っていること。
WAIST_TOLERANCE_CM = 3.0


@pytest.fixture(scope="module")
def pipe(tmp_path_factory):
    return PatternForgePipeline(output_dir=str(tmp_path_factory.mktemp("r67")))


def _bodice(pipe, body: str, zip_: bool):
    spec = build_garment_spec(neckline="round_neck", sleeve_style=None,
                              skirt_style=None, front_zip=zip_)
    return pipe.generate_from_selection(spec, BODIES[body], skip_export=True)


def _finished_waist(result) -> float:
    """出来上がりのウエスト周(見返しを除き、ダーツを摘んだ後)。"""
    total = 0.0
    for finalized, scaled in zip(result.finalized_parts, result.scaled_parts):
        waist_y = getattr(scaled, "waist_y_cm", None)
        if waist_y is None:
            continue
        span = P._x_span_at_y(
            P._closed_points_from_segments(scaled.segments), waist_y)
        if span is None:
            continue
        intake = sum(max(x for x, _y in line) - min(x for x, _y in line)
                     for line in finalized.internal_lines)
        total += (span[1] - span[0]) - intake - _facing_width_cm(scaled)
    return total


# --- 1. パネルにウエストダーツが入る ----------------------------------------

@pytest.mark.parametrize("body", list(BODIES))
def test_a_front_zip_panel_gets_waist_darts(pipe, body):
    """前開きのパネルに、ウエストのひし形ダーツが入っていること。

    round66までは0本だった(「半幅」として半身ぶんのさらに半分を
    渡していたため、毎回「摘む余りが無い」と判断されていた)。
    """
    result = _bodice(pipe, body, zip_=True)
    panels = [p for p in result.finalized_parts
              if p.part_type == "front_bodice_zip_panel"]
    assert len(panels) == 2, body
    for panel in panels:
        assert panel.internal_lines, (
            f"{body}: 前開きのパネルにウエストダーツが1本も入っていません。")


@pytest.mark.parametrize("body", list(BODIES))
def test_the_finished_waist_fits_with_a_front_zip(pipe, body):
    """出来上がりのウエストが、採寸+ゆとりに収まっていること。"""
    result = _bodice(pipe, body, zip_=True)
    needed = BODIES[body].waist + 2.0
    got = _finished_waist(result)
    assert got - needed <= WAIST_TOLERANCE_CM, (
        f"{body}: 出来上がり{got:.1f}cm / 狙い{needed:.1f}cm "
        f"({got - needed:+.1f}cm)")
    assert got >= needed - 1.0, f"{body}: 狭すぎます({got:.1f} < {needed:.1f})"


@pytest.mark.parametrize("body", list(BODIES))
def test_no_waist_slack_warning_for_a_front_zip_pattern(pipe, body):
    """前開きを選んだだけでウエストの警告が出ないこと。"""
    result = _bodice(pipe, body, zip_=True)
    slack = [w for w in result.summary()["measurement_warnings"]
             if "出来上がりのウエスト" in w]
    assert not slack, (body, slack)


def test_the_darts_stay_between_the_center_front_and_the_side_seam(pipe):
    """ダーツが見返しや脇線に食い込んでいないこと。

    **「1本も無い」で満たされないように**、本数も一緒に見る。
    置き場所が範囲の外へ出ると`waist_diamond_dart_lines`は
    ダーツを諦めて0本を返すので、範囲だけを見るテストは
    「0本だから範囲外のものも無い」で静かに通ってしまう
    (round67で実際に空振りした)。
    """
    result = _bodice(pipe, "round66の体型", zip_=True)
    checked = 0
    for panel, scaled in zip(result.finalized_parts, result.scaled_parts):
        if panel.part_type != "front_bodice_zip_panel":
            continue
        anchors = _half_panel_anchors(scaled)
        assert anchors is not None
        cf_x, side_x = anchors
        lo, hi = min(cf_x, side_x), max(cf_x, side_x)
        assert panel.internal_lines, "ダーツが1本もありません。"
        for line in panel.internal_lines:
            xs = [x for x, _y in line]
            assert min(xs) > lo, (min(xs), lo)
            assert max(xs) < hi, (max(xs), hi)
            checked += 1
    assert checked >= 2, checked


# --- 2. 見返しを胴回りに数えない --------------------------------------------

def test_the_facing_is_measured_from_the_pattern(pipe):
    """見返しの幅を、型紙の基準点から取っていること(手書きしない)。"""
    result = _bodice(pipe, "round66の体型", zip_=True)
    widths = {_facing_width_cm(s) for f, s in
              zip(result.finalized_parts, result.scaled_parts)
              if f.part_type == "front_bodice_zip_panel"}
    assert widths and all(w > 0 for w in widths), widths


def test_a_plain_bodice_has_no_facing(pipe):
    """左右対称な身頃には見返しが無く、数え方が変わらないこと。"""
    result = _bodice(pipe, "round66の体型", zip_=False)
    for finalized, scaled in zip(result.finalized_parts, result.scaled_parts):
        if "bodice" in finalized.part_type:
            assert _facing_width_cm(scaled) == 0.0, finalized.part_type
            assert _half_panel_anchors(scaled) is None, finalized.part_type


# --- 3. 左右対称なパーツを壊していない --------------------------------------

@pytest.mark.parametrize("body", list(BODIES))
def test_the_plain_bodice_waist_is_unchanged(pipe, body):
    """前開きでない身頃は、これまでどおり狙いどおりに絞れていること。"""
    result = _bodice(pipe, body, zip_=False)
    needed = BODIES[body].waist + 2.0
    got = _finished_waist(result)
    assert abs(got - needed) <= 1.0, (body, got, needed)


# --- 4. できないことを勧めない ----------------------------------------------

class _Ease:
    def __init__(self, waist_cm: float):
        self.waist_cm = waist_cm


@pytest.mark.parametrize("waist_ease", [2.0, -3.0])
def test_the_advice_does_not_suggest_an_impossible_combination(waist_ease):
    """前開きの型紙に「切り替え線にしてください」と言わないこと。

    この2つは同時に指定できない(`build_garment_spec`が断る)。
    """
    message = _waist_slack_message(
        99.0, BODIES["round66の体型"], _Ease(waist_ease),
        princess_available=False)[0]
    assert "プリンセスライン" not in message or "同時に指定できません" in message
    assert "デザインにしてください" not in message or "同時に" in message


@pytest.mark.parametrize("waist_ease", [2.0, -3.0])
def test_the_advice_still_suggests_princess_when_it_is_possible(waist_ease):
    """前開きでない型紙には、これまでどおり切り替え線を勧めること。"""
    message = _waist_slack_message(
        99.0, BODIES["round66の体型"], _Ease(waist_ease),
        princess_available=True)[0]
    assert "プリンセスライン" in message


def test_the_pipeline_knows_when_princess_is_unavailable():
    """呼び出し側が、前開きかどうかを見て渡していること。"""
    import inspect
    source = inspect.getsource(P.PatternForgePipeline._build_from_spec)
    assert "princess_available=" in source
    assert "front_bodice_zip_panel" in source


# --- 5. 画面で同時に押せない ------------------------------------------------

def test_the_screen_blocks_the_impossible_combination():
    """前開きと切り替え線を、画面で同時に押せなくしていること。"""
    assert 'id="opt-front-zip"' in INDEX
    assert 'id="opt-princess-line"' in INDEX
    assert 'id="zip-princess-conflict"' in INDEX
    assert "syncZipPrincessConflict" in APP_JS
    assert "optPrincess.disabled" in APP_JS
    assert "optFrontZip.disabled" in APP_JS


def test_the_reason_is_not_a_collapsible_hint():
    """理由に class="hint" を付けないこと。

    round32の`collapseLongHints`が長い`p.hint`を<details>へ畳むので、
    hintにすると**押せない理由が畳まれて読めなくなる**。
    """
    # この要素の開始タグだけを取り出す(近くの別の<p class="hint">を
    # 拾わないように)。
    idx = INDEX.index('id="zip-princess-conflict"')
    open_tag = INDEX[INDEX.rindex("<", 0, idx):INDEX.index(">", idx) + 1]
    assert 'id="zip-princess-conflict"' in open_tag, open_tag
    assert "hint" not in open_tag, open_tag
    assert "conflict-note" in open_tag, open_tag


def test_the_blocked_checkbox_says_why_to_a_screen_reader():
    """押せない方に、押せない理由を結び付けていること。"""
    assert 'setAttribute("aria-describedby", "zip-princess-conflict")' in APP_JS
    assert 'removeAttribute("aria-describedby")' in APP_JS


# --- 6. 出力の見張りに前開きが入っている ------------------------------------

def test_the_snapshot_tool_covers_a_front_zip_pattern():
    """出力の突き合わせに、前開きの型紙が1つは入っていること。

    round66まで9通りすべてが前開きを含まず、前開きのパネルだけ形が
    変わってもこの道具は「変わっていない」と言い続けた。
    """
    source = (ROOT / "scripts" / "snapshot_outputs.py").read_text(encoding="utf-8")
    start = source.index("CASES = [")
    end = source.index("\n]", start)
    assert "front_zip=True" in source[start:end]
