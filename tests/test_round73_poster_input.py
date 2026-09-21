"""round73: 公式の宣材ポスターを入れたら「裾の広がりはウエストの599倍」と
書いて型紙を出した。

利用者が手元に持っている絵は、たいてい**切り抜かれていない**。公式サイトの
キャラクター紹介画像、ゲームのスクリーンショット、雑誌の1ページ——人物の
まわりにロゴ・帯・タイトル文字があり、背景には床のグラデーションが敷いて
ある。round72まではその手の画像を1枚も通していなかった。

【実測した状態】602×1200のキャラクター紹介画像1枚:

```
    前景(=服とみなした画素)   画像の 50.3%
    読み取った裾の広がり       ウエスト幅の **599.00倍**
    読み取ったスカート丈       背丈の1.75倍 → 68cm
```

599倍という数字が、そのまま利用者への注記として画面に出ていた。そして
いちばん広いサーキュラースカートの型紙が、何の断りもなく出てきた。

このファイルが見張るのは:

  1. 背景にグラデーションがあると、背景が丸ごと「服」になる
  2. 服として成立しない値が、注記になって型紙に入る
  3. 人物が画像の端で切れている絵から、丈や袖を読む
  4. 理由の分かっている「読めない」を、分からない方の文面で言う
"""

import numpy as np
import pytest

from PIL import Image, ImageDraw

from engine import illustration_fit
from engine.illustration_fit import (
    DesignProportions, measure_proportions, measure_sleeves, runs_off_the_picture,
)
from engine.segmentation import SimpleSilhouetteSegmenter, get_default_segmenter

WIDTH, HEIGHT = 720, 1200
CENTRE = WIDTH // 2
SKIN = (246, 217, 196)
LINE = (43, 36, 48)
HAIR = (74, 59, 82)
COAT = (38, 40, 52)
SHOULDER_Y, WAIST_Y, HEM_Y = 300, 560, 880


def _gradient(draw, top=(252, 252, 252), bottom=(150, 150, 150),
              start=0.45):
    """下へ行くほど暗くなる背景。床の陰影のつもり。

    宣材画像でいちばんよくある背景で、**四隅から1色を取る**やり方では
    まったく追えない。上端252・下端150で、隔たりは102ある。
    """
    for y in range(HEIGHT):
        t = max(0.0, (y / HEIGHT - start) / (1.0 - start))
        draw.line([(0, y), (WIDTH, y)],
                  fill=tuple(int(a + (b - a) * t) for a, b in zip(top, bottom)))


def _person(draw, arm_span=150, head_top=120, hem=HEM_Y):
    """頭・腕・コート・脚。3枚に共通の下地。"""
    draw.ellipse([CENTRE - 61, head_top, CENTRE + 61, head_top + 156],
                 fill=SKIN, outline=LINE, width=3)
    draw.polygon([(CENTRE - 67, head_top + 74), (CENTRE - 74, head_top - 27),
                  (CENTRE + 74, head_top - 27), (CENTRE + 67, head_top + 74),
                  (CENTRE, head_top + 27)], fill=HAIR)
    draw.rectangle([CENTRE - 20, head_top + 140, CENTRE + 20, SHOULDER_Y + 8],
                   fill=SKIN, outline=LINE, width=3)
    for sign in (-1, 1):
        draw.polygon([(CENTRE + sign * 96, SHOULDER_Y),
                      (CENTRE + sign * (96 + arm_span), SHOULDER_Y + 30),
                      (CENTRE + sign * (96 + arm_span), SHOULDER_Y + 74),
                      (CENTRE + sign * 108, SHOULDER_Y + 110)],
                     fill=COAT, outline=LINE, width=4)
    draw.polygon([(CENTRE - 96, SHOULDER_Y), (CENTRE + 96, SHOULDER_Y),
                  (CENTRE + 112, WAIST_Y - 70), (CENTRE + 74, WAIST_Y),
                  (CENTRE + 120, hem), (CENTRE - 120, hem),
                  (CENTRE - 74, WAIST_Y), (CENTRE - 112, WAIST_Y - 70)],
                 fill=COAT, outline=LINE, width=4)
    for x in (CENTRE - 60, CENTRE + 26):
        draw.rounded_rectangle([x, hem - 10, x + 34, HEIGHT - 120], radius=16,
                               fill=SKIN, outline=LINE, width=3)


