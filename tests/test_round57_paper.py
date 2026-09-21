"""round57(後半): マントの分割 / PDFの1本化 / A3 / Claude APIの経路。

  6. **マントが収まらないときの逃げ道を作った。** round56は「正しい幅を
     言えるようにしただけで、作れるようにはなっていない」と書いて終わって
     いた。分割(engine/panel_split.py)はスカート・パンツ限定だったので、
     カスタムパーツにも**利用者が望んだときだけ**効くようにした。
     マントは中心で縫い合わせるのがふつうだが、EVAフォームの装甲に縫い目を
     入れるのは別の話——どちらなのかは作る人にしか分からないので、
     勝手に分けず、パーツごとの指定に従う。警告も「採寸値を見直すか」から
     「何枚に分ければ収まるか」に変えた。

  7. **生地ごとのPDFを1本にまとめられるようにした。** round54では生地の
     数だけ別ファイルで、コンビニで2色なら2ファイル送ることになっていた。

  8. **A3に対応した。** 用紙寸法が73か所に直書きされていたのを1か所に
     まとめた。実測: 同じ型紙が A4 48枚 → A3 23枚。
     **A4の出力はround56と1ページも変わらない**ことを、全ページの画像を
     突き合わせて確かめてある。

Claude APIの経路は tests/test_round57_api_path.py。
"""

import tempfile

import pytest

from engine.measurements import Measurements
from engine.nesting import nest_parts
from engine.pdf_export import (
    A3_PAPER, A4_PAPER, DEFAULT_PAPER, PAPERS,
    get_paper, printed_tile_cells, render_a4_pdf, render_combined_pdf,
)
from engine.pipeline import (
    PatternForgePipeline, build_custom_panel_requests, build_garment_spec,
)
from engine.seam import finalize_part
from engine.svgpath import parse_path


MEAS = Measurements(bust=84, waist=68, hip=92, height=160,
                    sleeve_length=54, shoulder_width=37)
#: どの候補幅(110/140/150cm)にも収まらないマント。
HUGE_CAPE_CM = [(0.0, 0.0), (173.0, 0.0), (173.0, 227.0), (0.0, 227.0)]


def _pages(path):
    import pypdf

    return [p.extract_text() or "" for p in pypdf.PdfReader(path).pages]


def _cape(tmp_path, allow_split: bool):
    spec = build_garment_spec(neckline="round_neck", sleeve_style="straight",
                              skirt_style="flare")
    spec.parts.clear()
    spec.parts.extend(build_custom_panel_requests(
        "マント", HUGE_CAPE_CM, allow_split=allow_split))
    return PatternForgePipeline(output_dir=str(tmp_path)).generate_from_selection(
        spec, MEAS, skip_export=True)


# --- 6. マントの逃げ道 ------------------------------------------------------

def test_a_cape_that_does_not_fit_can_be_split_on_request(tmp_path):
    """分割を許すと、収まらなかったマントが型紙になること。"""
    kept = _cape(tmp_path, allow_split=False)
    split = _cape(tmp_path, allow_split=True)

    assert kept.nesting.unplaced, "このマントは1枚では収まらないはず"
    assert not split.nesting.unplaced, "分割しても収まっていません"
    assert len(split.finalized_parts) > len(kept.finalized_parts)


def test_a_custom_panel_is_never_split_without_being_asked(tmp_path):
    """既定では分けないこと。

    EVAフォームの装甲に勝手に縫い目を入れられては困る。
    そこに縫い目が入ってよいかは、**作る人にしか分からない**。
    """
    kept = _cape(tmp_path, allow_split=False)
    assert len(kept.finalized_parts) == 1
    assert kept.nesting.unplaced


def test_the_warning_says_how_many_panels_would_fit(tmp_path):
    """逃げ道を、具体的な枚数で言うこと。

    round56までは「採寸値を見直すか、手作業でこのパーツだけ別途作成して
    ください」だった。幅173cmのマントに**採寸値は関係がない**し、
    「手作業で」は何も解決していない。
    """
    warning = _cape(tmp_path, allow_split=False).summary()["unplaced_warnings"][0]
    assert "2枚に分けて" in warning, warning
    assert "採寸値を見直すか、手作業で" not in warning, warning
    # 分けてはいけない素材のことも書く。
    assert "EVAフォーム" in warning, warning


def test_the_screen_offers_the_split_option(client):
    js = client.get("/static/app.js").get_data(as_text=True)
    assert "収まらないときは分割する" in js
    assert "allow_split" in js


