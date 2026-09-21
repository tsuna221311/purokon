"""pipeline.py — 採寸〜PDF出力までをつなぐエンドツーエンドの生成フロー。

6ステップ(①イラスト入力〜⑥PDF出力)を実装する、このプロジェクトの
中心モジュール。

入口は2つ:
  generate_from_selection    — ネックライン・袖・スカート等をユーザーが
                                手動で選ぶモード。APIキーやAI推論なしで
                                常に確実に動く既定の経路。
  generate_from_illustration — イラストをアップロードし、SAM分割+Claude API
                                判定でパーツ構成を自動推定するモード。

どちらも最終的に GarmentSpec（どのpart_type+variationを何枚使うか）を
組み立て、共通の _build_from_spec() で
  テンプレート取得 → 体型スケーリング → 縫い代/合印/布目線付与
  → AIネスティング → PDF/SVG出力
を行う。
"""

from __future__ import annotations
import os
import time
import uuid
from dataclasses import dataclass, field, replace
from types import SimpleNamespace

from PIL import Image

from .compatibility import (
    COLLAR_EASE_CM, CUFFS_EASE_CM, CompatibilityWarning, SLEEVE_CAP_DESIGN_GATHER_CM,
    SLEEVE_CAP_EASE_CM, WAISTBAND_CLOSURE_EASE_CM, armhole_length, sleeve_cap_ease_cm,
    check_seam_compatibility, hem_or_wrist_opening_length, neckline_length,
    shoulder_seam_length, shoulder_seams_match, unchecked_seams,
    waist_opening_length,
)
from .darts import (
    BUST_DART_ELIGIBLE_PART_TYPES, WAIST_DART_BELOW_BP_CM, waist_dart_share,
    _closed_points_from_segments, _x_span_at_y, waist_diamond_dart_lines,
)
from .custom_panel import (
    CUSTOM_PANEL_PART_TYPE,
    MAX_CUSTOM_PANEL_QUANTITY,
    mirror_points_x,
    points_to_segments,
)
from .measurements import (
    Measurements,
    STANDARD_SIZE_GRADE_CM,
    STANDARD_SIZE_ORDER,
    detect_dart_count_inconsistencies,
    grading_relative_change_notes,
    graded_measurements,
    validate_custom_grade_cm,
)
from .drop_shoulder import (
    DROP_SHOULDER_PART_TYPES, apply_drop_shoulder, drop_shoulder_notes,
    too_large_drop_reason,
)
from .hood import hood_notes, hood_segments, plan_hood
from .layering import (
    finished_bust_cm, layering_notes, plan_layer, too_tight_to_layer,
)
from .skin_tone import read_colours
from .illustration_fit import (
    DesignProportions, SleeveReading, choose_skirt_variation, choose_sleeve_variation,
    combine_proportions, measure_neckline, measure_proportions, measure_sleeves,
    skirt_length_cm,
)
from .nesting import DEFAULT_FABRIC_WIDTHS_CM, NestingResult, best_fabric_width
from .notches import (
    armhole_notch_distance_cm, armhole_notch_points, seam_edge_points_at,
    side_seam_notch_distance_cm, side_seam_notch_points,
    sleeve_cap_notch_points,
)
from .assembly import assembly_steps
from .panel_split import (
    MAX_PANELS, SPLITTABLE_PART_TYPES, panel_labels, panels_needed,
    split_into_panels,
    split_note,
)
from .part_classifier import (
    MAX_CLASSIFICATIONS_PER_REQUEST,
    ClassificationResult,
    get_default_classifier,
)
from .part_names import part_type_label
from .bodice_fit import bust_point_from_cf_cm
from .part_specs import (
    BODICE_PART_TYPES, DEFAULT_FIT, FIT_PRESETS, fit_ease, is_stretch,
)
from .princess import (
    PRINCESS_PANEL_TYPES, PRINCESS_PART_TYPES, split_bodice,
)
from .alteration import (ALTERABLE_PART_TYPES, apply_alterations,
                          shoulder_slope_correction_cm,
                          notes_for as alteration_notes,
                          validate as validate_alterations)
from .blocks import (ADULT_FEMALE, Block, block_notes, block_warnings,
                      get_block)
from .fabric import ShoppingList, build_shopping_list
from .fabric_groups import (DEFAULT_FABRIC_NAME, split_parts as split_fabric_groups)
from .lining import (build_lining_parts, lining_hem_allowance_cm, lining_notes,
                      yardage_reference_note)
from .stash import StashVerdict, evaluate_stash
from .pdf_export import (export_multi_size_bundle, export_pattern, get_paper,
                          render_combined_pdf, unprintable_characters)
from .scaling import (
    ScaledPart, bodice_fit_clamp_warning, measurement_clamp_warnings,
    scale_band_to_seam_length, scale_sleeve_to_cap_length, scale_template,
)
from .seam import DEFAULT_SEAM_ALLOWANCE_CM, FinalizedPart, finalize_part
from .segmentation import get_default_segmenter
from .svgpath import bounding_box, segments_to_polyline
from .templates_db import TemplateDB

NECKLINES = {"round_neck", "v_neck", "turtle_neck", "square_neck", "boat_neck", "sweetheart"}
# 前開きファスナー用のネックラインテンプレート(_zip)を実際に用意して
# いるのはこの5種(round9でsquare_neck/boat_neck/sweetheartを追加、
# それ以前はround_neck/v_neckのみだった)。turtle_neckのみ対象外のまま
# 残している: タートルネックは台襟(スタンドカラー状の立ち上がり)がネック
# ライン開口部そのものであり、中心前で単純に2分割するとその台襟の輪郭が
# 破綻する(front_bodice("turtle_neck", ...)のneck_dは"L 22 0 L 8 0 L 8 4"
# という台襟の縦の縁を含む形状で、round_neck等のような「肩→肩を結ぶ
# 単純な開口カーブ」ではないため、_front_zip_panel_dの中心前分割
# アルゴリズム(中心線上でちょうど2点だけがヒットする前提)が別の頂点と
# 衝突する可能性が高く、既存の検証(test_front_bodice_zip_panel_is_valid_
# across_full_measurement_range)の範囲外になる)。turtle_neckの前開き
# 対応は、台襟部分の分割方法を別途設計する将来の対応候補としてREADMEに
# 記載する。
ZIP_COMPATIBLE_NECKLINES = {"round_neck", "v_neck", "square_neck", "boat_neck", "sweetheart"}
# three_quarter(7分袖)はround9で追加。straight/curveの中間的な袖丈で、
# 既存のsleeveスケーリング則(engine/part_specs.py、幅=肩幅・丈=袖丈の
# 両方を変形)をそのまま使う。
SLEEVE_STYLES = {"straight", "curve", "puff", "bell", "cap", "three_quarter"}
# tight/mermaidはフィットしたデザインなのでウエストダーツ(apply_skirt_waist_dart)
# の対象。flare/pleated/wrap/circleは意図的にウエストで摘まずフレアで逃がす
# デザインのため対象外(engine/darts.py SKIRT_DART_ELIGIBLE_VARIATIONS参照)。
# circle(サーキュラースカート)はround9で追加。flareよりさらに裾を大きく
# 広げ、裾を直線ではなく曲線にした点でflareと区別している(honest note:
# 実際の完全な円裁ちパネルの幾何(円弧)ではなく、あくまで既存flareパネルの
# 延長線上の近似。scripts/generate_templates.py参照)。
SKIRT_STYLES = {"flare", "tight", "pleated", "wrap", "mermaid", "circle"}
# 衿・カフス・パンツ・ウエストバンドは、既定の""(標準)に加えて名前付きの
# バリエーションを選べる。空文字列は後方互換のため引き続き既定値として残す。
# convertible_collar(コンバーチブルカラー)はround9で追加。既定の""
# (標準=スタンドカラー)と紛らわしくならないよう、既存のスタンド襟とは
# 異なる「開襟・角の効いた折り返し衿」の形状にしている。
COLLAR_STYLES = {"", "shirt_collar", "peter_pan_collar", "bow_collar", "ruffle_collar", "convertible_collar"}
# button_tab(ボタンタブ付き)はround9で追加。
CUFFS_STYLES = {"", "wide", "ruffle", "button_tab"}
# pantsはskirtと異なり「フレアで逃がす」デザイン上の選択肢が無いため、
# 全variationがapply_pants_waist_dartの対象(engine/darts.py
# PANTS_DART_ELIGIBLE_VARIATIONS参照)。cropped(クロップド丈)はround9で
# 追加し、追加時にPANTS_DART_ELIGIBLE_VARIATIONSへも忘れずに加えている。
PANTS_STYLES = {"", "wide", "tapered", "shorts", "flare", "cropped"}
# round21: イラスト1枚ごとに「前から見た絵か、後ろから見た絵か」を渡せる
# ようにした。""(空文字列)は「指定なし」で、round20までと同じ扱い
# (=前として読む)。指定しなければ従来どおり動く。
ILLUSTRATION_VIEWS = {"", "front", "back"}
# contour(体に沿うコンター)はround9で追加。
WAISTBAND_STYLES = {"", "wide", "elastic", "contour"}

# 同じテンプレートを複数枚使うパーツについて、何枚目をどう呼ぶか。
# 形状が同一でも、実際の型紙では必ずこの区別をラベルとして印刷する。
PAIR_LABELS: dict[str, tuple[str, ...]] = {
    "sleeve": ("左", "右"),
    "cuffs": ("左", "右"),
    "front_pants": ("左", "右"),
    "back_pants": ("左", "右"),
    "skirt": ("前", "後"),
    "front_bodice_zip_panel": ("左", "右"),
}

# round9で追加: custom_panel(自由形状パーツ)が同一ラベルでquantity>1枚
# 指定された場合に、枚数を区別するための通し番号(丸数字)。
# MAX_CUSTOM_PANEL_QUANTITYまでしか無いのは、それ以上の枚数を1回の
# パーツ追加で要求できない(engine/custom_panel.py参照)ため。
_NUMERIC_SUFFIXES = tuple("①②③④⑤⑥⑦⑧"[:MAX_CUSTOM_PANEL_QUANTITY])

# フィットするタイプ(tight)のスカート後ろ身頃には、ウエストダーツの目安位置を
# 追加の合印として入れる（前後で仕立てが異なることを示す最小限の表現）。
SKIRT_BACK_DART_NOTCHES = [0.04, 0.09]

# round7で追加: waistband/cuffsを「独立した採寸比率」ではなく「実際に縫い
# 合わせる相手パーツ(skirt/pants・sleeve)の完成後の長さ」から直接導出する
# ようにした際に加える、クロージャー(前中心の重なり)・ゆとり分の定数。
# engine/compatibility.pyが「意図的な差分であって不整合ではない」と判定する
# 際にも同じ値を使う必要があるため、そちらを唯一の定義元とし、ここでは
# importして使う(値の重複定義を避ける)。
# engine/scaling.pyのscale_band_to_target_width()のdocstring、および
# 「パーツ間の縫い合わせ長さの整合性チェック」節(README)参照。


@dataclass(frozen=True)
class PartRequest:
    part_type: str
    variation: str
    quantity: int = 1
    # round9で追加: 「定型に当てはまらない自由形状パーツ」(engine/custom_panel.py
    # 参照)用。Noneなら従来通りTemplateDBからpart_type/variationで検索する。
    # 値がある場合はTemplateDBを検索せず、この座標をそのまま(既にcm換算・
    # 校正済みとして)使う。part_typeは常に"custom_panel"、variationは
    # 利用者が付けた自由記述のラベル(型紙上の表示名)として使う。
    custom_segments: list[tuple[str, list[float]]] | None = None
    #: round57: 生地幅に収まらないときに、縦に分けてよいか。
    #: カスタムパーツだけで使う(定型のパーツは種類ごとに決まっている)。
    allow_split: bool = False


@dataclass
class GarmentSpec:
    """生成する衣装の構成（どのパーツ種+バリエーションを何枚使うか）。"""
    parts: list[PartRequest]
    #: round30: 身頃を切り替え線(プリンセスライン)で分割するか。
    #: Trueにすると、前身頃・後ろ身頃がそれぞれ「中央」「脇」の2枚になり、
    #: ウエストの絞りはダーツではなくその縫い目が担う
    #: (engine/princess.py)。
    princess_line: bool = False

    def total_pieces(self) -> int:
        return sum(p.quantity for p in self.parts)


def build_garment_spec(neckline: str = "round_neck",
                        sleeve_style: str | None = "straight",
                        skirt_style: str | None = "flare",
                        front_zip: bool = False,
                        include_pants: bool = False,
                        pants_style: str = "",
                        include_collar: bool = False,
                        collar_style: str = "",
                        include_cuffs: bool = False,
                        cuffs_style: str = "",
                        include_waistband: bool = False,
                        waistband_style: str = "",
                        princess_line: bool = False) -> GarmentSpec:
    """UIのフォーム入力に近い形で GarmentSpec を組み立てる便利関数。

    pants_style/collar_style/cuffs_style/waistband_style は、対応する
    include_* がTrueの場合にのみ意味を持つ（Falseなら無視される）。
    既定値の""はそれぞれの標準バリエーションを表す。
    """
    if neckline not in NECKLINES:
        raise ValueError(f"neckline は {sorted(NECKLINES)} のいずれかを指定してください: {neckline!r}")

    bodice_variation = neckline
    if front_zip:
        if neckline not in ZIP_COMPATIBLE_NECKLINES:
            raise ValueError(
                f"{neckline} + 前開きファスナーの組み合わせのテンプレートは未対応です"
                f"（前開き対応ネックラインは {sorted(ZIP_COMPATIBLE_NECKLINES)} のみ）。"
            )
        bodice_variation = f"{neckline}_zip"

    if include_cuffs and not sleeve_style:
        # 以前はここが if sleeve_style: ブロックの内側にネストされたチェックだった
        # ため、袖を「なし（ノースリーブ）」にしたままカフスにチェックを入れると、
        # カフスが黙って無視されて「型紙生成に成功した」ことになっていた
        # （利用者はカフスが入っていないことに生成結果を見るまで気付けない）。
        # 前開きファスナー+タートルネックの非対応組み合わせと同様、明確なエラーにする。
        raise ValueError("カフスは袖を選択している場合のみ追加できます（袖なしの場合は指定できません）。")

    if front_zip:
        # round5より前開き前身頃を実際に中心前で分割した2枚(左右)構成に
        # 変更した(front_bodice_zip_panel、engine/darts.pyの追記
        # 「前開きファスナーの前後分割」参照)。back_bodiceは分割不要
        # (開閉するのは中心"前"のみ)なので、従来通りbodice_variationの
        # 通常の1枚構成のまま。
        parts = [
            PartRequest("front_bodice_zip_panel", neckline, 2),
            PartRequest("back_bodice", bodice_variation, 1),
        ]
    else:
        parts = [
            PartRequest("front_bodice", bodice_variation, 1),
            PartRequest("back_bodice", bodice_variation, 1),
        ]

    if sleeve_style:
        if sleeve_style not in SLEEVE_STYLES:
            raise ValueError(f"sleeve_style は {sorted(SLEEVE_STYLES)} のいずれかを指定してください: {sleeve_style!r}")
        parts.append(PartRequest("sleeve", sleeve_style, 2))
        if include_cuffs:
            if cuffs_style not in CUFFS_STYLES:
                raise ValueError(f"cuffs_style は {sorted(CUFFS_STYLES)} のいずれかを指定してください: {cuffs_style!r}")
            parts.append(PartRequest("cuffs", cuffs_style, 2))

    if skirt_style:
        if skirt_style not in SKIRT_STYLES:
            raise ValueError(f"skirt_style は {sorted(SKIRT_STYLES)} のいずれかを指定してください: {skirt_style!r}")
        parts.append(PartRequest("skirt", skirt_style, 2))  # 前スカート+後スカート

    if include_pants:
        if pants_style not in PANTS_STYLES:
            raise ValueError(f"pants_style は {sorted(PANTS_STYLES)} のいずれかを指定してください: {pants_style!r}")
        # round5でpantsをfront_pants/back_pantsに分離した(engine/darts.pyの
        # 「パンツの前後分離」追記参照)。それぞれ左右の脚で2枚ずつ、計4枚。
        parts.append(PartRequest("front_pants", pants_style, 2))  # 前パーツ 左右の脚
        parts.append(PartRequest("back_pants", pants_style, 2))  # 後ろパーツ 左右の脚

    if include_collar:
        if collar_style not in COLLAR_STYLES:
            raise ValueError(f"collar_style は {sorted(COLLAR_STYLES)} のいずれかを指定してください: {collar_style!r}")
        if neckline == "turtle_neck":
            # round15で明示的なエラーにした。タートルネックは首ぐりそのものが
            # 台襟(立ち上がり)になっており、衿を縫い付けるための首ぐり線が
            # 輪郭上に存在しない。round14まではこの組み合わせでも生成でき、
            # 台襟とは無関係な長さ(バスト比で決まる40cm前後)の衿が黙って
            # 出力されていた——縫い付ける場所が無いので、実際には使えない
            # パーツが1枚混ざった型紙になっていた。前開きファスナー+
            # タートルネックを拒否しているのと同じ理由・同じ扱いにする。
            raise ValueError(
                "タートルネックは首ぐり自体が台襟になっているため、別途の衿は"
                "追加できません(衿を縫い付ける首ぐり線が型紙上に存在しません)。"
                "衿を付ける場合は他のネックラインを選んでください。"
            )
        parts.append(PartRequest("collar", collar_style, 1))

    if include_waistband:
        if waistband_style not in WAISTBAND_STYLES:
            raise ValueError(f"waistband_style は {sorted(WAISTBAND_STYLES)} のいずれかを指定してください: {waistband_style!r}")
        parts.append(PartRequest("waistband", waistband_style, 1))

    if princess_line and front_zip:
        # 前開きの片側パネルは左右非対称で、中心前が輪郭の縁にある。
        # 切り替え線の分割はその形を前提にしていないので、黙って
        # 片方を無視せず、はっきり断る。
        raise ValueError(
            "前開きファスナーと切り替え線(プリンセスライン)は同時に指定できません。")
    return GarmentSpec(parts=parts, princess_line=princess_line)


def build_custom_panel_requests(label: str, points_cm: list[tuple[float, float]],
                                 quantity: int = 1, mirror: bool = False,
                                 allow_split: bool = False) -> list[PartRequest]:
    """校正済み(cm単位)の輪郭から、custom_panel用のPartRequestを組み立てる。

    round9で追加した「定型に当てはまらない自由形状パーツ」機能
    (engine/custom_panel.py参照)のエントリポイント。`build_garment_spec`が
    作る通常のGarmentSpecとは独立に呼び出し、返り値のリストを
    `GarmentSpec.parts`に追加して使う(app.pyの`/api/generate`参照)。

    mirror=Trueの場合、左右対称パーツ用に水平反転した2枚目のPartRequestも
    追加する(ラベルは元のラベルに"(反転)"を付けたもの。「左」「右」という
    決め打ちのラベルにしないのは、このパーツが本当に左右の関係にあるとは
    限らない=利用者次第のため)。
    """
    segments = points_to_segments(points_cm)
    requests = [PartRequest(CUSTOM_PANEL_PART_TYPE, label, quantity=quantity,
                             custom_segments=segments, allow_split=allow_split)]
    if mirror:
        mirrored_segments = points_to_segments(mirror_points_x(points_cm))
        requests.append(PartRequest(CUSTOM_PANEL_PART_TYPE, f"{label}(反転)",
                                     quantity=quantity, custom_segments=mirrored_segments,
                                     allow_split=allow_split))
    return requests


@dataclass
class FabricGroupResult:
    """1種類の生地ぶんの型紙(round54)。

    `index`が0のものは、`PipelineResult`の`nesting`/`output_files`/
    `shopping_list`と**同じ実体**を指す。生地を1種類しか使わない生成と
    2種類以上使う生成で、1つ目の出力が変わらないようにするため。
    """

    name: str
    index: int
    parts: list
    part_labels: list[str]
    nesting: NestingResult
    output_files: dict[str, str]
    shopping_list: object = None
    #: round57: 白紙の面も印刷する設定で作ったか。生地ごとの枚数も
    #: 同じ設定に従わせる(片方だけ別の数え方をすると食い違う)。
    include_empty_tiles: bool = False

    def sheet_count(self) -> int:
        from engine.pdf_export import printed_tile_cells

        _rows, _cols, cells = printed_tile_cells(
            self.nesting, include_empty_tiles=self.include_empty_tiles)
        return len(cells)

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "index": self.index,
            "part_count": len(self.parts),
            "part_labels": list(self.part_labels),
            "fabric_width_cm": self.nesting.fabric_width_cm,
            "used_length_cm": round(self.nesting.used_length_cm, 1),
            "waste_ratio": round(self.nesting.waste_ratio, 4),
            "unplaced_count": len(self.nesting.unplaced),
            "pdf_sheet_count": self.sheet_count(),
            "shopping_list": (self.shopping_list.as_dict()
                               if self.shopping_list is not None else None),
        }


