from collections import Counter
import io
import json
from pathlib import Path
import struct
import zipfile
from xml.etree import ElementTree as ET

import pytest
from PIL import Image, ImageDraw

from engine.accessory3d import (
    Accessory3DError, export_accessories_stl, export_vendor_package,
    normalize_order_options, validate_attachment_interface,
    validate_magnet_pockets, validate_mounting_holes,
    validate_mounting_slots,
)
from engine.custom_panel import CustomPanelSpec


def _triangles(path: Path):
    vertices = []
    for line in path.read_text(encoding="ascii").splitlines():
        words = line.strip().split()
        if words[:1] == ["vertex"]:
            vertices.append(tuple(round(float(value), 6) for value in words[1:4]))
    assert len(vertices) % 3 == 0
    return [tuple(vertices[index:index + 3]) for index in range(0, len(vertices), 3)]


def _assert_watertight(triangles):
    edges = Counter()
    for triangle in triangles:
        for start, end in zip(triangle, (triangle[1], triangle[2], triangle[0])):
            edges[tuple(sorted((start, end)))] += 1
    assert edges
    assert set(edges.values()) == {2}


def test_rectangle_exports_closed_stl_in_millimetres(tmp_path):
    spec = CustomPanelSpec("バックル", [(0, 0), (4, 0), (4, 3), (0, 3)])
    target = tmp_path / "buckle.stl"

    result = export_accessories_stl([spec], str(target), thickness_mm=2.5)

    triangles = _triangles(target)
    assert result.piece_count == 1
    assert result.triangle_count == 12
    assert result.arranged_width_mm == pytest.approx(40)
    assert result.arranged_depth_mm == pytest.approx(30)
    assert {vertex[2] for triangle in triangles for vertex in triangle} == {0.0, 2.5}
    _assert_watertight(triangles)


def test_concave_shape_is_watertight_and_preserves_notch(tmp_path):
    spec = CustomPanelSpec(
        "L字装甲", [(0, 0), (4, 0), (4, 1), (1, 1), (1, 4), (0, 4)])
    target = tmp_path / "armor.stl"

    export_accessories_stl([spec], str(target), thickness_mm=3)

    triangles = _triangles(target)
    _assert_watertight(triangles)
    # 欠けている右上領域を横切る面が作られていない。
    top_centres = [
        (sum(v[0] for v in triangle) / 3, sum(v[1] for v in triangle) / 3)
        for triangle in triangles if all(v[2] == 3 for v in triangle)
    ]
    assert all(not (x > 10 and y > 10) for x, y in top_centres)


def test_curved_accessory_is_watertight_and_has_real_surface_depth(tmp_path):
    spec = CustomPanelSpec("胸当て", [(0, 0), (8, 0), (8, 4), (0, 4)])
    target = tmp_path / "curved.stl"

    result = export_accessories_stl(
        [spec], str(target), thickness_mm=2.5,
        curvature_radius_mm=120, curve_axis="width")

    triangles = _triangles(target)
    _assert_watertight(triangles)
    z_values = {vertex[2] for triangle in triangles for vertex in triangle}
    assert len(z_values) > 2
    assert min(z_values) == 0
    assert result.curvature_radius_mm == 120


def test_double_curved_accessory_is_watertight(tmp_path):
    spec = CustomPanelSpec("胸当て", [(0, 0), (8, 0), (8, 6), (0, 6)])
    target = tmp_path / "double-curved.stl"
    result = export_accessories_stl(
        [spec], str(target), thickness_mm=3,
        curvature_radius_mm=100, curve_axis="both")
    triangles = _triangles(target)
    _assert_watertight(triangles)
    assert result.curve_axis == "both"
    assert len({round(v[2], 4) for triangle in triangles for v in triangle}) > 4
    assert any("実測" in warning for warning in result.warnings)


def test_double_curve_can_use_separate_horizontal_and_vertical_radii(tmp_path):
    spec = CustomPanelSpec("胸当て", [(0, 0), (8, 0), (8, 6), (0, 6)])
    result = export_accessories_stl(
        [spec], str(tmp_path / "compound.stl"),
        curvature_radius_mm=120, curvature_radius_height_mm=180,
        curve_axis="both")
    assert result.curvature_radius_mm == 120
    assert result.curvature_radius_height_mm == 180
    assert result.as_dict()["curvature_radius_height_mm"] == 180


