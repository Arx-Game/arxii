"""E2E integration test for battlefield shaping (#2019).

Full journey: caster raises a Barricade, Phase Jumps, Force Grips an enemy,
and conjures a fire zone — then obstacles + hazards expire via round-tick.
"""

from types import SimpleNamespace

from django.test import TestCase

from world.areas.positioning.factories import PositionFactory
from world.areas.positioning.models import PositionEdge
from world.areas.positioning.services import (
    connect_positions,
    create_conjured_obstacle,
    expire_obstacle_rounds,
    place_in_position,
    position_of,
    teardown_conjured_obstacles,
)
from world.character_sheets.factories import CharacterSheetFactory
from world.conditions.factories import ConditionTemplateFactory
from world.conditions.models import ConditionInstance
from world.magic.services.effect_handlers import (
    create_obstacle_on_condition,
    create_zone_hazard_on_condition,
    force_move_target_on_condition,
    move_position_on_condition,
)
from world.room_features.trap_services import (
    teardown_conjured_hazards,
    tick_zone_hazards,
)


class BattlefieldShapingE2ETest(TestCase):
    """Full battlefield shaping journey exercising all four mechanisms (#2019)."""

    def setUp(self) -> None:
        from evennia import create_object

        self.room = create_object("typeclasses.rooms.Room", key="battlefield")
        # Position graph: alpha — bravo — charlie — delta (chasm)
        self.alpha = PositionFactory(room=self.room, name="alpha")
        self.bravo = PositionFactory(room=self.room, name="bravo")
        self.charlie = PositionFactory(room=self.room, name="charlie")
        self.delta = PositionFactory(room=self.room, name="delta")

        # Edges between positions
        self.edge_ab = connect_positions(self.alpha, self.bravo, is_passable=True)
        self.edge_bc = connect_positions(self.bravo, self.charlie, is_passable=True)
        self.edge_cd = connect_positions(self.charlie, self.delta, is_passable=True)

        # Caster + enemy
        self.caster_sheet = CharacterSheetFactory()
        self.caster = self.caster_sheet.character
        self.caster.db_location = self.room
        self.caster.save()
        place_in_position(self.caster, self.alpha)

        self.enemy_sheet = CharacterSheetFactory()
        self.enemy = self.enemy_sheet.character
        self.enemy.db_location = self.room
        self.enemy.save()
        place_in_position(self.enemy, self.charlie)

        # Condition templates for each effect
        self.barricade_template = ConditionTemplateFactory(name="Barricade")
        self.teleport_template = ConditionTemplateFactory(name="Phase Jump")
        self.telekinesis_template = ConditionTemplateFactory(name="Force Grip")
        self.fire_template = ConditionTemplateFactory(name="Conjure Fire")

    def test_barricade_blocks_movement(self) -> None:
        """1. Caster raises a Barricade on the bravo-charlie edge."""
        instance = ConditionInstance.objects.create(
            target=self.caster,
            condition=self.barricade_template,
            cast_position_a=self.bravo,
            cast_position_b=self.charlie,
            source_character=self.caster,
            rounds_remaining=5,
        )
        payload = SimpleNamespace(target=self.caster, instance=instance)
        create_obstacle_on_condition(payload=payload, position_a_id=0, position_b_id=0)

        edge = PositionEdge.objects.get(position_a=self.bravo, position_b=self.charlie)
        self.assertFalse(edge.is_passable)
        self.assertEqual(edge.duration_rounds, 5)
        self.assertIsNotNone(edge.created_by_sheet)

    def test_barricade_expires_via_round_tick(self) -> None:
        """2. Obstacle duration decrements and restores at 0."""
        create_conjured_obstacle(
            self.bravo, self.charlie, caster_sheet=self.caster_sheet, duration_rounds=1
        )
        expire_obstacle_rounds(self.room)

        edge = PositionEdge.objects.get(position_a=self.bravo, position_b=self.charlie)
        self.assertTrue(edge.is_passable)
        self.assertIsNone(edge.duration_rounds)
        self.assertIsNone(edge.created_by_sheet)

    def test_phase_jump_relocates_caster(self) -> None:
        """3. Caster Phase Jumps to a chosen destination."""
        instance = ConditionInstance.objects.create(
            target=self.caster,
            condition=self.teleport_template,
            cast_destination=self.charlie,
        )
        payload = SimpleNamespace(target=self.caster, instance=instance)
        move_position_on_condition(payload=payload, destination_position_id=0)
        self.assertEqual(position_of(self.caster), self.charlie)

    def test_force_grip_relocates_enemy(self) -> None:
        """4. Caster Force Grips the enemy to delta."""
        instance = ConditionInstance.objects.create(
            target=self.enemy,
            condition=self.telekinesis_template,
            cast_destination=self.delta,
        )
        payload = SimpleNamespace(target=self.enemy, instance=instance)
        force_move_target_on_condition(payload=payload, destination_position_id=0)
        self.assertEqual(position_of(self.enemy), self.delta)

    def test_zone_hazard_created_and_expires(self) -> None:
        """5. Caster conjures a fire zone that ticks and expires."""
        from actions.factories import ConsequencePoolFactory
        from world.checks.factories import CheckTypeFactory

        pool = ConsequencePoolFactory()
        check = CheckTypeFactory()

        instance = ConditionInstance.objects.create(
            target=self.caster,
            condition=self.fire_template,
            cast_destination=self.bravo,
        )
        payload = SimpleNamespace(target=self.caster, instance=instance)
        create_zone_hazard_on_condition(
            payload=payload,
            position_id=0,
            duration_rounds=2,
            consequence_pool_id=pool.pk,
            detect_check_type_id=check.pk,
        )

        from world.room_features.models import Trap

        hazard = Trap.objects.get(position=self.bravo)
        self.assertTrue(hazard.is_armed)
        self.assertEqual(hazard.duration_rounds, 2)

        # Tick once — decrements to 1, still armed
        tick_zone_hazards(self.room)
        hazard.refresh_from_db()
        self.assertEqual(hazard.duration_rounds, 1)
        self.assertTrue(hazard.is_armed)

        # Tick again — reaches 0, disarmed
        tick_zone_hazards(self.room)
        from evennia.utils.idmapper.models import flush_cache

        flush_cache()
        hazard = Trap.objects.get(pk=hazard.pk)
        self.assertFalse(hazard.is_armed)

    def test_teardown_restores_obstacles_and_disarms_hazards(self) -> None:
        """6. Encounter-end teardown restores obstacles + disarms hazards."""
        # Create a conjured obstacle
        create_conjured_obstacle(
            self.bravo, self.charlie, caster_sheet=self.caster_sheet, duration_rounds=5
        )
        # Create a conjured hazard
        from actions.factories import ConsequencePoolFactory
        from world.checks.factories import CheckTypeFactory
        from world.room_features.models import Trap

        pool = ConsequencePoolFactory()
        check = CheckTypeFactory()
        from evennia_extensions.models import RoomProfile

        room_profile, _created = RoomProfile.objects.get_or_create(objectdb=self.room)
        Trap.objects.create(
            room_profile=room_profile,
            position=self.bravo,
            name="Fire Field",
            consequence_pool=pool,
            detect_check_type=check,
            disarm_check_type=check,
            is_armed=True,
            is_hidden=False,
            duration_rounds=3,
            created_by_sheet=self.caster_sheet,
        )

        # Teardown
        teardown_conjured_obstacles(self.room)
        teardown_conjured_hazards(self.room)

        # Obstacle restored to passable
        edge = PositionEdge.objects.get(position_a=self.bravo, position_b=self.charlie)
        self.assertTrue(edge.is_passable)

        # Hazard disarmed
        from evennia.utils.idmapper.models import flush_cache

        flush_cache()
        hazard = Trap.objects.get(position=self.bravo)
        self.assertFalse(hazard.is_armed)

    def test_staff_edges_survive_teardown(self) -> None:
        """7. Staff-authored edges survive encounter-end teardown."""
        connect_positions(self.alpha, self.delta, is_passable=False)
        teardown_conjured_obstacles(self.room)
        edge = PositionEdge.objects.get(position_a=self.alpha, position_b=self.delta)
        self.assertFalse(edge.is_passable)
