"""Pair a sewn costume hem extension with its *actual* bodice hem.

This is deliberately opt-in.  A free-hanging decorative overlay must not be
silently stretched or treated as a structural extension.
"""

from __future__ import annotations

from dataclasses import replace
from math import dist

from .notches import notch_marks_at
from .seam import (FinalizedPart, extend_notches_to_cut_line,
                   finalize_from_stitch_line, offset_polygon_variable)

EDGE_TOLERANCE_CM = 0.03
MATCH_TOLERANCE_CM = 0.1
NOTCH_FRACTIONS = (0.25, 0.75)


def _straight_edge(part: FinalizedPart, *, bottom: bool) -> tuple[float, float, float]:
    """Return continuous horizontal stitch edge as (left, right, y)."""
    points = part.stitch_line
    vertices = points[:-1] if points[0] == points[-1] else points
    y = (max if bottom else min)(point[1] for point in vertices)
    edges = sorted((min(a[0], b[0]), max(a[0], b[0]))
                   for a, b in zip(vertices, vertices[1:] + vertices[:1])
                   if abs(a[1] - y) <= EDGE_TOLERANCE_CM
                   and abs(b[1] - y) <= EDGE_TOLERANCE_CM
                   and abs(a[0] - b[0]) > EDGE_TOLERANCE_CM)
    if not edges:
        raise ValueError(f"{part.display_name}: 接合できる水平な裾辺がありません")
    left, right = edges[0]
    for start, end in edges[1:]:
        if start > right + EDGE_TOLERANCE_CM:
            raise ValueError(f"{part.display_name}: 裾辺が途切れています")
        right = max(right, end)
    return left, right, y


def _sewn_bottom_edge(part: FinalizedPart, *, allow_darts: bool
                      ) -> tuple[list[tuple[float, float]], float]:
    """Horizontal hem runs remaining after verified waist darts are closed.

    A dart's two legs are sewn to each other, not into the lower panel.  Its
    mouth must therefore be omitted from the panel joining length.  This is
    opt-in: an arbitrary broken hem must never be silently bridged.
    """
    points = part.stitch_line
    vertices = points[:-1] if points[0] == points[-1] else points
    y = max(point[1] for point in vertices)
    runs = sorted((min(a[0], b[0]), max(a[0], b[0]))
                  for a, b in zip(vertices, vertices[1:] + vertices[:1])
                  if abs(a[1] - y) <= EDGE_TOLERANCE_CM
                  and abs(b[1] - y) <= EDGE_TOLERANCE_CM
                  and abs(a[0] - b[0]) > EDGE_TOLERANCE_CM)
    if not runs:
        raise ValueError(f"{part.display_name}: 接合できる水平な裾辺がありません")
    merged = [runs[0]]
    for left, right in runs[1:]:
        old_left, old_right = merged[-1]
        if left <= old_right + EDGE_TOLERANCE_CM:
            merged[-1] = (old_left, max(old_right, right))
        else:
            merged.append((left, right))
    if len(merged) > 1 and not allow_darts:
        raise ValueError(f"{part.display_name}: 裾辺が途切れています")
    for (_left, mouth_a), (mouth_b, _right) in zip(merged, merged[1:]):
        # The intervening contour must consist of two nearly equal legs
        # meeting at an interior tip.  A slit, hole or missing seam is not a
        # closed waist dart and cannot be replaced by a straight join.
        found = False
        for index, point in enumerate(vertices):
            next_point = vertices[(index + 1) % len(vertices)]
            tip = vertices[(index + 2) % len(vertices)]
            if (abs(point[0] - mouth_a) > EDGE_TOLERANCE_CM or
                    abs(point[1] - y) > EDGE_TOLERANCE_CM or
                    abs(tip[0] - mouth_b) > EDGE_TOLERANCE_CM or
                    abs(tip[1] - y) > EDGE_TOLERANCE_CM):
                continue
            depth = y - next_point[1]
            # Truing can move a narrow dart tip slightly past its mouth
            # without changing the two sewn leg lengths.  Limit this to
            # half a centimetre rather than accepting an arbitrary notch.
            if (5 <= depth <= 20 and
                    mouth_a - .5 <= next_point[0] <= mouth_b + .5
                    and abs(dist(point, next_point) -
                            dist(next_point, tip)) <= .1):
                found = True
                break
        if not found:
            raise ValueError(f"{part.display_name}: 裾の隙間は閉じるダーツと確認できません")
    return merged, y


def _hem_mark_at(runs: list[tuple[float, float]], y: float,
                 fraction: float) -> tuple[float, float]:
    target = sum(right - left for left, right in runs) * fraction
    for left, right in runs:
        width = right - left
        if target <= width:
            return left + target, y
        target -= width
    return runs[-1][1], y


