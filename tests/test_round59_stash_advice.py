"""round59: 「足りません」と言うとき、手元にある答えを言っていなかった。

手芸店にスマホで立っている人のつもりで、幅110cm×150cmの手持ちを入れて
生成した。画面には、こういう2つの箱が縦に並んで出た:

    手持ちの生地（幅110cm × 150cm）では足りません
      裁つのに248.8cm必要で、98.8cm足りません。
      ・99cm足りません。丈を詰める・回転を許すといった範囲では
        収まらなかったので、生地を足すか、パーツの構成を変えてください。

    用意する生地
      幅140cm の生地を 1.9m
      型紙が実際に使うのは 181.6cm で …

**同じ画面で248.8cmと181.6cmが食い違っている。** 理由は測った生地幅が
違うこと(手持ちは110cm、推奨は140cm)だけなのに、どちらの数字にも幅が
書いていないので、読むと矛盾する。

しかも買い物メモは**同じ型紙を幅ごとに測ってある**:

    幅110cm … 248.8cm 要る（買うのは250cm）
    幅140cm … 181.6cm 要る（買うのは190cm）

店に立っている人にとっていちばん役に立つ答え——「幅140cmの生地なら
190cmで足ります」——を、**既に測ってあるのに言っていなかった**。
逃げ道として探していたのは「回転」と「丈を詰める」の2つだけで、
どちらも駄目なら「生地を足すか、パーツの構成を変えてください」だった。

さらに「98.8cm足りません」は、裁断台で頼めない数字である
(生地は10cm単位でしか切ってもらえない)。同じ画面に98.8cmと99cmという
2通りの丸めが並んでもいた。
"""

import pytest

import app as app_module
from engine.fabric import BUY_ROUND_UP_CM, round_up_to_buy, yardage_options
from engine.measurements import Measurements
from engine.nesting import DEFAULT_FABRIC_WIDTHS_CM
from engine.pipeline import PatternForgePipeline, build_garment_spec
from engine.stash import evaluate_stash


#: 手芸店の場面そのもの。バスト88のフレアスカート、手持ちは幅110cm×150cm。
MEAS = Measurements(bust=88, waist=70, hip=94, height=162,
                    sleeve_length=55, shoulder_width=39)
FORM = {"bust": "88", "waist": "70", "hip": "94", "height": "162",
        "sleeve_length": "55", "shoulder_width": "39", "mode": "manual",
        "neckline": "round_neck", "sleeve_style": "straight",
        "skirt_style": "flare", "custom_panels_json": "[]"}


@pytest.fixture(scope="module")
def pipeline(tmp_path_factory):
    return PatternForgePipeline(output_dir=str(tmp_path_factory.mktemp("r59")))


@pytest.fixture(scope="module")
def spec():
    return build_garment_spec(neckline="round_neck", sleeve_style="straight",
                              skirt_style="flare")


@pytest.fixture(scope="module")
def short_verdict(pipeline, spec):
    """手持ちでは足りない場合の判定(この場面のほとんどの検査で使う)。"""
    result = pipeline.generate_from_selection(spec, MEAS, skip_export=True)
    return pipeline.evaluate_stash_for(result, spec, MEAS,
                                        have_width_cm=110, have_length_cm=150)


# ---------------------------------------------------------------------------
# 1. 幅を替えれば足りることを、実測して言う
# ---------------------------------------------------------------------------

def test_a_wider_bolt_is_offered_when_it_needs_less(short_verdict):
    assert not short_verdict.fits
    assert short_verdict.wider_option is not None, \
        "幅の広い生地なら足りるのに、それを言っていません"
    width, buy = short_verdict.wider_option
    assert width > short_verdict.have_width_cm
    kinds = [s.kind for s in short_verdict.suggestions]
    assert "wider_fabric" in kinds, kinds


def test_the_wider_bolt_amount_matches_the_shopping_list(pipeline, spec):
    """提案する買う量が、すぐ下の「用意する生地」と同じ値であること。

    ここが食い違うと、画面の上でまた2つの数字が争うことになる。
    """
    result = pipeline.generate_from_selection(spec, MEAS, skip_export=True)
    verdict = pipeline.evaluate_stash_for(result, spec, MEAS,
                                           have_width_cm=110, have_length_cm=150)
    width, buy = verdict.wider_option
    options = {o.width_cm: o.buy_length_cm
               for o in yardage_options(result.finalized_parts)}
    assert options[width] == buy, \
        f"買い物メモは{options[width]}cm、手持ちの提案は{buy}cm"


