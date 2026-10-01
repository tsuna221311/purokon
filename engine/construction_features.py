"""確認済みの仕立て情報を、出力共通の型紙線へ反映する。

PDF/SVG/DXFそれぞれへ個別実装すると、ある形式にだけ線が出ない事故になる。
そこでネスティング・出力より前の ``FinalizedPart.reference_lines`` に追加する。
裁断線を変えない補助線（プリーツ、開き止まり、ボーン位置）が対象である。
"""

from __future__ import annotations

from dataclasses import replace
from math import ceil, hypot, isfinite, pi

from shapely.geometry import LineString, Polygon
from shapely.ops import split

from .seam import FinalizedPart, finalize_from_stitch_line


_PETTICOAT_MAX_PANEL_WIDTH_CM = 90.0

INTERFACING_TARGETS: dict[str, frozenset[str]] = {
    "bodice": frozenset({
        "front_bodice", "back_bodice", "front_bodice_zip_panel",
        "front_bodice_center", "front_bodice_side",
        "back_bodice_center", "back_bodice_side",
    }),
    "sleeve": frozenset({"sleeve"}),
    "skirt": frozenset({"skirt"}),
    "pants": frozenset({"front_pants", "back_pants"}),
    "collar": frozenset({"collar"}),
    "cuffs": frozenset({"cuffs"}),
    "waistband": frozenset({"waistband"}),
    "hood": frozenset({"hood"}),
    "custom_panel": frozenset({"custom_panel"}),
}


def _rectangle_part(part_type: str, variation: str, width_cm: float,
                    height_cm: float, seam_allowance_cm: float,
                    label_suffix: str,
                    references: list[tuple[str, list[tuple[float, float]]]] | None = None
                    ) -> FinalizedPart:
    stitch = [(0.0, 0.0), (width_cm, 0.0), (width_cm, height_cm),
              (0.0, height_cm), (0.0, 0.0)]
    return finalize_from_stitch_line(
        part_type, variation, stitch, seam_allowance_cm=seam_allowance_cm,
        label_suffix=label_suffix, reference_lines=references or [])


def _add_petticoat(parts: list[FinalizedPart], features: dict[str, object]
                   ) -> list[FinalizedPart]:
    """確認済み寸法から段式パニエを独立した裁断パーツとして追加する。"""
    style = str(features.get("petticoat_style") or "")
    tier_count = int(features.get("petticoat_tier_count") or 0)
    length_cm = float(features.get("petticoat_length_cm") or 0)
    waist_cm = float(features.get("petticoat_waist_cm") or 0)
    seam = float(features.get("petticoat_seam_allowance_cm") or 1.0)
    if style not in {"soft", "hoop"} or not 1 <= tier_count <= 5:
        raise ValueError("パニエは方式と1〜5段の段数を確定してください。")
    if not 20 <= length_cm <= 120 or not 40 <= waist_cm <= 200:
        raise ValueError("パニエ丈は20〜120cm、仕上がりウエストは40〜200cmで指定してください。")

    circumferences: list[float]
    if style == "soft":
        fullness = float(features.get("petticoat_fullness_ratio") or 0)
        if not 1.2 <= fullness <= 2.5:
            raise ValueError("柔らかいパニエの段倍率は1.2〜2.5倍で指定してください。")
        circumferences = [waist_cm * fullness ** (index + 1)
                          for index in range(tier_count)]
    else:
        raw = features.get("petticoat_hoop_diameters_cm")
        if not isinstance(raw, (list, tuple)) or len(raw) != tier_count:
            raise ValueError("ワイヤーパニエは段数と同じ数の輪直径が必要です。")
        diameters = [float(value) for value in raw]
        if any(not 20 <= value <= 180 for value in diameters):
            raise ValueError("ワイヤー輪の直径は各20〜180cmで指定してください。")
        if any(b <= a for a, b in zip(diameters, diameters[1:])):
            raise ValueError("ワイヤー輪の直径は上段から下段へ大きくしてください。")
        circumferences = [pi * value for value in diameters]

    tier_height = length_cm / tier_count
    additions: list[FinalizedPart] = []
    previous = waist_cm
    for tier_index, circumference in enumerate(circumferences, start=1):
        if circumference > 900:
            raise ValueError("パニエの段周長が900cmを超えます。倍率または直径を下げてください。")
        panel_count = max(1, ceil(circumference / _PETTICOAT_MAX_PANEL_WIDTH_CM))
        panel_width = circumference / panel_count
        for panel_index in range(1, panel_count + 1):
            references = [(
                f"上辺を段全体で{previous:.1f}cmへ寄せる",
                [(0.0, 0.0), (panel_width, 0.0)],
            )]
            if style == "hoop":
                diameter = float(features["petticoat_hoop_diameters_cm"][tier_index - 1])
                references.append((
                    f"ワイヤー通し位置・輪直径{diameter:g}cm",
                    [(0.0, tier_height - 2.0),
                     (panel_width, tier_height - 2.0)],
                ))
            additions.append(_rectangle_part(
                "petticoat_tier", style, panel_width, tier_height, seam,
                f"第{tier_index}段・{panel_index}/{panel_count}", references))
        previous = circumference

    band_length = waist_cm + 3.0
    band_panels = max(1, ceil(band_length / _PETTICOAT_MAX_PANEL_WIDTH_CM))
    band_width = band_length / band_panels
    for panel_index in range(1, band_panels + 1):
        additions.append(_rectangle_part(
            "petticoat_waistband", style, band_width, 4.0, seam,
            f"ゴム通し・{panel_index}/{band_panels}（全長に打ち合わせ3cm含む）",
            [("ゴム通し折り線", [(0.0, 2.0), (band_width, 2.0)])]))
    return [*parts, *additions]


