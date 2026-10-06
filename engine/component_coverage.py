"""Check whether named outfit components survived a 3D export.

This is an inventory check, not a visual-quality or construction certificate.
The manifest is supplied by the reviewer; it must not be inferred from the
mesh itself, or a missing part could silently disappear from the benchmark.
"""

from __future__ import annotations

from itertools import product


def _transform(point: tuple[float, float, float], node: dict) -> tuple[float, float, float]:
    x, y, z = point
    if "matrix" in node:
        m = node["matrix"]  # glTF stores column-major matrices.
        return (m[0] * x + m[4] * y + m[8] * z + m[12],
                m[1] * x + m[5] * y + m[9] * z + m[13],
                m[2] * x + m[6] * y + m[10] * z + m[14])
    sx, sy, sz = node.get("scale", (1, 1, 1))
    x, y, z = x * sx, y * sy, z * sz
    qx, qy, qz, qw = node.get("rotation", (0, 0, 0, 1))
    # v' = v + 2w(q x v) + 2(q x (q x v)).
    tx, ty, tz = (2 * (qy * z - qz * y),
                  2 * (qz * x - qx * z),
                  2 * (qx * y - qy * x))
    x, y, z = (x + qw * tx + qy * tz - qz * ty,
               y + qw * ty + qz * tx - qx * tz,
               z + qw * tz + qx * ty - qy * tx)
    dx, dy, dz = node.get("translation", (0, 0, 0))
    return x + dx, y + dy, z + dz


def _node_bounds(gltf: dict, node_index: int, parents: dict[int, int]) -> dict | None:
    node = gltf["nodes"][node_index]
    if node["mesh"] >= len(gltf.get("meshes", [])):
        return None
    bounds = []
    for primitive in gltf["meshes"][node["mesh"]].get("primitives", []):
        position_index = primitive.get("attributes", {}).get("POSITION")
        if position_index is None:
            continue
        accessor = gltf["accessors"][position_index]
        if "min" not in accessor or "max" not in accessor:
            continue
        for corner in product(*zip(accessor["min"], accessor["max"])):
            point = tuple(corner)
            current = node_index
            while True:
                point = _transform(point, gltf["nodes"][current])
                if current not in parents:
                    break
                current = parents[current]
            bounds.append(point)
    if not bounds:
        return None
    return {"min": [min(p[axis] for p in bounds) for axis in range(3)],
            "max": [max(p[axis] for p in bounds) for axis in range(3)]}


def _geometry_passes(bounds: dict, component: dict) -> bool:
    center = [(a + b) / 2 for a, b in zip(bounds["min"], bounds["max"])]
    for axis_name, interval in component.get("center_region", {}).items():
        axis = {"x": 0, "y": 1, "z": 2, "x_abs": 0}[axis_name]
        value = abs(center[axis]) if axis_name == "x_abs" else center[axis]
        if not interval[0] <= value <= interval[1]:
            return False
    for axis_name, minimum in component.get("min_extent", {}).items():
        axis = {"x": 0, "y": 1, "z": 2}[axis_name]
        if bounds["max"][axis] - bounds["min"][axis] < minimum:
            return False
    return True


def _aabb_overlap(left: dict, right: dict, tolerance: float = .005) -> bool:
    """Conservative warning only; intersecting bounding boxes are not mesh collisions."""
    return all(min(left["max"][axis], right["max"][axis])
               - max(left["min"][axis], right["min"][axis]) > tolerance
               for axis in range(3))


def audit_component_nodes(gltf: dict, components: list[dict]) -> dict:
    nodes = gltf.get("nodes", [])
    parents = {child: index for index, node in enumerate(nodes)
               for child in node.get("children", [])}
    results = []
    for component in components:
        needle = str(component["name_contains"]).casefold()
        minimum = int(component.get("required_count", 1))
        if not needle or minimum < 1:
            raise ValueError("component name and positive required_count are required")
        matched_indices = [index for index, node in enumerate(nodes)
                           if "mesh" in node and needle in node.get("name", "").casefold()]
        matches = [nodes[index].get("name", "").casefold() for index in matched_indices]
        bounds = [_node_bounds(gltf, index, parents) for index in matched_indices]
        geometry_requested = any(key in component for key in
                                 ("center_region", "min_extent", "bilateral",
                                  "avoid_overlap_with"))
        geometry_ok = None
        if geometry_requested:
            geometry_ok = (len(matches) >= minimum and all(bounds)
                           and all(_geometry_passes(box, component) for box in bounds))
            if geometry_ok and component.get("bilateral"):
                centers_x = [(box["min"][0] + box["max"][0]) / 2 for box in bounds]
                geometry_ok = any(x < 0 for x in centers_x) and any(x > 0 for x in centers_x)
        results.append({
            "component": component["component"],
            "required_count": minimum,
            "found_count": len(matches),
            "present": len(matches) >= minimum,
            "geometry_ok": geometry_ok,
            "bounds": bounds,
            "matched_nodes": matches,
            "evidence": component.get("evidence", ""),
        })
    by_name = {item["component"]: item for item in results}
    for rule, item in zip(components, results):
        possible_overlap = []
        for other_name in rule.get("avoid_overlap_with", []):
            other = by_name.get(other_name)
            if other and any(_aabb_overlap(left, right)
                             for left in item["bounds"] if left
                             for right in other["bounds"] if right):
                possible_overlap.append(other_name)
        item["possible_overlap_with"] = possible_overlap
        if possible_overlap and item["geometry_ok"] is True:
            item["geometry_ok"] = False
    return {
        "present_groups": sum(item["present"] for item in results),
        "geometry_pass_groups": sum(item["geometry_ok"] is True for item in results),
        "geometry_checked_groups": sum(item["geometry_ok"] is not None for item in results),
        "expected_groups": len(results),
        "components": results,
        "note": "名称・位置・大きさ・AABB重なりの機械的確認のみ。AABB重なりは実メッシュの貫通を証明しない。写真との形状一致、裁断、可動、固定方法は別途確認が必要。",
    }
