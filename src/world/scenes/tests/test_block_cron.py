"""The block-finalize cron task (#1278): removes blocks whose lift grace period has elapsed."""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from evennia_extensions.factories import AccountFactory
from evennia_extensions.models import PlayerData
from world.scenes.factories import PersonaFactory
from world.scenes.models import Block
from world.scenes.tasks import block_finalize_task


class BlockFinalizeTaskTests(TestCase):
    def _block(self, **kwargs):
        owner = PlayerData.objects.get_or_create(account=AccountFactory())[0]
        blocked = PlayerData.objects.get_or_create(account=AccountFactory())[0]
        return Block.objects.create(
            owner=owner,
            blocked_player=blocked,
            blocker_persona=PersonaFactory(),
            blocked_persona=PersonaFactory(),
            **kwargs,
        )

    def test_finalizes_only_blocks_past_their_grace_window(self) -> None:
        active = self._block()  # never lifted
        lifting = self._block(pending_removal_at=timezone.now() + timedelta(hours=1))  # in grace
        expired = self._block(pending_removal_at=timezone.now() - timedelta(minutes=1))  # elapsed

        block_finalize_task()

        assert Block.objects.filter(pk=active.pk).exists()
        assert Block.objects.filter(pk=lifting.pk).exists()
        assert not Block.objects.filter(pk=expired.pk).exists()
