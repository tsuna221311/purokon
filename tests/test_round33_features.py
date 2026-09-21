"""round33: 型紙は出るのに服が完成しない、3つの原因を潰す。

1. 印刷倍率がずれても気づけない  -> 検定スクエア(1辺5cmの正方形)
2. 縫う順番がどこにも書いていない -> 縫製手順ページ(PDFにも入れる)
3. 採寸ミスの指摘が生成後にしか出ない -> 入力時のチェック

どれも「型紙の形」ではなく「型紙を使って服が出来上がるまで」の穴で、
round32までの改良(製図の正しさ・画面の使いやすさ)では埋まらなかった。
"""

import pathlib
import re

import pytest

from engine.assembly import AssemblyStep, assembly_steps
from engine.cutting import cutting_note, interfacing_note, needs_interfacing
from engine.measurements import Measurements
from engine.pipeline import PatternForgePipeline, build_garment_spec
from engine.plausibility import measurement_hints

STANDARD = Measurements(84, 68, 92, 160, 54, 37)


def _generate(tmp_path, **spec_kwargs):
    pipeline = PatternForgePipeline(output_dir=str(tmp_path))
    spec = build_garment_spec(**spec_kwargs)
    return pipeline.generate_from_selection(spec, STANDARD)


# --- 1) 検定スクエア ---------------------------------------------------------

def test_the_pdf_carries_a_square_that_is_exactly_five_centimetres(tmp_path):
    """PDFに、1辺ちょうど5.0cmの正方形が入っていること。

    【なぜ必要か】この型紙は「実寸1:1で印刷してそのまま裁断に使える」ことを
    中心的な主張にしているのに、PDFにあったのは「倍率100%で印刷してください」
    という**お願いの文だけ**で、実際にそうなったかを確かめる手段が無かった。
    家庭用プリンタの既定は多くが「用紙に合わせる」で、A4原稿をA4に印刷しても
    数%縮む機種がある。縮んだことに気づくのは布を裁ったあと。

    ここではPDFの内容ストリームを読み、5cm四方の矩形が実際に描かれている
    ことを座標で確かめる(見た目の確認ではなく寸法そのものを見る)。
    """
    pypdf = pytest.importorskip("pypdf")
    from reportlab.lib.units import cm

    from engine.pdf_export import SCALE_CHECK_SQUARE_CM

    result = _generate(tmp_path)
    reader = pypdf.PdfReader(result.output_files["pdf"])
    data = reader.pages[0].get_contents().get_data().decode("latin-1")
    rects = re.findall(r"([-\d.]+) ([-\d.]+) ([-\d.]+) ([-\d.]+) re", data)
    squares = [(float(w), float(h)) for _x, _y, w, h in rects
               if abs(float(w) - float(h)) < 0.05]
    target = SCALE_CHECK_SQUARE_CM * cm
    assert any(abs(w - target) < 0.05 for w, _h in squares), \
        f"1辺{SCALE_CHECK_SQUARE_CM}cmの正方形が見つからない: {squares}"


def test_the_pdf_says_how_to_use_that_square(tmp_path):
    """四角の使い方(定規で測る)が、同じページに文字で書いてあること。

    四角だけあっても、何のためのものか分からなければ測ってもらえない。
    """
    pypdf = pytest.importorskip("pypdf")
    result = _generate(tmp_path)
    text = pypdf.PdfReader(result.output_files["pdf"]).pages[0].extract_text() or ""
    assert "印刷倍率の確認" in text
    assert "定規" in text and "5.0cm" in text


# --- 2) 縫製手順 -------------------------------------------------------------

def test_the_steps_only_mention_parts_that_exist(tmp_path):
    """選んでいないパーツの工程が出ないこと。

    (袖なしで作ったのに「袖を身頃に付ける」と書いてあったら、手順書として
     信用されなくなる。)
    """
    result = _generate(tmp_path, sleeve_style=None, skirt_style=None)
    titles = [s.title for s in result.assembly_steps()]
    assert not any("袖" in t for t in titles), titles
    assert not any("スカート" in t for t in titles), titles
    assert "肩線を縫う" in titles and "脇線を縫う" in titles


def test_the_steps_are_numbered_without_gaps(tmp_path):
    """出た工程だけで1から連番になっていること。"""
    for kwargs in ({}, {"sleeve_style": None}, {"skirt_style": None},
                   {"include_collar": True, "include_cuffs": True},
                   {"princess_line": True}):
        steps = _generate(tmp_path, **kwargs).assembly_steps()
        assert [s.number for s in steps] == list(range(1, len(steps) + 1)), kwargs


