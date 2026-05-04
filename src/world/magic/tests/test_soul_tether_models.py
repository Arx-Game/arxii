"""Soul Tether model tests (Spec B §15)."""

from __future__ import annotations

from django.test import TestCase

from world.magic.factories import CharacterResonanceFactory, ThreadFactory


class ThreadHollowFieldTests(TestCase):
    def test_hollow_current_default_zero(self) -> None:
        thread = ThreadFactory()
        thread.refresh_from_db()
        self.assertEqual(thread.hollow_current, 0)

    def test_hollow_current_persists(self) -> None:
        thread = ThreadFactory()
        thread.hollow_current = 12
        thread.save(update_fields=["hollow_current"])
        thread.refresh_from_db()
        self.assertEqual(thread.hollow_current, 12)


class CharacterResonanceLifetimeHelpedTests(TestCase):
    def test_lifetime_helped_default_zero(self) -> None:
        cr = CharacterResonanceFactory()
        cr.refresh_from_db()
        self.assertEqual(cr.lifetime_helped, 0)

    def test_lifetime_helped_persists_and_is_monotonic_in_practice(self) -> None:
        cr = CharacterResonanceFactory()
        cr.lifetime_helped = 50
        cr.save(update_fields=["lifetime_helped"])
        cr.refresh_from_db()
        self.assertEqual(cr.lifetime_helped, 50)


class CorruptionResistanceEffectKindTests(TestCase):
    def test_corruption_resistance_is_a_valid_effect_kind(self) -> None:
        from world.magic.constants import EffectKind

        self.assertIn("CORRUPTION_RESISTANCE", EffectKind.values)


class SoulTetherExceptionTests(TestCase):
    def test_user_message_round_trip(self) -> None:
        from world.magic.exceptions import AffinityGateError

        expected_msg = "Sinner cannot be Celestial-affinity primary."
        with self.assertRaises(AffinityGateError) as ctx:
            raise AffinityGateError(expected_msg)
        self.assertEqual(ctx.exception.user_message, expected_msg)

    def test_default_user_message_when_no_args(self) -> None:
        from world.magic.exceptions import (
            AffinityGateError,
            NoSoulTetherUnlockError,
            RescueValidationError,
            SineatingValidationError,
            SoulTetherFormationError,
        )

        for cls in [
            AffinityGateError,
            NoSoulTetherUnlockError,
            SoulTetherFormationError,
            SineatingValidationError,
            RescueValidationError,
        ]:
            err = cls()
            self.assertNotEqual(
                err.user_message,
                "",
                f"{cls.__name__} should have a non-empty default",
            )
            self.assertIn(
                err.user_message,
                cls.SAFE_MESSAGES,
                f"{cls.__name__} default should be in SAFE_MESSAGES",
            )


class TypesImportTests(TestCase):
    def test_types_module_imports(self) -> None:
        from world.magic.types.soul_tether import (
            SoulTetherRole,
        )

        self.assertEqual(SoulTetherRole.ABYSSAL.value, "ABYSSAL")
        self.assertEqual(SoulTetherRole.SINEATER.value, "SINEATER")

    def test_sineating_offer_frozen(self) -> None:
        from world.character_sheets.factories import CharacterSheetFactory
        from world.magic.factories import ResonanceFactory
        from world.magic.types.soul_tether import SineatingOffer
        from world.relationships.factories import CharacterRelationshipFactory

        sinner = CharacterSheetFactory()
        sineater = CharacterSheetFactory()
        relationship = CharacterRelationshipFactory(source=sinner, target=sineater)
        resonance = ResonanceFactory()

        offer = SineatingOffer(
            sinner_sheet=sinner,
            sineater_sheet=sineater,
            relationship=relationship,
            resonance=resonance,
            max_units_offered=10,
            anima_cost_per_unit=2,
            fatigue_cost_per_unit=1,
            current_hollow=5,
            hollow_max=20,
            sineater_current_strain_stage=0,
        )
        self.assertEqual(offer.max_units_offered, 10)
        # Verify it's frozen (immutable)
        with self.assertRaises(AttributeError):
            offer.max_units_offered = 5  # type: ignore[misc]


