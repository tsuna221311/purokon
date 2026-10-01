"""
svgpath.py — SVGの path (d属性) を読み書き・変形するための最小ツール。

外部ライブラリを増やさずに済むよう、自前で実装している。
対応コマンド: M L H V C Z （型紙に必要な最小セット）
  M = 移動, L = 直線, H = 水平線, V = 垂直線,
  C = 3次ベジェ曲線（カーブ）, Z = 閉じる

やること:
  1) parse_path : "M 8 0 C 5 0 ..." → セグメントのリスト
  2) scale_segments : X方向 rx倍, Y方向 ry倍 に変形（曲線の制御点ごと）
  3) segments_to_d : セグメント → path文字列に戻す
  4) segments_to_polyline : 曲線を細かい直線に分解した頂点リスト
                            （ネスティングとPDF描画で使う）
"""

from __future__ import annotations
from math import hypot
import re


# 0.01cm = 0.1mm。A4分割印刷や業務用プロッタでも、目で見える
# 角張りを残さないための最終型紙用許容誤差。従来の「各1カーブ12分割」
# と違い、大きく曲がる袖山は細かく、ほぼ直線の部分は少なく分割する。
DEFAULT_CURVE_ERROR_CM = 0.01
_MAX_ADAPTIVE_DEPTH = 14


def parse_path(d: str) -> list[tuple[str, list[float]]]:
    """path文字列をセグメント [(コマンド, [数値...]), ...] に分解する。"""
    # コマンド文字と数値を取り出す
    tokens = re.findall(r"[MLHVCZ]|-?\d*\.?\d+", d, re.IGNORECASE)
    segments: list[tuple[str, list[float]]] = []
    i = 0
    while i < len(tokens):
        cmd = tokens[i]
        i += 1
        if cmd.upper() == "Z":
            segments.append(("Z", []))
            continue
        # コマンドに応じて必要な数値の個数
        n = {"M": 2, "L": 2, "H": 1, "V": 1, "C": 6}[cmd.upper()]
        nums = [float(tokens[i + k]) for k in range(n)]
        i += n
        segments.append((cmd.upper(), nums))
    return segments


def scale_segments(segments: list[tuple[str, list[float]]],
                   rx: float, ry: float) -> list[tuple[str, list[float]]]:
    """全セグメントの座標を X×rx, Y×ry で変形する。曲線の制御点も含む。"""
    out = []
    for cmd, nums in segments:
        if cmd == "Z":
            out.append(("Z", []))
        elif cmd == "H":
            out.append(("H", [nums[0] * rx]))
        elif cmd == "V":
            out.append(("V", [nums[0] * ry]))
        else:
            # M, L, C は (x,y) のペアが並んでいる → 交互に rx, ry を掛ける
            scaled = []
            for k, val in enumerate(nums):
                scaled.append(val * (rx if k % 2 == 0 else ry))
            out.append((cmd, scaled))
    return out


def segments_to_d(segments: list[tuple[str, list[float]]]) -> str:
    """セグメントを path の d文字列に戻す。"""
    parts = []
    for cmd, nums in segments:
        if cmd == "Z":
            parts.append("Z")
        else:
            nums_str = " ".join(f"{v:.3f}" for v in nums)
            parts.append(f"{cmd} {nums_str}")
    return " ".join(parts)


def _bezier_point(p0, p1, p2, p3, t):
    """3次ベジェ曲線上の点を t (0..1) で求める。"""
    mt = 1 - t
    x = (mt**3 * p0[0] + 3 * mt**2 * t * p1[0]
         + 3 * mt * t**2 * p2[0] + t**3 * p3[0])
    y = (mt**3 * p0[1] + 3 * mt**2 * t * p1[1]
         + 3 * mt * t**2 * p2[1] + t**3 * p3[1])
    return (x, y)


def _distance_to_chord(point, start, end) -> float:
    """点から始点ー終点の無限直線までの距離。"""
    dx, dy = end[0] - start[0], end[1] - start[1]
    chord = hypot(dx, dy)
    if chord <= 1e-12:
        return hypot(point[0] - start[0], point[1] - start[1])
    return abs(dy * point[0] - dx * point[1]
               + end[0] * start[1] - end[1] * start[0]) / chord


