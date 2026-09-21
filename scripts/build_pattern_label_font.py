"""build_pattern_label_font.py — A4分割PDFに部品名・ページ情報を描くための
日本語フォント(サブセット)を再生成するスクリプト。

なぜ必要か
----------
reportlab(A4分割PDF出力に使用)の組み込み標準フォント(Helvetica等)は
Latin文字しか持たず、日本語(漢字・かな)を描画できない。以前は
render_a4_pdf()内のページ情報テキストに日本語の「枚」という文字が
そのまま渡されており、実際に生成したPDFをレンダリングして確認したところ
豆腐(■)として表示される実バグがあった。また、SVGプレビューには表示され
ている「左脚/右脚/前/後」などのパーツ識別ラベルが、実際に印刷して裁断に
使うA4分割PDF側には一切描かれていない(パーツ名が無いと、貼り合わせ後に
どの裁断線がどのパーツか分からなくなる)という機能不足もあった。

この2点を修正するには、reportlab側でも日本語グリフを描画できるフォント
が必要。ただしOS標準で入っている「Noto Sans CJK」はCFF(PostScript輪郭)
形式のOpenTypeで、reportlab.pdfbase.ttfonts.TTFontはCFF輪郭を読めない
("postscript outlines are not supported"で例外になる)。そこで、TrueType
輪郭を持つIPAゴシック(ipag.ttf, IPAフォントライセンスv1.0で配布)から、
実際にアプリが生成しうる文字だけを抜き出したサブセットを作り、
engine/assets/pattern_label_ja_subset.ttf として同梱している
(フルセットは10MB超あるが、サブセットは数十KB程度)。

ライセンスについて
------------------
IPAフォントライセンスv1.0 第3条1項に基づき、派生プログラム(このサブセット)
を再配布する場合は、(a)派生プログラム自体、(b)派生プログラムをさらに加工
するために使えるファイル、を一緒に配布する必要がある。本スクリプトが(b)に
相当する(=このスクリプトと下記の文字リストがあれば、いつでも同じ手順で
サブセットを再構築・変更できる)。ライセンス全文は
engine/assets/PATTERN_LABEL_FONT_LICENSE.txt に同梱している。
また同条項により、派生プログラムのフォント名・ファイル名に元プログラム
("IPAゴシック"/"ipag"等)と同一または類似の名称を使ってはならないため、
`pattern_label_ja_subset.ttf` という名称にしている。

前提: Debian/Ubuntu系で `apt-get install fonts-ipafont-gothic` 済みで
/usr/share/fonts/opentype/ipafont-gothic/ipag.ttf が存在すること、
および `pip install fonttools` 済みであること(本番の実行時には不要。
このビルドスクリプトを動かす時だけ必要)。

使い方:
    python3 scripts/build_pattern_label_font.py
"""
from __future__ import annotations
import subprocess
import sys
from pathlib import Path

# 実際にengine/pdf_export.pyがA4分割PDFへ描画する文字だけを対象にした
# 最小限のサブセット。ASCII全体とひらがな・カタカナ全域は「将来パーツ種や
# ラベルが増えても、ある程度は追加のフォント再構築なしで済む」ための
# 余裕分。漢字は現時点でPAIR_LABELS(左/右/脚/前/後)・ダーツ注記(本)・
# ページラベル(枚)・回転注記(度/回/転・布/目/確/認)・空タイル注記
# (型/紙/面)・配置不能パーツ警告(含/不/完/全/配/置/採/寸/見/直)で
# 実際に使われているものだけを明示的に列挙している。新しい漢字を使う
# ラベルを追加した場合は、ここに追記して本スクリプトを再実行すること
# (足りないと、その文字だけが抜けて空白になる。クラッシュはしない。実際に
# 「布目確認」の「布」「目」、「この面に型紙なし」の「型」「紙」「面」を
# 抜け漏れさせてしまい、テスト(tests/test_pdf_export.py内の
# test_jp_label_font_contains_every_character_the_pdf_actually_draws)で
# 検出して追加した。配置不能パーツ警告(このコメントの少し下、
# render_a4_pdf/render_layout_svg参照)を追加した際も、最初は「不完全」等の
# 未収録の漢字を使った文言を書いてしまい、実際に生成したPDFをpypdfで
# テキスト抽出して初めてヌル文字に化けていることに気付いた。このスクリプト
# で再ビルドし、このリストに追記して修正した)。
# 描画する固定文言そのものは engine/pdf_export.py の PDF_STATIC_TEXTS に
# 集約されている。ここではそれを読み込んで必要な文字を自動的に集めるため、
# 「文言を足したのにこのリストを更新し忘れて、文字が黙って消える」という
# round11で実際に起きた事故が構造的に起こらないようにしている。
# (REQUIRED_KANJIは、PDF_STATIC_TEXTS以外の箇所で使う可能性のある漢字の
#  保険として残す。)
# round31: 裁ち方の指示(engine/cutting.py)で「表地/裁/要/接着芯」を使う。
REQUIRED_KANJI = "左右脚前後本枚度回転確認布目型紙面含不完全配置採寸見直表地裁要接着芯"

