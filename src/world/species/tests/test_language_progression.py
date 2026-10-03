"""Language training config and XP-lock tests (#4090 amendment)."""

from __future__ import annotations

from unittest import mock

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from evennia_extensions.factories import AccountFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.progression.factories import DevelopmentPointsFactory, ExperiencePointsDataFactory
from world.progression.models import TraitRatingUnlock, TraitXPCost, XPCostChart, XPCostEntry
from world.progression.models.rewards import (
    DevelopmentPoints,
    ExperiencePointsData,
    cumulative_dp_for_level,
)
from world.species.factories import LanguageFactory
from world.species.language_progression import (
    get_language_training_config,
    language_lock_rating,
    languages_at_lock,
    purchase_language_breakthrough,
)
from world.species.models import LanguageTrainingConfig
from world.traits.factories import TraitFactory
from world.traits.models import (
    CharacterTraitChange,
    CharacterTraitValue,
    TraitChangeSource,
    TraitType,
)


class LanguageTrainingConfigTests(TestCase):
    def setUp(self) -> None:
        LanguageTrainingConfig.objects.flush_singleton_cache()

    def test_accessor_lazily_creates_defaults(self) -> None:
        self.assertFalse(LanguageTrainingConfig.objects.exists())
        config = get_language_training_config()
        self.assertEqual(config.teacher_dp_per_session, 15)
        self.assertEqual(config.self_study_dp_per_session, 8)
        self.assertEqual(LanguageTrainingConfig.objects.count(), 1)

    def test_accessor_returns_the_edited_row(self) -> None:
        LanguageTrainingConfig.objects.create(
            pk=1, teacher_dp_per_session=40, self_study_dp_per_session=12
        )
        config = get_language_training_config()
        self.assertEqual(config.teacher_dp_per_session, 40)
        self.assertEqual(config.self_study_dp_per_session, 12)


class LanguageXPLockTests(TestCase):
    """award_points parks a LANGUAGE trait one below an authored TraitRatingUnlock."""

    def setUp(self) -> None:
        DevelopmentPoints.flush_instance_cache()
        CharacterTraitValue.flush_instance_cache()
        self.trait = TraitFactory(name="LockTestTongue", trait_type=TraitType.LANGUAGE)
        self.language = LanguageFactory(name="LockTestTongue", trait=self.trait)
        self.sheet = CharacterSheetFactory()
        CharacterTraitValue.objects.create(character=self.sheet, trait=self.trait, value=18)
        self.tracker = DevelopmentPointsFactory(
            character_sheet=self.sheet,
            trait=self.trait,
            total_earned=cumulative_dp_for_level(18),
        )

    def test_without_an_authored_lock_training_levels_freely(self) -> None:
        self.tracker.award_points(cumulative_dp_for_level(21) - self.tracker.total_earned)
        value = CharacterTraitValue.objects.get(character=self.sheet, trait=self.trait).value
        self.assertEqual(value, 21)
        self.assertIsNone(language_lock_rating(self.sheet, self.language))

    def test_training_parks_one_below_the_lock_and_surplus_dissipates(self) -> None:
        TraitRatingUnlock.objects.create(trait=self.trait, target_rating=20)
        level_ups = self.tracker.award_points(100_000)
        value = CharacterTraitValue.objects.get(character=self.sheet, trait=self.trait).value
        self.assertEqual(value, 19)
        self.assertEqual(level_ups[-1], (18, 19))
        self.tracker.refresh_from_db()
        self.assertEqual(self.tracker.total_earned, cumulative_dp_for_level(19))
        self.assertEqual(language_lock_rating(self.sheet, self.language), 20)

    def test_a_skill_trait_is_not_gated_by_award_points(self) -> None:
        skill_trait = TraitFactory(name="LockTestSkill", trait_type=TraitType.SKILL)
        TraitRatingUnlock.objects.create(trait=skill_trait, target_rating=20)
        CharacterTraitValue.objects.create(character=self.sheet, trait=skill_trait, value=18)
        tracker = DevelopmentPointsFactory(
            character_sheet=self.sheet, trait=skill_trait, total_earned=0
        )
        tracker.award_points(cumulative_dp_for_level(21))
        value = CharacterTraitValue.objects.get(character=self.sheet, trait=skill_trait).value
        self.assertEqual(value, 21)

    def test_a_non_language_award_makes_no_new_query(self) -> None:
        """The LANGUAGE gate returns before any query, so other traits pay nothing for it."""
        skill_trait = TraitFactory(name="LockQuerySkill", trait_type=TraitType.SKILL)
        TraitRatingUnlock.objects.create(trait=skill_trait, target_rating=20)
        gated = DevelopmentPointsFactory(
            character_sheet=CharacterSheetFactory(), trait=skill_trait, total_earned=0
        )
        ungated = DevelopmentPointsFactory(
            character_sheet=CharacterSheetFactory(), trait=skill_trait, total_earned=0
        )

        with CaptureQueriesContext(connection) as with_gate:
            gated.award_points(cumulative_dp_for_level(12))
        with (
            mock.patch.object(DevelopmentPoints, "_language_rating_ceiling", return_value=None),
            CaptureQueriesContext(connection) as without_gate,
        ):
            ungated.award_points(cumulative_dp_for_level(12))

        self.assertEqual(len(with_gate), len(without_gate))
        unlock_table = TraitRatingUnlock._meta.db_table
        self.assertFalse(any(unlock_table in query["sql"] for query in with_gate.captured_queries))


