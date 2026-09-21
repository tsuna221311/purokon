"""round32: 型紙に印字されるパーツ名を日本語にする。

round31まで、A4分割PDFを印刷して裁断する人の手元に並ぶ紙には

    front_bodice(round_neck) [ダーツ4本]
    back_bodice_side(round_neck) 左

と書かれていた(実際にブラウザで生成しPDFを開いて確認した)。日本語の
家庭洋裁向けサービスとして、裁断中にいちばん見る文字がこれでは用をなさない。

日本語ラベルの辞書自体はround9から存在していたが、`labels.py`の
「正直な限界」に書いたとおり**印字されるパーツ名は対象外**にしていた。
理由は「複数のテストが英語表記に依存しているから」で、利用者にとっての
正しさではなかった。round32でそれを直し、機械が必要とする識別子は
`FinalizedPart.identifier` / APIの`part_type`・`variation`として別に出す。
"""

import pytest

from engine.part_names import (
    PART_TYPE_LABELS_JA, VARIATION_LABELS_JA,
    part_display_name, part_identifier, part_type_label, style_label,
)
from engine.princess import PRINCESS_PANEL_TYPES
from engine.svgpath import parse_path
from engine.seam import finalize_part
from engine.templates_db import TemplateDB


def _is_japanese(text: str) -> bool:
    """日本語(かな・漢字・全角記号)を含み、内部識別子らしさが無いこと。"""
    has_ja = any("　" <= ch <= "鿿" or "＀" <= ch <= "￯" for ch in text)
    return has_ja and "_" not in text


# --- 登録漏れが1つも無いこと -------------------------------------------------

def test_every_template_part_type_has_a_japanese_name():
    """テンプレートが持つ全part_typeに日本語名があること。

    漏れると、そのパーツだけ型紙に英語識別子が印字される(例外は出ない)。
    """
    db = TemplateDB()
    for part_type, _variation in db.available():
        assert part_type in PART_TYPE_LABELS_JA, part_type


def test_every_template_variation_has_a_japanese_name():
    db = TemplateDB()
    for part_type, variation in db.available():
        assert variation in VARIATION_LABELS_JA, (part_type, variation)


def test_the_princess_panels_have_japanese_names():
    """round30で増えた切り替え線のパーツにも名前があること。

    round31時点では未登録で、`back_bodice_side(round_neck) 左`と印字
    されていた。
    """
    for pair in PRINCESS_PANEL_TYPES.values():
        for part_type in pair:
            assert part_type in PART_TYPE_LABELS_JA, part_type
            assert _is_japanese(part_type_label(part_type))


def test_the_zip_necklines_have_japanese_names():
    """前開き用のバリエーション(`*_zip`)にも名前があること。

    round31時点では未登録で、プルダウンにも型紙にも「round_neck_zip」と
    そのまま出ていた。
    """
    db = TemplateDB()
    zips = {v for _pt, v in db.available() if v.endswith("_zip")}
    assert zips, "前提: _zip のバリエーションが存在すること"
    for variation in zips:
        assert _is_japanese(style_label(variation)), variation


@pytest.mark.parametrize("part_type",
                          sorted(set(PART_TYPE_LABELS_JA) - {"custom_panel"}))
def test_no_name_leaks_an_internal_identifier(part_type):
    """全part_type × 全variationで、印字名に「_」が現れないこと。

    custom_panelだけは除く——そのvariationは利用者が付けた自由記述の
    名前で、辞書の変換対象ではない(下の専用テストで見ている)。
    """
    for variation in VARIATION_LABELS_JA:
        name = part_display_name(part_type, variation, "左", 2)
        assert "_" not in name, (part_type, variation, name)


# --- 組み立て方 -------------------------------------------------------------

def test_the_name_reads_naturally():
    assert part_display_name("front_bodice", "round_neck") == "前身頃（ラウンドネック）"
    assert part_display_name("sleeve", "straight", "左") == "袖（ストレート） 左"
    assert part_display_name("front_bodice", "round_neck", "", 4) \
        == "前身頃（ラウンドネック） [ダーツ4本]"
    assert part_display_name("waistband", "") == "ウエストバンド"


def test_a_label_that_already_has_brackets_is_not_nested():
    """「袖（カーブ（フィット））」のような入れ子にならないこと。"""
    assert part_display_name("sleeve", "curve") == "袖・カーブ（フィット）"
    assert part_display_name("collar", "convertible_collar") \
        == "衿・コンバーチブルカラー（オープンカラー）"


def test_a_custom_panel_shows_only_the_name_the_user_gave_it():
    """カスタムパーツは利用者が付けた名前だけを出すこと。

    「カスタムパーツ（標準） マント」では、自分で付けた名前が埋もれる。
    """
    assert part_display_name("custom_panel", "マント") == "マント"
    assert part_display_name("custom_panel", "マント", "②") == "マント ②"


# --- 機械向けの識別子は残っていること ---------------------------------------

def test_the_identifier_is_unchanged_from_round31():
    """`identifier`がround31までの`display_name`と同じ文字列であること。

    テスト・ログ・APIの利用者が「どのパーツか」を特定するのに使う。
    表示名を直すたびにそれが壊れると、直せなくなる。
    """
    part = finalize_part("front_bodice", "round_neck",
                         parse_path("M 0 0 L 40 0 L 40 60 L 0 60 Z"),
                         seam_allowance_cm=1.0, dart_count=4)
    assert part.identifier == "front_bodice(round_neck) [ダーツ4本]"
    assert part.display_name == "前身頃（ラウンドネック） [ダーツ4本]"
    assert part_identifier("sleeve", "straight", "左") == "sleeve(straight) 左"


def test_the_api_payload_carries_both(tmp_path):
    """APIの`parts[]`に、日本語名と機械向けの値が両方入っていること。"""
    from engine.measurements import Measurements
    from engine.pipeline import PatternForgePipeline, build_garment_spec

    pipeline = PatternForgePipeline(output_dir=str(tmp_path))
    spec = build_garment_spec(neckline="round_neck", sleeve_style="straight",
                              skirt_style=None)
    result = pipeline.generate_from_selection(spec, Measurements(83, 66, 91, 158, 52, 37))
    entries = result.summary()["parts"]
    assert entries
    for entry in entries:
        assert _is_japanese(entry["display_name"]), entry
        assert entry["part_type"] and entry["part_type"] in entry["identifier"]
        assert entry["cutting_note"]
