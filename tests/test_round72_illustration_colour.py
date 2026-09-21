"""round72: 袖なしのイラストに、袖の型紙が2枚付いてきた。

アニメ風の衣装ラフを3着描き起こして、イラストモードに通した
(既存作品のキャラクターは使えないので、この検証のために描いた架空の衣装)。

【実測】同じ袖が3着とも出てきた

```
    絵              round71が出した袖       正しくは
    パフ袖(短い)    straight 36.1×56.0cm    短い袖
    長袖            straight 36.1×56.0cm    長袖(これだけ合っていた)
    **袖なし**      straight 36.1×56.0cm    **袖は要らない**
```

原因は`engine/illustration_fit.measure_sleeves`の最初の数行にあった。

```python
    if figure_detected:
        return SleeveReading()
```

**人物が着ている絵では、袖の読み取りを丸ごと諦めていた。** 素肌の腕も袖も
シルエットでは同じ黒い塊なので見分けられない、という理由で、docstringにも
そう書いてある。諦めた結果どうなるかは書いていなかった——袖は常に採寸
どおりになり、袖なしのドレスにも袖が2枚付く。

同じ根から、スカート丈も壊れていた。シルエットだけで裾を探すと、長袖の絵では
**腕が終わる行**を裾と取り違える。

```
    絵        round71のスカート丈   正しくは
    パフ袖    読めない(既定値)      短いフレア
    長袖      26cm                  49cm      ← 腕の先を裾と読んでいた
    袖なし    110cm                 111cm
```

【round72で足したもの】シルエットには写らないが**絵には写っている**情報——
色——を使う(`engine/skin_tone.py`)。素肌と服は色が違うので、腕のどこまでが
袖かは色なら読める。読めないとき(肌色の服・腕が体にくっついた絵)は、
黙って当てずっぽうを返さず**読めなかったと言う**。

このファイルが見張るのは:

  1. 袖なしの絵に袖が付く
  2. 袖の長さ・形が絵と無関係になる
  3. スカート丈が腕の先で決まる
  4. 背景に近い色の服がシルエットから抜け落ちる
  5. 読めなかったときに黙る
"""

import math
import tempfile

import pytest

from PIL import Image, ImageDraw

from engine.measurements import Measurements
from engine.pipeline import PatternForgePipeline
from engine.segmentation import get_default_segmenter
from engine.skin_tone import read_colours

WIDTH, HEIGHT = 900, 1500
CENTRE = WIDTH // 2
SKIN = (246, 217, 196)
LINE = (43, 36, 48)
HAIR = (74, 59, 82)

#: 絵を描いたときの座標(＝正解)。読み取りをこれと突き合わせる。
SHOULDER_Y = 330
WAIST_Y = 600


def _figure(draw):
    """頭・首・脚。3着に共通の下地。

    首は**肩線まで届かせる**。最初に描いたときは首を302行で止めて肩線(330)
    との間に白を残してしまい、頭が本体とつながらず、シルエットから頭が
    丸ごと落ちていた(実測: 上端が120ではなく330)。頭が落ちると
    `garment_span`の首・肩の検出そのものが動かず、**本番の絵では通る道を
    テストが通っていない**ことになる。
    """
    draw.ellipse([CENTRE - 61, 120, CENTRE + 61, 276], fill=SKIN, outline=LINE, width=3)
    draw.polygon([(CENTRE - 67, 194), (CENTRE - 74, 93), (CENTRE + 74, 93),
                  (CENTRE + 67, 194), (CENTRE, 147)], fill=HAIR)
    draw.rectangle([CENTRE - 20, 260, CENTRE + 20, SHOULDER_Y + 8],
                   fill=SKIN, outline=LINE, width=3)


