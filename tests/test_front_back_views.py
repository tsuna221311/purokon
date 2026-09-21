"""round21: 前から見た絵と後ろから見た絵を区別する。

round20まで、イラストモードは「どの画像が前でどれが後ろか」をまったく
判定しておらず、後身頃は必ず前身頃と同じネックラインで追加されていた
(engine/pipeline.py の generate_from_illustration に「正直な限界」として
明記していた)。ここでは、前後を指定できるようになったことと、
**前後で首の開き幅が違うと肩線が縫い合わせられない**という新しく生じた
危険を、実際に生成して確かめる。
"""

import io

import pytest
from PIL import Image

from engine.compatibility import (
    check_seam_compatibility, shoulder_seam_length, shoulder_seams_match,
)
from engine.measurements import Measurements
from engine.pipeline import GarmentSpec, PartRequest, PatternForgePipeline
from engine.svgpath import segments_to_polyline
from engine.templates_db import TemplateDB

M = Measurements(83, 66, 91, 158, 52, 37)
NECKLINES = ("round_neck", "v_neck", "square_neck", "boat_neck", "sweetheart", "turtle_neck")


def _silhouette(part: str, variation: str, pad: float = 1.8) -> Image.Image:
    """テンプレートSVGを塗りつぶしのシルエット画像として描画する。

    tests/test_illustration_fit.py の `_template_silhouette` と同じ作り
    (「服だけが写った画像」= このアプリが推奨する入力の理想形)。
    """
    cairosvg = pytest.importorskip("cairosvg")

    with open(f"pattern_templates/{part}__{variation}.svg", encoding="utf-8") as handle:
        svg = handle.read().replace('fill="none"', 'fill="black"')
    png = cairosvg.svg2png(bytestring=svg.encode(), output_width=400,
                            background_color="white")
    body = Image.open(io.BytesIO(png)).convert("RGB")
    canvas = Image.new("RGB", (int(body.width * pad), int(body.height * pad)), "white")
    canvas.paste(body, (int(body.width * (pad - 1) / 2), int(body.height * (pad - 1) / 2)))
    return canvas


def _bodices(result) -> dict[str, str]:
    return {p.part_type: p.variation for p in result.scaled_parts
            if p.part_type in ("front_bodice", "back_bodice")}


# --- 肩線の測定そのもの -----------------------------------------------------

@pytest.mark.parametrize("part,variation,expected", [
    # 標準Mサイズのテンプレートを実測した値。ボートネックだけ首の開きが
    # 1.75倍広く、そのぶん肩線が短い。
    ("front_bodice", "round_neck", 12.79),
    ("front_bodice", "v_neck", 12.79),
    ("front_bodice", "square_neck", 12.79),
    ("front_bodice", "sweetheart", 12.79),
    ("front_bodice", "turtle_neck", 12.79),
    ("front_bodice", "boat_neck", 8.39),
    ("back_bodice", "round_neck", 12.48),
    ("back_bodice", "v_neck", 12.48),
    ("back_bodice", "square_neck", 12.48),
    ("back_bodice", "sweetheart", 12.48),
    ("back_bodice", "turtle_neck", 12.48),
    ("back_bodice", "boat_neck", 7.90),
])
def test_shoulder_seam_length_matches_the_templates(part, variation, expected):
    """肩線の測定値が、テンプレートの実測と一致すること。

    しきい値もこの値から決めているので、テンプレートを描き変えたら
    ここで気付ける(当てずっぽうの数値を置かないため)。
    """
    from types import SimpleNamespace

    segments = TemplateDB().get(part, variation)
    assert segments is not None
    measured = shoulder_seam_length(SimpleNamespace(
        part_type=part, variation=variation,
        stitch_line=segments_to_polyline(segments)))
    assert measured == pytest.approx(expected, abs=0.01)


