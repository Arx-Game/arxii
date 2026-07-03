from django.test import TestCase

from evennia_extensions.factories import RoomProfileFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.locations.factories import LocationOwnershipFactory
from world.projects.constants import ProjectKind
from world.projects.models import Project
from world.room_features.constants import (
    RoomFeatureInstallMechanism,
    RoomFeatureServiceStrategy,
)
from world.room_features.factories import RoomFeatureInstanceFactory, RoomFeatureKindFactory
from world.room_features.models import RoomFeatureProgressionDetails


class StartRoomFeatureProjectActionTests(TestCase):
    def setUp(self) -> None:
        from actions.definitions.room_features import StartRoomFeatureProjectAction

        self.action_cls = StartRoomFeatureProjectAction
        self.kind = RoomFeatureKindFactory(
            service_strategy=RoomFeatureServiceStrategy.LAB,
            install_mechanism=RoomFeatureInstallMechanism.PROJECT,
        )
        self.sheet = CharacterSheetFactory()
        self.character = self.sheet.character
        self.room_profile = RoomProfileFactory()
        self.character.location = self.room_profile.objectdb
        self.character.save()
        LocationOwnershipFactory(
            on_room=True,
            room_profile=self.room_profile,
            holder_persona=self.sheet.primary_persona,
        )

    def test_install_creates_project_and_progression_details(self) -> None:
        result = self.action_cls().run(
            actor=self.character,
            room_profile=self.room_profile,
            feature_kind=self.kind,
            target_level=1,
        )
        self.assertTrue(result.success, result.message)
        project = Project.objects.get(kind=ProjectKind.ROOM_FEATURE_PROGRESSION)
        details = RoomFeatureProgressionDetails.objects.get(project=project)
        self.assertEqual(details.target_room_profile, self.room_profile)
        self.assertEqual(details.target_feature_kind, self.kind)
        self.assertEqual(details.target_level, 1)

    def test_install_rejected_when_room_already_has_a_feature(self) -> None:
        other_kind = RoomFeatureKindFactory(
            service_strategy=RoomFeatureServiceStrategy.COMMAND_CENTER
        )
        RoomFeatureInstanceFactory(room_profile=self.room_profile, feature_kind=other_kind, level=1)
        result = self.action_cls().run(
            actor=self.character,
            room_profile=self.room_profile,
            feature_kind=self.kind,
            target_level=1,
        )
        self.assertFalse(result.success)
        self.assertIn("already has a feature", result.message)

    def test_rejected_without_ownership_or_tenancy(self) -> None:
        other_room = RoomProfileFactory()
        self.character.location = other_room.objectdb
        self.character.save()
        result = self.action_cls().run(
            actor=self.character,
            room_profile=other_room,
            feature_kind=self.kind,
            target_level=1,
        )
        self.assertFalse(result.success)

    def test_upgrade_succeeds_at_higher_level(self) -> None:
        RoomFeatureInstanceFactory(room_profile=self.room_profile, feature_kind=self.kind, level=1)
        result = self.action_cls().run(
            actor=self.character,
            room_profile=self.room_profile,
            feature_kind=self.kind,
            target_level=2,
        )
        self.assertTrue(result.success, result.message)
        project = Project.objects.get(kind=ProjectKind.ROOM_FEATURE_PROGRESSION)
        details = RoomFeatureProgressionDetails.objects.get(project=project)
        self.assertEqual(details.target_room_profile, self.room_profile)
        self.assertEqual(details.target_feature_kind, self.kind)
        self.assertEqual(details.target_level, 2)

    def test_upgrade_rejected_when_target_level_not_higher(self) -> None:
        RoomFeatureInstanceFactory(room_profile=self.room_profile, feature_kind=self.kind, level=2)
        result = self.action_cls().run(
            actor=self.character,
            room_profile=self.room_profile,
            feature_kind=self.kind,
            target_level=2,
        )
        self.assertFalse(result.success)
        self.assertIn("not be an upgrade", result.message)

    def test_install_rejected_when_mechanism_is_ritual(self) -> None:
        ritual_kind = RoomFeatureKindFactory(
            service_strategy=RoomFeatureServiceStrategy.GRANARY,
            install_mechanism=RoomFeatureInstallMechanism.RITUAL,
        )
        result = self.action_cls().run(
            actor=self.character,
            room_profile=self.room_profile,
            feature_kind=ritual_kind,
            target_level=1,
        )
        self.assertFalse(result.success)
        self.assertIn("cannot be installed via a project", result.message)
