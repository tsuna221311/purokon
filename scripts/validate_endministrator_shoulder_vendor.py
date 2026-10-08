"""Make and audit a quotation-only Endministrator shoulder accessory trial.

The supplied front illustration confirms a yellow asymmetric shoulder accent,
not its dimensions, rear surface, fastening method or curvature.  These trial
values are design hypotheses, never measured dimensions of the character.
"""

from __future__ import annotations

import argparse
import hashlib
from io import BytesIO
import json
from pathlib import Path
import struct
import sys
from xml.etree import ElementTree
from zipfile import ZipFile

from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.accessory3d import export_vendor_package
from engine.custom_panel import CustomPanelSpec


LABEL = "管理人・右肩黄色プレート試作"
# Front-image interpretation only: one off-centre shoulder plate, 110 x 60 mm
# unbent outer box.  The shape is deliberately asymmetric, not a rectangle.
OUTLINE_CM = [
    (0.0, 1.4), (1.4, 0.3), (4.1, 0.0), (9.1, 0.7),
    (11.0, 2.5), (10.5, 4.6), (8.2, 6.0), (2.5, 5.5), (0.3, 3.5),
]
SOURCE_IMAGE = "User-supplied female Endministrator front illustration (side/back unavailable)"
OFFICIAL_REFERENCE = "https://endfield.gryphline.com/en-us/operator"
SLS_GUIDE = "https://formlabs.com/jp/white-papers/fuse-series-sls-design-guide/"
VENDOR_GUIDE = "https://www.protolabs.com/en-gb/resources/design-tips/how-to-design-for-nylon-3d-printing/"


def _order_review(manifest: dict) -> str:
    part = manifest["files"][0]
    size = part["dimensions_mm"]
    return f"""PatternForge 管理人（女性）右肩・黄色装飾 試作見積確認票
======================================================
図面: DIMENSIONED_DRAWINGS.pdf / {part['label']}
状態: 試作見積・装着確認専用。量産／完成衣装用の確定発注ではありません。

参照: {SOURCE_IMAGE}
公式キャラクター資料: {OFFICIAL_REFERENCE}
注意: 正面画像に縮尺線がなく、側面・背面・身体への装着寸法は未取得です。
      以下は図面機能と業者入稿手順を試すための設計仮説です。

仮の造形指定
- 数量: 1個。反転・左右対称コピーなし。
- 方式/材料候補: PA12ナイロンのSLS。業者が対応可否と代替を回答する。
- 曲げ前輪郭: 最大110 x 60 mm、非対称。曲げ方向は幅方向。
- 内側曲率半径: 160 mm（仮）。実際の肩・袖の曲率ではない。
- CAD厚さ: 3.0 mm（仮）。実体化後の厚さ・剛性は試作品で確認。
- 取付孔: 直径3.2 mm x 2、輪郭X最小/最大から中心まで各12 mm（仮）。
- 出力メッシュ外接寸法: X={size['x']} / Y={size['y']} / Z={size['z']} mm。
- 色/表面: 黄色のマット塗装を希望。ただし色見本未指定。SLS造形後の
  下地処理・塗装・耐擦過性について業者に別見積を求める。
- 金具: 同梱なし。実物の固定具と裏当て材を先に選び、孔径と位置を再確認する。

業者へ確認する公差・仕上げ（まだ承認値ではない）
- この材料・工法で達成可能な外形、孔径、孔位置の公差をそれぞれ見積回答してもらう。
- 孔は塗装後に狭くなる可能性がある。必要なら後加工で最終径を確保する。
- 肌／生地に触れる縁を丸める。CADには縁Rがまだ存在しないので、
  仕上げで保証できなければ、縁Rをモデルに追加して再入稿する。
- 造形方向、反り、サポート/粉抜き、塗装工程、費用と納期を回答してもらう。

試作品の受入・着用確認
1. ノギスで外形X/Y/Zと孔径・孔中心間隔を測り、業者回答の公差と照合する。
2. 固定具を仮組みし、裏側が肌に当たらないことを確認する。
3. 衣装に仮止めし、腕を前後・上へ動かして袖／フードと干渉しないか確認する。
4. 角、バリ、塗装剥離、曲げ時の白化・割れを確認する。
5. EVAフォーム＋黄色合皮の現行案と重量・追従性・見た目を比較し、
   硬質版を採用するか決める。

発注を止める未確定事項
- 着用者の肩に合わせた実幅・曲率・前後位置
- 側面/背面の形状、厚みの変化、表裏の指定
- 固定金具と裏当て、孔位置、塗装色見本、公差の業者合意

参考設計ガイド（特定業者の保証値ではありません）
- Formlabs: {SLS_GUIDE}
- Protolabs: {VENDOR_GUIDE}
"""