#: round36で追加。**この製品が利用者に例として示している名前**の文字。
#:
#: カスタムパーツの名前は利用者の自由入力なので、全部を先回りして収録する
#: ことはできない(それをやると全漢字が要り、フォントが10MB超になる)。
#: 収録外の文字は`engine/pipeline.py`の`_unprintable_label_warnings`が
#: 「型紙には印字されません」と開示する——それが恒久的な受け皿である。
#:
#: ただし、**製品自身が「例: マント・翼・肩当て・装甲プレート」と勧めて
#: おきながら、その通りに入力すると文字が消える**のは筋が通らない。
#: 実測(round36)では、勧めている6語のうちマント以外の5語すべてで文字が
#: 落ちていた(翼→空、装甲プレート→「プレート」、肩当て→「肩て」、
#: 小道具→「小」)。画面(web/templates/index.html)と入力欄のプレース
#: ホルダーに出す例だけは、必ず印字できる状態にしておく。
#: 例を増やすときは、ここにも文字を足すこと。
SUGGESTED_CUSTOM_PANEL_KANJI = "翼肩当胸装甲小道具"

#: round36で追加。`engine/pipeline.py`がパーツ名に**自分で付け足す**文字。
#:
#: カスタムパーツで「左右反転パーツも作る」を選ぶと、2枚目のラベルは
#: `f"{label}(反転)"`(build_custom_panel_requests)になる。この「反」は
#: これまでどの収集対象(part_names/cutting/assembly/PDF_STATIC_TEXTS)にも
#: 入っておらず、実測では型紙に「翼 左(転)」と印字されていた——
#: **利用者の入力ではなく、エンジン自身が作った名前が化けていた**。
#: 利用者にはどうしようもないので、開示ではなく収録で直す。
#: (再発防止は tests/test_round36_fixes.py の
#:  test_every_name_the_engine_itself_generates_is_printable。)
ENGINE_GENERATED_LABEL_KANJI = "反転"


def _part_name_chars() -> set:
    """engine/part_names.py の日本語パーツ名に出てくる文字を集める(round32)。

    round31まで型紙に印字されるパーツ名は英語識別子だったので、必要な
    漢字は「左右脚前後」程度で足りていた。round32で日本語名にした結果、
    「身頃」「衿」「袖」「脇」「中央」などが**実際に印刷される**ように
    なった。1文字でも欠けると、その字だけ黙って空白になる(クラッシュ
    しない)ので、辞書からそのまま集める——ここで自動的に集めておけば、
    パーツやバリエーションを増やしたときに追記を忘れようがない。
    """
    import ast

    source_path = Path(__file__).resolve().parent.parent / "engine" / "part_names.py"
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    chars: set = set()
    for node in ast.walk(tree):
        targets = node.targets if isinstance(node, ast.Assign) else (
            [node.target] if isinstance(node, ast.AnnAssign) else [])
        for t in targets:
            if isinstance(t, ast.Name) and t.id in {
                    "PART_TYPE_LABELS_JA", "VARIATION_LABELS_JA"}:
                chars.update("".join(ast.literal_eval(node.value).values()))
    if not chars:
        raise RuntimeError("engine/part_names.py からラベル辞書を読み取れませんでした")
    # 組み立てに使う区切り文字・注記も含める(part_display_name参照)。
    chars.update("（）[]ダーツ本 ")
    return chars


def _module_japanese_chars(module_name: str, max_len: int = 400) -> set:
    """engine/<module>.py の文字列リテラルに出てくる日本語の文字を集める。

    f-string の中の固定部分(ast.JoinedStr の中の Constant)も ast.walk が
    そのまま拾うので、`f"ダーツ(合計{n}本)を..."` のような文も対象になる。
    docstring も混ざるが、**多めに入る分には害が無い**(サブセットが
    数KB太るだけ)。足りない方が事故になる——1文字欠けると、その字だけ
    黙って空白で印刷される。
    """
    import ast

    source_path = Path(__file__).resolve().parent.parent / "engine" / f"{module_name}.py"
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    chars: set = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if len(node.value) <= max_len:
                chars.update(node.value)
    return chars


def _cutting_note_chars() -> set:
    """engine/cutting.py の裁ち方の指示に出てくる文字(round31で追加)。"""
    chars = _module_japanese_chars("cutting")
    chars.update("表地枚わ裁ち不要接着芯あり見返し部分に0123456789 ")
    return chars


