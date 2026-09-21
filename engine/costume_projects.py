"""特定衣装を「服」と「別工程の装飾」に分けるためのプリセット。

イラスト1枚から、量産コスプレ衣装と同じ完成度の衣装を安全に自動製図する
ことはできない。特に金具・EVAフォーム・左右非対称の飾りは、身体に沿う布の
型紙と同じ規則では扱えない。このモジュールは、型紙にできる布パーツだけを
生成に渡し、別工程にすべき部材を明示して取り落としを防ぐ。
"""

from __future__ import annotations

from dataclasses import dataclass

from .custom_panel import CustomPanelSpec
from .measurements import Measurements


@dataclass(frozen=True)
class CostumeProject:
    """衣装プリセットの、生成用設定と制作指示。"""

    key: str
    label: str
    garment_spec_kwargs: dict[str, object]
    custom_panel_specs: tuple[CustomPanelSpec, ...]
    lining: bool
    shoulder_drop_cm: float
    worn_over_bust_cm: float
    patternable_components: tuple[str, ...]
    separate_components: tuple[str, ...]
    material_plan: tuple[str, ...]
    construction_plan: tuple[str, ...]
    limitations: tuple[str, ...]
    commercial_benchmark: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, object]:
        """画面/APIで表示する。数値や推測を隠さない制作計画。"""
        return {
            "key": self.key,
            "label": self.label,
            "patternable_components": list(self.patternable_components),
            "separate_components": list(self.separate_components),
            "material_plan": list(self.material_plan),
            "construction_plan": list(self.construction_plan),
            "limitations": list(self.limitations),
            "commercial_benchmark": list(self.commercial_benchmark),
        }


def _endministrator_female(measurements: Measurements) -> CostumeProject:
    """提供画像の管理人（女性）向けの、採寸連動コート＋小物計画。

    裾パネルは正面資料から読める外側シルエットを、身体に密着しない別裁ちの
    オーバーレイとして置く。左右を同じ形へ丸めず、別々の輪郭にすることで
    この衣装の非対称性を保つ。後面資料を得たらこの2枚を実測で調整する。
    """
    height = measurements.height
    hip = measurements.hip
    # コートの下半分。体に沿わせる本体ではなく、前開き身頃に重ねて縫い付ける
    # 外装なので、身長・ヒップから穏やかに決める。極端な採寸でも型紙が
    # 扱いにくい大きさにならないよう範囲を置く。
    tail_length = min(112.0, max(82.0, height * 0.60))
    tail_width = min(43.0, max(28.0, hip * 0.34))
    back_width = min(52.0, max(36.0, hip * 0.48))

    panels = (
        CustomPanelSpec(
            label="管理人コート・左前裾オーバーレイ",
            points_cm=[(0.0, 0.0), (tail_width, 0.0),
                       (tail_width * 0.86, tail_length * 0.48),
                       (tail_width * 0.56, tail_length),
                       (tail_width * 0.08, tail_length * 0.73)],
            quantity=1, mirror=False, allow_split=False),
        CustomPanelSpec(
            label="管理人コート・右前裾オーバーレイ",
            points_cm=[(0.0, 0.0), (tail_width * 0.92, 0.0),
                       (tail_width, tail_length * 0.72),
                       (tail_width * 0.38, tail_length),
                       (0.0, tail_length * 0.40)],
            quantity=1, mirror=False, allow_split=False),
        CustomPanelSpec(
            label="管理人コート・背中フレアオーバーレイ",
            points_cm=[(0.0, 0.0), (back_width, 0.0),
                       (back_width * 0.94, tail_length * 0.78),
                       (back_width * 0.58, tail_length),
                       (back_width * 0.12, tail_length * 0.84)],
            quantity=1, mirror=False, allow_split=False),
    )
    return CostumeProject(
        key="endministrator_female",
        label="アークナイツ：エンドフィールド 管理人（女性）",
        garment_spec_kwargs={
            "neckline": "round_neck",
            "sleeve_style": "straight",
            "skirt_style": None,
            "front_zip": True,
            "include_pants": True,
            "pants_style": "shorts",
            "include_collar": False,
            "include_cuffs": False,
            "include_waistband": False,
            # 現行エンジンでは中心前を分割する前開きと、身頃を縦に分ける
            # プリンセスラインを同時に製図できない。コートでは前開きの
            # ファスナー／見返しを優先し、立体感は別裁ちの外装パネルで出す。
            "princess_line": False,
        },
        custom_panel_specs=panels,
        lining=True,
        shoulder_drop_cm=5.0,
        worn_over_bust_cm=measurements.bust + 10.0,
        patternable_components=(
            "前開きコート本体（前身頃・後身頃・長袖）",
            "ショートパンツ",
            "左右非対称の前裾オーバーレイ2枚",
            "背中フレアオーバーレイ1枚",
            "コート本体の裏地",
        ),
        separate_components=(
            "黄色い肩当て（EVAフォームまたは合皮で別制作）",
            "胸元・袖・背中の金具とストラップ",
            "リブ編みのハイネックインナー",
            "タイツ、靴、髪飾り、マスク",
        ),
        material_plan=(
            "表地: チャコールの中肉ツイル／ポリエステル混。光沢が強すぎないもの。",
            "裏地: 黒または濃グレーの滑りのよい裏地。",
            "オーバーレイ: 表地と同系色の合皮または張りのある布。",
            "黄色い肩当て: 2〜3mm EVAフォーム＋黄色合皮。",
            "副資材: 黒のコイルファスナー、黒テープ、Dカン／ナスカン、銀色バックル。",
        ),
        construction_plan=(
            "先にインナーとショートパンツを試着して、上に羽織るコートのゆとりを確認する。",
            "コート本体を組み、裏地を付ける前にドロップショルダーと袖丈を仮縫いで確認する。",
            "非対称オーバーレイは本体の前裾・背中でしつけ留めし、着用状態で位置を決めてから縫い付ける。",
            "EVAフォーム、金具、ストラップは最後に取り付ける。布型紙へ無理に混在させない。",
        ),
        limitations=(
            "このプリセットは提供された正面イラストを基にした制作計画であり、公式衣装の複製型紙ではありません。",
            "背面の形、金具の位置、黄色い肩当ての立体形状は正面資料だけでは確定できません。背面資料と実物合わせが必要です。",
            "リブ編みインナーは伸縮率で寸法が変わるため、通常布向けのコート型紙とは別に試作してください。",
        ),
        commercial_benchmark=(
            "市販セットはコート、ショートパンツ、タイツ、各種飾りを含む。型紙だけで完結させず、別工程の飾りを制作計画に残す。",
            "比較対象: Costowns 管理人（女性）38,800円、XS〜XXL（2026-09確認）。",
        ),
    )


