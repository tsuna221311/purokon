import ezdxf

from engine.dxf_export import _drop_closing_duplicate, render_dxf
from engine.nesting import nest_parts
from engine.seam import finalize_part
from engine.svgpath import parse_path


def _rect_part(part_type="front_bodice", variation="round_neck", w=20.0, h=30.0):
    segments = parse_path(f"M 0 0 L {w} 0 L {w} {h} L 0 {h} Z")
    return finalize_part(part_type, variation, segments, seam_allowance_cm=1.0)


def test_drop_closing_duplicate_removes_repeated_first_point():
    closed = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 0.0)]
    assert _drop_closing_duplicate(closed) == [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0)]


def test_drop_closing_duplicate_leaves_open_polylines_untouched():
    open_line = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0)]
    assert _drop_closing_duplicate(open_line) == open_line


def test_render_dxf_writes_a_readable_file_with_expected_layers(tmp_path):
    part = _rect_part()
    result = nest_parts([part], fabric_width_cm=110.0)
    path = render_dxf(result, str(tmp_path / "job.dxf"))

    doc = ezdxf.readfile(path)
    msp = doc.modelspace()
    layer_names = {layer.dxf.name for layer in doc.layers}
    for expected in ("CUT_LINE", "STITCH_LINE", "NOTCH", "GRAINLINE", "LABEL"):
        assert expected in layer_names

    entities_by_layer = {}
    for e in msp:
        entities_by_layer.setdefault(e.dxf.layer, []).append(e)
    assert any(e.dxftype() == "LWPOLYLINE" for e in entities_by_layer.get("CUT_LINE", []))
    assert any(e.dxftype() == "LWPOLYLINE" for e in entities_by_layer.get("STITCH_LINE", []))
    assert any(e.dxftype() == "LINE" for e in entities_by_layer.get("NOTCH", []))
    assert any(e.dxftype() == "LINE" for e in entities_by_layer.get("GRAINLINE", []))
    assert any(e.dxftype() == "TEXT" for e in entities_by_layer.get("LABEL", []))


def test_render_dxf_cut_line_matches_the_part_shape_up_to_a_y_flip(tmp_path):
    # このアプリの内部座標(Y下向き)とDXF/CADの慣習(Y上向き)の違いを
    # 吸収するため、render_dxfは全座標のYを生地の総丈から引いて反転させる。
    # その反転を除けば、書き出したCUT_LINEの形状は元のcut_lineと一致するはず。
    part = _rect_part(w=20.0, h=30.0)
    result = nest_parts([part], fabric_width_cm=110.0)
    path = render_dxf(result, str(tmp_path / "job.dxf"))

    doc = ezdxf.readfile(path)
    msp = doc.modelspace()
    cut_entities = [e for e in msp if e.dxf.layer == "CUT_LINE"]
    assert len(cut_entities) == 1
    dxf_points = [(p[0], p[1]) for p in cut_entities[0].get_points()]

    placed = result.placed[0]
    total_height = max(result.used_length_cm, 1.0)
    expected = _drop_closing_duplicate(
        [(x, total_height - y) for x, y in placed.placed_cut_line()]
    )
    assert _points_match(dxf_points, expected)


def _points_match(a, b, tol=1e-6) -> bool:
    if len(a) != len(b):
        return False
    return all(abs(ax - bx) < tol and abs(ay - by) < tol for (ax, ay), (bx, by) in zip(a, b))


def test_render_dxf_labels_every_placed_part_with_its_display_name(tmp_path):
    part_a = _rect_part("front_bodice", "round_neck", w=20.0, h=30.0)
    part_b = _rect_part("back_bodice", "round_neck", w=20.0, h=30.0)
    result = nest_parts([part_a, part_b], fabric_width_cm=110.0)
    path = render_dxf(result, str(tmp_path / "job.dxf"))

    doc = ezdxf.readfile(path)
    msp = doc.modelspace()
    labels = {e.dxf.text for e in msp if e.dxftype() == "TEXT" and e.dxf.layer == "LABEL"}
    assert labels == {p.part.display_name for p in result.placed}

    # round32: パーツ名を日本語にしたので、ASCIIだけの識別子を別レイヤーへ
    # 併記する。日本語グリフを持たないSHXフォントのCAD環境で文字化けしても、
    # どのパーツかは必ず分かるようにするため(モジュールdocstringの
    # 「正直な制約」に元から書いてあったリスクへの対応)。
    ids = {e.dxf.text for e in msp if e.dxftype() == "TEXT" and e.dxf.layer == "LABEL_ID"}
    assert ids == {p.part.identifier for p in result.placed}
    assert all(text.isascii() for text in ids), ids


def test_render_dxf_marks_rotated_parts_in_their_label():
    # render_layout_svg/render_a4_pdfと同じ「(90度回転・布目確認)」の注記が
    # DXFのラベルにも付くことを確認する(3つの出力形式で表現が食い違うと、
    # 現場でどれを信じればいいか分からなくなるため)。
    from engine.nesting import NestedPart

    part = _rect_part(w=20.0, h=30.0)
    result = nest_parts([part], fabric_width_cm=110.0)
    rotated_placed = NestedPart(part=result.placed[0].part, x=0.0, y=0.0, rotated=True)
    result.placed[0] = rotated_placed

    import tempfile
    import os
    with tempfile.TemporaryDirectory() as d:
        path = render_dxf(result, os.path.join(d, "job.dxf"))
        doc = ezdxf.readfile(path)
        msp = doc.modelspace()
        labels = [e.dxf.text for e in msp if e.dxftype() == "TEXT" and e.dxf.layer == "LABEL"]
        assert any("90度回転" in label for label in labels)


def test_render_dxf_writes_a_warning_text_for_unplaced_parts(tmp_path):
    wide_segments = parse_path("M 0 0 L 500 0 L 500 30 L 0 30 Z")
    normal_part = _rect_part()
    wide_part = finalize_part("skirt", "flare", wide_segments, seam_allowance_cm=1.0)

    result = nest_parts([normal_part, wide_part], fabric_width_cm=110.0)
    assert len(result.unplaced) == 1  # 前提: 実際にunplacedが発生していること

    path = render_dxf(result, str(tmp_path / "job.dxf"))
    doc = ezdxf.readfile(path)
    msp = doc.modelspace()
    warnings = [e.dxf.text for e in msp if e.dxftype() == "TEXT" and e.dxf.layer == "WARNING"]
    assert len(warnings) == 1
    # round32: パーツ名は日本語で書かれる(内部識別子ではない)。
    assert result.unplaced[0].display_name in warnings[0], warnings[0]
    assert "型紙に含まれていない" in warnings[0]


def test_render_dxf_has_no_warning_text_when_everything_is_placed(tmp_path):
    part = _rect_part()
    result = nest_parts([part], fabric_width_cm=110.0)
    assert result.unplaced == []

    path = render_dxf(result, str(tmp_path / "job.dxf"))
    doc = ezdxf.readfile(path)
    msp = doc.modelspace()
    warnings = [e for e in msp if e.dxf.layer == "WARNING"]
    assert warnings == []