#: 文言が**紙に印刷される**エンジンのモジュール。ここに載っているモジュールは
#: 文字列リテラルを丸ごと走査してサブセットに入れる。
#:
#: 【round41でなぜ一覧にしたか】round38の`_pdf_inline_chars`のdocstringに
#: 書いたとおり、この事故は同じ形で6回起きている(round11で「布」「目」、
#: round11で「不完全」、round32でパーツ名、round35で縫製手順、round38で
#: 買い物メモ、round39でプロジェクター出力の文言)。毎回の原因は同じで、
#: **新しく紙に出る文言を足したのに、集める関数を足し忘れる**。
#: round35のREADMEには「文字列を生む関数を1か所に登録し、テストがその
#: 登録簿を回る形にすべき」と書いて、書いただけで作らなかった。
#: round41で裏地(engine/lining.py)を足すとき7回目を踏みかけたので、
#: ここで登録簿にする。以後は**この行にモジュール名を1つ足すだけ**でよい。
#:
#: なお`tests/test_pdf_export.py`の
#: `test_the_bundled_font_is_up_to_date_with_the_sources_it_is_built_from`
#: が、この登録簿を回した結果と同梱フォントを突き合わせるので、
#: 足し忘れても**テストが落ちる**(round39で追加した歯止め)。
PRINTED_MODULES = (
    "assembly",    # 縫製手順(round33)
    "fabric",      # 買い物メモ(round38)
    "lining",      # 裏地の注記(round41)
    "pdf_export",  # PDFの見出し・注記そのもの(round38)
)


def _printed_module_chars() -> set:
    """`PRINTED_MODULES`の文字列リテラルに出てくる文字を全部集める(round41)。

    docstringやコメント由来の文字が余分に入るが、サブセットが数KB太るだけで
    害は無い。**足りない方が事故になる**——1文字欠けると、その字だけ黙って
    空白で印刷される(クラッシュしないので、紙にするまで気づけない)。

    【round38の`_pdf_inline_chars`から引き継いだ判断の記録】
    pdf_export.pyには「描画する固定文言はPDF_STATIC_TEXTSに集約する」という
    約束があったが、**約束は守られなかった**。round38で買い物メモのページ
    (`_draw_shopping_page`)を足したとき、見出しの「買い物メモ」「表地」
    「接着芯」「向いている生地」をその場に直接書いてしまい、
    PDF_STATIC_TEXTSへの追加を忘れた。結果、生成したPDFには
    **「買い物メモ」が1文字も印刷されず**、テキスト抽出するとヌル文字が
    並んだ。そこで約束に頼るのをやめ、リテラルを全部集める形にした。
    round41ではその「全部集める」対象自体を`PRINTED_MODULES`という
    登録簿にして、モジュールを足し忘れる経路も消してある。
    """
    chars: set = set()
    for name in PRINTED_MODULES:
        chars.update(_module_japanese_chars(name))
    return chars


def _static_text_chars() -> set:
    """engine/pdf_export.py の PDF_STATIC_TEXTS に出てくる文字を集める。

    pdf_export のインポートは reportlab 等に依存するため、フォントが未生成の
    状態でも動くよう、ソースを構文解析して定数だけを取り出す。
    """
    import ast

    source_path = Path(__file__).resolve().parent.parent / "engine" / "pdf_export.py"
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        targets = []
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]
        for t in targets:
            if isinstance(t, ast.Name) and t.id == "PDF_STATIC_TEXTS":
                return set("".join(ast.literal_eval(node.value)))
    raise RuntimeError("engine/pdf_export.py に PDF_STATIC_TEXTS が見つかりません")

SOURCE_FONT = Path("/usr/share/fonts/opentype/ipafont-gothic/ipag.ttf")
OUTPUT_FONT = Path(__file__).resolve().parent.parent / "engine" / "assets" / "pattern_label_ja_subset.ttf"


def _build_char_set() -> str:
    chars = set()
    chars.update(chr(c) for c in range(0x20, 0x7F))  # ASCII
    chars.update(chr(c) for c in range(0x3040, 0x30FF + 1))  # ひらがな + カタカナ
    chars.update(REQUIRED_KANJI)
    chars.update(SUGGESTED_CUSTOM_PANEL_KANJI)
    chars.update(ENGINE_GENERATED_LABEL_KANJI)
    chars.update(_static_text_chars())
    chars.update(_part_name_chars())
    chars.update(_cutting_note_chars())
    chars.update(_printed_module_chars())
    return "".join(sorted(chars))


def main() -> None:
    if not SOURCE_FONT.exists():
        print(
            f"元フォントが見つかりません: {SOURCE_FONT}\n"
            "Debian/Ubuntuなら `apt-get install fonts-ipafont-gothic` でインストールしてください。",
            file=sys.stderr,
        )
        sys.exit(1)

    text_file = Path("/tmp/pattern_label_font_chars.txt")
    text_file.write_text(_build_char_set(), encoding="utf-8")

    OUTPUT_FONT.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            sys.executable, "-m", "fontTools.subset",
            str(SOURCE_FONT),
            f"--text-file={text_file}",
            f"--output-file={OUTPUT_FONT}",
            "--layout-features=",
            "--no-hinting",
            "--drop-tables+=DSIG",
        ],
        check=True,
    )
    print(f"書き出し完了: {OUTPUT_FONT} ({OUTPUT_FONT.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
