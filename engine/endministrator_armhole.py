"""Identify Endministrator coat stitch paths, with explicit pattern assumptions.

Only the project's current front-zip and symmetric-back blocks are supported.
An unexpected contour must fail instead of silently sewing a non-armhole edge.
"""

from __future__ import annotations

from math import dist, isfinite

from .zip_front_geometry import front_zip_armhole_path


def path_length_cm(points) -> float:
    return sum(dist(a, b) for a, b in zip(points, points[1:]))


def arc_of_point_cm(path, point, tolerance_cm=.05):
    """Distance from the first stitch endpoint, or None when off that seam."""
    travelled = 0.0
    best = (float("inf"), None)
    for a, b in zip(path, path[1:]):
        length = dist(a, b)
        if length <= 0:
            continue
        t = max(0.0, min(1.0, ((point[0] - a[0]) * (b[0] - a[0])
                                + (point[1] - a[1]) * (b[1] - a[1]))
                               / length**2))
        projected = (a[0] + t * (b[0] - a[0]),
                     a[1] + t * (b[1] - a[1]))
        candidate = (dist(point, projected), travelled + t * length)
        if candidate[0] < best[0]:
            best = candidate
        travelled += length
    return best[1] if best[0] <= tolerance_cm else None


def endministrator_notch_pairing_warnings(parts, *,
                                         require_shoulder=False) -> list[str]:
    """Check actual printed front/back/sleeve notch stations before cutting.

    This check is intentionally costume-specific.  Other sleeves can use
    different notch conventions, and no 2D station check proves a sewn fit.
    """
    from .compatibility import underarm_y_of

    fronts = [part for part in parts
              if part.part_type == "front_bodice_zip_panel"]
    backs = [part for part in parts if part.part_type == "back_bodice"]
    sleeves = [part for part in parts if part.part_type == "sleeve"]
    if len(fronts) != 2 or len(backs) != 1 or len(sleeves) != 2:
        return ["前開き身頃2枚・後ろ身頃1枚・袖2枚が揃っていません"]
    try:
        front_stations = []
        for part in fronts:
            path = front_zip_armhole_path(part.stitch_line,
                                           underarm_y_of(part))
            stations = [arc_of_point_cm(path, origin)
                        for origin, _end in part.notches]
            stations = [station for station in stations if station is not None]
            if len(stations) != 1:
                return [f"{part.display_name}: 前袖ぐりの合印が1本ではありません"]
            front_stations.append(stations[0])
        if abs(front_stations[0] - front_stations[1]) > .05:
            return ["左右の前袖ぐり合印が同じ縫い位置にありません"]

        back = backs[0]
        back_paths = back_armhole_paths(back.stitch_line,
                                        underarm_y_of(back))
        back_stations = []
        for index, path in enumerate(back_paths):
            stations = [arc_of_point_cm(path, origin)
                        for origin, _end in back.notches]
            stations = sorted(path_length_cm(path) - station if index == 0
                              else station for station in stations
                              if station is not None)
            if len(stations) != 2:
                return ["後ろ身頃の左右各袖ぐりに合印2本が必要です"]
            back_stations.append(stations)
        if any(abs(a - b) > .05 for a, b in zip(*back_stations)):
            return ["後ろ身頃の左右の合印位置が一致しません"]

        for sleeve in sleeves:
            cap = sleeve_cap_path(sleeve.stitch_line)
            cap_length = path_length_cm(cap)
            stations = [arc_of_point_cm(cap, origin)
                        for origin, _end in sleeve.notches]
            if (len(stations) not in (3, 4) or
                    any(station is None for station in stations)):
                return [f"{sleeve.display_name}: 袖山に前1本・後ろ2本の合印が必要です"]
            from_underarm = [stations[0], cap_length - stations[1],
                             cap_length - stations[2]]
            if (abs(from_underarm[0] - front_stations[0]) > .1 or
                    any(abs(a - b) > .1 for a, b in zip(
                        sorted(from_underarm[1:]), back_stations[1]))):
                return [f"{sleeve.display_name}: 袖山の合印が身頃袖ぐりと対応しません"]
            if len(stations) == 4:
                front_length = path_length_cm(front_zip_armhole_path(
                    fronts[0].stitch_line, underarm_y_of(fronts[0])))
                back_length = path_length_cm(back_armhole_paths(
                    back.stitch_line, underarm_y_of(back))[1])
                try:
                    index = choose_sleeve_shoulder_station(
                        cap, front_length, back_length,
                        front_notch_cm=front_stations[0],
                        back_notch_cm=max(back_stations[1]))
                except ValueError as exc:
                    return [f"{sleeve.display_name}: 肩合わせ位置を決められません: {exc}"]
                expected = path_length_cm(cap[:index + 1])
                if abs(stations[3] - expected) > .1:
                    return [f"{sleeve.display_name}: 肩合わせ印が袖山の縫い位置と一致しません"]
            elif require_shoulder:
                return [f"{sleeve.display_name}: 肩合わせ印がありません"]
    except (TypeError, ValueError, IndexError) as exc:
        return [f"袖ぐり・袖山の合印を検査できません: {exc}"]
    return []


