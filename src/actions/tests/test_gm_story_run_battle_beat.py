"""Tests for the #3569 battle branch of RunBeatAction: an ENCOUNTER beat with a
BeatStagedBattle row (session prep) stages a Battle from its blueprint instead of
a CombatEncounter -- units spawn on their authored side/place, the running
scene's party is enlisted on the staged party_side_role, the battle links back
to the beat (story_beat), and a re-run returns the same unconcluded battle.
GMListRunnableBeatsAction's staged_battle_name row flag is covered too.
"""

from __future__ import annotations

from actions.definitions.gm_story import GMListRunnableBeatsAction, RunBeatAction
from actions.tests.test_gm_story_run_beat import RunBeatActionTestBase
from world.battles.constants import BattleSideRole
from world.battles.factories import (
    BattleMapBlueprintFactory,
    BattleUnitTemplateFactory,
    BlueprintBattlePlaceFactory,
)
from world.battles.models import Battle
from world.societies.constants import RenownRisk
from world.stories.constants import BeatKind
from world.stories.factories import (
    BeatFactory,
    BeatStagedBattleFactory,
    BeatStagedBattleUnitFactory,
)
from world.stories.models import EpisodeScene


class RunBeatActionBattleJourneyTests(RunBeatActionTestBase):
    """The full battle-staging journey a BeatStagedBattle row unlocks (#3569)."""

    def setUp(self) -> None:
        super().setUp()
        self.player_sheet = self.player_actor.character_sheet
        self.blueprint = BattleMapBlueprintFactory(name="Siege of the Gate")
        self.gate = BlueprintBattlePlaceFactory(blueprint=self.blueprint, name="Outer Gate")
        self.beat = BeatFactory(
            episode=self.episode,
            kind=BeatKind.ENCOUNTER,
            risk=RenownRisk.HIGH,
            internal_description="Hold the gate until dawn\nsecond line",
        )
        self.staged = BeatStagedBattleFactory(beat=self.beat, blueprint=self.blueprint, name="")
        self.template = BattleUnitTemplateFactory(name="Levy spears")
        BeatStagedBattleUnitFactory(
            staged_battle=self.staged,
            template=self.template,
            side_role=BattleSideRole.ATTACKER,
            place_name="Outer Gate",
            count=2,
            order=0,
        )

    def _run(self):
        return RunBeatAction().run(self.lead_gm_actor, beat_id=self.beat.pk)

    def test_run_stages_the_battle_from_the_blueprint(self) -> None:
        result = self._run()
        self.assertTrue(result.success, result.message)

        battle = Battle.objects.get(pk=result.data["battle_id"])
        self.assertEqual(battle.story_beat_id, self.beat.pk)
        self.assertEqual(battle.name, "Hold the gate until dawn")
        self.assertEqual(battle.risk_level, "high")
        self.assertEqual(list(battle.places.values_list("name", flat=True)), ["Outer Gate"])
        self.assertTrue(
            EpisodeScene.objects.filter(episode=self.episode, scene=battle.scene).exists()
        )

        self.scene.refresh_from_db()
        self.assertEqual(self.scene.running_beat_id, self.beat.pk)
        self.assertEqual(result.data["battle_scene_id"], battle.scene_id)

    def test_units_spawn_on_their_side_at_their_place(self) -> None:
        result = self._run()
        battle = Battle.objects.get(pk=result.data["battle_id"])
        units = list(battle.units.all())
        self.assertEqual(len(units), 2)
        self.assertTrue(all(u.side.role == BattleSideRole.ATTACKER for u in units))
        self.assertTrue(all(u.place.name == "Outer Gate" for u in units))

    def test_party_is_enlisted_on_the_party_side(self) -> None:
        result = self._run()
        battle = Battle.objects.get(pk=result.data["battle_id"])
        enlisted = {p.character_sheet_id: p.side.role for p in battle.participants.all()}
        self.assertIn(self.player_sheet.pk, enlisted)
        self.assertEqual(enlisted[self.player_sheet.pk], BattleSideRole.DEFENDER)
        self.assertTrue(battle.scene.is_gm(self.lead_gm_account))

    def test_attack_stages_the_party_as_attackers(self) -> None:
        self.staged.party_side_role = BattleSideRole.ATTACKER
        self.staged.save()
        result = self._run()
        battle = Battle.objects.get(pk=result.data["battle_id"])
        self.assertTrue(
            all(p.side.role == BattleSideRole.ATTACKER for p in battle.participants.all())
        )

    def test_rerun_returns_the_same_unconcluded_battle(self) -> None:
        first = self._run()
        self.scene.running_beat = None
        self.scene.save(update_fields=["running_beat"])
        second = self._run()
        self.assertEqual(first.data["battle_id"], second.data["battle_id"])
        self.assertTrue(second.data["already_staged"])
        self.assertEqual(Battle.objects.count(), 1)

    def test_unknown_place_logs_and_spawns_unplaced(self) -> None:
        # A per-instance save (not a bulk .update()) so the idmapper cache doesn't
        # keep serving the stale row back to _run_battle_beat's own query.
        for line in self.staged.unit_lines.all():
            line.place_name = "No Such Place"
            line.save(update_fields=["place_name"])
        result = self._run()
        battle = Battle.objects.get(pk=result.data["battle_id"])
        self.assertEqual(battle.units.count(), 2)
        self.assertTrue(all(u.place_id is None for u in battle.units.all()))

    def test_no_participants_stages_and_enlists_nobody(self) -> None:
        self.scene.participations.filter(is_gm=False).delete()
        result = self._run()
        battle = Battle.objects.get(pk=result.data["battle_id"])
        self.assertEqual(battle.participants.count(), 0)
        self.assertEqual(result.data["enlisted"], [])

    def test_runnable_list_marks_the_staged_battle(self) -> None:
        result = GMListRunnableBeatsAction().run(self.lead_gm_actor)
        row = next(r for r in result.data["beats"] if r["id"] == self.beat.pk)
        self.assertEqual(row["staged_battle_name"], "Siege of the Gate")

        plain = BeatFactory(episode=self.episode, kind=BeatKind.ENCOUNTER)
        result = GMListRunnableBeatsAction().run(self.lead_gm_actor)
        row = next(r for r in result.data["beats"] if r["id"] == plain.pk)
        self.assertIsNone(row["staged_battle_name"])
