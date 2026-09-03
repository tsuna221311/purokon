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
import time
import uuid
from dataclasses import dataclass, field
from types import SimpleNamespace

from PIL import Image

from .compatibility import (
    COLLAR_EASE_CM, CUFFS_EASE_CM, CompatibilityWarning, SLEEVE_CAP_DESIGN_GATHER_CM,
    SLEEVE_CAP_EASE_CM, WAISTBAND_CLOSURE_EASE_CM, armhole_length,
    check_seam_compatibility, hem_or_wrist_opening_length, neckline_length,
    waist_opening_length,
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
from .nesting import DEFAULT_FABRIC_WIDTHS_CM, NestingResult, best_fabric_width
from .part_classifier import ClassificationResult, get_default_classifier
from .pdf_export import export_multi_size_bundle, export_pattern
from .scaling import (
    ScaledPart, bodice_fit_clamp_warning, measurement_clamp_warnings,
    scale_band_to_seam_length, scale_sleeve_to_cap_length, scale_template,
)
from .seam import DEFAULT_SEAM_ALLOWANCE_CM, FinalizedPart, finalize_part
from .segmentation import get_default_segmenter
from .svgpath import segments_to_polyline
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


@dataclass
class GarmentSpec:
    """生成する衣装の構成（どのパーツ種+バリエーションを何枚使うか）。"""
    parts: list[PartRequest]

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
                        waistband_style: str = "") -> GarmentSpec:
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

    return GarmentSpec(parts=parts)