def _bare_arms(draw, top, bottom):
    """素肌の腕。肩の内側から始めて、身頃と**つなげて**描く。

    最初は腕を身頃から12px離して描いていた。シルエットは連結成分の
    いちばん大きい塊だけを残すので、離れた腕はそこで捨てられ、
    「腕が胴から離れて見えません」として色が読めなかった。実際の
    ラフでは腕は肩でつながっている。

    つなげたうえで、腕は下へ行くほど**外へ**開かせる。まっすぐ下ろすと、
    腕と胴のすき間が上(肩)でも下(広がったスカート)でも閉じて、
    囲まれた穴になる。穴は`_fill_outline`が埋めるので、腕と胴が
    1つの塊にくっつき、やはり腕が見えなくなった。
    """
    for sign in (-1, 1):
        draw.polygon([(CENTRE + sign * 90, top), (CENTRE + sign * 132, top),
                      (CENTRE + sign * 176, bottom), (CENTRE + sign * 134, bottom)],
                     fill=SKIN, outline=LINE, width=3)


def _curve(p0, c0, c1, p1, steps=24):
    """3次ベジエを点列にする。身頃の脇線を**曲線**で描くために使う。

    最初は肩からウエストまで直線で細らせていた。直線のテーパーには
    「くびれ」が無い——ウエストの31行上でも幅は5%しか違わず、
    `_find_waist`が要求する1.06倍に届かない。実測でスカート丈が
    読めず(`skirt_ratio=None`)、原因は絵の側にあった。実際の衣装ラフの
    脇線は胸で張り出してウエストで入る曲線なので、そう描き直す。
    """
    out = []
    for i in range(steps + 1):
        t = i / steps
        u = 1.0 - t
        out.append((u ** 3 * p0[0] + 3 * u * u * t * c0[0]
                    + 3 * u * t * t * c1[0] + t ** 3 * p1[0],
                    u ** 3 * p0[1] + 3 * u * u * t * c0[1]
                    + 3 * u * t * t * c1[1] + t ** 3 * p1[1]))
    return out


def _bodice(shoulder_half, waist_half, bulge_half, waist_y, bulge_y):
    """肩からウエストまで、脇線が曲線の身頃の輪郭。"""
    right = _curve((CENTRE + shoulder_half, SHOULDER_Y),
                   (CENTRE + bulge_half, bulge_y),
                   (CENTRE + waist_half + 18, waist_y - 60),
                   (CENTRE + waist_half, waist_y))
    left = [(2 * CENTRE - x, y) for x, y in reversed(right)]
    return [(CENTRE - shoulder_half, SHOULDER_Y),
            (CENTRE + shoulder_half, SHOULDER_Y)] + right + left


def _legs(draw, top, bottom):
    for x in (CENTRE - 60, CENTRE + 26):
        draw.rounded_rectangle([x, top, x + 34, bottom], radius=16,
                               fill=SKIN, outline=LINE, width=3)


def puff_sleeve_illustration() -> Image.Image:
    """パフ袖・フレアの短いスカート。身頃は**背景に近い淡い色**。"""
    image = Image.new("RGB", (WIDTH, HEIGHT), (255, 255, 255))
    draw = ImageDraw.Draw(image)
    _figure(draw)
    hem_y = 860
    # 腕(素肌)
    for x in (CENTRE - 222, CENTRE + 182):
        draw.rounded_rectangle([x, SHOULDER_Y + 110, x + 40, SHOULDER_Y + 360],
                               radius=19, fill=SKIN, outline=LINE, width=3)
    # 身頃(淡い水色 = 白い背景に近い)
    draw.polygon(_bodice(118, 86, 128, WAIST_Y, SHOULDER_Y + 130),
                 fill=(232, 236, 248), outline=LINE, width=4)
    # パフ袖(丸くふくらむ。胴より外へ出る)
    for cx in (CENTRE - 168, CENTRE + 168):
        draw.ellipse([cx - 82, SHOULDER_Y + 52 - 70, cx + 82, SHOULDER_Y + 52 + 70],
                     fill=(232, 236, 248), outline=LINE, width=4)
    # フレアの短いスカート
    draw.polygon([(CENTRE - 86, WAIST_Y), (CENTRE + 86, WAIST_Y),
                  (CENTRE + 236, hem_y), (CENTRE - 236, hem_y)],
                 fill=(85, 102, 170), outline=LINE, width=4)
    _legs(draw, hem_y - 10, 1330)
    return image


