"""stash.py — 「家にある生地で足りるか」を判定する。round39で追加。

【round38まで何が足りなかったか】買い物メモで生地幅ごとの必要量は出せる
ようになった。だが実際によくあるのは**これから買う**話ではなく、
「押し入れに幅110cmの生地が1.8mある。これで作れる?」である。
round38の表を見て自分で引き算すれば分かる——が、**作れないと分かった
あとが行き止まり**だった。何をどれだけ変えれば入るのかは、
利用者が採寸や構成をいじって何度も生成し直すしかない。

【このモジュールがやること】
足りるかを判定し、足りなければ**何をどれだけ変えれば入るか**を出す。
肝心なのは、その提案を**推定しないこと**である。「丈を5cm詰めれば入る
はず」ではなく、実際に丈を詰めた型紙を作り直してネスティングし、
入ることを確かめてから言う。詰める量も二分探索で実測する。

【出さないもの】
入らない場合に「諦めてください」以外の逃げ道が無いときは、無理に
提案をひねり出さない。詰めれば入る、という嘘をつく方が有害である。
"""

from __future__ import annotations

from dataclasses import dataclass, field

# round59: 買う量は10cm単位に切り上げる。切り上げ方は買い物メモ
# (engine/fabric.py)が既に持っているので、同じものを使う——同じ画面に
# 出る2つの数字が別々の丸め方をしていると、どちらが本当か分からなくなる。
from .fabric import round_up_to_buy

#: 手持ちの生地として受け付ける最小の長さ(cm)。これ未満は入力ミスとみなす。
MIN_STASH_LENGTH_CM = 10.0

#: 丈を詰める提案で、これ以上短くはしない(cm)。
#: スカートがこれより短いと下着が見えるので、提案として成立しない。
MIN_SKIRT_LENGTH_CM = 30.0

#: 袖丈を詰める提案の下限(cm)。半袖よりさらに短いものは提案しない。
MIN_SLEEVE_LENGTH_CM = 20.0

#: 二分探索の打ち切り幅(cm)。これ以上細かく詰めても、裁つときに意味が無い。
_SEARCH_TOLERANCE_CM = 1.0

#: 提案として意味のある最小の短縮量(cm)。1cm未満の短縮は誤差の範囲。
_MIN_USEFUL_REDUCTION_CM = 1.0

#: 「幅の広い生地に替える」提案で、買う量がこれ以上減らないなら出さない(cm)。
#: 10cm単位で切り売りされるので、1単位も減らない提案は意味が無い。
_MIN_USEFUL_SAVING_CM = 10.0


@dataclass(frozen=True)
class StashSuggestion:
    """入らなかったときの逃げ道を1つ。すべて実際に作り直して確かめた結果。"""
    kind: str
    label: str
    detail: str

    def as_dict(self) -> dict:
        return {"kind": self.kind, "label": self.label, "detail": self.detail}


@dataclass
class StashVerdict:
    """手持ちの生地で足りるかの判定。"""
    have_width_cm: float
    have_length_cm: float
    needed_length_cm: float
    fits: bool
    leftover_cm: float = 0.0
    shortfall_cm: float = 0.0
    all_parts_fit: bool = True
    suggestions: list[StashSuggestion] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    #: round59: 足りないときに**買い足す量**(10cm単位)。
    #: 「98.8cm足りません」は裁断台で頼めない数字である。
    buy_more_cm: int = 0
    #: round59: 幅の広い生地に替えたときの (幅, 買う量)。無ければ None。
    wider_option: tuple[float, int] | None = None

    def as_dict(self) -> dict:
        return {
            "have_width_cm": self.have_width_cm,
            "have_length_cm": self.have_length_cm,
            "needed_length_cm": round(self.needed_length_cm, 1),
            "fits": self.fits,
            "leftover_cm": round(self.leftover_cm, 1),
            "shortfall_cm": round(self.shortfall_cm, 1),
            "all_parts_fit": self.all_parts_fit,
            "suggestions": [s.as_dict() for s in self.suggestions],
            "notes": list(self.notes),
            "buy_more_cm": self.buy_more_cm,
            "wider_option": (list(self.wider_option) if self.wider_option else None),
        }


def _needed_length(build, **kwargs) -> tuple[float, bool]:
    """その条件で作った型紙が、手持ちの幅で何cm要るかを返す。

    `skip_export=True`で呼ぶ——ここでの生成は**測るためだけ**のもので、
    途中経過のSVG/PDF/DXFは誰も見ない。書き出すと時間もディスクも無駄になる。

    Returns:
        (必要な丈, 全パーツが配置できたか)
    """
    result = build(skip_export=True, **kwargs)
    return result.nesting.used_length_cm, not result.nesting.unplaced


