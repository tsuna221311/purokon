"""round72の検証に使ったアニメ風の衣装ラフを描き直すスクリプト。

    python3 docs/round72_illustrations/draw_illustrations.py docs/round72_illustrations

で `mia.svg` / `ren.svg` / `sera.svg` を書き出す。PNGにするには、同じ
ディレクトリに出る `*.html` をブラウザで900×1500のビューポートで
スクリーンショットすればよい（round72ではheadless Chromiumで行った）。

既存のアニメ作品のキャラクター画像は使えないので、**この検証のために
自分で描いた**架空の衣装を3着用意する。狙いは「絵から型紙を起こす」経路に
実際の絵を通すことで、絵そのものの美しさではない。

各絵は、コスプレ衣装のラフによくある

    * 正面向き・全身・白い背景
    * 線画＋塗り(シルエットがはっきり出る)
    * 頭と手足は描く(実際のラフがそうなので、頭を含む絵で試す意味がある)

という条件で描く。
"""
import math
import pathlib
import sys

W, H = 900, 1500
OUT = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/claude-0/r72")
OUT.mkdir(parents=True, exist_ok=True)

SKIN = "#f6d9c4"
HAIR = "#4a3b52"
LINE = "#2b2430"


def head(cx, top, scale=1.0, neck_to=None):
    """頭・髪・首。

    首は**肩線まで**届かせる。最初は首を302で止めて肩線(330)との間に白を
    残していたため、頭が本体とつながらず、シルエット(連結成分のいちばん
    大きい塊)から頭が丸ごと落ちていた。実測で上端が120ではなく330になり、
    頭を描いた絵で必ず通るはずの首・肩の検出が、一度も動いていなかった。
    """
    r = 78 * scale
    return f"""
  <ellipse cx="{cx}" cy="{top + r}" rx="{r * 0.78}" ry="{r}" fill="{SKIN}" stroke="{LINE}" stroke-width="3"/>
  <path d="M{cx - r * 0.86} {top + r * 0.95}
           C{cx - r * 0.95} {top - r * 0.35} {cx + r * 0.95} {top - r * 0.35} {cx + r * 0.86} {top + r * 0.95}
           C{cx + r * 0.7} {top + r * 0.35} {cx - r * 0.7} {top + r * 0.35} {cx - r * 0.86} {top + r * 0.95} Z"
        fill="{HAIR}"/>
  <path d="M{cx - r * 0.86} {top + r * 0.9} L{cx - r * 1.05} {top + r * 2.6} L{cx - r * 0.55} {top + r * 2.2} Z" fill="{HAIR}"/>
  <path d="M{cx + r * 0.86} {top + r * 0.9} L{cx + r * 1.05} {top + r * 2.6} L{cx + r * 0.55} {top + r * 2.2} Z" fill="{HAIR}"/>
  <rect x="{cx - 20}" y="{top + r * 1.8}" width="40" height="{(neck_to if neck_to is not None else top + r * 1.8 + 42) - (top + r * 1.8)}" fill="{SKIN}" stroke="{LINE}" stroke-width="3"/>
"""


def legs(cx, top, bottom, gap=26):
    return f"""
  <rect x="{cx - gap - 34}" y="{top}" width="34" height="{bottom - top}" rx="16" fill="{SKIN}" stroke="{LINE}" stroke-width="3"/>
  <rect x="{cx + gap}" y="{top}" width="34" height="{bottom - top}" rx="16" fill="{SKIN}" stroke="{LINE}" stroke-width="3"/>
"""


def svg(body, name):
    doc = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
           f'viewBox="0 0 {W} {H}"><rect width="{W}" height="{H}" fill="#ffffff"/>'
           + body + "</svg>")
    (OUT / f"{name}.svg").write_text(doc, encoding="utf-8")
    (OUT / f"{name}.html").write_text(
        f"<!doctype html><html><body style='margin:0'>{doc}</body></html>",
        encoding="utf-8")
    return name


