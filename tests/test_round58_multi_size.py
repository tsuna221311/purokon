"""round58: サイズ展開モードが、設定を8つ黙って捨てていた。

round52(イラスト)・round55(手動)・round57(イラスト、再び)と、
**同じ形の取り落としを3回**直してきた。4回目がここにあった。

画面のフォームはモードを変えても同じものが出ている。同じ値を入れて
モードだけ「サイズ展開」に変えて生成した実測:

    設定              手動モード          サイズ展開モード
    用紙 A3           A3・12枚            A4・23枚
    着丈 45cm         前身頃 49.6cm       65.2cm(無視)
    袖丈 30cm         当たっている        無視
    原型「子ども」     子ども式で製図       大人式(注記も出ない)
    収縮率 5%         「買うのは70cm」     一般論の注記だけ
    一方方向の生地     「一方方向として配置」 記載なし
    柄リピート 20cm   「最大20cmずらす」   余分 0cm
    白紙の面を印刷     —                   無視

警告も注記も出ない。`generate_multi_size`が**受け取る口を持っていない**
だけで、その先の`_build_from_spec`は最初から全部受け取れた。

3回直して4回目が出たので、このラウンドでは個別の穴を塞ぐだけでなく、
**署名そのものを突き合わせるテスト**を置いた
(`test_every_entry_point_accepts_the_same_settings`)。新しい設定を
1つの経路にだけ足すと、そこで落ちる。

ついでに見つけたもの: round57が足した「生地ぜんぶを1本にしたPDF」が
ZIPの中で **S/S_all_fabrics_pdf.pdf** という名前になっていた
(内部のキー名が拡張子の前にそのまま出ていた)。
"""

import inspect
import json
import zipfile

import pytest

import app as app_module
from engine.measurements import Measurements
from engine.pdf_export import _BUNDLE_NAME_SUFFIX, export_multi_size_bundle
from engine.pipeline import (PatternForgePipeline, _closed_points_from_segments,
                              _x_span_at_y, build_garment_spec)


MEAS = Measurements(bust=84, waist=68, hip=92, height=160,
                    sleeve_length=54, shoulder_width=37)
FORM = {"bust": "84", "waist": "68", "hip": "92", "height": "160",
        "sleeve_length": "54", "shoulder_width": "37",
        "neckline": "round_neck", "sleeve_style": "straight", "skirt_style": "flare"}


def _spec():
    return build_garment_spec(neckline="round_neck", sleeve_style="straight",
                              skirt_style="flare")


def _multi(tmp_path, **kwargs):
    return PatternForgePipeline(output_dir=str(tmp_path)).generate_multi_size(
        _spec(), MEAS, ["S", "M"], **kwargs)


def _width_of(result, part_type):
    parts = [p for p in result.finalized_parts if p.part_type == part_type]
    assert parts, part_type
    xs = [x for p in parts for x, _y in p.stitch_line]
    return max(xs) - min(xs)


def _height_of(result, part_type):
    parts = [p for p in result.finalized_parts if p.part_type == part_type]
    assert parts, part_type
    ys = [y for p in parts for _x, y in p.stitch_line]
    return max(ys) - min(ys)


# ---------------------------------------------------------------------------
# 1. 署名の突き合わせ — これが「4回目」を最後にするための見張り
# ---------------------------------------------------------------------------

def test_every_entry_point_accepts_the_same_settings():
    """3つの入口が、同じ設定を受け取れること。

    round57はイラストと手動の2つだけを見ていた。サイズ展開が抜けていて、
    そこに8件たまっていた。**入口を数え上げて全部を突き合わせる**形にする。

    各入口にしか無くて当然のものだけを、理由を書いて除外する。
    「今は渡していないから」は理由にならない——それがこのテストで
    見つけたいものなので、除外に足してはいけない。
    """
    def params(name):
        return set(inspect.signature(getattr(PatternForgePipeline, name)).parameters)

    manual = params("generate_from_selection")
    illustration = params("generate_from_illustration")
    multi = params("generate_multi_size")

    # 入口の形そのもの(何を入力として受け取るか)。設定ではない。
    SHAPE = {
        "self", "garment_spec", "measurements",   # 手動: パーツ構成と採寸
        "image", "views",                          # イラスト: 絵そのもの
        "base_measurements", "sizes", "custom_grade_cm",  # サイズ展開: 展開の仕方
        "skip_export",   # テスト用に書き出しを省く内部向けの口
        "fabric_width_candidates",
        "design",        # イラストが絵から作るもの(利用者は入力しない)
    }
    settings = (manual | illustration | multi) - SHAPE
    for name, got in (("イラスト", illustration), ("サイズ展開", multi),
                      ("手動", manual)):
        missing = sorted(settings - got)
        assert not missing, (
            f"{name}モードが受け取れない設定があります: {missing}。"
            "画面には欄が出るので、渡す口が無いと**黙って無視**されます。")


