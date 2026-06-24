"""Non-lethal cap on soulfray / overburn (Duels #568, Task 9).

A cast inside a NON-LETHAL encounter (``lethal=False``) must not push magical
fatigue into dangerous territory: ``deduct_anima`` draws no overburn deficit,
soulfray severity is bounded below the first death-risk stage, and the soulfray
stage consequence pool never fires a ``character_loss`` consequence. The SAME
setup in a LETHAL encounter (``lethal=True``, the default) keeps everything live.
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase, tag

from actions.factories import ConsequencePoolEntryFactory, ConsequencePoolFactory
from world.checks.factories import (
    CheckTypeFactory,
    ConsequenceEffectFactory,
    ConsequenceFactory,
)
from world.checks.types import CheckResult
from world.conditions.constants import DurationType
from world.conditions.factories import (
    ConditionStageFactory,
    ConditionTemplateFactory,
)
from world.magic.audere import SOULFRAY_CONDITION_NAME
from world.magic.factories import (
    CharacterAnimaFactory,
    SoulfrayConfigFactory,
    TechniqueFactory,
)
from world.magic.services import use_technique
from world.magic.services.anima import deduct_anima
from world.magic.services.soulfray import get_soulfray_warning
from world.mechanics.factories import CharacterEngagementFactory


class DeductAnimaNonLethalTests(TestCase):
    """``deduct_anima`` clamps cost to available anima when ``lethal`` is False."""

    def setUp(self) -> None:
        self.anima = CharacterAnimaFactory(current=3, maximum=10)
        self.character = self.anima.character

    def test_lethal_records_overburn_deficit(self) -> None:
        deficit = deduct_anima(self.character, 10)  # default lethal=True
        self.assertEqual(deficit, 7)
        self.anima.refresh_from_db()
        self.assertEqual(self.anima.current, 0)

    def test_non_lethal_clamps_cost_no_deficit(self) -> None:
        deficit = deduct_anima(self.character, 10, lethal=False)
        self.assertEqual(deficit, 0)
        self.anima.refresh_from_db()
        # Only the available anima is spent — no life-force draw past zero.
        self.assertEqual(self.anima.current, 0)


@tag("postgres")  # Soulfray is progressive → apply_condition uses DISTINCT ON (PG-only)
class _SoulfrayCapTestBase(TestCase):
    """Shared content: a soulfray stage whose pool can kill (character_loss)."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.resilience_check_type = CheckTypeFactory(name="Resilience (nonlethal cap test)")
        cls.soulfray_config = SoulfrayConfigFactory(
            soulfray_threshold_ratio=Decimal("0.30"),
            severity_scale=10,
            deficit_scale=5,
            resilience_check_type=cls.resilience_check_type,
            base_check_difficulty=15,
        )

        cls.soulfray_template = ConditionTemplateFactory(
            name=SOULFRAY_CONDITION_NAME,
            has_progression=True,
            default_duration_type=DurationType.PERMANENT,
        )

        # A death-risk stage: its consequence pool carries a character_loss consequence.
        # The consequence applies a real condition so apply_resolution yields an
        # AppliedEffect (and thus a non-None stage_consequence) when it fires.
        cls.burnout_condition = ConditionTemplateFactory(
            name="Soul Burnout Mark (nonlethal cap test)",
            default_duration_type=DurationType.PERMANENT,
        )
        cls.death_pool = ConsequencePoolFactory(name="Soulfray Death-Risk (nonlethal cap test)")
        cls.death_consequence = ConsequenceFactory(
            label="Soul Burnout (nonlethal cap test)",
            character_loss=True,
        )
        ConsequenceEffectFactory(
            consequence=cls.death_consequence,
            effect_type="apply_condition",
            condition_template=cls.burnout_condition,
            condition_severity=1,
        )
        ConsequencePoolEntryFactory(pool=cls.death_pool, consequence=cls.death_consequence)

        # A benign first stage (no death-risk pool) at severity >= 1. apply_condition
        # makes the lowest-order stage the current stage on creation, so the benign
        # stage holds a non-lethal cast that stays at severity 1.
        cls.benign_stage = ConditionStageFactory(
            condition=cls.soulfray_template,
            stage_order=1,
            name="Smoldering (nonlethal cap test)",
            consequence_pool=None,
            severity_threshold=1,
        )
        # The death-risk stage requires severity >= 2 (so an unbounded LETHAL cast
        # reaches it, but a bounded non-lethal cast stays under it).
        cls.death_stage = ConditionStageFactory(
            condition=cls.soulfray_template,
            stage_order=2,
            name="Soul Rupture (nonlethal cap test)",
            consequence_pool=cls.death_pool,
            severity_threshold=2,
        )

        # High anima cost + low control so effective_cost > current_anima (overburn).
        cls.technique = TechniqueFactory(
            name="Overburn Blast (nonlethal cap test)",
            intensity=5,
            control=2,
            anima_cost=20,
        )

    def setUp(self) -> None:
        self.anima = CharacterAnimaFactory(current=0, maximum=10)
        self.character = self.anima.character
        # Engage so the social-safety control bonus does not inflate control.
        CharacterEngagementFactory(character=self.character)

    def _run(self, *, lethal: bool):
        """Run use_technique twice (create then advance/fire) with a mocked resilience check.

        The mocked resilience-check outcome matches the death consequence's
        ``outcome_tier`` so the character_loss consequence is the one selected.
        """
        outcome = self.death_consequence.outcome_tier
        mock_result = CheckResult(
            check_type=self.resilience_check_type,
            outcome=outcome,
            chart=None,
            roller_rank=None,
            target_rank=None,
            rank_difference=0,
            trait_points=0,
            aspect_bonus=0,
            total_points=0,
        )
        with patch("world.checks.services.perform_check", return_value=mock_result):
            # First cast creates the Soulfray condition (pool not fired on creation).
            use_technique(
                character=self.character,
                technique=self.technique,
                resolve_fn=lambda *, power, ledger, extra_modifiers=0: "resolved",  # noqa: ARG005
                confirm_soulfray_risk=True,
                lethal=lethal,
            )
            self.anima.refresh_from_db()
            self.anima.current = 0
            self.anima.save(update_fields=["current"])
            # Second cast advances severity → death stage threshold (in lethal mode).
            return use_technique(
                character=self.character,
                technique=self.technique,
                resolve_fn=lambda *, power, ledger, extra_modifiers=0: "resolved",  # noqa: ARG005
                confirm_soulfray_risk=True,
                lethal=lethal,
            )