def long_sleeve_illustration() -> Image.Image:
    """長袖・膝丈のタイトスカート。袖は手首まで。"""
    image = Image.new("RGB", (WIDTH, HEIGHT), (255, 255, 255))
    draw = ImageDraw.Draw(image)
    _figure(draw)
    waist_y, hem_y, wrist_y = 610, 960, SHOULDER_Y + 400
    for sign in (-1, 1):
        draw.polygon([(CENTRE + sign * 118, SHOULDER_Y),
                      (CENTRE + sign * 186, SHOULDER_Y + 34),
                      (CENTRE + sign * 206, wrist_y),
                      (CENTRE + sign * 142, wrist_y),
                      (CENTRE + sign * 124, SHOULDER_Y + 90)],
                     fill=(31, 42, 68), outline=LINE, width=4)
        x = CENTRE + sign * 206 if sign < 0 else CENTRE + 142
        draw.rounded_rectangle([x, wrist_y, x + 64, wrist_y + 70], radius=26,
                               fill=SKIN, outline=LINE, width=3)
    draw.polygon([(CENTRE - 118, SHOULDER_Y), (CENTRE + 118, SHOULDER_Y),
                  (CENTRE + 80, waist_y), (CENTRE - 80, waist_y)],
                 fill=(31, 42, 68), outline=LINE, width=4)
    draw.polygon([(CENTRE - 80, waist_y), (CENTRE + 80, waist_y),
                  (CENTRE + 96, hem_y), (CENTRE - 96, hem_y)],
                 fill=(59, 63, 82), outline=LINE, width=4)
    _legs(draw, hem_y - 10, 1330)
    return image


def sleeveless_illustration() -> Image.Image:
    """袖なし・床までのサーキュラードレス。裾は波形(スカラップ)。"""
    image = Image.new("RGB", (WIDTH, HEIGHT), (255, 255, 255))
    draw = ImageDraw.Draw(image)
    _figure(draw)
    waist_y, hem_y = 590, 1330
    _bare_arms(draw, SHOULDER_Y + 6, SHOULDER_Y + 360)
    draw.polygon([(CENTRE - 104, SHOULDER_Y), (CENTRE + 104, SHOULDER_Y),
                  (CENTRE + 78, waist_y), (CENTRE - 78, waist_y)],
                 fill=(122, 47, 78), outline=LINE, width=4)
    wave = [(CENTRE - 330 + 660 * i / 40.0,
             hem_y + 26 * math.sin(i / 40.0 * math.pi * 5)) for i in range(41)]
    draw.polygon([(CENTRE - 78, waist_y), (CENTRE + 78, waist_y)] + wave[::-1],
                 fill=(122, 47, 78), outline=LINE, width=4)
    return image


def skin_coloured_dress_illustration() -> Image.Image:
    """服が肌と同じ色。**読めない**はずの絵。"""
    image = Image.new("RGB", (WIDTH, HEIGHT), (255, 255, 255))
    draw = ImageDraw.Draw(image)
    _figure(draw)
    waist_y, hem_y = 600, 900
    _bare_arms(draw, SHOULDER_Y + 6, SHOULDER_Y + 360)
    draw.polygon([(CENTRE - 104, SHOULDER_Y), (CENTRE + 104, SHOULDER_Y),
                  (CENTRE + 78, waist_y), (CENTRE - 78, waist_y)],
                 fill=SKIN, outline=LINE, width=4)
    draw.polygon([(CENTRE - 78, waist_y), (CENTRE + 78, waist_y),
                  (CENTRE + 150, hem_y), (CENTRE - 150, hem_y)],
                 fill=SKIN, outline=LINE, width=4)
    _legs(draw, hem_y - 10, 1330)
    return image


#: 紺(31,42,68)から見ても肌(246,217,196)から見ても遠いが、**肌の方が近い**色。
#: redmeanで 肌まで176 / 紺まで557。セーラー服の金の袖口のつもり。
GOLD = (255, 255, 85)
NAVY = (31, 42, 68)


