"""Telnet journey tests for CmdDuel — the full duel lifecycle over the seam (#1492).

Drives ``CmdDuel.func()`` end-to-end with real characters through
``dispatch_player_action`` (the same REGISTRY seam the web uses), asserting the
DB-state outcome of each verb rather than mocking. Proves the telnet command
reaches each already-built duel Action:

  - ``duel challenge <name>`` → PENDING DuelChallenge
  - ``duel accept``           → ACCEPTED + linked CombatEncounter
  - ``duel decline``          → DECLINED, no encounter
  - ``duel withdraw``         → WITHDRAWN, no encounter
  - ``duel risk`` (lethal)    → EncounterRiskAcknowledgement recorded

ObjectDB rows live in setUp (not deepcopy-safe) with ``idmapper.flush_cache()``
to avoid idmapper contamination between tests — mirroring
``world/combat/tests/test_duels_integration.py``.
"""

from __future__ import annotations

from typing import Any

from django.test import TestCase
from evennia.utils import idmapper

from commands.duels import CmdDuel
from evennia_extensions.factories import CharacterFactory, ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.combat.constants import DuelChallengeStatus
from world.combat.duels import create_lethal_duel
from world.combat.factories import ThreatPoolFactory
from world.combat.models import CombatEncounter, DuelChallenge, EncounterRiskAcknowledgement
from world.roster.factories import RosterEntryFactory, RosterTenureFactory


def _make_room(name: str = "Arena") -> Any:
    return ObjectDBFactory(db_key=name, db_typeclass_path="typeclasses.rooms.Room")


def _make_pc(name: str, room: Any) -> tuple[Any, Any]:
    """Return (character ObjectDB, CharacterSheet) with an active RosterTenure.

    The tenure chain is required for the challenge consent gate to resolve.
    """
    actor = CharacterFactory(db_key=name, location=room)
    sheet = CharacterSheetFactory(character=actor)
    entry = RosterEntryFactory(character_sheet=sheet)
    RosterTenureFactory(roster_entry=entry)
    return actor, sheet


def _run(caller: Any, args: str) -> CmdDuel:
    """Construct and execute ``duel <args>`` as *caller* would over telnet."""
    cmd = CmdDuel()
    cmd.caller = caller
    cmd.args = args
    cmd.raw_string = f"duel {args}".strip()
    cmd.cmdname = "duel"
    cmd.func()
    return cmd


class CmdDuelJourneyTests(TestCase):
    def setUp(self) -> None:
        idmapper.models.flush_cache()
        self.room = _make_room()
        self.challenger, self.challenger_sheet = _make_pc("Challenger", self.room)
        self.target, self.target_sheet = _make_pc("Target", self.room)

    def _challenge(self) -> DuelChallenge:
        _run(self.challenger, "challenge Target")
        challenge = DuelChallenge.objects.filter(
            challenger_sheet=self.challenger_sheet,
            challenged_sheet=self.target_sheet,
            status=DuelChallengeStatus.PENDING,
        ).first()
        self.assertIsNotNone(challenge, "duel challenge should create a PENDING DuelChallenge")
        return challenge

    def test_challenge_creates_pending_challenge(self) -> None:
        self._challenge()

    def test_accept_creates_linked_encounter(self) -> None:
        challenge = self._challenge()

        _run(self.target, "accept")

        challenge.refresh_from_db()
        self.assertEqual(challenge.status, DuelChallengeStatus.ACCEPTED)
        self.assertIsNotNone(challenge.resulting_encounter, "accept should link an encounter")
        self.assertEqual(CombatEncounter.objects.count(), 1)

    def test_decline_terminates_without_encounter(self) -> None:
        challenge = self._challenge()

        _run(self.target, "decline")

        challenge.refresh_from_db()
        self.assertEqual(challenge.status, DuelChallengeStatus.DECLINED)
        self.assertFalse(CombatEncounter.objects.exists())

    def test_withdraw_terminates_without_encounter(self) -> None:
        challenge = self._challenge()

        _run(self.challenger, "withdraw")

        challenge.refresh_from_db()
        self.assertEqual(challenge.status, DuelChallengeStatus.WITHDRAWN)
        self.assertFalse(CombatEncounter.objects.exists())

    def test_risk_in_lethal_duel_records_acknowledgement(self) -> None:
        encounter = create_lethal_duel(
            self.challenger_sheet,
            {"name": "Ogre", "max_health": 30, "threat_pool": ThreatPoolFactory()},
            self.room,
        )
        self.assertFalse(EncounterRiskAcknowledgement.objects.filter(encounter=encounter).exists())

        _run(self.challenger, "risk")

        self.assertTrue(
            EncounterRiskAcknowledgement.objects.filter(
                encounter=encounter,
                character_sheet=self.challenger_sheet,
            ).exists(),
            "duel risk should record the PC's lethal-risk acknowledgement",
        )
