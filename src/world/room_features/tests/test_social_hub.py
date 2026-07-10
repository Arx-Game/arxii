"""Social Hub feature (#1694): seed, install strategy, and read-time lookup.

Slice 1 — the owner-upgradeable amplifier's designation layer:
- ``ensure_social_hub_kind`` seeds the kind + its store/room owner-type rules.
- ``handle_social_hub_progression`` installs/levels the instance AND flips the
  room's ``is_social_hub`` designation on.
- ``active_social_hub_in`` is the read-time hook every amplifier magnitude
  (fame/prestige multiplier, crowd draw) derives from.
"""

from django.test import TestCase

from evennia_extensions.factories import RoomProfileFactory
from world.projects.factories import ProjectFactory
from world.room_features.constants import (
    SOCIAL_HUB_MAX_LEVEL,
    RoomFeatureInstallMechanism,
    RoomFeatureOwnerType,
    RoomFeatureServiceStrategy,
)
from world.room_features.factories import RoomFeatureInstanceFactory
from world.room_features.models import RoomFeatureInstance, RoomFeatureProgressionDetails
from world.room_features.seeds import ensure_social_hub_kind
from world.room_features.services import active_social_hub_in, handle_social_hub_progression


class EnsureSocialHubKindTests(TestCase):
    def test_creates_kind_with_expected_fields(self) -> None:
        kind = ensure_social_hub_kind()
        self.assertEqual(kind.service_strategy, RoomFeatureServiceStrategy.SOCIAL_HUB)
        self.assertEqual(kind.max_level, SOCIAL_HUB_MAX_LEVEL)
        self.assertEqual(kind.install_mechanism, RoomFeatureInstallMechanism.PROJECT)

    def test_seeds_store_owner_types(self) -> None:
        kind = ensure_social_hub_kind()
        owner_types = set(kind.required_building_owner_types.values_list("owner_type", flat=True))
        self.assertEqual(
            owner_types,
            {RoomFeatureOwnerType.PERSONA, RoomFeatureOwnerType.ORGANIZATION_TRADE},
        )

    def test_idempotent(self) -> None:
        first = ensure_social_hub_kind()
        second = ensure_social_hub_kind()
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(first.required_building_owner_types.count(), 2)


class ActiveSocialHubInTests(TestCase):
    def test_finds_instance(self) -> None:
        kind = ensure_social_hub_kind()
        instance = RoomFeatureInstanceFactory(feature_kind=kind)
        self.assertEqual(active_social_hub_in(instance.room_profile), instance)

    def test_returns_none_when_absent(self) -> None:
        instance = RoomFeatureInstanceFactory()
        self.assertIsNone(active_social_hub_in(instance.room_profile))

    def test_excludes_dissolved(self) -> None:
        kind = ensure_social_hub_kind()
        instance = RoomFeatureInstanceFactory(feature_kind=kind)
        instance.dissolved_at = instance.installed_at
        instance.save(update_fields=["dissolved_at"])
        self.assertIsNone(active_social_hub_in(instance.room_profile))


class HandleSocialHubProgressionTests(TestCase):
    def setUp(self) -> None:
        self.kind = ensure_social_hub_kind()
        self.room_profile = RoomProfileFactory(is_social_hub=False)

    def _progression(self, target_level: int = 1):
        project = ProjectFactory()
        RoomFeatureProgressionDetails.objects.create(
            project=project,
            target_room_profile=self.room_profile,
            target_feature_kind=self.kind,
            target_level=target_level,
        )
        return project

    def test_install_creates_instance_and_marks_hub(self) -> None:
        handle_social_hub_progression(self._progression(1), 1, None)
        instance = RoomFeatureInstance.objects.get(room_profile=self.room_profile)
        self.assertEqual(instance.feature_kind, self.kind)
        self.assertEqual(instance.level, 1)
        self.room_profile.refresh_from_db()
        self.assertTrue(self.room_profile.is_social_hub)

    def test_upgrade_bumps_level(self) -> None:
        handle_social_hub_progression(self._progression(1), 1, None)
        handle_social_hub_progression(self._progression(3), 3, None)
        instance = RoomFeatureInstance.objects.get(room_profile=self.room_profile)
        self.assertEqual(instance.level, 3)

    def test_dissolve_clears_amplification_but_leaves_baseline_hub(self) -> None:
        handle_social_hub_progression(self._progression(2), 2, None)
        instance = RoomFeatureInstance.objects.get(room_profile=self.room_profile)
        instance.dissolved_at = instance.installed_at
        instance.save(update_fields=["dissolved_at"])
        # Amplification is gone (no active instance) ...
        self.assertIsNone(active_social_hub_in(self.room_profile))
        # ... but the baseline gossip-hub designation is deliberately preserved.
        self.room_profile.refresh_from_db()
        self.assertTrue(self.room_profile.is_social_hub)
