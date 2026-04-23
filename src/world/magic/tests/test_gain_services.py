"""Tests for Spec C gain service functions."""

from django.test import TestCase


class TagRoomResonanceTests(TestCase):
    def test_creates_aura_profile_if_missing(self) -> None:
        from evennia_extensions.factories import RoomProfileFactory
        from world.magic.factories import ResonanceFactory
        from world.magic.models import RoomAuraProfile, RoomResonance
        from world.magic.services.gain import tag_room_resonance

        rp = RoomProfileFactory()
        res = ResonanceFactory()
        self.assertFalse(hasattr(rp, "room_aura_profile") and rp.room_aura_profile is not None)

        tag = tag_room_resonance(rp, res)

        self.assertTrue(RoomAuraProfile.objects.filter(room_profile=rp).exists())
        self.assertIsInstance(tag, RoomResonance)
        self.assertEqual(tag.resonance, res)

    def test_idempotent_on_duplicate(self) -> None:
        from evennia_extensions.factories import RoomProfileFactory
        from world.magic.factories import ResonanceFactory
        from world.magic.models import RoomResonance
        from world.magic.services.gain import tag_room_resonance

        rp = RoomProfileFactory()
        res = ResonanceFactory()
        t1 = tag_room_resonance(rp, res)
        t2 = tag_room_resonance(rp, res)
        self.assertEqual(t1.pk, t2.pk)
        self.assertEqual(RoomResonance.objects.count(), 1)


class UntagRoomResonanceTests(TestCase):
    def test_untag_removes_row(self) -> None:
        from evennia_extensions.factories import RoomProfileFactory
        from world.magic.factories import ResonanceFactory
        from world.magic.models import RoomResonance
        from world.magic.services.gain import tag_room_resonance, untag_room_resonance

        rp = RoomProfileFactory()
        res = ResonanceFactory()
        tag_room_resonance(rp, res)
        self.assertEqual(RoomResonance.objects.count(), 1)
        untag_room_resonance(rp, res)
        self.assertEqual(RoomResonance.objects.count(), 0)

    def test_untag_noop_if_absent(self) -> None:
        from evennia_extensions.factories import RoomProfileFactory
        from world.magic.factories import ResonanceFactory
        from world.magic.services.gain import untag_room_resonance

        rp = RoomProfileFactory()
        res = ResonanceFactory()
        untag_room_resonance(rp, res)  # should not raise
