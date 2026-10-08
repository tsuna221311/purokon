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


LABEL = "管理人・黄色肩タブの芯材試作"
# The previous 110 x 60 mm plate conflated the shoulder tab, its two metal
# ornaments and a hanging charm.  These are now separate components.  Neither
# outline is pixel traced: sizes remain quotation-only design hypotheses.
OUTLINE_CM = [
    (0.3, 0.0), (3.2, 0.0), (4.5, 0.5), (4.5, 8.1),
    (3.7, 9.0), (1.0, 9.0), (0.0, 8.1), (0.0, 0.6),
]
CHARM_LABEL = "管理人・黒いしずく形飾り芯材試作"
CHARM_OUTLINE_CM = [
    (1.0, 0.0), (0.2, 1.4), (0.0, 2.2), (0.3, 2.8),
    (0.8, 3.2), (1.2, 3.2), (1.7, 2.8), (2.0, 2.2),
    (1.8, 1.4),
]
SOURCE_IMAGE = "User-supplied female Endministrator front illustration (side/back unavailable)"
OFFICIAL_REFERENCE = "https://endfield.gryphline.com/en-us/operator"
COMMERCIAL_DETAIL = "https://www.ccosplay.com/arknights-endfield-costume-endministrator-women-cosplay-suit"
SLS_GUIDE = "https://formlabs.com/jp/white-papers/fuse-series-sls-design-guide/"
VENDOR_GUIDE = "https://www.protolabs.com/en-gb/resources/design-tips/how-to-design-for-nylon-3d-printing/"


