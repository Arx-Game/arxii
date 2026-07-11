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
from world.roster.factories import PlayerDataFactory, RosterEntryFactory, RosterTenureFactory


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

        # cls.user owns sheet1 via a current RosterTenure — required for it to
        # read sheet1's outbound relationships under the privacy scoping.
        cls.player_data = PlayerDataFactory(account=cls.user)
        cls.roster_entry1 = RosterEntryFactory(character_sheet=cls.sheet1)
        cls.tenure1 = RosterTenureFactory(
            player_data=cls.player_data, roster_entry=cls.roster_entry1
        )

        cls.track = RelationshipTrackFactory(name="Respect", sign=TrackSign.POSITIVE)
        cls.tier = RelationshipTierFactory(
            track=cls.track, name="Acknowledged", tier_number=0, point_threshold=0
        )

        cls.rel1 = CharacterRelationshipFactory(source=cls.sheet1, target=cls.sheet2)
        cls.rel2 = CharacterRelationshipFactory(source=cls.sheet1, target=cls.sheet3)
        cls.rel3 = CharacterRelationshipFactory(source=cls.sheet2, target=cls.sheet1)

        # Add track progress to rel1
        cls.progress = RelationshipTrackProgressFactory(
            relationship=cls.rel1, track=cls.track, capacity=50, developed_points=25
        )

    def setUp(self) -> None:
        """Set up test client."""
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_list_relationships(self) -> None:
        """Authenticated users can list relationships whose source they own."""
        response = self.client.get("/api/relationships/relationships/")
        assert response.status_code == status.HTTP_200_OK
        data = self._get_results(response.data)
        # rel1 and rel2 both source from sheet1 (owned by cls.user); rel3
        # sources from sheet2 (unowned, not a soul tether) and is excluded.
        ids = [r["id"] for r in data]
        assert self.rel1.pk in ids
        assert self.rel2.pk in ids
        assert self.rel3.pk not in ids

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
        assert "developed_absolute_value" in first
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
        """Detail response includes nested track_progress with new fields."""
        response = self.client.get(f"/api/relationships/relationships/{self.rel1.id}/")
        assert response.status_code == status.HTTP_200_OK
        assert "track_progress" in response.data
        progress_list = response.data["track_progress"]
        assert len(progress_list) == 1
        progress = progress_list[0]
        assert progress["track"] == self.track.pk
        assert progress["track_name"] == "Respect"
        assert progress["capacity"] == 50
        assert progress["developed_points"] == 25
        assert progress["current_tier_name"] == "Acknowledged"

    def test_detail_includes_computed_fields(self) -> None:
        """Detail response includes absolute_value, developed_absolute_value, and affection."""
        response = self.client.get(f"/api/relationships/relationships/{self.rel1.id}/")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["developed_absolute_value"] == 25
        assert "mechanical_bonus" in response.data

    def test_unauthenticated_rejected(self) -> None:
        """Unauthenticated users cannot access relationships."""
        self.client.force_authenticate(user=None)
        response = self.client.get("/api/relationships/relationships/")
        assert response.status_code in (
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        )

    def test_filter_by_is_soul_tether(self) -> None:
        """Can filter relationships by is_soul_tether."""
        # Create one tether and one non-tether relationship between new sheets
        sheet_a = CharacterSheetFactory()
        sheet_b = CharacterSheetFactory()
        sheet_c = CharacterSheetFactory()
        tether_rel = CharacterRelationshipFactory(
            source=sheet_a, target=sheet_b, is_soul_tether=True
        )
        non_tether_rel = CharacterRelationshipFactory(
            source=sheet_a, target=sheet_c, is_soul_tether=False
        )

        response = self.client.get("/api/relationships/relationships/?is_soul_tether=true")
        assert response.status_code == status.HTTP_200_OK
        data = self._get_results(response.data)
        ids = [r["id"] for r in data]
        assert tether_rel.pk in ids
        assert non_tether_rel.pk not in ids

    def test_list_serializer_exposes_soul_tether_fields(self) -> None:
        """List serializer includes is_soul_tether and soul_tether_role fields."""
        response = self.client.get("/api/relationships/relationships/")
        assert response.status_code == status.HTTP_200_OK
        data = self._get_results(response.data)
        assert len(data) > 0
        first = data[0]
        assert "is_soul_tether" in first
        assert "soul_tether_role" in first

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


