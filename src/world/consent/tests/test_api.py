"""API tests for the /api/consent/ endpoints."""

from types import SimpleNamespace

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from world.consent.constants import ConsentMode
from world.consent.factories import (
    SocialConsentBlacklistFactory,
    SocialConsentCategoryFactory,
    SocialConsentCategoryRuleFactory,
    SocialConsentPreferenceFactory,
    SocialConsentWhitelistFactory,
)
from world.consent.models import (
    SocialConsentBlacklist,
    SocialConsentCategoryRule,
    SocialConsentPreference,
    SocialConsentWhitelist,
)
from world.roster.factories import PlayerDataFactory, RosterTenureFactory


def _force_api_user(client: APIClient, player_data, character) -> None:
    """Authenticate the client with a user that has a player_data and a puppet character.

    The viewset dispatches consent actions through the shared player-action seam, which
    needs an ObjectDB character whose account matches the owning player. Tests wire the
    character.account to the player account and expose the character as request.user.puppet.
    """
    character.account = player_data.account
    user = SimpleNamespace(
        is_authenticated=True,
        is_staff=False,
        player_data=player_data,
        puppet=character,
    )
    client.force_authenticate(user=user)


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
        _force_api_user(self.client, self.player, self._character_for(self.player))

    def _character_for(self, player_data):
        tenure = RosterTenureFactory(player_data=player_data)
        character = tenure.roster_entry.character_sheet.character
        character.account = player_data.account
        return character

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

    def test_category_serializes_parent_and_default_mode(self):
        """Category rows expose parent + default_mode so the client can render the tree (#2170)."""
        from world.consent.constants import ConsentMode

        root = SocialConsentCategoryFactory(
            key="antagonism", name="All Antagonism", default_mode=ConsentMode.FRIENDS_WHITELIST
        )
        self.category_b.parent = root
        self.category_b.save(update_fields=["parent"])
        response = self.client.get(f"/api/consent/categories/{self.category_b.id}/")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["parent"] == root.id
        assert "default_mode" in response.data
        root_response = self.client.get(f"/api/consent/categories/{root.id}/")
        assert root_response.data["parent"] is None
        assert root_response.data["default_mode"] == ConsentMode.FRIENDS_WHITELIST

    def test_modes_endpoint_returns_guidance(self):
        """/categories/modes/ returns a guidance row per ConsentMode (#2170)."""
        from world.consent.constants import ConsentMode

        response = self.client.get("/api/consent/categories/modes/")
        assert response.status_code == status.HTTP_200_OK
        values = {row["value"] for row in response.data}
        assert values == set(ConsentMode.values)
        for row in response.data:
            assert row["guidance"]  # non-empty explanation
            assert row["label"]

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
        cls.character_a = cls.tenure_a.roster_entry.character_sheet.character
        cls.character_a.account = cls.player_a.account

    def setUp(self):
        self.client = APIClient()
        _force_api_user(self.client, self.player_a, self.character_a)

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

    def test_patch_own_preference_response_shape(self):
        """PATCH response preserves the original serializer contract."""
        response = self.client.patch(
            f"/api/consent/preferences/{self.pref_a.id}/",
            {"allow_social_actions": False},
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK
        assert set(response.data.keys()) == {"id", "tenure", "allow_social_actions"}
        assert response.data["id"] == self.pref_a.id
        assert response.data["tenure"] == self.tenure_a.id
        assert response.data["allow_social_actions"] is False

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
        # 404 comes from the RosterTenure ownership guard (exists() check) — the view
        # never reaches the preference lookup.  The synthesized default would otherwise
        # leak tenure existence.
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_post_creates_preference_for_own_tenure(self):
        """Player can POST to create a preference for a tenure they own."""
        tenure_new = RosterTenureFactory(player_data=self.player_a)
        tenure_new.roster_entry.character_sheet.character.account = self.player_a.account
        response = self.client.post(
            "/api/consent/preferences/",
            {"tenure": tenure_new.id, "allow_social_actions": False},
            format="json",
        )
        assert response.status_code == status.HTTP_201_CREATED
        assert SocialConsentPreference.objects.filter(tenure=tenure_new).exists()

    def test_post_preference_response_shape(self):
        """POST response preserves the original serializer contract."""
        tenure_new = RosterTenureFactory(player_data=self.player_a)
        tenure_new.roster_entry.character_sheet.character.account = self.player_a.account
        response = self.client.post(
            "/api/consent/preferences/",
            {"tenure": tenure_new.id, "allow_social_actions": False},
            format="json",
        )
        assert response.status_code == status.HTTP_201_CREATED
        assert set(response.data.keys()) == {"id", "tenure", "allow_social_actions"}
        assert response.data["tenure"] == tenure_new.id
        assert response.data["allow_social_actions"] is False
        preference = SocialConsentPreference.objects.get(tenure=tenure_new)
        assert response.data["id"] == preference.id

    def test_post_with_other_players_tenure_rejected(self):
        """POST with another player's tenure id is rejected and no row is created."""
        response = self.client.post(
            "/api/consent/preferences/",
            {"tenure": self.tenure_b.id, "allow_social_actions": True},
            format="json",
        )
        assert response.status_code in (status.HTTP_400_BAD_REQUEST, status.HTTP_403_FORBIDDEN)
        # No preference row must have been created for the other player's tenure.
        assert not SocialConsentPreference.objects.filter(
            tenure=self.tenure_b,
            tenure__player_data=self.player_a,
        ).exists()

    def test_post_duplicate_tenure_returns_400(self):
        """POST a second preference for a tenure that already has one returns 400."""
        # pref_a is already created for tenure_a in setUpTestData.
        response = self.client.post(
            "/api/consent/preferences/",
            {"tenure": self.tenure_a.id, "allow_social_actions": False},
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST


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
        cls.character_a = cls.tenure_a.roster_entry.character_sheet.character
        cls.character_a.account = cls.player_a.account

    def setUp(self):
        self.client = APIClient()
        _force_api_user(self.client, self.player_a, self.character_a)

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

    def test_create_rule_response_shape(self):
        """POST response preserves the original serializer contract."""
        new_category = SocialConsentCategoryFactory(key="romantic-shape-test")
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
        assert set(response.data.keys()) == {"id", "preference", "category", "mode"}
        assert response.data["preference"] == self.pref_a.id
        assert response.data["category"] == new_category.id
        assert response.data["mode"] == ConsentMode.ALLOWLIST
        rule = SocialConsentCategoryRule.objects.get(preference=self.pref_a, category=new_category)
        assert response.data["id"] == rule.id

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

    def test_patch_own_rule_mode_response_shape(self):
        """PATCH response preserves the original serializer contract."""
        response = self.client.patch(
            f"/api/consent/category-rules/{self.rule_a.id}/",
            {"mode": ConsentMode.EVERYONE},
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK
        assert set(response.data.keys()) == {"id", "preference", "category", "mode"}
        assert response.data["id"] == self.rule_a.id
        assert response.data["preference"] == self.pref_a.id
        assert response.data["category"] == self.category.id
        assert response.data["mode"] == ConsentMode.EVERYONE

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
        cls.character_a = cls.tenure_a.roster_entry.character_sheet.character
        cls.character_a.account = cls.player_a.account

    def setUp(self):
        self.client = APIClient()
        _force_api_user(self.client, self.player_a, self.character_a)

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

    def test_add_whitelist_entry_response_shape(self):
        """POST response preserves the original serializer contract."""
        new_category = SocialConsentCategoryFactory(key="wl-add-shape-test")
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
        assert set(response.data.keys()) == {
            "id",
            "owner_tenure",
            "allowed_tenure",
            "allowed_tenure_name",
            "category",
            "added_at",
        }
        assert response.data["owner_tenure"] == self.tenure_a.id
        assert response.data["allowed_tenure"] == another_tenure.id
        assert response.data["category"] == new_category.id
        entry = SocialConsentWhitelist.objects.get(
            owner_tenure=self.tenure_a, allowed_tenure=another_tenure, category=new_category
        )
        assert response.data["id"] == entry.id
        assert response.data["allowed_tenure_name"] == another_tenure.display_name

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

    def test_delete_own_whitelist_entry_returns_204(self):
        """DELETE response preserves the original contract (no body, 204)."""
        entry_to_delete = SocialConsentWhitelistFactory(
            owner_tenure=self.tenure_a,
            allowed_tenure=self.tenure_other,
            category=SocialConsentCategoryFactory(key="wl-delete-shape-test"),
        )
        response = self.client.delete(f"/api/consent/whitelist/{entry_to_delete.id}/")
        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert response.data is None or response.data == ""

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


class SocialConsentBlacklistViewSetTests(TestCase):
    """Tests for /api/consent/blacklist/ (#1698)."""

    @classmethod
    def setUpTestData(cls):
        cls.player_a = PlayerDataFactory()
        cls.player_b = PlayerDataFactory()
        cls.tenure_a = RosterTenureFactory(player_data=cls.player_a)
        cls.tenure_b = RosterTenureFactory(player_data=cls.player_b)
        cls.tenure_other = RosterTenureFactory(player_data=PlayerDataFactory())
        cls.category = SocialConsentCategoryFactory(key="blacklist-test-cat")
        cls.entry_a = SocialConsentBlacklistFactory(
            owner_tenure=cls.tenure_a,
            blocked_tenure=cls.tenure_other,
            category=cls.category,
        )
        cls.entry_b = SocialConsentBlacklistFactory(
            owner_tenure=cls.tenure_b,
            blocked_tenure=cls.tenure_other,
            category=cls.category,
        )
        cls.character_a = cls.tenure_a.roster_entry.character_sheet.character
        cls.character_a.account = cls.player_a.account

    def setUp(self):
        self.client = APIClient()
        _force_api_user(self.client, self.player_a, self.character_a)

    def test_list_returns_only_own_entries(self):
        response = self.client.get("/api/consent/blacklist/")
        assert response.status_code == status.HTTP_200_OK
        ids = [e["id"] for e in response.data["results"]]
        assert self.entry_a.id in ids
        assert self.entry_b.id not in ids

    def test_cross_player_delete_returns_404(self):
        response = self.client.delete(f"/api/consent/blacklist/{self.entry_b.id}/")
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_add_blacklist_entry(self):
        new_category = SocialConsentCategoryFactory(key="bl-add-test")
        another_tenure = RosterTenureFactory(player_data=PlayerDataFactory())
        response = self.client.post(
            "/api/consent/blacklist/",
            {
                "owner_tenure": self.tenure_a.id,
                "blocked_tenure": another_tenure.id,
                "category": new_category.id,
            },
            format="json",
        )
        assert response.status_code == status.HTTP_201_CREATED
        assert set(response.data.keys()) == {
            "id",
            "owner_tenure",
            "blocked_tenure",
            "blocked_tenure_name",
            "category",
            "added_at",
        }
        assert SocialConsentBlacklist.objects.filter(
            owner_tenure=self.tenure_a, blocked_tenure=another_tenure, category=new_category
        ).exists()

    def test_delete_own_blacklist_entry(self):
        entry_to_delete = SocialConsentBlacklistFactory(
            owner_tenure=self.tenure_a,
            blocked_tenure=self.tenure_other,
            category=SocialConsentCategoryFactory(key="bl-delete-test"),
        )
        response = self.client.delete(f"/api/consent/blacklist/{entry_to_delete.id}/")
        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert not SocialConsentBlacklist.objects.filter(id=entry_to_delete.id).exists()

    def test_add_entry_for_other_player_owner_tenure_rejected(self):
        response = self.client.post(
            "/api/consent/blacklist/",
            {
                "owner_tenure": self.tenure_b.id,
                "blocked_tenure": self.tenure_other.id,
                "category": self.category.id,
            },
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
