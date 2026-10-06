"""Sample a sewn 2D panel for a separate, explicitly provisional 3D drape.

Coordinates remain in centimetres here.  The Blender adapter owns scale and
placement on a fitting body; this module does not infer a wearer's shape.
"""

from __future__ import annotations

import math
from collections import Counter


def outward_wound_faces(vertices, faces):
    """Orient a wrapped open garment surface away from its body origin.

    Paper triangles may reverse their effective normal when placed around an
    avatar.  This changes the simulation mesh only, never the paper pattern.
    """
    oriented = [tuple(face) for face in faces]
    score = 0.0
    for face in oriented:
        a, b, c = (vertices[index] for index in face[:3])
        ab = tuple(b[axis] - a[axis] for axis in range(3))
        ac = tuple(c[axis] - a[axis] for axis in range(3))
        nx = ab[1] * ac[2] - ab[2] * ac[1]
        ny = ab[2] * ac[0] - ab[0] * ac[2]
        cx = (a[0] + b[0] + c[0]) / 3
        cy = (a[1] + b[1] + c[1]) / 3
        score += nx * cx + ny * cy
    if abs(score) < 1e-9:
        raise ValueError("Garment panel winding is ambiguous")
    flip = score < 0
    return ([tuple(reversed(face)) for face in oriented] if flip else oriented), flip


def relax_overlay_to_paper_edges(surface_vertices, paper_vertices_cm, faces,
                                 pinned_indices, support_vertices, normals,
                                 *, unit_m_per_cm=.02, iterations=120,
                                 guide_pull=.025, min_gap_m=.018,
                                 max_guide_distance_m=.20):
    """Experimental low-strain placement, not a calibrated cloth simulation."""
    count = len(surface_vertices)
    if not (count == len(paper_vertices_cm) == len(support_vertices)
            == len(normals)) or not faces:
        raise ValueError("Overlay relaxation needs aligned nonempty meshes")
    if not 0 < unit_m_per_cm or not 0 < iterations <= 1000:
        raise ValueError("Invalid overlay relaxation scale or iterations")
    pinned = set(pinned_indices)
    if not pinned or any(not 0 <= index < count for index in pinned):
        raise ValueError("Overlay mounting edge must be pinned")
    points = [list(vertex) for vertex in surface_vertices]
    guides = [tuple(vertex) for vertex in surface_vertices]
    edges = sorted({tuple(sorted((face[i], face[(i + 1) % len(face)])))
                    for face in faces for i in range(len(face))})
    targets = []
    for a, b in edges:
        if not 0 <= a < count or not 0 <= b < count or a == b:
            raise ValueError("Invalid overlay mesh edge")
        target = math.dist(paper_vertices_cm[a], paper_vertices_cm[b]) * unit_m_per_cm
        if target <= 1e-9:
            raise ValueError("Overlay paper mesh contains a zero-length edge")
        targets.append(target)
    unit_normals = []
    for normal in normals:
        length = math.sqrt(sum(value * value for value in normal))
        if length <= 1e-9:
            raise ValueError("Overlay support normal is zero")
        unit_normals.append(tuple(value / length for value in normal))
    for _ in range(iterations):
        for (a, b), target in zip(edges, targets):
            if a in pinned and b in pinned:
                continue
            delta = [points[b][axis] - points[a][axis] for axis in range(3)]
            length = math.sqrt(sum(value * value for value in delta))
            if length <= 1e-9:
                continue
            correction = .45 * (length - target) / length
            if a in pinned or b in pinned:
                correction *= 2
            if a not in pinned:
                for axis in range(3):
                    points[a][axis] += delta[axis] * correction
            if b not in pinned:
                for axis in range(3):
                    points[b][axis] -= delta[axis] * correction
        for index in range(count):
            if index in pinned:
                continue
            point = points[index]
            guide = guides[index]
            normal = unit_normals[index]
            support = support_vertices[index]
            for axis in range(3):
                point[axis] += (guide[axis] - point[axis]) * guide_pull
            clearance = sum((point[axis] - support[axis]) * normal[axis]
                            for axis in range(3))
            if clearance < min_gap_m:
                for axis in range(3):
                    point[axis] += normal[axis] * (min_gap_m - clearance)
            offset = [point[axis] - guide[axis] for axis in range(3)]
            distance = math.sqrt(sum(value * value for value in offset))
            if distance > max_guide_distance_m:
                factor = max_guide_distance_m / distance
                for axis in range(3):
                    point[axis] = guide[axis] + offset[axis] * factor
    return [tuple(point) for point in points]