def _endministrator_male(measurements: Measurements) -> CostumeProject:
    """管理人（男性）のコート＋パンツ。市販セットの付属品も制作指示へ残す。"""
    height = measurements.height
    hip = measurements.hip
    coat_tail = min(108.0, max(78.0, height * 0.56))
    side_width = min(38.0, max(25.0, hip * 0.30))
    panels = (
        CustomPanelSpec(
            label="管理人（男性）コート・左前裾オーバーレイ",
            points_cm=[(0.0, 0.0), (side_width, 0.0), (side_width * 0.92, coat_tail * 0.66),
                       (side_width * 0.48, coat_tail), (0.0, coat_tail * 0.54)],
            quantity=1, mirror=False, allow_split=False),
        CustomPanelSpec(
            label="管理人（男性）コート・右脇フレア",
            points_cm=[(0.0, 0.0), (side_width * 0.88, 0.0), (side_width, coat_tail * 0.78),
                       (side_width * 0.34, coat_tail), (0.0, coat_tail * 0.40)],
            quantity=1, mirror=False, allow_split=False),
    )
    return CostumeProject(
        key="endministrator_male",
        label="アークナイツ：エンドフィールド 管理人（男性）",
        garment_spec_kwargs={
            "neckline": "round_neck", "sleeve_style": "straight", "skirt_style": None,
            # エンジンのパンツは標準ストレートより、裾を絞れる tapered が
            # 現行の男性管理人のシルエットに近い。未実装の "standard" を
            # 渡して生成を失敗させない。
            "front_zip": True, "include_pants": True, "pants_style": "tapered",
            "include_collar": False, "include_cuffs": False, "include_waistband": False,
            "princess_line": False,
        },
        custom_panel_specs=panels, lining=True, shoulder_drop_cm=4.0,
        worn_over_bust_cm=measurements.bust + 12.0,
        patternable_components=(
            "前開きロングコート本体（前身頃・後身頃・長袖・裏地）", "ストレートパンツ",
            "非対称の前裾／脇フレアオーバーレイ2枚",
        ),
        separate_components=(
            "セーター、つけ襟、首飾り", "肩・背中・腕の立体飾りとストラップ",
            "手首飾り、面頰、紐飾り、靴、ウィッグ",
        ),
        material_plan=(
            "表地: 黒〜チャコールの中肉ツイル。", "裏地: 黒のすべりのよい裏地。",
            "差し色: 黄色合皮／ナイロンテープ。", "副資材: コイルファスナー、Dカン、バックル、EVAフォーム。",
        ),
        construction_plan=(
            "パンツを先に仮縫いし、コートのゆとりを上から確認する。",
            "コート本体と裏地を組む前に、前開き位置と袖丈を試着確認する。",
            "フレアパネルは着用状態で仮留めしてから縫い付ける。",
            "EVAフォームと金具は縫製完了後に取り付ける。",
        ),
        limitations=(
            "公式衣装の複製型紙ではなく、公開資料を基にした制作支援用の型紙です。",
            "背面装飾・面頰の固定方法は身体と素材に合わせた別試作が必要です。",
        ),
        commercial_benchmark=(
            "市販セットはコート、セーター、つけ襟、パンツ、各種飾りを含むため、布パーツと立体装飾を分けて不足を可視化する。",
            "比較対象: Costowns 管理人（男性）38,800円、XS〜XXL（2026-09確認）。",
        ),
    )


