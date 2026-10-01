"""校正済みの平面パーツを3Dプリンター用メッシュへ変換する。

輪郭を押し出した平板、または利用者が指定した半径で一方向／二方向に曲げた小物を
生成する。身体の曲率を画像から推測はしない。単位は入力がcm、出力がmm。
"""

from __future__ import annotations

import math
import os
import hashlib
import io
import json
import struct
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from xml.etree import ElementTree as ET

from shapely.geometry import LineString, Point, Polygon
from shapely.geometry.polygon import orient

from .custom_panel import CustomPanelSpec, mirror_points_x


MIN_THICKNESS_MM = 0.8
MAX_THICKNESS_MM = 30.0
MIN_BED_MM = 50.0
MAX_BED_MM = 1000.0
PART_GAP_MM = 5.0
MIN_CURVATURE_RADIUS_MM = 20.0
MAX_CURVATURE_RADIUS_MM = 2000.0
CURVE_AXES = {"width", "height", "both"}
MOUNTING_HOLE_PATTERNS = {"none", "center", "pair_width", "pair_height"}
MIN_HOLE_DIAMETER_MM = 1.0
MAX_HOLE_DIAMETER_MM = 30.0
MIN_HOLE_INSET_MM = 2.0
MAX_HOLE_INSET_MM = 100.0
MOUNTING_SLOT_PATTERNS = {"none", "center", "pair_width", "pair_height"}
MOUNTING_SLOT_AXES = {"width", "height"}
MIN_SLOT_LENGTH_MM = 5.0
MAX_SLOT_LENGTH_MM = 120.0
MIN_SLOT_WIDTH_MM = 2.0
MAX_SLOT_WIDTH_MM = 40.0
MAGNET_POCKET_PATTERNS = {"none", "center", "pair_width", "pair_height"}
ATTACHMENT_INTERFACES = {"none", "sew_on_clip", "brooch_pin", "pivot_joint"}
MIN_MAGNET_DIAMETER_MM = 3.0
MAX_MAGNET_DIAMETER_MM = 50.0
MIN_MAGNET_DEPTH_MM = 0.5


class Accessory3DError(ValueError):
    """3D小物の入力または配置が成立しない場合。"""


@dataclass(frozen=True)
class Accessory3DResult:
    path: str
    piece_count: int
    thickness_mm: float
    arranged_width_mm: float
    arranged_depth_mm: float
    triangle_count: int
    curvature_radius_mm: float | None = None
    curvature_radius_height_mm: float | None = None
    curve_axis: str = "width"
    mounting_hole_pattern: str = "none"
    mounting_hole_diameter_mm: float | None = None
    mounting_slot_pattern: str = "none"
    mounting_slot_length_mm: float | None = None
    mounting_slot_width_mm: float | None = None
    mounting_slot_axis: str = "width"
    magnet_pocket_pattern: str = "none"
    magnet_pocket_diameter_mm: float | None = None
    magnet_pocket_depth_mm: float | None = None
    attachment_interface: str = "none"
    warnings: tuple[str, ...] = ()

    def as_dict(self) -> dict:
        return {
            "piece_count": self.piece_count,
            "thickness_mm": round(self.thickness_mm, 2),
            "arranged_width_mm": round(self.arranged_width_mm, 1),
            "arranged_depth_mm": round(self.arranged_depth_mm, 1),
            "triangle_count": self.triangle_count,
            "curvature_radius_mm": (
                round(self.curvature_radius_mm, 2)
                if self.curvature_radius_mm is not None else None
            ),
            "curvature_radius_height_mm": (
                round(self.curvature_radius_height_mm, 2)
                if self.curvature_radius_height_mm is not None else None
            ),
            "curve_axis": self.curve_axis,
            "mounting_hole_pattern": self.mounting_hole_pattern,
            "mounting_hole_diameter_mm": self.mounting_hole_diameter_mm,
            "mounting_slot_pattern": self.mounting_slot_pattern,
            "mounting_slot_length_mm": self.mounting_slot_length_mm,
            "mounting_slot_width_mm": self.mounting_slot_width_mm,
            "mounting_slot_axis": self.mounting_slot_axis,
            "magnet_pocket_pattern": self.magnet_pocket_pattern,
            "magnet_pocket_diameter_mm": self.magnet_pocket_diameter_mm,
            "magnet_pocket_depth_mm": self.magnet_pocket_depth_mm,
            "attachment_interface": self.attachment_interface,
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True)
class VendorPackageResult:
    path: str
    piece_count: int
    file_count: int
    package_size_bytes: int

    def as_dict(self) -> dict:
        return {
            "piece_count": self.piece_count,
            "file_count": self.file_count,
            "package_size_bytes": self.package_size_bytes,
            "units": "mm",
            "primary_format": "3MF",
            "fallback_format": "binary STL",
        }


