"""裁断前のデジタル検査と、仮縫いでしか確定できない検査を分ける。

画像や寸法だけでは、生地の戻り、姿勢、動作時のつれを観測できない。
それらを「問題なし」と推測する代わりに、生成したパーツに応じた検査票を
返し、実測値を既存の補正入力へ戻せるようにする。
"""

from __future__ import annotations

from dataclasses import dataclass

from .compatibility import check_seam_compatibility, unchecked_seams


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
    """生成物に存在する部位だけを含む仮縫い検査票を返す。"""
    kinds = {part.part_type for part in result.finalized_parts}
    checks: list[QualityCheck] = []
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
    construction = result.garment_spec.construction
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
            "デジタル検査は通過しました。本番裁断前に試験片と仮縫いの承認が必要です。"
            if not blockers else
            "未確認または不整合があります。解消するまで本番生地を裁断しないでください。"
        ),
    }
