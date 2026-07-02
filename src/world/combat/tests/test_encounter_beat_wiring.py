"""Tests for the ENCOUNTER_COMPLETED → beat auto-wiring (#1746)."""

from django.db import IntegrityError, transaction
from django.test import TestCase
from evennia.utils.test_resources import EvenniaTestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.combat.beat_wiring import (
    classify_battle_outcome,
    install_encounter_beat_trigger,
    wire_encounter_beat_triggers,
)
from world.combat.constants import EncounterOutcome, RiskLevel
from world.combat.factories import CombatEncounterFactory
from world.combat.models import EncounterOutcomeMapping
from world.combat.services import complete_encounter
from world.stories.constants import (
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
from world.stories.models import StakeOutcome
from world.traits.models import CheckOutcome


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

    def test_mapping_allows_null_check_outcome(self) -> None:
        """A null check_outcome means 'resolve to PENDING_GM_REVIEW' (FLED/ABANDONED)."""
        mapping = EncounterOutcomeMapping.objects.create(
            outcome=EncounterOutcome.FLED,
            risk_level=RiskLevel.MODERATE,
            check_outcome=None,
        )
        self.assertIsNone(mapping.check_outcome)

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
    """classify_battle_outcome: (EncounterOutcome, risk_level) → CheckOutcome | None."""

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

    def test_unmapped_pair_returns_none(self) -> None:
        """A pair with no mapping row → None (signals PENDING_GM_REVIEW)."""
        encounter = CombatEncounterFactory(outcome=EncounterOutcome.FLED, risk_level=RiskLevel.LOW)
        self.assertIsNone(classify_battle_outcome(encounter))

    def test_null_check_outcome_mapping_returns_none(self) -> None:
        """A mapping row whose check_outcome is null → None (FLED/ABANDONED review)."""
        EncounterOutcomeMapping.objects.create(
            outcome=EncounterOutcome.ABANDONED,
            risk_level=RiskLevel.MODERATE,
            check_outcome=None,
        )
        encounter = CombatEncounterFactory(
            outcome=EncounterOutcome.ABANDONED, risk_level=RiskLevel.MODERATE
        )
        self.assertIsNone(classify_battle_outcome(encounter))

    def test_empty_outcome_raises_value_error(self) -> None:
        """An encounter with no outcome set is programmer error."""
        encounter = CombatEncounterFactory(outcome="")
        with self.assertRaises(ValueError):
            classify_battle_outcome(encounter)


class EncounterCompletedBeatWiringTests(EvenniaTestCase):
    """Integration: ENCOUNTER_COMPLETED resolves a linked OUTCOME_TIER beat."""

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
            outcome=EncounterOutcome.VICTORY, risk_level=RiskLevel.MODERATE
        )
        EpisodeSceneFactory(episode=episode, scene=encounter.scene)
        install_encounter_beat_trigger(encounter)

        complete_encounter(encounter, outcome=EncounterOutcome.VICTORY)

        beat.refresh_from_db()
        self.assertEqual(beat.outcome, BeatOutcome.SUCCESS)

    def test_fled_resolves_to_pending_gm_review(self) -> None:
        """A fled encounter resolves the linked beat to PENDING_GM_REVIEW."""
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
            outcome=EncounterOutcome.FLED, risk_level=RiskLevel.MODERATE
        )
        EpisodeSceneFactory(episode=episode, scene=encounter.scene)
        install_encounter_beat_trigger(encounter)

        complete_encounter(encounter, outcome=EncounterOutcome.FLED)

        beat.refresh_from_db()
        self.assertEqual(beat.outcome, BeatOutcome.PENDING_GM_REVIEW)

    def test_no_linked_beat_noops(self) -> None:
        """An encounter whose scene has no OUTCOME_TIER beat completes without error."""
        encounter = CombatEncounterFactory(
            outcome=EncounterOutcome.VICTORY, risk_level=RiskLevel.MODERATE
        )
        install_encounter_beat_trigger(encounter)
        # No EpisodeScene linking this scene to any beat — must not raise.
        complete_encounter(encounter, outcome=EncounterOutcome.VICTORY)

    def test_fled_fires_withdrawal_stakes_and_pends_the_rest(self) -> None:
        """FLED = withdrawal (#1770 PR2): a stake with an authored WITHDRAWAL
        branch resolves immediately (method=MACHINE); a stake without one pends
        with the beat's PENDING_GM_REVIEW for the GM's constrained pick.
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
        encounter = CombatEncounterFactory(
            outcome=EncounterOutcome.FLED, risk_level=RiskLevel.MODERATE
        )
        EpisodeSceneFactory(episode=episode, scene=encounter.scene)
        install_encounter_beat_trigger(encounter)

        complete_encounter(encounter, outcome=EncounterOutcome.FLED)

        beat.refresh_from_db()
        self.assertEqual(beat.outcome, BeatOutcome.PENDING_GM_REVIEW)
        outcome = StakeOutcome.objects.get(stake=authored)
        self.assertEqual(outcome.column, StakeResolutionColumn.WITHDRAWAL)
        self.assertEqual(outcome.method, StakeOutcomeMethod.MACHINE)
        self.assertEqual(outcome.resolution_id, withdrawal_branch.pk)
        self.assertFalse(StakeOutcome.objects.filter(stake=unauthored).exists())

    def test_fled_withdraws_even_when_a_mapping_row_is_authored(self) -> None:
        """Withdrawal is structural (#1770 PR2): a designer-authored
        EncounterOutcomeMapping tier for FLED is ignored — the beat still
        pends and the withdrawal branch fires; the mapped tier never grades
        the beat.
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
        encounter = CombatEncounterFactory(
            outcome=EncounterOutcome.FLED, risk_level=RiskLevel.MODERATE
        )
        EpisodeSceneFactory(episode=episode, scene=encounter.scene)
        install_encounter_beat_trigger(encounter)

        complete_encounter(encounter, outcome=EncounterOutcome.FLED)

        beat.refresh_from_db()
        self.assertEqual(beat.outcome, BeatOutcome.PENDING_GM_REVIEW)
        outcome = StakeOutcome.objects.get(stake=stake)
        self.assertEqual(outcome.column, StakeResolutionColumn.WITHDRAWAL)
        self.assertEqual(outcome.resolution_id, branch.pk)
