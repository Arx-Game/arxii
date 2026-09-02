"""Tests for ENCOUNTER options: a fight resolves a node, never the beat (#3565).

Fixture shape: a scenario run whose ``source_beat`` is the scene's
``running_beat`` (mirrors ``RunBeatActionEncounterJourneyTests`` in
``actions/tests/test_gm_story_run_beat.py``) - so ``encounter_option.
_scene_for_run`` finds the scene via the run's source beat, exactly like a
GM-run scenario would.
"""

from __future__ import annotations

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory, ObjectDBFactory
from flows.events.payloads import EncounterCompletedPayload
from world.character_sheets.factories import CharacterSheetFactory
from world.combat.beat_wiring import encounter_completed_beat_handler
from world.combat.constants import EncounterOutcome, RiskLevel
from world.combat.factories import CreatureTemplateFactory, seed_scaling_defaults
from world.combat.models import CombatEncounter, CombatOpponent, EncounterOutcomeMapping
from world.missions.constants import OptionKind, OptionSource
from world.missions.factories import (
    MissionInstanceFactory,
    MissionNodeFactory,
    MissionOptionFactory,
    MissionOptionOpponentLineFactory,
    MissionOptionRouteFactory,
    MissionParticipantFactory,
    MissionTemplateFactory,
)
from world.missions.services.encounter_option import complete_encounter_for_option
from world.missions.services.play import BeatActionError, beat_for, resolve_beat_option
from world.missions.services.resolution import resolve_option
from world.scenes.factories import SceneFactory
from world.stories.constants import BeatKind, BeatOutcome
from world.stories.factories import BeatFactory, StoryProgressFactory
from world.traits.factories import CheckOutcomeFactory


def _make_room(label: str = "EncounterOptionRoom") -> object:
    return ObjectDBFactory(db_key=label, db_typeclass_path="typeclasses.rooms.Room")


class EncounterOptionTestBase(TestCase):
    """Shared fixture: an ENCOUNTER option on an entry node of a beat-bound run."""

    def setUp(self) -> None:
        seed_scaling_defaults()
        self.room = _make_room()
        self.character = CharacterFactory(location=self.room)
        self.sheet = CharacterSheetFactory(character=self.character)

        self.beat = BeatFactory(kind=BeatKind.ENCOUNTER)
        self.scene = SceneFactory(location=self.room, is_active=True, running_beat=self.beat)

        self.template = MissionTemplateFactory()
        self.entry = MissionNodeFactory(template=self.template, key="entry", is_entry=True)
        self.instance = MissionInstanceFactory(template=self.template, source_beat=self.beat)
        self.instance.current_node = self.entry
        self.instance.save(update_fields=["current_node"])
        self.participant = MissionParticipantFactory(
            instance=self.instance, character=self.sheet, is_contract_holder=True
        )

        self.creature = CreatureTemplateFactory()
        self.option = MissionOptionFactory(
            node=self.entry,
            order=0,
            option_kind=OptionKind.ENCOUNTER,
            source_kind=OptionSource.AUTHORED,
            encounter_risk_level=RiskLevel.MODERATE,
        )
        MissionOptionOpponentLineFactory(
            option=self.option, creature_template=self.creature, count=2, order=0
        )


class PickEncounterOptionTests(EncounterOptionTestBase):
    """resolve_option on an ENCOUNTER option mints the pending deed + fight."""

    def test_pick_spawns_fight_and_pauses(self) -> None:
        deed = resolve_option(self.instance, self.entry, self.option, self.participant)

        self.assertIsNone(deed.outcome_id)
        encounter = CombatEncounter.objects.get(scenario_deed=deed)
        self.assertEqual(encounter.risk_level, self.option.encounter_risk_level)
        self.assertIsNone(encounter.story_beat_id)
        self.assertEqual(CombatOpponent.objects.filter(encounter=encounter).count(), 2)
        self.instance.refresh_from_db()
        self.assertTrue(self.instance.is_paused)

    def test_pick_refused_while_paused(self) -> None:
        resolve_option(self.instance, self.entry, self.option, self.participant)
        self.instance.refresh_from_db()

        with self.assertRaises(BeatActionError):
            resolve_beat_option(self.instance, self.character, option_id=self.option.pk)

    def test_beat_view_reports_pause(self) -> None:
        resolve_option(self.instance, self.entry, self.option, self.participant)
        self.instance.refresh_from_db()

        view = beat_for(self.instance, self.character)

        self.assertTrue(view.is_paused)


