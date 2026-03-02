"""
Tests for distinctions API views.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from world.character_creation.factories import CharacterDraftFactory
from world.distinctions.factories import (
    DistinctionCategoryFactory,
    DistinctionEffectFactory,
    DistinctionFactory,
    DistinctionTagFactory,
)
from world.mechanics.factories import (
    ModifierCategoryFactory,
    ModifierTypeFactory,
)


class DistinctionCategoryViewSetTests(TestCase):
    """Tests for DistinctionCategoryViewSet."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data."""
        User = get_user_model()
        cls.user = User.objects.create_user(username="testuser", password="testpass")
        cls.category1 = DistinctionCategoryFactory(name="TestPhysical", display_order=1)
        cls.category2 = DistinctionCategoryFactory(name="TestMental", display_order=2)

    def setUp(self):
        """Set up test client."""
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_list_categories_authenticated(self):
        """Authenticated users can list categories."""
        response = self.client.get("/api/distinctions/categories/")
        assert response.status_code == status.HTTP_200_OK
        # Includes seeded categories from migration + our test categories
        assert len(response.data) >= 2
        names = [c["name"] for c in response.data]
        assert "TestPhysical" in names
        assert "TestMental" in names

    def test_list_categories_unauthenticated(self):
        """Unauthenticated users cannot list categories."""
        self.client.force_authenticate(user=None)
        response = self.client.get("/api/distinctions/categories/")
        # DRF returns 403 for unauthenticated requests with SessionAuthentication
        assert response.status_code in (
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        )

    def test_retrieve_category(self):
        """Can retrieve a single category."""
        response = self.client.get(f"/api/distinctions/categories/{self.category1.id}/")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["name"] == "TestPhysical"
        assert response.data["slug"] == self.category1.slug


class DistinctionViewSetTests(TestCase):
    """Tests for DistinctionViewSet."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data."""
        User = get_user_model()
        cls.user = User.objects.create_user(username="testuser", password="testpass")
        cls.category = DistinctionCategoryFactory(name="TestCategory")
        cls.tag = DistinctionTagFactory(name="Combat")
        cls.distinction1 = DistinctionFactory(
            name="Strong",
            category=cls.category,
            description="Physically strong",
            is_active=True,
        )
        cls.distinction1.tags.add(cls.tag)
        cls.distinction2 = DistinctionFactory(
            name="Weak",
            category=cls.category,
            description="Physically weak",
            cost_per_rank=-5,
            is_active=True,
        )
        cls.inactive = DistinctionFactory(name="Inactive", is_active=False)

    def setUp(self):
        """Set up test client."""
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_list_distinctions_authenticated(self):
        """Authenticated users can list distinctions."""
        response = self.client.get("/api/distinctions/distinctions/")
        assert response.status_code == status.HTTP_200_OK
        # Includes seeded distinctions + our test distinctions
        assert len(response.data) >= 2
        names = [d["name"] for d in response.data]
        assert "Strong" in names
        assert "Weak" in names

    def test_list_excludes_inactive(self):
        """Inactive distinctions are not listed."""
        response = self.client.get("/api/distinctions/distinctions/")
        names = [d["name"] for d in response.data]
        assert "Inactive" not in names

    def test_filter_by_category(self):
        """Can filter distinctions by category slug."""
        other_category = DistinctionCategoryFactory(name="OtherTestCategory")
        DistinctionFactory(name="Smart", category=other_category, is_active=True)

        response = self.client.get(f"/api/distinctions/distinctions/?category={self.category.slug}")
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 2
        for d in response.data:
            assert d["category_slug"] == self.category.slug

    def test_search_by_name(self):
        """Can search distinctions by name."""
        response = self.client.get("/api/distinctions/distinctions/?search=Strong")
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 1
        assert response.data[0]["name"] == "Strong"

    def test_search_by_description(self):
        """Can search distinctions by description."""
        response = self.client.get("/api/distinctions/distinctions/?search=weak")
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 1
        assert response.data[0]["name"] == "Weak"

    def test_search_by_tag(self):
        """Can search distinctions by tag name."""
        response = self.client.get("/api/distinctions/distinctions/?search=Combat")
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 1
        assert response.data[0]["name"] == "Strong"

    def test_retrieve_distinction(self):
        """Can retrieve a single distinction with full details."""
        response = self.client.get(f"/api/distinctions/distinctions/{self.distinction1.id}/")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["name"] == "Strong"
        assert "effects" in response.data
        assert "prerequisite_description" in response.data

    def test_unauthenticated_access_denied(self):
        """Unauthenticated users cannot access distinctions."""
        self.client.force_authenticate(user=None)
        response = self.client.get("/api/distinctions/distinctions/")
        # DRF returns 403 for unauthenticated requests with SessionAuthentication
        assert response.status_code in (
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        )

    def test_distinctions_ordered_by_cost_descending(self):
        """Distinctions should be ordered by cost descending, then name ascending."""
        DistinctionFactory(
            name="Expensive", category=self.category, cost_per_rank=20, is_active=True
        )
        DistinctionFactory(name="Cheap", category=self.category, cost_per_rank=5, is_active=True)
        DistinctionFactory(
            name="Disadvantage", category=self.category, cost_per_rank=-10, is_active=True
        )
        DistinctionFactory(name="Medium", category=self.category, cost_per_rank=10, is_active=True)

        response = self.client.get("/api/distinctions/distinctions/")
        assert response.status_code == status.HTTP_200_OK

        names = [d["name"] for d in response.data]
        # Verify relative ordering: expensive > medium > cheap > disadvantage
        assert names.index("Expensive") < names.index("Medium")
        assert names.index("Medium") < names.index("Cheap")
        assert names.index("Cheap") < names.index("Disadvantage")


