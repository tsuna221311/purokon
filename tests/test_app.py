import io
import pathlib
import re

import pytest
from PIL import Image

import app as app_module
from tests.conftest import TEST_CSRF_TOKEN


def _signup(client, email="user@example.com", password="password123"):
    return client.post("/signup", data={"email": email, "password": password}, follow_redirects=True)


def _login(client, email="user@example.com", password="password123"):
    return client.post("/login", data={"email": email, "password": password}, follow_redirects=True)


def _valid_form():
    return {
        "bust": "84", "waist": "68", "hip": "92", "height": "160",
        "sleeve_length": "54", "shoulder_width": "37",
        "mode": "manual", "neckline": "round_neck",
        "sleeve_style": "straight", "skirt_style": "flare",
    }


def test_index_page_loads(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "PatternForge" in response.get_data(as_text=True)


def test_optional_step_numbers_are_renumbered_from_the_dom(client):
    """任意セクションの見出し番号が、DOMの順に振り直せる形になっていること。

    【round32の元の不具合】「イラストからAI判定」に切り替えると
    「③ パーツ構成」の見出しが消えるのに、直後の見出しが固定の「④」のままで、
    画面上は①②④としか見えなかった。round32はこれを、**セクションごとに
    idを振ってJSがモード別の三項演算子で書き換える**やり方で直した。

    【round40で壊れた】その三項演算子は2か所に散っていて、round40で
    「⑥ 着てみて合わなかったら」を割り込ませたとき、HTML側の縫い代だけを
    ⑦へ書き換えてJS側は"⑥"のまま残った。初回表示はHTMLの値が出るので
    気付かないが、**モードを切り替えて手動に戻すと**JSが上書きして
    ⑥が2つ並ぶ。番号を2か所で管理していたことが原因である。

    【round41の直し方】番号を手で管理するのをやめ、`syncStepNumbers`が
    DOMの順に「表示されている任意セクション」を数えて振り直すようにした。
    このテストは、その前提——(1)全ての任意セクションの見出しが
    `class="optional-step"`という同じ目印を持つこと、(2)初期表示(手動モード)の
    番号が重複せず連続していること——を保証する。目印が1つでも外れると、
    そのセクションだけ番号が飛ぶ。
    """
    body = client.get("/").get_data(as_text=True)
    steps = re.findall(r'<span class="optional-step">(.)</span>', body)
    assert len(steps) >= 4, "任意セクションの見出しに目印が付いていない"
    assert len(set(steps)) == len(steps), f"番号が重複している: {steps}"
    # 初期表示は手動モード。①入力モード ②採寸値 ③パーツ構成 の次から始まる。
    circled = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮"
    expected = list(circled[3:3 + len(steps)])
    assert steps == expected, f"初期表示の番号が連続していない: {steps}"

    js = (pathlib.Path(app_module.BASE_DIR) / "web" / "static" / "app.js").read_text(encoding="utf-8")
    assert "syncStepNumbers" in js
    # 番号をモード別に決め打ちする書き方に戻っていないこと(round40の再発防止)。
    assert "fabricStepNumber" not in js
    assert "seamStepNumber" not in js


def test_healthz(client):
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.get_json() == {"ok": True}


def test_healthz_reports_unhealthy_when_database_is_unreachable(client, monkeypatch):
    # 実際にpatternforge.dbを壊れた内容(SQLiteヘッダを持たないテキスト)に
    # 置き換えた状態でサーバーを起動して見つけた実バグの回帰テスト:
    # 以前の/healthzはDBに一切触れず常に200 {"ok": true}を返していたため、
    # DBが壊れてsignup/login等が実際には500になっている状況でも、
    # ロードバランサ/オーケストレータのヘルスチェックだけは「正常」と
    # 判定し続けてしまう監視上の盲点があった。DBへの到達確認
    # (store.Store.ping())が失敗したら、/healthzも503で異常を報告する
    # ことを検証する。
    def _boom():
        raise RuntimeError("database is unreachable")

    monkeypatch.setattr(app_module.db, "ping", _boom)
    response = client.get("/healthz")
    assert response.status_code == 503
    assert response.get_json()["ok"] is False


def test_favicon_is_served_at_site_root(client):
    # 実際にブラウザで動かして見つけた不具合の回帰テスト。ブラウザは各テンプレートの
    # <link rel="icon"> の有無に関係なく、サイトルートの /favicon.ico を毎回自動的に
    # リクエストする。以前はファイルが存在せず全ページで404になっていた
    # （コンソールにエラーが出るうえ、タブにアイコンが表示されない）。
    response = client.get("/favicon.ico")
    assert response.status_code == 200
    assert response.content_length and response.content_length > 0


def test_index_page_links_a_favicon(client):
    body = client.get("/").get_data(as_text=True)
    assert 'rel="icon"' in body
    assert "favicon.svg" in body


def test_robots_txt_disallows_private_paths_and_references_sitemap(client):
    # 一般公開する実サービスとしてテストして見つかった不備の回帰テスト。
    # ログイン必須のマイページやトークン付きURL(メール確認・パスワード再設定)は
    # 検索結果に出す意味がなく、トークンが漏れる懸念もあるため明示的に除外する。
    response = client.get("/robots.txt")
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert response.mimetype == "text/plain"
    assert "Disallow: /account" in body
    assert "Disallow: /download/" in body
    assert "Disallow: /verify/" in body
    assert "Disallow: /reset-password/" in body
    assert "Sitemap:" in body
    assert "/sitemap.xml" in body


def test_sitemap_xml_lists_public_pages_only(client):
    response = client.get("/sitemap.xml")
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert response.mimetype == "application/xml"
    for path in ("/", "/guide", "/pricing", "/signup", "/login", "/terms", "/privacy", "/legal"):
        assert f"<loc>http://localhost{path}</loc>" in body
    # マイページ・ダウンロード等のログイン必須/トークン付きページは含めない。
    assert "/account" not in body
    assert "/download" not in body


def test_index_page_has_meta_description(client):
    body = client.get("/").get_data(as_text=True)
    assert 'name="description"' in body


def test_measurement_field_labels_are_associated_with_their_inputs(client):
    # 実際にブラウザで動かして見つけたアクセシビリティ上の不備の回帰テスト。
    # 以前は<label>にfor属性が無く、input側にもidはあったが紐付いていなかった
    # ため、ラベルをクリックしても対応する入力欄にフォーカスが移らず、
    # スクリーンリーダーにも項目名が正しく伝わらなかった。
    body = client.get("/").get_data(as_text=True)
    for field in ("bust", "waist", "hip", "height", "sleeve_length", "shoulder_width"):
        assert f'for="field-{field}"' in body
        assert f'id="field-{field}"' in body


def test_auth_forms_declare_autocomplete_attributes_for_password_managers(client):
    """実際にPlaywrightで/signup・/login・/forgot-passwordを開いてブラウザの
    コンソールログを確認したところ、いずれのページでも
    「Input elements should have autocomplete attributes」という警告が
    出ていた(実バグ、修正済み)。email/password欄に`autocomplete`属性が
    無いと、ブラウザのパスワードマネージャーによる自動入力・新しい
    パスワードの生成提案・保存確認が正しく働かない場合がある。
    signup(新規登録)は"new-password"、login(既存アカウント)は
    "username"/"current-password"、reset-passwordは"new-password"、
    forgot-passwordのメール欄は"email"をそれぞれ指定するよう修正し、
    実際に3ページ全てで上記コンソール警告が0件になったことを確認した。
    """
    signup_body = client.get("/signup").get_data(as_text=True)
    assert 'autocomplete="email"' in signup_body
    assert 'autocomplete="new-password"' in signup_body

    login_body = client.get("/login").get_data(as_text=True)
    assert 'autocomplete="username"' in login_body
    assert 'autocomplete="current-password"' in login_body

    forgot_body = client.get("/forgot-password").get_data(as_text=True)
    assert 'autocomplete="email"' in forgot_body

    reset_body = client.get("/reset-password/dummy-token-for-template-check").get_data(as_text=True)
    assert 'autocomplete="new-password"' in reset_body


def test_generate_manual_mode_returns_downloadable_job(client):
    response = client.post("/api/generate", data=_valid_form())
    assert response.status_code == 200
    data = response.get_json()
    assert data["ok"] is True
    assert data["part_count"] > 0
    assert "ai_contribution" in data
    assert data["measurement_warnings"] == []

    svg_response = client.get(data["download"]["svg"])
    assert svg_response.status_code == 200
    pdf_response = client.get(data["download"]["pdf"])
    assert pdf_response.status_code == 200


def test_generate_warns_when_measurement_exceeds_template_scale_range(client):
    """実際にHTTP経由でbust=160cmとbust=132.8cmを送って比較し、生成される
    型紙が完全に同一になる(=入力した採寸値が実際には使われていない)ことを
    発見した実バグの回帰テスト。`/api/generate`のJSONレスポンスに、この
    食い違いを利用者へ開示する`measurement_warnings`が含まれることを
    確認する。"""
    form = _valid_form()
    form["bust"] = "160"  # Measurements側の入力検証(50〜160cm)は通るが、
    # テンプレートの変形限界(標準サイズの0.7〜1.6倍)は超える。
    response = client.post("/api/generate", data=form)
    assert response.status_code == 200
    data = response.get_json()
    assert data["ok"] is True
    # 採寸クランプの注記だけを見る(round27で「ウエストが絞りきれていない」
    # など別の注記も出うるため)。
    clamp = [w for w in data["measurement_warnings"] if "変形可能範囲" in w]
    assert len(clamp) == 1
    assert "バスト" in clamp[0]
    # 注記に出る境界は、実際にクランプされる値と一致していること。round23で
    # 身頃の幅を「バスト + 一定のゆとり」で決めるようにしたとき、注記側だけ
    # 古い式のままで 137.6cm を 132.8cm と説明する状態になった(数値を直書き
    # していると、この種の食い違いを取り逃がす)。
    from engine.bodice_fit import bodice_bust_cm_for_scale
    from engine.part_specs import MAX_SCALE

    assert f"{bodice_bust_cm_for_scale(MAX_SCALE):.1f}" in clamp[0]


def test_generate_rejects_invalid_measurement(client):
    form = _valid_form()
    form["bust"] = "5"  # 現実的な範囲外
    response = client.post("/api/generate", data=form)
    assert response.status_code == 400
    assert response.get_json()["ok"] is False


def test_generate_rejects_unsupported_combo(client):
    form = _valid_form()
    form["neckline"] = "turtle_neck"
    form["front_zip"] = "on"
    response = client.post("/api/generate", data=form)
    assert response.status_code == 400


def test_generate_supports_front_zip_with_split_front_panel(client):
    # round5より前開きファスナーは実際に中心前で前身頃を分割した2枚構成に
    # なった(engine/pipeline.pyのfront_bodice_zip_panel)。HTTP経由でも
    # 生成が成功し、パーツ数に前パネル2枚が反映されることを確認する。
    form = _valid_form()
    form["neckline"] = "round_neck"
    form["front_zip"] = "on"
    form["sleeve_style"] = ""
    form["skirt_style"] = ""
    response = client.post("/api/generate", data=form)
    assert response.status_code == 200
    data = response.get_json()
    assert data["ok"] is True
    # 前パネル(左右2枚) + 後身頃(1枚) = 3
    assert data["part_count"] == 3
    # round32: 表示名は日本語になったので、機械向けの`part_type`で見る
    # (表示名の文字列に依存すると、ラベルを直すたびにテストが壊れる)。
    assert any(p["part_type"] == "front_bodice_zip_panel" for p in data["parts"])
    assert any("ファスナーパネル" in p["display_name"] for p in data["parts"])


def test_generate_reports_darts_applied_for_hourglass_measurements(client):
    form = _valid_form()
    form["bust"] = "110"
    form["waist"] = "60"
    response = client.post("/api/generate", data=form)
    assert response.status_code == 200
    data = response.get_json()
    assert data["darts_applied"] > 0


def test_generate_reports_the_waist_darts_for_standard_measurements(client):
    """標準採寸でも、ウエストのダーツ本数が報告されること。

    round26まで、標準採寸(バスト84/ウエスト68)ではダーツが0本だった。
    ウエストのダーツは**裾の線**に入る仕組みだったが、身頃の裾はヒップの
    高さにあり、そこで摘むとヒップが通らなくなるため摘めなかったからである。
    round27でウエストの線に両端の尖ったダーツ(ダイヤモンドダーツ)を置ける
    ようにしたので、標準採寸でもウエストが絞られる。
    """
    response = client.post("/api/generate", data=_valid_form())
    assert response.status_code == 200
    data = response.get_json()
    assert data["darts_applied"] > 0


def test_generate_returns_naive_baseline_and_parts_list(client):
    response = client.post("/api/generate", data=_valid_form())
    assert response.status_code == 200
    data = response.get_json()
    assert data["naive_used_length_cm"] >= data["used_length_cm"]
    assert len(data["parts"]) == data["part_count"]
    assert all("display_name" in p and "width_cm" in p and "height_cm" in p for p in data["parts"])


def test_generate_rejects_cuffs_without_sleeve(client):
    form = _valid_form()
    form["sleeve_style"] = ""  # ノースリーブ
    form["include_cuffs"] = "on"
    response = client.post("/api/generate", data=form)
    assert response.status_code == 400


def test_index_page_lists_new_variation_options(client):
    body = client.get("/").get_data(as_text=True)
    # 新しいネックライン・袖・衿/カフス/パンツ/ウエストバンドのバリエーションが
    # フォームの選択肢として実際に表示されていること。
    assert 'name="pants_style"' in body
    assert 'name="collar_style"' in body
    assert 'name="cuffs_style"' in body
    assert 'name="waistband_style"' in body
    for value in ("square_neck", "boat_neck", "puff", "shirt_collar",
                  "peter_pan_collar", "wide", "tapered"):
        assert f'value="{value}"' in body, f"{value} が選択肢に見当たらない"


def test_generate_supports_new_necklines_and_puff_sleeve(client):
    form = _valid_form()
    form["neckline"] = "square_neck"
    form["sleeve_style"] = "puff"
    response = client.post("/api/generate", data=form)
    assert response.status_code == 200
    assert response.get_json()["ok"] is True


def test_generate_supports_collar_cuffs_pants_waistband_styles(client):
    form = _valid_form()
    form["include_collar"] = "on"
    form["collar_style"] = "peter_pan_collar"
    form["include_cuffs"] = "on"
    form["cuffs_style"] = "wide"
    form["include_pants"] = "on"
    form["pants_style"] = "tapered"
    form["include_waistband"] = "on"
    form["waistband_style"] = "wide"
    response = client.post("/api/generate", data=form)
    assert response.status_code == 200
    data = response.get_json()
    assert data["ok"] is True
    # 前身頃+後身頃(2) + 袖(2) + スカート(2、既定flare) + カフス(2)
    # + パンツ前後(round5でfront_pants/back_pantsに分離、左右各2枚=4)
    # + 衿(1) + ウエストバンド(1) = 14
    assert data["part_count"] == 14


def test_generate_rejects_unknown_collar_style(client):
    form = _valid_form()
    form["include_collar"] = "on"
    form["collar_style"] = "not-a-real-style"
    response = client.post("/api/generate", data=form)
    assert response.status_code == 400


def test_index_page_lists_round3_variation_options(client):
    body = client.get("/").get_data(as_text=True)
    for value in ("sweetheart", "bell", "pleated", "wrap", "shorts",
                  "bow_collar", "elastic"):
        assert f'value="{value}"' in body, f"{value} が選択肢に見当たらない"


def test_generate_supports_sweetheart_neckline_and_bell_sleeve(client):
    form = _valid_form()
    form["neckline"] = "sweetheart"
    form["sleeve_style"] = "bell"
    response = client.post("/api/generate", data=form)
    assert response.status_code == 200
    assert response.get_json()["ok"] is True


def test_generate_rejects_turtleneck_zip_combo(client):
    # round9で前開き対応ネックラインをround_neck/v_neckの2種から
    # square_neck/boat_neck/sweetheartを含む5種へ拡大したが、turtle_neckは
    # 台襟の構造上そのままでは対応できないため、引き続き明確な400になる
    # はず(engine/pipeline.py ZIP_COMPATIBLE_NECKLINESのコメント参照)。
    form = _valid_form()
    form["neckline"] = "turtle_neck"
    form["front_zip"] = "on"
    response = client.post("/api/generate", data=form)
    assert response.status_code == 400


@pytest.mark.parametrize("neckline", ["square_neck", "boat_neck", "sweetheart"])
def test_generate_supports_front_zip_for_newly_added_necklines(client, neckline):
    # round9で追加: 以前はround_neck/v_neckのみ前開きファスナーに対応して
    # いたが、square_neck/boat_neck/sweetheartにも対応を広げた
    # (scripts/generate_templates.pyのfront_bodice_zip_panel追記参照)。
    form = _valid_form()
    form["neckline"] = neckline
    form["front_zip"] = "on"
    response = client.post("/api/generate", data=form)
    assert response.status_code == 200, response.get_json()
    assert response.get_json()["ok"] is True


def test_generate_supports_pleated_and_wrap_skirt(client):
    for skirt_style in ("pleated", "wrap"):
        form = _valid_form()
        form["skirt_style"] = skirt_style
        response = client.post("/api/generate", data=form)
        assert response.status_code == 200, skirt_style
        assert response.get_json()["ok"] is True


def test_generate_supports_shorts_bow_collar_and_elastic_waistband(client):
    form = _valid_form()
    form["include_pants"] = "on"
    form["pants_style"] = "shorts"
    form["include_collar"] = "on"
    form["collar_style"] = "bow_collar"
    form["include_waistband"] = "on"
    form["waistband_style"] = "elastic"
    response = client.post("/api/generate", data=form)
    assert response.status_code == 200
    assert response.get_json()["ok"] is True


def test_generate_reports_skirt_waist_dart_for_pear_shaped_measurements(client):
    form = _valid_form()
    form["waist"] = "60"
    form["hip"] = "105"
    form["skirt_style"] = "tight"
    response = client.post("/api/generate", data=form)
    assert response.status_code == 200
    data = response.get_json()
    assert data["darts_applied"] > 0


def test_index_page_lists_round4_variation_options(client):
    body = client.get("/").get_data(as_text=True)
    for value in ("cap", "mermaid", "flare", "ruffle_collar", "ruffle"):
        assert f'value="{value}"' in body, f"{value} が選択肢に見当たらない"


def test_generate_supports_cap_sleeve_and_mermaid_skirt(client):
    form = _valid_form()
    form["sleeve_style"] = "cap"
    form["skirt_style"] = "mermaid"
    response = client.post("/api/generate", data=form)
    assert response.status_code == 200
    assert response.get_json()["ok"] is True


def test_generate_supports_flare_pants_ruffle_collar_and_ruffle_cuffs(client):
    form = _valid_form()
    form["sleeve_style"] = "straight"
    form["include_pants"] = "on"
    form["pants_style"] = "flare"
    form["include_collar"] = "on"
    form["collar_style"] = "ruffle_collar"
    form["include_cuffs"] = "on"
    form["cuffs_style"] = "ruffle"
    response = client.post("/api/generate", data=form)
    assert response.status_code == 200
    assert response.get_json()["ok"] is True


def test_generate_reports_pants_waist_dart_for_pear_shaped_measurements(client):
    # スカートのタイトと違い、パンツは全バリエーションがウエストダーツの
    # 対象なので、flareパンツでも洋なし型の体型ならダーツが入るはず。
    form = _valid_form()
    form["waist"] = "60"
    form["hip"] = "105"
    form["skirt_style"] = "flare"  # スカート側はダーツ対象外にして、パンツ側の寄与だけを見る
    form["include_pants"] = "on"
    form["pants_style"] = "flare"
    response = client.post("/api/generate", data=form)
    assert response.status_code == 200
    data = response.get_json()
    assert data["darts_applied"] > 0


def test_download_rejects_path_traversal_and_bad_format(client):
    response = client.get("/download/../../etc/passwd/svg")
    assert response.status_code in (400, 404)

    response = client.get("/download/0123456789ab/exe")
    assert response.status_code == 400


def test_download_missing_job_returns_404(client):
    response = client.get("/download/aaaaaaaaaaaa/pdf")
    assert response.status_code == 404


def test_generate_illustration_mode_with_uploaded_image(client, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    image = Image.new("RGB", (400, 800), "white")
    from PIL import ImageDraw
    ImageDraw.Draw(image).rectangle([100, 150, 300, 700], fill="black")
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    buf.seek(0)

    form = _valid_form()
    form["mode"] = "illustration"
    response = client.post("/api/generate", data={
        **form,
        "illustration": (buf, "test.png"),
    }, content_type="multipart/form-data")
    assert response.status_code == 200
    data = response.get_json()
    assert data["ok"] is True
    assert len(data["classification_log"]) > 0


def test_generate_illustration_mode_accepts_multiple_images(client, monkeypatch):
    """round18: 同じ入力欄に複数枚を投げても受け付け、枚数を開示すること。"""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    from PIL import ImageDraw

    def _png(width_ratio):
        image = Image.new("RGB", (400, 800), "white")
        half = int(100 * width_ratio)
        ImageDraw.Draw(image).rectangle([200 - half, 150, 200 + half, 700], fill="black")
        buf = io.BytesIO()
        image.save(buf, format="PNG")
        buf.seek(0)
        return buf

    form = _valid_form()
    form["mode"] = "illustration"
    response = client.post("/api/generate", data={
        **form,
        "illustration": [(_png(1.0), "front.png"), (_png(0.8), "back.png")],
    }, content_type="multipart/form-data")
    assert response.status_code == 200
    data = response.get_json()
    assert data["ok"] is True
    assert any("2枚" in note for note in data["measurement_warnings"]), data["measurement_warnings"]


def test_generate_illustration_mode_rejects_too_many_images(client, monkeypatch):
    """枚数の上限を超えたら、黙って切り捨てずにエラーにすること。

    1枚ごとに分割と判定が走る(APIキーがあればClaude API呼び出し)ため、
    処理時間と費用が枚数に比例する。
    """
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    from app import MAX_ILLUSTRATION_IMAGES
    from PIL import ImageDraw

    def _png():
        image = Image.new("RGB", (400, 800), "white")
        ImageDraw.Draw(image).rectangle([100, 150, 300, 700], fill="black")
        buf = io.BytesIO()
        image.save(buf, format="PNG")
        buf.seek(0)
        return buf

    files = [(_png(), f"cut{i}.png") for i in range(MAX_ILLUSTRATION_IMAGES + 1)]
    form = _valid_form()
    form["mode"] = "illustration"
    response = client.post("/api/generate", data={**form, "illustration": files},
                            content_type="multipart/form-data")
    data = response.get_json()
    assert data["ok"] is False
    assert "枚まで" in data["error"]


def test_load_uploaded_image_applies_exif_orientation(client):
    # 実写のスマートフォン写真でテストして見つかった不具合の再現テスト。
    # 多くのスマホは「見た目通りに回転させるにはEXIFのOrientationタグ通りに
    # 回転してください」という向きでJPEGのピクセルを保存する。以前は
    # Image.open()の結果をそのまま使っていたため、縦向きで撮った服の写真が
    # 内部的には横向きの画素配列のまま処理され、ネックライン・裾の位置判定が
    # 全てずれてしまっていた。ImageOps.exif_transpose()で正規化されることを
    # 確認する。
    from PIL import Image as PILImage

    upright = PILImage.new("RGB", (400, 800), "white")  # 見た目は縦長(400x800)
    rotated_pixels = upright.rotate(-90, expand=True)  # 実際のピクセル配列は横向き(800x400)
    exif = PILImage.Exif()
    exif[274] = 6  # Orientation=6: 表示時に90度回転が必要
    buf = io.BytesIO()
    rotated_pixels.save(buf, format="JPEG", exif=exif, quality=90)
    buf.seek(0)

    class _FakeUpload:
        stream = buf

    loaded = app_module._load_uploaded_image(_FakeUpload())
    assert loaded.size == (400, 800)  # 見た目通りの縦長に正規化されている


def test_oversized_image_gets_resolution_error_not_generic_unreadable_error(client):
    # 実際に1.5万x1.5万pxのPNGを送って見つかった不具合の再現テスト。
    #
    # Pillow自身も「解凍爆弾」対策として、既定でMAX_IMAGE_PIXELS(約1.79億px)を
    # 超える画像に対してはImage.open()の時点でDecompressionBombErrorを投げる。
    # これが有効なままだと、_load_uploaded_image()内の
    # 「width*height > MAX_UPLOAD_IMAGE_PIXELS」判定(2500万px)に到達する前に
    # open()自体が例外で落ち、広いexceptに捕まって「画像を読み込めませんでした。
    # 対応形式(PNG/JPEG等)かご確認ください」という的外れなメッセージになって
    # いた(実際には対応形式そのままの正しいPNGだった)。
    # app.py側でImage.MAX_IMAGE_PIXELS = Noneとし、常に自前の
    # MAX_UPLOAD_IMAGE_PIXELS判定を「解像度が大きすぎます」という正しい案内文
    # で先に発生させるように修正した。
    #
    # 実際にフルサイズ(2万x2万px)の画像をエンコードするとテストが重くなるため、
    # IHDRチャンクだけ巨大な解像度を宣言した最小限のPNG(IDATは中身のない
    # ダミー)で代用する。Pillowの解凍爆弾チェックはヘッダーから読み取った
    # width*heightだけで判定され、実際のピクセルデータはまだ読まないため、
    # このごく小さいファイルでも同じ例外(DecompressionBombError)を再現できる。
    import struct
    import zlib

    def _chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data))

    width, height = 20000, 20000
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    idat = zlib.compress(b"\x00" * 10)
    fake_huge_png = (
        b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", ihdr) + _chunk(b"IDAT", idat) + _chunk(b"IEND", b"")
    )

    form = _valid_form()
    form["mode"] = "illustration"
    response = client.post(
        "/api/generate",
        data={**form, "illustration": (io.BytesIO(fake_huge_png), "huge.png")},
    )
    assert response.status_code == 400
    body = response.get_json()
    assert "解像度が大きすぎます" in body["error"]
    assert "読み込めませんでした" not in body["error"]