def _finite_in_range(value: object, name: str, lower: float, upper: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise Accessory3DError(f"{name}は数値で指定してください。") from None
    if not math.isfinite(number) or not lower <= number <= upper:
        raise Accessory3DError(f"{name}は{lower:g}〜{upper:g}mmの範囲で指定してください。")
    return number


def validate_accessory_settings(thickness_mm: object, bed_width_mm: object,
                                bed_depth_mm: object) -> tuple[float, float, float]:
    return (
        _finite_in_range(thickness_mm, "厚み", MIN_THICKNESS_MM, MAX_THICKNESS_MM),
        _finite_in_range(bed_width_mm, "造形範囲の幅", MIN_BED_MM, MAX_BED_MM),
        _finite_in_range(bed_depth_mm, "造形範囲の奥行", MIN_BED_MM, MAX_BED_MM),
    )


def validate_curvature_settings(radius_mm: object = None,
                                curve_axis: object = "width") -> tuple[float | None, str]:
    """空欄は平板、数値は円筒面の内側半径として検証する。"""
    axis = str(curve_axis or "width").strip()
    if axis not in CURVE_AXES:
        raise Accessory3DError("曲げ方向が不正です。画面から選び直してください。")
    if radius_mm is None or str(radius_mm).strip() in {"", "0", "0.0"}:
        return None, axis
    return (_finite_in_range(radius_mm, "曲率半径", MIN_CURVATURE_RADIUS_MM,
                             MAX_CURVATURE_RADIUS_MM), axis)


def validate_compound_curvature_settings(
        radius_mm: object = None, height_radius_mm: object = None,
        curve_axis: object = "width") -> tuple[float | None, float | None, str]:
    """縦横別半径の二方向曲面を検証する。

    旧データは半径1つなので、`both`で縦半径が空欄なら同じ
    値を使う。縦半径は二方向のときだけ有効にし、誤入力を黙って
    保存しない。
    """
    width_radius, axis = validate_curvature_settings(radius_mm, curve_axis)
    if axis != "both" or width_radius is None:
        return width_radius, None, axis
    if height_radius_mm is None or str(height_radius_mm).strip() in {"", "0", "0.0"}:
        return width_radius, width_radius, axis
    return width_radius, _finite_in_range(
        height_radius_mm, "縦方向の曲率半径", MIN_CURVATURE_RADIUS_MM,
        MAX_CURVATURE_RADIUS_MM), axis


def validate_mounting_holes(pattern: object = "none", diameter_mm: object = None,
                            inset_mm: object = None) -> tuple[str, float | None, float | None]:
    """利用者が明示した貫通穴だけを受け付ける。画像から位置を推定しない。"""
    selected = str(pattern or "none").strip()
    if selected not in MOUNTING_HOLE_PATTERNS:
        raise Accessory3DError("取り付け穴の配置が不正です。画面から選び直してください。")
    if selected == "none":
        return selected, None, None
    diameter = _finite_in_range(
        diameter_mm, "取り付け穴の直径", MIN_HOLE_DIAMETER_MM, MAX_HOLE_DIAMETER_MM)
    if selected == "center":
        return selected, diameter, None
    inset = _finite_in_range(
        inset_mm, "取り付け穴の端からの距離", MIN_HOLE_INSET_MM, MAX_HOLE_INSET_MM)
    if inset <= diameter / 2:
        raise Accessory3DError(
            "取り付け穴の端からの距離は、穴の半径より大きくしてください。")
    return selected, diameter, inset


def validate_attachment_interface(method: object = "none",
                                  hole_diameter_mm: object = None,
                                  hole_inset_mm: object = None
                                  ) -> tuple[str, str, float | None, float | None]:
    """市販のクリップ・ピン・可動軸を通す取付インターフェース。"""
    selected = str(method or "none").strip()
    if selected not in ATTACHMENT_INTERFACES:
        raise Accessory3DError("取付金具の種類が不正です。画面から選び直してください。")
    if selected == "none":
        return selected, "none", None, None
    diameter = _finite_in_range(
        hole_diameter_mm, "取付金具用の穴径", MIN_HOLE_DIAMETER_MM, 20.0)
    if selected == "pivot_joint":
        return selected, "center", diameter, None
    inset = _finite_in_range(
        hole_inset_mm, "取付金具用穴の端からの距離",
        MIN_HOLE_INSET_MM, MAX_HOLE_INSET_MM)
    if inset <= diameter / 2:
        raise Accessory3DError(
            "取付金具用穴の端からの距離は、穴の半径より大きくしてください。")
    return selected, "pair_width", diameter, inset


def validate_mounting_slots(pattern: object = "none", length_mm: object = None,
                            width_mm: object = None, axis: object = "width",
                            inset_mm: object = None
                            ) -> tuple[str, float | None, float | None, str, float | None]:
    """角を丸めたベルト用貫通長穴の入力を検証する。"""
    selected = str(pattern or "none").strip()
    selected_axis = str(axis or "width").strip()
    if selected not in MOUNTING_SLOT_PATTERNS:
        raise Accessory3DError("ベルト長穴の配置が不正です。画面から選び直してください。")
    if selected_axis not in MOUNTING_SLOT_AXES:
        raise Accessory3DError("ベルト長穴の向きが不正です。画面から選び直してください。")
    if selected == "none":
        return selected, None, None, selected_axis, None
    length = _finite_in_range(
        length_mm, "ベルト長穴の長さ", MIN_SLOT_LENGTH_MM, MAX_SLOT_LENGTH_MM)
    width = _finite_in_range(
        width_mm, "ベルト長穴の幅", MIN_SLOT_WIDTH_MM, MAX_SLOT_WIDTH_MM)
    if length <= width:
        raise Accessory3DError("ベルト長穴の長さは幅より大きくしてください。")
    if selected == "center":
        return selected, length, width, selected_axis, None
    inset = _finite_in_range(
        inset_mm, "ベルト長穴の端からの距離", MIN_HOLE_INSET_MM, MAX_HOLE_INSET_MM)
    if inset <= max(length, width) / 2.0:
        raise Accessory3DError(
            "ベルト長穴の端からの距離は、長穴の長さまたは幅の半分より大きくしてください。")
    return selected, length, width, selected_axis, inset


def validate_magnet_pockets(pattern: object = "none", diameter_mm: object = None,
                            depth_mm: object = None, inset_mm: object = None,
                            thickness_mm: object = 3.0
                            ) -> tuple[str, float | None, float | None, float | None]:
    """上面から掘る円形磁石ポケット。底厚を必ず0.6mm以上残す。"""
    selected = str(pattern or "none").strip()
    if selected not in MAGNET_POCKET_PATTERNS:
        raise Accessory3DError("磁石ポケットの配置が不正です。画面から選び直してください。")
    if selected == "none":
        return selected, None, None, None
    thickness = float(thickness_mm)
    diameter = _finite_in_range(
        diameter_mm, "磁石ポケットの直径", MIN_MAGNET_DIAMETER_MM,
        MAX_MAGNET_DIAMETER_MM)
    depth = _finite_in_range(
        depth_mm, "磁石ポケットの深さ", MIN_MAGNET_DEPTH_MM,
        max(MIN_MAGNET_DEPTH_MM, MAX_THICKNESS_MM - 0.6))
    if depth > thickness - 0.6:
        raise Accessory3DError(
            f"磁石ポケット深さ{depth:g}mmでは底厚が0.6mm未満になります。"
            f"本体厚{thickness:g}mmに対し、深さは{max(0, thickness - 0.6):g}mm以下にしてください。")
    if selected == "center":
        return selected, diameter, depth, None
    inset = _finite_in_range(
        inset_mm, "磁石ポケットの端からの距離", MIN_HOLE_INSET_MM,
        MAX_HOLE_INSET_MM)
    if inset <= diameter / 2.0:
        raise Accessory3DError(
            "磁石ポケットの端からの距離は、ポケット半径より大きくしてください。")
    return selected, diameter, depth, inset


def _polygon(points_cm: Iterable[tuple[float, float]]) -> Polygon:
    points_mm = [(float(x) * 10.0, float(y) * 10.0) for x, y in points_cm]
    polygon = Polygon(points_mm)
    if not polygon.is_valid:
        polygon = polygon.buffer(0)
    if polygon.is_empty or polygon.geom_type != "Polygon" or polygon.area < 1.0:
        raise Accessory3DError("3D化できない輪郭です。線の交差や重複した点を修正してください。")
    return orient(polygon, sign=1.0)


def _copies(specs: Iterable[CustomPanelSpec]) -> list[tuple[str, Polygon]]:
    pieces: list[tuple[str, Polygon]] = []
    for spec in specs:
        variants = [(spec.label, spec.points_cm)]
        if spec.mirror:
            variants.append((f"{spec.label}(反転)", mirror_points_x(spec.points_cm)))
        for label, points in variants:
            polygon = _polygon(points)
            for index in range(spec.quantity):
                suffix = f" {index + 1}" if spec.quantity > 1 else ""
                pieces.append((label + suffix, polygon))
    if not pieces:
        raise Accessory3DError("STLにするカスタムパーツがありません。")
    return pieces


def _with_mounting_holes(pieces: list[tuple[str, Polygon]], pattern: str,
                         diameter: float | None, inset: float | None
                         ) -> list[tuple[str, Polygon]]:
    """各部品へ同じ明示設定の貫通穴を開ける。成立しない部品は個別に止める。"""
    if pattern == "none":
        return pieces
    assert diameter is not None
    radius = diameter / 2.0
    output: list[tuple[str, Polygon]] = []
    for label, polygon in pieces:
        min_x, min_y, max_x, max_y = polygon.bounds
        centre = polygon.representative_point()
        if pattern == "center":
            centres = [(centre.x, centre.y)]
        elif pattern == "pair_width":
            assert inset is not None
            centres = [(min_x + inset, centre.y), (max_x - inset, centre.y)]
        else:
            assert inset is not None
            centres = [(centre.x, min_y + inset), (centre.x, max_y - inset)]
        holes = [Point(x, y).buffer(radius, quad_segs=16) for x, y in centres]
        if any(not polygon.contains(hole) for hole in holes):
            raise Accessory3DError(
                f"「{label}」に直径{diameter:g}mmの取り付け穴を安全に配置できません。"
                "穴の直径を小さくするか、端からの距離または輪郭を見直してください。")
        if len(holes) == 2 and holes[0].intersects(holes[1]):
            raise Accessory3DError(
                f"「{label}」の取り付け穴同士が重なります。端からの距離を見直してください。")
        drilled = polygon
        for hole in holes:
            drilled = drilled.difference(hole)
        if drilled.geom_type != "Polygon" or not drilled.is_valid:
            raise Accessory3DError(f"「{label}」の取り付け穴を開けた形状が成立しません。")
        output.append((label, orient(drilled, sign=1.0)))
    return output


def _slot_shape(x: float, y: float, length: float, width: float,
                axis: str) -> Polygon:
    half_straight = (length - width) / 2.0
    if axis == "width":
        centre_line = LineString([(x - half_straight, y),
                                  (x + half_straight, y)])
    else:
        centre_line = LineString([(x, y - half_straight),
                                  (x, y + half_straight)])
    return centre_line.buffer(width / 2.0, quad_segs=16)


def _with_mounting_slots(pieces: list[tuple[str, Polygon]], pattern: str,
                         length: float | None, width: float | None,
                         axis: str, inset: float | None
                         ) -> list[tuple[str, Polygon]]:
    """各部品へ、明示指定された角丸の貫通長穴を追加する。"""
    if pattern == "none":
        return pieces
    assert length is not None and width is not None
    output: list[tuple[str, Polygon]] = []
    for label, polygon in pieces:
        min_x, min_y, max_x, max_y = polygon.bounds
        centre = polygon.representative_point()
        if pattern == "center":
            centres = [(centre.x, centre.y)]
        elif pattern == "pair_width":
            assert inset is not None
            centres = [(min_x + inset, centre.y), (max_x - inset, centre.y)]
        else:
            assert inset is not None
            centres = [(centre.x, min_y + inset), (centre.x, max_y - inset)]
        slots = [_slot_shape(x, y, length, width, axis) for x, y in centres]
        if any(not polygon.contains(slot) for slot in slots):
            raise Accessory3DError(
                f"「{label}」に{length:g}×{width:g}mmのベルト長穴を安全に配置できません。"
                "長穴を小さくするか、端からの距離・向き・輪郭を見直してください。")
        if len(slots) == 2 and slots[0].intersects(slots[1]):
            raise Accessory3DError(
                f"「{label}」のベルト長穴同士が重なります。配置を見直してください。")
        slotted = polygon
        for slot in slots:
            slotted = slotted.difference(slot)
        if slotted.geom_type != "Polygon" or not slotted.is_valid:
            raise Accessory3DError(f"「{label}」へベルト長穴を開けた形状が成立しません。")
        output.append((label, orient(slotted, sign=1.0)))
    return output


def _magnet_recesses(polygon: Polygon, label: str, pattern: str,
                      diameter: float | None, inset: float | None
                      ) -> list[Polygon]:
    if pattern == "none":
        return []
    assert diameter is not None
    radius = diameter / 2.0
    min_x, min_y, max_x, max_y = polygon.bounds
    # 既存の丸穴・長穴によって representative_point が横へ逃げると、利用者が
    # 「中央」と指定した磁石位置を黙って変えてしまう。外接枠の中央へ固定し、
    # そこが穴や輪郭外なら安全側で止める。
    centre_x = (min_x + max_x) / 2.0
    centre_y = (min_y + max_y) / 2.0
    if pattern == "center":
        centres = [(centre_x, centre_y)]
    elif pattern == "pair_width":
        assert inset is not None
        centres = [(min_x + inset, centre_y), (max_x - inset, centre_y)]
    else:
        assert inset is not None
        centres = [(centre_x, min_y + inset), (centre_x, max_y - inset)]
    pockets = [Point(x, y).buffer(radius, quad_segs=16) for x, y in centres]
    if any(not polygon.contains(pocket) for pocket in pockets):
        raise Accessory3DError(
            f"「{label}」に直径{diameter:g}mmの磁石ポケットを安全に配置できません。"
            "直径を小さくするか、端からの距離・丸穴・長穴を見直してください。")
    if len(pockets) == 2 and pockets[0].intersects(pockets[1]):
        raise Accessory3DError(
            f"「{label}」の磁石ポケット同士が重なります。配置を見直してください。")
    return [orient(pocket, sign=1.0) for pocket in pockets]


def _arrange(pieces: list[tuple[str, Polygon]], bed_width: float,
             bed_depth: float) -> tuple[list[tuple[str, Polygon]], float, float]:
    """左下から行単位で並べる。各部品は回転させず画像の向きを保つ。"""
    arranged: list[tuple[str, Polygon]] = []
    cursor_x = cursor_y = row_height = 0.0
    max_x = max_y = 0.0
    for label, polygon in pieces:
        min_x, min_y, max_px, max_py = polygon.bounds
        width, depth = max_px - min_x, max_py - min_y
        if width > bed_width or depth > bed_depth:
            raise Accessory3DError(
                f"「{label}」({width:.1f}×{depth:.1f}mm)が指定した造形範囲"
                f"({bed_width:.0f}×{bed_depth:.0f}mm)に収まりません。"
                "輪郭の実寸を小さくするか、造形範囲を見直してください。")
        if cursor_x and cursor_x + width > bed_width:
            cursor_x = 0.0
            cursor_y += row_height + PART_GAP_MM
            row_height = 0.0
        if cursor_y + depth > bed_depth:
            raise Accessory3DError(
                "全パーツを1枚の造形範囲に配置できません。枚数を減らすか、"
                "造形範囲を大きくしてください。")
        from shapely.affinity import translate
        moved = translate(polygon, xoff=cursor_x - min_x, yoff=cursor_y - min_y)
        arranged.append((label, moved))
        cursor_x += width + PART_GAP_MM
        row_height = max(row_height, depth)
        max_x = max(max_x, moved.bounds[2])
        max_y = max(max_y, moved.bounds[3])
    return arranged, max_x, max_y


Vertex = tuple[float, float, float]
Triangle = tuple[Vertex, Vertex, Vertex]


#: 三角形分割が多角形を覆えたかを確かめる許容(面積比)。
_TRIANGULATION_AREA_TOLERANCE = 1e-6


def _ring_coords(ring, counter_clockwise: bool) -> list[tuple[float, float]]:
    """リングを、重複した終点を落として指定の向きで返す。"""
    coords = [(float(x), float(y)) for x, y in ring.coords]
    if len(coords) > 1 and coords[0] == coords[-1]:
        coords = coords[:-1]
    area = 0.0
    for (ax, ay), (bx, by) in zip(coords, coords[1:] + coords[:1]):
        area += ax * by - bx * ay
    if (area > 0) != counter_clockwise:
        coords.reverse()
    return coords


def _bridge_hole(ring: list[tuple[float, float]],
                 hole: list[tuple[float, float]], polygon: Polygon
                 ) -> list[tuple[float, float]] | None:
    """穴のリングを、外周リングへ「橋」でつないで1本の単純多角形にする。

    穴の右端の点から、いちばん近くて**見える**(その線分が多角形の内側に
    収まる)外周の頂点へ橋を架ける。earcutと同じ考え方である。

    橋を架ける順番は呼び出し側が決める(`_triangulate_polygon`)。
    右にある穴から架けないと、あとの橋が先の橋と交差しうる。
    """
    start = max(range(len(hole)), key=lambda i: hole[i][0])
    ordered = hole[start:] + hole[:start]
    origin = ordered[0]
    candidates = sorted(range(len(ring)),
                        key=lambda i: (ring[i][0] - origin[0]) ** 2
                        + (ring[i][1] - origin[1]) ** 2)
    for index in candidates:
        if polygon.covers(LineString([origin, ring[index]])):
            return (ring[:index + 1] + [origin] + ordered[1:] + [origin]
                    + ring[index:])
    return None


def _ear_clip(points: list[tuple[float, float]]) -> list[tuple[int, int, int]]:
    """耳切り法で単純多角形を三角形へ分ける。頂点番号の組を返す。

    `shapely.ops.triangulate`は**頂点集合の**ドロネー分割で、多角形の辺を
    守らない。凹んだ形では辺をまたぐ三角形ができ、それを捨てると面に穴が
    残る(round77で実測: 凹形状で上下面20枚中2枚しか張れなかった)。
    耳切り法は多角形の辺を必ず守るので、この穴が原理的に出ない。
    """
    n = len(points)
    if n < 3:
        return []
    index = list(range(n))

    def cross(o, a, b):
        return ((a[0] - o[0]) * (b[1] - o[1])
                - (a[1] - o[1]) * (b[0] - o[0]))

    # 穴を橋でつなぐと、橋の両端の点が**2回ずつ**並びに現れる。番号で
    # 除外するだけでは、同じ座標のもう1つが「三角形の中にある」と判定され、
    # どの角も耳になれなくなる(実測: 穴のある形で三角形が0枚になった)。
    # 座標が一致する点も除外する。
    def same(p, q) -> bool:
        return abs(p[0] - q[0]) <= 1e-9 and abs(p[1] - q[1]) <= 1e-9

    def inside(p, a, b, c) -> bool:
        if same(p, a) or same(p, b) or same(p, c):
            return False
        d1, d2, d3 = cross(a, b, p), cross(b, c, p), cross(c, a, p)
        has_neg = min(d1, d2, d3) < -1e-12
        has_pos = max(d1, d2, d3) > 1e-12
        return not (has_neg and has_pos)

    area = sum(points[i][0] * points[(i + 1) % n][1]
               - points[(i + 1) % n][0] * points[i][1] for i in range(n))
    if area < 0:                      # 反時計回りにそろえる
        points = list(reversed(points))
        index = list(range(n))

    output: list[tuple[int, int, int]] = []
    guard = 0
    while len(index) > 3 and guard < 4 * n * n:
        guard += 1
        clipped = False
        for k in range(len(index)):
            i0 = index[k - 1]
            i1 = index[k]
            i2 = index[(k + 1) % len(index)]
            a, b, c = points[i0], points[i1], points[i2]
            if cross(a, b, c) <= 1e-12:      # 凸でない角は耳になれない
                continue
            if any(inside(points[j], a, b, c)
                   for j in index if j not in (i0, i1, i2)):
                continue
            output.append((i0, i1, i2))
            index.pop(k)
            clipped = True
            break
        if not clipped:
            return []
    if len(index) == 3:
        output.append((index[0], index[1], index[2]))
    return output


def _triangulate_polygon(polygon: Polygon) -> list[tuple[tuple[float, float],
                                                          tuple[float, float],
                                                          tuple[float, float]]]:
    """多角形(穴があってもよい)を、面を覆う三角形へ分ける。

    覆えたかを**面積で確かめてから**返す。覆えていなければ例外にする——
    穴の開いたメッシュを黙って3Dプリント業者へ渡さないため。
    """
    outer = _ring_coords(polygon.exterior, counter_clockwise=True)
    points = list(outer)
    # 右にある穴から橋を架ける(earcutと同じ順序)。
    #
    # round77: **この並べ替えが効いている。** `polygon.interiors`の順で
    # 架けると、あとの橋が先の橋と交差して耳が1つも取れなくなる。実測で、
    # 穴が2つのときだけ三角形が0枚になった(1つと3つは通っていたので
    # 気付きにくい)。交差そのものを判定する手当ても書いたが、無作為な
    # 穴配置200通り・681回の判定で1度も弾かれず、外しても落ちるテストを
    # 作れなかったので置かないことにした。
    interiors = sorted(polygon.interiors,
                       key=lambda ring: -max(x for x, _y in ring.coords))
    for interior in interiors:
        hole = _ring_coords(interior, counter_clockwise=False)
        bridged = _bridge_hole(points, hole, polygon)
        if bridged is None:
            raise ValueError(
                "3D出力: 穴のある形を三角形へ分けられませんでした"
                "(穴と外周をつなぐ線が引けません)。")
        points = bridged
    faces = _ear_clip(points)
    triangles = [(points[i], points[j], points[k]) for i, j, k in faces]
    covered = sum(abs((b[0] - a[0]) * (c[1] - a[1])
                      - (c[0] - a[0]) * (b[1] - a[1])) / 2.0
                  for a, b, c in triangles)
    if abs(covered - polygon.area) > max(polygon.area * 1e-6, 1e-9):
        raise ValueError(
            "3D出力: 面を三角形で覆いきれませんでした"
            f"(多角形{polygon.area:.4f}に対し三角形の合計{covered:.4f})。"
            "この形のままでは閉じたメッシュを出せません。")
    return triangles


def _open_edge_count(triangles: list["Triangle"]) -> int:
    """閉じていない辺(2枚の面で共有されていない辺)の本数。"""
    from collections import Counter

    counts: Counter = Counter()
    for face in triangles:
        rounded = [tuple(round(v, 6) for v in vertex) for vertex in face]
        for a, b in ((0, 1), (1, 2), (2, 0)):
            counts[frozenset((rounded[a], rounded[b]))] += 1
    return sum(1 for _edge, n in counts.items() if n != 2)


def _extrude(polygon: Polygon, thickness: float) -> list[Triangle]:
    triangles: list[Triangle] = []
    # round77: 多角形の辺を守る三角形分割を使う(`_triangulate_polygon`)。
    # `shapely.ops.triangulate`は頂点集合のドロネー分割なので、凹んだ形では
    # 辺をまたぐ三角形ができ、捨てると面に穴が残っていた。
    for face in _triangulate_polygon(polygon):
        top = tuple((x, y, thickness) for x, y in face)
        bottom = tuple((x, y, 0.0) for x, y in reversed(face))
        triangles.extend((top, bottom))

    rings = [polygon.exterior, *polygon.interiors]
    for ring in rings:
        coords = list(ring.coords)
        # exteriorはCCW。穴のリングはCWなので、同じ式で双方とも外向きになる。
        for (ax, ay), (bx, by) in zip(coords, coords[1:]):
            a0, b0 = (ax, ay, 0.0), (bx, by, 0.0)
            a1, b1 = (ax, ay, thickness), (bx, by, thickness)
            triangles.extend(((a0, b0, b1), (a0, b1, a1)))
    return triangles


def _surface_triangles(polygon: Polygon, z: float, *, upward: bool) -> list[Triangle]:
    output: list[Triangle] = []
    for face in _triangulate_polygon(polygon):
        coords = list(face)
        if not upward:
            coords.reverse()
        output.append(tuple((x, y, z) for x, y in coords))
    return output


def _wall_triangles(ring, z0: float, z1: float) -> list[Triangle]:
    output: list[Triangle] = []
    coords = list(ring.coords)
    for (ax, ay), (bx, by) in zip(coords, coords[1:]):
        a0, b0 = (ax, ay, z0), (bx, by, z0)
        a1, b1 = (ax, ay, z1), (bx, by, z1)
        output.extend(((a0, b0, b1), (a0, b1, a1)))
    return output


def _extrude_with_recesses(polygon: Polygon, thickness: float,
                            recesses: list[Polygon], depth: float
                            ) -> list[Triangle]:
    """上面だけを掘り、底を残した閉じたメッシュを作る。"""
    if not recesses:
        return _extrude(polygon, thickness)
    floor_z = thickness - depth
    top = polygon
    for recess in recesses:
        top = top.difference(recess)
    if top.geom_type != "Polygon" or not top.is_valid:
        raise Accessory3DError("磁石ポケットを追加した上面形状が成立しません。")
    triangles = _surface_triangles(polygon, 0.0, upward=False)
    triangles.extend(_surface_triangles(top, thickness, upward=True))
    for ring in [polygon.exterior, *polygon.interiors]:
        triangles.extend(_wall_triangles(ring, 0.0, thickness))
    for recess in recesses:
        triangles.extend(_surface_triangles(recess, floor_z, upward=True))
        # recessはCCWなので、穴壁として法線を内向きにするため逆順にする。
        reverse_ring = LineString(list(recess.exterior.coords)[::-1])
        triangles.extend(_wall_triangles(reverse_ring, floor_z, thickness))
    return triangles


def _curve_mesh(triangles: list[Triangle], polygon: Polygon,
                radius: float | None, axis: str,
                height_radius: float | None = None) -> list[Triangle]:
    """平板を円筒面または縦横別半径の二方向曲面へ写像する。"""
    if radius is None:
        return triangles
    min_x, min_y, max_x, max_y = polygon.bounds
    radius_y = height_radius if axis == "both" and height_radius else radius
    checks = ([(max_x - min_x, radius), (max_y - min_y, radius_y)]
              if axis == "both" else
              [(max_x - min_x, radius)] if axis == "width" else
              [(max_y - min_y, radius)])
    # 180度を超えると自己干渉や裏返りが起き得るため、推測で出力しない。
    if any(span / checked_radius >= math.pi for span, checked_radius in checks):
        span, checked_radius = max(checks, key=lambda item: item[0] / item[1])
        raise Accessory3DError(
            f"曲率半径{checked_radius:g}mmでは輪郭の曲げ方向{span:.1f}mmを"
            f"安全に曲げられません。半径を{span / math.pi:.1f}mmより"
            "大きくしてください。")
    centre_x = (min_x + max_x) / 2
    centre_y = (min_y + max_y) / 2

    def bend(vertex: Vertex) -> Vertex:
        x, y, z = vertex
        if axis == "width":
            angle = (x - centre_x) / radius
            # zは平板の厚み方向。曲げた後は円筒面の法線方向に
            # 厚みを持たせる。従来はzだけを垂直に足していたため、
            # 厚い部品でも造形幅が増えず、プリンタの範囲判定を
            # すり抜けていた。
            effective_radius = radius + z
            return (centre_x + effective_radius * math.sin(angle), y,
                    effective_radius * math.cos(angle) - radius)
        if axis == "height":
            angle = (y - centre_y) / radius
            effective_radius = radius + z
            return (x, centre_y + effective_radius * math.sin(angle),
                    effective_radius * math.cos(angle) - radius)
        angle_x = (x - centre_x) / radius
        angle_y = (y - centre_y) / radius_y
        return (centre_x + radius * math.sin(angle_x),
                centre_y + radius_y * math.sin(angle_y),
                z + radius * (math.cos(angle_x) - 1.0)
                  + radius_y * (math.cos(angle_y) - 1.0))

    return [tuple(bend(vertex) for vertex in triangle) for triangle in triangles]


def _densify_for_curve(polygon: Polygon, radius: float | None,
                       axis: str) -> Polygon:
    """円筒面が粗い多角形の1枚板にならないよう、曲げ方向の辺を分割する。"""
    if radius is None:
        return polygon
    # 1区間10mm以下かつ中心角10度以下。衣装小物として滑らかさを保ちつつ、
    # STLが不必要に巨大になるのを避ける。
    max_step = min(10.0, radius * math.pi / 18.0)

    def densify_ring(ring) -> list[tuple[float, float]]:
        coords = list(ring.coords)
        output: list[tuple[float, float]] = []
        for start, end in zip(coords, coords[1:]):
            output.append((start[0], start[1]))
            span = (max(abs(end[0] - start[0]), abs(end[1] - start[1]))
                    if axis == "both" else
                    abs(end[0] - start[0]) if axis == "width" else
                    abs(end[1] - start[1]))
            divisions = max(1, math.ceil(span / max_step))
            for index in range(1, divisions):
                fraction = index / divisions
                output.append((
                    start[0] + (end[0] - start[0]) * fraction,
                    start[1] + (end[1] - start[1]) * fraction,
                ))
        return output

    dense = Polygon(
        densify_ring(polygon.exterior),
        [densify_ring(ring) for ring in polygon.interiors],
    )
    return orient(dense, sign=1.0)


def _mesh(polygon: Polygon, thickness: float, radius: float | None,
          axis: str, *, label: str = "", magnet_pattern: str = "none",
          height_radius: float | None = None,
          magnet_diameter: float | None = None,
          magnet_depth: float | None = None,
          magnet_inset: float | None = None) -> list[Triangle]:
    dense = _densify_for_curve(polygon, radius, axis)
    recesses = _magnet_recesses(
        dense, label, magnet_pattern, magnet_diameter, magnet_inset)
    flat = (_extrude_with_recesses(dense, thickness, recesses, float(magnet_depth))
            if recesses and magnet_depth is not None else _extrude(dense, thickness))
    return _curve_mesh(flat, dense, radius, axis, height_radius)


def _mesh_bounds(triangles: Iterable[Triangle]) -> tuple[float, float, float, float, float, float]:
    vertices = [vertex for triangle in triangles for vertex in triangle]
    if not vertices:
        raise Accessory3DError("3Dメッシュに頂点がありません。輪郭を確認してください。")
    xs, ys, zs = zip(*vertices)
    return min(xs), min(ys), min(zs), max(xs), max(ys), max(zs)


def _mesh_dimensions(triangles: Iterable[Triangle]) -> tuple[float, float, float]:
    min_x, min_y, min_z, max_x, max_y, max_z = _mesh_bounds(triangles)
    return max_x - min_x, max_y - min_y, max_z - min_z


def _move_mesh_to_origin(triangles: list[Triangle]) -> list[Triangle]:
    """スライサーへ置いた時に造形面より下へ潜らないようXYZ最小値を0にする。"""
    min_x, min_y, min_z, _max_x, _max_y, _max_z = _mesh_bounds(triangles)
    return [tuple((x - min_x, y - min_y, z - min_z) for x, y, z in triangle)
            for triangle in triangles]


def _arranged_meshes(arranged: list[tuple[str, Polygon]], thickness: float,
                     radius: float | None, axis: str, *,
                     height_radius: float | None = None,
                     magnet_pattern: str = "none",
                     magnet_diameter: float | None = None,
                     magnet_depth: float | None = None,
                     magnet_inset: float | None = None,
                     ) -> list[tuple[str, list[Triangle]]]:
    raw = [(label, _mesh(
        polygon, thickness, radius, axis, label=label, height_radius=height_radius,
        magnet_pattern=magnet_pattern, magnet_diameter=magnet_diameter,
        magnet_depth=magnet_depth, magnet_inset=magnet_inset))
           for label, polygon in arranged]
    all_triangles = [triangle for _label, triangles in raw for triangle in triangles]
    min_x, min_y, min_z, _max_x, _max_y, _max_z = _mesh_bounds(all_triangles)
    return [
        (label, [tuple((x - min_x, y - min_y, z - min_z) for x, y, z in triangle)
                 for triangle in triangles])
        for label, triangles in raw
    ]


def _normal(triangle: Triangle) -> Vertex:
    a, b, c = triangle
    ux, uy, uz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
    vx, vy, vz = c[0] - a[0], c[1] - a[1], c[2] - a[2]
    nx, ny, nz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
    length = math.sqrt(nx * nx + ny * ny + nz * nz)
    return (nx / length, ny / length, nz / length) if length else (0.0, 0.0, 0.0)


def _write_ascii_stl(path: str, triangles: Iterable[Triangle]) -> int:
    count = 0
    temp_path = path + ".tmp"
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(temp_path, "w", encoding="ascii", newline="\n") as output:
            output.write("solid patternforge_accessories\n")
            for triangle in triangles:
                normal = _normal(triangle)
                output.write(f"  facet normal {normal[0]:.9g} {normal[1]:.9g} {normal[2]:.9g}\n")
                output.write("    outer loop\n")
                for x, y, z in triangle:
                    output.write(f"      vertex {x:.9g} {y:.9g} {z:.9g}\n")
                output.write("    endloop\n  endfacet\n")
                count += 1
            output.write("endsolid patternforge_accessories\n")
        os.replace(temp_path, path)
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)
    return count


