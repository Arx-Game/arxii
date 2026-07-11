"""Tests for the idempotent Companion content seeder (#672)."""

from __future__ import annotations

from django.test import TestCase

from world.checks.models import CheckType
from world.companions.constants import CompanionDomain
from world.companions.content import (
    BEASTLORD_GIFT_NAME,
    BIND_ATTEMPT_CHECK_NAME,
    ensure_companion_abilities,
    ensure_companion_content,
)
from world.companions.models import CompanionAbility, CompanionArchetype
from world.magic.models.threads import ThreadPullEffect


class EnsureCompanionContentTests(TestCase):
    def test_seeds_beastlord_gift(self) -> None:
        gift = ensure_companion_content()

        self.assertEqual(gift.name, BEASTLORD_GIFT_NAME)
        self.assertTrue(gift.resonances.exists())

    def test_seeds_bind_attempt_check_type(self) -> None:
        ensure_companion_content()

        self.assertTrue(CheckType.objects.filter(name=BIND_ATTEMPT_CHECK_NAME).exists())

    def test_seeds_beast_archetypes(self) -> None:
        ensure_companion_content()

        archetypes = CompanionArchetype.objects.filter(domain=CompanionDomain.BEAST)
        self.assertGreaterEqual(archetypes.count(), 3)

    def test_seeds_capacity_tier_rows(self) -> None:
        gift = ensure_companion_content()

        rows = ThreadPullEffect.objects.filter(target_gift=gift)
        self.assertGreaterEqual(rows.count(), 2)

    def test_is_idempotent(self) -> None:
        ensure_companion_content()
        gift_count_before = CompanionArchetype.objects.count()

        ensure_companion_content()

        self.assertEqual(CompanionArchetype.objects.count(), gift_count_before)


class EnsureStablesKindTests(TestCase):
    """Tests for the Stables RoomFeatureKind seed (#1863)."""

    def test_ensure_stables_kind_creates_kind(self) -> None:
        from world.companions.seeds import ensure_stables_kind
        from world.room_features.constants import (
            RoomFeatureInstallMechanism,
            RoomFeatureServiceStrategy,
        )
        from world.room_features.models import RoomFeatureKind

        ensure_stables_kind()

        kind = RoomFeatureKind.objects.get(
            service_strategy=RoomFeatureServiceStrategy.STABLES,
        )
        self.assertEqual(kind.name, "Stables")
        self.assertEqual(kind.max_level, 5)
        self.assertEqual(kind.install_mechanism, RoomFeatureInstallMechanism.PROJECT)

    def test_ensure_stables_kind_is_idempotent(self) -> None:
        from world.companions.seeds import ensure_stables_kind
        from world.room_features.constants import RoomFeatureServiceStrategy
        from world.room_features.models import RoomFeatureKind

        ensure_stables_kind()
        ensure_stables_kind()
        self.assertEqual(
            RoomFeatureKind.objects.filter(
                service_strategy=RoomFeatureServiceStrategy.STABLES,
            ).count(),
            1,
        )


class EnsureCompanionAbilitiesTests(TestCase):
    def test_seeds_abilities_for_archetypes(self) -> None:
        ensure_companion_content()
        ensure_companion_abilities()

        direwolf = CompanionArchetype.objects.get(name="Direwolf")
        rend = direwolf.abilities.get(name="Rend")
        self.assertEqual(rend.base_damage, 8)

        wolf = CompanionArchetype.objects.get(name="Wolf")
        bite = wolf.abilities.get(name="Bite")
        self.assertEqual(bite.base_damage, 5)

    def test_is_idempotent(self) -> None:
        ensure_companion_content()
        ensure_companion_abilities()
        count_before = CompanionAbility.objects.count()

        ensure_companion_abilities()

        self.assertEqual(CompanionAbility.objects.count(), count_before)