def _perlica(measurements: Measurements) -> CostumeProject:
    """ペリカのワンピース＋コート。販売セットの手袋等を別工程として明記する。"""
    height = measurements.height
    bust = measurements.bust
    coat_length = min(86.0, max(62.0, height * 0.47))
    tab_width = min(20.0, max(13.0, bust * 0.18))
    panels = (
        CustomPanelSpec(
            label="ペリカ・前身頃ベルトタブ（左）",
            points_cm=[(0.0, 0.0), (tab_width, 0.0), (tab_width * 0.88, coat_length * 0.38),
                       (tab_width * 0.30, coat_length * 0.54), (0.0, coat_length * 0.27)],
            quantity=1, mirror=False, allow_split=False),
        CustomPanelSpec(
            label="ペリカ・前身頃ベルトタブ（右）",
            points_cm=[(0.0, 0.0), (tab_width * 0.92, 0.0), (tab_width, coat_length * 0.30),
                       (tab_width * 0.45, coat_length * 0.54), (0.0, coat_length * 0.40)],
            quantity=1, mirror=False, allow_split=False),
    )
    return CostumeProject(
        key="perlica", label="アークナイツ：エンドフィールド ペリカ",
        garment_spec_kwargs={
            "neckline": "square_neck", "sleeve_style": "straight", "skirt_style": "flare",
            "front_zip": False, "include_pants": False, "pants_style": "",
            "include_collar": False, "include_cuffs": True, "cuffs_style": "wide",
            "include_waistband": True, "waistband_style": "contour", "princess_line": False,
        },
        custom_panel_specs=panels, lining=True, shoulder_drop_cm=1.0,
        worn_over_bust_cm=measurements.bust + 6.0,
        patternable_components=(
            "ワンピース本体（角首・フレアスカート・ウエストバンド）", "ジャケット／コート本体と裏地",
            "袖口カフス", "左右非対称の前ベルトタブ",
        ),
        separate_components=(
            "手袋、手首飾り、レッグリング、靴下、靴", "金属バックルと小型アクセサリー",
        ),
        material_plan=(
            "ワンピース: 白または淡色の中肉ブロード／ツイル。", "コート: 濃色ツイル、必要に応じて裏地。",
            "ベルトタブ: 薄手の合皮または芯を貼ったツイル。", "副資材: 接着芯、面ファスナーまたはスナップ、バックル。",
        ),
        construction_plan=(
            "ワンピースを先に仮縫いし、ウエスト位置とスカート丈を決める。",
            "コートは肩・袖・袖口の順で組み、ワンピースの上に着てゆとりを確認する。",
            "ベルトタブとバックルは最後に仮留めし、正面の左右差を着用状態で調整する。",
        ),
        limitations=(
            "市販画像の細かなプリント・金属部品の寸法は、正面資料だけから自動確定できません。",
            "手袋やレッグリングは伸縮素材・人体との干渉があるため別採寸で試作してください。",
        ),
        commercial_benchmark=(
            "市販セットはワンピース、コート、手首飾り、手袋、レッグリング、靴下を含む。型紙外の付属品を制作チェック項目にする。",
            "比較対象: Costowns ペリカ 53,800円、S〜XL／オーダーメイド（2026-09確認）。",
        ),
    )