def test_round_mounting_holes_are_real_watertight_through_holes(tmp_path):
    spec = CustomPanelSpec("ベルト飾り", [(0, 0), (8, 0), (8, 4), (0, 4)])
    target = tmp_path / "holes.stl"
    result = export_accessories_stl(
        [spec], str(target), thickness_mm=3,
        mounting_hole_pattern="pair_width",
        mounting_hole_diameter_mm=4, mounting_hole_inset_mm=10)

    triangles = _triangles(target)
    _assert_watertight(triangles)
    assert result.mounting_hole_pattern == "pair_width"
    assert result.mounting_hole_diameter_mm == 4
    # 穴の中心(10,20)と(70,20)を覆う上面三角形が無い。
    for centre in ((10, 20), (70, 20)):
        for triangle in triangles:
            if all(vertex[2] == 3 for vertex in triangle):
                from shapely.geometry import Point, Polygon
                assert not Polygon([(v[0], v[1]) for v in triangle]).covers(Point(*centre))


def test_mounting_hole_that_does_not_fit_is_rejected(tmp_path):
    spec = CustomPanelSpec("細い飾り", [(0, 0), (2, 0), (2, 1), (0, 1)])
    with pytest.raises(Accessory3DError, match="安全に配置できません"):
        export_accessories_stl(
            [spec], str(tmp_path / "bad-hole.stl"),
            mounting_hole_pattern="center", mounting_hole_diameter_mm=12)


def test_pair_hole_inset_must_clear_the_hole_radius():
    with pytest.raises(Accessory3DError, match="穴の半径"):
        validate_mounting_holes("pair_width", 8, 4)


def test_rounded_strap_slots_are_real_watertight_through_slots(tmp_path):
    spec = CustomPanelSpec("ベルト金具", [(0, 0), (10, 0), (10, 5), (0, 5)])
    target = tmp_path / "slots.stl"
    result = export_accessories_stl(
        [spec], str(target), thickness_mm=3,
        mounting_slot_pattern="pair_width", mounting_slot_length_mm=20,
        mounting_slot_width_mm=5, mounting_slot_axis="height",
        mounting_slot_inset_mm=15)
    triangles = _triangles(target)
    _assert_watertight(triangles)
    assert result.mounting_slot_pattern == "pair_width"
    assert result.mounting_slot_length_mm == 20
    assert result.mounting_slot_width_mm == 5
    for centre in ((15, 25), (85, 25)):
        for triangle in triangles:
            if all(vertex[2] == 3 for vertex in triangle):
                from shapely.geometry import Point, Polygon
                assert not Polygon([(v[0], v[1]) for v in triangle]).covers(Point(*centre))


def test_slot_dimensions_and_edge_clearance_are_validated():
    with pytest.raises(Accessory3DError, match="長さは幅より"):
        validate_mounting_slots("center", 5, 8, "width", None)
    with pytest.raises(Accessory3DError, match="半分より"):
        validate_mounting_slots("pair_width", 20, 5, "height", 8)


def test_magnet_pocket_is_real_watertight_non_through_recess(tmp_path):
    spec = CustomPanelSpec("磁石式バッジ", [(0, 0), (10, 0), (10, 5), (0, 5)])
    target = tmp_path / "magnet-pocket.stl"
    result = export_accessories_stl(
        [spec], str(target), thickness_mm=5,
        magnet_pocket_pattern="center", magnet_pocket_diameter_mm=12,
        magnet_pocket_depth_mm=2)

    triangles = _triangles(target)
    _assert_watertight(triangles)
    assert result.magnet_pocket_pattern == "center"
    assert result.magnet_pocket_diameter_mm == 12
    assert result.magnet_pocket_depth_mm == 2
    from shapely.geometry import Point, Polygon
    centre = Point(50, 25)
    top_faces = [Polygon([(v[0], v[1]) for v in triangle]) for triangle in triangles
                 if all(v[2] == 5 for v in triangle)]
    floor_faces = [Polygon([(v[0], v[1]) for v in triangle]) for triangle in triangles
                   if all(v[2] == 3 for v in triangle)]
    assert not any(face.covers(centre) for face in top_faces)
    assert any(face.covers(centre) for face in floor_faces)
    assert min(v[2] for triangle in triangles for v in triangle) == 0