def test_multi_size_forwards_every_setting_it_accepts():
    """受け取るだけでなく、**実際に渡している**こと。

    署名だけ合わせて中で捨てる、というのが一番たちが悪い。
    `_build_from_spec`の呼び出しを構文木で見て、受け取った設定名が
    そのままキーワード引数として現れていることを確かめる。
    """
    import ast

    source = inspect.getsource(PatternForgePipeline.generate_multi_size)
    tree = ast.parse(source.lstrip())
    calls = [n for n in ast.walk(tree)
             if isinstance(n, ast.Call)
             and isinstance(n.func, ast.Attribute)
             and n.func.attr == "_build_from_spec"]
    assert len(calls) == 1, "_build_from_spec の呼び出しが1か所ではありません"
    passed = {kw.arg for kw in calls[0].keywords}

    accepted = set(inspect.signature(
        PatternForgePipeline.generate_multi_size).parameters)
    ONLY_HERE = {"self", "garment_spec", "base_measurements", "sizes",
                 "custom_grade_cm", "fabric_width_candidates"}
    dropped = sorted(accepted - ONLY_HERE - passed)
    assert not dropped, (
        f"受け取っておきながら渡していない設定があります: {dropped}")


# ---------------------------------------------------------------------------
# 2. 実際に効いていること(署名ではなく出来上がりで見る)
# ---------------------------------------------------------------------------

def test_a3_is_used_for_every_size(tmp_path):
    a4 = _multi(tmp_path / "a4")
    a3 = _multi(tmp_path / "a3", paper="a3")
    for size in ("S", "M"):
        assert a4.results[size].paper_name == "A4"
        assert a3.results[size].paper_name == "A3"
        assert a3.results[size].pdf_sheet_count() < a4.results[size].pdf_sheet_count(), (
            f"{size}: A3にしたのに枚数が減っていません")


def test_design_lengths_apply_to_every_size(tmp_path):
    plain = _multi(tmp_path / "plain")
    short = _multi(tmp_path / "short",
                   design_length_overrides={"front_bodice": 45.0,
                                             "back_bodice": 45.0,
                                             "sleeve": 30.0})
    for size in ("S", "M"):
        assert _height_of(short.results[size], "front_bodice") < \
            _height_of(plain.results[size], "front_bodice"), \
            f"{size}: 着丈の指定が効いていません"
        assert _height_of(short.results[size], "sleeve") == pytest.approx(30.0, abs=0.6), \
            f"{size}: 袖丈の指定が効いていません"


def test_design_lengths_stay_the_same_across_sizes(tmp_path):
    """丈は、サイズが変わっても指定どおりのままであること。

    「スカート丈45cm」と書いた人は出来上がりの45cmのことを言っている。
    Sだから43cmにする、という意味ではない。**身幅はサイズごとに変わる**
    ので、そこが動いていることも一緒に確かめる(丈が固定されているのが
    「グレーディングが効いていない」ではないことの裏取り)。
    """
    result = _multi(tmp_path, design_length_overrides={"front_bodice": 45.0,
                                                        "back_bodice": 45.0})
    # 後身頃は指定の45cmちょうどで出る。
    heights = {s: _height_of(r, "back_bodice") for s, r in result.results.items()}
    for size, height in heights.items():
        assert height == pytest.approx(45.0, abs=0.05), \
            f"{size}: 丈が指定どおりではありません: {heights}"

    # 前身頃だけは、胸のダーツぶん**型紙が長く出る**(round57の開示のとおり)。
    # ダーツの量はバストで決まるので、この差はサイズごとに違って正しい。
    # 「丈が固定されている」ことと矛盾しないことを、ダーツ量と突き合わせる。
    for size, one in result.results.items():
        dart = [p.bust_dart_shift_cm for p in one.scaled_parts
                if p.part_type == "front_bodice"][0]
        assert _height_of(one, "front_bodice") == pytest.approx(45.0 + dart, abs=0.1), \
            f"{size}: 前身頃の長さがダーツぶんで説明できません"
        assert any("ダーツぶん" in n for n in one.design_notes), \
            f"{size}: ダーツぶん長く出ることが書かれていません"

    def width_of(r):
        parts = [p for p in r.finalized_parts if p.part_type == "front_bodice"]
        xs = [x for p in parts for x, _y in p.stitch_line]
        return max(xs) - min(xs)
    widths = {s: width_of(r) for s, r in result.results.items()}
    assert widths["S"] < widths["M"], f"身幅が変わっていません: {widths}"