def _chen_qianyu(measurements: Measurements) -> CostumeProject:
    """チェン・センユーのコート＋トップス＋スカートを分け、角と尻尾は別工程にする。"""
    height = measurements.height
    hip = measurements.hip
    coat_length = min(94.0, max(68.0, height * 0.51))
    panel_width = min(34.0, max(22.0, hip * 0.29))
    panels = (
        CustomPanelSpec(
            label="チェン・センユー・左前コートオーバーレイ",
            points_cm=[(0.0, 0.0), (panel_width, 0.0), (panel_width * 0.94, coat_length * 0.62),
                       (panel_width * 0.46, coat_length), (0.0, coat_length * 0.48)],
            quantity=1, mirror=False, allow_split=False),
        CustomPanelSpec(
            label="チェン・センユー・腰飾りベース",
            points_cm=[(0.0, 0.0), (panel_width * 0.70, 0.0), (panel_width, coat_length * 0.25),
                       (panel_width * 0.42, coat_length * 0.42), (0.0, coat_length * 0.22)],
            quantity=1, mirror=False, allow_split=False),
    )
    return CostumeProject(
        key="chen_qianyu", label="アークナイツ：エンドフィールド チェン・センユー",
        garment_spec_kwargs={
            "neckline": "v_neck", "sleeve_style": "straight", "skirt_style": "pleated",
            "front_zip": False, "include_pants": False, "pants_style": "",
            "include_collar": False, "include_cuffs": True, "cuffs_style": "wide",
            "include_waistband": True, "waistband_style": "contour", "princess_line": False,
        },
        custom_panel_specs=panels, lining=True, shoulder_drop_cm=1.5,
        worn_over_bust_cm=measurements.bust + 7.0,
        patternable_components=(
            "トップス・プリーツスカート・ウエストバンド", "コート本体と裏地・袖口カフス",
            "左前オーバーレイ、腰飾りの布ベース",
        ),
        separate_components=(
            "リボン、手袋、腰飾りの立体金具", "角、尻尾、靴、ウィッグ",
        ),
        material_plan=(
            "トップス／スカート: 色分けしたツイルまたはブロード。", "コート: 張りのある濃色ツイルと裏地。",
            "腰飾り: 合皮、EVAフォーム、ナイロンテープ。", "副資材: 接着芯、スナップ、バックル、着脱可能な尻尾固定具。",
        ),
        construction_plan=(
            "トップスとスカートを別に仮縫いし、ウエスト位置を決めてから接続する。",
            "コートを仮縫いして腕の可動域を確認し、裏地を入れる。",
            "腰飾りベースに金具を取り付け、尻尾は荷重を腰ベルトへ逃がす。",
        ),
        limitations=(
            "角と尻尾は安全性・重量・固定方法が最優先の造形工程であり、布型紙には含めません。",
            "プリーツ量と色分割は追加の全身資料で確認してから裁断してください。",
        ),
        commercial_benchmark=(
            "市販セットはコート、トップス、スカート、リボン、手袋、腰飾り、角、尻尾、飾り物を含む。",
            "比較対象: Costowns チェン・センユー 23,800円、S〜XXL（2026-09確認）。",
        ),
    )