def _find_part(parts: list[FinalizedPart], *, part_type: str,
               variation: str | None = None, suffix: str | None = None) -> int:
    matches = [index for index, part in enumerate(parts)
               if part.part_type == part_type
               and (variation is None or part.variation == variation)
               and (suffix is None or part.label_suffix == suffix)]
    if len(matches) != 1:
        raise ValueError(f"裾パネルの接合先が一意でありません: {part_type}/{variation}/{suffix}")
    return matches[0]


def _pairs(brief: dict | None) -> list[dict]:
    value = (brief or {}).get("hem_extension_pairs", [])
    return value if isinstance(value, list) else []


def _overlay_pairs(brief: dict | None) -> list[dict]:
    value = (brief or {}).get("overlay_pairs", [])
    return value if isinstance(value, list) else []


def pair_hem_extensions(parts: list[FinalizedPart], brief: dict | None
                        ) -> tuple[list[FinalizedPart], list[str]]:
    """Fit extension stitch edges, not cutting edges; add paired marks.

    A host's turned-hem allowance is replaced by a normal joining allowance.
    Only the panel's horizontal width changes; its inferred silhouette and
    length remain provisional for the physical toile.
    """
    pairs = _pairs(brief)
    if not pairs:
        return parts, []
    output = list(parts)
    notes = []
    used: set[int] = set()
    for pair in pairs:
        code = str(pair["code"])
        host_index = _find_part(output, part_type=str(pair["host_type"]),
                                suffix=str(pair["host_suffix"]))
        panel_index = _find_part(output, part_type="custom_panel",
                                 variation=str(pair["panel"]))
        if host_index in used or panel_index in used:
            raise ValueError(f"接合{code}: 同じパーツを二つの接合へ使えません")
        used.update((host_index, panel_index))
        host, panel = output[host_index], output[panel_index]
        host_runs, host_y = _sewn_bottom_edge(
            host, allow_darts=bool(pair.get("allow_sewn_hem_darts")))
        host_left, host_right = host_runs[0][0], host_runs[-1][1]
        panel_left, panel_right, panel_y = _straight_edge(panel, bottom=False)
        host_length = sum(right - left for left, right in host_runs)
        panel_length = panel_right - panel_left
        if panel_length <= 0:
            raise ValueError(f"接合{code}: パネル上辺の長さが不正です")
        ratio = host_length / panel_length
        if not 0.75 <= ratio <= 1.35:
            raise ValueError(f"接合{code}: パネルと本体の幅差が大きすぎます ({ratio:.2f}倍)")

        # A coat's continuous lower shell must also have compatible side
        # seams.  Resize its top to the real host and set the *same* sideways
        # flare on all three pieces, rather than scaling the back flare more.
        if "side_flare_cm" in pair:
            flare = float(pair["side_flare_cm"])
            vertices = (panel.stitch_line[:-1] if panel.stitch_line[0] ==
                        panel.stitch_line[-1] else panel.stitch_line)
            bottom_y = max(y for _x, y in vertices)
            if (not 0 < flare <= 12 or len(vertices) != 4
                    or bottom_y - panel_y < 15
                    or flare > (bottom_y - panel_y) * .35):
                raise ValueError(f"接合{code}: 下身頃の台形と裾広がりが不正です")
            resized = [(panel_left, panel_y),
                       (panel_left + host_length, panel_y),
                       (panel_left + host_length + flare, bottom_y),
                       (panel_left - flare, bottom_y)]
        else:
            # Keep the panel's own x origin; the stitch-line span becomes exact.
            resized = [(panel_left + (x - panel_left) * ratio, y)
                       for x, y in panel.stitch_line]
        panel_marks = [(panel_left + host_length * f, panel_y)
                       for f in NOTCH_FRACTIONS]
        host_marks = [_hem_mark_at(host_runs, host_y, f)
                      for f in NOTCH_FRACTIONS]
        panel_new = finalize_from_stitch_line(
            panel.part_type, panel.variation, resized,
            seam_allowance_cm=panel.seam_allowance_cm,
            label_suffix=panel.label_suffix, notch_points=panel_marks,
            reference_lines=[*panel.reference_lines,
                             (f"接合{code}", [(panel_left + host_length / 2, panel_y + 2),
                                              (panel_left + host_length / 2, panel_y + 0.5)])])
        output[panel_index] = replace(
            panel_new, cut_quantity=panel.cut_quantity,
            cut_on_fold=panel.cut_on_fold,
            interfacing_instruction=panel.interfacing_instruction)

        # The bodice bottom is now a joining seam, not a turned-up free hem.
        cut = offset_polygon_variable(host.stitch_line, host.seam_allowance_cm)
        marks = notch_marks_at(host.stitch_line, host_marks)
        new_notches = extend_notches_to_cut_line(
            [*host.notches, *marks], cut,
            maximum_distance_cm=host.seam_allowance_cm * 2 + 0.5,
            stitch_line=host.stitch_line)
        output[host_index] = replace(
            host, cut_line=cut, notches=new_notches,
            hem_seam_allowance_cm=host.seam_allowance_cm,
            hem_edge_is_joined=True,
            reference_lines=[*host.reference_lines,
                             (f"接合{code}", [(_hem_mark_at(host_runs, host_y, .5)[0],
                                              host_y - 2),
                                             (_hem_mark_at(host_runs, host_y, .5)[0],
                                              host_y - 0.5)])])
        notes.append(
            f"接合{code}: {host.display_name}の裾と{panel.display_name}の上辺を"
            f"縫い線で各{host_length:.1f}cmに揃え、1/4・3/4位置へ対の合印を配置。"
            "裾は折り返さず縫い合わせます。"
            + ("ウエストダーツを先に縫い閉じてから接合します。"
               if len(host_runs) > 1 else ""))
    used_overlays: set[int] = set()
    for pair in _overlay_pairs(brief):
        code = str(pair["code"])
        base_index = _find_part(output, part_type="custom_panel",
                                variation=str(pair["base"]))
        overlay_index = _find_part(output, part_type="custom_panel",
                                   variation=str(pair["overlay"]))
        if (base_index == overlay_index or overlay_index in used_overlays
                or overlay_index in used):
            raise ValueError(f"重ね{code}: 飾りと下身頃を一意に指定してください")
        used_overlays.add(overlay_index)
        base, overlay = output[base_index], output[overlay_index]
        base_left, base_right, base_y = _straight_edge(base, bottom=False)
        overlay_left, overlay_right, overlay_y = _straight_edge(overlay, bottom=False)
        length = base_right - base_left
        ratio = length / (overlay_right - overlay_left)
        if not .75 <= ratio <= 1.35:
            raise ValueError(f"重ね{code}: 上辺の幅差が大きすぎます ({ratio:.2f}倍)")
        resized = [(overlay_left + (x - overlay_left) * ratio, y)
                   for x, y in overlay.stitch_line]
        marks = [(overlay_left + length * fraction, overlay_y)
                 for fraction in NOTCH_FRACTIONS]
        new_overlay = finalize_from_stitch_line(
            overlay.part_type, overlay.variation, resized,
            seam_allowance_cm=overlay.seam_allowance_cm,
            label_suffix=overlay.label_suffix, notch_points=marks,
            reference_lines=[*overlay.reference_lines,
                             (f"重ね{code}", [(overlay_left + length / 2, overlay_y + 2),
                                              (overlay_left + length / 2, overlay_y + .5)])])
        output[overlay_index] = replace(
            new_overlay, cut_quantity=overlay.cut_quantity,
            cut_on_fold=overlay.cut_on_fold,
            interfacing_instruction=overlay.interfacing_instruction)
        output[base_index] = replace(
            base, reference_lines=[*base.reference_lines,
                                   (f"重ね{code}", [(base_left + length / 2, base_y + 2),
                                                    (base_left + length / 2, base_y + .5)])])
        notes.append(f"重ね{code}: {overlay.display_name}の上辺を"
                     f"{base.display_name}の上辺{length:.1f}cmへ合わせて仮止め。"
                     "横辺と下辺は別途デザイン確認する自由端です。")
    return output, notes