class CharacterRelationshipViewSetPrivacyTests(TestCase):
    """Privacy scoping tests for CharacterRelationshipViewSet.get_queryset (#2159).

    Numeric relationship state is author-private: the caller may only read
    rows whose ``source`` is one of their own (tenure-owned) characters, or
    rows flagged ``is_soul_tether=True`` (a ratified carve-out — the tether
    panel rendered on a foreign character's sheet depends on it).
    """

    @classmethod
    def setUpTestData(cls) -> None:
        """Set up two accounts, each with an owned character, plus a bystander."""
        User = get_user_model()
        cls.owner_user = User.objects.create_user(username="owner", password="testpass")
        cls.other_user = User.objects.create_user(username="other", password="testpass")

        cls.owner_sheet = CharacterSheetFactory()
        cls.other_sheet = CharacterSheetFactory()
        cls.bystander_sheet = CharacterSheetFactory()
        cls.tether_target_sheet = CharacterSheetFactory()

        cls.owner_player_data = PlayerDataFactory(account=cls.owner_user)
        cls.owner_roster_entry = RosterEntryFactory(character_sheet=cls.owner_sheet)
        cls.owner_tenure = RosterTenureFactory(
            player_data=cls.owner_player_data, roster_entry=cls.owner_roster_entry
        )

        # Own outbound relationship (source=owner_sheet).
        cls.own_outbound = CharacterRelationshipFactory(
            source=cls.owner_sheet, target=cls.bystander_sheet
        )
        # A pair entirely foreign to owner_user (neither side owned).
        cls.foreign_pair = CharacterRelationshipFactory(
            source=cls.other_sheet, target=cls.bystander_sheet
        )
        # A foreign soul-tether row — should remain readable via the carve-out.
        cls.foreign_tether = CharacterRelationshipFactory(
            source=cls.other_sheet, target=cls.tether_target_sheet, is_soul_tether=True
        )

    def setUp(self) -> None:
        """Set up test client."""
        self.client = APIClient()

    def test_foreign_pair_excluded_from_list(self) -> None:
        """A relationship neither owned nor soul-tethered is absent from the list."""
        self.client.force_authenticate(user=self.owner_user)
        response = self.client.get("/api/relationships/relationships/")
        assert response.status_code == status.HTTP_200_OK
        ids = [r["id"] for r in self._get_results(response.data)]
        assert self.foreign_pair.pk not in ids

    def test_foreign_pair_retrieve_404s(self) -> None:
        """Directly retrieving a foreign, non-tethered relationship 404s."""
        self.client.force_authenticate(user=self.owner_user)
        response = self.client.get(f"/api/relationships/relationships/{self.foreign_pair.pk}/")
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_own_outbound_relationship_readable(self) -> None:
        """The caller can list and retrieve their own outbound relationship."""
        self.client.force_authenticate(user=self.owner_user)
        list_response = self.client.get("/api/relationships/relationships/")
        ids = [r["id"] for r in self._get_results(list_response.data)]
        assert self.own_outbound.pk in ids

        detail_response = self.client.get(
            f"/api/relationships/relationships/{self.own_outbound.pk}/"
        )
        assert detail_response.status_code == status.HTTP_200_OK

    def test_foreign_soul_tether_readable(self) -> None:
        """A soul-tether row is readable even though neither side is owned."""
        self.client.force_authenticate(user=self.owner_user)
        list_response = self.client.get("/api/relationships/relationships/")
        ids = [r["id"] for r in self._get_results(list_response.data)]
        assert self.foreign_tether.pk in ids

        detail_response = self.client.get(
            f"/api/relationships/relationships/{self.foreign_tether.pk}/"
        )
        assert detail_response.status_code == status.HTTP_200_OK

    def test_multi_character_account_sees_non_puppeted_characters_rows(self) -> None:
        """A tenure-owned character's rows are visible even while not currently puppeted.

        Ownership is resolved via the current ``RosterTenure`` join (mirroring
        ``RelationshipUpdateViewSet``), never Evennia's live-puppet ``db_account``
        field, so an account with several owned characters sees every owned
        character's outbound rows regardless of which one it is puppeting.
        """
        second_sheet = CharacterSheetFactory()
        second_roster_entry = RosterEntryFactory(character_sheet=second_sheet)
        RosterTenureFactory(player_data=self.owner_player_data, roster_entry=second_roster_entry)
        second_outbound = CharacterRelationshipFactory(
            source=second_sheet, target=self.bystander_sheet
        )

        self.client.force_authenticate(user=self.owner_user)
        response = self.client.get("/api/relationships/relationships/")
        ids = [r["id"] for r in self._get_results(response.data)]
        assert second_outbound.pk in ids

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