def _hatsune_miku_classic(measurements: Measurements) -> CostumeProject:
    """初音ミクの定番衣装。トップス・プリーツ・別体アームカバーに分ける。

    ミクは公式／二次創作を含め衣装バリエーションが多いため、ここでは特定の
    イベント衣装ではなく、銀灰色トップス・黒プリーツ・青緑ネクタイという
    広く流通している定番シルエットだけを対象にする。
    """
    bust = measurements.bust
    height = measurements.height
    strap_width = min(10.0, max(6.0, bust * 0.09))
    arm_length = min(52.0, max(35.0, height * 0.25))
    panels = (
        CustomPanelSpec(
            label="初音ミク・スカート前ストラップ（左）",
            points_cm=[(0.0, 0.0), (strap_width, 0.0), (strap_width * 0.88, arm_length),
                       (strap_width * 0.25, arm_length), (0.0, arm_length * 0.62)],
            quantity=1, mirror=False, allow_split=False),
        CustomPanelSpec(
            label="初音ミク・スカート前ストラップ（右）",
            points_cm=[(0.0, 0.0), (strap_width * 0.86, 0.0), (strap_width, arm_length * 0.62),
                       (strap_width * 0.72, arm_length), (0.0, arm_length)],
            quantity=1, mirror=False, allow_split=False),
    )
    return CostumeProject(
        key="hatsune_miku_classic", label="VOCALOID 初音ミク（定番衣装）",
        garment_spec_kwargs={
            "neckline": "boat_neck", "sleeve_style": None, "skirt_style": "pleated",
            "front_zip": False, "include_pants": False, "pants_style": "",
            "include_collar": False, "include_cuffs": False,
            "include_waistband": True, "waistband_style": "wide", "princess_line": False,
        },
        custom_panel_specs=panels, lining=False, shoulder_drop_cm=0.0,
        worn_over_bust_cm=measurements.bust + 4.0,
        patternable_components=(
            "ノースリーブトップス", "プリーツスカートと幅広ウエストバンド",
            "左右の前ストラップ布ベース",
        ),
        separate_components=(
            "青緑ネクタイとネクタイクリップ", "左右アームカバー、レッグカバー、ヘッドセット",
            "ウィッグ、靴、番号『01』等の意匠プリント",
        ),
        material_plan=(
            "トップス: 銀灰色の薄手ツイルまたはポリエステル。", "スカート: 黒のプリーツ向きツイル。",
            "差し色: 青緑のバイアステープ／合皮。", "副資材: 接着芯、面ファスナー、ネクタイクリップ、熱転写シート。",
        ),
        construction_plan=(
            "トップスの首ぐり・袖ぐりを先に処理して試着し、胸まわりのゆとりを確認する。",
            "スカートはプリーツを固定してからウエストバンドへ縫い付ける。",
            "ストラップと青緑の縁取りは、前後の見え方を確認して最後に付ける。",
            "アームカバーは伸縮素材の別パターンとして試作し、本体へ縫い込まない。",
        ),
        limitations=(
            "初音ミクには多数の公式・イベント衣装があるため、このプリセットは定番衣装のみです。特定衣装には追加資料が必要です。",
            "ロゴ・番号・文字情報は権利表示を確認し、個人制作の範囲で熱転写等を検討してください。",
        ),
        commercial_benchmark=(
            "市販セットはトップス、スカート、ネクタイ、左右アームカバー、左右レッグカバー、クリップ／ステッカーを含む。",
            "比較対象: NSMG SHOP 定番セット US$109、S〜XL（2026-09確認）。",
        ),
    )


def _yor_forger_thorn_princess(measurements: Measurements) -> CostumeProject:
    """SPY×FAMILY ヨルの黒いホルタードレスを、着用可能な縫製計画へ落とす。"""
    height = measurements.height
    bust = measurements.bust
    strap_width = min(8.0, max(4.5, bust * 0.065))
    bodice_length = min(48.0, max(34.0, height * 0.24))
    panels = (
        CustomPanelSpec(
            label="ヨル・ホルターネックストラップ（左）",
            points_cm=[(0.0, 0.0), (strap_width, 0.0), (strap_width * 0.86, bodice_length),
                       (strap_width * 0.20, bodice_length), (0.0, bodice_length * 0.54)],
            quantity=1, mirror=False, allow_split=False),
        CustomPanelSpec(
            label="ヨル・ホルターネックストラップ（右）",
            points_cm=[(0.0, 0.0), (strap_width * 0.84, 0.0), (strap_width, bodice_length * 0.54),
                       (strap_width * 0.72, bodice_length), (0.0, bodice_length)],
            quantity=1, mirror=False, allow_split=False),
    )
    return CostumeProject(
        key="yor_forger_thorn_princess", label="SPY×FAMILY ヨル・フォージャー（いばら姫）",
        garment_spec_kwargs={
            "neckline": "v_neck", "sleeve_style": None, "skirt_style": "flare",
            "front_zip": False, "include_pants": False, "pants_style": "",
            "include_collar": False, "include_cuffs": False,
            "include_waistband": True, "waistband_style": "contour", "princess_line": False,
        },
        custom_panel_specs=panels, lining=True, shoulder_drop_cm=0.0,
        worn_over_bust_cm=measurements.bust + 5.0,
        patternable_components=(
            "黒ドレス本体（Vネック身頃・フレアスカート・ウエストバンド）", "ドレスの裏地",
            "左右ホルターネックストラップ",
        ),
        separate_components=(
            "金色のヘッドバンド、イヤリング", "黒手袋、ストッキング、靴、ウィッグ",
            "武器小道具（イベント規約・安全基準を必ず確認）",
        ),
        material_plan=(
            "表地: 黒のストレッチツイルまたは中肉サテン。", "裏地: 赤系または黒のすべりのよい裏地。",
            "ストラップ: 芯を貼ったストレッチ合皮またはツイル。", "副資材: コンシールファスナー、接着芯、ホック、肌色テープ。",
        ),
        construction_plan=(
            "身頃を仮縫いして、胸元・脇・ホルターストラップの保持力を最初に確認する。",
            "スカートを接続する前に、必要なスリット位置を本人の歩幅で決める。",
            "裏地を入れてから背中心ファスナーとホックを仕上げる。",
            "アクセサリーは本体の負荷にならないよう別留めにする。",
        ),
        limitations=(
            "深い胸元やスリットの安全性は、着用者の体型・イベント規約・下着設計で変わるため、必ず仮縫いで調整してください。",
            "手袋・ストッキングは伸縮率が大きく、通常布のドレス型紙からは生成しません。",
        ),
        commercial_benchmark=(
            "市販セットは黒ドレス、ヘッドバンド、イヤリング、手袋、ストッキングを含む。",
            "比較対象: Animeclo ヨル衣装 US$24.79、XS〜3XL（2026-09確認）。",
        ),
    )


