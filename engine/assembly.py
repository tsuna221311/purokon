"""assembly.py — 縫製手順書(どのパーツをどの順で縫うか)を組み立てる。round33で追加。

【round32まで何が足りなかったか】型紙は出るが、**縫う順番はどこにも
書いていなかった**。市販の型紙には必ず付いてくる紙で、これが無いと
「パーツは裁てたが、どこから手を付ければいいか分からない」で止まる。
特に袖付けは、脇を縫う前に付けるか後に付けるかで難易度も仕上がりも
変わるため、順番そのものが情報である。

【生成するもの / しないもの】
このエンジンは、一般的な洋裁書の手順を**そのまま印刷し直す**のではなく、
**この型紙について実際に知っている数字**を手順に埋め込む:

  * どのパーツが何枚あるか(`FinalizedPart`)
  * どのパーツにダーツが何本入ったか(`dart_count`)
  * 縫い代が何cmか(`seam_allowance_cm` / 裾だけ別なら裾の値も)
  * 袖山をいくつ縮めるか(いせ込み量。`compatibility.sleeve_cap_ease_cm`)
  * 合印が前1本・後ろ2本で打ってあること(`engine/notches.py`)
  * 接着芯を貼るパーツはどれか(`engine/cutting.py`)

逆に、**知らないことは書かない**。ミシンの設定・アイロンの温度・
生地ごとの扱いは、このエンジンが情報を持っていないので手順に含めない
(それらしく書くと、根拠のない指示が型紙に載る)。

【round41で変わったこと】round40まではここに「裏地の付け方」も
「情報を持っていない」側に並べていた。round41で`engine/lining.py`が
裏地の型紙を引くようになり、**きせの深さ(1cm)と裾の縫い代の差(2cm)**
という2つの数字を出典付きで持つようになったので、その2つに限って
手順に出す。裏地の**付け方の細部**(袋縫いにするか手まつりにするか、
見返しをどう作るか)は今も知らないので、知らないと書く。

【順番の根拠】
  * 全体の流れ(ダーツ→中心・切り替え→肩→衿(見返し)→脇→袖→裾):
    うさこの洋裁工房「ウエスト切り替えのワンピースのつくり方」
    https://yousai.net/how_to/dress/waist_kirikae_wanpi
  * 袖は**筒にしてから**身頃へ付ける(袖下を先に縫い、袖山のいせを
    ぐし縫いで縮め、袖山=肩・袖下=脇の合印を合わせる):
    MAISON DE AS「セットインスリーブ(基本袖)の縫い方」
    https://maisondeas.com/set-in-sleeve-tutorial/

この2つは同じ物を違う順で作っているわけではなく、前者が全体、後者が
袖付けの中身を述べている。前者の「10. そで」の中身が後者にあたる。

【正直な限界】
  * ここで出すのは**標準的な1通り**である。同じ型紙でも、裏地を付ける・
    ファスナーを別の位置に付ける・肩を最後に縫う(袖ぐりを先に始末する
    やり方)など、成立する順番は他にもある。
  * 縫い方そのもの(ぐし縫いの針目・アイロンの当て方)は書いていない。
  * 前開きファスナーの付け方は「見返しをつけて中心前で合わせる」以上の
    ことを、このエンジンは知らない。
"""

from __future__ import annotations
from dataclasses import dataclass

from .cutting import interfacing_note, needs_interfacing
from .hood import HOOD_FRONT_FOLD_CM
from .lining import (CB_PLEAT_DEPTH_CM, CB_PLEAT_FABRIC_CM, CB_PLEAT_PART_TYPES,
                      hem_gap_phrase, hem_reduction_sentence,
                      lining_hem_allowance_cm)
from .part_names import part_type_label


@dataclass(frozen=True)
class AssemblyStep:
    """縫製手順の1工程。

    title は工程名(短く)、detail はその工程で実際に何をするか。
    parts は「この工程で手に取るパーツ」の表示名で、画面と紙のどちらでも
    「どれを持てばいいか」がすぐ分かるようにするためのもの。
    """
    number: int
    title: str
    detail: str
    parts: tuple[str, ...] = ()

    def as_dict(self) -> dict:
        return {"number": self.number, "title": self.title,
                "detail": self.detail, "parts": list(self.parts)}


#: 袖山のいせ込みを縮めるときの、ぐし縫いの範囲を表す文言に使う。
#: (量そのものは`compatibility.sleeve_cap_ease_cm`が実測から返す。)
_SLEEVE_EASE_NOTE = (
    "袖山の合印から合印までをぐし縫いし、糸を引いて約{ease:.1f}cm縮めます"
    "(この分が肩先の丸みになります)。"
)