@dataclass
class PipelineResult:
    job_id: str
    garment_spec: GarmentSpec
    measurements: Measurements
    scaled_parts: list[ScaledPart]
    finalized_parts: list[FinalizedPart]
    nesting: NestingResult
    output_files: dict[str, str]
    classification_log: list[ClassificationResult] = field(default_factory=list)
    elapsed_seconds: float = 0.0
    measurement_warnings: list[str] = field(default_factory=list)
    #: round32で追加: 「こう作りました」という**説明**。警告ではない。
    #:
    #: round31まで、ゆとりの選択や切り替え線の説明まで
    #: `measurement_warnings`に混ぜていたため、画面では
    #: 「⚠ 入力した採寸値の一部が、テンプレートを正確に変形できる範囲を
    #: 超えています」という赤い見出しの下に並んでいた。標準の採寸で
    #: ゆとりを選び直しただけでも赤い警告が出る状態で、実際に読むべき
    #: 警告が埋もれる(ブラウザで操作して発見)。
    design_notes: list[str] = field(default_factory=list)
    #: round35で追加: 生地幅に収まらず縦に分けたパーツ種 -> 枚数。
    #: 縫製手順に「パネルを縫い合わせる」工程を出すのに使う。
    split_panels: dict[str, int] = field(default_factory=dict)
    #: round38: 買い物メモ(engine/fabric.py)。生地幅ごとの必要量・接着芯・
    #: 縮み分・柄合わせの上乗せ・素材の提案。
    shopping_list: ShoppingList | None = None
    #: round39: 手持ちの生地で足りるかの判定(engine/stash.py)。
    #: 手持ちの寸法を渡されたときだけ入る。
    stash_verdict: StashVerdict | None = None
    #: round55: 生地を分けたときの、生地ごとの判定 [(生地名, 判定), ...]。
    #: 分けていない生成では空。手持ちの端切れは1種類の生地なので、
    #: 全パーツ合計の長さで答えると持っている生地を使わせ損ねる。
    stash_verdicts_by_fabric: list = field(default_factory=list)
    seam_allowance_cm: float = DEFAULT_SEAM_ALLOWANCE_CM
    hem_seam_allowance_cm: float | None = None
    #: round41: 裏地のパーツ一式(engine/lining.py)。裏地を付けない生成では空。
    #: 表地とは**別の生地**なので、`finalized_parts`には混ぜず、
    #: ネスティングも`lining_nesting`として別に持つ。
    lining_parts: list[FinalizedPart] = field(default_factory=list)
    lining_nesting: NestingResult | None = None
    #: round41: 裏地の型紙に付ける注記(入れた数字とその出典・入れなかったもの)。
    lining_notes: list[str] = field(default_factory=list)
    #: round54: 生地ごとの型紙(engine/fabric_groups.py)。1種類しか使わない
    #: 生成では**空**。空でないときは、1つ目がこの結果の`nesting`/
    #: `output_files`/`shopping_list`と同じものを指す。
    fabric_groups: list["FabricGroupResult"] = field(default_factory=list)

    def summary(self) -> dict:
        naive_length = self.naive_baseline_length_cm()
        return {
            "job_id": self.job_id,
            "seam_allowance_cm": self.seam_allowance_cm,
            "hem_seam_allowance_cm": self.hem_seam_allowance_cm,
            "part_count": len(self.finalized_parts),
            "unplaced_count": len(self.nesting.unplaced),
            # `nesting.py`はunplaced(配置できなかったパーツ)を検出できる作りに
            # なっている一方、以前はSVG/PDF側がresult.placedしか描画しないため
            # 配置できなかったパーツは出力から完全に消え、画面上も他の統計と
            # 同じ見た目の「配置不能パーツ」という数値表示のみだった(赤枠で
            # 目立たせている採寸クランプ警告と違い、これが実際に何を意味するか・
            # 型紙が不完全であることを利用者に伝える文言が無かった)。実際に
            # 発生すると生地を裁ってからパーツが足りないことに気づくという
            # 実害があるため、round11で明示的な警告文へ変えた
            # (measurement_warningsと同じ表示形式)。
            #
            # 【round35で訂正】round11当時ここには「1200通り総当たりした結果
            # unplacedは発生しない(到達不能)」と書いていたが、round9で入った
            # サーキュラースカートによってその時点で既に到達可能になっていた
            # (ヒップ143cm以上、110通り中70通りでスカートが型紙から消えていた)。
            # round35で`engine/panel_split.py`を足し、分けてよい種類のパーツは
            # 縦に分けて収めるようにした。それでも分けられない種類・分けても
            # 収まらない幅では発生するので、**この警告は到達可能**である。
            "unplaced_warnings": self._unplaced_warnings(),
            "fabric_width_cm": self.nesting.fabric_width_cm,
            "used_length_cm": round(self.nesting.used_length_cm, 1),
            # round53: A4で何枚印刷することになるか。
            #
            # コンビニで印刷する人にとっては、これがそのまま値段(1枚20円)と
            # 待ち時間になる。家のプリンタでも「用紙が足りるか」を出かける前に
            # 知りたい。PDFを開くまで分からないのは遅すぎる。
            # 数え方はPDFを作る側と同じ関数(printed_tile_cells)を使う。
            "pdf_sheet_count": self.pdf_sheet_count(),
            # round57: どの用紙で数えた枚数かを、画面が言えるようにする。
            "paper": self.paper_name,
            "waste_ratio": round(self.nesting.waste_ratio, 4),
            "rotation_used": any(p.rotated for p in self.nesting.placed),
            "elapsed_seconds": round(self.elapsed_seconds, 2),
            "output_files": self.output_files,
            "ai_contribution": self.ai_contribution_note(),
            # round50: バッジの表示に使う。文を解釈させない(上記docstring参照)。
            "ai_engine": self.ai_engine(),
            "darts_applied": sum(p.dart_count for p in self.finalized_parts),
            # round65: **どのパーツに何本入ったか**。round64まで画面が
            # 受け取っていたのは合計(`darts_applied`)だけで、
            # 「身頃のウエスト/脇ダーツ、タイトスカートのウエストダーツなど」
            # というパーツ名は画面のHTMLに手書きしてあった。14通りで実測すると、
            # 文が出る11通りのうち**10通りで、挙げたパーツにダーツは
            # 1本も入っていない**(標準体型ではタイトスカートにも入らない/
            # パンツに8本入っても文はパンツに触れない)。
            # 縫う順番(engine/assembly.py)は
            # 同じことを`dart_count`から作っていたので、画面にも同じ形で渡す。
            "darts_by_part": [
                {"name": p.name_without_dart_count, "dart_count": p.dart_count}
                for p in self.finalized_parts if p.dart_count
            ],
            "measurement_warnings": self.measurement_warnings,
            "design_notes": self.design_notes,
            # round35: どのパーツを何枚に分けたか。分割は`design_notes`の
            # 日本語文でも伝えているが、それは**人間に読ませる文**であって、
            # 画面やAPI利用者が「分割が起きたか」を判定する手がかりにはならない
            # (文言を直すたびに壊れる)。実際、追加した直後は`summary()`に
            # 出しておらず、画面側から分割の有無が分からなかった。
            "split_panels": dict(self.split_panels),
            # round38: 買い物メモ(engine/fabric.py)。
            "shopping_list": self.shopping_list.as_dict() if self.shopping_list else None,
            # round39: 手持ちの生地の判定(engine/stash.py)。
            "stash_verdict": self.stash_verdict.as_dict() if self.stash_verdict else None,
            "stash_verdicts_by_fabric": ([{"fabric_name": name, **verdict.as_dict()}
                                           for name, verdict in self.stash_verdicts_by_fabric]
                                          if self.stash_verdicts_by_fabric else None),
            # round41: 裏地(engine/lining.py)。付けない生成では空・None。
            # round54: 生地ごとの型紙。1種類しか使わない生成ではNone
            # (画面は「あるときだけ」生地ごとの表に切り替える)。
            "fabric_groups": ([g.as_dict() for g in self.fabric_groups]
                               if self.fabric_groups else None),
            "lining": {
                "part_count": len(self.lining_parts),
                "parts": [{"display_name": p.display_name,
                            "identifier": p.identifier,
                            "width_cm": round(p.width_cm, 1),
                            "height_cm": round(p.height_cm, 1)}
                           for p in self.lining_parts],
                "fabric_width_cm": (self.lining_nesting.fabric_width_cm
                                     if self.lining_nesting else None),
                "used_length_cm": (round(self.lining_nesting.used_length_cm, 1)
                                    if self.lining_nesting else None),
                "unplaced_count": (len(self.lining_nesting.unplaced)
                                    if self.lining_nesting else 0),
                "notes": list(self.lining_notes),
            } if self.lining_parts else None,
            # round33: 縫製手順(engine/assembly.py)。型紙は出るが縫う順番が
            # どこにも書いていなかった、という不足への対応。
            "assembly_steps": [s.as_dict() for s in self.assembly_steps()],
            "compatibility_warnings": [w.as_dict() for w in self.compatibility_warnings()],
            "naive_used_length_cm": round(naive_length, 1),
            "naive_waste_ratio": round(self.naive_baseline_waste_ratio(naive_length), 4),
            "parts": [
                {
                    "display_name": p.display_name,
                    # round32: 画面に出す名前を日本語にしたので、
                    # 「どのパーツか」を機械が特定するための値を別に出す
                    # (テストやAPI利用者が表示名の文字列に依存すると、
                    #  ラベルを直すたびに壊れる)。
                    "part_type": p.part_type,
                    "variation": p.variation,
                    "identifier": p.identifier,
                    "cutting_note": p.cutting_note,
                    # round65: 表示名の中に「[ダーツ4本]」と書いてはあるが、
                    # 機械が読むには文字列を切り出すしかなかった。数で出す。
                    "dart_count": p.dart_count,
                    "width_cm": round(p.width_cm, 1),
                    "height_cm": round(p.height_cm, 1),
                }
                for p in self.finalized_parts
            ],
        }

    def assembly_steps(self) -> list:
        """縫製手順(round33で追加、engine/assembly.py参照)。"""
        from .assembly import assembly_steps_for_result
        return assembly_steps_for_result(self)

    def compatibility_warnings(self) -> list[CompatibilityWarning]:
        """縫い合わせ長さの不整合(round6で追加、engine.compatibility参照)。"""
        return check_seam_compatibility(self.finalized_parts)

    #: round57: 白紙の面も印刷する設定で作ったか(画面の枚数もこれに従う)。
    include_empty_tiles: bool = False
    #: round57: 使った用紙("A4"/"A3")。画面に出す枚数もこれに従う。
    paper_name: str = "A4"
    #: round57: **実際に使われた**丈(cm)。イラストから読み取った値も含む。
    #: これを生成履歴に残すと、画像を保存しなくても同じ型紙を作り直せる。
    resolved_design_lengths: dict[str, float] = field(default_factory=dict)

    def pdf_sheet_count(self) -> int:
        """A4分割PDFが実際に印刷する枚数(表紙・買い物メモ・縫う順番を除く)。

        表紙に書く枚数と必ず同じ数にするため、PDFを作る側と同じ関数から出す。
        """
        from engine.pdf_export import printed_tile_cells

        _rows, _cols, cells = printed_tile_cells(
            self.nesting, include_empty_tiles=self.include_empty_tiles,
            paper=get_paper(self.paper_name))
        return len(cells)

    def _unplaced_warnings(self) -> list[str]:
        """配置できなかったパーツがある場合、その旨を明示する警告文を返す。

        `measurement_clamp_warnings`と同じ位置づけの、利用者へ正直に開示する
        ための文言。空リストなら配置できなかったパーツは無い(通常はこちら)。
        """
        if not self.nesting.unplaced:
            return []
        names = "・".join(p.display_name for p in self.nesting.unplaced)
        # round56: 「最大」に**選ばれた幅**を書いていたので、150cmまで
        # 試して全部だめだった場合でも「最大110cm」と出ていた。
        # 読んだ人は「150cm幅を買えば入る」と受け取ってしまう。
        # 実際に試した幅の最大を書く。
        widest = max(self.nesting.tried_widths_cm or (self.nesting.fabric_width_cm,))
        # round57: 逃げ道を具体的に書く。
        #
        # round56までの文は「採寸値を見直すか、手作業でこのパーツだけ
        # 別途作成してください」で終わっていた。幅173cmのマントに対して
        # **採寸値は関係がない**し、「手作業で」は何も解決していない。
        # 実際の答えは「分けて縫い合わせる」で、この製品はもう分けられる
        # (engine/panel_split.py)。何枚に分ければ収まるかまで書く。
        splittable = [p for p in self.nesting.unplaced
                       if p.part_type == CUSTOM_PANEL_PART_TYPE]
        advice = "採寸値を見直すか、パーツの形を小さくしてください。"
        if splittable:
            counts = [panels_needed(p.width_cm, widest, self.seam_allowance_cm)
                       for p in splittable]
            count = max(counts) if counts else 0
            if 2 <= count <= MAX_PANELS:
                advice = (
                    f"{count}枚に分けて縫い合わせれば、幅{widest:.0f}cmの生地に"
                    "収まります。マントのように、そこに縫い目が入ってよい"
                    "パーツなら、そのパーツの「収まらないときは分割する」を"
                    "オンにして生成し直してください"
                    "（EVAフォームの装甲のように縫い目を入れられないものは、"
                    "分けずに素材の方を継いでください）。")
        return [
            f"{names}は、どの生地幅(最大{widest:.0f}cm)にも"
            "収まらず型紙に含まれていません。この型紙のSVG/PDFには上記のパーツが"
            f"描かれていないため、そのまま裁断すると衣服が完成しません。{advice}"
        ]

    def naive_baseline_length_cm(self) -> float:
        """比較用の素朴なベースライン: 各パーツを1枚ずつ縦に積んだだけの
        (パーツ同士を横に並べて詰め合わせる工夫を一切しない)必要生地丈。

        実際のネスティング(nesting.used_length_cm)がこれよりどれだけ
        短く収まっているかで、詰め合わせの効果を分かりやすく示す。
        あくまで「詰めない場合はこうなる」という参考値であり、実際の
        裁断現場での標準的な配置手法と比較したものではない。
        """
        return sum(p.height_cm for p in self.finalized_parts)

    def naive_baseline_waste_ratio(self, naive_length_cm: float | None = None) -> float:
        if naive_length_cm is None:
            naive_length_cm = self.naive_baseline_length_cm()
        fabric_area = self.nesting.fabric_width_cm * naive_length_cm
        if not fabric_area:
            return 0.0
        return max(0.0, 1.0 - (self.nesting.total_part_area_cm2 / fabric_area))

    def ai_engine(self) -> str:
        """このジョブで実際に判定を行ったものを、機械が読める形で返す。

        `"none"`(AIを使っていない) / `"mock"`(鍵が無いときの簡易判定) /
        `"claude"`(実際にAPIを呼んだ)のいずれか。

        【round50で見つけた実バグ】画面のバッジは
        `classification_log.length > 0` だけを見て「AI使用」と出していた。
        `get_default_classifier()` は ANTHROPIC_API_KEY が無ければ
        MockPartClassifier に落ちるので、**鍵の無い環境では、AIを一度も
        呼んでいないのに緑の「AI使用」が出ていた**。すぐ下の
        `ai_contribution_note()` は「簡易判定(モック)」と正しく書き分けて
        いたのに、目立つ方のバッジが食い違っていた。
        画面に日本語の文を解釈させるのではなく、判定に使える値を渡す
        (round35で「分割が起きたか」を`split_panels`として出したのと同じ方針)。
        """
        if not self.classification_log:
            return "none"
        modes = {c.raw.get("mode", "claude") if c.raw else "claude"
                 for c in self.classification_log}
        if modes == {"mock"}:
            return "mock"
        return "claude"

    def ai_contribution_note(self) -> str:
        """このジョブでAIが実際に何をしたかを、誇張せずに一言で説明する。

        「デザイン画→型紙の完全自動生成」という謳い文句と実装内容の間に
        ギャップが生まれやすい部分なので、生成結果に必ず添えて誤解を防ぐ。
        """
        if not self.classification_log:
            return (
                "このジョブではAIは使用していません（手動で選んだパーツ構成を、"
                "テンプレート型紙+ルールベースの体型スケーリングのみで生成しました）。"
            )
        modes = {c.raw.get("mode", "claude") if c.raw else "claude" for c in self.classification_log}
        engine_desc = "簡易判定(モック)" if "mock" in modes and len(modes) == 1 else "Claude API"
        return (
            f"AI({engine_desc})が行ったのは「切り出した各パーツ領域が"
            f"{len(self.classification_log)}件、どのテンプレート種類に近いか」の判定のみです。"
            "型紙の輪郭そのものはテンプレート型紙+体型スケーリング(ルールベース)で生成しており、"
            "AIが型紙形状を直接生成しているわけではありません。"
        )


@dataclass
class MultiSizeResult:
    """複数サイズを一括生成した結果(round5「複数サイズの一括生成」で追加)。

    `results`は{サイズ名: そのサイズのPipelineResult}。各サイズは通常の
    1サイズ生成と全く同じ経路(`_build_from_spec`)で個別に生成されており、
    複数サイズ間で型紙の輪郭やダーツを共有・使い回す処理は一切していない
    (それぞれ独立に採寸→スケーリング→縫い代→ネスティングまで行う。
    正直な設計として、「1回の生成の中でサイズ間の輪郭に一貫性を持たせる
    高度なグレーディング処理」ではなく、「グレーディングした採寸値で
    単純に複数回生成する」だけであることを明記する)。
    """
    sizes: list[str]
    base_measurements: Measurements
    results: dict[str, PipelineResult]
    bundle_job_id: str
    zip_path: str
    #: round7で追加。この一括生成で実際に使われたカスタムグレーディング
    #: ルール(利用者が指定した項目だけを含む、STANDARD_SIZE_GRADE_CMからの
    #: 上書き分)。Noneまたは空辞書なら既定値をそのまま使ったことを示す。
    custom_grade_cm: dict[str, float] | None = None

    def effective_grade_cm(self) -> dict[str, float]:
        """実際に使われた部位ごとの刻み幅(既定値にカスタム上書きを適用した
        もの)を返す(round7で追加)。生成結果に添えることで、利用者が
        「このサイズ展開が実際にどの刻み幅で作られたか」を後から確認できる
        ようにする。
        """
        effective = dict(STANDARD_SIZE_GRADE_CM)
        if self.custom_grade_cm:
            effective.update(self.custom_grade_cm)
        return effective

    def size_consistency_warnings(self) -> list[str]:
        """サイズ間でダーツ本数が不連続に変化していないかの診断
        (round6で追加、engine.measurements.detect_dart_count_inconsistencies参照)。
        """
        dart_counts_by_size = {
            size: sum(p.dart_count for p in result.finalized_parts)
            for size, result in self.results.items()
        }
        return detect_dart_count_inconsistencies(dart_counts_by_size)

    def grading_precision_notes(self) -> list[str]:
        """グレーディングの絶対cm刻みが、baseの体型に対して相対的に大きな
        変化率になっている項目の開示(round6で追加、
        engine.measurements.grading_relative_change_notes参照)。round7で
        カスタムグレーディングルールに対応(実際に使われた刻み幅で診断する)。
        """
        return grading_relative_change_notes(self.base_measurements, self.sizes,
                                              grade_cm=self.custom_grade_cm)

    def totals(self) -> dict:
        """全サイズを合わせて「何枚刷るか・何を買うか」(round69で追加)。

        【なぜ要るか】サイズ展開を使うのは、同じ衣装を何人ぶんか作る人
        である(コスプレなら合わせや団体衣装)。ところがround68まで、
        画面に出ていたのはサイズごとのパーツ数・布ロス率・生地丈だけで、

          * 全部で何枚刷るのか(実測: S/M/Lで**143枚**)
          * 合わせて生地を何m買うのか
          * 接着芯・ファスナーがいくつ要るのか

        がどこにも出ていなかった。3人ぶん作る人にとって、印刷枚数は
        そのままコンビニの代金であり、生地は一度に買う量である。

        【正直な足し方】生地は**サイズごとに別々に裁つ前提**で足している。
        1枚の布に全サイズを詰め合わせ直した値ではない(そうすれば短くなる
        余地はあるが、この製品はサイズをまたいだ詰め合わせをしていない)。
        `by_width`は生地幅ごとの合計で、`recommended_width_cm`は
        **合計がいちばん短くなる幅**である。サイズごとのおすすめ幅とは
        違うことがある(1本の反物で買うなら、合計で選ぶのが正しい)。
        """
        summaries = {size: self.results[size].summary() for size in self.sizes
                     if size in self.results}
        # **すべてのサイズが収まった幅だけ**を候補にする。1サイズでも
        # 収まらない幅の合計を出すと、「その幅で全員ぶん作れる」と読める。
        # 1つも無ければ合計を出さない——足りない数字を出すより、
        # 出さない方を選ぶ(サイズごとの表は別に出ている)。
        candidates: dict[float, int] = {}
        for summary in summaries.values():
            memo = summary.get("shopping_list") or {}
            for option in memo.get("widths", []):
                candidates.setdefault(option["width_cm"], 0)
        for width in list(candidates):
            lengths = []
            for summary in summaries.values():
                memo = summary.get("shopping_list") or {}
                option = next((o for o in memo.get("widths", [])
                               if o["width_cm"] == width), None)
                if option is None or not option.get("all_parts_fit"):
                    lengths = []
                    break
                lengths.append(option["buy_length_cm"])
            if lengths:
                candidates[width] = sum(lengths)
            else:
                del candidates[width]
        recommended = (min(candidates, key=lambda w: (candidates[w], w))
                       if candidates else None)
        zippers = [{"size": size,
                    "opening_cm": (summary.get("shopping_list") or {})
                                  .get("front_opening_cm")}
                   for size, summary in summaries.items()
                   if (summary.get("shopping_list") or {}).get("front_opening_cm")]
        return {
            "size_count": len(summaries),
            "pdf_sheet_count": sum(s.get("pdf_sheet_count") or 0
                                    for s in summaries.values()),
            "paper": next((s.get("paper") for s in summaries.values()), None),
            "fabric_by_width_cm": {str(w): total
                                    for w, total in sorted(candidates.items())},
            # どの幅でも全サイズが収まらなかったか。画面はこのとき
            # 「合計は出せません」と言う(黙って空欄にしない)。
            "no_width_fits_every_size": not candidates,
            "fabric_recommended_width_cm": recommended,
            "fabric_recommended_length_cm": (candidates.get(recommended)
                                              if recommended else None),
            "interfacing_length_cm": sum(
                (s.get("shopping_list") or {}).get("interfacing_length_cm") or 0
                for s in summaries.values()),
            "interfacing_width_cm": next(
                ((s.get("shopping_list") or {}).get("interfacing_width_cm")
                 for s in summaries.values()
                 if (s.get("shopping_list") or {}).get("interfacing_length_cm")),
                None),
            "zippers": zippers,
        }

    def summary(self) -> dict:
        return {
            "bundle_job_id": self.bundle_job_id,
            "sizes": self.sizes,
            "base_measurements": self.base_measurements.as_dict(),
            "results": {size: result.summary() for size, result in self.results.items()},
            "size_consistency_warnings": self.size_consistency_warnings(),
            "grading_precision_notes": self.grading_precision_notes(),
            "grade_cm_used": self.effective_grade_cm(),
            "custom_grade_cm_applied": bool(self.custom_grade_cm),
            # round69: 全サイズを合わせた「何枚刷るか・何を買うか」。
            "totals": self.totals(),
        }


def _top_opening_length_cm(segments: list) -> float:
    """`ScaledPart.segments`(まだfinalize_part前)から、上端(ウエストライン)
    の開き長さを求める。compatibility.pyのwaist_opening_length()は
    FinalizedPart(`.stitch_line`属性を持つ)を想定しているため、finalize前の
    生のsegmentsに対しても同じロジックを使えるよう、`.stitch_line`だけを
    持つ最小限のオブジェクトでラップする(finalize_part()もstitch_lineを
    `segments_to_polyline(segments)`としてそのまま使っているだけなので、
    finalize前後で値は変わらない)。
    """
    return waist_opening_length(SimpleNamespace(stitch_line=segments_to_polyline(segments)))


