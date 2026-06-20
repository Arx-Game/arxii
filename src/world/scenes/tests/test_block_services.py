"""Block resolution + lifecycle (#1278, slice 1).

A block is mutual and keyed on the player (account). By default it's the exact persona pair;
account_level covers all the blocker's faces. The blocked player's *other* personas are NOT
coded-blocked (anti-derivation — that's the separate awareness layer).
"""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from evennia_extensions.factories import AccountFactory
from evennia_extensions.models import PlayerData
from world.scenes.block_services import (
    coded_block_active,
    finalize_expired_blocks,
    lift_block,
)
from world.scenes.factories import PersonaFactory
from world.scenes.models import Block


class BlockServiceTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.blocker = PlayerData.objects.get_or_create(account=AccountFactory())[0]
        cls.target = PlayerData.objects.get_or_create(account=AccountFactory())[0]
        cls.blocker_face = PersonaFactory(name="Blocker Face")
        cls.target_face = PersonaFactory(name="Target Face")
        cls.target_alt = PersonaFactory(name="Target Alt")

    def _pair_block(self, **kwargs):
        return Block.objects.create(
            owner=self.blocker,
            blocked_player=self.target,
            blocker_persona=self.blocker_face,
            blocked_persona=self.target_face,
            **kwargs,
        )

    def _active(self, persona_a, persona_b):
        return coded_block_active(
            player_a=self.blocker,
            persona_a=persona_a,
            player_b=self.target,
            persona_b=persona_b,
        )

    def test_exact_pair_is_blocked_in_both_directions(self) -> None:
        self._pair_block()
        # Mutual: the order of the sides doesn't matter.
        assert self._active(self.blocker_face, self.target_face) is True
        assert (
            coded_block_active(
                player_a=self.target,
                persona_a=self.target_face,
                player_b=self.blocker,
                persona_b=self.blocker_face,
            )
            is True
        )

    def test_blocked_players_other_persona_is_not_coded_blocked(self) -> None:
        # Anti-derivation: a persona-scoped block does NOT cover the target's other faces.
        self._pair_block()
        assert self._active(self.blocker_face, self.target_alt) is False

    def test_account_level_covers_any_blocker_face_against_the_blocked_persona(self) -> None:
        Block.objects.create(
            owner=self.blocker,
            blocked_player=self.target,
            blocker_persona=None,
            blocked_persona=self.target_face,
            account_level=True,
        )
        other_blocker_face = PersonaFactory(name="Blocker Alt")
        assert self._active(other_blocker_face, self.target_face) is True
        # Still scoped to the exact blocked face, not the target's alt.
        assert self._active(other_blocker_face, self.target_alt) is False

    def test_different_player_does_not_match(self) -> None:
        # The block follows the person: a stranger playing the same face isn't blocked.
        self._pair_block()
        stranger = PlayerData.objects.get_or_create(account=AccountFactory())[0]
        assert (
            coded_block_active(
                player_a=self.blocker,
                persona_a=self.blocker_face,
                player_b=stranger,
                persona_b=self.target_face,
            )
            is False
        )

    def test_lift_keeps_block_active_until_the_grace_period_elapses(self) -> None:
        block = self._pair_block()
        future = timezone.now() + timedelta(hours=1)
        lift_block(block, finalize_at=future)
        # Lifted but still within the grace window → still active.
        assert self._active(self.blocker_face, self.target_face) is True

    def test_finalize_removes_only_expired_blocks(self) -> None:
        block = self._pair_block()
        past = timezone.now() - timedelta(minutes=1)
        lift_block(block, finalize_at=past)
        # Past its grace window → inactive, and the cron removes it.
        assert self._active(self.blocker_face, self.target_face) is False
        assert finalize_expired_blocks(now=timezone.now()) == 1
        assert not Block.objects.filter(pk=block.pk).exists()