def test_the_wider_bolt_is_measured_not_estimated(pipeline, spec):
    """提案の値が、その幅で実際に並べ直した結果であること。

    「幅が1.27倍だから長さは1/1.27」のような比例計算だと、パーツが
    並び替わることを織り込めない。実際に測った値と一致するかで見る。
    """
    result = pipeline.generate_from_selection(spec, MEAS, skip_export=True)
    verdict = pipeline.evaluate_stash_for(result, spec, MEAS,
                                           have_width_cm=110, have_length_cm=150)
    width, buy = verdict.wider_option
    measured = pipeline.generate_from_selection(
        spec, MEAS, skip_export=True, fabric_width_candidates=(width,))
    assert buy == round_up_to_buy(measured.nesting.used_length_cm)


def test_a_wider_bolt_that_does_not_help_is_not_offered(pipeline, spec):
    """買う量が10cm単位で1つも減らないなら、出さないこと。

    「幅を広げれば必ず得」ではない。減らないのに勧めると、意味の無い
    買い直しをさせることになる。
    """
    result = pipeline.generate_from_selection(spec, MEAS, skip_export=True)
    # いちばん広い幅を手持ちにすれば、それより広い候補はもう無い。
    widest = max(DEFAULT_FABRIC_WIDTHS_CM)
    verdict = pipeline.evaluate_stash_for(result, spec, MEAS,
                                           have_width_cm=widest, have_length_cm=50)
    assert verdict.wider_option is None
    assert "wider_fabric" not in [s.kind for s in verdict.suggestions]


def test_nothing_is_offered_when_no_other_widths_are_given(pipeline, spec):
    """呼び出し側が買える幅を渡さなければ、この提案は出さないこと。

    どの幅が買えるのかは呼び出し側しか知らない。勝手に決めない。
    """
    result = pipeline.generate_from_selection(spec, MEAS, skip_export=True)

    def _build(**kwargs):
        return pipeline.generate_from_selection(spec, MEAS, **kwargs)

    verdict = evaluate_stash(_build, have_width_cm=110, have_length_cm=150)
    assert verdict.wider_option is None


def test_the_wider_bolt_is_offered_last(short_verdict):
    """手持ちを使い切る逃げ道がある場合は、そちらを先に置くこと。

    買わずに済む道の方が良い。買う話は最後。
    """
    kinds = [s.kind for s in short_verdict.suggestions]
    if len(kinds) > 1:
        assert kinds[-1] == "wider_fabric", kinds


# ---------------------------------------------------------------------------
# 2. 店で言える量にする
# ---------------------------------------------------------------------------

def test_the_shortfall_is_rounded_up_to_a_buyable_amount(short_verdict):
    assert short_verdict.buy_more_cm % BUY_ROUND_UP_CM == 0, \
        f"{short_verdict.buy_more_cm}cmは10cm単位ではありません"
    assert short_verdict.buy_more_cm >= short_verdict.shortfall_cm
    assert short_verdict.buy_more_cm - short_verdict.shortfall_cm < BUY_ROUND_UP_CM


def test_the_same_rounding_is_used_everywhere(short_verdict):
    """買う量の丸め方が、買い物メモと同じ1か所から出ていること。

    round58まで、手持ちの注記は`{:.0f}`で四捨五入していたので、
    同じ不足量が画面の上で98.8cmと99cmの2通りに見えていた。
    """
    assert short_verdict.buy_more_cm == round_up_to_buy(short_verdict.shortfall_cm)
    joined = " ".join(short_verdict.notes
                      + [s.detail for s in short_verdict.suggestions])
    assert f"{short_verdict.shortfall_cm:.0f}cm足りません" not in joined, \
        f"切り上げていない不足量が残っています: {joined}"


@pytest.mark.parametrize("shortfall, expected", [
    (0.1, 10), (9.9, 10), (10.0, 10), (10.1, 20), (98.8, 100), (100.0, 100),
])
def test_the_buy_amount_never_falls_short(shortfall, expected):
    assert round_up_to_buy(shortfall) == expected


# ---------------------------------------------------------------------------
# 3. どの幅で測ったかを言う（画面の上で数字が争わないように）
# ---------------------------------------------------------------------------

def test_the_note_says_which_width_it_measured(pipeline, spec):
    """逃げ道が1つも無いときの注記に、幅と買う量が入っていること。"""
    result = pipeline.generate_from_selection(spec, MEAS, skip_export=True)

    def _build(**kwargs):
        return pipeline.generate_from_selection(spec, MEAS, **kwargs)

    # 他の幅を渡さず、丈も渡さない＝逃げ道が1つも作れない状態。
    verdict = evaluate_stash(_build, have_width_cm=110, have_length_cm=150)
    assert not verdict.suggestions
    note = " ".join(verdict.notes)
    assert "幅110cmで裁つと" in note, note
    assert f"あと{verdict.buy_more_cm}cm足りません" in note, note


