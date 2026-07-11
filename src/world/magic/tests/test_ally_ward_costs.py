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

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory
from flows.events.payloads import DamagePreApplyPayload, DamageSource
from world.character_sheets.factories import CharacterSheetFactory
from world.combat.constants import ParticipantStatus
from world.combat.factories import CombatEncounterFactory, CombatParticipantFactory
from world.combat.services import drain_reactive_upkeep
from world.conditions.constants import FORCE_FIELD_CONDITION_NAME
from world.conditions.factories import ConditionInstanceFactory
from world.conditions.models import ConditionInstance, ConditionTemplate
from world.magic.effect_palette_content import ensure_force_field_content
from world.magic.factories import CharacterAnimaFactory
from world.magic.models.anima import CharacterAnima
from world.magic.services.effect_handlers import absorb_pool


class AllyWardReactiveCostTests(TestCase):
    """Reactive-fire anima cost is billed to the caster who warded an ally."""

    def test_ally_ward_debits_caster_not_ally(self) -> None:
        """Damage absorbed; caster's anima drops by reactive_anima_cost; ally's untouched."""
        ensure_force_field_content()
        template = ConditionTemplate.objects.get(name=FORCE_FIELD_CONDITION_NAME)

        caster = CharacterFactory()
        ally = CharacterFactory()
        caster_anima = CharacterAnimaFactory(character=caster, current=10, maximum=10)
        ally_anima = CharacterAnimaFactory(character=ally, current=10, maximum=10)

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

        # Sanity: without the fix, CharacterAnima.objects.filter(character=instance.target)
        # would have found the ally's row instead and debited it.
        self.assertEqual(CharacterAnima.objects.get(character=ally).current, 10)

    def test_ally_ward_lapses_on_caster_poverty_not_ally(self) -> None:
        """drain_reactive_upkeep: caster too poor to sustain -> instance deleted, ally untouched."""
        ensure_force_field_content()
        template = ConditionTemplate.objects.get(name=FORCE_FIELD_CONDITION_NAME)

        caster = CharacterFactory()
        ally = CharacterFactory()
        CharacterAnimaFactory(character=caster, current=0, maximum=10)
        ally_anima = CharacterAnimaFactory(character=ally, current=10, maximum=10)

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
