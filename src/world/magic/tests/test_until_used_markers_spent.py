"""A one-shot marker condition is spent once its CONDITION_APPLIED flow fires (#4584).

The six ``*_on_condition`` adapters each read what they need from the marker
instance and then spend it through ``spend_condition_use``: the marker's flow fired
and cannot fire again for that instance. The seeded templates are ``UNTIL_USED``; a
marker authored with a lasting duration is never spent by use, and the zone-hazard
marker here is a factory template named unlike any seed.
"""

from types import SimpleNamespace

from django.test import TestCase
from evennia import create_object

from actions.factories import ConsequencePoolFactory
from actions.models import ConsequencePool
from world.areas.positioning.factories import PositionFactory
from world.areas.positioning.models import PositionEdge, Rampart
from world.areas.positioning.services import place_in_position, position_of
from world.checks.factories import CheckTypeFactory
from world.combat.constants import CombatAllegiance, ParticipantStatus
from world.combat.factories import CombatEncounterFactory, CombatParticipantFactory
from world.combat.models import CombatOpponent, ThreatPool
from world.conditions.constants import (
    OBSTACLE_CONDITION_NAME,
    SUMMONING_CONDITION_NAME,
    TELEKINESIS_CONDITION_NAME,
    TELEPORT_CONDITION_NAME,
    DurationType,
)
from world.conditions.factories import ConditionTemplateFactory
from world.conditions.models import ConditionInstance, ConditionTemplate
from world.magic.effect_palette_content import (
    SUMMON_POOL_NAME,
    ensure_obstacle_content,
    ensure_rampart_content,
    ensure_summon_content,
    ensure_telekinesis_content,
    ensure_teleport_content,
)
from world.magic.services.effect_handlers import (
    create_obstacle_on_condition,
    create_zone_hazard_on_condition,
    force_move_target_on_condition,
    move_position_on_condition,
    raise_rampart_on_condition,
    summon_ally_on_condition,
)
from world.room_features.models import Trap


def _gone(instance: ConditionInstance) -> bool:
    return not ConditionInstance.objects.filter(pk=instance.pk).exists()


class _PlacedCharacterFixture(TestCase):
    """A character standing at one position in a room with a second position."""

    def setUp(self) -> None:
        self.room = create_object("typeclasses.rooms.Room", key="MarkerRoom4584", nohome=True)
        self.target = create_object("typeclasses.characters.Character", key="Marked4584")
        self.target.db_location = self.room
        self.target.save()
        self.start = PositionFactory(room=self.room, name="start")
        self.dest = PositionFactory(room=self.room, name="destination")
        place_in_position(self.target, self.start)

    def _marker(self, template: ConditionTemplate, **fields) -> ConditionInstance:
        return ConditionInstance.objects.create(target=self.target, condition=template, **fields)


class MovementMarkersSpentTests(_PlacedCharacterFixture):
    def test_a_phase_jump_marker_is_spent_after_the_jump(self) -> None:
        ensure_teleport_content()
        marker = self._marker(
            ConditionTemplate.objects.get(name=TELEPORT_CONDITION_NAME), cast_destination=self.dest
        )

        move_position_on_condition(
            payload=SimpleNamespace(target=self.target, instance=marker),
            destination_position_id=0,
        )

        self.assertEqual(position_of(self.target), self.dest)
        self.assertTrue(_gone(marker))

    def test_a_force_grip_marker_is_spent_after_the_shove(self) -> None:
        ensure_telekinesis_content()
        marker = self._marker(
            ConditionTemplate.objects.get(name=TELEKINESIS_CONDITION_NAME),
            cast_destination=self.dest,
        )

        force_move_target_on_condition(
            payload=SimpleNamespace(target=self.target, instance=marker),
            destination_position_id=0,
        )

        self.assertEqual(position_of(self.target), self.dest)
        self.assertTrue(_gone(marker))

    def test_a_marker_with_no_destination_is_still_spent(self) -> None:
        ensure_teleport_content()
        marker = self._marker(ConditionTemplate.objects.get(name=TELEPORT_CONDITION_NAME))

        move_position_on_condition(
            payload=SimpleNamespace(target=self.target, instance=marker),
            destination_position_id=0,
        )

        self.assertEqual(position_of(self.target), self.start)
        self.assertTrue(_gone(marker))

    def test_a_rounds_marker_is_not_spent(self) -> None:
        template = ConditionTemplateFactory(
            name="Lingering Stride 4584", default_duration_type=DurationType.ROUNDS
        )
        marker = self._marker(template, cast_destination=self.dest)

        move_position_on_condition(
            payload=SimpleNamespace(target=self.target, instance=marker),
            destination_position_id=0,
        )

        self.assertEqual(position_of(self.target), self.dest)
        self.assertFalse(_gone(marker))

    def test_a_payload_without_an_instance_does_not_raise(self) -> None:
        move_position_on_condition(
            payload=SimpleNamespace(target=self.target), destination_position_id=self.dest.pk
        )

        self.assertEqual(position_of(self.target), self.dest)