def test_the_same_numbers_are_not_repeated_three_times(short_verdict):
    """買う道が見つかったときに、同じ数字を注記でも繰り返さないこと。

    【自分で作った散らかり】注記に「あと100cm足りません（幅110cmで裁つと
    248.8cm）」を必ず入れる作りにしたところ、見出し・説明文・提案に
    同じ数字が既に出ているので、スマホの画面が同じ話で埋まった
    (実機幅390pxで、この箱だけで画面の6割を占めた)。
    注記でしか言えないのは「手持ちに収める道は無かった」ことだけである。
    """
    assert short_verdict.suggestions
    note = " ".join(short_verdict.notes)
    assert "収まりませんでした" in note, note
    assert str(short_verdict.buy_more_cm) not in note, \
        f"提案に出ている数字を注記でも繰り返しています: {note}"
    assert "248" not in note, note


def test_the_screen_puts_the_reason_before_the_options():
    """画面で、注記(事情)を逃げ道(選べる道)より先に出すこと。

    逆だと、提案を読んだあとに「収まりませんでした」が来て、
    いま読んだ提案が否定されたように見える。
    """
    with open("web/static/app.js", encoding="utf-8") as handle:
        source = handle.read()
    body = source.split("function renderStashVerdict(")[1].split("\n}\n")[0]
    notes_at = body.index("for (const note of verdict.notes")
    suggestions_at = body.index("for (const suggestion of verdict.suggestions")
    assert notes_at < suggestions_at, "逃げ道が注記より先に出ています"


def test_the_screen_says_which_width_each_number_is_for():
    """画面の文言に、必ず幅が入っていること。

    すぐ下の「用意する生地」の箱は推奨幅で測った別の数字を出す。
    幅を書かないと、248.8cmと181.6cmが矛盾して見える。
    """
    with open("web/static/app.js", encoding="utf-8") as handle:
        source = handle.read()
    body = source.split("function renderStashVerdict(")[1].split("\n}\n")[0]
    # 足りる側・足りない側、どちらの文にも幅が入っていること。
    assert body.count("幅${verdict.have_width_cm}cmで裁つと") >= 2, body[:400]
    # 不足は買える量で出す。
    assert "verdict.buy_more_cm" in body
    assert "${verdict.shortfall_cm}cm足りません" not in body


def test_the_screen_uses_buyable_amounts_everywhere():
    """生地ごとの行と、サイズ展開の行でも、買える量で出していること。"""
    with open("web/static/app.js", encoding="utf-8") as handle:
        source = handle.read()
    assert "item.buy_more_cm" in source, "生地ごとの行が切り上げていません"
    assert "stash.buy_more_cm" in source, "サイズ展開の行が切り上げていません"
    assert "${item.shortfall_cm}cm足りません" not in source
    assert "${v.shortfall_cm}cm足りません" not in source


# ---------------------------------------------------------------------------
# 4. 画面(HTTP)から見たときの姿
# ---------------------------------------------------------------------------

def test_the_advice_reaches_the_screen(client):
    data = dict(FORM, stash_width_cm="110", stash_length_cm="150")
    body = client.post("/api/generate", data=data).get_json()
    assert body["ok"], body.get("error")
    verdict = body["stash_verdict"]
    assert verdict["fits"] is False
    assert verdict["buy_more_cm"] == 100
    assert verdict["wider_option"] == [140.0, 190]
    labels = [s["label"] for s in verdict["suggestions"]]
    assert any("幅140cmの生地に替えるなら190cmで足ります" == label
               for label in labels), labels


def test_the_two_numbers_on_screen_now_agree(client):
    """手持ちの提案と「用意する生地」が、同じ幅について同じ量を言うこと。

    これがこのラウンドの発端である。画面には
    「248.8cm必要」と「幅140cmを1.9m」が並んで出ていた。
    """
    data = dict(FORM, stash_width_cm="110", stash_length_cm="150")
    body = client.post("/api/generate", data=data).get_json()
    width, buy = body["stash_verdict"]["wider_option"]
    shopping = body["shopping_list"]
    assert shopping["recommended_width_cm"] == width
    chosen = [o for o in shopping["widths"] if o["width_cm"] == width]
    assert chosen and chosen[0]["buy_length_cm"] == buy, (chosen, buy)


