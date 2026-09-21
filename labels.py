"""labels.py — 画面(Jinja/JS)向けの日本語ラベル。

round32で、辞書の実体を`engine/part_names.py`へ移した。ここはその再輸出で、
**唯一の変換元は engine 側**である。

【なぜ移したか】round9でこの辞書を作ったとき、印刷される型紙のパーツ名
(`engine/seam.py`の`FinalizedPart.display_name`)は「テストが英語表記に
依存しているから」という理由で対象外にしていた。その結果、裁断中にいちばん
見る文字が `front_bodice(round_neck)` のままだった。round32でそちらも
日本語にするにあたり、engine が app 直下のモジュールへ依存しないよう
(依存の向きを保つため)、辞書を engine 側の単一の場所へ集約した。

画面側での使い道は round9 から変わっていない:
  - web/templates/index.html: Jinjaフィルタ`style_label`でプルダウンの
    表示テキストに使う(valueは内部識別子のまま送信する)。
  - web/static/app.js: AIパーツ判定ログ表の表示に使う。CSPで
    `script-src 'self'`のため、辞書をJSON化して`data-*`属性経由で渡す。
"""

from __future__ import annotations

from engine.part_names import (  # noqa: F401  (再輸出)
    PART_TYPE_LABELS_JA,
    VARIATION_LABELS_JA,
    part_display_name,
    part_identifier,
    part_type_label,
    style_label,
)

__all__ = [
    "PART_TYPE_LABELS_JA",
    "VARIATION_LABELS_JA",
    "part_display_name",
    "part_identifier",
    "part_type_label",
    "style_label",
]
