"""裁断前のデジタル検査と、仮縫いでしか確定できない検査を分ける。

画像や寸法だけでは、生地の戻り、姿勢、動作時のつれを観測できない。
それらを「問題なし」と推測する代わりに、生成したパーツに応じた検査票を
返し、実測値を既存の補正入力へ戻せるようにする。
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from shapely.errors import GEOSException
from shapely.geometry import LineString, Point, Polygon

from .compatibility import check_seam_compatibility, unchecked_seams
from .endministrator_armhole import (endministrator_notch_pairing_warnings,
                                      endministrator_side_seam_warnings)
from .hem_extensions import hem_extension_warnings


def pattern_geometry_warnings(parts) -> list[str]:
    """Detect pieces whose raw cutting contour is unsafe to follow.

    A repaired polygon from ``buffer(0)`` can hide a self-intersection or
    remove material.  Inspect the exported coordinates as-is instead, and
    require the cut outline to contain the entire finished shape.
    """
    warnings: list[str] = []
    for part in parts:
        label = part.display_name
        stitch_points, cut_points = part.stitch_line, part.cut_line
        try:
            valid_coordinates = all(
                len(point) == 2 and all(isfinite(float(value)) for value in point)
                for point in stitch_points + cut_points)
        except (TypeError, ValueError, OverflowError):
            valid_coordinates = False
        if (len(stitch_points) < 3 or len(cut_points) < 3
                or not valid_coordinates):
            warnings.append(f"{label}: 輪郭の点が不足するか、座標が不正です")
            continue
        try:
            stitch = Polygon(stitch_points)
            cut = Polygon(cut_points)
        except (TypeError, ValueError):
            warnings.append(f"{label}: 輪郭を多角形として読めません")
            continue
        if (not stitch.is_valid or stitch.is_empty or stitch.area <= 1e-6
                or not cut.is_valid or cut.is_empty or cut.area <= 1e-6):
            warnings.append(f"{label}: 縫い線または裁断線が自己交差・消失しています")
        elif not cut.buffer(1e-6).covers(stitch):
            warnings.append(f"{label}: 裁断線が縫い線の内側に入り込んでいます")
        else:
            grain = part.grainline or {}
            segments = [grain.get("line"), *(grain.get("arrows") or ())]
            try:
                inside = bool(grain.get("line")) and all(
                    segment and stitch.buffer(1e-6).covers(LineString(segment))
                    for segment in segments)
            except (TypeError, ValueError, GEOSException):
                inside = False
            if not inside:
                warnings.append(f"{label}: 布目線が型紙本体の外に出ています")
            stitch_interior = stitch.buffer(-0.01)
            for index, (origin, end) in enumerate(part.notches, start=1):
                try:
                    if not all(isfinite(float(value)) for point in (origin, end)
                               for value in point):
                        raise ValueError("non-finite notch coordinate")
                    mark = LineString((origin, end))
                    if stitch.boundary.distance(Point(origin)) > 0.03:
                        warnings.append(f"{label}: 合印{index}の起点が縫い線から外れています")
                    if cut.boundary.distance(Point(end)) > 0.03:
                        warnings.append(f"{label}: 合印{index}が裁断線に届いていません")
                    if (not stitch_interior.is_empty
                            and mark.intersection(stitch_interior).length > 0.05):
                        warnings.append(f"{label}: 合印{index}が型紙本体を横切っています")
                except (TypeError, ValueError, GEOSException):
                    warnings.append(f"{label}: 合印{index}の座標が不正です")
    return warnings


@dataclass(frozen=True)
class QualityCheck:
    code: str
    label: str
    method: str
    pass_condition: str
    correction_field: str | None = None

    def as_dict(self) -> dict[str, str | None]:
        return {
            "code": self.code,
            "label": self.label,
            "method": self.method,
            "pass_condition": self.pass_condition,
            "correction_field": self.correction_field,
        }


def fitting_checklist(result) -> list[QualityCheck]:
    """印刷から仮縫いまで、生成物に必要な実物検査票を返す。"""
    kinds = {part.part_type for part in result.finalized_parts}
    checks: list[QualityCheck] = [
        QualityCheck(
            "print_scale", "印刷倍率の実測",
            "各型紙PDFを実物大・倍率100%で試し印刷し、校正用の5cm枠を定規で測る。表地・別布・裏地を別々に出す場合は各PDFで確認する。",
            "すべての校正枠が実測5.0cmで、印刷時の自動拡大・縮小が無効である。"),
        QualityCheck(
            "tile_assembly", "分割紙面の貼り合わせ",
            "行列番号に従って全ページを仮配置し、紙面の境界をまたぐ裁断線・縫い線・合印を突き合わせる。",
            "欠けたページ、線の段差、重複がなく、裁断する全パーツが揃っている。"),
    ]
    bodice = bool(kinds & {
        "front_bodice", "back_bodice", "front_bodice_zip_panel",
        "front_bodice_center", "front_bodice_side",
        "back_bodice_center", "back_bodice_side",
    })
    if bodice:
        checks.extend([
            QualityCheck(
                "shoulder_position", "肩線の位置",
                "首側と肩先を合わせて着用し、縫い目と実際の肩先のずれをcmで測る。",
                "前後の肩線が肩の頂点を通り、腕を下ろして食い込みや浮きがない。",
                "肩幅の補正欄"),
            QualityCheck(
                "shoulder_slope", "肩の傾き",
                "肩先または首元で余る布をつまみ、つまんだ幅をcmで測る。",
                "首元・肩先のどちらにも放射状のしわや浮きがない。",
                "肩の傾きの補正欄"),
            QualityCheck(
                "bust_ease", "胸まわり",
                "水平に一周し、足りない量を正、余る量を負としてcmで記録する。",
                "呼吸でき、前中心が開かず、脇線が前後へ引かれない。",
                "胸まわりの補正欄"),
            QualityCheck(
                "waist_ease", "ウエスト",
                "ウエストを水平に一周し、足りない量を正、余る量を負で測る。",
                "座位でも食い込まず、余分なしわが脇へ集中しない。",
                "ウエストの補正欄"),
        ])
    if kinds & {"skirt", "front_pants", "back_pants"}:
        checks.append(QualityCheck(
            "hip_ease", "ヒップと下半身の動作",
            "ヒップを水平に一周して差を測り、座る・しゃがむ・一歩踏み出す。",
            "横じわ、開き、裾の持ち上がりがなく、予定動作を行える。",
            "ヒップの補正欄"))
    if "sleeve" in kinds:
        checks.append(QualityCheck(
            "arm_motion", "袖ぐりと腕の可動域",
            "両腕を前・横・上へ動かし、袖山のねじれと袖ぐりの食い込みを確認する。",
            "予定する最大動作で身頃が大きく持ち上がらず、血流を妨げない。"))
        checks.append(QualityCheck(
            "sleeve_cap_toile", "袖山のいせ込みと左右差",
            "本番生地と同条件の仮縫いで前1本・後ろ2本の合印を合わせ、袖山の波打ち・つれと左右の形を正面・側面・背面で比較する。",
            "袖山に意図しないギャザー、縫い目の裂け、左右差がなく、腕を動かしても肩先に強いしわが出ない。"))
    construction = result.garment_spec.construction
    brief = construction.get("costume_project_brief")
    if isinstance(brief, dict):
        if "custom_panel" in kinds:
            checks.append(QualityCheck(
                "overlay_alignment", "別裁ちパネルの位置・落ち感",
                "左右・前後のパネルをしつけ留めし、正面・側面・背面を撮影して裾位置と布のたまりを測る。",
                "左右非対称の向きが資料と一致し、歩行・着座で巻き込みや大きな浮きがない。"))
        if brief.get("separate_components"):
            checks.append(QualityCheck(
                "costume_attachment", "装飾の固定と干渉",
                "肩・袖口・上腕・背面の別体部品を仮止めし、着脱10回と腕上げ・着座を試す。",
                "取付部が裂けず、金具が外れず、可動を妨げず、肌に鋭い縁が触れない。"))
        if brief.get("limitations"):
            checks.append(QualityCheck(
                "reference_match", "未確定形状の照合",
                "正面・側面・背面の資料と仮縫い写真を並べ、丈・切替・装飾位置を記録する。",
                "推定箇所の寸法と取付位置を着用者・製作者が承認している。"))
    if construction.get("closure") not in (None, "none"):
        checks.append(QualityCheck(
            "closure_load", "開閉部の荷重",
            "開閉を10回行い、着用姿勢と予定動作で端部・留め具周辺を観察する。",
            "噛み込み、口開き、留め具の変形、縫い目の伸びがない。"))
    if construction.get("internal_support") not in (None, "none"):
        checks.append(QualityCheck(
            "support_safety", "芯材・ボーン・造形土台",
            "30分着用し、端部を指でなぞって皮膚への圧力と突き抜けを確認する。",
            "痛み、鋭い端、折れ、ずれ、皮膚への局所的な圧迫がない。"))
    checks.extend([
        QualityCheck(
            "fabric_sample", "本番生地の試験片",
            "20cm角を地直しして前後寸法を測り、縫い代と同条件で縫って引張る。",
            "収縮率を必要量へ反映し、縫い目の波打ち・裂け・色移りがない。"),
        QualityCheck(
            "final_toile", "最終仮縫い承認",
            "左右、前、後ろの写真を撮り、上の全項目を着用者と製作者が確認する。",
            "未確認項目がなく、補正後の仮縫いで再確認済みである。"),
    ])
    return checks


def production_quality_report(result) -> dict[str, object]:
    """機械検査と実物検査を混同しない構造化レポート。"""
    blockers: list[str] = []
    blockers.extend(str(item) for item in
                    result.garment_spec.construction.get("unconfirmed_fields") or [])
    blockers.extend(f"型紙形状: {message}" for message in pattern_geometry_warnings(
        [*result.finalized_parts, *result.lining_parts]))
    blockers.extend(f"裾パネル: {message}" for message in hem_extension_warnings(
        result.finalized_parts,
        result.garment_spec.construction.get("costume_project_brief")))
    brief = result.garment_spec.construction.get("costume_project_brief")
    if isinstance(brief, dict) and brief.get("key") == "endministrator_female":
        blockers.extend(
            f"袖付け合印: {message}" for message in
            endministrator_notch_pairing_warnings(
                result.finalized_parts, require_shoulder=True))
        blockers.extend(
            f"脇縫い線: {message}" for message in
            endministrator_side_seam_warnings(result.finalized_parts))
    blockers.extend(
        f"縫い合わせ: {warning.message}"
        for warning in check_seam_compatibility(result.finalized_parts))
    blockers.extend(
        f"未検査の縫い合わせ: {message}"
        for message in unchecked_seams(result.finalized_parts))
    blockers.extend(
        f"採寸・補正: {message}" for message in result.measurement_warnings)
    if result.nesting.unplaced:
        blockers.append(f"配置できていない型紙が{len(result.nesting.unplaced)}枚あります")
    blockers = list(dict.fromkeys(item for item in blockers if item.strip()))
    checklist = fitting_checklist(result)
    return {
        "digital_ready": not blockers,
        "status": "physical_verification_required" if not blockers else "blocked",
        "blockers": blockers,
        "physical_signoff_required": True,
        "fitting_checklist": [item.as_dict() for item in checklist],
        "summary": (
            "デジタル検査は通過しました。本番裁断前に印刷倍率・貼り合わせ・試験片・仮縫いの確認が必要です。"
            if not blockers else
            "未確認または不整合があります。解消するまで本番生地を裁断しないでください。"
        ),
    }
