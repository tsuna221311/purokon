"""labels.pyのテスト。round9で追加。

実際にindex.htmlをレンダリングして見つけた「内部識別子(round_neck等)が
そのまま日本語UIに表示される」実バグの修正(labels.py)に対するテスト。
単純な変換関数のテストに加え、「pipeline.pyのスタイル集合(NECKLINES等)に
新しい値を追加したのにlabels.pyへのラベル追記を忘れる」という、この
バグが再発する具体的なパターンを検出する網羅性チェックを含める
(このチェックが無いと、次に新バリエーションを追加したときに同じ種類の
表示バグが再びサイレントに紛れ込む)。
"""

from engine.pipeline import (
    COLLAR_STYLES,
    CUFFS_STYLES,
    NECKLINES,
    PANTS_STYLES,
    SKIRT_STYLES,
    SLEEVE_STYLES,
    WAISTBAND_STYLES,
)
from engine.templates_db import REQUIRED_PARTS
from labels import PART_TYPE_LABELS_JA, VARIATION_LABELS_JA, part_type_label, style_label


def test_style_label_translates_known_variations():
    assert style_label("round_neck") == "ラウンドネック"
    assert style_label("peter_pan_collar") == "ピーターパンカラー"
    assert style_label("") == "標準"
    assert style_label(None) == "標準"


def test_style_label_falls_back_to_raw_value_for_unknown_variation():
    # 未登録の値は例外にせず、識別子をそのまま返す(生成機能自体は止めない
    # という設計方針。labels.pyのモジュールdocstring「正直な限界」参照)。
    assert style_label("not-a-real-variation") == "not-a-real-variation"


def test_part_type_label_translates_known_part_types():
    assert part_type_label("front_bodice") == "前身頃"
    assert part_type_label("") == "—"
    assert part_type_label(None) == "—"


def test_part_type_label_falls_back_to_raw_value_for_unknown_part_type():
    assert part_type_label("not-a-real-part-type") == "not-a-real-part-type"


def test_every_style_set_variation_has_a_japanese_label():
    # engine/pipeline.pyの各STYLE集合(フォームのプルダウンに出てくる値)は
    # すべてVARIATION_LABELS_JAに登録されているはず。ここが欠けると、
    # index.htmlのプルダウンにその値だけ英語のまま表示される
    # (round9で見つけた実バグと同種の退行)。
    all_variations = (NECKLINES | SLEEVE_STYLES | SKIRT_STYLES
                       | COLLAR_STYLES | CUFFS_STYLES | PANTS_STYLES | WAISTBAND_STYLES)
    missing = sorted(v for v in all_variations if v not in VARIATION_LABELS_JA)
    assert missing == [], f"日本語ラベル未登録のバリエーション: {missing}"


def test_every_required_part_type_has_a_japanese_label():
    part_types = {part_type for part_type, _variation in REQUIRED_PARTS}
    missing = sorted(pt for pt in part_types if pt not in PART_TYPE_LABELS_JA)
    assert missing == [], f"日本語ラベル未登録のpart_type: {missing}"