def test_the_block_choice_reaches_every_size(tmp_path):
    adult = _multi(tmp_path / "adult")
    child = _multi(tmp_path / "child", block_key="child")
    for size in ("S", "M"):
        assert not any("子ども" in n for n in adult.results[size].design_notes)
        assert any("子ども" in n for n in child.results[size].design_notes), \
            f"{size}: 原型の選択が効いていません"


def test_shrink_and_one_way_and_repeat_reach_every_size(tmp_path):
    plain = _multi(tmp_path / "plain")
    dressed = _multi(tmp_path / "dressed", one_way_fabric=True,
                     shrink_percent=5.0, pattern_repeat_cm=20.0)
    for size in ("S", "M"):
        plain_notes = " ".join(plain.results[size].shopping_list.notes)
        notes = " ".join(dressed.results[size].shopping_list.notes)
        assert "収縮率5%" in notes, f"{size}: 収縮率が効いていません"
        assert "一方方向の生地" in notes, f"{size}: 一方方向の指定が効いていません"
        assert "収縮率5%" not in plain_notes
        assert dressed.results[size].shopping_list.pattern_repeat_extra_cm, \
            f"{size}: 柄のリピートが効いていません"


def test_alterations_reach_every_size(tmp_path):
    """胸まわりの補正が、どのサイズにも指定どおりの量で効くこと。

    幅は**胸の高さで**測る(round40と同じ)。輪郭の最大幅は袖ぐり付近で
    決まるので、そこを見ても胸の補正は現れない——最初にそう測って
    「効いていない」と読み違えた。
    """
    def bust_width(result):
        scaled = next(s for s in result.scaled_parts
                      if s.part_type == "front_bodice")
        span = _x_span_at_y(_closed_points_from_segments(scaled.segments),
                            scaled.bust_line_y_cm)
        return span[1] - span[0]

    plain = _multi(tmp_path / "plain")
    fixed = _multi(tmp_path / "fixed", alterations={"bust_width": 4.0})
    for size in ("S", "M"):
        # 一周4cmの不足を脇4本で分けるので、前身頃1枚では左右合わせて2cm。
        assert bust_width(fixed.results[size]) - bust_width(plain.results[size]) \
            == pytest.approx(2.0, abs=0.05), f"{size}: 補正が効いていません"
        assert any("胸まわりを4cm補正" in n
                   for n in fixed.results[size].design_notes), \
            f"{size}: 補正したことが書かれていません"


def test_lining_is_drawn_for_every_size(tmp_path):
    """round49は「サイズ展開では裏地を引きません」と断っていた。

    断っていた理由は`generate_multi_size`がliningを受け取らなかったこと
    だけで、その先は最初から引けた。裏地付きの衣装をS/M/Lでまとめて
    作れるようになった。
    """
    result = _multi(tmp_path, lining=True)
    for size in ("S", "M"):
        assert result.results[size].lining_parts, f"{size}: 裏地が出ていません"


def test_empty_tiles_can_be_printed_for_every_size(tmp_path):
    off = _multi(tmp_path / "off")
    on = _multi(tmp_path / "on", include_empty_tiles=True)
    for size in ("S", "M"):
        assert on.results[size].pdf_sheet_count() >= off.results[size].pdf_sheet_count()
    assert any(on.results[s].pdf_sheet_count() > off.results[s].pdf_sheet_count()
               for s in ("S", "M")), "白紙を印刷する指定が、どのサイズでも効いていません"


# ---------------------------------------------------------------------------
# 3. 画面(HTTP)から見たときの姿
# ---------------------------------------------------------------------------

