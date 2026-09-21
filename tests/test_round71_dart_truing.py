"""round71: 胸ぐせダーツの2本の脚が揃っておらず、たたんでも平らにならなかった。

コスプレイヤーとして実際に作るつもりで、標準体型(B88 W68 H95 身長163)の
型紙を出し、ダーツのところを測った。

【実測】ダーツの脚が2cm余る

```
    ダーツ先端 T = (12.05, 25.66)   ← BPの手前2.83cmで止めてある(正しい)
    口A        = ( 0.05, 27.91)     脚 T→A = 12.210cm
    口B        = ( 0.14, 33.41)     脚 T→B = 14.208cm
                                    ────────────────
                                    差       1.998cm (14.1%)
```

ダーツは**2本の脚を合わせて縫う**。長い方が2cm余るということは、
たたんでも平らにならない——脇線に2cmの段差が残る。標準体型だけの
話ではなく、B80〜B130の10通りすべてで 1.77〜3.04cm (9.8〜14.1%)
ずれていた。

原因は幾何そのものにある。脇の胸ぐせダーツは

  * 口を**脇線の上**(まっすぐな線の上)に並べ、
  * 先端を**BP**へ向けて斜めに刺す

ので、口の中心と先端が同じ高さに来ない。実測では先端が口の中心より
5.0cm上にあり、そのぶん上の脚が短くなっていた。**口を脇線に並べたまま
脚を揃えることは、原理的にできない。**

洋裁ではこれを「たたみ出し」で解く——ダーツをたたんだ状態で脇線を
引き直して裁つ。すると口の片方が脇線から少し外へ出る(型紙で見かける、
あの出っ張り)。`engine/darts.py`の`_true_dart`はその手順をそのまま
計算している。

もう1つ、**縫うと脇線がどれだけ縮むか**の見積もりも直した。round70まで
「口の縦幅ぶん縮む」としていたが、それが正しいのは口が脇線の上に
並んでいるときだけである。実測(B88)では、たたみ出し後の本当の縮み量は
4.66cmで、口の縦幅5.50cmより0.84cm小さかった。つまり前身頃を0.84cm
長く引いていた。

このファイルが見張るのは:

  1. ダーツの脚が揃わなくなる(＝たたんでも平らにならない)
  2. たたんだときに脇線が折れる/段差が出る
  3. 縮む量を「口の縦幅」で見積もるやり方に戻る
  4. ダーツがBPを狙わなくなる・先端がBPに刺さる
  5. たたみ出しのせいでダーツをダーツと認識できなくなる
"""

import math
import tempfile

import pytest

from engine import compatibility as C
from engine.darts import (BUST_DART_TRUING_MAX_OFFSET_CM, _equalise_legs,
                          retrue_bust_darts)
from engine.measurements import Measurements
from engine.pipeline import PatternForgePipeline, build_garment_spec

#: 実際に出した型紙で確かめる体型。小柄から大きめまで。
BODIES = [
    ("B80 W60 H86", Measurements(bust=80, waist=60, hip=86, height=152,
                                  sleeve_length=57, shoulder_width=38)),
    ("B88 W68 H95", Measurements(bust=88, waist=68, hip=95, height=163,
                                  sleeve_length=58, shoulder_width=39)),
    ("B96 W68 H95", Measurements(bust=96, waist=68, hip=95, height=163,
                                  sleeve_length=58, shoulder_width=39)),
    ("B104 W92 H112", Measurements(bust=104, waist=92, hip=112, height=176,
                                    sleeve_length=60, shoulder_width=43)),
    ("B130 W110 H132", Measurements(bust=130, waist=110, hip=132, height=175,
                                     sleeve_length=57, shoulder_width=38)),
]


def _generate(measurements, **spec_kw):
    pipe = PatternForgePipeline(output_dir=tempfile.mkdtemp())
    spec = build_garment_spec(skirt_style="tight", **spec_kw)
    return pipe.generate_from_selection(spec, measurements, skip_export=True)


def _darts_of(part):
    """輪郭から胸ぐせダーツ(口A・先端・口B)を取り出す。

    探し方は`engine/compatibility.py`の`_is_dart_notch_at`に合わせる
    ——見張る側と探す側で規則が食い違うと、片方だけ静かに素通りする。
    """
    points = C._closed_points(part.stitch_line)
    return [(points[i], points[i + 1], points[i + 2])
            for i in range(len(points) - 3)
            if C._is_dart_notch_at(points, i, 0.5)]