class DraftDistinctionViewSetTests(TestCase):
    """Tests for DraftDistinctionViewSet."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data."""
        User = get_user_model()
        cls.user = User.objects.create_user(username="testuser", password="testpass")
        cls.other_user = User.objects.create_user(username="otheruser", password="testpass")
        cls.category = DistinctionCategoryFactory(name="DraftTestCategory")
        cls.distinction = DistinctionFactory(
            name="Strong",
            category=cls.category,
            cost_per_rank=10,
            max_rank=3,
            is_active=True,
        )
        cls.distinction2 = DistinctionFactory(
            name="Tough",
            category=cls.category,
            cost_per_rank=5,
            is_active=True,
        )

    def setUp(self):
        """Set up test client and draft."""
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.draft = CharacterDraftFactory(account=self.user, draft_data={})

    def test_list_draft_distinctions_empty(self):
        """List returns empty array for new draft."""
        response = self.client.get(f"/api/distinctions/drafts/{self.draft.id}/distinctions/")
        assert response.status_code == status.HTTP_200_OK
        assert response.data == []

    def test_list_draft_distinctions_with_data(self):
        """List returns distinctions from draft_data."""
        self.draft.draft_data["distinctions"] = [
            {"distinction_id": self.distinction.id, "rank": 1, "cost": 10}
        ]
        self.draft.save()

        response = self.client.get(f"/api/distinctions/drafts/{self.draft.id}/distinctions/")
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 1

    def test_add_distinction_to_draft(self):
        """Can add a distinction to a draft."""
        response = self.client.post(
            f"/api/distinctions/drafts/{self.draft.id}/distinctions/",
            {"distinction_id": self.distinction.id, "rank": 2},
            format="json",
        )
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["distinction_id"] == self.distinction.id
        assert response.data["rank"] == 2
        assert response.data["cost"] == 20  # 10 * 2 ranks

        # Verify draft was updated
        self.draft.refresh_from_db()
        assert len(self.draft.draft_data["distinctions"]) == 1

    def test_add_distinction_default_rank(self):
        """Adding without rank defaults to 1."""
        response = self.client.post(
            f"/api/distinctions/drafts/{self.draft.id}/distinctions/",
            {"distinction_id": self.distinction.id},
            format="json",
        )
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["rank"] == 1

    def test_add_distinction_invalid_rank(self):
        """Cannot add distinction with invalid rank."""
        response = self.client.post(
            f"/api/distinctions/drafts/{self.draft.id}/distinctions/",
            {"distinction_id": self.distinction.id, "rank": 5},  # max is 3
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "Rank must be between" in response.data["detail"]

    def test_add_distinction_already_on_draft(self):
        """Cannot add distinction that's already on draft."""
        self.draft.draft_data["distinctions"] = [
            {"distinction_id": self.distinction.id, "rank": 1, "cost": 10}
        ]
        self.draft.save()

        response = self.client.post(
            f"/api/distinctions/drafts/{self.draft.id}/distinctions/",
            {"distinction_id": self.distinction.id},
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "already on draft" in response.data["detail"]

    def test_add_distinction_inactive(self):
        """Cannot add inactive distinction."""
        inactive = DistinctionFactory(name="Inactive", is_active=False)
        response = self.client.post(
            f"/api/distinctions/drafts/{self.draft.id}/distinctions/",
            {"distinction_id": inactive.id},
            format="json",
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_add_distinction_mutual_exclusion(self):
        """Cannot add distinction that conflicts with existing."""
        conflicting = DistinctionFactory(name="Conflicting", category=self.category, is_active=True)
        self.distinction.mutually_exclusive_with.add(conflicting)

        # Add first distinction
        self.draft.draft_data["distinctions"] = [
            {"distinction_id": self.distinction.id, "rank": 1, "cost": 10}
        ]
        self.draft.save()

        # Try to add conflicting
        response = self.client.post(
            f"/api/distinctions/drafts/{self.draft.id}/distinctions/",
            {"distinction_id": conflicting.id},
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "Mutually exclusive" in response.data["detail"]

    def test_add_distinction_variant_exclusion(self):
        """Cannot add variant when sibling variant already selected."""
        # Create parent with variants_are_mutually_exclusive=True
        parent = DistinctionFactory(
            name="Parent",
            category=self.category,
            is_active=True,
            variants_are_mutually_exclusive=True,
        )
        variant1 = DistinctionFactory(
            name="Variant 1",
            category=self.category,
            is_active=True,
            parent_distinction=parent,
        )
        variant2 = DistinctionFactory(
            name="Variant 2",
            category=self.category,
            is_active=True,
            parent_distinction=parent,
        )

        # Add first variant to draft
        self.draft.draft_data["distinctions"] = [
            {"distinction_id": variant1.id, "rank": 1, "cost": 10}
        ]
        self.draft.save()

        # Try to add second variant - should fail
        response = self.client.post(
            f"/api/distinctions/drafts/{self.draft.id}/distinctions/",
            {"distinction_id": variant2.id},
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "only select one" in response.data["detail"].lower()

    def test_remove_distinction_from_draft(self):
        """Can remove a distinction from a draft."""
        self.draft.draft_data["distinctions"] = [
            {"distinction_id": self.distinction.id, "rank": 1, "cost": 10}
        ]
        self.draft.save()

        response = self.client.delete(
            f"/api/distinctions/drafts/{self.draft.id}/distinctions/{self.distinction.id}/"
        )
        assert response.status_code == status.HTTP_204_NO_CONTENT

        # Verify draft was updated
        self.draft.refresh_from_db()
        assert len(self.draft.draft_data["distinctions"]) == 0

    def test_remove_distinction_not_on_draft(self):
        """Cannot remove distinction that isn't on draft."""
        response = self.client.delete(
            f"/api/distinctions/drafts/{self.draft.id}/distinctions/{self.distinction.id}/"
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_swap_distinctions(self):
        """Can swap mutually exclusive distinctions."""
        # Set up mutual exclusion
        conflicting = DistinctionFactory(name="Conflicting", category=self.category, is_active=True)
        self.distinction.mutually_exclusive_with.add(conflicting)

        # Add first distinction
        self.draft.draft_data["distinctions"] = [
            {"distinction_id": self.distinction.id, "rank": 1, "cost": 10}
        ]
        self.draft.save()

        # Swap to conflicting
        response = self.client.post(
            f"/api/distinctions/drafts/{self.draft.id}/distinctions/swap/",
            {"remove_id": self.distinction.id, "add_id": conflicting.id},
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.data["removed"] == self.distinction.id
        assert response.data["added"]["distinction_id"] == conflicting.id

        # Verify draft state
        self.draft.refresh_from_db()
        ids = [d["distinction_id"] for d in self.draft.draft_data["distinctions"]]
        assert self.distinction.id not in ids
        assert conflicting.id in ids

    def test_access_other_users_draft_denied(self):
        """Cannot access another user's draft."""
        other_draft = CharacterDraftFactory(account=self.other_user)
        response = self.client.get(f"/api/distinctions/drafts/{other_draft.id}/distinctions/")
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_unauthenticated_access_denied(self):
        """Unauthenticated users cannot access draft distinctions."""
        self.client.force_authenticate(user=None)
        response = self.client.get(f"/api/distinctions/drafts/{self.draft.id}/distinctions/")
        # DRF returns 403 for unauthenticated requests with SessionAuthentication
        assert response.status_code in (
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        )

    # =========================================================================
    # Sync endpoint tests
    # =========================================================================

    def test_sync_distinctions_success(self):
        """Can sync multiple distinctions at once."""
        response = self.client.put(
            f"/api/distinctions/drafts/{self.draft.id}/distinctions/sync/",
            {
                "distinctions": [
                    {"id": self.distinction.id, "rank": 1},
                    {"id": self.distinction2.id, "rank": 1},
                ]
            },
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["distinctions"]) == 2

        # Verify draft was updated
        self.draft.refresh_from_db()
        ids = [d["distinction_id"] for d in self.draft.draft_data["distinctions"]]
        assert self.distinction.id in ids
        assert self.distinction2.id in ids

    def test_sync_distinctions_empty_clears_all(self):
        """Syncing empty list clears all distinctions."""
        # Add some distinctions first
        self.draft.draft_data["distinctions"] = [
            {"distinction_id": self.distinction.id, "rank": 1, "cost": 10}
        ]
        self.draft.save()

        response = self.client.put(
            f"/api/distinctions/drafts/{self.draft.id}/distinctions/sync/",
            {"distinctions": []},
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.data["distinctions"] == []
        assert "stat_adjustments" in response.data

        # Verify draft was cleared
        self.draft.refresh_from_db()
        assert self.draft.draft_data["distinctions"] == []

    def test_sync_distinctions_replaces_existing(self):
        """Sync replaces existing distinctions entirely."""
        # Start with distinction1
        self.draft.draft_data["distinctions"] = [
            {"distinction_id": self.distinction.id, "rank": 1, "cost": 10}
        ]
        self.draft.save()

        # Sync with only distinction2
        response = self.client.put(
            f"/api/distinctions/drafts/{self.draft.id}/distinctions/sync/",
            {"distinctions": [{"id": self.distinction2.id, "rank": 1}]},
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK

        # Verify only distinction2 remains
        self.draft.refresh_from_db()
        ids = [d["distinction_id"] for d in self.draft.draft_data["distinctions"]]
        assert self.distinction.id not in ids
        assert self.distinction2.id in ids

    def test_sync_distinctions_mutual_exclusion_conflict(self):
        """Cannot sync distinctions with mutual exclusion conflicts."""
        conflicting = DistinctionFactory(name="Conflicting", category=self.category, is_active=True)
        self.distinction.mutually_exclusive_with.add(conflicting)

        response = self.client.put(
            f"/api/distinctions/drafts/{self.draft.id}/distinctions/sync/",
            {
                "distinctions": [
                    {"id": self.distinction.id, "rank": 1},
                    {"id": conflicting.id, "rank": 1},
                ]
            },
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "mutually exclusive" in response.data["detail"].lower()

    def test_sync_distinctions_variant_exclusion_conflict(self):
        """Cannot sync conflicting variant distinctions."""
        parent = DistinctionFactory(
            name="Parent",
            category=self.category,
            is_active=True,
            variants_are_mutually_exclusive=True,
        )
        variant1 = DistinctionFactory(
            name="Variant 1",
            category=self.category,
            is_active=True,
            parent_distinction=parent,
        )
        variant2 = DistinctionFactory(
            name="Variant 2",
            category=self.category,
            is_active=True,
            parent_distinction=parent,
        )

        response = self.client.put(
            f"/api/distinctions/drafts/{self.draft.id}/distinctions/sync/",
            {
                "distinctions": [
                    {"id": variant1.id, "rank": 1},
                    {"id": variant2.id, "rank": 1},
                ]
            },
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "only select one" in response.data["detail"].lower()

    def test_sync_distinctions_invalid_ids(self):
        """Syncing with invalid/inactive IDs returns 400."""
        inactive = DistinctionFactory(name="Inactive", is_active=False)

        response = self.client.put(
            f"/api/distinctions/drafts/{self.draft.id}/distinctions/sync/",
            {
                "distinctions": [
                    {"id": inactive.id, "rank": 1},
                    {"id": 99999, "rank": 1},
                ]
            },
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "not found or inactive" in response.data["detail"].lower()

    def test_sync_distinctions_not_a_list(self):
        """Syncing with non-list data returns 400."""
        response = self.client.put(
            f"/api/distinctions/drafts/{self.draft.id}/distinctions/sync/",
            {"distinctions": "not a list"},
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "must be a list" in response.data["detail"].lower()

    def test_sync_distinctions_missing_field(self):
        """Syncing without distinctions field returns 400."""
        response = self.client.put(
            f"/api/distinctions/drafts/{self.draft.id}/distinctions/sync/",
            {},
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "required" in response.data["detail"].lower()

    def test_sync_distinctions_with_ranks(self):
        """Can sync distinctions with specific ranks."""
        response = self.client.put(
            f"/api/distinctions/drafts/{self.draft.id}/distinctions/sync/",
            {
                "distinctions": [
                    {"id": self.distinction.id, "rank": 2},
                    {"id": self.distinction2.id, "rank": 1},
                ]
            },
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["distinctions"]) == 2

        # Verify ranks are correct
        self.draft.refresh_from_db()
        distinctions_by_id = {d["distinction_id"]: d for d in self.draft.draft_data["distinctions"]}
        assert distinctions_by_id[self.distinction.id]["rank"] == 2
        assert distinctions_by_id[self.distinction.id]["cost"] == 20  # 10 * 2
        assert distinctions_by_id[self.distinction2.id]["rank"] == 1

    def test_sync_distinctions_rank_exceeds_max(self):
        """Cannot sync a distinction with rank exceeding max_rank."""
        response = self.client.put(
            f"/api/distinctions/drafts/{self.draft.id}/distinctions/sync/",
            {
                "distinctions": [
                    {"id": self.distinction.id, "rank": 99},
                ]
            },
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_sync_distinctions_rank_zero_rejected(self):
        """Cannot sync a distinction with rank 0."""
        response = self.client.put(
            f"/api/distinctions/drafts/{self.draft.id}/distinctions/sync/",
            {
                "distinctions": [
                    {"id": self.distinction.id, "rank": 0},
                ]
            },
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST


class SyncStatAdjustmentsTests(TestCase):
    """Test that sync endpoint returns stat_adjustments."""

    @classmethod
    def setUpTestData(cls):
        cls.stat_category = ModifierCategoryFactory(name="stat")
        cls.strength_type = ModifierTypeFactory(name="strength", category=cls.stat_category)

    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="statcapuser", password="testpass")
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.draft = CharacterDraftFactory(account=self.user)

    def test_sync_returns_stat_adjustments_on_overcap(self):
        """Syncing a distinction that causes overcap returns adjustments."""
        self.draft.draft_data["stats"] = {
            "strength": 50,
            "agility": 20,
            "stamina": 20,
            "charm": 20,
            "presence": 20,
            "perception": 20,
            "intellect": 20,
            "wits": 20,
            "willpower": 20,
        }
        self.draft.save(update_fields=["draft_data"])

        distinction = DistinctionFactory()
        DistinctionEffectFactory(
            distinction=distinction,
            target=self.strength_type,
            value_per_rank=10,
            description="",
        )

        url = f"/api/distinctions/drafts/{self.draft.id}/distinctions/sync/"
        response = self.client.put(
            url,
            {"distinctions": [{"id": distinction.id, "rank": 1}]},
            format="json",
        )

        assert response.status_code == 200
        assert "stat_adjustments" in response.data
        assert len(response.data["stat_adjustments"]) == 1
        adj = response.data["stat_adjustments"][0]
        assert adj["stat"] == "strength"
        assert adj["old_display"] == 5
        assert adj["new_display"] == 4

    def test_sync_returns_empty_adjustments_when_no_overcap(self):
        """Syncing without overcap returns empty adjustments."""
        self.draft.draft_data["stats"] = {
            "strength": 30,
            "agility": 20,
            "stamina": 20,
            "charm": 20,
            "presence": 20,
            "perception": 20,
            "intellect": 20,
            "wits": 20,
            "willpower": 20,
        }
        self.draft.save(update_fields=["draft_data"])

        distinction = DistinctionFactory()
        DistinctionEffectFactory(
            distinction=distinction,
            target=self.strength_type,
            value_per_rank=10,
            description="",
        )

        url = f"/api/distinctions/drafts/{self.draft.id}/distinctions/sync/"
        response = self.client.put(
            url,
            {"distinctions": [{"id": distinction.id, "rank": 1}]},
            format="json",
        )

        assert response.status_code == 200
        assert response.data["stat_adjustments"] == []

    def test_sync_response_includes_distinctions(self):
        """Sync response includes the distinctions list."""
        distinction = DistinctionFactory()

        url = f"/api/distinctions/drafts/{self.draft.id}/distinctions/sync/"
        response = self.client.put(
            url,
            {"distinctions": [{"id": distinction.id, "rank": 1}]},
            format="json",
        )

        assert response.status_code == 200
        assert "distinctions" in response.data
        assert len(response.data["distinctions"]) == 1