_CATALOG_ENTRIES: tuple[tuple[str, str, str, str], ...] = (
    # key, 表示名, ジャンル, 検証用の衣服シルエット
    ("genshin_amber", "原神 アンバー", "オープンワールドRPG", "idol"),
    ("genshin_lisa", "原神 リサ", "オープンワールドRPG", "dress"),
    ("genshin_noelle", "原神 ノエル", "オープンワールドRPG", "dress"),
    ("genshin_raiden", "原神 雷電将軍", "オープンワールドRPG", "kimono"),
    ("genshin_ayaka", "原神 神里綾華", "オープンワールドRPG", "kimono"),
    ("genshin_hutao", "原神 胡桃", "オープンワールドRPG", "coat"),
    ("genshin_venti", "原神 ウェンティ", "オープンワールドRPG", "uniform"),
    ("genshin_zhongli", "原神 鍾離", "オープンワールドRPG", "coat"),
    ("hsr_march7", "崩壊：スターレイル 三月なのか", "SF RPG", "idol"),
    ("hsr_danheng", "崩壊：スターレイル 丹恒", "SF RPG", "coat"),
    ("hsr_kafka", "崩壊：スターレイル カフカ", "SF RPG", "dress"),
    ("hsr_himeko", "崩壊：スターレイル 姫子", "SF RPG", "coat"),
    ("hsr_silverwolf", "崩壊：スターレイル 銀狼", "SF RPG", "uniform"),
    ("hsr_firefly", "崩壊：スターレイル ホタル", "SF RPG", "idol"),
    ("demon_tanjiro", "鬼滅の刃 竈門炭治郎", "少年漫画・アニメ", "uniform"),
    ("demon_nezuko", "鬼滅の刃 竈門禰豆子", "少年漫画・アニメ", "kimono"),
    ("demon_zenitsu", "鬼滅の刃 我妻善逸", "少年漫画・アニメ", "uniform"),
    ("demon_inosuke", "鬼滅の刃 嘴平伊之助", "少年漫画・アニメ", "uniform"),
    ("demon_giyu", "鬼滅の刃 冨岡義勇", "少年漫画・アニメ", "uniform"),
    ("demon_rengoku", "鬼滅の刃 煉獄杏寿郎", "少年漫画・アニメ", "uniform"),
    ("sailor_usagi", "美少女戦士セーラームーン 月野うさぎ", "少女漫画・アニメ", "idol"),
    ("sailor_rei", "美少女戦士セーラームーン 火野レイ", "少女漫画・アニメ", "idol"),
    ("sailor_ami", "美少女戦士セーラームーン 水野亜美", "少女漫画・アニメ", "idol"),
    ("sailor_makoto", "美少女戦士セーラームーン 木野まこと", "少女漫画・アニメ", "idol"),
    ("jjk_yuji", "呪術廻戦 虎杖悠仁", "現代ファンタジー漫画・アニメ", "uniform"),
    ("jjk_megumi", "呪術廻戦 伏黒恵", "現代ファンタジー漫画・アニメ", "uniform"),
    ("jjk_nobara", "呪術廻戦 釘崎野薔薇", "現代ファンタジー漫画・アニメ", "uniform"),
    ("jjk_gojo", "呪術廻戦 五条悟", "現代ファンタジー漫画・アニメ", "coat"),
    ("onepiece_luffy", "ONE PIECE モンキー・D・ルフィ", "冒険漫画・アニメ", "uniform"),
    ("onepiece_nami", "ONE PIECE ナミ", "冒険漫画・アニメ", "idol"),
    ("onepiece_zoro", "ONE PIECE ロロノア・ゾロ", "冒険漫画・アニメ", "uniform"),
    ("mha_deku", "僕のヒーローアカデミア 緑谷出久", "ヒーロー漫画・アニメ", "uniform"),
    ("mha_bakugo", "僕のヒーローアカデミア 爆豪勝己", "ヒーロー漫画・アニメ", "uniform"),
    ("mha_ochaco", "僕のヒーローアカデミア 麗日お茶子", "ヒーロー漫画・アニメ", "idol"),
    ("hololive_suisei", "hololive 星街すいせい", "VTuber", "idol"),
    ("hololive_marine", "hololive 宝鐘マリン", "VTuber", "coat"),
    ("hololive_calliope", "hololive 森カリオペ", "VTuber", "dress"),
    ("ff7_cloud", "FINAL FANTASY VII クラウド", "JRPG", "uniform"),
    ("ff7_tifa", "FINAL FANTASY VII ティファ", "JRPG", "idol"),
    ("ff7_aerith", "FINAL FANTASY VII エアリス", "JRPG", "dress"),
    ("ff7_sephiroth", "FINAL FANTASY VII セフィロス", "JRPG", "coat"),
    ("pokemon_misty", "ポケットモンスター カスミ", "ゲーム・アニメ", "idol"),
    ("pokemon_cynthia", "ポケットモンスター シロナ", "ゲーム・アニメ", "coat"),
    ("pokemon_lillie", "ポケットモンスター リーリエ", "ゲーム・アニメ", "dress"),
)


