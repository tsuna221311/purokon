"""Stitch geometry for the generated single-side front-zip bodice panels.

The current SVG templates share an underarm-to-shoulder contour followed by
a pronounced shoulder-to-neck jump.  Refuse other contours instead of
silently measuring the front opening as an armhole.
"""

from __future__ import annotations

from math import dist, isfinite


def front_zip_armhole_path(stitch_outline_cm, underarm_y_cm):
    points = list(stitch_outline_cm)
    if (len(points) < 3 or underarm_y_cm is None or
            not isfinite(underarm_y_cm) or
            any(len(point) != 2 or not all(isfinite(v) for v in point)
                for point in points)):
        raise ValueError("Front zip armhole needs a finite stitch contour")
    xs = [point[0] for point in points]
    span = max(xs) - min(xs)
    if span <= 0:
        raise ValueError("Front zip armhole has zero width")
    mid = (min(xs) + max(xs)) / 2
    underarms = [(abs(point[1] - underarm_y_cm), index)
                 for index, point in enumerate(points) if point[0] > mid]
    if not underarms:
        raise ValueError("The declared underarm is not on the stitch contour")
    error, start = min(underarms)
    if error > .05:
        raise ValueError("The declared underarm is not on the stitch contour")
    shoulder = None
    for index in range(start, len(points) - 1):
        a, b = points[index:index + 2]
        if a[0] - b[0] > .20 * span and b[1] < a[1]:
            shoulder = index
            break
    if shoulder is None:
        raise ValueError("The shoulder-to-neck edge was not identifiable")
    path = points[start:shoulder + 1]
    length = sum(dist(a, b) for a, b in zip(path, path[1:]))
    if len(path) < 5 or length < 10:
        raise ValueError("The front armhole path is incomplete")
    return path


def front_zip_armhole_length_cm(stitch_outline_cm, underarm_y_cm):
    path = front_zip_armhole_path(stitch_outline_cm, underarm_y_cm)
    return sum(dist(a, b) for a, b in zip(path, path[1:]))