def _bust_darts(result):
    out = []
    for part in result.finalized_parts:
        if part.part_type not in ("front_bodice", "front_bodice_zip_panel"):
            continue
        out.extend(_darts_of(part))
    return out


def _sewn_side_seam(part):
    """左の脇線を、**ダーツをたたんだ状態**で測る。

    ダーツをたたむと口Aと口Bが重なるので、縫った後の脇線は
    「脇の下→口A」＋「口B→裾」である。型紙の上の長さ
    (`side_seam_length`)ではなく、**実際に縫う長さ**を見たいときに使う。
    """
    points = C._closed_points(part.stitch_line)
    underarm = C.underarm_y_of(part)
    xs = [q[0] for q in points]
    center = (min(xs) + max(xs)) / 2.0
    hem = max(q[1] for q in points)
    start = next(i for i, q in enumerate(points)
                 if abs(q[1] - underarm) < 1e-6 and q[0] < center)
    total = 0.0
    cursor = points[start]
    i = start
    while i < len(points) - 1:
        if C._is_dart_notch_at(points, i, 0.5):
            total += math.dist(cursor, points[i])
            cursor = points[i + 2]          # たたむと口Bは口Aに重なる
            i += 2
            continue
        nxt = points[i + 1]
        total += math.dist(cursor, nxt)
        cursor = nxt
        i += 1
        if abs(nxt[1] - hem) < 1e-6:
            break
    return total


# --- 1. 脚が揃っている ------------------------------------------------------

@pytest.mark.parametrize("label,measurements", BODIES, ids=[b[0] for b in BODIES])
def test_the_two_dart_legs_are_the_same_length(label, measurements):
    """ダーツの2本の脚が同じ長さであること。

    揃っていなければ、長い方が余ってたためない。round70までの実測:
    B80で1.77cm / B88で2.00cm / B130で3.04cm 余っていた。
    """
    darts = _bust_darts(_generate(measurements))
    assert darts, f"{label}: ダーツが1本も無く、テストが空振りしています"
    for mouth_a, tip, mouth_b in darts:
        leg_a = math.dist(tip, mouth_a)
        leg_b = math.dist(tip, mouth_b)
        assert leg_a == pytest.approx(leg_b, abs=1e-6), (
            f"{label}: ダーツの脚が {leg_a:.4f} と {leg_b:.4f} で "
            f"{abs(leg_a - leg_b):.4f}cm ずれています。たたんでも平らになりません")


def test_the_front_zip_panel_darts_are_equal_too():
    """前開き(中心前で裁ち割る)パネルのダーツも同じであること。

    こちらは脇線が1本しか無い非対称なパーツで、ダーツの置き方も別経路
    (`BUST_DART_ZIP_PANEL_PART_TYPES`)を通る。片方だけ直したまま
    出荷しないよう、別に見張る。
    """
    darts = _bust_darts(_generate(BODIES[1][1], front_zip=True))
    assert darts, "前開きのダーツが見つからず、テストが空振りしています"
    for mouth_a, tip, mouth_b in darts:
        assert math.dist(tip, mouth_a) == pytest.approx(math.dist(tip, mouth_b),
                                                        abs=1e-6)


# --- 2. たたむと脇線がつながる ----------------------------------------------