def _vertical(part: FinalizedPart, x_ratio: float,
              y_start_ratio: float = 0.05,
              y_end_ratio: float = 0.95) -> list[tuple[float, float]]:
    x0, y0, x1, y1 = part.bbox
    x = x0 + (x1 - x0) * x_ratio
    return [(x, y0 + (y1 - y0) * y_start_ratio),
            (x, y0 + (y1 - y0) * y_end_ratio)]


def _with_reference(part: FinalizedPart, label: str,
                    points: list[tuple[float, float]]) -> FinalizedPart:
    return replace(part, reference_lines=[*part.reference_lines, (label, points)])


def _layer_one_skirts(parts: list[FinalizedPart]) -> list[FinalizedPart]:
    skirts = [part for part in parts if part.part_type == "skirt"]
    layered = any("第" in part.label_suffix for part in skirts)
    if not layered:
        return skirts
    return [part for part in skirts if "第1層" in part.label_suffix]


def _scale_points_x(points, centre_x: float, ratio: float):
    return [(centre_x + (x - centre_x) * ratio, y) for x, y in points]


def _apply_gather_ratio(parts: list[FinalizedPart], ratio: float
                        ) -> list[FinalizedPart]:
    """スカートの裁ち幅を実際に広げ、寄せ上がり寸法を保持する。"""
    if ratio <= 1.0 + 1e-9:
        return parts
    from .compatibility import waist_opening_length

    targets = [part for part in parts if part.part_type == "skirt"]
    if not targets:
        raise ValueError("ギャザー倍率を反映するスカート型紙がありません。")
    target_ids = {id(part) for part in targets}
    output: list[FinalizedPart] = []
    for part in parts:
        if id(part) not in target_ids:
            output.append(part)
            continue
        original_waist = waist_opening_length(part)
        x0, _y0, x1, _y1 = part.bbox
        centre_x = (x0 + x1) / 2.0
        stitch = _scale_points_x(part.stitch_line, centre_x, ratio)
        internal = [_scale_points_x(line, centre_x, ratio)
                    for line in part.internal_lines]
        references = [
            (label, _scale_points_x(points, centre_x, ratio))
            for label, points in part.reference_lines
        ]
        top_y = min(y for _x, y in stitch)
        top_xs = [x for x, y in stitch if abs(y - top_y) <= 1e-6]
        if len(top_xs) >= 2:
            references.append((
                f"ギャザー寄せ {ratio:g}倍→出来上がり{original_waist:.1f}cm",
                [(min(top_xs), top_y), (max(top_xs), top_y)],
            ))
        measures = dict(part.compatibility_measurements)
        measures["waist_opening_length"] = original_waist
        output.append(finalize_from_stitch_line(
            part.part_type, part.variation, stitch,
            seam_allowance_cm=part.seam_allowance_cm,
            hem_seam_allowance_cm=part.hem_seam_allowance_cm,
            label_suffix=(part.label_suffix + "・" if part.label_suffix else "")
                         + f"ギャザー{ratio:g}倍",
            dart_count=part.dart_count, seam_edge=part.seam_edge,
            internal_lines=internal, reference_lines=references,
            underarm_y_cm=part.underarm_y_cm,
            compatibility_measurements=measures,
        ))
    return output


def _waist_edge_span(part: FinalizedPart) -> tuple[float, float]:
    """ウエスト側(上端)の辺の、左右の端のx(round77)。"""
    top = min(y for _x, y in part.stitch_line)
    xs = [x for x, y in part.stitch_line if abs(y - top) <= 0.01]
    if len(xs) < 2:
        return (0.0, 0.0)
    return (min(xs), max(xs))