def test_the_sleeve_step_carries_the_measured_ease(tmp_path):
    """袖付けの工程に、この型紙の実際のいせ込み量(cm)が入っていること。

    一般的な洋裁書を書き写しただけなら「少し縮めます」としか書けない。
    このエンジンは袖ぐりを測っていて、いせ量を知っている(round31)ので、
    数字で書ける。ここがこの手順書の存在意義なので、失われたら気づきたい。
    """
    from engine.compatibility import armhole_length, sleeve_cap_ease_cm

    result = _generate(tmp_path)
    parts = {p.part_type: p for p in result.finalized_parts}
    per_arm = (armhole_length(parts["front_bodice"])
               + armhole_length(parts["back_bodice"])) / 2.0
    expected = f"{sleeve_cap_ease_cm(per_arm):.1f}cm"
    step = next(s for s in result.assembly_steps() if s.title == "袖を身頃に付ける")
    assert expected in step.detail, (expected, step.detail)


def test_the_sleeve_is_made_into_a_tube_before_it_is_attached(tmp_path):
    """袖を筒にする工程が、袖付けより前にあること(出典どおりの順)。

    出典: MAISON DE AS「セットインスリーブ(基本袖)の縫い方」——袖下を先に
    縫って筒にし、いせを縮めてから身頃へ付ける。
    """
    titles = [s.title for s in _generate(tmp_path).assembly_steps()]
    assert titles.index("袖を筒にする") < titles.index("袖を身頃に付ける")


def test_the_front_zip_is_attached_before_the_shoulder_and_side(tmp_path):
    """前開きファスナーが、肩線・脇線より前にあること。

    身頃が筒になってからでは中心前にミシンを入れにくい。出典(うさこの
    洋裁工房)の順番でも、ファスナーは「肩と脇」より前に付ける。
    """
    result = _generate(tmp_path, front_zip=True, skirt_style=None)
    titles = [s.title for s in result.assembly_steps()]
    assert "前開きファスナーを付ける" in titles, titles
    assert titles.index("前開きファスナーを付ける") < titles.index("肩線を縫う")
    assert titles.index("前開きファスナーを付ける") < titles.index("脇線を縫う")


def test_the_steps_reach_the_printed_pdf(tmp_path):
    """手順が、実際に印刷するPDFの文字として入っていること。

    縫うときに見ているのは布と紙であってブラウザではない。
    """
    pypdf = pytest.importorskip("pypdf")
    from engine import pdf_export
    if pdf_export._LABEL_FONT == "Helvetica":
        pytest.skip("この環境では日本語フォントが読み込めていない")

    result = _generate(tmp_path)
    text = "".join(page.extract_text() or ""
                   for page in pypdf.PdfReader(result.output_files["pdf"]).pages)
    assert "縫う順番" in text
    for step in result.assembly_steps():
        assert step.title in text, step.title


def test_a_bodice_only_pattern_still_gets_the_basics(tmp_path):
    """身頃だけでも、印付け・肩・脇・裾の工程は出ること。"""
    steps = _generate(tmp_path, sleeve_style=None, skirt_style=None).assembly_steps()
    titles = [s.title for s in steps]
    assert titles[0] == "印を付ける"
    assert titles[-1] == "裾を始末する"


def test_no_step_is_empty():
    """全工程が、本文を持っていること(見出しだけの工程を作らない)。"""
    from types import SimpleNamespace

    fake = [SimpleNamespace(part_type=pt, display_name=pt, label_suffix="",
                            dart_count=0)
            for pt in ("front_bodice", "back_bodice", "sleeve", "skirt",
                        "collar", "cuffs", "waistband")]
    for step in assembly_steps(fake, sleeve_cap_ease_cm=2.0):
        assert isinstance(step, AssemblyStep)
        assert step.title and len(step.detail) > 10, step


# --- 接着芯: 全面か一部か ----------------------------------------------------

def test_the_zip_panel_is_only_interfaced_at_the_facing():
    """前開きパネルは「見返し部分」だけに芯を貼ると書くこと。

    【round31で雑だった点】このパーツを「接着芯あり」の集合に入れていたので
    「表地1枚 わ裁ち不要 接着芯あり」と印字されていた。中身は**身頃の半身に
    見返しが付いた形**なので、そのまま読むと前身頃全体に芯を貼ることになり、
    板のように固い前身頃が出来上がる。
    """
    assert needs_interfacing("front_bodice_zip_panel")
    assert interfacing_note("front_bodice_zip_panel") == "見返し部分に接着芯"
    assert "見返し部分に接着芯" in cutting_note("front_bodice_zip_panel")
    # 衿・カフス・ウエストバンドは従来どおり全面。
    for part_type in ("collar", "cuffs", "waistband"):
        assert interfacing_note(part_type) == "接着芯あり", part_type
    assert interfacing_note("front_bodice") == ""