def test_rate_limit_returns_429_when_exceeded(client, monkeypatch):
    monkeypatch.setattr(app_module._generate_rate_limiter, "max_requests", 1)
    first = client.post("/api/generate", data=_valid_form())
    second = client.post("/api/generate", data=_valid_form())
    assert first.status_code == 200
    assert second.status_code == 429


def test_rate_limit_cannot_be_bypassed_by_spoofing_forwarded_for_header(client, monkeypatch):
    # X-Forwarded-Forはクライアントが自由に送れるヘッダーなので、信頼できる
    # プロキシの背後で動かしていない限り、これを鍵にレート制限をかけては
    # ならない（毎リクエストで値を変えるだけで無制限に迂回できてしまう）。
    # 既定(PATTERNFORGE_TRUST_PROXY_HEADERS未設定)ではremote_addrのみを
    # 鍵に使うため、ヘッダーを変えても制限が効くことを確認する。
    assert app_module.TRUST_PROXY_HEADERS is False
    monkeypatch.setattr(app_module._generate_rate_limiter, "max_requests", 1)
    first = client.post("/api/generate", data=_valid_form(),
                         headers={"X-Forwarded-For": "1.1.1.1"})
    second = client.post("/api/generate", data=_valid_form(),
                          headers={"X-Forwarded-For": "2.2.2.2"})
    assert first.status_code == 200
    assert second.status_code == 429


