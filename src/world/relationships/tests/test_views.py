"""Tests for relationships API views."""

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from world.character_sheets.factories import CharacterSheetFactory
from world.relationships.constants import TrackSign
from world.relationships.factories import (
    CharacterRelationshipFactory,
    HybridRelationshipTypeFactory,
    HybridRequirementFactory,
    RelationshipConditionFactory,
    RelationshipTierFactory,
    RelationshipTrackFactory,
    RelationshipTrackProgressFactory,
)


class RelationshipTrackViewSetTests(TestCase):
    """Tests for RelationshipTrackViewSet."""

    @classmethod
    def setUpTestData(cls) -> None:
        """Set up test data."""
        User = get_user_model()
        cls.user = User.objects.create_user(username="trackuser", password="testpass")

        cls.track = RelationshipTrackFactory(name="Trust", sign=TrackSign.POSITIVE)
        cls.tier1 = RelationshipTierFactory(
            track=cls.track, name="Wary", tier_number=0, point_threshold=0
        )
        cls.tier2 = RelationshipTierFactory(
            track=cls.track, name="Acquaintance", tier_number=1, point_threshold=10
        )
        cls.track2 = RelationshipTrackFactory(name="Fear", sign=TrackSign.NEGATIVE)

    def setUp(self) -> None:
        """Set up test client."""
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_list_tracks(self) -> None:
        """Authenticated users can list tracks."""
        response = self.client.get("/api/relationships/tracks/")
        assert response.status_code == status.HTTP_200_OK
        assert isinstance(response.data, list)
        names = [t["name"] for t in response.data]
        assert "Trust" in names
        assert "Fear" in names

    def test_detail_includes_nested_tiers(self) -> None:
        """Track detail includes nested tier data."""
        response = self.client.get(f"/api/relationships/tracks/{self.track.pk}/")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["name"] == "Trust"
        assert response.data["sign"] == TrackSign.POSITIVE
        tiers = response.data["tiers"]
        assert len(tiers) == 2
        tier_names = [t["name"] for t in tiers]
        assert "Wary" in tier_names
        assert "Acquaintance" in tier_names

    def test_unauthenticated_rejected(self) -> None:
        """Unauthenticated users cannot access tracks."""
        self.client.force_authenticate(user=None)
        response = self.client.get("/api/relationships/tracks/")
        assert response.status_code in (
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        )

    def test_tracks_no_pagination(self) -> None:
        """Tracks endpoint returns a flat list (no pagination wrapper)."""
        response = self.client.get("/api/relationships/tracks/")
        assert response.status_code == status.HTTP_200_OK
        assert isinstance(response.data, list)

    def test_tracks_read_only(self) -> None:
        """Tracks viewset is read-only; POST should fail."""
        response = self.client.post(
            "/api/relationships/tracks/",
            {"name": "New", "slug": "new", "sign": "positive"},
            format="json",
        )
        assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED


class CharacterRelationshipViewSetTests(TestCase):
    """Tests for CharacterRelationshipViewSet."""

    @classmethod
    def setUpTestData(cls) -> None:
        """Set up test data."""
        User = get_user_model()
        cls.user = User.objects.create_user(username="reluser", password="testpass")

        cls.sheet1 = CharacterSheetFactory()
        cls.sheet2 = CharacterSheetFactory()
        cls.sheet3 = CharacterSheetFactory()

        cls.track = RelationshipTrackFactory(name="Respect", sign=TrackSign.POSITIVE)
        cls.tier = RelationshipTierFactory(
            track=cls.track, name="Acknowledged", tier_number=0, point_threshold=0
        )

        cls.rel1 = CharacterRelationshipFactory(source=cls.sheet1, target=cls.sheet2)
        cls.rel2 = CharacterRelationshipFactory(source=cls.sheet1, target=cls.sheet3)
        cls.rel3 = CharacterRelationshipFactory(source=cls.sheet2, target=cls.sheet1)

        # Add track progress to rel1
        cls.progress = RelationshipTrackProgressFactory(
            relationship=cls.rel1, track=cls.track, points=25
        )

    def setUp(self) -> None:
        """Set up test client."""
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_list_relationships(self) -> None:
        """Authenticated users can list relationships."""
        response = self.client.get("/api/relationships/relationships/")
        assert response.status_code == status.HTTP_200_OK
        data = self._get_results(response.data)
        assert len(data) >= 3

    def test_list_uses_list_serializer(self) -> None:
        """List response uses lightweight serializer (no track_progress)."""
        response = self.client.get("/api/relationships/relationships/")
        assert response.status_code == status.HTTP_200_OK
        data = self._get_results(response.data)
        first = data[0]
        # List serializer should not include track_progress
        assert "track_progress" not in first
        # But should include summary fields
        assert "source_name" in first
        assert "absolute_value" in first
        assert "affection" in first

    def test_filter_by_source(self) -> None:
        """Can filter relationships by source."""
        response = self.client.get(f"/api/relationships/relationships/?source={self.sheet1.pk}")
        assert response.status_code == status.HTTP_200_OK
        data = self._get_results(response.data)
        assert len(data) == 2
        for rel in data:
            assert rel["source"] == self.sheet1.pk

    def test_detail_includes_track_progress(self) -> None:
        """Detail response includes nested track_progress."""
        response = self.client.get(f"/api/relationships/relationships/{self.rel1.id}/")
        assert response.status_code == status.HTTP_200_OK
        assert "track_progress" in response.data
        progress_list = response.data["track_progress"]
        assert len(progress_list) == 1
        progress = progress_list[0]
        assert progress["track"] == self.track.pk
        assert progress["track_name"] == "Respect"
        assert progress["points"] == 25
        assert progress["current_tier_name"] == "Acknowledged"

    def test_detail_includes_computed_fields(self) -> None:
        """Detail response includes absolute_value and affection."""
        response = self.client.get(f"/api/relationships/relationships/{self.rel1.id}/")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["absolute_value"] == 25
        assert response.data["affection"] == 25

    def test_unauthenticated_rejected(self) -> None:
        """Unauthenticated users cannot access relationships."""
        self.client.force_authenticate(user=None)
        response = self.client.get("/api/relationships/relationships/")
        assert response.status_code in (
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        )

    def test_relationships_read_only(self) -> None:
        """Viewset is read-only; POST should fail."""
        response = self.client.post(
            "/api/relationships/relationships/",
            {"source": self.sheet1.pk, "target": self.sheet2.pk},
            format="json",
        )
        assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED

    def _get_results(self, response_data: dict | list) -> list:
        """Extract results from paginated or non-paginated response."""
        if isinstance(response_data, dict) and "results" in response_data:
            return response_data["results"]
        return response_data


class RelationshipConditionViewSetTests(TestCase):
    """Tests for RelationshipConditionViewSet."""

    @classmethod
    def setUpTestData(cls) -> None:
        """Set up test data."""
        User = get_user_model()
        cls.user = User.objects.create_user(username="conduser", password="testpass")
        cls.condition = RelationshipConditionFactory(name="Trusts", display_order=1)

    def setUp(self) -> None:
        """Set up test client."""
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_list_conditions(self) -> None:
        """Authenticated users can list conditions."""
        response = self.client.get("/api/relationships/conditions/")
        assert response.status_code == status.HTTP_200_OK
        assert isinstance(response.data, list)
        names = [c["name"] for c in response.data]
        assert "Trusts" in names

    def test_retrieve_condition(self) -> None:
        """Can retrieve a single condition."""
        response = self.client.get(f"/api/relationships/conditions/{self.condition.pk}/")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["name"] == "Trusts"
        assert response.data["display_order"] == 1


class HybridRelationshipTypeViewSetTests(TestCase):
    """Tests for HybridRelationshipTypeViewSet."""

    @classmethod
    def setUpTestData(cls) -> None:
        """Set up test data."""
        User = get_user_model()
        cls.user = User.objects.create_user(username="hybriduser", password="testpass")

        cls.track_trust = RelationshipTrackFactory(name="TrustH", sign=TrackSign.POSITIVE)
        cls.track_respect = RelationshipTrackFactory(name="RespectH", sign=TrackSign.POSITIVE)
        cls.hybrid = HybridRelationshipTypeFactory(name="Devotion", slug="devotion")
        HybridRequirementFactory(hybrid_type=cls.hybrid, track=cls.track_trust, minimum_tier=2)
        HybridRequirementFactory(hybrid_type=cls.hybrid, track=cls.track_respect, minimum_tier=1)

    def setUp(self) -> None:
        """Set up test client."""
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_list_hybrid_types(self) -> None:
        """Authenticated users can list hybrid types."""
        response = self.client.get("/api/relationships/hybrid-types/")
        assert response.status_code == status.HTTP_200_OK
        assert isinstance(response.data, list)
        names = [h["name"] for h in response.data]
        assert "Devotion" in names

    def test_detail_includes_requirements(self) -> None:
        """Hybrid type detail includes nested requirements."""
        response = self.client.get(f"/api/relationships/hybrid-types/{self.hybrid.pk}/")
        assert response.status_code == status.HTTP_200_OK
        reqs = response.data["requirements"]
        assert len(reqs) == 2
        track_names = {r["track_name"] for r in reqs}
        assert "TrustH" in track_names
        assert "RespectH" in track_names
