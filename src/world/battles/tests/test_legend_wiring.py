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
from world.military.factories import MilitaryUnitFactory
from world.societies.constants import RenownRisk
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
        self.activation = self._stake_the_battle()

    def _stake_the_battle(self, *, target_level: int = 3, held: bool = True):
        """Give the battle a staked beat with a locked, resolved contract.

        Required since #3467: a battle prices its Legend from the beat it was
        fought over. A battle with no staked beat has no target level, so no
        station, so no advancement Legend — these tests are about who earns and
        how much, so they need a real war to be fought over.
        """
        from world.stories.constants import StakeResolutionColumn
        from world.stories.factories import (
            BeatFactory,
            EpisodeFactory,
            EpisodeSceneFactory,
            StakeFactory,
            StakeOutcomeFactory,
        )
        from world.stories.models import StakeContractActivation

        episode = EpisodeFactory()
        EpisodeSceneFactory(episode=episode, scene=self.battle.scene)
        beat = BeatFactory(episode=episode, risk=RenownRisk.EXTREME, target_level=target_level)
        activation = StakeContractActivation.objects.create(
            beat=beat,
            party_average_level=target_level,
            declared_target_level=target_level,
            declared_risk=RenownRisk.EXTREME,
            effective_risk=RenownRisk.EXTREME,
            is_ready=True,
        )
        stake = StakeFactory(beat=beat)
        StakeOutcomeFactory(
            stake=stake,
            activation=activation,
            column=StakeResolutionColumn.WIN if held else StakeResolutionColumn.LOSS,
        )
        return activation

    def _levelled(self, level: int = 3):
        """A sheet at a level inside the beat's band — station and risk both real."""
        from world.classes.factories import CharacterClassLevelFactory

        sheet = CharacterSheetFactory()
        CharacterClassLevelFactory(character=sheet, level=level, is_primary=True)
        return sheet

    def _restore_hooks(self) -> None:
        conclusion_hooks._HOOKS[:] = self._saved_hooks

    def test_decisive_win_awards_event_to_participants_and_commander(self) -> None:
        winner_sheet = self._levelled()
        BattleParticipantFactory(
            battle=self.battle, side=self.attacker_side, character_sheet=winner_sheet
        )
        commander_sheet = self._levelled()
        BattleUnitFactory(
            battle=self.battle,
            side=self.attacker_side,
            military_unit=MilitaryUnitFactory(commander=commander_sheet),
        )
        loser_sheet = self._levelled()
        BattleParticipantFactory(
            battle=self.battle, side=self.defender_side, character_sheet=loser_sheet
        )

        conclude_battle(battle=self.battle, outcome=BattleOutcome.ATTACKER_DECISIVE)

        event = LegendEvent.objects.get(scene=self.battle.scene)
        self.assertEqual(event.title, f"Victory at {self.battle.name}")
        # #3467: priced from the beat's risk tier, not a flat per-outcome constant.
        self.assertGreater(event.base_value, 0)

        entries = LegendEntry.objects.filter(event=event)
        winner_personas = {winner_sheet.primary_persona.pk, commander_sheet.primary_persona.pk}
        self.assertEqual({e.persona_id for e in entries}, winner_personas)
        self.assertFalse(LegendEntry.objects.filter(persona=loser_sheet.primary_persona).exists())

    def test_marginal_win_still_pays_the_winning_side(self) -> None:
        """#3467: the decisive/marginal split no longer picks a flat value.

        It survives only to name the winning side; what the war pays comes from
        its beat's risk and each earner's station. Replaces
        test_marginal_win_uses_marginal_value, which asserted the retired
        BATTLE_LEGEND_MARGINAL_VALUE constant.
        """
        winner_sheet = self._levelled()
        BattleParticipantFactory(
            battle=self.battle, side=self.attacker_side, character_sheet=winner_sheet
        )

        conclude_battle(battle=self.battle, outcome=BattleOutcome.ATTACKER_MARGINAL)

        event = LegendEvent.objects.get(scene=self.battle.scene)
        self.assertGreater(event.base_value, 0)

    def test_losing_side_standout_rescue_earns_stacking_solo_deed(self) -> None:
        winner_sheet = self._levelled()
        BattleParticipantFactory(
            battle=self.battle, side=self.attacker_side, character_sheet=winner_sheet
        )
        rescuer_sheet = self._levelled()
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
        self.assertGreater(standout.base_value, 0)
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
        winner_sheet = self._levelled()
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
