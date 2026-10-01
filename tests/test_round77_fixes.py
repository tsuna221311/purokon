"""round77: v125で入った不具合を直した回の見張り。

このファイルが見張るのは4つ。どれも「実際に動かすと壊れた型紙が出るのに、
警告も注記も出ていなかった」ものである。

  1. 前開き＋切り替え線(プリンセスライン)の**パネルの大きさ**
  2. プリーツを入れたときの**ウエストの畳み量と折り線の位置**
  3. 3Dプリント用ZIPが名乗る**watertight(閉じているか)**
  4. 反映できなかった採寸・部位を**言うこと**
"""

import math
import tempfile

import pytest

from engine.measurements import Measurements
from engine.pipeline import PatternForgePipeline, build_garment_spec

#: 体型は「標準M」を含めて広く取る。v125の不具合は**標準Mで**出ていた。
BODIES = [("標準M", 83, 66, 91), ("テスト標準", 84, 68, 92),
          ("バスト大", 96, 66, 100), ("グラマー", 110, 90, 115),
          ("小柄", 70, 55, 80)]


def _body(bust, waist, hip, **kwargs):
    base = dict(bust=bust, waist=waist, hip=hip, height=158,
                sleeve_length=52, shoulder_width=37)
    base.update(kwargs)
    return Measurements(**base)


def _build(spec, body, **kwargs):
    return PatternForgePipeline(
        output_dir=tempfile.mkdtemp()).generate_from_selection(
            spec, body, skip_export=True, **kwargs)


def _one(result, part_type):
    """左右のうち1枚(左右は鏡像なので代表1枚で足りる)。"""
    parts = [p for p in result.finalized_parts
             if p.part_type == part_type and p.label_suffix != "左"]
    assert parts, f"{part_type} がありません"
    return parts[0]


def _top_y(part):
    return min(y for _x, y in part.stitch_line)


# ---------------------------------------------------------------------------
# 1. 前開き＋切り替え線 — パネルの大きさ
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name,bust,waist,hip", BODIES, ids=[b[0] for b in BODIES])
def test_the_front_zip_princess_panels_are_real_panels(name, bust, waist, hip):
    """前開き＋切り替え線で、前のパネルが後ろと同じ形に割れること。

    【v125で何が起きていたか】輪郭を回す起点を「xが脇アンカーにいちばん
    近い点」で選んでいたため、ヒップの開きがあると**脇の下**が脇裾として
    選ばれ、切り替え線が裾のすぐ上を横切っていた。実測(標準M):

        front_bodice_zip_panel  16.2 x  7.4 cm   ← 中心前パネルが切れ端
        front_bodice_side       30.7 x 60.4 cm   ← 「脇パネル」が前身頃ほぼ全部

    後ろは正しく割れているので、**前と後ろを突き合わせれば必ず捕まる**。
    枚数と合印しか見ないテストでは、7.4cmの切れ端が通ってしまう
    (v125の`test_the_princess_line_can_be_combined_with_a_front_zip`が
     実際に通していた)。
    """
    result = _build(build_garment_spec(neckline="round_neck", skirt_style=None,
                                        front_zip=True, princess_line=True),
                     _body(bust, waist, hip))
    centre = _one(result, "front_bodice_zip_panel")
    side = _one(result, "front_bodice_side")
    back_centre = _one(result, "back_bodice_center")
    back_side = _one(result, "back_bodice_side")

    # 中心前パネルは、後ろの中央パネルと同じだけの丈がある。
    assert centre.height_cm == pytest.approx(back_centre.height_cm, abs=1.0), (
        name, centre.height_cm, back_centre.height_cm)
    # 脇パネルは前後で縫い合わせる。丈が揃っていなければ縫えない。
    assert side.height_cm == pytest.approx(back_side.height_cm, abs=1.0), (
        name, side.height_cm, back_side.height_cm)
    # 切り替え線の起点は袖ぐりの上。脇パネルの上端が、後ろと同じ高さに来る。
    assert _top_y(side) == pytest.approx(_top_y(back_side), abs=1.5), name
    # どちらのパネルも、身頃の幅のうち相応の割合を持っている。
    assert centre.width_cm > 8.0 and side.width_cm > 8.0, (
        name, centre.width_cm, side.width_cm)