def relax_connected_shell_to_paper_edges(vertices, edge_targets_m,
                                         pinned_indices, *, iterations=160,
                                         guide_pull=.005,
                                         max_guide_distance_m=.08):
    """Fit a welded shell's initial mesh to paper lengths without moving seams.

    This is only a 3D starting-placement experiment.  The upper bodice stays
    pinned and the caller must separately check face orientation, body
    clearance, self-intersection and the eventual cloth simulation.
    """
    count = len(vertices)
    if count < 3 or not edge_targets_m or not 0 < iterations <= 1000:
        raise ValueError("Connected-shell relaxation needs vertices and edges")
    if not 0 <= guide_pull < 1 or not 0 < max_guide_distance_m:
        raise ValueError("Invalid connected-shell guide constraint")
    pinned = set(pinned_indices)
    if not pinned or any(not 0 <= index < count for index in pinned):
        raise ValueError("Connected shell needs valid pinned upper vertices")
    edges = sorted(edge_targets_m.items())
    for (a, b), length in edges:
        if not (0 <= a < b < count and math.isfinite(length) and length > 1e-9):
            raise ValueError("Invalid connected-shell paper edge")
    guides = [tuple(point) for point in vertices]
    if any(len(point) != 3 or not all(math.isfinite(value) for value in point)
           for point in guides):
        raise ValueError("Connected-shell vertices must be finite 3D points")
    points = [list(point) for point in guides]
    for _ in range(iterations):
        for (a, b), target in edges:
            if a in pinned and b in pinned:
                continue
            delta = [points[b][axis] - points[a][axis] for axis in range(3)]
            length = math.sqrt(sum(value * value for value in delta))
            if length <= 1e-9:
                continue
            correction = .4 * (length - target) / length
            if a in pinned or b in pinned:
                correction *= 2
            if a not in pinned:
                for axis in range(3):
                    points[a][axis] += delta[axis] * correction
            if b not in pinned:
                for axis in range(3):
                    points[b][axis] -= delta[axis] * correction
        for index in range(count):
            if index in pinned:
                continue
            point, guide = points[index], guides[index]
            for axis in range(3):
                point[axis] += (guide[axis] - point[axis]) * guide_pull
            offset = [point[axis] - guide[axis] for axis in range(3)]
            distance = math.sqrt(sum(value * value for value in offset))
            if distance > max_guide_distance_m:
                scale = max_guide_distance_m / distance
                for axis in range(3):
                    point[axis] = guide[axis] + offset[axis] * scale
    return [tuple(point) for point in points]



def horizontal_span(points: list[tuple[float, float]], y: float) -> tuple[float, float]:
    """Return intersections of a convex panel with a horizontal scanline."""
    polygon = points[:-1] if points[0] == points[-1] else points
    intersections = []
    for a, b in zip(polygon, polygon[1:] + polygon[:1]):
        if min(a[1], b[1]) <= y < max(a[1], b[1]):
            t = (y - a[1]) / (b[1] - a[1])
            intersections.append(a[0] + t * (b[0] - a[0]))
    if len(intersections) != 2:
        raise ValueError(f"Panel scanline y={y:.3f} cm has {len(intersections)} crossings")
    return min(intersections), max(intersections)


