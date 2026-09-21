"""round66: 前開きファスナーの型紙は、必ず「そのままでは縫えません」と言われていた。

パソコンで、コスプレでいちばんよく使う作りの服を1着通した——前開き
ファスナー・衿・カフス・ウエストバンド付きのワンピース。生成された結果に
赤い⚠が2つ出た。

    前身頃の脇線の長さ(合計154.5cm)と、後ろ身頃の脇線の長さ(合計70.4cm)が
    84.1cm一致していません。……そのままでは縫えません。

    身頃の首ぐりの長さ(前+後で15.6cm)に対し、衿の首ぐり側の辺が42.4cmで、
    26.8cm一致していません。……そのままでは付けられません。

**どちらも型紙ではなく、測り方の誤りだった。**

【1つ目・脇線】前開きにすると前身頃は`front_bodice_zip_panel`2枚になる。
1枚の輪郭には縦の長い線が2本ある——外側の脇線と、中心前(見返し)の縁。
`side_seam_length`は「y_topの差が3cmを超えたら非対称とみなし、
ネックラインから遠い方を本物の脇線とする」で見分ける設計だった。

ところが round31 が `side_seam_edges` に「脇の下より上の辺は候補にしない」
を足した(後ろ袖ぐりが脇線と区別できなくなったため。これ自体は正しい)。
その結果**どの候補もy_topが脇の下の高さちょうどになり、差は常に0**。

    切り詰め無し  脇線 y_top=24.7 / 中心前の縁 y_top=8.1  → 差16.6cm
    脇の下で切る  脇線 y_top=24.7 / 中心前の縁 y_top=24.7 → 差 0cm

見分ける判定は、書いてあるのに二度と成立しない状態だった。差0なので
「左右対称な本物の脇線2本」とみなされ、中心前の縁(42.1cm)まで足して
77.3cm。パネル2枚で154.5cm。正しい脇線は35.2cmで、後ろ身頃の片側と
ぴったり同じである(=型紙は最初から正しかった)。

【2つ目・衿】首ぐりの比較対象が `{"front_bodice", "back_bodice"}` で、
前開きだと前身頃がこの集合から**静かに消える**。後ろ身頃だけが残り、
それでも`all(v is not None)`は通るので、後ろだけの15.6cmを
「前+後で15.6cm」と名乗って衿と比べていた。

【実測】体型3通り × 前開きを含む構成4通り = 12通りすべてで、脇線の警告が
出ていた。衿を足した3通りでは衿の警告も出ていた。前開きを選ばない
12通りでは1件も出ていない。

このファイルが見張るのは:

  1. 前開きのパネルの脇線が、また中心前の縁を足した値に戻る
  2. 首ぐりの比較対象から、前身頃が静かに消える
  3. 測れないものを「測れない」と言わずに黙って飛ばす
  4. 誤警告を消したつもりで、**本物の食い違いまで見えなくする**
  5. 読み上げが、画面に出ている⚠を数え落とす
"""

from pathlib import Path

import pytest

from engine import compatibility as C
from engine.compatibility import check_seam_compatibility, unchecked_seams
from engine.measurements import Measurements
from engine.pipeline import PatternForgePipeline, build_garment_spec
from engine.seam import finalize_part
from engine.svgpath import scale_segments

ROOT = Path(__file__).resolve().parents[1]
APP_JS = (ROOT / "web" / "static" / "app.js").read_text(encoding="utf-8")

BODIES = {
    "標準": Measurements(bust=88, waist=68, hip=95, height=163,
                          sleeve_length=58, shoulder_width=39),
    "細い": Measurements(bust=83, waist=60, hip=90, height=158,
                          sleeve_length=52, shoulder_width=37),
    "大きい": Measurements(bust=104, waist=92, hip=112, height=170,
                            sleeve_length=58, shoulder_width=42),
}

#: 前開きを含む構成。コスプレでよく使う組み合わせを並べてある。
ZIP_CONFIGS = {
    "前開き": dict(skirt_style="flare", front_zip=True),
    "前開き+衿": dict(skirt_style="flare", front_zip=True, include_collar=True),
    "Vネック前開き": dict(skirt_style="flare", neckline="v_neck", front_zip=True),
    "タイト前開き": dict(skirt_style="tight", front_zip=True),
}

