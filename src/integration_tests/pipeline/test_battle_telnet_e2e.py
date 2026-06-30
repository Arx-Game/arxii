"""Telnet E2E: battle lifecycle journey (#1592).

Drives the full stage→declare→resolve→conclude flow through CmdBattle, asserting
DB state after each step and telnet feedback via caller.msg MagicMock.

Journey outline:
  1. GM opens a round  (``battle round``).
  2. Two defender PCs each declare a strike against the enemy unit
     (``battle declare strike <unit>``).
  3. GM resolves the round (``battle resolve``) with ``perform_check`` patched:
     - PC1 succeeds (``success_level=5``) → enemy unit loses 50 strength,
       defender side gains 25 VP.
     - PC2 fails (``success_level=-3``) → PC2 takes 11 damage.
  4. The defender side's VP (25) reaches its ``victory_threshold`` (25), so the
     resolve action auto-concludes the battle.

All assertions run on the SQLite fast tier — no ``@tag("postgres")`` needed
because no progressive-condition / ``DISTINCT ON`` path is touched here.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import TestCase

from commands.battle import CmdBattle
from evennia_extensions.factories import AccountFactory, CharacterFactory, ObjectDBFactory
from world.battles.constants import (
    BASE_FAILURE_DAMAGE,
    BATTLE_CHECK_TYPE_NAME,
    STRIKE_ATTRITION_PER_LEVEL,
    STRIKE_VP_PER_LEVEL,
    BattleActionKind,
    BattleSideRole,
)
from world.battles.models import BattleActionDeclaration, BattleRound
from world.battles.services import add_side, add_unit, create_battle, enlist_participant
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import CheckCategoryFactory, CheckTypeFactory
from world.roster.factories import RosterEntryFactory, RosterTenureFactory
from world.scenes.constants import RoundStatus
from world.vitals.factories import CharacterVitalsFactory

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_room(label: str = "BattleE2ERoom") -> object:
    """Create a Room ObjectDB in the identity map."""
    return ObjectDBFactory(
        db_key=label,
        db_typeclass_path="typeclasses.rooms.Room",
    )


def _make_gm_actor(db_key: str, room: object, account: object) -> object:
    """Create a staff-account-linked character.

    ``account.is_staff`` is True, so ``_actor_may_gm_battle`` short-circuits
    without needing a scene.is_gm SceneParticipation.
    """
    char = CharacterFactory(db_key=db_key, location=room)
    sheet = CharacterSheetFactory(character=char)
    entry = RosterEntryFactory(character_sheet=sheet)
    RosterTenureFactory(
        roster_entry=entry,
        player_data__account=account,
        end_date=None,
    )
    return char


def _make_pc(db_key: str, room: object) -> tuple[object, object]:
    """Create a PC character with a sheet and vitals in *room*.

    Returns (character, character_sheet).
    """
    char = CharacterFactory(db_key=db_key, location=room)
    sheet = CharacterSheetFactory(character=char)
    CharacterVitalsFactory(character_sheet=sheet, health=100, max_health=100)
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


def _stub_check(success_level: int) -> MagicMock:
    """Return a MagicMock resembling a CheckResult with *success_level*."""
    result = MagicMock()
    result.success_level = success_level
    return result


# ---------------------------------------------------------------------------
# E2E journey
# ---------------------------------------------------------------------------


class BattleTelnetE2EJourneyTest(TestCase):
    """Full battle lifecycle journey through telnet CmdBattle.

    Uses a low ``victory_threshold`` (25 VP) so that one successful strike
    at ``success_level=5`` (→ 25 VP) triggers auto-conclude at resolve time.
    """

    def setUp(self) -> None:
        # Room — all actors located here so _active_battle_in_room finds the battle.
        self.room = _make_room()

        # Seed the CheckType required by resolve_battle_round → get_battle_check_type().
        category = CheckCategoryFactory(name="BattleE2ECategory")
        CheckTypeFactory(name=BATTLE_CHECK_TYPE_NAME, category=category)

        # GM actor — staff account so _actor_may_gm_battle returns True immediately.
        self.gm_account = AccountFactory(username="e2e_gm_account", is_staff=True)
        self.gm_char = _make_gm_actor("e2e_gm", self.room, self.gm_account)

        # Battle located in the test room.
        self.battle = create_battle(name="E2E Test Battle")
        self.battle.scene.location = self.room
        self.battle.scene.save(update_fields=["location"])

        # Two sides: enemy attackers, defender PCs.
        # Low victory_threshold so one success_level=5 strike reaches it.
        # victory_threshold = success_level(5) * STRIKE_VP_PER_LEVEL(5) = 25
        self.attacker_side = add_side(battle=self.battle, role=BattleSideRole.ATTACKER)
        self.defender_side = add_side(
            battle=self.battle,
            role=BattleSideRole.DEFENDER,
            victory_threshold=25,
        )

        # Enemy unit on the attacker side — the target of PC strikes.
        self.enemy_unit = add_unit(
            battle=self.battle,
            side=self.attacker_side,
            name="Iron Vanguard",
            unit_type="soldiers",
            strength=100,
        )

        # Two PC participants on the defender side.
        self.pc1_char, self.pc1_sheet = _make_pc("e2e_pc1", self.room)
        self.pc2_char, self.pc2_sheet = _make_pc("e2e_pc2", self.room)

        self.pc1_participant = enlist_participant(
            battle=self.battle,
            character_sheet=self.pc1_sheet,
            side=self.defender_side,
        )
        self.pc2_participant = enlist_participant(
            battle=self.battle,
            character_sheet=self.pc2_sheet,
            side=self.defender_side,
        )

    # -----------------------------------------------------------------------
    # Full journey in one test to match the E2E contract.
    # -----------------------------------------------------------------------

    def test_full_battle_lifecycle(self) -> None:
        """stage→declare(×2)→resolve(patched)→auto-conclude."""

        # ----------------------------------------------------------------
        # Step 1: GM opens a round.
        # ----------------------------------------------------------------
        _run(self.gm_char, "round")

        battle_round = BattleRound.objects.filter(
            battle=self.battle,
            status=RoundStatus.DECLARING,
        ).first()
        self.assertIsNotNone(
            battle_round,
            "A DECLARING BattleRound should exist after 'battle round'.",
        )
        self.assertEqual(battle_round.round_number, 1)

        self.gm_char.msg.assert_called()
        gm_open_msg = self.gm_char.msg.call_args[0][0]
        self.assertIn("1", gm_open_msg, "'Round 1 begins' feedback expected")

        # ----------------------------------------------------------------
        # Step 2: Both PCs declare a strike on the enemy unit.
        # ----------------------------------------------------------------
        _run(self.pc1_char, "declare strike Iron Vanguard")
        pc1_declare_msg = self.pc1_char.msg.call_args[0][0]
        self.assertIn("declare", pc1_declare_msg.lower())

        _run(self.pc2_char, "declare strike Iron Vanguard")

        declarations = BattleActionDeclaration.objects.filter(battle_round=battle_round)
        self.assertEqual(declarations.count(), 2, "Both PCs should have a declaration.")
        self.assertTrue(
            declarations.filter(
                participant=self.pc1_participant,
                action_kind=BattleActionKind.STRIKE,
                target_unit=self.enemy_unit,
            ).exists(),
            "PC1 declaration should exist.",
        )
        self.assertTrue(
            declarations.filter(
                participant=self.pc2_participant,
                action_kind=BattleActionKind.STRIKE,
                target_unit=self.enemy_unit,
            ).exists(),
            "PC2 declaration should exist.",
        )

        # ----------------------------------------------------------------
        # Step 3: GM resolves with patched perform_check.
        #
        # BattleActionDeclaration.Meta.ordering = ["battle_round", "participant"]
        # Participants are ordered by ["battle", "character_sheet"].
        # pc1_sheet was created before pc2_sheet → pc1 pk < pc2 pk → pc1 first.
        #
        # Call 1 → pc1 succeeds (success_level=5): unit loses strength, VP awarded.
        # Call 2 → pc2 fails  (success_level=-3): pc2 health debited.
        # ----------------------------------------------------------------
        check_side_effects = [
            _stub_check(5),  # pc1 — STRIKE success
            _stub_check(-3),  # pc2 — failure → damage
        ]
        with patch(
            "world.battles.resolution.perform_check",
            side_effect=check_side_effects,
        ):
            _run(self.gm_char, "resolve")

        # ----------------------------------------------------------------
        # Step 4: Assertions.
        # ----------------------------------------------------------------

        # Enemy unit strength: 100 − (5 × STRIKE_ATTRITION_PER_LEVEL) = 100 − 50 = 50.
        self.enemy_unit.refresh_from_db()
        expected_attrition = 5 * STRIKE_ATTRITION_PER_LEVEL
        self.assertEqual(
            self.enemy_unit.strength,
            100 - expected_attrition,
            f"Enemy unit strength should be {100 - expected_attrition}.",
        )

        # Defender side VP: 5 × STRIKE_VP_PER_LEVEL = 25.
        self.defender_side.refresh_from_db()
        expected_vp = 5 * STRIKE_VP_PER_LEVEL
        self.assertEqual(
            self.defender_side.victory_points,
            expected_vp,
            f"Defender side should have {expected_vp} VP.",
        )

        # PC2 health: 100 − (BASE_FAILURE_DAMAGE + abs(−3)) = 100 − 11 = 89.
        pc2_vitals = self.pc2_sheet.vitals
        pc2_vitals.refresh_from_db()
        expected_damage = BASE_FAILURE_DAMAGE + 3
        self.assertEqual(
            pc2_vitals.health,
            100 - expected_damage,
            "Failing PC (PC2) should have taken damage.",
        )

        # PC1 health: unchanged (success path, no damage).
        pc1_vitals = self.pc1_sheet.vitals
        pc1_vitals.refresh_from_db()
        self.assertEqual(
            pc1_vitals.health,
            100,
            "Successful PC (PC1) should not have taken damage.",
        )

        # ----------------------------------------------------------------
        # Step 5: Auto-conclude (victory_points ≥ victory_threshold triggers
        # check_victory inside ResolveBattleRoundAction.execute).
        # ----------------------------------------------------------------
        self.battle.refresh_from_db()
        self.assertTrue(
            self.battle.is_concluded,
            "Battle should be auto-concluded after VP reached the threshold.",
        )

        self.battle.scene.refresh_from_db()
        self.assertFalse(
            self.battle.scene.is_active,
            "The backing scene should be inactive after battle conclusion.",
        )

        # GM received a conclude message from the resolve action.
        gm_resolve_msg = self.gm_char.msg.call_args[0][0]
        self.assertIn(
            "concludes",
            gm_resolve_msg.lower(),
            "GM should see a battle-concluded message.",
        )
