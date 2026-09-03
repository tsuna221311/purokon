"""part_specs.py — パーツ種ごとの体型スケーリング規則。

パーツごとに「横のみ(スカート幅)」「縦横両方(袖丈)」のルールを定義して
精度を担保する、という設計をコードとして表現したもの。

x_measure / y_measure に Measurements のフィールド名を指定すると、
「標準Mサイズとの比率」でその軸を変形する。None を指定した軸は変形しない
(常に1.0倍＝標準Mサイズのまま)。
"""

from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class ScaleRule:
    x_measure: str | None  # 幅方向(X)を決める採寸項目。Noneなら幅は固定。
    y_measure: str | None  # 長さ方向(Y)を決める採寸項目。Noneなら長さは固定。
    note: str = ""


PART_SCALE_RULES: dict[str, ScaleRule] = {
    # 身頃: 幅はバスト、長さは身長（着丈）に比例。縦横両方を変形する。
    "front_bodice": ScaleRule("bust", "height", "身頃は幅=バスト、丈=身長比で両方変形"),
    "back_bodice": ScaleRule("bust", "height", "身頃は幅=バスト、丈=身長比で両方変形"),
    # 前開きファスナー用に中心前で分割した前パネル(round5)。スケーリング則
    # 自体はfront_bodiceと同じ(幅=バスト、丈=身長比)。
    "front_bodice_zip_panel": ScaleRule("bust", "height", "前開き前パネルは幅=バスト、丈=身長比で両方変形"),
    # 袖: 「縦横両方」変形の代表例。
    # 幅(振り)は肩幅、長さは袖丈で変形する。
    "sleeve": ScaleRule("shoulder_width", "sleeve_length", "袖は幅=肩幅、丈=袖丈で両方変形"),
    # スカート: 幅はウエストとヒップの両方から必要量を求める(下記
    # LOWER_GARMENT_FIT参照)。丈(標準M基準の長さ)はデザイン通りに固定する。
    "skirt": ScaleRule("hip", None, "スカートは幅=ウエスト/ヒップの必要量、丈は固定"),
    # パンツ: 幅はスカートと同じ考え方、丈は身長に比例。round5で前パーツ
    # (front_pants)・後ろパーツ(back_pants)に分離した。
    "front_pants": ScaleRule("hip", "height", "パンツ(前)は幅=ウエスト/ヒップの必要量、丈=身長比"),
    "back_pants": ScaleRule("hip", "height", "パンツ(後)は幅=ウエスト/ヒップの必要量、丈=身長比"),
    # 帯状パーツ: 対応する採寸に応じて長さ(=帯の長さ方向であるX)のみ変形する。
    "collar": ScaleRule("bust", None, "衿は首回りの近似としてバスト比でX(帯の長さ)のみ変形"),
    "cuffs": ScaleRule("sleeve_length", None, "カフスは腕の太さの近似として袖丈比でX(帯の長さ)のみ変形"),
    "waistband": ScaleRule("waist", None, "ウエストバンドはウエスト比でX(帯の長さ)のみ変形"),
    # round9で追加: custom_panel(定型に当てはまらない自由形状パーツ、
    # engine/custom_panel.py参照)は、輪郭取得時に校正(参照線の実寸cm)済み
    # のため、採寸値による追加のスケーリングを一切行わない
    # (x_measure/y_measure=Noneの効果は「常に倍率1.0」であることを
    # scale_template()経由で保証している)。
    "custom_panel": ScaleRule(None, None, "カスタムパーツは校正済みの実寸(cm)のためスケーリングしない"),
}