_SILHOUETTE_SPECS: dict[str, dict[str, object]] = {
    "uniform": {"neckline": "round_neck", "sleeve_style": "straight", "skirt_style": None,
                "front_zip": False, "include_pants": True, "pants_style": "tapered",
                "include_collar": False, "include_cuffs": False, "include_waistband": False,
                "princess_line": False},
    "coat": {"neckline": "round_neck", "sleeve_style": "straight", "skirt_style": None,
             "front_zip": True, "include_pants": True, "pants_style": "tapered",
             "include_collar": False, "include_cuffs": False, "include_waistband": False,
             "princess_line": False},
    "dress": {"neckline": "v_neck", "sleeve_style": None, "skirt_style": "flare",
              "front_zip": False, "include_pants": False, "pants_style": "",
              "include_collar": False, "include_cuffs": False, "include_waistband": True,
              "waistband_style": "contour", "princess_line": False},
    "idol": {"neckline": "boat_neck", "sleeve_style": None, "skirt_style": "pleated",
             "front_zip": False, "include_pants": False, "pants_style": "",
             "include_collar": False, "include_cuffs": False, "include_waistband": True,
             "waistband_style": "wide", "princess_line": False},
    "kimono": {"neckline": "v_neck", "sleeve_style": "straight", "skirt_style": "wrap",
               "front_zip": False, "include_pants": False, "pants_style": "",
               "include_collar": False, "include_cuffs": False, "include_waistband": True,
               "waistband_style": "wide", "princess_line": False},
}