def gradient_background_illustration() -> Image.Image:
    """床のグラデーションの上に立っている人物。レイアウトは無い。"""
    image = Image.new("RGB", (WIDTH, HEIGHT), (252, 252, 252))
    draw = ImageDraw.Draw(image)
    _gradient(draw)
    _person(draw)
    return image


def poster_illustration() -> Image.Image:
    """宣材ポスターのつもり。グラデーション＋帯＋罫線＋タイトル文字。"""
    image = gradient_background_illustration()
    draw = ImageDraw.Draw(image)
    draw.rectangle([0, 40, WIDTH, 86], fill=(20, 20, 24))          # 上の帯
    draw.rectangle([0, 1010, WIDTH, 1110], fill=(20, 20, 24))      # 下の帯
    draw.rectangle([0, 1150, WIDTH, 1190], fill=(250, 226, 40))    # 黄色い帯
    draw.line([(0, 470), (WIDTH, 470)], fill=(40, 40, 40), width=3)  # 罫線
    for i in range(6):                                              # タイトル文字
        draw.rectangle([24 + i * 112, 1030, 24 + i * 112 + 76, 1092],
                       fill=(250, 250, 250))
    return image


def cut_off_at_the_sides_illustration() -> Image.Image:
    """腕が画像の左右の端まで伸びている絵。袖の先が写っていない。"""
    image = Image.new("RGB", (WIDTH, HEIGHT), (252, 252, 252))
    draw = ImageDraw.Draw(image)
    _person(draw, arm_span=CENTRE - 90)
    return image


def cut_off_at_the_top_illustration() -> Image.Image:
    """頭が画像の上端で切れている絵。"""
    image = Image.new("RGB", (WIDTH, HEIGHT), (252, 252, 252))
    draw = ImageDraw.Draw(image)
    _person(draw, head_top=-40)
    return image


def feet_on_the_bottom_edge_illustration() -> Image.Image:
    """足が画像の下端に接している、ごく普通の全身の構図。

    下端だけに接しているのは切れているのではない。ここまで弾くと、
    全身を目一杯に入れた絵がすべて読めなくなる。
    """
    image = Image.new("RGB", (WIDTH, HEIGHT), (252, 252, 252))
    draw = ImageDraw.Draw(image)
    _person(draw)
    for x in (CENTRE - 60, CENTRE + 26):
        draw.rounded_rectangle([x, HEM_Y - 10, x + 34, HEIGHT - 1], radius=16,
                               fill=SKIN, outline=LINE, width=3)
    return image


def _mask(image):
    return np.asarray(get_default_segmenter().silhouette_mask(image)).astype(bool)


# --- 1. 背景のグラデーションが「服」にならない -------------------------------

def test_a_gradient_background_is_not_read_as_clothing():
    """下へ行くほど暗くなる背景を、前景に取り込まないこと。

    前景は「背景色からの距離」で決まり、背景色は四隅の平均だった。四隅が
    どこも明るい絵では、暗くなった下半分が丸ごと前景になる。実測(この絵):

        四隅1色で判定        前景 80.4%   ← 床が丸ごと入っている
        行ごとに取り直す     前景 20.3%   ← 人物だけ

    正解は計算できる。人物として描いた画素は、背景のグラデーションと
    まったく違う色だからである。
    """
    segmenter = SimpleSilhouetteSegmenter()
    image = gradient_background_illustration()
    mask = np.asarray(segmenter._foreground_mask(image)).astype(bool)
    assert 0.08 < mask.mean() < 0.30, mask.mean()

    # 床の上のほう(人物の左右)は背景のまま。
    assert not mask[HEIGHT - 60, 30], "床が前景に入っています"
    assert not mask[HEIGHT - 60, WIDTH - 30]
    # 人物(コートの中央)は前景。
    assert mask[WAIST_Y - 40, CENTRE]


