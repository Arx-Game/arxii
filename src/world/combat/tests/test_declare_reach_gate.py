"""Tests for Task 4 / #533: technique reach gate at declare_action time.

Verifies that declare_action raises ValueError when a technique's reach
requirement cannot be satisfied by the combatants' current positions.

Uses setUp (not setUpTestData) because factories create Evennia ObjectDB
instances (DbHolder — not deepcopyable, which breaks setUpTestData).
"""

from __future__ import annotations

from django.test import TestCase

from world.areas.positioning.services import (
    connect_positions,
    create_position,
    place_in_position,
)
from world.combat.constants import ActionCategory, EncounterStatus
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
)
from world.combat.services import declare_action
from world.fatigue.constants import EffortLevel
from world.magic.constants import TechniqueReach
from world.magic.factories import EffectTypeFactory, GiftFactory, TechniqueFactory
from world.vitals.models import CharacterVitals


def _wire_vitals(participant) -> None:
    """Ensure the participant has ALIVE CharacterVitals (required by declare_action)."""
    CharacterVitals.objects.get_or_create(
        character_sheet=participant.character_sheet,
        defaults={"health": 100, "max_health": 100},
    )


class DeclareActionReachGateOpponentTests(TestCase):
    """Reach gate: attacker vs opponent target in different positions."""

    def setUp(self) -> None:
        from evennia import create_object
        from evennia.objects.models import ObjectDB

        # Create a room with two connected positions.
        self.room = create_object("typeclasses.rooms.Room", key="ReachGateRoom", nohome=True)
        self.pos_a = create_position(self.room, "gate_pos_a")
        self.pos_b = create_position(self.room, "gate_pos_b")
        connect_positions(self.pos_a, self.pos_b, is_passable=True)

        # Shared effect type + gift for all techniques.
        self.effect_type = EffectTypeFactory(name="ReachGateAtk", base_power=20)
        self.gift = GiftFactory()

        # Create encounter and participant. Use the same room so that
        # CombatOpponentFactory places its ephemeral NPC there too.
        self.encounter = CombatEncounterFactory(
            status=EncounterStatus.DECLARING, round_number=1, room=self.room
        )
        self.participant = CombatParticipantFactory(encounter=self.encounter)
        _wire_vitals(self.participant)

        # Move the attacker's ObjectDB into the room (characters start in limbo).
        self.attacker_objectdb = self.participant.character_sheet.character
        self.attacker_objectdb.move_to(self.room, quiet=True)
        place_in_position(self.attacker_objectdb, self.pos_a)

        # Create an opponent whose ObjectDB is placed in pos_b.
        # CombatOpponentFactory creates an ephemeral CombatNPC in the encounter's room;
        # fetch the ObjectDB by PK (factory stores objectdb_id to avoid DbHolder caching).
        self.opponent = CombatOpponentFactory(encounter=self.encounter)
        opponent_objectdb = ObjectDB.objects.get(pk=self.opponent.objectdb_id)
        place_in_position(opponent_objectdb, self.pos_b)

    def test_same_reach_against_adjacent_opponent_raises(self) -> None:
        """Technique with reach=SAME cannot target opponent in a different position."""
        technique = TechniqueFactory(
            gift=self.gift,
            effect_type=self.effect_type,
            action_category=ActionCategory.PHYSICAL,
            reach=TechniqueReach.SAME,
        )
        with self.assertRaisesRegex(ValueError, "[Rr]each|out of reach"):
            declare_action(
                self.participant,
                focused_action=technique,
                focused_category=ActionCategory.PHYSICAL,
                effort_level=EffortLevel.MEDIUM,
                focused_opponent_target=self.opponent,
            )

    def test_any_reach_against_adjacent_opponent_succeeds(self) -> None:
        """Technique with reach=ANY can target opponent in any position."""
        technique = TechniqueFactory(
            gift=self.gift,
            effect_type=self.effect_type,
            action_category=ActionCategory.PHYSICAL,
            reach=TechniqueReach.ANY,
        )
        # Should not raise.
        action = declare_action(
            self.participant,
            focused_action=technique,
            focused_category=ActionCategory.PHYSICAL,
            effort_level=EffortLevel.MEDIUM,
            focused_opponent_target=self.opponent,
        )
        self.assertEqual(action.focused_opponent_target, self.opponent)

    def test_adjacent_reach_against_adjacent_opponent_succeeds(self) -> None:
        """Technique with reach=ADJACENT succeeds against opponent in an adjacent position."""
        technique = TechniqueFactory(
            gift=self.gift,
            effect_type=self.effect_type,
            action_category=ActionCategory.PHYSICAL,
            reach=TechniqueReach.ADJACENT,
        )
        action = declare_action(
            self.participant,
            focused_action=technique,
            focused_category=ActionCategory.PHYSICAL,
            effort_level=EffortLevel.MEDIUM,
            focused_opponent_target=self.opponent,
        )
        self.assertEqual(action.focused_opponent_target, self.opponent)


class DeclareActionReachGateLenientTests(TestCase):
    """Reach gate is lenient (no block) when either combatant is unpositioned."""

    def setUp(self) -> None:
        self.effect_type = EffectTypeFactory(name="LenientAtk", base_power=20)
        self.gift = GiftFactory()

        self.encounter = CombatEncounterFactory(status=EncounterStatus.DECLARING, round_number=1)
        self.participant = CombatParticipantFactory(encounter=self.encounter)
        _wire_vitals(self.participant)

        # Opponent is created but NEITHER combatant is placed in any position.
        self.opponent = CombatOpponentFactory(encounter=self.encounter)

    def test_same_reach_without_positioning_does_not_raise(self) -> None:
        """When combatants are unpositioned, reach=SAME should not block."""
        technique = TechniqueFactory(
            gift=self.gift,
            effect_type=self.effect_type,
            action_category=ActionCategory.PHYSICAL,
            reach=TechniqueReach.SAME,
        )
        action = declare_action(
            self.participant,
            focused_action=technique,
            focused_category=ActionCategory.PHYSICAL,
            effort_level=EffortLevel.MEDIUM,
            focused_opponent_target=self.opponent,
        )
        self.assertEqual(action.focused_opponent_target, self.opponent)
