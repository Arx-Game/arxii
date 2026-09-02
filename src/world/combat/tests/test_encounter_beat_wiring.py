"""Tests for the ENCOUNTER_COMPLETED → beat auto-wiring (#1746, #3559)."""

from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from evennia.utils.test_resources import EvenniaTestCase

from flows.events.payloads import EncounterCompletedPayload
from world.character_sheets.factories import CharacterSheetFactory
from world.combat.beat_wiring import (
    classify_battle_outcome,
    encounter_completed_beat_handler,
    install_encounter_beat_trigger,
    wire_encounter_beat_triggers,
)
from world.combat.constants import EncounterOutcome, RiskLevel
from world.combat.factories import CombatEncounterFactory, CombatParticipantFactory
from world.combat.models import CombatEncounter, EncounterOutcomeMapping
from world.combat.services import complete_encounter
from world.stories.constants import (
    BeatKind,
    BeatOutcome,
    BeatPredicateType,
    StakeOutcomeMethod,
    StakeResolutionColumn,
    StoryScope,
)
from world.stories.factories import (
    BeatFactory,
    ChapterFactory,
    EpisodeFactory,
    EpisodeSceneFactory,
    StakeFactory,
    StakeResolutionFactory,
    StoryFactory,
    StoryProgressFactory,
)
from world.stories.models import BeatCompletion, StakeOutcome
from world.stories.services.stakes import activate_stakes_contract, get_open_activation
from world.traits.models import CheckOutcome


def _payload(encounter: CombatEncounter) -> EncounterCompletedPayload:
    """Build the ENCOUNTER_COMPLETED payload directly (#3559 handler-level tests)."""
    return EncounterCompletedPayload(
        encounter=encounter,
        outcome=str(encounter.outcome),
        scene=encounter.scene,
        room=encounter.room,
    )


