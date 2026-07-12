"""Tests for battle -> win-gated LegendEntry wiring (#2184).

``apply_battle_legend_awards`` is registered as a battle-conclusion hook in
``world.battles.apps.ready()``. Tests reset the registry to exactly this hook
(avoiding duplicate firing or cross-test leakage from other suites' probe
hooks / production hooks like the ship writeback or duel wiring), then
snapshot and restore the pre-test contents on cleanup — clearing to empty
(rather than restoring) would permanently drop the production registration
for the rest of the test process (mirrors ``test_conclusion_hooks.py`` /
``ships/tests/test_battle_writeback.py``).
"""

from __future__ import annotations

from django.test import TestCase

from world.battles import conclusion_hooks
from world.battles.conclusion_hooks import (
    clear_battle_conclusion_hooks,
    register_battle_conclusion_hook,
)
from world.battles.constants import (
    BATTLE_LEGEND_DECISIVE_VALUE,
    BATTLE_LEGEND_MARGINAL_VALUE,
    BATTLE_LEGEND_STANDOUT_VALUE,
    STANDOUT_SUCCESS_LEVEL,
    BattleActionKind,
    BattleOutcome,
    BattleSideRole,
)
from world.battles.factories import (
    BattleActionDeclarationFactory,
    BattleFactory,
    BattleParticipantFactory,
    BattleRoundFactory,
    BattleSideFactory,
    BattleUnitFactory,
)
from world.battles.legend_wiring import apply_battle_legend_awards
from world.battles.services import conclude_battle
from world.character_sheets.factories import CharacterSheetFactory
from world.societies.models import LegendEntry, LegendEvent


class ApplyBattleLegendAwardsTests(TestCase):
    def setUp(self) -> None:
        self._saved_hooks = list(conclusion_hooks._HOOKS)
        self.addCleanup(self._restore_hooks)
        clear_battle_conclusion_hooks()
        register_battle_conclusion_hook(apply_battle_legend_awards)

        self.battle = BattleFactory(name="Siege of the Salt Marsh")
        self.attacker_side = BattleSideFactory(battle=self.battle, role=BattleSideRole.ATTACKER)
        self.defender_side = BattleSideFactory(battle=self.battle, role=BattleSideRole.DEFENDER)

    def _restore_hooks(self) -> None:
        conclusion_hooks._HOOKS[:] = self._saved_hooks

    def test_decisive_win_awards_event_to_participants_and_commander(self) -> None:
        winner_sheet = CharacterSheetFactory()
        BattleParticipantFactory(
            battle=self.battle, side=self.attacker_side, character_sheet=winner_sheet
        )
        commander_sheet = CharacterSheetFactory()
        BattleUnitFactory(battle=self.battle, side=self.attacker_side, commander=commander_sheet)
        loser_sheet = CharacterSheetFactory()
        BattleParticipantFactory(
            battle=self.battle, side=self.defender_side, character_sheet=loser_sheet
        )

        conclude_battle(battle=self.battle, outcome=BattleOutcome.ATTACKER_DECISIVE)

        event = LegendEvent.objects.get(scene=self.battle.scene)
        self.assertEqual(event.title, f"Victory at {self.battle.name}")
        self.assertEqual(event.base_value, BATTLE_LEGEND_DECISIVE_VALUE)

        entries = LegendEntry.objects.filter(event=event)
        winner_personas = {winner_sheet.primary_persona.pk, commander_sheet.primary_persona.pk}
        self.assertEqual({e.persona_id for e in entries}, winner_personas)
        self.assertFalse(LegendEntry.objects.filter(persona=loser_sheet.primary_persona).exists())

    def test_marginal_win_uses_marginal_value(self) -> None:
        winner_sheet = CharacterSheetFactory()
        BattleParticipantFactory(
            battle=self.battle, side=self.attacker_side, character_sheet=winner_sheet
        )

        conclude_battle(battle=self.battle, outcome=BattleOutcome.ATTACKER_MARGINAL)

        event = LegendEvent.objects.get(scene=self.battle.scene)
        self.assertEqual(event.base_value, BATTLE_LEGEND_MARGINAL_VALUE)

    def test_losing_side_standout_rescue_earns_stacking_solo_deed(self) -> None:
        winner_sheet = CharacterSheetFactory()
        BattleParticipantFactory(
            battle=self.battle, side=self.attacker_side, character_sheet=winner_sheet
        )
        rescuer_sheet = CharacterSheetFactory()
        rescuer_participant = BattleParticipantFactory(
            battle=self.battle, side=self.defender_side, character_sheet=rescuer_sheet
        )
        battle_round = BattleRoundFactory(battle=self.battle)
        BattleActionDeclarationFactory(
            battle_round=battle_round,
            participant=rescuer_participant,
            action_kind=BattleActionKind.RESCUE,
            resolved=True,
            success_level=STANDOUT_SUCCESS_LEVEL,
        )

        conclude_battle(battle=self.battle, outcome=BattleOutcome.ATTACKER_DECISIVE)

        standout = LegendEntry.objects.get(
            persona=rescuer_sheet.primary_persona, event__isnull=True
        )
        self.assertEqual(standout.title, f"Daring rescue at {self.battle.name}")
        self.assertEqual(standout.base_value, BATTLE_LEGEND_STANDOUT_VALUE)
        self.assertEqual(standout.scene, self.battle.scene)

        # The victory event still fired for the winning side.
        self.assertTrue(LegendEvent.objects.filter(scene=self.battle.scene).exists())

    def test_unresolved_outcome_mints_nothing(self) -> None:
        BattleParticipantFactory(
            battle=self.battle,
            side=self.attacker_side,
            character_sheet=CharacterSheetFactory(),
        )

        conclude_battle(battle=self.battle, outcome=BattleOutcome.UNRESOLVED)

        self.assertFalse(LegendEntry.objects.filter(scene=self.battle.scene).exists())
        self.assertFalse(LegendEvent.objects.filter(scene=self.battle.scene).exists())

    def test_second_call_does_not_duplicate(self) -> None:
        winner_sheet = CharacterSheetFactory()
        BattleParticipantFactory(
            battle=self.battle, side=self.attacker_side, character_sheet=winner_sheet
        )

        conclude_battle(battle=self.battle, outcome=BattleOutcome.ATTACKER_DECISIVE)
        entry_count = LegendEntry.objects.filter(scene=self.battle.scene).count()
        event_count = LegendEvent.objects.filter(scene=self.battle.scene).count()

        # conclude_battle itself is idempotent (is_concluded guard), so exercise
        # the hook's own idempotency directly, as a second conclusion attempt would.
        apply_battle_legend_awards(self.battle)

        self.assertEqual(LegendEntry.objects.filter(scene=self.battle.scene).count(), entry_count)
        self.assertEqual(LegendEvent.objects.filter(scene=self.battle.scene).count(), event_count)