def sample_panel(points: list[tuple[float, float]], *, spacing_cm: float = 1.8,
                 strict_boundary: bool = False,
                 require_horizontal_top: bool = True) -> dict:
    """Constrained polygon fill without a degenerate row at an acute tip.

    A regular rectangular grid squeezes dozens of vertices into a pointed hem,
    which makes Blender self-collision explode.  Sample the actual boundary at
    near-uniform spacing, insert interior points away from the cut edge, then
    keep only Delaunay triangles covered by the stitch polygon.
    """
    if not 0.5 <= spacing_cm <= 5:
        raise ValueError("Unsupported panel mesh spacing")
    from shapely import constrained_delaunay_triangles
    from shapely.geometry import MultiPoint, Point, Polygon
    from shapely.ops import triangulate, unary_union
    polygon = points[:-1] if points[0] == points[-1] else points
    if len(polygon) < 3:
        raise ValueError("A panel needs at least three outline points")
    shape = Polygon(polygon)
    if not shape.is_valid or shape.area <= 0:
        raise ValueError("Invalid stitch polygon")
    y_min = min(point[1] for point in polygon)
    y_max = max(point[1] for point in polygon)
    if y_max - y_min <= spacing_cm:
        raise ValueError("Panel height is too small")
    sampled: dict[tuple[float, float], tuple[float, float]] = {}
    for edge_index, (a, b) in enumerate(zip(polygon, polygon[1:] + polygon[:1])):
        length = math.dist(a, b)
        # The attachment seam must follow a curved 3D bodice row.  A coarse
        # 2D edge becomes a shorter chord when projected there, even though
        # the pattern length is correct.  Sample only that edge more densely.
        edge_spacing = (min(spacing_cm, .6)
                        if edge_index == 0 or
                        (abs(a[1] - y_min) < 1e-7 and
                         abs(b[1] - y_min) < 1e-7)
                        else spacing_cm)
        # A nominal 0.6 cm edge can evaluate as 0.6000000000000014 after
        # re-gridding.  Do not split only that edge into two 0.3 cm segments.
        steps = max(1, math.ceil((length - 1e-8) / edge_spacing))
        for index in range(steps):
            t = index / steps
            point = (a[0] * (1 - t) + b[0] * t,
                     a[1] * (1 - t) + b[1] * t)
            sampled[tuple(round(value, 7) for value in point)] = point
    min_x = min(point[0] for point in polygon)
    max_x = max(point[0] for point in polygon)
    for row in range(1, math.ceil((y_max - y_min) / spacing_cm)):
        y = y_min + row * spacing_cm
        for col in range(1, math.ceil((max_x - min_x) / spacing_cm)):
            x = min_x + col * spacing_cm
            point = Point(x, y)
            if shape.contains(point) and shape.boundary.distance(point) > spacing_cm * .35:
                sampled[(round(x, 7), round(y, 7))] = (x, y)
    vertices = sorted(sampled.values(), key=lambda point: (point[1], point[0]))
    lookup = {tuple(round(value, 7) for value in point): index
              for index, point in enumerate(vertices)}
    # GEOS can include almost-collinear zero-area faces on a dense straight
    # seam.  Those would turn a welded two-face side seam non-manifold.
    kept = [triangle for triangle in triangulate(MultiPoint(vertices))
            if triangle.area > 1e-8 and shape.buffer(1e-8).covers(triangle)]
    covered = unary_union(kept) if kept else None
    if not kept or covered.area / shape.area < .995:
        raise ValueError("Triangulation failed to cover the stitch polygon")
    faces = [tuple(lookup[tuple(round(value, 7) for value in point)]
                   for point in list(triangle.exterior.coords)[:3])
             for triangle in kept]
    # Unconstrained Delaunay can bridge a small concave notch while passing
    # the 99.5% area test. Fill only that exact uncovered polygon, using
    # vertices already in the sampled stitch outline. Never invent a new
    # point or move a sewing endpoint to make the mesh appear complete.
    boundary_gap_patch_faces = 0
    if strict_boundary:
        uncovered = shape.difference(covered)
        gaps = (list(uncovered.geoms) if hasattr(uncovered, "geoms")
                else [uncovered])
    else:
        gaps = []
    for gap in gaps:
        if not isinstance(gap, Polygon) or gap.area <= 1e-8:
            continue
        additions = []
        for triangle in constrained_delaunay_triangles(gap).geoms:
            keys = [tuple(round(value, 7) for value in point)
                    for point in list(triangle.exterior.coords)[:3]]
            if any(key not in lookup for key in keys):
                additions = []
                break
            additions.append(tuple(lookup[key] for key in keys))
        if additions and abs(sum(abs((vertices[b][0] - vertices[a][0])
                                       * (vertices[c][1] - vertices[a][1])
                                       - (vertices[b][1] - vertices[a][1])
                                       * (vertices[c][0] - vertices[a][0])) / 2
                                   for a, b, c in additions) - gap.area) < 1e-5:
            faces.extend(additions)
            boundary_gap_patch_faces += len(additions)
    top_indices = [index for index, point in enumerate(vertices)
                   if abs(point[1] - y_min) < 1e-7]
    top_indices.sort(key=lambda index: vertices[index][0])
    if require_horizontal_top:
        left, right = horizontal_span(polygon, y_min)
        if abs(vertices[top_indices[0]][0] - left) > 1e-6 or abs(
                vertices[top_indices[-1]][0] - right) > 1e-6:
            raise ValueError("Top stitch endpoints were lost")
        top_width = right - left
    else:
        # Neckline flaps can end in a point.  They still need complete
        # triangulation and boundary validation, but have no horizontal seam.
        top_width = 0.0
    boundary_paths = []
    for a, b in zip(polygon, polygon[1:] + polygon[:1]):
        dx, dy = b[0] - a[0], b[1] - a[1]
        length_squared = dx * dx + dy * dy
        along = []
        for index, point in enumerate(vertices):
            t = ((point[0] - a[0]) * dx + (point[1] - a[1]) * dy) / length_squared
            distance = abs((point[0] - a[0]) * dy - (point[1] - a[1]) * dx)
            if -1e-6 <= t <= 1 + 1e-6 and distance < 1e-4:
                along.append((t, index))
        boundary_paths.append([index for _t, index in sorted(along)])
    # Delaunay may skip collinear vertices on a non-quadrilateral outline.
    # Leaving them in the vertex list creates unconstrained cloth particles:
    # they fall through the scene while a decorative boundary curve still
    # follows them. Split the one adjacent triangle along the omitted edge.
    used = {index for face in faces for index in face}
    for path_index, path in enumerate(
            boundary_paths if strict_boundary or len(polygon) == 4 else []):
        attached_positions = [position for position, index in enumerate(path)
                              if index in used]
        if not attached_positions or attached_positions[0] != 0 or (
                attached_positions[-1] != len(path) - 1):
            raise ValueError(
                "Stitch boundary endpoint was omitted by triangulation: "
                f"segment {path_index}, "
                f"from {vertices[path[0]]} to {vertices[path[-1]]}")
        for first_pos, last_pos in zip(attached_positions,
                                       attached_positions[1:]):
            if last_pos - first_pos == 1:
                continue
            first, last = path[first_pos], path[last_pos]
            candidates = [(face_index, face) for face_index, face in enumerate(faces)
                          if first in face and last in face]
            if len(candidates) != 1:
                raise ValueError("Skipped stitch vertices lack one boundary face")
            face_index, face = candidates[0]
            chain = path[first_pos:last_pos + 1]
            for index in range(3):
                if face[index] == last and face[(index + 1) % 3] == first:
                    chain = list(reversed(chain))
                    break
                if face[index] == first and face[(index + 1) % 3] == last:
                    break
            else:
                raise ValueError("Skipped stitch vertices are not on a face edge")
            opposite = next(index for index in face if index not in {first, last})
            fragments = [(a, b, opposite) for a, b in zip(chain, chain[1:])]
            if any(abs((vertices[b][0] - vertices[a][0])
                        * (vertices[opposite][1] - vertices[a][1])
                        - (vertices[b][1] - vertices[a][1])
                        * (vertices[opposite][0] - vertices[a][0])) <= 2e-8
                   for a, b, _ in fragments):
                raise ValueError("Boundary repair would create a degenerate face")
            faces[face_index:face_index + 1] = fragments
            used.update(chain)
    if (strict_boundary or len(polygon) == 4) and used != set(range(len(vertices))):
        raise ValueError("Sampled panel has vertices disconnected from all faces")
    edge_faces = Counter(tuple(sorted((face[index], face[(index + 1) % 3])))
                         for face in faces for index in range(3))
    invalid = [(path_index, edge_faces[tuple(sorted((a, b)))],
                tuple(round(value, 4) for value in vertices[a]),
                tuple(round(value, 4) for value in vertices[b]))
               for path_index, path in enumerate(boundary_paths)
               for a, b in zip(path, path[1:])
               if strict_boundary or len(polygon) == 4 or path_index == 0
               if edge_faces[tuple(sorted((a, b)))] != 1]
    if invalid:
        raise ValueError(f"Stitch boundary is not a one-face mesh edge: "
                         f"{Counter(invalid).most_common(6)}")
    return {"vertices_cm": vertices, "faces": faces,
            "top_indices": top_indices,
            "boundary_paths": boundary_paths,
            "top_width_cm": top_width, "height_cm": y_max - y_min,
            "stitch_area_cm2": shape.area,
            "boundary_gap_patch_faces": boundary_gap_patch_faces}