def test_magnet_pocket_keeps_minimum_floor_and_cannot_overlap_round_hole(tmp_path):
    with pytest.raises(Accessory3DError, match="底厚が0.6mm未満"):
        validate_magnet_pockets("center", 10, 2.5, None, 3)

    spec = CustomPanelSpec("磁石式留め具", [(0, 0), (8, 0), (8, 4), (0, 4)])
    with pytest.raises(Accessory3DError, match="磁石ポケットを安全に配置できません"):
        export_accessories_stl(
            [spec], str(tmp_path / "collision.stl"), thickness_mm=5,
            mounting_hole_pattern="center", mounting_hole_diameter_mm=4,
            magnet_pocket_pattern="center", magnet_pocket_diameter_mm=10,
            magnet_pocket_depth_mm=2)


def test_curved_accessory_with_magnet_pockets_stays_watertight(tmp_path):
    spec = CustomPanelSpec("曲面磁石胸当て", [(0, 0), (10, 0), (10, 5), (0, 5)])
    target = tmp_path / "curved-magnets.stl"
    export_accessories_stl(
        [spec], str(target), thickness_mm=5,
        curvature_radius_mm=140, curve_axis="width",
        magnet_pocket_pattern="pair_width", magnet_pocket_diameter_mm=10,
        magnet_pocket_depth_mm=2, magnet_pocket_inset_mm=20)
    triangles = _triangles(target)
    _assert_watertight(triangles)
    # 曲面化後も平板の厚み2値だけにはならず、ポケットを含む閉じた曲面である。
    assert len({v[2] for triangle in triangles for v in triangle}) > 4


def test_too_tight_curvature_is_rejected_instead_of_self_intersecting(tmp_path):
    spec = CustomPanelSpec("長い装甲", [(0, 0), (20, 0), (20, 4), (0, 4)])
    with pytest.raises(Accessory3DError, match="安全に曲げられません"):
        export_accessories_stl(
            [spec], str(tmp_path / "bad.stl"),
            curvature_radius_mm=40, curve_axis="width")


def test_curve_expansion_is_checked_against_print_bed(tmp_path):
    spec = CustomPanelSpec("造形範囲ぎりぎり", [(0, 0), (22, 0), (22, 4), (0, 4)])
    with pytest.raises(Accessory3DError, match="曲面化後の配置"):
        export_accessories_stl(
            [spec], str(tmp_path / "expanded.stl"), thickness_mm=30,
            bed_width_mm=220, curvature_radius_mm=100, curve_axis="width")


def test_quantity_and_mirror_are_laid_out_as_separate_pieces(tmp_path):
    spec = CustomPanelSpec("髪飾り", [(0, 0), (2, 0), (1, 3)], quantity=2, mirror=True)
    result = export_accessories_stl([spec], str(tmp_path / "hair.stl"),
                                    bed_width_mm=220, bed_depth_mm=220)
    assert result.piece_count == 4


def test_part_larger_than_print_bed_is_rejected(tmp_path):
    spec = CustomPanelSpec("胸当て", [(0, 0), (30, 0), (30, 10), (0, 10)])
    with pytest.raises(Accessory3DError, match="収まりません"):
        export_accessories_stl([spec], str(tmp_path / "large.stl"),
                               bed_width_mm=220, bed_depth_mm=220)


def test_invalid_thickness_is_rejected(tmp_path):
    spec = CustomPanelSpec("バッジ", [(0, 0), (3, 0), (3, 3), (0, 3)])
    with pytest.raises(Accessory3DError, match="厚み"):
        export_accessories_stl([spec], str(tmp_path / "thin.stl"), thickness_mm=0.2)


def test_vendor_order_options_reject_unknown_material_and_flatten_line_breaks():
    with pytest.raises(Accessory3DError, match="素材希望"):
        normalize_order_options("unknown-material", "黒")

    profile, finish = normalize_order_options("pa12", "つや消し黒\r\n塗装済み希望\t急ぎ")
    assert profile == "pa12"
    assert finish == "つや消し黒 塗装済み希望 急ぎ"