def test_trust_proxy_headers_uses_last_hop_not_full_header_value(client, monkeypatch):
    # 実際にPATTERNFORGE_TRUST_PROXY_HEADERS=1でサーバを起動し、/loginへ
    # 間違ったパスワードで15回連続POSTしたところ、X-Forwarded-Forの先頭部分
    # （クライアントが自由に書ける、単一の信頼できるプロキシの手前の値）を
    # 毎回変えるだけで一度も429にならず、レート制限が完全に無効化される
    # ことを確認した実バグ。以前は`_client_key()`がヘッダー値全体をそのまま
    # 鍵に使っていたため、単一プロキシが末尾に追記した「実際に接続してきた
    # IP」が同じでも、先頭のなりすまし部分が違うだけで別の鍵として扱われて
    # いた。カンマ区切りの末尾（信頼できる直近のプロキシ自身が追記した部分）
    # だけを鍵に使うよう修正した。
    monkeypatch.setattr(app_module, "TRUST_PROXY_HEADERS", True)
    monkeypatch.setattr(app_module._generate_rate_limiter, "max_requests", 1)

    first = client.post(
        "/api/generate", data=_valid_form(),
        headers={"X-Forwarded-For": "1.1.1.1, 203.0.113.9"},
    )
    # 末尾(信頼できるプロキシが追記した実際の接続元IP)は同じで、先頭の
    # なりすまし部分だけを変える。修正前はこれで無制限に迂回できていた。
    second = client.post(
        "/api/generate", data=_valid_form(),
        headers={"X-Forwarded-For": "2.2.2.2, 203.0.113.9"},
    )
    assert first.status_code == 200
    assert second.status_code == 429

    # 末尾の実際の接続元IPそのものが異なる、本当に別クライアントの場合は
    # 引き続き別の制限バケットとして扱われる(正しい単一プロキシ運用)。
    third = client.post(
        "/api/generate", data=_valid_form(),
        headers={"X-Forwarded-For": "3.3.3.3, 198.51.100.5"},
    )
    assert third.status_code == 200