# --- 3) 採寸値のチェック -----------------------------------------------------

def test_a_normal_body_gets_no_hint():
    """標準的な採寸では何も言わないこと。

    (常に何か出るなら、出たときに読んでもらえない。)
    """
    assert measurement_hints(STANDARD) == []
    assert measurement_hints(Measurements(95, 78, 102, 168, 57, 40)) == []


def test_swapping_bust_and_waist_is_flagged():
    """バストとウエストを逆に入れた疑いを指摘すること。"""
    hints = measurement_hints(Measurements(68, 84, 92, 160, 54, 37))
    assert any(h.field == "waist" and "取り違え" in h.message for h in hints), hints


def test_a_hip_narrower_than_the_waist_is_flagged():
    """ヒップがウエストより細い入力を指摘すること(履けない)。"""
    hints = measurement_hints(Measurements(84, 68, 60, 160, 54, 37))
    assert any(h.field == "hip" and "履く" in h.message for h in hints), hints


def test_a_shoulder_too_narrow_for_the_bust_is_flagged():
    """バストに対して肩幅が狭い入力を、生成する前に指摘すること。

    round31では同じ内容を**生成後**にしか出していなかった。
    """
    hints = measurement_hints(Measurements(120, 100, 125, 160, 54, 37))
    assert any(h.field == "shoulder_width" and "肩幅" in h.message for h in hints), hints


def test_an_out_of_range_value_says_what_it_will_become():
    """変形範囲の外なら、実際には何cm相当になるかを言うこと。"""
    hints = measurement_hints(Measurements(155, 100, 130, 160, 54, 37))
    bust_hints = [h for h in hints if h.field == "bust"]
    assert bust_hints and bust_hints[0].severity == "warning"
    assert "132.8cm" in bust_hints[0].message, bust_hints[0].message


def test_the_hint_never_says_the_input_is_wrong():
    """文面が「間違っています」と断定しないこと。

    測り間違いでない体型も当然あるので、断定は失礼であり、かつ誤りうる。
    """
    bodies = [
        Measurements(68, 84, 92, 160, 54, 37),
        Measurements(84, 68, 60, 160, 54, 37),
        Measurements(120, 100, 125, 160, 54, 37),
        Measurements(155, 100, 130, 160, 54, 37),
        Measurements(84, 68, 92, 160, 32, 37),
    ]
    for m in bodies:
        for hint in measurement_hints(m):
            assert "間違っています" not in hint.message, hint.message
            assert any(word in hint.message
                       for word in ("確かめ", "確認", "できます")), hint.message


def test_the_check_endpoint_does_not_consume_a_generation(client):
    """チェックAPIが、1日の生成回数を消費しないこと。"""
    form = {"bust": "68", "waist": "84", "hip": "92", "height": "160",
            "sleeve_length": "54", "shoulder_width": "37"}
    before = client.get("/").get_data(as_text=True)
    response = client.post("/api/measurements/check", data=form)
    assert response.status_code == 200
    data = response.get_json()
    assert data["ok"] is True and data["hints"]
    after = client.get("/").get_data(as_text=True)
    # 「本日の生成回数」欄の N が変わっていないこと(HTMLでは
    # 見出しと数値の間に改行とspanが挟まるので、id側から拾う)。
    pattern = r'id="usage-note-text">\s*(\d+)\s*/'
    assert re.search(pattern, before).group(1) == re.search(pattern, after).group(1)


def test_the_check_endpoint_is_quiet_about_an_incomplete_form(client):
    """値が有効範囲の外でも、例外ではなくメッセージで返すこと。

    入力途中の欄でHTTP 500になると、打っている最中にエラーが出続ける。
    """
    form = {"bust": "5", "waist": "68", "hip": "92", "height": "160",
            "sleeve_length": "54", "shoulder_width": "37"}
    response = client.post("/api/measurements/check", data=form)
    assert response.status_code == 200
    assert response.get_json()["ok"] is True


def test_the_form_shows_the_hints_and_the_steps(client):
    """画面側に、指摘欄と縫う順番の置き場所があること。"""
    html = client.get("/").get_data(as_text=True)
    assert 'id="measurement-hints"' in html
    assert 'id="assembly-steps"' in html
    js = (pathlib.Path(__file__).resolve().parent.parent
          / "web" / "static" / "app.js").read_text(encoding="utf-8")
    assert "/api/measurements/check" in js
    assert "renderAssemblySteps" in js
