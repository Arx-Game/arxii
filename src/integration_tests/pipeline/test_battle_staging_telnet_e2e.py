"""Telnet E2E: GM battle-staging journey (#2010).

Drives create -> spawn -> enlist -> browse-catalog through ``CmdBattle``'s new
staging subverbs (``battle create``/``stage``/``spawn``/``enlist``/``maps``/
``units``), asserting DB state after each step and telnet feedback via
``caller.msg`` MagicMock — same command-harness pattern as
``test_battle_telnet_e2e.py``.

**Battle-resolution finding (carried from Task 3, settled empirically here):**
a battle created via ``stage_battle``/``CreateBattleAction`` is deliberately
location-less (ADR-0081) — ``Battle.save()`` always creates its backing Scene
with ``location=None``, and neither ``create_battle`` nor ``stage_battle``
take a location parameter. The existing ``battle round`` subverb
(``BeginBattleRoundAction`` -> ``_active_battle_in_room``) resolves "the
active battle" via ``Battle.objects.filter(scene__location=<actor's
room>, ...)`` — a query a location-less Scene can never satisfy. So ``battle
round`` cannot begin a round on a battle staged purely through this pipeline;
the journey below proves this rather than assuming it (see
``.superpowers/sdd/task-4-report.md`` for the full write-up). This task does
NOT add location wiring to close that gap — see the report for why.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from django.test import TestCase

from commands.battle import CmdBattle
from evennia_extensions.factories import CharacterFactory, ObjectDBFactory
from world.battles.constants import BattleParticipantStatus, BattleSideRole
from world.battles.factories import (
    BattleMapBlueprintFactory,
    BattleUnitTemplateCapabilityFactory,
    BattleUnitTemplateFactory,
    BlueprintBattlePlaceFactory,
)
from world.battles.models import Battle, BattleParticipant, BattlePlace, BattleSide, BattleUnit
from world.character_sheets.factories import CharacterSheetFactory
from world.conditions.factories import CapabilityTypeFactory
from world.gm.constants import GMLevel
from world.gm.factories import GMProfileFactory
from world.roster.factories import RosterEntryFactory, RosterTenureFactory

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _room(db_key: str = "StagingE2ERoom") -> object:
    """Create a Room ObjectDB in the identity map."""
    return ObjectDBFactory(db_key=db_key, db_typeclass_path="typeclasses.rooms.Room")


def _gm_in_room(room: object, *, db_key: str = "StagingGM") -> tuple[object, object]:
    """Create a JUNIOR-trust GM character standing in *room*.

    Returns (character, account). A live RosterTenure is required for
    ``actor.active_account`` (and therefore ``MinimumGMLevelPrerequisite``) to
    resolve at all.
    """
    char = CharacterFactory(db_key=db_key, location=room)
    sheet = CharacterSheetFactory(character=char)
    entry = RosterEntryFactory(character_sheet=sheet)
    tenure = RosterTenureFactory(roster_entry=entry, end_date=None)
    account = tenure.player_data.account
    GMProfileFactory(account=account, level=GMLevel.JUNIOR)
    return char, account


def _pc_in_room(room: object, *, db_key: str) -> tuple[object, object]:
    """Create a PC character with a sheet in *room*. Returns (character, sheet)."""
    char = CharacterFactory(db_key=db_key, location=room)
    sheet = CharacterSheetFactory(character=char)
    return char, sheet


def _run(caller: object, args: str = "") -> None:
    """Instantiate CmdBattle, wire caller/args, call func() immediately.

    Sets ``caller.msg`` to a fresh MagicMock before each call so the
    assertion site can inspect the single most-recent message.
    """
    cmd = CmdBattle()
    cmd.caller = caller
    cmd.args = args
    cmd.raw_string = f"battle {args}".strip()
    caller.msg = MagicMock()
    cmd.func()


# ---------------------------------------------------------------------------
# E2E journey
# ---------------------------------------------------------------------------


class BattleStagingTelnetE2EJourneyTest(TestCase):
    """create -> spawn -> enlist -> maps browse, then the round-resolution finding."""

    def setUp(self) -> None:
        self.room = _room()
        self.gm_char, self.gm_account = _gm_in_room(self.room)
        self.pc_char, self.pc_sheet = _pc_in_room(self.room, db_key="Recruit")

        # Catalog seed: a blueprint named "River Crossing" with one staged
        # front, "West Bank"; a unit template "Levy Spears" carrying one
        # capability -- proves the "copied capabilities" leg of the journey.
        self.blueprint = BattleMapBlueprintFactory(name="River Crossing")
        BlueprintBattlePlaceFactory(blueprint=self.blueprint, name="West Bank")

        self.template = BattleUnitTemplateFactory(name="Levy Spears")
        self.capability = CapabilityTypeFactory(name="Spear Wall")
        BattleUnitTemplateCapabilityFactory(
            template=self.template, capability=self.capability, value=3
        )

    def test_full_staging_journey(self) -> None:
        # ------------------------------------------------------------
        # Step 1: battle create Skirmish risk=low map=River Crossing
        # ------------------------------------------------------------
        _run(self.gm_char, "create Skirmish risk=low map=River Crossing")

        battle = Battle.objects.get(name="Skirmish")
        self.assertEqual(battle.risk_level, "low")
        self.assertEqual(battle.sides.count(), 2)
        self.assertTrue(
            BattleSide.objects.filter(battle=battle, role=BattleSideRole.ATTACKER).exists()
        )
        self.assertTrue(
            BattleSide.objects.filter(battle=battle, role=BattleSideRole.DEFENDER).exists()
        )
        place = BattlePlace.objects.get(battle=battle, name="West Bank")

        self.gm_char.msg.assert_called()
        create_msg = self.gm_char.msg.call_args[0][0]
        self.assertIn("Skirmish", create_msg)

        # ------------------------------------------------------------
        # Step 2: battle spawn Levy Spears count=3 at West Bank side=defender
        # ------------------------------------------------------------
        _run(self.gm_char, "spawn Levy Spears count=3 at West Bank side=defender")

        units = list(BattleUnit.objects.filter(battle=battle, name__startswith="Levy Spears"))
        self.assertEqual(len(units), 3)
        defender_side = BattleSide.objects.get(battle=battle, role=BattleSideRole.DEFENDER)
        for unit in units:
            self.assertEqual(unit.side_id, defender_side.pk)
            self.assertEqual(unit.place_id, place.pk)
            capability_rows = list(unit.capability_values.all())
            self.assertEqual(len(capability_rows), 1)
            self.assertEqual(capability_rows[0].capability_id, self.capability.pk)
            self.assertEqual(capability_rows[0].value, 3)

        # ------------------------------------------------------------
        # Step 3: battle enlist Recruit = attacker
        # ------------------------------------------------------------
        _run(self.gm_char, "enlist Recruit = attacker")

        participant = BattleParticipant.objects.get(battle=battle, character_sheet=self.pc_sheet)
        attacker_side = BattleSide.objects.get(battle=battle, role=BattleSideRole.ATTACKER)
        self.assertEqual(participant.side_id, attacker_side.pk)
        self.assertEqual(participant.status, BattleParticipantStatus.ACTIVE)

        # ------------------------------------------------------------
        # Step 4: battle maps riv -- browse output names the staged blueprint.
        # ------------------------------------------------------------
        _run(self.gm_char, "maps riv")
        maps_msg = self.gm_char.msg.call_args[0][0]
        self.assertIn("River Crossing", maps_msg)

        # ------------------------------------------------------------
        # Step 5 (battle-resolution finding, see module docstring):
        # `battle round` cannot find this staged battle -- it is
        # location-less by design (ADR-0081). Proven here rather than
        # assumed.
        # ------------------------------------------------------------
        _run(self.gm_char, "round")
        round_msg = self.gm_char.msg.call_args[0][0]
        self.assertIn("no active battle", round_msg.lower())
        self.assertFalse(battle.rounds.exists())