def endministrator_side_seam_warnings(parts, tolerance_cm=.5) -> list[str]:
    """Require a close paper seam match for this fitted woven coat.

    The generic engine permits 1.5 cm for many garment types.  On this
    specific three-panel coat, a near-centimetre side mismatch must remain
    an explicit alteration task rather than being labelled cutting-ready.
    """
    from .compatibility import side_seam_length

    fronts = [part for part in parts
              if part.part_type == "front_bodice_zip_panel"]
    backs = [part for part in parts if part.part_type == "back_bodice"]
    if len(fronts) != 2 or len(backs) != 1:
        return ["前後身頃が揃わず脇線の長さを照合できません"]
    front_lengths = [side_seam_length(part) for part in fronts]
    back_length = side_seam_length(backs[0])
    if any(value is None for value in front_lengths) or back_length is None:
        return ["前後身頃の脇線長を測定できません"]
    expected = back_length / 2
    return [f"{part.display_name}: 前脇線{actual:.2f}cmは後ろ脇線"
            f"{expected:.2f}cmより{abs(actual - expected):.2f}cm"
            f"{'長い' if actual > expected else '短い'}ため、縫い線を再製図してください"
            for part, actual in zip(fronts, front_lengths)
            if abs(actual - expected) > tolerance_cm]


def distribute_sleeve_cap_ease(cap_arcs_cm, armhole_length_cm, *,
                               crown_at_start: bool,
                               no_ease_from_underarm_cm: float | None = None):
    """Map sleeve-cap arc stations onto the sewn armhole, easing near crown.

    The cap start/end nearest the underarm must keep its paper length.  A cubic
    easing distribution puts the unavoidable cap surplus progressively toward
    the shoulder.  With an underarm notch distance, the region from underarm
    to that notch stays at its full paper length and surplus goes above it.
    This is a sewing-placement hypothesis, not measured drape.
    """
    arcs = list(cap_arcs_cm)
    if (len(arcs) < 3 or abs(arcs[0]) > 1e-8 or
            any(not isfinite(value) for value in arcs) or
            any(b <= a for a, b in zip(arcs, arcs[1:])) or
            not isfinite(armhole_length_cm) or armhole_length_cm <= 0):
        raise ValueError("Cap and armhole arcs must be finite and increasing")
    cap_length = arcs[-1]
    surplus = cap_length - armhole_length_cm
    if surplus < -1e-6 or surplus > min(3.0, .12 * armhole_length_cm):
        raise ValueError("Sleeve-cap ease is outside the trial's supported range")
    if no_ease_from_underarm_cm is not None:
        notch = no_ease_from_underarm_cm
        if (not isfinite(notch) or notch <= 0 or
                notch >= armhole_length_cm or
                3 * surplus >= cap_length - notch):
            raise ValueError("The armhole notch cannot anchor this sleeve ease")
        mapped = []
        for station in arcs:
            from_underarm = (cap_length - station if crown_at_start
                             else station)
            over_notch = max(0.0, from_underarm - notch)
            eased = from_underarm - surplus * (
                over_notch / (cap_length - notch)) ** 3
            mapped.append(armhole_length_cm - eased if crown_at_start
                          else eased)
        mapped[0], mapped[-1] = 0.0, armhole_length_cm
        if any(b <= a for a, b in zip(mapped, mapped[1:])):
            raise ValueError("Notch-anchored ease reversed a stitch station")
        return mapped
    mapped = []
    for station in arcs:
        fraction = station / cap_length
        crown_fraction = (1 - (1 - fraction) ** 3 if crown_at_start
                          else fraction ** 3)
        mapped.append(station - surplus * crown_fraction)
    mapped[0], mapped[-1] = 0.0, armhole_length_cm
    if any(b <= a for a, b in zip(mapped, mapped[1:])):
        raise ValueError("Easing distribution reversed a stitch station")
    return mapped


