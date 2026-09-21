"""round35: たくさんの体型で実際に生成して見つけた、3つの実バグ。

「動かしてみてよりよくして」という依頼で、体型 x パーツ構成を総当たりして
生成し、出来上がった型紙を機械的に検査した。テスト1645本が全部通っている
状態で、次の3つが見つかった。どれも**特定の体型でだけ**起きるので、
標準サイズを見ているだけでは分からない。

1. 生地幅に収まらないスカートが、型紙から黙って消えていた(110通り中70通り)
2. 前後の脇線が14cm食い違い、「縫えません」と誤警告が出ていた
3. (2を直した副作用)袖ぐりの測り方が作る側と検査側で食い違い、
   368通り中288通りで「袖が袖ぐりに合っていません」と誤警告が出た
"""

import pytest

from engine.compatibility import armhole_length, side_seam_length
from engine.measurements import Measurements
from engine.nesting import DEFAULT_FABRIC_WIDTHS_CM
from engine.panel_split import (
    MAX_PANELS, MIN_PANEL_WIDTH_CM, SPLITTABLE_PART_TYPES,
    panels_needed, split_into_panels,
)
from engine.pipeline import PatternForgePipeline, build_garment_spec
from engine.svgpath import bounding_box, segments_to_polyline

MAX_FABRIC_CM = max(DEFAULT_FABRIC_WIDTHS_CM)


def _generate(tmp_path, measurements, **spec_kwargs):
    pipeline = PatternForgePipeline(output_dir=str(tmp_path))
    return pipeline.generate_from_selection(
        build_garment_spec(**spec_kwargs), measurements)


# --- 1) 生地幅に収まらないパーツが消えていた --------------------------------

@pytest.mark.parametrize("hip", [150, 160, 170])
def test_a_huge_circle_skirt_is_split_instead_of_vanishing(tmp_path, hip):
    """大きなサーキュラースカートが、消えずに分割されて出ること。

    【実際に起きていたこと】生地幅(最大150cm)に収まらないパーツは
    `engine/nesting.py`がunplacedにし、SVG/PDFには**描かれない**。
    実測でウエスト60〜150 x ヒップ70〜170を10cm刻みで総当たりした110通りの
    うち**70通り**で、サーキュラースカート(ヒップ150cmで幅155.6cm)が
    型紙から丸ごと消えていた。消え始めるのはヒップ143cmから。
    つまり「スカートの無いワンピースの型紙」が出ていた。
    """
    m = Measurements(84, 68, hip, 160, 54, 37)
    result = _generate(tmp_path, m, neckline="round_neck",
                       sleeve_style=None, skirt_style="circle")
    assert result.nesting.unplaced == [], \
        [p.display_name for p in result.nesting.unplaced]
    skirts = [p for p in result.finalized_parts if p.part_type == "skirt"]
    assert len(skirts) > 2, "前後2枚のまま=分割されていない"
    for part in skirts:
        assert part.width_cm <= MAX_FABRIC_CM, part.width_cm


def test_the_split_is_disclosed(tmp_path):
    """分けたことを、利用者に伝えていること(黙って形を変えない)。"""
    m = Measurements(84, 68, 155, 160, 54, 37)
    result = _generate(tmp_path, m, neckline="round_neck",
                       sleeve_style=None, skirt_style="circle")
    notes = [n for n in result.design_notes if "分けました" in n]
    assert notes, result.design_notes
    assert "縫い合わせる" in notes[0]
    assert result.split_panels.get("skirt", 0) >= 2


def test_the_assembly_gains_a_step_for_joining_the_panels(tmp_path):
    """分けたぶん、縫う順番に「縫い合わせる」工程が増えること。

    増えないと、以降の「スカートの脇を縫う」が何を指すのか分からない。
    """
    m = Measurements(84, 68, 155, 160, 54, 37)
    result = _generate(tmp_path, m, neckline="round_neck",
                       sleeve_style=None, skirt_style="circle")
    titles = [s.title for s in result.assembly_steps()]
    assert "スカートのパネルを縫い合わせる" in titles, titles
    assert titles.index("スカートのパネルを縫い合わせる") < titles.index("スカートの脇を縫う")