def _shortest_that_fits(build, part_type: str, current_cm: float,
                         floor_cm: float, have_length_cm: float,
                         **kwargs) -> float | None:
    """その部位を何cmまで詰めれば手持ちに収まるかを、二分探索で実測する。

    「たぶんこれくらい」ではなく、**実際にその丈で型紙を作り直して**
    ネスティングし、収まったかどうかで判定する。丈を縮めると必要な生地丈が
    単調に減る、という前提だけを使う(型紙の丈が短くなれば、それを含む
    レイアウトが長くなることはない)。

    Returns:
        収まる最長の丈(cm)。floor_cmまで詰めても収まらなければ None。
    """
    at_floor, floor_ok = _needed_length(
        build, design_length_overrides={part_type: floor_cm}, **kwargs)
    if not floor_ok or at_floor > have_length_cm:
        return None            # 下限まで詰めても入らない。逃げ道にならない。

    lo, hi = floor_cm, current_cm        # lo は収まる、hi は収まらない
    while hi - lo > _SEARCH_TOLERANCE_CM:
        mid = (lo + hi) / 2.0
        needed, ok = _needed_length(
            build, design_length_overrides={part_type: mid}, **kwargs)
        if ok and needed <= have_length_cm:
            lo = mid
        else:
            hi = mid
    return lo


