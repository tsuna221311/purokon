"""Preview-specific visual hints must stay separate from sewing classification."""

from PIL import Image, ImageDraw

from engine.outfit_appearance import analyze_outfit_appearance


def _reference_with_open_outerwear():
    image = Image.new("RGB", (200, 300), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((48, 105, 91, 195), fill="#303239")
    draw.rectangle((136, 105, 180, 195), fill="#303239")
    draw.rectangle((94, 108, 132, 164), fill="#b1aeae")
    draw.polygon([(130, 85), (169, 85), (180, 111), (141, 112)], fill="#ddcc18")
    return image


def test_open_coat_separates_outer_inner_and_accent_colours():
    hint = analyze_outfit_appearance(_reference_with_open_outerwear())
    assert hint["silhouette"] == "open_long_coat"
    assert hint["confidence"] > 0
    assert hint["review_required"] is True
    assert hint["palette"]["outer"] != hint["palette"]["inner"]
    assert hint["palette"]["accent"] != hint["palette"]["outer"]
    assert hint["shape"]["accent_side"] == "right"
    assert .15 <= hint["shape"]["hem_flare"] <= .95
    assert .20 <= hint["shape"]["sleeve_volume"] <= .90


def test_wider_lower_coat_increases_preview_hem_flare():
    plain = _reference_with_open_outerwear()
    flared = plain.copy()
    draw = ImageDraw.Draw(flared)
    draw.polygon([(15, 165), (48, 140), (63, 190)], fill="#303239")
    draw.polygon([(170, 140), (199, 165), (172, 190)], fill="#303239")
    assert (analyze_outfit_appearance(flared)["shape"]["hem_flare"]
            > analyze_outfit_appearance(plain)["shape"]["hem_flare"])


def test_accent_can_be_on_the_left_without_a_character_preset():
    image = _reference_with_open_outerwear()
    draw = ImageDraw.Draw(image)
    draw.rectangle((130, 80, 185, 112), fill="white")
    draw.polygon([(22, 85), (63, 85), (72, 111), (30, 111)], fill="#ddcc18")
    hint = analyze_outfit_appearance(image)
    assert hint["silhouette"] == "open_long_coat"
    assert hint["shape"]["accent_side"] == "left"


def test_solid_dress_is_not_claimed_to_be_an_open_coat():
    image = Image.new("RGB", (200, 300), "white")
    ImageDraw.Draw(image).rectangle((45, 95, 180, 200), fill="#303239")
    hint = analyze_outfit_appearance(image)
    assert hint["silhouette"] == "unknown"
    assert hint["review_required"] is True
    assert hint["shape"] is None


def test_monochrome_line_art_is_left_for_manual_review():
    image = _reference_with_open_outerwear()
    ImageDraw.Draw(image).rectangle((130, 85, 180, 112), fill="white")
    assert analyze_outfit_appearance(image)["silhouette"] == "unknown"


def test_tiny_or_unusable_reference_remains_unknown():
    hint = analyze_outfit_appearance(Image.new("RGB", (10, 10), "white"))
    assert hint["silhouette"] == "unknown"
