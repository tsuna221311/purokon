"""生成した衣装型紙の製作仕様書PDFを作る。

型紙だけでは伝わらない採寸、パーツ寸法、構造指定、縫製順、未確定事項を
同じjob_idへ束ねる。未確認値を推測で「確定」とは表示しない。
"""

from __future__ import annotations

import os
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import (
    PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)
from .production_quality import fitting_checklist, production_quality_report


_FONT = "HeiseiKakuGo-W5"
try:
    pdfmetrics.registerFont(UnicodeCIDFont(_FONT))
except Exception:  # pragma: no cover - reportlab側で登録済みの場合など
    _FONT = "Helvetica"


_MEASUREMENT_LABELS = {
    "bust": "バスト", "waist": "ウエスト", "hip": "ヒップ",
    "height": "身長", "sleeve_length": "袖丈", "shoulder_width": "肩幅",
    "upper_arm": "二の腕", "bust_point_spacing": "乳間",
    "bust_point_drop": "乳下がり", "head_circumference": "頭囲",
}

_CONSTRUCTION_LABELS = {
    "closure": "開閉方法", "closure_length_cm": "開き長（cm）",
    "closure_count": "留め具の個数", "closure_spacing_cm": "留め具の間隔（cm）",
    "closure_overlap_cm": "打ち合わせ・重なり（cm）",
    "symmetry": "左右構造", "layer_count": "重ね枚数",
    "layer_lengths_cm": "層ごとの丈（cm）", "movement": "使用時の動き",
    "gather_ratio": "ギャザー倍率", "pleat_count": "プリーツ本数",
    "pleat_depth_cm": "ひだ深さ（cm）", "construction_note": "仕立てメモ",
    "slit_position": "スリット位置", "slit_length_cm": "スリット長",
    "internal_support": "内部支持", "motif_position": "柄・装飾位置",
    "petticoat_style": "パニエ方式", "petticoat_tier_count": "パニエ段数",
    "petticoat_length_cm": "パニエ丈（cm）",
    "petticoat_fullness_ratio": "段ごとの周長倍率",
    "petticoat_hoop_diameters_cm": "ワイヤー輪直径（cm）",
    "petticoat_waist_cm": "パニエ仕上がりウエスト（cm）",
    "petticoat_seam_allowance_cm": "パニエ縫い代（cm）",
    "interfacing_targets": "接着芯を貼る部位",
    "interfacing_inset_cm": "接着芯の縁からの控え（cm）",
    "motif_width_cm": "柄・装飾幅", "motif_height_cm": "柄・装飾高さ",
    "motif_outline_normalized": "装飾画像の外周線",
    "motif_regions_normalized": "装飾画像の主要色面",
    "lining_scope": "裏地を付ける部位",
    "accessory_3d": "3D小物",
}


def _styles():
    base = getSampleStyleSheet()
    normal = ParagraphStyle(
        "jp", parent=base["BodyText"], fontName=_FONT, fontSize=9.5,
        leading=14, wordWrap="CJK", spaceAfter=3,
    )
    heading = ParagraphStyle(
        "jp-heading", parent=normal, fontSize=14, leading=19,
        textColor=colors.HexColor("#172047"), spaceBefore=9, spaceAfter=5,
        keepWithNext=1,
    )
    title = ParagraphStyle(
        "jp-title", parent=heading, fontSize=21, leading=27,
        alignment=TA_CENTER, spaceAfter=10,
    )
    small = ParagraphStyle("jp-small", parent=normal, fontSize=8, leading=11)
    return normal, heading, title, small


def _p(value, style):
    return Paragraph(escape(str(value)).replace("\n", "<br/>"), style)


def _table(rows, widths, normal, *, header=True, compact=False):
    rendered = [[_p(cell, normal) for cell in row] for row in rows]
    table = Table(rendered, colWidths=widths, repeatRows=1 if header else 0,
                  hAlign="LEFT")
    commands = [
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#9AA1B5")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 1 if compact else 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1 if compact else 4),
    ]
    if header:
        commands += [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E9ECF7")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#172047")),
        ]
    table.setStyle(TableStyle(commands))
    return table