class CompleteEncounterOptionTests(TestCase):
    """ENCOUNTER_COMPLETED grades the pending deed's route, never a beat (#3565).

    Drives ``complete_encounter_for_option`` directly (and, in one test,
    ``encounter_completed_beat_handler`` with a hand-built payload) rather
    than the real ``complete_encounter`` completion seam: the reactive flow
    trigger's dispatch cache is populated the first time anything touches
    the room's ``trigger_handler`` (character placement, scene setup, the
    encounter's own opponent spawn all do), and
    ``TriggerHandler.on_trigger_added``'s invalidation is deferred to
    ``transaction.on_commit`` - which never fires inside a ``TestCase``'s
    rolled-back transaction - so a trigger installed *after* that first
    touch is invisible for the rest of the test. This is the brief's
    sanctioned fallback (Task 5 Step 1, test 2): exercise the real grading
    logic directly, plus a dedicated test that the handler delegates to it.
    """

    def setUp(self) -> None:
        seed_scaling_defaults()
        self.room = _make_room("CompleteEncounterOptionRoom")
        self.character = CharacterFactory(location=self.room)
        self.sheet = CharacterSheetFactory(character=self.character)

        self.beat = BeatFactory(kind=BeatKind.ENCOUNTER)
        self.scene = SceneFactory(location=self.room, is_active=True, running_beat=self.beat)
        # An active StoryProgress is required for on_mission_complete_for_beat to
        # actually grade the beat on a terminal route (test_fled_...).
        story = self.beat.episode.chapter.story
        story.character_sheet = self.sheet
        story.save()
        StoryProgressFactory(story=story, character_sheet=self.sheet)

        self.template = MissionTemplateFactory()
        self.entry = MissionNodeFactory(template=self.template, key="entry", is_entry=True)
        self.node_b = MissionNodeFactory(template=self.template, key="node-b")
        self.instance = MissionInstanceFactory(template=self.template, source_beat=self.beat)
        self.instance.current_node = self.entry
        self.instance.save(update_fields=["current_node"])
        self.participant = MissionParticipantFactory(
            instance=self.instance, character=self.sheet, is_contract_holder=True
        )

        self.creature = CreatureTemplateFactory()
        self.option = MissionOptionFactory(
            node=self.entry,
            order=0,
            option_kind=OptionKind.ENCOUNTER,
            source_kind=OptionSource.AUTHORED,
            encounter_risk_level=RiskLevel.MODERATE,
        )
        MissionOptionOpponentLineFactory(
            option=self.option, creature_template=self.creature, count=1, order=0
        )

        self.victory_tier = CheckOutcomeFactory(name="EncounterOptVictoryTier", success_level=5)
        self.fled_tier = CheckOutcomeFactory(name="EncounterOptFledTier", success_level=-3)
        EncounterOutcomeMapping.objects.create(
            outcome=EncounterOutcome.VICTORY,
            risk_level=self.option.encounter_risk_level,
            check_outcome=self.victory_tier,
        )
        EncounterOutcomeMapping.objects.create(
            outcome=EncounterOutcome.FLED,
            risk_level=self.option.encounter_risk_level,
            check_outcome=self.fled_tier,
        )
        # VICTORY tier routes onward (non-terminal); FLED tier is an
        # authored terminal FAILURE - FLED/ABANDONED are mapped tiers like
        # any other on a scenario ENCOUNTER option (#3565).
        MissionOptionRouteFactory(
            option=self.option, outcome_tier=self.victory_tier, target_node=self.node_b
        )
        self.fled_route = MissionOptionRouteFactory(
            option=self.option, outcome_tier=self.fled_tier, target_node=None
        )
        self.fled_route.beat_outcome = BeatOutcome.FAILURE
        self.fled_route.save()

        self.deed = resolve_option(self.instance, self.entry, self.option, self.participant)
        self.encounter = CombatEncounter.objects.get(scenario_deed=self.deed)

    def test_victory_routes_victory_tier_and_unpauses(self) -> None:
        self.encounter.outcome = EncounterOutcome.VICTORY
        self.encounter.save(update_fields=["outcome"])

        deed = complete_encounter_for_option(self.encounter)

        self.assertIsNotNone(deed)
        self.instance.refresh_from_db()
        self.assertEqual(deed.outcome_id, self.victory_tier.pk)
        self.assertEqual(self.instance.current_node_id, self.node_b.pk)
        self.assertFalse(self.instance.is_paused)

    def test_beat_untouched_until_terminal(self) -> None:
        self.encounter.outcome = EncounterOutcome.VICTORY
        self.encounter.save(update_fields=["outcome"])

        complete_encounter_for_option(self.encounter)

        self.beat.refresh_from_db()
        self.assertEqual(self.beat.outcome, BeatOutcome.UNSATISFIED)

    def test_fled_routes_the_authored_fled_tier(self) -> None:
        self.encounter.outcome = EncounterOutcome.FLED
        self.encounter.save(update_fields=["outcome"])

        deed = complete_encounter_for_option(self.encounter)

        self.assertIsNotNone(deed)
        self.beat.refresh_from_db()
        self.assertEqual(deed.outcome_id, self.fled_tier.pk)
        self.assertEqual(self.beat.outcome, BeatOutcome.FAILURE)
        self.assertEqual(self.beat.outcome_key, self.option.key)

    def test_missing_mapping_leaves_node_paused(self) -> None:
        # No EncounterOutcomeMapping row was authored for (DEFEAT, MODERATE) -
        # only VICTORY and FLED were, in setUp.
        self.encounter.outcome = EncounterOutcome.DEFEAT
        self.encounter.save(update_fields=["outcome"])

        with self.assertLogs("world.missions.services.encounter_option", level="ERROR"):
            result = complete_encounter_for_option(self.encounter)

        self.assertIsNone(result)
        self.deed.refresh_from_db()
        self.instance.refresh_from_db()
        self.assertIsNone(self.deed.outcome_id)
        self.assertTrue(self.instance.is_paused)

    def test_handler_delegates_to_complete_encounter_for_option(self) -> None:
        """The ENCOUNTER_COMPLETED handler routes a scenario deed's encounter here,
        never through the story-beat path, even when a story_beat/running_beat is
        also present (the scenario_deed check short-circuits first)."""
        self.encounter.outcome = EncounterOutcome.VICTORY
        self.encounter.save(update_fields=["outcome"])
        payload = EncounterCompletedPayload(
            encounter=self.encounter,
            outcome=str(self.encounter.outcome),
            scene=self.encounter.scene,
            room=self.encounter.room,
        )

        encounter_completed_beat_handler(payload=payload)

        self.deed.refresh_from_db()
        self.beat.refresh_from_db()
        self.assertEqual(self.deed.outcome_id, self.victory_tier.pk)
        # Delegated to the scenario route, never the story beat.
        self.assertEqual(self.beat.outcome, BeatOutcome.UNSATISFIED)