def test_generate_endpoint_rejects_unknown_accessory_material(client):
    form = _valid_form()
    form.update({
        "include_body_garment": "0",
        "custom_panels_json": json.dumps([_panel_payload()]),
        "generate_accessory_stl": "on",
        "accessory_material_profile": "unknown-material",
    })

    response = client.post("/api/generate", data=form)

    assert response.status_code == 400
    assert "素材希望" in response.get_json()["error"]


def test_vendor_package_contains_mm_3mf_individual_binary_stl_and_order_sheet(tmp_path):
    specs = [
        CustomPanelSpec("肩飾り", [(0, 0), (4, 0), (3, 2), (0, 2)], quantity=2),
        CustomPanelSpec("髪飾り", [(0, 0), (2, 0), (1, 3)], mirror=True),
    ]
    target = tmp_path / "vendor.zip"

    result = export_vendor_package(
        specs, str(target), thickness_mm=2.5, material_profile="pa12",
        finish_note="つや消し黒、塗装済み希望")

    assert result.piece_count == 4
    with zipfile.ZipFile(target) as package:
        names = set(package.namelist())
        assert {"all_parts_mm.3mf", "manifest.json", "ORDER_NOTES_JA.txt"} <= names
        stl_names = sorted(name for name in names if name.endswith(".stl"))
        assert len(stl_names) == 4
        manifest = json.loads(package.read("manifest.json"))
        assert manifest["units"] == "mm"
        assert manifest["piece_count"] == 4
        assert manifest["files"][0]["shell_count"] == 1
        assert manifest["files"][0]["watertight"] is True
        assert "PA12" in manifest["material_request"]
        assert manifest["finish_request"] == "つや消し黒、塗装済み希望"
        notes = package.read("ORDER_NOTES_JA.txt").decode("utf-8-sig")
        assert "STLは形式上単位を保持しない" in notes

        first_stl = package.read(stl_names[0])
        triangle_count = struct.unpack("<I", first_stl[80:84])[0]
        assert len(first_stl) == 84 + triangle_count * 50

        with zipfile.ZipFile(io.BytesIO(package.read("all_parts_mm.3mf"))) as three_mf:
            model = ET.fromstring(three_mf.read("3D/3dmodel.model"))
            assert model.attrib["unit"] == "millimeter"
            namespace = {"m": "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"}
            assert len(model.findall(".//m:object", namespace)) == 4


def test_vendor_package_records_user_specified_curvature(tmp_path):
    spec = CustomPanelSpec("肩当て", [(0, 0), (6, 0), (6, 4), (0, 4)])
    target = tmp_path / "curved_vendor.zip"

    export_vendor_package(
        [spec], str(target), curvature_radius_mm=100, curve_axis="height")

    with zipfile.ZipFile(target) as package:
        manifest = json.loads(package.read("manifest.json"))
        assert manifest["curvature"] == {
            "type": "cylindrical", "inner_radius_mm": 100.0, "axis": "height"}
        assert manifest["arranged_3mf_dimensions_mm"]["z"] > manifest["thickness_mm"]
        assert manifest["files"][0]["dimensions_mm"]["z"] > manifest["thickness_mm"]
        notes = package.read("ORDER_NOTES_JA.txt").decode("utf-8-sig")
        assert "内側半径100mm" in notes
        assert "縦方向" in notes


def test_vendor_package_records_mounting_holes(tmp_path):
    spec = CustomPanelSpec("留め具", [(0, 0), (8, 0), (8, 4), (0, 4)])
    target = tmp_path / "hole_vendor.zip"
    export_vendor_package(
        [spec], str(target), mounting_hole_pattern="pair_width",
        mounting_hole_diameter_mm=4, mounting_hole_inset_mm=10)
    with zipfile.ZipFile(target) as package:
        manifest = json.loads(package.read("manifest.json"))
        assert manifest["mounting_holes"] == {
            "pattern": "pair_width", "diameter_mm": 4.0,
            "edge_inset_mm": 10.0, "through_hole": True}
        notes = package.read("ORDER_NOTES_JA.txt").decode("utf-8-sig")
        assert "直径4mm" in notes
        assert "丸い貫通穴" in notes


def test_commercial_hardware_interfaces_map_to_dimensioned_holes():
    assert validate_attachment_interface("sew_on_clip", 3, 10) == (
        "sew_on_clip", "pair_width", 3.0, 10.0)
    assert validate_attachment_interface("brooch_pin", 2, 8) == (
        "brooch_pin", "pair_width", 2.0, 8.0)
    assert validate_attachment_interface("pivot_joint", 5, None) == (
        "pivot_joint", "center", 5.0, None)