# --- ①「星屑のミア」: パフ袖・フレアの短いスカート・セーラー衿 ----------------
CX = W // 2
SH_Y = 330          # 肩の高さ
WAIST_Y = 600
HEM_Y = 860

mia = head(CX, 120, neck_to=SH_Y + 8) + f"""
  <!-- パフ袖(丸くふくらんだ短い袖) -->
  <ellipse cx="{CX - 168}" cy="{SH_Y + 52}" rx="82" ry="70" fill="#e8ecf8" stroke="{LINE}" stroke-width="4"/>
  <ellipse cx="{CX + 168}" cy="{SH_Y + 52}" rx="82" ry="70" fill="#e8ecf8" stroke="{LINE}" stroke-width="4"/>
  <!-- 腕 -->
  <rect x="{CX - 222}" y="{SH_Y + 110}" width="40" height="250" rx="19" fill="{SKIN}" stroke="{LINE}" stroke-width="3"/>
  <rect x="{CX + 182}" y="{SH_Y + 110}" width="40" height="250" rx="19" fill="{SKIN}" stroke="{LINE}" stroke-width="3"/>
  <!-- 身頃(ウエストでくびれる) -->
  <path d="M{CX - 118} {SH_Y}
           L{CX + 118} {SH_Y}
           C{CX + 128} {SH_Y + 130} {CX + 104} {WAIST_Y - 60} {CX + 86} {WAIST_Y}
           L{CX - 86} {WAIST_Y}
           C{CX - 104} {WAIST_Y - 60} {CX - 128} {SH_Y + 130} {CX - 118} {SH_Y} Z"
        fill="#e8ecf8" stroke="{LINE}" stroke-width="4"/>
  <!-- セーラー衿 -->
  <path d="M{CX - 118} {SH_Y} L{CX - 56} {SH_Y + 6} L{CX} {SH_Y + 86} L{CX + 56} {SH_Y + 6} L{CX + 118} {SH_Y}
           L{CX + 96} {SH_Y + 104} L{CX - 96} {SH_Y + 104} Z"
        fill="#5566aa" stroke="{LINE}" stroke-width="4"/>
  <!-- フレアの短いスカート -->
  <path d="M{CX - 86} {WAIST_Y}
           L{CX + 86} {WAIST_Y}
           L{CX + 236} {HEM_Y}
           L{CX - 236} {HEM_Y} Z"
        fill="#5566aa" stroke="{LINE}" stroke-width="4"/>
""" + legs(CX, HEM_Y - 10, 1330)
svg(mia, "mia")

# --- ②「制服のレン」: 長袖・タイトな膝丈スカート ------------------------------
SH_Y = 330
WAIST_Y = 610
HEM_Y = 960
ren = head(CX, 120, neck_to=SH_Y + 8) + f"""
  <!-- 長袖(まっすぐ) -->
  <path d="M{CX - 118} {SH_Y} L{CX - 186} {SH_Y + 34} L{CX - 206} {SH_Y + 400} L{CX - 142} {SH_Y + 400} L{CX - 124} {SH_Y + 90} Z"
        fill="#1f2a44" stroke="{LINE}" stroke-width="4"/>
  <path d="M{CX + 118} {SH_Y} L{CX + 186} {SH_Y + 34} L{CX + 206} {SH_Y + 400} L{CX + 142} {SH_Y + 400} L{CX + 124} {SH_Y + 90} Z"
        fill="#1f2a44" stroke="{LINE}" stroke-width="4"/>
  <rect x="{CX - 206}" y="{SH_Y + 400}" width="64" height="70" rx="26" fill="{SKIN}" stroke="{LINE}" stroke-width="3"/>
  <rect x="{CX + 142}" y="{SH_Y + 400}" width="64" height="70" rx="26" fill="{SKIN}" stroke="{LINE}" stroke-width="3"/>
  <!-- 身頃 -->
  <path d="M{CX - 118} {SH_Y} L{CX + 118} {SH_Y}
           C{CX + 124} {SH_Y + 140} {CX + 100} {WAIST_Y - 60} {CX + 80} {WAIST_Y}
           L{CX - 80} {WAIST_Y}
           C{CX - 100} {WAIST_Y - 60} {CX - 124} {SH_Y + 140} {CX - 118} {SH_Y} Z"
        fill="#1f2a44" stroke="{LINE}" stroke-width="4"/>
  <!-- Vネック -->
  <path d="M{CX - 62} {SH_Y + 2} L{CX} {SH_Y + 96} L{CX + 62} {SH_Y + 2} Z" fill="#f2f2ee" stroke="{LINE}" stroke-width="3"/>
  <!-- タイトな膝丈スカート(ほぼ広がらない) -->
  <path d="M{CX - 80} {WAIST_Y} L{CX + 80} {WAIST_Y} L{CX + 96} {HEM_Y} L{CX - 96} {HEM_Y} Z"
        fill="#3b3f52" stroke="{LINE}" stroke-width="4"/>
""" + legs(CX, HEM_Y - 10, 1330)
svg(ren, "ren")

