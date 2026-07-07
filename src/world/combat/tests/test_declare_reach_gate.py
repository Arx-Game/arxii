"""Tests for Task 4 / #533: technique reach gate at declare_action time.

Verifies that declare_action raises ActionDispatchError when a technique's
reach requirement cannot be satisfied by the combatants' current positions,
and that the dispatch endpoint surfaces this as HTTP 400.

Uses setUp (not setUpTestData) because factories create Evennia ObjectDB
instances (DbHolder — not deepcopyable, which breaks setUpTestData).
"""

from __future__ import annotations

from django.test import TestCase
from rest_framework import status as http_status
from rest_framework.test import APIClient

from actions.errors import ActionDispatchError
from evennia_extensions.factories import AccountFactory
from world.areas.positioning.services import (
    connect_positions,
    create_position,
    place_in_position,
)
from world.combat.constants import ActionCategory
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
)
from world.combat.services import declare_action
from world.fatigue.constants import EffortLevel
from world.magic.constants import TechniqueReach
from world.magic.factories import EffectTypeFactory, GiftFactory, TechniqueFactory
from world.roster.factories import RosterTenureFactory
from world.scenes.constants import RoundStatus
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
            status=RoundStatus.DECLARING, round_number=1, room=self.room
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
        with self.assertRaises(ActionDispatchError) as cm:
            declare_action(
                self.participant,
                focused_action=technique,
                focused_category=ActionCategory.PHYSICAL,
                effort_level=EffortLevel.MEDIUM,
                focused_opponent_target=self.opponent,
            )
        self.assertEqual(cm.exception.code, ActionDispatchError.TARGET_OUT_OF_REACH)
        self.assertIn("out of reach", cm.exception.user_message)

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

        self.encounter = CombatEncounterFactory(status=RoundStatus.DECLARING, round_number=1)
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


class DeclareActionReachGateSpawnedOpponentJourneyTests(TestCase):
    """Journey payoff (#2005): reach gating binds for real combatants placed at
    spawn time via ``add_opponent(position=...)`` — not just objects placed
    after the fact via ``place_in_position``.
    """

    def setUp(self) -> None:
        from evennia import create_object

        self.room = create_object("typeclasses.rooms.Room", key="JourneyRoom", nohome=True)
        self.pos_a = create_position(self.room, "journey_pos_a")
        self.pos_b = create_position(self.room, "journey_pos_b")
        self.pos_c = create_position(self.room, "journey_pos_c")
        connect_positions(self.pos_a, self.pos_b, is_passable=True)
        # pos_c is deliberately left unconnected to pos_a (non-adjacent).

        self.effect_type = EffectTypeFactory(name="JourneyAtk", base_power=20)
        self.gift = GiftFactory()

        self.encounter = CombatEncounterFactory(
            status=RoundStatus.DECLARING, round_number=1, room=self.room
        )
        self.participant = CombatParticipantFactory(encounter=self.encounter)
        _wire_vitals(self.participant)

        # PC placed at position A.
        self.attacker_objectdb = self.participant.character_sheet.character
        self.attacker_objectdb.move_to(self.room, quiet=True)
        place_in_position(self.attacker_objectdb, self.pos_a)

        self.technique = TechniqueFactory(
            gift=self.gift,
            effect_type=self.effect_type,
            action_category=ActionCategory.PHYSICAL,
            reach=TechniqueReach.ADJACENT,
        )

    def test_opponent_spawned_non_adjacent_is_out_of_reach(self) -> None:
        """Opponent spawned at C (non-adjacent to A) is out of reach for ADJACENT."""
        from world.combat.factories import ThreatPoolFactory
        from world.combat.services import add_opponent

        pool = ThreatPoolFactory()
        opponent = add_opponent(
            self.encounter,
            name="Journey Foe (far)",
            tier="mook",
            max_health=20,
            threat_pool=pool,
            position=self.pos_c,
        )

        with self.assertRaises(ActionDispatchError) as cm:
            declare_action(
                self.participant,
                focused_action=self.technique,
                focused_category=ActionCategory.PHYSICAL,
                effort_level=EffortLevel.MEDIUM,
                focused_opponent_target=opponent,
            )
        self.assertEqual(cm.exception.code, ActionDispatchError.TARGET_OUT_OF_REACH)

    def test_opponent_spawned_adjacent_is_accepted(self) -> None:
        """Opponent spawned at B (adjacent to A) is accepted for ADJACENT reach."""
        from world.combat.factories import ThreatPoolFactory
        from world.combat.services import add_opponent

        pool = ThreatPoolFactory()
        opponent = add_opponent(
            self.encounter,
            name="Journey Foe (near)",
            tier="mook",
            max_health=20,
            threat_pool=pool,
            position=self.pos_b,
        )

        action = declare_action(
            self.participant,
            focused_action=self.technique,
            focused_category=ActionCategory.PHYSICAL,
            effort_level=EffortLevel.MEDIUM,
            focused_opponent_target=opponent,
        )
        self.assertEqual(action.focused_opponent_target, opponent)


class DispatchOutOfReachReturns400Tests(TestCase):
    """DispatchActionView returns HTTP 400 when technique reach is violated.

    Verifies the view's error-handling boundary: ``ActionDispatchError`` with
    ``TARGET_OUT_OF_REACH`` must surface as HTTP 400 with the user message.
    ``dispatch_player_action`` is mocked so the test focuses purely on the
    view's try/except path rather than the full combat round setup.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        from evennia.objects.models import ObjectDB

        cls.account = AccountFactory()
        cls.character = ObjectDB.objects.create(db_key="ReachDispatchChar")
        cls.tenure = RosterTenureFactory(
            roster_entry__character_sheet__character=cls.character,
            player_data__account=cls.account,
        )

    def setUp(self) -> None:
        self.client = APIClient()
        self.client.force_authenticate(user=self.account)

    def _url(self) -> str:
        return f"/api/actions/characters/{self.character.pk}/dispatch/"

    def test_out_of_reach_dispatch_returns_400(self) -> None:
        """When dispatch raises TARGET_OUT_OF_REACH, the view returns HTTP 400."""
        from unittest.mock import patch

        payload = {
            "ref": {
                "backend": "combat",
                "technique_id": 1,
            },
            "kwargs": {
                "effort_level": EffortLevel.MEDIUM,
            },
        }
        with patch(
            "actions.views.dispatch_player_action",
            side_effect=ActionDispatchError(ActionDispatchError.TARGET_OUT_OF_REACH),
        ):
            response = self.client.post(self._url(), payload, format="json")
        self.assertEqual(response.status_code, http_status.HTTP_400_BAD_REQUEST)
        detail = response.json().get("detail", "")
        self.assertIn("out of reach", detail)
