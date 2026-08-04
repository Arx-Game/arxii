"""Tests for ensure_portal_travel_content() — Task 6, #2222.

Verifies the Mirror anchor kind resolves and starter mirror anchors are created
idempotently in the seeded public rooms, that the room-anchor step skips
gracefully when a candidate room hasn't been seeded yet (rather than crashing),
and — since #2967 — that the seeder authors no Gift, Technique or Resonance of
its own. The "Mirrorwalking"/"Mirrorwalk" placeholder it used to invent was
obliterated; a real portal-travel gift is lore-repo content.
"""

from __future__ import annotations

from django.test import TestCase, override_settings

from world.magic.models import (
    Gift,
    PortalAnchor,
    PortalAnchorKind,
    Resonance,
    Technique,
)
from world.seeds.character_creation import ensure_canonical_fallback_room
from world.seeds.game_content.magic import (
    _MIRROR_ANCHOR_KIND_NAME,
    ensure_portal_travel_content,
)


@override_settings(SEED_SAMPLE_CONTENT=True)
class EnsurePortalTravelContentTests(TestCase):
    def test_seeds_mirror_anchor_kind(self) -> None:
        ensure_portal_travel_content()

        kind = PortalAnchorKind.objects.get(name=_MIRROR_ANCHOR_KIND_NAME)
        self.assertEqual(kind.arrival_verb, "steps out of")
        self.assertEqual(kind.departure_verb, "steps into")

    def test_authors_no_gift_technique_or_resonance(self) -> None:
        """#2967: the Mirrorwalking/Mirrorwalk placeholder is gone for good."""
        ensure_portal_travel_content()

        self.assertFalse(Gift.objects.exists())
        self.assertFalse(Technique.objects.exists())
        self.assertFalse(Resonance.objects.exists())

    def test_seeds_anchor_in_canonical_fallback_room(self) -> None:
        ensure_portal_travel_content()

        room = ensure_canonical_fallback_room()
        kind = PortalAnchorKind.objects.get(name=_MIRROR_ANCHOR_KIND_NAME)
        anchor = PortalAnchor.objects.active().get(
            room_profile__objectdb=room,
            kind=kind,
        )
        self.assertTrue(anchor.is_network_open)

    def test_skips_gracefully_when_cascade_rooms_not_seeded(self) -> None:
        """Calling this function standalone (without seed_starter_magic_story()
        having run first) must not crash even though the two cascade-room
        candidates don't exist yet — only the guaranteed fallback-room anchor
        is created."""
        ensure_portal_travel_content()

        kind = PortalAnchorKind.objects.get(name=_MIRROR_ANCHOR_KIND_NAME)
        self.assertEqual(PortalAnchor.objects.active().filter(kind=kind).count(), 1)

    def test_skips_when_the_anchor_kind_is_not_authored(self) -> None:
        """With sampling off and no content repo, there is nothing to place."""
        with override_settings(SEED_SAMPLE_CONTENT=False):
            ensure_portal_travel_content()

        self.assertFalse(PortalAnchorKind.objects.exists())
        self.assertFalse(PortalAnchor.objects.exists())

    def test_is_idempotent(self) -> None:
        ensure_portal_travel_content()
        kind_count_1 = PortalAnchorKind.objects.count()
        anchor_count_1 = PortalAnchor.objects.count()

        ensure_portal_travel_content()

        self.assertEqual(PortalAnchorKind.objects.count(), kind_count_1)
        self.assertEqual(PortalAnchor.objects.count(), anchor_count_1)


@override_settings(SEED_SAMPLE_CONTENT=True)
class EnsurePortalTravelContentWithCascadeRoomsTests(TestCase):
    """When the magic-story cascade rooms exist first, the network has 3 nodes."""

    def test_anchors_reach_all_three_seeded_public_rooms(self) -> None:
        from world.magic.factories import AffinityFactory, ResonanceFactory
        from world.seeds.game_content.magic import seed_starter_magic_story

        # The cascade rooms are only seeded when a Celestial and an Abyssal
        # resonance are authored (#2967) — stand in for the content repo.
        ResonanceFactory(affinity=AffinityFactory(name="Celestial"))
        ResonanceFactory(affinity=AffinityFactory(name="Abyssal"))

        seed_starter_magic_story()
        ensure_portal_travel_content()

        kind = PortalAnchorKind.objects.get(name=_MIRROR_ANCHOR_KIND_NAME)
        room_names = set(
            PortalAnchor.objects.active()
            .filter(kind=kind)
            .values_list("room_profile__objectdb__db_key", flat=True)
        )
        self.assertEqual(
            room_names,
            {
                "The Wanderer's Rest",
                "The Hallowed Threshold (Low)",
                "The Resonant Sanctum (Aligned)",
            },
        )
