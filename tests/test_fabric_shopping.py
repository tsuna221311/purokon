"""round38: 「何を、どれだけ買えばよいか」を出す(engine/fabric.py)。

round37まで画面には「幅150cm の生地を 2.6m」とだけ出ていた。これは
**エンジンが選んだ1つの幅**の結果で、他の幅なら何m要るかは内部で計算して
いるのに捨てていた。接着芯も「接着芯あり」と書くだけで量は出さず、
地直しの縮み分は「その分を足して購入してください」と丸投げしていた。

このテストが見張っているのは、出す数字が**実際に計算した値**であること、
出せない数字(値段・在庫)を出さないこと、素材の提案に**必ず出典が付く**こと。
"""

import pytest

from engine.fabric import (COTTON_LINEN_SHRINK_MAX_PERCENT,
                            COTTON_LINEN_SHRINK_MIN_PERCENT,
                            INTERFACING_WIDTH_CM, build_shopping_list,
                            buy_length_with_shrink, fabric_suggestions,
                            interfacing_length_cm, layout_row_count,
                            pattern_repeat_extra_cm, round_up_to_buy,
                            yardage_options)
from engine.measurements import Measurements
from engine.nesting import nest_parts
from engine.pipeline import PatternForgePipeline, build_garment_spec

STANDARD = Measurements(84, 68, 92, 160, 54, 37)


@pytest.fixture(scope="module")
def parts(tmp_path_factory):
    pipeline = PatternForgePipeline(
        output_dir=str(tmp_path_factory.mktemp("fabric")))
    spec = build_garment_spec(neckline="round_neck", sleeve_style="puff",
                              skirt_style="circle", include_collar=True,
                              collar_style="shirt_collar")
    return pipeline.generate_from_selection(spec, STANDARD).finalized_parts


# --- 買う長さの丸め -----------------------------------------------------------

def test_lengths_are_rounded_up_to_how_fabric_is_sold():
    """切り売りの単位へ**切り上げ**ること(切り捨てると足りない)。"""
    assert round_up_to_buy(180.6) == 190
    assert round_up_to_buy(180.0) == 180      # ちょうどなら足さない
    assert round_up_to_buy(180.0001) == 190
    assert round_up_to_buy(0) == 0
    assert round_up_to_buy(-5) == 0


def test_shrinkage_divides_rather_than_adds():
    """縮む分は「足す」のではなく「割る」こと。

    【よくある間違い】「3%縮むから3%足す」は正しくない。買った長さLは
    地直し後に L×(1−p) になるので、必要量Nを残すには N÷(1−p) 要る。
    pが大きいほど、素朴な (1+p) 倍との差が開く。
    """
    # 20%縮む生地で100cm残したい: 100/0.8 = 125 -> 130cm
    # 素朴に20%足すと 120 -> 120cm で、地直し後は96cmしか残らない
    assert buy_length_with_shrink(100, 20) == 130
    assert round_up_to_buy(100 * 1.20) == 120
    naive_left = 120 * 0.8
    assert naive_left < 100, "素朴な足し算では足りないことの確認"
    correct_left = 130 * 0.8
    assert correct_left >= 100

    assert buy_length_with_shrink(100, 0) == 100
    with pytest.raises(ValueError):
        buy_length_with_shrink(100, 100)


# --- 生地幅ごとの必要量 -------------------------------------------------------

def test_every_width_is_measured_not_converted(parts):
    """幅ごとに**実際に並べ直して**測っていること。

    幅と必要丈は比例しない(パーツが横に2枚並ぶかどうかで段が変わる)ので、
    1つの幅から換算した値では合わない。ここでは、各幅の必要丈が
    「その幅で実際にネスティングした結果」と一致することを確かめる。
    """
    options = yardage_options(parts)
    assert len(options) == 3
    assert [o.width_cm for o in options] == [110.0, 140.0, 150.0]

    for option in options:
        actual = nest_parts(parts, fabric_width_cm=option.width_cm,
                             allow_rotation=False)
        assert option.used_length_cm == pytest.approx(actual.used_length_cm)
        assert option.buy_length_cm >= option.used_length_cm

    # 比例していないことの確認(比例するなら幅を1.36倍にすれば丈は1/1.36)
    narrow = next(o for o in options if o.width_cm == 110.0)
    wide = next(o for o in options if o.width_cm == 150.0)
    proportional = narrow.used_length_cm * 110.0 / 150.0
    assert abs(wide.used_length_cm - proportional) > 1.0, (
        "偶然ぴったり比例した。テストの前提を見直すこと")