def test_the_front_zip_princess_split_is_not_at_the_hem():
    """切り替え線が裾の高さから始まっていないこと(v125の壊れ方そのもの)。"""
    result = _build(build_garment_spec(neckline="round_neck", skirt_style=None,
                                        front_zip=True, princess_line=True),
                     _body(83, 66, 91))
    centre = _one(result, "front_bodice_zip_panel")
    hem_y = max(y for _x, y in centre.stitch_line)
    # 中心前パネルの丈が、裾までの距離のほとんどを占めていること。
    assert centre.height_cm > hem_y * 0.8, (centre.height_cm, hem_y)


# ---------------------------------------------------------------------------
# 2. プリーツ — ウエストの畳み量と折り線
# ---------------------------------------------------------------------------

def _waist_edge(part):
    """ウエスト側(上端)の辺の、左右の端と長さ。"""
    top = _top_y(part)
    xs = [x for x, y in part.stitch_line if abs(y - top) < 0.01]
    return min(xs), max(xs), max(xs) - min(xs)


def _pleated(count, depth, **kwargs):
    spec = build_garment_spec(neckline="round_neck", skirt_style="flare")
    spec.construction["pleat_count"] = count
    spec.construction["pleat_depth_cm"] = depth
    spec.construction.update(kwargs)
    return _build(spec, _body(84, 68, 92, height=160, sleeve_length=54))


def test_the_pleats_add_what_they_fold_away():
    """プリーツでたたむ量が、ウエスト辺にちゃんと足されていること。

    【v125で何が起きていたか】足す量を**外接矩形の幅**(フレアスカートでは
    裾幅85.3cm)から出していたため、ウエスト辺には必要な量が届かなかった。

        プリーツ0本      ウエスト辺 35.00cm  たたむ量  0.0cm  仕上がり 35.00cm
        プリーツ3本×2cm  ウエスト辺 38.28cm  たたむ量 12.0cm  仕上がり 26.28cm
        プリーツ6本×2cm  ウエスト辺 39.92cm  たたむ量 24.0cm  仕上がり 15.92cm

    1枚15.92cm×4枚=一周63.7cm。ウエスト68cmの人は着られない。
    """
    def _waist_total(result):
        return sum(_waist_edge(part)[2] for part in result.finalized_parts
                   if part.part_type == "skirt")

    base = _waist_total(_pleated(0, 0.0))
    for count, depth in ((2, 2.0), (3, 2.0), (6, 2.0), (4, 3.5)):
        total = _waist_total(_pleated(count, depth))
        folded = 2.0 * depth * count
        assert total - folded == pytest.approx(base, abs=0.3), (
            count, depth, total, folded, base)


def test_every_pleat_fold_line_lands_on_the_waist_edge():
    """折り線が、ウエスト辺の上に乗っていること。

    プリーツはウエストからたたむ。外接矩形の比で置くと、裾が広がった
    スカートでは**ウエスト辺の外**に線が出る。実測(6本×2cm)では
    6本中4本がウエスト辺の外にあり、そのままではたためなかった。
    """
    part = _one(_pleated(6, 2.0), "skirt")
    lo, hi, _width = _waist_edge(part)
    lines = [(label, pts) for label, pts in part.reference_lines
             if "プリーツ" in label]
    assert lines, "折り線が1本も出ていません"
    outside = [(label, round(pts[0][0], 2)) for label, pts in lines
               if not (lo - 0.01 <= pts[0][0] <= hi + 0.01)]
    assert not outside, (f"ウエスト辺 {lo:.2f}〜{hi:.2f} の外に折り線: {outside}")


def test_the_waist_reported_to_the_seam_check_is_the_finished_one():
    """縫い合わせの検査へ渡すウエストが、**輪郭から測った**仕上がり値であること。

    v125はここへ「広げる前の値」を書き込んでいた。幅が足りていなくても
    検査を通ってしまうので、壊れたプリーツが素通りしていた。
    """
    plain = _one(_pleated(0, 0.0), "skirt")
    _lo, _hi, base = _waist_edge(plain)
    for count, depth in ((2, 2.0), (6, 2.0)):
        part = _one(_pleated(count, depth), "skirt")
        reported = part.compatibility_measurements.get("waist_opening_length")
        assert reported is not None, "仕上がりウエストを渡していません"
        assert reported == pytest.approx(base, abs=0.3), (count, depth, reported, base)