class SoulfrayLethalTests(_SoulfrayCapTestBase):
    """Lethal duel: overburn deficit + death-risk stage + character_loss path stay live."""

    def test_lethal_reaches_death_risk_and_fires_character_loss(self) -> None:
        result = self._run(lethal=True)

        # Overburn deficit recorded (cost 20 > anima 0).
        self.assertGreater(result.anima_cost.deficit, 0)

        # The death-risk stage is reachable.
        warning = get_soulfray_warning(self.character)
        self.assertIsNotNone(warning)
        self.assertTrue(warning.has_death_risk)

        # The character_loss consequence actually fired.
        self.assertIsNotNone(result.soulfray_result)
        self.assertIsNotNone(result.soulfray_result.stage_consequence)


class SoulfrayNonLethalTests(_SoulfrayCapTestBase):
    """Non-lethal encounter: no overburn deficit, severity bounded, no character_loss."""

    def test_non_lethal_no_deficit_bounded_severity_no_character_loss(self) -> None:
        result = self._run(lethal=False)

        # No overburn deficit — cost clamped to available anima.
        self.assertEqual(result.anima_cost.deficit, 0)

        # Severity stays below the death-risk stage threshold.
        warning = get_soulfray_warning(self.character)
        if warning is not None:
            self.assertFalse(warning.has_death_risk)

        # No character_loss consequence applied.
        if result.soulfray_result is not None:
            self.assertIsNone(result.soulfray_result.stage_consequence)
