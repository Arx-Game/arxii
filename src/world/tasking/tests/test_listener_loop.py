"""Listener-post loop tests (#2820 phase 3)."""

from django.test import TestCase

from evennia_extensions.factories import RoomProfileFactory
from world.assets.factories import NPCAssetFactory
from world.checks.factories import CheckTypeFactory
from world.checks.test_helpers import force_check_outcome
from world.roster.factories import RosterEntryFactory
from world.scenes.factories import SceneFactory
from world.secrets.constants import SecretProvenance
from world.secrets.models import SecretKnowledge
from world.secrets.services import author_secret
from world.tasking.constants import (
    LISTENER_BUZZ_BASE,
    LISTENER_BUZZ_PER_SCENE,
    LISTENER_BUZZ_PER_SECRET,
)
from world.tasking.listener_services import (
    HarvestCollectionError,
    ListenerPostError,
    NotPresentError,
    collect_harvest,
    create_listener_post,
    listener_sweep,
)
from world.traits.factories import CheckOutcomeFactory


class ListenerLoopTestBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.room = RoomProfileFactory()
        cls.asset = NPCAssetFactory()
        cls.handler = cls.asset.promoter_persona

    def _post(self, **kwargs):
        return create_listener_post(self.asset, self.room, self.handler, **kwargs)

    def _mint_room_secret(self):
        scene = SceneFactory(location=self.room.objectdb)
        subject = RosterEntryFactory()
        return author_secret(
            subject_sheet=subject.character_sheet,
            provenance=SecretProvenance.GM_AUTHORED,
            level=2,
            content="PLACEHOLDER something happened in the tavern.",
            scene=scene,
        )


class ListenerSweepTests(ListenerLoopTestBase):
    def test_quiet_week_accrues_base_only(self):
        post = self._post()
        listener_sweep()
        post.refresh_from_db()
        self.assertEqual(post.buzz, LISTENER_BUZZ_BASE)
        self.assertIsNotNone(post.last_sweep_at)

    def test_residue_accrues_and_threshold_banks_the_secret(self):
        secret = self._mint_room_secret()
        post = self._post()
        post.threshold = 30
        post.save(update_fields=["threshold"])
        listener_sweep()
        post.refresh_from_db()
        expected = LISTENER_BUZZ_BASE + LISTENER_BUZZ_PER_SCENE + LISTENER_BUZZ_PER_SECRET - 30
        self.assertEqual(post.buzz, expected)
        harvest = post.harvests.get()
        self.assertEqual(harvest.secret, secret)
        self.assertIsNone(harvest.collected_at)

    def test_failed_tradecraft_roll_accrues_nothing(self):
        botch = CheckOutcomeFactory(name="listener botch", success_level=-1)
        post = self._post(check_type=CheckTypeFactory())
        with force_check_outcome(botch):
            listener_sweep()
        post.refresh_from_db()
        self.assertEqual(post.buzz, 0)

    def test_room_seat_is_exclusive(self):
        self._post()
        rival_asset = NPCAssetFactory()
        with self.assertRaises(ListenerPostError):
            create_listener_post(rival_asset, self.room, rival_asset.promoter_persona)


class HarvestCollectionTests(ListenerLoopTestBase):
    def _post_with_harvest(self):
        secret = self._mint_room_secret()
        post = self._post()
        post.threshold = 10
        post.save(update_fields=["threshold"])
        listener_sweep()
        return post, secret

    def test_collection_requires_presence(self):
        post, _ = self._post_with_harvest()
        with self.assertRaises(NotPresentError):
            collect_harvest(post, self.handler)

    def test_collection_grants_secret_knowledge(self):
        post, secret = self._post_with_harvest()
        handler_entry = RosterEntryFactory(character_sheet=self.handler.character_sheet)
        character = self.handler.character_sheet.character
        character.db_location = self.room.objectdb
        character.save()
        clue = collect_harvest(post, self.handler)
        self.assertIsNotNone(clue)
        self.assertEqual(clue.target_secret, secret)
        self.assertTrue(
            SecretKnowledge.objects.filter(roster_entry=handler_entry, secret=secret).exists()
        )
        self.assertEqual(post.harvests.filter(collected_at__isnull=True).count(), 0)

    def test_nothing_pending_raises(self):
        post = self._post()
        with self.assertRaises(HarvestCollectionError):
            collect_harvest(post, self.handler)

    def test_cron_registered(self):
        from world.game_clock.task_registry import get_registered_tasks
        from world.game_clock.tasks import register_all_tasks

        register_all_tasks()
        keys = {t.task_key for t in get_registered_tasks()}
        self.assertIn("tasking.listener_sweep", keys)
