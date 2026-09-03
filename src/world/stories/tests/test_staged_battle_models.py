"""BeatStagedBattle / BeatStagedBattleUnit invariants (#3569)."""

from django.core.exceptions import ValidationError
from django.test import TestCase

from world.battles.constants import BattleSideRole
from world.battles.factories import BattleMapBlueprintFactory
from world.stories.constants import BeatKind
from world.stories.factories import (
    BeatFactory,
    BeatOpponentLineFactory,
    BeatStagedBattleFactory,
    BeatStagedBattleUnitFactory,
)
from world.stories.models import BeatStagedBattle, BeatStagedBattleUnit


class BeatStagedBattleTests(TestCase):
    def setUp(self) -> None:
        self.blueprint = BattleMapBlueprintFactory(name="Siege of the Gate")

    def test_encounter_beat_can_stage_a_battle(self) -> None:
        beat = BeatFactory(kind=BeatKind.ENCOUNTER)
        staged = BeatStagedBattleFactory(beat=beat, blueprint=self.blueprint)
        staged.full_clean()
        self.assertEqual(beat.staged_battle, staged)
        self.assertEqual(staged.party_side_role, BattleSideRole.DEFENDER)

    def test_situation_beat_cannot_stage_a_battle(self) -> None:
        beat = BeatFactory(kind=BeatKind.SITUATION)
        staged = BeatStagedBattle(beat=beat, blueprint=self.blueprint)
        with self.assertRaises(ValidationError):
            staged.full_clean()

    def test_staged_battle_refused_when_opponent_lines_exist(self) -> None:
        beat = BeatFactory(kind=BeatKind.ENCOUNTER)
        BeatOpponentLineFactory(beat=beat)
        staged = BeatStagedBattle(beat=beat, blueprint=self.blueprint)
        with self.assertRaises(ValidationError):
            staged.full_clean()

    def test_opponent_line_refused_when_a_battle_is_staged(self) -> None:
        beat = BeatFactory(kind=BeatKind.ENCOUNTER)
        BeatStagedBattleFactory(beat=beat, blueprint=self.blueprint)
        line = BeatOpponentLineFactory.build(beat=beat)
        with self.assertRaises(ValidationError):
            line.full_clean()

    def test_one_staged_battle_per_beat(self) -> None:
        from django.db import IntegrityError

        beat = BeatFactory(kind=BeatKind.ENCOUNTER)
        BeatStagedBattleFactory(beat=beat, blueprint=self.blueprint)
        with self.assertRaises(IntegrityError):
            BeatStagedBattle.objects.create(beat=beat, blueprint=self.blueprint)

    def test_unit_lines_order_and_defaults(self) -> None:
        beat = BeatFactory(kind=BeatKind.ENCOUNTER)
        staged = BeatStagedBattleFactory(beat=beat, blueprint=self.blueprint)
        second = BeatStagedBattleUnitFactory(staged_battle=staged, order=2)
        first = BeatStagedBattleUnitFactory(
            staged_battle=staged, order=1, side_role=BattleSideRole.DEFENDER, count=3
        )
        self.assertEqual(list(staged.unit_lines.all()), [first, second])
        self.assertEqual(second.side_role, BattleSideRole.ATTACKER)
        self.assertEqual(second.count, 1)

    def test_deleting_the_beat_cascades_and_the_blueprint_is_protected(self) -> None:
        from django.db.models import ProtectedError

        beat = BeatFactory(kind=BeatKind.ENCOUNTER)
        staged = BeatStagedBattleFactory(beat=beat, blueprint=self.blueprint)
        BeatStagedBattleUnitFactory(staged_battle=staged)
        with self.assertRaises(ProtectedError):
            self.blueprint.delete()
        beat.delete()
        self.assertEqual(BeatStagedBattle.objects.count(), 0)
        self.assertEqual(BeatStagedBattleUnit.objects.count(), 0)