def choose_sleeve_shoulder_station(cap_path_cm, front_armhole_cm,
                                   back_armhole_cm, *,
                                   front_notch_cm=None,
                                   back_notch_cm=None):
    """Choose a mesh station where both cap halves have sewable ease.

    A symmetric cap does not imply equal front/back armholes.  The geometric
    crown can therefore be a poor shoulder registration point.  This selects
    an existing sampled cap vertex near that crown; it does not alter the
    paper pattern or assert that the resulting drape is a fitting approval.
    """
    points = list(cap_path_cm)
    if len(points) < 7 or any(not all(isfinite(x) for x in point)
                              for point in points):
        raise ValueError("Sleeve cap needs finite sampled points")
    arcs = [0.0]
    for first, second in zip(points, points[1:]):
        step = dist(first, second)
        if step <= 1e-6:
            raise ValueError("Sleeve cap has a repeated sampled point")
        arcs.append(arcs[-1] + step)
    crown = min(range(len(points)), key=lambda index: points[index][1])
    if not 2 <= crown <= len(points) - 3:
        raise ValueError("Sleeve cap crown is too close to the underarm")
    candidates = []
    for index in range(2, len(points) - 2):
        if abs(arcs[index] - arcs[crown]) > 3.0:
            continue
        front_cap = arcs[index]
        back_cap = arcs[-1] - arcs[index]
        try:
            distribute_sleeve_cap_ease(
                arcs[:index + 1], front_armhole_cm,
                crown_at_start=False,
                no_ease_from_underarm_cm=front_notch_cm)
            distribute_sleeve_cap_ease(
                [value - arcs[index] for value in arcs[index:]],
                back_armhole_cm, crown_at_start=True,
                no_ease_from_underarm_cm=back_notch_cm)
        except ValueError:
            continue
        front_ease = front_cap - front_armhole_cm
        back_ease = back_cap - back_armhole_cm
        candidates.append((abs(front_ease - back_ease),
                           abs(arcs[index] - arcs[crown]), index))
    if not candidates:
        raise ValueError("No sewable shoulder station on the sleeve cap")
    return min(candidates)[2]


def _underarm_index(points, y_cm, *, left: bool) -> int:
    xs = [point[0] for point in points]
    mid = (min(xs) + max(xs)) / 2
    candidates = [(abs(point[1] - y_cm), index)
                  for index, point in enumerate(points)
                  if (point[0] < mid if left else point[0] > mid)]
    error, index = min(candidates)
    if error > .05:
        raise ValueError("The declared underarm is not on the stitch contour")
    return index


