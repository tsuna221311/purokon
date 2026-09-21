"""round34: 画面を見て回って直したUI/UXと、その再発防止。

round32は「壊れているところ」を直した。今回は**壊れてはいないが、
使う人の役に立っていないところ**を直した:

1. 1440px幅で画面の右半分がずっと空白だった -> 採寸図
2. 形を文字のプルダウンで選んでいた -> 実際の型紙の輪郭のサムネイル
3. 結果の先頭がエンジン側の指標だった -> 「幅○cmの生地を△m」
4. 色の役割が分かれていなかった -> ヘッダーの色と操作の色を分ける
"""

import html as html_mod
import json
import pathlib
import re

import pytest

WEB_DIR = pathlib.Path(__file__).resolve().parent.parent / "web"
THUMB_DIR = WEB_DIR / "static" / "thumbs"


def _valid_form(**overrides):
    form = {
        "bust": "84", "waist": "68", "hip": "92", "height": "160",
        "sleeve_length": "54", "shoulder_width": "37",
        "mode": "manual", "neckline": "round_neck",
        "sleeve_style": "straight", "skirt_style": "flare",
    }
    form.update(overrides)
    return form


# --- 1) 採寸図 ---------------------------------------------------------------

def test_the_page_carries_the_measuring_figure(client):
    """生成前の画面に採寸図があり、全項目の線が引かれていること。

    【なぜ必要か】1440px幅で画面のほぼ半分が、生成するまで空白だった。
    一方で採寸ミスはこのサービスがうまくいかない最大の原因で、round33で
    足したのは「入れた値が辻褄に合わない」という**事後の指摘**だけ。
    正しく測る手助けは何もしていなかった。
    """
    from engine.measure_guide import MEASURE_ORDER

    html = client.get("/").get_data(as_text=True)
    assert 'id="measure-figure"' in html
    for field in MEASURE_ORDER:
        assert f'data-measure="{field}"' in html, field


def test_every_measurement_field_has_a_how_to(client):
    """全採寸項目に、測り方の説明があること(空欄が無いこと)。"""
    from engine.measure_guide import MEASURE_ORDER, MEASURE_GUIDES

    for field in MEASURE_ORDER:
        guide = MEASURE_GUIDES[field]
        assert guide.label and len(guide.how) > 10, field


def test_the_shoulder_guide_warns_about_the_common_mistake():
    """肩幅の説明が、よくある取り違えに触れていること。

    round33の指摘文で「腕の付け根から付け根まで、ではありません」と
    わざわざ否定する羽目になっていた原因そのもの。
    """
    from engine.measure_guide import MEASURE_GUIDES

    guide = MEASURE_GUIDES["shoulder_width"]
    assert "肩先" in guide.how
    assert "腕の付け根" in guide.caution


def test_the_guides_reach_the_page_as_data(client):
    """説明文がページに埋め込まれ、JSから読めること(CSP対応の受け渡し)。"""
    html = client.get("/").get_data(as_text=True)
    match = re.search(r"data-measure-guides='([^']+)'", html)
    assert match, "採寸図に説明文が渡されていない"
    # 属性値はJinjaがHTMLエスケープするので、戻してから読む
    # (ブラウザは自動で戻すため、実際のJSでは素のJSONが渡る)。
    guides = json.loads(html_mod.unescape(match.group(1)))
    assert guides["shoulder_width"]["label"] == "肩幅"
    js = (WEB_DIR / "static" / "app.js").read_text(encoding="utf-8")
    assert "measureGuides" in js and "setupMeasureFigure" in js


def test_the_figure_moves_next_to_the_fields_on_narrow_screens(client):
    """狭い画面用に、採寸欄のすぐ下へ移す仕掛けがあること。

    図は右のパネルにあるが、1列に積まれるスマホではフォーム全体の下に
    来てしまい、実測で採寸欄から2500px離れていた。測りながら見る図が
    そこにあっても役に立たない。
    """
    html = client.get("/").get_data(as_text=True)
    assert 'id="measure-figure-slot"' in html
    js = (WEB_DIR / "static" / "app.js").read_text(encoding="utf-8")
    assert "placeMeasureFigure" in js and "min-width: 1000px" in js


# --- 2) 形をサムネイルで選ぶ --------------------------------------------------

@pytest.mark.parametrize("kind,part_type", [
    ("neckline", "front_bodice"), ("sleeve", "sleeve"), ("skirt", "skirt"),
])
def test_every_style_has_a_thumbnail(kind, part_type):
    """選べる形すべてに、サムネイルのファイルがあること。

    1つ欠けると、その選択肢だけ画像が割れる。テンプレートを増やしたのに
    サムネイルを作り直し忘れる、が起こりうるのでここで固定する。
    """
    from engine.templates_db import TemplateDB

    db = TemplateDB()
    variations = {v for pt, v in db.available()
                  if pt == part_type and not v.endswith("_zip")}
    assert variations, (kind, part_type)
    for variation in variations:
        name = variation or "standard"
        path = THUMB_DIR / f"{kind}__{name}.svg"
        assert path.exists(), f"{path.name} が無い(scripts/build_style_thumbnails.py を実行)"
        assert path.stat().st_size > 100


