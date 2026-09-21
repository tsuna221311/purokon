"""contrast.py — 色のコントラスト比(WCAG 2.1)を計算する。round37で追加。

【なぜ要るか】round34で画面の配色を作り直したとき、READMEに
「色の見え方は検証していない。コントラスト比の実測や、色覚特性を持つ人での
確認はしていない」と限界として書いたまま、round36まで残っていた。
型紙を作るのは家庭の作り手で、年齢層は広い。読めない字は機能しない。

round37で実際にレンダリングした画面から`getComputedStyle`で実効色を
取り出して測ったところ、**白の上では足りているのに、この製品が実際に
使っている色付きの背景の上では足りていない**組が見つかった:

    --muted #78716c   白 4.80:1 / ページ地 4.29:1 / アクセント淡 4.22:1
    .style-none-mark  白 1.89:1 (「なし」のサムネイルの横棒)

白で確かめて決めた色を、色の付いた箱の中でも使っていたのが原因である。

【基準】WCAG 2.1
  * SC 1.4.3 Contrast (Minimum), AA — 通常の文字 4.5:1、大きい文字 3:1
    (大きい文字 = 24px以上、または18.66px以上の太字)
    https://www.w3.org/WAI/WCAG21/Understanding/contrast-minimum.html
  * SC 1.4.11 Non-text Contrast, AA — 意味を持つ図・UI部品 3:1
    https://www.w3.org/WAI/WCAG21/Understanding/non-text-contrast.html

【この計算でできないこと】コントラスト比は**明るさの差**しか見ない。
色覚特性(赤緑・青黄)の人にとって区別しやすいかは、これとは別の話で、
ここでは測れない(READMEの「正直な限界」参照)。
"""

from __future__ import annotations

#: 通常の文字に必要な比(WCAG 2.1 SC 1.4.3 AA)。
MIN_RATIO_TEXT = 4.5
#: 大きい文字に必要な比(同上)。
MIN_RATIO_LARGE_TEXT = 3.0
#: 意味を持つ図・UI部品に必要な比(WCAG 2.1 SC 1.4.11 AA)。
MIN_RATIO_NON_TEXT = 3.0

#: 「大きい文字」の下限(px)。WCAGは18pt/14pt太字で定義しており、
#: CSSの既定(1pt = 1/72インチ、1px = 1/96インチ)で換算すると
#: 18pt = 24px、14pt = 18.666...px になる。
LARGE_TEXT_PX = 24.0
LARGE_BOLD_TEXT_PX = 18.66
LARGE_TEXT_BOLD_WEIGHT = 700


def parse_hex(value: str) -> tuple[int, int, int]:
    """`#rgb` / `#rrggbb` を (r, g, b) にする。"""
    text = value.strip().lstrip("#")
    if len(text) == 3:
        text = "".join(ch * 2 for ch in text)
    if len(text) != 6:
        raise ValueError(f"色として読めません: {value!r}")
    return tuple(int(text[i:i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def relative_luminance(rgb: tuple[float, float, float]) -> float:
    """相対輝度。WCAG 2.1 の定義そのまま。

    https://www.w3.org/WAI/GL/wiki/Relative_luminance
    """
    def channel(value: float) -> float:
        v = value / 255.0
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4

    r, g, b = rgb
    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)


def contrast_ratio(a, b) -> float:
    """2色のコントラスト比(1.0〜21.0)。文字色と背景色の順序は問わない。

    文字列(`#rrggbb`)でもタプルでも受け取る。
    """
    ca = parse_hex(a) if isinstance(a, str) else a
    cb = parse_hex(b) if isinstance(b, str) else b
    la, lb = relative_luminance(ca), relative_luminance(cb)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def required_ratio(font_px: float, font_weight: int = 400) -> float:
    """その大きさ・太さの文字に必要な比を返す。"""
    if font_px >= LARGE_TEXT_PX or (
            font_px >= LARGE_BOLD_TEXT_PX and font_weight >= LARGE_TEXT_BOLD_WEIGHT):
        return MIN_RATIO_LARGE_TEXT
    return MIN_RATIO_TEXT


def blend(foreground: tuple[float, float, float, float],
          background: tuple[float, float, float]) -> tuple[float, float, float]:
    """半透明の色を背景に重ねた実効色を返す。

    半透明のまま輝度を計算すると、実際に見えている色と違う値が出る。
    """
    r, g, b, alpha = foreground
    br, bg_, bb = background
    return (r * alpha + br * (1 - alpha),
            g * alpha + bg_ * (1 - alpha),
            b * alpha + bb * (1 - alpha))
