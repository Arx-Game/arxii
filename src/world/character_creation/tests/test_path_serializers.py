"""Tests for path-related serializers."""

from django.test import TestCase
from rest_framework.test import APIRequestFactory

from evennia_extensions.factories import AccountFactory
from world.character_creation.factories import CharacterDraftFactory
from world.character_creation.serializers import CharacterDraftSerializer, PathSerializer
from world.classes.factories import AspectFactory, PathAspectFactory, PathFactory
from world.classes.models import PathStage


class PathSerializerTest(TestCase):
    """Tests for PathSerializer."""

    @classmethod
    def setUpTestData(cls):
        cls.path = PathFactory(
            name="Path of Steel",
            description="The martial path",
            stage=PathStage.QUIESCENT,
            minimum_level=1,
        )
        cls.warfare = AspectFactory(name="Warfare")
        PathAspectFactory(character_path=cls.path, aspect=cls.warfare, weight=2)

    def test_serializes_path_data(self):
        """PathSerializer includes all expected fields."""
        serializer = PathSerializer(self.path)
        data = serializer.data

        self.assertEqual(data["id"], self.path.id)
        self.assertEqual(data["name"], "Path of Steel")
        self.assertEqual(data["description"], "The martial path")
        self.assertEqual(data["stage"], PathStage.QUIESCENT)
        self.assertEqual(data["minimum_level"], 1)

    def test_includes_aspect_names_without_weights(self):
        """PathSerializer includes aspect names but not weights."""
        serializer = PathSerializer(self.path)
        data = serializer.data

        self.assertIn("aspects", data)
        self.assertEqual(data["aspects"], ["Warfare"])
        # Weight should NOT be exposed to players
        self.assertNotIn("weight", str(data))


class CharacterDraftPathSerializerTest(TestCase):
    """Tests for CharacterDraft serializer with path."""

    @classmethod
    def setUpTestData(cls):
        cls.account = AccountFactory()
        cls.path = PathFactory(name="Path of Steel", stage=PathStage.QUIESCENT)
        cls.factory = APIRequestFactory()

    def test_serializes_selected_path(self):
        """CharacterDraftSerializer includes selected_path."""
        draft = CharacterDraftFactory(account=self.account, selected_path=self.path)
        request = self.factory.get("/")
        request.user = self.account

        serializer = CharacterDraftSerializer(draft, context={"request": request})
        data = serializer.data

        self.assertIn("selected_path", data)
        self.assertEqual(data["selected_path"]["name"], "Path of Steel")

    def test_accepts_selected_path_id(self):
        """CharacterDraftSerializer accepts selected_path_id for write."""
        draft = CharacterDraftFactory(account=self.account)
        request = self.factory.patch("/")
        request.user = self.account

        serializer = CharacterDraftSerializer(
            draft,
            data={"selected_path_id": self.path.id},
            partial=True,
            context={"request": request},
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)
        updated = serializer.save()
        self.assertEqual(updated.selected_path, self.path)