class ServiceSkeletonImportsTests(TestCase):
    def test_service_module_imports(self) -> None:
        from world.magic.services import soul_tether

        self.assertTrue(callable(soul_tether.accept_soul_tether))
        self.assertTrue(callable(soul_tether.request_sineating))
        self.assertTrue(callable(soul_tether.resolve_sineating))
        self.assertTrue(callable(soul_tether.perform_soul_tether_rescue))
        self.assertTrue(callable(soul_tether.dissolve_soul_tether))
        self.assertTrue(callable(soul_tether.soul_tether_redirect_handler))
        self.assertTrue(callable(soul_tether.soul_tether_stage_advance_prompt))
        self.assertTrue(callable(soul_tether.resolve_stage_advance_prompt))

    def test_other_stubs_raise_not_implemented(self) -> None:
        """Phase 5 implemented request_sineating/resolve_sineating.

        dissolve_soul_tether and perform_soul_tether_rescue remain stubs.
        """
        from world.magic.services import soul_tether

        with self.assertRaises(NotImplementedError):
            soul_tether.dissolve_soul_tether(
                relationship_id=0,
                initiator_sheet=None,  # type: ignore[arg-type]
            )

        with self.assertRaises(NotImplementedError):
            soul_tether.perform_soul_tether_rescue(
                sineater_sheet=None,  # type: ignore[arg-type]
                sinner_sheet=None,  # type: ignore[arg-type]
                resonance=None,  # type: ignore[arg-type]
                components=[],
            )


class SineatingModelTests(TestCase):
    def test_sineating_can_be_created_with_required_fields(self) -> None:
        from world.character_sheets.factories import CharacterSheetFactory
        from world.magic.factories import ResonanceFactory
        from world.magic.models import Sineating
        from world.relationships.factories import CharacterRelationshipFactory

        sinner = CharacterSheetFactory()
        sineater = CharacterSheetFactory()
        relationship = CharacterRelationshipFactory(source=sinner, target=sineater)
        resonance = ResonanceFactory()

        row = Sineating.objects.create(
            sinner_sheet=sinner,
            sineater_sheet=sineater,
            relationship=relationship,
            resonance=resonance,
            units_offered=10,
            units_accepted=7,
            anima_cost=14,
            fatigue_cost=7,
        )
        self.assertEqual(row.units_offered, 10)
        self.assertEqual(row.units_accepted, 7)


# =============================================================================
# Phase 3 factory round-trip tests
# =============================================================================


class SineatingFactoryRoundTripTests(TestCase):
    """Task 3.1: SineatingFactory creates valid audit rows."""

    def test_sineating_factory_creates_valid_row(self) -> None:
        from world.magic.factories import SineatingFactory
        from world.magic.models import Sineating

        row = SineatingFactory()
        row.refresh_from_db()
        self.assertIsInstance(row, Sineating)
        self.assertEqual(row.units_accepted, 5)
        self.assertEqual(row.units_offered, 5)
        self.assertEqual(row.anima_cost, 10)

    def test_sineating_factory_declined_variant(self) -> None:
        from world.magic.factories import SineatingFactory

        row = SineatingFactory(units_accepted=0)
        row.refresh_from_db()
        self.assertEqual(row.units_accepted, 0)


class SoulTetherRescueFactoryRoundTripTests(TestCase):
    """Task 3.1: SoulTetherRescueFactory creates valid audit rows."""

    def test_rescue_factory_creates_valid_row(self) -> None:
        from world.magic.factories import SoulTetherRescueFactory
        from world.magic.models import SoulTetherRescue

        row = SoulTetherRescueFactory()
        row.refresh_from_db()
        self.assertIsInstance(row, SoulTetherRescue)
        self.assertEqual(row.sinner_stage_at_start, 4)
        self.assertEqual(row.sinner_stage_at_end, 3)
        self.assertEqual(row.severity_reduced, 5)