def test_the_thumbnails_are_drawn_from_the_real_templates():
    """サムネイルが、実際の型紙の輪郭から作られていること。

    描き起こした絵にすると、テンプレートを直したときに**絵だけ黙って
    古くなる**(絵と型紙が食い違っていても誰も気づかない)。ここでは
    サムネイルの点が、テンプレートの輪郭の範囲に収まっていることを見る。
    """
    from engine.svgpath import bounding_box
    from engine.templates_db import TemplateDB

    db = TemplateDB()
    segments = db.get("skirt", "flare")
    min_x, min_y, max_x, max_y = bounding_box(segments)
    svg = (THUMB_DIR / "skirt__flare.svg").read_text(encoding="utf-8")
    coords = re.findall(r"([-\d.]+) ([-\d.]+)", svg.split('d="', 1)[1].split('"', 1)[0])
    # 直線だけのパーツ(フレアスカートは5点)もあるので、点数ではなく
    # 「テンプレートの輪郭の範囲に収まっているか」を見る。
    assert len(coords) >= 4
    for sx, sy in coords:
        assert min_x - 0.5 <= float(sx) <= max_x + 0.5
        assert min_y - 0.5 <= float(sy) <= max_y + 0.5


def test_the_picker_submits_the_same_values_as_the_old_select(client):
    """サムネイルで選んでも、サーバへ送る値は従来と同じであること。

    見た目を変えただけで、送信の中身は変えていない。
    """
    html = client.get("/").get_data(as_text=True)
    for name in ("neckline", "sleeve_style", "skirt_style"):
        assert f'<input type="radio" name="{name}"' in html
    data = client.post("/api/generate", data=_valid_form()).get_json()
    assert data["ok"] is True
    assert any(p["variation"] == "round_neck" for p in data["parts"])
    assert any(p["part_type"] == "sleeve" for p in data["parts"])


def test_choosing_no_sleeve_is_still_possible(client):
    """「なし(ノースリーブ)」が選べること(空文字のラジオ)。"""
    html = client.get("/").get_data(as_text=True)
    assert '<input type="radio" name="sleeve_style" value=""' in html
    data = client.post("/api/generate",
                       data=_valid_form(sleeve_style="")).get_json()
    assert data["ok"] is True
    assert not any(p["part_type"] == "sleeve" for p in data["parts"])


# --- 3) 結果の先頭 -----------------------------------------------------------

def test_the_result_leads_with_the_fabric_to_buy(client):
    """結果のいちばん上が「用意する生地」であること。

    round33までの先頭は パーツ数/布ロス率/使用生地丈/生地幅/処理時間/
    配置不能パーツ という6つの数値タイルで、**処理時間のようなエンジン側の
    指標**が、買い物に必要な「幅○cmの生地を△m」と同じ大きさで並んでいた。
    """
    html = client.get("/").get_data(as_text=True)
    body = html.split('id="result-content"', 1)[1]
    need = body.index("fabric-need")
    download = body.index("download-row")
    stats = body.index("stat-grid")
    assert need < download < stats, (need, download, stats)


def test_the_internal_metrics_are_still_there_just_folded(client):
    """内部指標を消してはいないこと(開けば全部見られる)。"""
    html = client.get("/").get_data(as_text=True)
    assert "result-details" in html
    for stat_id in ("stat-parts", "stat-waste", "stat-length",
                     "stat-width", "stat-time", "stat-unplaced"):
        assert f'id="{stat_id}"' in html, stat_id
    assert "詰め合わせ効果" in html


def test_the_fabric_length_is_rounded_up_never_down():
    """必要な生地の長さを、切り上げていること。

    足りない方向へ丸めてはいけない(足りなければ作れない。多い分は残る
    だけ)。丸めはJS側にあるので、その規則が消えていないかを見る。
    """
    js = (WEB_DIR / "static" / "app.js").read_text(encoding="utf-8")
    assert "renderFabricNeed" in js
    assert "Math.ceil" in js
    assert "FABRIC_ROUND_UP_CM" in js
    assert "Math.floor" not in js.split("function renderFabricNeed")[1][:800]


# --- 4) 見た目 ---------------------------------------------------------------

def test_the_header_colour_and_the_action_colour_are_different():
    """ヘッダーの色と、操作の色を別の変数にしていること。

    round33まで --accent(ほぼ黒)をヘッダー背景・主ボタン・リンク・選択状態の
    すべてに使っていたため、**いちばん押してほしい物とただの帯が同じ色**で、
    視線の順番が生まれていなかった。
    """
    css = (WEB_DIR / "static" / "style.css").read_text(encoding="utf-8")
    header = re.search(r"--header-bg:\s*([^;]+);", css)
    accent = re.search(r"--accent:\s*([^;]+);", css)
    assert header and accent
    assert header.group(1).strip() != accent.group(1).strip()
    assert "background: var(--header-bg);" in css


def test_no_developer_jargon_in_the_visible_chrome(client):
    """ヘッダー・フッターに、作り手側の呼び名が出ていないこと。"""
    html = client.get("/").get_data(as_text=True)
    for jargon in ("rectpack", "AIネスティング", "AI型紙生成支援システム"):
        assert jargon not in html, jargon


def test_focus_is_visible(client):
    """キーボードで操作したとき、どこにいるか分かる指定があること。"""
    css = (WEB_DIR / "static" / "style.css").read_text(encoding="utf-8")
    assert "focus-visible" in css
    assert "outline: 2px solid var(--accent)" in css


def test_the_result_panel_follows_the_scroll_on_wide_screens():
    """広い画面で右のパネルが画面に貼り付くこと。

    左のフォームは縦に長いので、貼り付けないとスクロールしている間ずっと
    右半分が空白になる(実測: パーツ構成のあたりで右は完全に白紙)。
    """
    css = (WEB_DIR / "static" / "style.css").read_text(encoding="utf-8")
    wide = css.split("@media (min-width: 1000px)", 1)[1][:600]
    assert "position: sticky" in wide
    js = (WEB_DIR / "static" / "app.js").read_text(encoding="utf-8")
    # 貼り付いた要素に scrollIntoView は効かないので、親を基準にする。
    assert "resultPanel.parentElement" in js