def _next_neck_jump(points, start) -> int:
    span = max(point[0] for point in points) - min(point[0] for point in points)
    for index in range(start, len(points) - 1):
        a, b = points[index:index + 2]
        # This is the straight shoulder-to-neck edge after the sampled
        # armhole.  A 28%-of-back-width cutoff rejected valid broad-hip
        # blocks (18.36 cm on a 66 cm span = 27.8%); the lower cutoff still
        # exceeds any individual sampled armhole segment by a wide margin.
        if a[0] - b[0] > .20 * span and b[1] < a[1]:
            return index
    raise ValueError("The shoulder-to-neck edge was not identifiable")


def back_armhole_paths(stitch_outline_cm, underarm_y_cm):
    points = list(stitch_outline_cm)
    left_underarm = _underarm_index(points, underarm_y_cm, left=True)
    right_underarm = _underarm_index(points, underarm_y_cm, left=False)
    right_shoulder = _next_neck_jump(points, right_underarm)
    left = points[:left_underarm + 1]
    right = points[right_underarm:right_shoulder + 1]
    if not (len(left) >= 5 and len(right) >= 5):
        raise ValueError("The back armhole paths are incomplete")
    if abs(path_length_cm(left) - path_length_cm(right)) > .05:
        raise ValueError("The current back block should have symmetric armholes")
    return left, right


def sleeve_cap_path(stitch_outline_cm):
    points = list(stitch_outline_cm)
    y0 = points[0][1]
    for end in range(1, len(points)):
        if abs(points[end][1] - y0) < 1e-4:
            path = points[:end + 1]
            if path_length_cm(path) <= 10:
                break
            return path
    raise ValueError("The sleeve cap end was not identifiable")


def sleeve_underarm_side_paths(stitch_outline_cm):
    """Return the two sleeve tube seams, each from cap end to cuff."""
    points = list(stitch_outline_cm)
    cap = sleeve_cap_path(points)
    end = len(cap) - 1
    if len(points) != end + 4 or dist(points[-1], points[0]) > 1e-5:
        raise ValueError("Unsupported sleeve side/cuff contour")
    left = list(reversed(points[end + 2:end + 4]))
    right = points[end:end + 2]
    if (dist(left[0], cap[0]) > 1e-5 or
            dist(right[0], cap[-1]) > 1e-5 or
            abs(path_length_cm(left) - path_length_cm(right)) > .1):
        raise ValueError("Sleeve tube side seams do not match")
    return left, right


def mesh_indices_for_contour_path(pattern_mesh, stitch_outline_cm, contour_path_cm):
    """Follow the sampled one-face stitch boundary for a raw contour subpath."""
    path = list(contour_path_cm)
    outline = list(stitch_outline_cm)
    if len(path) < 2 or not any(
            outline[start:start + len(path)] in (path, list(reversed(path)))
            for start in range(len(outline) - len(path) + 1)):
        raise ValueError("Stitch path is not a unique contour subpath")
    vertices = pattern_mesh["vertices_cm"]
    indices = []
    for a, b in zip(path, path[1:]):
        matches = []
        for segment in pattern_mesh["boundary_paths"]:
            first, last = (vertices[segment[0]], vertices[segment[-1]])
            if dist(first, a) < 1e-4 and dist(last, b) < 1e-4:
                matches.append(segment)
            elif dist(first, b) < 1e-4 and dist(last, a) < 1e-4:
                matches.append(list(reversed(segment)))
        if len(matches) != 1:
            raise ValueError("Sampled stitch boundary segment is missing or ambiguous")
        segment = matches[0]
        if indices and indices[-1] != segment[0]:
            raise ValueError("Sampled stitch boundary has a break")
        indices.extend(segment if not indices else segment[1:])
    if dist(vertices[indices[0]], path[0]) > 1e-4 or dist(
            vertices[indices[-1]], path[-1]) > 1e-4:
        raise ValueError("Sampled stitch boundary endpoints do not match the paper")
    return indices