def test_shoulder_seam_is_not_measured_on_the_zip_panel():
    """front_bodice_zip_panelでは測らずNoneを返すこと(輪郭の先頭が肩先とは限らない)。"""
    from types import SimpleNamespace

    segments = TemplateDB().get("front_bodice_zip_panel", "round_neck")
    assert segments is not None
    assert shoulder_seam_length(SimpleNamespace(
        part_type="front_bodice_zip_panel", variation="round_neck",
        stitch_line=segments_to_polyline(segments))) is None


# --- 生成後のチェッカー(チェック7) -----------------------------------------

def _generate_pair(tmp_path, front_variation, back_variation):
    pipeline = PatternForgePipeline(output_dir=str(tmp_path))
    spec = GarmentSpec(parts=[PartRequest("front_bodice", front_variation, 1),
                               PartRequest("back_bodice", back_variation, 1)])
    return pipeline.generate_from_selection(spec, M)


def test_the_standard_front_back_pair_does_not_warn(tmp_path):
    """前後を同じネックラインで作った従来どおりの組み合わせでは警告が出ないこと。

    前身頃の肩線12.79cm・後ろ身頃12.48cm(差0.31cm)は、肩下がりを前後で
    変えている設計上の差であって不整合ではない。ここが警告になってしまうと
    round20までの全パターンに警告が付く。
    """
    for variation in NECKLINES:
        result = _generate_pair(tmp_path, variation, variation)
        kinds = [w.kind for w in result.compatibility_warnings()]
        assert "shoulder_seam" not in kinds, variation


def test_mixing_boat_neck_with_another_neckline_is_caught(tmp_path):
    """首の開き幅が違う組み合わせを、生成後のチェッカーが実際に捕らえること。

    上のテストで「警告が出ないこと」を固定しているので、チェッカーが
    そもそも動いていないだけ、という状態に陥らないよう対で置いている。
    """
    for front, back in (("round_neck", "boat_neck"), ("boat_neck", "v_neck")):
        result = _generate_pair(tmp_path, front, back)
        warnings = [w for w in result.compatibility_warnings()
                    if w.kind == "shoulder_seam"]
        assert warnings, (front, back)
        assert abs(warnings[0].expected_cm - warnings[0].actual_cm) > 4.0


def test_the_guard_and_the_checker_never_disagree(tmp_path):
    """生成前のガードと生成後のチェッカーが、全組み合わせで同じ判断をすること。

    ガード(`shoulder_seams_match`)が「縫える」と言った組み合わせを
    チェッカーが警告したら、利用者は縫えない型紙を受け取ることになる。
    逆にガードが厳しすぎれば、縫える組み合わせを理由なく拒否する。
    判定を1か所に集約している(compatibility.shoulder_seams_match)ことを、
    6×6=36通りすべてで確かめる。
    """
    pipeline = PatternForgePipeline(output_dir=str(tmp_path))
    for front in NECKLINES:
        for back in NECKLINES:
            guard_says_ok = shoulder_seams_match(
                pipeline._template_shoulder_cm("front_bodice", front),
                pipeline._template_shoulder_cm("back_bodice", back))
            result = _generate_pair(tmp_path, front, back)
            checker_warned = any(w.kind == "shoulder_seam"
                                 for w in result.compatibility_warnings())
            assert guard_says_ok == (not checker_warned), (front, back)


# --- イラストモードの前後指定 -----------------------------------------------

def test_a_back_view_sets_the_back_bodice_neckline(tmp_path):
    """後ろの絵を渡すと、後身頃だけ別のネックラインになること。

    round20まではこれができず、後身頃は必ず前と同じ形になっていた。
    """
    pipeline = PatternForgePipeline(output_dir=str(tmp_path))
    result = pipeline.generate_from_illustration(
        [_silhouette("front_bodice", "v_neck"),
         _silhouette("back_bodice", "square_neck")],
        M, views=["front", "back"])
    assert _bodices(result) == {"front_bodice": "v_neck", "back_bodice": "square_neck"}
    notes = [n for n in result.measurement_warnings if "襟ぐり" in n]
    assert any("前身頃" in n and "v_neck" in n for n in notes), notes
    assert any("後ろの絵" in n and "square_neck" in n for n in notes), notes