class EncounterOutcomeMappingModelTests(TestCase):
    """Model-level tests for EncounterOutcomeMapping."""

    def test_mapping_unique_per_outcome_risk(self) -> None:
        """Each (outcome, risk_level) pair maps to exactly one CheckOutcome."""
        outcome = CheckOutcome.objects.create(name="Victory", success_level=5)
        EncounterOutcomeMapping.objects.create(
            outcome=EncounterOutcome.VICTORY,
            risk_level=RiskLevel.MODERATE,
            check_outcome=outcome,
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                EncounterOutcomeMapping.objects.create(
                    outcome=EncounterOutcome.VICTORY,
                    risk_level=RiskLevel.MODERATE,
                    check_outcome=outcome,
                )

    def test_check_outcome_is_required(self) -> None:
        """check_outcome is required content now (#3559) — no more null 'pend' row."""
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                EncounterOutcomeMapping.objects.create(
                    outcome=EncounterOutcome.VICTORY,
                    risk_level=RiskLevel.LETHAL,
                    check_outcome=None,
                )

    def test_str_representation(self) -> None:
        outcome = CheckOutcome.objects.create(name="Defeat", success_level=-5)
        mapping = EncounterOutcomeMapping.objects.create(
            outcome=EncounterOutcome.DEFEAT,
            risk_level=RiskLevel.LETHAL,
            check_outcome=outcome,
        )
        self.assertIn("defeat", str(mapping).lower())
        self.assertIn("lethal", str(mapping).lower())


class ClassifyBattleOutcomeTests(TestCase):
    """classify_battle_outcome: (EncounterOutcome, risk_level) → CheckOutcome."""

    def test_victory_returns_mapped_check_outcome(self) -> None:
        tier = CheckOutcome.objects.create(name="Decisive Victory", success_level=5)
        EncounterOutcomeMapping.objects.create(
            outcome=EncounterOutcome.VICTORY,
            risk_level=RiskLevel.LETHAL,
            check_outcome=tier,
        )
        encounter = CombatEncounterFactory(
            outcome=EncounterOutcome.VICTORY, risk_level=RiskLevel.LETHAL
        )
        self.assertEqual(classify_battle_outcome(encounter), tier)

    def test_unmapped_pair_raises(self) -> None:
        """A pair with no mapping row raises — missing content, not a runtime branch."""
        encounter = CombatEncounterFactory(outcome=EncounterOutcome.FLED, risk_level=RiskLevel.LOW)
        with self.assertRaises(EncounterOutcomeMapping.DoesNotExist):
            classify_battle_outcome(encounter)

    def test_empty_outcome_raises_value_error(self) -> None:
        """An encounter with no outcome set is programmer error."""
        encounter = CombatEncounterFactory(outcome="")
        with self.assertRaises(ValueError):
            classify_battle_outcome(encounter)


@override_settings(SEED_SAMPLE_CONTENT=True)
class EncounterCompletedBeatWiringTests(EvenniaTestCase):
    """Integration: ENCOUNTER_COMPLETED resolves at most one beat (#1746, #3559).

    flows.FlowDefinition/TriggerDefinition are content-repo-owned (#2698);
    wire_encounter_beat_triggers() only invents them under SEED_SAMPLE_CONTENT —
    this test drives the real reactive-trigger firing, so it opts in.
    """

    def setUp(self) -> None:
        wire_encounter_beat_triggers()  # seed TriggerDefinition + FlowDefinition

    def test_victory_resolves_linked_beat(self) -> None:
        """A victorious encounter with a linked OUTCOME_TIER beat completes it."""
        tier = CheckOutcome.objects.create(name="Victory Wire", success_level=5)
        EncounterOutcomeMapping.objects.create(
            outcome=EncounterOutcome.VICTORY,
            risk_level=RiskLevel.MODERATE,
            check_outcome=tier,
        )
        sheet = CharacterSheetFactory()
        story = StoryFactory(scope=StoryScope.CHARACTER, character_sheet=sheet)
        chapter = ChapterFactory(story=story)
        episode = EpisodeFactory(chapter=chapter)
        beat = BeatFactory(
            episode=episode,
            predicate_type=BeatPredicateType.OUTCOME_TIER,
            outcome=BeatOutcome.UNSATISFIED,
        )
        StoryProgressFactory(story=story, character_sheet=sheet)
        encounter = CombatEncounterFactory(
            outcome=EncounterOutcome.VICTORY, risk_level=RiskLevel.MODERATE, story_beat=beat
        )
        EpisodeSceneFactory(episode=episode, scene=encounter.scene)
        install_encounter_beat_trigger(encounter)

        complete_encounter(encounter, outcome=EncounterOutcome.VICTORY)

        beat.refresh_from_db()
        self.assertEqual(beat.outcome, BeatOutcome.SUCCESS)

    def test_no_linked_beat_noops(self) -> None:
        """An encounter with no routed beat and no running beat completes without error."""
        encounter = CombatEncounterFactory(
            outcome=EncounterOutcome.VICTORY, risk_level=RiskLevel.MODERATE
        )
        install_encounter_beat_trigger(encounter)
        # No story_beat, no scene.running_beat — must not raise.
        complete_encounter(encounter, outcome=EncounterOutcome.VICTORY)

    def test_unlinked_encounter_grades_nothing(self) -> None:
        """No story_beat and no running ENCOUNTER beat: the episode's beat stays open."""
        sheet = CharacterSheetFactory()
        story = StoryFactory(scope=StoryScope.CHARACTER, character_sheet=sheet)
        chapter = ChapterFactory(story=story)
        episode = EpisodeFactory(chapter=chapter)
        beat = BeatFactory(
            episode=episode,
            predicate_type=BeatPredicateType.OUTCOME_TIER,
            outcome=BeatOutcome.UNSATISFIED,
        )
        StoryProgressFactory(story=story, character_sheet=sheet)
        tier = CheckOutcome.objects.create(name="Unlinked Victory", success_level=5)
        EncounterOutcomeMapping.objects.create(
            outcome=EncounterOutcome.VICTORY,
            risk_level=RiskLevel.MODERATE,
            check_outcome=tier,
        )
        encounter = CombatEncounterFactory(
            outcome=EncounterOutcome.VICTORY, risk_level=RiskLevel.MODERATE
        )
        EpisodeSceneFactory(episode=episode, scene=encounter.scene)

        encounter_completed_beat_handler(payload=_payload(encounter))

        beat.refresh_from_db()
        self.assertEqual(beat.outcome, BeatOutcome.UNSATISFIED)

    def test_running_encounter_beat_is_graded(self) -> None:
        """scene.running_beat of kind ENCOUNTER grades even with no explicit story_beat."""
        sheet = CharacterSheetFactory()
        story = StoryFactory(scope=StoryScope.CHARACTER, character_sheet=sheet)
        chapter = ChapterFactory(story=story)
        episode = EpisodeFactory(chapter=chapter)
        beat = BeatFactory(
            episode=episode,
            predicate_type=BeatPredicateType.OUTCOME_TIER,
            outcome=BeatOutcome.UNSATISFIED,
            kind=BeatKind.ENCOUNTER,
        )
        StoryProgressFactory(story=story, character_sheet=sheet)
        tier = CheckOutcome.objects.create(name="Running Victory", success_level=5)
        EncounterOutcomeMapping.objects.create(
            outcome=EncounterOutcome.VICTORY,
            risk_level=RiskLevel.MODERATE,
            check_outcome=tier,
        )
        encounter = CombatEncounterFactory(
            outcome=EncounterOutcome.VICTORY, risk_level=RiskLevel.MODERATE
        )
        encounter.scene.running_beat = beat
        encounter.scene.save(update_fields=["running_beat"])

        encounter_completed_beat_handler(payload=_payload(encounter))

        beat.refresh_from_db()
        self.assertEqual(beat.outcome, BeatOutcome.SUCCESS)

    def test_running_beat_of_other_kind_is_not_graded(self) -> None:
        """A running beat that isn't kind ENCOUNTER never grades from a fight."""
        sheet = CharacterSheetFactory()
        story = StoryFactory(scope=StoryScope.CHARACTER, character_sheet=sheet)
        chapter = ChapterFactory(story=story)
        episode = EpisodeFactory(chapter=chapter)
        beat = BeatFactory(
            episode=episode,
            predicate_type=BeatPredicateType.OUTCOME_TIER,
            outcome=BeatOutcome.UNSATISFIED,
            kind=BeatKind.SITUATION,
        )
        StoryProgressFactory(story=story, character_sheet=sheet)
        tier = CheckOutcome.objects.create(name="Situation Victory", success_level=5)
        EncounterOutcomeMapping.objects.create(
            outcome=EncounterOutcome.VICTORY,
            risk_level=RiskLevel.MODERATE,
            check_outcome=tier,
        )
        encounter = CombatEncounterFactory(
            outcome=EncounterOutcome.VICTORY, risk_level=RiskLevel.MODERATE
        )
        encounter.scene.running_beat = beat
        encounter.scene.save(update_fields=["running_beat"])

        encounter_completed_beat_handler(payload=_payload(encounter))

        beat.refresh_from_db()
        self.assertEqual(beat.outcome, BeatOutcome.UNSATISFIED)

    def test_fled_leaves_beat_open_and_resolves_withdrawal(self) -> None:
        """FLED never grades the beat (#3559): the party walked away from the wager,
        and resolve_stakes_for_withdrawal fires the open stake's WITHDRAWAL branch.
        """
        sheet = CharacterSheetFactory()
        story = StoryFactory(scope=StoryScope.CHARACTER, character_sheet=sheet)
        chapter = ChapterFactory(story=story)
        episode = EpisodeFactory(chapter=chapter)
        beat = BeatFactory(
            episode=episode,
            predicate_type=BeatPredicateType.OUTCOME_TIER,
            outcome=BeatOutcome.UNSATISFIED,
        )
        stake = StakeFactory(beat=beat)
        branch = StakeResolutionFactory(stake=stake, column=StakeResolutionColumn.WITHDRAWAL)
        StoryProgressFactory(story=story, character_sheet=sheet)
        activate_stakes_contract(beat, [sheet])
        encounter = CombatEncounterFactory(
            outcome=EncounterOutcome.FLED, risk_level=RiskLevel.MODERATE, story_beat=beat
        )
        CombatParticipantFactory(encounter=encounter, character_sheet=sheet)

        encounter_completed_beat_handler(payload=_payload(encounter))

        beat.refresh_from_db()
        self.assertEqual(beat.outcome, BeatOutcome.UNSATISFIED)
        outcome = StakeOutcome.objects.get(stake=stake)
        self.assertEqual(outcome.column, StakeResolutionColumn.WITHDRAWAL)
        self.assertEqual(outcome.method, StakeOutcomeMethod.MACHINE)
        self.assertEqual(outcome.resolution_id, branch.pk)
        self.assertIsNone(get_open_activation(beat))

    def test_fled_fires_every_open_stake_authored_or_not(self) -> None:
        """FLED resolves every open stake (#3559): an authored WITHDRAWAL branch
        fires; a stake with no authored branch still gets an audit-honest,
        resolution-less StakeOutcome rather than being left to a GM's pick.
        """
        sheet = CharacterSheetFactory()
        story = StoryFactory(scope=StoryScope.CHARACTER, character_sheet=sheet)
        chapter = ChapterFactory(story=story)
        episode = EpisodeFactory(chapter=chapter)
        beat = BeatFactory(
            episode=episode,
            predicate_type=BeatPredicateType.OUTCOME_TIER,
            outcome=BeatOutcome.UNSATISFIED,
        )
        authored = StakeFactory(beat=beat)
        withdrawal_branch = StakeResolutionFactory(
            stake=authored, column=StakeResolutionColumn.WITHDRAWAL
        )
        unauthored = StakeFactory(beat=beat)
        StoryProgressFactory(story=story, character_sheet=sheet)
        activate_stakes_contract(beat, [sheet])
        encounter = CombatEncounterFactory(
            outcome=EncounterOutcome.FLED, risk_level=RiskLevel.MODERATE, story_beat=beat
        )
        CombatParticipantFactory(encounter=encounter, character_sheet=sheet)

        encounter_completed_beat_handler(payload=_payload(encounter))

        beat.refresh_from_db()
        self.assertEqual(beat.outcome, BeatOutcome.UNSATISFIED)
        authored_outcome = StakeOutcome.objects.get(stake=authored)
        self.assertEqual(authored_outcome.column, StakeResolutionColumn.WITHDRAWAL)
        self.assertEqual(authored_outcome.resolution_id, withdrawal_branch.pk)
        unauthored_outcome = StakeOutcome.objects.get(stake=unauthored)
        self.assertEqual(unauthored_outcome.column, StakeResolutionColumn.WITHDRAWAL)
        self.assertIsNone(unauthored_outcome.resolution_id)

    def test_fled_withdraws_even_when_a_mapping_row_is_authored(self) -> None:
        """Withdrawal is structural (#1770 PR2, #3559): a designer-authored
        EncounterOutcomeMapping tier for FLED is never consulted — the beat
        still stays open and the withdrawal branch fires regardless.
        """
        mapped_tier = CheckOutcome.objects.create(name="Fled Mapped Tier", success_level=5)
        EncounterOutcomeMapping.objects.create(
            outcome=EncounterOutcome.FLED,
            risk_level=RiskLevel.MODERATE,
            check_outcome=mapped_tier,
        )
        sheet = CharacterSheetFactory()
        story = StoryFactory(scope=StoryScope.CHARACTER, character_sheet=sheet)
        chapter = ChapterFactory(story=story)
        episode = EpisodeFactory(chapter=chapter)
        beat = BeatFactory(
            episode=episode,
            predicate_type=BeatPredicateType.OUTCOME_TIER,
            outcome=BeatOutcome.UNSATISFIED,
        )
        stake = StakeFactory(beat=beat)
        branch = StakeResolutionFactory(stake=stake, column=StakeResolutionColumn.WITHDRAWAL)
        StoryProgressFactory(story=story, character_sheet=sheet)
        activate_stakes_contract(beat, [sheet])
        encounter = CombatEncounterFactory(
            outcome=EncounterOutcome.FLED, risk_level=RiskLevel.MODERATE, story_beat=beat
        )
        CombatParticipantFactory(encounter=encounter, character_sheet=sheet)

        encounter_completed_beat_handler(payload=_payload(encounter))

        beat.refresh_from_db()
        self.assertEqual(beat.outcome, BeatOutcome.UNSATISFIED)
        outcome = StakeOutcome.objects.get(stake=stake)
        self.assertEqual(outcome.column, StakeResolutionColumn.WITHDRAWAL)
        self.assertEqual(outcome.resolution_id, branch.pk)

    def test_missing_mapping_logs_and_leaves_beat_open(self) -> None:
        """A non-withdrawal outcome with no authored mapping row is content, not
        a pause (#3559): it's logged as an error and the beat is left open.
        """
        sheet = CharacterSheetFactory()
        story = StoryFactory(scope=StoryScope.CHARACTER, character_sheet=sheet)
        chapter = ChapterFactory(story=story)
        episode = EpisodeFactory(chapter=chapter)
        beat = BeatFactory(
            episode=episode,
            predicate_type=BeatPredicateType.OUTCOME_TIER,
            outcome=BeatOutcome.UNSATISFIED,
        )
        StoryProgressFactory(story=story, character_sheet=sheet)
        encounter = CombatEncounterFactory(
            outcome=EncounterOutcome.VICTORY, risk_level=RiskLevel.MODERATE, story_beat=beat
        )
        # No EncounterOutcomeMapping row for (VICTORY, MODERATE).

        with self.assertLogs("world.combat.beat_wiring", level="ERROR"):
            encounter_completed_beat_handler(payload=_payload(encounter))

        beat.refresh_from_db()
        self.assertEqual(beat.outcome, BeatOutcome.UNSATISFIED)

    def test_story_beat_routes_to_only_that_beat(self) -> None:
        """Two beats share one scene; only the encounter's own story_beat resolves."""
        sheet = CharacterSheetFactory()
        story = StoryFactory(scope=StoryScope.CHARACTER, character_sheet=sheet)
        chapter = ChapterFactory(story=story)
        episode = EpisodeFactory(chapter=chapter)
        gate_beat = BeatFactory(
            episode=episode,
            predicate_type=BeatPredicateType.OUTCOME_TIER,
            outcome=BeatOutcome.UNSATISFIED,
        )
        civilians_beat = BeatFactory(
            episode=episode,
            predicate_type=BeatPredicateType.OUTCOME_TIER,
            outcome=BeatOutcome.UNSATISFIED,
        )
        StoryProgressFactory(story=story, character_sheet=sheet)
        tier = CheckOutcome.objects.create(name="Front Victory", success_level=5)
        EncounterOutcomeMapping.objects.create(
            outcome=EncounterOutcome.VICTORY,
            risk_level=RiskLevel.MODERATE,
            check_outcome=tier,
        )
        encounter = CombatEncounterFactory(
            outcome=EncounterOutcome.VICTORY,
            risk_level=RiskLevel.MODERATE,
            story_beat=gate_beat,
        )
        EpisodeSceneFactory(episode=episode, scene=encounter.scene)
        install_encounter_beat_trigger(encounter)

        complete_encounter(encounter, outcome=EncounterOutcome.VICTORY)

        gate_beat.refresh_from_db()
        civilians_beat.refresh_from_db()
        self.assertEqual(gate_beat.outcome, BeatOutcome.SUCCESS)
        self.assertEqual(civilians_beat.outcome, BeatOutcome.UNSATISFIED)

    def test_story_beat_set_but_already_resolved_is_a_noop(self) -> None:
        """A routed story_beat that's already resolved (not UNSATISFIED) is untouched.

        Guards the gradability check in beat_for_scene_conclusion: if a future
        refactor dropped it, a routed encounter would incorrectly stamp its
        outcome onto an already-resolved beat instead of no-opping.
        """
        sheet = CharacterSheetFactory()
        story = StoryFactory(scope=StoryScope.CHARACTER, character_sheet=sheet)
        chapter = ChapterFactory(story=story)
        episode = EpisodeFactory(chapter=chapter)
        beat = BeatFactory(
            episode=episode,
            predicate_type=BeatPredicateType.OUTCOME_TIER,
            outcome=BeatOutcome.SUCCESS,
        )
        StoryProgressFactory(story=story, character_sheet=sheet)
        encounter = CombatEncounterFactory(
            outcome=EncounterOutcome.VICTORY,
            risk_level=RiskLevel.MODERATE,
            story_beat=beat,
        )
        EpisodeSceneFactory(episode=episode, scene=encounter.scene)
        install_encounter_beat_trigger(encounter)

        complete_encounter(encounter, outcome=EncounterOutcome.VICTORY)

        beat.refresh_from_db()
        self.assertEqual(beat.outcome, BeatOutcome.SUCCESS)
        self.assertFalse(BeatCompletion.objects.filter(beat=beat).exists())


class CombatEncounterStoryBeatFieldTests(EvenniaTestCase):
    """Model-level: story_beat is a plain nullable FK, no cascade surprises."""

    def test_story_beat_defaults_to_none(self) -> None:
        encounter = CombatEncounterFactory()
        self.assertIsNone(encounter.story_beat)

    def test_story_beat_survives_beat_deletion_as_set_null(self) -> None:
        sheet = CharacterSheetFactory()
        story = StoryFactory(scope=StoryScope.CHARACTER, character_sheet=sheet)
        chapter = ChapterFactory(story=story)
        episode = EpisodeFactory(chapter=chapter)
        beat = BeatFactory(episode=episode)
        encounter = CombatEncounterFactory(story_beat=beat)
        beat.delete()
        CombatEncounter.flush_instance_cache()
        encounter.refresh_from_db()
        self.assertIsNone(encounter.story_beat)
