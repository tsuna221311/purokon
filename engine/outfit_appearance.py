"""Conservative, local visual hints for the *preview*, not sewing instructions.

The pattern classifier returns construction parts. A long open coat can be
misread as a skirt there; the 3D preview needs a separate, explicitly
uncertain visual description. No character names or image fingerprints are
used. Unclear pictures return ``silhouette='unknown'`` instead of inventing a
specific costume.
"""

from __future__ import annotations

from statistics import median

from PIL import Image, ImageOps


def _hex(rgb: tuple[int, int, int]) -> str:
    return "#" + "".join(f"{max(0, min(255, value)):02x}" for value in rgb)


def _median_color(pixels: list[tuple[int, int, int]], default: str) -> str:
    if len(pixels) < 12:
        return default
    return _hex(tuple(round(median(channel)) for channel in zip(*pixels)))


def analyze_outfit_appearance(image: Image.Image) -> dict:
    """Return a low-confidence layered-coat hint only when pixel evidence agrees.

    Coordinates are deliberately broad regions of a centred, full-body costume
    reference. This is not a vision model: photos with cluttered backgrounds,
    unusual poses or crops may remain unknown and need user correction.
    """
    sample = ImageOps.exif_transpose(image).convert("RGB")
    sample.thumbnail((220, 360))
    width, height = sample.size
    if width < 64 or height < 96:
        return {"silhouette": "unknown", "confidence": 0.0, "source": "local_pixels"}

    def pixels_in(x0: float, y0: float, x1: float, y1: float):
        for y in range(int(height * y0), min(height, int(height * y1))):
            for x in range(int(width * x0), min(width, int(width * x1))):
                yield sample.getpixel((x, y))

    def neutral(rgb):
        return max(rgb) - min(rgb) < 44

    def dark(rgb):
        return neutral(rgb) and 20 <= sum(rgb) / 3 <= 112

    def pale_middle(rgb):
        value = sum(rgb) / 3
        return neutral(rgb) and 116 <= value <= 215

    def bright_accent(rgb):
        value = max(rgb)
        return 85 <= value <= 250 and max(rgb) - min(rgb) >= 65

    # Lower left/right dark panels around a lighter centre are characteristic
    # of an open coat, unlike a continuous skirt or closed dress.
    left = list(pixels_in(.24, .40, .46, .62))
    right = list(pixels_in(.68, .40, .90, .62))
    centre = list(pixels_in(.47, .39, .67, .54))
    left_dark = [color for color in left if dark(color)]
    right_dark = [color for color in right if dark(color)]
    centre_light = [color for color in centre if pale_middle(color)]
    dark_ratio = min(len(left_dark) / max(1, len(left)),
                     len(right_dark) / max(1, len(right)))
    light_ratio = len(centre_light) / max(1, len(centre))
    outer_samples = [color for color in pixels_in(.25, .34, .90, .63) if dark(color)]
    inner_samples = [color for color in pixels_in(.44, .35, .67, .53) if pale_middle(color)]
    accent_left = [color for color in pixels_in(.18, .27, .55, .43)
                   if bright_accent(color)]
    accent_right = [color for color in pixels_in(.55, .27, .95, .43)
                    if bright_accent(color)]
    accent_samples = accent_left + accent_right
    # Requiring a filled-colour accent keeps dense black line art (for example
    # a striped ball gown sketch) from masquerading as two coat panels.
    open_coat = (dark_ratio >= .08 and light_ratio >= .12
                 and len(accent_samples) >= max(18, width * height * .0005))
    # The visual hint is intentionally independent of the garment-part labels.
    # Distinct local colours are essential: a single saturated colour must not
    # be painted over the whole coat as the old client palette estimator did.
    palette = {
        "outer": _median_color(outer_samples, "#303139"),
        "inner": _median_color(inner_samples, "#aaa9a8"),
        "accent": _median_color(accent_samples, "#d9c900"),
    }
    confidence = round(min(.72, .28 + dark_ratio + light_ratio), 2) if open_coat else 0.0
    if open_coat:
        def dark_share(x0: float, y0: float, x1: float, y1: float) -> float:
            region = list(pixels_in(x0, y0, x1, y1))
            return sum(dark(color) for color in region) / max(1, len(region))

        waist_outer = (dark_share(.16, .41, .34, .48)
                       + dark_share(.82, .41, .98, .48)) / 2
        hem_outer = (dark_share(.16, .48, .34, .55)
                     + dark_share(.82, .48, .98, .55)) / 2
        waist_sleeve = (dark_share(.30, .41, .45, .48)
                         + dark_share(.75, .41, .90, .48)) / 2
        upper_sleeve = (dark_share(.30, .34, .45, .41)
                        + dark_share(.75, .34, .90, .41)) / 2
        hem_flare = max(.15, min(.95,
                                 .30 + (hem_outer - waist_outer) * 3.5))
        sleeve_volume = max(.20, min(.90,
                                     .25 + (upper_sleeve - waist_sleeve) * 3.5))
        accent_side = ("right" if len(accent_right) > len(accent_left) * 1.5
                       else "left" if len(accent_left) > len(accent_right) * 1.5
                       else "unknown")
        shape = {
            "hem_flare": round(hem_flare, 2),
            "sleeve_volume": round(sleeve_volume, 2),
            "accent_side": accent_side,
        }
    else:
        shape = None
    return {
        "silhouette": "open_long_coat" if open_coat else "unknown",
        "confidence": confidence,
        "source": "local_pixels",
        "palette": palette,
        "shape": shape,
        "review_required": True,
    }
