"""Make a clearly labelled *concept* video for the 1:3 blue-dress paper demo.

This is a visual explanation of the intended workflow, not footage of a sewn
garment or a physical fit test.  It reuses the project's original three-view
sketch and generated blue-dress pattern geometry.
"""

from __future__ import annotations

import argparse
import io
from pathlib import Path
import xml.etree.ElementTree as ET

import cairosvg
import imageio_ffmpeg
from PIL import Image, ImageDraw, ImageFont


WIDTH, HEIGHT, FPS, DURATION = 1280, 720, 15, 26
FONT_REGULAR = "C:/Windows/Fonts/NotoSansJP-VF.ttf"
FONT_BOLD = "C:/Windows/Fonts/BIZ-UDGothicB.ttc"
NAVY = "#17233d"
BLUE = "#3477bd"
INK = "#253650"


def font(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(FONT_BOLD if bold else FONT_REGULAR, size)


def sketch_image(source: Path) -> Image.Image:
    return Image.open(io.BytesIO(cairosvg.svg2png(
        url=str(source), output_width=1050, output_height=470))).convert("RGBA")


def pattern_image(source: Path) -> Image.Image:
    root = ET.fromstring(source.read_bytes())
    for parent in root.iter():
        for child in list(parent):
            if child.tag.endswith("}text"):
                parent.remove(child)
    return Image.open(io.BytesIO(cairosvg.svg2png(
        bytestring=ET.tostring(root, encoding="utf-8"),
        output_width=550))).convert("RGBA")


def fit(image: Image.Image, max_width: int, max_height: int) -> Image.Image:
    scale = min(max_width / image.width, max_height / image.height)
    return image.resize((round(image.width * scale), round(image.height * scale)),
                        Image.Resampling.LANCZOS)


def panel(draw: ImageDraw.ImageDraw, box, *, fill="#ffffff", outline="#dce5f0"):
    draw.rounded_rectangle(box, radius=24, fill=fill, outline=outline, width=2)


def centered(draw, x, y, content, size, *, color=INK, bold=False):
    draw.text((x, y), content, font=font(size, bold=bold), fill=color,
              anchor="mt")


def caption(draw, content: str, *, accent=False):
    draw.rounded_rectangle((65, 637, 1215, 689), radius=13,
                           fill="#e9f2fb" if accent else "#eef2f6")
    centered(draw, 640, 646, content, 22, color=INK, bold=True)


def draw_doll(image: Image.Image, x: int, top: int, *, garment: float):
    """Stylized jointed mannequin with layered paper garment, not a render."""
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)
    skin, edge, joint = "#e6d7c5", "#9d9185", "#c8baa9"
    # Body and joints are deliberately schematic.
    d.ellipse((x - 31, top, x + 31, top + 67), fill=skin, outline=edge, width=3)
    d.rounded_rectangle((x - 14, top + 59, x + 14, top + 88), radius=10,
                        fill=skin, outline=edge, width=2)
    d.polygon([(x - 59, top + 83), (x + 59, top + 83),
               (x + 49, top + 239), (x - 49, top + 239)], fill=skin)
    d.line([(x - 59, top + 83), (x - 49, top + 239),
            (x + 49, top + 239), (x + 59, top + 83)], fill=edge, width=3)
    for sign in (-1, 1):
        d.line([(x + sign * 55, top + 100),
                (x + sign * 83, top + 181),
                (x + sign * 99, top + 263)], fill=edge, width=32)
        d.line([(x + sign * 55, top + 100),
                (x + sign * 83, top + 181),
                (x + sign * 99, top + 263)], fill=skin, width=26)
        d.ellipse((x + sign * 83 - 13, top + 181 - 13,
                   x + sign * 83 + 13, top + 181 + 13),
                  fill=joint, outline=edge, width=2)
        d.line([(x + sign * 31, top + 241),
                (x + sign * 38, top + 341),
                (x + sign * 38, top + 445)], fill=edge, width=38)
        d.line([(x + sign * 31, top + 241),
                (x + sign * 38, top + 341),
                (x + sign * 38, top + 445)], fill=skin, width=32)
        d.ellipse((x + sign * 38 - 16, top + 340 - 16,
                   x + sign * 38 + 16, top + 340 + 16),
                  fill=joint, outline=edge, width=2)
    if garment > 0:
        alpha = int(255 * min(1.0, garment * 2.6))
        # Bodice with paper-fold shading.
        d.polygon([(x - 64, top + 83), (x - 20, top + 78),
                   (x + 20, top + 78), (x + 64, top + 83),
                   (x + 49, top + 227), (x - 49, top + 227)],
                  fill=(52, 116, 184, alpha), outline=(24, 55, 95, alpha))
        d.polygon([(x - 49, top + 90), (x - 16, top + 83),
                   (x - 28, top + 219), (x - 49, top + 219)],
                  fill=(30, 86, 152, int(alpha * .55)))
        d.arc((x - 25, top + 60, x + 25, top + 105), 4, 176,
              fill=(235, 240, 246, alpha), width=4)
        d.line((x - 49, top + 225, x + 49, top + 225),
               fill=(12, 47, 94, alpha), width=5)
    if garment > .26:
        alpha = int(255 * min(1.0, (garment - .26) * 3))
        for sign in (-1, 1):
            d.polygon([(x + sign * 60, top + 91),
                       (x + sign * 85, top + 177),
                       (x + sign * 103, top + 263),
                       (x + sign * 75, top + 266),
                       (x + sign * 51, top + 174),
                       (x + sign * 40, top + 96)],
                      fill=(54, 116, 184, alpha),
                      outline=(24, 55, 95, alpha))
            d.line((x + sign * 77, top + 248, x + sign * 101, top + 246),
                   fill=(194, 218, 241, alpha), width=3)
    if garment > .53:
        alpha = int(255 * min(1.0, (garment - .53) * 3.2))
        d.polygon([(x - 49, top + 228), (x + 49, top + 228),
                   (x + 132, top + 423), (x + 92, top + 438),
                   (x - 92, top + 438), (x - 132, top + 423)],
                  fill=(55, 113, 180, alpha),
                  outline=(24, 55, 95, alpha))
        d.polygon([(x - 49, top + 229), (x - 20, top + 230),
                   (x - 74, top + 430), (x - 107, top + 424)],
                  fill=(23, 74, 136, int(alpha * .40)))
        for dx in (-78, -26, 36, 87):
            d.line((x + dx // 2, top + 245, x + dx, top + 423),
                   fill=(181, 209, 233, int(alpha * .43)), width=2)
        d.arc((x - 125, top + 406, x + 125, top + 443), 0, 180,
              fill=(189, 216, 239, alpha), width=3)
    image.alpha_composite(overlay)


def render_frame(t: float, sketch: Image.Image,
                 pattern: Image.Image) -> Image.Image:
    image = Image.new("RGBA", (WIDTH, HEIGHT), "#f3f7fb")
    d = ImageDraw.Draw(image)
    d.rectangle((0, 0, WIDTH, 105), fill=NAVY)
    d.text((66, 28), "PatternForge", font=font(28, bold=True), fill="white")
    d.text((64, 72), "ラフから型紙へ。そして紙模型で確かめる。",
           font=font(16), fill="#c8d8ec")
    d.text((1196, 50), "1:3 DEMO", font=font(16, bold=True),
           fill="#a9d4ff", anchor="ra")
    d.rectangle((0, 699, WIDTH, 720), fill=NAVY)
    d.rectangle((0, 699, int(WIDTH * t / DURATION), 704), fill="#58a8ec")

    if t < 3.0:
        centered(d, 640, 210, "衣装のイメージを、手に取れる初稿へ", 39,
                 bold=True, color=NAVY)
        centered(d, 640, 296, "オリジナル青いドレス / 1:3 紙模型デモ", 27)
        panel(d, (390, 390, 890, 494), fill="#e6f1fa")
        centered(d, 640, 416, "イラスト  →  型紙  →  人形で確認", 26,
                 bold=True, color="#315b8a")
        caption(d, "これは制作工程の説明動画です。実物を縫った記録ではありません。")
    elif t < 9.0:
        panel(d, (90, 143, 1190, 603))
        thumb = fit(sketch, 1000, 438)
        image.alpha_composite(thumb, ((WIDTH - thumb.width) // 2,
                                      148 + (455 - thumb.height) // 2))
        d.rounded_rectangle((101, 154, 474, 203), radius=12, fill="#e1effb")
        d.text((119, 163), "01  正面・側面・背面のラフ", font=font(22, bold=True),
               fill="#235b94")
        caption(d, "見た目とパーツ構成を確認。ここでは画像AIで自動判定していません。")
    elif t < 16.0:
        panel(d, (86, 144, 1194, 604))
        thumb = fit(sketch, 420, 230)
        image.alpha_composite(thumb, (130, 246))
        d.text((133, 188), "ラフ3面図", font=font(23, bold=True), fill=NAVY)
        d.line((574, 372, 704, 372), fill="#5d8fbd", width=8)
        d.polygon([(704, 372), (679, 355), (679, 389)], fill="#5d8fbd")
        p = fit(pattern, 390, 400)
        image.alpha_composite(p, (744 + (410 - p.width)//2, 178))
        d.text((757, 159), "縮尺 1:3 の型紙", font=font(23, bold=True),
               fill=NAVY)
        d.rounded_rectangle((760, 550, 1126, 593), radius=11, fill="#e8eff9")
        centered(d, 943, 559, "元寸10cm → 印刷33.3mm", 17,
                 color="#315b8a", bold=True)
        caption(d, "A4で100%印刷。黒実線が裁断線、破線が縫い線です。", accent=True)
    elif t < 23.0:
        panel(d, (87, 144, 1193, 604))
        p = fit(pattern, 340, 395)
        image.alpha_composite(p, (151 + (350 - p.width)//2, 183))
        d.text((139, 167), "紙の型紙を切り出す", font=font(22, bold=True),
               fill=NAVY)
        d.line((535, 372, 659, 372), fill="#5d8fbd", width=8)
        d.polygon([(659, 372), (633, 355), (633, 389)], fill="#5d8fbd")
        progress = min(1.0, (t - 16) / 4.7)
        draw_doll(image, 900, 147, garment=progress)
        d = ImageDraw.Draw(image)
        d.text((749, 165), "紙模型を人形へ", font=font(22, bold=True), fill=NAVY)
        d.rounded_rectangle((733, 555, 1139, 591), radius=8, fill="#fff0e8")
        centered(d, 936, 560, "組み立てイメージ（実物未作成）", 16,
                 color="#9a4e31", bold=True)
        caption(d, "肩・袖・丈・開き位置を、人形に当てて書き込む想定です。")
    else:
        panel(d, (87, 145, 1193, 605))
        draw_doll(image, 350, 149, garment=1.0)
        d = ImageDraw.Draw(image)
        d.text((628, 177), "見て、触って、初稿に戻す", font=font(31, bold=True),
               fill=NAVY)
        questions = ["肩・袖は動かしやすい？", "丈と広がりはイメージどおり？",
                     "着脱用の開きはどこに必要？"]
        for i, question in enumerate(questions):
            y = 257 + i * 80
            d.rounded_rectangle((624, y, 1127, y + 58), radius=13,
                                fill="#e8f1fa")
            d.text((649, y + 11), question, font=font(21, bold=True),
                   fill="#244a76")
        caption(d, "実際の人形の採寸・紙組み・仮縫いは、これから行います。", accent=True)
    return image.convert("RGB")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--three-view", type=Path, required=True)
    parser.add_argument("--pattern-svg", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    sketch = sketch_image(args.three_view)
    pattern = pattern_image(args.pattern_svg)
    writer = imageio_ffmpeg.write_frames(
        str(args.out), (WIDTH, HEIGHT), fps=FPS, codec="libx264",
        output_params=["-pix_fmt", "yuv420p", "-movflags", "+faststart"],
        ffmpeg_log_level="error")
    writer.send(None)
    keyframes = []
    try:
        for index in range(DURATION * FPS):
            frame = render_frame(index / FPS, sketch, pattern)
            if index in (45, 150, 300, 360):
                keyframes.append(frame.copy())
            writer.send(frame.tobytes())
    finally:
        writer.close()
    contact = Image.new("RGB", (WIDTH, HEIGHT // 2), "white")
    for index, frame in enumerate(keyframes[:4]):
        contact.paste(frame.resize((WIDTH // 2, HEIGHT // 4),
                                   Image.Resampling.LANCZOS),
                      ((index % 2) * WIDTH // 2,
                       (index // 2) * HEIGHT // 4))
    contact.save(args.out.with_name(args.out.stem + "_contact.png"))


if __name__ == "__main__":
    main()
