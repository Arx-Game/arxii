"""Tests for Companion Capacity service functions (#672)."""

from __future__ import annotations

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.companions.factories import CompanionArchetypeFactory, CompanionFactory
from world.companions.services import (
    NoCompanionThreadError,
    companion_capacity,
    used_companion_capacity,
)
from world.magic.constants import EffectKind, GiftKind, TargetKind
from world.magic.factories import GiftFactory, ResonanceFactory, ThreadPullEffectFactory
from world.magic.specialization.services import provision_latent_gift_thread


class CompanionCapacityTests(TestCase):
    def setUp(self) -> None:
        self.sheet = CharacterSheetFactory()
        self.gift = GiftFactory(name="Beastlord", kind=GiftKind.MINOR)
        self.resonance = ResonanceFactory()
        self.gift.resonances.add(self.resonance)
        self.thread = provision_latent_gift_thread(self.sheet, self.gift, resonance=self.resonance)

    def test_capacity_is_zero_with_no_authored_rows(self) -> None:
        self.assertEqual(companion_capacity(self.sheet, self.gift), 0)

    def test_capacity_sums_flat_bonus_rows_at_or_below_level(self) -> None:
        ThreadPullEffectFactory(
            target_kind=TargetKind.GIFT,
            resonance=self.resonance,
            tier=0,
            min_thread_level=0,
            target_gift=self.gift,
            effect_kind=EffectKind.FLAT_BONUS,
            flat_bonus_amount=10,
        )
        ThreadPullEffectFactory(
            target_kind=TargetKind.GIFT,
            resonance=self.resonance,
            tier=0,
            min_thread_level=20,
            target_gift=self.gift,
            effect_kind=EffectKind.FLAT_BONUS,
            flat_bonus_amount=15,
        )
        self.thread.level = 10
        self.thread.save(update_fields=["level"])

        self.assertEqual(companion_capacity(self.sheet, self.gift), 10)

        self.thread.level = 20
        self.thread.save(update_fields=["level"])

        self.assertEqual(companion_capacity(self.sheet, self.gift), 25)

    def test_capacity_raises_without_a_thread(self) -> None:
        other_gift = GiftFactory(name="Necromancy", kind=GiftKind.MINOR)

        with self.assertRaises(NoCompanionThreadError):
            companion_capacity(self.sheet, other_gift)

    def test_used_capacity_sums_active_companions_only(self) -> None:
        from django.utils import timezone

        active = CompanionFactory(
            owner=self.sheet, granting_gift=self.gift, archetype__capacity_cost=10
        )
        released = CompanionFactory(
            owner=self.sheet, granting_gift=self.gift, archetype__capacity_cost=15
        )
        released.released_at = timezone.now()
        released.save(update_fields=["released_at"])

        self.assertEqual(
            used_companion_capacity(self.sheet, self.gift), active.archetype.capacity_cost
        )


class BindAndReleaseCompanionTests(TestCase):
    def setUp(self) -> None:
        from evennia import create_object

        self.room = create_object("typeclasses.rooms.Room", key="Test Room")
        self.sheet = CharacterSheetFactory()
        self.sheet.character.location = self.room
        self.sheet.character.save()
        self.gift = GiftFactory(name="Beastlord Bind Test", kind=GiftKind.MINOR)
        self.archetype = CompanionArchetypeFactory(name="Test Wolf")

    def test_bind_companion_creates_row_and_object(self) -> None:
        from world.companions.services import bind_companion

        companion = bind_companion(
            owner=self.sheet, archetype=self.archetype, granting_gift=self.gift, name="Fang"
        )

        self.assertEqual(companion.name, "Fang")
        self.assertTrue(companion.is_active)
        self.assertIsNotNone(companion.objectdb)
        self.assertEqual(companion.objectdb.location, self.room)
        self.assertEqual(
            companion.objectdb.db_typeclass_path, "typeclasses.companions.CompanionObject"
        )

    def test_release_companion_clears_object_keeps_row(self) -> None:
        from world.companions.services import bind_companion, release_companion

        companion = bind_companion(
            owner=self.sheet, archetype=self.archetype, granting_gift=self.gift, name="Fang"
        )
        object_id = companion.objectdb_id

        release_companion(companion)

        self.assertIsNone(companion.objectdb)
        self.assertIsNotNone(companion.released_at)
        from world.companions.models import Companion

        self.assertTrue(Companion.objects.filter(pk=companion.pk).exists())
        from evennia.objects.models import ObjectDB

        self.assertFalse(ObjectDB.objects.filter(pk=object_id).exists())
