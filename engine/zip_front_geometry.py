"""Stitch geometry for the generated single-side front-zip bodice panels.

The current SVG templates share an underarm-to-shoulder contour followed by
a pronounced shoulder-to-neck jump.  Refuse other contours instead of
silently measuring the front opening as an armhole.
"""

from __future__ import annotations

from math import dist, isfinite


def front_zip_center_path(stitch_outline_cm, hem_y_cm):
    """Return the sewn centre-front opening from neckline to hem.

    The zip-panel template runs down its centre edge immediately before the
    bottom edge.  Find that edge from geometry rather than a hard-coded point
    number; bust-dart sampling can add contour vertices before it.
    """
    points = list(stitch_outline_cm)
    if (len(points) < 5 or hem_y_cm is None or not isfinite(hem_y_cm)
            or any(len(point) != 2 or not all(isfinite(v) for v in point)
                   for point in points)):
        raise ValueError("Front zip opening needs a finite stitch contour")
    bottom = [(point[0], index) for index, point in enumerate(points)
              if abs(point[1] - hem_y_cm) <= .05]
    if len(bottom) < 2:
        raise ValueError("Front zip opening has no identifiable bottom edge")
    hem_index = min(bottom)[1]
    start = hem_index
    while (start > 0 and
           points[start - 1][1] < points[start][1] - .01):
        start -= 1
    path = points[start:hem_index + 1]
    length = sum(dist(a, b) for a, b in zip(path, path[1:]))
    if len(path) < 3 or length < 20 or any(
            b[1] <= a[1] for a, b in zip(path, path[1:])):
        raise ValueError("Front zip opening is not a descending centre seam")
    return path


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
        # Boat necklines leave a shorter shoulder edge.  At 15% of this
        # panel's width it is still distinct from sampled armhole segments.
        if a[0] - b[0] > .15 * span and b[1] < a[1]:
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
