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
class BoothCase:
    key: str
    title: str
    sha256: str
    spec: dict[str, object]
    included: tuple[str, ...]
    not_included: tuple[str, ...]


CASES = (
    BoothCase(
        "navy_coat", "紺のテーラードコート",
        "b0f553ad2640a24947584c1888fe5e320ccbe9d573fabe5335cd57242e352d35",
        dict(neckline="v_neck", sleeve_style="straight", skirt_style="flare",
             front_zip=True, include_pants=True, pants_style="tapered",
             include_collar=True, collar_style="convertible_collar",
             include_cuffs=True, cuffs_style="button_tab", include_waistband=False),
        ("前後身頃と左右袖", "コート下部のフレア", "衿・袖口", "内側のパンツ"),
        ("ダブルボタンの打ち合わせとボタン位置", "ベルトとバックル", "飾りのパイピング・ポケット"),
    ),
    BoothCase(
        "emerald_jumpsuit", "翡翠色のケープ付きジャンプスーツ",
        "6fe4edcbd5061fdb00223bf6fd97f1bc74059cd15a97b9e41d40bc2e8405e8fe",
        dict(neckline="round_neck", sleeve_style=None, skirt_style=None,
             front_zip=False, include_pants=True, pants_style="wide",
             include_collar=True, collar_style="", include_cuffs=False,
             include_waistband=True, waistband_style="wide"),
        ("ノースリーブの前後身頃", "ワイドパンツ", "衿・ウエスト帯"),
        ("片肩ケープの接合部", "肩タブと金具", "斜めの前開き線・脇の配色"),
    ),
    BoothCase(
        "terracotta_wrap", "テラコッタ色の巻き衣装",
        "398cd54dfa70d96101ff6eba1450d0d4357cb24357d56a7b213aec446cdffa02",
        dict(neckline="v_neck", sleeve_style="straight", skirt_style="wrap",
             front_zip=False, include_pants=False, pants_style="",
             include_collar=False, include_cuffs=False,
             include_waistband=True, waistband_style="wide"),
        ("Vネック前後身頃", "左右袖", "巻きスカート", "ウエスト帯"),
        ("斜めの裾線と重ね順の確定", "結びひも", "袖口の白いフレア別布"),
    ),
    BoothCase(
        "moss_jacket_skirt", "苔色フードジャケットと橙色スカート",
        "8fcaf44c0c42f58ea2b159c971f35ccc79191001eb346103b7c79b540214b8c0",
        dict(neckline="round_neck", sleeve_style="straight", skirt_style="flare",
             front_zip=True, include_pants=False, pants_style="",
             include_collar=False, include_hood=True, include_cuffs=True,
             cuffs_style="wide", include_waistband=True, waistband_style="wide"),
        ("前開きジャケットの身頃・袖・フード", "袖口", "別体のスカートとウエスト帯"),
        ("胸ポケットとフラップ", "裾のリブとドローストリング", "前ボタンの開き仕様"),
    ),
)

BY_DIGEST = {case.sha256: case for case in CASES}
ASSET_ROOT = Path(__file__).resolve().parents[1] / "web" / "static" / "demo" / "booth_patterns"


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
    return all(float(getattr(measurements, key)) == float(value)
               for key, value in DEMO_MEASUREMENTS.items())


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