def sample_constrained_stitch_outline(points: list[tuple[float, float]],
                                      *, spacing_cm: float = 1.8) -> dict:
    """Boundary-faithful diagnostic mesh for a notched, concave paper outline.

    Unconstrained Delaunay can silently omit a deep dart tip.  This preserves
    every stitch vertex and segment; it does not promise simulation-grade
    interior triangle sizing or a sewn dart closure.
    """
    from shapely import constrained_delaunay_triangles
    from shapely.geometry import Polygon

    polygon = points[:-1] if points[0] == points[-1] else list(points)
    if len(polygon) < 3:
        raise ValueError("A stitched outline needs at least three points")
    y_min = min(y for _x, y in polygon)
    y_max = max(y for _x, y in polygon)
    vertices = []
    boundary_paths = []
    for a, b in zip(polygon, polygon[1:] + polygon[:1]):
        length = math.dist(a, b)
        step = min(spacing_cm, .6) if (abs(a[1] - y_min) < 1e-7 and
                                         abs(b[1] - y_min) < 1e-7) else spacing_cm
        count = max(1, math.ceil((length - 1e-8) / step))
        start = len(vertices)
        vertices.extend((a[0] + (b[0] - a[0]) * index / count,
                         a[1] + (b[1] - a[1]) * index / count)
                        for index in range(count))
        boundary_paths.append(list(range(start, len(vertices))) + [
            len(vertices) if b != polygon[0] else 0])
    shape = Polygon(vertices)
    if not shape.is_valid or shape.area <= 0:
        raise ValueError("The darted stitch outline is not a simple polygon")
    lookup = {(round(x, 7), round(y, 7)): index
              for index, (x, y) in enumerate(vertices)}
    triangles = list(constrained_delaunay_triangles(shape).geoms)
    if not triangles or abs(sum(t.area for t in triangles) - shape.area) > 1e-6:
        raise ValueError("Constrained triangles do not cover the stitched outline")
    faces = [tuple(lookup[(round(x, 7), round(y, 7))]
                   for x, y in list(triangle.exterior.coords)[:3])
             for triangle in triangles]
    mesh = {"vertices_cm": vertices, "faces": faces,
            "top_indices": sorted((index for index, (_x, y) in enumerate(vertices)
                                   if abs(y - y_min) < 1e-7),
                                  key=lambda index: vertices[index][0]),
            "boundary_paths": boundary_paths,
            "top_width_cm": 0.0, "height_cm": y_max - y_min,
            "constrained_boundary_only": True,
            "stitch_area_cm2": shape.area}
    validate_cloth_panel_mesh(mesh)
    return mesh