def test_a_fitting_stash_is_unchanged_except_for_the_width(client):
    """足りる場合の判定は、これまでと同じ中身であること。"""
    data = dict(FORM, stash_width_cm="150", stash_length_cm="400")
    body = client.post("/api/generate", data=data).get_json()
    verdict = body["stash_verdict"]
    assert verdict["fits"] is True
    assert verdict["leftover_cm"] > 0
    assert verdict["buy_more_cm"] == 0
    assert verdict["wider_option"] is None
    assert verdict["suggestions"] == []


def test_the_two_amounts_are_compared_by_length_not_by_price(short_verdict):
    """買い足す量と、幅を替えたときの量を**並べて**言うこと。

    「幅140cmなら190cm」とだけ言うと、手持ちを捨てて買い直す話に読める。
    この場面では、手持ちに100cm足す方が新しく買う長さは短い。
    どちらが安いかは生地によるので言わない——言えるのは長さだけである。
    """
    wider = [s for s in short_verdict.suggestions if s.kind == "wider_fabric"]
    assert wider, "幅の提案が出ていません"
    detail = wider[0].detail
    assert f"{short_verdict.buy_more_cm}cm" in detail
    assert f"{short_verdict.wider_option[1]}cm" in detail
    assert "新しく買う長さは、手持ちに足す方が短く済みます" in detail, detail
    assert "安い" not in detail, "値段の話をしています"


def test_topping_up_is_flagged_as_needing_the_same_fabric(short_verdict):
    """手持ちに足す道には、同じ生地が要るという条件を書くこと。"""
    wider = [s for s in short_verdict.suggestions if s.kind == "wider_fabric"][0]
    assert "同じ生地が、まだ手に入る場合に限ります" in wider.detail


def test_equal_amounts_are_not_called_shorter(pipeline, spec):
    """買う長さが同じときに「短く済みます」と書かないこと。

    【自分で踏んだ間違い】比較を「手持ちに足す方が短い」か「そうでない」
    の2つに分けていたので、**どちらも190cmのとき**に
    「幅140cmに替える方が短く済みます（190cm と 190cm）」と書いていた。
    同じ数字を並べて「短い」と言っていたことになる
    (round39の既存テストが捕まえた)。
    """
    result = pipeline.generate_from_selection(spec, MEAS, skip_export=True)
    # 手持ちがごく短いと、買い足す量と幅を替えた量が並ぶことがある。
    verdict = pipeline.evaluate_stash_for(result, spec, MEAS,
                                           have_width_cm=110, have_length_cm=60)
    wider = [s for s in verdict.suggestions if s.kind == "wider_fabric"]
    assert wider, "この場面では幅の提案が出るはずです"
    detail = wider[0].detail
    width, buy = verdict.wider_option
    if verdict.buy_more_cm == buy:
        assert "短く済みます" not in detail, detail
        assert f"どちらも{buy}cmです" in detail, detail
    else:
        assert "短く済みます" in detail, detail


def test_the_comparison_never_claims_a_tie_is_shorter(pipeline, spec):
    """どの手持ちの長さでも、同じ数字を「短い」と言わないこと。

    上のテストは1つの場面しか見ていない。手持ちの長さを振って、
    「短く済みます（Ncm と Ncm）」という形が1つも出ないことを見る。
    """
    import re

    result = pipeline.generate_from_selection(spec, MEAS, skip_export=True)
    for have in (30, 60, 90, 120, 150, 180, 210):
        verdict = pipeline.evaluate_stash_for(result, spec, MEAS,
                                               have_width_cm=110,
                                               have_length_cm=have)
        for suggestion in verdict.suggestions:
            for a, b in re.findall(r"短く済みます（(\d+)cm と (\d+)cm）",
                                    suggestion.detail):
                assert a != b, (
                    f"手持ち{have}cm: 同じ数字を「短い」と言っています: "
                    f"{suggestion.detail}")


# ---------------------------------------------------------------------------
# 5. 幅の選び方そのものを、作り物の測定値で確かめる
# ---------------------------------------------------------------------------
#
# 【なぜ作り物を使うか】本物の型紙で確かめようとしたら、テストが弱かった。
#   - 「比例計算で済ませる」に書き換えても落ちなかった。幅150cmでの
#     比例値(190cm)が、実測値(190cm)とたまたま同じだったからである。
#   - 「手持ちより狭い幅も候補にする」に書き換えても落ちなかった。この型紙
#     では狭い幅の方が必ず多く要るので、どのみち選ばれないためである。
# 選び方の規則そのものを見るには、幅ごとの必要量をこちらで決められる
# 測定値が要る。下の`_fake_build`は「その幅なら何cm要るか」を表で返すだけの、
# 型紙を作らない`build`である(`evaluate_stash`は`nesting`しか見ない)。

