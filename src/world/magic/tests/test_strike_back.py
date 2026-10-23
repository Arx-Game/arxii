"""A ward that strikes back at the NPC that hits its bearer (#4584).

``strike_back`` is read directly where combat damage lands on a player character
(``_emit_post_damage_events``), designated by the ward's ``retaliation_damage`` and
``retaliation_condition`` fields, never by its name and never by a seeded flow.
Every row here is mutated by some test and lives in the idmapper cache, so the
fixtures are rebuilt in ``setUp``.
"""

from dataclasses import replace
from unittest.mock import patch

from django.test import TestCase
from evennia import create_object

from flows.events.payloads import DamageAppliedPayload
from world.character_sheets.factories import CharacterSheetFactory
from world.combat.constants import OpponentStatus
from world.combat.damage_source import classify_source
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
)
from world.combat.models import ThreatRecord
from world.combat.services import apply_damage_to_participant
from world.conditions.factories import (
    ConditionInstanceFactory,
    ConditionTemplateFactory,
    DamageTypeFactory,
)
from world.conditions.models import ConditionInstance
from world.conditions.services import apply_condition, retaliating_instances
from world.magic.factories import CharacterAnimaFactory
from world.magic.models.anima import CharacterAnima
from world.magic.services.effect_handlers import strike_back
from world.vitals.models import CharacterVitals

RETALIATING_PATH = "world.conditions.services.retaliating_instances"


class _StrikeBackFixture(TestCase):
    """A knight and a caster in a fight with one brute; the caster wards the knight."""

    def setUp(self) -> None:
        self.room = create_object("typeclasses.rooms.Room", key="BriarRoom4584", nohome=True)
        self.encounter = CombatEncounterFactory(room=self.room)

        self.knight_sheet = CharacterSheetFactory()
        self.knight_char = self.knight_sheet.character
        self.knight_char.location = self.room
        self.knight_char.save()
        CharacterVitals.objects.create(
            character_sheet=self.knight_sheet, health=100, max_health=100
        )
        self.knight_seat = CombatParticipantFactory(
            encounter=self.encounter, character_sheet=self.knight_sheet
        )

        self.caster_sheet = CharacterSheetFactory()
        self.caster_char = self.caster_sheet.character
        self.caster_char.location = self.room
        self.caster_char.save()
        self.caster_anima = CharacterAnimaFactory(
            character=self.caster_sheet, current=10, maximum=10
        )
        self.caster_seat = CombatParticipantFactory(
            encounter=self.encounter, character_sheet=self.caster_sheet
        )

        self.brute = CombatOpponentFactory(
            encounter=self.encounter, health=50, max_health=50, soak_value=0
        )


