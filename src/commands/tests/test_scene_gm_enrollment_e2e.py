"""E2E telnet journey: auto-enrollment of a table-owning GM's scene GM flag (#2113).

Before this fix, ``SceneParticipation.is_gm`` was only ever written by the crossover
lead-GM path — an ordinary trust-tier GM running their own table's session never
got flagged, so every GM-combat surface (``_actor_may_gm_encounter``,
``IsEncounterGMOrStaff``, effect visibility) silently refused them. These tests
drive the real telnet path (``scene start`` -> ``encounter begin``/``encounter add``)
to prove the auto-enrollment now unblocks a non-staff table GM, and that a GM with
no present table member is correctly left unflagged.

SQLite-compatible.
DbHolder trap: all Evennia ObjectDB instances live in setUp, never setUpTestData.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from django.test import TestCase

from actions.definitions.gm_combat import _actor_may_gm_encounter
from commands.encounter import CmdEncounter
from commands.scene import CmdScene
from evennia_extensions.factories import AccountFactory, CharacterFactory, ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.combat.constants import OpponentTier
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
    ThreatPoolFactory,
    seed_scaling_defaults,
)
from world.combat.models import CombatOpponent
from world.gm.constants import GMTableStatus
from world.gm.factories import GMProfileFactory, GMTableFactory, GMTableMembershipFactory
from world.roster.factories import RosterEntryFactory, RosterTenureFactory
from world.scenes.models import Scene, SceneParticipation


def _create_room(label: str) -> object:
    return ObjectDBFactory(db_key=label, db_typeclass_path="typeclasses.rooms.Room")


def _create_pc_with_account(db_key: str, room=None):
    """Create a PC character in *room* with a live roster tenure.

    Returns (character, account, character_sheet).
    """
    account = AccountFactory(username=f"gme2e_{db_key.lower()}")
    kwargs = {"db_key": db_key}
    if room is not None:
        kwargs["location"] = room
    char = CharacterFactory(**kwargs)
    sheet = CharacterSheetFactory(character=char)
    entry = RosterEntryFactory(character_sheet=sheet)
    RosterTenureFactory(roster_entry=entry, player_data__account=account, end_date=None)
    return char, account, sheet


def _run_scene_cmd(caller, args: str) -> list[str]:
    caller.msg = MagicMock()
    cmd = CmdScene()
    cmd.caller = caller
    cmd.args = args
    cmd.raw_string = f"scene {args}".strip()
    cmd.func()
    return [str(c.args[0]) for c in caller.msg.call_args_list if c.args]


def _run_encounter_cmd(caller, args: str) -> list[str]:
    caller.msg = MagicMock()
    cmd = CmdEncounter()
    cmd.caller = caller
    cmd.args = args
    cmd.raw_string = f"encounter {args}".strip()
    cmd.func()
    return [str(c.args[0]) for c in caller.msg.call_args_list if c.args]


class TableOwningGMAutoEnrollmentJourneyTest(TestCase):
    """A table-owning GM with a present table member gets is_gm=True at scene start."""

    def setUp(self) -> None:
        self.room = _create_room("TableGMRoom")
        self.gm_actor, self.gm_account, self.gm_sheet = _create_pc_with_account(
            "TableGM", room=self.room
        )
        self.player_actor, self.player_account, self.player_sheet = _create_pc_with_account(
            "TablePlayer", room=self.room
        )
        self.profile = GMProfileFactory(account=self.gm_account)
        self.table = GMTableFactory(gm=self.profile, status=GMTableStatus.ACTIVE)
        GMTableMembershipFactory(table=self.table, persona=self.player_sheet.primary_persona)

    def test_scene_start_flags_table_owning_gm(self) -> None:
        """``scene start`` auto-flags the table-owning GM's participation."""
        _run_scene_cmd(self.gm_actor, "start")

        scene = Scene.objects.get(location=self.room, is_active=True)
        self.assertTrue(
            SceneParticipation.objects.filter(
                scene=scene, account=self.gm_account, is_gm=True
            ).exists()
        )

    def test_actor_may_gm_encounter_passes_for_enrolled_gm(self) -> None:
        """The real permission gate combat surfaces use now passes (was the whole bug)."""
        _run_scene_cmd(self.gm_actor, "start")
        scene = Scene.objects.get(location=self.room, is_active=True)

        encounter = CombatEncounterFactory(room=self.room, scene=scene)

        self.assertTrue(_actor_may_gm_encounter(self.gm_actor, encounter))

    def test_encounter_begin_and_add_succeed_via_telnet(self) -> None:
        """``encounter begin`` and ``encounter add`` succeed for the auto-enrolled GM."""
        _run_scene_cmd(self.gm_actor, "start")
        scene = Scene.objects.get(location=self.room, is_active=True)

        seed_scaling_defaults()
        threat_pool = ThreatPoolFactory(name="soldiers")
        encounter = CombatEncounterFactory(room=self.room, scene=scene)
        # ``encounter begin`` requires at least one active opponent (mirrors
        # test_encounter_gm_lifecycle_e2e's seeded Grunt).
        CombatOpponentFactory(encounter=encounter, name="Grunt", tier=OpponentTier.MOOK)

        from world.vitals.models import CharacterVitals

        CharacterVitals.objects.get_or_create(
            character_sheet=self.player_sheet,
            defaults={"health": 50, "max_health": 50, "base_max_health": 50},
        )
        CombatParticipantFactory(encounter=encounter, character_sheet=self.player_sheet)

        msgs = _run_encounter_cmd(self.gm_actor, "begin")
        self.assertIn("round begins", " ".join(msgs).lower())

        msgs = _run_encounter_cmd(
            self.gm_actor,
            f"add Soldier {OpponentTier.MOOK} {threat_pool.name}",
        )
        self.assertIn("opponent 'soldier' added", " ".join(msgs).lower())
        self.assertTrue(CombatOpponent.objects.filter(encounter=encounter, name="Soldier").exists())