def test_a_normal_size_is_not_split(tmp_path):
    """収まるサイズでは分けないこと(不要な縫い目を増やさない)。"""
    m = Measurements(84, 68, 92, 160, 54, 37)
    result = _generate(tmp_path, m, neckline="round_neck",
                       sleeve_style=None, skirt_style="circle")
    skirts = [p for p in result.finalized_parts if p.part_type == "skirt"]
    assert len(skirts) == 2, [p.display_name for p in skirts]
    assert result.split_panels == {}
    assert not any("分けました" in n for n in result.design_notes)


def test_only_parts_where_a_seam_is_acceptable_are_split():
    """身頃・衿・カフスは分割対象にしないこと。

    身頃の中心に勝手に縫い目を入れると、見返し・ファスナー・柄合わせの
    前提が壊れる。帯(衿・カフス・ウエストバンド)は長さが命で、継ぐと
    伸び止めの効きが変わる。
    """
    assert SPLITTABLE_PART_TYPES == {"skirt", "front_pants", "back_pants"}


def test_the_split_keeps_the_area(tmp_path):
    """分けても、面積(=必要な布の量)がほぼ変わらないこと。

    分割で形が痩せていたら、出来上がりが小さくなる。
    """
    shapely = pytest.importorskip("shapely.geometry")

    m = Measurements(84, 68, 155, 160, 54, 37)
    pipeline = PatternForgePipeline(output_dir=str(tmp_path))
    result = pipeline.generate_from_selection(
        build_garment_spec(neckline="round_neck", sleeve_style=None,
                            skirt_style="circle"), m)
    scaled = next(s for s in result.scaled_parts if s.part_type == "skirt")
    whole = shapely.Polygon(segments_to_polyline(scaled.segments)).area
    pieces = split_into_panels(scaled.segments, 2)
    total = sum(shapely.Polygon(segments_to_polyline(p)).area for p in pieces)
    assert total == pytest.approx(whole, rel=0.01)


def test_panels_needed_accounts_for_the_extra_seam_allowance():
    """分けると縫い代が増えることを、枚数の計算に入れていること。

    n枚に分けると新しい縁が 2(n-1) 本できる。そのぶん総幅が増えるので、
    単純に幅÷nで考えると「収まるはず」が収まらない。
    """
    # ちょうど収まる: 150cm幅に対し幅155cm、縫い代1cm -> 2枚で78.5cm
    assert panels_needed(155.0, 150.0, 1.0) == 2
    assert panels_needed(140.0, 150.0, 1.0) == 1
    # ここが本題。幅300cmは、縫い代を無視すれば2枚でちょうど150cmに収まる。
    # だが分割線の左右に1cmずつ足すと1枚151cmになり、生地からはみ出す。
    # 「幅÷枚数」で考えていると、裁てない型紙をそのまま出してしまう。
    assert panels_needed(300.0, 150.0, 0.0) == 2
    assert panels_needed(300.0, 150.0, 1.0) == 3
    assert panels_needed(296.0, 150.0, 1.0) == 2      # 1枚149cm。こちらは収まる

    # 縫い代を厚くすると、同じ幅でも必要枚数が増える
    assert panels_needed(299.0, 150.0, 1.0) == 3      # (299+2)/2 = 150.5 ではみ出す
    assert panels_needed(299.0, 150.0, 3.0) == 3


def test_a_split_that_would_make_a_sliver_is_refused():
    """分けると細すぎる短冊になる場合は分けないこと。"""
    assert panels_needed(20.0, 5.0, 1.0) == 1     # 5cm幅の生地は非現実的
    assert MIN_PANEL_WIDTH_CM > 0 and MAX_PANELS >= 2


# --- 2) 前後の脇線が14cm食い違っていた --------------------------------------

@pytest.mark.parametrize("waist,hip", [(60, 150), (60, 130), (70, 150),
                                        (110, 170), (48, 62), (68, 92)])