class TetherStrainTemplateFactoryTests(TestCase):
    """Task 3.2: TetherStrainTemplateFactory with 5 stages."""

    def test_tether_strain_template_created(self) -> None:
        from world.magic.factories import TetherStrainTemplateFactory

        template = TetherStrainTemplateFactory()
        template.refresh_from_db()
        self.assertEqual(template.name, "Tether Strain")
        self.assertEqual(template.passive_decay_per_day, 1)
        self.assertFalse(template.passive_decay_blocked_in_engagement)
        self.assertTrue(template.has_progression)

    def test_tether_strain_has_five_stages(self) -> None:
        from world.magic.factories import TetherStrainTemplateFactory

        template = TetherStrainTemplateFactory()
        stages = list(template.stages.order_by("stage_order"))
        self.assertEqual(len(stages), 5)

    def test_tether_strain_stage_names(self) -> None:
        from world.magic.factories import TetherStrainTemplateFactory

        template = TetherStrainTemplateFactory()
        stages = list(template.stages.order_by("stage_order"))
        expected_names = [
            "Bone-Tired",
            "Soul-Worn",
            "Heart-Cracked",
            "Shadow-Touched",
            "Half-Lost",
        ]
        actual_names = [s.name for s in stages]
        self.assertEqual(actual_names, expected_names)

    def test_tether_strain_severity_thresholds(self) -> None:
        from world.magic.factories import TetherStrainTemplateFactory

        template = TetherStrainTemplateFactory()
        stages = list(template.stages.order_by("stage_order"))
        expected_thresholds = [5, 10, 18, 28, 40]
        actual_thresholds = [s.severity_threshold for s in stages]
        self.assertEqual(actual_thresholds, expected_thresholds)

    def test_tether_strain_idempotent(self) -> None:
        """Calling factory twice returns same row, does not duplicate stages."""
        from world.conditions.models import ConditionTemplate
        from world.magic.factories import TetherStrainTemplateFactory

        t1 = TetherStrainTemplateFactory()
        t2 = TetherStrainTemplateFactory()
        self.assertEqual(t1.pk, t2.pk)
        count = ConditionTemplate.objects.filter(name="Tether Strain").count()
        self.assertEqual(count, 1)
        self.assertEqual(t1.stages.count(), 5)


class SoulTetherActiveTemplateFactoryTests(TestCase):
    """Task 3.3: SoulTetherActiveTemplateFactory (marker condition)."""

    def test_active_template_created(self) -> None:
        from world.magic.factories import SoulTetherActiveTemplateFactory

        template = SoulTetherActiveTemplateFactory()
        template.refresh_from_db()
        self.assertEqual(template.name, "Soul Tether Active")
        self.assertFalse(template.has_progression)
        self.assertEqual(template.passive_decay_per_day, 0)

    def test_active_template_idempotent(self) -> None:
        from world.conditions.models import ConditionTemplate
        from world.magic.factories import SoulTetherActiveTemplateFactory

        t1 = SoulTetherActiveTemplateFactory()
        t2 = SoulTetherActiveTemplateFactory()
        self.assertEqual(t1.pk, t2.pk)
        self.assertEqual(ConditionTemplate.objects.filter(name="Soul Tether Active").count(), 1)


