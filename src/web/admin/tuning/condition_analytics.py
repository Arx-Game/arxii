"""Condition-danger analytics for the Game Tuning dashboard (#1221 Task 4).

For a chosen severity level, ranks every `ConditionTemplate` by a composite
"danger score" combining its worst-stage severity multiplier and its
damage-over-time throughput, so a designer can spot conditions that are
disproportionately lethal (or toothless) at a given severity. Built with a
bounded, fixed number of queries regardless of table size — no per-template
queries in a loop (see `compute_condition_danger`).
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from django.db.models import Prefetch

from world.conditions.models import ConditionDamageOverTime, ConditionStage, ConditionTemplate

# Weight applied to `dot_per_round` inside `danger_score` — DoT throughput is
# recurring (fires every round) so it's weighted higher than the one-time
# effective_severity figure.
DOT_WEIGHT = 2.0


@dataclass(frozen=True)
class ConditionDangerRow:
    """Danger analytics for one `ConditionTemplate` at a chosen severity level.

    Scaling formula (deliberately kept simple, decided here rather than in the
    domain model — see #1221 Task 4 brief):

    - `effective_severity = at_severity * max_stage_multiplier`: the stage
      multiplier (the worst/highest of the template's stages, or 1.0 if the
      template has no stages) applies ONLY here.
    - `dot_per_round`'s scaling severity is `at_severity` directly — the stage
      multiplier does NOT apply to DoT scaling, even for a DoT attached to a
      specific stage. This keeps the two figures independently legible: one
      shows how stage progression amplifies severity, the other shows raw
      damage throughput at a given severity, without compounding.
    - `danger_score = effective_severity + dot_per_round * DOT_WEIGHT`.
    """

    template_name: str
    at_severity: int
    max_stage_multiplier: float
    effective_severity: float
    dot_per_round: float
    days_to_decay: float | None
    danger_score: float


def compute_condition_danger(*, at_severity: int = 5) -> list[ConditionDangerRow]:
    """Danger analytics for every `ConditionTemplate`, sorted by danger_score desc.

    Fixed query count: one for templates, one for their stages (prefetched),
    one for all `ConditionDamageOverTime` rows (grouped in Python by the
    condition/stage they attach to) — never scales with the number of
    templates.
    """
    templates = list(
        ConditionTemplate.objects.prefetch_related(
            Prefetch(
                "stages",
                queryset=ConditionStage.objects.order_by("stage_order"),
                to_attr="cached_stages",
            )
        )
    )

    dots_by_condition_id: dict[int, list[ConditionDamageOverTime]] = defaultdict(list)
    dots_by_stage_id: dict[int, list[ConditionDamageOverTime]] = defaultdict(list)
    for dot in ConditionDamageOverTime.objects.all():
        if dot.condition_id is not None:
            dots_by_condition_id[dot.condition_id].append(dot)
        else:
            dots_by_stage_id[dot.stage_id].append(dot)

    rows: list[ConditionDangerRow] = []
    for template in templates:
        stages: list[ConditionStage] = template.cached_stages
        max_stage_multiplier = (
            max(float(stage.severity_multiplier) for stage in stages) if stages else 1.0
        )
        effective_severity = at_severity * max_stage_multiplier

        dot_rows = list(dots_by_condition_id.get(template.pk, ()))
        for stage in stages:
            dot_rows.extend(dots_by_stage_id.get(stage.pk, ()))
        dot_per_round = float(
            sum(
                dot.base_damage * (at_severity if dot.scales_with_severity else 1)
                for dot in dot_rows
            )
        )

        decay = template.passive_decay_per_day
        days_to_decay = (at_severity / decay) if decay else None

        danger_score = effective_severity + dot_per_round * DOT_WEIGHT

        rows.append(
            ConditionDangerRow(
                template_name=template.name,
                at_severity=at_severity,
                max_stage_multiplier=max_stage_multiplier,
                effective_severity=effective_severity,
                dot_per_round=dot_per_round,
                days_to_decay=days_to_decay,
                danger_score=danger_score,
            )
        )

    rows.sort(key=lambda row: (-row.danger_score, row.template_name))
    return rows
