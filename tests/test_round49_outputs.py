"""round49: 配っているファイルを1つずつ開いて見つけたもの。

round48まで、ダウンロードできるものは **A4分割PDFしか開いていなかった**。
round49はDXF・プロジェクター投影用PDF・SVG・複数サイズのZIPを実際に開き、
PDFの「買い物メモ」「縫う順番」も読んだ。

見つかったもの:

  1. **複数サイズのZIPで、A4分割PDFが消えていた。**
     ZIP内の名前を**拡張子だけ**から `f"{size}/{size}{ext}"` と組み立てて
     いたため、round39で増えたプロジェクター投影用(これも`.pdf`)と
     衝突し、1サイズにつき同名の`.pdf`が2件書かれていた。実測:

         L/L.pdf  153,663バイト … A4分割PDF(印刷して貼り合わせる本命)
         L/L.pdf   23,201バイト … プロジェクター投影用(145×196cmの1ページ)

     ZIPは同名を2件持てるので書き込みは通り、Pythonも
     `UserWarning: Duplicate name` を出すだけ。しかし**展開すると後勝ち**
     なので、手元に残るのは投影用だけになり、家庭用プリンタで刷るための
     PDFが消えていた。実際に展開して確かめた。
  2. **round46の直しが半分だった。** 「裏地は表地より2cm短い」という
     決め打ちを`engine/lining.py`で実測値に直したが、**同じ主張が
     `engine/assembly.py`にも手書きされていて**、そちらは残っていた。
     既定(裾1.0cm)でPDFに刷られる手順に「表地より2cm短く裁ってあります」
     ——1.0から2.0は引けない——と出続けていた。
  3. **サイズ展開モードで裏地が黙って無視されていた。** 画面には
     「⑥ 裏地（任意）」が出ていて押せるのに、`generate_multi_size`は
     liningを受け取らない。実測で、複数サイズ+裏地onの応答は
     `lining`がnull・注記も警告も無しだった。
"""

import os
import pathlib
import re
import zipfile

import pytest

import app as app_module
from engine import pdf_export
from engine.lining import (LINING_HEM_REDUCTION_CM, hem_reduction_cm,
                            hem_reduction_sentence, lining_hem_allowance_cm)

APP_JS = (pathlib.Path(app_module.BASE_DIR) / "web" / "static" / "app.js").read_text(encoding="utf-8")


# --- 1. ZIPの中で名前が衝突しないこと ---------------------------------------

def test_every_format_gets_its_own_name_in_the_bundle(tmp_path):
    """同じ拡張子の形式どうしが、ZIP内で同じ名前にならないこと。"""
    files = {}
    for fmt, ext in (("svg", ".svg"), ("pdf", ".pdf"),
                     ("dxf", ".dxf"), ("projector", ".pdf")):
        path = tmp_path / f"job_{fmt}{ext}"
        path.write_bytes(fmt.encode() * 100)
        files[fmt] = str(path)

    zip_path = pdf_export.export_multi_size_bundle(
        {"M": files, "L": files}, str(tmp_path), "bundle")
    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
    assert len(names) == len(set(names)), f"同名のものがあります: {names}"
    assert "M/M.pdf" in names and "M/M_projector.pdf" in names
    assert "M/M.svg" in names and "M/M.dxf" in names


def test_extracting_the_bundle_keeps_the_printable_pdf(tmp_path):
    """展開したあとも、A4分割PDFが残っていること。

    同名で2件入っていると、展開時に後から書いた方が上書きする。
    round48まで、残るのはプロジェクター投影用の方だった。
    """
    src = tmp_path / "src"
    src.mkdir()
    tiled = src / "job.pdf"
    tiled.write_bytes(b"A4-TILED" * 1000)          # 本命(大きい)
    projector = src / "job_projector.pdf"
    projector.write_bytes(b"PROJECTOR")            # 投影用(小さい)
    outputs = {"pdf": str(tiled), "projector": str(projector)}

    zip_path = pdf_export.export_multi_size_bundle(
        {"M": outputs}, str(tmp_path), "bundle")
    dest = tmp_path / "unzipped"
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(dest)
    assert (dest / "M" / "M.pdf").read_bytes() == tiled.read_bytes(), \
        "展開するとA4分割PDFが投影用で上書きされています"
    assert (dest / "M" / "M_projector.pdf").read_bytes() == projector.read_bytes()