def test_the_side_seams_match_front_to_back(tmp_path, waist, hip):
    """どんな体型でも、前後の脇線の長さが一致すること。

    【実際に起きていたこと】胸ぐせダーツが2本入る体型では、前身頃の脇線が
    3つの断片に割れる。上の2つは4.59cmと2.06cmで、round28〜31で足した
    「断片をつなぐ規則」(5cm以上の辺を含むこと/両方2.5cm以上)のどちらも
    満たさず、**上の6.65cmが丸ごと捨てられていた**。

    さらに、脇線を作る側は傾きを上限ぴったりまで開かせるので、厳密な
    比較では**左右の鏡像のうち片方だけが落ちる**(実測: |dx|も上限も
    1.113)。その結果、前身頃の脇線が31.0cm・後ろ71.9cmと**40.9cm**
    食い違い、「そのままでは縫えません」という誤った警告が出ていた。
    実際には縫える型紙だった——測り方が悪かっただけである。
    """
    m = Measurements(84, waist, hip, 160, 54, 37)
    result = _generate(tmp_path, m, neckline="round_neck",
                       sleeve_style=None, skirt_style=None)
    parts = {p.part_type: p for p in result.finalized_parts}
    front = side_seam_length(parts["front_bodice"])
    back = side_seam_length(parts["back_bodice"])
    assert front is not None and back is not None
    assert front == pytest.approx(back, abs=1.5), (front, back)
    assert [w.kind for w in result.compatibility_warnings()] == []


def test_the_detector_accepts_an_edge_exactly_at_the_slope_limit():
    """傾きが上限ちょうどの辺を、左右どちらでも同じように受け付けること。

    脇線を作る側(`hip_widening_start_y`/`waist_nip_limit_cm`)が上限
    ぴったりを作るので、ここが厳密だと鏡像の片方だけが落ちる。
    """
    from engine.compatibility import NEAR_VERTICAL_MAX_DX_RATIO, _is_side_seam_edge

    dy = 10.0
    dx = NEAR_VERTICAL_MAX_DX_RATIO * dy
    # 左右対称の細長い台形。左右の縁がちょうど上限の傾きを持つ。
    points = [(0.0, 0.0), (20.0, 0.0), (20.0 + dx, dy), (-dx, dy), (0.0, 0.0)]
    left = _is_side_seam_edge(points, (0.0, 0.0), (-dx, dy), 0.5, min_run=0.05)
    right = _is_side_seam_edge(points, (20.0, 0.0), (20.0 + dx, dy), 0.5, min_run=0.05)
    assert left == "left" and right == "right", (left, right)


# --- 3) 袖ぐりの測り方が2か所で食い違っていた -------------------------------

@pytest.mark.parametrize("bust,waist,hip", [
    (84, 48, 150), (110, 48, 150), (84, 60, 150), (130, 120, 170), (60, 48, 62),
])
def test_the_sleeve_still_fits_the_armhole(tmp_path, bust, waist, hip):
    """作った袖が、出来上がりの袖ぐりに合っていること。

    【実際に起きていたこと】`armhole_length`は脇の下の高さを渡すかどうかで
    測り方が変わる。袖の型紙を作る側(`_armhole_per_arm_cm`)は渡しておらず、
    出来上がりを検査する側(チェック5)は渡していたため、**同じ袖ぐりを
    違う長さで測っていた**。実測で368通り中288通りで
    「袖が袖ぐりに合っていません」という誤警告が出た。
    """
    m = Measurements(bust, waist, hip, 160, 54, 37)
    result = _generate(tmp_path, m, neckline="round_neck",
                       sleeve_style="straight", skirt_style=None)
    assert [w.kind for w in result.compatibility_warnings()] == [], \
        [w.message[:120] for w in result.compatibility_warnings()]


def test_both_sides_measure_the_armhole_the_same_way(tmp_path):
    """型紙を作る側と検査する側が、同じ袖ぐり長を得ること。"""
    from types import SimpleNamespace

    from engine.pipeline import _armhole_per_arm_cm

    m = Measurements(84, 48, 150, 160, 54, 37)
    result = _generate(tmp_path, m, neckline="round_neck",
                       sleeve_style="straight", skirt_style=None)
    parts = {p.part_type: p for p in result.finalized_parts}
    measured_after = (armhole_length(parts["front_bodice"])
                      + armhole_length(parts["back_bodice"])) / 2.0
    scaled_by_type: dict[str, list] = {}
    for sp in result.scaled_parts:
        scaled_by_type.setdefault(sp.part_type, []).append(sp)
    measured_before = _armhole_per_arm_cm(scaled_by_type)
    assert measured_before == pytest.approx(measured_after, abs=0.2)