def test_generate_illustration_mode_without_file_returns_clear_error(client):
    # イラストモードを選んでいるのにファイルが無い場合、以前は黙って
    # 手動モードのデフォルト選択で生成が成功してしまっていた
    # （利用者が「イラストを見てもらえなかった」ことに気づけない）。
    # 明確な400エラーになることを確認する。
    form = _valid_form()
    form["mode"] = "illustration"
    response = client.post("/api/generate", data=form)
    assert response.status_code == 400
    data = response.get_json()
    assert data["ok"] is False
    assert "画像" in data["error"]


def test_generate_rejects_oversized_upload_with_413_not_500(client, monkeypatch):
    monkeypatch.setitem(app_module.app.config, "MAX_CONTENT_LENGTH", 10)  # 10バイトに厳しく設定
    form = _valid_form()
    form["mode"] = "illustration"
    image = Image.new("RGB", (50, 50), "white")
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    buf.seek(0)
    response = client.post("/api/generate", data={
        **form, "illustration": (buf, "test.png"),
    }, content_type="multipart/form-data")
    assert response.status_code == 413
    assert response.get_json()["ok"] is False


def test_generate_rejects_high_pixel_count_image_before_decoding(client):
    # 圧縮率の高い単色画像は、ファイルサイズは小さいままピクセル数だけを
    # 巨大にできる(decompression bomb)。MAX_CONTENT_LENGTH(バイト数)だけでは
    # 防げないため、ピクセル数上限(MAX_UPLOAD_IMAGE_PIXELS)で別途弾く。
    monkeypatch_limit = 1_000_000  # テストなので小さい値に設定して高速化する
    orig = app_module.MAX_UPLOAD_IMAGE_PIXELS
    app_module.MAX_UPLOAD_IMAGE_PIXELS = monkeypatch_limit
    try:
        image = Image.new("RGB", (2000, 2000), "white")  # 4,000,000px > 1,000,000px
        buf = io.BytesIO()
        image.save(buf, format="PNG")
        buf.seek(0)
        form = _valid_form()
        form["mode"] = "illustration"
        response = client.post("/api/generate", data={
            **form, "illustration": (buf, "test.png"),
        }, content_type="multipart/form-data")
        assert response.status_code == 400
        data = response.get_json()
        assert data["ok"] is False
        assert "解像度" in data["error"]
    finally:
        app_module.MAX_UPLOAD_IMAGE_PIXELS = orig


def test_unexpected_error_returns_generic_message_with_error_id_not_raw_exception(client, monkeypatch):
    # 以前は str(exc) をそのままクライアントに返していたため、内部の例外文字列
    # (ファイルパス等)が漏れる恐れがあった。エラーIDだけを返し、詳細はログに
    # 残す形に修正したことを確認する。
    def _boom(*args, **kwargs):
        raise RuntimeError("secret internal detail: /etc/some/internal/path")

    monkeypatch.setattr(app_module.pipeline, "generate_from_selection", _boom)
    response = client.post("/api/generate", data=_valid_form())
    assert response.status_code == 500
    data = response.get_json()
    assert data["ok"] is False
    assert "エラーID" in data["error"]
    assert "secret internal detail" not in data["error"]
    assert "/etc/some/internal/path" not in data["error"]


def test_security_headers_present_on_every_response(client):
    response = client.get("/healthz")
    assert response.headers.get("X-Content-Type-Options") == "nosniff"
    assert response.headers.get("X-Frame-Options") == "DENY"
    assert "Content-Security-Policy" in response.headers


def test_download_rate_limited(client, monkeypatch):
    response = client.post("/api/generate", data=_valid_form())
    job_id = response.get_json()["job_id"]
    monkeypatch.setattr(app_module._download_rate_limiter, "max_requests", 1)
    first = client.get(f"/download/{job_id}/svg")
    second = client.get(f"/download/{job_id}/svg")
    assert first.status_code == 200
    assert second.status_code == 429


def test_download_denies_a_different_session_even_with_correct_job_id(client, monkeypatch):
    # job_id(推測困難な16進数)を知っているだけでは、生成した本人以外は
    # ダウンロードできないことを確認する（データ分離）。
    response = client.post("/api/generate", data=_valid_form())
    assert response.status_code == 200
    job_id = response.get_json()["job_id"]

    # 別クライアント = 別ブラウザ/別セッション(クッキーを共有しない)を模擬する。
    with app_module.app.test_client() as other_client:
        other_response = other_client.get(f"/download/{job_id}/svg")
        assert other_response.status_code == 404


def test_signup_login_logout_flow(client):
    signup_response = _signup(client)
    assert signup_response.status_code == 200
    account_page = client.get("/account")
    assert account_page.status_code == 200
    assert b"user@example.com" in account_page.data

    logout_response = client.post("/logout", follow_redirects=True)
    assert logout_response.status_code == 200
    assert client.get("/account", follow_redirects=False).status_code == 302

    login_response = _login(client)
    assert login_response.status_code == 200
    assert client.get("/account").status_code == 200


def test_signup_rejects_duplicate_email(client):
    _signup(client)
    with app_module.app.test_client() as other_client:
        other_client.get("/")  # visitor_idを発行させる(無くても動くが自然な経路にする)
        # round6でCSRF検証を追加したため、このクライアント自身のセッションに
        # 紐づくトークンをフォームにも含める必要がある(GET / で発行された
        # ものと同じ値なので、テスト専用の固定トークンをそのまま使う)。
        with other_client.session_transaction() as sess:
            sess["csrf_token"] = TEST_CSRF_TOKEN
        response = other_client.post("/signup", data={
            "email": "user@example.com", "password": "password123", "csrf_token": TEST_CSRF_TOKEN,
        })
        assert response.status_code == 400


def test_login_rejects_wrong_password(client):
    _signup(client)
    client.post("/logout")
    response = client.post("/login", data={"email": "user@example.com", "password": "wrong-password"})
    assert response.status_code == 400


def test_login_rate_limited_after_repeated_attempts(client, monkeypatch):
    # 実際にサーバを起動し、同一アカウント宛に間違ったパスワードで60回連続
    # ログインを試したところ、全て通常の400（認証失敗）として処理され、
    # 429やロックアウトが一切発生しないことを確認した(総当たり攻撃が無制限に
    # 可能な状態だった)。/api/generate等の他エンドポイントには既にIPベースの
    # レート制限(_generate_rate_limiter等)があるのに/loginにだけ無かった
    # という見落としを修正し、他と同じ`_RateLimiter`パターンで
    # `_login_rate_limiter` を追加した。
    _signup(client)
    client.post("/logout")
    monkeypatch.setattr(app_module._login_rate_limiter, "max_requests", 3)

    statuses = []
    for _ in range(5):
        response = client.post(
            "/login", data={"email": "user@example.com", "password": "wrong-password"}
        )
        statuses.append(response.status_code)
    assert statuses == [400, 400, 400, 429, 429]

    # 正しいパスワードでも、レート制限にかかっている間は429のままログインできない。
    blocked = client.post("/login", data={"email": "user@example.com", "password": "password123"})
    assert blocked.status_code == 429


def test_account_lockout_blocks_login_after_threshold_failures_regardless_of_ip(client, monkeypatch):
    # round7で追加: IPベースの`_login_rate_limiter`とは別に、アカウント
    # (メールアドレス)単位でも失敗回数を数えてロックアウトする
    # (store.check_account_lockout参照)。IPベースの制限だけでは、多数のIPを
    # 使い分けて1つのメールアドレスを狙う分散的な総当たりを防げないため。
    # IPベースの制限を実質無効にして、アカウント単位の仕組みだけを単体で
    # 検証する。
    monkeypatch.setattr(app_module._login_rate_limiter, "max_requests", 1000)
    monkeypatch.setattr(app_module.store, "ACCOUNT_LOCKOUT_THRESHOLD", 5)

    _signup(client)
    client.post("/logout")

    statuses = []
    for _ in range(6):
        response = client.post(
            "/login", data={"email": "user@example.com", "password": "wrong-password"}
        )
        statuses.append(response.status_code)
    assert statuses == [400, 400, 400, 400, 400, 429]

    # 正しいパスワードでも、ロックアウト中は弾かれる(正解を知っている攻撃者が
    # 「たまたま通った試行」で検知を逃れられないようにするため)。
    blocked = client.post("/login", data={"email": "user@example.com", "password": "password123"})
    assert blocked.status_code == 429


def test_account_lockout_does_not_block_a_different_account(client, monkeypatch):
    monkeypatch.setattr(app_module._login_rate_limiter, "max_requests", 1000)
    monkeypatch.setattr(app_module.store, "ACCOUNT_LOCKOUT_THRESHOLD", 5)

    _signup(client, email="victim@example.com")
    client.post("/logout")
    _signup(client, email="other@example.com")
    client.post("/logout")

    for _ in range(6):
        client.post("/login", data={"email": "victim@example.com", "password": "wrong-password"})

    # 別のアカウントは影響を受けず、正しいパスワードでログインできる。
    response = _login(client, email="other@example.com")
    assert response.status_code == 200