def _bottom_opening_length_cm(segments: list) -> float:
    """`_top_opening_length_cm`の袖口(下端)版。"""
    return hem_or_wrist_opening_length(SimpleNamespace(stitch_line=segments_to_polyline(segments)))


def _waistband_target_width_cm(scaled_by_type: dict[str, list[ScaledPart]]) -> float | None:
    """waistbandの目標幅(cm)を、実際に縫い合わせる相手(skirtまたはpants)の
    完成後のウエストライン長さの合計から求める(round7追加、
    scale_band_to_target_width()参照)。

    skirtとpantsが両方とも指定された(通常のUIでは想定しないが、APIレベルの
    GarmentSpecとしては構成可能な)場合は、どちらか一方に決め打ちする必要が
    あり、より一般的な組み合わせであるskirtを優先する(正直な単純化として
    ここに明記する)。どちらも無ければNoneを返し、呼び出し側で
    scale_template()による従来通りの独立スケーリングにフォールバックする。
    """
    skirt_scaled = scaled_by_type.get("skirt")
    if skirt_scaled:
        total = sum(_top_opening_length_cm(sp.segments) for sp in skirt_scaled)
        return total + WAISTBAND_CLOSURE_EASE_CM

    pants_scaled = scaled_by_type.get("front_pants", []) + scaled_by_type.get("back_pants", [])
    if pants_scaled:
        total = sum(_top_opening_length_cm(sp.segments) for sp in pants_scaled)
        return total + WAISTBAND_CLOSURE_EASE_CM

    return None


#: round76: 「相手の出来上がり寸法に合わせて引く」パーツの一覧。
#:
#: 変形を3回に分ける理由そのものである(`_scale_every_part`参照):
#: 2回目に袖・衿・フード、3回目に帯を引く。round75まではこの一覧が
#: `_scale_every_part`の中のローカル変数だったため、**外から確かめられ
#: なかった**。下の`PARTNER_FITTED_PART_TYPES`と食い違っていないことを
#: `tests/test_round76_partner_fit.py`が見張る。
SLEEVE_STAGE_PART_TYPES = ("sleeve", "collar", "hood")
BAND_PART_TYPES = ("waistband", "cuffs")

#: round76: 「相手の出来上がり寸法に合わせて引く」パーツと、その相手。
#:
#: 値は (相手のかたまりの並び, 何に合わせるのか) 。かたまりはそれぞれ
#: 「このうち1つでもあればよい」という意味で、**全部のかたまりが揃って
#: 初めて**目標寸法を計算できる(袖なら前身頃と後ろ身頃の両方が要る)。
PARTNER_FITTED_PART_TYPES: dict[str, tuple[tuple[frozenset[str], ...], str]] = {
    "sleeve": ((frozenset({"front_bodice", "front_bodice_zip_panel"}),
                frozenset({"back_bodice"})), "身頃の袖ぐり"),
    "collar": ((frozenset({"front_bodice", "front_bodice_zip_panel"}),
                frozenset({"back_bodice"})), "身頃の首ぐり"),
    "hood": ((frozenset({"front_bodice", "front_bodice_zip_panel"}),
              frozenset({"back_bodice"})), "身頃の首ぐり"),
    "waistband": ((frozenset({"skirt", "front_pants", "back_pants"}),),
                  "スカート・パンツのウエスト"),
    "cuffs": ((frozenset({"sleeve"}),), "袖口"),
}


def partner_is_present(part_type: str,
                       scaled_by_type: dict[str, list]) -> bool:
    """このパーツの「合わせる相手」が、この型紙に揃っているか(round76)。"""
    entry = PARTNER_FITTED_PART_TYPES.get(part_type)
    if entry is None:
        return False
    groups, _label = entry
    return all(any(scaled_by_type.get(t) for t in group) for group in groups)


def silent_fallback_note(part_type: str, variation: str,
                         scaled_by_type: dict[str, list]) -> str | None:
    """**相手がいるのに**相手に合わせられなかったときの説明(round76)。

    相手がいないなら、採寸比で引くのは正しい(合わせる相手が無いので)。
    ここが返すのは「相手はいるのに合わせられなかった」場合だけである。

    【なぜこれが要るか】round74(袖ぐり)とround75(首ぐり)で、**まったく
    同じ形の不具合**を2回直した:

        前開きにすると相手の寸法を測れず、目標がNoneになり、
        呼び出し側が採寸比の独立スケーリングへ**黙って**落ちる。

    どちらも「出来上がりが合わない」以外に何の手がかりも残さなかった。
    round58で署名の突き合わせを足したときと同じ考えで、3度目が起きても
    **黙って**は起きないようにする。同時に
    `tests/test_round76_partner_fit.py`が、作れる組み合わせを総当たり
    して「相手がいるのに落ちた」が1件も無いことを見張る。
    """
    entry = PARTNER_FITTED_PART_TYPES.get(part_type)
    if entry is None or not partner_is_present(part_type, scaled_by_type):
        return None
    _groups, target_label = entry
    name = part_type_label(part_type)
    return (f"{name}を{target_label}に合わせられませんでした。"
            f"この{name}は採寸の比率だけで拡大縮小してあります"
            f"（{target_label}の長さを測る方法が、この形にはまだありません）。"
            f"縫い付ける前に、{target_label}と長さを見比べてください。")


def _with_drop_shoulder(scaled: ScaledPart, part_type: str,
                        shoulder_drop_cm: float | None,
                        run: "_DropShoulderRun") -> ScaledPart:
    """身頃にドロップショルダーを当てた`ScaledPart`を返す(round76)。

    指定が無いパーツ・当てられない形ではそのまま返す。当てられなかった
    ことは`failures`に残し、呼び出し側が利用者へ開示する——黙って
    セットインスリーブの型紙を出さない。

    **変形のいちばん最後**に当てる。補正(round40/43)は肩先を動かす操作
    なので、先にドロップを当てると補正が「動いたあとの肩先」を基準に
    してしまう。
    """
    if not shoulder_drop_cm or part_type not in DROP_SHOULDER_PART_TYPES:
        return scaled
    dropped = apply_drop_shoulder(
        scaled.segments, list(scaled.fit_anchors_scaled),
        list(scaled.fit_anchors_y_scaled), shoulder_drop_cm)
    if dropped is None:
        run.failures.add(part_type)
        return scaled
    run.results.append(dropped)
    return replace(scaled, segments=dropped.segments,
                   underarm_y_cm=dropped.underarm_y_cm)


@dataclass
class _DropShoulderRun:
    """このラウンドの生成で、ドロップショルダーをどう当てたかの記録(round76)。

    注記を組み立てるのに要るものをまとめて持つ。`armhole_per_arm_cm`を
    ここに入れているのは、**前開きの袖ぐりは`scaled_by_type`だけでは
    測れない**ため(割る前の前身頃が要る。`_armhole_per_arm_cm`参照)。
    注記の側でもう一度測ろうとすると、前開きのときだけ袖山の注記が
    黙って消える(実測で消えていた)。
    """
    results: list = field(default_factory=list)
    failures: set = field(default_factory=set)
    armhole_per_arm_cm: float | None = None


def _drop_shoulder_disclosure(shoulder_drop_cm, drop_run,
                              scaled_by_type, measurements) -> list[str]:
    """ドロップショルダーをどう引いたかの注記(round76)。

    当てられなかった身頃があれば、そのことも書く。黙って
    セットインスリーブの型紙を出すと、指定した数字と違うものが出たこと
    だけが残る。
    """
    notes: list[str] = []
    if shoulder_drop_cm and drop_run.results:
        sleeves = scaled_by_type.get("sleeve") or []
        cap_height = None
        if sleeves:
            poly = segments_to_polyline(sleeves[0].segments)
            cap_height = poly[0][1] - min(y for _x, y in poly)
        notes.extend(drop_shoulder_notes(
            shoulder_drop_cm, drop_run.armhole_per_arm_cm, cap_height,
            upper_arm_ignored=(measurements.upper_arm is not None
                               and bool(sleeves))))
    for part_type in sorted(drop_run.failures):
        notes.append(
            f"{part_type_label(part_type)}にはドロップショルダーを"
            "当てられませんでした(肩先・首の付け根・脇の基準点から"
            "袖ぐりを取り出せない形でした)。この型紙は肩先を出さずに"
            "引いています。")
    return notes


def _underarm_y_of(scaled: ScaledPart) -> float | None:
    """このパーツの「脇の下の高さ」(cm)。round76。

    ドロップショルダーで下げた場合はその値、下げていなければバスト線。
    袖ぐりをどこで打ち切るかの判定(`engine/compatibility.py`の
    `side_seam_edges`)と合印の位置は、必ず同じ値を使う必要がある。
    """
    return (scaled.underarm_y_cm if scaled.underarm_y_cm is not None
            else scaled.bust_line_y_cm)


def _armhole_per_arm_cm(scaled_by_type: dict[str, list[ScaledPart]],
                         unsplit_fronts: list | None = None) -> float | None:
    """実際に生成された身頃から、片腕ぶんの袖ぐり周長(cm)を求める(round24)。

    `_sleeve_target_cap_cm`が使っていた計算をそのまま切り出したもの。
    round24で袖山の高さも袖ぐりに比例させるようになり、目標の袖山長だけで
    なく袖ぐりそのものの値が要るようになったため
    (`engine/scaling.py`の`scale_sleeve_to_cap_length`参照)。
    """
    fronts = scaled_by_type.get("front_bodice", [])
    backs = scaled_by_type.get("back_bodice", [])
    # round74: 前開きの身頃(front_bodice_zip_panel)でも袖ぐりを測る。
    #
    # 【round73まで何が起きていたか】ここは`front_bodice`しか見ていなかった。
    # 前開きを選ぶと前身頃は`front_bodice_zip_panel`2枚になるので`fronts`が
    # 空になり、この関数はNoneを返す。呼び出し側はそれを「身頃が無い」と
    # 受け取って、袖を**肩幅比の独立スケーリング**へ落とす。つまり
    # **前開きにした瞬間、袖が袖ぐりと無関係な寸法になる**。
    #
    # 実測(バスト82、同じ設定で前身頃だけ差し替え):
    #
    #     前身頃      設定           後ろ袖ぐり   袖山線
    #     普通        標準             41.34      43.62
    #     前開き      標準             41.34      42.60   ← 1.0cm 小さい
    #     普通        重ね着(+18cm)    43.70      46.54
    #     前開き      重ね着(+18cm)    43.70      42.60   ← 3.9cm 小さい
    #
    # 袖ぐりが広がっても袖は1mmも動かない。しかも
    # `engine/compatibility.py`のチェック5は`front_bodice_zip_panel`の
    # 袖ぐりを測れないので**警告も出ない**。前を開けただけで袖が入らなく
    # なり、誰も何も言わない状態だった。
    #
    # 測り方は「割る前の前身頃を測る」。`_front_zip_panel_d`
    # (scripts/generate_templates.py)は対称な前身頃を中心前で割ったもので、
    # 片側パネルが持つ袖ぐりは、割る前の左右どちらかとまったく同じ形である。
    # 変形の基準点(`側`・`肩`)も両者で同じ値へ写る(実測で確認)。輪郭から
    # 直接測ろうとすると「非対称な輪郭のどこが肩先か」という判定を新しく
    # 足すことになり、そこを外すと今度は静かに別の値が出る。
    if not fronts:
        fronts = list(unsplit_fronts or ())
    if not fronts or not backs:
        return None
    # round35: 脇の下の高さ(バストライン)を一緒に渡す。
    #
    # 【なぜ必要か】`armhole_length`は「輪郭の先頭から最初の脇線まで」を
    # 袖ぐりとして測る。round31で脇線の判定に脇の下の高さを使えるように
    # したので、**それを渡すかどうかで測り方が変わる**。ここは袖の型紙を
    # 作るために測る側で、`engine/compatibility.py`のチェック5は出来上がりを
    # 測る側。両者が違う測り方をすると、作った袖に対して「袖ぐりに合って
    # いません」と警告が出る。実測で368通り中288通りで誤警告が出た。
    # 同じ値を渡して、必ず同じ測り方にする。
    def _measure(part_type: str, sp) -> float | None:
        return armhole_length(SimpleNamespace(
            part_type=part_type,
            stitch_line=segments_to_polyline(sp.segments),
            underarm_y_cm=sp.underarm_y_cm,
            reference_lines=([("BL", [(0.0, sp.bust_line_y_cm)])]
                             if sp.bust_line_y_cm is not None else [])))

    front_lengths = [_measure("front_bodice", sp) for sp in fronts]
    back_lengths = [_measure("back_bodice", sp) for sp in backs]
    if not all(v is not None for v in front_lengths + back_lengths):
        return None
    # armhole_lengthは1パーツぶん(左右2つ分)を返すので、片腕ぶんは前後の
    # 合計を2で割った値(compatibility.pyのチェック5と同じ換算)。
    return (sum(front_lengths) + sum(back_lengths)) / 2.0


#: 出来上がりのウエストが「採寸+ゆとり」からこれ以上離れていたら開示する(cm)。
#: ダーツ2本×左右で摘める量には上限があり(engine/darts.pyの
#: MAX_DIAMOND_INTAKE_PER_HALF_CM)、くびれの強い体型では摘みきれない。
WAIST_SLACK_DISCLOSURE_CM = 3.0


def _unprintable_fabric_name_warnings(groups: list) -> list[str]:
    """生地の名前に、型紙へ印刷できない文字が入っている場合に伝える(round54)。

    生地の名前は型紙の表紙と**全タイルページの隅**に印字される。
    落ちる文字があると、2つの山のどちらがどの生地の型紙かを見分ける
    手がかりが欠けることになる。

    よく使う色・素材の漢字は`COMMON_FABRIC_NAME_CHARS`でフォントに
    入れてあるので(実測: 「紺サテン」「金ラメ」「エナメル黒」はいずれも
    round54以前は色が落ちていた)、ここに引っかかるのは珍しい字を
    使ったときだけになる。
    """
    notes: list[str] = []
    for group in groups:
        missing = unprintable_characters(group.name)
        if not missing:
            continue
        printed = "".join(ch for ch in group.name
                           if ch not in set(missing)) or "(空)"
        notes.append(
            f"生地の名前「{group.name}」のうち {'・'.join(missing)} は型紙に"
            f"印刷できない文字のため、型紙には「{printed}」と印字されます。"
            "軽量フォントを埋め込んでいるためです。"
            "名前を変えると、そのまま印字できます。")
    return notes


def _unprintable_label_warnings(finalized_parts: list) -> list[str]:
    """型紙に印刷できない文字がパーツ名に入っている場合に伝える(round36)。

    【何が起きていたか】型紙PDFに埋め込んでいるフォントはサブセットなので、
    収録外の文字は**何も描かれずに黙って消える**。固定文言は
    `scripts/build_pattern_label_font.py`が集めるので防げるが、カスタム
    パーツの名前は利用者が自由に入力するため、防ぎようがない。
    実測: 「薔薇の装甲」と名付けると、薔・薇・装・甲がすべて落ちて、
    型紙には**「の」とだけ印刷される**。警告は一切出なかった。

    全漢字を収録すればフォントが10MB超になり、A4分割PDFを配るという
    この製品の形に合わない。ならば直せるのは「黙って落とす」ところだけで、
    落ちる文字を先に伝える。布を裁つ前に名前を変えれば済む話である。
    """
    notes: list[str] = []
    for part in finalized_parts:
        name = getattr(part, "display_name", "") or ""
        missing = unprintable_characters(name)
        if not missing:
            continue
        printed = "".join(ch for ch in name if ch not in set(missing)) or "(空)"
        notes.append(
            f"パーツ名「{name}」のうち {'・'.join(missing)} は型紙に印刷できない"
            f"文字のため、型紙の上には「{printed}」と印字されます。"
            "ひらがな・カタカナ・英数字と、よく使う漢字だけを埋め込んだ"
            "軽量フォントを使っているためです。"
            "名前を変えると、そのまま印字できます。")
    return notes


def _anchor_x(scaled, role: str) -> float | None:
    """変形後の座標系での基準点(`data-fit-x`)のx。無ければ None。"""
    return next((x for r, x in getattr(scaled, "fit_anchors_scaled", ())
                 if r == role), None)


def _facing_width_cm(scaled) -> float:
    """見返し(中心前より外側の折り返し代)の幅(cm)。無ければ0。

    round67。前開きのパネルは、輪郭に見返し分の生地を含んでいる
    (`scripts/generate_templates.py`の`_front_zip_panel_d`)。見返しは
    **折り返して裏へ回る**ので、出来上がりの胴回りには入らない。
    輪郭の幅をそのまま胴回りとして数えると、その分だけ「ゆるい」と
    言ってしまう(実測: 左右2枚で8.0cm)。

    幅は基準点`cut`と`cf`の距離。体型によらず一定に保たれる
    (`engine/bodice_fit.py`の`build_x_map`)ので、変形後の座標で測れば
    そのまま出来上がりの見返し幅になる。
    """
    cut = _anchor_x(scaled, "cut")
    cf = _anchor_x(scaled, "cf")
    if cut is None or cf is None:
        return 0.0
    return abs(cf - cut)


def _half_panel_anchors(scaled) -> tuple[float, float] | None:
    """左右非対称な「半身ぶん」のパーツなら (中心前x, 脇線x) を返す(round67)。

    見返しを持つ = 中心前が輪郭の縁にある = 半身ぶん、と判定する。
    左右対称なパーツ(front_bodice / back_bodice)は`cut`を持たないので
    None が返り、round66までとまったく同じ動きになる。
    """
    if _facing_width_cm(scaled) <= 0.0:
        return None
    cf = _anchor_x(scaled, "cf")
    side = _anchor_x(scaled, "side")
    if cf is None or side is None:
        return None
    return (cf, side)


def _y_extent_at_x(points: list[tuple[float, float]], x: float
                    ) -> tuple[float, float] | None:
    """閉じた点列の、横位置 x における y の最小・最大(`_x_span_at_y`の縦版)。"""
    ys: list[float] = []
    for (x1, y1), (x2, y2) in zip(points, points[1:]):
        if x1 == x2:
            continue
        lo, hi = (x1, x2) if x1 < x2 else (x2, x1)
        if not (lo <= x <= hi):
            continue
        ys.append(y1 + (x - x1) / (x2 - x1) * (y2 - y1))
    if len(ys) < 2:
        return None
    return min(ys), max(ys)


def _front_opening_length_cm(finalized_parts: list, scaled_parts: list
                              ) -> float | None:
    """前開きの「開き寸法」(cm)。前開きでなければ None(round68)。

    ファスナーを買うときに要る長さである。中心前(`cf`基準点)の位置で
    パネルを縦に切り、出来上がり線(縫い線)の上端から下端までを測る。
    首ぐりが深いデザインでは上端が下がるので、**型紙を測る**以外に
    正しい値は出ない。
    """
    for finalized, scaled in zip(finalized_parts, scaled_parts):
        if finalized.part_type != "front_bodice_zip_panel":
            continue
        cf_x = _anchor_x(scaled, "cf")
        if cf_x is None:
            continue
        points = _closed_points_from_segments(scaled.segments)
        extent = _y_extent_at_x(points, cf_x)
        if extent is None:
            continue
        return extent[1] - extent[0]
    return None


#: round68: 開きの下端が何で閉じるか。ファスナーの種類(下まで開くものか)を
#: 選ぶのは利用者なので、こちらは**型紙がどうなっているか**だけを言う。
_LOWER_BODY_PART_TYPES = ("skirt", "front_pants", "back_pants")


def _front_opening_bottom(finalized_parts: list) -> str:
    """開きの下端。"waist"(スカート・パンツとの縫い目) か "hem"(裾)。"""
    if any(p.part_type in _LOWER_BODY_PART_TYPES for p in finalized_parts):
        return "waist"
    return "hem"


def _waist_slack_notes(finalized_parts: list, scaled_parts: list,
                       measurements: Measurements, ease,
                       finished_override_cm: float | None = None,
                       princess_available: bool = True) -> list[str]:
    """ウエストを絞りきれなかった場合の注記(round27)。

    「摘めるはずの量」を式から推定するのではなく、**実際に出力した型紙を
    測って**判断する。ダーツの本数・上限・配置のどれを変えても、注記が
    実態からずれない。
    """
    # round30: 切り替え線で分割した場合、パーツと変形結果が1対1で並ばない
    # (身頃1枚が3枚になる)ので、呼び出し側が測った値をそのまま使う。
    if finished_override_cm is not None:
        finished, measured = finished_override_cm, True
        return _waist_slack_message(finished, measurements, ease,
                                     princess_available)
    finished = 0.0
    measured = False
    for finalized, scaled in zip(finalized_parts, scaled_parts):
        waist_y = getattr(scaled, "waist_y_cm", None)
        if waist_y is None:
            continue
        span = _x_span_at_y(_closed_points_from_segments(scaled.segments), waist_y)
        if span is None:
            continue
        measured = True
        intake = sum(max(x for x, _y in line) - min(x for x, _y in line)
                     for line in finalized.internal_lines)
        # round67: 見返し(中心前より外側の折り返し代)は、折って裏へ回るので
        # 出来上がりの胴回りには入らない。輪郭の幅をそのまま数えると、
        # 前開きの型紙が実際より「ゆるい」ことになる(実測: 左右2枚で8.0cm)。
        finished += (span[1] - span[0]) - intake - _facing_width_cm(scaled)
    if not measured:
        return []
    return _waist_slack_message(finished, measurements, ease, princess_available)