def test_the_pleated_skirt_still_matches_its_waistband():
    """プリーツを入れても、ウエストバンドとの突き合わせが通ること。"""
    spec = build_garment_spec(neckline="round_neck", skirt_style="flare",
                              include_waistband=True)
    spec.construction["pleat_count"] = 6
    spec.construction["pleat_depth_cm"] = 2.0
    result = _build(spec, _body(84, 68, 92, height=160, sleeve_length=54))
    kinds = {w.kind for w in result.compatibility_warnings()}
    assert "waistband_skirt" not in kinds, [
        w.message for w in result.compatibility_warnings()]


# ---------------------------------------------------------------------------
# 3. 3Dプリント — watertightを名乗るなら測る
# ---------------------------------------------------------------------------

#: 凹んだ形。v125ではここで上下面の三角形が落ち、メッシュに穴が開いた。
CONCAVE = [(3.0, 7.94), (6.99, 2.44), (5.74, 5.25), (8.75, 7.29),
           (2.88, 9.8), (1.18, 4.18), (7.57, 1.52)]
CONVEX = [(0.0, 0.0), (10.0, 0.0), (10.0, 6.0), (0.0, 6.0)]
L_SHAPE = [(0.0, 0.0), (10.0, 0.0), (10.0, 4.0), (4.0, 4.0), (4.0, 10.0), (0.0, 10.0)]


def _stl_vertices(path):
    """STL(テキスト・バイナリどちらでも)から頂点を順に読む。"""
    import re
    import struct

    raw = open(path, "rb").read()
    if raw[:5] == b"solid" and b"facet" in raw[:2048]:
        return [tuple(round(float(v), 4) for v in m) for m in
                re.findall(rb"vertex\s+(\S+)\s+(\S+)\s+(\S+)", raw)]
    count = struct.unpack("<I", raw[80:84])[0]
    out = []
    for i in range(count):
        block = raw[84 + i * 50 + 12:84 + i * 50 + 48]
        values = struct.unpack("<9f", block)
        out.extend(tuple(round(v, 4) for v in values[j * 3:j * 3 + 3])
                   for j in range(3))
    return out


def _open_edge_count(path):
    """閉じていない辺(2枚の面で共有されていない辺)の本数。"""
    from collections import Counter

    verts = _stl_vertices(path)
    counts: Counter = Counter()
    for i in range(0, len(verts), 3):
        face = verts[i:i + 3]
        for a, b in ((0, 1), (1, 2), (2, 0)):
            counts[frozenset((face[a], face[b]))] += 1
    return sum(1 for _edge, n in counts.items() if n != 2)


@pytest.mark.parametrize("name,points",
                         [("凸", CONVEX), ("L字", L_SHAPE), ("凹", CONCAVE)])
def test_the_mesh_is_actually_closed(name, points, tmp_path):
    """凹んだ形でも、出したSTLが閉じていること。

    【v125で何が起きていたか】上下面を`shapely.ops.triangulate`(頂点集合の
    ドロネー分割)で張り、多角形の外へ出た三角形を捨てていた。凹形状では
    捨てた分の穴が残る。実測(凹形状): 三角形20枚のうち上下面は2枚だけ、
    閉じていない辺が12本。
    """
    from engine.accessory3d import export_accessories_stl
    from engine.custom_panel import CustomPanelSpec

    path = str(tmp_path / "part.stl")
    export_accessories_stl([CustomPanelSpec(name, points)], path,
                            thickness_mm=3.0)
    assert _open_edge_count(path) == 0, f"{name}: メッシュに穴があります"


def test_the_manifest_does_not_claim_watertight_without_measuring(tmp_path):
    """業者へ渡すmanifestのwatertightが、決め打ちでなく実測であること。

    v125は`"watertight": True`をそのまま書いていた。穴の開いたメッシュでも
    「閉じている」と業者へ申告していた。
    """
    import json
    import zipfile

    from engine.accessory3d import export_vendor_package
    from engine.custom_panel import CustomPanelSpec

    path = str(tmp_path / "vendor.zip")
    export_vendor_package([CustomPanelSpec("翼", CONCAVE)], path,
                           thickness_mm=3.0)
    with zipfile.ZipFile(path) as bundle:
        manifest = json.loads(bundle.read("manifest.json").decode("utf-8"))
        entry = manifest["files"][0]
        stl = bundle.extract(entry["file"], str(tmp_path))
    measured = _open_edge_count(stl) == 0
    assert entry["watertight"] == measured, (
        f"manifestは{entry['watertight']}と書いているが、実測は{measured}")
    assert entry["watertight"] is True, "凹形状でも閉じたメッシュを出すこと"