def test_account_lockout_clears_on_successful_login(client, monkeypatch):
    monkeypatch.setattr(app_module._login_rate_limiter, "max_requests", 1000)
    monkeypatch.setattr(app_module.store, "ACCOUNT_LOCKOUT_THRESHOLD", 5)

    _signup(client)
    client.post("/logout")

    for _ in range(4):
        client.post("/login", data={"email": "user@example.com", "password": "wrong-password"})

    # 閾値未満なのでまだロックされておらず、正しいパスワードでログインできる。
    ok = _login(client)
    assert ok.status_code == 200
    client.post("/logout")

    # 成功でカウンタがクリアされているはずなので、続けて4回失敗しても
    # (合計では8回失敗しているが、成功でリセットされている)まだロックされない。
    statuses = []
    for _ in range(4):
        response = client.post(
            "/login", data={"email": "user@example.com", "password": "wrong-password"}
        )
        statuses.append(response.status_code)
    assert statuses == [400, 400, 400, 400]


def test_account_requires_login(client):
    response = client.get("/account")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_login_required_redirect_does_not_touch_session_cookie(client):
    # 実際にPlaywright経由の本物のブラウザで、ログイン中の利用者が無関係な
    # 別オリジンのページを開き、そこに置かれた自動送信フォームがこの
    # アプリの@_login_required付きPOSTエンドポイント(例: プロフィール削除)へ
    # 送信するCSRFを実際に試して見つかった不具合の再発防止テスト。
    #
    # SESSION_COOKIE_SAMESITE=Laxにより、このクロスサイトPOSTには本物の
    # セッションCookieが付与されないため、保護対象の操作自体は実行され
    # ない(これは正しい挙動で、実際にDBを確認して操作が実行されていない
    # ことを確認済み)。しかし以前は、Cookie無しで届いたこのリクエストに対して
    # `_login_required`が`flash()`(=session書き込み)を呼んでいたため、
    # 302応答に真新しい(未ログインの)セッションのSet-Cookieが付与されていた。
    # ブラウザはこれを同一オリジンからの応答として素直に受け取り、たとえ
    # 本来のログイン済みセッションCookieがまだブラウザ側に残っていても
    # 同じCookie名で上書きしてしまい、利用者を強制的にログアウトさせて
    # いた(実際にPlaywrightでCookie値を追跡して確認済み)。
    #
    # ここではFlaskのテストクライアントで、Cookie無し(=未ログイン)の状態
    # から@_login_required付きエンドポイントに直接アクセスした際の応答に
    # Set-Cookieヘッダーが含まれない(=セッションを一切変更しない)ことを
    # 検証する。
    response = client.post("/account/profiles/1/delete")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]
    assert "login_required=1" in response.headers["Location"]
    assert "Set-Cookie" not in response.headers


def test_login_page_shows_notice_via_query_param_not_flash(client):
    # 上記の修正の裏返しの確認: session(flash)を経由しなくても、
    # クエリ文字列(login_required=1)だけで案内文言が表示されることを確認する。
    response = client.get("/login?login_required=1")
    assert response.status_code == 200
    assert "ログインが必要です。" in response.get_data(as_text=True)

    # クエリ文字列が無い通常のログイン画面表示では、この案内文言は出ない。
    plain_response = client.get("/login")
    assert "ログインが必要です。" not in plain_response.get_data(as_text=True)


def test_anonymous_jobs_are_adopted_by_account_after_signup(client):
    # ログイン前に生成したジョブは、その後アカウント登録すると引き継がれ、
    # ログイン後もダウンロードできる（匿名ジョブへのアクセス権が失われない）。
    generate_response = client.post("/api/generate", data=_valid_form())
    job_id = generate_response.get_json()["job_id"]

    _signup(client)
    download_response = client.get(f"/download/{job_id}/svg")
    assert download_response.status_code == 200


def test_anonymous_daily_usage_limit_is_enforced(client, monkeypatch):
    monkeypatch.setitem(app_module.store.DEFAULT_DAILY_LIMITS, "anon", 2)
    first = client.post("/api/generate", data=_valid_form())
    second = client.post("/api/generate", data=_valid_form())
    third = client.post("/api/generate", data=_valid_form())
    assert first.status_code == 200
    assert second.status_code == 200
    assert third.status_code == 429
    data = third.get_json()
    assert data["ok"] is False
    assert "upgrade_url" in data


def test_failed_generation_does_not_consume_daily_usage(client, monkeypatch):
    """round34で発見・修正した実バグの回帰テスト(store.Store.refund_usage
    のdocstring参照)。

    以前は`check_and_increment_usage()`が実際の生成処理(パイプライン内の
    ネスティング・イラストモードのAI判定等)より前に呼ばれていたため、
    採寸値やパーツ構成自体は正しくても、生成処理そのものが(想定外の例外や、
    イラストからパーツ領域/パーツ種を判定できない等の理由で)失敗した場合
    でも、利用者は型紙を1件も受け取れないまま本日の利用回数を1回消費させ
    られていた。実際にパイプラインが例外を投げる状況を再現し、失敗した
    リクエストの前後で利用回数が変化しないことを確認する。
    """
    monkeypatch.setitem(app_module.store.DEFAULT_DAILY_LIMITS, "anon", 2)

    def _boom(*args, **kwargs):
        raise RuntimeError("想定外のパイプライン内部エラーを模擬")

    # インスタンス属性としてpatchする(クラスをpatchすると、他のテストが
    # 同じ手法でpipelineインスタンスの属性を一度でも上書き→復元していた
    # 場合に、その復元がクラスではなくインスタンス自身に新しい属性として
    # 残ってしまい、以後クラスへのpatchが効かなくなるpytest monkeypatchの
    # 既知の癖がある。既存の同種テスト(
    # test_unexpected_error_returns_generic_message_with_error_id_not_raw_exception)
    # と同じ、インスタンス属性への直接patchに揃える)。
    monkeypatch.setattr(app_module.pipeline, "generate_from_selection", _boom)
    response = client.post("/api/generate", data=_valid_form())
    assert response.status_code == 500

    with client.session_transaction() as sess:
        vid = sess.get("visitor_id")
    used = app_module.db.usage_today(f"anon:{vid}", app_module._today_str())
    assert used == 0  # 失敗したので利用回数は消費されていない(=refundされている)


def test_illustration_mode_failure_does_not_consume_daily_usage(client, monkeypatch):
    """上のテストのイラストモード版。無地一色の画像はパーツ領域を検出
    できずValueErrorになる(engine.pipeline.generate_from_illustration
    参照)実際の失敗経路で、同様に利用回数が消費されないことを確認する。
    """
    import io
    from PIL import Image

    monkeypatch.setitem(app_module.store.DEFAULT_DAILY_LIMITS, "anon", 2)

    solid_image = io.BytesIO()
    Image.new("RGB", (200, 200), color=(120, 120, 120)).save(solid_image, format="PNG")
    solid_image.seek(0)

    form = {
        "bust": "84", "waist": "68", "hip": "92", "height": "160",
        "sleeve_length": "54", "shoulder_width": "37", "mode": "illustration",
    }
    response = client.post(
        "/api/generate", data={**form, "illustration": (solid_image, "solid.png")},
        content_type="multipart/form-data",
    )
    assert response.status_code == 400

    with client.session_transaction() as sess:
        vid = sess.get("visitor_id")
    used = app_module.db.usage_today(f"anon:{vid}", app_module._today_str())
    assert used == 0


def test_pro_plan_has_no_daily_limit(client, monkeypatch):
    monkeypatch.setitem(app_module.store.DEFAULT_DAILY_LIMITS, "free", 1)
    _signup(client)
    client.post("/account/upgrade")

    first = client.post("/api/generate", data=_valid_form())
    second = client.post("/api/generate", data=_valid_form())
    assert first.status_code == 200
    assert second.status_code == 200  # freeなら2回目で429になるはずの上限が、proでは効かない


def test_pricing_and_signup_pages_load(client):
    assert client.get("/pricing").status_code == 200
    assert client.get("/signup").status_code == 200
    assert client.get("/login").status_code == 200


def test_guide_page_loads_and_is_linked_from_nav_and_footer(client):
    # 一般公開するサービスとして、操作マニュアル（使い方ガイド）を
    # 実際に使えるページとして用意している。
    guide_response = client.get("/guide")
    assert guide_response.status_code == 200
    guide_body = guide_response.get_data(as_text=True)
    assert "使い方ガイド" in guide_body
    assert "採寸プロフィール" in guide_body

    index_body = client.get("/").get_data(as_text=True)
    assert '/guide' in index_body


def test_guide_page_explains_the_measurement_clamp_warning(client):
    # 実際に発見した不具合(bust=160cmとbust=132.8cmで同一の型紙が生成される
    # のに警告が無かった問題)の修正で、結果画面に警告(measurement_warnings)
    # を表示するようになった。ガイドページの「よくある質問」も、採寸値の
    # 許容範囲(入力検証)とテンプレートの変形限界(クランプ)が別物である
    # ことを説明するよう更新されていることを確認する(ドキュメントの
    # ドリフト防止)。
    guide_body = client.get("/guide").get_data(as_text=True)
    assert "テンプレートを正確に変形できる範囲" in guide_body
    # round32: 結果画面の赤枠の見出しを実態に合わせて変えた
    # （そこに並ぶのは「採寸値が範囲外」だけでなく、ヒップが通らない・
    #  ダーツが収まらない等の型紙と体の食い違い全般のため）。ガイドが
    # 古い見出しを引用したままにならないよう、現在の文言も確認する。
    assert "縫う前に確認してください" in guide_body


def test_legal_pages_load(client):
    # アカウント登録・メール送信・決済を扱うサービスとして公開する以上、
    # 利用規約・プライバシーポリシー・運営者情報のページは必須。
    terms = client.get("/terms")
    assert terms.status_code == 200
    assert "利用規約" in terms.get_data(as_text=True)

    privacy = client.get("/privacy")
    assert privacy.status_code == 200
    assert "プライバシー" in privacy.get_data(as_text=True)

    legal = client.get("/legal")
    assert legal.status_code == 200
    assert "特定商取引法" in legal.get_data(as_text=True)