def test_the_form_settings_reach_multi_size_over_http(client):
    data = dict(FORM, mode="multi_size", sizes=["S", "M"], paper="a3",
                length_front_bodice="45", length_sleeve="30",
                block="child", one_way_fabric="on", shrink_percent="5",
                pattern_repeat_cm="20", lining="on",
                custom_panels_json="[]")
    response = client.post("/api/generate", data=data)
    assert response.status_code == 200, response.get_json().get("error")
    body = response.get_json()
    for size in ("S", "M"):
        one = body["results"][size]
        assert one["paper"] == "A3", f"{size}: 用紙が効いていません"
        assert one["lining"], f"{size}: 裏地が効いていません"
        assert any("子ども" in n for n in one["design_notes"]), \
            f"{size}: 原型が効いていません"


def test_the_screen_says_lengths_do_not_change_with_size(client):
    """丈を固定したことを、黙ってやらない。"""
    data = dict(FORM, mode="multi_size", sizes=["S", "M"],
                length_front_bodice="45", custom_panels_json="[]")
    body = client.post("/api/generate", data=data).get_json()
    assert body["ok"], body.get("error")
    joined = " ".join(body["design_notes"])
    assert "着丈45cm" in joined and "どのサイズでも" in joined, \
        f"丈を固定したことが画面に出ていません: {body['design_notes']}"


def test_the_screen_no_longer_says_lining_is_unavailable(client):
    data = dict(FORM, mode="multi_size", sizes=["S"], lining="on",
                custom_panels_json="[]")
    body = client.post("/api/generate", data=data).get_json()
    assert body["ok"], body.get("error")
    joined = " ".join(body["design_notes"])
    assert "裏地の型紙は引いていません" not in joined
    assert body["results"]["S"]["lining"], "裏地が引かれていません"


def test_the_lining_section_is_no_longer_hidden_in_multi_size():
    """画面側でも、裏地の欄がサイズ展開で消えないこと。

    round49は「押せるのに効かない」を無くすために節ごと隠していた。
    効くようになったので、隠す側のコードが残っていないことを見る。
    """
    source = (app_module.app.root_path and
              open("web/static/app.js", encoding="utf-8").read())
    assert "liningSection.classList.toggle" not in source, \
        "裏地の節をモードで隠すコードが残っています"


def test_multi_size_settings_survive_regeneration(client):
    client.post("/signup", data={"email": "ms-regen@example.com",
                                 "password": "test-password-1234",
                                 "password_confirm": "test-password-1234"},
                follow_redirects=True)
    data = dict(FORM, mode="multi_size", sizes=["S", "M"], paper="a3",
                length_front_bodice="45", block="child", lining="on",
                one_way_fabric="on", custom_panels_json="[]")
    first = client.post("/api/generate", data=data)
    assert first.status_code == 200, first.get_json().get("error")
    bundle_job_id = first.get_json()["bundle_job_id"]

    with app_module.db._connect() as conn:
        row = conn.execute("SELECT spec_json FROM jobs WHERE job_id = ?",
                            (bundle_job_id,)).fetchone()
    saved = json.loads(row[0])["multi_size_kwargs"]
    for key, value in (("paper", "a3"), ("block_key", "child"),
                       ("lining", True), ("one_way_fabric", True)):
        assert saved.get(key) == value, \
            f"再生成に引き継がれない設定があります: {key}={saved.get(key)}"
    assert saved.get("design_length_overrides", {}).get("front_bodice") == 45.0


def test_the_saved_kwargs_are_the_ones_that_were_used():
    """保存する辞書と、生成に渡す辞書が同じものであること(round55と同じ形)。

    以前は6件を手で並べ直して保存していたので、渡す側が増えても
    保存側は増えなかった。構文木で「同じ変数を展開している」ことを見る。
    """
    import ast

    tree = ast.parse(open("app.py", encoding="utf-8").read())
    found = False
    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        for key, value in zip(node.keys, node.values):
            if isinstance(key, ast.Constant) and key.value == "multi_size_kwargs":
                assert isinstance(value, ast.Dict), \
                    "multi_size_kwargs を手で並べ直しています"
                assert any(k is None for k in value.keys), \
                    "multi_size_kwargs が `**` で展開されていません"
                found = True
    assert found, "multi_size_kwargs の保存箇所が見つかりません"


# ---------------------------------------------------------------------------
# 4. ZIPの中の名前
# ---------------------------------------------------------------------------