def test_the_watertight_flag_follows_the_mesh(monkeypatch, tmp_path):
    """メッシュが閉じていなければ、falseと書くこと(決め打ちでないことの確認)。

    わざと面を1枚落として、manifestが追従することを見る。決め打ちに
    戻すと、このテストが落ちる。
    """
    import json
    import zipfile

    import engine.accessory3d as A
    from engine.custom_panel import CustomPanelSpec

    original = A._extrude

    def drop_one(*args, **kwargs):
        faces = original(*args, **kwargs)
        return faces[1:] if len(faces) > 1 else faces

    monkeypatch.setattr(A, "_extrude", drop_one)
    path = str(tmp_path / "broken.zip")
    A.export_vendor_package([CustomPanelSpec("翼", CONVEX)], path,
                             thickness_mm=3.0)
    with zipfile.ZipFile(path) as bundle:
        manifest = json.loads(bundle.read("manifest.json").decode("utf-8"))
    assert manifest["files"][0]["watertight"] is False


# ---------------------------------------------------------------------------
# 4. 反映できなかったことを言う
# ---------------------------------------------------------------------------

def _measured_block(**overrides):
    from engine.blocks import MEASURED_BLOCK_FIELDS

    values = {key: (lo + hi) / 2 for key, (lo, hi, _label) in
              MEASURED_BLOCK_FIELDS.items()}
    values.update(overrides)
    return values


def test_it_says_when_the_measured_block_could_not_be_used():
    """採寸指定原型の値を型紙へ反映しきれなかったら、そう言うこと。

    【v125で何が起きていたか】背幅・胸幅は8.0〜40.0cmを受け付けるが、
    8cmでも9cmでも実際には9.210cmで引かれていた(袖ぐりのえぐれが頭打ち)。
    `chest_width_limited`は立っているのに警告は空で、型紙に刷る注記は
    「胸幅=8cmで引きました」——**引いていない数字**を印字していた。
    """
    result = _build(build_garment_spec(neckline="round_neck", skirt_style=None),
                     _body(83, 66, 91),
                     measured_block=_measured_block(back_width_cm=8.0,
                                                     chest_width_cm=8.0))
    notes = "\n".join(result.summary()["design_notes"]) \
        + "\n".join(result.measurement_warnings)
    assert "胸幅9.2cm" in notes, notes
    assert "狭められませんでした" in notes, notes


def test_it_does_not_say_that_when_the_block_was_used():
    """反映できた人に、その注記を出さないこと(空振りの確認)。"""
    result = _build(build_garment_spec(neckline="round_neck", skirt_style=None),
                     _body(83, 66, 91),
                     measured_block=_measured_block(back_width_cm=14.0,
                                                     chest_width_cm=14.0))
    notes = "\n".join(result.summary()["design_notes"]) \
        + "\n".join(result.measurement_warnings)
    assert "狭められませんでした" not in notes


def test_it_says_when_a_lining_scope_is_not_in_this_pattern():
    """裏地の対象部位がこの型紙に無いなら、そう言うこと。

    【v125で何が起きていたか】身頃だけの型紙に「スカートに裏地」を
    指定すると、裏地も注記も警告も**何も出なかった**。
    """
    spec = build_garment_spec(neckline="round_neck", skirt_style=None)
    spec.construction["lining_scope"] = ["skirt"]
    result = _build(spec, _body(84, 68, 92), lining=True)
    notes = "\n".join(result.summary()["design_notes"])
    assert "スカート" in notes, notes
    assert "ありません" in notes or "無い" in notes, notes


def test_it_does_not_say_that_when_the_scope_is_present():
    """対象部位がある型紙では、その注記を出さないこと(空振りの確認)。"""
    spec = build_garment_spec(neckline="round_neck", skirt_style="flare")
    spec.construction["lining_scope"] = ["skirt"]
    result = _build(spec, _body(84, 68, 92), lining=True)
    notes = "\n".join(result.summary()["design_notes"])
    assert "この型紙にありません" not in notes
    assert result.lining_parts, "裏地が引かれていません"


