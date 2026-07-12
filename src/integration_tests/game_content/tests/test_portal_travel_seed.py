"""Tests for ensure_portal_travel_content() — Task 6, #2222.

Verifies the Mirror anchor kind, the Mirrorwalking MINOR gift + Mirrorwalk
technique, its GiftUnlock, and starter mirror anchors in seeded public rooms
are all created idempotently, and that the room-anchor step skips gracefully
when a candidate room hasn't been seeded yet (rather than crashing).
"""

from __future__ import annotations

from django.test import TestCase

from world.magic.constants import GiftKind
from world.magic.effect_palette_content import TRANSLOCATION_STANCE_STYLE_NAME
from world.magic.models import (
    Gift,
    GiftUnlock,
    PortalAnchor,
    PortalAnchorKind,
    Technique,
)
from world.seeds.character_creation import ensure_canonical_fallback_room
from world.seeds.game_content.magic import (
    _MIRROR_ANCHOR_KIND_NAME,
    _MIRRORWALK_TECHNIQUE_NAME,
    _MIRRORWALK_UNLOCK_XP_COST,
    _MIRRORWALKING_GIFT_NAME,
    ensure_portal_travel_content,
)


class EnsurePortalTravelContentTests(TestCase):
    def test_seeds_mirror_anchor_kind(self) -> None:
        ensure_portal_travel_content()

        kind = PortalAnchorKind.objects.get(name=_MIRROR_ANCHOR_KIND_NAME)
        self.assertEqual(kind.arrival_verb, "steps out of")
        self.assertEqual(kind.departure_verb, "steps into")

    def test_seeds_mirrorwalking_minor_gift(self) -> None:
        ensure_portal_travel_content()

        gift = Gift.objects.get(name=_MIRRORWALKING_GIFT_NAME)
        self.assertEqual(gift.kind, GiftKind.MINOR)
        self.assertTrue(gift.resonances.exists())

    def test_seeds_mirrorwalk_technique(self) -> None:
        ensure_portal_travel_content()

        kind = PortalAnchorKind.objects.get(name=_MIRROR_ANCHOR_KIND_NAME)
        technique = Technique.objects.get(name=_MIRRORWALK_TECHNIQUE_NAME)
        self.assertEqual(technique.travel_anchor_kind, kind)
        self.assertEqual(technique.anima_cost, 0)
        self.assertEqual(technique.style.name, TRANSLOCATION_STANCE_STYLE_NAME)
        self.assertEqual(technique.effect_type.name, "Teleport")
        self.assertIsNotNone(technique.action_template)

    def test_seeds_gift_unlock(self) -> None:
        ensure_portal_travel_content()

        gift = Gift.objects.get(name=_MIRRORWALKING_GIFT_NAME)
        unlock = GiftUnlock.objects.get(gift=gift)
        self.assertEqual(unlock.xp_cost, _MIRRORWALK_UNLOCK_XP_COST)

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

    def test_is_idempotent(self) -> None:
        ensure_portal_travel_content()
        kind_count_1 = PortalAnchorKind.objects.count()
        gift_count_1 = Gift.objects.count()
        technique_count_1 = Technique.objects.count()
        unlock_count_1 = GiftUnlock.objects.count()
        anchor_count_1 = PortalAnchor.objects.count()

        ensure_portal_travel_content()

        self.assertEqual(PortalAnchorKind.objects.count(), kind_count_1)
        self.assertEqual(Gift.objects.count(), gift_count_1)
        self.assertEqual(Technique.objects.count(), technique_count_1)
        self.assertEqual(GiftUnlock.objects.count(), unlock_count_1)
        self.assertEqual(PortalAnchor.objects.count(), anchor_count_1)


class EnsurePortalTravelContentWithCascadeRoomsTests(TestCase):
    """When the magic-story cascade rooms exist first, the network has 3 nodes."""

    def test_anchors_reach_all_three_seeded_public_rooms(self) -> None:
        from world.seeds.game_content.magic import seed_starter_magic_story

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