def evaluate_stash(build, *, have_width_cm: float, have_length_cm: float,
                    current_lengths: dict[str, float] | None = None,
                    allow_rotation: bool = False,
                    one_way_fabric: bool = False,
                    other_width_candidates: tuple[float, ...] = ()) -> StashVerdict:
    """手持ちの生地で足りるかを判定し、足りなければ逃げ道を出す。

    Args:
        build: `(**kwargs) -> PipelineResult` を返す呼び出し可能オブジェクト。
            `fabric_width_candidates` / `allow_rotation` / `one_way_fabric` /
            `design_length_overrides` を受け取れること。
        have_width_cm / have_length_cm: 手持ちの生地の幅と長さ。
        current_lengths: いまの型紙での部位ごとの丈(cm)。詰める提案の
            出発点に使う。渡さなければ丈を詰める提案は出さない
            (現在値が分からないまま「詰めれば入る」とは言えない)。
        other_width_candidates: round59で追加。手芸店で買える他の生地幅。
            手持ちで足りないとき、**その幅で実際にネスティングし直して**、
            買う量が減るならそれを言う。渡さなければ従来どおりこの提案は
            出さない(どの幅が買えるのかは呼び出し側しか知らない)。
    """
    if have_length_cm < MIN_STASH_LENGTH_CM:
        raise ValueError(
            f"手持ちの生地の長さは{MIN_STASH_LENGTH_CM:g}cm以上で指定してください")

    base = dict(fabric_width_candidates=(have_width_cm,),
                 allow_rotation=allow_rotation, one_way_fabric=one_way_fabric)
    needed, all_fit = _needed_length(build, **base)

    verdict = StashVerdict(
        have_width_cm=have_width_cm, have_length_cm=have_length_cm,
        needed_length_cm=needed, fits=False, all_parts_fit=all_fit)

    if not all_fit:
        # 幅が足りず、そもそもパーツが載らない。長さの問題ではないので、
        # 丈を詰める提案は意味を成さない(詰めても幅は変わらない)。
        verdict.notes.append(
            f"幅{have_width_cm:g}cmには収まらないパーツがあります。"
            "長さではなく幅が足りていないので、丈を詰めても解決しません。"
            "もっと幅の広い生地を使うか、パーツの構成を変えてください。")
        return verdict

    if needed <= have_length_cm:
        verdict.fits = True
        verdict.leftover_cm = have_length_cm - needed
        return verdict

    verdict.shortfall_cm = needed - have_length_cm
    # 裁断台で頼める量にしておく。「98.8cm足りません」と言われても、
    # 店では10cm単位でしか切ってもらえない。
    verdict.buy_more_cm = round_up_to_buy(verdict.shortfall_cm)

    # --- 逃げ道を探す。どれも実際に作り直して確かめる ---
    #
    # 【組み合わせも試す理由】最初は「回転を許す」「丈を詰める」を別々にしか
    # 試していなかった。実測(標準M・幅110cm・手持ち180cm)では:
    #     そのまま 247cm / 回転あり 237cm / スカート30cm 187cm
    #     回転 + スカート30cm  **171cm** ← これだけが収まる
    # 単独では1つも収まらないのに、組み合わせれば収まる。別々にしか見て
    # いないと「収まりません」と答えてしまう——**入る道があるのに無いと
    # 言う**のがいちばん悪い。単独 → 組み合わせの順に試す。

    can_rotate = not allow_rotation and not one_way_fabric

    def _try_rotation(extra_overrides=None):
        return _needed_length(
            build, fabric_width_candidates=(have_width_cm,),
            allow_rotation=True, one_way_fabric=False,
            **({"design_length_overrides": extra_overrides} if extra_overrides else {}))

    # 1) 90度回転を許す(非方向性の生地なら使える)
    rotation_fits = False
    if can_rotate:
        rotated_needed, rotated_ok = _try_rotation()
        if rotated_ok and rotated_needed <= have_length_cm:
            rotation_fits = True
            verdict.suggestions.append(StashSuggestion(
                kind="allow_rotation",
                label="「非方向性の生地を使う」をオンにする",
                detail=(f"90度回転を許すと{rotated_needed:.0f}cmで収まります"
                        f"（いまは{needed:.0f}cm）。ニット・無地など、"
                        "布目の向きが仕上がりに影響しない生地でだけ使えます。"
                        "先染めチェック・ストライプ・起毛では使わないでください。")))

    # 2) 丈を詰める(いまの設定のまま)
    shortenable = [
        (part_type, label, floor_cm, (current_lengths or {}).get(part_type))
        for part_type, label, floor_cm in (
            ("skirt", "スカート", MIN_SKIRT_LENGTH_CM),
            ("sleeve", "袖", MIN_SLEEVE_LENGTH_CM))
    ]
    shortened_any = False
    for part_type, label, floor_cm, current in shortenable:
        if not current or current <= floor_cm + _MIN_USEFUL_REDUCTION_CM:
            continue
        fitting = _shortest_that_fits(
            build, part_type, current, floor_cm, have_length_cm,
            fabric_width_candidates=(have_width_cm,),
            allow_rotation=allow_rotation, one_way_fabric=one_way_fabric)
        if fitting is None:
            continue
        reduction = current - fitting
        if reduction < _MIN_USEFUL_REDUCTION_CM:
            continue
        shortened_any = True
        verdict.suggestions.append(StashSuggestion(
            kind=f"{part_type}_length",
            label=f"{label}の丈を{reduction:.0f}cm詰める",
            detail=(f"{label}を{current:.0f}cmから{fitting:.0f}cmにすると"
                    f"収まります（実際にその丈で型紙を作り直して確かめた値です）。")))

    # 3) 単独で1つも収まらなければ、回転と丈詰めを組み合わせる
    if can_rotate and not rotation_fits and not shortened_any:
        for part_type, label, floor_cm, current in shortenable:
            if not current or current <= floor_cm + _MIN_USEFUL_REDUCTION_CM:
                continue
            fitting = _shortest_that_fits(
                build, part_type, current, floor_cm, have_length_cm,
                fabric_width_candidates=(have_width_cm,),
                allow_rotation=True, one_way_fabric=False)
            if fitting is None:
                continue
            reduction = current - fitting
            if reduction < _MIN_USEFUL_REDUCTION_CM:
                continue
            combined, _ok = _try_rotation({part_type: fitting})
            verdict.suggestions.append(StashSuggestion(
                kind=f"rotation_and_{part_type}_length",
                label=(f"「非方向性の生地を使う」をオンにして、"
                       f"{label}の丈を{reduction:.0f}cm詰める"),
                detail=(f"どちらか片方だけでは収まりませんが、両方あわせると"
                        f"{combined:.0f}cmになり収まります"
                        f"（{label} {current:.0f}cm → {fitting:.0f}cm）。"
                        "回転は、布目の向きが仕上がりに影響しない生地でだけ"
                        "使えます。")))
            break        # 1つ見つかれば十分。並べても選びにくくなるだけ。

    # 4) もっと幅の広い生地に替える(round59)
    #
    # 【round58まで何を言っていなかったか】手持ちで足りないとき、逃げ道は
    # 「回転」「丈を詰める」の2つしか探していなかった。どちらも駄目なら
    # 「生地を足すか、パーツの構成を変えてください」で終わっていた。
    #
    # ところが**買い物メモは同じ型紙を幅ごとに測っている**。実測
    # (バスト88・フレアスカート):
    #
    #     幅110cm … 248.8cm 要る（買うのは250cm）
    #     幅140cm … 181.6cm 要る（買うのは190cm）
    #
    # つまり手芸店に立っている人にとっていちばん役に立つ答え——
    # 「幅140cmの生地なら190cmで足ります」——を、**既に測ってあるのに
    # 言っていなかった**。しかも画面には買い物メモの181.6cmが並んで出る
    # ので、248.8cmと矛盾して見えていた。
    #
    # 買う量が10cm単位で1つも減らないなら出さない(意味が無い)。
    #
    # ここより上の提案は**手持ちを使い切る**道、ここから下は**買う**道。
    # 下の注記("手持ちでは入りませんでした")は、上が1つも見つからなかった
    # ことについて言うので、買う道が見つかったかどうかでは変えない。
    has_stash_route = bool(verdict.suggestions)
    if other_width_candidates:
        best: tuple[float, int] | None = None
        same_width_buy = round_up_to_buy(needed)
        for width in sorted(w for w in other_width_candidates if w > have_width_cm):
            other_needed, other_ok = _needed_length(
                build, fabric_width_candidates=(width,),
                allow_rotation=allow_rotation, one_way_fabric=one_way_fabric)
            if not other_ok:
                continue        # その幅でも載らないパーツがある
            other_buy = round_up_to_buy(other_needed)
            if same_width_buy - other_buy < _MIN_USEFUL_SAVING_CM:
                continue
            if best is None or other_buy < best[1]:
                best = (width, other_buy)
        if best is not None:
            width, buy = best
            verdict.wider_option = best
            # 手持ちを使い切る逃げ道が他にあるなら、それを優先してほしい
            # (買わずに済む)。この提案は最後に置き、そう書き添える。
            # どちらが得かは決めつけない。**新しく買う長さ**を並べて、
            # 短い方を言うだけにする(値段は生地によって違うので、
            # 「安い」とは言えない。言えるのは長さだけである)。
            if verdict.buy_more_cm < buy:
                compare = (
                    f"新しく買う長さは、手持ちに足す方が短く済みます"
                    f"（{verdict.buy_more_cm}cm と {buy}cm）。"
                    "ただし手持ちと同じ生地が、まだ手に入る場合に限ります。")
            elif verdict.buy_more_cm == buy:
                # 【round59に踏んだ間違い】ここを`else`にまとめていたので、
                # 買う長さが同じ190cmと190cmのときに「幅140cmに替える方が
                # 短く済みます（190cm と 190cm）」と書いていた。**同じ数字を
                # 並べて「短い」と言っていた**(round39のテストが捕まえた)。
                compare = (
                    f"新しく買う長さはどちらも{buy}cmです。"
                    "手持ちに足す方なら、いまの生地も使い切れます"
                    "（手持ちと同じ生地が、まだ手に入る場合に限ります）。")
            else:
                compare = (
                    f"新しく買う長さは、幅{width:g}cmに替える方が短く済みます"
                    f"（{buy}cm と {verdict.buy_more_cm}cm）。")
            closing = ("手持ちを使い切りたい場合は、上の逃げ道なら"
                        "買わずに済みます。" if verdict.suggestions else "")
            verdict.suggestions.append(StashSuggestion(
                kind="wider_fabric",
                label=f"幅{width:g}cmの生地に替えるなら{buy}cmで足ります",
                detail=(
                    f"手持ちは幅{have_width_cm:g}cmなので、同じ型紙に"
                    f"{same_width_buy}cm要ります"
                    f"（いまの手持ちにあと{verdict.buy_more_cm}cm）。"
                    f"幅{width:g}cmなら{buy}cmです"
                    "（その幅で実際に並べ直して測った値です）。"
                    + compare + closing)))

    if not has_stash_route:
        # ひねり出さない。入らないものは入らないと言う。
        #
        # 【同じことを3回言わない】買う道が見つかったときは、必要量も
        # 買い足す量も**画面の見出しとその提案に既に出ている**。ここで
        # もう一度書くと、スマホの画面で同じ数字が3回並ぶ(実際にそうなり、
        # 端末の画面いっぱいが同じ話で埋まった)。ここでしか言えないのは
        # 「手持ちに収める道は探したが無かった」ことだけなので、それに絞る。
        if verdict.suggestions:
            verdict.notes.append(
                "丈を詰める・回転を許すといった範囲では、手持ちに"
                "収まりませんでした。")
        else:
            # 買う道も無いときは、ここが唯一の行き先になる。数字を出す。
            verdict.notes.append(
                f"あと{verdict.buy_more_cm}cm足りません"
                f"（幅{have_width_cm:g}cmで裁つと{needed:.1f}cm要ります）。"
                "丈を詰める・回転を許すといった範囲では、手持ちに"
                "収まりませんでした。同じ生地を買い足すか、"
                "パーツの構成を変えてください。")
    return verdict