def test_the_combined_pdf_has_a_readable_name_in_the_zip(tmp_path):
    result = _multi(tmp_path, fabric_group_assignments={"sleeve": "紺サテン"})
    with zipfile.ZipFile(result.zip_path) as bundle:
        names = bundle.namelist()
    assert "S/S_all_fabrics.pdf" in names, names
    assert not any("_pdf.pdf" in n for n in names), \
        f"内部のキー名がファイル名に出ています: {names}"


def test_an_unregistered_format_stops_instead_of_inventing_a_name(tmp_path):
    """名前が決まっていない形式は、変な名前を作らずに止まること。

    round49の見張りは**衝突**しか見ていなかったので、
    `S_all_fabrics_pdf.pdf`は素通りしていた。
    """
    source = tmp_path / "x.pdf"
    source.write_bytes(b"%PDF-1.4\n")
    with pytest.raises(ValueError, match="名前が決まっていない"):
        export_multi_size_bundle({"S": {"brand_new_format": str(source)}},
                                  str(tmp_path), "bundle")


def test_every_exported_format_has_a_name_in_the_bundle(tmp_path):
    """実際に書き出される形式が、全部ZIPの名前表に載っていること。"""
    # 任意の機能を全部入れて、出る形式を最大にする。
    # (最初は裏地を入れずに測って、裏地の名前が抜けているのを
    #  見つけられなかった——出ない形式は数えようがない)
    result = PatternForgePipeline(output_dir=str(tmp_path)).generate_from_selection(
        _spec(), MEAS, fabric_group_assignments={"sleeve": "紺サテン"},
        lining=True)
    assert any(k.startswith("lining_") for k in result.output_files)
    assert any(k.startswith("fabric2_") for k in result.output_files)
    assert "all_fabrics_pdf" in result.output_files
    missing = sorted(set(result.output_files) - set(_BUNDLE_NAME_SUFFIX))
    assert not missing, (
        f"ZIPでの名前が決まっていない形式があります: {missing}。"
        "engine/pdf_export.py の _BUNDLE_NAME_SUFFIX に足してください。")


# ---------------------------------------------------------------------------
# 5. 「引き継いだ設定」が、設定の増加に追いつくこと
# ---------------------------------------------------------------------------

def test_every_setting_shows_up_in_the_restored_summary():
    """再生成の「引き継いだ設定」が、設定を1つも取りこぼさないこと。

    round57がこの1行を作ったとき、原型・収縮率・柄のリピートは
    書き忘れられていた。設定が増えるたびにここも増やす必要があるので、
    **設定の一覧の方から**確かめる。

    ここで見ているのは「その設定の名前が文に出ること」だけで、
    値の正しさは上の再生成テストが見ている。
    """
    describe = app_module._describe_restored_settings
    # 既定以外の値を入れたら、必ず文に出てほしいもの。
    # (値, 文に出てほしい語) の組。
    CASES = {
        "lining": (True, "裏地"),
        "fabric_group_assignments": ({"sleeve": "紺サテン"}, "紺サテン"),
        "design_length_overrides": ({"skirt": 45.0}, "45"),
        "alterations": ({"bust_width": 2.0}, "補正"),
        "fit": ("loose", "ゆとり"),
        "one_way_fabric": (True, "一方方向"),
        "block_key": ("child", "子ども"),
        "shrink_percent": (5.0, "収縮率"),
        "pattern_repeat_cm": (20.0, "リピート"),
        "include_empty_tiles": (True, "白紙"),
        "paper": ("a3", "A3"),
        "seam_allowance_cm": (2.0, "縫い代"),
        # round74: 重ね着の前提。これが落ちると、コートが中に着る服と
        # 同じ太さで再生成される。
        "worn_over_bust_cm": (90.0, "羽織る"),
        # round76: ドロップショルダー。落ちると肩の形が黙って
        # セットインスリーブに戻る。
        "shoulder_drop_cm": (5.0, "ドロップショルダー"),
    }
    # 設定として扱わないもの(出来上がりに出ない/内部の都合)。
    NOT_A_SETTING = {"allow_rotation", "hem_seam_allowance_cm",
                     "custom_grade_cm", "skip_export", "garment_spec",
                     "measurements", "fabric_width_candidates", "self",
                     "image", "views", "design", "base_measurements", "sizes",
                     # round74: 「中の服に袖があるか」は、それ単体では何も
                     # 決めない——`worn_over_bust_cm`と組んで初めて足す量が
                     # 変わる。単体で説明文に出しても意味が無いので、ここでは
                     # 対象外にし、組んだときに出ることは
                     # tests/test_round74_layering.py で見ている。
                     "worn_over_has_sleeves"}

    accepted = set(inspect.signature(
        PatternForgePipeline.generate_from_selection).parameters)
    uncovered = sorted(accepted - NOT_A_SETTING - set(CASES))
    assert not uncovered, (
        f"再生成の説明文に出るかどうかを決めていない設定があります: {uncovered}。"
        "app.py の _describe_restored_settings に足してから、"
        "このテストの CASES にも足してください。")

    for key, (value, expected) in CASES.items():
        text = describe({key: value})
        assert expected in text, (
            f"{key} を設定しても「引き継いだ設定」に出ません: {text}")

    assert "既定のまま" in describe({})