class _FakeNesting:
    def __init__(self, used_length_cm):
        self.used_length_cm = used_length_cm
        self.unplaced = []


class _FakeResult:
    def __init__(self, used_length_cm):
        self.nesting = _FakeNesting(used_length_cm)


def _fake_build(by_width):
    """幅 -> 必要な丈(cm) の表から、`evaluate_stash`が使える`build`を作る。"""
    def build(**kwargs):
        width = kwargs["fabric_width_candidates"][0]
        return _FakeResult(by_width[width])
    return build


def test_a_narrower_bolt_is_never_offered_even_if_it_needs_less():
    """手持ちより狭い幅は、必要量が少なくても候補にしないこと。

    狭い方が少なく済むことは実際の型紙ではまず起きないが、規則としては
    「手持ちより広い幅」を見ている。表を作って、その規則を直に確かめる。
    """
    verdict = evaluate_stash(
        _fake_build({110.0: 100.0, 140.0: 300.0, 150.0: 300.0}),
        have_width_cm=140, have_length_cm=50,
        other_width_candidates=(110.0, 140.0, 150.0))
    assert not verdict.fits
    assert verdict.wider_option is None, \
        f"手持ち(140cm)より狭い110cmを勧めています: {verdict.wider_option}"


def test_the_offered_width_is_the_one_that_was_measured():
    """提案する量が、その幅で測った値そのものであること。

    比例計算(幅が広いぶん短くなるはず)で代用すると、ここで食い違う。
    表では幅150cmの方が**広いのに多く要る**ようにしてあるので、
    比例計算なら150cmを選んでしまう。
    """
    verdict = evaluate_stash(
        _fake_build({110.0: 300.0, 140.0: 180.0, 150.0: 280.0}),
        have_width_cm=110, have_length_cm=50,
        other_width_candidates=(110.0, 140.0, 150.0))
    assert verdict.wider_option == (140.0, 180), verdict.wider_option


def test_a_width_that_saves_less_than_one_cutting_unit_is_not_offered():
    """買う量が10cm単位で1つも減らないなら、勧めないこと。

    表では幅140cmにしても5cmしか減らない。切り売りは10cm単位なので、
    買う量は同じ190cmのまま——勧める意味が無い。
    """
    verdict = evaluate_stash(
        _fake_build({110.0: 185.0, 140.0: 181.0}),
        have_width_cm=110, have_length_cm=50,
        other_width_candidates=(110.0, 140.0))
    assert verdict.wider_option is None, verdict.wider_option


def test_a_width_that_saves_one_cutting_unit_is_offered():
    """1単位(10cm)減るなら勧めること。境目の反対側も見ておく。"""
    verdict = evaluate_stash(
        _fake_build({110.0: 185.0, 140.0: 175.0}),
        have_width_cm=110, have_length_cm=50,
        other_width_candidates=(110.0, 140.0))
    assert verdict.wider_option == (140.0, 180), verdict.wider_option


def test_a_width_where_parts_do_not_fit_is_not_offered():
    """その幅で載らないパーツがあるなら、勧めないこと。"""
    class _Unplaceable(_FakeResult):
        def __init__(self, used_length_cm):
            super().__init__(used_length_cm)
            self.nesting.unplaced = ["マント"]

    def build(**kwargs):
        width = kwargs["fabric_width_candidates"][0]
        return _FakeResult(300.0) if width == 110.0 else _Unplaceable(100.0)

    verdict = evaluate_stash(build, have_width_cm=110, have_length_cm=50,
                              other_width_candidates=(110.0, 140.0))
    assert verdict.wider_option is None


def test_the_width_that_needs_the_least_is_chosen():
    """条件を満たす幅が複数あるなら、いちばん少なく済む方を出すこと。

    表では、幅140cmでも20cm減るが、幅150cmなら120cm減る。
    先に見つかった方(140cm)で打ち切ると、少なく済む道を隠すことになる。
    """
    verdict = evaluate_stash(
        _fake_build({110.0: 300.0, 140.0: 280.0, 150.0: 180.0}),
        have_width_cm=110, have_length_cm=50,
        other_width_candidates=(110.0, 140.0, 150.0))
    assert verdict.wider_option == (150.0, 180), verdict.wider_option
