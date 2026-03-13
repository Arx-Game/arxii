"""Tests for periodic batch task functions."""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from world.game_clock.tasks import (
    batch_ap_daily_regen,
    batch_ap_weekly_regen,
    batch_condition_expiration_cleanup,
    batch_form_expiration_cleanup,
    batch_journal_weekly_reset,
    batch_relationship_weekly_reset,
)


class BatchJournalWeeklyResetTests(TestCase):
    def test_resets_stale_trackers(self) -> None:
        from world.character_sheets.factories import CharacterSheetFactory
        from world.journals.models import WeeklyJournalXP

        sheet = CharacterSheetFactory()
        tracker = WeeklyJournalXP.objects.create(
            character_sheet=sheet, posts_this_week=3, praised_this_week=True
        )
        tracker.week_reset_at = timezone.now() - timedelta(days=8)
        tracker.save(update_fields=["week_reset_at"])

        batch_journal_weekly_reset()

        tracker.refresh_from_db()
        self.assertEqual(tracker.posts_this_week, 0)
        self.assertFalse(tracker.praised_this_week)

    def test_skips_fresh_trackers(self) -> None:
        from world.character_sheets.factories import CharacterSheetFactory
        from world.journals.models import WeeklyJournalXP

        sheet = CharacterSheetFactory()
        WeeklyJournalXP.objects.create(character_sheet=sheet, posts_this_week=2)

        batch_journal_weekly_reset()

        tracker = WeeklyJournalXP.objects.get(character_sheet=sheet)
        self.assertEqual(tracker.posts_this_week, 2)


class BatchApDailyRegenTests(TestCase):
    """Tests for batch AP daily regen with modifier annotations."""

    @classmethod
    def setUpTestData(cls) -> None:
        from evennia_extensions.factories import CharacterFactory
        from world.action_points.factories import ActionPointConfigFactory
        from world.mechanics.factories import ModifierCategoryFactory, ModifierTargetFactory

        cls.config = ActionPointConfigFactory(daily_regen=5, is_active=True)
        cls.ap_category = ModifierCategoryFactory(name="action_points")
        cls.daily_target = ModifierTargetFactory(name="ap_daily_regen", category=cls.ap_category)
        cls.max_target = ModifierTargetFactory(name="ap_maximum", category=cls.ap_category)

        # Character with sheet (for modifiers)
        cls.character = CharacterFactory()

    def test_basic_regen_no_modifiers(self) -> None:
        """Pools regenerate at base rate without modifiers."""
        from world.action_points.factories import ActionPointPoolFactory

        pool = ActionPointPoolFactory(character=self.character, current=100, maximum=200)

        batch_ap_daily_regen()

        pool.refresh_from_db()
        self.assertEqual(pool.current, 105)

    def test_skips_pools_at_maximum(self) -> None:
        """Pools already at maximum are not updated."""
        from world.action_points.factories import ActionPointPoolFactory

        pool = ActionPointPoolFactory(character=self.character, current=200, maximum=200)

        batch_ap_daily_regen()

        pool.refresh_from_db()
        self.assertEqual(pool.current, 200)

    def test_regen_with_positive_modifier(self) -> None:
        """Positive modifier increases regen amount in batch."""
        from world.action_points.factories import ActionPointPoolFactory
        from world.character_sheets.factories import CharacterSheetFactory
        from world.distinctions.factories import (
            CharacterDistinctionFactory,
            DistinctionEffectFactory,
        )
        from world.mechanics.models import CharacterModifier, ModifierSource

        sheet = CharacterSheetFactory(character=self.character)
        effect = DistinctionEffectFactory(target=self.daily_target, value_per_rank=3)
        char_dist = CharacterDistinctionFactory(character=self.character)
        source = ModifierSource.objects.create(
            distinction_effect=effect, character_distinction=char_dist
        )
        CharacterModifier.objects.create(
            character=sheet, target=effect.target, value=3, source=source
        )

        pool = ActionPointPoolFactory(character=self.character, current=100, maximum=200)

        batch_ap_daily_regen()

        pool.refresh_from_db()
        self.assertEqual(pool.current, 108)  # 5 base + 3 modifier

    def test_regen_with_max_modifier(self) -> None:
        """Maximum modifier allows regen beyond base maximum."""
        from world.action_points.factories import ActionPointPoolFactory
        from world.character_sheets.factories import CharacterSheetFactory
        from world.distinctions.factories import (
            CharacterDistinctionFactory,
            DistinctionEffectFactory,
        )
        from world.mechanics.models import CharacterModifier, ModifierSource

        sheet = CharacterSheetFactory(character=self.character)
        effect = DistinctionEffectFactory(target=self.max_target, value_per_rank=100)
        char_dist = CharacterDistinctionFactory(character=self.character)
        source = ModifierSource.objects.create(
            distinction_effect=effect, character_distinction=char_dist
        )
        CharacterModifier.objects.create(
            character=sheet, target=effect.target, value=100, source=source
        )

        # At base max but below effective max (200 + 100 = 300)
        pool = ActionPointPoolFactory(character=self.character, current=200, maximum=200)

        batch_ap_daily_regen()

        pool.refresh_from_db()
        self.assertEqual(pool.current, 205)  # Still has room under effective max of 300


