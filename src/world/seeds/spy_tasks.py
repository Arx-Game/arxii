"""Spy Job Kit sample templates (#2833) — PLACEHOLDER content.

Seeds the six spy job templates with routes keyed to the best success tier
and worst failure tier present in the seeded check-resolution content, plus
a "Spywork Exposure" risk pool (ASSET_STATUS COMPROMISED on any tier —
tier-filtering happens at selection). Skips gracefully on shards without
CheckOutcome rows or a usable CheckType. All prose and difficulties are
PLACEHOLDER for Apostate's pass.
"""

from __future__ import annotations

from datetime import timedelta

from world.tasking.constants import TaskCategory, TaskTargetKind
from world.tasking.models import TaskOutcomeRoute, TaskTemplate

_CHECK_PREFERENCE = ("Stealth", "Perception", "Intimidation")

# name, category, target kind, description, success payout kwargs, failure payout kwargs
_TEMPLATES = [
    (
        "Shadow the Mark",
        TaskCategory.SPYCRAFT,
        TaskTargetKind.PERSONA,
        "PLACEHOLDER Follow them for a fortnight and report where they go.",
        {"movements_report": True},
        {"incriminate_level": 1},
    ),
    (
        "Unmask the Stranger",
        TaskCategory.SPYCRAFT,
        TaskTargetKind.PERSONA,
        "PLACEHOLDER Learn who they really are beneath the name they wear.",
        {"unmask_target": True},
        {"incriminate_level": 2},
    ),
    (
        "Whisper Campaign",
        TaskCategory.SPYCRAFT,
        TaskTargetKind.PERSONA,
        "PLACEHOLDER Make sure everyone hears what is already being said about them.",
        {"gossip_heat_delta": 15},
        {"incriminate_level": 2},
    ),
    (
        "Quiet the Whispers",
        TaskCategory.SPYCRAFT,
        TaskTargetKind.PERSONA,
        "PLACEHOLDER Buy silence, misdirect gossips, cool what is being said.",
        {"gossip_heat_delta": -15},
        {},
    ),
    (
        "Sabotage the Works",
        TaskCategory.CRIME,
        TaskTargetKind.ROOM,
        "PLACEHOLDER Something breaks. A shame, in a place like this.",
        {"building_condition_delta": -1},
        {"incriminate_level": 3},
    ),
    (
        "Suborn the Servant",
        TaskCategory.SPYCRAFT,
        TaskTargetKind.PERSONA,
        "PLACEHOLDER Coin and kindness until someone useful starts answering to us.",
        {"recruit_target": True},
        {"incriminate_level": 2},
    ),
]


def _outcome_tiers():
    """(best success, worst failure) CheckOutcome rows, or (None, None)."""
    from world.traits.models import CheckOutcome  # noqa: PLC0415

    best = CheckOutcome.objects.filter(success_level__gt=0).order_by("-success_level").first()
    worst = CheckOutcome.objects.filter(success_level__lte=0).order_by("success_level").first()
    return best, worst


def _spywork_pool():
    from actions.models.consequence_pools import (  # noqa: PLC0415
        ConsequencePool,
        ConsequencePoolEntry,
    )
    from world.assets.constants import AssetStatus  # noqa: PLC0415
    from world.checks.constants import EffectType  # noqa: PLC0415
    from world.checks.models import Consequence, ConsequenceEffect  # noqa: PLC0415

    _, worst = _outcome_tiers()
    if worst is None:
        return None
    pool, _ = ConsequencePool.objects.get_or_create(
        name="Spywork Exposure",
        defaults={"description": "PLACEHOLDER The risk every dirty job carries."},
    )
    consequence, created = Consequence.objects.get_or_create(
        label="Agent Compromised",
        outcome_tier=worst,
        defaults={
            "mechanical_description": "PLACEHOLDER The agent is burned.",
            "weight": 1,
            "character_loss": False,
        },
    )
    if created:
        ConsequenceEffect.objects.create(
            consequence=consequence,
            effect_type=EffectType.ASSET_STATUS,
            asset_status_target=AssetStatus.COMPROMISED,
            execution_order=0,
        )
    ConsequencePoolEntry.objects.get_or_create(pool=pool, consequence=consequence)
    return pool


def _check_type():
    from world.checks.models import CheckType  # noqa: PLC0415

    for name in _CHECK_PREFERENCE:
        check_type = CheckType.objects.filter(name=name).first()
        if check_type is not None:
            return check_type
    return CheckType.objects.first()


def ensure_spy_task_templates() -> int:
    """Seed the six spy job templates. Idempotent; returns templates ensured."""
    best, worst = _outcome_tiers()
    check_type = _check_type()
    if best is None or check_type is None:
        return 0  # unseeded shard: check content hasn't landed yet
    pool = _spywork_pool()

    ensured = 0
    for name, category, target_kind, description, on_success, on_failure in _TEMPLATES:
        template, created = TaskTemplate.objects.get_or_create(
            name=name,
            defaults={
                "description": description,
                "category": category,
                "check_type": check_type,
                "check_difficulty": 10,  # PLACEHOLDER
                "duration": timedelta(days=3),  # PLACEHOLDER
                "target_kind": target_kind,
                "consequence_pool": pool,
            },
        )
        ensured += int(created)
        TaskOutcomeRoute.objects.get_or_create(
            template=template,
            outcome_tier=best,
            defaults={
                "report_template": (
                    "PLACEHOLDER {agent} returns from {task} against {target}, satisfied."
                ),
                **on_success,
            },
        )
        if worst is not None and on_failure:
            TaskOutcomeRoute.objects.get_or_create(
                template=template,
                outcome_tier=worst,
                defaults={
                    "report_template": (
                        "PLACEHOLDER {agent} returns from {task} shaken — it went badly."
                    ),
                    **on_failure,
                },
            )
    return ensured