def pale_bodice_illustration() -> Image.Image:
    """身頃だけが白に近く、スカートが濃い、床までのノースリーブドレス。

    穴を埋めても前景が**1.16倍にしか増えない**絵。round71の「1.5倍以上
    増えたときだけ埋める」という条件をくぐり抜ける。
    """
    image = Image.new("RGB", (WIDTH, HEIGHT), (255, 255, 255))
    draw = ImageDraw.Draw(image)
    _figure(draw)
    _bare_arms(draw, SHOULDER_Y + 6, SHOULDER_Y + 360)
    draw.polygon(_bodice(110, 80, 116, WAIST_Y, SHOULDER_Y + 120),
                 fill=(238, 240, 250), outline=LINE, width=4)
    draw.polygon([(CENTRE - 80, WAIST_Y), (CENTRE + 80, WAIST_Y),
                  (CENTRE + 300, 1330), (CENTRE - 300, 1330)],
                 fill=(40, 44, 70), outline=LINE, width=4)
    return image


def framed_illustration() -> Image.Image:
    """絵の外周に枠線がある、よくあるラフ。

    枠があると「閉じた穴」が画像全体になる。埋めると画面の95.8%が前景に
    なってしまうので、**埋めてはいけない**。
    """
    image = Image.new("RGB", (WIDTH, HEIGHT), (255, 255, 255))
    draw = ImageDraw.Draw(image)
    draw.rectangle([12, 12, WIDTH - 13, HEIGHT - 13], outline=(60, 60, 60), width=5)
    _figure(draw)
    _bare_arms(draw, SHOULDER_Y + 6, SHOULDER_Y + 360)
    draw.polygon(_bodice(110, 80, 116, WAIST_Y, SHOULDER_Y + 120),
                 fill=(122, 47, 78), outline=LINE, width=4)
    draw.polygon([(CENTRE - 80, WAIST_Y), (CENTRE + 80, WAIST_Y),
                  (CENTRE + 300, 1330), (CENTRE - 300, 1330)],
                 fill=(122, 47, 78), outline=LINE, width=4)
    return image


#: 金の袖口と肌色リボンを入れた長袖の絵で、袖が終わる行(＝手首)。
TRIMMED_WRIST_Y = SHOULDER_Y + 400


def trimmed_sleeve_illustration() -> Image.Image:
    """長袖に**金の袖口**と**細い肌色のリボン**が付いた絵。

    どちらも袖の一部であって、素肌ではない。
      * 金(255,255,85)は、紺の身頃よりも肌に近い色である。
        「服と肌のどちらに近いか」で決めると、袖口から先が素肌に見える。
      * 肌色のリボンは7px。「1行でも肌なら袖の裾」とすると、リボンの
        高さで袖が終わったことになる。
    """
    image = Image.new("RGB", (WIDTH, HEIGHT), (255, 255, 255))
    draw = ImageDraw.Draw(image)
    _figure(draw)
    waist_y, hem_y, wrist = 610, 960, TRIMMED_WRIST_Y
    for sign in (-1, 1):
        a, b = sorted((CENTRE + sign * 142, CENTRE + sign * 206))
        draw.polygon([(CENTRE + sign * 118, SHOULDER_Y),
                      (CENTRE + sign * 186, SHOULDER_Y + 34),
                      (CENTRE + sign * 206, SHOULDER_Y + 300),
                      (CENTRE + sign * 206, wrist),
                      (CENTRE + sign * 142, wrist),
                      (CENTRE + sign * 142, SHOULDER_Y + 300),
                      (CENTRE + sign * 124, SHOULDER_Y + 90)],
                     fill=NAVY, outline=LINE, width=4)
        draw.rectangle([a, wrist - 90, b, wrist - 4], fill=GOLD, outline=LINE, width=3)
        draw.rectangle([a, SHOULDER_Y + 232, b, SHOULDER_Y + 239], fill=SKIN)
        draw.rounded_rectangle([a, wrist, b, wrist + 70], radius=26,
                               fill=SKIN, outline=LINE, width=3)
    draw.polygon(_bodice(118, 80, 124, waist_y, SHOULDER_Y + 140),
                 fill=NAVY, outline=LINE, width=4)
    draw.polygon([(CENTRE - 80, waist_y), (CENTRE + 80, waist_y),
                  (CENTRE + 96, hem_y), (CENTRE - 96, hem_y)],
                 fill=(59, 63, 82), outline=LINE, width=4)
    _legs(draw, hem_y - 10, 1330)
    return image