def validate_cloth_panel_mesh(panel: dict) -> dict:
    """Reject broken cloth topology before it reaches a drape simulation."""
    vertices = panel["vertices_cm"]
    faces = panel["faces"]
    try:
        finite_vertices = all(
            len(vertex) == 2 and all(isinstance(value, (int, float)) and
                                     math.isfinite(value) for value in vertex)
            for vertex in vertices)
    except (TypeError, ValueError, OverflowError):
        finite_vertices = False
    if not finite_vertices:
        raise ValueError("Cloth panel has invalid vertex coordinates")
    if not vertices or not faces or any(len(face) != 3 or any(
            not isinstance(index, int) or not 0 <= index < len(vertices)
            for index in face) or len(set(face)) != 3 for face in faces):
        raise ValueError("Cloth panel has invalid triangles")
    if len({tuple(sorted(face)) for face in faces}) != len(faces):
        raise ValueError("Cloth panel has duplicate triangles")
    double_areas = [(vertices[b][0] - vertices[a][0])
                    * (vertices[c][1] - vertices[a][1])
                    - (vertices[b][1] - vertices[a][1])
                    * (vertices[c][0] - vertices[a][0])
                    for a, b, c in faces]
    if any(abs(area) <= 2e-8 for area in double_areas):
        raise ValueError("Cloth panel has degenerate triangles")
    if any((area > 0) != (double_areas[0] > 0) for area in double_areas):
        raise ValueError("Cloth panel has inconsistent triangle winding")
    stitch_area = panel.get("stitch_area_cm2")
    if stitch_area is not None:
        if not isinstance(stitch_area, (int, float)) or not math.isfinite(
                stitch_area) or stitch_area <= 0:
            raise ValueError("Cloth panel has invalid stitch area")
        triangle_area = sum(abs(area) for area in double_areas) / 2
        if abs(triangle_area - stitch_area) > max(1e-5, stitch_area * .005):
            raise ValueError("Cloth triangle area does not match stitch outline")
    used = {index for face in faces for index in face}
    if used != set(range(len(vertices))):
        raise ValueError("Cloth panel has vertices disconnected from faces")
    edge_faces = Counter(tuple(sorted((face[index], face[(index + 1) % 3])))
                         for face in faces for index in range(3))
    if any(count > 2 for count in edge_faces.values()):
        raise ValueError("Cloth panel has non-manifold triangle edges")
    adjacent = {index: set() for index in range(len(vertices))}
    for a, b in edge_faces:
        adjacent[a].add(b)
        adjacent[b].add(a)
    reached = {0}
    pending = [0]
    while pending:
        current = pending.pop()
        new = adjacent[current] - reached
        reached.update(new)
        pending.extend(new)
    if len(reached) != len(vertices):
        raise ValueError("Cloth panel has disconnected mesh islands")
    paths = panel["boundary_paths"]
    if not paths or any(len(path) < 2 or any(
            not isinstance(index, int) or not 0 <= index < len(vertices)
            for index in path) for path in paths):
        raise ValueError("Cloth panel has invalid boundary paths")
    bad = [(path_index, a, b) for path_index, path in enumerate(paths)
           for a, b in zip(path, path[1:])
           if edge_faces[tuple(sorted((a, b)))] != 1]
    if bad:
        raise ValueError(f"Cloth panel has {len(bad)} non-boundary stitch edges")
    return {"vertices": len(vertices), "faces": len(faces),
            "stitch_edges": sum(len(path) - 1 for path in paths)}


def cloth_mesh_boundary_coverage(panel: dict) -> dict[str, int | bool]:
    """Report unrepresented outline edges without altering the paper pattern.

    A non-strict Delaunay panel can have a valid declared hem seam yet omit
    vertices on an armhole or side outline. Such a mesh is not ready for a
    garment preview even when its triangles and declared seam paths validate.
    """
    edge_faces = Counter(tuple(sorted((face[index], face[(index + 1) % 3])))
                         for face in panel["faces"] for index in range(3))
    mesh_boundary = {edge for edge, count in edge_faces.items() if count == 1}
    declared_boundary = {tuple(sorted((a, b)))
                         for path in panel["boundary_paths"]
                         for a, b in zip(path, path[1:])}
    return {"complete": mesh_boundary == declared_boundary,
            "undeclared_mesh_boundary_edges": len(mesh_boundary - declared_boundary),
            "missing_declared_boundary_edges": len(declared_boundary - mesh_boundary)}