def test_the_split_choice_survives_regeneration(client):
    """分割の指定が、生成履歴からの再生成でも引き継がれること。"""
    import json

    client.post("/signup", data={"email": "split-regen@example.com",
                                 "password": "test-password-1234",
                                 "password_confirm": "test-password-1234"},
                follow_redirects=True)
    panels = json.dumps([{"label": "マント",
                           "points": [[0, 0], [173, 0], [173, 227], [0, 227]],
                           "ref_point_a": [0, 0], "ref_point_b": [173, 0],
                           "reference_cm": 173, "quantity": 1, "mirror": False,
                           "allow_split": True}], ensure_ascii=False)
    response = client.post("/api/generate", data={
        "bust": "84", "waist": "68", "hip": "92", "height": "160",
        "sleeve_length": "54", "shoulder_width": "37", "mode": "manual",
        "include_body_garment": "0", "custom_panels_json": panels})
    assert response.status_code == 200, response.get_json().get("error")
    assert response.get_json()["unplaced_count"] == 0

    import app as app_module
    with app_module.db._connect() as conn:
        row = conn.execute("SELECT spec_json FROM jobs WHERE job_id = ?",
                            (response.get_json()["job_id"],)).fetchone()
    stored = json.loads(row[0])
    assert stored["custom_panels"][0]["allow_split"] is True


# --- 7. 生地ごとのPDFを1本に ------------------------------------------------

def test_the_fabrics_can_be_combined_into_one_pdf(tmp_path):
    spec = build_garment_spec(neckline="round_neck", sleeve_style="straight",
                              skirt_style="flare")
    result = PatternForgePipeline(output_dir=str(tmp_path)).generate_from_selection(
        spec, MEAS, fabric_group_assignments={"skirt": "紺サテン"})

    combined = result.output_files.get("all_fabrics_pdf")
    assert combined, "まとめた1本のPDFが作られていません"
    pages = _pages(combined)
    heads = [t.strip().splitlines()[0] for t in pages
             if t.strip().startswith("「")]
    assert heads == ["「表地」から裁つ型紙", "「紺サテン」から裁つ型紙"], heads
    # 生地ごとの個別ファイルも**残っている**(印刷の仕方で要るものが違う)。
    assert result.output_files["pdf"]
    assert result.output_files["fabric2_pdf"]
    # 中身の枚数が、生地ごとの合計と一致すること(取りこぼしが無いこと)。
    tiles = sum(1 for t in pages if "PatternForge" in t)
    assert tiles == sum(g.sheet_count() for g in result.fabric_groups)


def test_one_fabric_does_not_get_a_combined_pdf(tmp_path):
    """1種類しか使わないときは、まとめる相手がいないので作らないこと。"""
    spec = build_garment_spec(neckline="round_neck", sleeve_style="straight",
                              skirt_style="flare")
    result = PatternForgePipeline(output_dir=str(tmp_path)).generate_from_selection(
        spec, MEAS)
    assert "all_fabrics_pdf" not in result.output_files


def test_the_combined_pdf_can_be_downloaded(client):
    response = client.post("/api/generate", data={
        "bust": "84", "waist": "68", "hip": "92", "height": "160",
        "sleeve_length": "54", "shoulder_width": "37", "mode": "manual",
        "neckline": "round_neck", "sleeve_style": "straight",
        "skirt_style": "flare", "fabric_skirt": "紺サテン"})
    assert response.status_code == 200, response.get_json().get("error")
    url = response.get_json()["download"].get("all_fabrics_pdf")
    assert url, "まとめたPDFのリンクがありません"
    assert client.get(url).status_code == 200
    js = client.get("/static/app.js").get_data(as_text=True)
    assert "all_fabrics_pdf" in js, "画面がまとめたPDFを出していません"


def test_every_section_carries_the_full_sewing_order(tmp_path):
    """どの章にも縫う順番が入っていること。

    1着の服なので、片方の章にだけ工程が無いと、その紙を見た人は
    作り方が分からなくなる。
    """
    spec = build_garment_spec(neckline="round_neck", sleeve_style="straight",
                              skirt_style="flare")
    result = PatternForgePipeline(output_dir=str(tmp_path)).generate_from_selection(
        spec, MEAS, fabric_group_assignments={"skirt": "紺サテン"})
    pages = _pages(result.output_files["all_fabrics_pdf"])
    assert sum(1 for t in pages if "縫う順番" in t) == 2, "章ごとに縫う順番が要る"


# --- 8. A3 ------------------------------------------------------------------

def test_a3_really_halves_the_number_of_sheets(tmp_path):
    spec = build_garment_spec(neckline="round_neck", sleeve_style="straight",
                              skirt_style="flare")
    pipeline = PatternForgePipeline(output_dir=str(tmp_path))
    a4 = pipeline.generate_from_selection(spec, MEAS)
    a3 = pipeline.generate_from_selection(spec, MEAS, paper="a3")

    assert a4.summary()["paper"] == "A4"
    assert a3.summary()["paper"] == "A3"
    assert a3.summary()["pdf_sheet_count"] < a4.summary()["pdf_sheet_count"] * 0.6, (
        a3.summary()["pdf_sheet_count"], a4.summary()["pdf_sheet_count"])