def shoulder_stitch_paths(stitch_outline_cm, armhole_paths_cm):
    """Return each adjacent neck-to-shoulder stitch edge, never an armhole."""
    points = list(stitch_outline_cm)
    if points[0] == points[-1]:
        points.pop()
    out = []
    for armhole in armhole_paths_cm:
        shoulder = min((armhole[0], armhole[-1]), key=lambda point: point[1])
        matches = [index for index, point in enumerate(points)
                   if dist(point, shoulder) < 1e-5]
        if len(matches) != 1:
            raise ValueError("Armhole shoulder point is ambiguous on the bodice")
        index = matches[0]
        neighbors = [points[(index - 1) % len(points)],
                     points[(index + 1) % len(points)]]
        neck_candidates = [point for point in neighbors
                           if point[1] < shoulder[1] - 1.0]
        if len(neck_candidates) != 1:
            raise ValueError("Neck-to-shoulder stitch edge was not identifiable")
        out.append([neck_candidates[0], shoulder])
    return out


def front_effective_side_segments(stitch_outline_cm, underarm_y_cm,
                                  hem_right_cm, hem_y_cm, darts):
    """Side-seam spans remaining after the two bust darts are sewn closed.

    Dart legs are their own seams.  Counting both legs in the side seam would
    overstate its stitch length by dozens of centimetres.
    """
    points = list(stitch_outline_cm)
    hem = [index for index, point in enumerate(points)
           if dist(point, (hem_right_cm, hem_y_cm)) < 1e-4]
    if not hem:
        raise ValueError("Front side hem endpoint is missing")
    start = hem[0]
    end = _underarm_index(points, underarm_y_cm, left=False)
    if start >= end or len(darts) not in (1, 2):
        raise ValueError("Unsupported front side contour or bust dart count")

    def find(point):
        matches = [index for index in range(start, end + 1)
                   if dist(points[index], point) < 1e-4]
        if len(matches) != 1:
            raise ValueError("Bust dart mouth is missing from the side contour")
        return matches[0]

    spans = sorted((find(dart["leg_a_cm"][0]),
                    find(dart["leg_b_cm"][-1])) for dart in darts)
    segments = []
    cursor = start
    for mouth_a, mouth_b in spans:
        if mouth_a <= cursor or mouth_b <= mouth_a + 1:
            raise ValueError("Bust dart spans overlap or are out of contour order")
        segments.append(points[cursor:mouth_a + 1])
        cursor = mouth_b
    if cursor >= end:
        raise ValueError("No side seam remains above the bust darts")
    segments.append(points[cursor:end + 1])
    if any(len(segment) < 2 for segment in segments):
        raise ValueError("A side seam span has no stitch edge")
    return segments


def back_side_paths(stitch_outline_cm, underarm_y_cm,
                    hem_left_cm, hem_right_cm, hem_y_cm):
    """Return back left/right side seams, each ordered hem to underarm."""
    points = list(stitch_outline_cm)

    def find(point):
        matches = [index for index, candidate in enumerate(points)
                   if dist(candidate, point) < 1e-4]
        if len(matches) != 1:
            raise ValueError("Back side hem endpoint is missing or ambiguous")
        return matches[0]

    left_hem = find((hem_left_cm, hem_y_cm))
    right_hem = find((hem_right_cm, hem_y_cm))
    left_arm = _underarm_index(points, underarm_y_cm, left=True)
    right_arm = _underarm_index(points, underarm_y_cm, left=False)
    if not (left_arm < left_hem < right_hem < right_arm):
        raise ValueError("Unsupported back side contour order")
    paths = [list(reversed(points[left_arm:left_hem + 1])),
             points[right_hem:right_arm + 1]]
    if any(len(path) < 2 or not 20 < path_length_cm(path) < 60
           for path in paths):
        raise ValueError("Back side stitch path is incomplete")
    return paths