def _waist_slack_message(finished: float, measurements: Measurements,
                          ease, princess_available: bool = True) -> list[str]:
    needed = measurements.waist + ease.waist_cm
    slack = finished - needed
    if slack <= WAIST_SLACK_DISCLOSURE_CM:
        return []
    # round30: 伸びる生地はダーツを入れないので、絞りきれない理由が違う。
    # 「ダーツの上限」と書くと、入っていないものが原因だと読めてしまう。
    reason = ("脇線をこれ以上ウエストで絞ると、縫い合わせのチェックが"
              "できなくなるほど脇線が斜めになるため"
              if ease.waist_cm < 0 else
              "1枚の身頃にダーツで摘める量の上限に達したため")
    # 【round67で直した実バグ】この助言は、常に「切り替え(プリンセスライン)の
    # あるデザインにする」と勧めていた。ところが前開きファスナーと切り替え線は
    # **同時に指定できない**(`build_garment_spec`がはっきり断る)。前開きを
    # 選んだ人にこの文が出ると、**できないことを勧めている**ことになる。
    # 実際、この警告が出ていたのは前開きを選んだときだけだった(実測:
    # 体型5通り × 前開きで5/5、前開き以外では0/10)。
    if princess_available:
        remedy = "切り替え(プリンセスライン)のあるデザインにするか、"
        stretch_remedy = ("ウエストの位置をはっきり出したい場合は、切り替え"
                          "(プリンセスライン)のあるデザインにしてください。")
    else:
        # 前開きでは切り替え線を選べないので、選べる手だけを言う。
        remedy = ("ゆとりを「ぴったり」寄りに変えるか、"
                  "身頃を短くしてウエストで切り替え、スカートと組み合わせるか、")
        stretch_remedy = ("ウエストの位置をはっきり出したい場合は、"
                          "ウエストベルトで押さえてください"
                          "(前開きファスナーと切り替え線は同時に指定できません)。")
    advice = ("生地が伸びるぶんは実際には体に沿いますが、" + stretch_remedy
              if ease.waist_cm < 0 else
              "ウエストをぴったりさせたい場合は、" + remedy
              + "ウエストベルトで押さえてください。")
    return [
        f"出来上がりのウエストは約{finished:.0f}cmで、採寸{measurements.waist:g}cm"
        f"+ゆとり{ease.waist_cm:g}cmより{slack:.0f}cmゆるくなります"
        f"({reason})。" + advice
    ]


def _hip_shortfall_notes(scaled_parts: list, measurements: Measurements,
                          ease) -> list[str]:
    """ヒップが通る幅を確保しきれなかった場合の注記(round27)。

    裾を開かせると脇線が寝る。寝すぎると脇線として認識できなくなり、
    縫い合わせ長さのチェックが黙ってスキップされてしまうため、傾きには
    上限がある(`engine/bodice_fit.py`の`SIDE_SEAM_MAX_SLOPE`)。バストに
    対してヒップが極端に大きい体型では、その上限に当たって必要な幅を
    確保しきれない。**足りないまま黙って出さない。**
    """
    shortfall = max((getattr(p, "hip_shortfall_cm", 0.0) for p in scaled_parts),
                    default=0.0)
    if shortfall <= 0.5:
        return []
    return [
        f"バスト{measurements.bust:g}cmに対してヒップ{measurements.hip:g}cmが"
        f"大きく、裾の幅が約{shortfall:.0f}cm不足しています"
        "(1枚の身頃を脇線だけで広げられる限界を超えているため)。"
        "そのままでは腰を通らない可能性があります。"
        "身頃を短くしてスカートやパンツと組み合わせるか、"
        "前開きファスナーを付けてください。"
    ]


def _bust_dart_notes(scaled_parts: list, measurements: Measurements) -> list[str]:
    """胸ぐせダーツを脇線に収めきれなかった場合の注記(round29)。

    胸ぐせダーツの大きさは新文化式の (B/4 − 2.5) 度で決まる
    (`engine/darts.py`の`bust_dart_angle_deg`)。バストが大きいほど角度も
    大きく、脇線に開ける口も広くなる。1本では縫いにくいので2本まで分ける
    が、それでも入りきらない量が出ることがある。**足りないまま黙って
    出さない。**
    """
    unfitted = max((getattr(p, "bust_dart_unfitted_cm", 0.0) for p in scaled_parts),
                   default=0.0)
    if unfitted <= 0.5:
        return []
    return [
        f"バスト{measurements.bust:g}cmに必要な胸ぐせダーツのうち、"
        f"約{unfitted:.0f}cmが脇線に収まりませんでした"
        "(脇線に並べられるダーツは2本までとしているため)。"
        "胸の丸みがその分だけ浅くなり、バストの下に少し布が余ります。"
        "切り替え線(プリンセスライン)のある型紙の方が適した体型です。"
    ]


#: 胸幅/背幅が狙いから何cm以上ずれたら開示するか(round31)。
#: 0.5cmは半身の値なので、胴回りでは1cmの差にあたる。
CHEST_WIDTH_NOTE_THRESHOLD_CM = 0.5


def _split_oversized_part(base_part, scaled, request, measurements,
                           max_fabric_width_cm: float, seam_allowance_cm: float,
                           hem_seam_allowance_cm: float | None,
                           label_suffix: str, template_db) -> list | None:
    """生地幅に収まらないパーツを縦に分けて返す。分けない/分けられないならNone。

    幅の判定は**裁断線**(縫い代込み)で行う。生地に置かれるのは裁断線の
    大きさだからで、縫い線で判定すると縫い代のぶん収まらない。
    """
    # round57: カスタムパーツ(マント・翼・装甲プレート)も、**利用者が
    # 望んだときだけ**分ける。
    #
    # 分けてよいのは「そこに縫い目が入っても仕立てとして成り立つ」
    # パーツだけ(モジュールdocstring参照)。マントは中心で縫い合わせるのが
    # ふつうの作り方だが、EVAフォームの装甲プレートに縫い目を入れるのは
    # 別の話である。**どちらなのかは作る人にしか分からない**ので、
    # 勝手に分けず、パーツごとの指定に従う。
    if request.part_type == CUSTOM_PANEL_PART_TYPE:
        if not getattr(request, "allow_split", False):
            return None
    elif request.part_type not in SPLITTABLE_PART_TYPES:
        return None
    count = panels_needed(base_part.width_cm, max_fabric_width_cm, seam_allowance_cm)
    if count < 2:
        return None
    pieces = split_into_panels(scaled.segments, count)
    if pieces is None:
        return None

    seam_edge = template_db.get_seam_edge(request.part_type, request.variation)
    out = []
    for piece, panel_label in zip(pieces, panel_labels(count)):
        suffix = f"{label_suffix} {panel_label}".strip()
        # 分割後は、元のパーツ用に決めた合印座標(相手パーツの縫い目に
        # 合わせた絶対座標)がどのパネルに乗るか分からない。既定の
        # 周長比による合印へ戻す(engine/notches.pyのフォールバック)。
        out.append(finalize_part(
            request.part_type, request.variation, piece,
            seam_allowance_cm=seam_allowance_cm,
            hem_seam_allowance_cm=hem_seam_allowance_cm,
            label_suffix=suffix,
            seam_edge=seam_edge,
        ))
    return out


def _sleeve_cap_ease_for(finalized_parts: list) -> float | None:
    """この型紙のいせ込み量(cm)。身頃が揃っていなければNone(round33)。

    縫製手順に「袖山を約○cm縮めます」と書くために使う。
    `PipelineResult.assembly_steps()`と同じ値になるよう、計算はここ1か所。
    """
    fronts = [p for p in finalized_parts if p.part_type == "front_bodice"]
    backs = [p for p in finalized_parts if p.part_type == "back_bodice"]
    if not fronts or not backs:
        return None
    lengths = [armhole_length(p) for p in fronts + backs]
    if not all(v is not None for v in lengths):
        return None
    return sleeve_cap_ease_cm(sum(lengths) / 2.0)


def _chest_width_notes(scaled_parts: list, measurements: Measurements) -> list[str]:
    """胸幅・背幅を狙いの位置へ置ききれなかった場合の注記(round31)。

    袖ぐりの点(中心から胸幅/背幅だけ離れた点)は、**肩先より外へは
    出られない**。新文化式の胸幅 B/8+6.2 が肩幅の半分を超える体型——
    つまり「バストの割に肩幅が狭い」と入力された場合——は、袖ぐりの
    えぐれを0にしても届かない。実測(バスト130・肩幅37cmを入力):
    胸幅の狙い22.45cmに対し18.08cmで、4.4cm足りない(左右で8.7cm)。

    このとき考えられるのは「肩幅の採寸が実際より小さい」か「本当に
    なで肩で肩幅が狭い」かのどちらかで、型紙側では決められない。
    黙って狭い型紙を出さず、どちらなのかを確かめてもらう。
    """
    worst = 0.0
    parts: list[str] = []
    for p in scaled_parts:
        if not getattr(p, "chest_width_limited", False):
            continue
        target = getattr(p, "chest_width_cm_target", None)
        actual = getattr(p, "chest_width_cm_actual", None)
        if target is None or actual is None:
            continue
        gap = target - actual
        if gap <= CHEST_WIDTH_NOTE_THRESHOLD_CM:
            continue
        if gap > worst:
            worst = gap
        name = "胸幅" if p.part_type != "back_bodice" else "背幅"
        if name not in parts:
            parts.append(name)
    if not parts:
        return []
    return [
        f"バスト{measurements.bust:g}cmに対して肩幅"
        f"{measurements.shoulder_width:g}cmが狭いため、"
        f"{'・'.join(parts)}(中心から袖ぐりまでの幅)が狙いより"
        f"最大約{worst:.1f}cm足りません(左右で約{worst * 2:.1f}cm)。"
        "袖ぐりの点は肩先より外には出せないためです。"
        "腕の付け根の前後が突っ張るようなら、肩幅の採寸"
        "(左右の肩先の間を背中側で測った長さ)を確かめてください。"
    ]


def _waist_shaping_notes(scaled_parts: list, measurements: Measurements,
                          ease) -> list[str]:
    """(round26の注記。round27で役目を終えたため、もう呼ばれていない)

    round26では、裾のダーツを「ヒップが通る幅」で止めた結果ウエストが
    まったく絞られなくなり、その事実を伝える必要があった。round27で
    ウエストの線にダイヤモンドダーツを置けるようになり、裾のダーツが
    止まること自体は**正常な状態**になったので、この注記は出さない。
    代わりに`_waist_slack_notes`が、実際の出来上がり寸法を測って
    「絞りきれていない」場合だけ伝える。

    関数を消さずに残してあるのは、tests/test_hip_clearance.py が
    「裾のダーツがヒップで止まること」自体を引き続き検証しており、
    その判定(`waist_shaping_limited`)の意味を説明する場所が要るため。

    身頃の裾は**ヒップの高さ**にあるので、そこに入るダーツで絞れる量には
    「ヒップが通る幅を残す」という上限がある(engine/darts.pyの
    `compute_dart_plan`参照)。上限に当たった場合、ウエストは本来より
    絞りきれていない。黙って絞らないのでも、黙って着られない型紙を出すのでも
    なく、そうなった事実と理由を伝える。
    """
    if not any(getattr(p, "waist_shaping_limited", False) for p in scaled_parts):
        return []
    return [
        f"ヒップ{measurements.hip:g}cm(+ゆとり{ease.hip_cm:g}cm)が通る幅を"
        "裾に確保したため、ウエストのダーツはその範囲までしか摘んでいません"
        "(身頃の裾はヒップの高さにあり、ここで絞りすぎると腰を通らなくなります)。"
        "ウエストの位置で絞りたい場合は、ウエストベルトを併用するか、"
        "前開きファスナーを付けてください。"
    ]


def _upper_arm_notes(measurements: Measurements, finalized_parts: list,
                      ease) -> list[str]:
    """入力した二の腕まわりを袖に反映しきれなかった場合の注記(round25)。

    袖幅を腕で固定すると、袖ぐりに合わせられるのは袖山の**高さ**だけになる。
    腕がバストに対して極端に太い場合、袖山をいちばん低くしても袖山カーブが
    袖ぐりより長くなり、物理的に縫い付けられない。実測(バスト83・袖ぐり
    片腕39.7cm):

      二の腕36cm → 袖幅41.0cm 袖山3.3cm  縫える
      二の腕40cm → 袖幅45.0cm 袖山2.4cm  袖山カーブが3.6cm長すぎる

    このとき`engine/compatibility.py`のチェック5が警告を出すが、その文面は
    「身頃はバスト、袖は肩幅と別々の採寸で拡大縮小するため」という
    round14当時の理由になっていて、**二の腕を入力したせいだとは分からない**。
    実際の原因と、利用者が取れる手を併せて開示する。
    """
    if measurements.upper_arm is None:
        return []
    if not any(w.kind == "armhole_sleeve_cap"
               for w in check_seam_compatibility(finalized_parts)):
        return []
    return [
        f"入力された二の腕まわり{measurements.upper_arm:g}cm"
        f"(+袖のゆとり{ease.sleeve_cm:g}cm)に対して袖ぐりが小さく、"
        "袖山をいちばん低くしても袖を袖ぐりに縫い付けられません。"
        "二の腕まわりの入力を空欄にする(袖ぐりから相似で決める)か、"
        "袖のゆとりを小さくするか、バストの採寸値をご確認ください。"
    ]


def _sleeve_target_cap_cm(scaled_by_type: dict[str, list[ScaledPart]],
                           variation: str,
                           unsplit_fronts: list | None = None,
                           drop_shoulder: bool = False) -> float | None:
    """袖山カーブの目標長さ(cm)を、実際に縫い付ける袖ぐりの長さから求める
    (round14追加、`scale_sleeve_to_cap_length`参照)。

    `engine/compatibility.py`のチェック5が「あるべき袖山長」として使って
    いる式(袖ぐり(片腕) + いせ込み + デザイン上のギャザー)をそのまま
    目標値にする。つまり「警告が出ない寸法をあらかじめ作る」という関係に
    なっていて、チェック側と生成側で別々の式を持たない。

    身頃が指定されていない(袖だけを生成する)場合はNoneを返し、呼び出し側は
    従来通り肩幅比による独立スケーリングにフォールバックする。
    """
    armhole_per_arm = _armhole_per_arm_cm(scaled_by_type, unsplit_fronts)
    if armhole_per_arm is None:
        return None
    return (armhole_per_arm
            + sleeve_cap_ease_cm(armhole_per_arm, drop_shoulder=drop_shoulder)
            + SLEEVE_CAP_DESIGN_GATHER_CM.get(variation, 0.0))


def _collar_target_length_cm(scaled_by_type: dict[str, list[ScaledPart]],
                              unsplit_fronts: list | None = None) -> float | None:
    """衿の首ぐり側の辺の目標長さ(cm)を、前身頃+後ろ身頃の実際の首ぐり長から
    求める(round15追加、`engine/compatibility.py`の`neckline_length`参照)。

    round14まで、衿は「首まわりの近似としてバスト比」で拡大縮小しており、
    実際に縫い付ける首ぐりとは一切関係が無かった。実測(標準M):

      首ぐりの長さ(前+後)  ラウンド37.6 / スクエア44.0 / スウィートハート44.3
                            / Vネック48.3 / ボート49.6 cm
      衿の縫い付け辺        どのネックラインでも 28〜40cm(形状で決まる固定値)

    つまりVネックやボートネックでは衿が10cm以上足りず、そもそも縫い付け
    られなかった。round7のウエストバンド/カフス、round14の袖と同じく、
    相手の実際の長さに合わせて作るようにする。

    Noneを返す(=従来通り採寸比での独立スケーリングにフォールバックする)ケース:
      - 身頃が無い(衿だけを生成する)
      - タートルネック … 首ぐりが台襟になっていて、衿を縫い付ける線が無い
      - タートルネック … 首ぐりが台襟になっていて、衿を縫い付ける線が無い

    round75: **前開き(front_bodice_zip_panel)でも測る。** 中心前で裁ち割った
    片側パネルからは首ぐりを一意に取り出せない(`neckline_length`の
    docstring)ので、round74までここはNoneを返していた。返すとどうなるか:

      * 衿は「バスト比」で拡大縮小され、実際の首ぐりとは無関係になる
        (round14で直したはずの状態へ、前開きのときだけ戻っていた)
      * 画面には「衿の長さが身頃の首ぐりに合っているかは、この型紙では
        確かめていません」とだけ出る
      * round75で足したフードは、目標が無いので**採寸比の伸縮**に落ち、
        頭囲を入れても大きさが変わらない(実測: 頭囲56cmを入れても
        既定の57cmで引いたものと同じ28.6×47.8cmが出た)

    割る前の前身頃を測れば済む——袖ぐりで同じことをした
    (`_armhole_per_arm_cm`)のと、まったく同じ理由と同じ手当てである。
    """
    fronts = scaled_by_type.get("front_bodice", [])
    backs = scaled_by_type.get("back_bodice", [])
    if not fronts:
        fronts = list(unsplit_fronts or ())
    if not fronts or not backs:
        return None
    total = 0.0
    for scaled in fronts + backs:
        length = neckline_length(SimpleNamespace(
            part_type=scaled.part_type, variation=scaled.variation,
            stitch_line=segments_to_polyline(scaled.segments)))
        if length is None:
            return None
        total += length
    return total + COLLAR_EASE_CM


def _cuffs_target_width_cm(scaled_by_type: dict[str, list[ScaledPart]]) -> float | None:
    """cuffsの目標幅(cm)を、実際に縫い合わせる相手(sleeve)の袖口長さから
    求める(round7追加)。左右の袖は同一の採寸で対称に変形されるため、
    代表して1枚分の袖口長を使う。sleeveが無ければNone
    (build_garment_spec()はcuffs単独指定を拒否するため通常は到達しないが、
    GarmentSpecを直接組み立てるテスト等のためにフォールバックを残す)。
    """
    sleeves = scaled_by_type.get("sleeve")
    if not sleeves:
        return None
    return _bottom_opening_length_cm(sleeves[0].segments) + CUFFS_EASE_CM


#: 基準線の両端を、輪郭からどれだけ内側で止めるか(cm)。輪郭ぴったりまで
#: 引くと裁断線と重なって読みにくいので、少しだけ内側で止める。
REFERENCE_LINE_INSET_CM = 0.4
#: BP(バストポイント)を示す十字の腕の長さ(cm)。横の腕はバスト線と重なる
#: (BPはバスト線の上にある)ので、縦の腕がBPの目印として効く。
BUST_POINT_MARK_CM = 1.0


def _reference_lines_for(part_type: str, scaled, measurements: Measurements,
                          outline_segments: list | None = None,
                          with_center: bool = True,
                          block: Block = ADULT_FEMALE
                          ) -> list[tuple[str, list[tuple[float, float]]]]:
    """身頃に描く基準線を組み立てる(round30)。

    JIS L 0110「衣料パターンの表示記号」が挙げている記号のうち、この
    エンジンが位置を知っていながら描いていなかったものを描く:

      表2-40 内部線 … 「パターン設計上必要なバスト線，ウエスト線及び
                       ヒップ線を表す」
      表1-2  中心線 … 「パターン設計上の前身ごろ，後ろ身ごろなどの中心」
      表1-12 バストポイント

    どれも縫う線ではないが、**型紙を補正するときの基準**になる。丈を
    詰める・ダーツを移す・切り替えを入れる、といった作業はすべて
    「バスト線から何cm」「ウエスト線の上で」という形で指示されるので、
    線が引かれていない型紙はそこで手が止まる。

    位置はこのエンジンが既に計算して持っている値をそのまま使う
    (`ScaledPart`のbust_line_y_cm / waist_y_cm / bust_point_y_cm)ので、
    二重に推定することはない。裾(=ヒップの高さ)は輪郭の下端。
    """
    if part_type not in BODICE_PART_TYPES:
        return []
    # round30: 切り替え線で分けた場合、線はそのパーツの輪郭の中だけに引く。
    # 分ける前の身頃の幅で引くと、パーツの外へはみ出す。
    points = _closed_points_from_segments(outline_segments or scaled.segments)
    if len(points) < 4:
        return []
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    center_x = (min(xs) + max(xs)) / 2.0
    inset = REFERENCE_LINE_INSET_CM

    lines: list[tuple[str, list[tuple[float, float]]]] = []

    def _horizontal(label: str, y: float | None) -> None:
        if y is None:
            return
        span = _x_span_at_y(points, y)
        if span is None or span[1] - span[0] <= 2 * inset:
            return
        lines.append((label, [(span[0] + inset, y), (span[1] - inset, y)]))

    _horizontal("BL", scaled.bust_line_y_cm)
    _horizontal("WL", scaled.waist_y_cm)
    # ヒップ線は身頃の裾(丈58cmは首の付け根からヒップまで)。
    _horizontal("HL", max(ys) - 0.001)

    # 中心線。前身頃・後ろ身頃は左右対称なので、外接矩形の中央が中心。
    # 前開きの片側パネルは非対称なので描かない(中心がどちらの縁かを
    # 形だけからは決められない)。
    if with_center and part_type in ("front_bodice", "back_bodice"):
        lines.append(("CF" if part_type == "front_bodice" else "CB",
                       [(center_x, min(ys) + inset), (center_x, max(ys) - inset)]))

    # BP(バストポイント)。前身頃だけ。左右に1つずつ、十字で示す。
    # round42: 子ども原型は描かない(出典の製図にBPが出てこない。
    # `engine/blocks.py`の`draws_bust_point`)。
    if (with_center and block.draws_bust_point
            and part_type in BUST_DART_ELIGIBLE_PART_TYPES
            and scaled.bust_point_y_cm is not None):
        offset = bust_point_from_cf_cm(measurements.bust,
                                       measurements.bust_point_spacing)
        y = scaled.bust_point_y_cm
        arm = BUST_POINT_MARK_CM
        for sign in (-1.0, 1.0):
            x = center_x + sign * offset
            if not (min(xs) < x < max(xs)):
                continue
            lines.append(("BP", [(x - arm, y), (x + arm, y)]))
            lines.append(("", [(x, y - arm), (x, y + arm)]))
    return lines


def _princess_notes(stats: dict[str, dict], failures: set[str]) -> list[str]:
    """切り替え線(プリンセスライン)についての開示(round30)。

    * 実際に何cm摘んだか。ダーツと違って上限が無いので、ここが大きいほど
      「ダーツでは無理だった量」を示す。
    * 中央側と脇側の縁の長さの差。実物の型紙では長い方をいせ込むか線を
      引き直して合わせるが、ここではその処理をしていないので開示する。
    * 引けなかったパーツがあれば、その事実(黙ってダーツ入りに戻さない)。
    """
    notes: list[str] = []
    if stats:
        intakes = [v.get("waist_intake_cm", 0.0) for v in stats.values()]
        notes.append(
            "切り替え線(プリンセスライン)で身頃を「中央」「脇」に分けました"
            f"(1本あたりウエストで最大{max(intakes):.1f}cm摘みます)。"
            "ウエストの絞りはダーツではなくこの縫い目が担うため、"
            "ダーツで摘める量の上限がありません。")
    return notes