def _catalog_project(key: str, label: str, genre: str, silhouette: str,
                     measurements: Measurements) -> CostumeProject:
    """大量比較用キャラを、検証済みの既存シルエットだけで生成する。

    ここは公式衣装の一対一複製ではない。参照画像を追加する前の段階でも、
    ``型紙化できる布`` と ``別途設計すべき意匠`` を区別して、50件のAPI
    生成互換性を継続テストできるようにするカタログである。
    """
    spec = _SILHOUETTE_SPECS[silhouette]
    base = min(20.0, max(12.0, measurements.bust * 0.17))
    length = min(46.0, max(28.0, measurements.height * 0.24))
    panel = CustomPanelSpec(
        label=f"{label}・装飾布ベース",
        points_cm=[(0.0, 0.0), (base, 0.0), (base * 0.90, length * 0.65),
                   (base * 0.43, length), (0.0, length * 0.52)],
        quantity=1, mirror=False, allow_split=False)
    shapes = {
        "uniform": "上着・パンツ・装飾布ベース",
        "coat": "前開きコート・パンツ・装飾布ベース",
        "dress": "身頃・フレアスカート・装飾布ベース",
        "idol": "トップス・プリーツスカート・装飾布ベース",
        "kimono": "和装風身頃・巻きスカート・帯布ベース",
    }
    return CostumeProject(
        key=key, label=f"{label} — {genre}検証ベース",
        garment_spec_kwargs=dict(spec), custom_panel_specs=(panel,),
        lining=silhouette in {"coat", "dress", "kimono"},
        shoulder_drop_cm=2.0 if silhouette in {"coat", "uniform"} else 0.5,
        worn_over_bust_cm=measurements.bust + (8.0 if silhouette == "coat" else 5.0),
        patternable_components=(shapes[silhouette],),
        separate_components=(
            "固有のロゴ・印刷・刺繍", "武器、装甲、帽子、耳、角、尻尾などの立体物",
            "ウィッグ、靴、手袋、伸縮素材の小物",
        ),
        material_plan=(
            "本体: シルエットに合わせた中肉ツイル／ブロード。",
            "意匠: 色別のバイアステープ、合皮、熱転写シートは別工程で検討する。",
        ),
        construction_plan=(
            "本体を仮縫いして可動域と丈を確認する。",
            "色分け・意匠・立体小物は本体の完成後に試作して取り付ける。",
        ),
        limitations=(
            "この項目は自動生成の互換性を確認する検証ベースであり、固有衣装の完成型紙ではありません。",
            "市販品に近い完成度へ進めるには、対象衣装版の正面・背面・側面資料に基づく個別プリセット化が必要です。",
        ),
        commercial_benchmark=(
            f"{genre}系の市販コスプレは衣服本体に加え、印刷・小物・立体装飾をセットにすることが多い。",
            "この検証ベースでは、布型紙にできない要素を必ず別工程として出力する。",
        ),
    )


_PROJECT_BUILDERS = {
    "endministrator_female": _endministrator_female,
    "endministrator_male": _endministrator_male,
    "perlica": _perlica,
    "chen_qianyu": _chen_qianyu,
    "hatsune_miku_classic": _hatsune_miku_classic,
    "yor_forger_thorn_princess": _yor_forger_thorn_princess,
}
_PROJECT_BUILDERS.update({
    key: (lambda measurements, key=key, label=label, genre=genre, silhouette=silhouette:
          _catalog_project(key, label, genre, silhouette, measurements))
    for key, label, genre, silhouette in _CATALOG_ENTRIES
})


def costume_project_choices() -> tuple[tuple[str, str], ...]:
    curated = (("", "指定しない"),
            ("endministrator_female", "管理人（女性）— コート＋ショートパンツ＋非対称裾"),
            ("endministrator_male", "管理人（男性）— ロングコート＋パンツ＋非対称裾"),
            ("perlica", "ペリカ — ワンピース＋コート＋ベルトタブ"),
            ("chen_qianyu", "チェン・センユー — コート＋トップス＋プリーツスカート"),
            ("hatsune_miku_classic", "初音ミク（定番衣装）— トップス＋プリーツ＋ストラップ"),
            ("yor_forger_thorn_princess", "ヨル・フォージャー（いばら姫）— ホルタードレス＋フレア"))
    catalog = tuple((key, f"{label} — {genre}検証ベース")
                    for key, label, genre, _silhouette in _CATALOG_ENTRIES)
    return curated + catalog


def get_costume_project(key: str | None, measurements: Measurements) -> CostumeProject | None:
    """キーが空ならプリセットを使わない。未知のキーは黙って無視しない。"""
    if not key:
        return None
    try:
        builder = _PROJECT_BUILDERS[key]
    except KeyError:
        raise ValueError("衣装プリセットの指定が不正です。") from None
    return builder(measurements)