def pointed_hem_gown_illustration() -> Image.Image:
    """剣先(ハンカチーフ)ヘムの、腕を覆い隠すほど広いドレス。

    裾の剣先は**396行**にわたって「左 | 中 | 右」の3塊を作る。腕は
    スカートに飲み込まれて見えないので、ここで剣先を腕と取り違えると、
    袖の有無も裾の位置も、もっともらしい別の値が静かに出る。
    """
    image = Image.new("RGB", (WIDTH, HEIGHT), (255, 255, 255))
    draw = ImageDraw.Draw(image)
    waist_y, hem_y, tip_y, points = 590, 900, 1300, 7
    _figure(draw)
    _bare_arms(draw, SHOULDER_Y + 6, SHOULDER_Y + 360)
    draw.polygon([(CENTRE - 104, SHOULDER_Y), (CENTRE + 104, SHOULDER_Y),
                  (CENTRE + 78, waist_y), (CENTRE - 78, waist_y)],
                 fill=(122, 47, 78), outline=LINE, width=4)
    edge = []
    for i in range(points + 1):
        edge.append((CENTRE - 300 + 600 * i / points, hem_y))
        if i < points:
            edge.append((CENTRE - 300 + 600 * (i + 0.5) / points, tip_y))
    draw.polygon([(CENTRE - 78, waist_y), (CENTRE + 78, waist_y),
                  (CENTRE + 300, hem_y)] + edge[::-1] + [(CENTRE - 300, hem_y)],
                 fill=(122, 47, 78), outline=LINE, width=4)
    return image


BODY = Measurements(bust=82, waist=62, hip=88, height=158,
                    sleeve_length=54, shoulder_width=37)


def _generate(image):
    pipe = PatternForgePipeline(output_dir=tempfile.mkdtemp())
    return pipe.generate_from_illustration(image, BODY)


def _parts(result) -> list[str]:
    return [p.part_type for p in result.finalized_parts]


def _notes(result) -> str:
    summary = result.summary()
    return "\n".join(list(summary.get("design_notes") or [])
                     + list(summary.get("measurement_warnings") or []))


def _colours(image):
    mask = get_default_segmenter().silhouette_mask(image)
    return read_colours(image, mask)


# --- 1. 袖なしの絵に袖を付けない ---------------------------------------------

def test_a_sleeveless_illustration_gets_no_sleeve_pattern():
    """袖なしの絵からは、袖の型紙を出さないこと。

    round71までは`straight 36.1×56.0cm`の袖が2枚付いてきた。布も裁つし、
    袖ぐりも袖を付ける前提で引かれる。
    """
    result = _generate(sleeveless_illustration())
    assert "sleeve" not in _parts(result), _parts(result)
    assert "cuffs" not in _parts(result)
    assert "ノースリーブ" in _notes(result)


def test_the_colour_reading_calls_it_sleeveless():
    reading = _colours(sleeveless_illustration())
    assert reading.usable, reading.reason
    assert reading.sleeveless
    assert reading.sleeve_hem_y is None


# --- 2. 袖の長さ・形が絵に沿う -----------------------------------------------

def test_a_puff_sleeve_illustration_gets_a_short_sleeve():
    """短い袖の絵から、短い袖が出ること。

    round71までは、どの絵でも袖丈56.0cm(採寸どおりの長袖)だった。
    """
    result = _generate(puff_sleeve_illustration())
    sleeves = [p for p in result.finalized_parts if p.part_type == "sleeve"]
    assert sleeves, "袖が1枚も出ていません"
    assert all(p.height_cm < 30.0 for p in sleeves), [p.height_cm for p in sleeves]


def test_a_long_sleeve_illustration_still_gets_a_long_sleeve():
    """長袖の絵は長袖のまま(直したことで壊れていないこと)。"""
    result = _generate(long_sleeve_illustration())
    sleeves = [p for p in result.finalized_parts if p.part_type == "sleeve"]
    assert sleeves
    assert all(p.height_cm > 45.0 for p in sleeves), [p.height_cm for p in sleeves]