class PurchaseLanguageBreakthroughTests(TestCase):
    def setUp(self) -> None:
        DevelopmentPoints.flush_instance_cache()
        CharacterTraitValue.flush_instance_cache()
        self.account = AccountFactory(username="langlocktester")
        self.sheet = CharacterSheetFactory()
        self.sheet.character.db_account = self.account
        self.sheet.character.save()
        self.trait = TraitFactory(name="BuyTestTongue", trait_type=TraitType.LANGUAGE)
        self.language = LanguageFactory(name="BuyTestTongue", trait=self.trait)
        chart = XPCostChart.objects.create(name="BuyTestTongue chart")
        XPCostEntry.objects.create(chart=chart, level=30, xp_cost=60)
        TraitXPCost.objects.create(trait=self.trait, cost_chart=chart)
        TraitRatingUnlock.objects.create(trait=self.trait, target_rating=30)

    def test_not_parked_is_refused(self) -> None:
        CharacterTraitValue.objects.create(character=self.sheet, trait=self.trait, value=25)
        success, _message = purchase_language_breakthrough(self.sheet, self.language)
        self.assertFalse(success)

    def test_insufficient_xp_is_refused(self) -> None:
        CharacterTraitValue.objects.create(character=self.sheet, trait=self.trait, value=29)
        ExperiencePointsDataFactory(account=self.account, total_earned=10, total_spent=0)
        success, message = purchase_language_breakthrough(self.sheet, self.language)
        self.assertFalse(success)
        self.assertIn("insufficient xp", message.lower())

    def test_purchase_raises_value_records_change_and_resumes_dp(self) -> None:
        CharacterTraitValue.objects.create(character=self.sheet, trait=self.trait, value=29)
        DevelopmentPointsFactory(
            character_sheet=self.sheet, trait=self.trait, total_earned=cumulative_dp_for_level(29)
        )
        ExperiencePointsDataFactory(account=self.account, total_earned=100, total_spent=0)

        success, _message = purchase_language_breakthrough(self.sheet, self.language)

        self.assertTrue(success)
        value = CharacterTraitValue.objects.get(character=self.sheet, trait=self.trait).value
        self.assertEqual(value, 30)
        change = CharacterTraitChange.objects.get(character_sheet=self.sheet, trait=self.trait)
        self.assertEqual(change.source, TraitChangeSource.XP_BREAKTHROUGH)
        self.assertEqual((change.old_value, change.new_value), (29, 30))
        tracker = DevelopmentPoints.objects.get(character_sheet=self.sheet, trait=self.trait)
        self.assertEqual(tracker.total_earned, cumulative_dp_for_level(30))
        prospects = languages_at_lock(self.sheet)
        self.assertEqual(prospects, [])

    def test_prospect_lists_the_parked_language_and_cost(self) -> None:
        CharacterTraitValue.objects.create(character=self.sheet, trait=self.trait, value=29)
        prospects = languages_at_lock(self.sheet)
        self.assertEqual(len(prospects), 1)
        self.assertEqual(prospects[0].language, self.language)
        self.assertEqual(prospects[0].next_rating, 30)
        self.assertEqual(prospects[0].xp_cost, 60)

    def test_double_purchase_second_call_refused_not_parked(self) -> None:
        """A second purchase against the same breakthrough is refused, not re-spent (#4090)."""
        CharacterTraitValue.objects.create(character=self.sheet, trait=self.trait, value=29)
        DevelopmentPointsFactory(
            character_sheet=self.sheet, trait=self.trait, total_earned=cumulative_dp_for_level(29)
        )
        ExperiencePointsDataFactory(account=self.account, total_earned=200, total_spent=0)

        first_success, _message = purchase_language_breakthrough(self.sheet, self.language)
        self.assertTrue(first_success)

        second_success, message = purchase_language_breakthrough(self.sheet, self.language)
        self.assertFalse(second_success)
        self.assertEqual(message, f"Your {self.language.name} is not waiting at a breakthrough.")
        ledger = ExperiencePointsData.objects.get(account=self.account)
        self.assertEqual(ledger.total_spent, 60)

    def test_two_locks_after_buying_the_first_training_parks_at_the_second_minus_one(
        self,
    ) -> None:
        """Buying the 20 lock resumes training, which parks one below the still-authored
        30 lock from setUp (not past it) — #4090's chained-breakthrough case."""
        TraitRatingUnlock.objects.create(trait=self.trait, target_rating=20)
        CharacterTraitValue.objects.create(character=self.sheet, trait=self.trait, value=19)
        DevelopmentPointsFactory(
            character_sheet=self.sheet, trait=self.trait, total_earned=cumulative_dp_for_level(19)
        )
        ExperiencePointsDataFactory(account=self.account, total_earned=200, total_spent=0)

        success, _message = purchase_language_breakthrough(self.sheet, self.language)
        self.assertTrue(success)
        self.assertEqual(
            CharacterTraitValue.objects.get(character=self.sheet, trait=self.trait).value, 20
        )

        tracker = DevelopmentPoints.objects.get(character_sheet=self.sheet, trait=self.trait)
        tracker.award_points(100_000)
        self.assertEqual(
            CharacterTraitValue.objects.get(character=self.sheet, trait=self.trait).value, 29
        )

    def test_value_moving_between_the_read_and_the_lock_refuses_the_stale_purchase(self) -> None:
        """Simulates a race: something else moves the trait's value between the unlocked
        read (which still sees it parked at 29, below the 30 lock) and the locked
        re-read inside the atomic block. The re-check must catch the mismatch and
        refuse, rather than spend XP against a cost computed off the stale value
        (#4090 double-spend fix)."""
        trait_value = CharacterTraitValue.objects.create(
            character=self.sheet, trait=self.trait, value=29
        )
        ExperiencePointsDataFactory(account=self.account, total_earned=100, total_spent=0)

        real_select_for_update = CharacterTraitValue.objects.select_for_update

        def racing_select_for_update(*args: object, **kwargs: object) -> object:
            racer = CharacterTraitValue.objects.get(pk=trait_value.pk)
            racer.value = 30
            racer.save(update_fields=["value"])
            return real_select_for_update(*args, **kwargs)

        with mock.patch.object(
            CharacterTraitValue.objects,
            "select_for_update",
            side_effect=racing_select_for_update,
        ):
            success, message = purchase_language_breakthrough(self.sheet, self.language)

        self.assertFalse(success)
        self.assertEqual(message, f"Your {self.language.name} is not waiting at a breakthrough.")
        ledger = ExperiencePointsData.objects.get(account=self.account)
        self.assertEqual(ledger.total_spent, 0)