class StrikeBackHandlerTests(_StrikeBackFixture):
    """``strike_back`` called with the payload of a hit on the bearer."""

    def setUp(self) -> None:
        super().setUp()
        self.called_out = ConditionTemplateFactory(
            name="Called Out 4584", forces_attack_on_source=True
        )
        self.briar = ConditionTemplateFactory(
            name="Briar Ward 4584",
            retaliation_damage=5,
            retaliation_damage_type=DamageTypeFactory(name="Briar 4584"),
            retaliation_condition=self.called_out,
            reactive_anima_cost=2,
        )
        self.inst = ConditionInstanceFactory(
            target=self.knight_char, condition=self.briar, source_character=self.caster_char
        )
        self.payload = DamageAppliedPayload(
            target=self.knight_char,
            amount_dealt=8,
            damage_type=None,
            source=classify_source(self.brute),
            hp_after=92,
        )

    def _caster_anima(self) -> int:
        return CharacterAnima.objects.get(character=self.caster_sheet).current

    def _called_out_on_brute(self) -> bool:
        return ConditionInstance.objects.filter(
            target_id=self.brute.objectdb_id, condition=self.called_out
        ).exists()

    def test_strike_back_damages_the_npc_that_struck(self) -> None:
        strike_back(payload=self.payload, instance=self.inst)

        self.brute.refresh_from_db()
        self.assertEqual(self.brute.health, 50 - 5)
        self.assertEqual(self._caster_anima(), 10 - 2)

    def test_strike_back_lays_its_condition_with_the_caster_as_source(self) -> None:
        strike_back(payload=self.payload, instance=self.inst)

        laid = ConditionInstance.objects.get(
            target_id=self.brute.objectdb_id, condition=self.called_out
        )
        self.assertEqual(laid.source_character_id, self.caster_char.pk)

    def test_strike_back_damage_counts_as_the_casters_threat(self) -> None:
        strike_back(payload=self.payload, instance=self.inst)

        record = ThreatRecord.objects.get(opponent=self.brute, participant=self.caster_seat)
        self.assertEqual(record.threat_value, 5)

    def test_a_self_cast_ward_bills_and_credits_the_bearer(self) -> None:
        self.inst.source_character = None
        self.inst.save(update_fields=["source_character"])
        CharacterAnimaFactory(character=self.knight_sheet, current=10, maximum=10)

        strike_back(payload=self.payload, instance=self.inst)

        self.assertEqual(CharacterAnima.objects.get(character=self.knight_sheet).current, 8)
        record = ThreatRecord.objects.get(opponent=self.brute, participant=self.knight_seat)
        self.assertEqual(record.threat_value, 5)

    def test_strike_back_never_hits_a_player_character(self) -> None:
        payload = replace(self.payload, source=classify_source(self.caster_char))

        strike_back(payload=payload, instance=self.inst)

        self.assertEqual(self._caster_anima(), 10)
        self.brute.refresh_from_db()
        self.assertEqual(self.brute.health, 50)

    def test_a_blow_from_nowhere_is_not_answered(self) -> None:
        payload = replace(self.payload, source=classify_source(None))

        strike_back(payload=payload, instance=self.inst)

        self.assertEqual(self._caster_anima(), 10)

    def test_a_blow_that_dealt_nothing_is_not_answered(self) -> None:
        strike_back(payload=replace(self.payload, amount_dealt=0), instance=self.inst)

        self.brute.refresh_from_db()
        self.assertEqual(self.brute.health, 50)
        self.assertEqual(self._caster_anima(), 10)

    def test_an_npc_already_out_of_the_fight_is_not_answered(self) -> None:
        self.brute.status = OpponentStatus.FLED
        self.brute.save(update_fields=["status"])

        strike_back(payload=self.payload, instance=self.inst)

        self.brute.refresh_from_db()
        self.assertEqual(self.brute.health, 50)
        self.assertEqual(self._caster_anima(), 10)

    def test_a_ward_already_spent_this_round_does_nothing(self) -> None:
        self.inst.delete()

        strike_back(payload=self.payload, instance=self.inst)

        self.brute.refresh_from_db()
        self.assertEqual(self.brute.health, 50)
        self.assertEqual(self._caster_anima(), 10)

    def test_a_ward_with_nothing_to_strike_with_charges_nothing(self) -> None:
        empty = ConditionTemplateFactory(name="Bare Hedge 4584", reactive_anima_cost=2)
        inst = ConditionInstanceFactory(
            target=self.knight_char, condition=empty, source_character=self.caster_char
        )

        strike_back(payload=self.payload, instance=inst)

        self.brute.refresh_from_db()
        self.assertEqual(self.brute.health, 50)
        self.assertEqual(self._caster_anima(), 10)

    def test_a_ward_the_caster_cannot_pay_for_fizzles(self) -> None:
        self.caster_anima.current = 1
        self.caster_anima.save(update_fields=["current"])

        strike_back(payload=self.payload, instance=self.inst)

        self.brute.refresh_from_db()
        self.assertEqual(self.brute.health, 50)
        self.assertFalse(self._called_out_on_brute())

    def test_a_retaliation_that_defeats_the_npc_lays_no_condition(self) -> None:
        self.brute.health = 3
        self.brute.save(update_fields=["health"])

        strike_back(payload=self.payload, instance=self.inst)

        self.brute.refresh_from_db()
        self.assertEqual(self.brute.status, OpponentStatus.DEFEATED)
        self.assertFalse(self._called_out_on_brute())

    def test_a_condition_only_ward_lays_its_condition_without_damage(self) -> None:
        self.briar.retaliation_damage = 0
        self.briar.save(update_fields=["retaliation_damage"])

        strike_back(payload=self.payload, instance=self.inst)

        self.brute.refresh_from_db()
        self.assertEqual(self.brute.health, 50)
        self.assertTrue(self._called_out_on_brute())