def test_vendor_package_records_hardware_interface_without_claiming_hardware_is_printed(tmp_path):
    spec = CustomPanelSpec("可動肩装甲", [(0, 0), (8, 0), (8, 5), (0, 5)])
    target = tmp_path / "pivot_vendor.zip"
    result = export_accessories_stl(
        [spec], str(tmp_path / "pivot.stl"),
        mounting_hole_pattern="center", mounting_hole_diameter_mm=5,
        attachment_interface="pivot_joint")
    assert result.attachment_interface == "pivot_joint"
    _assert_watertight(_triangles(tmp_path / "pivot.stl"))
    export_vendor_package(
        [spec], str(target), mounting_hole_pattern="center",
        mounting_hole_diameter_mm=5, attachment_interface="pivot_joint")
    with zipfile.ZipFile(target) as package:
        manifest = json.loads(package.read("manifest.json"))
        assert manifest["attachment_interface"] == {
            "type": "pivot_joint", "uses_mounting_holes": True,
            "hardware_included": False}
        notes = package.read("ORDER_NOTES_JA.txt").decode("utf-8-sig")
        assert "pivot_joint" in notes
        assert "市販金具を別途用意" in notes


def test_vendor_package_records_strap_slots(tmp_path):
    spec = CustomPanelSpec("ベルト金具", [(0, 0), (10, 0), (10, 5), (0, 5)])
    target = tmp_path / "slot_vendor.zip"
    export_vendor_package(
        [spec], str(target), mounting_slot_pattern="pair_width",
        mounting_slot_length_mm=20, mounting_slot_width_mm=5,
        mounting_slot_axis="height", mounting_slot_inset_mm=15)
    with zipfile.ZipFile(target) as package:
        manifest = json.loads(package.read("manifest.json"))
        assert manifest["mounting_slots"] == {
            "pattern": "pair_width", "length_mm": 20.0, "width_mm": 5.0,
            "axis": "height", "edge_inset_mm": 15.0, "through_slot": True}
        notes = package.read("ORDER_NOTES_JA.txt").decode("utf-8-sig")
        assert "20×5mm" in notes
        assert "縦向き" in notes


def test_vendor_package_records_non_through_magnet_pockets(tmp_path):
    spec = CustomPanelSpec("磁石式胸章", [(0, 0), (10, 0), (10, 5), (0, 5)])
    target = tmp_path / "magnet_vendor.zip"
    export_vendor_package(
        [spec], str(target), thickness_mm=5,
        magnet_pocket_pattern="pair_width", magnet_pocket_diameter_mm=10,
        magnet_pocket_depth_mm=2, magnet_pocket_inset_mm=15)
    with zipfile.ZipFile(target) as package:
        manifest = json.loads(package.read("manifest.json"))
        assert manifest["magnet_pockets"] == {
            "pattern": "pair_width", "diameter_mm": 10.0,
            "depth_mm": 2.0, "edge_inset_mm": 15.0,
            "through_hole": False, "non_through": True,
            "minimum_remaining_floor_mm": 0.6}
        notes = package.read("ORDER_NOTES_JA.txt").decode("utf-8-sig")
        assert "直径10mm" in notes
        assert "深さ2mm" in notes
        assert "非貫通" in notes


def _valid_form():
    return {
        "bust": "84", "waist": "68", "hip": "92", "height": "160",
        "sleeve_length": "54", "shoulder_width": "37", "mode": "manual",
        "neckline": "round_neck", "sleeve_style": "straight", "skirt_style": "flare",
    }


def _panel_payload():
    return {
        "label": "バックル",
        "points": [[0, 0], [100, 0], [100, 50], [0, 50]],
        "ref_point_a": [0, 0], "ref_point_b": [100, 0],
        "reference_cm": 4,
        "quantity": 1, "mirror": False,
    }


def _illustration_png():
    image = Image.new("RGB", (500, 700), "white")
    draw = ImageDraw.Draw(image)
    draw.polygon([(180, 100), (320, 100), (350, 220), (330, 420),
                  (390, 650), (110, 650), (170, 420), (150, 220)],
                 fill=(60, 80, 130))
    buffer = io.BytesIO()
    image.save(buffer, "PNG")
    buffer.seek(0)
    return buffer


