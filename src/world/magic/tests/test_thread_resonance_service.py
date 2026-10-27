"""The retune's locked re-check and its race with another retune (slice 6 of #4672).

Unit tests because no journey can reach them: each needs another process to act between
the moment this one read a row and the moment it writes. The tests write rows behind the
identity map's back, or hide a row from the lookup, which is what that other process does.
"""

from __future__ import annotations

from unittest import mock

from django.test import TestCase

from world.magic.exceptions import ThreadAnchorTakenError, ThreadResonanceChangeError
from world.magic.factories import ResonanceFactory, ThreadFactory, ensure_conversion_pairs
from world.magic.models import Thread
from world.magic.services.thread_resonance import (
    THREAD_MOVED_MESSAGE,
    change_thread_resonance,
)


class AThreadMovedElsewhereIsRefused(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        celestial, _primal, _abyssal = ensure_conversion_pairs()
        cls.bene = ResonanceFactory(name="Bene", affinity=celestial)
        cls.lumen = ResonanceFactory(name="Lumen", affinity=celestial)
        cls.aurum = ResonanceFactory(name="Aurum", affinity=celestial)

    def test_a_move_from_a_stale_resonance_is_refused_and_writes_nothing(self) -> None:
        thread = ThreadFactory(resonance=self.bene, developed_points=40)
        # Another process moved it to Aurum; this process's cached instance still says Bene.
        Thread.objects.filter(pk=thread.pk).update_with_reason(
            reason="test: another process moved the row behind this one's cache",
            resonance=self.aurum,
        )

        with self.assertRaises(ThreadResonanceChangeError) as raised:
            change_thread_resonance(thread.owner, thread=thread, target_resonance=self.lumen)

        self.assertEqual(raised.exception.user_message, THREAD_MOVED_MESSAGE)
        self.assertEqual(
            Thread.objects.filter(pk=thread.pk).values_list("resonance_id", flat=True)[0],
            self.aurum.pk,
        )


class AnAnchorTakenMidMoveIsRefused(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        celestial, _primal, _abyssal = ensure_conversion_pairs()
        cls.bene = ResonanceFactory(name="Bene", affinity=celestial)
        cls.lumen = ResonanceFactory(name="Lumen", affinity=celestial)

    def test_the_unique_index_refusal_is_clean_and_leaves_the_cache_as_stored(self) -> None:
        thread = ThreadFactory(resonance=self.bene, developed_points=40)
        # Another process wove a live Lumen thread on the same trait after this one looked:
        # the lookup misses it, the partial unique index does not.
        ThreadFactory(
            owner=thread.owner,
            resonance=self.lumen,
            target_trait=thread.target_trait,
            developed_points=3,
        )
        with (
            mock.patch(
                "world.magic.services.conversion._find_existing_target_thread",
                return_value=None,
            ),
            self.assertRaises(ThreadAnchorTakenError) as raised,
        ):
            change_thread_resonance(thread.owner, thread=thread, target_resonance=self.lumen)

        self.assertEqual(raised.exception.user_message, ThreadAnchorTakenError.user_message)
        self.assertEqual(thread.resonance_id, self.bene.pk)
        self.assertEqual(thread.developed_points, 40)
        self.assertEqual(
            Thread.objects.filter(pk=thread.pk).values_list("resonance_id", flat=True)[0],
            self.bene.pk,
        )