@pytest.mark.parametrize("paper, width_cm, height_cm", [
    (A4_PAPER, 21.0, 29.7),
    (A3_PAPER, 29.7, 42.0),
])
def test_the_page_is_physically_the_right_size(tmp_path, paper, width_cm, height_cm):
    """**1:1の実寸がすべて**なので、紙の寸法そのものを測る。"""
    import pypdf

    part = finalize_part("skirt", "flare",
                          parse_path("M 0 0 L 100 0 L 100 140 L 0 140 Z"),
                          seam_allowance_cm=1.0)
    result = nest_parts([part], fabric_width_cm=110.0)
    out = str(tmp_path / f"{paper.name}.pdf")
    render_a4_pdf(result, out, paper=paper)
    box = pypdf.PdfReader(out).pages[0].mediabox
    assert abs(float(box.width) / 72 * 2.54 - width_cm) < 0.02
    assert abs(float(box.height) / 72 * 2.54 - height_cm) < 0.02


def test_the_number_of_sheets_matches_the_pdf_for_both_papers(tmp_path):
    spec = build_garment_spec(neckline="round_neck", sleeve_style="straight",
                              skirt_style="flare")
    pipeline = PatternForgePipeline(output_dir=str(tmp_path))
    for paper_name in ("a4", "a3"):
        result = pipeline.generate_from_selection(spec, MEAS, paper=paper_name)
        tiles = [t for t in _pages(result.output_files["pdf"]) if "PatternForge" in t]
        assert result.summary()["pdf_sheet_count"] == len(tiles), paper_name


def test_an_unknown_paper_is_refused_not_silently_defaulted(client):
    with pytest.raises(ValueError):
        get_paper("b4")
    response = client.post("/api/generate", data={
        "bust": "84", "waist": "68", "hip": "92", "height": "160",
        "sleeve_length": "54", "shoulder_width": "37", "mode": "manual",
        "neckline": "round_neck", "sleeve_style": "straight",
        "skirt_style": "flare", "paper": "b4"})
    assert response.status_code == 400
    assert "用紙は" in response.get_json()["error"]


def test_the_default_is_still_a4():
    assert DEFAULT_PAPER is A4_PAPER
    assert get_paper(None) is A4_PAPER
    assert get_paper("") is A4_PAPER
    assert set(PAPERS) == {"a4", "a3"}


def test_the_usable_area_leaves_the_margin_on_both_sides():
    for paper in (A4_PAPER, A3_PAPER):
        assert abs(paper.usable_w_cm - (paper.width_cm - 2 * paper.margin_cm)) < 1e-9
        assert abs(paper.usable_h_cm - (paper.height_cm - 2 * paper.margin_cm)) < 1e-9


def test_the_tiles_cover_the_whole_layout_on_a3(tmp_path):
    """A3でも、型紙の全部の点がどこかの面に載ること。

    面が大きくなったぶん取りこぼす、ということが無いように。
    """
    spec = build_garment_spec(neckline="round_neck", sleeve_style="straight",
                              skirt_style="flare")
    result = PatternForgePipeline(output_dir=str(tmp_path)).generate_from_selection(
        spec, MEAS, paper="a3", skip_export=True)
    rows, cols, cells = printed_tile_cells(result.nesting, paper=A3_PAPER)
    printed = set(cells)
    for placed in result.nesting.placed:
        for x, y in placed.placed_cut_line():
            col = min(cols - 1, max(0, int(x // A3_PAPER.usable_w_cm)))
            row = min(rows - 1, max(0, int(y // A3_PAPER.usable_h_cm)))
            assert (row, col) in printed, (row, col)


def test_the_screen_offers_the_paper_choice(client):
    body = client.get("/").get_data(as_text=True)
    assert 'name="paper"' in body
    assert 'value="a3"' in body
    js = client.get("/static/app.js").get_data(as_text=True)
    assert "data.paper" in js, "画面が用紙名を読んでいません"


def test_a_combined_pdf_can_also_be_a3(tmp_path):
    part = finalize_part("skirt", "flare",
                          parse_path("M 0 0 L 90 0 L 90 60 L 0 60 Z"),
                          seam_allowance_cm=1.0)
    result = nest_parts([part], fabric_width_cm=110.0)
    out = str(tmp_path / "combined_a3.pdf")
    render_combined_pdf([("白", result, None), ("紺", result, None)], out,
                         paper=A3_PAPER)
    import pypdf

    box = pypdf.PdfReader(out).pages[0].mediabox
    assert abs(float(box.width) / 72 * 2.54 - 29.7) < 0.02