def test_generate_endpoint_returns_downloadable_stl(client):
    form = _valid_form()
    form.update({
        "include_body_garment": "0",
        "custom_panels_json": json.dumps([_panel_payload()]),
        "generate_accessory_stl": "on",
        "accessory_thickness_mm": "2.4",
        "accessory_bed_width_mm": "220",
        "accessory_bed_depth_mm": "220",
    })

    response = client.post("/api/generate", data=form)

    assert response.status_code == 200
    data = response.get_json()
    assert data["accessory_3d"]["piece_count"] == 1
    assert data["accessory_3d"]["thickness_mm"] == 2.4
    assert data["download"]["stl"].endswith("/stl")
    assert data["download"]["vendor_zip"].endswith("/vendor_zip")
    assert data["accessory_3d"]["vendor_package"]["units"] == "mm"
    download = client.get(data["download"]["stl"])
    assert download.status_code == 200
    assert download.data.startswith(b"solid patternforge_accessories")
    vendor_download = client.get(data["download"]["vendor_zip"])
    assert vendor_download.status_code == 200
    with zipfile.ZipFile(io.BytesIO(vendor_download.data)) as package:
        assert "all_parts_mm.3mf" in package.namelist()


def test_generate_endpoint_preserves_curvature_in_result_and_vendor_zip(client):
    form = _valid_form()
    form.update({
        "include_body_garment": "0",
        "custom_panels_json": json.dumps([_panel_payload()]),
        "generate_accessory_stl": "on",
        "accessory_curvature_radius_mm": "90",
        "accessory_curve_axis": "height",
    })

    response = client.post("/api/generate", data=form)

    assert response.status_code == 200
    data = response.get_json()
    assert data["accessory_3d"]["curvature_radius_mm"] == 90
    assert data["accessory_3d"]["curve_axis"] == "height"
    vendor_download = client.get(data["download"]["vendor_zip"])
    with zipfile.ZipFile(io.BytesIO(vendor_download.data)) as package:
        manifest = json.loads(package.read("manifest.json"))
        assert manifest["curvature"]["inner_radius_mm"] == 90
        assert manifest["curvature"]["axis"] == "height"


def test_generate_endpoint_preserves_mounting_holes_in_result_and_vendor_zip(client):
    form = _valid_form()
    form.update({
        "include_body_garment": "0",
        "custom_panels_json": json.dumps([_panel_payload()]),
        "generate_accessory_stl": "on",
        "accessory_mounting_hole_pattern": "pair_width",
        "accessory_mounting_hole_diameter_mm": "3",
        "accessory_mounting_hole_inset_mm": "8",
    })
    response = client.post("/api/generate", data=form)
    assert response.status_code == 200, response.get_json().get("error")
    data = response.get_json()
    assert data["accessory_3d"]["mounting_hole_pattern"] == "pair_width"
    assert data["accessory_3d"]["mounting_hole_diameter_mm"] == 3
    with zipfile.ZipFile(io.BytesIO(client.get(data["download"]["vendor_zip"]).data)) as package:
        manifest = json.loads(package.read("manifest.json"))
        assert manifest["mounting_holes"]["diameter_mm"] == 3


def test_generate_endpoint_preserves_strap_slots_in_result_and_vendor_zip(client):
    form = _valid_form()
    form.update({
        "include_body_garment": "0",
        "custom_panels_json": json.dumps([_panel_payload()]),
        "generate_accessory_stl": "on",
        "accessory_mounting_slot_pattern": "center",
        "accessory_mounting_slot_length_mm": "12",
        "accessory_mounting_slot_width_mm": "3",
        "accessory_mounting_slot_axis": "width",
    })
    response = client.post("/api/generate", data=form)
    assert response.status_code == 200, response.get_json().get("error")
    data = response.get_json()
    assert data["accessory_3d"]["mounting_slot_pattern"] == "center"
    assert data["accessory_3d"]["mounting_slot_length_mm"] == 12
    with zipfile.ZipFile(io.BytesIO(client.get(data["download"]["vendor_zip"]).data)) as package:
        manifest = json.loads(package.read("manifest.json"))
        assert manifest["mounting_slots"]["length_mm"] == 12