def place_three_panel_tops(host_length_cm: float, widths_cm: dict[str, float]
                           ) -> dict[str, float]:
    """Locate B/C/A along the open coat hem with equal side gaps.

    The side gaps represent unmodelled joining/seam regions.  This function
    rejects negative ease rather than silently stretching the real pattern.
    """
    if set(widths_cm) != {"A", "B", "C"} or any(
            width <= 0 for width in widths_cm.values()):
        raise ValueError("Expected positive A/B/C stitch top lengths")
    spare = host_length_cm - sum(widths_cm.values())
    if spare < -0.1:
        raise ValueError("Bodice hem is shorter than the three pattern tops")
    gap = max(0.0, spare / 2)
    return {"B": 0.0,
            "C": widths_cm["B"] + gap,
            "A": widths_cm["B"] + gap + widths_cm["C"] + gap}


def xy_scale_for_polyline_length(points: list[tuple[float, float, float]],
                                 target_length: float) -> float:
    """Fit a guide hem circumference without ignoring its vertical folds."""
    if len(points) < 2 or target_length <= 0:
        raise ValueError("A positive target and at least two guide points are required")

    def length(scale: float) -> float:
        return sum(math.sqrt(((b[0] - a[0]) * scale) ** 2
                             + ((b[1] - a[1]) * scale) ** 2
                             + (b[2] - a[2]) ** 2)
                   for a, b in zip(points, points[1:]))

    if length(0.0) > target_length:
        raise ValueError("Vertical folds alone exceed target hem length")
    low, high = 0.0, 1.0
    while length(high) < target_length:
        high *= 2
        if high > 32:
            raise ValueError("Guide hem cannot be scaled to target")
    for _ in range(50):
        midpoint = (low + high) / 2
        if length(midpoint) < target_length:
            low = midpoint
        else:
            high = midpoint
    return (low + high) / 2


def pair_seam_vertices(host_x_cm: list[float], panel_x_cm: list[float],
                       *, max_length_mismatch_cm: float = .1
                       ) -> list[tuple[int, int]]:
    """Pair every endpoint of two unequal seam discretizations by position.

    Indices refer to the caller's ordered seam lists, not a complete mesh.
    The resulting edges are candidates for Blender sewing springs; no claim
    of actual stitch count or thread strength is implied.
    """
    if len(host_x_cm) < 2 or len(panel_x_cm) < 2:
        raise ValueError("A seam needs at least two points on each side")
    host_origin, panel_origin = host_x_cm[0], panel_x_cm[0]
    host_span = host_x_cm[-1] - host_origin
    panel_span = panel_x_cm[-1] - panel_origin
    if host_span <= 0 or panel_span <= 0:
        raise ValueError("Seam points must be ordered from left to right")
    if max_length_mismatch_cm < 0 or abs(host_span - panel_span) > max_length_mismatch_cm:
        raise ValueError("Seam stitch lengths do not match")
    host_positions = [(x - host_origin) / host_span for x in host_x_cm]
    panel_positions = [(x - panel_origin) / panel_span for x in panel_x_cm]
    pairs = set()
    for index, location in enumerate(host_positions):
        closest = min(range(len(panel_positions)),
                      key=lambda other: abs(panel_positions[other] - location))
        pairs.add((index, closest))
    for index, location in enumerate(panel_positions):
        closest = min(range(len(host_positions)),
                      key=lambda other: abs(host_positions[other] - location))
        pairs.add((closest, index))
    return sorted(pairs)


def require_initial_sewing_clearance(vertices, spring_pairs, *,
                                     unit_m_per_cm=.02,
                                     max_gap_cm=10.0):
    """Reject a sewing setup that would pull distant cloth across the body.

    This is an initial-placement sanity check, not proof of a sewable seam or
    a fit tolerance.  ``spring_pairs`` refer to the complete 3D cloth mesh.
    """
    if not vertices or not spring_pairs or unit_m_per_cm <= 0 or max_gap_cm <= 0:
        raise ValueError("Initial sewing clearance needs valid mesh and limits")
    if any(min(a, b) < 0 or max(a, b) >= len(vertices) or a == b
           for a, b in spring_pairs):
        raise ValueError("Initial sewing clearance has invalid spring indices")
    gaps = [math.dist(vertices[a], vertices[b]) / unit_m_per_cm
            for a, b in spring_pairs]
    worst = max(gaps)
    if worst > max_gap_cm:
        raise ValueError(
            f"Initial sewing gap {worst:.2f} cm exceeds "
            f"{max_gap_cm:.2f} cm; revise panel placement before cloth simulation")
    return {"spring_count": len(gaps), "maximum_gap_cm": round(worst, 3)}


def _pattern_triangle_weights(point_cm, paper_vertices_cm, faces):
    x, y = point_cm
    for ia, ib, ic in faces:
        a, b, c = (paper_vertices_cm[index] for index in (ia, ib, ic))
        if (x < min(a[0], b[0], c[0]) - 1e-7
                or x > max(a[0], b[0], c[0]) + 1e-7
                or y < min(a[1], b[1], c[1]) - 1e-7
                or y > max(a[1], b[1], c[1]) + 1e-7):
            continue
        denominator = ((b[1] - c[1]) * (a[0] - c[0])
                       + (c[0] - b[0]) * (a[1] - c[1]))
        if abs(denominator) < 1e-10:
            continue
        wa = ((b[1] - c[1]) * (x - c[0])
              + (c[0] - b[0]) * (y - c[1])) / denominator
        wb = ((c[1] - a[1]) * (x - c[0])
              + (a[0] - c[0]) * (y - c[1])) / denominator
        wc = 1 - wa - wb
        if min(wa, wb, wc) >= -1e-6:
            return (ia, ib, ic), (wa, wb, wc)
    return None


