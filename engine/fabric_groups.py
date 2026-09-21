"""生地の割り当て(round54)。1着を複数の生地から裁つための仕分け。

【なぜ要るのか】

キャラクターの衣装は、**1着が1種類の生地でできていない**。本体の色、
差し色、襟や袖口の別布、裏地——3〜5種類使うのがふつうである。ところが
round53まで、この製品は「全パーツを1枚の生地から裁つ」前提で通していた。

round53に実測した、白い身頃＋紺のスカートのワンピース(身長160cm):

    いまの買い物メモ : 幅140cmを181cm  ← 1種類ぶんの数字
    実際に要るもの   : 白 幅110cmを122cm ＋ 紺 幅110cmを124cm
                       合計246cm(+66cm)

数字が足りないだけではない。**配置図が役に立たない**のが本題である。
全パーツを1枚に詰めた配置では、白いパーツと紺のパーツが交互に並ぶ。
その紙を白い生地の上に置いても、紺のパーツのぶんだけ穴が空く。
つまり2色の衣装では、出力そのものがそのままでは使えなかった。

【どう直したか】

パーツを「どの生地から裁つか」でグループに分け、**グループごとに
配置・書き出し・買い物メモを作る**。裏地(round41)が既にやっていることを、
利用者が名前を付けた任意の生地に広げた形である。

割り当ての単位は`ASSIGNABLE_AREAS`——「身頃」「袖」「スカート」のような
**利用者が見て分かる区分**で、内部のpart_typeそのものではない。
part_typeは襟ぐりや切り替え線の選び方で増減する(前身頃が
`front_bodice_center`と`front_bodice_side`に分かれる等)ので、
そのまま見せると画面が構成によって変わってしまう。

グループを1つしか使わない場合(既定)は、round53までと**まったく同じ経路**を
通る。出力もバイト単位で変わらない。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .part_names import part_type_label

#: 既定の生地の名前。1種類しか使わないときは、この名前だけが現れる。
DEFAULT_FABRIC_NAME = "表地"

#: 1回の生成で扱える生地の数の上限。
#:
#: 根拠は「配置・書き出しをグループの数だけ繰り返す」という実装の重さで
#: あって、縫製上の制約ではない。1グループあたりSVG/PDF/DXFの3ファイルを
#: 作るので、無制限にすると1リクエストで大量のファイルを書くことになる。
MAX_FABRIC_GROUPS = 6

#: 生地の名前に許す長さ(文字数)。型紙のページや画面に出す見出しなので、
#: 1行に収まる範囲にする。
MAX_FABRIC_NAME_LENGTH = 20


@dataclass(frozen=True)
class AssignableArea:
    """利用者が生地を割り当てられる区分。

    `part_types`は、この区分に入る内部のpart_type。襟ぐりや切り替え線の
    選び方で実際に出てくるものは変わるが、ここには**出てくる可能性のある
    ものを全部**書いておく(出てこなければ空のグループになるだけで、
    空のグループは捨てる)。
    """

    key: str
    label: str
    part_types: tuple[str, ...]


#: 画面に出す順番でもある(上から着る順・大きい順)。
ASSIGNABLE_AREAS: tuple[AssignableArea, ...] = (
    AssignableArea("bodice", "身頃（前・後ろ）",
                   ("front_bodice", "back_bodice", "front_bodice_zip_panel",
                    "front_bodice_center", "front_bodice_side",
                    "back_bodice_center", "back_bodice_side")),
    AssignableArea("sleeve", "袖", ("sleeve",)),
    AssignableArea("skirt", "スカート", ("skirt",)),
    AssignableArea("pants", "パンツ", ("front_pants", "back_pants")),
    AssignableArea("collar", "衿", ("collar",)),
    AssignableArea("cuffs", "カフス", ("cuffs",)),
    AssignableArea("hood", "フード", ("hood",)),
    AssignableArea("waistband", "ウエストバンド", ("waistband",)),
    AssignableArea("custom_panel", "カスタムパーツ", ("custom_panel",)),
)

#: part_type -> 区分のkey。
PART_TYPE_TO_AREA: dict[str, str] = {
    part_type: area.key
    for area in ASSIGNABLE_AREAS
    for part_type in area.part_types
}


class FabricGroupError(ValueError):
    """生地の割り当てが受け取れないときに投げる。"""


def area_label(key: str) -> str:
    for area in ASSIGNABLE_AREAS:
        if area.key == key:
            return area.label
    return key


def validate_fabric_name(raw: str) -> str:
    """生地の名前を検査して返す。

    型紙のページ・画面・ファイル名の説明に出るので、改行やタブが入ると
    レイアウトが崩れる。長さも1行に収まる範囲に限る。
    """
    name = " ".join(str(raw).split())  # 改行・連続空白を1つの空白に潰す
    if not name:
        raise FabricGroupError("生地の名前を入力してください。")
    if len(name) > MAX_FABRIC_NAME_LENGTH:
        raise FabricGroupError(
            f"生地の名前は{MAX_FABRIC_NAME_LENGTH}文字までにしてください: {name!r}")
    return name


def normalize_assignments(raw: dict[str, str] | None) -> dict[str, str]:
    """{区分key: 生地の名前} を検査して整える。

    空欄の区分は「既定の生地」に入るので、ここには入れない(呼び出し側が
    `assign_parts`で既定名に落とす)。知らない区分keyは黙って捨てずに
    エラーにする——綴りを間違えたまま「割り当てたつもり」になるのを防ぐ。
    """
    if not raw:
        return {}
    known = {area.key for area in ASSIGNABLE_AREAS}
    cleaned: dict[str, str] = {}
    for key, value in raw.items():
        if key not in known:
            raise FabricGroupError(f"知らない区分です: {key!r}")
        if value is None or not str(value).strip():
            continue
        cleaned[key] = validate_fabric_name(value)
    names = {name for name in cleaned.values()}
    if len(names) > MAX_FABRIC_GROUPS:
        raise FabricGroupError(
            f"生地は{MAX_FABRIC_GROUPS}種類までです（現在{len(names)}種類）。")
    return cleaned


def fabric_name_for(part_type: str, assignments: dict[str, str],
                    default_name: str = DEFAULT_FABRIC_NAME) -> str:
    """このpart_typeを、どの生地から裁つか。"""
    area = PART_TYPE_TO_AREA.get(part_type)
    if area is None:
        return default_name
    return assignments.get(area, default_name)


@dataclass
class FabricGroup:
    """1種類の生地と、そこから裁つパーツ。"""

    name: str
    parts: list = field(default_factory=list)

    @property
    def part_labels(self) -> list[str]:
        """この生地から裁つパーツの名前(重複を除き、出てくる順)。"""
        seen: list[str] = []
        for part in self.parts:
            label = part_type_label(part.part_type)
            if label not in seen:
                seen.append(label)
        return seen


def split_parts(parts: list, assignments: dict[str, str] | None,
                default_name: str = DEFAULT_FABRIC_NAME) -> list[FabricGroup]:
    """パーツを生地ごとに分ける。

    並び順は「そのパーツが最初に現れた順」にする。番号や名前の五十音で
    並べ替えると、画面と型紙で順番が食い違ったときに追いにくい。

    割り当てが空、または実際には1種類にしかならない場合は、**1つの
    グループ**を返す。呼び出し側はその場合に従来の経路をそのまま通れる。
    """
    assignments = assignments or {}
    groups: dict[str, FabricGroup] = {}
    order: list[str] = []
    for part in parts:
        name = fabric_name_for(part.part_type, assignments, default_name)
        if name not in groups:
            groups[name] = FabricGroup(name=name)
            order.append(name)
        groups[name].parts.append(part)
    return [groups[name] for name in order]


def uses_multiple_fabrics(parts: list, assignments: dict[str, str] | None,
                          default_name: str = DEFAULT_FABRIC_NAME) -> bool:
    """実際に2種類以上の生地に分かれるか。

    「割り当てが指定されているか」ではなく「**分かれるか**」を見る。
    全部の区分に同じ名前を書いた場合や、割り当てた区分のパーツが
    そもそも構成に無い場合は、1種類のままなので従来の経路でよい。
    """
    return len(split_parts(parts, assignments, default_name)) > 1
