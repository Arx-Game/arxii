"""Telnet E2E: battle Surrounded peril/rescue journey (#1733)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import TestCase, tag

from actions.factories import ActionTemplateFactory
from integration_tests.pipeline.test_battle_telnet_e2e import (
    _make_gm_actor,
    _make_pc,
    _make_room,
    _run,
    _stub_check,
)
from world.battles.constants import BattleParticipantStatus, BattleSideRole
from world.battles.services import add_place, add_side, add_unit, create_battle, enlist_participant
from world.conditions.factories import ConditionInstanceFactory
from world.conditions.services import get_active_conditions
from world.magic.factories import CharacterAnimaFactory, CharacterTechniqueFactory, TechniqueFactory
from world.traits.models import CheckOutcome
from world.vitals.factories import ensure_surrounded_content


class BattlePerilRescueE2EJourneyTest(TestCase):
    """Full Surrounded peril lifecycle journey through telnet CmdBattle.

    Two journeys:
      1. Isolated STRIKE failure -> Surrounded entry -> AFK-driven escalation
         (via ``afk_peril_override``) -> a successful RESCUE clears it.
      2. Terminal-stage resolution routes to the death-permitting enemy pool
         when no opposing PC shares the victim's place, and to the death-free
         PvP pool when one does (ADR-0023).
    """

    def setUp(self) -> None:
        """Build a battle with an isolated PC (no ally at their place) and a rescuer."""
        self.content = ensure_surrounded_content()
        self.room = _make_room("PerilRescueE2ERoom")
        self.technique = TechniqueFactory(
            action_template=ActionTemplateFactory(), damage_profile=False
        )
        from evennia_extensions.factories import AccountFactory

        self.gm_account = AccountFactory(username="peril_e2e_gm", is_staff=True)
        self.gm_char = _make_gm_actor("peril_e2e_gm_char", self.room, self.gm_account)

        self.battle = create_battle(name="Peril Rescue E2E Battle")
        self.battle.scene.location = self.room
        self.battle.scene.save(update_fields=["location"])
        self.battle.afk_peril_override = True
        self.battle.save(update_fields=["afk_peril_override"])

        self.side = add_side(battle=self.battle, role=BattleSideRole.DEFENDER)
        self.place = add_place(battle=self.battle, name="The Breach")
        self.enemy_unit = add_unit(
            battle=self.battle, side=self.side, name="Foes", unit_type="infantry"
        )

        self.pc_char, self.pc_sheet = _make_pc("peril_pc", self.room)
        self.rescuer_char, self.rescuer_sheet = _make_pc("peril_rescuer", self.room)
        for sheet, char in ((self.pc_sheet, self.pc_char), (self.rescuer_sheet, self.rescuer_char)):
            CharacterTechniqueFactory(character=sheet, technique=self.technique)
            CharacterAnimaFactory(character=char, current=20, maximum=30)

        self.pc_participant = enlist_participant(
            battle=self.battle, character_sheet=self.pc_sheet, side=self.side, place=self.place
        )
        # Rescuer is NOT at self.place — the PC is isolated there.
        self.rescuer_participant = enlist_participant(
            battle=self.battle, character_sheet=self.rescuer_sheet, side=self.side
        )

    @tag("postgres")
    def test_isolated_pc_surrounded_escalates_while_afk_then_rescued(self) -> None:
        """PG-only: Round 1 exercises the real _maybe_apply_surrounded -> apply_condition
        production path (Task 6), which hits the same PG-only DISTINCT ON query as
        EntryRollTests. Run via `just test-parity integration_tests`, not `test-fast`.
        """
        failure_outcome = CheckOutcome.objects.get(name="Failure")

        # ---- Round 1: isolated STRIKE failure -> entry roll -> Surrounded (stage 1). ----
        _run(self.gm_char, "round")
        _run(self.pc_char, f"declare strike {self.enemy_unit.name} with {self.technique.name}")

        with (
            patch(
                "world.battles.resolution.resolve_battle_technique",
                return_value=_stub_check(-10),
            ),
            patch(
                "world.checks.consequence_resolution.perform_check",
                return_value=MagicMock(outcome=failure_outcome, success_level=-1),
            ),
            # The PC declared this round, so _advance_surrounded_participants ticks
            # their brand-new stage-1 instance in this SAME resolve call (declaring
            # gates the tick regardless of afk_peril_override — see
            # _advance_surrounded_participants). Without this patch that resist
            # check would hit the real, unmocked dice roll and could nondeterministically
            # advance past stage 1 before this assertion runs. A non-negative
            # success_level keeps the stage held at 1 (advance only fires on failure).
            patch("world.vitals.services.perform_check", return_value=_stub_check(1)),
        ):
            _run(self.gm_char, "resolve")

        instance = get_active_conditions(self.pc_char, condition=self.content["condition"]).first()
        self.assertIsNotNone(instance, "Isolated failure should have applied Surrounded.")
        self.assertEqual(instance.current_stage.stage_order, 1)

        # ---- Round 2: PC declares nothing (AFK) -- escalates anyway via afk_peril_override. ----
        _run(self.gm_char, "round")
        # Only the rescuer declares (a SUPPORT no-op target isn't needed for this
        # assertion) -- the PC's own peril still ticks because afk_peril_override=True.
        with patch("world.vitals.services.perform_check", return_value=_stub_check(-1)):
            _run(self.gm_char, "resolve")

        instance.refresh_from_db()
        self.assertEqual(
            instance.current_stage.stage_order, 2, "AFK-override should have escalated the stage."
        )

        # ---- Round 3: rescuer declares RESCUE, succeeds -> Surrounded clears. ----
        _run(self.gm_char, "round")
        _run(
            self.rescuer_char,
            f"declare rescue {self.pc_char.key} with {self.technique.name}",
        )
        with patch(
            "world.battles.resolution.resolve_battle_technique",
            return_value=_stub_check(4),
        ):
            _run(self.gm_char, "resolve")

        self.assertFalse(
            get_active_conditions(self.pc_char, condition=self.content["condition"]).exists(),
            "A successful RESCUE should have cleared Surrounded.",
        )
        self.pc_participant.refresh_from_db()
        self.assertEqual(self.pc_participant.status, BattleParticipantStatus.ACTIVE)

    def test_terminal_surrounded_dies_when_enemy_sourced_survives_when_pvp_sourced(self) -> None:
        """Terminal Surrounded routes to the death-gated enemy pool by default, but the
        death-free PvP pool once an opposing PC shares the victim's place (ADR-0023).
        """
        failure_outcome = CheckOutcome.objects.get(name="Failure")

        # ---- Enemy-sourced: no opposing PC at self.place -> surrounded_terminal_enemy. ----
        self._apply_condition_at_terminal_stage(self.pc_char)
        with patch(
            "world.checks.consequence_resolution.perform_check",
            return_value=MagicMock(outcome=failure_outcome, success_level=-1),
        ):
            from world.vitals.services import advance_surrounded

            died = advance_surrounded(self.pc_sheet, battle=self.battle)

        self.assertTrue(died, "Enemy-sourced terminal Failure should permit death.")
        self.pc_sheet.vitals.refresh_from_db()
        from world.vitals.constants import CharacterLifeState

        self.assertEqual(self.pc_sheet.vitals.life_state, CharacterLifeState.DEAD)
        self.pc_participant.refresh_from_db()
        self.assertEqual(self.pc_participant.status, BattleParticipantStatus.INCAPACITATED)

        # ---- PvP-sourced: an opposing PC now shares the victim's place. ----
        # _make_pc already creates a CharacterVitals row for the sheet — do not
        # create a second one (CharacterVitals.character_sheet is a OneToOne;
        # a duplicate factory call here raises IntegrityError).
        victim2_char, victim2_sheet = _make_pc("peril_pc2", self.room)
        victim2_participant = enlist_participant(
            battle=self.battle, character_sheet=victim2_sheet, side=self.side, place=self.place
        )
        opposing_side = add_side(battle=self.battle, role=BattleSideRole.ATTACKER)
        opposing_char, opposing_sheet = _make_pc("peril_opposing_pc", self.room)
        # A bare _make_pc()-created character has db_account=None (NPC by convention —
        # see world/vitals/peril_resolution.py:is_pc_source and
        # SelectSurroundedTerminalPoolTests in world/battles/tests/test_resolution.py);
        # attach a real account so select_surrounded_terminal_pool classifies this
        # participant as an opposing PC rather than routing to the enemy pool.
        from evennia_extensions.factories import AccountFactory

        opposing_char.db_account = AccountFactory()
        opposing_char.save()
        enlist_participant(
            battle=self.battle, character_sheet=opposing_sheet, side=opposing_side, place=self.place
        )
        self._apply_condition_at_terminal_stage(victim2_char)

        with patch(
            "world.checks.consequence_resolution.perform_check",
            return_value=MagicMock(outcome=failure_outcome, success_level=-1),
        ):
            from world.vitals.services import advance_surrounded

            died2 = advance_surrounded(victim2_sheet, battle=self.battle)

        self.assertFalse(
            died2, "PvP-sourced terminal resolution must never select death (ADR-0023)."
        )
        victim2_participant.refresh_from_db()
        self.assertNotEqual(victim2_participant.status, BattleParticipantStatus.INCAPACITATED)

    def _apply_condition_at_terminal_stage(self, character) -> None:
        """Test-only shortcut: build the ConditionInstance directly at the terminal
        stage, rather than via apply_condition (which routes through
        _build_bulk_context's PG-only DISTINCT ON query and errors on the SQLite fast
        tier — same known trap as Task 7's fixture and Task 8's RescueResolutionTests).
        This keeps this journey SQLite-safe: advance_surrounded's terminal path uses
        remove_condition, not apply_condition, so nothing else in this test touches the
        PG-only path.
        """
        ConditionInstanceFactory(
            target=character,
            condition=self.content["condition"],
            current_stage=self.content["stages"][-1],  # stage_order=3, terminal
        )
