"""Default skill-breakthrough catalog seed (#2115).

Every skill's four XP boundaries (20/30/40/50) need a purchasable
``TraitRatingUnlock`` or the breakthrough purchase is a landmine no player can
ever clear — mirrors the #2116(a) authored-unlock landmine pattern. Seeds one
shared ``XPCostChart`` ("Skill Breakthroughs") with a flat placeholder cost
curve, then a ``TraitXPCost`` + four ``TraitRatingUnlock`` rows per ``Skill``.

Idempotent throughout (get_or_create / update_or_create). Content only — no
data migration (ADR-0013). Must run *after* every cluster that seeds new
``Skill`` rows (``combat_checks``/``social``/``investigation``/``governance``/
``stealth``) since it iterates ``Skill.objects.all()`` at call time; re-run
this seeder (it is idempotent) after authoring a new skill outside those
clusters.
"""

from __future__ import annotations

_CHART_NAME = "Skill Breakthroughs"

# Flat placeholder cost curve — staff-tunable content, not a final economy
# (mirrors the sanctum touchstone precedent: minimum reachable, not tuned).
_FLAT_COST_PER_BOUNDARY: dict[int, int] = {
    20: 50,
    30: 100,
    40: 150,
    50: 200,
}


def seed_skill_breakthrough_catalog() -> None:
    """Idempotently seed the shared skill-breakthrough XP-cost chart + unlocks."""
    from world.progression.models import (  # noqa: PLC0415
        TraitRatingUnlock,
        TraitXPCost,
        XPCostChart,
        XPCostEntry,
    )
    from world.skills.models import Skill  # noqa: PLC0415

    chart, _ = XPCostChart.objects.update_or_create(
        name=_CHART_NAME,
        defaults={
            "description": "Default placeholder cost curve for skill XP-boundary breakthroughs.",
            "is_active": True,
        },
    )
    for level, cost in _FLAT_COST_PER_BOUNDARY.items():
        XPCostEntry.objects.update_or_create(
            chart=chart,
            level=level,
            defaults={"xp_cost": cost},
        )

    for skill in Skill.objects.select_related("trait").all():
        TraitXPCost.objects.get_or_create(trait=skill.trait, cost_chart=chart)
        for rating in _FLAT_COST_PER_BOUNDARY:
            TraitRatingUnlock.objects.get_or_create(trait=skill.trait, target_rating=rating)