def test_a_new_format_that_would_collide_is_refused(tmp_path):
    """名前が衝突する形式が増えたら、黙って上書きせず止まること。

    round48まではこの見張りが無く、「同名2件」が3ラウンド分そのまま
    配られていた。
    """
    a = tmp_path / "a.pdf"; a.write_bytes(b"a")
    b = tmp_path / "b.pdf"; b.write_bytes(b"b")
    original = dict(pdf_export._BUNDLE_NAME_SUFFIX)
    try:
        # round58まで、名前表に無い形式は `_<形式名>` という保険の名前で
        # 通っていた。衝突はしないので、この行は通ったまま
        # `S_all_fabrics_pdf.pdf` のような名前を配ることができた。
        # いまは名前表に載っていること自体を求めるので、ここで登録する。
        pdf_export._BUNDLE_NAME_SUFFIX["poster"] = "_poster"
        zip_path = pdf_export.export_multi_size_bundle(
            {"M": {"pdf": str(a), "poster": str(b)}}, str(tmp_path), "ok")
        with zipfile.ZipFile(zip_path) as zf:
            assert sorted(zf.namelist()) == ["M/M.pdf", "M/M_poster.pdf"]
        # 接尾辞を同じにすると衝突するので、そのときははっきり止まる。
        pdf_export._BUNDLE_NAME_SUFFIX["poster"] = ""
        with pytest.raises(ValueError, match="衝突"):
            pdf_export.export_multi_size_bundle(
                {"M": {"pdf": str(a), "poster": str(b)}}, str(tmp_path), "ng")
    finally:
        pdf_export._BUNDLE_NAME_SUFFIX.clear()
        pdf_export._BUNDLE_NAME_SUFFIX.update(original)


# --- 2. 裏地の裾の説明が、1か所から出ていること ------------------------------

@pytest.mark.parametrize("outer, lining_hem, removed", [
    (4.0, 2.0, 2.0), (3.0, 1.0, 2.0), (2.0, 0.0, 2.0),   # 出典の実例
    (1.0, 0.0, 1.0), (0.5, 0.0, 0.5),                      # 引き切れない側
])
def test_the_reduction_is_computed_in_one_place(outer, lining_hem, removed):
    assert lining_hem_allowance_cm(outer) == pytest.approx(lining_hem)
    assert hem_reduction_cm(outer) == pytest.approx(removed)
    sentence = hem_reduction_sentence(outer)
    assert f"表地より{removed:g}cm短く" in sentence, sentence
    if removed < LINING_HEM_REDUCTION_CM:
        assert "規則どおりの2cmは引けていません" in sentence
    else:
        assert "規則どおりの2cmは引けていません" not in sentence


def test_the_sewing_steps_use_that_same_sentence():
    """縫う順番が、裏地の裾の説明を自分で書き直していないこと。

    round46は`lining_notes`だけを直したので、ここに手書きされた
    「表地より2cm短く」が取り残され、PDFに刷られる手順で嘘が残っていた。
    """
    source = (pathlib.Path(app_module.BASE_DIR) / "engine" / "assembly.py").read_text(encoding="utf-8")
    assert "hem_reduction_sentence(" in source
    # コメントを除いてから見る。**経緯を説明したコメントにその語が出てくる**
    # ので、そのまま探すと自分の説明文を不具合として報告してしまう
    # (round45でも同じ間違いをした)。
    code = "\n".join(re.sub(r"#.*$", "", line) for line in source.splitlines())
    assert "表地より2cm短く" not in code, \
        "縫う順番に「2cm」が手書きで戻っています"