# --- ③「夜会のセラ」: ノースリーブ・床までのサーキュラードレス ----------------
SH_Y = 330
WAIST_Y = 590
HEM_Y = 1330
pts = []
for i in range(41):
    t = i / 40
    x = CX - 330 + 660 * t
    y = HEM_Y + 26 * math.sin(t * math.pi * 5)
    pts.append(f"{x:.1f} {y:.1f}")
hem_path = " L".join(pts)
# 衿ぐりが深く抉れているので、首はその底(SH_Y+40)より下まで届かせる。
sera = head(CX, 120, neck_to=SH_Y + 52) + f"""
  <!-- 腕(ノースリーブなので肩から素肌)。
       肩で身頃と重ねてつなげ、脇の下から下は外へ開かせる。離して描くと
       シルエットから腕ごと捨てられ、身頃にぴたりと沿わせると腕と胴の
       すき間が閉じた穴になって埋められる——どちらでも腕が見えなくなる。 -->
  <path d="M{CX - 92} {SH_Y + 6} L{CX - 134} {SH_Y + 6} L{CX - 176} {SH_Y + 360} L{CX - 134} {SH_Y + 360} L{CX - 120} {SH_Y + 90} Z"
        fill="{SKIN}" stroke="{LINE}" stroke-width="3"/>
  <path d="M{CX + 92} {SH_Y + 6} L{CX + 134} {SH_Y + 6} L{CX + 176} {SH_Y + 360} L{CX + 134} {SH_Y + 360} L{CX + 120} {SH_Y + 90} Z"
        fill="{SKIN}" stroke="{LINE}" stroke-width="3"/>
  <!-- 身頃(ノースリーブ・袖ぐりは滑らかなカーブ) -->
  <path d="M{CX - 104} {SH_Y}
           C{CX - 118} {SH_Y + 90} {CX - 112} {WAIST_Y - 80} {CX - 78} {WAIST_Y}
           L{CX + 78} {WAIST_Y}
           C{CX + 112} {WAIST_Y - 80} {CX + 118} {SH_Y + 90} {CX + 104} {SH_Y}
           C{CX + 60} {SH_Y + 40} {CX - 60} {SH_Y + 40} {CX - 104} {SH_Y} Z"
        fill="#7a2f4e" stroke="{LINE}" stroke-width="4"/>
  <!-- 床までのサーキュラースカート -->
  <path d="M{CX - 78} {WAIST_Y} L{CX + 78} {WAIST_Y} L{CX + 330} {HEM_Y} L{hem_path} L{CX - 330} {HEM_Y} Z"
        fill="#7a2f4e" stroke="{LINE}" stroke-width="4"/>
"""
svg(sera, "sera")
print("描いた:", ", ".join(p.name for p in sorted(OUT.glob("*.svg"))))
