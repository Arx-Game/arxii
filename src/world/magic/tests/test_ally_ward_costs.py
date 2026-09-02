"""Ally-ward reactive costs debit the caster, not the bearer (#2208).

SQLite-safe: exercises the real seeded "Aegis Field" bundle
(``ensure_force_field_content()``) but drives the ``absorb_pool`` handler
directly with a ``DamagePreApplyPayload`` — the same lightweight pattern as
``test_absorb_pool.py`` — rather than the full combat/event-dispatch harness,
since this test's only concern is *who pays*, not that the trigger fires.

Journey: a caster pre-casts a force-field ward on an ALLY (``source_character``
set to the caster, mirroring what ``apply_technique_conditions`` stamps on
every technique-applied condition). When the ally is hit, the ward absorbs the
damage but the reactive anima cost is billed to the CASTER, never the ally.
"""

from unittest.mock import patch

from django.test import TestCase

from flows.events.payloads import DamagePreApplyPayload, DamageSource
from world.character_sheets.factories import CharacterSheetFactory
from world.combat.constants import ParticipantStatus, RiskLevel
from world.combat.factories import CombatEncounterFactory, CombatParticipantFactory
from world.combat.services import drain_reactive_upkeep
from world.conditions.constants import FORCE_FIELD_CONDITION_NAME
from world.conditions.factories import ConditionInstanceFactory
from world.conditions.models import ConditionInstance, ConditionTemplate
from world.magic.effect_palette_content import (
    FORCE_FIELD_TECHNIQUE_NAME,
    ensure_force_field_content,
)
from world.magic.factories import CharacterAnimaFactory
from world.magic.models import Technique
from world.magic.models.anima import CharacterAnima
from world.magic.services.condition_application import apply_technique_conditions
from world.magic.services.effect_handlers import absorb_pool


