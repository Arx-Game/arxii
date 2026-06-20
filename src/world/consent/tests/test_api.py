"""API tests for the /api/consent/ endpoints."""

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from world.consent.constants import ConsentMode
from world.consent.factories import (
    SocialConsentCategoryFactory,
    SocialConsentCategoryRuleFactory,
    SocialConsentPreferenceFactory,
    SocialConsentWhitelistFactory,
)
from world.consent.models import (
    SocialConsentCategoryRule,
    SocialConsentPreference,
    SocialConsentWhitelist,
)
from world.roster.factories import PlayerDataFactory, RosterTenureFactory


class SocialConsentCategoryViewSetTests(TestCase):
    """Tests for /api/consent/categories/."""

    @classmethod
    def setUpTestData(cls):
        cls.player = PlayerDataFactory()
        cls.category_a = SocialConsentCategoryFactory(
            key="romantic", name="Romantic", display_order=1
        )
        cls.category_b = SocialConsentCategoryFactory(
            key="hostile", name="Hostile", display_order=2
        )

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(user=self.player.account)

    def test_unauthenticated_returns_401_or_403(self):
        """Unauthenticated requests are rejected."""
        self.client.force_authenticate(user=None)
        response = self.client.get("/api/consent/categories/")
        assert response.status_code in (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)

    def test_list_categories(self):
        """Authenticated users can list categories."""
        response = self.client.get("/api/consent/categories/")
        assert response.status_code == status.HTTP_200_OK
        keys = [c["key"] for c in response.data["results"]]
        assert "romantic" in keys
        assert "hostile" in keys

    def test_category_includes_action_templates(self):
        """Category detail includes action_templates list."""
        response = self.client.get(f"/api/consent/categories/{self.category_a.id}/")
        assert response.status_code == status.HTTP_200_OK
        assert "action_templates" in response.data
        assert isinstance(response.data["action_templates"], list)

    def test_categories_read_only_no_post(self):
        """POST to categories is not allowed (read-only)."""
        response = self.client.post(
            "/api/consent/categories/",
            {"key": "new", "name": "New", "display_order": 99},
            format="json",
        )
        assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED


