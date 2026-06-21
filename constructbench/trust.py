from __future__ import annotations

from constructbench.state import TrustAssessment


def mean_pairwise_trust(trust_state: dict[str, dict[str, TrustAssessment]]) -> float:
    values: list[float] = []
    for row in trust_state.values():
        for assessment in row.values():
            values.extend(
                [
                    assessment.performance_reliability,
                    assessment.information_reliability,
                    assessment.contractual_reliability,
                ]
            )
    return sum(values) / len(values) if values else 0.0