def _short_name(part) -> str:
    """手順書に出す短い名前。

    型紙の上には「前身頃（ラウンドネック） [ダーツ4本]」と印字するが、
    手順の「どのパーツを持つか」欄では、ネックラインの種類とダーツ本数は
    どれも同じで区別に寄与しない。パーツ種と左右/前後だけにする。
    """
    base = part_type_label(part.part_type)
    return f"{base} {part.label_suffix}" if part.label_suffix else base


def _names(parts: list, part_types: set[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(_short_name(p) for p in parts
                                if p.part_type in part_types))


def _has(parts: list, part_types: set[str]) -> bool:
    return any(p.part_type in part_types for p in parts)


_BODICE_FRONT = {"front_bodice", "front_bodice_center", "front_bodice_side",
                  "front_bodice_zip_panel"}
_BODICE_BACK = {"back_bodice", "back_bodice_center", "back_bodice_side"}
_BODICE = _BODICE_FRONT | _BODICE_BACK
_PRINCESS = {"front_bodice_center", "front_bodice_side",
              "back_bodice_center", "back_bodice_side"}
_LOWER = {"skirt", "front_pants", "back_pants"}


def assembly_steps(finalized_parts: list,
                    seam_allowance_cm: float = 1.0,
                    hem_seam_allowance_cm: float | None = None,
                    sleeve_cap_ease_cm: float | None = None,
                    front_zip: bool = False,
                    split_panels: dict[str, int] | None = None,
                    lining_parts: list | None = None) -> list[AssemblyStep]:
    """このパーツ構成に対する縫製手順を組み立てる。

    パーツが無い工程は出さない(袖を選んでいなければ袖付けの工程は
    そもそも現れない)。番号は出る工程だけで振り直す。
    """
    steps: list[tuple[str, str, tuple[str, ...]]] = []
    hem_cm = hem_seam_allowance_cm if hem_seam_allowance_cm is not None else seam_allowance_cm

    # --- 0. 裁つ前 ---------------------------------------------------------
    steps.append((
        "印を付ける",
        "裁った布に、型紙の合印(短い線)・ダーツ・基準線(BL/WL/HL/CF/CB/BP)を"
        "写します。合印は縫い合わせる相手と必ず突き合うように打ってあるので、"
        "ここを省くとどこを合わせればよいか分からなくなります。",
        (),
    ))

    interfaced = [p for p in finalized_parts if needs_interfacing(p.part_type)]
    if interfaced:
        # どこに貼るかはパーツによって違う(全面か、見返し部分だけか)。
        where = tuple(dict.fromkeys(
            f"{_short_name(p)}（{interfacing_note(p.part_type)}）"
            for p in interfaced))
        steps.append((
            "接着芯を貼る",
            "下のパーツの裏に接着芯を貼ります。貼らないと衿が立たず、"
            "カフスやウエストバンドがよれます。"
            "括弧の中に、全面か一部かを書いてあります。",
            where,
        ))

    # --- 1. パーツ単体を立体にする ------------------------------------------
    if _has(finalized_parts, _PRINCESS):
        steps.append((
            "切り替え線を縫う",
            "前身頃・後身頃それぞれで、「中央」と「脇」を中表に合わせて縫います。"
            "この縫い目がウエストの絞りと胸の丸みを作るので、合印をきちんと"
            "合わせてください。カーブがきつい所は、縫い代に切り込みを入れると"
            "きれいに開きます。",
            _names(finalized_parts, _PRINCESS),
        ))
    else:
        darted = [p for p in finalized_parts
                   if p.dart_count and p.part_type in _BODICE]
        if darted:
            total = sum(p.dart_count for p in darted)
            steps.append((
                "ダーツを縫う",
                f"身頃のダーツ(合計{total}本)を、印の頂点に向かって縫います。"
                "V字の切り込みは縫い閉じる位置、両端が尖ったひし形は内側で摘む"
                "位置です。先端は返し縫いをせず、糸を結んで留めます。",
                tuple(dict.fromkeys(_short_name(p) for p in darted)),
            ))
        lower_darted = [p for p in finalized_parts
                         if p.dart_count and p.part_type in _LOWER]
        if lower_darted:
            steps.append((
                "スカート・パンツのダーツを縫う",
                "ウエスト側のダーツを縫い、縫い代を中心側へ倒します。",
                tuple(dict.fromkeys(_short_name(p) for p in lower_darted)),
            ))

    # --- 2. 開き(前開きファスナー) ------------------------------------------
    # 出典(うさこの洋裁工房)の順番でも、ファスナーは**肩と脇より前**に付ける。
    # 身頃が筒になってからでは、中心前の長い直線にミシンを入れにくい。
    if front_zip:
        steps.append((
            "前開きファスナーを付ける",
            "中心前の裁ち割りにファスナーを付け、見返し(裏側の折り返し布)を"
            "重ねて始末します。まだ肩も脇も縫っていない平らな状態なので、"
            "ここがいちばん縫いやすい段階です。左右の切り替えの高さが合うよう、"
            "しつけをしてから縫ってください。",
            _names(finalized_parts, {"front_bodice_zip_panel"}),
        ))

    # --- 3. 身頃を組む ------------------------------------------------------
    if _has(finalized_parts, _BODICE_FRONT) and _has(finalized_parts, _BODICE_BACK):
        steps.append((
            "肩線を縫う",
            f"前身頃と後身頃を中表に合わせ、肩線を縫い代{seam_allowance_cm:g}cmで縫います。"
            "縫い代は割ります。",
            _names(finalized_parts, {"front_bodice", "front_bodice_center",
                                      "front_bodice_zip_panel", "back_bodice",
                                      "back_bodice_center"}),
        ))

    if _has(finalized_parts, {"hood"}):
        steps.append((
            "フードを作る",
            "フード2枚を中表に合わせ、**中心後(まっすぐな辺)**を縫って"
            "1つにします。次に顔の開きになる前端を、縫い代"
            f"{HOOD_FRONT_FOLD_CM:g}cmで裏側へ折ってステッチをかけます"
            "(裏フードを付ける場合は、表と裏を中表に合わせて前端を縫い、"
            "表に返してから同じ位置にステッチをかけます)。",
            _names(finalized_parts, {"hood"}),
        ))
        steps.append((
            "フードを付ける",
            "フードの付け根を身頃の首ぐりに中表で合わせ、合印を突き合わせて"
            "縫います。フードの前端が身頃の前端と揃う向きです。"
            "首ぐりはカーブなので、縫い代に浅く切り込みを入れてから縫うと"
            "つれません。",
            _names(finalized_parts, {"hood"}),
        ))

    if _has(finalized_parts, {"collar"}):
        steps.append((
            "衿を付ける",
            "衿を身頃の首ぐりに中表で合わせ、合印を突き合わせて縫います。"
            "首ぐりはカーブなので、縫い代に浅く切り込みを入れてから縫うと"
            "つれません。",
            _names(finalized_parts, {"collar"}),
        ))

    if _has(finalized_parts, _BODICE_FRONT) and _has(finalized_parts, _BODICE_BACK):
        steps.append((
            "脇線を縫う",
            f"前後の身頃を中表に合わせ、脇線を縫い代{seam_allowance_cm:g}cmで縫います。"
            "脇線の途中にある合印が前後で必ず突き合うので、そこを合わせてから"
            "縫い始めてください。",
            _names(finalized_parts, {"front_bodice", "front_bodice_side",
                                      "front_bodice_zip_panel",
                                      "back_bodice", "back_bodice_side"}),
        ))

    # --- 4. 袖 --------------------------------------------------------------
    if _has(finalized_parts, {"sleeve"}):
        steps.append((
            "袖を筒にする",
            "袖の袖下を縫って筒にし、縫い代を割ります。"
            "(身頃に付ける前に袖を完成させる「筒付け」の手順です。)",
            _names(finalized_parts, {"sleeve"}),
        ))
        if _has(finalized_parts, {"cuffs"}):
            steps.append((
                "カフスを付ける",
                "袖口にカフスを付けます。カフスは袖口より少し長く作ってあるので、"
                "重なる分が開閉のゆとりになります。",
                _names(finalized_parts, {"cuffs"}),
            ))
        ease_note = (_SLEEVE_EASE_NOTE.format(ease=sleeve_cap_ease_cm)
                     if sleeve_cap_ease_cm else
                     "袖山を袖ぐりの寸法まで少し縮めます。")
        steps.append((
            "袖を身頃に付ける",
            ease_note
            + "そのあと袖と身頃を中表に合わせ、"
            "「袖山の合印を肩線に、袖下の縫い目を脇線に」合わせてしつけをしてから縫います。"
            "袖ぐり側の合印は前が1本・後ろが2本なので、袖を前後逆に付ける心配が"
            "ありません。",
            _names(finalized_parts, {"sleeve"}),
        ))

    # --- 5. 下半身とつなぐ --------------------------------------------------
    # round35: 生地幅に収まらず縦に分けたパーツは、まず1枚に縫い合わせる
    # (engine/panel_split.py)。ここを飛ばすと、以降の「脇を縫う」が
    # 何を指しているのか分からなくなる。
    for part_type, count in sorted((split_panels or {}).items()):
        if count < 2:
            continue
        steps.append((
            f"{part_type_label(part_type)}のパネルを縫い合わせる",
            f"生地幅に収まらないため{count}枚に分けてあります。縦の分割線どうしを"
            f"縫い代{seam_allowance_cm:g}cmで中表に縫い合わせ、1枚に戻します"
            "(大きなスカートを接いで作るのは、実際の洋裁でも普通の手順です)。"
            "縫い代は割ります。",
            _names(finalized_parts, {part_type}),
        ))

    if _has(finalized_parts, {"front_pants", "back_pants"}):
        steps.append((
            "パンツを組む",
            "前後のパンツをそれぞれ脇と股下で縫い、片方をもう片方に入れ込んで"
            "股ぐりを縫います。",
            _names(finalized_parts, {"front_pants", "back_pants"}),
        ))
    if _has(finalized_parts, {"skirt"}):
        steps.append((
            "スカートの脇を縫う",
            "前後のスカートを中表に合わせ、脇を縫います。",
            _names(finalized_parts, {"skirt"}),
        ))

    if _has(finalized_parts, _BODICE) and _has(finalized_parts, _LOWER):
        steps.append((
            "身頃とスカート(パンツ)をつなぐ",
            "ウエストで中表に合わせ、脇線どうし・中心どうしを合わせてから"
            "縫います。縫い代は身頃側へ倒します。",
            (),
        ))
    if _has(finalized_parts, {"waistband"}):
        steps.append((
            "ウエストバンドを付ける",
            "ウエストバンドを上端に付けます。バンドはウエストより長く作って"
            "あり、その差が開閉の重なり分になります。",
            _names(finalized_parts, {"waistband"}),
        ))

    # --- 6. 始末 ------------------------------------------------------------
    # round36: カスタムパーツ(自由形状)は、**付け方を書けない**。
    #
    # 【なぜ書けないか】マント・翼・肩当てのような自由形状パーツは、利用者が
    # 輪郭を描いて実寸を指定しただけのもので、このエンジンは「それが体の
    # どこに、どちら向きに、どう留まるのか」を一切知らない。首に結ぶのか、
    # 肩に縫い付けるのか、面ファスナーで着脱するのかはパーツ次第である。
    # 知らないものについて、もっともらしい手順を書くわけにはいかない。
    #
    # 【では黙っていてよいか】よくない。round35までは**一言も触れていな
    # かった**ので、利用者は9工程を最後まで縫い終えたところで、裁ったのに
    # どこにも使っていない布が手元に残る。しかも手順が「裾を始末する」で
    # 終わっているため、**型紙のとおり作り終えた**と読めてしまう。
    # 手順に載っていない=付けなくてよい、ではない。
    # 分からないことは分からないと書く。
    # --- 6b. 裏地(round41) --------------------------------------------------
    # 表地を縫い終えてから、同じ手順でもう1つ「裏地の身頃」を作り、最後に
    # 合わせる。ここに出すのは`engine/lining.py`が出典付きで持っている
    # 2つの数字(きせの深さ・裾の縫い代の差)だけで、付け方の細部は書かない。
    if lining_parts:
        lining_names = tuple(dict.fromkeys(p.display_name for p in lining_parts))
        pleated = tuple(dict.fromkeys(
            _short_name(p) for p in lining_parts
            if p.part_type in CB_PLEAT_PART_TYPES))
        if pleated:
            steps.append((
                "裏地の背中心にきせをたたむ",
                "・".join(pleated) + "は、背中心に"
                f"{CB_PLEAT_FABRIC_CM:g}cm分の布を足してあります。"
                f"型紙の「きせ」の線どうしを合わせて深さ{CB_PLEAT_DEPTH_CM:g}cmの"
                "ひだにたたみ、襟ぐりと裾で仮止めします。たたむと表地と同じ幅に"
                "戻ります。このゆとりが無いと、着たときに表地がつっぱります"
                "(かたやまゆうこ「1cmのきせ分、布の長さでいうと2cm、これが重要」)。",
                pleated,
            ))
        steps.append((
            "裏地を組み立てる",
            "裏地のパーツを、表地とまったく同じ順(ダーツ→切り替え→肩→脇→袖)で"
            "縫い合わせ、もう1つの身頃を作ります。裏地の型紙の出来上がり線は"
            "表地と同じ寸法なので、縫う位置も同じです。",
            lining_names,
        ))

    steps.append((
        "裾を始末する",
        # round49: 「三つ折り」は縫い代を2回折る始末なので、折り幅は縫い代の
        # 半分になる。既定の1cmだと5mmずつで、そのことを書かないと
        # 「三つ折りにしてください」だけが残って手が止まる。
        # 割り算の結果を書くだけで、縫い方の新しい主張はしていない。
        f"裾を三つ折りにして縫います(縫い代を2回折るので、折り幅は"
        f"{hem_cm / 2:g}cmずつになります)。この型紙の裾の縫い代は{hem_cm:g}cmです"
        + ("(他の辺とは別に指定した値です)。" if hem_seam_allowance_cm is not None
           and hem_seam_allowance_cm != seam_allowance_cm else "。")
        # round49: 裏地の説明は engine/lining.py に1つだけ置いた文を使う。
        # 以前はここに「表地より2cm短く」と手書きしてあり、round46で
        # lining.py 側だけを実測値に直したため、**この1文だけが取り残されて**
        # 既定(裾1.0cm)で「2cm短く」と嘘を言い続けていた。
        + (hem_reduction_sentence(hem_cm) if lining_parts else ""),
        (),
    ))

    if lining_parts:
        steps.append((
            "裏地を身頃に合わせる",
            "表地と裏地を合わせます。どう合わせるか——袋状に縫って裏返すのか、"
            "見返しを付けて裾は手まつりにするのか——は、この型紙からは決まりません。"
            "作るものと使う生地によって変わり、このエンジンはその情報を"
            "持っていないので、ここに手順を書けません。"
            # 【round61で直した実バグ】ここは「裏地の裾が表地より2cm短い」と
            # **手書き**されていた。実際に引ける量は表地の裾の縫い代で決まり、
            # 既定(裾1.0cm)では1.0cmしか引けない。つまり同じPDFの中で、
            #     手順11「表地より1cm短く裁ってあります」
            #     手順12「裏地の裾が表地より2cm短い」
            # と食い違っていた。しかもこれは**round46→49で1度直した間違い**で、
            # そのときの警告コメントが、この10行上に書いてある。
            # コメントでは再発を止められなかったので、テストで止める
            # (tests/test_round61_one_source_of_truth.py)。
            + hem_gap_phrase(hem_cm)
            + "背中心のきせの分量だけです。",
            (),
        ))

    customs = [p for p in finalized_parts if p.part_type == "custom_panel"]
    if customs:
        names = tuple(dict.fromkeys(p.display_name for p in customs))
        steps.append((
            "カスタムパーツを取り付ける",
            "カスタムパーツ(" + "・".join(names) + ")は、あなたが形と寸法を"
            "指定したパーツです。体のどこにどう留まるのかはパーツごとに違い、"
            "この型紙はその情報を持っていないため、付け方をここに書けません。"
            "作りたいものに合わせて取り付けてください。"
            "この工程を最後に置いてあるのは順番の指示ではなく、"
            "他の工程と混ざらないようにするためです。",
            names,
        ))

    return [AssemblyStep(i + 1, title, detail, parts)
            for i, (title, detail, parts) in enumerate(steps)]


def assembly_steps_for_result(result) -> list[AssemblyStep]:
    """`PipelineResult`から手順を組み立てる便利関数。

    いせ込み量・縫い代・前開きかどうかを、結果から自分で拾う。
    """
    from .pipeline import _sleeve_cap_ease_for

    parts = result.finalized_parts
    ease = _sleeve_cap_ease_for(parts)
    front_zip = any(p.part_type == "front_bodice_zip_panel" for p in parts)
    return assembly_steps(
        parts,
        seam_allowance_cm=result.seam_allowance_cm,
        hem_seam_allowance_cm=result.hem_seam_allowance_cm,
        sleeve_cap_ease_cm=ease,
        front_zip=front_zip,
        split_panels=getattr(result, "split_panels", None),
        lining_parts=getattr(result, "lining_parts", None),
    )