@pytest.mark.parametrize("noise", [0, 4], ids=["きれいな白", "ノイズ入り"])
def test_a_flat_background_gives_exactly_the_same_mask_as_before(noise):
    """背景が一様な絵では、判定が1画素も変わらないこと。

    round72までに通した絵の出力を動かさないための確認。行ごとに取り直しても、
    背景が一様なら四隅から取ったのと同じ値になる(実測で差は0画素)。
    写真のようにノイズが乗っていても同じであることも見る。
    """
    segmenter = SimpleSilhouetteSegmenter()
    image = feet_on_the_bottom_edge_illustration()   # 背景は真っ白1色
    rgb = np.array(image.convert("RGB")).astype(np.int16)
    if noise:
        rgb = np.clip(rgb + np.random.default_rng(7).normal(0, noise, rgb.shape),
                      0, 255).astype(np.int16)
    corner = segmenter._corner_background(rgb)
    rows = segmenter._row_background(rgb, corner)
    by_corner = np.linalg.norm(rgb - corner, axis=2) > segmenter.COLOR_DISTANCE_THRESHOLD
    by_row = np.linalg.norm(rgb - rows[:, None, :], axis=2) > segmenter.COLOR_DISTANCE_THRESHOLD
    assert int((by_corner != by_row).sum()) == 0


def cape_touching_one_side_illustration() -> Image.Image:
    """マントが画像の右端まで届いている、グラデーション背景の絵。

    右端は400行にわたってマントの色になる。左端はずっと背景なので、
    **左右が一致した行だけ**を背景として採れば正しく読める。
    """
    image = gradient_background_illustration()
    draw = ImageDraw.Draw(image)
    draw.polygon([(CENTRE + 90, SHOULDER_Y + 20), (WIDTH - 1, SHOULDER_Y + 60),
                  (WIDTH - 1, SHOULDER_Y + 430), (CENTRE + 110, SHOULDER_Y + 400)],
                 fill=(60, 54, 70), outline=LINE, width=4)
    return image


def test_a_figure_touching_one_edge_does_not_poison_the_background():
    """人物が片側の端に掛かっていても、背景の推定を壊さないこと。

    その行の右端はマントの色なので、左右を平均すると背景が暗い方へ引かれ、
    **左の余白まで前景**になる。実測(マントの高さの帯、左端から10〜60px):

        左右の一致を見る    その帯が前景になった割合  8.6%
        見ない              その帯が前景になった割合  100%
    """
    segmenter = SimpleSilhouetteSegmenter()
    image = cape_touching_one_side_illustration()
    mask = np.asarray(segmenter._foreground_mask(image)).astype(bool)
    band = mask[SHOULDER_Y + 60:SHOULDER_Y + 420, 10:60]
    assert band.mean() < 0.30, band.mean()


# --- 2. 服として成立しない値を型紙にしない -----------------------------------

def _figure_mask(waist_half: int, hem_half: int) -> "np.ndarray":
    """肩からウエストへ細り、ウエストから裾へ広がるだけのマスク。

    絵ではなくマスクを直に組み立てるのは、**どんな比になるかを座標から
    計算できる**ようにするため。ここで見たいのは読み取りの精度ではなく、
    あり得ない値が来たときの振る舞いである。
    """
    mask = np.zeros((700, 400), dtype=bool)
    for y in range(60, 250):
        t = (y - 60) / 190.0
        half = int(62 - (62 - waist_half) * t)
        mask[y, 200 - half:200 + half] = True
    for y in range(250, 660):
        t = (y - 250) / 410.0
        half = int(waist_half + (hem_half - waist_half) * t)
        mask[y, max(0, 200 - half):min(400, 200 + half)] = True
    return mask


def test_an_impossible_flare_is_not_turned_into_a_pattern():
    """ウエストの何十倍にも広がる裾を、読み取り結果として採らないこと。

    実測(公式の宣材ポスター): ウエスト幅1pxに対して裾が画像の幅いっぱいに
    なり、広がりが**599.00倍**。この数がそのまま
    「イラストから読み取った裾の広がり: ウエスト幅の599.00倍」という
    注記になって、いちばん広いサーキュラースカートの型紙が出ていた。
    """
    reading = measure_proportions(_figure_mask(waist_half=3, hem_half=196))
    assert reading.hem_flare is None, reading.hem_flare
    assert reading.implausible_reason, "黙って捨ててはいけない"
    assert "裾の広がり" in reading.implausible_reason