def _princess_warnings(stats: dict[str, dict], failures: set[str]) -> list[str]:
    """切り替え線のうち、**気をつけないと困る**ことだけ(round32で分離)。

    round31まで、上の「分けました」という単なる説明も含めて全部が
    「⚠ 入力した採寸値が変形できる範囲を超えています」という赤い枠の中に
    出ていた。何も問題が無い生成でも赤が出るので、本当に読むべき警告が
    埋もれる。説明は`_princess_notes`、警告はこちら、と分けた。
    """
    warnings: list[str] = []
    if stats:
        gaps = [v.get("edge_gap_cm", 0.0) for v in stats.values()]
        if max(gaps, default=0.0) >= 0.3:
            warnings.append(
                f"切り替え線の中央側と脇側で、縁の長さが最大{max(gaps):.1f}cm"
                "違います。縫うときは長い方を少しいせ込んで合わせてください"
                "(型紙側での調整はしていません)。")
    for part_type in sorted(failures):
        warnings.append(
            f"{part_type_label(part_type)}には切り替え線を引けませんでした"
            "(輪郭の形が想定と違うため)。このパーツはダーツで絞っています。")
    return warnings


def _notch_points_by_type(scaled_by_type: dict[str, list[ScaledPart]],
                           template_db: TemplateDB) -> dict[str, list]:
    """パーツ種ごとの合印座標を、実際に縫い合わせる相手から決める(round16)。

    `engine/notches.py`のモジュールdocstringに、round15までの合印が
    どれだけ役に立っていなかったか(実測)と、この方針の理由を書いてある。
    ここでは「相手が居るときだけ」座標を決め、決められないパーツは
    Noneのままにして従来の既定位置へフォールバックさせる。
    """
    out: dict[str, list] = {}

    def _poly(scaled: ScaledPart):
        return segments_to_polyline(scaled.segments)

    # 1. 脇線: 前身頃 ⇔ 後ろ身頃、パンツ前 ⇔ パンツ後。
    #    脇の下から縫い線に沿って同じ比率の位置なので、必ず突き合う。
    #    round71: 位置は**距離**で合わせる。比率で測ると、前後の脇線長が
    #    わずかに違うだけで合印がずれる(実測 17.219 対 17.271)。ダーツの
    #    無い側(後ろ)で測った距離を、前にもそのまま使う。
    for group in (("back_bodice", "front_bodice", "front_bodice_zip_panel"),
                  ("back_pants", "front_pants")):
        reference = scaled_by_type.get(group[0])
        distance = None
        if reference:
            distance = side_seam_notch_distance_cm(
                _poly(reference[0]), underarm_y=_underarm_y_of(reference[0]))
        for part_type in group:
            parts = scaled_by_type.get(part_type)
            if parts:
                out[part_type] = side_seam_notch_points(
                    _poly(parts[0]), underarm_y=_underarm_y_of(parts[0]),
                    distance_cm=distance)

    # 2. 袖ぐり ⇔ 袖山: 前は1本、後ろは2本。袖側は袖山の両端から
    #    「身頃の脇の下から合印までの距離」と同じだけ入った位置に打つ。
    fronts = scaled_by_type.get("front_bodice") or []
    backs = scaled_by_type.get("back_bodice") or []
    if fronts and backs:
        front_poly, back_poly = _poly(fronts[0]), _poly(backs[0])
        # round31: 脇の下の高さを渡す(後ろの袖ぐりはほぼ直線で、形だけでは
        # 脇線と区別できない。engine/compatibility.pyの`side_seam_edges`参照)。
        front_underarm = _underarm_y_of(fronts[0])
        back_underarm = _underarm_y_of(backs[0])
        out["front_bodice"] = (out.get("front_bodice", [])
                                + armhole_notch_points(front_poly, is_back=False,
                                                       underarm_y=front_underarm))
        out["back_bodice"] = (out.get("back_bodice", [])
                               + armhole_notch_points(back_poly, is_back=True,
                                                      underarm_y=back_underarm))
        sleeves = scaled_by_type.get("sleeve")
        if sleeves:
            distance = armhole_notch_distance_cm(front_poly, underarm_y=front_underarm)
            out["sleeve"] = sleeve_cap_notch_points(_poly(sleeves[0]), distance)

    # 3. ウエストバンド: 縫い付け辺の上に、スカート/パンツの各パーツの
    #    継ぎ目(脇線)が来る位置を示す。
    lower = scaled_by_type.get("skirt") or (
        scaled_by_type.get("front_pants", []) + scaled_by_type.get("back_pants", []))
    bands = scaled_by_type.get("waistband")
    if lower and bands:
        distances, acc = [], 0.0
        for scaled in lower[:-1]:
            acc += _top_opening_length_cm(scaled.segments)
            distances.append(acc)
        out["waistband"] = seam_edge_points_at(
            _poly(bands[0]), template_db.get_seam_edge("waistband", bands[0].variation),
            distances)

    # 4. 衿: 縫い付け辺の上に、肩の継ぎ目が来る位置を示す。衿は
    #    後ろ中心→肩→前中心→肩→後ろ中心の順に回るので、片端(後ろ中心)から
    #    「後ろ首ぐりの半分」「そこから前首ぐり1枚分」の2点が肩になる。
    collars = scaled_by_type.get("collar")
    if collars and fronts and backs:
        front_neck = neckline_length(SimpleNamespace(
            part_type="front_bodice", variation=fronts[0].variation,
            stitch_line=_poly(fronts[0])))
        back_neck = neckline_length(SimpleNamespace(
            part_type="back_bodice", variation=backs[0].variation,
            stitch_line=_poly(backs[0])))
        if front_neck is not None and back_neck is not None:
            out["collar"] = seam_edge_points_at(
                _poly(collars[0]),
                template_db.get_seam_edge("collar", collars[0].variation),
                [back_neck / 2.0, back_neck / 2.0 + front_neck])

    # 5. カフス: 袖口の中心に1つ。袖の下端の中点と突き合わせる目印。
    cuffs = scaled_by_type.get("cuffs")
    if cuffs:
        from .compatibility import seam_edge_length as _seam_len
        edge = template_db.get_seam_edge("cuffs", cuffs[0].variation)
        length = _seam_len(SimpleNamespace(stitch_line=_poly(cuffs[0]), seam_edge=edge))
        out["cuffs"] = seam_edge_points_at(_poly(cuffs[0]), edge, [length / 2.0])

    return out