class GMAloneInStrangersRoomTest(TestCase):
    """A GM with an active table but no present table member is NOT flagged (#2113)."""

    def setUp(self) -> None:
        self.room = _create_room("StrangerRoom")
        self.gm_actor, self.gm_account, self.gm_sheet = _create_pc_with_account(
            "PassingGM", room=self.room
        )
        self.stranger_actor, self.stranger_account, self.stranger_sheet = _create_pc_with_account(
            "Stranger", room=self.room
        )
        self.profile = GMProfileFactory(account=self.gm_account)
        # Active table exists, but the stranger present is not a member of it.
        GMTableFactory(gm=self.profile, status=GMTableStatus.ACTIVE)

    def test_scene_start_does_not_flag_gm(self) -> None:
        """``scene start`` leaves the GM's participation is_gm=False."""
        _run_scene_cmd(self.gm_actor, "start")

        scene = Scene.objects.get(location=self.room, is_active=True)
        self.assertFalse(
            SceneParticipation.objects.filter(
                scene=scene, account=self.gm_account, is_gm=True
            ).exists()
        )

    def test_actor_may_gm_encounter_still_refuses(self) -> None:
        """Combat-GM permission stays refused — no member-present, no auto-grant."""
        _run_scene_cmd(self.gm_actor, "start")
        scene = Scene.objects.get(location=self.room, is_active=True)

        encounter = CombatEncounterFactory(room=self.room, scene=scene)

        self.assertFalse(_actor_may_gm_encounter(self.gm_actor, encounter))

    def test_encounter_begin_refused_via_telnet(self) -> None:
        """``encounter begin`` refuses the un-enrolled GM through the real telnet path."""
        _run_scene_cmd(self.gm_actor, "start")
        scene = Scene.objects.get(location=self.room, is_active=True)
        CombatEncounterFactory(room=self.room, scene=scene)

        msgs = _run_encounter_cmd(self.gm_actor, "begin")
        self.assertTrue(
            any("gm or staff" in m.lower() for m in msgs),
            f"Expected a permission-refusal message; got: {msgs}",
        )