class AcceptSoulTetherRitualFactoryTests(TestCase):
    """Task 3.4: AcceptSoulTetherRitualFactory creates SERVICE-dispatched Ritual."""

    def test_accept_ritual_created(self) -> None:
        from world.magic.constants import RitualExecutionKind
        from world.magic.factories import AcceptSoulTetherRitualFactory
        from world.magic.models import Ritual

        ritual = AcceptSoulTetherRitualFactory()
        ritual.refresh_from_db()
        self.assertIsInstance(ritual, Ritual)
        self.assertEqual(ritual.name, "accept_soul_tether")
        self.assertEqual(ritual.execution_kind, RitualExecutionKind.SERVICE)
        self.assertEqual(
            ritual.service_function_path,
            "world.magic.services.soul_tether.accept_soul_tether",
        )

    def test_accept_ritual_idempotent(self) -> None:
        from world.magic.factories import AcceptSoulTetherRitualFactory
        from world.magic.models import Ritual

        r1 = AcceptSoulTetherRitualFactory()
        r2 = AcceptSoulTetherRitualFactory()
        self.assertEqual(r1.pk, r2.pk)
        self.assertEqual(Ritual.objects.filter(name="accept_soul_tether").count(), 1)


class SoulTetherRescueRitualFactoryTests(TestCase):
    """Task 3.4: SoulTetherRescueRitualFactory creates SERVICE-dispatched Ritual."""

    def test_rescue_ritual_created(self) -> None:
        from world.magic.constants import RitualExecutionKind
        from world.magic.factories import SoulTetherRescueRitualFactory
        from world.magic.models import Ritual

        ritual = SoulTetherRescueRitualFactory()
        ritual.refresh_from_db()
        self.assertIsInstance(ritual, Ritual)
        self.assertEqual(ritual.name, "soul_tether_rescue")
        self.assertEqual(ritual.execution_kind, RitualExecutionKind.SERVICE)
        self.assertEqual(
            ritual.service_function_path,
            "world.magic.services.soul_tether.perform_soul_tether_rescue",
        )

    def test_rescue_ritual_idempotent(self) -> None:
        from world.magic.factories import SoulTetherRescueRitualFactory
        from world.magic.models import Ritual

        r1 = SoulTetherRescueRitualFactory()
        r2 = SoulTetherRescueRitualFactory()
        self.assertEqual(r1.pk, r2.pk)
        self.assertEqual(Ritual.objects.filter(name="soul_tether_rescue").count(), 1)


class SoulTetherTriggerDefinitionFactoryTests(TestCase):
    """Task 3.5: TriggerDefinition factories for the two Spec B subscribers."""

    def test_redirect_trigger_definition_created(self) -> None:
        from flows.models import TriggerDefinition
        from world.magic.factories import SoulTetherRedirectTriggerDefinitionFactory

        trig_def = SoulTetherRedirectTriggerDefinitionFactory()
        trig_def.refresh_from_db()
        self.assertIsInstance(trig_def, TriggerDefinition)
        self.assertEqual(trig_def.name, "soul_tether_redirect")
        self.assertEqual(trig_def.event_name, "corruption_accruing")
        self.assertEqual(trig_def.priority, 100)

    def test_redirect_trigger_has_service_step(self) -> None:
        from flows.consts import FlowActionChoices
        from world.magic.factories import SoulTetherRedirectTriggerDefinitionFactory

        trig_def = SoulTetherRedirectTriggerDefinitionFactory()
        steps = list(trig_def.flow_definition.steps.all())
        self.assertEqual(len(steps), 1)
        step = steps[0]
        self.assertEqual(step.action, FlowActionChoices.CALL_SERVICE_FUNCTION)
        self.assertIn("soul_tether_redirect_handler", step.variable_name)

    def test_stage_advance_prompt_trigger_definition_created(self) -> None:
        from flows.models import TriggerDefinition
        from world.magic.factories import (
            SoulTetherStageAdvancePromptTriggerDefinitionFactory,
        )

        trig_def = SoulTetherStageAdvancePromptTriggerDefinitionFactory()
        trig_def.refresh_from_db()
        self.assertIsInstance(trig_def, TriggerDefinition)
        self.assertEqual(trig_def.name, "soul_tether_stage_advance_prompt")
        self.assertEqual(trig_def.event_name, "condition_stage_advance_check_about_to_fire")
        self.assertEqual(trig_def.priority, 100)

    def test_stage_advance_prompt_trigger_has_service_step(self) -> None:
        from flows.consts import FlowActionChoices
        from world.magic.factories import (
            SoulTetherStageAdvancePromptTriggerDefinitionFactory,
        )

        trig_def = SoulTetherStageAdvancePromptTriggerDefinitionFactory()
        steps = list(trig_def.flow_definition.steps.all())
        self.assertEqual(len(steps), 1)
        step = steps[0]
        self.assertEqual(step.action, FlowActionChoices.CALL_SERVICE_FUNCTION)
        self.assertIn("soul_tether_stage_advance_prompt", step.variable_name)

    def test_trigger_definitions_idempotent(self) -> None:
        from flows.models import TriggerDefinition
        from world.magic.factories import (
            SoulTetherRedirectTriggerDefinitionFactory,
            SoulTetherStageAdvancePromptTriggerDefinitionFactory,
        )

        r1 = SoulTetherRedirectTriggerDefinitionFactory()
        r2 = SoulTetherRedirectTriggerDefinitionFactory()
        self.assertEqual(r1.pk, r2.pk)
        self.assertEqual(TriggerDefinition.objects.filter(name="soul_tether_redirect").count(), 1)

        p1 = SoulTetherStageAdvancePromptTriggerDefinitionFactory()
        p2 = SoulTetherStageAdvancePromptTriggerDefinitionFactory()
        self.assertEqual(p1.pk, p2.pk)
        self.assertEqual(
            TriggerDefinition.objects.filter(name="soul_tether_stage_advance_prompt").count(),
            1,
        )