# --- 全体: 総当たりでの回帰防止 ----------------------------------------------

@pytest.mark.parametrize("skirt", ["circle", "flare", "tight"])
def test_no_part_ever_vanishes_across_the_size_range(tmp_path, skirt):
    """有効な採寸の範囲で、パーツが型紙から消えないこと。

    round11のテストには「総当たりで確認したところunplacedは発生しない
    (=製品としては到達不能)」と書いてあったが、round9で追加した
    サーキュラースカートによって**それはもう本当ではなくなっていた**。
    到達不能という前提を置かず、実際に総当たりして確かめる。
    """
    pipeline = PatternForgePipeline(output_dir=str(tmp_path))
    spec = build_garment_spec(neckline="round_neck", sleeve_style="straight",
                              skirt_style=skirt)
    for waist in (48, 90, 150):
        for hip in (62, 110, 170):
            if hip < waist - 10:
                continue
            m = Measurements(84, waist, hip, 160, 54, 37)
            result = pipeline.generate_from_selection(spec, m)
            assert result.nesting.unplaced == [], \
                (skirt, waist, hip, [p.display_name for p in result.nesting.unplaced])


# --- 4) 同じ説明が2回並んでいた(ブラウザで見て気付いた) ---------------------

def test_the_split_is_disclosed_once_not_once_per_piece(tmp_path):
    """前後が同時に分かれても、説明は1件にまとまること。

    【実際に見えていたもの】1440pxのブラウザで確認したところ、
    「スカート（サーキュラー） 前は…」「スカート（サーキュラー） 後は…」と、
    **100文字を超える同じ説明が2回**並んでいた。前身頃と後ろ身頃は同じ理由で
    必ず対で分かれるので、2件目は読む側にとって情報量がゼロで、
    他の注意書きを画面の下へ押しやるだけだった。
    """
    m = Measurements(84, 68, 155, 160, 54, 37)
    result = _generate(tmp_path, m, neckline="round_neck",
                       sleeve_style=None, skirt_style="circle")
    notes = [n for n in result.design_notes if "分けました" in n]
    assert len(notes) == 1, notes
    # まとめても「どのパーツが分かれたのか」は消えない
    assert "前" in notes[0] and "後" in notes[0], notes[0]


def test_merge_part_labels_pulls_out_the_common_prefix():
    """共通部分をくくり出し、無い場合は素直に並べること。"""
    from engine.panel_split import merge_part_labels

    assert merge_part_labels(
        ["スカート（サーキュラー） 前", "スカート（サーキュラー） 後"]
    ) == "スカート（サーキュラー） 前・後"
    # 共通部分が無ければ、勝手にくくらない
    assert merge_part_labels(["前パンツ", "後ろパンツ"]) == "前パンツ・後ろパンツ"
    # 片方がもう片方の前置きそのものの場合、くくると意味が変わるので並べる
    assert merge_part_labels(["スカート", "スカート 前"]) == "スカート・スカート 前"
    assert merge_part_labels(["スカート"]) == "スカート"
    assert merge_part_labels([]) == ""
    # 重複は1つに
    assert merge_part_labels(["袖", "袖"]) == "袖"


def test_the_summary_says_which_parts_were_split(tmp_path):
    """分割の有無を、機械が読める形でも出していること。

    【なぜ文だけでは足りないか】`design_notes`の日本語文は**人間に読ませる
    文**であって、画面やAPI利用者が「分割が起きたか」を判定する手がかりには
    ならない(文言を直すたびに壊れる)。実際、`split_panels`を追加した直後は
    `summary()`に含めておらず、画面側から分割の有無が分からなかった。
    """
    m = Measurements(84, 68, 155, 160, 54, 37)
    result = _generate(tmp_path, m, neckline="round_neck",
                       sleeve_style=None, skirt_style="circle")
    summary = result.summary()
    assert summary["split_panels"] == {"skirt": 2}, summary["split_panels"]

    # 分割が起きていないときは空。Noneや欠落ではない(画面側が
    # `data.split_panels || {}` を書かなくて済むように、必ず辞書を返す)。
    plain = _generate(tmp_path, Measurements(84, 68, 92, 160, 54, 37),
                      neckline="round_neck", sleeve_style=None, skirt_style="circle")
    assert plain.summary()["split_panels"] == {}