def test_generate_endpoint_preserves_magnet_pockets_in_result_and_vendor_zip(client):
    form = _valid_form()
    form.update({
        "include_body_garment": "0",
        "custom_panels_json": json.dumps([_panel_payload()]),
        "generate_accessory_stl": "on",
        "accessory_thickness_mm": "5",
        "accessory_magnet_pocket_pattern": "center",
        "accessory_magnet_pocket_diameter_mm": "10",
        "accessory_magnet_pocket_depth_mm": "2",
    })
    response = client.post("/api/generate", data=form)
    assert response.status_code == 200, response.get_json().get("error")
    data = response.get_json()
    assert data["accessory_3d"]["magnet_pocket_pattern"] == "center"
    assert data["accessory_3d"]["magnet_pocket_diameter_mm"] == 10
    assert data["accessory_3d"]["magnet_pocket_depth_mm"] == 2
    with zipfile.ZipFile(io.BytesIO(client.get(data["download"]["vendor_zip"]).data)) as package:
        manifest = json.loads(package.read("manifest.json"))
        assert manifest["magnet_pockets"]["non_through"] is True
        assert manifest["magnet_pockets"]["depth_mm"] == 2


def test_illustration_mode_combines_garment_custom_panel_and_stl(client):
    left_panel = _panel_payload()
    right_panel = _panel_payload()
    right_panel.update({
        "label": "バックル右",
        "points": [[0, 0], [90, 0], [85, 55], [0, 50]],
    })
    form = _valid_form()
    form.update({
        "mode": "illustration",
        "illustration_stage": "production",
        "illustration": (_illustration_png(), "front.png"),
        "illustration_neckline": "round_neck",
        "illustration_back_neckline": "round_neck",
        "illustration_sleeve_style": "straight",
        "illustration_skirt_style": "flare",
        "illustration_pants_style": "none",
        "illustration_collar_style": "none",
        "illustration_cuffs_style": "none",
        "illustration_waistband_style": "none",
        "illustration_hood": "no",
        "illustration_closure": "none",
        "illustration_symmetry": "asymmetric",
        "illustration_internal_support": "armor_base",
        "illustration_movement": "standard",
        "custom_panels_json": json.dumps([left_panel, right_panel]),
        "generate_accessory_stl": "on",
        "accessory_thickness_mm": "3",
        "accessory_bed_width_mm": "220",
        "accessory_bed_depth_mm": "220",
    })
    response = client.post("/api/generate", data=form,
                           content_type="multipart/form-data")
    assert response.status_code == 200, response.get_json().get("error")
    data = response.get_json()
    assert any(part["part_type"] == "custom_panel" for part in data["parts"])
    assert any(part["part_type"] == "front_bodice" for part in data["parts"])
    assert data["download"]["stl"].endswith("/stl")
    assert data["download"]["vendor_zip"].endswith("/vendor_zip")


def test_generate_endpoint_requires_custom_panel_for_stl(client):
    form = _valid_form()
    form["generate_accessory_stl"] = "on"
    response = client.post("/api/generate", data=form)
    assert response.status_code == 400
    assert "カスタムパーツ" in response.get_json()["error"]


def test_generate_without_3d_option_does_not_offer_stl(client):
    form = _valid_form()
    form["custom_panels_json"] = json.dumps([_panel_payload()])
    response = client.post("/api/generate", data=form)
    assert response.status_code == 200
    assert "stl" not in response.get_json()["download"]
    assert "vendor_zip" not in response.get_json()["download"]


def test_regenerate_keeps_accessory_stl_setting(client):
    signup = client.post(
        "/signup",
        data={"email": "accessory3d@example.com", "password": "password123"},
        follow_redirects=True,
    )
    assert signup.status_code == 200
    form = _valid_form()
    form.update({
        "include_body_garment": "0",
        "custom_panels_json": json.dumps([_panel_payload()]),
        "generate_accessory_stl": "on",
        "accessory_thickness_mm": "3",
        "accessory_bed_width_mm": "220",
        "accessory_bed_depth_mm": "220",
    })
    generated = client.post("/api/generate", data=form).get_json()

    response = client.post(
        f"/account/jobs/{generated['job_id']}/regenerate", follow_redirects=True)

    assert response.status_code == 200
    assert "3D小物STL" in response.get_data(as_text=True)