def test_without_views_the_back_still_follows_the_front(tmp_path):
    """viewsを指定しなければ、round20までとまったく同じ動きになること。"""
    pipeline = PatternForgePipeline(output_dir=str(tmp_path))
    result = pipeline.generate_from_illustration(
        _silhouette("front_bodice", "v_neck"), M)
    assert _bodices(result) == {"front_bodice": "v_neck", "back_bodice": "v_neck"}


def test_an_unsewable_back_neckline_falls_back_and_says_why(tmp_path):
    """縫えない組み合わせを黙って出さず、前に合わせたうえで理由を開示すること。

    後ろがボートネック・前がラウンドネックだと肩線が4.89cm食い違い、
    そのままでは肩を縫い合わせられない。
    """
    pipeline = PatternForgePipeline(output_dir=str(tmp_path))
    result = pipeline.generate_from_illustration(
        [_silhouette("front_bodice", "round_neck"),
         _silhouette("back_bodice", "boat_neck")],
        M, views=["front", "back"])
    assert _bodices(result) == {"front_bodice": "round_neck", "back_bodice": "round_neck"}
    assert not any(w.kind == "shoulder_seam" for w in result.compatibility_warnings())
    excuse = [n for n in result.measurement_warnings if "肩線" in n]
    assert excuse, result.measurement_warnings
    assert "boat_neck" in excuse[0] and "round_neck" in excuse[0]


@pytest.mark.parametrize("views,message", [
    (["front"], "同じ枚数"),
    (["front", "side"], "views に指定できるのは"),
])
def test_bad_views_are_rejected_rather_than_ignored(tmp_path, views, message):
    """viewsの指定が画像と食い違っていたら、黙って無視せずエラーにすること。"""
    pipeline = PatternForgePipeline(output_dir=str(tmp_path))
    images = [_silhouette("front_bodice", "v_neck"),
              _silhouette("back_bodice", "square_neck")]
    with pytest.raises(ValueError, match=message):
        pipeline.generate_from_illustration(images, M, views=views)


# --- Web側 -------------------------------------------------------------------

def test_the_form_offers_a_back_view_field(client):
    """「後ろから見た絵」の入力欄が実際にフォームに出ていること。"""
    page = client.get("/").get_data(as_text=True)
    assert 'name="illustration_back"' in page
    assert "後ろから見た絵" in page


def test_uploading_a_back_view_through_the_web_reaches_the_back_bodice(client):
    """Webから後ろの絵を送ると、後身頃のネックラインに実際に届くこと。

    APIとUIを別々に直して片方だけ動く、という状態にならないよう、
    フォーム送信からパーツ構成までを一気に確かめる。
    """
    def _png(part, variation):
        buf = io.BytesIO()
        _silhouette(part, variation).save(buf, "PNG")
        buf.seek(0)
        return buf

    response = client.post("/api/generate", data={
        "mode": "illustration",
        "bust": "83", "waist": "66", "hip": "91",
        "height": "158", "sleeve_length": "52", "shoulder_width": "37",
        "illustration": (_png("front_bodice", "v_neck"), "front.png"),
        "illustration_back": (_png("back_bodice", "square_neck"), "back.png"),
    }, content_type="multipart/form-data")
    assert response.status_code == 200, response.get_data(as_text=True)[:400]
    payload = response.get_json()
    assert payload["ok"], payload
    # round32: 表示名は日本語になったので、機械向けの`part_type`/`variation`で
    # 見る(ここで確かめたいのは「前後で違う襟ぐりが反映されたか」であって、
    # ラベルの文言ではない)。
    pairs = {(p["part_type"], p["variation"]) for p in payload["parts"]}
    assert ("front_bodice", "v_neck") in pairs, pairs
    assert ("back_bodice", "square_neck") in pairs, pairs
    notes = [n for n in payload["measurement_warnings"] if "襟ぐり" in n]
    assert any("後ろの絵" in n and "square_neck" in n for n in notes), notes