def _order_review(manifest: dict) -> str:
    part = manifest["files"][0]
    size = part["dimensions_mm"]
    return f"""PatternForge 管理人（女性）黄色肩タブ芯材 試作見積確認票
======================================================
図面: DIMENSIONED_DRAWINGS.pdf / {part['label']}
状態: 試作見積・装着確認専用。量産／完成衣装用の確定発注ではありません。

参照: {SOURCE_IMAGE}
公式キャラクター資料: {OFFICIAL_REFERENCE}
市販衣装の拡大写真: {COMMERCIAL_DETAIL}
注意: 正面画像に縮尺線がなく、側面・背面・身体への装着寸法は未取得です。
      以下は図面機能と業者入稿手順を試すための設計仮説です。
      拡大写真で見える銀色金具2個と黒い垂れ飾りは別部品です。

仮の造形指定
- 数量: 1個。反転・左右対称コピーなし。
- 方式/材料候補: PA12ナイロンのSLS。業者が対応可否と代替を回答する。
- 曲げ前輪郭: 最大45 x 90 mm、非対称。実物の輪郭寸法ではない。
- 内側曲率半径: 160 mm（仮）。実際の肩・袖の曲率ではない。
- CAD厚さ: 2.0 mm（仮）。表面は合皮等で覆う芯材案。
- 取付孔: なし。銀色の金具の位置・裏構造を写真から決め打ちしない。
- 出力メッシュ外接寸法: X={size['x']} / Y={size['y']} / Z={size['z']} mm。
- 色/表面: 市販品は光沢のある黄色の表面。芯材の見積には塗装を含めず、
  黄色合皮などの被覆と白い縁取りは縫製側で別途試す。
- 金具: 銀色装飾2個、吊り金具1個は別途調達。サイズ・取付位置は未確定。

業者へ確認する公差・仕上げ（まだ承認値ではない）
- この材料・工法で達成可能な外形、孔径、孔位置の公差をそれぞれ見積回答してもらう。
- 金具を選定後に孔または縫い留め位置を確定する。現CADへ穴を推定追加しない。
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
- 固定金具と裏当て、孔位置、被覆材の厚み、公差の業者合意

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
        thickness_mm=2.0, bed_width_mm=220, bed_depth_mm=220,
        material_profile="pa12",
        finish_note="表面は黄色合皮等で別途被覆する芯材候補。金具孔は未指定。",
        curvature_radius_mm=160, curve_axis="width",
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
    assert manifest["mounting_holes"]["through_hole"] is False
    assert len(stl_data) == 84 + struct.unpack("<I", stl_data[80:84])[0] * 50
    pdf_text = PdfReader(BytesIO(pdf_data)).pages[0].extract_text()
    dims = manifest["files"][0]["dimensions_mm"]
    assert "C1 THROUGH" not in pdf_text
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

    # The hanging ornament is a separate black part.  Its reverse connector is
    # unknown, so no guessed through-hole or integral hook is sent to a vendor.
    charm_zip = output_dir / "endministrator_waterdrop_trial_vendor.zip"
    export_vendor_package(
        [CustomPanelSpec(CHARM_LABEL, CHARM_OUTLINE_CM)], str(charm_zip),
        thickness_mm=2.5, bed_width_mm=220, bed_depth_mm=220,
        material_profile="pa12",
        finish_note="黒い外装候補。吊り金具と表面仕上げは別途決定。",
    )
    with ZipFile(charm_zip) as archive:
        charm_manifest = json.loads(archive.read("manifest.json"))
        charm_pdf_data = archive.read("DIMENSIONED_DRAWINGS.pdf")
        charm_stl = archive.read(charm_manifest["files"][0]["file"])
        with ZipFile(BytesIO(archive.read("all_parts_mm.3mf"))) as model_archive:
            charm_model = ElementTree.fromstring(model_archive.read("3D/3dmodel.model"))
    assert charm_manifest["piece_count"] == 1
    assert charm_manifest["files"][0]["watertight"] is True
    assert charm_manifest["mounting_holes"]["through_hole"] is False
    assert charm_model.attrib["unit"] == "millimeter"
    assert len(charm_stl) == 84 + struct.unpack("<I", charm_stl[80:84])[0] * 50
    charm_pdf_text = PdfReader(BytesIO(charm_pdf_data)).pages[0].extract_text()
    charm_dims = charm_manifest["files"][0]["dimensions_mm"]
    assert f"X {charm_dims['x']:g} mm" in charm_pdf_text
    assert f"Y {charm_dims['y']:g} mm" in charm_pdf_text
    assert f"Z {charm_dims['z']:g} mm" in charm_pdf_text
    charm_pdf = pdf_dir / "PatternForge_Endministrator_waterdrop_trial_drawing.pdf"
    charm_pdf.write_bytes(charm_pdf_data)
    components = {
        "status": "reference_features_compared; dimensions_and_attachments_unverified",
        "reference": COMMERCIAL_DETAIL,
        "observed": [
            {"feature": "glossy yellow shoulder tab", "route": "flexible fabric/faux leather over optional printed core", "cad": "shoulder trial"},
            {"feature": "two silver exposed fasteners", "route": "source separate metal hardware; do not print as plate surface", "cad": "not generated"},
            {"feature": "black dangling teardrop", "route": "separate printed-core trial plus separately chosen hanger", "cad": "waterdrop trial"},
            {"feature": "white edged yellow patch in second close-up", "route": "separate sewn/fabric part", "cad": "not generated"},
        ],
        "unresolved": ["front illustration pixel trace", "real scale", "back and side", "hardware type and hole centers", "charm connector", "wearer fit", "fabrication tolerance"],
        "ready_for_fabrication_order": False,
    }
    component_path = output_dir / "endministrator_accessory_component_review.json"
    component_path.write_text(json.dumps(components, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with ZipFile(zip_path, "a") as archive:
        archive.writestr("COMPONENT_REVIEW.json", json.dumps(components, ensure_ascii=False, indent=2))
    with ZipFile(charm_zip, "a") as archive:
        archive.writestr("COMPONENT_REVIEW.json", json.dumps(components, ensure_ascii=False, indent=2))
    audit = {
        "status": "digital_vendor_package_validated; visual_match_and_physical_fit_unverified",
        "source": SOURCE_IMAGE,
        "official_reference": OFFICIAL_REFERENCE,
        "design_values_are_estimates": True,
        "visual_match_checked_against_source_pixels": False,
        "fabrication_order_approved": False,
        "piece_count": 2,
        "stl_watertight": True,
        "mesh_dimensions_mm": dims,
        "through_holes": manifest["mounting_holes"],
        "component_features_checked": 4,
        "missing_source_dimensions": len(components["unresolved"]),
        "material_request": manifest["material_request"],
        "pdf_pages": 2,
        "vendor_zip_sha256": hashlib.sha256(zip_path.read_bytes()).hexdigest(),
        "charm_vendor_zip_sha256": hashlib.sha256(charm_zip.read_bytes()).hexdigest(),
        "files": {"vendor_zip": str(zip_path.resolve()),
                  "drawing_pdf": str(pdf_path.resolve()),
                  "order_review": str(review_path.resolve()),
                  "charm_vendor_zip": str(charm_zip.resolve()),
                  "charm_drawing_pdf": str(charm_pdf.resolve()),
                  "component_review": str(component_path.resolve())},
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
