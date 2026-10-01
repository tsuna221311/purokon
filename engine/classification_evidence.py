"""複数画像・複数領域のパーツ判定を、入力順に依存せず統合する。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EvidenceAlternative:
    variation: str
    votes: int
    confidence_sum: float
    max_confidence: float

    def as_dict(self) -> dict[str, object]:
        return {
            "variation": self.variation,
            "votes": self.votes,
            "confidence_sum": round(self.confidence_sum, 3),
            "max_confidence": round(self.max_confidence, 3),
        }


@dataclass(frozen=True)
class EvidenceDecision:
    part_type: str
    variation: str
    votes: int
    confidence_sum: float
    alternatives: tuple[EvidenceAlternative, ...] = ()
    conflicted: bool = False

    def as_dict(self) -> dict[str, object]:
        return {
            "part_type": self.part_type,
            "variation": self.variation,
            "votes": self.votes,
            "confidence_sum": round(self.confidence_sum, 3),
            "conflicted": self.conflicted,
            "alternatives": [item.as_dict() for item in self.alternatives],
        }


def _confidence(value: object) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return 0.0


def resolve_classification_evidence(results) -> list[EvidenceDecision]:
    """part_typeごとに票をまとめ、最も根拠の強いvariationを1つ選ぶ。

    合計信頼度、票数、単票の最大信頼度、variation名の順で決めるため、同じ
    判定集合なら画像の投入順を変えても結果は変わらない。次点が首位の65%以上
    かつ合計0.55以上なら、利用者が確認すべき対立として記録する。
    """
    order: list[str] = []
    grouped: dict[str, dict[str, list[float]]] = {}
    for result in results:
        part_type = str(getattr(result, "part_type", "") or "").strip()
        if not part_type:
            continue
        variation = str(getattr(result, "variation", "") or "")
        if part_type not in grouped:
            grouped[part_type] = {}
            order.append(part_type)
        grouped[part_type].setdefault(variation, []).append(
            _confidence(getattr(result, "confidence", 0.0)))

    decisions: list[EvidenceDecision] = []
    for part_type in order:
        ranked = sorted(
            (
                EvidenceAlternative(
                    variation=variation,
                    votes=len(values),
                    confidence_sum=sum(values),
                    max_confidence=max(values, default=0.0),
                )
                for variation, values in grouped[part_type].items()
            ),
            key=lambda item: (-item.confidence_sum, -item.votes,
                              -item.max_confidence, item.variation),
        )
        winner = ranked[0]
        alternatives = tuple(ranked[1:])
        runner_up = alternatives[0] if alternatives else None
        conflicted = bool(
            runner_up
            and runner_up.confidence_sum >= 0.55
            and runner_up.confidence_sum >= winner.confidence_sum * 0.65
        )
        decisions.append(EvidenceDecision(
            part_type=part_type,
            variation=winner.variation,
            votes=winner.votes,
            confidence_sum=winner.confidence_sum,
            alternatives=alternatives,
            conflicted=conflicted,
        ))
    return decisions
