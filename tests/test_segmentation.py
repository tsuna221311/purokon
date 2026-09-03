from PIL import Image, ImageDraw

from engine.segmentation import SimpleSilhouetteSegmenter, get_default_segmenter


def _figure_on(background, fill, size=(400, 800), box=(100, 150, 300, 700)):
    image = Image.new("RGB" if len(background) == 3 else "RGBA", size, background)
    ImageDraw.Draw(image).rectangle(box, fill=fill)
    return image


def test_white_background_still_works():
    image = _figure_on((255, 255, 255), (0, 0, 0))
    regions = SimpleSilhouetteSegmenter().segment(image)
    labels = {r.label for r in regions}
    assert labels == {"torso", "left_sleeve", "right_sleeve", "lower_body"}


def test_dark_background_is_supported_via_corner_color_estimation():
    image = _figure_on((20, 20, 30), (230, 210, 190))
    regions = SimpleSilhouetteSegmenter().segment(image)
    assert len(regions) == 4


def test_transparent_background_uses_alpha_channel():
    image = _figure_on((0, 0, 0, 0), (230, 210, 190, 255))
    regions = SimpleSilhouetteSegmenter().segment(image)
    assert len(regions) == 4


def test_blank_image_returns_no_regions_instead_of_guessing():
    image = Image.new("RGB", (400, 800), "white")
    regions = SimpleSilhouetteSegmenter().segment(image)
    assert regions == []


def test_solid_color_image_is_rejected_as_unreliable():
    # 背景推定が失敗し「画像全体が前景」に見えるケースを想定。
    image = Image.new("RGB", (400, 800), (128, 60, 60))
    regions = SimpleSilhouetteSegmenter().segment(image)
    assert regions == []


def test_regions_are_within_image_bounds():
    image = _figure_on((255, 255, 255), (10, 10, 10))
    regions = SimpleSilhouetteSegmenter().segment(image)
    for region in regions:
        x0, y0, x1, y1 = region.bbox
        assert 0 <= x0 < x1 <= image.width
        assert 0 <= y0 < y1 <= image.height


def test_large_image_is_downscaled_for_analysis_but_bbox_stays_in_original_coords():
    # 実際のスマートフォン写真相当(数千px四方)をテストしたところ、フル解像度で
    # 前景マスクを計算すると数秒〜十数秒かかることが判明したための性能対策
    # (MAX_ANALYSIS_DIMENSION)。ここでは「大きな画像でも縮小して解析される」
    # ことと「返されるbboxは縮小後ではなく元画像の座標系である」ことを確認する。
    size = (2400, 4000)
    box = (600, 900, 1800, 4000 - 900)
    image = _figure_on((255, 255, 255), (10, 10, 10), size=size, box=box)

    segmenter = SimpleSilhouetteSegmenter()
    analysis_image, scale = segmenter._analysis_image_and_scale(image)
    assert scale < 1.0
    assert max(analysis_image.size) <= segmenter.MAX_ANALYSIS_DIMENSION

    regions = segmenter.segment(image)
    assert len(regions) == 4
    for region in regions:
        x0, y0, x1, y1 = region.bbox
        assert 0 <= x0 < x1 <= image.width
        assert 0 <= y0 < y1 <= image.height
    # ダウンスケールしても、検出された全体の輪郭は元の矩形(box)に近い範囲になる
    # はず（縮小の丸め誤差を許容するゆるい許容範囲でチェック）。
    torso = next(r for r in regions if r.label == "torso")
    lower = next(r for r in regions if r.label == "lower_body")
    assert abs(torso.bbox[0] - box[0]) < 40
    assert abs(lower.bbox[3] - box[3]) < 40


def test_small_image_is_not_downscaled():
    segmenter = SimpleSilhouetteSegmenter()
    image = _figure_on((255, 255, 255), (10, 10, 10), size=(400, 800), box=(100, 150, 300, 700))
    analysis_image, scale = segmenter._analysis_image_and_scale(image)
    assert scale == 1.0
    assert analysis_image.size == image.size


def test_get_default_segmenter_returns_simple_silhouette_without_sam_env():
    assert isinstance(get_default_segmenter(), SimpleSilhouetteSegmenter)


def test_stray_disconnected_blob_does_not_distort_bbox():
    # 実写画像でのテストで見つかった不具合の再現テスト。ブランドタグ・ロゴ
    # シール等の小さな写り込みが、本体の衣類とは無関係な位置にあるだけで
    # ネックライン等の境界計算が大きくずれてしまっていた（隅の小さなタグ1つ
    # だけで4割近く境界が移動するケースを実写相当のテスト画像で確認済み）。
    # 最大の連結領域だけを採用する修正により、写り込みが無い場合と同一の
    # bboxになることを確認する。
    baseline = _figure_on((255, 255, 255), (10, 10, 10))
    with_tag = baseline.copy()
    ImageDraw.Draw(with_tag).rectangle((5, 5, 20, 20), fill=(200, 30, 30))  # 隅の小さなタグ

    baseline_regions = SimpleSilhouetteSegmenter().segment(baseline)
    tagged_regions = SimpleSilhouetteSegmenter().segment(with_tag)

    assert len(tagged_regions) == 4
    baseline_bboxes = {r.label: r.bbox for r in baseline_regions}
    tagged_bboxes = {r.label: r.bbox for r in tagged_regions}
    assert baseline_bboxes == tagged_bboxes


def test_two_separate_garments_in_one_photo_uses_only_the_larger_one():
    # 「コーディネート写真」のように、1枚の画像に離れた2つの衣類が写っている
    # 場合、以前は両方を囲む無意味な合成矩形になっていた。最大の連結領域のみを
    # 採用することで、より大きい方の衣類だけの一貫した範囲になることを確認する
    # （もう一方は無視される既知の制約。README/使い方ガイドに明記済み）。
    w, h = 1000, 1400
    image = Image.new("RGB", (w, h), (255, 255, 255))
    draw = ImageDraw.Draw(image)
    small_box = (150, 80, 550, 420)     # 小さい方の衣類
    large_box = (500, 900, 900, 1300)   # 大きい方の衣類
    draw.rectangle(small_box, fill=(30, 60, 120))
    draw.rectangle(large_box, fill=(90, 40, 40))

    regions = SimpleSilhouetteSegmenter().segment(image)
    assert len(regions) == 4

    all_x = [c for r in regions for c in (r.bbox[0], r.bbox[2])]
    all_y = [c for r in regions for c in (r.bbox[1], r.bbox[3])]
    # 全リージョンの外接範囲が、大きい方の矩形の範囲内に収まっている
    # （小さい方の矩形と混ざっていない）ことを確認する。
    assert min(all_x) >= large_box[0] - 2
    assert max(all_x) <= large_box[2] + 2
    assert min(all_y) >= large_box[1] - 2
    assert max(all_y) <= large_box[3] + 2
