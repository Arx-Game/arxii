"""Tests for magic system API ViewSets."""

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from evennia_extensions.factories import AccountFactory
from world.magic.factories import (
    AffinityModifierTypeFactory,
    EffectTypeFactory,
    GiftFactory,
    ResonanceModifierTypeFactory,
    RestrictionFactory,
    TechniqueFactory,
    TechniqueStyleFactory,
)


class TechniqueStyleViewSetTest(APITestCase):
    """Tests for TechniqueStyleViewSet."""

    @classmethod
    def setUpTestData(cls):
        cls.user = AccountFactory()
        cls.style = TechniqueStyleFactory(name="Test Manifestation")

    def test_list_requires_auth(self):
        """Test that listing styles requires authentication."""
        url = reverse("magic:technique-style-list")
        response = self.client.get(url)
        self.assertIn(
            response.status_code,
            [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN],
        )

    def test_list_authenticated(self):
        """Test listing styles when authenticated."""
        self.client.force_authenticate(user=self.user)
        url = reverse("magic:technique-style-list")
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_retrieve(self):
        """Test retrieving a single style."""
        self.client.force_authenticate(user=self.user)
        url = reverse("magic:technique-style-detail", args=[self.style.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["name"], "Test Manifestation")


class EffectTypeViewSetTest(APITestCase):
    """Tests for EffectTypeViewSet."""

    @classmethod
    def setUpTestData(cls):
        cls.user = AccountFactory()
        cls.attack = EffectTypeFactory(name="Test Attack")

    def test_list_requires_auth(self):
        """Test that listing effect types requires authentication."""
        url = reverse("magic:effect-type-list")
        response = self.client.get(url)
        self.assertIn(
            response.status_code,
            [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN],
        )

    def test_list_authenticated(self):
        """Test listing effect types when authenticated."""
        self.client.force_authenticate(user=self.user)
        url = reverse("magic:effect-type-list")
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_retrieve(self):
        """Test retrieving a single effect type."""
        self.client.force_authenticate(user=self.user)
        url = reverse("magic:effect-type-detail", args=[self.attack.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["name"], "Test Attack")


class RestrictionViewSetTest(APITestCase):
    """Tests for RestrictionViewSet."""

    @classmethod
    def setUpTestData(cls):
        cls.user = AccountFactory()
        cls.effect_type = EffectTypeFactory(name="Test Effect")
        cls.restriction = RestrictionFactory(
            name="Test Touch Range", allowed_effect_types=[cls.effect_type]
        )

    def test_list_requires_auth(self):
        """Test that listing restrictions requires authentication."""
        url = reverse("magic:restriction-list")
        response = self.client.get(url)
        self.assertIn(
            response.status_code,
            [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN],
        )

    def test_list_authenticated(self):
        """Test listing restrictions when authenticated."""
        self.client.force_authenticate(user=self.user)
        url = reverse("magic:restriction-list")
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_filter_by_allowed_effect_types(self):
        """Test filtering restrictions by allowed effect types."""
        self.client.force_authenticate(user=self.user)
        url = reverse("magic:restriction-list")
        response = self.client.get(url, {"allowed_effect_types": self.effect_type.pk})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # No pagination on lookup tables
        names = [r["name"] for r in response.data]
        self.assertIn("Test Touch Range", names)


class GiftViewSetTest(APITestCase):
    """Tests for GiftViewSet CRUD operations."""

    @classmethod
    def setUpTestData(cls):
        cls.user = AccountFactory()
        cls.affinity = AffinityModifierTypeFactory()
        cls.resonance = ResonanceModifierTypeFactory()
        cls.gift = GiftFactory(name="Test Shadow Majesty")

    def test_list_requires_auth(self):
        """Test that listing gifts requires authentication."""
        url = reverse("magic:gift-list")
        response = self.client.get(url)
        self.assertIn(
            response.status_code,
            [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN],
        )

    def test_list_authenticated(self):
        """Test listing gifts when authenticated."""
        self.client.force_authenticate(user=self.user)
        url = reverse("magic:gift-list")
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_retrieve(self):
        """Test retrieving a single gift."""
        self.client.force_authenticate(user=self.user)
        url = reverse("magic:gift-detail", args=[self.gift.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["name"], "Test Shadow Majesty")

    def test_create_gift(self):
        """Test creating a gift via API."""
        self.client.force_authenticate(user=self.user)
        url = reverse("magic:gift-list")
        data = {
            "name": "Test New Gift",
            "affinity": self.affinity.pk,
            "resonance_ids": [self.resonance.pk],
            "description": "A new test gift",
        }
        response = self.client.post(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["name"], "Test New Gift")

    def test_update_gift(self):
        """Test updating a gift via API."""
        self.client.force_authenticate(user=self.user)
        gift = GiftFactory(affinity=self.affinity)
        gift.resonances.add(self.resonance)
        url = reverse("magic:gift-detail", args=[gift.pk])
        data = {
            "name": "Test Updated Gift",
            "affinity": self.affinity.pk,
            "resonance_ids": [self.resonance.pk],
            "description": "Updated description",
        }
        response = self.client.put(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["name"], "Test Updated Gift")

    def test_delete_gift(self):
        """Test deleting a gift via API."""
        self.client.force_authenticate(user=self.user)
        gift = GiftFactory()
        url = reverse("magic:gift-detail", args=[gift.pk])
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)


class TechniqueViewSetTest(APITestCase):
    """Tests for TechniqueViewSet CRUD operations."""

    @classmethod
    def setUpTestData(cls):
        cls.user = AccountFactory()
        cls.gift = GiftFactory(name="Test Gift")
        cls.style = TechniqueStyleFactory(name="Test Style")
        cls.effect_type = EffectTypeFactory(name="Test Effect")
        cls.technique = TechniqueFactory(
            name="Test Shadow Strike",
            gift=cls.gift,
            style=cls.style,
            effect_type=cls.effect_type,
        )

    def test_list_requires_auth(self):
        """Test that listing techniques requires authentication."""
        url = reverse("magic:technique-list")
        response = self.client.get(url)
        self.assertIn(
            response.status_code,
            [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN],
        )

    def test_list_authenticated(self):
        """Test listing techniques when authenticated."""
        self.client.force_authenticate(user=self.user)
        url = reverse("magic:technique-list")
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_filter_by_gift(self):
        """Test filtering techniques by gift."""
        self.client.force_authenticate(user=self.user)
        url = reverse("magic:technique-list")
        response = self.client.get(url, {"gift": self.gift.pk})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Handle both paginated and non-paginated responses
        results = response.data["results"] if isinstance(response.data, dict) else response.data
        self.assertGreaterEqual(len(results), 1)

    def test_filter_by_style(self):
        """Test filtering techniques by style."""
        self.client.force_authenticate(user=self.user)
        url = reverse("magic:technique-list")
        response = self.client.get(url, {"style": self.style.pk})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Handle both paginated and non-paginated responses
        results = response.data["results"] if isinstance(response.data, dict) else response.data
        self.assertGreaterEqual(len(results), 1)

    def test_retrieve(self):
        """Test retrieving a single technique."""
        self.client.force_authenticate(user=self.user)
        url = reverse("magic:technique-detail", args=[self.technique.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["name"], "Test Shadow Strike")

    def test_create_technique(self):
        """Test creating a technique via API."""
        self.client.force_authenticate(user=self.user)
        url = reverse("magic:technique-list")
        data = {
            "name": "Test New Technique",
            "gift": self.gift.pk,
            "style": self.style.pk,
            "effect_type": self.effect_type.pk,
            "level": 1,
            "anima_cost": 2,
            "description": "A new test technique",
            "restriction_ids": [],
        }
        response = self.client.post(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["name"], "Test New Technique")

    def test_create_technique_with_restrictions(self):
        """Test creating a technique with restrictions."""
        self.client.force_authenticate(user=self.user)
        restriction = RestrictionFactory(allowed_effect_types=[self.effect_type])
        url = reverse("magic:technique-list")
        data = {
            "name": "Test Restricted Technique",
            "gift": self.gift.pk,
            "style": self.style.pk,
            "effect_type": self.effect_type.pk,
            "level": 1,
            "anima_cost": 2,
            "description": "A technique with restrictions",
            "restriction_ids": [restriction.pk],
        }
        response = self.client.post(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn(restriction.pk, response.data["restriction_ids"])

    def test_update_technique(self):
        """Test updating a technique via API."""
        self.client.force_authenticate(user=self.user)
        url = reverse("magic:technique-detail", args=[self.technique.pk])
        data = {
            "name": "Test Updated Technique",
            "gift": self.gift.pk,
            "style": self.style.pk,
            "effect_type": self.effect_type.pk,
            "level": 5,
            "anima_cost": 3,
            "description": "Updated description",
            "restriction_ids": [],
        }
        response = self.client.put(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["name"], "Test Updated Technique")
        self.assertEqual(response.data["level"], 5)

    def test_delete_technique(self):
        """Test deleting a technique via API."""
        self.client.force_authenticate(user=self.user)
        technique = TechniqueFactory()
        url = reverse("magic:technique-detail", args=[technique.pk])
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)


class FacetViewSetTest(APITestCase):
    """Tests for FacetViewSet."""

    @classmethod
    def setUpTestData(cls):
        from world.magic.models import Facet

        cls.user = AccountFactory()
        cls.creatures = Facet.objects.create(name="Creatures")
        cls.mammals = Facet.objects.create(name="Mammals", parent=cls.creatures)
        cls.wolf = Facet.objects.create(name="Wolf", parent=cls.mammals)

    def test_list_facets(self):
        """Test listing facets."""
        self.client.force_authenticate(user=self.user)
        response = self.client.get("/api/magic/facets/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 3)  # Creatures, Mammals, Wolf

    def test_list_requires_auth(self):
        """Test that listing facets requires authentication."""
        response = self.client.get("/api/magic/facets/")
        self.assertIn(
            response.status_code,
            [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN],
        )

    def test_filter_by_parent(self):
        """Test filtering facets by parent."""
        self.client.force_authenticate(user=self.user)
        response = self.client.get(f"/api/magic/facets/?parent={self.creatures.id}")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["name"], "Mammals")

    def test_filter_top_level(self):
        """Test filtering for top-level facets (no parent)."""
        self.client.force_authenticate(user=self.user)
        response = self.client.get("/api/magic/facets/?parent__isnull=true")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["name"], "Creatures")

    def test_tree_endpoint(self):
        """Test tree endpoint returns nested structure."""
        self.client.force_authenticate(user=self.user)
        response = self.client.get("/api/magic/facets/tree/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Should return only top-level with nested children
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["name"], "Creatures")
        self.assertIn("children", response.data[0])


class CharacterFacetViewSetTest(APITestCase):
    """Tests for CharacterFacetViewSet."""

    @classmethod
    def setUpTestData(cls):
        from evennia_extensions.factories import CharacterFactory
        from world.character_sheets.factories import CharacterSheetFactory
        from world.magic.factories import ResonanceModifierTypeFactory
        from world.magic.models import CharacterFacet, Facet

        cls.CharacterFacet = CharacterFacet  # Make available for tests
        cls.user = AccountFactory()
        cls.character = CharacterFactory()
        cls.character.db_account = cls.user
        cls.character.save()
        cls.sheet = CharacterSheetFactory(character=cls.character)
        cls.resonance = ResonanceModifierTypeFactory()
        cls.spider = Facet.objects.create(name="Spider")

    def test_list_character_facets(self):
        """Test listing character facets."""
        self.CharacterFacet.objects.create(
            character=self.sheet,
            facet=self.spider,
            resonance=self.resonance,
        )
        self.client.force_authenticate(user=self.user)
        response = self.client.get("/api/magic/character-facets/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)

    def test_create_character_facet(self):
        """Test creating a character facet."""
        self.client.force_authenticate(user=self.user)
        response = self.client.post(
            "/api/magic/character-facets/",
            {
                "character": self.sheet.pk,
                "facet": self.spider.pk,
                "resonance": self.resonance.pk,
                "flavor_text": "Patient predator",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(self.CharacterFacet.objects.count(), 1)
