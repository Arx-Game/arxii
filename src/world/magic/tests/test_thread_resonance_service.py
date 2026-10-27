"""The retune's locked re-check (slice 6 of #4672).

A unit test because no journey can reach it: it needs another process to move the thread
between the moment this one read it and the moment it takes the row lock. The test writes
the row behind the identity map's back, which is what that other process does.
"""

from __future__ import annotations

from django.test import TestCase

from world.magic.exceptions import ThreadResonanceChangeError
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
