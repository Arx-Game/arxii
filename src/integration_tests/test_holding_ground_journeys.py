"""Journeys for held ground (#4663, slice 2 of #4651).

A ready enemy holds the place it stands in. A walker who steps into a held place stops
there for the round; one who starts the round there may walk out. A flier passes over it,
and so does a leaper. NPCs obey the same rule when they route toward player characters.

The causeway is five positions in a row, Lane - Gate - Yard - Hall - Tower, joined by open
edges, with a fight in DECLARING round 1.

- Kit has three hops a round (movement 5 + 10 = 15, five points a hop). A Bandit stands in
  the Yard. Kit walks from the Gate into the Yard and is told "You are stopped by Bandit.";
  she has no hops left, and a step on to the Hall is refused.
- A Bandit already DEFEATED holds nothing: Kit walks into the Yard and keeps two hops.
- Kit starting the round in the Yard beside the Bandit walks out to the Hall for one hop.
- Kit in the air above the Gate flies on above the Yard and is not stopped.
- Kit's move list marks the Yard: "Held by Bandit: you'd stop there."
- A Grey Wolf (three hops) at the Tower goes for Wren at the Lane. Hobb stands in the
  Yard between them: the walking wolf stops in the Yard. A leaping wolf goes past him to
  the Gate, beside Wren. With Hobb unconscious, the walking wolf goes past him too.

Expected values are the rows built here; "You are stopped by {name}." and
"Held by {name}: you'd stop there." are the spec's copy.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from django.test import override_settings

from actions.player_interface import get_player_actions
from integration_tests.harness import JourneyCase
from world.areas.positioning.constants import CreatureTraversal, PositionKind
from world.areas.positioning.factories import PositionFactory
from world.areas.positioning.services import connect_positions, place_in_position, position_of
from world.combat.constants import (
    OpponentStatus,
    OpponentTier,
    ParticipantStatus,
    StrikeDelivery,
    TargetingMode,
    TargetSelection,
)
from world.combat.factories import (
    CombatEncounterFactory,
    CombatParticipantFactory,
    CreatureTemplateFactory,
    OpponentTierTemplateFactory,
    ThreatPoolEntryFactory,
    ThreatPoolFactory,
)
from world.combat.models import CombatOpponent, CombatOpponentAction, CombatParticipant
from world.combat.services import resolve_round
from world.combat.services.boss.creature_spawn import spawn_from_creature_template
from world.combat.services.movement_budget import hops_left
from world.conditions.constants import FoundationalCapability
from world.conditions.factories import CapabilityTypeFactory
from world.conditions.models import CapabilityType
from world.conditions.services import apply_condition
from world.magic.factories import CharacterAnimaFactory
from world.mechanics.factories import (
    AerialPropertyFactory,
    CharacterEngagementFactory,
    ModifierCategoryFactory,
)
from world.mechanics.models import CharacterModifier, ModifierSource, ModifierTarget
from world.scenes.constants import RoundStatus
from world.seeds.checks import seed_check_resolution_tables
from world.vitals.models import CharacterVitals
from world.vitals.seeds import ensure_foundational_capabilities, ensure_unconscious_condition
from world.vitals.services import can_act

FULL_HEALTH = 100
BITE = 10
EXTRA_MOVEMENT = 10  # baseline 5 + 10 = 15 movement = 3 hops a round
CAPABILITY_RAISE = 3
STOPPED_BY = "You are stopped by {name}."
HELD_BY = "Held by {name}: you'd stop there."
NO_MOVEMENT_LEFT = "You have no movement left this round."


def _full_strength(*args: object, **kwargs: object) -> MagicMock:
    """A defence roll at success level 0, which takes the blow at full strength."""
    return MagicMock(success_level=0)


def _clean_hit(*args: object, **kwargs: object) -> MagicMock:
    """An offence roll at success level 2, which lands a PC's strike."""
    return MagicMock(success_level=2)