def _split_cubic_half(p0, p1, p2, p3):
    """de Casteljau法で3次ベジェをt=0.5の2本に分ける。"""
    p01 = ((p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2)
    p12 = ((p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2)
    p23 = ((p2[0] + p3[0]) / 2, (p2[1] + p3[1]) / 2)
    p012 = ((p01[0] + p12[0]) / 2, (p01[1] + p12[1]) / 2)
    p123 = ((p12[0] + p23[0]) / 2, (p12[1] + p23[1]) / 2)
    middle = ((p012[0] + p123[0]) / 2,
              (p012[1] + p123[1]) / 2)
    return ((p0, p01, p012, middle),
            (middle, p123, p23, p3))


def _flatten_cubic(p0, p1, p2, p3, tolerance_cm: float,
                   depth: int = 0) -> list[tuple[float, float]]:
    """カーブが弦から許容値以上離れる間だけ2分し、終点列を返す。

    3次ベジェは制御点の凸包内に必ず収まる。両制御点から弦までの
    距離を判定に使うことで、実際のカーブの逸脱も許容値以内に収める。
    """
    flatness = max(_distance_to_chord(p1, p0, p3),
                   _distance_to_chord(p2, p0, p3))
    if flatness <= tolerance_cm or depth >= _MAX_ADAPTIVE_DEPTH:
        return [p3]
    left, right = _split_cubic_half(p0, p1, p2, p3)
    return (_flatten_cubic(*left, tolerance_cm, depth + 1)
            + _flatten_cubic(*right, tolerance_cm, depth + 1))


def translate_segments(segments: list[tuple[str, list[float]]],
                        dx: float, dy: float) -> list[tuple[str, list[float]]]:
    """全セグメントの座標を (dx, dy) だけ平行移動する。

    H/V は絶対座標の片軸だけを持つコマンドなので、対応する軸の値に
    dx（またはdy）を加えるだけで正しく平行移動できる。
    ネスティング結果をレイアウト上の配置座標に反映する際に使う。
    """
    out = []
    for cmd, nums in segments:
        if cmd == "Z":
            out.append(("Z", []))
        elif cmd == "H":
            out.append(("H", [nums[0] + dx]))
        elif cmd == "V":
            out.append(("V", [nums[0] + dy]))
        else:
            moved = []
            for k, val in enumerate(nums):
                moved.append(val + (dx if k % 2 == 0 else dy))
            out.append((cmd, moved))
    return out


def normalize_hv(segments: list[tuple[str, list[float]]]) -> list[tuple[str, list[float]]]:
    """H/V コマンドを L コマンドに展開する（現在位置を追跡して絶対座標にする）。

    平行移動・回転・バウンディングボックス計算など、座標ペアとして扱いたい
    処理の前処理に使う。M/L/C/Z はそのまま通す。
    """
    out: list[tuple[str, list[float]]] = []
    cur = (0.0, 0.0)
    for cmd, nums in segments:
        if cmd == "M":
            cur = (nums[0], nums[1])
            out.append((cmd, list(nums)))
        elif cmd == "L":
            cur = (nums[0], nums[1])
            out.append((cmd, list(nums)))
        elif cmd == "H":
            cur = (nums[0], cur[1])
            out.append(("L", [cur[0], cur[1]]))
        elif cmd == "V":
            cur = (cur[0], nums[0])
            out.append(("L", [cur[0], cur[1]]))
        elif cmd == "C":
            cur = (nums[4], nums[5])
            out.append((cmd, list(nums)))
        elif cmd == "Z":
            out.append(("Z", []))
    return out


def rotate_segments_90(segments: list[tuple[str, list[float]]]) -> list[tuple[str, list[float]]]:
    """パーツを時計回りに90度回転する（(x, y) -> (-y, x) の後で原点合わせはしない）。

    ネスティングで縦長パーツを横向きにする「回転配置」に使う。
    H/V は回転すると単独の値では表現できなくなるため、事前に normalize_hv で
    L に展開してから回転する。
    """
    normalized = normalize_hv(segments)
    out = []
    for cmd, nums in normalized:
        if cmd == "Z":
            out.append(("Z", []))
        elif cmd == "C":
            rotated = []
            for k in range(0, len(nums), 2):
                x, y = nums[k], nums[k + 1]
                rotated.extend([-y, x])
            out.append((cmd, rotated))
        else:  # M, L
            x, y = nums[0], nums[1]
            out.append((cmd, [-y, x]))
    return out


def bounding_box(segments: list[tuple[str, list[float]]]) -> tuple[float, float, float, float]:
    """セグメントのバウンディングボックスを (min_x, min_y, max_x, max_y) で返す。

    曲線も polyline に展開して評価するので、制御点だけを見るより正確。
    """
    points = segments_to_polyline(segments)
    if not points:
        return (0.0, 0.0, 0.0, 0.0)
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return (min(xs), min(ys), max(xs), max(ys))


def segments_to_polyline(segments: list[tuple[str, list[float]]],
                         curve_steps: int | None = None,
                         max_curve_error_cm: float = DEFAULT_CURVE_ERROR_CM
                         ) -> list[tuple[float, float]]:
    """
    曲線を含むパスを、細かい直線の頂点リストに変換する。
    ネスティング（外接矩形の計算）とPDF描画で使う。
    既定は曲率と実寸に応じて自動分割し、カーブと折れ線の差を
    `max_curve_error_cm`以内にする。`curve_steps`を明示した場合だけ、
    互換性のため従来の固定分割を使う。
    """
    if curve_steps is not None and curve_steps < 1:
        raise ValueError("curve_stepsは1以上で指定してください")
    if max_curve_error_cm <= 0:
        raise ValueError("max_curve_error_cmは0より大きくしてください")
    points: list[tuple[float, float]] = []
    cur = (0.0, 0.0)
    start = (0.0, 0.0)
    for cmd, nums in segments:
        if cmd == "M":
            cur = (nums[0], nums[1]); start = cur
            points.append(cur)
        elif cmd == "L":
            cur = (nums[0], nums[1]); points.append(cur)
        elif cmd == "H":
            cur = (nums[0], cur[1]); points.append(cur)
        elif cmd == "V":
            cur = (cur[0], nums[0]); points.append(cur)
        elif cmd == "C":
            p1 = (nums[0], nums[1]); p2 = (nums[2], nums[3]); p3 = (nums[4], nums[5])
            if curve_steps is None:
                points.extend(_flatten_cubic(
                    cur, p1, p2, p3, max_curve_error_cm))
            else:
                for s in range(1, curve_steps + 1):
                    points.append(_bezier_point(
                        cur, p1, p2, p3, s / curve_steps))
            cur = p3
        elif cmd == "Z":
            points.append(start); cur = start
    return points