def test_the_sleeve_hem_is_read_where_the_sleeve_actually_ends():
    """袖の裾の行が、絵で袖が終わっている高さと合うこと。

    パフ袖はy≈435で袖が終わり、その下は素肌の腕。長袖はy≈730の手首まで。
    """
    puff = _colours(puff_sleeve_illustration())
    assert puff.usable, puff.reason
    assert puff.sleeve_hem_y is not None
    assert abs(puff.sleeve_hem_y - 440) <= 30, puff.sleeve_hem_y

    long_sleeve = _colours(long_sleeve_illustration())
    assert long_sleeve.usable, long_sleeve.reason
    assert long_sleeve.sleeve_hem_y is not None
    assert abs(long_sleeve.sleeve_hem_y - 730) <= 30, long_sleeve.sleeve_hem_y


# --- 3. スカート丈が腕の先で決まらない ---------------------------------------

def test_the_hem_is_found_at_the_skirt_not_at_the_wrist():
    """服の下端が、手首ではなくスカートの裾であること。

    round71までは、長袖の絵で**手首の行(801)**を裾と判定していた。
    正しい裾は960行で、丈にすると26cm対49cm——ミニスカートと膝丈の違いが
    静かに出ていた。
    """
    reading = _colours(long_sleeve_illustration())
    assert reading.usable, reading.reason
    assert reading.garment_bottom is not None
    assert abs(reading.garment_bottom - 960) <= 20, reading.garment_bottom


@pytest.mark.parametrize("maker,expected", [
    (puff_sleeve_illustration, 0.96),
    (long_sleeve_illustration, 1.25),
    (sleeveless_illustration, 2.85),
], ids=["パフ袖", "長袖", "袖なし"])
def test_the_skirt_length_ratio_matches_the_drawing(maker, expected):
    """スカート丈の比が、絵の座標から計算した値と合うこと。

    正解は描いたときの座標そのもの——(裾 − ウエスト) ÷ (ウエスト − 肩)。
    許容は10%。絵から読む値なので、桁が合っていることを見る。
    """
    from engine import illustration_fit

    image = maker()
    mask = get_default_segmenter().silhouette_mask(image)
    reading = illustration_fit.measure_proportions(mask, read_colours(image, mask))
    assert reading.skirt_ratio is not None, "丈比が読めていません"
    assert reading.skirt_ratio == pytest.approx(expected, rel=0.10), reading.skirt_ratio


# --- 4. 背景に近い色の服が、シルエットから抜け落ちない -----------------------

def test_a_pale_garment_on_white_is_not_hollowed_out():
    """白に近い色の身頃が、シルエットの穴にならないこと。

    前景は「背景色から離れた画素」なので、淡い色の服は抜け落ちる。
    閉じた穴を埋めれば戻る。round71は「1.5倍以上に増えたときだけ埋める」
    という条件を置いていて、この絵では埋めなかった。その結果、胴のくびれが
    見つからずスカート丈が読めなかった(`skirt_ratio=None`)。

    ここは**倍率で見ない**。倍率は絵を描き替えるたびに動く数で、いくつなら
    正しいのかを説明できない(実際、身頃の脇線を曲線に描き直しただけで
    1.36倍→1.51倍に動き、上限1.5を根拠なく踏んだ)。代わりに、この絵では
    **正解が計算できる**ことを使う——白(255,255,255)でない画素が、
    描いたものそのものである。
    """
    import numpy as np

    from engine.segmentation import SimpleSilhouetteSegmenter

    segmenter = SimpleSilhouetteSegmenter()
    image = puff_sleeve_illustration()
    pixels = np.asarray(image, dtype=np.int16)
    drawn = np.abs(pixels - 255).max(axis=2) > 6        # 白でない = 描いた所

    raw = np.asarray(segmenter._foreground_mask(image)).astype(bool)
    solid = np.asarray(segmenter._solid_foreground_mask(image)).astype(bool)
    # 埋める前は、淡い水色の身頃がまるごと欠けている。
    assert int((drawn & ~raw).sum()) > drawn.sum() * 0.2
    # 埋めた後は、描いたものと一致する(欠けも、はみ出しもない)。
    assert int((drawn & ~solid).sum()) == 0, int((drawn & ~solid).sum())
    assert int((solid & ~drawn).sum()) == 0, int((solid & ~drawn).sum())

    mask = segmenter.silhouette_mask(image)
    from engine import illustration_fit
    reading = illustration_fit.measure_proportions(mask, read_colours(image, mask))
    assert reading.skirt_ratio is not None, "穴が埋まっていないと丈が読めません"