# ---------------------------------------------------------------------------
# 6. サイズ展開の画面から、作った型紙が全部取れること
# ---------------------------------------------------------------------------

def test_the_multi_size_download_row_is_built_from_the_response():
    """サイズ展開のダウンロード行が、形式を直書きしていないこと。

    【実測した状態】ここには SVG/PDF/DXF の3本が直書きされていた。
    裏地あり・生地2種類で生成すると、1サイズにつき応答には13本の
    リンクが入っているのに、画面に出るのは3本だった
    (`scripts/audit_multi_size_downloads.py` で実測)。
    生地を分ける機能はround55からサイズ展開で動いていたので、
    **2色目の型紙は3ラウンド分、画面から取れなかった**。

    リンクの組み立ては応答の鍵から行う。ここではその形を固定する
    (実際に何本出るかは上の監査スクリプトが画面で測る)。
    """
    source = open("web/static/app.js", encoding="utf-8").read()
    assert "function downloadLinksForSize(" in source
    body = source.split("function downloadLinksForSize(")[1].split("\n}\n")[0]
    for key in ("lining_pdf", "all_fabrics_pdf", "projector"):
        assert key in body, f"{key} が組み立てに入っていません"
    # 無い形式のリンクは作らない(押して404にしない)。
    assert "if (download[key])" in body

    multi = source.split("function renderMultiSizeResults(")[1]
    assert "downloadLinksForSize(result)" in multi
    assert 'result.download.svg' not in multi, \
        "サイズ展開の画面に、形式が直書きで残っています"


# ---------------------------------------------------------------------------
# 7. 手持ちの生地の判定が、サイズ展開にも届くこと
# ---------------------------------------------------------------------------

def test_the_stash_check_runs_for_every_size(client):
    """手持ちの生地で足りるかを、サイズごとに答えること。

    【実測した状態】手持ちの欄は「⑤生地の配置設定」の中にあり、
    どのモードでも出ている。それなのに判定していたのは手動モードだけで、
    サイズ展開では `stash_verdict` が null のまま返っていた——
    画面にも何も出ないので、入れた値がどこへ行ったのか分からない。
    """
    data = dict(FORM, mode="multi_size", sizes=["S", "M"],
                stash_width_cm="110", stash_length_cm="130",
                custom_panels_json="[]")
    body = client.post("/api/generate", data=data).get_json()
    assert body["ok"], body.get("error")
    for size in ("S", "M"):
        verdict = body["results"][size].get("stash_verdict")
        assert verdict, f"{size}: 手持ちの判定が出ていません"
        assert verdict["have_width_cm"] == 110.0
        assert verdict["needed_length_cm"] > 0


def test_the_stash_verdict_is_measured_on_that_size(client):
    """判定が、そのサイズの型紙で測られていること。

    全サイズに同じ答えを返すなら、判定していないのと変わらない。
    小さいサイズの方が短くて済むはずである。
    """
    data = dict(FORM, mode="multi_size", sizes=["S", "L"],
                stash_width_cm="110", stash_length_cm="400",
                custom_panels_json="[]")
    body = client.post("/api/generate", data=data).get_json()
    assert body["ok"], body.get("error")
    small = body["results"]["S"]["stash_verdict"]["needed_length_cm"]
    large = body["results"]["L"]["stash_verdict"]["needed_length_cm"]
    assert small < large, f"サイズで必要量が変わっていません: S={small} L={large}"