class AllyWardReactiveCostTests(TestCase):
    """Reactive-fire anima cost is billed to the caster who warded an ally."""

    def test_ally_ward_debits_caster_not_ally(self) -> None:
        """Damage absorbed; caster's anima drops by reactive_anima_cost; ally's untouched."""
        ensure_force_field_content()
        template = ConditionTemplate.objects.get(name=FORCE_FIELD_CONDITION_NAME)

        caster = CharacterSheetFactory().character
        ally = CharacterSheetFactory().character
        caster_anima = CharacterAnimaFactory(character=caster.sheet_data, current=10, maximum=10)
        ally_anima = CharacterAnimaFactory(character=ally.sheet_data, current=10, maximum=10)

        instance = ConditionInstanceFactory(
            condition=template,
            target=ally,
            source_character=caster,
            absorb_remaining=20,
        )

        payload = DamagePreApplyPayload(
            target=ally,
            amount=30,
            damage_type=None,
            source=DamageSource(type="environment", ref=None),
        )

        absorb_pool(payload=payload)

        # Buffer soaked 20 of the 30 incoming damage — overflow still lands.
        # Buffer fully spent → the instance is deleted (matches absorb_pool's contract).
        self.assertEqual(payload.amount, 10)
        self.assertFalse(
            type(instance).objects.filter(pk=instance.pk).exists(),
            "buffer fully consumed → instance should be deleted",
        )

        # Caster paid the reactive_anima_cost (1) for the ally's ward.
        caster_anima.refresh_from_db()
        self.assertEqual(
            caster_anima.current,
            9,
            "the caster who warded the ally should be debited the reactive anima cost",
        )

        # Ally's own anima is untouched — they didn't cast the ward.
        ally_anima.refresh_from_db()
        self.assertEqual(
            ally_anima.current,
            10,
            "the ally bearing the ward should NOT be debited for a caster-sourced condition",
        )

        # Sanity: without the fix,
        # CharacterAnima.objects.filter(character=instance.target.sheet_data)
        # would have found the ally's row instead and debited it.
        self.assertEqual(CharacterAnima.objects.get(character=ally.sheet_data).current, 10)

    def test_ally_ward_lapses_on_caster_poverty_not_ally(self) -> None:
        """drain_reactive_upkeep: caster too poor to sustain -> instance deleted, ally untouched."""
        ensure_force_field_content()
        template = ConditionTemplate.objects.get(name=FORCE_FIELD_CONDITION_NAME)

        caster = CharacterSheetFactory().character
        ally = CharacterSheetFactory().character
        CharacterAnimaFactory(character=caster.sheet_data, current=0, maximum=10)
        ally_anima = CharacterAnimaFactory(character=ally.sheet_data, current=10, maximum=10)

        ally_sheet = CharacterSheetFactory(character=ally)
        encounter = CombatEncounterFactory()
        CombatParticipantFactory(
            encounter=encounter,
            character_sheet=ally_sheet,
            status=ParticipantStatus.ACTIVE,
        )

        instance = ConditionInstanceFactory(
            condition=template,
            target=ally,
            source_character=caster,
        )

        drain_reactive_upkeep(encounter)

        # Caster couldn't afford the upkeep -> the ward lapses (deleted).
        self.assertFalse(
            ConditionInstance.objects.filter(pk=instance.pk).exists(),
            "ward should lapse when the CASTER can't afford upkeep, not the ally",
        )

        # Ally never paid for a ward they didn't cast -> untouched.
        ally_anima.refresh_from_db()
        self.assertEqual(
            ally_anima.current,
            10,
            "the ally bearing the ward should NOT be debited for a caster-sourced condition",
        )

    def test_consented_ward_fires_past_zero_and_accrues_for_the_caster(self) -> None:
        ensure_force_field_content()
        template = ConditionTemplate.objects.get(name=FORCE_FIELD_CONDITION_NAME)
        caster = CharacterSheetFactory().character
        ally = CharacterSheetFactory().character
        caster_anima = CharacterAnimaFactory(character=caster.sheet_data, current=0, maximum=10)
        ConditionInstanceFactory(
            condition=template,
            target=ally,
            source_character=caster,
            absorb_remaining=20,
            soulfray_consented=True,
        )
        payload = DamagePreApplyPayload(
            target=ally,
            amount=30,
            damage_type=None,
            source=DamageSource(type="environment", ref=None),
        )
        with patch("world.magic.services.effect_handlers.accumulate_soulfray") as accrue:
            absorb_pool(payload=payload)
        self.assertEqual(payload.amount, 10)
        caster_anima.refresh_from_db()
        self.assertEqual(caster_anima.current, 0)
        accrue.assert_called_once()
        self.assertEqual(accrue.call_args.kwargs["deficit"], template.reactive_anima_cost)
        self.assertEqual(accrue.call_args.kwargs["character"], caster)

    def test_unconsented_ward_at_zero_still_fizzles(self) -> None:
        ensure_force_field_content()
        template = ConditionTemplate.objects.get(name=FORCE_FIELD_CONDITION_NAME)
        caster = CharacterSheetFactory().character
        ally = CharacterSheetFactory().character
        CharacterAnimaFactory(character=caster.sheet_data, current=0, maximum=10)
        ConditionInstanceFactory(
            condition=template, target=ally, source_character=caster, absorb_remaining=20
        )
        payload = DamagePreApplyPayload(
            target=ally,
            amount=30,
            damage_type=None,
            source=DamageSource(type="environment", ref=None),
        )
        absorb_pool(payload=payload)
        self.assertEqual(payload.amount, 30)

    def test_consented_ally_upkeep_holds_the_caster_through_deficit(self) -> None:
        """drain_reactive_upkeep: consented caster runs into deficit, ward survives."""
        ensure_force_field_content()
        template = ConditionTemplate.objects.get(name=FORCE_FIELD_CONDITION_NAME)

        caster = CharacterSheetFactory().character
        ally = CharacterSheetFactory().character
        CharacterAnimaFactory(character=caster.sheet_data, current=0, maximum=10)
        ally_anima = CharacterAnimaFactory(character=ally.sheet_data, current=10, maximum=10)

        ally_sheet = CharacterSheetFactory(character=ally)
        # LETHAL so deduct_anima does not clamp the debit to the caster's
        # available anima - the whole point of this test is that the caster
        # runs into deficit rather than lapsing (mirrors _build_guardian_and_ally
        # in test_guardian_reactions.py, #3573).
        encounter = CombatEncounterFactory(risk_level=RiskLevel.LETHAL)
        CombatParticipantFactory(
            encounter=encounter,
            character_sheet=ally_sheet,
            status=ParticipantStatus.ACTIVE,
        )

        instance = ConditionInstanceFactory(
            condition=template,
            target=ally,
            source_character=caster,
            soulfray_consented=True,
        )

        with (
            patch("world.combat.services.accumulate_soulfray") as accrue,
            patch("world.combat.services._broadcast_commitment_line"),
        ):
            drain_reactive_upkeep(encounter)

        # Consented caster runs into deficit instead of the ward lapsing.
        self.assertTrue(
            ConditionInstance.objects.filter(pk=instance.pk).exists(),
            "consented caster should hold the ward through deficit, not lapse it",
        )
        caster_anima = CharacterAnima.objects.get(character=caster.sheet_data)
        self.assertEqual(caster_anima.current, 0)
        accrue.assert_called_once()
        # Caster started at 0 anima; the ward's upkeep cost is 1/round (lethal
        # encounter, so deduct_anima does not clamp) -> deficit is exactly 1.
        self.assertEqual(accrue.call_args.kwargs["deficit"], template.upkeep_anima_per_round)

        # Ally never paid for a ward they didn't cast -> untouched.
        ally_anima.refresh_from_db()
        self.assertEqual(
            ally_anima.current,
            10,
            "the ally bearing the ward should NOT be debited for a caster-sourced condition",
        )


class WardConsentStampTests(TestCase):
    """ConditionInstance.soulfray_consented is stamped from the cast (#3573)."""

    def test_apply_technique_conditions_stamps_consent_on_the_ward(self) -> None:
        ensure_force_field_content()
        technique = Technique.objects.get(name=FORCE_FIELD_TECHNIQUE_NAME)
        caster = CharacterSheetFactory().character
        ally = CharacterSheetFactory().character
        row = technique.condition_applications.get()
        results = apply_technique_conditions(
            technique=technique,
            success_level=2,
            eff_intensity=5,
            targets_by_kind={row.target_kind: [ally]},
            source_character=caster,
            soulfray_consented=True,
        )
        instance = ConditionInstance.objects.get(target=ally, condition=row.condition)
        self.assertTrue(instance.soulfray_consented)
        self.assertEqual(len(results), 1)