def _construction_value(key: str, value) -> str:
    if key == "interfacing_targets" and isinstance(value, (list, tuple)):
        labels = {
            "bodice": "前後身頃", "sleeve": "袖", "skirt": "スカート",
            "pants": "パンツ", "collar": "衿", "cuffs": "カフス",
            "waistband": "ウエスト帯", "hood": "フード",
            "custom_panel": "カスタムパーツ",
        }
        return " / ".join(labels.get(str(item), str(item)) for item in value)
    if key == "lining_scope" and isinstance(value, (list, tuple)):
        labels = {
            "front_bodice": "前身頃", "back_bodice": "後ろ身頃",
            "sleeve": "袖", "skirt": "スカート",
            "front_pants": "パンツ前", "back_pants": "パンツ後ろ",
        }
        return " / ".join(labels.get(str(item), str(item)) for item in value)
    if key == "motif_outline_normalized" and isinstance(value, (list, tuple)):
        return f"画像から抽出済み（{len(value)}点の閉じた外周）"
    if key == "motif_regions_normalized" and isinstance(value, (list, tuple)):
        colours = [str(item.get("color")) for item in value if isinstance(item, dict)]
        return f"画像から抽出済み（{len(value)}領域: {' / '.join(colours)}）"
    if key == "accessory_3d" and isinstance(value, dict):
        radius = value.get("curvature_radius_mm")
        axis_label = {"width": "横", "height": "縦", "both": "横＋縦"}.get(
            value.get("curve_axis"), "横")
        shape = (f"曲率半径{radius:g}mm・"
                 f"{axis_label}曲げ"
                 if radius is not None else "平板")
        hole_pattern = value.get("mounting_hole_pattern", "none")
        hole_names = {"center": "中央1穴", "pair_width": "左右2穴", "pair_height": "上下2穴"}
        holes = (f" / 取付穴{hole_names.get(hole_pattern, hole_pattern)}"
                 f"・直径{value.get('mounting_hole_diameter_mm'):g}mm"
                 if hole_pattern != "none" else " / 取付穴なし")
        slot_pattern = value.get("mounting_slot_pattern", "none")
        slot_names = {"center": "中央1穴", "pair_width": "左右2穴", "pair_height": "上下2穴"}
        slots = (f" / ベルト長穴{slot_names.get(slot_pattern, slot_pattern)}"
                 f"・{value.get('mounting_slot_length_mm'):g}×"
                 f"{value.get('mounting_slot_width_mm'):g}mm・"
                 f"{'横' if value.get('mounting_slot_axis') == 'width' else '縦'}向き"
                 if slot_pattern != "none" else " / ベルト長穴なし")
        magnet_pattern = value.get("magnet_pocket_pattern", "none")
        magnet_names = {
            "center": "中央1個", "pair_width": "左右2個", "pair_height": "上下2個"}
        magnets = (
            f" / 磁石ポケット{magnet_names.get(magnet_pattern, magnet_pattern)}"
            f"・直径{value.get('magnet_pocket_diameter_mm'):g}mm"
            f"・深さ{value.get('magnet_pocket_depth_mm'):g}mm・非貫通"
            if magnet_pattern != "none" else " / 磁石ポケットなし")
        attachment_names = {
            "sew_on_clip": "縫い付けクリップ", "brooch_pin": "ブローチピン",
            "pivot_joint": "可動軸・リベット",
        }
        attachment = value.get("attachment_interface", "none")
        attachment_text = (f" / 市販金具{attachment_names.get(attachment, attachment)}"
                           if attachment != "none" else "")
        return (f"厚み{value.get('thickness_mm', 3):g}mm / {shape} / "
                f"素材{value.get('material_profile', 'consult')} / "
                f"仕上げ{value.get('finish_note', '業者と相談')}"
                f"{holes}{slots}{magnets}{attachment_text}")
    if isinstance(value, bool):
        return "あり" if value else "なし"
    labels = {
        "closure": {
            "none": "開閉部品なし", "front_zip": "前ファスナー",
            "back_zip": "後ろファスナー", "side_zip": "脇ファスナー",
            "hooks": "ホック", "snaps": "スナップ",
        },
        "symmetry": {"symmetric": "左右対称", "asymmetric": "左右非対称"},
        "movement": {"standard": "通常動作", "dance": "ダンス",
                     "action": "激しい演技"},
        "internal_support": {
            "none": "芯材なし", "interfacing": "接着芯", "boning": "ボーン",
            "petticoat": "パニエ", "armor_base": "造形物用の土台",
        },
        "slit_position": {
            "none": "なし", "front": "前中心", "back": "後ろ中心",
            "left": "左脇", "right": "右脇",
        },
        "petticoat_style": {"soft": "柔らかい段フリル式", "hoop": "ワイヤー式"},
    }
    if key in labels:
        return labels[key].get(str(value), str(value))
    if key == "layer_lengths_cm" and isinstance(value, (list, tuple)):
        return " / ".join(f"第{index}層 {float(length):g}cm"
                          for index, length in enumerate(value, start=1))
    if key == "gather_ratio":
        return f"{float(value):g}倍"
    if key == "petticoat_fullness_ratio":
        return f"{float(value):g}倍"
    if key == "petticoat_hoop_diameters_cm" and isinstance(value, (list, tuple)):
        return " / ".join(f"第{index}段 {float(diameter):g}cm"
                          for index, diameter in enumerate(value, start=1))
    return str(value)