def _add_pleats(parts: list[FinalizedPart], total_count: int,
                 depth_cm: float | None) -> list[FinalizedPart]:
    if total_count <= 0:
        return parts
    if depth_cm is None:
        raise ValueError("プリーツ本数を指定した場合は、ひだ深さ(cm)も必要です。")
    targets = _layer_one_skirts(parts)
    if not targets:
        raise ValueError("プリーツ線を入れるスカート型紙がありません。")
    front = [part for part in targets if part.label_suffix.startswith("前")]
    back = [part for part in targets if part.label_suffix.startswith("後")]
    ordered = front + back or targets
    base, extra = divmod(total_count, len(ordered))
    counts = [base + (1 if index < extra else 0) for index in range(len(ordered))]
    target_ids = {id(part): count for part, count in zip(ordered, counts)}
    out: list[FinalizedPart] = []
    for part in parts:
        count = target_ids.get(id(part), 0)
        if count <= 0:
            out.append(part)
            continue
        from .compatibility import waist_opening_length
        original_waist = (waist_opening_length(part)
                          if part.part_type == "skirt" else None)
        # round77: 広げる量は**ウエスト辺**から出す。
        #
        # 【v125で何が起きていたか】外接矩形の幅を基準にしていた。
        # フレアスカートの外接幅は裾幅(85.3cm)で、ウエスト辺(35.0cm)の
        # 2.4倍ある。そのぶん倍率が足りず、ウエストに必要な量が届かない。
        # 実測(ウエスト辺35.00cm・1枚あたり):
        #
        #     プリーツ3本×2cm  ウエスト辺38.28cm  畳む量12.0cm  仕上がり26.28cm
        #     プリーツ6本×2cm  ウエスト辺39.92cm  畳む量24.0cm  仕上がり15.92cm
        #
        # 1枚15.92cm×4枚=一周63.7cm。ウエスト68cmの人は着られない。
        waist_lo, waist_hi = _waist_edge_span(part)
        waist_width = waist_hi - waist_lo
        if waist_width <= 0:
            raise ValueError("プリーツ: ウエスト側の辺を取り出せませんでした。")
        x0, _y0, x1, _y1 = part.bbox
        extra = 2.0 * depth_cm * count
        ratio = (waist_width + extra) / waist_width
        centre_x = (x0 + x1) / 2.0
        stitch = _scale_points_x(part.stitch_line, centre_x, ratio)
        internal = [_scale_points_x(line, centre_x, ratio)
                    for line in part.internal_lines]
        references = [
            (label, _scale_points_x(points, centre_x, ratio))
            for label, points in part.reference_lines
        ]
        measures = dict(part.compatibility_measurements)
        updated = finalize_from_stitch_line(
            part.part_type, part.variation, stitch,
            seam_allowance_cm=part.seam_allowance_cm,
            hem_seam_allowance_cm=part.hem_seam_allowance_cm,
            label_suffix=(part.label_suffix + "・" if part.label_suffix else "")
                         + f"プリーツ{count}本・深さ{depth_cm:g}cm",
            dart_count=part.dart_count, seam_edge=part.seam_edge,
            internal_lines=internal, reference_lines=references,
            underarm_y_cm=part.underarm_y_cm,
            compatibility_measurements=measures,
        )
        # round77: 折り線も**ウエスト辺の上**に置く。外接矩形の幅で割ると、
        # 裾が広がったスカートではウエスト辺の外に線が出る(実測: 6本中4本が
        # 外に出ていて、そのままではたためなかった)。
        new_lo, new_hi = _waist_edge_span(updated)
        expanded_y0 = min(y for _x, y in updated.stitch_line)
        expanded_y1 = max(y for _x, y in updated.stitch_line)
        cell = (new_hi - new_lo) / count
        for index in range(count):
            center = new_lo + (index + 0.5) * cell
            updated = _with_reference(
                updated, f"プリーツ{index + 1} 折り山",
                [(center - depth_cm, expanded_y0),
                 (center - depth_cm, expanded_y1)])
            updated = _with_reference(
                updated, f"プリーツ{index + 1} 折り合わせ（深さ{depth_cm:g}cm）",
                [(center + depth_cm, expanded_y0),
                 (center + depth_cm, expanded_y1)])
        # たたんだあとのウエストを、**実際の輪郭から測って**持たせる。
        # v125はここへ「広げる前の値」を書き込んでいたので、幅が足りて
        # いなくても縫い合わせの検査を通ってしまった。
        if original_waist is not None:
            measured = waist_opening_length(updated)
            if measured is not None:
                updated = replace(updated,
                                  compatibility_measurements={
                                      **measures,
                                      "waist_opening_length": measured - extra})
        out.append(updated)
    return out


def _slit_targets(parts: list[FinalizedPart], position: str) -> list[FinalizedPart]:
    skirts = _layer_one_skirts(parts)
    if position == "front":
        return [part for part in skirts if part.label_suffix.startswith("前")]
    if position == "back":
        return [part for part in skirts if part.label_suffix.startswith("後")]
    # 脇スリットは前後両方の脇線に縫い止まりを示す。
    if position in {"left", "right"}:
        return skirts
    return []


