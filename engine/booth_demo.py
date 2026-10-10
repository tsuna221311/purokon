"""Four *exact-file* presentation examples, never a general image classifier.

The PNG digest identifies an author-supplied three-view sheet.  Each sheet has
an explicitly reviewed, fixed sewing plan.  A modified/re-encoded image or a
different measurement set must go through the ordinary image workflow.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path

from .demo_cases import DEMO_MEASUREMENTS


@dataclass(frozen=True)
class BoothPanel:
    label: str
    points_cm: tuple[tuple[float, float], ...]
    quantity: int
    attachment: str


@dataclass(frozen=True)
class BoothCase:
    key: str
    title: str
    sha256: str
    spec: dict[str, object]
    included: tuple[str, ...]
    not_included: tuple[str, ...]
    panels: tuple[BoothPanel, ...] = ()


CASES = (
    BoothCase(
        "navy_coat", "紺のテーラードコート",
        "b0f553ad2640a24947584c1888fe5e320ccbe9d573fabe5335cd57242e352d35",
        dict(neckline="v_neck", sleeve_style="straight", skirt_style="flare",
             front_zip=True, include_pants=True, pants_style="tapered",
             include_collar=True, collar_style="convertible_collar",
             include_cuffs=True, cuffs_style="button_tab", include_waistband=False),
        ("前後身頃と左右袖", "コート下部のフレア", "衿・袖口", "内側のパンツ", "左右の外付けポケット・フラップ", "ベルト・ベルト通し"),
        ("ダブルボタンの打ち合わせとボタン位置", "バックル・パイピングの実物仕様"),
        (
            BoothPanel("COAT PATCH POCKET", ((0, 0), (14, 0), (14, 13), (11, 17), (3, 17), (0, 13)), 2,
                       "左右前身頃の前中心から外側7cm、肩線から下31cmをポケット上端の目安とする。フラップは上端から1cm上に付ける。仮縫いでダーツとの干渉を確認。"),
            BoothPanel("COAT POCKET FLAP", ((0, 0), (15, 0), (15, 3), (12, 5), (3, 5), (0, 3)), 2,
                       "対応するポケット上端の1cm上に縫付ける。完成幅はポケットより左右各0.5cm広い。"),
            BoothPanel("COAT BELT", ((0, 0), (96, 0), (96, 5), (0, 5)), 1,
                       "ウエスト位置に通す。芯材・バックル・留め具は別途選定。"),
            BoothPanel("COAT BELT LOOP", ((0, 0), (9, 0), (9, 3), (0, 3)), 4,
                       "左右脇と前身頃のベルト線に配分。ベルト完成幅に合わせ仮縫いで通し幅を確認。"),
        ),
    ),
    BoothCase(
        "emerald_jumpsuit", "翡翠色のケープ付きジャンプスーツ",
        "6fe4edcbd5061fdb00223bf6fd97f1bc74059cd15a97b9e41d40bc2e8405e8fe",
        dict(neckline="round_neck", sleeve_style=None, skirt_style=None,
             front_zip=False, include_pants=True, pants_style="wide",
             include_collar=True, collar_style="", include_cuffs=False,
             include_waistband=True, waistband_style="wide"),
        ("ノースリーブの前後身頃", "ワイドパンツ", "衿・ウエスト帯", "片肩ケープと肩タブ"),
        ("肩タブ用のボタン・スナップ実物仕様", "斜めの前開き線・脇の配色"),
        (
            BoothPanel("SHOULDER CAPE", ((0, 0), (13, 0), (23, 20), (46, 69), (38, 80), (19, 66), (0, 45)), 1,
                       "上端13cmを着用者左肩に沿わせ、上端の3cm・9cm位置を肩タブで留める。肩からの垂れ方と腕の可動域は紙模型で確認。"),
            BoothPanel("CAPE SHOULDER TAB", ((0, 0), (10, 0), (10, 4), (0, 4)), 2,
                       "左肩の首側から4cm・10cmの2点を目安に、ケープ上端3cm・9cm位置を留める。留め具は別途選定。"),
        ),
    ),
    BoothCase(
        "terracotta_wrap", "テラコッタ色の巻き衣装",
        "398cd54dfa70d96101ff6eba1450d0d4357cb24357d56a7b213aec446cdffa02",
        dict(neckline="v_neck", sleeve_style="straight", skirt_style="wrap",
             front_zip=False, include_pants=False, pants_style="",
             include_collar=False, include_cuffs=False,
             include_waistband=True, waistband_style="wide"),
        ("Vネック前後身頃", "左右袖", "巻きスカート", "ウエスト帯", "左右の結びひも", "袖口の白いフレア別布"),
        ("斜めの裾線と重ね順の確定", "白い内スカートの実物仕様"),
        (
            BoothPanel("WRAP TIE", ((0, 0), (65, 0), (65, 5), (0, 5)), 2,
                       "左右ウエスト帯の端に各1本。結び代と着用時の締め具合は仮縫いで確認。"),
            BoothPanel("WHITE SLEEVE FLOUNCE", ((0, 0), (37, 0), (42, 11), (35, 15), (7, 15), (0, 11)), 2,
                       "袖口にギャザーを寄せて取付ける。袖口側縫い線37cmを袖口実測長に合わせて分配し、ギャザー量は紙模型で調整。"),
        ),
    ),
    BoothCase(
        "moss_jacket_skirt", "苔色フードジャケットと橙色スカート",
        "8fcaf44c0c42f58ea2b159c971f35ccc79191001eb346103b7c79b540214b8c0",
        dict(neckline="round_neck", sleeve_style="straight", skirt_style="flare",
             front_zip=True, include_pants=False, pants_style="",
             include_collar=False, include_hood=True, include_cuffs=True,
             cuffs_style="wide", include_waistband=True, waistband_style="wide"),
        ("前開きジャケットの身頃・袖・フード", "袖口", "別体のスカートとウエスト帯", "左右の胸ポケット・フラップ"),
        ("裾のリブとドローストリングの実物仕様", "前ボタンの開き仕様"),
        (
            BoothPanel("JACKET CHEST POCKET", ((0, 0), (11, 0), (11, 9), (8, 12), (3, 12), (0, 9)), 2,
                       "左右前身頃の前中心から外側6cm、肩線から下18cmを上端の目安にする。着用時に腕と重ならないか確認。"),
            BoothPanel("JACKET POCKET FLAP", ((0, 0), (12, 0), (12, 3), (10, 5), (2, 5), (0, 3)), 2,
                       "各ポケット上端の1cm上に縫付ける。完成幅はポケットより左右各0.5cm広い。"),
        ),
    ),
)

BY_DIGEST = {case.sha256: case for case in CASES}
ASSET_ROOT = Path(__file__).resolve().parents[1] / "web" / "static" / "demo" / "booth_patterns_v2"


def exact_match(uploaded) -> BoothCase | None:
    """Hash the uploaded bytes without altering the stream used by Pillow."""
    stream = uploaded.stream
    position = stream.tell()
    try:
        stream.seek(0)
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    finally:
        stream.seek(position)
    return BY_DIGEST.get(digest)


def fixed_measurements_match(measurements) -> bool:
    return (all(float(getattr(measurements, key)) == float(value)
                for key, value in DEMO_MEASUREMENTS.items())
            and all(getattr(measurements, key) is None for key in (
                "upper_arm", "bust_point_spacing", "bust_point_drop",
                "head_circumference")))


def default_options_match(form) -> bool:
    """Do not silently discard any setting that changes prepared geometry."""
    basic = {
        "fit": {"", "standard"},
        "block": {""},
        "seam_allowance_cm": {"", "1", "1.0"},
        "hem_seam_allowance_cm": {""},
        "paper": {"", "a4", "A4"},
        "shrink_percent": {"", "0", "0.0"},
        "pattern_repeat_cm": {""},
        "custom_panels_json": {"", "[]"},
    }
    if any((form.get(key) or "").strip() not in values
           for key, values in basic.items()):
        return False
    if any(form.get(key) for key in (
            "lining", "allow_rotation", "one_way_fabric", "include_empty_tiles",
            "generate_accessory_stl", "fabric_groups_json")):
        return False
    if any(value.strip() for key, value in form.items()
           if key.startswith(("alter_", "design_length_", "ease_"))):
        return False
    # Corrections would otherwise appear to have been applied to the frozen PDF.
    correction_fields = ("illustration_neckline", "illustration_back_neckline",
                         "illustration_sleeve_style", "illustration_skirt_style",
                         "illustration_pants_style", "illustration_collar_style",
                         "illustration_cuffs_style", "illustration_waistband_style")
    if any((form.get(key) or "auto") != "auto" for key in correction_fields):
        return False
    defaults = {"illustration_three_views": {"", "1"},
                "illustration_stage": {"", "draft", "production"},
                "illustration_layer_count": {"", "1"},
                "illustration_slit_position": {"", "none"},
                "illustration_motif_position": {"", "none"}}
    for key, value in form.items():
        if not key.startswith("illustration_") or key in correction_fields:
            continue
        if key in defaults and value in defaults[key]:
            continue
        if key not in defaults and value in {"", "auto", "none"}:
            continue
        return False
    return True


def load_prepared(case: BoothCase) -> dict[str, object]:
    """Fail closed if a case has no audited files in the deployed package."""
    path = ASSET_ROOT / case.key / "result.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("source_sha256") != case.sha256 or not data.get("digital_ready"):
        raise ValueError("展示用の型紙データの検査情報が一致しません。")
    for relative in data["files"].values():
        if not (ASSET_ROOT / case.key / relative).is_file():
            raise ValueError("展示用の型紙ファイルが不足しています。")
    return data
