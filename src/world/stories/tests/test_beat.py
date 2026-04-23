from django.core.exceptions import ValidationError
from django.test import TestCase

from world.achievements.factories import AchievementFactory
from world.codex.factories import CodexEntryFactory
from world.conditions.factories import ConditionTemplateFactory
from world.stories.constants import BeatOutcome, BeatPredicateType, BeatVisibility
from world.stories.factories import BeatFactory, EpisodeFactory


class BeatTests(TestCase):
    def test_default_beat_is_gm_marked(self):
        beat = BeatFactory()
        self.assertEqual(beat.predicate_type, BeatPredicateType.GM_MARKED)
        self.assertEqual(beat.outcome, BeatOutcome.UNSATISFIED)
        self.assertEqual(beat.visibility, BeatVisibility.HINTED)

    def test_character_level_beat_requires_required_level(self):
        episode = EpisodeFactory()
        beat = BeatFactory.build(
            episode=episode,
            predicate_type=BeatPredicateType.CHARACTER_LEVEL_AT_LEAST,
            required_level=None,
        )
        with self.assertRaises(ValidationError):
            beat.full_clean()

    def test_gm_marked_beat_rejects_required_level(self):
        episode = EpisodeFactory()
        beat = BeatFactory.build(
            episode=episode,
            predicate_type=BeatPredicateType.GM_MARKED,
            required_level=5,
        )
        with self.assertRaises(ValidationError):
            beat.full_clean()

    def test_beat_text_layers(self):
        beat = BeatFactory(
            internal_description="Real predicate: research project X",
            player_hint="Something about the night...",
            player_resolution_text="You learned the truth.",
        )
        self.assertIn("X", beat.internal_description)
        self.assertIn("night", beat.player_hint)
        self.assertIn("truth", beat.player_resolution_text)

    # --- ACHIEVEMENT_HELD invariants ---

    def test_achievement_held_beat_requires_required_achievement(self):
        episode = EpisodeFactory()
        beat = BeatFactory.build(
            episode=episode,
            predicate_type=BeatPredicateType.ACHIEVEMENT_HELD,
            required_achievement=None,
        )
        with self.assertRaises(ValidationError):
            beat.full_clean()

    def test_gm_marked_beat_rejects_required_achievement(self):
        episode = EpisodeFactory()
        achievement = AchievementFactory()
        beat = BeatFactory.build(
            episode=episode,
            predicate_type=BeatPredicateType.GM_MARKED,
            required_achievement=achievement,
        )
        with self.assertRaises(ValidationError):
            beat.full_clean()

    def test_character_level_beat_rejects_required_achievement(self):
        episode = EpisodeFactory()
        achievement = AchievementFactory()
        beat = BeatFactory.build(
            episode=episode,
            predicate_type=BeatPredicateType.CHARACTER_LEVEL_AT_LEAST,
            required_level=5,
            required_achievement=achievement,
        )
        with self.assertRaises(ValidationError):
            beat.full_clean()

    # --- CONDITION_HELD invariants ---

    def test_condition_held_beat_requires_required_condition_template(self):
        episode = EpisodeFactory()
        beat = BeatFactory.build(
            episode=episode,
            predicate_type=BeatPredicateType.CONDITION_HELD,
            required_condition_template=None,
        )
        with self.assertRaises(ValidationError):
            beat.full_clean()

    def test_gm_marked_beat_rejects_required_condition_template(self):
        episode = EpisodeFactory()
        template = ConditionTemplateFactory()
        beat = BeatFactory.build(
            episode=episode,
            predicate_type=BeatPredicateType.GM_MARKED,
            required_condition_template=template,
        )
        with self.assertRaises(ValidationError):
            beat.full_clean()

    def test_achievement_held_beat_rejects_required_condition_template(self):
        episode = EpisodeFactory()
        achievement = AchievementFactory()
        template = ConditionTemplateFactory()
        beat = BeatFactory.build(
            episode=episode,
            predicate_type=BeatPredicateType.ACHIEVEMENT_HELD,
            required_achievement=achievement,
            required_condition_template=template,
        )
        with self.assertRaises(ValidationError):
            beat.full_clean()

    # --- CODEX_ENTRY_UNLOCKED invariants ---

    def test_codex_entry_unlocked_beat_requires_required_codex_entry(self):
        episode = EpisodeFactory()
        beat = BeatFactory.build(
            episode=episode,
            predicate_type=BeatPredicateType.CODEX_ENTRY_UNLOCKED,
            required_codex_entry=None,
        )
        with self.assertRaises(ValidationError):
            beat.full_clean()

    def test_gm_marked_beat_rejects_required_codex_entry(self):
        episode = EpisodeFactory()
        entry = CodexEntryFactory()
        beat = BeatFactory.build(
            episode=episode,
            predicate_type=BeatPredicateType.GM_MARKED,
            required_codex_entry=entry,
        )
        with self.assertRaises(ValidationError):
            beat.full_clean()

    def test_condition_held_beat_rejects_required_codex_entry(self):
        episode = EpisodeFactory()
        template = ConditionTemplateFactory()
        entry = CodexEntryFactory()
        beat = BeatFactory.build(
            episode=episode,
            predicate_type=BeatPredicateType.CONDITION_HELD,
            required_condition_template=template,
            required_codex_entry=entry,
        )
        with self.assertRaises(ValidationError):
            beat.full_clean()