class _TheCauseway(JourneyCase):
    """Lane - Gate - Yard - Hall - Tower, open edges, and a fight in DECLARING round 1."""

    def setUp(self) -> None:
        super().setUp()
        seed_check_resolution_tables()
        with override_settings(SEED_SAMPLE_CONTENT=True):  # movement and awareness
            ensure_foundational_capabilities()
        AerialPropertyFactory()
        OpponentTierTemplateFactory(tier=OpponentTier.MOOK, base_health=30, base_soak=0)
        self.flight = CapabilityTypeFactory(
            name="winged flight", innate_baseline=0, traversal=CreatureTraversal.FLIES
        )
        self.room = self.make_room("The Causeway")
        self.lane = PositionFactory(room=self.room, name="Lane")
        self.gate = PositionFactory(room=self.room, name="Gate")
        self.yard = PositionFactory(room=self.room, name="Yard")
        self.hall = PositionFactory(room=self.room, name="Hall")
        self.tower = PositionFactory(room=self.room, name="Tower")
        connect_positions(self.lane, self.gate)
        connect_positions(self.gate, self.yard)
        connect_positions(self.yard, self.hall)
        connect_positions(self.hall, self.tower)
        self.encounter = CombatEncounterFactory(
            status=RoundStatus.DECLARING, round_number=1, room=self.room
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

    def fighter(self, name: str, *, at, flies: bool = False):
        character = self.make_player(name, room=self.room)
        sheet = character.sheet_data
        CharacterVitals.objects.create(
            character_sheet=sheet, health=FULL_HEALTH, max_health=FULL_HEALTH, base_max_health=100
        )
        CharacterAnimaFactory(character=sheet, current=20, maximum=20)
        CharacterEngagementFactory(character=sheet)
        CombatParticipantFactory(
            encounter=self.encounter, character_sheet=sheet, status=ParticipantStatus.ACTIVE
        )
        movement = CapabilityType.objects.get(name=FoundationalCapability.MOVEMENT)
        self.raise_capability(character, movement, EXTRA_MOVEMENT)
        if flies:
            self.raise_capability(character, self.flight, CAPABILITY_RAISE)
        place_in_position(character, at)
        return character

    def creature(
        self, name: str, *, at, hops: int = 1, traversal: str = CreatureTraversal.WALKS
    ) -> CombatOpponent:
        """An enemy spawned from its bestiary entry at ``at``, with one bite of 10."""
        pool = ThreatPoolFactory(name=f"{name} attacks")
        ThreatPoolEntryFactory(
            pool=pool,
            name=f"{name} strike",
            base_damage=BITE,
            delivery=StrikeDelivery.MELEE,
            targeting_mode=TargetingMode.SINGLE,
            target_selection=TargetSelection.HIGHEST_THREAT,
        )
        template = CreatureTemplateFactory(
            name=name,
            tier=OpponentTier.MOOK,
            threat_pool=pool,
            speed_hops=hops,
            traversal=traversal,
        )
        return spawn_from_creature_template(self.encounter, template, position=at)

    def participant(self, character) -> CombatParticipant:
        return CombatParticipant.objects.get(
            encounter=self.encounter, character_sheet=character.sheet_data
        )

    def resolve(self) -> None:
        resolve_round(self.encounter, defense_check_fn=_full_strength, offense_check_fn=_clean_hit)


class AWalkerStopsInHeldGround(_TheCauseway):
    def test_walker_entering_held_ground_stops(self) -> None:
        self.creature("Bandit", at=self.yard)
        kit = self.fighter("Kit", at=self.gate)

        result = self.web(kit, "move_to_position", position_id=self.yard.pk)

        self.assertTrue(result.detail.success, result.detail.message)
        self.assertIn("stopped", result.detail.message)
        self.assertIn(STOPPED_BY.format(name="Bandit"), result.detail.message)
        self.assertEqual(position_of(kit), self.yard)
        self.assertEqual(hops_left(self.participant(kit)), 0)

        onward = self.web(kit, "move_to_position", position_id=self.hall.pk)

        self.assertFalse(onward.detail.success)
        self.assertEqual(position_of(kit), self.yard)

    def test_defeated_or_unconscious_holder_holds_nothing(self) -> None:
        bandit = self.creature("Bandit", at=self.yard)
        bandit.status = OpponentStatus.DEFEATED
        bandit.save(update_fields=["status"])
        kit = self.fighter("Kit", at=self.gate)

        result = self.web(kit, "move_to_position", position_id=self.yard.pk)

        self.assertTrue(result.detail.success, result.detail.message)
        self.assertNotIn("stopped", result.detail.message or "")
        self.assertEqual(position_of(kit), self.yard)
        self.assertEqual(self.participant(kit).hops_used, 1)
        self.assertEqual(hops_left(self.participant(kit)), 2)

    def test_starting_in_held_ground_can_leave(self) -> None:
        self.creature("Bandit", at=self.yard)
        kit = self.fighter("Kit", at=self.yard)

        result = self.web(kit, "move_to_position", position_id=self.hall.pk)

        self.assertTrue(result.detail.success, result.detail.message)
        self.assertEqual(position_of(kit), self.hall)
        self.assertEqual(self.participant(kit).hops_used, 1)

    def test_aerial_mover_is_not_stopped(self) -> None:
        self.creature("Bandit", at=self.yard)
        kit = self.fighter("Kit", at=self.gate, flies=True)
        self.telnet(kit, "position/fly")
        above_yard = self.room.positions.get(kind=PositionKind.AERIAL, elevation_anchor=self.yard)

        result = self.web(kit, "move_to_position", position_id=above_yard.pk)

        self.assertTrue(result.detail.success, result.detail.message)
        self.assertNotIn("stopped", result.detail.message or "")
        self.assertEqual(position_of(kit), above_yard)
        self.assertEqual(self.participant(kit).hops_used, 2)

    def test_move_list_marks_held_places(self) -> None:
        self.creature("Bandit", at=self.yard)
        kit = self.fighter("Kit", at=self.gate)

        moves = {action.display_name: action for action in get_player_actions(kit)}

        self.assertEqual(moves["Move to Yard"].description, HELD_BY.format(name="Bandit"))
        self.assertNotEqual(moves["Move to Lane"].description, HELD_BY.format(name="Bandit"))


class AnNpcStopsInHeldGround(_TheCauseway):
    """A wolf at the Tower goes for Wren at the Lane; Hobb stands in the Yard between."""

    def setUp(self) -> None:
        super().setUp()
        self.hobb = self.fighter("Hobb", at=self.yard)
        self.wren = self.fighter("Wren", at=self.lane)

    def wolf_going_for_wren(self, traversal: str) -> CombatOpponent:
        wolf = self.creature("Grey Wolf", at=self.tower, hops=3, traversal=traversal)
        bite = CombatOpponentAction.objects.create(
            opponent=wolf, round_number=1, threat_entry=wolf.threat_pool.entries.get()
        )
        bite.targets.set([self.participant(self.wren)])
        return wolf

    def test_npc_walker_stops_at_a_pc_holding_the_way(self) -> None:
        wolf = self.wolf_going_for_wren(CreatureTraversal.WALKS)

        self.resolve()

        self.assertEqual(position_of(wolf.objectdb), self.yard)

    def test_npc_leaper_passes_held_ground(self) -> None:
        wolf = self.wolf_going_for_wren(CreatureTraversal.LEAPS)

        self.resolve()

        self.assertEqual(position_of(wolf.objectdb), self.gate)

    def test_an_unconscious_pc_holds_nothing(self) -> None:
        with override_settings(SEED_SAMPLE_CONTENT=True):
            unconscious = ensure_unconscious_condition()
        apply_condition(self.hobb, unconscious)
        self.assertFalse(can_act(self.hobb.sheet_data))
        wolf = self.wolf_going_for_wren(CreatureTraversal.WALKS)

        self.resolve()

        self.assertEqual(position_of(wolf.objectdb), self.gate)