def _binary_stl_bytes(triangles: Iterable[Triangle], label: str = "PatternForge") -> bytes:
    triangles = list(triangles)
    header = (f"PatternForge mm | {label}".encode("ascii", "replace")[:80]).ljust(80, b" ")
    output = io.BytesIO()
    output.write(header)
    output.write(struct.pack("<I", len(triangles)))
    for triangle in triangles:
        values = [*_normal(triangle)]
        for vertex in triangle:
            values.extend(vertex)
        output.write(struct.pack("<12fH", *values, 0))
    return output.getvalue()


def _mesh_xml(parent: ET.Element, object_id: int, label: str,
              triangles: list[Triangle]) -> None:
    object_el = ET.SubElement(parent, "object", {
        "id": str(object_id), "type": "model", "name": label,
    })
    mesh = ET.SubElement(object_el, "mesh")
    vertices_el = ET.SubElement(mesh, "vertices")
    triangles_el = ET.SubElement(mesh, "triangles")
    indices: dict[Vertex, int] = {}
    for triangle in triangles:
        face_indices = []
        for vertex in triangle:
            if vertex not in indices:
                indices[vertex] = len(indices)
                ET.SubElement(vertices_el, "vertex", {
                    "x": f"{vertex[0]:.9g}",
                    "y": f"{vertex[1]:.9g}",
                    "z": f"{vertex[2]:.9g}",
                })
            face_indices.append(indices[vertex])
        ET.SubElement(triangles_el, "triangle", {
            "v1": str(face_indices[0]), "v2": str(face_indices[1]),
            "v3": str(face_indices[2]),
        })


