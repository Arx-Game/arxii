"""Save rules for trial consequences (#4501), through the models an admin form runs."""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.test import TestCase

from world.checks.constants import EffectTarget, EffectType
from world.checks.factories import ConsequenceEffectFactory, ConsequenceFactory
from world.checks.models import ConsequenceEffect
from world.codex.factories import CodexEntryFactory
from world.conditions.factories import ConditionTemplateFactory
from world.magic.factories import TechniqueFactory
from world.progression.factories import CodexKnowledgeRequirementFactory
from world.traits.factories import CheckOutcomeFactory


class TrialRuleTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.crit = CheckOutcomeFactory(name="Crit", success_level=2)
        cls.success = CheckOutcomeFactory(name="Win", success_level=1)
        cls.partial = CheckOutcomeFactory(name="Partial", success_level=0)
        cls.failure = CheckOutcomeFactory(name="Lose", success_level=-1)
        cls.technique = TechniqueFactory()
        cls.entry = CodexEntryFactory(name="Gating entry")
        CodexKnowledgeRequirementFactory(codex_entry=cls.entry, path=None, technique=cls.technique)
        cls.lore = CodexEntryFactory(name="Plain lore")
        cls.condition = ConditionTemplateFactory(name="Chill")

    def _effect(self, tier, effect_type, order=0, **fields) -> ConsequenceEffect:
        consequence = fields.pop("consequence", None) or ConsequenceFactory(outcome_tier=tier)
        return ConsequenceEffect(
            consequence=consequence,
            effect_type=effect_type,
            execution_order=order,
            target=EffectTarget.SELF,
            **fields,
        )

    def assertRefused(self, effect: ConsequenceEffect, field: str) -> None:  # noqa: N802
        with self.assertRaises(ValidationError) as caught:
            effect.clean()
        self.assertIn(field, caught.exception.message_dict)

    def test_known_grant_needs_success(self) -> None:
        for tier in (self.partial, self.failure):
            effect = self._effect(
                tier, EffectType.GRANT_CODEX, codex_entry=self.lore, grants_known=True
            )
            self.assertRefused(effect, "grants_known")
        self._effect(
            self.success, EffectType.GRANT_CODEX, codex_entry=self.lore, grants_known=True
        ).clean()

    def test_a_failure_never_grants_an_entry_that_gates_a_technique(self) -> None:
        effect = self._effect(self.failure, EffectType.GRANT_CODEX, codex_entry=self.entry)
        self.assertRefused(effect, "codex_entry")
        self._effect(self.failure, EffectType.GRANT_CODEX, codex_entry=self.lore).clean()
        self._effect(self.partial, EffectType.GRANT_CODEX, codex_entry=self.entry).clean()

    def test_training_rules(self) -> None:
        self.assertRefused(
            self._effect(
                self.failure,
                EffectType.TECHNIQUE_TRAINING,
                technique=self.technique,
                training_points=5,
                training_meter_size=10,
            ),
            "effect_type",
        )
        self.assertRefused(
            self._effect(self.success, EffectType.TECHNIQUE_TRAINING, technique=self.technique),
            "training_points",
        )
        self.assertRefused(
            self._effect(
                self.success,
                EffectType.TECHNIQUE_TRAINING,
                technique=self.technique,
                grants_technique_outright=True,
            ),
            "grants_technique_outright",
        )
        self.assertRefused(
            self._effect(
                self.success,
                EffectType.TECHNIQUE_TRAINING,
                technique=self.technique,
                training_points=5,
            ),
            "training_meter_size",
        )
        self.assertRefused(self._effect(self.success, EffectType.TECHNIQUE_TRAINING), "technique")
        ultimate = TechniqueFactory(is_ultimate=True)
        self.assertRefused(
            self._effect(
                self.success,
                EffectType.TECHNIQUE_TRAINING,
                technique=ultimate,
                training_points=5,
                training_meter_size=10,
            ),
            "technique",
        )
        self._effect(
            self.crit,
            EffectType.TECHNIQUE_TRAINING,
            technique=self.technique,
            grants_technique_outright=True,
        ).clean()

    def test_a_cosmetic_scar_is_a_reward_for_success_or_better(self) -> None:
        for tier in (self.partial, self.failure):
            self.assertRefused(
                self._effect(
                    tier,
                    EffectType.MAGICAL_SCARS,
                    condition_template=self.condition,
                    scar_is_cosmetic=True,
                ),
                "scar_is_cosmetic",
            )
        self._effect(
            self.success,
            EffectType.MAGICAL_SCARS,
            condition_template=self.condition,
            scar_is_cosmetic=True,
        ).clean()

    def test_opening_a_technique_needs_a_real_cost(self) -> None:
        consequence = ConsequenceFactory(outcome_tier=self.success)
        opening = self._effect(
            self.success,
            EffectType.GRANT_CODEX,
            consequence=consequence,
            codex_entry=self.entry,
            grants_known=True,
        )
        self.assertEqual(len(consequence.trial_rule_errors([opening])), 1)

        cosmetic = self._effect(
            self.success,
            EffectType.MAGICAL_SCARS,
            order=1,
            consequence=consequence,
            condition_template=self.condition,
            scar_is_cosmetic=True,
        )
        (error,) = consequence.trial_rule_errors([opening, cosmetic])
        self.assertIn("reward, not a cost", error)

        scar = self._effect(
            self.success,
            EffectType.MAGICAL_SCARS,
            order=1,
            consequence=consequence,
            condition_template=self.condition,
        )
        self.assertEqual(consequence.trial_rule_errors([opening, scar]), [])

    def test_a_condition_on_someone_else_is_not_a_cost(self) -> None:
        consequence = ConsequenceFactory(outcome_tier=self.success)
        opening = self._effect(
            self.success,
            EffectType.GRANT_CODEX,
            consequence=consequence,
            codex_entry=self.entry,
            grants_known=True,
        )
        other = self._effect(
            self.success,
            EffectType.APPLY_CONDITION,
            order=1,
            consequence=consequence,
            condition_template=self.condition,
        )
        other.target = EffectTarget.TARGET
        self.assertEqual(len(consequence.trial_rule_errors([opening, other])), 1)

    def test_deliberately_free_needs_a_reason_and_lifts_the_cost_rule(self) -> None:
        consequence = ConsequenceFactory(outcome_tier=self.success, deliberately_free=True)
        with self.assertRaises(ValidationError):
            consequence.clean()
        consequence.free_reason = "[staff-authored reason]"
        consequence.clean()
        opening = self._effect(
            self.success,
            EffectType.GRANT_CODEX,
            consequence=consequence,
            codex_entry=self.entry,
            grants_known=True,
        )
        self.assertEqual(consequence.trial_rule_errors([opening]), [])

    def test_a_known_grant_of_lore_that_gates_nothing_needs_no_cost(self) -> None:
        consequence = ConsequenceFactory(outcome_tier=self.success)
        lore = self._effect(
            self.success,
            EffectType.GRANT_CODEX,
            consequence=consequence,
            codex_entry=self.lore,
            grants_known=True,
        )
        self.assertEqual(consequence.trial_rule_errors([lore]), [])

    def test_training_runs_after_the_known_grant(self) -> None:
        consequence = ConsequenceFactory(outcome_tier=self.success)
        known = self._effect(
            self.success,
            EffectType.GRANT_CODEX,
            order=1,
            consequence=consequence,
            codex_entry=self.entry,
            grants_known=True,
        )
        training = self._effect(
            self.success,
            EffectType.TECHNIQUE_TRAINING,
            order=0,
            consequence=consequence,
            technique=self.technique,
            training_points=5,
            training_meter_size=10,
        )
        scar = self._effect(
            self.success,
            EffectType.MAGICAL_SCARS,
            order=2,
            consequence=consequence,
            condition_template=self.condition,
        )
        (error,) = consequence.trial_rule_errors([known, training, scar])
        self.assertIn("after the codex effect", error)

    def test_stored_effects_are_read_when_no_set_is_given(self) -> None:
        consequence = ConsequenceFactory(outcome_tier=self.success)
        ConsequenceEffectFactory(
            consequence=consequence,
            effect_type=EffectType.GRANT_CODEX,
            codex_entry=self.entry,
            grants_known=True,
        )
        self.assertEqual(len(consequence.trial_rule_errors()), 1)