def test_the_recommended_width_is_the_one_you_buy_least_of(parts):
    """おすすめは「買う長さがいちばん短い幅」であること。

    布ロス率がいちばん低い幅ではない——買い物メモなので、利用者が払うのは
    長さであって、ロス率ではない。実際、この構成では布ロス率が最小の幅と
    買う長さが最小の幅は一致しない。
    """
    memo = build_shopping_list(parts)
    options = {o.width_cm: o for o in memo.widths}
    recommended = options[memo.recommended_width_cm]
    assert recommended.buy_length_cm == min(o.buy_length_cm for o in memo.widths)


def test_a_width_that_cannot_hold_the_parts_shows_no_length():
    """収まらない幅に長さを出さないこと。

    出すと「その長さを買えば作れる」と読めるが、実際にはその幅では作れない。
    """
    pipeline = PatternForgePipeline(output_dir="/tmp")
    spec = build_garment_spec(neckline="round_neck", sleeve_style=None,
                              skirt_style="circle")
    big = pipeline.generate_from_selection(
        spec, Measurements(84, 68, 150, 160, 54, 37)).finalized_parts
    options = yardage_options(big, widths=(50.0, 110.0, 150.0))
    too_narrow = next(o for o in options if o.width_cm == 50.0)
    assert not too_narrow.all_parts_fit


# --- 接着芯 -------------------------------------------------------------------

def test_interfacing_is_measured_by_laying_the_pieces_out(parts):
    """接着芯の量を、面積割りではなく**並べて**測っていること。

    面積÷幅では、細長いパーツが並ばない事情(衿やウエストバンドは長い)を
    取りこぼす。
    """
    length = interfacing_length_cm(parts)
    assert length > 0, "衿を含む構成なので接着芯が要るはず"
    assert length % 10 == 0, "切り売り単位に丸めること"


def test_no_interfacing_no_number(tmp_path):
    """接着芯が要らない構成では0を返すこと(適当な値を出さない)。"""
    pipeline = PatternForgePipeline(output_dir=str(tmp_path))
    plain = pipeline.generate_from_selection(
        build_garment_spec(neckline="round_neck", sleeve_style=None,
                            skirt_style=None), STANDARD).finalized_parts
    assert interfacing_length_cm(plain) == 0


# --- 柄合わせ -----------------------------------------------------------------

def test_the_repeat_allowance_counts_rows_not_pieces(parts):
    """柄合わせの上乗せを、パーツの枚数ではなく**段の数**で数えること。

    横に並んだパーツは同じ縦の帯を占めるので、その帯をまとめてずらせば
    帯の中のパーツはすべて収まる。枚数で数えると、同じ段のぶんを何重にも
    数えてしまい、必要量を大きく見積もりすぎる。
    """
    result = nest_parts(parts, fabric_width_cm=150.0)
    rows = layout_row_count(result)
    assert 1 <= rows <= len(parts)
    assert rows < len(parts), "この構成では横に並ぶ段があるはず"

    by_rows = pattern_repeat_extra_cm(rows, 12)
    by_pieces = pattern_repeat_extra_cm(len(parts), 12)
    assert by_rows < by_pieces


def test_the_repeat_allowance_lands_near_the_published_rule_of_thumb(parts):
    """上乗せ量が、手芸店の目安(2〜3割)からかけ離れないこと。

    クラフトハートトーカイは「柄が大きい場合や柄合わせが必要な場合は、
    通常より2〜3割(柄の一送り分)多く用意する」としている。
    https://www.crafthearttokai.jp/handmade_info/faq_cloth5/

    こちらは幾何から出す上限なので一致する必要は無いが、**桁が違えば
    どちらかが間違っている**。突き合わせておく。
    """
    memo = build_shopping_list(parts, pattern_repeat_cm=12)
    need = next(o for o in memo.widths
                 if o.width_cm == memo.recommended_width_cm).used_length_cm
    ratio = memo.pattern_repeat_extra_cm / need
    assert 0.0 < ratio < 0.6, f"上乗せが必要量の{ratio:.0%}。目安と桁が違う"


def test_no_repeat_no_allowance(parts):
    """柄合わせをしないなら、上乗せを出さないこと。"""
    memo = build_shopping_list(parts)
    assert memo.pattern_repeat_extra_cm == 0
    assert pattern_repeat_extra_cm(3, 0) == 0
    assert pattern_repeat_extra_cm(0, 12) == 0


