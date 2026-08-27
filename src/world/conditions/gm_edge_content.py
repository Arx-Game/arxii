"""Edge / Setback GM-fiat condition content (#3387).

A curated, catalog-safe one-round nudge a GM can apply through the existing
``gm_apply_condition`` lever (ruling 1, 2026-08-26 combat audit) — no new
mechanism, just two authored ``ConditionTemplate`` rows that deliver their
effect via a ``ConditionCheckModifier`` row scoped to the Combat
``CheckCategory``, matching the model docstring's own category-scoped
precedent ("Wounded gives -5 to all physical checks"). ``duration_rounds=1``
expires the nudge at that round's own end-of-round tick — a GM applying it
before or during a round covers every check made in that round; see the
#3387 spec for the full round-tick trace.

Mirrors ``ensure_berserk_content``/``ensure_intoxication_content``'s
get-or-create shape (this file, like those, is the authoring surface for this
content — not a seeder hanging config off already-authored rows).
"""

from __future__ import annotations

EDGE_CONDITION_NAME = "Edge"
SETBACK_CONDITION_NAME = "Setback"
GM_FIAT_CATEGORY_NAME = "GM Fiat"

# A modest, clearly-felt one-round nudge — matches the -10 test-factory-default
# precedent surveyed in the #3387 spec (seeded magnitudes run -5..-30).
EDGE_MODIFIER_VALUE = 10
SETBACK_MODIFIER_VALUE = -10


def ensure_gm_edge_content() -> None:
    """Idempotently seed the GM Fiat category + the Edge/Setback templates."""
    from world.conditions.constants import DurationType  # noqa: PLC0415
    from world.conditions.models import ConditionCategory, ConditionTemplate  # noqa: PLC0415

    category, _ = ConditionCategory.objects.get_or_create(
        name=GM_FIAT_CATEGORY_NAME,
        defaults={
            "description": (
                "A GM's scoped, catalog-safe mid-round nudge — Edge or Setback, applied "
                "through the existing condition-adjudication lever (#3387). Not inherently "
                "negative: the category hosts both directions."
            ),
            "is_negative": False,
            "display_order": 90,
        },
    )

    edge, _ = ConditionTemplate.objects.get_or_create(
        name=EDGE_CONDITION_NAME,
        defaults={
            "category": category,
            "description": (
                "A GM-granted edge — clever positioning or a lucky break, felt for one round."
            ),
            "player_description": "Something is working in your favor this round.",
            "observer_description": "moves with a sudden, clean advantage.",
            "default_duration_type": DurationType.ROUNDS,
            "default_duration_value": 1,
            "is_stackable": False,
            "can_be_dispelled": False,
        },
    )
    setback, _ = ConditionTemplate.objects.get_or_create(
        name=SETBACK_CONDITION_NAME,
        defaults={
            "category": category,
            "description": "A GM-imposed setback — a costly misstep, felt for one round.",
            "player_description": "Something is working against you this round.",
            "observer_description": "falters, thrown off for the moment.",
            "default_duration_type": DurationType.ROUNDS,
            "default_duration_value": 1,
            "is_stackable": False,
            "can_be_dispelled": False,
        },
    )

    _ensure_combat_check_modifier(edge, EDGE_MODIFIER_VALUE)
    _ensure_combat_check_modifier(setback, SETBACK_MODIFIER_VALUE)


def _ensure_combat_check_modifier(template, modifier_value: int) -> None:
    """Attach a Combat-category ``ConditionCheckModifier`` to *template*, if the
    Combat ``CheckCategory`` is authored.

    ``checks.checkcategory`` is content-repo-owned (#2698) — this is a
    cross-content-model reference, not authorship of a new category, so it is
    looked up (never invented) and skipped gracefully when absent, mirroring
    ``ensure_restore_to_sense_effect``'s ``CheckType.objects.filter(...).first()``
    precedent (``world/conditions/berserk_content.py``).
    """
    from world.checks.models import CheckCategory  # noqa: PLC0415
    from world.conditions.models import ConditionCheckModifier  # noqa: PLC0415

    combat_category = CheckCategory.objects.filter(name="Combat").first()
    if combat_category is None:
        return

    ConditionCheckModifier.objects.get_or_create(
        condition=template,
        check_category=combat_category,
        defaults={
            "modifier_value": modifier_value,
            "scales_with_severity": True,
        },
    )