def test_signup_page_links_to_terms_and_privacy(client):
    body = client.get("/signup").get_data(as_text=True)
    assert '/terms' in body
    assert '/privacy' in body


def test_password_fields_load_the_show_password_toggle_script(client):
    """実際にログイン・サインアップ・パスワード再設定画面を動かして確認した
    実UX上の問題への対応(password_toggle.js参照): このアプリのサインアップ・
    パスワード再設定画面には確認用(2回目入力)のパスワード欄が無く、かつ
    入力内容を目視確認する手段も無かったため、タイプミスに気付けないまま
    送信し、直後のログインで自分が設定したはずのパスワードが通らない、
    という分かりにくい詰みに陥りやすかった。3画面すべてに表示切り替え
    トグル用のスクリプトが読み込まれていることを固定する。
    """
    signup_body = client.get("/signup").get_data(as_text=True)
    assert 'password_toggle.js' in signup_body
    assert 'type="password"' in signup_body

    login_body = client.get("/login").get_data(as_text=True)
    assert 'password_toggle.js' in login_body
    assert 'type="password"' in login_body

    # reset-password/<token> はtokenの有効性を検証しないGETなので、
    # ダミーのtoken文字列でページ自体の描画だけを確認できる。
    reset_body = client.get("/reset-password/dummy-token-for-rendering-test").get_data(as_text=True)
    assert 'password_toggle.js' in reset_body
    assert 'type="password"' in reset_body


def test_password_toggle_script_is_served_and_syntactically_valid_js(client):
    resp = client.get("/static/password_toggle.js")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    # 実際に3画面へトグルを追加する仕組み(input要素へトグルボタンを注入する
    # DOM操作)が壊れていないことの最低限の固定。壊れると表示上気付きにくい
    # (JSエラーで静かにトグルが出ないだけ)ため、キーとなる要素をテキストで
    # 確認しておく。
    assert 'password-toggle-btn' in body
    assert 'input[type="password"]' in body


def test_footer_links_to_legal_pages(client):
    body = client.get("/").get_data(as_text=True)
    assert '/terms' in body
    assert '/privacy' in body
    assert '/legal' in body


def test_unknown_html_route_returns_branded_404(client):
    response = client.get("/this-page-does-not-exist")
    assert response.status_code == 404
    assert "見つかりません" in response.get_data(as_text=True)


def test_unknown_api_style_request_returns_json_404(client):
    response = client.get("/this-page-does-not-exist", headers={"Accept": "application/json"})
    assert response.status_code == 404
    assert response.get_json()["ok"] is False


def test_internal_error_returns_branded_500_not_raw_traceback(client, monkeypatch):
    # 想定外の例外がHTMLページ経路で起きても、Werkzeugの生の例外ページや
    # スタックトレースがそのまま利用者に見えないことを確認する。
    def _boom():
        raise RuntimeError("boom")

    monkeypatch.setattr(app_module, "_daily_limit_for_plan", lambda plan_name: _boom())
    app_module.app.config["TESTING"] = False
    app_module.app.config["PROPAGATE_EXCEPTIONS"] = False
    try:
        response = client.get("/")
    finally:
        app_module.app.config["TESTING"] = True
    assert response.status_code == 500
    assert "内部エラー" in response.get_data(as_text=True)
    assert "RuntimeError" not in response.get_data(as_text=True)


def _profile_form(name="田中様"):
    return {
        "name": name, "bust": "84", "waist": "68", "hip": "92",
        "height": "160", "sleeve_length": "54", "shoulder_width": "37",
    }


def test_create_profile_requires_login(client):
    response = client.post("/api/profiles", data=_profile_form())
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_create_profile_and_appears_on_index_and_account(client):
    _signup(client)
    response = client.post("/api/profiles", data=_profile_form())
    assert response.status_code == 200
    data = response.get_json()
    assert data["ok"] is True
    assert data["profile"]["name"] == "田中様"

    index_body = client.get("/").get_data(as_text=True)
    assert "田中様" in index_body

    account_body = client.get("/account").get_data(as_text=True)
    assert "田中様" in account_body


def test_create_profile_rejects_blank_name(client):
    _signup(client)
    response = client.post("/api/profiles", data=_profile_form(name="  "))
    assert response.status_code == 400
    assert response.get_json()["ok"] is False


def test_create_profile_rejects_invalid_measurements(client):
    _signup(client)
    form = _profile_form()
    form["bust"] = "not-a-number"
    response = client.post("/api/profiles", data=form)
    assert response.status_code == 400


def test_delete_profile_removes_it_and_only_owner_can_delete(client):
    _signup(client, email="owner@example.com")
    created = client.post("/api/profiles", data=_profile_form()).get_json()
    profile_id = created["profile"]["id"]

    client.post("/logout")
    _signup(client, email="other@example.com")
    other_delete = client.post(f"/account/profiles/{profile_id}/delete", follow_redirects=True)
    assert "見つかりませんでした" in other_delete.get_data(as_text=True)

    client.post("/logout")
    _login(client, email="owner@example.com")
    own_delete = client.post(f"/account/profiles/{profile_id}/delete", follow_redirects=True)
    assert "削除しました" in own_delete.get_data(as_text=True)
    assert "田中様" not in client.get("/account").get_data(as_text=True)


def test_profile_name_containing_script_tag_is_html_escaped_everywhere(client):
    # プロフィール名は利用者が自由に入力できるテキストなので、他の利用者が
    # 見るページにそのまま出力されるとXSSにつながる。ここでは実際に
    # <script>タグを含む名前を作成し、それを表示する経路(index/account の
    # 両画面のHTML、および/api/profilesのJSON応答)で、生のタグが混入して
    # いないことを検証する。JinjaのautoescapeはHTML側で常に有効なはずだが、
    # 「|safe」の付け忘れや、テンプレートを介さない文字列結合の追加などで
    # 将来壊れうるため、回帰テストとして固定する。
    _signup(client)
    malicious_name = "<script>alert(1)</script>"
    response = client.post("/api/profiles", data=_profile_form(name=malicious_name))
    assert response.status_code == 200

    # JSON応答はHTMLとして解釈されないので、ここは生の値のままでよい
    # (エスケープされていたらむしろそれ自体が別の不具合になる)。
    assert response.get_json()["profile"]["name"] == malicious_name

    index_body = client.get("/").get_data(as_text=True)
    account_body = client.get("/account").get_data(as_text=True)
    for body in (index_body, account_body):
        assert "<script>alert(1)</script>" not in body
        assert "&lt;script&gt;alert(1)&lt;/script&gt;" in body


# --- round5: 縫い代を辺ごとに設定可能に(seam_allowance_cm/hem_seam_allowance_cm) ---


def test_generate_without_seam_allowance_fields_uses_the_default(client):
    # 両方空欄(未入力)の従来通りの挙動: 全辺1.0cm一律。
    response = client.post("/api/generate", data=_valid_form())
    assert response.status_code == 200
    data = response.get_json()
    assert data["ok"] is True
    assert data["seam_allowance_cm"] == 1.0
    assert data["hem_seam_allowance_cm"] is None


def test_generate_supports_custom_seam_allowance_and_hem_allowance(client):
    form = _valid_form()
    form["seam_allowance_cm"] = "1.5"
    form["hem_seam_allowance_cm"] = "4.0"
    response = client.post("/api/generate", data=form)
    assert response.status_code == 200
    data = response.get_json()
    assert data["ok"] is True
    assert data["seam_allowance_cm"] == 1.5
    assert data["hem_seam_allowance_cm"] == 4.0

    svg_response = client.get(data["download"]["svg"])
    assert svg_response.status_code == 200
    pdf_response = client.get(data["download"]["pdf"])
    assert pdf_response.status_code == 200


def test_generate_rejects_out_of_range_seam_allowance(client):
    form = _valid_form()
    form["seam_allowance_cm"] = "10.0"  # MAX_SEAM_ALLOWANCE_CM(3.0cm)超え
    response = client.post("/api/generate", data=form)
    assert response.status_code == 400
    assert response.get_json()["ok"] is False


def test_generate_rejects_out_of_range_hem_seam_allowance(client):
    form = _valid_form()
    form["hem_seam_allowance_cm"] = "0.05"  # MIN_HEM_SEAM_ALLOWANCE_CM(0.3cm)未満
    response = client.post("/api/generate", data=form)
    assert response.status_code == 400
    assert response.get_json()["ok"] is False


def test_generate_rejects_non_numeric_seam_allowance(client):
    form = _valid_form()
    form["seam_allowance_cm"] = "abc"
    response = client.post("/api/generate", data=form)
    assert response.status_code == 400
    assert response.get_json()["ok"] is False


def test_index_page_has_seam_allowance_fields(client):
    body = client.get("/").get_data(as_text=True)
    assert 'name="seam_allowance_cm"' in body
    assert 'name="hem_seam_allowance_cm"' in body


# --- round5: DXF出力 ---------------------------------------------------------


def test_generate_response_includes_a_dxf_download_link(client):
    response = client.post("/api/generate", data=_valid_form())
    assert response.status_code == 200
    data = response.get_json()
    assert data["download"]["dxf"] == f"/download/{data['job_id']}/dxf"


def test_dxf_can_actually_be_downloaded_after_generate(client):
    import ezdxf

    response = client.post("/api/generate", data=_valid_form())
    data = response.get_json()

    dxf_response = client.get(data["download"]["dxf"])
    assert dxf_response.status_code == 200
    assert dxf_response.headers["Content-Disposition"].startswith("attachment")

    # 実際にezdxfで読み戻せる(=壊れたファイルではない)ことまで確認する。
    tmp_path = pathlib.Path(app_module.OUTPUT_DIR) / f"{data['job_id']}.dxf"
    doc = ezdxf.readfile(str(tmp_path))
    assert len(list(doc.modelspace())) > 0


