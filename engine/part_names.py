"""part_names.py — パーツ種(part_type)・バリエーション(variation)の日本語名。

round32で`labels.py`(プルダウン表示専用)からここへ移した。**唯一の変換元**
(single source of truth)で、`labels.py`はここを読み直しているだけ。

【なぜ engine 側へ移したか】round9でこの辞書を作ったとき、
`engine/seam.py`の`FinalizedPart.display_name`——**実際に印刷される型紙の
上に書かれるパーツ名**——は対象外にしていた(当時のlabels.pyの
「正直な限界」にその旨を明記)。理由は「複数のテストが英語表記に依存して
いるから」で、利用者にとっての正しさではなかった。

その結果、A4分割PDFを印刷して裁断する人の手元には

    front_bodice(round_neck) [ダーツ4本]
    back_bodice_side(round_neck) 左

と書かれた紙が並んでいた。日本語の家庭洋裁向けサービスとして、裁断中に
いちばん見る文字がこれでは用をなさない。round32で実際にブラウザで
生成してPDFを開いて確認し、日本語名に変えた。機械側(テスト・ログ・
APIの利用者)が必要とする識別子は、`FinalizedPart.identifier`と
APIレスポンスの`part_type`/`variation`として**別に**出している。

未登録の識別子は、生成を止めないよう識別子をそのまま返す(フォールバック)。
「登録漏れがあると型紙に英語が出る」ことになるので、
tests/test_part_names.py が全テンプレートの組み合わせを列挙して、
未登録が1つも無いことを確かめている。
"""

from __future__ import annotations

#: パーツ種(part_type)の日本語名。
PART_TYPE_LABELS_JA: dict[str, str] = {
    "front_bodice": "前身頃",
    "front_bodice_zip_panel": "前身頃・ファスナーパネル",
    "back_bodice": "後身頃",
    # round30の切り替え線(プリンセスライン)で分かれるパーツ。
    "front_bodice_center": "前身頃・中央",
    "front_bodice_side": "前身頃・脇",
    "back_bodice_center": "後身頃・中央",
    "back_bodice_side": "後身頃・脇",
    "sleeve": "袖",
    "skirt": "スカート",
    "front_pants": "パンツ・前",
    "back_pants": "パンツ・後",
    "collar": "衿",
    "cuffs": "カフス",
    "hood": "フード",
    "waistband": "ウエストバンド",
    "custom_panel": "カスタムパーツ",
}

#: バリエーション(variation)の日本語名。値がpart_typeをまたいで重複する
#: 場合(例: "wide"はcuffs/pants/waistbandのいずれにも登場する)も、日本語の
#: 意味が共通するため単一の辞書で問題ないことを確認済み。
VARIATION_LABELS_JA: dict[str, str] = {
    "": "標準",
    # ネックライン
    "round_neck": "ラウンドネック",
    "v_neck": "Vネック",
    "turtle_neck": "タートルネック",
    "square_neck": "スクエアネック",
    "boat_neck": "ボートネック",
    "sweetheart": "スウィートハートネック",
    # 前開きファスナー用のネックライン(round32で追加。それまで
    # 「round_neck_zip」のように識別子がそのまま出ていた)。
    "round_neck_zip": "ラウンドネック・前開き",
    "v_neck_zip": "Vネック・前開き",
    "square_neck_zip": "スクエアネック・前開き",
    "boat_neck_zip": "ボートネック・前開き",
    "sweetheart_zip": "スウィートハートネック・前開き",
    # 袖
    "straight": "ストレート",
    "curve": "カーブ（フィット）",
    "puff": "パフ",
    "bell": "ベル",
    "cap": "キャップ",
    "three_quarter": "7分袖",
    # スカート
    "flare": "フレア",
    "tight": "タイト",
    "pleated": "プリーツ",
    "wrap": "ラップ",
    "mermaid": "マーメイド",
    "circle": "サーキュラー",
    # 衿
    "shirt_collar": "シャツカラー",
    "peter_pan_collar": "ピーターパンカラー",
    "bow_collar": "ボウカラー",
    "ruffle_collar": "フリルカラー",
    "convertible_collar": "コンバーチブルカラー（オープンカラー）",
    # カフス（"wide"はパンツ・ウエストバンドと共有）
    "wide": "ワイド",
    "ruffle": "フリル",
    "button_tab": "ボタンタブ付き",
    # パンツ
    "tapered": "テーパード",
    "shorts": "ショート丈",
    "cropped": "クロップド丈",
    # ウエストバンド
    "elastic": "ゴム仕様",
    "contour": "コンター（体に沿う形）",
}


def style_label(value: str | None) -> str:
    """variation識別子を日本語ラベルに変換する(未登録なら識別子のまま)。"""
    if value is None:
        return VARIATION_LABELS_JA[""]
    return VARIATION_LABELS_JA.get(value, value)


def part_type_label(value: str | None) -> str:
    """part_type識別子を日本語ラベルに変換する(未登録なら識別子のまま)。"""
    if not value:
        return "—"
    return PART_TYPE_LABELS_JA.get(value, value)


def part_display_name(part_type: str, variation: str = "",
                       label_suffix: str = "", dart_count: int = 0) -> str:
    """型紙に印字するパーツ名。

    >>> part_display_name("front_bodice", "round_neck", dart_count=4)
    '前身頃（ラウンドネック） [ダーツ4本]'
    >>> part_display_name("sleeve", "straight", "左")
    '袖（ストレート） 左'
    >>> part_display_name("sleeve", "curve", "左")
    '袖・カーブ（フィット） 左'

    カスタムパーツは**`variation`に利用者が付けた自由記述の名前**が入る
    (engine/pipeline.pyの`PartRequest.custom_segments`のコメント参照)。
    「カスタムパーツ（マント）」と重ねず、付けた名前をそのまま出す。
    複数枚のときの通し番号(①②)は`label_suffix`に入るので後ろに付ける。
    """
    if part_type == "custom_panel":
        base = variation or part_type_label(part_type)
        if label_suffix:
            base = f"{base} {label_suffix}"
    else:
        base = part_type_label(part_type)
        if variation:
            label = style_label(variation)
            # 「カーブ（フィット）」のように括弧を含むラベルをそのまま
            # 括弧でくくると「袖（カーブ（フィット））」と入れ子になって
            # 読みにくい。その場合は中黒でつなぐ。
            base = f"{base}・{label}" if "（" in label else f"{base}（{label}）"
        if label_suffix:
            base = f"{base} {label_suffix}"
    return f"{base} [ダーツ{dart_count}本]" if dart_count else base


def part_identifier(part_type: str, variation: str = "",
                     label_suffix: str = "", dart_count: int = 0) -> str:
    """機械向けの識別子(round31までの`display_name`とまったく同じ文字列)。

    テスト・ログ・DXFの検証など「パーツを一意に指したい」用途のために残す。
    人に見せる場所では`part_display_name`を使う。
    """
    base = f"{part_type}({variation})" if variation else part_type
    if label_suffix:
        base = f"{base} {label_suffix}"
    return f"{base} [ダーツ{dart_count}本]" if dart_count else base