def _split_skirt_for_center_slit(part: FinalizedPart, length_cm: float,
                                 position: str) -> list[FinalizedPart]:
    """全幅スカートを中心で2枚へ分け、中央スリットを縫える形にする。"""
    from .compatibility import waist_opening_length

    polygon = Polygon(part.stitch_line)
    if not polygon.is_valid:
        polygon = polygon.buffer(0)
    x0, y0, x1, y1 = polygon.bounds
    centre_x = (x0 + x1) / 2.0
    cutter = LineString([(centre_x, y0 - 10), (centre_x, y1 + 10)])
    pieces = [shape for shape in split(polygon, cutter).geoms
              if shape.geom_type == "Polygon" and shape.area > 0.1]
    if len(pieces) != 2:
        raise ValueError("中央スリット用にスカートを左右へ分割できませんでした。")
    original_waist = waist_opening_length(part)
    label = "前中心" if position == "front" else "後中心"
    output: list[FinalizedPart] = []
    for shape in sorted(pieces, key=lambda item: item.centroid.x):
        side = "左" if shape.centroid.x < centre_x else "右"
        internal = _clipped_lines(part.internal_lines, shape)
        references = []
        for old_label, points in part.reference_lines:
            for clipped in _clipped_lines([points], shape):
                references.append((old_label, clipped))
        centre_section = shape.boundary.intersection(cutter)
        lines = ([centre_section] if centre_section.geom_type == "LineString"
                 else [line for line in getattr(centre_section, "geoms", [])
                       if line.geom_type == "LineString"])
        if not lines:
            raise ValueError("中央スリットの縫い線を特定できませんでした。")
        centre_line = max(lines, key=lambda line: line.length)
        bottom_y = max(y for _x, y in centre_line.coords)
        top_y = min(y for _x, y in centre_line.coords)
        if length_cm >= bottom_y - top_y:
            raise ValueError(
                f"スリット長{length_cm:g}cmが中心縫い線"
                f"{bottom_y - top_y:.1f}cm以上です。")
        references.append((
            f"{label}スリット（裾から{length_cm:g}cm）",
            [(centre_x, bottom_y), (centre_x, bottom_y - length_cm)],
        ))
        measures = dict(part.compatibility_measurements)
        measures["waist_opening_length"] = original_waist / 2.0
        output.append(finalize_from_stitch_line(
            part.part_type, part.variation, list(shape.exterior.coords),
            seam_allowance_cm=part.seam_allowance_cm,
            hem_seam_allowance_cm=part.hem_seam_allowance_cm,
            label_suffix=(part.label_suffix + "・" if part.label_suffix else "")
                         + f"{label}スリット・{side}",
            dart_count=max(0, part.dart_count // 2), seam_edge=part.seam_edge,
            internal_lines=internal, reference_lines=references,
            underarm_y_cm=part.underarm_y_cm,
            compatibility_measurements=measures,
        ))
    return output


def _side_slit_line(part: FinalizedPart, side: str,
                    length_cm: float) -> list[tuple[float, float]]:
    """裾角から実際の外周脇線を上へ指定長だけたどる。"""
    ring = list(part.stitch_line)
    if ring and ring[0] == ring[-1]:
        ring.pop()
    if len(ring) < 3:
        raise ValueError("脇スリットを配置する輪郭が不正です。")
    bottom_y = max(y for _x, y in ring)
    bottom_indices = [i for i, (_x, y) in enumerate(ring)
                      if abs(y - bottom_y) <= 1e-5]
    if not bottom_indices:
        raise ValueError("脇スリットの裾角を特定できませんでした。")
    corner = (min(bottom_indices, key=lambda i: ring[i][0]) if side == "left"
              else max(bottom_indices, key=lambda i: ring[i][0]))
    n = len(ring)
    directions = []
    for step in (-1, 1):
        nxt = ring[(corner + step) % n]
        # 裾線ではなく、上へ向かう隣接辺を選ぶ。
        if nxt[1] < bottom_y - 1e-5:
            directions.append(step)
    if len(directions) != 1:
        raise ValueError("脇スリットの裾から上へ続く脇線を一意に特定できません。")
    step = directions[0]
    output = [ring[corner]]
    remaining = length_cm
    index = corner
    for _ in range(n - 1):
        nxt_index = (index + step) % n
        start, end = ring[index], ring[nxt_index]
        segment = hypot(end[0] - start[0], end[1] - start[1])
        if segment <= 1e-9:
            index = nxt_index
            continue
        used = min(segment, remaining)
        ratio = used / segment
        output.append((start[0] + (end[0] - start[0]) * ratio,
                       start[1] + (end[1] - start[1]) * ratio))
        remaining -= used
        if remaining <= 1e-6:
            return output
        index = nxt_index
        # 上端へ回り込む前に止める。スリットは脇縫い線内だけに置く。
        if end[1] <= min(y for _x, y in ring) + 1e-5:
            break
    raise ValueError(
        f"スリット長{length_cm:g}cmが{part.display_name}の脇縫い線に収まりません。")


def _add_slit(parts: list[FinalizedPart], position: str,
              length_cm: float) -> list[FinalizedPart]:
    targets = _slit_targets(parts, position)
    if not targets:
        raise ValueError("スリット位置に対応するスカート型紙がありません。")
    shortest = min(part.height_cm for part in targets)
    if length_cm >= shortest:
        raise ValueError(
            f"スリット長{length_cm:g}cmが対象パーツ丈{shortest:.1f}cm以上です。"
            "丈より短い値を指定してください。")
    target_ids = {id(part) for part in targets}
    out: list[FinalizedPart] = []
    for part in parts:
        if id(part) not in target_ids:
            out.append(part)
            continue
        if position in {"front", "back"}:
            out.extend(_split_skirt_for_center_slit(part, length_cm, position))
        else:
            out.append(_with_reference(
                part, f"{position}脇スリット（裾から{length_cm:g}cm）",
                _side_slit_line(part, position, length_cm)))
    return out


def _clipped_lines(lines, polygon: Polygon):
    """内部線を分割後の片側に切り詰める。点だけの交差は捨てる。"""
    output = []
    for entry in lines:
        geometry = LineString(entry).intersection(polygon)
        candidates = ([geometry] if geometry.geom_type == "LineString"
                      else list(getattr(geometry, "geoms", [])))
        output.extend([list(line.coords) for line in candidates
                       if line.geom_type == "LineString" and line.length > 1e-6])
    return output


def _split_back_for_zip(part: FinalizedPart, opening_cm: float) -> list[FinalizedPart]:
    """全幅の後身頃を中心後で左右2枚へ分け、中心後にも縫い代を付ける。"""
    from .compatibility import (armhole_length, neckline_length,
                                shoulder_seam_length, side_seam_length)

    full_measurements = {
        "armhole_length": armhole_length(part),
        "neckline_length": neckline_length(part),
        "shoulder_seam_length": shoulder_seam_length(part),
        "side_seam_length": side_seam_length(part),
    }
    if any(value is None for value in full_measurements.values()):
        raise ValueError(
            "後ろファスナー分割前の袖ぐり・首ぐり・肩線・脇線を測定できません。"
            "縫い合わせを検査できないため生成を中止しました。")
    polygon = Polygon(part.stitch_line)
    if not polygon.is_valid:
        polygon = polygon.buffer(0)
    x0, y0, x1, y1 = polygon.bounds
    centre_x = (x0 + x1) / 2.0
    cutter = LineString([(centre_x, y0 - 10.0), (centre_x, y1 + 10.0)])
    pieces = [shape for shape in split(polygon, cutter).geoms
              if shape.geom_type == "Polygon" and shape.area > 0.1]
    if len(pieces) != 2:
        raise ValueError(
            "後ろファスナー用に後身頃を中心後で2枚へ分割できませんでした。"
            "別の襟ぐりまたは前ファスナーを選んでください。")
    height = y1 - y0
    if not 1.0 <= opening_cm < height:
        raise ValueError(
            f"後ろファスナーの開き{opening_cm:g}cmは、後身頃丈{height:.1f}cm未満で"
            "指定してください。")

    output = []
    for shape in sorted(pieces, key=lambda item: item.centroid.x):
        side = "左" if shape.centroid.x < centre_x else "右"
        internal = _clipped_lines(part.internal_lines, shape)
        references = []
        for label, points in part.reference_lines:
            for clipped in _clipped_lines([points], shape):
                references.append((label, clipped))
        centre_section = shape.boundary.intersection(cutter)
        centre_lines = ([centre_section] if centre_section.geom_type == "LineString"
                        else [line for line in getattr(centre_section, "geoms", [])
                              if line.geom_type == "LineString"])
        if not centre_lines:
            raise ValueError("後ろファスナーの中心後線を型紙上で特定できませんでした。")
        centre_line = max(centre_lines, key=lambda line: line.length)
        top_y = min(y for _x, y in centre_line.coords)
        references.append((
            f"後中心ファスナー開き止まり（上から{opening_cm:g}cm）",
            [(centre_x, top_y), (centre_x, top_y + opening_cm)],
        ))
        finalized = finalize_from_stitch_line(
            part.part_type, part.variation, list(shape.exterior.coords),
            seam_allowance_cm=part.seam_allowance_cm,
            hem_seam_allowance_cm=part.hem_seam_allowance_cm,
            label_suffix=(part.label_suffix + "・" if part.label_suffix else "")
                         + f"後中心ファスナー・{side}",
            dart_count=max(0, part.dart_count // 2),
            seam_edge=part.seam_edge, internal_lines=internal,
            reference_lines=references, underarm_y_cm=part.underarm_y_cm,
            compatibility_measurements={
                "armhole_length": full_measurements["armhole_length"] / 2.0,
                "neckline_length": full_measurements["neckline_length"] / 2.0,
                "shoulder_seam_length": full_measurements["shoulder_seam_length"],
                "side_seam_length": full_measurements["side_seam_length"] / 2.0,
            },
        )
        output.append(finalized)
    return output


def _side_zip_reference_lines(part: FinalizedPart,
                              opening_cm: float
                              ) -> list[list[tuple[float, float]]]:
    """右脇の実際の縫い線を、脇下から指定長だけ返す。

    身頃の脇線はウエストの絞りや胸ぐせダーツで折れるため、外接矩形上の
    垂直線では製作位置を表せない。互換性検査と同じ脇線検出器を使い、
    ダーツ口では線をつながず複数区間として保持する。
    """
    from .compatibility import side_seam_edges, underarm_y_of

    edges = [entry for entry in side_seam_edges(
        part.stitch_line, underarm_y=underarm_y_of(part))
             if entry[1] == "right"]
    if not edges:
        raise ValueError(
            f"{part.display_name}の右脇縫い線を特定できないため、"
            "脇ファスナーを配置できませんでした。")

    # 座標系は上から下へyが増える。各区間を脇下側から裾側へ向けて並べる。
    ordered: list[tuple[tuple[float, float], tuple[float, float]]] = []
    for _index, _side, first, second in edges:
        ordered.append((first, second) if first[1] <= second[1]
                       else (second, first))
    ordered.sort(key=lambda entry: (entry[0][1], entry[1][1]))

    available = sum(hypot(end[0] - start[0], end[1] - start[1])
                    for start, end in ordered)
    if not 1.0 <= opening_cm <= available + 1e-6:
        raise ValueError(
            f"脇ファスナーの開き{opening_cm:g}cmは、{part.display_name}の"
            f"縫える片脇線{available:.1f}cm以内で指定してください。")

    remaining = opening_cm
    output: list[list[tuple[float, float]]] = []
    for start, end in ordered:
        if remaining <= 1e-6:
            break
        length = hypot(end[0] - start[0], end[1] - start[1])
        if length <= 1e-9:
            continue
        used = min(length, remaining)
        ratio = used / length
        clipped_end = (
            start[0] + (end[0] - start[0]) * ratio,
            start[1] + (end[1] - start[1]) * ratio,
        )
        output.append([start, clipped_end])
        remaining -= used
    if remaining > 1e-5:
        raise ValueError(
            f"{part.display_name}の脇線上へ指定長を配置できませんでした。")
    return output


def _split_back_for_discrete_closure(
        part: FinalizedPart, closure: str, count: int, spacing_cm: float,
        overlap_cm: float = 0.0) -> list[FinalizedPart]:
    """後中心を左右へ分割し、ホックまたはスナップの実位置を作る。"""
    from .compatibility import (armhole_length, neckline_length,
                                shoulder_seam_length, side_seam_length)

    label = "ホック" if closure == "hooks" else "スナップ"
    measurements = {
        "armhole_length": armhole_length(part),
        "neckline_length": neckline_length(part),
        "shoulder_seam_length": shoulder_seam_length(part),
        "side_seam_length": side_seam_length(part),
    }
    if any(value is None for value in measurements.values()):
        raise ValueError(
            f"{label}分割前の縫い合わせ寸法を測定できないため生成を中止しました。")
    polygon = Polygon(part.stitch_line)
    if not polygon.is_valid:
        polygon = polygon.buffer(0)
    x0, y0, x1, y1 = polygon.bounds
    centre_x = (x0 + x1) / 2.0
    cutter = LineString([(centre_x, y0 - 10.0), (centre_x, y1 + 10.0)])
    pieces = [shape for shape in split(polygon, cutter).geoms
              if shape.geom_type == "Polygon" and shape.area > 0.1]
    if len(pieces) != 2:
        raise ValueError(f"{label}用に後身頃を中心後で2枚へ分割できませんでした。")

    output: list[FinalizedPart] = []
    for original_shape in sorted(pieces, key=lambda item: item.centroid.x):
        side = "左" if original_shape.centroid.x < centre_x else "右"
        centre_section = original_shape.boundary.intersection(cutter)
        centre_lines = ([centre_section] if centre_section.geom_type == "LineString"
                        else [line for line in getattr(centre_section, "geoms", [])
                              if line.geom_type == "LineString"])
        if not centre_lines:
            raise ValueError(f"{label}の後中心線を特定できませんでした。")
        centre_line = max(centre_lines, key=lambda line: line.length)
        top_y = min(y for _x, y in centre_line.coords)
        bottom_y = max(y for _x, y in centre_line.coords)
        span = (count - 1) * spacing_cm
        if span > bottom_y - top_y + 1e-6:
            raise ValueError(
                f"{label}{count}個×間隔{spacing_cm:g}cmは、後中心の取付可能長"
                f"{bottom_y - top_y:.1f}cmに収まりません。")

        shape = original_shape
        if closure == "snaps" and side == "右":
            extension = Polygon([
                (centre_x - overlap_cm, top_y), (centre_x, top_y),
                (centre_x, bottom_y), (centre_x - overlap_cm, bottom_y),
            ])
            shape = shape.union(extension)
            if shape.geom_type != "Polygon":
                raise ValueError("スナップの持ち出しを単一の型紙へ追加できませんでした。")

        internal = _clipped_lines(part.internal_lines, shape)
        references = []
        for old_label, points in part.reference_lines:
            for clipped in _clipped_lines([points], shape):
                references.append((old_label, clipped))
        mark_x = centre_x - overlap_cm / 2.0 if closure == "snaps" else centre_x
        for index in range(count):
            y = top_y + index * spacing_cm
            references.append((
                f"{label}{index + 1}/{count}（間隔{spacing_cm:g}cm）",
                [(mark_x - 0.3, y), (mark_x + 0.3, y)],
            ))
        if closure == "snaps" and side == "右":
            references.append((
                f"スナップ持ち出し・重なり{overlap_cm:g}cm",
                [(centre_x - overlap_cm, top_y),
                 (centre_x - overlap_cm, bottom_y)],
            ))
        output.append(finalize_from_stitch_line(
            part.part_type, part.variation, list(shape.exterior.coords),
            seam_allowance_cm=part.seam_allowance_cm,
            hem_seam_allowance_cm=part.hem_seam_allowance_cm,
            label_suffix=(part.label_suffix + "・" if part.label_suffix else "")
                         + f"後中心{label}・{side}",
            dart_count=max(0, part.dart_count // 2),
            seam_edge=part.seam_edge, internal_lines=internal,
            reference_lines=references, underarm_y_cm=part.underarm_y_cm,
            compatibility_measurements={
                "armhole_length": measurements["armhole_length"] / 2.0,
                "neckline_length": measurements["neckline_length"] / 2.0,
                "shoulder_seam_length": measurements["shoulder_seam_length"],
                "side_seam_length": measurements["side_seam_length"] / 2.0,
            },
        ))
    return output


def _add_closure(parts: list[FinalizedPart], closure: str,
                 opening_cm: float | None, *, count: int | None = None,
                 spacing_cm: float | None = None,
                 overlap_cm: float | None = None, draft_mode: bool = False
                 ) -> list[FinalizedPart]:
    labels = {
        "back_zip": "後中心ファスナー",
        "side_zip": "脇ファスナー",
        "hooks": "ホック位置",
        "snaps": "スナップ位置",
    }
    if closure not in labels:
        return parts
    if draft_mode and ((closure in {"hooks", "snaps"}
                        and (count is None or spacing_cm is None
                             or (closure == "snaps" and overlap_cm is None)))
                       or (closure in {"back_zip", "side_zip"} and opening_cm is None)):
        return parts
    if closure in {"back_zip", "side_zip"} and opening_cm is None:
        raise ValueError("後ろ・脇ファスナーには開きの長さ(cm)が必要です。")
    if closure in {"hooks", "snaps"}:
        if count is None or spacing_cm is None:
            raise ValueError("ホック／スナップには個数と取付間隔(cm)が必要です。")
        if closure == "snaps" and overlap_cm is None:
            raise ValueError("スナップには布の重なり量(cm)が必要です。")
        output = []
        found = False
        for part in parts:
            if part.part_type == "back_bodice":
                output.extend(_split_back_for_discrete_closure(
                    part, closure, count, spacing_cm, overlap_cm or 0.0))
                found = True
            else:
                output.append(part)
        if not found:
            raise ValueError("ホック／スナップを付ける後身頃型紙がありません。")
        return output
    if closure == "back_zip":
        output = []
        found = False
        for part in parts:
            if part.part_type == "back_bodice":
                output.extend(_split_back_for_zip(part, float(opening_cm)))
                found = True
            else:
                output.append(part)
        if not found:
            raise ValueError("後ろファスナーを入れる後身頃型紙がありません。")
        return output

    out: list[FinalizedPart] = []
    for part in parts:
        target = (part.part_type == "back_bodice" if closure != "side_zip"
                  else part.part_type in {"front_bodice", "back_bodice"})
        if not target:
            out.append(part)
            continue
        if closure == "side_zip":
            updated = part
            label = f"右脇ファスナー開き（脇下から{float(opening_cm):g}cm）"
            for points in _side_zip_reference_lines(part, float(opening_cm)):
                updated = _with_reference(updated, label, points)
            out.append(updated)
        else:
            out.append(_with_reference(
                part, f"{labels[closure]}開き止まり（{float(opening_cm):g}cm）",
                _vertical(part, 0.5, 0.02, 0.98)))
    return out


def _add_boning(parts: list[FinalizedPart]) -> list[FinalizedPart]:
    out: list[FinalizedPart] = []
    for part in parts:
        if part.part_type not in {"front_bodice", "back_bodice"}:
            out.append(part)
            continue
        updated = part
        for index, ratio in enumerate((0.25, 0.5, 0.75), start=1):
            updated = _with_reference(
                updated, f"ボーン位置{index}/3", _vertical(updated, ratio, 0.12, 0.92))
        out.append(updated)
    return out


def _add_interfacing(parts: list[FinalizedPart], targets_raw: object,
                     inset_cm: float, *, draft_mode: bool = False
                     ) -> list[FinalizedPart]:
    """選択部位へ、実際に写せる芯地裁断線と個別の裁断指示を付ける。"""
    if not isinstance(targets_raw, (list, tuple)) or not targets_raw:
        if draft_mode:
            return parts
        raise ValueError("接着芯を選んだ場合は、貼る部位を1つ以上指定してください。")
    targets = [str(value) for value in targets_raw]
    unknown = sorted(set(targets) - set(INTERFACING_TARGETS))
    if unknown:
        raise ValueError(f"接着芯の貼り先が不正です: {unknown}")
    if not 0 <= inset_cm <= 5:
        raise ValueError("接着芯の縁からの控えは0〜5cmで指定してください。")
    found: set[str] = set()
    output: list[FinalizedPart] = []
    for part in parts:
        matched = [key for key in targets
                   if part.part_type in INTERFACING_TARGETS[key]]
        if not matched:
            output.append(part)
            continue
        found.update(matched)
        polygon = Polygon(part.stitch_line)
        if not polygon.is_valid:
            polygon = polygon.buffer(0)
        region = polygon if inset_cm <= 1e-9 else polygon.buffer(-inset_cm)
        candidates = ([region] if region.geom_type == "Polygon" else
                      [item for item in getattr(region, "geoms", [])
                       if item.geom_type == "Polygon"])
        if not candidates:
            raise ValueError(
                f"{part.display_name}は縁から{inset_cm:g}cm控えると"
                "接着芯の面積が残りません。控え寸法を小さくしてください。")
        region = max(candidates, key=lambda item: item.area)
        points = list(region.exterior.coords)
        label = ("接着芯裁断線（端から"
                 f"{inset_cm:g}cm内側）" if inset_cm > 0 else
                 "接着芯裁断線（縫い線と同じ）")
        output.append(replace(
            _with_reference(part, label, points),
            interfacing_instruction=(
                f"接着芯あり（型紙内の芯地裁断線で裁つ・"
                f"端から{inset_cm:g}cm内側）")))
    missing = [key for key in targets if key not in found]
    if missing:
        raise ValueError(
            "接着芯の貼り先に対応する型紙がありません: " + "・".join(missing))
    return output


def _normalised_motif_points(raw: object) -> list[tuple[float, float]] | None:
    """画像から保存した0..1輪郭を検証する。未指定なら従来の矩形を使う。"""
    if raw in (None, "", []):
        return None
    if not isinstance(raw, (list, tuple)) or not 3 <= len(raw) <= 400:
        raise ValueError("装飾画像の輪郭は3〜400点で指定してください。")
    points: list[tuple[float, float]] = []
    for point in raw:
        if not isinstance(point, (list, tuple)) or len(point) != 2:
            raise ValueError("装飾画像の輪郭座標が不正です。画像を選び直してください。")
        try:
            x, y = float(point[0]), float(point[1])
        except (TypeError, ValueError):
            raise ValueError("装飾画像の輪郭座標が不正です。画像を選び直してください。") from None
        if not isfinite(x) or not isfinite(y) or not 0 <= x <= 1 or not 0 <= y <= 1:
            raise ValueError("装飾画像の輪郭座標は0〜1の範囲で指定してください。")
        points.append((x, y))
    if points[0] != points[-1]:
        points.append(points[0])
    polygon = Polygon(points)
    if not polygon.is_valid or polygon.area <= 1e-6:
        raise ValueError("装飾画像から有効な閉じた輪郭を作れませんでした。")
    return points


def _normalised_motif_regions(raw: object) -> list[tuple[str, list[tuple[float, float]]]]:
    """主要色面の輪郭と色コードを検証する。"""
    if raw in (None, "", []):
        return []
    if not isinstance(raw, (list, tuple)) or len(raw) > 8:
        raise ValueError("装飾画像の色面は8領域以内で指定してください。")
    output = []
    for region in raw:
        if not isinstance(region, dict):
            raise ValueError("装飾画像の色面データが不正です。")
        colour = str(region.get("color") or "").upper()
        if len(colour) != 7 or not colour.startswith("#") or any(
                char not in "0123456789ABCDEF" for char in colour[1:]):
            raise ValueError("装飾画像の色コードが不正です。")
        points = _normalised_motif_points(region.get("points"))
        if points:
            output.append((colour, points))
    return output


def _placed_motif(part: FinalizedPart, width_cm: float, height_cm: float,
                  normalised: list[tuple[float, float]] | None
                  ) -> list[tuple[float, float]]:
    """指定寸法を変えず、型紙内に収まる最も中央寄りの位置を探す。"""
    shape = Polygon(part.stitch_line)
    if not shape.is_valid:
        shape = shape.buffer(0)
    x0, y0, x1, y1 = shape.bounds
    if width_cm >= x1 - x0 or height_cm >= y1 - y0:
        raise ValueError(
            f"装飾{width_cm:g}×{height_cm:g}cmが対象パーツ"
            f"{part.width_cm:.1f}×{part.height_cm:.1f}cmに収まりません。")
    unit = normalised or [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0),
                          (0.0, 1.0), (0.0, 0.0)]
    # 胸・背・スカートの中央付近を優先し、輪郭が袖ぐりや脇線へ掛かる場合だけ
    # 少しずつ位置をずらす。寸法を黙って縮小しない。
    preferred_y = y0 + (y1 - y0) * 0.45
    centre_x = (x0 + x1) / 2.0
    x_span = max(0.0, (x1 - x0 - width_cm) / 2.0)
    y_span = max(0.0, (y1 - y0 - height_cm) / 2.0)
    offsets = [(0.0, 0.0)]
    for step in (0.15, 0.3, 0.45, 0.6, 0.8, 1.0):
        offsets.extend([
            (0.0, -y_span * step), (0.0, y_span * step),
            (-x_span * step, 0.0), (x_span * step, 0.0),
            (-x_span * step, -y_span * step), (x_span * step, -y_span * step),
            (-x_span * step, y_span * step), (x_span * step, y_span * step),
        ])
    for dx, dy in offsets:
        left = centre_x + dx - width_cm / 2.0
        top = preferred_y + dy - height_cm / 2.0
        points = [(left + x * width_cm, top + y * height_cm)
                  for x, y in unit]
        motif = Polygon(points)
        if motif.is_valid and motif.area > 1e-6 and shape.covers(motif):
            return points
    raise ValueError(
        f"装飾{width_cm:g}×{height_cm:g}cmの実際の輪郭が"
        f"{part.display_name}の縫い線内に収まりません。"
        "寸法を小さくするか、配置先を変えてください。")


def _add_motif(parts: list[FinalizedPart], position: str,
               width_cm: float, height_cm: float,
               outline_normalized: object = None,
               regions_normalized: object = None) -> list[FinalizedPart]:
    selectors = {
        "chest_front": lambda p: p.part_type in {"front_bodice", "front_bodice_zip_panel"},
        "chest_back": lambda p: p.part_type == "back_bodice",
        "skirt_front": lambda p: p.part_type == "skirt" and p.label_suffix.startswith("前"),
        "skirt_back": lambda p: p.part_type == "skirt" and p.label_suffix.startswith("後"),
        "sleeve": lambda p: p.part_type == "sleeve",
    }
    selector = selectors.get(position)
    targets = [part for part in parts if selector and selector(part)]
    if position.startswith("skirt_"):
        first_layer = _layer_one_skirts(targets)
        targets = first_layer or targets
    if not targets:
        raise ValueError("装飾配置に対応する型紙パーツがありません。")
    normalised = _normalised_motif_points(outline_normalized)
    regions = _normalised_motif_regions(regions_normalized)
    out: list[FinalizedPart] = []
    target_ids = {id(part) for part in targets}
    for part in parts:
        if id(part) not in target_ids:
            out.append(part)
            continue
        motif_points = _placed_motif(part, width_cm, height_cm, normalised)
        kind = "画像外形" if normalised else "配置線"
        updated = _with_reference(
            part, f"{kind} {width_cm:g}×{height_cm:g}cm", motif_points)
        left = min(x for x, _y in motif_points)
        top = min(y for _x, y in motif_points)
        for index, (colour, region) in enumerate(regions, start=1):
            placed = [(left + x * width_cm, top + y * height_cm)
                      for x, y in region]
            updated = _with_reference(
                updated, f"装飾色面{index} {colour}", placed)
        out.append(updated)
    return out


def apply_construction_features(parts: list[FinalizedPart],
                                features: dict[str, object] | None
                                ) -> list[FinalizedPart]:
    """仕立て確認値を型紙上の補助線へ変換する。"""
    if not features:
        return parts
    out = list(parts)
    if features.get("internal_support") == "petticoat":
        out = _add_petticoat(out, features)
    gather_ratio = float(features.get("gather_ratio") or 1.0)
    pleats = int(features.get("pleat_count") or 0)
    # 両方ある場合は「プリーツを畳んだ後、その上端をギャザーで寄せる」
    # 構造として扱う。裁ち幅と折り込み量の両方を型紙へ反映する。
    if gather_ratio > 1.0:
        out = _apply_gather_ratio(out, gather_ratio)
    if pleats:
        out = _add_pleats(
            out, pleats,
            (float(features["pleat_depth_cm"])
             if features.get("pleat_depth_cm") not in (None, "") else None))
    slit_position = str(features.get("slit_position") or "none")
    if slit_position != "none":
        out = _add_slit(out, slit_position,
                        float(features.get("slit_length_cm") or 0))
    out = _add_closure(
        out, str(features.get("closure") or "auto"),
        (float(features["closure_length_cm"])
         if features.get("closure_length_cm") not in (None, "") else None),
        count=(int(features["closure_count"])
               if features.get("closure_count") not in (None, "") else None),
        spacing_cm=(float(features["closure_spacing_cm"])
                    if features.get("closure_spacing_cm") not in (None, "") else None),
        overlap_cm=(float(features["closure_overlap_cm"])
                    if features.get("closure_overlap_cm") not in (None, "") else None),
        draft_mode=bool(features.get("draft_mode")))
    if features.get("internal_support") == "boning":
        out = _add_boning(out)
    motif_position = str(features.get("motif_position") or "none")
    if motif_position != "none":
        out = _add_motif(
            out, motif_position, float(features.get("motif_width_cm") or 0),
            float(features.get("motif_height_cm") or 0),
            features.get("motif_outline_normalized"),
            features.get("motif_regions_normalized"))
    if features.get("internal_support") == "interfacing":
        out = _add_interfacing(
            out, features.get("interfacing_targets"),
            float(features.get("interfacing_inset_cm") or 0),
            draft_mode=bool(features.get("draft_mode")))
    return out
