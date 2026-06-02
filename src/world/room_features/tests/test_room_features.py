"""Tests for the Room Features framework (Plan 4 Subsystem E)."""

from __future__ import annotations

from unittest.mock import MagicMock

from django.db import IntegrityError
from django.test import TestCase

from world.projects.constants import ProjectKind
from world.projects.factories import ProjectFactory
from world.room_features.constants import (
    RoomFeatureInstallMechanism,
    RoomFeatureOwnerType,
    RoomFeatureServiceStrategy,
)
from world.room_features.factories import (
    RoomFeatureInstanceFactory,
    RoomFeatureKindFactory,
    RoomFeatureKindInstallRitualFactory,
    RoomFeatureKindOwnerTypeFactory,
    RoomFeatureProgressionDetailsFactory,
)
from world.room_features.models import (
    RoomFeatureInstance,
    RoomFeatureKind,
    RoomFeatureKindInstallRitual,
    RoomFeatureKindOwnerType,
)
from world.room_features.seeds import SANCTUM_KIND_NAME, ensure_sanctum_kind
from world.room_features.services import (
    can_modify_room_features,
    complete_room_feature_progression,
    register_room_feature_strategy,
    reset_room_feature_strategies,
)


class RoomFeatureKindTests(TestCase):
    def test_str(self) -> None:
        kind = RoomFeatureKindFactory(name="Sanctum")
        self.assertEqual(str(kind), "Sanctum")

    def test_max_level_check_constraint(self) -> None:
        with self.assertRaises(IntegrityError):
            RoomFeatureKind.objects.create(name="bad", max_level=0, service_strategy="LIBRARY")

    def test_service_strategy_unique(self) -> None:
        RoomFeatureKindFactory(service_strategy=RoomFeatureServiceStrategy.SANCTUM)
        with self.assertRaises(IntegrityError):
            RoomFeatureKind.objects.create(
                name="other",
                max_level=3,
                service_strategy=RoomFeatureServiceStrategy.SANCTUM,
            )


class RoomFeatureKindOwnerTypeTests(TestCase):
    def test_uniqueness_per_kind_owner_type(self) -> None:
        kind = RoomFeatureKindFactory()
        RoomFeatureKindOwnerTypeFactory(feature_kind=kind, owner_type=RoomFeatureOwnerType.PERSONA)
        with self.assertRaises(IntegrityError):
            RoomFeatureKindOwnerType.objects.create(
                feature_kind=kind, owner_type=RoomFeatureOwnerType.PERSONA
            )


class RoomFeatureInstanceTests(TestCase):
    def test_one_feature_per_room(self) -> None:
        instance = RoomFeatureInstanceFactory()
        with self.assertRaises(IntegrityError):
            RoomFeatureInstance.objects.create(
                room_profile=instance.room_profile,
                feature_kind=RoomFeatureKindFactory(
                    service_strategy=RoomFeatureServiceStrategy.LIBRARY,
                    name="Library",
                ),
            )

    def test_level_check_constraint(self) -> None:
        with self.assertRaises(IntegrityError):
            RoomFeatureInstanceFactory(level=0)

    def test_str(self) -> None:
        instance = RoomFeatureInstanceFactory(level=3)
        result = str(instance)
        self.assertIn("L3", result)
        self.assertIn("room", result)


class RoomFeatureProgressionDetailsTests(TestCase):
    def test_str(self) -> None:
        details = RoomFeatureProgressionDetailsFactory(target_level=2)
        result = str(details)
        self.assertIn("L2", result)


class StrategyRegistryTests(TestCase):
    def tearDown(self) -> None:
        reset_room_feature_strategies()
        super().tearDown()

    def test_register_and_dispatch(self) -> None:
        details = RoomFeatureProgressionDetailsFactory(target_level=2)
        handler = MagicMock()
        register_room_feature_strategy(details.target_feature_kind.service_strategy, handler)

        complete_room_feature_progression(details.project, outcome_tier=None)

        handler.assert_called_once_with(details.project, 2, None)

    def test_unregistered_strategy_raises(self) -> None:
        details = RoomFeatureProgressionDetailsFactory()
        with self.assertRaises(NotImplementedError):
            complete_room_feature_progression(details.project, outcome_tier=None)

    def test_missing_details_raises(self) -> None:
        project = ProjectFactory(kind=ProjectKind.ROOM_FEATURE_PROGRESSION)
        with self.assertRaises(RuntimeError):
            complete_room_feature_progression(project, outcome_tier=None)

    def test_reset_clears_overrides(self) -> None:
        register_room_feature_strategy(RoomFeatureServiceStrategy.SANCTUM, MagicMock())
        reset_room_feature_strategies()
        details = RoomFeatureProgressionDetailsFactory(
            target_feature_kind=RoomFeatureKindFactory(
                service_strategy=RoomFeatureServiceStrategy.SANCTUM
            ),
        )
        with self.assertRaises(NotImplementedError):
            complete_room_feature_progression(details.project, outcome_tier=None)


class PermissionGateTests(TestCase):
    def test_neither_owner_nor_tenant_denied(self) -> None:
        from evennia_extensions.factories import RoomProfileFactory
        from world.scenes.factories import PersonaFactory

        persona = PersonaFactory()
        profile = RoomProfileFactory()

        self.assertFalse(can_modify_room_features(persona, profile.objectdb))


class SanctumSeedTests(TestCase):
    def test_seeds_idempotent(self) -> None:
        kind1 = ensure_sanctum_kind()
        kind2 = ensure_sanctum_kind()

        self.assertEqual(kind1.pk, kind2.pk)
        self.assertEqual(kind1.name, SANCTUM_KIND_NAME)
        self.assertEqual(kind1.max_level, 5)
        self.assertEqual(kind1.install_mechanism, RoomFeatureInstallMechanism.RITUAL)
        owner_types = set(kind1.required_building_owner_types.values_list("owner_type", flat=True))
        self.assertEqual(
            owner_types,
            {
                RoomFeatureOwnerType.PERSONA,
                RoomFeatureOwnerType.ORGANIZATION_COVENANT,
            },
        )


class RoomFeatureKindInstallRitualTests(TestCase):
    def test_install_ritual_link_persists(self) -> None:
        link = RoomFeatureKindInstallRitualFactory(variant_label="Personal")
        fetched = RoomFeatureKindInstallRitual.objects.get(pk=link.pk)
        self.assertEqual(fetched.variant_label, "Personal")
        self.assertEqual(fetched.feature_kind.install_mechanism, RoomFeatureInstallMechanism.RITUAL)

    def test_unique_per_kind_ritual(self) -> None:
        link = RoomFeatureKindInstallRitualFactory()
        with self.assertRaises(IntegrityError):
            RoomFeatureKindInstallRitual.objects.create(
                feature_kind=link.feature_kind,
                ritual=link.ritual,
                variant_label="Duplicate",
            )

    def test_kind_can_have_multiple_variants(self) -> None:
        from world.magic.factories import RitualFactory

        kind = RoomFeatureKindFactory()
        ritual_a = RitualFactory()
        ritual_b = RitualFactory()
        RoomFeatureKindInstallRitualFactory(
            feature_kind=kind, ritual=ritual_a, variant_label="Personal"
        )
        RoomFeatureKindInstallRitualFactory(
            feature_kind=kind, ritual=ritual_b, variant_label="Covenant"
        )
        variants = set(kind.install_rituals.values_list("variant_label", flat=True))
        self.assertEqual(variants, {"Personal", "Covenant"})
