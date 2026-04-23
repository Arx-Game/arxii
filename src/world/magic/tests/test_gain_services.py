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


class SetResidenceTests(TestCase):
    def test_set_residence_stores_fk(self) -> None:
        from evennia_extensions.factories import RoomProfileFactory
        from world.character_sheets.factories import CharacterSheetFactory
        from world.magic.services.gain import set_residence

        sheet = CharacterSheetFactory()
        rp = RoomProfileFactory()
        set_residence(sheet, rp)
        sheet.refresh_from_db()
        self.assertEqual(sheet.current_residence, rp)

    def test_clear_residence_with_none(self) -> None:
        from evennia_extensions.factories import RoomProfileFactory
        from world.character_sheets.factories import CharacterSheetFactory
        from world.magic.services.gain import set_residence

        sheet = CharacterSheetFactory()
        set_residence(sheet, RoomProfileFactory())
        set_residence(sheet, None)
        sheet.refresh_from_db()
        self.assertIsNone(sheet.current_residence)


class GetResidenceResonancesTests(TestCase):
    def test_empty_when_no_residence(self) -> None:
        from world.character_sheets.factories import CharacterSheetFactory
        from world.magic.services.gain import get_residence_resonances

        sheet = CharacterSheetFactory()
        self.assertEqual(get_residence_resonances(sheet), set())

    def test_empty_when_residence_has_no_aura_profile(self) -> None:
        from evennia_extensions.factories import RoomProfileFactory
        from world.character_sheets.factories import CharacterSheetFactory
        from world.magic.services.gain import get_residence_resonances, set_residence

        sheet = CharacterSheetFactory()
        set_residence(sheet, RoomProfileFactory())
        self.assertEqual(get_residence_resonances(sheet), set())

    def test_returns_intersection_of_tagged_and_claimed(self) -> None:
        from evennia_extensions.factories import RoomProfileFactory
        from world.character_sheets.factories import CharacterSheetFactory
        from world.magic.factories import (
            CharacterResonanceFactory,
            ResonanceFactory,
        )
        from world.magic.services.gain import (
            get_residence_resonances,
            set_residence,
            tag_room_resonance,
        )

        sheet = CharacterSheetFactory()
        rp = RoomProfileFactory()
        r_claimed_and_tagged = ResonanceFactory()
        r_tagged_only = ResonanceFactory()
        r_claimed_only = ResonanceFactory()

        CharacterResonanceFactory(character_sheet=sheet, resonance=r_claimed_and_tagged)
        CharacterResonanceFactory(character_sheet=sheet, resonance=r_claimed_only)

        tag_room_resonance(rp, r_claimed_and_tagged)
        tag_room_resonance(rp, r_tagged_only)

        set_residence(sheet, rp)

        self.assertEqual(get_residence_resonances(sheet), {r_claimed_and_tagged})
