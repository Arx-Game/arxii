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
    def test_resets_trackers_from_old_week(self) -> None:
        from world.character_sheets.factories import CharacterSheetFactory
        from world.game_clock.week_services import advance_game_week, get_current_game_week
        from world.journals.models import WeeklyJournalXP

        old_week = get_current_game_week()
        sheet = CharacterSheetFactory()
        tracker = WeeklyJournalXP.objects.create(
            character_sheet=sheet, posts_this_week=3, praised_this_week=True, game_week=old_week
        )

        advance_game_week()
        batch_journal_weekly_reset()

        WeeklyJournalXP.flush_instance_cache()
        tracker.refresh_from_db()
        self.assertEqual(tracker.posts_this_week, 0)
        self.assertFalse(tracker.praised_this_week)

    def test_skips_current_week_trackers(self) -> None:
        from world.character_sheets.factories import CharacterSheetFactory
        from world.game_clock.week_services import get_current_game_week
        from world.journals.models import WeeklyJournalXP

        current_week = get_current_game_week()
        sheet = CharacterSheetFactory()
        WeeklyJournalXP.objects.create(
            character_sheet=sheet, posts_this_week=2, game_week=current_week
        )

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

    def test_resets_old_week_relationships(self) -> None:
        """Relationship counters from a previous game week are reset."""
        from world.game_clock.week_services import advance_game_week, get_current_game_week
        from world.relationships.factories import CharacterRelationshipFactory
        from world.relationships.models import CharacterRelationship

        old_week = get_current_game_week()
        rel = CharacterRelationshipFactory(
            developments_this_week=3, changes_this_week=2, game_week=old_week
        )

        advance_game_week()
        batch_relationship_weekly_reset()

        CharacterRelationship.flush_instance_cache()
        rel.refresh_from_db()
        self.assertEqual(rel.developments_this_week, 0)
        self.assertEqual(rel.changes_this_week, 0)

    def test_skips_current_week_relationships(self) -> None:
        """Relationships in the current game week are not touched."""
        from world.game_clock.week_services import get_current_game_week
        from world.relationships.factories import CharacterRelationshipFactory

        current_week = get_current_game_week()
        rel = CharacterRelationshipFactory(
            developments_this_week=3,
            changes_this_week=2,
            game_week=current_week,
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


class Scope6TaskRegistrationTests(TestCase):
    """Phase 10: anima regen and condition decay scheduler tasks registered."""

    def setUp(self) -> None:
        from world.game_clock.task_registry import clear_registry

        clear_registry()

    def test_scope6_tasks_registered(self) -> None:
        from world.game_clock.task_registry import get_registered_tasks
        from world.game_clock.tasks import register_all_tasks

        register_all_tasks()

        keys = {t.task_key for t in get_registered_tasks()}
        self.assertIn("magic.anima_regen_daily", keys)
        self.assertIn("conditions.decay_daily", keys)

    def test_scope6_tasks_callables_runnable(self) -> None:
        """Smoke test: both new tasks' callables can be invoked without error."""
        from world.conditions.services import decay_all_conditions_tick
        from world.magic.models.anima import AnimaConfig
        from world.magic.services.anima import anima_regen_tick
        from world.mechanics.factories import PropertyFactory

        # Create the blocking property before calling anima_regen_tick
        config = AnimaConfig.get_singleton()
        PropertyFactory(name=config.daily_regen_blocking_property_key)

        # Empty DB is a fine smoke test — both functions bulk-query and return
        # summary dataclasses; no fixtures are required for a crash check.
        anima_summary = anima_regen_tick()
        self.assertEqual(anima_summary.examined, 0)

        decay_summary = decay_all_conditions_tick()
        # Just assert it returned something truthy-typed without raising.
        self.assertIsNotNone(decay_summary)
