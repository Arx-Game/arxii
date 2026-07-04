from __future__ import annotations

from django.test import TestCase

from world.npc_services.factories import MissionOfferDetailsFactory
from world.npc_services.models import MissionOfferDetails
from world.stories.factories import BeatFactory


class MissionOfferDetailsSourceBeatTests(TestCase):
    def test_source_beat_defaults_null(self):
        details = MissionOfferDetailsFactory()
        self.assertIsNone(details.source_beat_id)

    def test_source_beat_links_and_survives_beat_delete(self):
        beat = BeatFactory()
        details = MissionOfferDetailsFactory(source_beat=beat)
        self.assertEqual(details.source_beat_id, beat.pk)
        beat.delete()
        # Collector-driven SET_NULL bypasses the idmapper identity map (it's a
        # bulk UPDATE, not a per-instance .save()), so the cached `details`
        # instance must be evicted before refresh_from_db() will see the new
        # value. See tools/skills/sharedmemory-model/references/stale-cache-traps.md.
        MissionOfferDetails.flush_instance_cache()
        details.refresh_from_db()
        self.assertIsNone(details.source_beat_id)  # SET_NULL keeps the detail row
