"""Tests for Miracle models and divine intervention (#2360)."""

from django.test import TestCase

from world.worship.constants import MiracleTrigger
from world.worship.factories import WorshippedBeingFactory, wire_miracle_content
from world.worship.models import (
    DivineInterventionConfig,
    Miracle,
    MiraclePerformance,
)
from world.worship.services import (
    bump_devotion,
    get_divine_intervention_config,
    install_divine_intervention_trigger,
    perform_divine_intervention,
    spend_worship_pool,
)


class MiracleModelTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.being = WorshippedBeingFactory()
        cls.miracle = Miracle.objects.create(
            name="Test Aegis",
            being=cls.being,
            resonance_pool_cost=100,
            intervention_trigger=MiracleTrigger.INCAPACITATED,
            favor_threshold=50,
            narrative_text="A divine shield flares.",
        )

    def test_miracle_str(self) -> None:
        self.assertIn("Test Aegis", str(self.miracle))

    def test_unique_name_per_being(self) -> None:
        from django.db import IntegrityError

        with self.assertRaises(IntegrityError):
            Miracle.objects.create(
                name="Test Aegis",
                being=self.being,
                resonance_pool_cost=50,
                intervention_trigger=MiracleTrigger.INCAPACITATED,
                narrative_text="dup",
            )

    def test_divine_intervention_config_defaults(self) -> None:
        cfg = DivineInterventionConfig.objects.create()
        self.assertEqual(cfg.favor_threshold, 50)
        self.assertEqual(cfg.cooldown_hours, 24)
        self.assertEqual(cfg.min_pool_for_intervention, 100)

    def test_miracle_performance_str(self) -> None:
        perf = MiraclePerformance.objects.create(
            miracle=self.miracle,
            being=self.being,
            resonance_spent=100,
            trigger_event="character_incapacitated",
        )
        self.assertIn("Test Aegis", str(perf))


class SpendWorshipPoolTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.being = WorshippedBeingFactory()
        cls.being.resonance_pool = 500
        cls.being.save()

    def test_succeeds_when_sufficient(self) -> None:
        result = spend_worship_pool(self.being, 100, reason="test")
        self.assertTrue(result)
        self.being.refresh_from_db()
        self.assertEqual(self.being.resonance_pool, 400)

    def test_fails_when_insufficient(self) -> None:
        result = spend_worship_pool(self.being, 600, reason="test")
        self.assertFalse(result)
        self.being.refresh_from_db()
        self.assertEqual(self.being.resonance_pool, 500)

    def test_rejects_non_positive(self) -> None:
        with self.assertRaises(ValueError):
            spend_worship_pool(self.being, 0)

    def test_get_config_creates_singleton(self) -> None:
        DivineInterventionConfig.objects.all().delete()
        cfg = get_divine_intervention_config()
        self.assertEqual(cfg.pk, 1)
        self.assertEqual(cfg.favor_threshold, 50)


class DivineInterventionTests(TestCase):
    """Tests for perform_divine_intervention + maybe_fire_divine_intervention (#2360)."""

    @classmethod
    def setUpTestData(cls) -> None:
        from world.character_sheets.factories import CharacterSheetFactory
        from world.conditions.factories import ConditionTemplateFactory
        from world.worship.models import DevotionStanding

        cls.sheet = CharacterSheetFactory()
        cls.being = WorshippedBeingFactory(resonance_pool=500)
        cls.being.save()
        cls.miracle = Miracle.objects.create(
            name="Aegis",
            being=cls.being,
            resonance_pool_cost=100,
            intervention_trigger=MiracleTrigger.INCAPACITATED,
            favor_threshold=50,
            narrative_text="[PLACEHOLDER] A divine shield flares.",
        )
        DevotionStanding.objects.create(
            character_sheet=cls.sheet,
            being=cls.being,
            favor=75,
        )
        # Seed cooldown condition template
        cls.cooldown_template = ConditionTemplateFactory(name="Divine Intervention Cooldown")

    def test_perform_intervention_spends_pool_and_creates_audit(self) -> None:
        from unittest.mock import patch

        with patch("world.worship.services._broadcast_miracle_narrative"):
            perf = perform_divine_intervention(self.sheet, self.being, self.miracle)

        self.assertEqual(perf.resonance_spent, 100)
        self.being.refresh_from_db()
        self.assertEqual(self.being.resonance_pool, 400)

    def test_perform_intervention_applies_conditions(self) -> None:
        from unittest.mock import patch

        from world.conditions.factories import ConditionTemplateFactory
        from world.magic.models.techniques import ConditionTargetKind
        from world.worship.models import MiracleAppliedCondition

        cond_template = ConditionTemplateFactory(name="Divine Protection")
        MiracleAppliedCondition.objects.create(
            miracle=self.miracle,
            condition=cond_template,
            target_kind=ConditionTargetKind.SELF,
            base_severity=2,
        )

        with patch("world.worship.services._broadcast_miracle_narrative"):
            perform_divine_intervention(self.sheet, self.being, self.miracle)

        from world.conditions.models import ConditionInstance

        self.assertTrue(
            ConditionInstance.objects.filter(
                target=self.sheet.character,
                condition__name="Divine Protection",
            ).exists()
        )