def test_the_screen_shows_the_stash_verdict_for_each_size():
    """サイズごとの手持ち判定を、画面が読んで描いていること。

    最初は `"result.stash_verdict" in multi` とだけ書いたが、これは
    `result.stash_verdicts_by_fabric` の**一部分**にも当たるので、
    判定を描くのをやめても落ちなかった(ミューテーションで発覚)。
    round56に踏んだ「別の文字列に当たっていた」と同じ形である。
    読み取っている行そのものを見る。
    """
    source = open("web/static/app.js", encoding="utf-8").read()
    multi = source.split("function renderMultiSizeResults(")[1]
    assert "const stash = result.stash_verdict;" in multi, \
        "サイズごとの手持ち判定を読んでいません"
    assert "result.stash_verdicts_by_fabric" in multi, \
        "生地ごとの判定を読んでいません"
    # 読むだけで描かなければ意味が無いので、描いている先も見る。
    assert "box.appendChild(line)" in multi


# ---------------------------------------------------------------------------
# 8. B2B API が、画面と同じ欄を読むこと
# ---------------------------------------------------------------------------

def test_the_b2b_api_reads_the_same_fields_as_the_browser_form():
    """`/api/v1/generate` が、画面のフォームと同じ欄を読むこと。

    このAPIのdocstringは「リクエストボディは`/api/generate`と同じ
    フォームフィールドを受け付ける」と約束している。round41に1度
    取りこぼしを直したのに、その後に増えた欄がまた落ちていた——
    ゆとり(round24)・切り替え線(round30)・用紙(round57)・
    白紙の面(round57)の4つは、送っても効かなかった。

    ここでは**読んでいるフォーム欄の名前**を構文木で数え上げて比べる。
    """
    import ast

    tree = ast.parse(open("app.py", encoding="utf-8").read())
    handlers = {node.name: node for node in ast.walk(tree)
                if isinstance(node, ast.FunctionDef)
                and node.name in ("api_generate", "api_v1_generate")}
    assert len(handlers) == 2, sorted(handlers)

    def form_fields(node):
        """その関数が読んでいる `request.form` の欄名。"""
        names = set()
        for child in ast.walk(node):
            if isinstance(child, ast.Constant) and isinstance(child.value, str):
                continue
            if isinstance(child, ast.Call):
                # request.form.get("x") / _bool_field(request.form, "x")
                args = child.args
                if (isinstance(child.func, ast.Attribute)
                        and child.func.attr in ("get", "getlist")
                        and args and isinstance(args[0], ast.Constant)):
                    names.add(args[0].value)
                elif (isinstance(child.func, ast.Name)
                      and child.func.id == "_bool_field"
                      and len(args) >= 2 and isinstance(args[1], ast.Constant)):
                    names.add(args[1].value)
            if isinstance(child, ast.Subscript) and isinstance(child.slice, ast.Constant):
                pass
        return names

    browser = form_fields(handlers["api_generate"])
    api = form_fields(handlers["api_v1_generate"])
    # 画面だけのもの(このAPIが対応しないと明記しているモード・入力)。
    ONLY_BROWSER = {
        "mode",                    # イラスト/サイズ展開はこのAPIの対象外
        "sizes", "illustration", "illustration_back",
        "custom_panels_json",      # 自由形状パーツも対象外
        "csrf_token",              # Cookie認証ではないので要らない
    }
    missing = sorted(browser - api - ONLY_BROWSER)
    assert not missing, (
        f"B2B APIが読んでいないフォーム欄があります: {missing}。"
        "docstringは「同じフォームフィールドを受け付ける」と約束しています。")


def test_the_b2b_api_actually_applies_the_new_fields(client):
    import re

    client.post("/signup", data={"email": "b2b58@example.com",
                                 "password": "test-password-1234",
                                 "password_confirm": "test-password-1234"},
                follow_redirects=True)
    raw_key = client.post("/account/api-keys", data={"label": "round58"},
                          follow_redirects=True)
    # 鍵の生の値は作成直後の画面にしか出ないので、そこから拾う。
    match = re.search(r"pf_(?:live|test)_[A-Za-z0-9_\-]+",
                      raw_key.get_data(as_text=True))
    assert match, "APIキーが画面に出ていません"
    key = match.group(0)

    response = client.post("/api/v1/generate",
                            data=dict(FORM, paper="a3"),
                            headers={"Authorization": f"Bearer {key}"})
    assert response.status_code == 200, response.get_json()
    assert response.get_json()["paper"] == "A3"