class WireSoulTetherContentTests(TestCase):
    """Task 3.6: wire_soul_tether_content() master orchestrator."""

    def test_wire_creates_all_content(self) -> None:
        from world.magic.factories import wire_soul_tether_content

        content = wire_soul_tether_content()
        self.assertEqual(content.strain_template.name, "Tether Strain")
        self.assertEqual(content.active_template.name, "Soul Tether Active")
        self.assertEqual(content.accept_ritual.name, "accept_soul_tether")
        self.assertEqual(content.rescue_ritual.name, "soul_tether_rescue")
        self.assertEqual(content.redirect_trigger_def.name, "soul_tether_redirect")
        self.assertEqual(content.stage_advance_trigger_def.name, "soul_tether_stage_advance_prompt")

    def test_wire_is_idempotent(self) -> None:
        """Calling wire_soul_tether_content() twice creates no duplicate rows."""
        from flows.models import TriggerDefinition
        from world.conditions.models import ConditionTemplate as CondTemplate
        from world.magic.factories import wire_soul_tether_content
        from world.magic.models import Ritual

        c1 = wire_soul_tether_content()
        c2 = wire_soul_tether_content()

        # Same PKs returned
        self.assertEqual(c1.strain_template.pk, c2.strain_template.pk)
        self.assertEqual(c1.active_template.pk, c2.active_template.pk)
        self.assertEqual(c1.accept_ritual.pk, c2.accept_ritual.pk)
        self.assertEqual(c1.rescue_ritual.pk, c2.rescue_ritual.pk)
        self.assertEqual(c1.redirect_trigger_def.pk, c2.redirect_trigger_def.pk)

        # No duplicate DB rows
        self.assertEqual(CondTemplate.objects.filter(name="Tether Strain").count(), 1)
        self.assertEqual(CondTemplate.objects.filter(name="Soul Tether Active").count(), 1)
        self.assertEqual(Ritual.objects.filter(name="accept_soul_tether").count(), 1)
        self.assertEqual(Ritual.objects.filter(name="soul_tether_rescue").count(), 1)
        self.assertEqual(TriggerDefinition.objects.filter(name="soul_tether_redirect").count(), 1)
        self.assertEqual(
            TriggerDefinition.objects.filter(name="soul_tether_stage_advance_prompt").count(),
            1,
        )

    def test_strain_template_has_five_stages_after_wire(self) -> None:
        from world.magic.factories import wire_soul_tether_content

        content = wire_soul_tether_content()
        self.assertEqual(content.strain_template.stages.count(), 5)