class SocialConsentPreferenceViewSetTests(TestCase):
    """Tests for /api/consent/preferences/."""

    @classmethod
    def setUpTestData(cls):
        cls.player_a = PlayerDataFactory()
        cls.player_b = PlayerDataFactory()
        cls.tenure_a = RosterTenureFactory(player_data=cls.player_a)
        cls.tenure_b = RosterTenureFactory(player_data=cls.player_b)
        cls.pref_a = SocialConsentPreferenceFactory(tenure=cls.tenure_a, allow_social_actions=True)
        cls.pref_b = SocialConsentPreferenceFactory(tenure=cls.tenure_b, allow_social_actions=False)

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(user=self.player_a.account)

    def test_unauthenticated_returns_401_or_403(self):
        """Unauthenticated requests are rejected."""
        self.client.force_authenticate(user=None)
        response = self.client.get("/api/consent/preferences/")
        assert response.status_code in (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)

    def test_list_returns_only_own_preferences(self):
        """Listing scopes results to the requesting player's tenures."""
        response = self.client.get("/api/consent/preferences/")
        assert response.status_code == status.HTTP_200_OK
        ids = [p["id"] for p in response.data["results"]]
        assert self.pref_a.id in ids
        assert self.pref_b.id not in ids

    def test_cross_player_retrieve_returns_404(self):
        """Player A cannot retrieve player B's preference."""
        response = self.client.get(f"/api/consent/preferences/{self.pref_b.id}/")
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_cross_player_patch_returns_404(self):
        """Player A cannot patch player B's preference."""
        response = self.client.patch(
            f"/api/consent/preferences/{self.pref_b.id}/",
            {"allow_social_actions": True},
            format="json",
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_patch_own_preference(self):
        """Player can patch their own preference."""
        response = self.client.patch(
            f"/api/consent/preferences/{self.pref_a.id}/",
            {"allow_social_actions": False},
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK
        self.pref_a.refresh_from_db()
        assert self.pref_a.allow_social_actions is False

    def test_for_tenure_returns_existing_preference(self):
        """for-tenure action returns existing preference row."""
        response = self.client.get(f"/api/consent/preferences/for-tenure/{self.tenure_a.id}/")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["tenure"] == self.tenure_a.id

    def test_for_tenure_returns_default_when_absent(self):
        """for-tenure action returns default when no row exists."""
        tenure_no_pref = RosterTenureFactory(player_data=self.player_a)
        response = self.client.get(f"/api/consent/preferences/for-tenure/{tenure_no_pref.id}/")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["allow_social_actions"] is True
        # Confirm it was NOT persisted
        assert not SocialConsentPreference.objects.filter(tenure=tenure_no_pref).exists()

    def test_for_tenure_cross_player_returns_404(self):
        """for-tenure action does not expose another player's tenure."""
        response = self.client.get(f"/api/consent/preferences/for-tenure/{self.tenure_b.id}/")
        # Should 404 (row exists but belongs to another player, scoped queryset + DoesNotExist)
        # The synthesized default would leak tenure existence; the view returns 404.
        assert response.status_code == status.HTTP_404_NOT_FOUND


class SocialConsentCategoryRuleViewSetTests(TestCase):
    """Tests for /api/consent/category-rules/."""

    @classmethod
    def setUpTestData(cls):
        cls.player_a = PlayerDataFactory()
        cls.player_b = PlayerDataFactory()
        cls.tenure_a = RosterTenureFactory(player_data=cls.player_a)
        cls.tenure_b = RosterTenureFactory(player_data=cls.player_b)
        cls.pref_a = SocialConsentPreferenceFactory(tenure=cls.tenure_a)
        cls.pref_b = SocialConsentPreferenceFactory(tenure=cls.tenure_b)
        cls.category = SocialConsentCategoryFactory(key="hostile-test")
        cls.rule_a = SocialConsentCategoryRuleFactory(
            preference=cls.pref_a,
            category=cls.category,
            mode=ConsentMode.ALLOWLIST,
        )
        cls.rule_b = SocialConsentCategoryRuleFactory(
            preference=cls.pref_b,
            category=cls.category,
            mode=ConsentMode.EVERYONE,
        )

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(user=self.player_a.account)

    def test_unauthenticated_returns_401_or_403(self):
        """Unauthenticated requests are rejected."""
        self.client.force_authenticate(user=None)
        response = self.client.get("/api/consent/category-rules/")
        assert response.status_code in (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)

    def test_list_returns_only_own_rules(self):
        """Listing scopes results to the requesting player's rules."""
        response = self.client.get("/api/consent/category-rules/")
        assert response.status_code == status.HTTP_200_OK
        ids = [r["id"] for r in response.data["results"]]
        assert self.rule_a.id in ids
        assert self.rule_b.id not in ids

    def test_cross_player_retrieve_returns_404(self):
        """Player A cannot retrieve player B's rule."""
        response = self.client.get(f"/api/consent/category-rules/{self.rule_b.id}/")
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_cross_player_patch_returns_404(self):
        """Player A cannot patch player B's rule."""
        response = self.client.patch(
            f"/api/consent/category-rules/{self.rule_b.id}/",
            {"mode": ConsentMode.ALLOWLIST},
            format="json",
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_create_rule(self):
        """Player can create a new category rule for their own preference."""
        new_category = SocialConsentCategoryFactory(key="romantic-create-test")
        response = self.client.post(
            "/api/consent/category-rules/",
            {
                "preference": self.pref_a.id,
                "category": new_category.id,
                "mode": ConsentMode.ALLOWLIST,
            },
            format="json",
        )
        assert response.status_code == status.HTTP_201_CREATED
        assert SocialConsentCategoryRule.objects.filter(
            preference=self.pref_a, category=new_category
        ).exists()

    def test_patch_own_rule_mode(self):
        """Player can patch their own rule's mode."""
        response = self.client.patch(
            f"/api/consent/category-rules/{self.rule_a.id}/",
            {"mode": ConsentMode.EVERYONE},
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK
        self.rule_a.refresh_from_db()
        assert self.rule_a.mode == ConsentMode.EVERYONE

    def test_filter_by_preference(self):
        """Can filter rules by preference id."""
        response = self.client.get(f"/api/consent/category-rules/?preference={self.pref_a.id}")
        assert response.status_code == status.HTTP_200_OK
        ids = [r["id"] for r in response.data["results"]]
        assert self.rule_a.id in ids

    def test_create_rule_for_other_player_preference_rejected(self):
        """Serializer validation rejects referencing another player's preference."""
        new_category = SocialConsentCategoryFactory(key="xplayer-test")
        response = self.client.post(
            "/api/consent/category-rules/",
            {
                "preference": self.pref_b.id,
                "category": new_category.id,
                "mode": ConsentMode.EVERYONE,
            },
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST


class SocialConsentWhitelistViewSetTests(TestCase):
    """Tests for /api/consent/whitelist/."""

    @classmethod
    def setUpTestData(cls):
        cls.player_a = PlayerDataFactory()
        cls.player_b = PlayerDataFactory()
        cls.tenure_a = RosterTenureFactory(player_data=cls.player_a)
        cls.tenure_b = RosterTenureFactory(player_data=cls.player_b)
        cls.tenure_other = RosterTenureFactory(player_data=PlayerDataFactory())
        cls.category = SocialConsentCategoryFactory(key="whitelist-test-cat")
        cls.entry_a = SocialConsentWhitelistFactory(
            owner_tenure=cls.tenure_a,
            allowed_tenure=cls.tenure_other,
            category=cls.category,
        )
        cls.entry_b = SocialConsentWhitelistFactory(
            owner_tenure=cls.tenure_b,
            allowed_tenure=cls.tenure_other,
            category=cls.category,
        )

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(user=self.player_a.account)

    def test_unauthenticated_returns_401_or_403(self):
        """Unauthenticated requests are rejected."""
        self.client.force_authenticate(user=None)
        response = self.client.get("/api/consent/whitelist/")
        assert response.status_code in (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)

    def test_list_returns_only_own_entries(self):
        """Listing scopes results to the requesting player's owner tenures."""
        response = self.client.get("/api/consent/whitelist/")
        assert response.status_code == status.HTTP_200_OK
        ids = [e["id"] for e in response.data["results"]]
        assert self.entry_a.id in ids
        assert self.entry_b.id not in ids

    def test_cross_player_retrieve_returns_404(self):
        """Player A cannot retrieve player B's whitelist entry."""
        response = self.client.get(f"/api/consent/whitelist/{self.entry_b.id}/")
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_cross_player_delete_returns_404(self):
        """Player A cannot delete player B's whitelist entry."""
        response = self.client.delete(f"/api/consent/whitelist/{self.entry_b.id}/")
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_add_whitelist_entry(self):
        """Player can add a whitelist entry for their own tenure."""
        new_category = SocialConsentCategoryFactory(key="wl-add-test")
        another_tenure = RosterTenureFactory(player_data=PlayerDataFactory())
        response = self.client.post(
            "/api/consent/whitelist/",
            {
                "owner_tenure": self.tenure_a.id,
                "allowed_tenure": another_tenure.id,
                "category": new_category.id,
            },
            format="json",
        )
        assert response.status_code == status.HTTP_201_CREATED
        assert SocialConsentWhitelist.objects.filter(
            owner_tenure=self.tenure_a, allowed_tenure=another_tenure, category=new_category
        ).exists()

    def test_delete_own_whitelist_entry(self):
        """Player can delete their own whitelist entry."""
        entry_to_delete = SocialConsentWhitelistFactory(
            owner_tenure=self.tenure_a,
            allowed_tenure=self.tenure_other,
            category=SocialConsentCategoryFactory(key="wl-delete-test"),
        )
        response = self.client.delete(f"/api/consent/whitelist/{entry_to_delete.id}/")
        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert not SocialConsentWhitelist.objects.filter(id=entry_to_delete.id).exists()

    def test_filter_by_owner_tenure(self):
        """Can filter whitelist entries by owner_tenure id."""
        response = self.client.get(f"/api/consent/whitelist/?owner_tenure={self.tenure_a.id}")
        assert response.status_code == status.HTTP_200_OK
        ids = [e["id"] for e in response.data["results"]]
        assert self.entry_a.id in ids

    def test_add_entry_for_other_player_owner_tenure_rejected(self):
        """Serializer validation rejects adding entry for another player's owner_tenure."""
        response = self.client.post(
            "/api/consent/whitelist/",
            {
                "owner_tenure": self.tenure_b.id,
                "allowed_tenure": self.tenure_other.id,
                "category": self.category.id,
            },
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
