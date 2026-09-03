"""labels.py — 内部の英語スネークケース識別子(part_type/variation)を
日本語UIラベルに変換する辞書。round9で追加。

実際に開発用サーバーを起動しindex.htmlをレンダリングして見つけた実バグの
修正: フォームのプルダウン（ネックライン・袖の形・スカートの形・衿・
カフス・パンツ・ウエストバンド）はどれも`<option value="{{ n }}">{{ n }}</option>`
という実装で、選択肢の"表示テキスト"がそのまま内部識別子（例:
"round_neck"、"peter_pan_collar"）になっていた。日本語UIのアプリで
このような英語スネークケースがそのまま利用者に見えるのは明確なUXの不具合
であり、日本語ラベルへの変換機構がアプリ全体のどこにも存在しないことも
確認した(web/static/app.jsのAIパーツ判定ログ表も同様に生の識別子を
そのまま表示していた)。

この辞書を唯一の変換元(single source of truth)とし、
  - web/templates/index.html: Jinjaフィルタ`style_label`経由でプルダウンの
    表示テキストに使う(valueは引き続き内部識別子のまま送信する)。
  - web/static/app.js: AIパーツ判定ログ表の表示に使う。CSPで
    `script-src 'self'`(インラインscript不可)のため、この辞書をJSON化して
    `data-*`属性(非実行属性でCSPの対象外)経由でHTMLからJSへ渡す
    (app.py `index()` → index.html → app.js の3段で受け渡す)。

正直な限界（意図的に対象外にした範囲）:
  - `engine/seam.py`の`FinalizedPart.display_name`（PDF/DXF出力で実際に
    型紙パーツへ印字されるラベル、およびAPIレスポンスの`parts[].display_name`）
    は、この辞書による変換の対象に含めていない。英語識別子のまま
    (`front_bodice(round_neck)`のような形式)。
    理由: display_nameは印刷される型紙そのものへの表示ラベルであり、
    `tests/test_app.py`の`assert any("front_bodice_zip_panel" in n ...)`や
    `tests/test_dxf_export.py`のラベル突合テストなど、複数のテストファイルが
    現在の英語表記に依存している。ここを変更するとPDF/DXF出力・
    パーツラベルの実際の見た目・複数テストファイルにまたがる変更になり、
    今回確認できたブラウザUI（プルダウン・AI判定ログ表）の表示だけを直す
    範囲を超える。見つかった実際の課題としてREADMEに記録し、将来の
    対応候補とする。
  - 新しいpart_type/variationを追加した際にここへ追記し忘れても、
    生成自体は正常に動作する（`style_label`はフォールバックとして識別子を
    そのまま返すだけで、例外にはしない）。ラベルが英語のまま表示される
    だけなので、追加時のチェックリストとしてREADMEにも明記する。
"""

from __future__ import annotations

# パーツ種(part_type)の日本語ラベル。AIパーツ判定ログ表でのみ使用。
PART_TYPE_LABELS_JA: dict[str, str] = {
    "front_bodice": "前身頃",
    "front_bodice_zip_panel": "前身頃（ファスナー用パネル）",
    "back_bodice": "後身頃",
    "sleeve": "袖",
    "skirt": "スカート",
    "front_pants": "パンツ（前）",
    "back_pants": "パンツ（後）",
    "collar": "衿",
    "cuffs": "カフス",
    "waistband": "ウエストバンド",
}

# バリエーション(variation)の日本語ラベル。値(variation識別子)が
# part_typeをまたいで重複する場合(例: "wide"はcuffs/pants/waistbandの
# いずれにも登場する)も、日本語の意味が共通するため単一の辞書で問題ない
# ことを確認済み。
VARIATION_LABELS_JA: dict[str, str] = {
    "": "標準",
    # ネックライン
    "round_neck": "ラウンドネック",
    "v_neck": "Vネック",
    "turtle_neck": "タートルネック",
    "square_neck": "スクエアネック",
    "boat_neck": "ボートネック",
    "sweetheart": "スウィートハートネック",
    # 袖
    "straight": "ストレート",
    "curve": "カーブ（フィット）",
    "puff": "パフ",
    "bell": "ベル",
    "cap": "キャップ",
    "three_quarter": "7分袖",  # round9で追加
    # スカート
    "flare": "フレア",
    "tight": "タイト",
    "pleated": "プリーツ",
    "wrap": "ラップ",
    "mermaid": "マーメイド",
    "circle": "サーキュラー",  # round9で追加
    # 衿
    "shirt_collar": "シャツカラー",
    "peter_pan_collar": "ピーターパンカラー",
    "bow_collar": "ボウカラー",
    "ruffle_collar": "フリルカラー",
    "convertible_collar": "コンバーチブルカラー（オープンカラー）",  # round9で追加
    # カフス（"wide"はパンツ・ウエストバンドと共有）
    "wide": "ワイド",
    "ruffle": "フリル",
    "button_tab": "ボタンタブ付き",  # round9で追加
    # パンツ
    "tapered": "テーパード",
    "shorts": "ショート丈",
    "cropped": "クロップド丈",  # round9で追加
    # ウエストバンド
    "elastic": "ゴム仕様",
    "contour": "コンター（体に沿う形）",  # round9で追加
}


def style_label(value: str | None) -> str:
    """variation識別子を日本語ラベルに変換する。

    未登録の値（辞書への追記漏れ）は、生成自体を妨げないよう例外を投げず、
    識別子をそのまま返す（フォールバック。上記モジュールdocstring
    「正直な限界」参照）。
    """
    if value is None:
        return VARIATION_LABELS_JA[""]
    return VARIATION_LABELS_JA.get(value, value)


def part_type_label(value: str | None) -> str:
    """part_type識別子を日本語ラベルに変換する（未登録時は識別子をそのまま返す）。"""
    if not value:
        return "—"
    return PART_TYPE_LABELS_JA.get(value, value)