# --- 素材の提案 ---------------------------------------------------------------

def test_every_suggestion_carries_a_source(parts):
    """素材の提案には、必ず出典が付いていること。

    どこから来た助言なのかが分からないと、利用者は自分で確かめようがない。
    このエンジンは生地の専門家ではないので、**誰がそう言っているか**を
    示せない助言は出してはいけない。
    """
    suggestions, _notes = fabric_suggestions(parts)
    assert suggestions, "この構成なら提案が出るはず"
    for item in suggestions:
        assert item.source_name, item
        assert item.source_url.startswith("https://"), item
        assert item.text.strip()


def test_shapes_with_no_source_get_no_advice(tmp_path):
    """資料に記述が無い形については、何も言わないこと。

    似た形の記述から推測すると、根拠のない助言が型紙に載る。
    分からないことは分からないと言い、黙って埋めない。
    """
    pipeline = PatternForgePipeline(output_dir=str(tmp_path))
    mermaid = pipeline.generate_from_selection(
        build_garment_spec(neckline="round_neck", sleeve_style=None,
                            skirt_style="mermaid"), STANDARD).finalized_parts
    suggestions, notes = fabric_suggestions(mermaid)
    skirt_advice = [s for s in suggestions if "スカート" in s.part_label]
    assert not skirt_advice, skirt_advice
    assert notes, "記述が見つからなかったことを伝えるべき"
    assert "見つかりませんでした" in notes[0]


# --- 一方方向の生地 -----------------------------------------------------------

def test_one_way_fabric_never_flips_a_piece(parts):
    """一方方向の生地では、180度反転を1枚も使わないこと。

    【実際に起きていたこと】圧縮パスは「180度回転は常に布目安全」という
    理由で、布目安全モード(allow_rotation=False)でも180度反転を使っていた。
    布目という意味ではその通りだが、起毛・別珍・コーデュロイは毛の向きで
    色と艶が変わり、片方向プリントは絵柄が逆さまになる。
    実測では、布目安全モードでも前身頃と右袖の2枚が反転して配置されていた
    ——その生地で作ると、前身頃と右袖だけ色の違う服ができた。

    【round38での既定の変更】反転を切ったときの損を171通りで実測したところ、
    生地が増えたのは18通りだけ、最大+0.60cm、平均+0.032cmだった。
    78%の型紙で使っておきながら節約は0.03cm——それと引き換えに起毛の生地で
    「一部のパーツだけ色の違う服」ができていた。そこで反転は
    `allow_rotation`(非方向性の生地)のときだけに限り、**既定では反転しない**
    ようにした。画面が既定を「布目安全モード」と呼んでいるので、
    文言の方を実態に合わせるより、実態を文言に合わせる方が筋が通る。
    """
    # 非方向性の生地(回転あり)なら反転が起きる。ここが起きないなら、
    # このテストは何も守っていない。
    directional = nest_parts(parts, fabric_width_cm=150.0, allow_rotation=True)
    assert any(p.flipped for p in directional.placed), (
        "前提: 非方向性モードでは反転が起きていること")

    # 既定(布目安全モード)は、もう反転しない
    default = nest_parts(parts, fabric_width_cm=150.0, allow_rotation=False)
    assert not any(p.flipped for p in default.placed)

    # 一方方向を明示すれば、非方向性モードでも反転しない
    one_way = nest_parts(parts, fabric_width_cm=150.0, allow_rotation=True,
                          one_way_fabric=True)
    assert not any(p.flipped for p in one_way.placed)
    # 全パーツが置けていること(向きを縛って配置が壊れていない)
    assert len(one_way.placed) == len(directional.placed)
    assert not one_way.unplaced


def test_one_way_fabric_is_disclosed(parts):
    """一方方向として配置したことを、黙らずに伝えること。"""
    memo = build_shopping_list(parts, one_way_fabric=True)
    assert any("一方方向" in note for note in memo.notes), memo.notes


# --- 出さないもの -------------------------------------------------------------

def test_the_memo_does_not_invent_prices_or_stock(parts):
    """値段や在庫を出さないこと。持っていない情報だから。"""
    memo = build_shopping_list(parts, pattern_repeat_cm=12)
    blob = repr(memo.as_dict())
    for forbidden in ("円", "価格", "値段", "在庫", "税込"):
        assert forbidden not in blob, forbidden