class StrikeBackAtTheDamageSeamTests(_StrikeBackFixture):
    """A real hit on a warded PC answers through the damage seam, with no trigger rows."""

    def test_a_real_hit_on_the_bearer_runs_the_strike_back(self) -> None:
        ward = ConditionTemplateFactory(name="Hedge Thorns 4584", retaliation_damage=4)
        apply_condition(self.knight_char, ward, source_character=self.caster_char)

        apply_damage_to_participant(self.knight_seat, 8, source=self.brute)

        self.brute.refresh_from_db()
        self.assertEqual(self.brute.health, 50 - 4)

    def test_a_ward_with_no_damage_and_no_condition_does_nothing_and_charges_nothing(
        self,
    ) -> None:
        ward = ConditionTemplateFactory(name="Quiet Hedge 4584", reactive_anima_cost=2)
        apply_condition(self.knight_char, ward, source_character=self.caster_char)

        apply_damage_to_participant(self.knight_seat, 8, source=self.brute)

        self.brute.refresh_from_db()
        self.assertEqual(self.brute.health, 50)
        self.assertEqual(CharacterAnima.objects.get(character=self.caster_sheet).current, 10)

    def test_a_hit_from_a_player_character_is_not_answered(self) -> None:
        ward = ConditionTemplateFactory(name="Hedge Thorns PvP 4584", retaliation_damage=4)
        apply_condition(self.knight_char, ward, source_character=self.caster_char)

        apply_damage_to_participant(self.knight_seat, 8, source=self.caster_char)

        self.brute.refresh_from_db()
        self.assertEqual(self.brute.health, 50)
        self.assertEqual(CharacterVitals.objects.get(character_sheet=self.knight_sheet).health, 92)

    def test_a_hit_from_a_player_character_never_reads_the_wards(self) -> None:
        """A blow only a CombatOpponent can be answered for skips the wards query."""
        with patch(RETALIATING_PATH) as wards:
            apply_damage_to_participant(self.knight_seat, 8, source=self.caster_char)

        wards.assert_not_called()


class RetaliatingInstancesTests(_StrikeBackFixture):
    """The helper returns the bearer's active strike-back instances, oldest first."""

    def test_returns_only_active_retaliating_instances_in_one_query(self) -> None:
        provoke = ConditionTemplateFactory(name="Mark 4584", forces_attack_on_source=True)
        by_damage = ConditionTemplateFactory(name="Thorn 4584", retaliation_damage=3)
        by_condition = ConditionTemplateFactory(name="Snare 4584", retaliation_condition=provoke)
        plain = ConditionTemplateFactory(name="Plain 4584")
        first = ConditionInstanceFactory(target=self.knight_char, condition=by_damage)
        ConditionInstanceFactory(target=self.knight_char, condition=plain)
        ConditionInstanceFactory(
            target=self.knight_char,
            condition=ConditionTemplateFactory(name="Hidden Thorn 4584", retaliation_damage=3),
            is_suppressed=True,
        )
        second = ConditionInstanceFactory(target=self.knight_char, condition=by_condition)
        ConditionInstanceFactory(target=self.caster_char, condition=by_damage)

        with self.assertNumQueries(1):
            found = retaliating_instances(self.knight_char)
            self.assertEqual([inst.condition.retaliation_damage for inst in found], [3, 0])

        self.assertEqual([inst.pk for inst in found], [first.pk, second.pk])