@pytest.mark.parametrize("label,measurements", BODIES, ids=[b[0] for b in BODIES])
def test_folding_the_dart_closes_it_without_a_step(label, measurements):
    """ダーツをたたむと、口Bが口Aにぴったり重なること。

    これが「平らにたためる」の定義そのものである。先端を中心に回して
    脚Bを脚Aに重ねたとき、口Bが口Aから離れていれば、その距離が
    そのまま脇線に残る段差になる。
    """
    for mouth_a, tip, mouth_b in _bust_darts(_generate(measurements)):
        leg_a = math.dist(tip, mouth_a)
        leg_b = math.dist(tip, mouth_b)
        unit_a = ((mouth_a[0] - tip[0]) / leg_a, (mouth_a[1] - tip[1]) / leg_a)
        unit_b = ((mouth_b[0] - tip[0]) / leg_b, (mouth_b[1] - tip[1]) / leg_b)
        angle = (math.atan2(unit_a[1], unit_a[0])
                 - math.atan2(unit_b[1], unit_b[0]))
        sin_a, cos_a = math.sin(angle), math.cos(angle)
        dx, dy = mouth_b[0] - tip[0], mouth_b[1] - tip[1]
        folded = (tip[0] + dx * cos_a - dy * sin_a,
                  tip[1] + dx * sin_a + dy * cos_a)
        assert math.dist(folded, mouth_a) == pytest.approx(0.0, abs=1e-6), (
            f"{label}: たたむと脇線に {math.dist(folded, mouth_a):.3f}cm の段差が残ります")


@pytest.mark.parametrize("label,measurements", BODIES, ids=[b[0] for b in BODIES])
def test_the_front_and_back_side_seams_still_match(label, measurements):
    """前後の脇線が、たたみ出しの後も釣り合っていること。

    たたみ出しは口を脇線から少し外へ出すので、**縮む量の見積もりを
    直さないと前身頃が長すぎる型紙になる**(実測でB88は0.84cm長かった)。
    ここが崩れると「そのままでは縫えません」という警告が出る。
    """
    result = _generate(measurements)
    parts = {}
    for part in result.finalized_parts:
        parts.setdefault(part.part_type, []).append(part)
    front_part = parts["front_bodice"][0]
    back = C.side_seam_length(parts["back_bodice"][0]) / 2.0
    front = _sewn_side_seam(front_part)

    # 許容は0.4cm。エンジンの警告のしきい値(1.5cm)より**厳しく**取る。
    #
    # round70の見積もり違い(縮む量＝口の縦幅)は、実測でB88の前身頃を
    # 0.84cm長くしていた。1.5cmで見ると素通りしてしまうので、ここは
    # 「直したことが効いている」と言える細かさで見る。直した後の実測は
    # 0.10〜0.25cmである。
    assert abs(front - back) <= 0.4, (
        f"{label}: 縫った後の脇線が 前{front:.2f} / 後{back:.2f} で "
        f"{front - back:+.2f}cm 食い違っています")


@pytest.mark.parametrize("label,measurements", BODIES, ids=[b[0] for b in BODIES])
def test_no_sewing_warning_comes_out_of_a_plain_bodice(label, measurements):
    """普通の身頃で「縫えません」の警告が出ないこと。

    たたみ出しで口が脇線から外れると、見張る側が**ダーツをダーツと
    認識できなくなり**、脇線の断片を取りこぼす。実測で、前身頃の脇線が
    35.2cmのはずが31.4cmと報告され、誤った警告が出た。
    """
    warnings = _generate(measurements).compatibility_warnings()
    seam_warnings = [w for w in warnings if "脇" in w.message]
    assert seam_warnings == [], f"{label}: {[w.message for w in seam_warnings]}"


# --- 3. 縮む量を「口の縦幅」で見積もらない ----------------------------------

def test_the_seam_shrink_is_measured_not_assumed():
    """`_mouth_span`が、縮む量を口の縦幅ではなく実際の長さから出すこと。

    口が脇線の上に並んでいる場合、両者は**厳密に一致する**(全部が同一
    直線に乗るため)。食い違うのは、たたみ出しで口が脇線から外れたとき
    ——つまり round71 で直した当のところだけである。
    """
    from engine.darts import _mouth_span

    # 口が脇線(x=0の縦線)の上に並んでいる形。両者は一致する。
    on_seam = [("L", [0.0, 10.0]), ("L", [6.0, 12.0]), ("L", [0.0, 14.0]),
               ("L", [0.0, 30.0])]
    assert _mouth_span(on_seam, (0.0, 0.0))[1] == pytest.approx(4.0)
    assert _mouth_span(on_seam)[1] == pytest.approx(4.0)

    # 口が脇線から外れている形(たたみ出し後)。縦幅より小さくなる。
    trued = [("L", [-1.5, 10.2]), ("L", [6.0, 12.0]), ("L", [0.8, 13.8]),
             ("L", [0.0, 30.0])]
    measured = _mouth_span(trued, (0.0, 0.0))[1]
    mouth_height = abs(13.8 - 10.2)
    assert measured != pytest.approx(mouth_height)
    assert 0 < measured < mouth_height