def build_custom_panel_requests(label: str, points_cm: list[tuple[float, float]],
                                 quantity: int = 1, mirror: bool = False) -> list[PartRequest]:
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
    requests = [PartRequest(CUSTOM_PANEL_PART_TYPE, label, quantity=quantity, custom_segments=segments)]
    if mirror:
        mirrored_segments = points_to_segments(mirror_points_x(points_cm))
        requests.append(PartRequest(CUSTOM_PANEL_PART_TYPE, f"{label}(反転)",
                                     quantity=quantity, custom_segments=mirrored_segments))
    return requests


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
    seam_allowance_cm: float = DEFAULT_SEAM_ALLOWANCE_CM
    hem_seam_allowance_cm: float | None = None

    def summary(self) -> dict:
        naive_length = self.naive_baseline_length_cm()
        return {
            "job_id": self.job_id,
            "seam_allowance_cm": self.seam_allowance_cm,
            "hem_seam_allowance_cm": self.hem_seam_allowance_cm,
            "part_count": len(self.finalized_parts),
            "unplaced_count": len(self.nesting.unplaced),
            # 実際に全テンプレート×採寸の組み合わせ(1200通り)を有効な採寸値の
            # 最も極端な範囲で総当たりして確認したところ、現状のテンプレート・
            # MIN_SCALE/MAX_SCALEの範囲では unplaced_count が0より大きくなる
            # ケースは存在しない(確認済み・問題無し)。ただし将来テンプレートや
            # スケール範囲を変更した場合に備え、`nesting.py`はunplaced(配置
            # できなかったパーツ)を検出できる作りになっている一方、以前は
            # SVG/PDF側がresult.placedしか描画しないため配置できなかったパーツ
            # は出力から完全に消え、画面上も他の統計と同じ見た目の
            # 「配置不能パーツ」という数値表示のみだった(赤枠で目立たせている
            # 採寸クランプ警告と違い、これが実際に何を意味するか・型紙が
            # 不完全であることを利用者に伝える文言が無かった)。到達不能である
            # ことを確認済みとはいえ、実際に発生した場合は生地を裁ってから
            # パーツが足りないことに気づくという実害があるため、防御的に
            # 明示的な警告文へ変える(measurement_warningsと同じ表示形式)。
            "unplaced_warnings": self._unplaced_warnings(),
            "fabric_width_cm": self.nesting.fabric_width_cm,
            "used_length_cm": round(self.nesting.used_length_cm, 1),
            "waste_ratio": round(self.nesting.waste_ratio, 4),
            "rotation_used": any(p.rotated for p in self.nesting.placed),
            "elapsed_seconds": round(self.elapsed_seconds, 2),
            "output_files": self.output_files,
            "ai_contribution": self.ai_contribution_note(),
            "darts_applied": sum(p.dart_count for p in self.finalized_parts),
            "measurement_warnings": self.measurement_warnings,
            "compatibility_warnings": [w.as_dict() for w in self.compatibility_warnings()],
            "naive_used_length_cm": round(naive_length, 1),
            "naive_waste_ratio": round(self.naive_baseline_waste_ratio(naive_length), 4),
            "parts": [
                {
                    "display_name": p.display_name,
                    "width_cm": round(p.width_cm, 1),
                    "height_cm": round(p.height_cm, 1),
                }
                for p in self.finalized_parts
            ],
        }

    def compatibility_warnings(self) -> list[CompatibilityWarning]:
        """縫い合わせ長さの不整合(round6で追加、engine.compatibility参照)。"""
        return check_seam_compatibility(self.finalized_parts)

    def _unplaced_warnings(self) -> list[str]:
        """配置できなかったパーツがある場合、その旨を明示する警告文を返す。

        `measurement_clamp_warnings`と同じ位置づけの、利用者へ正直に開示する
        ための文言。空リストなら配置できなかったパーツは無い(通常はこちら)。
        """
        if not self.nesting.unplaced:
            return []
        names = "・".join(p.display_name for p in self.nesting.unplaced)
        return [
            f"{names}は、どの生地幅(最大{self.nesting.fabric_width_cm:.0f}cm)にも"
            "収まらず型紙に含まれていません。この型紙のSVG/PDFには上記のパーツが"
            "描かれていないため、そのまま裁断すると衣服が完成しません。採寸値を"
            "見直すか、手作業でこのパーツだけ別途作成してください。"
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


def _sleeve_target_cap_cm(scaled_by_type: dict[str, list[ScaledPart]],
                           variation: str) -> float | None:
    """袖山カーブの目標長さ(cm)を、実際に縫い付ける袖ぐりの長さから求める
    (round14追加、`scale_sleeve_to_cap_length`参照)。

    `engine/compatibility.py`のチェック5が「あるべき袖山長」として使って
    いる式(袖ぐり(片腕) + いせ込み + デザイン上のギャザー)をそのまま
    目標値にする。つまり「警告が出ない寸法をあらかじめ作る」という関係に
    なっていて、チェック側と生成側で別々の式を持たない。

    身頃が指定されていない(袖だけを生成する)場合はNoneを返し、呼び出し側は
    従来通り肩幅比による独立スケーリングにフォールバックする。
    """
    fronts = scaled_by_type.get("front_bodice", [])
    backs = scaled_by_type.get("back_bodice", [])
    if not fronts or not backs:
        return None
    front_lengths = [armhole_length(SimpleNamespace(
        part_type="front_bodice", stitch_line=segments_to_polyline(sp.segments)))
        for sp in fronts]
    back_lengths = [armhole_length(SimpleNamespace(
        part_type="back_bodice", stitch_line=segments_to_polyline(sp.segments)))
        for sp in backs]
    if not all(v is not None for v in front_lengths + back_lengths):
        return None
    # armhole_lengthは1パーツぶん(左右2つ分)を返すので、片腕ぶんは前後の
    # 合計を2で割った値(compatibility.pyのチェック5と同じ換算)。
    armhole_per_arm = (sum(front_lengths) + sum(back_lengths)) / 2.0
    return (armhole_per_arm + SLEEVE_CAP_EASE_CM
            + SLEEVE_CAP_DESIGN_GATHER_CM.get(variation, 0.0))


def _collar_target_length_cm(scaled_by_type: dict[str, list[ScaledPart]]) -> float | None:
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
      - 前開き(front_bodice_zip_panel) … 中心前で裁ち割った片側パネルからは
        首ぐりを一意に取り出せない(`neckline_length`のdocstring参照)
    """
    fronts = scaled_by_type.get("front_bodice", [])
    backs = scaled_by_type.get("back_bodice", [])
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

    def _build_from_spec(self, garment_spec: GarmentSpec, measurements: Measurements,
                          fabric_width_candidates: tuple[float, ...],
                          allow_rotation: bool = False,
                          seam_allowance_cm: float | None = None,
                          hem_seam_allowance_cm: float | None = None) -> PipelineResult:
        start = time.time()
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
        _BAND_TYPES = ("waistband", "cuffs")
        # round14で袖を1段階増やした。袖は「袖ぐりの実際の長さ」に袖山を
        # 合わせるため身頃より後、カフスは「袖口の実際の長さ」に合わせるため
        # 袖より後でなければならない。順序の制約は
        #   身頃など → 袖 → 帯(waistband/cuffs)
        # の3段階になる。
        # round15: 衿も「実際の首ぐりの長さ」に合わせるため、身頃より後に回す
        # (袖と同じ段。衿と袖は互いに依存しない)。
        _SLEEVE_TYPES = ("sleeve", "collar")
        _DEFERRED_TYPES = _BAND_TYPES + _SLEEVE_TYPES
        scaled_by_type: dict[str, list[ScaledPart]] = {}
        precomputed: dict[tuple[int, int], ScaledPart] = {}

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
                        request.part_type, request.variation))
                precomputed[(req_idx, i)] = scaled
                scaled_by_type.setdefault(request.part_type, []).append(scaled)

        for req_idx, request in enumerate(garment_spec.parts):
            if request.part_type not in _SLEEVE_TYPES:
                continue
            quantity = max(1, request.quantity)
            if request.part_type == "collar":
                target = _collar_target_length_cm(scaled_by_type)
            else:
                target = _sleeve_target_cap_cm(scaled_by_type, request.variation)
            for i in range(quantity):
                if target is None:
                    # 相手パーツが無い等で目標を決められない場合は、従来通り
                    # 採寸比での独立スケーリングにフォールバックする。
                    scaled = scale_template(request.part_type, request.variation,
                                             segments_by_idx[req_idx], measurements)
                elif request.part_type == "collar":
                    scaled = scale_band_to_seam_length(
                        request.part_type, request.variation,
                        segments_by_idx[req_idx], target,
                        seam_edge=self.template_db.get_seam_edge(
                            request.part_type, request.variation))
                else:
                    scaled = scale_sleeve_to_cap_length(
                        request.part_type, request.variation,
                        segments_by_idx[req_idx], measurements, target)
                precomputed[(req_idx, i)] = scaled
                scaled_by_type.setdefault(request.part_type, []).append(scaled)

        for req_idx, request in enumerate(garment_spec.parts):
            if request.part_type not in _BAND_TYPES:
                continue
            quantity = max(1, request.quantity)
            if request.part_type == "waistband":
                target = _waistband_target_width_cm(scaled_by_type)
            else:
                target = _cuffs_target_width_cm(scaled_by_type)
            for i in range(quantity):
                if target is None:
                    # 相手パーツ(skirt/pants/sleeve)が指定されていない場合は、
                    # 従来通り採寸比率による独立スケーリングにフォールバックする。
                    scaled = scale_template(request.part_type, request.variation,
                                             segments_by_idx[req_idx], measurements)
                else:
                    # round15: 外接矩形の幅ではなく、実際に縫い付けられる辺の
                    # 長さを目標に合わせる(scale_band_to_seam_length参照)。
                    scaled = scale_band_to_seam_length(
                        request.part_type, request.variation,
                        segments_by_idx[req_idx], target,
                        seam_edge=self.template_db.get_seam_edge(
                            request.part_type, request.variation))
                precomputed[(req_idx, i)] = scaled

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

                finalized_parts.append(finalize_part(
                    request.part_type, request.variation, scaled.segments,
                    seam_allowance_cm=effective_seam_cm,
                    hem_seam_allowance_cm=effective_hem_cm,
                    label_suffix=label_suffix,
                    extra_notch_fractions=extra_notches,
                    dart_count=scaled.dart_count,
                    # round15: 帯状パーツの「縫い付けられる辺」の宣言を
                    # 最終パーツへ引き継ぐ(整合性チェックが同じ辺を測るため)。
                    seam_edge=self.template_db.get_seam_edge(
                        request.part_type, request.variation),
                ))

        nesting = best_fabric_width(finalized_parts, candidates=fabric_width_candidates,
                                     allow_rotation=allow_rotation)
        job_id = uuid.uuid4().hex[:12]
        outputs = export_pattern(nesting, self.output_dir, basename=job_id,
                                  seam_allowance_cm=effective_seam_cm,
                                  hem_seam_allowance_cm=effective_hem_cm)

        warnings = measurement_clamp_warnings(measurements)
        # round14: 入力した肩幅を型紙へ反映できなかった場合の注記
        # (engine/scaling.pyのbodice_fit_clamp_warning参照)。身頃を含む
        # 生成のときだけ意味を持つ。
        bodice_anchors = next(
            (self.template_db.get_fit_anchors(r.part_type, r.variation)
             for r in garment_spec.parts if r.part_type == "front_bodice"), [])
        shoulder_note = bodice_fit_clamp_warning(bodice_anchors, measurements)
        if shoulder_note:
            warnings = warnings + [shoulder_note]

        return PipelineResult(
            job_id=job_id, garment_spec=garment_spec, measurements=measurements,
            scaled_parts=scaled_parts, finalized_parts=finalized_parts, nesting=nesting,
            output_files=outputs, elapsed_seconds=time.time() - start,
            measurement_warnings=warnings,
            seam_allowance_cm=effective_seam_cm, hem_seam_allowance_cm=effective_hem_cm,
        )

    def generate_from_selection(self, garment_spec: GarmentSpec, measurements: Measurements,
                                 fabric_width_candidates: tuple[float, ...] = DEFAULT_FABRIC_WIDTHS_CM,
                                 allow_rotation: bool = False,
                                 seam_allowance_cm: float | None = None,
                                 hem_seam_allowance_cm: float | None = None) -> PipelineResult:
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
                                      hem_seam_allowance_cm=hem_seam_allowance_cm)

    def generate_from_illustration(self, image: Image.Image, measurements: Measurements,
                                    fabric_width_candidates: tuple[float, ...] = DEFAULT_FABRIC_WIDTHS_CM,
                                    allow_rotation: bool = False,
                                    seam_allowance_cm: float | None = None,
                                    hem_seam_allowance_cm: float | None = None
                                    ) -> PipelineResult:
        """STEP①〜⑥: イラストからSAM分割+Claude API判定でパーツ構成を自動推定する。"""
        segmenter = get_default_segmenter()
        classifier = get_default_classifier()

        regions = segmenter.segment(image)
        if not regions:
            raise ValueError(
                "イラストからパーツ領域を検出できませんでした。"
                "背景を単色にするか、手動選択モードをお試しください。"
            )

        classifications: list[ClassificationResult] = []
        requests: list[PartRequest] = []
        # sleeve/cuffs/front_pants/back_pants/skirtは「左右一対」または「前後一対」で2枚必要な
        # パーツ種（PAIR_LABELS参照）。これらはpart_typeだけで重複排除する
        # （variationまで含めて排除すると、AIが左右の領域を別バリエーションと
        # 誤判定した場合に2種類×2枚=4枚が生成されてしまうため）。
        # front_bodice/back_bodice/collar/waistbandはvariationごとに区別する。
        seen: set = set()

        def _add(part_type: str, variation: str, quantity: int) -> None:
            key = part_type if part_type in PAIR_LABELS else (part_type, variation)
            if key in seen:
                return
            seen.add(key)
            requests.append(PartRequest(part_type, variation, quantity))

        for region in regions:
            crop = region.crop(image)
            if crop.width < 4 or crop.height < 4:
                continue
            result = classifier.classify(crop, region_label=region.label)
            classifications.append(result)
            if not result.part_type:
                continue
            # PAIR_LABELSに定義されている全パーツ種(sleeve/cuffs/front_pants/back_pants/skirt)は
            # 2枚一対で必要（例: skirtは前後2枚。以前はskirtがこの判定から
            # 漏れており、後ろスカートが生成されない不具合があった）。
            quantity = 2 if result.part_type in PAIR_LABELS else 1
            _add(result.part_type, result.variation, quantity)
            # 前身頃が判定できたら、対応する後身頃も同じネックラインで自動的に追加する。
            if result.part_type == "front_bodice":
                _add("back_bodice", result.variation, 1)

        if not requests:
            raise ValueError("パーツ種を判定できませんでした。手動選択モードをお試しください。")

        spec = GarmentSpec(parts=requests)
        result = self._build_from_spec(spec, measurements, fabric_width_candidates,
                                        allow_rotation=allow_rotation,
                                        seam_allowance_cm=seam_allowance_cm,
                                        hem_seam_allowance_cm=hem_seam_allowance_cm)
        result.classification_log = classifications
        return result

    def generate_multi_size(self, garment_spec: GarmentSpec, base_measurements: Measurements,
                             sizes: list[str],
                             fabric_width_candidates: tuple[float, ...] = DEFAULT_FABRIC_WIDTHS_CM,
                             allow_rotation: bool = False,
                             seam_allowance_cm: float | None = None,
                             hem_seam_allowance_cm: float | None = None,
                             custom_grade_cm: dict[str, float] | None = None) -> MultiSizeResult:
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
