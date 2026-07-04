"""Guard rail for ``ConditionDamageOverTime.tick_timing`` (#1762).

A DoT seeded at ``START_OF_ROUND`` is a trap: it ticks during the DECLARING phase,
*before* Succor's cover window opens at RESOLVING (``round_context.py``), so it is
structurally un-shieldable in combat; and no non-combat scene-round path ever calls
``tick_round_for_targets(timing="start")`` (``scenes/round_services.py`` only ticks
``timing="end"``), so it is completely inert in scene rounds. ``START_OF_ROUND`` is a
legitimate, distinct primitive ("unpreventable top-of-round damage that lands before
any action resolves") — but it must be a *deliberate* choice, never a silent default.

These tests lock ``END_OF_ROUND`` (the convention: poison, sunlight) as the default on
both the model field and the factory, and fail loudly if authored DoT content ever ships
at ``START_OF_ROUND`` without being explicitly acknowledged below.
"""

from django.test import TestCase

from world.conditions.constants import DamageTickTiming
from world.conditions.factories import ConditionDamageOverTimeFactory
from world.conditions.models import ConditionDamageOverTime
from world.conditions.services import ensure_poison_content

# Authored conditions (by ConditionTemplate name) whose DoT deliberately ticks at
# START_OF_ROUND, with a comment justifying why unpreventable top-of-round damage is
# intended. Empty today — nothing needs it. Adding an entry is a conscious statement
# that the hazard SHOULD land before any action resolves (un-shieldable by Succor) AND
# that its author accepts it will be inert in non-combat scene rounds until a
# scene-round START tick is built (see docs/systems/conditions.md).
ACKNOWLEDGED_START_OF_ROUND_HAZARDS: frozenset[str] = frozenset()


class TickTimingDefaultTests(TestCase):
    """The safe, conventional default must be END_OF_ROUND on every authoring surface."""

    def test_model_field_default_is_end_of_round(self) -> None:
        field = ConditionDamageOverTime._meta.get_field("tick_timing")
        self.assertEqual(
            field.default,
            DamageTickTiming.END_OF_ROUND,
            "ConditionDamageOverTime.tick_timing must default to END_OF_ROUND (the poison/"
            "sunlight convention). START_OF_ROUND is un-shieldable in combat and inert in "
            "scene rounds — it must be an explicit, deliberate choice, never the default.",
        )

    def test_factory_default_is_end_of_round(self) -> None:
        built = ConditionDamageOverTimeFactory.build()
        self.assertEqual(
            built.tick_timing,
            DamageTickTiming.END_OF_ROUND,
            "ConditionDamageOverTimeFactory must default tick_timing to END_OF_ROUND so "
            "test fixtures and factory-as-seed-data don't silently inherit the START trap.",
        )


class AuthoredDotContentTickTimingTests(TestCase):
    """No authored DoT content may ship at START_OF_ROUND without acknowledgement."""

    @classmethod
    def setUpTestData(cls) -> None:
        # Seed every known authored DoT-bearing content set. When you add a new
        # ConditionDamageOverTime seeder, call it here so its rows are covered.
        from world.species.factories import ensure_sunlight_exposure_content

        ensure_poison_content()
        ensure_sunlight_exposure_content()

    @staticmethod
    def _condition_name(dot: ConditionDamageOverTime) -> str:
        # A DoT row targets either a condition (all stages) OR a specific stage;
        # for a stage-specific row the condition is reached via stage.condition.
        return dot.condition.name if dot.condition_id else dot.stage.condition.name

    def test_authored_dot_content_ticks_end_of_round(self) -> None:
        offenders = [
            dot
            for dot in ConditionDamageOverTime.objects.select_related(
                "condition", "stage__condition"
            )
            if dot.tick_timing == DamageTickTiming.START_OF_ROUND
            and self._condition_name(dot) not in ACKNOWLEDGED_START_OF_ROUND_HAZARDS
        ]
        offending_names = sorted(self._condition_name(dot) for dot in offenders)
        self.assertEqual(
            offenders,
            [],
            "Authored DoT content ticks at START_OF_ROUND: "
            f"{offending_names}. START_OF_ROUND damage lands BEFORE any action resolves this "
            "round, so it is (a) un-shieldable by Succor/Interpose in combat and (b) inert in "
            "non-combat scene rounds (no scene-round START tick exists). Either switch these to "
            "END_OF_ROUND (the convention), or — if you genuinely intend unpreventable "
            "top-of-round damage — add the condition name to ACKNOWLEDGED_START_OF_ROUND_HAZARDS "
            "with a justifying comment. See docs/systems/conditions.md.",
        )