# --- 4. ダーツはBPを狙い、刺さらない ----------------------------------------

@pytest.mark.parametrize("label,measurements", BODIES, ids=[b[0] for b in BODIES])
def test_truing_moves_the_mouths_and_nothing_else(label, measurements, monkeypatch):
    """たたみ出しが動かすのは**口だけ**で、先端は1mmも動かないこと。

    先端の位置は「BPの手前で止める」という判断そのもの(round28)である。
    たたみ出しでそこが動いたら、ダーツが狙う先が変わってしまう。
    たたみ出しを止めた型紙と、掛けた型紙の先端を突き合わせる。
    """
    import engine.darts as darts_module

    trued = sorted(t for _a, t, _b in _bust_darts(_generate(measurements)))

    monkeypatch.setattr(darts_module, "_equalise_legs", lambda *a, **k: None)
    plain = sorted(t for _a, t, _b in _bust_darts(_generate(measurements)))

    assert plain, f"{label}: たたみ出し無しでもダーツが出ず、テストが空振りしています"
    assert len(trued) == len(plain), f"{label}: ダーツの本数が変わりました"
    # 許容は0.01cm(0.1mm)。型紙の線の太さより細かい。
    #
    # 厳密に一致はしない: たたみ出しで輪郭が変わるので、その後に掛かる
    # ウエスト絞りの計算にごく小さな差が出る(実測の最大 0.0007cm＝7ミクロン)。
    # 「先端は動かない」と言えるかを見たいので、その桁で見る。
    for before, after in zip(plain, trued):
        assert math.dist(before, after) < 0.01, (
            f"{label}: たたみ出しで先端が {math.dist(before, after):.4f}cm 動きました")


def test_the_dart_tip_stops_short_of_the_bust_point():
    """先端がBPの手前で止まっていること(標準体型・ダーツ1本の場合)。

    先端をBPまで刺すと、そこに角(とんがり)ができる。洋裁の定石は
    2〜3cm手前で止めること(round28)。ここはその定石が生きていることの
    確認で、たたみ出しはこの距離を変えない(上のテストが見張っている)。
    """
    result = _generate(BODIES[1][1])
    front = [p for p in result.finalized_parts if p.part_type == "front_bodice"][0]
    bust_points = [line for name, line in front.reference_lines if name == "BP"]
    assert bust_points, "BPの基準線が無く、テストが空振りしています"
    darts = _darts_of(front)
    assert darts, "ダーツが無く、テストが空振りしています"
    for _mouth_a, tip, _mouth_b in darts:
        nearest = min(
            math.dist(tip, (sum(x for x, _ in line) / len(line), line[0][1]))
            for line in bust_points)
        assert 1.5 <= nearest <= 4.5, f"先端からBPまで {nearest:.2f}cm"


# --- 5. たたみ出しそのものの性質 --------------------------------------------

def test_equalise_legs_moves_each_side_by_the_same_small_amount():
    """仕上げの揃え直しが、**いちばん動かさずに**揃えること。

    ここは、たたみ出しの後に掛かる変形(ウエスト絞り・裾の開き)で
    生じた 0.14cm のずれを直すためのもの。大きく動かすと、済ませた
    丈の補正と釣り合わなくなる。
    """
    tip = (10.0, 10.0)
    mouth_a, mouth_b = (0.0, 10.0), (0.0, 16.0)      # 脚 10.0 と 11.66
    new_a, new_b = _equalise_legs(mouth_a, tip, mouth_b)
    radius = math.dist(tip, new_a)
    assert radius == pytest.approx(math.dist(tip, new_b), abs=1e-9)
    assert radius == pytest.approx((10.0 + math.dist(tip, mouth_b)) / 2.0)
    # 片方だけ大きく動かすやり方(長い方に合わせる/短い方に合わせる)では
    # ないこと。どちらの口も、差の半分しか動いていない。
    half = abs(math.dist(tip, mouth_b) - 10.0) / 2.0
    assert math.dist(mouth_a, new_a) == pytest.approx(half, abs=1e-9)
    assert math.dist(mouth_b, new_b) == pytest.approx(half, abs=1e-9)


