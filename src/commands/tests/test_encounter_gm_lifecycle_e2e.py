"""E2E telnet journey: GM combat encounter lifecycle (#1494).

Drives the full encounter command path through begin, add, resolve, pause,
and end, asserting both DB state and caller messages.

SQLite-compatible.
DbHolder trap: all Evennia ObjectDB instances live in setUp, never setUpTestData.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import TestCase

from commands.encounter import CmdEncounter
from evennia_extensions.factories import AccountFactory, CharacterFactory, ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.combat.constants import (
    EncounterOutcome,
    OpponentTier,
    ParticipantStatus,
    RiskLevel,
    StakesLevel,
)
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
    ThreatPoolFactory,
    seed_scaling_defaults,
)
from world.combat.models import CombatOpponent
from world.roster.factories import RosterEntryFactory, RosterTenureFactory
from world.scenes.constants import RoundStatus
from world.scenes.factories import SceneFactory, SceneParticipationFactory

_BROADCAST_PATH = "world.combat.services._broadcast_encounter_outcome"


def _create_room():
    return ObjectDBFactory(
        db_key="EncounterJourneyRoom",
        db_typeclass_path="typeclasses.rooms.Room",
    )


def _create_pc_with_account(db_key: str, room=None, is_staff: bool = False):
    """Create a PC character in *room* with a live roster tenure.

    Returns (character, account, character_sheet).
    """
    account = AccountFactory(username=f"e2e_{db_key.lower()}", is_staff=is_staff)
    kwargs = {"db_key": db_key}
    if room is not None:
        kwargs["location"] = room
    char = CharacterFactory(**kwargs)
    sheet = CharacterSheetFactory(character=char)
    entry = RosterEntryFactory(character_sheet=sheet)
    RosterTenureFactory(
        roster_entry=entry,
        player_data__account=account,
        end_date=None,
    )
    return char, account, sheet


def _run_cmd(caller, args: str) -> list[str]:
    """Invoke CmdEncounter with *args* and return all messages sent to caller."""
    caller.msg = MagicMock()
    cmd = CmdEncounter()
    cmd.caller = caller
    cmd.args = args
    cmd.raw_string = f"encounter {args}".strip()
    cmd.func()
    return [str(call.args[0]) for call in caller.msg.call_args_list if call.args]


class EncounterGMLifecycleE2ETest(TestCase):
    """Full telnet journey for the GM encounter lifecycle."""

    def setUp(self) -> None:
        # DbHolder trap: build all Evennia objects in setUp, never setUpTestData.
        self.room = _create_room()

        # GM character (staff) and one PC participant.
        self.gm_actor, self.gm_account, _ = _create_pc_with_account(
            "JourneyGM",
            room=self.room,
            is_staff=True,
        )
        self.player_actor, self.player_account, self.player_sheet = _create_pc_with_account(
            "JourneyPlayer",
            room=self.room,
        )

        # Active scene in the room with the GM flagged as GM and player as participant.
        self.scene = SceneFactory(location=self.room, is_active=True)
        SceneParticipationFactory(scene=self.scene, account=self.gm_account, is_gm=True)
        SceneParticipationFactory(scene=self.scene, account=self.player_account)

        # Active encounter with one opponent so ``begin`` can advance.
        self.encounter = CombatEncounterFactory(
            room=self.room,
            scene=self.scene,
            status=RoundStatus.BETWEEN_ROUNDS,
            round_number=0,
            risk_level=RiskLevel.MODERATE,
            stakes_level=StakesLevel.LOCAL,
        )
        self.initial_opponent = CombatOpponentFactory(
            encounter=self.encounter,
            name="Grunt",
            tier=OpponentTier.MOOK,
        )
        self.participant = CombatParticipantFactory(
            encounter=self.encounter,
            character_sheet=self.player_sheet,
            status=ParticipantStatus.ACTIVE,
        )
        from world.vitals.models import CharacterVitals

        CharacterVitals.objects.get_or_create(
            character_sheet=self.player_sheet,
            defaults={
                "health": 50,
                "max_health": 50,
                "base_max_health": 50,
            },
        )

        # Seeded scaling config + a named threat pool for ``encounter add``.
        seed_scaling_defaults()
        self.threat_pool = ThreatPoolFactory(name="soldiers")

    def test_full_gm_encounter_lifecycle(self) -> None:
        """Run the encounter lifecycle through the telnet command seam."""
        # ---- Step 1: begin -> DECLARING ---------------------------------
        msgs = _run_cmd(self.gm_actor, "begin")
        self.assertIn("round begins", " ".join(msgs).lower())

        self.encounter.refresh_from_db()
        self.assertEqual(self.encounter.status, RoundStatus.DECLARING)
        self.assertEqual(self.encounter.round_number, 1)

        # ---- Step 2: add a second opponent -------------------------------
        msgs = _run_cmd(
            self.gm_actor,
            f"add Soldier {OpponentTier.MOOK} {self.threat_pool.name}",
        )
        self.assertIn("opponent 'soldier' added", " ".join(msgs).lower())

        added = CombatOpponent.objects.filter(encounter=self.encounter, name="Soldier").first()
        self.assertIsNotNone(added)
        self.assertEqual(added.tier, OpponentTier.MOOK)
        self.assertEqual(added.threat_pool_id, self.threat_pool.pk)

        # ---- Step 3: resolve -> BETWEEN_ROUNDS or COMPLETED --------------
        with patch(_BROADCAST_PATH):
            msgs = _run_cmd(self.gm_actor, "resolve")
        self.assertIn("the round resolves", " ".join(msgs).lower())

        self.encounter.refresh_from_db()
        self.assertIn(
            self.encounter.status,
            {RoundStatus.BETWEEN_ROUNDS, RoundStatus.COMPLETED},
            f"Unexpected status after resolve: {self.encounter.status}",
        )

        # The easy scenario should always return to BETWEEN_ROUNDS.
        self.assertEqual(
            self.encounter.status,
            RoundStatus.BETWEEN_ROUNDS,
            f"Expected BETWEEN_ROUNDS after resolve; got {self.encounter.status}",
        )

        # ---- Step 4: pause toggles --------------------------------------
        msgs = _run_cmd(self.gm_actor, "pause")
        self.assertIn("encounter paused", " ".join(msgs).lower())
        self.encounter.refresh_from_db()
        self.assertTrue(self.encounter.is_paused)

        msgs = _run_cmd(self.gm_actor, "pause")
        self.assertIn("encounter resumed", " ".join(msgs).lower())
        self.encounter.refresh_from_db()
        self.assertFalse(self.encounter.is_paused)

        # ---- Step 5: end -> COMPLETED ABANDONED ------------------------
        with patch(_BROADCAST_PATH):
            msgs = _run_cmd(self.gm_actor, "end")
        self.assertIn("encounter ended", " ".join(msgs).lower())

        self.encounter.refresh_from_db()
        self.assertEqual(self.encounter.status, RoundStatus.COMPLETED)
        self.assertEqual(self.encounter.outcome, EncounterOutcome.ABANDONED)