ZIP_CASES = [(b, c) for b in BODIES for c in ZIP_CONFIGS]


@pytest.fixture(scope="module")
def pipe(tmp_path_factory):
    return PatternForgePipeline(output_dir=str(tmp_path_factory.mktemp("r66")))


def _result(pipe, body: str, config: str):
    spec = build_garment_spec(**ZIP_CONFIGS[config])
    return pipe.generate_from_selection(spec, BODIES[body], skip_export=True)


# --- 1. 脇線 ---------------------------------------------------------------

@pytest.mark.parametrize("body,config", ZIP_CASES)
def test_a_zip_panel_side_seam_matches_one_side_of_the_back(pipe, body, config):
    """パネル1枚の脇線が、後ろ身頃の**片側**と同じ長さであること。

    round65までは中心前の縁まで足していたので、後ろの片側の2倍以上に
    なっていた(実測35.2 → 77.3)。
    """
    result = _result(pipe, body, config)
    panels = [p for p in result.finalized_parts
              if p.part_type == "front_bodice_zip_panel"]
    backs = [p for p in result.finalized_parts if p.part_type == "back_bodice"]
    assert len(panels) == 2 and len(backs) == 1, (body, config)
    back_per_side = C.side_seam_length(backs[0]) / 2.0
    for panel in panels:
        got = C.side_seam_length(panel)
        assert got == pytest.approx(back_per_side, abs=1.0), (
            f"{body}/{config}: パネルの脇線が{got:.1f}cm、"
            f"後ろ身頃の片側が{back_per_side:.1f}cm。"
            "中心前の縁まで足していませんか。")


@pytest.mark.parametrize("body,config", ZIP_CASES)
def test_no_side_seam_warning_for_a_front_zip_pattern(pipe, body, config):
    """前開きを選んだだけで「そのままでは縫えません」と言われないこと。"""
    result = _result(pipe, body, config)
    kinds = {w.kind for w in result.compatibility_warnings()}
    assert "side_seam" not in kinds, (
        f"{body}/{config}: "
        + " / ".join(w.message for w in result.compatibility_warnings()))


def test_the_discriminator_needs_the_untruncated_outline(pipe):
    """見分けるy_topを「脇の下で切り詰める前」から取っていること。

    これが今回の不具合の芯である。切り詰めた後のy_topは、どんな形でも
    脇の下の高さちょうどになるので、差は常に0になり、
    「差が3cmを超えたら非対称」という判定は二度と成立しない。
    """
    result = _result(pipe, "標準", "前開き")
    panel = next(p for p in result.finalized_parts
                 if p.part_type == "front_bodice_zip_panel")
    points = C._closed_points(panel.stitch_line)

    def y_tops(underarm):
        out: dict[str, float] = {}
        for _i, side, p1, p2 in C.side_seam_edges(points, 0.5, underarm):
            out[side] = min(out.get(side, 1e9), p1[1], p2[1])
        return out

    truncated = y_tops(C.underarm_y_of(panel))
    full = y_tops(None)
    assert len(truncated) == 2 and len(full) == 2
    assert abs(truncated["left"] - truncated["right"]) \
        <= C._CF_VS_SIDE_YTOP_DIFF_CM, (
        "切り詰めた後のy_topに差があります。"
        "この前提が変わったなら side_seam_length の作りを見直してください。")
    assert abs(full["left"] - full["right"]) > C._CF_VS_SIDE_YTOP_DIFF_CM, (
        "切り詰め前のy_topにも差がありません。中心前と脇線を見分けられません。")