def test_the_final_pass_runs_after_the_waist_is_nipped():
    """揃え直しが、**全ての変形が終わってから**掛かること。

    ダーツを作った直後は脚がぴったり揃う(実測 13.66678 / 13.66678)。
    そのあとのウエスト絞りが口を動かすので、先に揃えても意味が無い
    (実測で 13.57526 / 13.43760 になっていた)。
    """
    import inspect

    from engine import scaling

    source = inspect.getsource(scaling.scale_template)
    nip = source.index("_nip_waist(")
    retrue = source.index("retrue_bust_darts(")
    assert nip < retrue, "揃え直しが、ウエスト絞りより先に掛かっています"


def test_retrue_leaves_a_shape_without_darts_alone():
    """ダーツが無い輪郭には、何も起きないこと。"""
    plain = [("M", [0.0, 0.0]), ("L", [10.0, 0.0]), ("L", [10.0, 20.0]),
             ("L", [0.0, 20.0]), ("Z", [])]
    assert retrue_bust_darts(plain) is plain


def test_the_watcher_and_the_maker_share_one_number():
    """出っ張りの上限を、作る側と見張る側で**同じ値**から読むこと。

    2か所に書くと、片方だけ動かしたときに「ダーツをダーツと認識
    できない」形で静かに壊れる。
    """
    assert BUST_DART_TRUING_MAX_OFFSET_CM is C.DART_TRUING_MAX_OFFSET_CM


# --- 6. 左右のダーツが鏡像である ---------------------------------------------

@pytest.mark.parametrize("label,measurements", BODIES, ids=[b[0] for b in BODIES])
def test_the_left_and_right_darts_are_mirror_images(label, measurements):
    """左右のダーツが、中心前について鏡像であること。

    【round70まで何が起きていたか】左右の中心を、脇線セグメントの
    **終点**のxを平均して出していた。輪郭は左の脇線を下へ、右の脇線を
    上へ辿るので、終点は左が「ウエスト側」・右が「脇の下側」である。
    脇線は裾へ向かって開くので、この2点は鏡像ではない。ずれた中心を
    基準にBPを置くと、**左右のダーツが違う方向を向く**。

        実測(バスト84・ウエスト60・ヒップ150):
            左の先端 x= 7.39 / 右 x=30.09
            正しい鏡像なら 右は 38.61 ——8.5cmずれていた
        標準体型(B88)でも0.67cmずれていた。

    体は左右対称なのに、同じ服の左右で違う型紙になっていた。
    """
    result = _generate(measurements)
    front = [p for p in result.finalized_parts
             if p.part_type == "front_bodice"][0]
    points = C._closed_points(front.stitch_line)
    underarm = C.underarm_y_of(front)
    # 中心は「脇の下の高さでの左右の脇線の中点」。裾は開いているので、
    # 外接矩形の中点では測れない。
    at_underarm = [q[0] for q in points if abs(q[1] - underarm) < 1e-6]
    center = (min(at_underarm) + max(at_underarm)) / 2.0

    tips = sorted(t[0] for _a, t, _b in _darts_of(front))
    assert len(tips) >= 2 and len(tips) % 2 == 0, f"{label}: {tips}"
    for near, far in zip(tips, reversed(tips)):
        assert (near + far) / 2.0 == pytest.approx(center, abs=1e-6), (
            f"{label}: 先端 {near:.2f} と {far:.2f} の中点が {center:.2f} と "
            f"{abs((near + far) / 2.0 - center):.3f}cm ずれています")