def _three_mf_bytes(arranged: list[tuple[str, Polygon]], thickness: float,
                    curvature_radius: float | None = None,
                    curve_axis: str = "width", *,
                    curvature_height_radius: float | None = None,
                    magnet_pattern: str = "none",
                    magnet_diameter: float | None = None,
                    magnet_depth: float | None = None,
                    magnet_inset: float | None = None) -> bytes:
    namespace = "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"
    ET.register_namespace("", namespace)
    model = ET.Element(f"{{{namespace}}}model", {"unit": "millimeter", "xml:lang": "ja-JP"})
    ET.SubElement(model, f"{{{namespace}}}metadata", {"name": "Title"}).text = \
        "PatternForge costume accessories"
    ET.SubElement(model, f"{{{namespace}}}metadata", {"name": "Description"}).text = \
        "Print-ready closed meshes. Dimensions are millimetres."
    resources = ET.SubElement(model, f"{{{namespace}}}resources")
    build = ET.SubElement(model, f"{{{namespace}}}build")
    # ElementTreeは既定名前空間を子へ引き継ぐが、生成補助は素のタグを使うため
    # 最後に名前空間を付ける。3MF検証ソフトが要素をCore名前空間として読むため。
    mesh_entries = _arranged_meshes(
        arranged, thickness, curvature_radius, curve_axis,
        height_radius=curvature_height_radius,
        magnet_pattern=magnet_pattern, magnet_diameter=magnet_diameter,
        magnet_depth=magnet_depth, magnet_inset=magnet_inset)
    for object_id, (label, triangles) in enumerate(mesh_entries, start=1):
        _mesh_xml(resources, object_id, label, triangles)
        ET.SubElement(build, f"{{{namespace}}}item", {"objectid": str(object_id)})
    for element in resources.iter():
        if not element.tag.startswith("{"):
            element.tag = f"{{{namespace}}}{element.tag}"

    content_types = """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>
</Types>"""
    relationships = """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Target="/3D/3dmodel.model" Id="rel-1" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>
</Relationships>"""
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("_rels/.rels", relationships)
        archive.writestr("3D/3dmodel.model", ET.tostring(
            model, encoding="utf-8", xml_declaration=True))
    return output.getvalue()