def generate(output_dir: Path) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    pdf_dir = output_dir / "pdf"
    pdf_dir.mkdir(parents=True, exist_ok=True)
    zip_path = output_dir / "endministrator_right_shoulder_trial_vendor.zip"
    export_vendor_package(
        [CustomPanelSpec(LABEL, OUTLINE_CM)], str(zip_path),
        thickness_mm=3.0, bed_width_mm=220, bed_depth_mm=220,
        material_profile="pa12",
        finish_note="黄色マット塗装希望。色見本・表面処理・耐擦過性は業者と合意後に確定。",
        curvature_radius_mm=160, curve_axis="width",
        mounting_hole_pattern="pair_width",
        mounting_hole_diameter_mm=3.2, mounting_hole_inset_mm=12,
    )
    with ZipFile(zip_path) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        pdf_data = archive.read("DIMENSIONED_DRAWINGS.pdf")
        stl_data = archive.read(manifest["files"][0]["file"])
        with ZipFile(BytesIO(archive.read("all_parts_mm.3mf"))) as model_archive:
            model = ElementTree.fromstring(model_archive.read("3D/3dmodel.model"))
        assert model.attrib["unit"] == "millimeter"
    assert manifest["piece_count"] == 1
    assert manifest["files"][0]["watertight"] is True
    assert manifest["mounting_holes"]["through_hole"] is True
    assert len(stl_data) == 84 + struct.unpack("<I", stl_data[80:84])[0] * 50
    pdf_text = PdfReader(BytesIO(pdf_data)).pages[0].extract_text()
    dims = manifest["files"][0]["dimensions_mm"]
    assert "C1 THROUGH dia 3.2" in pdf_text
    assert "C2 THROUGH dia 3.2" in pdf_text
    assert f"X {dims['x']:g} mm" in pdf_text
    assert f"Y {dims['y']:g} mm" in pdf_text
    assert f"Z {dims['z']:g} mm" in pdf_text
    assert "Process request: PA12 nylon / SLS candidate" in pdf_text

    pdf_path = pdf_dir / "PatternForge_Endministrator_shoulder_trial_drawing.pdf"
    pdf_path.write_bytes(pdf_data)
    review = _order_review(manifest)
    review_path = output_dir / "endministrator_shoulder_trial_order_review_ja.txt"
    review_path.write_text(review, encoding="utf-8-sig")
    # A vendor receiving only the ZIP must still see the order hold points.
    with ZipFile(zip_path, "a") as archive:
        archive.writestr("TRIAL_ORDER_REVIEW_JA.txt", review.encode("utf-8-sig"))
    audit = {
        "status": "digital_vendor_package_validated; visual_match_and_physical_fit_unverified",
        "source": SOURCE_IMAGE,
        "official_reference": OFFICIAL_REFERENCE,
        "design_values_are_estimates": True,
        "visual_match_checked_against_source_pixels": False,
        "fabrication_order_approved": False,
        "piece_count": 1,
        "stl_watertight": True,
        "mesh_dimensions_mm": dims,
        "through_holes": manifest["mounting_holes"],
        "material_request": manifest["material_request"],
        "pdf_pages": 1,
        "vendor_zip_sha256": hashlib.sha256(zip_path.read_bytes()).hexdigest(),
        "files": {"vendor_zip": str(zip_path.resolve()),
                  "drawing_pdf": str(pdf_path.resolve()),
                  "order_review": str(review_path.resolve())},
    }
    audit_path = output_dir / "endministrator_shoulder_trial_audit.json"
    audit_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n",
                          encoding="utf-8")
    return audit


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "output")
    args = parser.parse_args()
    print(json.dumps(generate(args.output_dir), ensure_ascii=False, indent=2))