# --- 5. 読めなかったときに黙らない -------------------------------------------

def test_a_skin_coloured_dress_says_it_could_not_read_the_sleeve():
    """服と肌が同じ色の絵では、読めなかったと言うこと。

    ここで黙ると、袖なしの絵に袖が付いたまま利用者は気付けない。
    round71までは、人物の絵すべてがこの状態だった。
    """
    result = _generate(skin_coloured_dress_illustration())
    notes = _notes(result)
    assert "袖は絵から読み取れませんでした" in notes, notes
    assert "袖が付きます" in notes


def test_the_reason_is_specific_not_generic():
    """読めなかった理由が、具体的に書かれていること。"""
    reading = _colours(skin_coloured_dress_illustration())
    assert not reading.usable
    assert reading.reason
    assert reading.reason != "色を読める状態ではありません"


def test_a_readable_illustration_does_not_get_the_warning():
    """読めた絵には、その注記を出さないこと(空振りしていないか)。"""
    assert "袖は絵から読み取れませんでした" not in _notes(
        _generate(long_sleeve_illustration()))


# --- 6. 色の見分けそのもの ---------------------------------------------------

def test_the_distance_is_perceptual_not_plain_rgb():
    """色の隔たりを、素のRGBの距離では測らないこと。

    淡い水色の身頃(232,236,248)と肌(246,217,196)は、素のRGBでは57しか
    離れていない。見た目にははっきり違う色なのに「近すぎて読めない」と
    判定されていた。redmeanでは87になり、読めるようになる。
    """
    from engine.skin_tone import _distance

    pale = (232.0, 236.0, 248.0)
    skin = (246.0, 217.0, 196.0)
    plain = sum((a - b) ** 2 for a, b in zip(pale, skin)) ** 0.5
    assert plain < 60.0                      # 素のRGBでは近い
    assert _distance(pale, skin) > 80.0      # redmeanでは離れている


def test_skin_is_decided_by_nearness_to_skin_not_by_which_colour_is_closer():
    """「服に近いか肌に近いか」ではなく「肌に近いか」で決めていること。

    服は1色とは限らない。実測(パフ袖の絵)では、青いスカート(85,102,170)が
    **身頃の色より肌の色に近かった**(351 対 378)。「近い方」で決めると
    スカートが肌になり、服の下端が裾ではなく身頃の下になる。
    """
    from engine.skin_tone import _distance

    bodice = (232.0, 236.0, 248.0)
    skirt = (85.0, 102.0, 170.0)
    skin = (246.0, 217.0, 196.0)
    assert _distance(skirt, skin) < _distance(skirt, bodice)   # 「近い方」なら肌

    reading = _colours(puff_sleeve_illustration())
    assert reading.usable, reading.reason
    # それでも、裾はスカートの裾として読めている。
    assert reading.garment_bottom is not None
    assert abs(reading.garment_bottom - 860) <= 20, reading.garment_bottom