def test_download_rejects_unsupported_format(client):
    response = client.post("/api/generate", data=_valid_form())
    data = response.get_json()
    response = client.get(f"/download/{data['job_id']}/exe")
    assert response.status_code == 400


# --- round5: 複数サイズの一括生成(サイズ展開) --------------------------------


def test_generate_multi_size_returns_a_result_per_size_and_a_zip_link(client):
    form = _valid_form()
    form["mode"] = "multi_size"
    form["sizes"] = ["S", "M", "L"]
    response = client.post("/api/generate", data=form)
    assert response.status_code == 200
    data = response.get_json()
    assert data["ok"] is True
    assert data["mode"] == "multi_size"
    assert data["sizes"] == ["S", "M", "L"]
    assert set(data["results"].keys()) == {"S", "M", "L"}
    for size in ("S", "M", "L"):
        assert data["results"][size]["part_count"] > 0
        assert data["results"][size]["download"]["svg"].startswith("/download/")
    assert data["download"]["zip"] == f"/download/{data['bundle_job_id']}/zip"
    assert isinstance(data["size_consistency_warnings"], list)


def test_generate_multi_size_reports_size_consistency_warnings_when_present(client):
    # round6で追加。engine/measurements.pyのdetect_dart_count_inconsistencies
    # docstringで実際に不整合が起きることを確認済みの体型を使う。
    form = _valid_form()
    form["bust"] = "70"
    form["waist"] = "50"
    form["hip"] = "70"
    form["skirt_style"] = "tight"
    form["sleeve_style"] = ""
    form["mode"] = "multi_size"
    form["sizes"] = ["XS", "S", "M", "L", "XL"]
    response = client.post("/api/generate", data=form)
    data = response.get_json()
    assert data["ok"] is True
    assert isinstance(data["size_consistency_warnings"], list)


def test_generate_multi_size_zip_can_actually_be_downloaded(client):
    import zipfile

    form = _valid_form()
    form["mode"] = "multi_size"
    form["sizes"] = ["S", "M"]
    response = client.post("/api/generate", data=form)
    data = response.get_json()

    zip_response = client.get(data["download"]["zip"])
    assert zip_response.status_code == 200
    assert zip_response.headers["Content-Disposition"].startswith("attachment")

    tmp_path = pathlib.Path(app_module.OUTPUT_DIR) / f"{data['bundle_job_id']}.zip"
    with zipfile.ZipFile(str(tmp_path)) as zf:
        names = set(zf.namelist())
    for size in ("S", "M"):
        for ext in ("svg", "pdf", "dxf"):
            assert f"{size}/{size}.{ext}" in names


def test_generate_multi_size_individual_size_download_also_works(client):
    # サイズ展開の各サイズも、それぞれ独立したjob_idを持つ通常のジョブと
    # 同じ経路でダウンロードできる(ZIPと個別リンクの両方を提供する設計)。
    form = _valid_form()
    form["mode"] = "multi_size"
    form["sizes"] = ["M"]
    response = client.post("/api/generate", data=form)
    data = response.get_json()

    svg_response = client.get(data["results"]["M"]["download"]["svg"])
    assert svg_response.status_code == 200


def test_generate_multi_size_rejects_empty_size_selection(client):
    form = _valid_form()
    form["mode"] = "multi_size"
    response = client.post("/api/generate", data=form)
    assert response.status_code == 400
    assert response.get_json()["ok"] is False


def test_generate_multi_size_rejects_unknown_size_name(client):
    form = _valid_form()
    form["mode"] = "multi_size"
    form["sizes"] = ["M", "XXL"]
    response = client.post("/api/generate", data=form)
    assert response.status_code == 400


def test_generate_multi_size_only_counts_as_one_generation_toward_the_daily_limit(client):
    # 3サイズ生成しても、日次生成回数への課金は1回分のみ(app.py側の設計)。
    form = _valid_form()
    form["mode"] = "multi_size"
    form["sizes"] = ["S", "M", "L"]
    response = client.post("/api/generate", data=form)
    data = response.get_json()
    assert data["usage"]["used_today"] == 1


def test_index_page_has_multi_size_mode_option(client):
    body = client.get("/").get_data(as_text=True)
    assert 'value="multi_size"' in body
    assert 'name="sizes"' in body


# --- round7: カスタムグレーディングルール対応(API層) -----------------------

def test_generate_multi_size_with_custom_grade_cm_is_applied(client):
    form = _valid_form()
    form["mode"] = "multi_size"
    form["sizes"] = ["S", "M", "L"]
    form["grade_bust"] = "6.0"
    response = client.post("/api/generate", data=form)
    assert response.status_code == 200
    data = response.get_json()
    assert data["ok"] is True
    assert data["custom_grade_cm_applied"] is True
    assert data["grade_cm_used"]["bust"] == 6.0
    # 上書きしなかった項目は既定値のまま。
    assert data["grade_cm_used"]["waist"] == 4.0


def test_generate_multi_size_without_custom_grade_cm_fields_uses_default(client):
    form = _valid_form()
    form["mode"] = "multi_size"
    form["sizes"] = ["S", "M", "L"]
    response = client.post("/api/generate", data=form)
    data = response.get_json()
    assert data["custom_grade_cm_applied"] is False
    assert data["grade_cm_used"]["bust"] == 4.0


def test_generate_multi_size_custom_grade_cm_rejects_out_of_range_value(client):
    form = _valid_form()
    form["mode"] = "multi_size"
    form["sizes"] = ["S", "M"]
    form["grade_bust"] = "83.0"  # 採寸値そのものを誤入力したケースを模す
    response = client.post("/api/generate", data=form)
    assert response.status_code == 400
    assert response.get_json()["ok"] is False


def test_generate_multi_size_custom_grade_cm_rejects_non_numeric_value(client):
    form = _valid_form()
    form["mode"] = "multi_size"
    form["sizes"] = ["S", "M"]
    form["grade_bust"] = "abc"
    response = client.post("/api/generate", data=form)
    assert response.status_code == 400
    assert response.get_json()["ok"] is False


def test_generate_multi_size_custom_grade_cm_does_not_leak_into_single_size_mode(client):
    # grade_*フィールドが送られても、multi_size以外のモードでは無視される
    # (単体生成にはグレーディングという概念自体が無いため)。
    form = _valid_form()
    form["mode"] = "manual"
    form["grade_bust"] = "6.0"
    response = client.post("/api/generate", data=form)
    assert response.status_code == 200
    data = response.get_json()
    assert data["ok"] is True
    assert "grade_cm_used" not in data


def test_cleanup_removes_old_dxf_and_zip_files_too(client):
    # round5でexport_pattern/export_multi_size_bundleが.dxf/.zipを
    # generated/に書き出すようになったが、_cleanup_old_outputs()の対象
    # 拡張子リストへの追加を忘れていたため、この2つは1時間経っても永久に
    # 削除されない実バグがあった(既にsvg/pdfでは掃除される)。回帰テスト。
    import os
    import time

    output_dir = app_module.OUTPUT_DIR
    old_names = ["old.svg", "old.pdf", "old.dxf", "old.zip"]
    keep_name = "keep.txt"  # 対象外の拡張子は触らないことも併せて確認する
    for name in old_names + [keep_name]:
        path = os.path.join(output_dir, name)
        with open(path, "w") as f:
            f.write("x")
        old_time = time.time() - app_module.OUTPUT_TTL_SECONDS - 60
        os.utime(path, (old_time, old_time))

    app_module._cleanup_old_outputs()

    for name in old_names:
        assert not os.path.exists(os.path.join(output_dir, name)), f"{name} が削除されていない"
    assert os.path.exists(os.path.join(output_dir, keep_name))


# ---------------------------------------------------------------------------
# round8で追加: アカウント削除・データエクスポート
# ---------------------------------------------------------------------------

def test_account_export_requires_login(client):
    response = client.get("/account/export")
    assert response.status_code == 302
    assert "login" in response.headers["Location"]


def test_account_export_returns_expected_json(client):
    _signup(client, email="export@example.com")
    client.post("/api/profiles", data={
        "name": "顧客A", "bust": "84", "waist": "68", "hip": "92",
        "height": "160", "sleeve_length": "54", "shoulder_width": "37",
    })
    response = client.get("/account/export")
    assert response.status_code == 200
    assert "attachment" in response.headers["Content-Disposition"]
    data = response.get_json()
    assert data["account"]["email"] == "export@example.com"
    assert len(data["measurement_profiles"]) == 1
    assert data["organization"] is None


def test_account_delete_page_requires_login(client):
    response = client.get("/account/delete")
    assert response.status_code == 302


def test_account_delete_rejects_wrong_password(client):
    _signup(client, email="wrongpass@example.com", password="correct-password-123")
    response = client.post(
        "/account/delete", data={"password": "not-the-right-password"}, follow_redirects=True
    )
    assert "正しくない" in response.get_data(as_text=True)
    # まだログインしたままであることを確認する(削除されていない)。
    account_response = client.get("/account")
    assert account_response.status_code == 200


def test_account_delete_removes_account_and_logs_out(client):
    _signup(client, email="deleteme@example.com", password="delete-password-123")
    response = client.post(
        "/account/delete", data={"password": "delete-password-123"}, follow_redirects=True
    )
    assert response.status_code == 200
    assert "削除しました" in response.get_data(as_text=True)
    # ログアウトさせられているため、/accountはログイン画面へリダイレクトされる。
    account_response = client.get("/account")
    assert account_response.status_code == 302
    assert "login" in account_response.headers["Location"]


