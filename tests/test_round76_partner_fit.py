"""round76: 「相手に合わせて引く」が黙って外れる形の不具合を見張る。

【round74とround75で、同じ形の不具合を2回直した】

    round74  前開き(front_bodice_zip_panel)にすると**袖ぐり**を測れず、
             袖が肩幅比の独立スケーリングへ落ちる。
             実測: 重ね着(+18cm)で袖ぐり43.70cmに対し袖山42.60cm。
             袖ぐりが広がっても袖は1mmも動かなかった。

    round75  同じ理由で**首ぐり**を測れず、衿とフードが採寸比へ落ちる。
             実測: 頭囲56cmを入れても、既定の57cmで引いたものと
             同じ28.6×47.8cmのフードが出た。

どちらも共通の形をしている。

    相手の寸法が測れない → 目標がNoneになる → 呼び出し側が
    **黙って**採寸比の独立スケーリングへ落ちる → 出来上がりが合わない
    以外、何の手がかりも残らない

round76で、この形が3度目に起きても**黙っては**起きないようにする。
round58で署名の突き合わせを足したのと同じ考え方である。

  1. 実行時 … 相手がいるのに合わせられなかったら、利用者へそう言う
               (`engine/pipeline.py`の`silent_fallback_note`)
  2. テスト … 作れる組み合わせを総当たりして、落ちるものが
               「タートルネック+衿/フード」だけであることを確かめる

2の一覧が増えたら、それは新しい「黙って落ちる」が生まれたということで、
このテストが落ちる。
"""

import itertools
import tempfile

import pytest

from engine.measurements import Measurements
from engine.pipeline import (
    PARTNER_FITTED_PART_TYPES, GarmentSpec, PartRequest, PatternForgePipeline,
    partner_is_present, silent_fallback_note,
)

#: 相手に合わせられなかったことを言う注記の、見分けに使う言葉。
MARK = "合わせられませんでした"

#: 総当たりで**落ちてよい**組み合わせ。タートルネックは首ぐりが台襟に
#: なっていて、衿を縫い付ける線がそもそも無い(`_collar_target_length_cm`)。
#: ここが増えるときは、増やす理由をこのコメントに書くこと。
KNOWN_UNFITTABLE = {("turtle_neck", "collar"), ("turtle_neck", "hood")}


def _body():
    return Measurements(bust=82, waist=62, hip=88, height=158,
                        sleeve_length=54, shoulder_width=37,
                        head_circumference=57)


def _build(parts, princess=False):
    spec = GarmentSpec(parts=parts, princess_line=princess)
    return PatternForgePipeline(
        output_dir=tempfile.mkdtemp()).generate_from_selection(spec, _body())


def _fallback_notes(result):
    return [n for n in result.summary()["design_notes"] if MARK in n]


#: 前身頃の作り方(普通/タートルネック/前開き)。
FRONTS = {
    "普通": [PartRequest("front_bodice", "round_neck", 1),
             PartRequest("back_bodice", "round_neck", 1)],
    "タートルネック": [PartRequest("front_bodice", "turtle_neck", 1),
                       PartRequest("back_bodice", "turtle_neck", 1)],
    "前開き": [PartRequest("front_bodice_zip_panel", "round_neck", 2),
               PartRequest("back_bodice", "round_neck_zip", 1)],
}

#: 「相手に合わせて引く」パーツの足し方。
EXTRAS = {
    "袖": [PartRequest("sleeve", "straight", 2)],
    "衿": [PartRequest("collar", "", 1)],
    "フード": [PartRequest("hood", "", 2)],
    "袖+カフス": [PartRequest("sleeve", "straight", 2),
                  PartRequest("cuffs", "", 2)],
    "スカート+ウエストバンド": [PartRequest("skirt", "flare", 1),
                                PartRequest("waistband", "", 1)],
    "全部": [PartRequest("sleeve", "straight", 2),
             PartRequest("collar", "", 1),
             PartRequest("cuffs", "", 2),
             PartRequest("skirt", "flare", 1),
             PartRequest("waistband", "", 1)],
}


@pytest.mark.parametrize("front,extra,princess", [
    (f, e, p) for f, e, p in itertools.product(FRONTS, EXTRAS, (False, True))
])
def test_nothing_falls_back_silently(front, extra, princess):
    """相手がいるのに相手へ合わせられなかった組み合わせが、増えていないこと。

    落ちてよいのは`KNOWN_UNFITTABLE`に書いたものだけ。ここが増えたら、
    round74/75と同じ形の不具合が新しく生まれたということである。
    """
    neck = FRONTS[front][0].variation
    result = _build(FRONTS[front] + EXTRAS[extra], princess=princess)
    notes = _fallback_notes(result)
    expected = {part.part_type for part in EXTRAS[extra]
                if (neck, part.part_type) in KNOWN_UNFITTABLE}
    assert len(notes) == len(expected), (front, extra, princess, notes)


def test_the_front_opening_bodice_is_fitted_everywhere():
    """前開きでも、袖・衿・フードが相手に合わせて引かれること。

    round74とround75が閉じた2件が、開き直っていないかの回帰。
    """
    result = _build(FRONTS["前開き"] + EXTRAS["全部"]
                    + [PartRequest("hood", "", 2)])
    assert _fallback_notes(result) == []


def test_the_turtle_neck_collar_is_disclosed():
    """タートルネックに衿を足したら、合わせていないことを言うこと。

    round75まで、ここは**黙って**採寸比へ落ちていた。
    """
    result = _build(FRONTS["タートルネック"] + EXTRAS["衿"])
    notes = _fallback_notes(result)
    assert len(notes) == 1, notes
    assert "衿" in notes[0]
    assert "首ぐり" in notes[0]
    assert "見比べて" in notes[0], "利用者が何をすればよいかを書くこと"


# --- 空振りの確認 -------------------------------------------------------------

def test_it_says_nothing_when_there_is_no_partner():
    """相手がいなければ、注記を出さないこと。

    袖だけ・衿だけを作るのは正しい使い方で、そのとき採寸比で引くのは
    間違いではない。ここで言葉を出すと、正しい使い方に毎回警告が付く。
    """
    result = _build([PartRequest("sleeve", "straight", 2),
                     PartRequest("cuffs", "", 2)])
    assert _fallback_notes(result) == []
    assert silent_fallback_note("sleeve", "straight", {"sleeve": [object()]}) is None


def test_the_partner_table_covers_every_deferred_part_type():
    """「相手に合わせて引く」パーツが、この表から漏れていないこと。

    `engine/pipeline.py`は袖・衿・フードを2回目、ウエストバンドと
    カフスを3回目の変形で引く(相手が先に決まらないと計算できないため)。
    その一覧と、この表の見出しは必ず一致する。片方だけ増えると、
    新しいパーツ種が黙って見張りの外に出る。
    """
    from engine.pipeline import BAND_PART_TYPES, SLEEVE_STAGE_PART_TYPES

    deferred = set(BAND_PART_TYPES) | set(SLEEVE_STAGE_PART_TYPES)
    assert set(PARTNER_FITTED_PART_TYPES) == deferred


def test_partner_is_present_needs_both_halves():
    """袖ぐりは、前身頃と後ろ身頃の**両方**が無ければ測れないこと。"""
    assert not partner_is_present("sleeve", {"front_bodice": [1]})
    assert not partner_is_present("sleeve", {"back_bodice": [1]})
    assert partner_is_present("sleeve", {"front_bodice": [1], "back_bodice": [1]})
    assert partner_is_present("sleeve", {"front_bodice_zip_panel": [1],
                                          "back_bodice": [1]})