def test_a_pale_bodice_below_the_old_gate_is_still_filled():
    """穴を埋めても1.16倍にしかならない絵でも、埋めること。

    round71は「塗って1.5倍以上に増えたら線画」という1つの条件で、
    線画かどうかと、穴を埋めるかどうかを**両方**決めていた。濃いスカートに
    淡い身頃という配色では増分が小さく、身頃の内側が空洞のまま残る。

    実測(この絵): 前景 333,850px → 穴を埋めて 386,126px (1.16倍)。
    空洞のままだと胸から服の色が拾えず、色の読み取りが丸ごと落ちる。
    """
    import numpy as np

    from engine.segmentation import SimpleSilhouetteSegmenter

    segmenter = SimpleSilhouetteSegmenter()
    image = pale_bodice_illustration()
    raw = np.asarray(segmenter._foreground_mask(image)).astype(bool)
    solid = np.asarray(segmenter._solid_foreground_mask(image)).astype(bool)
    grew = int(solid.sum()) / max(1, int(raw.sum()))
    assert grew < segmenter.OUTLINE_FILL_MIN_GAIN, grew   # 旧条件は通らない増分
    assert grew > 1.05, grew                              # それでも埋まっている

    mask = get_default_segmenter().silhouette_mask(image)
    reading = read_colours(image, mask)
    assert reading.usable, reading.reason
    assert reading.sleeveless


def test_a_framed_illustration_is_not_filled_solid():
    """外周に枠線のある絵で、画面ごと塗りつぶさないこと。

    枠があると、図形として閉じているのは**画像の外周**になる。そこを
    埋めると前景が画面の95.8%になり、シルエットが真っ黒の長方形になる。
    """
    import numpy as np

    from engine.segmentation import SimpleSilhouetteSegmenter

    segmenter = SimpleSilhouetteSegmenter()
    image = framed_illustration()
    solid = np.asarray(segmenter._solid_foreground_mask(image)).astype(bool)
    assert solid.sum() / solid.size < 0.5, solid.sum() / solid.size


def test_a_gold_cuff_is_part_of_the_sleeve_not_bare_skin():
    """紺の袖に付いた金の袖口を、素肌と読まないこと。

    金(255,255,85)は、redmeanで肌まで176・紺まで557——**肌の方が近い**。
    「服と肌のどちらに近いか」で決めると、袖口から先が素肌に見えて、
    袖丈が手首(730行)ではなく袖口の上(640行)で終わる。
    """
    reading = _colours(trimmed_sleeve_illustration())
    assert reading.usable, reading.reason
    assert reading.sleeve_hem_y is not None
    assert abs(reading.sleeve_hem_y - TRIMMED_WRIST_Y) <= 20, reading.sleeve_hem_y


def test_a_thin_skin_coloured_ribbon_does_not_end_the_sleeve():
    """袖に巻いた7pxの肌色リボンで、袖が終わったことにしないこと。"""
    reading = _colours(trimmed_sleeve_illustration())
    assert reading.usable, reading.reason
    assert reading.sleeve_hem_y is not None
    assert reading.sleeve_hem_y > SHOULDER_Y + 260, reading.sleeve_hem_y


def test_a_pointed_hem_is_not_mistaken_for_arms():
    """剣先の裾を腕と取り違えないこと。

    剣先の裾は**396行**にわたって「左 | 中 | 右」の3塊を作る。腕の帯
    (405〜660行、256行)より長いので、「いちばん長い帯」だけでは剣先の方が
    勝ってしまう。腕と剣先を分けるのは長さではなく、**真ん中の塊が
    左右よりはっきり太いか**である——腕のあいだには胴があるが、剣先の
    あいだには剣先しかない。

    実測: この条件を外すと、腕の位置が405行から**905行**(ウエストより
    ずっと下)になり、裾も1220行から1183行へずれる。どちらも
    「読めました」という顔で返る。
    """
    reading = _colours(pointed_hem_gown_illustration())
    assert reading.usable, reading.reason
    assert reading.arm_top is not None and reading.arm_top < 590, reading.arm_top
    assert reading.sleeveless


def test_the_outline_stroke_is_not_mistaken_for_cloth():
    """輪郭線を「服」と数えないこと。

    輪郭線は3〜4pxの濃い線で、肌の色からは遠い。幅を問わずに数えると
    **素肌の腕の輪郭線まで服**になり、袖なしの絵で肩の張り出しが
    104pxではなく156pxと測られて、袖ありと区別できなかった。
    """
    reading = _colours(sleeveless_illustration())
    assert reading.usable, reading.reason
    assert reading.sleeveless, "輪郭線を服と数えると、袖ありに見える"