def test_side_seam_warning_still_fires_on_a_zip_pattern(pipe):
    """誤警告を消したことで、**本物の食い違い**まで見えなくなっていないこと。

    前身頃のパネルだけ丈を0.8倍に縮めた型紙を組み立てて確かめる。
    """
    db = pipe.template_db
    segments = scale_segments(db.get("front_bodice_zip_panel", "round_neck"), 1.0, 0.8)
    panel = finalize_part("front_bodice_zip_panel", "round_neck", segments)
    back = finalize_part("back_bodice", "round_neck",
                         db.get("back_bodice", "round_neck"))
    kinds = {w.kind for w in check_seam_compatibility([panel, panel, back])}
    assert "side_seam" in kinds


def test_the_plain_bodice_side_seam_is_unchanged(pipe):
    """前開きでない身頃は、前後とも左右を合算したままであること。"""
    spec = build_garment_spec(skirt_style="flare")
    result = pipe.generate_from_selection(spec, BODIES["標準"], skip_export=True)
    front = next(p for p in result.finalized_parts if p.part_type == "front_bodice")
    back = next(p for p in result.finalized_parts if p.part_type == "back_bodice")
    assert C.side_seam_length(front) == pytest.approx(C.side_seam_length(back), abs=1.0)
    # 左右2本ぶんであること(片側だけを返していない)。
    assert C.side_seam_length(back) > 60.0


# --- 2. 衿 -----------------------------------------------------------------

def test_the_front_is_not_dropped_from_the_neckline_comparison():
    """首ぐりの比較対象に、前開きのパネルが入っていること。

    集合から漏れると、前身頃が静かに消えて後ろだけの長さを
    「前+後で」と名乗る(それが round65 までの状態だった)。
    """
    import inspect
    source = inspect.getsource(check_seam_compatibility)
    marker = 'neckline_parts = _all(finalized_parts,'
    start = source.index(marker)
    block = source[start:start + 260]
    for part_type in ("front_bodice", "front_bodice_zip_panel", "back_bodice"):
        assert f'"{part_type}"' in block, part_type


@pytest.mark.parametrize("body", list(BODIES))
def test_no_collar_warning_for_a_front_zip_pattern(pipe, body):
    """前開き+衿で「そのままでは付けられません」と言われないこと。"""
    result = _result(pipe, body, "前開き+衿")
    kinds = {w.kind for w in result.compatibility_warnings()}
    assert "neckline_collar" not in kinds, (
        body, [w.message for w in result.compatibility_warnings()])


@pytest.mark.parametrize("body", list(BODIES))
def test_the_unchecked_collar_is_said_out_loud(pipe, body):
    """確かめていないことを、黙らずに言うこと。

    黙って飛ばすと「確かめた結果、問題なし」と区別が付かない。
    """
    result = _result(pipe, body, "前開き+衿")
    notes = unchecked_seams(result.finalized_parts)
    assert notes, body
    assert any("確かめていません" in n for n in notes), notes
    # 画面へ届いていること(design_notes に混ぜてある)。
    assert any(n in result.summary()["design_notes"] for n in notes), body


def test_nothing_is_reported_unchecked_when_the_check_really_ran(pipe):
    """前開きでない身頃+衿では、衿の長さを実際に確かめているので黙る。"""
    spec = build_garment_spec(skirt_style="flare", include_collar=True)
    result = pipe.generate_from_selection(spec, BODIES["標準"], skip_export=True)
    assert unchecked_seams(result.finalized_parts) == []


def test_nothing_is_reported_unchecked_without_a_collar(pipe):
    """衿が無ければ、衿の話はしない。"""
    result = _result(pipe, "標準", "前開き")
    assert unchecked_seams(result.finalized_parts) == []


# --- 3. 読み上げ -------------------------------------------------------------

def test_the_spoken_summary_counts_the_seam_warnings():
    """読み上げの件数に、縫い合わせの警告が入っていること。

    round65までは採寸の指摘と配置不能だけを数えており、画面に⚠が3件
    出ているのに「注意が1件あります」と言っていた。数え落としていたのは
    「そのままでは縫えません」という、いちばん先に知りたい種類である。
    """
    start = APP_JS.index("const warnings = (data.measurement_warnings")
    block = APP_JS[start:start + 320]
    for key in ("measurement_warnings", "unplaced_warnings",
                "compatibility_warnings"):
        assert f"data.{key}" in block, key