class TriggerLifecycleTests(TestCase):
    """Tests for install/remove_divine_intervention_trigger + bump_devotion wiring (#2360)."""

    @classmethod
    def setUpTestData(cls) -> None:
        from world.character_sheets.factories import CharacterSheetFactory

        cls.sheet = CharacterSheetFactory()
        cls.being = WorshippedBeingFactory()

    def _seed_trigger_def(self) -> None:
        from flows.consts import FlowActionChoices
        from flows.factories import FlowStepDefinitionFactory
        from flows.models import FlowDefinition, TriggerDefinition

        flow, _ = FlowDefinition.objects.get_or_create(name="divine_intervention_flow")
        if not flow.steps.exists():
            FlowStepDefinitionFactory(
                flow=flow,
                action=FlowActionChoices.CALL_SERVICE_FUNCTION,
                variable_name="world.worship.services.maybe_fire_divine_intervention",
                parameters={"payload": "{{payload}}"},
            )
        TriggerDefinition.objects.create(
            name="divine_intervention_on_incapacitated",
            event_name="character_incapacitated",
            flow_definition=flow,
            priority=60,
        )

    def test_install_is_idempotent(self) -> None:
        from flows.models import Trigger

        self._seed_trigger_def()
        install_divine_intervention_trigger(self.sheet, self.being)
        install_divine_intervention_trigger(self.sheet, self.being)

        count = Trigger.objects.filter(
            obj=self.sheet.character,
            trigger_definition__name="divine_intervention_on_incapacitated",
        ).count()
        self.assertEqual(count, 1)

    def test_bump_devotion_installs_trigger_above_threshold(self) -> None:
        from flows.models import Trigger

        self._seed_trigger_def()
        bump_devotion(self.sheet, self.being, 60)

        self.assertTrue(
            Trigger.objects.filter(
                obj=self.sheet.character,
                trigger_definition__name="divine_intervention_on_incapacitated",
            ).exists()
        )

    def test_bump_devotion_does_not_install_below_threshold(self) -> None:
        from flows.models import Trigger

        self._seed_trigger_def()
        bump_devotion(self.sheet, self.being, 10)

        self.assertFalse(
            Trigger.objects.filter(
                obj=self.sheet.character,
                trigger_definition__name="divine_intervention_on_incapacitated",
            ).exists()
        )


class WireMiracleContentTests(TestCase):
    """Tests for wire_miracle_content seed (#2360)."""

    def test_seeds_trigger_and_config(self) -> None:
        wire_miracle_content()

        from flows.models import TriggerDefinition

        self.assertTrue(
            TriggerDefinition.objects.filter(name="divine_intervention_on_incapacitated").exists()
        )

        from world.conditions.models import ConditionTemplate

        self.assertTrue(
            ConditionTemplate.objects.filter(name="Divine Intervention Cooldown").exists()
        )

    def test_idempotent(self) -> None:
        wire_miracle_content()
        wire_miracle_content()

        from flows.models import TriggerDefinition

        self.assertEqual(
            TriggerDefinition.objects.filter(name="divine_intervention_on_incapacitated").count(),
            1,
        )