class PatternForgePipeline:
    """テンプレートDB・出力先を束ねた、生成フローのエントリポイント。"""

    def __init__(self, template_dir: str | None = None, output_dir: str = "generated",
                 seam_allowance_cm: float = DEFAULT_SEAM_ALLOWANCE_CM,
                 hem_seam_allowance_cm: float | None = None):
        self.template_db = TemplateDB(template_dir) if template_dir else TemplateDB()
        self.output_dir = output_dir
        self.seam_allowance_cm = seam_allowance_cm
        # round5「縫い代を辺ごとに設定可能に」の既定値。Noneなら裾も
        # seam_allowance_cmと同じ(=従来通り全辺一律)。generate_from_selection
        # 等の呼び出し時に上書きできる(利用者ごとに異なる値を使いたい場合、
        # このインスタンス全体の既定値を変えずに1回の生成だけ変更できる)。
        self.hem_seam_allowance_cm = hem_seam_allowance_cm

        missing = self.template_db.missing()
        if missing:  # pragma: no cover - テンプレートSVGが欠けている環境向けの早期警告
            raise RuntimeError(
                "テンプレートDBに必要なSVGが不足しています: "
                + ", ".join(f"{p}/{v}" for p, v in missing)
                + " 。scripts/generate_templates.py を実行してください。"
            )

    # ------------------------------------------------------------------
    # `_build_from_spec` の段階ごとの中身(round63で切り分けた)
    #
    # 【なぜ切り分けたか】型紙ができる流れの本体が663行の1つの関数で、
    # 新しく入った人は全体像をつかむ前に細部に埋もれていた。**動きは
    # 何も変えず**、段階ごとに名前を付けて外へ出した。
    # `_build_from_spec` を上から読めば、何がどの順で起きるかが分かる。
    # ------------------------------------------------------------------

    def _finalize_every_part(self, garment_spec, measurements, precomputed,
                              scaled_by_type, fit, ease, effective_seam_cm,
                              effective_hem_cm, fabric_width_candidates,
                              allow_rotation, one_way_fabric,
                              design_length_overrides, block):
        """変形したパーツに、合印・ダーツ・縫い代を入れて確定させる。

        生地の幅に収まらないパーツは、ここで何枚かに分ける。

        Returns:
            (変形後の一覧, 確定した一覧, 切り替え線の統計, 引けなかった
             切り替え線, 切り替え線で絞った合計, 分割の記録, 分割した枚数)
        """
        scaled_parts: list[ScaledPart] = []
        finalized_parts: list[FinalizedPart] = []
        princess_stats: dict[str, dict] = {}
        princess_failures: set[str] = set()
        princess_waist_total = 0.0
        split_records: dict[int, list[str]] = {}
        split_panels: dict[str, int] = {}
        # round16: 合印を「実際に縫い合わせる相手」から決める。
        notch_points_by_type = _notch_points_by_type(scaled_by_type, self.template_db)

        princess_stats: dict[str, dict] = {}
        princess_failures: set[str] = set()
        princess_waist_total = 0.0
        split_records: dict[int, list[str]] = {}
        split_panels: dict[str, int] = {}
        for req_idx, request in enumerate(garment_spec.parts):
            quantity = max(1, request.quantity)
            labels = PAIR_LABELS.get(request.part_type)
            for i in range(quantity):
                scaled = precomputed[(req_idx, i)]
                scaled_parts.append(scaled)

                if labels and quantity > 1:
                    label_suffix = labels[i % len(labels)]
                elif request.part_type == CUSTOM_PANEL_PART_TYPE and quantity > 1:
                    # round9で追加: custom_panelはpart_type単位でグローバルに
                    # 決まる左右/前後ラベル(PAIR_LABELS)を持たない(利用者が
                    # 自由に付けたラベルはvariationの方に入っている)ため、
                    # 同一パーツの複数枚は"①""②"のような通し番号で区別する
                    # (型紙PDF/DXFに複数枚を印字する際、区別できないと
                    # 裁断時に取り違える恐れがあるため)。
                    label_suffix = _NUMERIC_SUFFIXES[i % len(_NUMERIC_SUFFIXES)]
                else:
                    label_suffix = ""
                extra_notches = None
                if (request.part_type == "skirt" and request.variation == "tight"
                        and label_suffix == "後"):
                    extra_notches = SKIRT_BACK_DART_NOTCHES

                # round27: ウエストの線に置くダイヤモンドダーツ。輪郭を
                # 切り欠かずに内側で摘むので、裁断線にも縫い合わせ長さにも
                # 影響しない(engine/darts.pyの`waist_diamond_dart_lines`)。
                # round30: 切り替え線(プリンセスライン)で身頃を2枚に分ける。
                # 分けた側はダーツを持たないので、ダイヤモンドダーツの計算へ
                # 進まずここで確定させる。
                if (garment_spec.princess_line
                        and request.part_type in PRINCESS_PART_TYPES):
                    split = split_bodice(request.part_type, scaled,
                                          measurements, fit)
                    if split is not None:
                        center_segments, side_segments, stats = split
                        princess_stats.setdefault(request.part_type, stats)
                        # 出来上がりのウエスト周は、分けた3枚の
                        # 「ウエストの高さでの幅」の合計そのもの
                        # (縫い代を含まない縫い線どうしで測る)。
                        for seg, count in ((center_segments, 1),
                                            (side_segments, 2)):
                            span = _x_span_at_y(
                                _closed_points_from_segments(seg),
                                scaled.waist_y_cm)
                            if span is not None:
                                princess_waist_total += (span[1] - span[0]) * count
                        center_type, side_type = PRINCESS_PANEL_TYPES[
                            request.part_type]
                        # round76: 分けた3枚にも、下げた脇の下を引き継ぐ
                        # (ドロップショルダーの`ScaledPart.underarm_y_cm`)。
                        # 渡さないと、脇パーツの脇線が深い袖ぐりを飲み込む
                        # ——実測: ドロップ8cmで70.5cmのところ32.7cm。
                        # 3枚まとめて1か所で渡す(片方にだけ渡す書き方だと、
                        # 抜けても落ちるテストを作れない形になる)。
                        for panel_type, segs, suffixes, with_center in (
                                (center_type, center_segments, ("中央",), True),
                                (side_type, side_segments, ("左", "右"), False)):
                            for suffix in suffixes:
                                finalized_parts.append(finalize_part(
                                    panel_type, request.variation, segs,
                                    reference_lines=_reference_lines_for(
                                        request.part_type, scaled, measurements,
                                        outline_segments=segs,
                                        with_center=with_center, block=block),
                                    seam_allowance_cm=effective_seam_cm,
                                    hem_seam_allowance_cm=effective_hem_cm,
                                    underarm_y_cm=scaled.underarm_y_cm,
                                    label_suffix=suffix))
                        continue
                    princess_failures.add(request.part_type)

                internal_lines, diamond_count = ([], 0)
                if scaled.waist_y_cm is not None:
                    # round28: 前身頃では上の先端をBPの手前で止める(BPを
                    # 越えると胸の頂点の真上で布が尖る)。後ろ身頃にBPは
                    # 無いので制限しない。
                    apex_limit = None
                    if (request.part_type in BUST_DART_ELIGIBLE_PART_TYPES
                            and scaled.bust_line_y_cm is not None):
                        # round29: 胸ぐせダーツの口より下は、紙の上で
                        # `bust_dart_shift_cm`だけ下がっている(縫い閉じると
                        # 戻る)。BPは口より上なので下がらない。よって
                        # 「BPの手前で止める」高さも、紙の上ではその分だけ
                        # 下へずらさないと効かない(実測: バスト120で
                        # 制限が19.5cm先になり、まったく効いていなかった)。
                        apex_limit = (scaled.bust_line_y_cm + WAIST_DART_BELOW_BP_CM
                                      + scaled.bust_dart_shift_cm)
                    internal_lines, diamond_count = waist_diamond_dart_lines(
                        scaled.segments, measurements, scaled.waist_y_cm,
                        ease.waist_cm, apex_limit_y=apex_limit,
                        share=waist_dart_share(request.part_type),
                        dartless=is_stretch(fit),
                        # round67: 前開きのパネルは左右非対称で、中心前が
                        # 輪郭の縁にある。「真ん中が中心前」という前提の
                        # ままでは、摘む余りが無いと判断されて**1本も
                        # 入らない**(実測: ウエストが約11cm大きいまま)。
                        half_panel=_half_panel_anchors(scaled))

                base_part = finalize_part(
                    request.part_type, request.variation, scaled.segments,
                    internal_lines=internal_lines,
                    reference_lines=_reference_lines_for(
                        request.part_type, scaled, measurements, block=block),
                    notch_points=notch_points_by_type.get(request.part_type),
                    seam_allowance_cm=effective_seam_cm,
                    hem_seam_allowance_cm=effective_hem_cm,
                    label_suffix=label_suffix,
                    extra_notch_fractions=extra_notches,
                    dart_count=scaled.dart_count + diamond_count,
                    # round15: 帯状パーツの「縫い付けられる辺」の宣言を
                    # 最終パーツへ引き継ぐ(整合性チェックが同じ辺を測るため)。
                    seam_edge=self.template_db.get_seam_edge(
                        request.part_type, request.variation),
                    # round76: ドロップショルダーで脇の下を下げた場合、
                    # 袖ぐりをどこで打ち切るかの判定に使う高さも下がる
                    # (`engine/scaling.py`のScaledPart.underarm_y_cm)。
                    underarm_y_cm=scaled.underarm_y_cm,
                )

                # round35: 生地幅に収まらないパーツは、型紙から**黙って消えて
                # いた**(engine/nesting.pyがunplacedにし、SVG/PDFは描かない)。
                # 実測でウエスト60〜150 x ヒップ70〜170を10cm刻みで総当たり
                # した110通りのうち70通りでサーキュラースカートが消えていた
                # (消え始めるのはヒップ143cmから)。分けられるものは縦に分けて、
                # そのまま作れるようにする(engine/panel_split.py)。
                panels = _split_oversized_part(
                    base_part, scaled, request, measurements,
                    max_fabric_width_cm=max(fabric_width_candidates),
                    seam_allowance_cm=effective_seam_cm,
                    hem_seam_allowance_cm=effective_hem_cm,
                    label_suffix=label_suffix,
                    template_db=self.template_db)
                if panels is None:
                    finalized_parts.append(base_part)
                else:
                    finalized_parts.extend(panels)
                    split_panels[request.part_type] = len(panels)
                    # round35: 前後は必ず対で分かれるので、1件ずつ書くと同じ
                    # 説明が2回並ぶ。あとでまとめて1件にする。
                    split_records.setdefault(len(panels), []).append(
                        base_part.display_name)
        return (scaled_parts, finalized_parts, princess_stats, princess_failures,
                princess_waist_total, split_records, split_panels)

    def _scale_every_part(self, garment_spec, measurements, segments_by_idx,
                           fit, block, alterations, design_lengths,
                           shoulder_drop_cm=None):
        """テンプレートを採寸に合わせて変形する(3回に分けて回す)。

        【なぜ3回に分けるか】パーツによっては「相手の出来上がり寸法」に
        合わせる必要があり、相手が先に決まっていないと計算できない:

            1回目  身頃・スカート・パンツなど(自分の採寸だけで決まる)
            2回目  袖・衿      (身頃の袖ぐり・首ぐりの長さに合わせる)
            3回目  帯(ウエストバンド・カフス) (スカート・袖口の長さに合わせる)

        イラストモードではパーツの並び順がAIの判定順になるので、
        並び順に頼らずこの3回で順序を保証している。

        Returns:
            ((要求の番号, 何枚目) -> 変形後のパーツ, 種類ごとの一覧)
        """
        precomputed: dict[tuple[int, int], ScaledPart] = {}
        scaled_by_type: dict[str, list[ScaledPart]] = {}
        # round14で袖を1段階増やした。袖は「袖ぐりの実際の長さ」に袖山を
        # 合わせるため身頃より後、カフスは「袖口の実際の長さ」に合わせるため
        # 袖より後でなければならない。順序の制約は
        #   身頃など → 袖 → 帯(waistband/cuffs)
        # の3段階になる。
        # round15: 衿も「実際の首ぐりの長さ」に合わせるため、身頃より後に回す
        # (袖と同じ段。衿と袖は互いに依存しない)。
        _DEFERRED_TYPES = BAND_PART_TYPES + SLEEVE_STAGE_PART_TYPES
        scaled_by_type: dict[str, list[ScaledPart]] = {}
        precomputed: dict[tuple[int, int], ScaledPart] = {}
        # round76: ドロップショルダーを当てた結果。
        drop_run = _DropShoulderRun()
        # round76: 「相手がいるのに相手に合わせられなかった」ものの説明。
        fallback_notes: list[str] = []

        for req_idx, request in enumerate(garment_spec.parts):
            if request.part_type in _DEFERRED_TYPES:
                continue
            quantity = max(1, request.quantity)
            for i in range(quantity):
                # round14: 身頃は「区間ごとに違う倍率」で変形するため、
                # テンプレートSVGが持つ基準点(data-fit-x)を一緒に渡す
                # (engine/bodice_fit.py参照)。持たないパーツでは空リストに
                # なり、従来通りの一律スケーリングになる。
                scaled = scale_template(
                    request.part_type, request.variation,
                    segments_by_idx[req_idx], measurements,
                    fit_anchors=self.template_db.get_fit_anchors(
                        request.part_type, request.variation),
                    fit_anchors_y=self.template_db.get_fit_anchors_y(
                        request.part_type, request.variation),
                    design_length_cm=design_lengths.get(request.part_type),
                    fit=fit,
                    # round30: 切り替え線で分割する身頃はダーツを入れない。
                    # ウエストの絞りは切り替えの縫い目が担う(engine/princess.py)。
                    dartless=(garment_spec.princess_line
                              and request.part_type in PRINCESS_PART_TYPES),
                    block=block)
                # round40: 着てみて合わなかったときの補正。実測した余り/不足を
                # cmで受け取り、基準点(肩先・首の付け根・脇の下・ウエスト)を
                # 使って輪郭を動かす。ここで当てるのは**変形後・縫い代前**——
                # 縫い代を付けたあとで動かすと、縫い代の幅まで変わってしまう。
                #
                # round43: 肩傾斜を製図の角度へ合わせる補正も、ここで同じ
                # 仕組みに乗せる。肩先を動かす操作は round40 と同一なので、
                # **1回の写像にまとめる**——別々に2回かけると、輪郭を2度
                # 分割することになり、極端な体型で自己交差した(実測:
                # バスト50・ヒップ170・身長210の前身頃。変形の途中で当てた
                # ものをヒップの開きが引き継いで壊れていた)。
                part_alterations = dict(alterations or {})
                if request.part_type in ALTERABLE_PART_TYPES:
                    slope_fix = shoulder_slope_correction_cm(
                        scaled.segments, request.part_type,
                        list(scaled.fit_anchors_scaled),
                        list(scaled.fit_anchors_y_scaled),
                        block.shoulder_slope_deg(request.part_type),
                        bust_line_y_cm=scaled.bust_line_y_cm)
                    if slope_fix:
                        part_alterations["shoulder_slope"] = (
                            part_alterations.get("shoulder_slope", 0.0) + slope_fix)
                if part_alterations and request.part_type in ALTERABLE_PART_TYPES:
                    # 基準点は**変形後の座標**を使う(`fit_anchors_scaled`)。
                    # テンプレート座標のまま使うと、変形でずれたぶん的を外す
                    # (実測: ウエストの補正が-2.0cmではなく-1.44cmしか効かな
                    #  かった。engine/scaling.pyの同名フィールドのコメント参照)。
                    scaled = replace(scaled, segments=apply_alterations(
                        scaled.segments, request.part_type,
                        list(scaled.fit_anchors_scaled),
                        list(scaled.fit_anchors_y_scaled),
                        part_alterations,
                        bust_line_y_cm=scaled.bust_line_y_cm,
                        waist_y_cm=scaled.waist_y_cm))
                # round76: ドロップショルダー(engine/drop_shoulder.py)。
                # 肩先を肩線の延長上へ出し、袖ぐりを引き直す。**変形の
                # いちばん最後**に当てる——補正(round40/43)は肩先を動かす
                # 操作なので、先にドロップを当てると補正が動いた肩先を
                # 基準にしてしまう。
                scaled = _with_drop_shoulder(
                    scaled, request.part_type, shoulder_drop_cm, drop_run)
                precomputed[(req_idx, i)] = scaled
                scaled_by_type.setdefault(request.part_type, []).append(scaled)

        # round75: 引いたフードの計画(利用者への注記に使う)。
        hood_plans: list = []

        # round74: 前開きの身頃しか無い型紙のために、**割る前の前身頃**を
        # 同じ設定で1枚だけ変形しておく。袖ぐりを測るためだけに使い、
        # 型紙としては出力しない(`_armhole_per_arm_cm`のコメント参照)。
        unsplit_fronts = self._unsplit_fronts_for_measuring(
            garment_spec, scaled_by_type, measurements, fit, block,
            shoulder_drop_cm=shoulder_drop_cm)

        for req_idx, request in enumerate(garment_spec.parts):
            if request.part_type not in SLEEVE_STAGE_PART_TYPES:
                continue
            quantity = max(1, request.quantity)
            armhole_per_arm = None
            if request.part_type in ("collar", "hood"):
                target = _collar_target_length_cm(scaled_by_type, unsplit_fronts)
            else:
                target = _sleeve_target_cap_cm(
                    scaled_by_type, request.variation, unsplit_fronts,
                    drop_shoulder=bool(drop_run.results))
                armhole_per_arm = _armhole_per_arm_cm(scaled_by_type, unsplit_fronts)
                drop_run.armhole_per_arm_cm = armhole_per_arm
            if target is None:
                note = silent_fallback_note(request.part_type, request.variation,
                                             scaled_by_type)
                if note is not None and note not in fallback_notes:
                    fallback_notes.append(note)
            for i in range(quantity):
                if target is None:
                    # 相手パーツが無い等で目標を決められない場合は、従来通り
                    # 採寸比での独立スケーリングにフォールバックする。
                    scaled = scale_template(request.part_type, request.variation,
                                             segments_by_idx[req_idx], measurements,
                                             fit=fit, block=block)
                elif request.part_type == "hood":
                    # round75: フードは**引く**(engine/hood.py)。
                    # 首ぐりの長さと頭囲の2つに同時に従うので、
                    # テンプレートを比率で伸ばしても片方しか合わない。
                    plan = plan_hood(target, measurements.head_circumference)
                    hood_plans.append(plan)
                    if not plan.usable:
                        scaled = scale_template(
                            request.part_type, request.variation,
                            segments_by_idx[req_idx], measurements,
                            fit=fit, block=block)
                    else:
                        drawn = hood_segments(plan)
                        min_x, min_y, max_x, max_y = bounding_box(drawn)
                        scaled = ScaledPart(
                            part_type=request.part_type,
                            variation=request.variation,
                            segments=drawn, scale_x=1.0, scale_y=1.0,
                            width_cm=max_x - min_x, height_cm=max_y - min_y,
                            dart_count=0)
                elif request.part_type == "collar":
                    scaled = scale_band_to_seam_length(
                        request.part_type, request.variation,
                        segments_by_idx[req_idx], target,
                        seam_edge=self.template_db.get_seam_edge(
                            request.part_type, request.variation))
                else:
                    scaled = scale_sleeve_to_cap_length(
                        request.part_type, request.variation,
                        segments_by_idx[req_idx],
                        # round76: ドロップショルダーでは、肩先が
                        # `shoulder_drop_cm`だけ腕の上へ出ている。袖はその
                        # 分だけ短く引かないと、出来上がりの袖丈が指定より
                        # 伸びる(肩先から手首までが袖丈である)。
                        (replace(measurements,
                                 sleeve_length=max(
                                     1.0, measurements.sleeve_length - shoulder_drop_cm))
                         if drop_run.results else measurements),
                        target,
                        armhole_per_arm_cm=armhole_per_arm,
                        shoulder_drop_cm=(shoulder_drop_cm if drop_run.results else None),
                        fit_anchors_y=self.template_db.get_fit_anchors_y(
                            request.part_type, request.variation),
                        fit=fit,
                        # round57: 袖丈の指定(袖山より下だけを伸縮させる)。
                        design_length_cm=design_lengths.get(request.part_type),
                        block=block)
                precomputed[(req_idx, i)] = scaled
                scaled_by_type.setdefault(request.part_type, []).append(scaled)

        self._scale_band_parts(garment_spec, measurements, segments_by_idx,
                                fit, block, precomputed, scaled_by_type,
                                fallback_notes)
        return (precomputed, scaled_by_type, hood_plans,
                drop_run, fallback_notes)

    def _scale_band_parts(self, garment_spec, measurements, segments_by_idx,
                           fit, block, precomputed, scaled_by_type,
                           fallback_notes):
        """3回目: 帯(ウエストバンド・カフス)を、相手の長さに合わせて引く。

        相手はスカート/パンツのウエスト線と、袖の袖口。どちらも2回目までに
        変形が終わっているので、ここで初めて出来上がりの長さが分かる
        (`_scale_every_part`のdocstringの「3回に分ける理由」)。
        """
        for req_idx, request in enumerate(garment_spec.parts):
            if request.part_type not in BAND_PART_TYPES:
                continue
            quantity = max(1, request.quantity)
            if request.part_type == "waistband":
                target = _waistband_target_width_cm(scaled_by_type)
            else:
                target = _cuffs_target_width_cm(scaled_by_type)
            if target is None:
                note = silent_fallback_note(request.part_type, request.variation,
                                             scaled_by_type)
                if note is not None and note not in fallback_notes:
                    fallback_notes.append(note)
            for i in range(quantity):
                if target is None:
                    # 相手パーツ(skirt/pants/sleeve)が指定されていない場合は、
                    # 従来通り採寸比率による独立スケーリングにフォールバックする。
                    scaled = scale_template(request.part_type, request.variation,
                                             segments_by_idx[req_idx], measurements,
                                             fit=fit, block=block)
                else:
                    # round15: 外接矩形の幅ではなく、実際に縫い付けられる辺の
                    # 長さを目標に合わせる(scale_band_to_seam_length参照)。
                    scaled = scale_band_to_seam_length(
                        request.part_type, request.variation,
                        segments_by_idx[req_idx], target,
                        seam_edge=self.template_db.get_seam_edge(
                            request.part_type, request.variation))
                precomputed[(req_idx, i)] = scaled
                # round16: 帯も合印の計算対象にするため、他のパーツと同じく
                # 種類別の一覧へ入れる(以前はprecomputedにだけ入れていた)。
                scaled_by_type.setdefault(request.part_type, []).append(scaled)

    def _unsplit_fronts_for_measuring(self, garment_spec, scaled_by_type,
                                       measurements, fit, block,
                                       shoulder_drop_cm=None):
        """前開きの型紙で、袖ぐりを測るためだけに「割る前の前身頃」を作る。

        返すのは`ScaledPart`の一覧(測るためだけ。型紙には出さない)。
        前開きでない型紙、または同じバリエーションの`front_bodice`
        テンプレートが無い場合は空の一覧を返す——そのときは従来どおり
        袖ぐりを測れず、呼び出し側が肩幅比へ落ちる。
        """
        # 前開きのパネルが無ければ何もしない。「普通の前身頃も一緒にある
        # なら作らない」という条件も書いたが、**外しても落ちるテストを
        # 作れなかった**ので置かないことにした——パネルと普通の前身頃が
        # 同時に並ぶ組み合わせが、そもそも作れない。
        panels = scaled_by_type.get("front_bodice_zip_panel") or []
        if not panels:
            return []
        variations = {r.variation for r in garment_spec.parts
                      if r.part_type == "front_bodice_zip_panel"}
        out = []
        for variation in sorted(variations):
            segments = self.template_db.get("front_bodice", variation)
            if not segments:
                continue
            scaled = scale_template(
                "front_bodice", variation, segments, measurements,
                fit_anchors=self.template_db.get_fit_anchors(
                    "front_bodice", variation),
                fit_anchors_y=self.template_db.get_fit_anchors_y(
                    "front_bodice", variation),
                fit=fit, block=block)
            # round76: 測るためだけの前身頃にも、同じドロップショルダーを
            # 当てる。当てないと、袖だけが**ドロップ前の袖ぐり**に
            # 合わせて引かれる(前開き+ドロップで袖が付かなくなる)。
            if shoulder_drop_cm:
                dropped = apply_drop_shoulder(
                    scaled.segments, list(scaled.fit_anchors_scaled),
                    list(scaled.fit_anchors_y_scaled), shoulder_drop_cm)
                if dropped is not None:
                    scaled = replace(scaled, segments=dropped.segments,
                                     underarm_y_cm=dropped.underarm_y_cm)
            out.append(scaled)
        return out

    def _prepare_settings(self, measurements, block_key, alterations, fit,
                           design_length_overrides, design,
                           worn_over_bust_cm=None, worn_over_has_sleeves=True,
                           shoulder_drop_cm=None):
        """入力の設定を確かめ、型紙に添える注記を用意する。

        ここで弾けるものは弾く——知らない原型・範囲外の補正は、黙って
        既定に落とさずエラーにする。

        Returns:
            (原型, 検査済みの補正, ゆとり, 部位ごとの丈, 注記の一覧)
        """
        design_lengths: dict[str, float] = {}
        design_notes: list[str] = []
        # round42: どの原型(ブロック)の式で身頃を引くか(engine/blocks.py)。
        # 知らないキーはここでエラーになる——黙って既定に落とすと、
        # 子どもを選んだつもりで大人の型紙が出る。
        block = get_block(block_key)
        # round40: 着てみて合わなかったときの補正(engine/alteration.py)。
        # 知らない項目・範囲外はここで弾く(黙って丸めない)。
        alterations = validate_alterations(alterations or {})
        # round76: 引けないドロップ量はここで弾く。黙って頭打ちにすると、
        # 指定した数字と違う型紙が出たことだけが残る。
        if shoulder_drop_cm:
            reason = too_large_drop_reason(shoulder_drop_cm,
                                            measurements.shoulder_width)
            if reason is not None:
                raise ValueError(reason)
        # round17: イラストから読み取ったデザイン上の丈(cm)。イラストモード
        # 以外はNoneのままで、従来通り採寸だけで決まる。
        design_lengths: dict[str, float] = {}
        design_notes: list[str] = []
        # round24: 既定以外のゆとりを選んだ場合は、実際に使った量を開示する
        # (どのゆとりで作られたかは出来上がりを見ても分かりにくいため)。
        ease = fit_ease(fit)
        # round74: 「この服は何かの上に羽織る」と言われたら、ゆとりの基準を
        # 素体から**中に着る服の出来上がり寸法**へ移す(engine/layering.py)。
        # これをしないと、上に羽織る服が中の服と同じ太さで出てくる。
        layer_plan = None
        if worn_over_bust_cm is not None:
            layer_plan = plan_layer(measurements.bust, worn_over_bust_cm,
                                    inner_has_sleeves=worn_over_has_sleeves)
            ease = replace(ease,
                           bodice_cm=layer_plan.bodice_ease_cm,
                           waist_cm=ease.waist_cm + layer_plan.waist_add_cm,
                           hip_cm=ease.hip_cm + layer_plan.hip_add_cm)
            design_notes.extend(layering_notes(layer_plan))
        if ease != FIT_PRESETS[DEFAULT_FIT] and layer_plan is None:
            # round30: 伸びる生地ではゆとりがマイナスになる。"+-4.15cm" と
            # 出ないよう、符号は値そのものから出す。
            def _signed(value: float) -> str:
                return f"{value:+g}cm"

            design_notes.append(
                f"ゆとり「{ease.label}」で作成しました"
                f"(身頃 バスト{_signed(ease.bodice_cm)} / "
                f"スカート・パンツ ウエスト{_signed(ease.waist_cm)}"
                f"・ヒップ{_signed(ease.hip_cm)})。")
        # round39: 呼び出し側から丈を差し替える(手持ちの生地に収めるために
        # 「スカートを何cm詰めれば入るか」を実際に作って確かめる用途。
        # engine/stash.py参照)。イラストからの読み取りより先に置いて、
        # イラストモードでも上書きが効くようにする。
        if design_length_overrides:
            design_lengths.update(design_length_overrides)
            # round52: 指定された丈を、必ず結果に書く。身長からの比例では
            # なく利用者の指定で決まったことが分かるようにする
            # (round39まではstash内部からしか使われず、画面に出る道が無かった)。
            # round57: 「指定どおりにした」と書くのは、あとで**本当に
            # そうなったか**を確かめてからにする(下の節でまとめて書く)。
            # 当てられなかった指定にまで「指定どおり」と書くと、
            # それ自体が嘘になる。
            # round57: 袖・身頃は「袖ぐりより下だけ」を伸縮させている。
            # 上半分(襟ぐり・袖ぐり・袖山)を動かすと縫い合わせが壊れるため。
            if any(t in ("sleeve",) or t in BODICE_PART_TYPES
                   for t in design_length_overrides):
                design_notes.append(
                    "袖丈・着丈は、袖ぐりより下の部分だけを伸縮させて合わせています"
                    "(襟ぐり・袖ぐり・袖山は採寸から決まる形のままです)。"
                    "そうしないと、丈を変えただけで袖が付かなくなります。")
        design_notes.extend(block_notes(block, measurements.bust,
                                         measurements.height))
        if design is not None:
            design_notes.extend(design.notes())
            length, clamped = skirt_length_cm(design.skirt_ratio, measurements.height)
            if length is not None and "skirt" not in (design_length_overrides or {}):
                design_lengths["skirt"] = length
                design_notes.append(
                    f"スカート丈をイラストに合わせて{length:.0f}cmにしました"
                    + ("(読み取り値が範囲外だったため上下限で止めています)。" if clamped else "。"))
        return block, alterations, ease, design_lengths, design_notes

    def _export_files(self, nesting, lining_nesting, job_id, skip_export,
                       effective_seam_cm, effective_hem_cm, outer_hem_cm,
                       steps, shopping_list, fabric_split, multi_fabric,
                       include_empty_tiles, paper_obj):
        """SVG / PDF / DXF / 投影用を書き出す。

        `skip_export=True` のときは1つも書き出さない(測るためだけの生成)。
        """
        # round39: 手持ちの生地の判定(engine/stash.py)は、丈を変えた型紙を
        # 何通りも作り直して「入るか」を実際に確かめる。その途中経過まで
        # SVG/PDF/DXFに書き出すのは、時間の無駄でありディスクのゴミでもある
        # (実測: 1回の生成0.78秒のうち、書き出しがその大半)。
        # 測るだけの呼び出しは書き出さない。
        if skip_export:
            outputs: dict[str, str] = {}
        else:
            outputs = export_pattern(nesting, self.output_dir, basename=job_id,
                                      seam_allowance_cm=effective_seam_cm,
                                      hem_seam_allowance_cm=effective_hem_cm,
                                      assembly_steps=steps,
                                      shopping_list=shopping_list,
                                      # 1種類しか使わないときは名前を出さない
                                      # (round53までと同じ表紙にするため)。
                                      fabric_name=(fabric_split[0].name
                                                   if multi_fabric else None),
                                      include_empty_tiles=include_empty_tiles,
                                      paper=paper_obj)
            # round41: 裏地は別の生地なので、型紙も別のファイルにする。
            # 表地の型紙に混ぜると、裁つときにどちらの生地で裁つ紙なのかが
            # 一覧の上で分からなくなる(パーツ名の「裏」だけが頼りになる)。
            if lining_nesting is not None:
                lining_outputs = export_pattern(
                    lining_nesting, self.output_dir, basename=f"{job_id}_lining",
                    seam_allowance_cm=effective_seam_cm,
                    hem_seam_allowance_cm=lining_hem_allowance_cm(outer_hem_cm),
                    assembly_steps=None, shopping_list=None,
                    include_empty_tiles=include_empty_tiles, paper=paper_obj)
                outputs.update({f"lining_{k}": v for k, v in lining_outputs.items()})
        return outputs

    def _build_fabric_groups(self, fabric_split, multi_fabric, nesting, outputs,
                              job_id, fabric_width_candidates, allow_rotation,
                              one_way_fabric, shrink_percent, pattern_repeat_cm,
                              effective_seam_cm, effective_hem_cm, steps,
                              skip_export, include_empty_tiles, paper_obj,
                              shopping_list):
        """生地を2種類以上に分けたとき、生地ごとの配置とファイルを作る。

        1種類しか使わないときは空のリストを返す(そのときは`nesting`と
        `outputs`がそのまま1種類ぶんの答えになっている)。
        """
        fabric_group_results: list[FabricGroupResult] = []
        # round54: 2種類目以降の生地。1種類目は上の`nesting`/`outputs`が
        # そのまま担当する(1種類しか使わない場合と同じファイルになる)。
        #
        # 各生地のPDFには**縫う順番を全部入れる**。1着の服なので、
        # 白い生地の紙にだけ「スカートを付ける」工程が無い、という形に
        # するとどちらの紙を見ても作り方が分からなくなる。
        fabric_group_results: list[FabricGroupResult] = []
        if multi_fabric:
            for index, group in enumerate(fabric_split):
                if index == 0:
                    group_nesting, group_outputs = nesting, outputs
                    group_shopping = shopping_list
                else:
                    group_nesting = best_fabric_width(
                        group.parts, candidates=fabric_width_candidates,
                        allow_rotation=allow_rotation, one_way_fabric=one_way_fabric)
                    # round68: ファスナーは「その生地の紙」に載せる。
                    # 前開きのパネルが入っていない生地の買い物メモに
                    # ファスナーを書くと、その生地を買う人が混乱する。
                    group_has_zip = any(
                        p.part_type == "front_bodice_zip_panel"
                        for p in group.parts)
                    group_shopping = build_shopping_list(
                        group.parts, widths=fabric_width_candidates,
                        allow_rotation=allow_rotation, one_way_fabric=one_way_fabric,
                        shrink_percent=shrink_percent,
                        pattern_repeat_cm=pattern_repeat_cm,
                        # 値は表地の買い物メモ(`shopping_list`)が既に
                        # 持っている。ここで測り直さない。
                        front_opening_cm=(shopping_list.front_opening_cm
                                          if group_has_zip else None),
                        front_opening_bottom=shopping_list.front_opening_bottom)
                    group_outputs = {} if skip_export else export_pattern(
                        group_nesting, self.output_dir,
                        basename=f"{job_id}_fabric{index + 1}",
                        seam_allowance_cm=effective_seam_cm,
                        hem_seam_allowance_cm=effective_hem_cm,
                        assembly_steps=steps, shopping_list=group_shopping,
                        fabric_name=group.name,
                        include_empty_tiles=include_empty_tiles, paper=paper_obj)
                fabric_group_results.append(FabricGroupResult(
                    name=group.name, index=index, parts=list(group.parts),
                    part_labels=group.part_labels, nesting=group_nesting,
                    output_files=group_outputs, shopping_list=group_shopping,
                    include_empty_tiles=include_empty_tiles))
                # 裏地と同じやり方で、2種類目以降を`output_files`にも載せる。
                # ダウンロードのリンクは`output_files`の鍵から作られるので、
                # ここに入れないと「生成できているのに取りに行けない」になる。
                if index > 0:
                    outputs.update({f"fabric{index + 1}_{k}": v
                                    for k, v in group_outputs.items()})

            # round57: 生地ごとの章を1本にまとめたPDFも作る。
            #
            # round54では生地の数だけ別のファイルにしていた。コンビニで
            # 印刷する人は2色なら2ファイルを送ることになり、1回で済ませたい
            # のに手間が生地の数だけ増える。**生地ごとのPDFも残したまま**、
            # 「まとめて1本」を足す——どちらが要るかは印刷の仕方で変わる。
            if not skip_export and len(fabric_group_results) > 1:
                combined_path = os.path.join(
                    self.output_dir, f"{job_id}_all_fabrics.pdf")
                render_combined_pdf(
                    [(g.name, g.nesting, g.shopping_list)
                     for g in fabric_group_results],
                    combined_path,
                    seam_allowance_cm=effective_seam_cm,
                    hem_seam_allowance_cm=effective_hem_cm,
                    assembly_steps=steps,
                    include_empty_tiles=include_empty_tiles,
                    paper=paper_obj)
                outputs["all_fabrics_pdf"] = combined_path
        return fabric_group_results

    def _nest_on_fabric(self, finalized_parts, fabric_group_assignments, paper,
                         fabric_width_candidates, allow_rotation, one_way_fabric):
        """確定したパーツを生地の上に並べる。

        Returns:
            (用紙, 生地ごとの分かれ方, 2種類以上か, 並べるパーツ, 配置結果)
        """
        # round54: 生地の割り当て(engine/fabric_groups.py)。
        #
        # 2種類以上に分かれる場合、**全パーツを1枚に詰めた配置は使えない**。
        # 白いパーツと紺のパーツが交互に並ぶので、その紙を白い生地の上に
        # 置いても紺のぶんだけ穴が空く。生地ごとに並べ直す。
        # 1種類のままなら、この行より下はround53までと同じ経路を通る。
        # round57: 用紙(A4/A3)。知らない名前はここで弾く(黙って既定にしない)。
        paper_obj = get_paper(paper)
        fabric_split = split_fabric_groups(finalized_parts, fabric_group_assignments)
        multi_fabric = len(fabric_split) > 1
        nesting_parts = fabric_split[0].parts if multi_fabric else finalized_parts

        nesting = best_fabric_width(nesting_parts, candidates=fabric_width_candidates,
                                     allow_rotation=allow_rotation,
                                     one_way_fabric=one_way_fabric)
        return paper_obj, fabric_split, multi_fabric, nesting_parts, nesting

    def _draw_lining(self, finalized_parts, lining, effective_seam_cm,
                      effective_hem_cm, fabric_width_candidates,
                      allow_rotation, one_way_fabric):
        """裏地の型紙を引いて、裏地だけで並べ直す。

        Returns:
            (裏地のパーツ, 裏地の配置結果, 裏地の注記, 表地の裾の縫い代)
        """
        # round41: 裏地の型紙(engine/lining.py)。表地と**別の生地**なので、
        # 同じ生地に並べてはいけない。裏地だけで並べ直し、別のファイルに
        # 書き出し、買い物メモにも別の行として出す。
        lining_parts_list: list[FinalizedPart] = []
        lining_nesting = None
        lining_note_list: list[str] = []
        # 裾の縫い代を別指定しなかった場合、表地の裾は全辺と同じ幅で裁って
        # いる。裏地の「表地より2cm短く」はその幅からの引き算になる
        # (Noneのまま渡すと、注記が「表地のNone cmから」になる)。
        outer_hem_cm = (effective_seam_cm if effective_hem_cm is None
                         else effective_hem_cm)
        if lining:
            lining_parts_list = build_lining_parts(
                finalized_parts, hem_seam_allowance_cm=outer_hem_cm)
            if lining_parts_list:
                lining_nesting = best_fabric_width(
                    lining_parts_list, candidates=fabric_width_candidates,
                    allow_rotation=allow_rotation, one_way_fabric=one_way_fabric)
                lining_note_list = lining_notes(lining_parts_list, outer_hem_cm)
                cross = yardage_reference_note(
                    lining_parts_list, lining_nesting.used_length_cm,
                    lining_nesting.fabric_width_cm)
                if cross:
                    lining_note_list.append(cross)
        return lining_parts_list, lining_nesting, lining_note_list, outer_hem_cm

    def _build_from_spec(self, garment_spec: GarmentSpec, measurements: Measurements,
                          fabric_width_candidates: tuple[float, ...],
                          allow_rotation: bool = False,
                          seam_allowance_cm: float | None = None,
                          hem_seam_allowance_cm: float | None = None,
                          design: DesignProportions | None = None,
                          fit: str | None = None,
                          one_way_fabric: bool = False,
                          shrink_percent: float | None = None,
                          pattern_repeat_cm: float | None = None,
                          design_length_overrides: dict[str, float] | None = None,
                          skip_export: bool = False,
                          alterations: dict[str, float] | None = None,
                          lining: bool = False,
                          block_key: str | None = None,
                          fabric_group_assignments: dict[str, str] | None = None,
                          include_empty_tiles: bool = False,
                          paper: str | None = None,
                          worn_over_bust_cm: float | None = None,
                          worn_over_has_sleeves: bool = True,
                          shoulder_drop_cm: float | None = None,
                          ) -> PipelineResult:
        """型紙を1着ぶん作る。**この製品の本体**。

        【最初に読む人へ】ここは全体の段取りだけを書いてある。実際の
        中身はそれぞれの段階に分けてあるので、知りたい段階の関数へ
        進んでほしい。順番はこうなっている:

            1. `_prepare_settings`    設定を確かめ、注記を用意する
            2. （テンプレートを読む） SVGから輪郭を取り出す
            3. `_scale_every_part`    採寸に合わせて変形する(3回に分ける)
            4. `_finalize_every_part` 合印・ダーツ・縫い代を入れて確定する
            5. （注記をまとめる）     指定どおりにできたかを書く
            6. `_nest_on_fabric`      生地の上に並べる
            7. `_draw_lining`         裏地を引いて、裏地だけで並べ直す
            8. （買い物メモ・縫う順番）
            9. `_export_files`        SVG / PDF / DXF / 投影用を書き出す
           10. `_build_fabric_groups` 生地を分けたときの、生地ごとの結果
           11. （警告をまとめて返す）

        この順番には理由がある。3は「相手の出来上がり寸法」に合わせる
        パーツがあるので3回に分かれ、6は4が終わらないと並べられず、
        9は6と7の両方が決まってからでないと書き出せない。

        【round63で何をしたか】ここは663行の1つの関数だった。動きは
        何も変えずに、段階ごとに名前を付けて外へ出してある(出力が
        1ビットも変わっていないことは`scripts/snapshot_outputs.py`で
        確かめた)。
        """
        start = time.time()
        (block, alterations, ease, design_lengths,
         design_notes) = self._prepare_settings(
            measurements, block_key, alterations, fit,
            design_length_overrides, design,
            worn_over_bust_cm=worn_over_bust_cm,
            worn_over_has_sleeves=worn_over_has_sleeves,
            shoulder_drop_cm=shoulder_drop_cm)
        # round74: 以降は、`_prepare_settings`が確定させた**ゆとりそのもの**を
        # 渡す。ここを`fit`(プリセット名)のまま流すと、重ね着で計算し直した
        # ゆとりが変形へ届かない——注記には「バスト100cmで引いています」と
        # 出るのに、型紙は標準の90cmのまま、という食い違いが出る(実測で
        # 起きた)。`fit_ease`は`FitEase`をそのまま返すので、重ね着を使わない
        # 呼び出しの挙動は1mmも変わらない。
        fit = ease
        scaled_parts: list[ScaledPart] = []
        finalized_parts: list[FinalizedPart] = []

        # 呼び出し側(generate_from_selection等)で指定が無ければ、インスタンス
        # 既定値(self.seam_allowance_cm/self.hem_seam_allowance_cm)を使う。
        effective_seam_cm = self.seam_allowance_cm if seam_allowance_cm is None else seam_allowance_cm
        effective_hem_cm = self.hem_seam_allowance_cm if hem_seam_allowance_cm is None else hem_seam_allowance_cm

        segments_by_idx: dict[int, list] = {}
        for req_idx, request in enumerate(garment_spec.parts):
            if request.custom_segments is not None:
                # round9で追加: 「定型に当てはまらない自由形状パーツ」
                # (engine/custom_panel.py参照)。TemplateDBを検索せず、
                # 既にcm換算・校正済みの座標をそのまま使う。
                segments_by_idx[req_idx] = request.custom_segments
                continue
            segments = self.template_db.get(request.part_type, request.variation)
            if segments is None:
                raise ValueError(f"テンプレートが見つかりません: {request.part_type}/{request.variation}")
            segments_by_idx[req_idx] = segments

        # round7: waistband/cuffsは「相手パーツ(skirt/pants/sleeve)の縫い
        # 合わせ後の長さ」に幅を合わせる(scale_band_to_target_width参照)ため、
        # 相手パーツを先にスケーリングしてscaled_by_typeを確定させておく
        # 必要がある。generate_from_selection経由ならbuild_garment_spec()が
        # 常にband系パーツを相手より後ろに置くため単純な1パスでも足りるが、
        # generate_from_illustration経由ではAIが検出した領域の順序がそのまま
        # partsの順序になり、band系が相手より先に来ることもありうる。
        # そのため「band系以外を先にスケーリング」→「band系をスケーリング」→
        # 「元のrequests順序でfinalize」という3パス構成にし、partsの並び順に
        # 依存しない実装にした。
        (precomputed, scaled_by_type, hood_plans,
         drop_run, fallback_notes) = self._scale_every_part(
            garment_spec, measurements, segments_by_idx, fit, block,
            alterations, design_lengths, shoulder_drop_cm=shoulder_drop_cm)
        # round76: 相手がいるのに相手へ合わせられなかったパーツと、
        # ドロップショルダーをどう引いたかを開示する。
        design_notes.extend(fallback_notes)
        design_notes.extend(_drop_shoulder_disclosure(
            shoulder_drop_cm, drop_run, scaled_by_type, measurements))
        # round75: フードをどう引いたかを、利用者へ開示する
        # (頭囲を測っていなければ既定値を使ったことも言う)。
        for plan in hood_plans[:1]:
            design_notes.extend(hood_notes(plan))
        (scaled_parts, finalized_parts, princess_stats, princess_failures,
         princess_waist_total, split_records, split_panels
         ) = self._finalize_every_part(
            garment_spec, measurements, precomputed, scaled_by_type,
            fit, ease, effective_seam_cm, effective_hem_cm,
            fabric_width_candidates, allow_rotation, one_way_fabric,
            design_length_overrides, block)

        # round52: カスタムパーツにも縫い代が付いていることを言う。
        #
        # この機能の案内文は「マント・翼・**EVAフォーム装甲プレート**のような
        # 体に沿わない平面的なパーツ」と、**縫わない素材を名指しで勧めている**。
        # ところが出来上がる輪郭には他のパーツと同じ縫い代が足されていて、
        # そのことはどこにも書かれていなかった(round52に実測: 30×40cmの
        # 板が、裁断線32×42cmで出ていた)。フォームや樹脂板は線の上で切るので、
        # 黙って2cm大きい型紙を渡すのは間違いのもとになる。
        if effective_seam_cm > 0 and any(
                p.part_type == CUSTOM_PANEL_PART_TYPE for p in finalized_parts):
            design_notes.append(
                f"カスタムパーツの裁断線には、他のパーツと同じ縫い代"
                f"{effective_seam_cm:g}cmが四方に付いています"
                f"(出来上がり線は破線の方です)。EVAフォームや樹脂板のように"
                # 見出しの番号は入力モードで振り直されるので書かない(round49)。
                "「線の上で切る」素材で作る場合は、「縫い代」の設定を0にするか、"
                "「本体パーツを含めない」でカスタムパーツだけを"
                "縫い代0で生成し直してください。")

        # round52: 縫い代0で**縫うパーツ**が入っている場合に、そのことを言う。
        #
        # 0を通せるようにした(app.pyのSEAM_ALLOWANCE_NONE_CM参照)のは
        # フォーム・樹脂板のような縫わない素材のためだが、同じ設定で
        # 身頃や袖まで0で出てしまう。縫い代の無い型紙で布を裁つと、
        # 縫った分だけ小さい服になる——裁ってからでは戻せない。
        if effective_seam_cm <= 0 and any(
                p.part_type != CUSTOM_PANEL_PART_TYPE for p in finalized_parts):
            design_notes.append(
                "縫い代0で出力しました。裁断線と出来上がり線が同じなので、"
                "布を裁って縫うパーツは、縫った分だけ小さく仕上がります"
                "（EVAフォームや樹脂板のように「線の上で切る」素材だけを"
                "作る場合を除きます）。布で作るパーツがある場合は、"
                "「縫い代」に1cm前後を指定し直してください。")

        # round57: 指定した丈が**実際にどうなったか**を測って書く。
        #
        # 丈の指定は2つの理由で指定値どおりにならないことがある。
        #   1. 胸のダーツを入れると、前身頃の型紙は縦に伸びる。縫うと
        #      ダーツがそのぶんを食うので、**出来上がりは指定どおり**に
        #      なる(実測: バスト84で+5.0cm、バスト110で+8.6cm)。
        #   2. 袖ぐりより下が無くなるほど短い指定は、受け付けずに
        #      無視している(袖山・袖ぐりを壊さないため)。
        # どちらも黙っていると「指定した数字と違う型紙が出た」だけが
        # 残る。測った値をそのまま書く。
        for _part_type, _length in sorted((design_length_overrides or {}).items()):
            _parts = [p for p in finalized_parts if p.part_type == _part_type]
            _scaled = [p for p in scaled_parts if p.part_type == _part_type]
            if not _parts or not _scaled:
                continue
            _label = part_type_label(_part_type)
            _applied = _scaled[0].design_length_applied
            if _applied is False:
                # 当てられなかった。**指定どおりとは書かない**。
                _ys = [y for p in _parts for _x, y in p.stitch_line]
                design_notes.append(
                    f"{_label}の丈は、指定した{_length:g}cmにできませんでした"
                    f"（{max(_ys) - min(_ys):.1f}cmのままです）。袖ぐりより下が"
                    "無くなる短さなので、袖ぐり・袖山を壊さないために"
                    "指定を当てていません。もっと長い値を指定してください。")
                continue
            if _part_type.startswith("back_"):
                continue          # 前後で同じ値なので1回だけ書く
            design_notes.append(
                f"{_label}の丈を、指定どおり{_length:g}cmにしました"
                "(身長からの比例ではありません)。")
            # 胸のダーツを入れると、前身頃の型紙は縦に伸びる。縫うと
            # ダーツがそのぶんを食うので出来上がりは指定どおりになるが、
            # 紙の上の数字が違うことは書いておく(実測: バスト84で+5.0cm、
            # バスト110で+8.6cm)。伸びた量はダーツの口の幅そのものなので、
            # 測り直さずその値を使う。
            _shift = getattr(_scaled[0], "bust_dart_shift_cm", 0.0) or 0.0
            if _shift > 0.6:
                design_notes.append(
                    f"{_label}の型紙は、胸のダーツぶん{_shift:.1f}cm長く"
                    "出ています。縫うとダーツがそのぶんを食うので、"
                    "出来上がりは指定どおりの丈になります。")

        # round35: 同じ枚数に分かれたパーツはまとめて1文にする(前後で同じ
        # 説明が2回並ぶのを避ける。merge_part_labelsのdocstring参照)。
        split_notes = [split_note(labels, count, effective_seam_cm)
                       for count, labels in sorted(split_records.items())]

        (paper_obj, fabric_split, multi_fabric,
         nesting_parts, nesting) = self._nest_on_fabric(
            finalized_parts, fabric_group_assignments, paper,
            fabric_width_candidates, allow_rotation, one_way_fabric)
        (lining_parts_list, lining_nesting,
         lining_note_list, outer_hem_cm) = self._draw_lining(
            finalized_parts, lining, effective_seam_cm, effective_hem_cm,
            fabric_width_candidates, allow_rotation, one_way_fabric)
        # round38: 買い物メモ。生地幅ごとの必要量は「内部で計算していたのに
        # 捨てていた」数字で、近所の店に置いている幅が違う人には、
        # おすすめの1つだけ見せても役に立たない。
        # round68: 前開きの開き寸法。縫う順番は「ファスナーを付ける」と
        # 言うのに、買い物メモにファスナーが一度も出てこなかった。
        front_opening_cm = _front_opening_length_cm(finalized_parts, scaled_parts)
        shopping_list = build_shopping_list(
            nesting_parts, widths=fabric_width_candidates,
            allow_rotation=allow_rotation, one_way_fabric=one_way_fabric,
            shrink_percent=shrink_percent, pattern_repeat_cm=pattern_repeat_cm,
            lining_parts=lining_parts_list,
            front_opening_cm=front_opening_cm,
            front_opening_bottom=_front_opening_bottom(finalized_parts))
        job_id = uuid.uuid4().hex[:12]
        # round33: 縫う順番をPDFにも入れる。縫うときに見ているのは布と紙で
        # あってブラウザではないので、型紙と一緒に必ず届くようにする。
        steps = assembly_steps(
            finalized_parts,
            seam_allowance_cm=effective_seam_cm,
            hem_seam_allowance_cm=effective_hem_cm,
            sleeve_cap_ease_cm=_sleeve_cap_ease_for(finalized_parts),
            front_zip=any(p.part_type == "front_bodice_zip_panel"
                          for p in finalized_parts),
            split_panels=split_panels,
            lining_parts=lining_parts_list)
        outputs = self._export_files(
            nesting, lining_nesting, job_id, skip_export,
            effective_seam_cm, effective_hem_cm, outer_hem_cm,
            steps, shopping_list, fabric_split, multi_fabric,
            include_empty_tiles, paper_obj)

        fabric_group_results = self._build_fabric_groups(
            fabric_split, multi_fabric, nesting, outputs, job_id,
            fabric_width_candidates, allow_rotation, one_way_fabric,
            shrink_percent, pattern_repeat_cm, effective_seam_cm,
            effective_hem_cm, steps, skip_export, include_empty_tiles,
            paper_obj, shopping_list)

        warnings = (measurement_clamp_warnings(measurements, fit, block)
                     + block_warnings(block, measurements.height))
        # round14: 入力した肩幅を型紙へ反映できなかった場合の注記
        # (engine/scaling.pyのbodice_fit_clamp_warning参照)。身頃を含む
        # 生成のときだけ意味を持つ。
        bodice_anchors = next(
            (self.template_db.get_fit_anchors(r.part_type, r.variation)
             for r in garment_spec.parts if r.part_type == "front_bodice"), [])
        shoulder_note = bodice_fit_clamp_warning(bodice_anchors, measurements,
                                                  block)
        if shoulder_note:
            warnings = warnings + [shoulder_note]

        princess_waist_cm = (princess_waist_total
                              if garment_spec.princess_line and princess_stats
                              else None)
        return PipelineResult(
            job_id=job_id, garment_spec=garment_spec, measurements=measurements,
            scaled_parts=scaled_parts, finalized_parts=finalized_parts, nesting=nesting,
            output_files=outputs, elapsed_seconds=time.time() - start,
            measurement_warnings=(warnings
                                   + _upper_arm_notes(measurements, finalized_parts, ease)
                                   + _hip_shortfall_notes(scaled_parts, measurements, ease)
                                   + _bust_dart_notes(scaled_parts, measurements)
                                   + _chest_width_notes(scaled_parts, measurements)
                                   + _waist_slack_notes(
                                       finalized_parts, scaled_parts,
                                       measurements, ease,
                                       finished_override_cm=princess_waist_cm,
                                       princess_available=not any(
                                           p.part_type == "front_bodice_zip_panel"
                                           for p in finalized_parts))
                                   + _princess_warnings(princess_stats,
                                                         princess_failures)
                                   + _unprintable_label_warnings(finalized_parts)
                                   + _unprintable_fabric_name_warnings(fabric_group_results)),
            # round66: 「測れなかったので確かめていない」も注記に混ぜる。
            # 黙って飛ばすと「確かめて問題なし」と区別が付かない。
            design_notes=(design_notes + alteration_notes(alterations) + split_notes
                           + _princess_notes(princess_stats, princess_failures)
                           + unchecked_seams(finalized_parts)),
            split_panels=split_panels,
            shopping_list=shopping_list,
            seam_allowance_cm=effective_seam_cm, hem_seam_allowance_cm=effective_hem_cm,
            lining_parts=lining_parts_list, lining_nesting=lining_nesting,
            lining_notes=lining_note_list,
            fabric_groups=fabric_group_results,
            include_empty_tiles=include_empty_tiles,
            paper_name=paper_obj.name,
            resolved_design_lengths=dict(design_lengths),
        )

    def generate_from_selection(self, garment_spec: GarmentSpec, measurements: Measurements,
                                 fabric_width_candidates: tuple[float, ...] = DEFAULT_FABRIC_WIDTHS_CM,
                                 allow_rotation: bool = False,
                                 seam_allowance_cm: float | None = None,
                                 hem_seam_allowance_cm: float | None = None,
                                 fit: str | None = None,
                                 one_way_fabric: bool = False,
                                 shrink_percent: float | None = None,
                                 pattern_repeat_cm: float | None = None,
                                 design_length_overrides: dict[str, float] | None = None,
                                 skip_export: bool = False,
                                 alterations: dict[str, float] | None = None,
                                 lining: bool = False,
                                 block_key: str | None = None,
                                 fabric_group_assignments: dict[str, str] | None = None,
                                 include_empty_tiles: bool = False,
                                 paper: str | None = None,
                                 worn_over_bust_cm: float | None = None,
                                 worn_over_has_sleeves: bool = True,
                                 shoulder_drop_cm: float | None = None,
                                 ) -> PipelineResult:
        """STEP④〜⑥: 手動で選んだ構成から型紙を生成する（既定の確実な経路）。

        allow_rotation: 90度回転配置を許可するか。既定Falseは全パーツの布目を
            生地の縦地に揃える「布目安全」モード。ニット等の非方向性生地を
            使う場合のみTrueにして布ロスをさらに減らせる。
        seam_allowance_cm/hem_seam_allowance_cm: 指定すればこの1回の生成
            だけインスタンス既定値を上書きする(round5「縫い代を辺ごとに
            設定可能に」)。hem_seam_allowance_cmは裾だけ別幅にしたい場合に
            使う(判定方法はengine.seam.offset_polygon_variable参照)。
        """
        return self._build_from_spec(garment_spec, measurements, fabric_width_candidates,
                                      allow_rotation=allow_rotation,
                                      seam_allowance_cm=seam_allowance_cm,
                                      hem_seam_allowance_cm=hem_seam_allowance_cm,
                                      fit=fit,
                                      one_way_fabric=one_way_fabric,
                                      shrink_percent=shrink_percent,
                                      pattern_repeat_cm=pattern_repeat_cm,
                                      design_length_overrides=design_length_overrides,
                                      skip_export=skip_export,
                                      alterations=alterations,
                                      lining=lining,
                                      block_key=block_key,
                                      fabric_group_assignments=fabric_group_assignments,
                                      include_empty_tiles=include_empty_tiles,
                                      paper=paper,
                                      worn_over_bust_cm=worn_over_bust_cm,
                                      worn_over_has_sleeves=worn_over_has_sleeves,
                                      shoulder_drop_cm=shoulder_drop_cm)

    #: round39: 丈を詰める提案の出発点にする部位。
    #: 「詰めれば入る」と言うには、いまの丈が分かっている必要がある。
    STASH_SHORTENABLE_PART_TYPES = ("skirt", "sleeve")

    def evaluate_stash_for(self, result: PipelineResult,
                            garment_spec: GarmentSpec, measurements: Measurements,
                            *, have_width_cm: float, have_length_cm: float,
                            allow_rotation: bool = False,
                            one_way_fabric: bool = False,
                            fit: str | None = None,
                            seam_allowance_cm: float | None = None,
                            hem_seam_allowance_cm: float | None = None,
                            fabric_group_assignments: dict[str, str] | None = None,
                            fabric_group_name: str | None = None,
                            ) -> StashVerdict:
        """手持ちの生地で足りるかを判定する(round39)。

        `engine/stash.py`は「丈を変えた型紙を作り直して、入るか確かめる」
        という形で動くので、作り直す手段をここで渡す。作り直しは
        `skip_export=True`——測るだけの生成なので、途中経過のSVG/PDF/DXFは
        書き出さない(実測で3.93秒→1.72秒、`generated/`のゴミも出ない)。
        """
        # round55: 生地を分けているときは、**その生地のぶんだけ**を測る。
        #
        # 手持ちの端切れは1種類の生地である。全パーツを1枚に詰めた長さで
        # 判定すると、「白い身頃＋紺のスカート」の紺だけを持っている人に
        # 「117cm足りません」と答えてしまう——実際には紺のぶんは124cmで、
        # 130cmの手持ちに**収まっていた**。持っている生地を使わずに
        # 買い足させる、いちばん困る間違え方である。
        def _build(**kwargs):
            merged = dict(allow_rotation=allow_rotation,
                           one_way_fabric=one_way_fabric,
                           fit=fit,
                           seam_allowance_cm=seam_allowance_cm,
                           hem_seam_allowance_cm=hem_seam_allowance_cm,
                           fabric_group_assignments=fabric_group_assignments)
            merged.update(kwargs)
            built = self.generate_from_selection(garment_spec, measurements, **merged)
            if fabric_group_name is not None:
                for group in built.fabric_groups:
                    if group.name == fabric_group_name:
                        # 測るのはこの生地のぶんだけ。`stash.py`は
                        # `result.nesting`しか見ないので、差し替えれば足りる
                        # (skip_export=Trueの使い捨ての結果なので安全)。
                        built.nesting = group.nesting
                        break
            return built

        # 詰める提案の出発点も、その生地に載るパーツだけにする。
        #
        # 【正直な記録】これは**今の出力を変えない**。提案は「その丈で作り
        # 直して本当に収まったか」を測ってから残す作りなので、別の生地の
        # パーツを出発点に混ぜても、効かない提案は自動的に捨てられる
        # (round55に実測: 表地の提案は混ぜても混ぜなくても0件)。
        # それでも狭めてあるのは、「紺サテンの紙が足りない」話に
        # 表地の袖を出発点として渡すのが、意味として間違っているからである。
        # 効果を示せていないので、直した一覧には数えていない。
        measured_parts = result.finalized_parts
        if fabric_group_name is not None:
            for group in result.fabric_groups:
                if group.name == fabric_group_name:
                    measured_parts = group.parts
                    break
        current_lengths: dict[str, float] = {}
        for part in measured_parts:
            if part.part_type in self.STASH_SHORTENABLE_PART_TYPES:
                current_lengths.setdefault(part.part_type, part.height_cm)

        return evaluate_stash(_build, have_width_cm=have_width_cm,
                               have_length_cm=have_length_cm,
                               current_lengths=current_lengths,
                               allow_rotation=allow_rotation,
                               one_way_fabric=one_way_fabric,
                               # round59: 手芸店でふつうに買える生地幅。
                               # 手持ちで足りないとき、この幅で並べ直して
                               # 買う量が減るなら、それを言う。
                               other_width_candidates=DEFAULT_FABRIC_WIDTHS_CM)

    def generate_from_illustration(self, image, measurements: Measurements,
                                    fabric_width_candidates: tuple[float, ...] = DEFAULT_FABRIC_WIDTHS_CM,
                                    allow_rotation: bool = False,
                                    seam_allowance_cm: float | None = None,
                                    hem_seam_allowance_cm: float | None = None,
                                    views: list[str] | tuple[str, ...] | None = None,
                                    fit: str | None = None,
                                    design_length_overrides: dict[str, float] | None = None,
                                    fabric_group_assignments: dict[str, str] | None = None,
                                    include_empty_tiles: bool = False,
                                    paper: str | None = None,
                                    # round57: ここまで、イラストモードは
                                    # 下の6つを**受け取れなかった**。
                                    # 画面には欄があり、値の検査まで通るのに
                                    # エンジンへ渡る道が無く、裏地を選んでも
                                    # 裏地の型紙が出ない、補正を入れても効かない、
                                    # という状態だった(round55で手動側を直した
                                    # のと同じ形の取り落とし)。
                                    one_way_fabric: bool = False,
                                    shrink_percent: float | None = None,
                                    pattern_repeat_cm: float | None = None,
                                    alterations: dict[str, float] | None = None,
                                    lining: bool = False,
                                    block_key: str | None = None,
                                    worn_over_bust_cm: float | None = None,
                                    worn_over_has_sleeves: bool = True,
                                    shoulder_drop_cm: float | None = None,
                                    ) -> PipelineResult:
        """STEP①〜⑥: イラストからパーツ構成とデザイン上の比率を推定して生成する。

        round18で**複数枚**を受け付けるようにした。`image` には1枚の
        `PIL.Image` でも、複数枚のリスト/タプルでも渡せる(1枚のときの
        挙動は従来と同じ)。複数枚の扱いは次のとおり:

          パーツ構成 … 全枚の検出結果の**和**を取る。1枚では見切れていた
                       パーツ(袖・衿など)が別のカットに写っていれば拾える。
          比率       … 枚ごとに読み取り、項目ごとの**中央値**を使う
                       (`engine/illustration_fit.combine_proportions`)。
                       1枚だけ大きく外れた読み取りに引きずられない。

        round21で**前後の区別**を追加した。`views` に画像と同じ長さの
        リストを渡すと、各画像が「前から見た絵」("front")か「後ろから見た
        絵」("back")かを指定できる(""は指定なし=前として読む。`views`
        自体を省略すれば全て指定なしになり、round20までと同じ動きになる)。

        絵から読み取れるもののうち、前後で違いうるのは**襟ぐりの形**である
        (丈と裾の広がりは前から見ても後ろから見ても同じなので、従来どおり
        全枚の中央値を使う)。そこで:

          前の絵から読んだ襟ぐり → front_bodice のネックライン
          後ろの絵から読んだ襟ぐり → back_bodice のネックライン

        とする。後ろの絵が無ければ、後身頃は従来どおり前身頃と同じ
        ネックラインになる。

        ただし**前後で首の開き幅が違うと肩線の長さが合わず縫えない**。
        ボートネックだけは首の開きが他の1.75倍あり、実測で肩線が
        4.10〜4.89cm食い違う(標準の前後差は0.31cm)。この組み合わせに
        なった場合は、黙って縫えない型紙を出さず、後身頃を前と同じ
        ネックラインに戻したうえで**その理由を注記として開示する**。
        判定は`engine/compatibility.shoulder_seams_match`に集約しており、
        生成後のチェッカー(チェック7)とまったく同じ許容誤差を使う。

        正直な限界: 「どちらが前か」は利用者の指定でのみ決まる。絵を見て
        前後を判定してはいない(後ろ姿かどうかをシルエットから見分ける
        手掛かりが無いため)。また前後で違いうるのは襟ぐりだけで、
        「背中が大きく開いている」といった身頃そのものの造形は、
        テンプレートに該当する形が無いため反映できない。
        """
        images = list(image) if isinstance(image, (list, tuple)) else [image]
        if not images:
            raise ValueError("イラストが1枚も渡されていません。")

        if views is None:
            view_list = [""] * len(images)
        else:
            view_list = list(views)
            if len(view_list) != len(images):
                raise ValueError(
                    f"views は画像と同じ枚数で指定してください"
                    f"(画像{len(images)}枚に対して views は{len(view_list)}件)。")
            unknown = [v for v in view_list if v not in ILLUSTRATION_VIEWS]
            if unknown:
                raise ValueError(
                    f"views に指定できるのは {sorted(ILLUSTRATION_VIEWS)} のいずれかです: "
                    f"{unknown!r}")

        segmenter = get_default_segmenter()
        classifier = get_default_classifier()

        classifications: list[ClassificationResult] = []
        requests: list[PartRequest] = []
        readings: list[DesignProportions] = []
        sleeve_readings: list[SleeveReading] = []
        colour_readings: list = []
        # sleeve/cuffs/front_pants/back_pants/skirtは「左右一対」または「前後一対」で2枚必要な
        # パーツ種（PAIR_LABELS参照）。これらはpart_typeだけで重複排除する
        # （variationまで含めて排除すると、AIが左右の領域を別バリエーションと
        # 誤判定した場合に2種類×2枚=4枚が生成されてしまうため）。
        # front_bodice/back_bodice/collar/waistbandはvariationごとに区別する。
        # 複数枚のときは、この`seen`を全枚で共有することで「和を取る」を実現する。
        seen: set = set()

        def _add(part_type: str, variation: str, quantity: int) -> None:
            key = part_type if part_type in PAIR_LABELS else (part_type, variation)
            if key in seen:
                return
            seen.add(key)
            requests.append(PartRequest(part_type, variation, quantity))

        mask_source = getattr(segmenter, "silhouette_mask", None)
        # round21: 前から見た絵と後ろから見た絵で、別々に襟ぐりを集める。
        necklines: list[str] = []          # 前(および指定なし)の絵から
        back_necklines: list[str] = []     # 後ろの絵から
        for one, view in zip(images, view_list):
            regions = segmenter.segment(one)
            if callable(mask_source):
                mask = mask_source(one)
                # round72: 絵の色から、肌と服を見分ける。人物が着ている絵で
                # 袖を読むのと、腕に邪魔されずにスカートの裾を見つけるのに使う。
                colours = read_colours(one, mask)
                colour_readings.append(colours)
                readings.append(measure_proportions(mask, colours))
                # round22: 袖の有無・袖丈・袖の形をシルエットから読む。
                # round72: 人物の絵では色から読む。
                sleeve_readings.append(
                    measure_sleeves(mask, measurements.height, colours))
                # round18: シルエットの上辺の凹み=襟ぐりの形を読む。
                detected = measure_neckline(mask)
                if detected:
                    (back_necklines if view == "back" else necklines).append(detected)
            for region in regions:
                crop = region.crop(one)
                if crop.width < 4 or crop.height < 4:
                    continue
                # round45: 判定の回数に上限を置く。領域数には上限が無く、
                # SAMを使う構成では1枚で数十〜数百の領域が返りうるため、
                # その全部に外部APIを1回ずつ投げていた。
                if len(classifications) >= MAX_CLASSIFICATIONS_PER_REQUEST:
                    break
                result = classifier.classify(crop, region_label=region.label)
                classifications.append(result)
                if not result.part_type:
                    continue
                # PAIR_LABELSに定義されている全パーツ種(sleeve/cuffs/front_pants/back_pants/skirt)は
                # 2枚一対で必要（例: skirtは前後2枚）。
                quantity = 2 if result.part_type in PAIR_LABELS else 1
                _add(result.part_type, result.variation, quantity)
                # 前身頃が判定できたら、対応する後身頃も同じネックラインで自動的に追加する。
                if result.part_type == "front_bodice":
                    _add("back_bodice", result.variation, 1)

        if not requests:
            raise ValueError(
                "イラストからパーツ種を判定できませんでした。"
                "背景を単色にするか、手動選択モードをお試しください。"
            )

        # round18: 読み取れた襟ぐりの形で、身頃のバリエーションを差し替える。
        # 既定の判定器(APIキー無しのMockPartClassifier)は領域ラベルから
        # 決め打ちするため、round17まではどんなイラストでも必ず
        # round_neckになっていた。複数枚のときは多数決を採る。
        #
        # round21: 前の絵と後ろの絵で別々に多数決を採り、前身頃と後身頃に
        # それぞれ適用する。後ろの絵が無ければ後身頃は前と同じになる
        # (=round20までとまったく同じ動き)。
        n_front_images = sum(1 for v in view_list if v != "back")
        n_back_images = len(view_list) - n_front_images

        def _majority(votes: list[str]) -> tuple[str, int] | None:
            if not votes:
                return None
            chosen = max(set(votes), key=votes.count)
            return chosen, votes.count(chosen)

        neckline_notes: list[str] = []
        front_choice = _majority(necklines)
        back_choice = _majority(back_necklines)

        if front_choice and back_choice and front_choice[0] != back_choice[0]:
            # 前後で首の開き幅が違うと肩線が合わず縫えない。生成前にここで
            # 弾き、理由を開示する(黙って縫えない型紙を出さない)。
            if not shoulder_seams_match(
                    self._template_shoulder_cm("front_bodice", front_choice[0]),
                    self._template_shoulder_cm("back_bodice", back_choice[0])):
                neckline_notes.append(
                    f"後ろの絵からは襟ぐり {back_choice[0]} を読み取りましたが、"
                    f"前の {front_choice[0]} と首の開き幅が違うため肩線の長さが合わず、"
                    "そのままでは肩を縫い合わせられません。"
                    f"後身頃も {front_choice[0]} にしています。"
                )
                back_choice = None

        front_variation = front_choice[0] if front_choice else None
        back_variation = (back_choice[0] if back_choice
                          else front_variation)

        if front_variation or back_variation:
            def _substitute(r: PartRequest) -> PartRequest:
                if r.part_type == "front_bodice" and front_variation:
                    return PartRequest(r.part_type, front_variation, r.quantity, r.custom_segments)
                if r.part_type == "back_bodice" and back_variation:
                    return PartRequest(r.part_type, back_variation, r.quantity, r.custom_segments)
                return r
            requests = [_substitute(r) for r in requests]

        if front_choice:
            source = (f"({front_choice[1]}/{n_front_images}枚から)"
                      if n_front_images > 1 else "")
            label = "前身頃の" if back_choice else ""
            neckline_notes.insert(
                0, f"イラストから読み取った{label}襟ぐりの形: {front_choice[0]}{source}")
        if back_choice:
            source = (f"({back_choice[1]}/{n_back_images}枚から)"
                      if n_back_images > 1 else "")
            neckline_notes.insert(
                1 if front_choice else 0,
                f"後ろの絵から読み取った後身頃の襟ぐりの形: {back_choice[0]}{source}")

        # round17: シルエットから「丈」と「裾の広がり」を測り、型紙へ反映する。
        # round16まではイラストが(part_type, variation)の選択にしか使われて
        # おらず、まったく違うデザインでも寸法が1mmも変わらなかった
        # (engine/illustration_fit.py のモジュールdocstringに実測を記載)。
        design = combine_proportions(readings) if readings else DesignProportions(image_count=0)
        if design.hem_flare is not None:
            # 読み取った広がりに最も近いスカートへ差し替える。
            requests = [
                PartRequest("skirt", choose_skirt_variation(design.hem_flare, r.variation),
                             r.quantity, r.custom_segments)
                if r.part_type == "skirt" else r
                for r in requests
            ]

        # round22: 袖をシルエットから決める。round21までは袖がまったく
        # 読めておらず、ノースリーブの絵でも半袖の絵でも長袖の絵でも、
        # 判定器の既定値(通常straight)の袖が同じように付いていた。
        sleeve_note = self._apply_sleeve_reading(sleeve_readings, requests)
        if sleeve_note:
            requests, note = sleeve_note
            neckline_notes.append(note)

        spec = GarmentSpec(parts=requests)
        result = self._build_from_spec(spec, measurements, fabric_width_candidates,
                                        allow_rotation=allow_rotation,
                                        seam_allowance_cm=seam_allowance_cm,
                                        hem_seam_allowance_cm=hem_seam_allowance_cm,
                                        design=design, fit=fit,
                                        # round52: 丈の指定は、絵からの読み取り
                                        # より優先する(_build_from_spec 側が
                                        # `"skirt" not in design_length_overrides`
                                        # を見て上書きしないようにしてある)。
                                        design_length_overrides=design_length_overrides,
                                        fabric_group_assignments=fabric_group_assignments,
                                        include_empty_tiles=include_empty_tiles,
                                        paper=paper,
                                        worn_over_bust_cm=worn_over_bust_cm,
                                        worn_over_has_sleeves=worn_over_has_sleeves,
                                        shoulder_drop_cm=shoulder_drop_cm,
                                        # round57: 画面にある設定は、イラスト
                                        # モードでも効かせる(それまで裏地・補正・
                                        # 一方方向の生地・収縮率・柄のリピート・
                                        # 原型の6つが、受け取りながら渡って
                                        # いなかった)。
                                        one_way_fabric=one_way_fabric,
                                        shrink_percent=shrink_percent,
                                        pattern_repeat_cm=pattern_repeat_cm,
                                        alterations=alterations,
                                        lining=lining,
                                        block_key=block_key)
        if neckline_notes:
            result.measurement_warnings = result.measurement_warnings + neckline_notes
        result.classification_log = classifications
        return result

    @staticmethod
    def _apply_sleeve_reading(readings: list[SleeveReading], requests: list[PartRequest]
                               ) -> tuple[list[PartRequest], str] | None:
        """イラストから読んだ袖を、実際のパーツ構成へ反映する(round22)。

        複数枚のときは多数決を採る(枚数ごとに違う袖が読めた場合、いちばん
        多く読めたものを使う)。読み取れた枚数が0なら何もしない。

        ノースリーブと読めた場合は袖を外す。**カフスも一緒に外す**——
        袖が無いのにカフスだけ残ると、縫い付ける相手が無いパーツが1枚
        混ざった型紙になる(`build_garment_spec`が手動モードで同じ
        組み合わせを明確なエラーにしているのと同じ理由)。

        返り値は (新しいrequests, 利用者へ出す注記) または None。
        """
        picks = [choose_sleeve_variation(r, "") for r in readings if r.detected]
        if not picks:
            return None
        chosen = max(set(picks), key=picks.count)
        agree = picks.count(chosen)
        source = f"({agree}/{len(readings)}枚から)" if len(readings) > 1 else ""

        if chosen is None:
            kept = [r for r in requests if r.part_type not in ("sleeve", "cuffs")]
            if len(kept) == len(requests):
                return None
            return kept, f"イラストにはノースリーブと判断し、袖を付けていません{source}。"

        if not chosen:
            return None
        replaced = [
            PartRequest(r.part_type, chosen, r.quantity, r.custom_segments)
            if r.part_type == "sleeve" else r
            for r in requests
        ]
        if replaced == requests:
            return None
        return replaced, f"イラストから読み取った袖の形: {chosen}{source}"

    def _template_shoulder_cm(self, part_type: str, variation: str) -> float | None:
        """テンプレート(標準Mサイズ)そのものの肩線の長さ(cm)。round21で追加。

        前後で違うネックラインを組み合わせてよいかを**生成する前に**
        判定するために使う。体型スケーリングは前後の身頃に同じ規則
        (engine/part_specs.py の PART_SCALE_RULES)で効くので、標準サイズで
        比べた大小関係はスケーリング後も変わらない。
        """
        segments = self.template_db.get(part_type, variation)
        if not segments:
            return None
        return shoulder_seam_length(SimpleNamespace(
            part_type=part_type, variation=variation,
            stitch_line=segments_to_polyline(segments)))

    def generate_multi_size(self, garment_spec: GarmentSpec, base_measurements: Measurements,
                             sizes: list[str],
                             fabric_width_candidates: tuple[float, ...] = DEFAULT_FABRIC_WIDTHS_CM,
                             allow_rotation: bool = False,
                             seam_allowance_cm: float | None = None,
                             hem_seam_allowance_cm: float | None = None,
                             custom_grade_cm: dict[str, float] | None = None,
                             fit: str | None = None,
                             fabric_group_assignments: dict[str, str] | None = None,
                             # round58: ここから下は`_build_from_spec`が元から
                             # 受け取れたのに、サイズ展開だけ**受け取る口が
                             # 無かった**設定である。画面には欄があり、値の
                             # 検査まで通り、押せるのに効かなかった。
                             # 実測(同じフォームでモードだけ変えた):
                             #   用紙A3        手動 12枚 / サイズ展開 23枚(A4)
                             #   着丈45cm      手動 49.6cm / サイズ展開 65.2cm
                             #   原型「子ども」 手動 子ども式 / サイズ展開 大人式
                             #   収縮率5%      手動「買うのは70cm」/ サイズ展開 記載なし
                             # 同じ取り落としはround52(イラスト)・round55(手動)・
                             # round57(イラスト)でも起きている。4回目なので、
                             # 下の`test_every_entry_point_accepts_the_same_settings`で
                             # **署名そのものを突き合わせて**止めるようにした。
                             one_way_fabric: bool = False,
                             shrink_percent: float | None = None,
                             pattern_repeat_cm: float | None = None,
                             design_length_overrides: dict[str, float] | None = None,
                             alterations: dict[str, float] | None = None,
                             lining: bool = False,
                             block_key: str | None = None,
                             include_empty_tiles: bool = False,
                             paper: str | None = None,
                             worn_over_bust_cm: float | None = None,
                             worn_over_has_sleeves: bool = True,
                             shoulder_drop_cm: float | None = None,
                             ) -> MultiSizeResult:
        """round5で追加。同じパーツ構成(garment_spec)を、複数サイズ分まとめて
        生成する（「S/M/Lを一式まとめて発注したい」というブランド・作り手向けの
        ユースケースを想定）。

        base_measurementsは「利用者が入力した採寸値をどのサイズとみなすか」の
        基準で、`engine.measurements.graded_measurements`で述べた通り、
        既定ではJIS L4005のS/M/L系列を単純化した線形の刻み幅(バスト/ウエスト/
        ヒップは4cm、肩幅/袖丈は1cm、身長は変えない)で前後のサイズを機械的に
        算出する(実際のブランド固有のグレーディングルールとは異なる、正直な
        近似であることを明記する)。

        各サイズは完全に独立した1回の生成として扱われ、それぞれ個別の
        job_id・SVG/PDF/DXFを持つ(単体でも`/download/<job_id>/<fmt>`で
        取得できる)。加えて、全サイズ分をまとめた1つのZIPも生成する
        (`engine.pdf_export.export_multi_size_bundle`)。

        Args:
            sizes: 生成するサイズ名のリスト(`engine.measurements.
                STANDARD_SIZE_STEPS`のキー、例: ["S", "M", "L"])。
                重複や空リストは呼び出し側の責任で防ぐこと(ここでは
                空リストならValueErrorにする)。
            custom_grade_cm: round7で追加。自社の実際のグレーディングルールを
                把握している利用者向けに、既定の`STANDARD_SIZE_GRADE_CM`の
                代わりに使う部位ごとのカスタム刻み幅。指定しなかった項目は
                既定値のまま使われる(部分的な上書きが可能)。
                `engine.measurements.validate_custom_grade_cm()`で検証する
                (範囲外の値やキー名の誤りはここでValueError/TypeErrorになる)。
        """
        if not sizes:
            raise ValueError("sizes は1つ以上指定してください。")
        unknown = [s for s in sizes if s not in STANDARD_SIZE_ORDER]
        if unknown:
            raise ValueError(
                f"サイズ名が不正です: {unknown}。指定可能なサイズは{list(STANDARD_SIZE_ORDER)}です。"
            )
        validated_grade_cm = validate_custom_grade_cm(custom_grade_cm) if custom_grade_cm else None

        results: dict[str, PipelineResult] = {}
        for size in sizes:
            measurements = graded_measurements(base_measurements, size, grade_cm=validated_grade_cm)
            results[size] = self._build_from_spec(
                garment_spec, measurements, fabric_width_candidates,
                allow_rotation=allow_rotation,
                seam_allowance_cm=seam_allowance_cm,
                hem_seam_allowance_cm=hem_seam_allowance_cm,
                fit=fit,
                # round55: サイズ展開でも生地の割り当てを効かせる。
                # それまでは受け取って検査までしておきながら**渡していなかった**
                # ので、2色の衣装をS/M/Lで作ると全サイズが1種類の生地に
                # 詰めた配置で出ていた(画面にもPDFにも何も出ない)。
                fabric_group_assignments=fabric_group_assignments,
                # round58: 残り8件。丈の指定だけは**サイズごとに変えない**
                # ——利用者が「スカート丈45cm」と書いたのは出来上がりの
                # 45cmのことで、Sだから43cmにしてほしいという意味ではない。
                # 身幅はグレーディングで変わり、丈は指定どおりになる。
                # これは選択なので、画面にも注記として出す(app.py参照)。
                one_way_fabric=one_way_fabric,
                shrink_percent=shrink_percent,
                pattern_repeat_cm=pattern_repeat_cm,
                design_length_overrides=design_length_overrides,
                alterations=alterations,
                lining=lining,
                block_key=block_key,
                include_empty_tiles=include_empty_tiles,
                paper=paper,
                worn_over_bust_cm=worn_over_bust_cm,
                worn_over_has_sleeves=worn_over_has_sleeves,
                shoulder_drop_cm=shoulder_drop_cm,
            )

        bundle_job_id = uuid.uuid4().hex[:12]
        zip_path = export_multi_size_bundle(
            {size: result.output_files for size, result in results.items()},
            self.output_dir, bundle_job_id,
        )
        return MultiSizeResult(
            sizes=list(sizes), base_measurements=base_measurements,
            results=results, bundle_job_id=bundle_job_id, zip_path=zip_path,
            custom_grade_cm=validated_grade_cm,
        )