@pytest.mark.parametrize("label,measurements", BODIES, ids=[b[0] for b in BODIES])
def test_the_left_and_right_dart_mouths_are_mirror_images_too(label, measurements):
    """口の位置も鏡像であること(先端だけ合わせて満足しない)。"""
    result = _generate(measurements)
    front = [p for p in result.finalized_parts
             if p.part_type == "front_bodice"][0]
    points = C._closed_points(front.stitch_line)
    underarm = C.underarm_y_of(front)
    at_underarm = [q[0] for q in points if abs(q[1] - underarm) < 1e-6]
    center = (min(at_underarm) + max(at_underarm)) / 2.0

    mouths = sorted((round(a[1], 6), a[0]) for a, _t, _b in _darts_of(front))
    mouths += sorted((round(b[1], 6), b[0]) for _a, _t, b in _darts_of(front))
    by_height: dict[float, list[float]] = {}
    for height, x in mouths:
        by_height.setdefault(height, []).append(x)
    assert by_height, f"{label}: ダーツが無く、テストが空振りしています"
    for height, row in by_height.items():
        assert len(row) == 2, f"{label}: 高さ{height}に口が{len(row)}個"
        assert sum(row) / 2.0 == pytest.approx(center, abs=1e-6), (
            f"{label}: 高さ{height}の口が左右非対称です {row}")


# --- 7. 揃えても、摘み量が痩せない ------------------------------------------

@pytest.mark.parametrize("label,measurements", BODIES, ids=[b[0] for b in BODIES])
def test_equalising_does_not_shrink_the_dart_intake(label, measurements,
                                                    monkeypatch):
    """脚を揃えても、摘み量(口の開き)が痩せないこと。

    【なぜ痩せるか】`_equalise_legs`は口を「先端から同じ距離」へ寄せる。
    長い方は縮み短い方は伸びるが、寄せる先が2本の平均なので、出来上がりの
    口は元より少し狭くなる。実測(B88): 狙い5.50cmに対し**5.15cm**——
    0.35cm(6%)足りなかった。摘み量は新文化式の角度式から決めた値なので、
    勝手に減らしてはいけない(胸の丸みがその分足りなくなる)。

    `_bust_dart_notch`は、狭くなる分だけ先に広げておく(作って測って直すを
    3回)。**広げる処理を止めた型紙と突き合わせて**、効いていることを見る
    ——式を写して比べると、式を変えたときに両方を同じ間違いへ揃えて
    しまうので、そうしない。

    摘み量は「口を閉じたときに消える布の幅」＝**口の2点の距離**であって、
    縦の差ではない。脚を揃えると口は脇線から外れるので、縦で測ると
    小さく出る。
    """
    import engine.darts as darts_module

    def _intake_total(result):
        front = [p for p in result.finalized_parts
                 if p.part_type == "front_bodice"][0]
        points = C._closed_points(front.stitch_line)
        xs = [q[0] for q in points]
        center = (min(xs) + max(xs)) / 2.0
        return sum(math.dist(a, b) for a, _t, b in _darts_of(front)
                   if a[0] < center)

    with_fix = _intake_total(_generate(measurements))
    assert with_fix > 0, f"{label}: ダーツが無く、テストが空振りしています"

    # 広げる処理だけを止める(揃える処理はそのまま)。
    monkeypatch.setattr(darts_module, "_realised_mouth_cm",
                        lambda span, *a, **k: span)
    without_fix = _intake_total(_generate(measurements))

    assert with_fix > without_fix + 0.1, (
        f"{label}: 広げる処理を止めても摘み量が {without_fix:.3f}→{with_fix:.3f} "
        f"としか変わらず、効いているか分かりません")
    # 痩せていた量は実測で6%前後。桁が合っていることも見る。
    assert (with_fix - without_fix) / with_fix < 0.20, (with_fix, without_fix)

def test_the_intake_compensation_actually_moves_the_number():
    """狭くなる分を先に広げる処理が、本当に効いていること。

    処理を外すと摘み量が痩せる、という形で確かめる(空振りしない)。
    """
    from math import hypot

    from engine.darts import _equalise_legs, _realised_mouth_cm

    # 脇線は x=0 の縦線、先端は右上。round71で実測した形に近い配置。
    seam_x = lambda y: 0.0
    tip_for = lambda y: (12.0, y - 5.0)
    plain = _realised_mouth_cm(5.5, 30.66, seam_x, tip_for, 20.0, 45.0)
    assert plain is not None
    # 揃えると、5.5cm 開けた口は 5.5cm より狭くなる。
    assert plain < 5.5 - 0.05, plain
    # 広げてやると 5.5cm に戻る。
    widened = _realised_mouth_cm(5.5 * 5.5 / plain, 30.66, seam_x, tip_for,
                                 20.0, 45.0)
    assert widened == pytest.approx(5.5, abs=0.1)