def test_the_hem_step_says_how_deep_each_fold_is():
    """三つ折りの折り幅(=縫い代の半分)を書くこと。

    既定の1cmだと5mmずつになる。書かないと「三つ折りにしてください」
    だけが残って手が止まる。
    """
    from engine.measurements import Measurements
    from engine.pipeline import PatternForgePipeline, build_garment_spec

    pipeline = PatternForgePipeline()
    measurements = Measurements(bust=88, waist=72, hip=96, height=162,
                                sleeve_length=55, shoulder_width=38)
    spec = build_garment_spec(neckline="round_neck", sleeve_style="straight",
                              skirt_style="flare")
    for hem, fold in ((None, 0.5), (4.0, 2.0)):
        result = pipeline.generate_from_selection(
            garment_spec=spec, measurements=measurements, skip_export=True,
            lining=True, hem_seam_allowance_cm=hem)
        step = [s for s in result.assembly_steps() if "裾" in s.title][0]
        assert f"折り幅は{fold:g}cmずつ" in step.detail, step.detail
        # 既定(1cm)では、2cm引けなかったことも書く。
        if hem is None:
            assert "規則どおりの2cmは引けていません" in step.detail


# --- 3. サイズ展開で裏地を頼まれたら、やらないことを言う ---------------------

def test_the_lining_section_is_shown_in_every_mode(client):
    """裏地の節が、どのモードでも出ていること。

    【round49がここで何をしていたか】`generate_multi_size` がliningを
    受け取らなかったため、サイズ展開モードだけこの節を隠していた。
    押せるのに黙って無視される欄を無くすための、**回避**である。

    【round58で何が変わったか】サイズ展開でも裏地を引けるようにしたので、
    隠す理由が無くなった。回避の側(隠す・チェックを外す)が残っていると、
    直ったのに使えないままになるので、残っていないことを見る。
    """
    body = client.get("/").get_data(as_text=True)
    assert 'id="lining-section"' in body
    assert "liningSection" not in APP_JS, \
        "裏地の節をモードで隠すコードが残っています"


def test_a_multi_size_request_with_lining_actually_draws_it(client):
    """APIで裏地を頼まれたら、**引くこと**。

    round49はここで「引いていません」と断っていた(頼まれたのにやらな
    かったことは必ず言う、という方針)。round58で引けるようになったので、
    断り書きではなく出来上がりを見る。
    """
    form = {
        "bust": "84", "waist": "68", "hip": "92", "height": "160",
        "sleeve_length": "54", "shoulder_width": "37",
        "mode": "multi_size", "sizes": "S",
        "neckline": "round_neck", "sleeve_style": "straight",
        "skirt_style": "flare", "lining": "1",
    }
    data = client.post("/api/generate", data=form).get_json()
    assert data["ok"] is True
    notes = data.get("design_notes") or []
    assert not any("裏地の型紙は引いていません" in n for n in notes), notes
    assert data["results"]["S"]["lining"], "裏地が引かれていません"


def test_a_multi_size_request_without_lining_says_nothing(client):
    """頼まれていないことまで並べないこと(毎回出ると読み飛ばされる)。"""
    form = {
        "bust": "84", "waist": "68", "hip": "92", "height": "160",
        "sleeve_length": "54", "shoulder_width": "37",
        "mode": "multi_size", "sizes": "S",
        "neckline": "round_neck", "sleeve_style": "straight",
        "skirt_style": "flare",
    }
    data = client.post("/api/generate", data=form).get_json()
    assert (data.get("design_notes") or []) == []


def test_the_note_is_shown_on_screen(client):
    """その注記を映す箱が画面にあり、JSが埋めること。"""
    body = client.get("/").get_data(as_text=True)
    assert 'id="multi-size-note"' in body
    assert 'id="multi-size-note-list"' in body
    assert 'document.getElementById("multi-size-note")' in APP_JS
    assert 'multiNoteBox.classList.toggle("hidden"' in APP_JS