# --- round12(続き)で追加: 下半身パーツの幅は、ウエストとヒップの両方を見る ---
#
# 【なぜ必要か】スカート・パンツは round11 まで幅をヒップ比だけで変形して
# いた。ウエストとヒップの差は engine/darts.py のウエストダーツが吸収する
# 設計だったが、ダーツは「余った幅を摘む」ことしかできず、**足りない幅を
# 足すことはできない**。標準M(ウエスト66・ヒップ91)はウエスト/ヒップ比が
# 0.725とくびれの強い体型なので、それより胴が寸胴寄りの体型では
# ウエストが足りず、スカートやパンツが閉まらない型紙になっていた。
# 実測では、ウエスト88・ヒップ102の体型でウエスト周が13.8cm不足していた。
#
# 【対処】幅の倍率を「ウエストが必要とする倍率」と「ヒップが必要とする倍率」
# の大きい方にする。ウエスト側が効いた場合はヒップにゆとりが出るが、
# 「腰は少しゆるい」で済むのに対し「ウエストが閉まらない」は着られないため、
# こちらを優先する。ヒップ側が効いた場合(くびれの強い体型)は従来通りで、
# 余ったウエスト幅はウエストダーツが摘む。
#
# 基準値はテンプレートの実寸(scripts/generate_templates.py)と対:
#   スカート … 前後2枚で ウエスト68cm / ヒップ95cm
#   パンツ  … 前後左右4枚で ウエスト68cm / ヒップ95cm
# ゆとりは、ウエスト2cm・ヒップ4cm(テンプレート側の設計値と同じ)。
LOWER_GARMENT_PART_TYPES = {"skirt", "front_pants", "back_pants"}
LOWER_BASE_WAIST_CM = 68.0
LOWER_BASE_HIP_CM = 95.0
LOWER_WAIST_EASE_CM = 2.0
LOWER_HIP_EASE_CM = 4.0


def lower_garment_x_scale(waist_cm: float, hip_cm: float) -> float:
    """スカート・パンツの幅方向の倍率を、ウエストとヒップの必要量から求める。"""
    return max((waist_cm + LOWER_WAIST_EASE_CM) / LOWER_BASE_WAIST_CM,
               (hip_cm + LOWER_HIP_EASE_CM) / LOWER_BASE_HIP_CM)


# 極端な入力（例: 身長210cmなど）でテンプレートが破綻しない範囲にクランプする。
MIN_SCALE = 0.7
MAX_SCALE = 1.6

# --- round11で追加: 帯状パーツ専用の、より広いクランプ範囲 -------------------
#
# MIN_SCALE/MAX_SCALE(0.7〜1.6)は、front_bodice/back_bodice/sleeve/skirt/
# front_pants/back_pantsのような「曲線を含み、X/Y両方向に変形するパーツ」が
# 極端な入力で破綻しないための安全域として選ばれている(曲線の制御点を大きく
# 伸縮させると、カーブどうしが交差して型紙として無効な形状になりうる)。
#
# 一方 collar/cuffs/waistband は、いずれもscripts/generate_templates.pyの
# `_write_band`で単純な矩形として生成され、ScaleRule(下記PART_SCALE_RULES)も
# X方向のみを変形する(Y方向は常に1.0倍で固定)。矩形をX方向にだけ伸縮する
# 変形は、倍率がどれだけ大きく/小さくても自己交差が原理的に起こらない
# (4頂点の矩形が細長く/短くなるだけ)。つまりこれらに身頃と同じ狭い
# クランプを適用する理由は無い。
#
# 実際、round11でこのクランプの影響を実測したところ、Measurements自体が
# 受け付ける有効な入力の両端で、3種類とも必ずクランプが効いてしまっていた:
#   collar   (bust比):          有効範囲50〜160cm  → 比率0.602〜1.928
#   cuffs    (sleeve_length比):  有効範囲30〜90cm   → 比率0.577〜1.731
#   waistband(waist比):          有効範囲40〜150cm  → 比率0.606〜2.273
# 例えばウエスト150cmの利用者に対し、ウエストバンドは本来2.273倍にすべき
# ところ1.6倍で頭打ちになり、実測で約3割短い型紙が出ていた(生地を裁って
# 初めて気づく類の実害)。
#
# そこで上記3項目の比率の和集合(最も広い範囲)を帯状パーツ専用のクランプと
# して採用し、有効な採寸値の範囲内では一切クランプが起きないようにした。
# 単位間違い等の異常入力に対する歯止めは、Measurements側の入力検証
# (_VALID_RANGES)が引き続き担う。
BAND_PART_TYPES = {"collar", "cuffs", "waistband"}
MIN_SCALE_BAND = 30.0 / 52.0   # cuffsのsleeve_length下限(30cm)÷標準52cm。
MAX_SCALE_BAND = 150.0 / 66.0  # waistbandのwaist上限(150cm)÷標準66cm。


def clamp_scale_for_part(value: float, part_type: str) -> float:
    """part_typeに応じて、通常のクランプか帯状パーツ用の広いクランプを選ぶ。"""
    if part_type in BAND_PART_TYPES:
        return max(MIN_SCALE_BAND, min(MAX_SCALE_BAND, value))
    return clamp_scale(value)


def clamp_scale(value: float) -> float:
    return max(MIN_SCALE, min(MAX_SCALE, value))
