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


class StablesCapacityBonusTests(TestCase):
    """Tests for stables_capacity_bonus_for_sheet (#1863)."""

    def test_no_stables_returns_zero(self) -> None:
        """A character with no Stables gets 0 bonus."""
        sheet = CharacterSheetFactory()
        from world.companions.services import stables_capacity_bonus_for_sheet

        self.assertEqual(stables_capacity_bonus_for_sheet(sheet), 0)

    def test_stables_bonus_scales_with_level(self) -> None:
        """A character with standing in a Stables room gets bonus * level."""
        from evennia import create_object

        from world.companions.models import StablesDetails
        from world.companions.services import stables_capacity_bonus_for_sheet
        from world.locations.constants import HolderType, LocationParentType
        from world.locations.models import LocationTenancy
        from world.room_features.constants import (
            RoomFeatureInstallMechanism,
            RoomFeatureServiceStrategy,
        )
        from world.room_features.factories import (
            RoomFeatureInstanceFactory,
        )
        from world.room_features.models import RoomFeatureKind

        sheet = CharacterSheetFactory()
        persona = sheet.primary_persona

        room = create_object("typeclasses.rooms.Room", key="Stables Room")
        from evennia_extensions.factories import RoomProfileFactory

        room_profile = RoomProfileFactory(objectdb=room)

        kind = RoomFeatureKind.objects.create(
            name="Stables",
            max_level=5,
            service_strategy=RoomFeatureServiceStrategy.STABLES,
            install_mechanism=RoomFeatureInstallMechanism.PROJECT,
        )
        instance = RoomFeatureInstanceFactory(
            room_profile=room_profile,
            feature_kind=kind,
            level=3,
        )
        StablesDetails.objects.create(
            feature_instance=instance,
            capacity_bonus_per_level=2,
        )
        # Grant the sheet's persona tenancy in the room.
        LocationTenancy.objects.create(
            parent_type=LocationParentType.ROOM,
            room_profile=room_profile,
            tenant_type=HolderType.PERSONA,
            tenant_persona=persona,
        )

        bonus = stables_capacity_bonus_for_sheet(sheet)
        # Expected: 2 (per_level) * 3 (level) = 6
        self.assertEqual(bonus, 6)

    def test_no_standing_returns_zero(self) -> None:
        """A Stables the character has no standing in gives no bonus."""
        from evennia import create_object

        from world.companions.models import StablesDetails
        from world.companions.services import stables_capacity_bonus_for_sheet
        from world.room_features.constants import (
            RoomFeatureInstallMechanism,
            RoomFeatureServiceStrategy,
        )
        from world.room_features.factories import RoomFeatureInstanceFactory
        from world.room_features.models import RoomFeatureKind

        sheet = CharacterSheetFactory()
        room = create_object("typeclasses.rooms.Room", key="Other Room")
        from evennia_extensions.factories import RoomProfileFactory

        room_profile = RoomProfileFactory(objectdb=room)
        kind = RoomFeatureKind.objects.create(
            name="Stables2",
            max_level=5,
            service_strategy=RoomFeatureServiceStrategy.STABLES,
            install_mechanism=RoomFeatureInstallMechanism.PROJECT,
        )
        instance = RoomFeatureInstanceFactory(
            room_profile=room_profile,
            feature_kind=kind,
            level=3,
        )
        StablesDetails.objects.create(
            feature_instance=instance,
            capacity_bonus_per_level=2,
        )
        # No tenancy or ownership granted.
        self.assertEqual(stables_capacity_bonus_for_sheet(sheet), 0)