class BattlefieldMarkersSpentTests(_PlacedCharacterFixture):
    def test_a_barricade_marker_is_spent_after_the_edge_is_sealed(self) -> None:
        ensure_obstacle_content()
        marker = self._marker(
            ConditionTemplate.objects.get(name=OBSTACLE_CONDITION_NAME),
            cast_position_a=self.start,
            cast_position_b=self.dest,
        )

        create_obstacle_on_condition(
            payload=SimpleNamespace(target=self.target, instance=marker),
            position_a_id=0,
            position_b_id=0,
        )

        low, high = sorted([self.start, self.dest], key=lambda p: p.pk)
        edge = PositionEdge.objects.get(position_a=low, position_b=high)
        self.assertFalse(edge.is_passable)
        self.assertTrue(_gone(marker))

    def test_a_rampart_marker_is_spent_after_the_rampart_rises(self) -> None:
        ensure_rampart_content()
        marker = self._marker(
            ConditionTemplate.objects.get(name="Stone Rampart"), cast_destination=self.dest
        )

        raise_rampart_on_condition(
            payload=SimpleNamespace(target=self.target, instance=marker),
            position_id=0,
            element_profile_name="Stone",
            integrity=24,
        )

        self.assertTrue(Rampart.objects.filter(position=self.dest).exists())
        self.assertTrue(_gone(marker))

    def test_a_zone_hazard_marker_is_spent_after_the_hazard_is_laid(self) -> None:
        template = ConditionTemplateFactory(
            name="Caltrop Scatter 4584", default_duration_type=DurationType.UNTIL_USED
        )
        marker = ConditionInstance.objects.create(
            target=self.room, condition=template, cast_destination=self.dest
        )

        create_zone_hazard_on_condition(
            payload=SimpleNamespace(target=self.room, instance=marker),
            position_id=0,
            duration_rounds=3,
            consequence_pool_id=ConsequencePoolFactory().pk,
            detect_check_type_id=CheckTypeFactory().pk,
        )

        self.assertTrue(Trap.objects.filter(position=self.dest).exists())
        self.assertTrue(_gone(marker))

    def test_an_adapter_that_raises_keeps_its_error_and_its_marker(self) -> None:
        template = ConditionTemplateFactory(
            name="Broken Scatter 4584", default_duration_type=DurationType.UNTIL_USED
        )
        marker = ConditionInstance.objects.create(
            target=self.room, condition=template, cast_destination=self.dest
        )

        with self.assertRaises(ConsequencePool.DoesNotExist):
            create_zone_hazard_on_condition(
                payload=SimpleNamespace(target=self.room, instance=marker),
                position_id=0,
                duration_rounds=3,
                consequence_pool_id=0,
                detect_check_type_id=CheckTypeFactory().pk,
            )

        self.assertFalse(_gone(marker))


class SummoningMarkerSpentTests(TestCase):
    def test_a_summoning_marker_is_spent_after_the_ally_arrives(self) -> None:
        ensure_summon_content()
        pool = ThreatPool.objects.get(name=SUMMON_POOL_NAME)
        encounter = CombatEncounterFactory()
        participant = CombatParticipantFactory(encounter=encounter, status=ParticipantStatus.ACTIVE)
        caster = participant.character_sheet.character
        marker = ConditionInstance.objects.create(
            target=caster, condition=ConditionTemplate.objects.get(name=SUMMONING_CONDITION_NAME)
        )

        summon_ally_on_condition(
            payload=SimpleNamespace(target=caster, instance=marker),
            threat_pool_name=pool.name,
            bond_rounds=5,
        )

        self.assertTrue(
            CombatOpponent.objects.filter(
                encounter=encounter, allegiance=CombatAllegiance.ALLY
            ).exists()
        )
        self.assertTrue(_gone(marker))