def test_the_split_does_not_depend_on_which_way_the_outline_winds():
    """輪郭の回り方(時計回り/反時計回り)が変わっても、同じ形に割れること。

    テンプレートは全部同じ向きで描いてあるので、普段は効かない手当てである。
    描き直したときに黙って壊れないよう、輪郭を逆回しにして直接確かめる。
    """
    import engine.princess as PR

    captured = {}
    original = PR._split_zip_panel

    def spy(points, scaled, measurements, fit=None):
        forward = original(points, scaled, measurements, fit)
        reversed_ring = [points[0]] + list(reversed(points[1:-1])) + [points[-1]]
        backward = original(reversed_ring, scaled, measurements, fit)
        captured["forward"] = forward
        captured["backward"] = backward
        return forward

    PR._split_zip_panel = spy
    try:
        import engine.pipeline as PP
        PP._split_zip_panel = spy
        _build(build_garment_spec(neckline="round_neck", skirt_style=None,
                                   front_zip=True, princess_line=True),
               _body(83, 66, 91))
    finally:
        PR._split_zip_panel = original
        import engine.pipeline as PP
        PP._split_zip_panel = original

    forward, backward = captured.get("forward"), captured.get("backward")
    assert forward is not None and backward is not None, "分割が呼ばれていません"

    def _height(segments):
        ys = [args[i + 1] for _cmd, args in segments
              for i in range(0, len(args) - 1, 2)]
        return max(ys) - min(ys)

    assert _height(backward[0]) == pytest.approx(_height(forward[0]), abs=0.5)
    assert _height(backward[1]) == pytest.approx(_height(forward[1]), abs=0.5)


def test_the_reported_waist_follows_the_outline_even_if_the_widening_is_wrong(monkeypatch):
    """広げ方が間違っていたら、報告するウエストもそれに追従すること。

    v125はここへ「広げる前の値」を定数のように書き込んでいたので、
    幅が足りていなくても縫い合わせ検査を素通りした。わざと広げ方を
    壊して、報告値が**輪郭から測った値**であることを確かめる。
    """
    import engine.construction_features as CF

    original = CF._waist_edge_span

    def too_narrow(part):
        lo, hi = original(part)
        return (lo, lo + (hi - lo) * 0.5)      # ウエスト辺を半分と誤認させる

    plain = _one(_pleated(0, 0.0), "skirt")
    _lo, _hi, base = _waist_edge(plain)
    monkeypatch.setattr(CF, "_waist_edge_span", too_narrow)
    part = _one(_pleated(4, 2.0), "skirt")
    reported = part.compatibility_measurements.get("waist_opening_length")
    assert reported is not None
    assert abs(reported - base) > 1.0, (
        f"広げ方を壊したのに、報告値が{reported:.2f}cmのまま基準{base:.2f}cmと"
        "一致しています(輪郭から測っていません)")


def test_it_refuses_when_the_faces_do_not_cover_the_shape(monkeypatch, tmp_path):
    """三角形で面を覆いきれなかったら、黙って出さずに断ること。"""
    import engine.accessory3d as A
    from engine.custom_panel import CustomPanelSpec

    original = A._ear_clip
    monkeypatch.setattr(A, "_ear_clip", lambda points: original(points)[1:])
    with pytest.raises(ValueError) as excinfo:
        A.export_accessories_stl([CustomPanelSpec("x", CONVEX)],
                                  str(tmp_path / "a.stl"), thickness_mm=3.0)
    assert "覆いきれ" in str(excinfo.value)


@pytest.mark.parametrize("holes", [1, 2, 3, 4], ids=lambda n: f"穴{n}個")
def test_holes_are_bridged_without_crossing_each_other(holes):
    """穴が複数あっても、橋どうしが交差せず面を張れること。

    橋を架ける相手を**元の多角形**に対してだけ見ていると、2つ目の橋が
    1つ目の橋と交差しうる。実測では穴1つと3つは通り、**2つのときだけ**
    三角形が0枚になった(気付きにくい形だった)。
    """
    from shapely.geometry import Point, Polygon

    from engine.accessory3d import _triangulate_polygon

    shape = Polygon([(0, 0), (100, 0), (100, 60), (0, 60)])
    for index in range(holes):
        shape = shape.difference(Point(13 * index + 12, 30).buffer(5, quad_segs=8))
    faces = _triangulate_polygon(shape)
    covered = sum(abs((b[0] - a[0]) * (c[1] - a[1])
                      - (c[0] - a[0]) * (b[1] - a[1])) / 2.0
                  for a, b, c in faces)
    assert covered == pytest.approx(shape.area, abs=1e-6), (holes, len(faces))