def production_readiness(result) -> tuple[bool, list[str]]:
    """Use the same geometry and seam gate as the digital quality report."""
    report = production_quality_report(result)
    return bool(report["digital_ready"]), list(report["blockers"])


def export_specification_pdf(result, output_path: str) -> str:
    """この生成結果に対応するA4製作仕様書を原子的に書き出す。"""
    normal, heading, title, small = _styles()
    ready, pending = production_readiness(result)
    costume_brief = result.garment_spec.construction.get("costume_project_brief")
    if not isinstance(costume_brief, dict):
        costume_brief = None
    temp_path = output_path + ".tmp"
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(
        temp_path, pagesize=A4, rightMargin=14 * mm, leftMargin=14 * mm,
        topMargin=13 * mm, bottomMargin=13 * mm,
        title="PatternForge 製作仕様書", author="PatternForge",
    )
    story = [
        _p("PatternForge 製作仕様書", title),
        _table([
            ["ジョブID", result.job_id],
            *([["対象衣装", costume_brief.get("label", "")]] if costume_brief else []),
            ["製作判定", ("仮縫い用の試作可（本番裁断は実物確認後）" if ready
                      else "要確認（確認完了まで裁断しない）")],
            ["型紙", f"表地・別布{len(result.finalized_parts)}枚 / 裏地{len(result.lining_parts)}枚"],
            ["縫い代", f"標準{result.seam_allowance_cm:g}cm / 裾"
             + (f"{result.hem_seam_allowance_cm:g}cm"
                if result.hem_seam_allowance_cm is not None else "標準と同じ")],
        ], [34 * mm, 142 * mm], normal, header=False),
        Spacer(1, 4 * mm),
    ]

    story.append(_p("製作前の確認事項", heading))
    if pending:
        story.append(_table(
            [["状態", "確認内容"]] + [["未確認", item] for item in pending],
            [24 * mm, 152 * mm], normal))
    else:
        story.append(_p("自動検査で未配置・採寸警告・縫い合わせ不整合・未確認入力はありません。仮縫い確認は別途必要です。", normal))

    story.append(_p("採寸（cm）", heading))
    measurement_rows = [["項目", "入力値"]] + [
        [_MEASUREMENT_LABELS.get(key, key), f"{value:g}"]
        for key, value in result.measurements.as_dict().items()
    ]
    story.append(_table(measurement_rows, [74 * mm, 102 * mm], normal))

    story.append(_p("型紙パーツ一覧", heading))
    part_rows = [["パーツ", "裁断寸法（外接）", "裁ち方"]]
    for part in result.finalized_parts:
        part_rows.append([
            part.display_name,
            f"{part.width_cm:.1f} × {part.height_cm:.1f} cm",
            part.cutting_note,
        ])
    story.append(_table(part_rows, [72 * mm, 42 * mm, 62 * mm], small))

    construction = {
        key: value for key, value in result.garment_spec.construction.items()
        if key not in {"unconfirmed_fields", "draft_mode", "costume_project_brief",
                       "hem_extension_pairs"}
    }
    if construction:
        story.append(_p("構造・装飾指定", heading))
        rows = [["項目", "確定値"]] + [
            [_CONSTRUCTION_LABELS.get(key, key), _construction_value(key, value)]
            for key, value in construction.items()
        ]
        story.append(_table(rows, [58 * mm, 118 * mm], normal))

    story += [PageBreak(), _p("縫製順・検査記録", title)]
    steps = result.assembly_steps()
    step_rows = [["No.", "工程", "内容"]] + [
        [step.number, step.title, step.detail] for step in steps
    ]
    story.append(_table(step_rows, [12 * mm, 42 * mm, 122 * mm], small))

    notes = list(result.design_notes)
    if result.lining_notes:
        notes.extend(result.lining_notes)
    story.append(_p("設計・素材メモ", heading))
    if result.shopping_list:
        story.append(_p(
            f"生地幅{result.nesting.fabric_width_cm:g}cm / 必要長さ"
            f"{result.nesting.used_length_cm / 100:.2f}m。", normal))
    for note in notes or ["追加メモはありません。"]:
        story.append(_p(f"・{note}", normal))

    if costume_brief:
        # Long design notes may spill onto a nearly empty page.  Continue the
        # costume plan there instead of forcing another mostly blank sheet.
        story += [Spacer(1, 6 * mm), _p("衣装固有の製作計画", title)]
        story.append(_p(
            "以下は型紙の幾何検査とは別の制作指示です。正面資料から推定した部分は"
            "仮縫いと背面資料で確認するまで確定寸法として扱わないでください。", normal))
        from .hem_extensions import hem_extension_rows
        paired_rows = hem_extension_rows(result.finalized_parts, costume_brief)
        if paired_rows:
            story.append(_p("裾パネルの縫い合わせ表", heading))
            story.append(_p(
                "A/B/Cは型紙の接合記号です。両方の縫い線と1/4・3/4の合印を"
                "合わせ、折り返し裾にはしないでください。", normal))
            story.append(_table(
                [["記号", "本体裾", "追加パネル上辺", "縫い線長 本体/パネル"]
                 ] + [list(row) for row in paired_rows],
                [14 * mm, 49 * mm, 68 * mm, 45 * mm], small))
        sections = (
            ("型紙に含む布パーツ", "patternable_components"),
            ("別途製作・調達する部品", "separate_components"),
            ("素材の使い分け", "material_plan"),
            ("組立・取付の順序", "construction_plan"),
            ("未確定事項", "limitations"),
        )
        for label, key in sections:
            items = costume_brief.get(key)
            if not isinstance(items, (list, tuple)) or not items:
                continue
            story.append(_p(label, heading))
            for item in items:
                story.append(_p(f"・{item}", normal))

    # The costume-specific notes may continue onto a second page.  Do not
    # force another break here: that used to strand two short caveats on an
    # otherwise empty page before the fitting checklist.
    story += [Spacer(1, 6 * mm), _p("仮縫い・実物検査票", title)]
    story.append(_p(
        "デジタル検査を通過しても、生地の伸び・姿勢・動作時のつれは実物でしか"
        "確定できません。測った補正量は画面の「着てみて合わなかったら」へ入力し、"
        "再生成後にもう一度確認してください。", normal))
    fitting_rows = [["確認部位", "測り方", "合格条件", "記録"]]
    for item in fitting_checklist(result):
        correction = (f"入力先: {item.correction_field}" if item.correction_field
                      else "結果: □合格 □要修正")
        fitting_rows.append([item.label, item.method, item.pass_condition, correction])
    story.append(_table(fitting_rows, [28 * mm, 56 * mm, 60 * mm, 32 * mm],
                        small, compact=True))

    story.append(Spacer(1, 1 * mm))
    story.append(_p(
        "重要: 本書は入力値と自動検査の記録です。素材固有の伸び、熱、強度、着用者の動作は実物の仮縫いで確認してください。未確認欄がある場合は解消するまで本番生地を裁断しないでください。",
        small))
    try:
        doc.build(story)
        os.replace(temp_path, output_path)
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)
    return output_path
