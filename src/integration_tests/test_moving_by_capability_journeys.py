"""Journeys for moving by capability (#4663, slice 2 of #4651).

A player character's movement capabilities decide how she crosses the position graph.
The yard has two positions, West and Middle, joined by a sealed edge with a way past it:
a Thorn Hedge, an active gating challenge.

- Kit can climb: a "climbing" capability, whose Climb application (way of moving Climbs,
  no property needed, #5066) her trained +3 modifier reaches. Her movement is raised to
  10, two hops a round. She goes over the hedge from the web client's move dispatch for
  two hops, and the hedge stays up.
- Hobb walks. The hedge stops him with "Crossing that requires getting past Thorn Hedge."
- Kit with one hop left is refused: "That crossing takes 2 hops; you have 1 left."
- Wren has wings from her species: a "winged flight" capability, whose Fly application
  (way of moving Flies) a +3 modifier reaches. ``position/fly`` puts her above West,
  ``position/land`` brings her back down, one hop each.
- Kit's move list (she climbs and flies) offers "Climb over to Middle (2 hops)" and
  "Take flight"; Hobb's offers neither.

- A climb over the wall in a fight is a use of her trained ability: 1 physical fatigue, no
  anima (#5066 decision 17). Walking is free.
- Phase Through (#5066): Sela knows Smoke Step, a technique marked ``incorporeal`` that
  grants "phasing". The Phase Through application needs ``incorporeal`` and passes through a
  wall whose challenge carries ``solid``. The hedge is ``solid``: she phases through it for
  one hop, and the crossing is a cast of Smoke Step (its 3 anima). A wall that is not solid
  stops her.

Expected values are the rows built here: movement baseline 5 (the foundational seed) plus
5 is 10, two hops at five points a hop; the crossing cost 2 is GATED_CROSSING_HOPS.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import override_settings

from actions.factories import ActionTemplateFactory
from actions.player_interface import get_player_actions
from integration_tests.harness import JourneyCase
from world.areas.positioning.constants import CreatureTraversal, PositionKind
from world.areas.positioning.factories import PositionFactory
from world.areas.positioning.models import Position
from world.areas.positioning.services import (
    connect_positions,
    edge_between,
    is_aerial,
    materialize_aerial_layer,
    place_in_position,
    position_of,
    set_position_cover,
)
from world.checks.factories import CheckTypeFactory
from world.combat.constants import ParticipantStatus
from world.combat.factories import CombatEncounterFactory, CombatParticipantFactory
from world.combat.models import CombatParticipant
from world.conditions.constants import FoundationalCapability
from world.conditions.factories import CapabilityTypeFactory
from world.conditions.models import CapabilityType
from world.fatigue.models import FatiguePool
from world.magic.factories import (
    CharacterAnimaFactory,
    CharacterTechniqueFactory,
    TechniqueCapabilityGrantFactory,
    TechniqueFactory,
)
from world.magic.models.anima import CharacterAnima
from world.mechanics.factories import (
    AerialPropertyFactory,
    ChallengeInstanceFactory,
    ChallengeTemplateFactory,
    CharacterEngagementFactory,
    ModifierCategoryFactory,
    MovementApplicationFactory,
    PropertyFactory,
)
from world.mechanics.models import (
    ChallengeInstance,
    CharacterModifier,
    ModifierSource,
    ModifierTarget,
)
from world.scenes.constants import RoundStatus
from world.vitals.seeds import ensure_foundational_capabilities

HEDGE = "Thorn Hedge"
GATED = f"Crossing that requires getting past {HEDGE}."
ROOFED = "A roof is in the way."
TOO_FEW_HOPS = "That crossing takes 2 hops; you have 1 left."
EXTRA_MOVEMENT = 5  # baseline 5 + 5 = 10 movement = 2 hops a round
CAPABILITY_RAISE = 3


class _TheHedgedYard(JourneyCase):
    """West and Middle behind a Thorn Hedge, and a fight in DECLARING round 1."""

    def setUp(self) -> None:
        super().setUp()
        with override_settings(SEED_SAMPLE_CONTENT=True):  # the movement capability
            ensure_foundational_capabilities()
        AerialPropertyFactory()
        self.climbing = CapabilityTypeFactory(name="climbing", innate_baseline=0)
        MovementApplicationFactory(
            name="Climb", capability=self.climbing, way_of_moving=CreatureTraversal.CLIMBS
        )
        self.flight = CapabilityTypeFactory(name="winged flight", innate_baseline=0)
        MovementApplicationFactory(
            name="Fly", capability=self.flight, way_of_moving=CreatureTraversal.FLIES
        )
        self.solid = PropertyFactory(name="solid")
        self.yard = self.make_room("The Yard")
        self.west = PositionFactory(room=self.yard, name="West")
        self.middle = PositionFactory(room=self.yard, name="Middle")
        hedge_template = ChallengeTemplateFactory(name=HEDGE)
        hedge_template.properties.add(self.solid)
        self.hedge = ChallengeInstanceFactory(template=hedge_template, location=self.yard)
        connect_positions(self.west, self.middle, is_passable=False, gating_challenge=self.hedge)
        self.encounter = CombatEncounterFactory(
            status=RoundStatus.DECLARING, round_number=1, room=self.yard
        )

    def raise_capability(self, character, capability: CapabilityType, value: int) -> None:
        """A modifier on the sheet (the species/distinction shape) raising ``capability``."""
        target, _ = ModifierTarget.objects.get_or_create(
            name=f"capability_{capability.pk}",
            category=ModifierCategoryFactory(name="capability"),
            defaults={
                "description": "",
                "display_order": 0,
                "is_active": True,
                "target_capability": capability,
            },
        )
        CharacterModifier.objects.create(
            character=character.sheet_data,
            target=target,
            value=value,
            source=ModifierSource.objects.create(),
        )

    def mover(self, name: str, *, climbs: bool = False, flies: bool = False):
        character = self.make_player(name, room=self.yard)
        CombatParticipantFactory(
            encounter=self.encounter,
            character_sheet=character.sheet_data,
            status=ParticipantStatus.ACTIVE,
        )
        movement = CapabilityType.objects.get(name=FoundationalCapability.MOVEMENT)
        self.raise_capability(character, movement, EXTRA_MOVEMENT)
        if climbs:
            self.raise_capability(character, self.climbing, CAPABILITY_RAISE)
        if flies:
            self.raise_capability(character, self.flight, CAPABILITY_RAISE)
        place_in_position(character, self.west)
        return character

    def participant(self, character) -> CombatParticipant:
        return CombatParticipant.objects.get(
            encounter=self.encounter, character_sheet=character.sheet_data
        )


class ClimbingTheHedge(_TheHedgedYard):
    def test_climber_crosses_a_gated_wall_for_two_hops(self) -> None:
        kit = self.mover("Kit", climbs=True)

        result = self.web(kit, "move_to_position", position_id=self.middle.pk)

        self.assertTrue(result.detail.success, result.detail.message)
        self.assertEqual(position_of(kit), self.middle)
        self.assertEqual(self.participant(kit).hops_used, 2)
        self.assertTrue(ChallengeInstance.objects.get(pk=self.hedge.pk).is_active)

    def test_a_trained_climb_in_a_fight_costs_physical_fatigue_and_no_anima(self) -> None:
        kit = self.mover("Kit", climbs=True)
        CharacterAnimaFactory(character=kit.sheet_data, current=10, maximum=10)

        self.web(kit, "move_to_position", position_id=self.middle.pk)

        pool = FatiguePool.objects.get(character_sheet=kit.sheet_data)
        self.assertGreater(pool.physical_current, 0)
        self.assertEqual(CharacterAnima.objects.get(character=kit.sheet_data).current, 10)

    def test_walker_is_still_stopped_by_the_wall(self) -> None:
        hobb = self.mover("Hobb")

        result = self.web(hobb, "move_to_position", position_id=self.middle.pk)

        self.assertFalse(result.detail.success)
        self.assertEqual(result.detail.message, GATED)
        self.assertEqual(position_of(hobb), self.west)
        self.assertEqual(self.participant(hobb).hops_used, 0)

    def test_two_hop_crossing_with_one_hop_left_is_refused(self) -> None:
        kit = self.mover("Kit", climbs=True)
        participant = self.participant(kit)
        participant.hops_used = 1  # two hops a round, one spent
        participant.save(update_fields=["hops_used"])

        result = self.web(kit, "move_to_position", position_id=self.middle.pk)

        self.assertFalse(result.detail.success)
        self.assertEqual(result.detail.message, TOO_FEW_HOPS)
        self.assertEqual(position_of(kit), self.west)
        self.assertEqual(self.participant(kit).hops_used, 1)


class TakingFlight(_TheHedgedYard):
    def test_flier_from_a_modifier_takes_off_and_lands(self) -> None:
        wren = self.mover("Wren", flies=True)

        self.telnet(wren, "position/fly")

        above = position_of(wren)
        self.assertEqual(above.kind, PositionKind.AERIAL)
        self.assertEqual(above.elevation_anchor, self.west)
        self.assertTrue(is_aerial(wren))
        self.assertEqual(self.participant(wren).hops_used, 1)

        self.telnet(wren, "position/land")

        self.assertEqual(position_of(wren), self.west)
        self.assertFalse(is_aerial(wren))
        self.assertEqual(self.participant(wren).hops_used, 2)

    def test_flier_cannot_take_off_under_a_roof(self) -> None:
        wren = self.mover("Wren", flies=True)
        set_position_cover(self.west, roofed=True, screens_ranged=False)

        self.assertIn(ROOFED, self.telnet(wren, "position/fly"))

        self.assertEqual(position_of(wren), self.west)
        self.assertFalse(is_aerial(wren))
        self.assertEqual(self.participant(wren).hops_used, 0)
        names = {action.display_name for action in get_player_actions(wren)}
        self.assertNotIn("Take flight", names)

    def test_flier_cannot_land_onto_a_roofed_place(self) -> None:
        wren = self.mover("Wren", flies=True)
        self.telnet(wren, "position/fly")
        above = position_of(wren)
        set_position_cover(self.west, roofed=True, screens_ranged=False)

        self.assertIn(ROOFED, self.telnet(wren, "position/land"))

        self.assertEqual(position_of(wren), above)
        self.assertTrue(is_aerial(wren))
        self.assertEqual(self.participant(wren).hops_used, 1)
        names = {action.display_name for action in get_player_actions(wren)}
        self.assertNotIn("Land", names)

    def test_flier_takes_off_from_a_place_added_after_the_sky_was_drawn(self) -> None:
        materialize_aerial_layer(self.yard)  # someone is already up; the sky has a layer
        east = PositionFactory(room=self.yard, name="East")
        connect_positions(self.west, east)
        wren = self.mover("Wren", flies=True)
        place_in_position(wren, east)

        self.telnet(wren, "position/fly")

        above = position_of(wren)
        self.assertEqual(above.kind, PositionKind.AERIAL)
        self.assertEqual(above.elevation_anchor, east)
        above_west = Position.objects.get(
            room=self.yard, kind=PositionKind.AERIAL, elevation_anchor=self.west
        )
        self.assertIsNotNone(edge_between(above, above_west))

    def test_a_walker_cannot_take_flight(self) -> None:
        hobb = self.mover("Hobb")

        self.assertIn("You cannot fly.", self.telnet(hobb, "position/fly"))

        self.assertEqual(position_of(hobb), self.west)
        self.assertEqual(self.participant(hobb).hops_used, 0)


class TheMoveList(_TheHedgedYard):
    def test_move_list_offers_climb_and_take_off(self) -> None:
        kit = self.mover("Kit", climbs=True, flies=True)
        hobb = self.mover("Hobb")

        kits = {action.display_name: action for action in get_player_actions(kit)}
        climb = kits["Climb over to Middle (2 hops)"]
        self.assertTrue(climb.prerequisite_met)
        self.assertEqual(climb.ref.registry_key, "move_to_position")
        self.assertEqual(climb.ref.position_id, self.middle.pk)
        self.assertIn("Take flight", kits)

        hobbs = {action.display_name for action in get_player_actions(hobb)}
        self.assertNotIn("Climb over to Middle (2 hops)", hobbs)
        self.assertNotIn("Take flight", hobbs)
        self.assertIn(f"Move to Middle (blocked: {HEDGE})", hobbs)


class PhasingThroughAWall(_TheHedgedYard):
    def setUp(self) -> None:
        super().setUp()
        self.phasing = CapabilityTypeFactory(name="phasing", innate_baseline=0)
        incorporeal = PropertyFactory(name="incorporeal")
        MovementApplicationFactory(
            name="Phase Through",
            capability=self.phasing,
            target_property=self.solid,
            required_effect_property=incorporeal,
            way_of_moving=CreatureTraversal.PHASES,
        )
        self.smoke_step = TechniqueFactory(
            name="Smoke Step",
            anima_cost=3,
            intensity=1,
            control=1,
            action_template=ActionTemplateFactory(check_type=CheckTypeFactory(name="Smoke Cast")),
        )
        self.smoke_step.properties.add(incorporeal)
        TechniqueCapabilityGrantFactory(
            technique=self.smoke_step, capability=self.phasing, base_value=3, intensity_multiplier=0
        )
        patcher = patch(
            "world.combat.services.movement_use.roll_technique",
            return_value=MagicMock(success_level=1),
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def phaser(self, name: str):
        sela = self.mover(name)
        CharacterAnimaFactory(character=sela.sheet_data, current=10, maximum=10)
        CharacterEngagementFactory(character=sela.sheet_data)
        CharacterTechniqueFactory(character=sela.sheet_data, technique=self.smoke_step)
        return sela

    def test_she_phases_through_the_solid_hedge_for_one_hop_and_a_cast(self) -> None:
        sela = self.phaser("Sela")

        moves = {action.display_name for action in get_player_actions(sela)}
        self.assertIn("Phase through to Middle (1 hop)", moves)
        result = self.web(sela, "move_to_position", position_id=self.middle.pk)

        self.assertTrue(result.detail.success, result.detail.message)
        self.assertEqual(position_of(sela), self.middle)
        self.assertEqual(self.participant(sela).hops_used, 1)
        self.assertEqual(CharacterAnima.objects.get(character=sela.sheet_data).current, 7)

    def test_a_wall_that_is_not_solid_stops_her(self) -> None:
        self.hedge.template.properties.remove(self.solid)
        sela = self.phaser("Sela")

        result = self.web(sela, "move_to_position", position_id=self.middle.pk)

        self.assertFalse(result.detail.success)
        self.assertEqual(result.detail.message, GATED)
        self.assertEqual(position_of(sela), self.west)
