"""Tests for fatigue periodic tasks."""

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.fatigue.models import FatiguePool
from world.fatigue.services import get_or_create_fatigue_pool
from world.fatigue.tasks import fatigue_dawn_reset_task, process_deferred_fatigue_resets
from world.roster.factories import PlayerDataFactory, RosterEntryFactory, RosterTenureFactory
from world.scenes.factories import SceneFactory, SceneParticipationFactory


def _create_character_with_account():
    """Create a CharacterSheet with a linked account via roster tenure.

    Returns (CharacterSheet, AccountDB).
    """
    sheet = CharacterSheetFactory()
    player_data = PlayerDataFactory()
    roster_entry = RosterEntryFactory(character=sheet.character)
    RosterTenureFactory(
        player_data=player_data,
        roster_entry=roster_entry,
    )
    return sheet, player_data.account


class FatigueDawnResetTaskTests(TestCase):
    """Tests for fatigue_dawn_reset_task."""

    def setUp(self):
        FatiguePool.flush_instance_cache()

    @classmethod
    def setUpTestData(cls):
        cls.sheet1, cls.account1 = _create_character_with_account()
        cls.sheet2, cls.account2 = _create_character_with_account()

    def test_resets_all_pools_when_no_active_scenes(self):
        """All fatigue pools are reset when no characters are in active scenes."""
        pool1 = get_or_create_fatigue_pool(self.sheet1)
        pool1.physical_current = 20
        pool1.save()

        pool2 = get_or_create_fatigue_pool(self.sheet2)
        pool2.social_current = 15
        pool2.save()

        fatigue_dawn_reset_task()

        pool1.refresh_from_db()
        pool2.refresh_from_db()
        assert pool1.physical_current == 0
        assert pool2.social_current == 0
        assert pool1.dawn_deferred is False
        assert pool2.dawn_deferred is False

    def test_defers_reset_for_character_in_active_scene(self):
        """Characters in active scenes get dawn_deferred=True, not a reset."""
        pool1 = get_or_create_fatigue_pool(self.sheet1)
        pool1.physical_current = 20
        pool1.save()

        pool2 = get_or_create_fatigue_pool(self.sheet2)
        pool2.social_current = 15
        pool2.save()

        # Put account1 in an active scene
        scene = SceneFactory(is_active=True)
        SceneParticipationFactory(scene=scene, account=self.account1)

        fatigue_dawn_reset_task()

        pool1.refresh_from_db()
        pool2.refresh_from_db()

        # Account1 is in scene: deferred, fatigue NOT reset
        assert pool1.physical_current == 20
        assert pool1.dawn_deferred is True

        # Account2 is NOT in scene: reset normally
        assert pool2.social_current == 0
        assert pool2.dawn_deferred is False

    def test_left_scene_not_deferred(self):
        """Characters who left a scene (left_at set) are not considered in-scene."""
        from django.utils import timezone

        pool = get_or_create_fatigue_pool(self.sheet1)
        pool.physical_current = 20
        pool.save()

        scene = SceneFactory(is_active=True)
        SceneParticipationFactory(scene=scene, account=self.account1, left_at=timezone.now())

        fatigue_dawn_reset_task()

        pool.refresh_from_db()
        assert pool.physical_current == 0
        assert pool.dawn_deferred is False

    def test_finished_scene_not_deferred(self):
        """Characters in finished (inactive) scenes are not deferred."""
        pool = get_or_create_fatigue_pool(self.sheet1)
        pool.physical_current = 20
        pool.save()

        scene = SceneFactory(is_active=False)
        SceneParticipationFactory(scene=scene, account=self.account1)

        fatigue_dawn_reset_task()

        pool.refresh_from_db()
        assert pool.physical_current == 0
        assert pool.dawn_deferred is False


class ProcessDeferredFatigueResetsTests(TestCase):
    """Tests for process_deferred_fatigue_resets."""

    def setUp(self):
        FatiguePool.flush_instance_cache()

    @classmethod
    def setUpTestData(cls):
        cls.sheet1, cls.account1 = _create_character_with_account()
        cls.sheet2, cls.account2 = _create_character_with_account()

    def test_resets_deferred_pool_for_scene_participant(self):
        """Deferred pools are reset when their account was in the finished scene."""
        pool = get_or_create_fatigue_pool(self.sheet1)
        pool.physical_current = 20
        pool.dawn_deferred = True
        pool.save()

        count = process_deferred_fatigue_resets({self.account1.pk})

        pool.refresh_from_db()
        assert pool.physical_current == 0
        assert pool.dawn_deferred is False
        assert count == 1

    def test_does_not_reset_deferred_pool_for_non_participant(self):
        """Deferred pools are NOT reset if the account was not in the scene."""
        pool = get_or_create_fatigue_pool(self.sheet1)
        pool.physical_current = 20
        pool.dawn_deferred = True
        pool.save()

        # Pass account2's ID, not account1's
        count = process_deferred_fatigue_resets({self.account2.pk})

        pool.refresh_from_db()
        assert pool.physical_current == 20
        assert pool.dawn_deferred is True
        assert count == 0

    def test_does_not_reset_non_deferred_pools(self):
        """Pools without dawn_deferred=True are not touched."""
        pool = get_or_create_fatigue_pool(self.sheet1)
        pool.physical_current = 20
        pool.dawn_deferred = False
        pool.save()

        count = process_deferred_fatigue_resets({self.account1.pk})

        pool.refresh_from_db()
        assert pool.physical_current == 20
        assert count == 0

    def test_multiple_deferred_resets(self):
        """Multiple deferred pools can be reset in one call."""
        pool1 = get_or_create_fatigue_pool(self.sheet1)
        pool1.physical_current = 20
        pool1.dawn_deferred = True
        pool1.save()

        pool2 = get_or_create_fatigue_pool(self.sheet2)
        pool2.social_current = 15
        pool2.dawn_deferred = True
        pool2.save()

        count = process_deferred_fatigue_resets({self.account1.pk, self.account2.pk})

        pool1.refresh_from_db()
        pool2.refresh_from_db()
        assert pool1.physical_current == 0
        assert pool2.social_current == 0
        assert count == 2