def test_account_delete_allows_re_signup_with_same_email(client):
    _signup(client, email="reuse@example.com", password="delete-password-123")
    client.post("/account/delete", data={"password": "delete-password-123"})
    response = _signup(client, email="reuse@example.com", password="new-password-456")
    assert response.status_code == 200
    assert response.request.path == "/account"


# ---------------------------------------------------------------------------
# round8で追加: 生成履歴からの再生成
# ---------------------------------------------------------------------------

def test_regenerate_job_recreates_pattern_from_stored_spec(client, monkeypatch):
    _signup(client, email="regen@example.com")
    generate_response = client.post("/api/generate", data=_valid_form())
    assert generate_response.status_code == 200
    job_id = generate_response.get_json()["job_id"]

    account_html = client.get("/account").get_data(as_text=True)
    assert f"/account/jobs/{job_id}/regenerate" in account_html

    used_before = app_module.db.usage_today("user:1", app_module._today_str())
    regen_response = client.post(f"/account/jobs/{job_id}/regenerate", follow_redirects=True)
    assert regen_response.status_code == 200
    assert "再生成しました" in regen_response.get_data(as_text=True)
    used_after = app_module.db.usage_today("user:1", app_module._today_str())
    assert used_after == used_before + 1  # 再生成も通常生成と同じく1回分消費する


def test_regenerate_job_rejects_other_users_job(client):
    _signup(client, email="owner_of_job@example.com")
    generate_response = client.post("/api/generate", data=_valid_form())
    job_id = generate_response.get_json()["job_id"]
    client.post("/logout")

    _signup(client, email="not_the_owner@example.com")
    response = client.post(f"/account/jobs/{job_id}/regenerate", follow_redirects=True)
    assert "再生成できません" in response.get_data(as_text=True)


def test_regenerate_job_rejects_illustration_jobs(client, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    _signup(client, email="illustration_regen@example.com")
    from PIL import ImageDraw

    image = Image.new("RGB", (400, 800), "white")
    ImageDraw.Draw(image).rectangle([100, 150, 300, 700], fill="black")
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    buf.seek(0)
    form = _valid_form()
    form["mode"] = "illustration"
    generate_response = client.post(
        "/api/generate",
        data={**form, "illustration": (buf, "test.png")},
        content_type="multipart/form-data",
    )
    assert generate_response.status_code == 200
    job_id = generate_response.get_json()["job_id"]
    response = client.post(f"/account/jobs/{job_id}/regenerate", follow_redirects=True)
    assert "再生成できません" in response.get_data(as_text=True)


def test_regenerate_job_respects_daily_usage_limit(client, monkeypatch):
    monkeypatch.setitem(app_module.store.DEFAULT_DAILY_LIMITS, "free", 1)
    _signup(client, email="regenlimit@example.com")
    generate_response = client.post("/api/generate", data=_valid_form())
    job_id = generate_response.get_json()["job_id"]
    response = client.post(f"/account/jobs/{job_id}/regenerate", follow_redirects=True)
    assert "上限" in response.get_data(as_text=True)


# ---------------------------------------------------------------------------
# round8で追加: APIキー・B2Bプログラマティックapi
# ---------------------------------------------------------------------------

def _extract_issued_api_key(html: str) -> str:
    match = re.search(r"(pf_live_[A-Za-z0-9_\-]+)", html)
    assert match, "発行されたAPIキーがflashメッセージから見つからない"
    return match.group(1)


def test_create_and_use_and_revoke_api_key(client):
    _signup(client, email="apikeyflow@example.com")
    create_response = client.post(
        "/account/api-keys", data={"name": "連携用キー"}, follow_redirects=True
    )
    raw_key = _extract_issued_api_key(create_response.get_data(as_text=True))

    generate_response = client.post(
        "/api/v1/generate",
        data=_valid_form(),
        headers={"Authorization": f"Bearer {raw_key}"},
    )
    assert generate_response.status_code == 200
    data = generate_response.get_json()
    assert data["ok"] is True
    assert "download" in data

    account_html = client.get("/account").get_data(as_text=True)
    key_id_match = re.search(r"/account/api-keys/(\d+)/revoke", account_html)
    assert key_id_match
    client.post(f"/account/api-keys/{key_id_match.group(1)}/revoke")

    revoked_response = client.post(
        "/api/v1/generate",
        data=_valid_form(),
        headers={"Authorization": f"Bearer {raw_key}"},
    )
    assert revoked_response.status_code == 401


def test_api_v1_generate_rejects_missing_or_malformed_auth_header(client):
    no_header = client.post("/api/v1/generate", data=_valid_form())
    assert no_header.status_code == 401

    bad_header = client.post(
        "/api/v1/generate", data=_valid_form(), headers={"Authorization": "Bearer not-a-real-key"}
    )
    assert bad_header.status_code == 401


def test_create_api_key_requires_login(client):
    response = client.post("/account/api-keys", data={"name": "x"})
    assert response.status_code == 302
    assert "login" in response.headers["Location"]


# ---------------------------------------------------------------------------
# round8で追加: 組織アカウント
# ---------------------------------------------------------------------------

def _last_org_invite_token() -> str:
    """テスト用メーラー(RecordingMailer)に記録された、直近の招待メール本文
    からトークンを取り出す(is_console=Falseのため、画面上のflash表示では
    なく実際に「送信された」メール本文から取得する。tests/test_billing_and_email.py
    の_extract_url等と同じ考え方)。"""
    body = app_module.mail.sent[-1]["body"]
    match = re.search(r"/org/invites/([A-Za-z0-9_\-]+)", body)
    assert match, "招待メール本文にトークンURLが見当たらない"
    return match.group(1)


def test_create_organization_and_invite_flow(client):
    _signup(client, email="orgowner@example.com")
    create_response = client.post("/org/create", data={"name": "テスト組織"}, follow_redirects=True)
    assert "テスト組織" in create_response.get_data(as_text=True)

    client.post("/org/invite", data={"email": "orgmember@example.com"})
    token = _last_org_invite_token()
    client.post("/logout")

    _signup(client, email="orgmember@example.com")
    accept_response = client.post(f"/org/invites/{token}/accept", follow_redirects=True)
    assert "参加しました" in accept_response.get_data(as_text=True)
    member_account_html = client.get("/account").get_data(as_text=True)
    assert "テスト組織" in member_account_html


def test_organization_members_share_usage_pool(client, monkeypatch):
    """組織のメンバーは利用回数の上限を共有する(store.pyの組織アカウントの
    節に明記した意図的な設計。app_module._current_owner_key参照)。

    オーナー(1つ目のブラウザセッション)が上限(1回/日)を使い切った後、
    別セッション(=別ブラウザ・別人)としてログインしたメンバーが同じ日に
    生成しようとしても429になることを確認する。owner_keyが個人単位の
    'user:<id>'ではなく組織単位の'org:<id>'になっているために初めて
    起こりうる挙動であり、組織機能が無ければオーナーとメンバーの利用回数は
    互いに影響しない別々のカウンタになるはずである。
    """
    monkeypatch.setitem(app_module.store.DEFAULT_DAILY_LIMITS, "free", 1)
    _signup(client, email="poolowner@example.com")
    client.post("/org/create", data={"name": "プール共有組織"})
    client.post("/org/invite", data={"email": "poolmember@example.com"})
    token = _last_org_invite_token()

    # オーナーが1回生成して、組織の1日の上限(1回)を使い切る。
    owner_generate = client.post("/api/generate", data=_valid_form())
    assert owner_generate.status_code == 200
    client.post("/logout")

    # 別人(メンバー)としてログインし直しても、同じ組織の上限を共有している
    # ため、まだ1回も自分では生成していないのに429になる。
    _signup(client, email="poolmember@example.com")
    client.post(f"/org/invites/{token}/accept")
    member_generate = client.post("/api/generate", data=_valid_form())
    assert member_generate.status_code == 429


def test_only_owner_can_invite_or_change_org_plan(client):
    _signup(client, email="realowner@example.com")
    client.post("/org/create", data={"name": "権限テスト組織"})
    client.post("/org/invite", data={"email": "justamember@example.com"})
    token = _last_org_invite_token()
    client.post("/logout")
    _signup(client, email="justamember@example.com")
    client.post(f"/org/invites/{token}/accept")

    invite_attempt = client.post(
        "/org/invite", data={"email": "sneaky@example.com"}, follow_redirects=True
    )
    assert "オーナーのみ" in invite_attempt.get_data(as_text=True)

    upgrade_attempt = client.post("/account/upgrade", follow_redirects=True)
    assert "オーナーのみ" in upgrade_attempt.get_data(as_text=True)


def test_a_user_already_in_an_organization_cannot_create_another(client):
    _signup(client, email="doubleorg@example.com")
    client.post("/org/create", data={"name": "組織イチ"})
    response = client.post("/org/create", data={"name": "組織ニ"}, follow_redirects=True)
    assert "既に" in response.get_data(as_text=True)


def test_org_disband_returns_members_to_individual_plan_and_usage(client, monkeypatch):
    monkeypatch.setitem(app_module.store.DEFAULT_DAILY_LIMITS, "free", 1)
    _signup(client, email="disbandowner@example.com")
    client.post("/org/create", data={"name": "解散予定組織"})
    client.post("/account/upgrade")  # 組織をProへ(モックモード)
    client.post("/org/disband", follow_redirects=True)

    account_html = client.get("/account").get_data(as_text=True)
    assert "解散予定組織" not in account_html
    # 組織を解散したので、個人のFreeプランの上限が適用される(組織Pro時の
    # 無制限には戻らない)。
    first = client.post("/api/generate", data=_valid_form())
    second = client.post("/api/generate", data=_valid_form())
    assert first.status_code == 200
    assert second.status_code == 429