_MATERIAL_NOTES = {
    "consult": "素材・造形方式は業者と相談（用途はコスプレ着用小物）",
    "pa12": "推奨候補: PA12ナイロン/SLS（軽さ・耐久性を優先）",
    "tough_resin": "推奨候補: 高靭性レジン（細部と表面品質を優先）",
    "prototype": "試作用候補: PLAまたはPETG/FDM（寸法・装着確認を優先）",
}


def _safe_order_text(raw: object, default: str, maximum: int) -> str:
    # 注文票へそのまま書き出す値である。改行や制御文字を残すと、利用者が
    # 入力した仕上げ希望が別の指示行に見えてしまうため、空白1個へ正規化する。
    text = " ".join(str(raw or "").replace("\x00", " ").split())
    return text[:maximum] or default


def normalize_order_options(material_profile: object,
                            finish_note: object) -> tuple[str, str]:
    """業者入稿用の選択値を検証し、再生成にも保存できる形へ正規化する。"""
    profile = str(material_profile or "consult").strip()
    if profile not in _MATERIAL_NOTES:
        raise Accessory3DError("素材希望の選択が不正です。画面から選び直してください。")
    return profile, _safe_order_text(finish_note, "業者と相談", 120)


def export_vendor_package(specs: Iterable[CustomPanelSpec], output_path: str,
                          thickness_mm: object = 3.0, bed_width_mm: object = 220.0,
                          bed_depth_mm: object = 220.0, material_profile: object = "consult",
                          finish_note: object = "業者と相談",
                          curvature_radius_mm: object = None,
                          curvature_radius_height_mm: object = None,
                          curve_axis: object = "width",
                          mounting_hole_pattern: object = "none",
                          mounting_hole_diameter_mm: object = None,
                          mounting_hole_inset_mm: object = None,
                          mounting_slot_pattern: object = "none",
                          mounting_slot_length_mm: object = None,
                          mounting_slot_width_mm: object = None,
                          mounting_slot_axis: object = "width",
                          mounting_slot_inset_mm: object = None,
                          magnet_pocket_pattern: object = "none",
                          magnet_pocket_diameter_mm: object = None,
                          magnet_pocket_depth_mm: object = None,
                          magnet_pocket_inset_mm: object = None,
                          attachment_interface: object = "none") -> VendorPackageResult:
    """業者入稿用ZIPを作る。

    個別のバイナリSTL（互換性優先）、単位を保持する3MF、寸法・数量・制約を
    明記した入稿票と機械可読manifestを同梱する。G-codeは機種依存なので作らない。
    """
    thickness, bed_width, bed_depth = validate_accessory_settings(
        thickness_mm, bed_width_mm, bed_depth_mm)
    curvature_radius, curvature_height_radius, curve_axis = \
        validate_compound_curvature_settings(
            curvature_radius_mm, curvature_radius_height_mm, curve_axis)
    hole_pattern, hole_diameter, hole_inset = validate_mounting_holes(
        mounting_hole_pattern, mounting_hole_diameter_mm, mounting_hole_inset_mm)
    attachment, expected_pattern, expected_diameter, expected_inset = \
        validate_attachment_interface(attachment_interface, hole_diameter, hole_inset)
    if attachment != "none" and (
            hole_pattern != expected_pattern or hole_diameter != expected_diameter
            or hole_inset != expected_inset):
        raise Accessory3DError(
            "取付金具用の穴と通常の取り付け穴の設定が矛盾しています。")
    slot_pattern, slot_length, slot_width, slot_axis, slot_inset = validate_mounting_slots(
        mounting_slot_pattern, mounting_slot_length_mm, mounting_slot_width_mm,
        mounting_slot_axis, mounting_slot_inset_mm)
    magnet_pattern, magnet_diameter, magnet_depth, magnet_inset = validate_magnet_pockets(
        magnet_pocket_pattern, magnet_pocket_diameter_mm,
        magnet_pocket_depth_mm, magnet_pocket_inset_mm, thickness)
    pieces = _with_mounting_slots(
        _with_mounting_holes(_copies(specs), hole_pattern, hole_diameter, hole_inset),
        slot_pattern, slot_length, slot_width, slot_axis, slot_inset)
    arranged, arranged_width, arranged_depth = _arrange(pieces, bed_width, bed_depth)
    profile, finish = normalize_order_options(material_profile, finish_note)
    material_note = _MATERIAL_NOTES[profile]

    individual_files: list[tuple[str, bytes, dict]] = []
    for index, (label, polygon) in enumerate(pieces, start=1):
        min_x, min_y, max_x, max_y = polygon.bounds
        from shapely.affinity import translate
        origin_polygon = translate(polygon, xoff=-min_x, yoff=-min_y)
        triangles = _move_mesh_to_origin(
            _mesh(origin_polygon, thickness, curvature_radius, curve_axis,
                  height_radius=curvature_height_radius,
                  label=label, magnet_pattern=magnet_pattern,
                  magnet_diameter=magnet_diameter, magnet_depth=magnet_depth,
                  magnet_inset=magnet_inset))
        mesh_x, mesh_y, mesh_z = _mesh_dimensions(triangles)
        filename = f"individual/part_{index:03d}_mm_binary.stl"
        data = _binary_stl_bytes(triangles, f"part {index:03d}")
        individual_files.append((filename, data, {
            "index": index,
            "label": label,
            "file": filename,
            "units": "mm",
            "dimensions_mm": {
                "x": round(mesh_x, 3),
                "y": round(mesh_y, 3),
                "z": round(mesh_z, 3),
            },
            "triangle_count": len(triangles),
            "shell_count": 1,
            # round77: **実際に数えた**結果を書く。v125はここをTrueで
            # 決め打ちしていたため、穴の開いたメッシュでも業者へ
            # 「閉じている」と申告していた。
            "watertight": _open_edge_count(triangles) == 0,
            "sha256": hashlib.sha256(data).hexdigest(),
        }))

    three_mf = _three_mf_bytes(
        arranged, thickness, curvature_radius, curve_axis,
        curvature_height_radius=curvature_height_radius,
        magnet_pattern=magnet_pattern, magnet_diameter=magnet_diameter,
        magnet_depth=magnet_depth, magnet_inset=magnet_inset)
    arranged_mesh_entries = _arranged_meshes(
        arranged, thickness, curvature_radius, curve_axis,
        height_radius=curvature_height_radius,
        magnet_pattern=magnet_pattern, magnet_diameter=magnet_diameter,
        magnet_depth=magnet_depth, magnet_inset=magnet_inset)
    arranged_triangles = [triangle for _label, triangles in arranged_mesh_entries
                          for triangle in triangles]
    mesh_width, mesh_depth, mesh_height = _mesh_dimensions(arranged_triangles)
    if mesh_width > bed_width + 1e-6 or mesh_depth > bed_depth + 1e-6:
        raise Accessory3DError(
            f"曲面化後の配置({mesh_width:.1f}×{mesh_depth:.1f}mm)が指定した造形範囲"
            f"({bed_width:.0f}×{bed_depth:.0f}mm)に収まりません。"
            "造形範囲を大きくするか、輪郭・厚み・曲率半径を見直してください。")
    axis_label = {"width": "横方向", "height": "縦方向", "both": "横＋縦方向"}[curve_axis]
    curve_description = (
        f"{'二方向曲面' if curve_axis == 'both' else '円筒曲面'}"
        f"（{'横半径' if curve_axis == 'both' else '内側半径'}{curvature_radius:g}mm"
        + (f"・縦半径{curvature_height_radius:g}mm" if curve_axis == "both" else "")
        + "、"
        f"{axis_label}）"
        if curvature_radius is not None else "平板"
    )
    curvature_manifest = {
        "type": ("compound" if curve_axis == "both" else "cylindrical")
                if curvature_radius is not None else "flat",
        "inner_radius_mm": curvature_radius,
        "axis": curve_axis,
    }
    # v1の一方向曲面を利用する業者側ツールの厳密なJSON比較を
    # 壊さない。追加キーは二方向曲面で実値があるときだけ出す。
    if curvature_height_radius is not None:
        curvature_manifest["height_inner_radius_mm"] = curvature_height_radius

    manifest = {
        "schema": "patternforge.vendor-package.v1",
        "units": "mm",
        "piece_count": len(pieces),
        "thickness_mm": thickness,
        "curvature": curvature_manifest,
        "mounting_holes": {
            "pattern": hole_pattern,
            "diameter_mm": hole_diameter,
            "edge_inset_mm": hole_inset,
            "through_hole": hole_pattern != "none",
        },
        "mounting_slots": {
            "pattern": slot_pattern,
            "length_mm": slot_length,
            "width_mm": slot_width,
            "axis": slot_axis,
            "edge_inset_mm": slot_inset,
            "through_slot": slot_pattern != "none",
        },
        "magnet_pockets": {
            "pattern": magnet_pattern,
            "diameter_mm": magnet_diameter,
            "depth_mm": magnet_depth,
            "edge_inset_mm": magnet_inset,
            "through_hole": False,
            "non_through": magnet_pattern != "none",
            "minimum_remaining_floor_mm": 0.6 if magnet_pattern != "none" else None,
        },
        "attachment_interface": {
            "type": attachment,
            "uses_mounting_holes": attachment != "none",
            "hardware_included": False,
        },
        "arranged_3mf_dimensions_mm": {
            "x": round(mesh_width, 3), "y": round(mesh_depth, 3),
            "z": round(mesh_height, 3),
        },
        "material_request": material_note,
        "finish_request": finish,
        "files": [metadata for _name, _data, metadata in individual_files],
        "limitations": [
            "Curvature is user-specified and is not inferred from the body or image.",
            "Attachment interfaces are dimensioned holes for user-supplied hardware; clips, pins and axles are not printed.",
            "No color or surface texture is embedded.",
        ],
    }
    manifest_bytes = json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8")
    notes = [
        "PatternForge 3D小物　業者入稿票",
        "================================",
        f"単位: mm（3MF内にもmillimeterを明記）",
        f"数量: {len(pieces)}個 / 厚み: {thickness:g}mm",
        f"形状: {curve_description}",
        (f"取り付け穴: {hole_pattern} / 直径{hole_diameter:g}mm"
         + (f" / 端から中心まで{hole_inset:g}mm" if hole_inset is not None else "")
         if hole_pattern != "none" else "取り付け穴: なし"),
        (f"ベルト長穴: {slot_pattern} / {slot_length:g}×{slot_width:g}mm / "
         f"{'横向き' if slot_axis == 'width' else '縦向き'}"
         + (f" / 端から中心まで{slot_inset:g}mm" if slot_inset is not None else "")
         if slot_pattern != "none" else "ベルト長穴: なし"),
        (f"磁石ポケット: {magnet_pattern} / 直径{magnet_diameter:g}mm / "
         f"深さ{magnet_depth:g}mm（非貫通・底厚{thickness - magnet_depth:.1f}mm）"
         + (f" / 端から中心まで{magnet_inset:g}mm" if magnet_inset is not None else "")
         if magnet_pattern != "none" else "磁石ポケット: なし"),
        (f"取付金具インターフェース: {attachment}"
         if attachment != "none" else "取付金具インターフェース: なし"),
        f"素材希望: {material_note}",
        f"色・仕上げ希望: {finish}",
        "",
        "推奨入稿ファイル:",
        "- 一括確認: all_parts_mm.3mf（単位情報あり）",
        "- 個別見積: individual/ 内の1パーツ1ファイルのバイナリSTL",
        "- STLは形式上単位を保持しないため、必ずmmとして読み込んでください。",
        "",
        "業者様への確認事項:",
        "- 造形方向とサポート位置は、見える表面の仕上がりを優先してご提案ください。",
        "- 肌や衣服に触れる着用小物です。材料の安全性、角の処理、耐熱性をご確認ください。",
        "- 寸法・数量はmanifest.jsonと照合してください。",
        "",
        "重要な制約:",
        "曲面は利用者が指定した半径による円筒／二方向曲面で、身体からの自動推定ではありません。",
        "丸い貫通穴、ベルト用長穴、磁石ポケットは利用者が指定した場合だけ生成します。",
        "クリップ・ブローチピン・可動軸は市販金具を別途用意し、生成した寸法穴へ取り付けます。",
        "金具自体と表面色は自動生成しません。現物金具と仮組みで穴径を確認してください。",
        "",
    ]
    notes_bytes = "\n".join(notes).encode("utf-8-sig")

    temp_path = output_path + ".tmp"
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(temp_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("all_parts_mm.3mf", three_mf)
            archive.writestr("manifest.json", manifest_bytes)
            archive.writestr("ORDER_NOTES_JA.txt", notes_bytes)
            for filename, data, _metadata in individual_files:
                archive.writestr(filename, data)
        os.replace(temp_path, output_path)
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)
    return VendorPackageResult(
        output_path, len(pieces), len(individual_files) + 3, os.path.getsize(output_path))