def test_the_length_from_the_same_waist_is_dropped_too():
    """広がりがあり得ないなら、同じくびれから出た丈も捨てること。

    丈と広がりは1本のくびれから出ている。片方だけ捨てると、もっともらしい
    方だけが注記になって型紙に入る(実測: 広がり414倍を捨てたあと、同じ
    くびれから出た丈2.80倍＝109cmがそのまま残っていた)。
    """
    reading = measure_proportions(_figure_mask(waist_half=3, hem_half=196))
    assert reading.skirt_ratio is None, reading.skirt_ratio


def test_the_implausible_value_is_named_in_the_note():
    """どの値がおかしかったのかを、利用者に見せること。"""
    notes = "\n".join(measure_proportions(
        _figure_mask(waist_half=3, hem_half=196)).notes())
    assert "読み取れませんでした" in notes
    assert "倍" in notes, notes


def test_a_normal_flare_is_still_accepted():
    """まともな広がりまで巻き添えにしていないこと(空振りの確認)。"""
    reading = measure_proportions(_figure_mask(waist_half=40, hem_half=120))
    assert reading.hem_flare is not None
    assert reading.hem_flare < illustration_fit.HEM_FLARE_MAX, reading.hem_flare
    assert reading.skirt_ratio is not None
    assert not reading.implausible_reason, reading.implausible_reason


# --- 3. 端で切れている絵から読まない -----------------------------------------

def test_a_figure_running_off_both_sides_is_not_measured():
    """腕が左右の端まで伸びている絵から、丈も袖も読まないこと。

    切れた先に何があるかは写っていないのに、シルエットの上では**そこで
    終わっている**ようにしか見えない。袖の先が画面の外にあるのに、
    画面の端が袖の裾として読まれる。
    """
    mask = _mask(cut_off_at_the_sides_illustration())
    assert runs_off_the_picture(mask), "端で切れていると気づいていません"

    reading = measure_proportions(mask)
    assert reading.skirt_ratio is None
    assert reading.hem_flare is None
    assert "左右の端" in reading.implausible_reason

    # 袖もこの絵からは読めない(色でも段差でも読めないため)。
    assert measure_sleeves(mask, 158.0).length_cm is None


def test_a_head_cut_off_at_the_top_is_not_measured():
    """頭が上端で切れている絵も読まないこと。

    肩の位置は首から決まる。首から上が写っていないと、肩をどこに取っても
    丈比が変わる。
    """
    mask = _mask(cut_off_at_the_top_illustration())
    assert "上端" in runs_off_the_picture(mask)
    assert measure_proportions(mask).skirt_ratio is None


def test_feet_on_the_bottom_edge_are_still_readable():
    """足が下端に接しているだけの絵は、これまでどおり読むこと。

    全身を目一杯に入れた構図はごく普通で、ここまで弾いたら何も読めない。
    """
    mask = _mask(feet_on_the_bottom_edge_illustration())
    assert mask[-1].any(), "この絵は下端に接しているはずです"
    assert not runs_off_the_picture(mask)
    assert measure_proportions(mask).skirt_ratio is not None


def test_a_poster_with_logos_and_bars_says_what_is_wrong():
    """ロゴ・帯・タイトル文字ごと測って、黙って型紙にしないこと。"""
    reading = measure_proportions(_mask(poster_illustration()))
    assert reading.skirt_ratio is None
    assert reading.hem_flare is None
    notes = "\n".join(reading.notes())
    assert "切り抜" in notes or "余白" in notes, notes


# --- 4. 読めない理由は1回だけ、具体的な方を言う -------------------------------

def test_the_specific_reason_replaces_the_vague_one():
    """理由が分かっているときに、分からない方の文面を重ねて出さないこと。

    「読み取れませんでした」が2行続くと、具体的な方が埋もれる。
    """
    notes = DesignProportions(implausible_reason="人物が画像の左右の端で切れています").notes()
    vague = [n for n in notes if "シルエットが小さすぎる" in n]
    assert not vague, notes
    assert any("左右の端" in n for n in notes), notes


@pytest.mark.parametrize("maker", [
    gradient_background_illustration,
    feet_on_the_bottom_edge_illustration,
], ids=["グラデーション背景", "足が下端"])
def test_a_readable_illustration_does_not_get_the_warning(maker):
    """読める絵に、この注記を出さないこと(空振りしていないか)。"""
    reading = measure_proportions(_mask(maker()))
    assert not reading.implausible_reason, reading.implausible_reason