class CompanionCapacityWithStablesTests(TestCase):
    """Tests that companion_capacity includes the Stables bonus (#1863)."""

    def setUp(self) -> None:
        self.sheet = CharacterSheetFactory()
        self.gift = GiftFactory(name="Beastlord Stables Test", kind=GiftKind.MINOR)
        self.resonance = ResonanceFactory()
        self.gift.resonances.add(self.resonance)
        self.thread = provision_latent_gift_thread(
            self.sheet,
            self.gift,
            resonance=self.resonance,
        )

    def test_stables_bonus_added_to_capacity(self) -> None:
        """companion_capacity includes the Stables bonus."""
        from evennia import create_object

        from world.companions.models import StablesDetails
        from world.locations.constants import HolderType, LocationParentType
        from world.locations.models import LocationTenancy
        from world.room_features.constants import (
            RoomFeatureInstallMechanism,
            RoomFeatureServiceStrategy,
        )
        from world.room_features.factories import RoomFeatureInstanceFactory
        from world.room_features.models import RoomFeatureKind

        # Base capacity: 10 from ThreadPullEffect.
        ThreadPullEffectFactory(
            target_kind=TargetKind.GIFT,
            resonance=self.resonance,
            tier=0,
            min_thread_level=0,
            target_gift=self.gift,
            effect_kind=EffectKind.FLAT_BONUS,
            flat_bonus_amount=10,
        )
        self.assertEqual(companion_capacity(self.sheet, self.gift), 10)

        # Install a Stables at level 2 with bonus_per_level=3 → +6.
        persona = self.sheet.primary_persona
        room = create_object("typeclasses.rooms.Room", key="Cap Room")
        from evennia_extensions.factories import RoomProfileFactory

        room_profile = RoomProfileFactory(objectdb=room)
        kind = RoomFeatureKind.objects.create(
            name="StablesCap",
            max_level=5,
            service_strategy=RoomFeatureServiceStrategy.STABLES,
            install_mechanism=RoomFeatureInstallMechanism.PROJECT,
        )
        instance = RoomFeatureInstanceFactory(
            room_profile=room_profile,
            feature_kind=kind,
            level=2,
        )
        StablesDetails.objects.create(
            feature_instance=instance,
            capacity_bonus_per_level=3,
        )
        LocationTenancy.objects.create(
            parent_type=LocationParentType.ROOM,
            room_profile=room_profile,
            tenant_type=HolderType.PERSONA,
            tenant_persona=persona,
        )

        self.assertEqual(companion_capacity(self.sheet, self.gift), 16)

    def test_no_stables_no_change(self) -> None:
        """companion_capacity unchanged when no Stables exists (no regression)."""
        ThreadPullEffectFactory(
            target_kind=TargetKind.GIFT,
            resonance=self.resonance,
            tier=0,
            min_thread_level=0,
            target_gift=self.gift,
            effect_kind=EffectKind.FLAT_BONUS,
            flat_bonus_amount=10,
        )
        self.assertEqual(companion_capacity(self.sheet, self.gift), 10)


class StablesProgressionTests(TestCase):
    """Tests for handle_stables_progression (#1863)."""

    def setUp(self) -> None:
        from evennia_extensions.factories import RoomProfileFactory
        from world.room_features.constants import (
            RoomFeatureInstallMechanism,
            RoomFeatureServiceStrategy,
        )
        from world.room_features.models import RoomFeatureKind

        self.room_profile = RoomProfileFactory()
        self.kind = RoomFeatureKind.objects.create(
            name="StablesProg",
            max_level=5,
            service_strategy=RoomFeatureServiceStrategy.STABLES,
            install_mechanism=RoomFeatureInstallMechanism.PROJECT,
        )

    def _progression(self, target_level: int = 1):
        from world.projects.factories import ProjectFactory
        from world.room_features.models import RoomFeatureProgressionDetails

        project = ProjectFactory()
        RoomFeatureProgressionDetails.objects.create(
            project=project,
            target_room_profile=self.room_profile,
            target_feature_kind=self.kind,
            target_level=target_level,
        )
        return project

    def test_install_creates_instance_and_details(self) -> None:
        """handle_stables_progression creates a RoomFeatureInstance + StablesDetails."""
        from world.companions.services import handle_stables_progression
        from world.room_features.models import RoomFeatureInstance

        project = self._progression(target_level=1)
        handle_stables_progression(project, 1, None)

        instance = RoomFeatureInstance.objects.get(room_profile=self.room_profile)
        self.assertEqual(instance.feature_kind, self.kind)
        self.assertEqual(instance.level, 1)
        # StablesDetails sidecar created.
        self.assertTrue(hasattr(instance, "stables_details"))
        self.assertEqual(instance.stables_details.capacity_bonus_per_level, 1)

    def test_upgrade_bumps_level_preserves_details(self) -> None:
        """Upgrading a Stables bumps the level and preserves StablesDetails (get_or_create)."""
        from world.companions.services import handle_stables_progression
        from world.room_features.models import RoomFeatureInstance

        # Install at L1.
        project1 = self._progression(target_level=1)
        handle_stables_progression(project1, 1, None)
        instance = RoomFeatureInstance.objects.get(room_profile=self.room_profile)
        details_pk = instance.stables_details.pk

        # Upgrade to L3.
        project3 = self._progression(target_level=3)
        handle_stables_progression(project3, 3, None)
        instance.refresh_from_db()
        self.assertEqual(instance.level, 3)
        # Same StablesDetails row (get_or_create).
        self.assertEqual(instance.stables_details.pk, details_pk)