def export_accessories_stl(specs: Iterable[CustomPanelSpec], output_path: str,
                           thickness_mm: object = 3.0, bed_width_mm: object = 220.0,
                           bed_depth_mm: object = 220.0,
                           curvature_radius_mm: object = None,
                           curvature_radius_height_mm: object = None,
                           curve_axis: object = "width",
                           mounting_hole_pattern: object = "none",
                           mounting_hole_diameter_mm: object = None,
                           mounting_hole_inset_mm: object = None,
                           mounting_slot_pattern: object = "none",
                           mounting_slot_length_mm: object = None,
                           mounting_slot_width_mm: object = None,
                           mounting_slot_axis: object = "width",
                           mounting_slot_inset_mm: object = None,
                           magnet_pocket_pattern: object = "none",
                           magnet_pocket_diameter_mm: object = None,
                           magnet_pocket_depth_mm: object = None,
                           magnet_pocket_inset_mm: object = None,
                           attachment_interface: object = "none") -> Accessory3DResult:
    thickness, bed_width, bed_depth = validate_accessory_settings(
        thickness_mm, bed_width_mm, bed_depth_mm)
    curvature_radius, curvature_height_radius, curve_axis = \
        validate_compound_curvature_settings(
            curvature_radius_mm, curvature_radius_height_mm, curve_axis)
    hole_pattern, hole_diameter, hole_inset = validate_mounting_holes(
        mounting_hole_pattern, mounting_hole_diameter_mm, mounting_hole_inset_mm)
    attachment, expected_pattern, expected_diameter, expected_inset = \
        validate_attachment_interface(attachment_interface, hole_diameter, hole_inset)
    if attachment != "none" and (
            hole_pattern != expected_pattern or hole_diameter != expected_diameter
            or hole_inset != expected_inset):
        raise Accessory3DError(
            "取付金具用の穴と通常の取り付け穴の設定が矛盾しています。")
    slot_pattern, slot_length, slot_width, slot_axis, slot_inset = validate_mounting_slots(
        mounting_slot_pattern, mounting_slot_length_mm, mounting_slot_width_mm,
        mounting_slot_axis, mounting_slot_inset_mm)
    magnet_pattern, magnet_diameter, magnet_depth, magnet_inset = validate_magnet_pockets(
        magnet_pocket_pattern, magnet_pocket_diameter_mm,
        magnet_pocket_depth_mm, magnet_pocket_inset_mm, thickness)
    pieces = _with_mounting_slots(
        _with_mounting_holes(_copies(specs), hole_pattern, hole_diameter, hole_inset),
        slot_pattern, slot_length, slot_width, slot_axis, slot_inset)
    arranged, width, depth = _arrange(pieces, bed_width, bed_depth)
    mesh_entries = _arranged_meshes(
        arranged, thickness, curvature_radius, curve_axis,
        height_radius=curvature_height_radius,
        magnet_pattern=magnet_pattern, magnet_diameter=magnet_diameter,
        magnet_depth=magnet_depth, magnet_inset=magnet_inset)
    triangles = [triangle for _label, mesh in mesh_entries for triangle in mesh]
    mesh_width, mesh_depth, _mesh_height = _mesh_dimensions(triangles)
    if mesh_width > bed_width + 1e-6 or mesh_depth > bed_depth + 1e-6:
        raise Accessory3DError(
            f"曲面化後の配置({mesh_width:.1f}×{mesh_depth:.1f}mm)が指定した造形範囲"
            f"({bed_width:.0f}×{bed_depth:.0f}mm)に収まりません。"
            "造形範囲を大きくするか、輪郭・厚み・曲率半径を見直してください。")
    count = _write_ascii_stl(output_path, triangles)
    warnings: list[str] = []
    if thickness < 1.2:
        warnings.append("厚みが薄いため、素材や向きによっては反り・破損が起きやすくなります。")
    if curvature_radius is not None:
        warnings.append(
            "曲率は画像からの推定ではなく指定値です。装着面の実測または試作品で確認してください。")
    return Accessory3DResult(
        path=output_path, piece_count=len(arranged), thickness_mm=thickness,
        arranged_width_mm=mesh_width, arranged_depth_mm=mesh_depth,
        triangle_count=count, curvature_radius_mm=curvature_radius,
        curvature_radius_height_mm=curvature_height_radius,
        curve_axis=curve_axis, mounting_hole_pattern=hole_pattern,
        mounting_hole_diameter_mm=hole_diameter,
        mounting_slot_pattern=slot_pattern,
        mounting_slot_length_mm=slot_length,
        mounting_slot_width_mm=slot_width, mounting_slot_axis=slot_axis,
        magnet_pocket_pattern=magnet_pattern,
        magnet_pocket_diameter_mm=magnet_diameter,
        magnet_pocket_depth_mm=magnet_depth,
        attachment_interface=attachment,
        warnings=tuple(warnings))