class BatchApWeeklyRegenTests(TestCase):
    """Tests for batch AP weekly regen."""

    @classmethod
    def setUpTestData(cls) -> None:
        from world.mechanics.factories import ModifierCategoryFactory, ModifierTargetFactory

        ap_category = ModifierCategoryFactory(name="action_points")
        ModifierTargetFactory(name="ap_weekly_regen", category=ap_category)
        ModifierTargetFactory(name="ap_maximum", category=ap_category)

    def test_basic_weekly_regen(self) -> None:
        """Pools regenerate at weekly rate."""
        from evennia_extensions.factories import CharacterFactory
        from world.action_points.factories import ActionPointConfigFactory, ActionPointPoolFactory

        ActionPointConfigFactory(weekly_regen=100, is_active=True)
        character = CharacterFactory()
        pool = ActionPointPoolFactory(character=character, current=50, maximum=200)

        batch_ap_weekly_regen()

        pool.refresh_from_db()
        self.assertEqual(pool.current, 150)


class BatchRelationshipWeeklyResetTests(TestCase):
    """Tests for batch relationship weekly reset."""

    def test_resets_stale_relationships(self) -> None:
        """Stale relationship counters are reset."""
        from world.relationships.factories import CharacterRelationshipFactory

        rel = CharacterRelationshipFactory(developments_this_week=3, changes_this_week=2)
        rel.week_reset_at = timezone.now() - timedelta(days=8)
        rel.save(update_fields=["week_reset_at"])

        batch_relationship_weekly_reset()

        rel.refresh_from_db()
        self.assertEqual(rel.developments_this_week, 0)
        self.assertEqual(rel.changes_this_week, 0)

    def test_skips_recently_reset_relationships(self) -> None:
        """Relationships reset within the last week are not touched."""
        from world.relationships.factories import CharacterRelationshipFactory

        rel = CharacterRelationshipFactory(
            developments_this_week=3,
            changes_this_week=2,
            week_reset_at=timezone.now(),
        )

        batch_relationship_weekly_reset()

        rel.refresh_from_db()
        self.assertEqual(rel.developments_this_week, 3)


class BatchFormExpirationTests(TestCase):
    def test_deletes_expired_real_time_changes(self) -> None:
        from world.forms.factories import TemporaryFormChangeFactory
        from world.forms.models import DurationType, TemporaryFormChange

        expired = TemporaryFormChangeFactory(
            duration_type=DurationType.REAL_TIME,
            expires_at=timezone.now() - timedelta(hours=1),
        )
        active = TemporaryFormChangeFactory(
            duration_type=DurationType.REAL_TIME,
            expires_at=timezone.now() + timedelta(hours=1),
        )
        permanent = TemporaryFormChangeFactory(
            duration_type=DurationType.UNTIL_REMOVED,
        )

        batch_form_expiration_cleanup()

        remaining_pks = set(TemporaryFormChange.objects.values_list("pk", flat=True))
        self.assertNotIn(expired.pk, remaining_pks)
        self.assertIn(active.pk, remaining_pks)
        self.assertIn(permanent.pk, remaining_pks)


class BatchConditionExpirationTests(TestCase):
    def test_deletes_expired_conditions(self) -> None:
        from world.conditions.factories import ConditionInstanceFactory
        from world.conditions.models import ConditionInstance

        expired = ConditionInstanceFactory(
            expires_at=timezone.now() - timedelta(hours=1),
        )
        active = ConditionInstanceFactory(
            expires_at=timezone.now() + timedelta(hours=1),
        )
        no_expiry = ConditionInstanceFactory(expires_at=None)

        batch_condition_expiration_cleanup()

        remaining_pks = set(ConditionInstance.objects.values_list("pk", flat=True))
        self.assertNotIn(expired.pk, remaining_pks)
        self.assertIn(active.pk, remaining_pks)
        self.assertIn(no_expiry.pk, remaining_pks)