def hem_extension_warnings(parts: list[FinalizedPart], brief: dict | None) -> list[str]:
    """Independently audit the delivered pattern, including paired marks."""
    warnings = []
    shell_side_lengths: list[tuple[str, float, float]] = []
    for pair in _pairs(brief):
        code = str(pair["code"])
        try:
            host = parts[_find_part(parts, part_type=str(pair["host_type"]),
                                    suffix=str(pair["host_suffix"]))]
            panel = parts[_find_part(parts, part_type="custom_panel",
                                     variation=str(pair["panel"]))]
            host_runs, hy = _sewn_bottom_edge(
                host, allow_darts=bool(pair.get("allow_sewn_hem_darts")))
            host_length = sum(right - left for left, right in host_runs)
            pl, pr, py = _straight_edge(panel, bottom=False)
            if abs(host_length - (pr - pl)) > MATCH_TOLERANCE_CM:
                warnings.append(f"接合{code}: 本体裾とパネル上辺の縫い線長が一致しません")
            if (host.hem_seam_allowance_cm is not None and
                    abs(host.hem_seam_allowance_cm - panel.seam_allowance_cm)
                    > MATCH_TOLERANCE_CM):
                warnings.append(f"接合{code}: 本体裾と下身頃の縫い代幅が一致しません")
            if not host.hem_edge_is_joined or abs(
                    (host.hem_seam_allowance_cm or 0) - host.seam_allowance_cm
            ) > 1e-6:
                warnings.append(f"接合{code}: 本体裾が折り返し用の縫い代です")
            for fraction in NOTCH_FRACTIONS:
                for part, point in ((host, _hem_mark_at(host_runs, hy, fraction)),
                                    (panel, (pl + (pr - pl) * fraction, py))):
                    if not any(abs(a[0] - point[0]) <= EDGE_TOLERANCE_CM
                               and abs(a[1] - point[1]) <= EDGE_TOLERANCE_CM
                               for a, _b in part.notches):
                        warnings.append(f"接合{code}: {part.display_name}の対応合印がありません")
            if "side_flare_cm" in pair:
                vertices = (panel.stitch_line[:-1] if panel.stitch_line[0] ==
                            panel.stitch_line[-1] else panel.stitch_line)
                if len(vertices) != 4:
                    warnings.append(f"接合{code}: 下身頃は4点の台形ではありません")
                else:
                    shell_side_lengths.append((code, dist(vertices[0], vertices[3]),
                                               dist(vertices[1], vertices[2])))
        except (KeyError, TypeError, ValueError, IndexError) as exc:
            warnings.append(f"接合{code}: {exc}")
    if shell_side_lengths:
        lengths = [length for _code, left, right in shell_side_lengths
                   for length in (left, right)]
        if max(lengths) - min(lengths) > MATCH_TOLERANCE_CM:
            warnings.append("下身頃の前後脇の縫い線長が一致しません")
    for pair in _overlay_pairs(brief):
        code = str(pair["code"])
        try:
            base = parts[_find_part(parts, part_type="custom_panel",
                                    variation=str(pair["base"]))]
            overlay = parts[_find_part(parts, part_type="custom_panel",
                                       variation=str(pair["overlay"]))]
            bl, br, by = _straight_edge(base, bottom=False)
            ol, or_, oy = _straight_edge(overlay, bottom=False)
            if abs((br - bl) - (or_ - ol)) > MATCH_TOLERANCE_CM:
                warnings.append(f"重ね{code}: 下身頃と飾りの上辺が一致しません")
            if abs(base.seam_allowance_cm - overlay.seam_allowance_cm) > MATCH_TOLERANCE_CM:
                warnings.append(f"重ね{code}: 下身頃と飾りの縫い代幅が一致しません")
            if not any(label == f"重ね{code}" for label, _line in base.reference_lines):
                warnings.append(f"重ね{code}: 下身頃の接合記号がありません")
            if not any(label == f"重ね{code}" for label, _line in overlay.reference_lines):
                warnings.append(f"重ね{code}: 飾りの接合記号がありません")
            for fraction in NOTCH_FRACTIONS:
                base_expected = (bl + (br - bl) * fraction, by)
                if not any(abs(point[0] - base_expected[0]) <= EDGE_TOLERANCE_CM
                           and abs(point[1] - base_expected[1]) <= EDGE_TOLERANCE_CM
                           for point, _end in base.notches):
                    warnings.append(f"重ね{code}: 下身頃の対応合印がありません")
                expected = (ol + (or_ - ol) * fraction, oy)
                if not any(abs(point[0] - expected[0]) <= EDGE_TOLERANCE_CM
                           and abs(point[1] - expected[1]) <= EDGE_TOLERANCE_CM
                           for point, _end in overlay.notches):
                    warnings.append(f"重ね{code}: 飾りの対応合印がありません")
        except (KeyError, TypeError, ValueError, IndexError) as exc:
            warnings.append(f"重ね{code}: {exc}")
    return warnings


def hem_extension_rows(parts: list[FinalizedPart], brief: dict | None
                       ) -> list[tuple[str, str, str, str]]:
    """Measured stitch-line pairs for the printable assembly sheet."""
    rows = []
    for pair in _pairs(brief):
        host = parts[_find_part(parts, part_type=str(pair["host_type"]),
                                suffix=str(pair["host_suffix"]))]
        panel = parts[_find_part(parts, part_type="custom_panel",
                                 variation=str(pair["panel"]))]
        host_runs, _ = _sewn_bottom_edge(
            host, allow_darts=bool(pair.get("allow_sewn_hem_darts")))
        host_length = sum(right - left for left, right in host_runs)
        pl, pr, _ = _straight_edge(panel, bottom=False)
        rows.append((str(pair["code"]), host.display_name, panel.display_name,
                     f"{host_length + 1e-8:.1f} / {pr - pl + 1e-8:.1f} cm"))
    return rows
