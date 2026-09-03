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
REQUIRED_KANJI = "左右脚前後本枚度回転確認布目型紙面含不完全配置採寸見直"


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
    chars.update(_static_text_chars())
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