def interpolate_pattern_surface_with_normal(
        point_cm: tuple[float, float],
        paper_vertices_cm: list[tuple[float, float]],
        faces: list[tuple[int, int, int]],
        surface_vertices: list[tuple[float, float, float]]
        ) -> tuple[tuple[float, float, float],
                   tuple[float, float, float]] | None:
    """Map a paper point to the draped shell and its local unit normal.

    The normal has the face's winding; the caller decides which side is the
    exterior.  None means the point lies outside the cut shell.
    """
    if len(paper_vertices_cm) != len(surface_vertices):
        raise ValueError("Paper and draped surface vertex counts differ")
    located = _pattern_triangle_weights(point_cm, paper_vertices_cm, faces)
    if located is None:
        return None
    indices, weights = located
    position = tuple(sum(weight * surface_vertices[index][axis]
                         for index, weight in zip(indices, weights))
                     for axis in range(3))
    a, b, c = (surface_vertices[index] for index in indices)
    ab = tuple(b[axis] - a[axis] for axis in range(3))
    ac = tuple(c[axis] - a[axis] for axis in range(3))
    cross = (ab[1] * ac[2] - ab[2] * ac[1],
             ab[2] * ac[0] - ab[0] * ac[2],
             ab[0] * ac[1] - ab[1] * ac[0])
    length = math.sqrt(sum(value * value for value in cross))
    if length < 1e-10:
        return None
    return position, tuple(value / length for value in cross)


def interpolate_pattern_surface(point_cm: tuple[float, float],
                                paper_vertices_cm: list[tuple[float, float]],
                                faces: list[tuple[int, int, int]],
                                surface_vertices: list[tuple[float, float, float]]
                                ) -> tuple[float, float, float] | None:
    """Locate a paper point on its already-draped triangular surface.

    Return None outside the cut shape.  This maps a decorative layer onto a
    provisional lower shell; it does not infer missing cloth beyond the edge.
    """
    mapped = interpolate_pattern_surface_with_normal(
        point_cm, paper_vertices_cm, faces, surface_vertices)
    return mapped[0] if mapped is not None else None


def weld_seam_vertices(vertices, faces, spring_edges, seam_pairs):
    """Join coincident stitch-boundary vertices in a simulation surface.

    This changes only the preview mesh, never a paper pattern or its seam
    allowance.  Return vertices, triangles, remaining springs and an old-to-
    new index map so measurements still refer to their original panel grids.
    """
    count = len(vertices)
    parent = list(range(count))

    def root(index):
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    for a, b in seam_pairs:
        if not 0 <= a < count or not 0 <= b < count:
            raise ValueError("Seam vertex index is outside the mesh")
        ra, rb = root(a), root(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)
    groups = {}
    for index in range(count):
        groups.setdefault(root(index), []).append(index)
    new_indices = {old_root: index for index, old_root in enumerate(groups)}
    index_map = [new_indices[root(index)] for index in range(count)]
    welded_vertices = [tuple(sum(vertices[index][axis] for index in group)
                             / len(group) for axis in range(3))
                       for group in groups.values()]
    welded_faces = [tuple(index_map[index] for index in face)
                    for face in faces]
    if any(len(set(face)) != 3 for face in welded_faces):
        raise ValueError("Welding collapsed a garment triangle")
    welded_springs = sorted({tuple(sorted((index_map[a], index_map[b])))
                             for a, b in spring_edges
                             if index_map[a] != index_map[b]})
    return welded_vertices, welded_faces, welded_springs, index_map


def aligned_trapezoid_distance(point_cm, outline_cm, seam_start_cm):
    """Place a flared panel row on the same 3D seam interval as its top.

    Both side boundaries map to the same seam positions as their top corners;
    radial flare must still be provided by the 3D adapter to preserve the
    row's extra 2D fabric width.  This is an initial placement, not a drape.
    """
    if len(outline_cm) != 4:
        raise ValueError("Aligned shell requires four-sided lower panels")
    top_left, top_right, lower_right, lower_left = outline_cm
    height = lower_left[1] - top_left[1]
    top_width = top_right[0] - top_left[0]
    if height <= 0 or top_width <= 0 or abs(lower_right[1] - lower_left[1]) > 1e-6:
        raise ValueError("Aligned shell requires a horizontal trapezoid hem")
    progress = (point_cm[1] - top_left[1]) / height
    if not -1e-6 <= progress <= 1 + 1e-6:
        raise ValueError("Point is outside the lower-panel height")
    left = top_left[0] * (1 - progress) + lower_left[0] * progress
    right = top_right[0] * (1 - progress) + lower_right[0] * progress
    return seam_start_cm + (point_cm[0] - left) / (right - left) * top_width


def sample_bodice_from_stitch_line(points: list[tuple[float, float]],
                                   hem_y_cm: float, *,
                                   sewn_hem_runs: list[tuple[float, float]] | None = None
                                   ) -> dict:
    """Tessellate a bodice with a dense, exact 2D hem boundary.

    Flip the paper pattern vertically so its bottom joining edge becomes the
    same seam axis as an extension's top edge.  A later 3D adapter may place
    both boundaries on one shared curve without fabricating a new cut shape.
    """
    polygon = points[:-1] if points[0] == points[-1] else list(points)
    flipped = [(x, hem_y_cm - y) for x, y in polygon]
    if sewn_hem_runs and len(sewn_hem_runs) > 1:
        # Preserve every waist-dart V as a true cloth boundary.  A dart mouth
        # is *not* a seam to the lower panel, so record separate horizontal
        # runs and their cumulative sewn distances instead of bridging it.
        mesh = sample_constrained_stitch_outline(flipped)
        paths = []
        sewn_positions = []
        elapsed = 0.0
        for left, right in sewn_hem_runs:
            indices = [index for index, (x, y) in enumerate(mesh["vertices_cm"])
                       if abs(y) < 1e-7 and left - 1e-6 <= x <= right + 1e-6]
            indices.sort(key=lambda index: mesh["vertices_cm"][index][0])
            if (len(indices) < 2 or
                    abs(mesh["vertices_cm"][indices[0]][0] - left) > 1e-5 or
                    abs(mesh["vertices_cm"][indices[-1]][0] - right) > 1e-5):
                raise ValueError("A sewn dart hem run lost its stitch endpoints")
            paths.append(indices)
            sewn_positions.extend(elapsed + mesh["vertices_cm"][index][0] - left
                                  for index in indices)
            elapsed += right - left
        validate_cloth_panel_mesh(mesh)
        mesh["vertices_cm"] = [(x, hem_y_cm - y)
                               for x, y in mesh["vertices_cm"]]
        mesh["faces"] = [tuple(reversed(face)) for face in mesh["faces"]]
        mesh["hem_indices"] = [index for path in paths for index in path]
        mesh["hem_paths"] = paths
        mesh["hem_sewn_positions_cm"] = sewn_positions
        mesh["hem_width_cm"] = elapsed
        mesh.pop("top_indices")
        mesh.pop("top_width_cm")
        mesh.pop("height_cm")
        return mesh
    candidates = [index for index, (a, b) in enumerate(
        zip(flipped, flipped[1:] + flipped[:1]))
        if abs(a[1]) < .03 and abs(b[1]) < .03 and abs(a[0] - b[0]) > .03]
    if not candidates:
        raise ValueError("Bodice has no straight stitch hem")
    seam_index = max(candidates, key=lambda index: abs(
        flipped[index][0] - flipped[(index + 1) % len(flipped)][0]))
    if flipped[seam_index][0] > flipped[(seam_index + 1) % len(flipped)][0]:
        flipped.reverse()
        seam_index = len(flipped) - 2 - seam_index
    flipped = flipped[seam_index:] + flipped[:seam_index]
    # Bodice hems can contain a notch vertex in the middle of an otherwise
    # straight stitch line.  Sampling each sub-edge independently gives a
    # different vertex grid from the lower panel, so sewing springs pull its
    # boundary into a tiny sawtooth.  Preserve the source stitch outline and
    # notch metadata elsewhere; only re-grid this simulation mesh seam.
    left_index = min((index for index, point in enumerate(flipped)
                      if abs(point[1]) < .03), key=lambda index: flipped[index][0])
    flipped = flipped[left_index:] + flipped[:left_index]
    seam_count = 0
    while seam_count < len(flipped) and abs(flipped[seam_count][1]) < .03:
        seam_count += 1
    if seam_count < 2 or any(b[0] <= a[0] for a, b in zip(
            flipped[:seam_count], flipped[1:seam_count])):
        raise ValueError("Bodice hem is not a left-to-right stitch line")
    seam_left, seam_right = flipped[0][0], flipped[seam_count - 1][0]
    steps = math.ceil((seam_right - seam_left) / .6)
    flipped = [(seam_left + (seam_right - seam_left) * index / steps, 0.0)
               for index in range(steps + 1)] + flipped[seam_count:]
    mesh = sample_panel(flipped, strict_boundary=True)
    mesh["vertices_cm"] = [(x, hem_y_cm - y) for x, y in mesh["vertices_cm"]]
    mesh["faces"] = [tuple(reversed(face)) for face in mesh["faces"]]
    mesh["hem_indices"] = mesh.pop("top_indices")
    mesh["hem_width_cm"] = mesh.pop("top_width_cm")
    mesh.pop("height_cm")
    return mesh
