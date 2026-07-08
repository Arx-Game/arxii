"""Tests for the 'Character Has You Blocked' membership-list placeholder (#2086).

When a blocked player views a covenant membership list that includes the blocker,
the blocker's row shows a generic "a member has blocked you" placeholder — never
the member's name, rank, or role. The blocker viewing the blocked player sees
the normal display. Staff always see the normal display.
"""

from django.test import TestCase
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory
from evennia_extensions.models import PlayerData
from world.character_sheets.factories import CharacterSheetFactory
from world.covenants.factories import (
    CharacterCovenantRoleFactory,
    CovenantFactory,
    CovenantRoleFactory,
)
from world.roster.factories import (
    PlayerDataFactory,
    RosterEntryFactory,
    RosterTenureFactory,
)
from world.scenes.models import Block


def _make_played_sheet(account, name):
    """Create a sheet + roster entry + current tenure for an account."""
    sheet = CharacterSheetFactory()
    entry = RosterEntryFactory(character_sheet=sheet)
    player_data = PlayerDataFactory(account=account)
    RosterTenureFactory(roster_entry=entry, player_data=player_data, end_date=None)
    return sheet


class MembershipListBlockPlaceholderTests(TestCase):
    """The covenant member roster shows a placeholder for a member who blocked the viewer."""

    @classmethod
    def setUpTestData(cls) -> None:
        # The blocker side.
        cls.blocker_acct = AccountFactory(username="blocker")
        cls.blocker_sheet = _make_played_sheet(cls.blocker_acct, "Blocker")

        # The blocked side.
        cls.blocked_acct = AccountFactory(username="blocked")
        cls.blocked_sheet = _make_played_sheet(cls.blocked_acct, "Blocked")

        # The covenant both are members of.
        cls.cov = CovenantFactory()
        cls.role = CovenantRoleFactory()
        cls.blocker_membership = CharacterCovenantRoleFactory(
            character_sheet=cls.blocker_sheet,
            covenant=cls.cov,
            covenant_role=cls.role,
        )
        cls.blocked_membership = CharacterCovenantRoleFactory(
            character_sheet=cls.blocked_sheet,
            covenant=cls.cov,
            covenant_role=cls.role,
        )

        # The blocker blocked the blocked player's persona.
        cls.blocker_pd = PlayerData.objects.get(account=cls.blocker_acct)
        cls.blocked_pd = PlayerData.objects.get(account=cls.blocked_acct)
        Block.objects.create(
            owner=cls.blocker_pd,
            blocked_player=cls.blocked_pd,
            blocker_persona=cls.blocker_sheet.primary_persona,
            blocked_persona=cls.blocked_sheet.primary_persona,
        )

    def test_blocked_viewer_sees_placeholder_for_blocker(self) -> None:
        """The blocked player sees 'a member has blocked you' for the blocker's row."""
        client = APIClient()
        client.force_authenticate(user=self.blocked_acct)
        response = client.get(f"/api/covenants/character-roles/?covenant={self.cov.pk}")
        self.assertEqual(response.status_code, 200)
        rows = response.data["results"]
        # Find the blocker's row by character_sheet PK.
        blocker_row = next(r for r in rows if r["character_sheet"] == self.blocker_sheet.pk)
        self.assertEqual(blocker_row["display_name"], "a member has blocked you")

    def test_blocked_viewer_sees_own_name_normally(self) -> None:
        """The blocked player sees their own row normally (not the placeholder)."""
        client = APIClient()
        client.force_authenticate(user=self.blocked_acct)
        response = client.get(f"/api/covenants/character-roles/?covenant={self.cov.pk}")
        self.assertEqual(response.status_code, 200)
        rows = response.data["results"]
        own_row = next(r for r in rows if r["character_sheet"] == self.blocked_sheet.pk)
        self.assertNotEqual(own_row["display_name"], "a member has blocked you")

    def test_blocker_sees_blocked_player_normally(self) -> None:
        """The blocker sees the blocked player's row normally (no suppression on blocker's side)."""
        client = APIClient()
        client.force_authenticate(user=self.blocker_acct)
        response = client.get(f"/api/covenants/character-roles/?covenant={self.cov.pk}")
        self.assertEqual(response.status_code, 200)
        rows = response.data["results"]
        blocked_row = next(r for r in rows if r["character_sheet"] == self.blocked_sheet.pk)
        self.assertNotEqual(blocked_row["display_name"], "a member has blocked you")

    def test_staff_sees_real_names(self) -> None:
        """Staff always see real names — no placeholder."""
        staff = AccountFactory(username="staff", is_staff=True)
        client = APIClient()
        client.force_authenticate(user=staff)
        response = client.get(f"/api/covenants/character-roles/?covenant={self.cov.pk}")
        self.assertEqual(response.status_code, 200)
        rows = response.data["results"]
        for row in rows:
            self.assertNotEqual(row["display_name"], "a member has blocked you")

    def test_non_blocked_pair_sees_normal_names(self) -> None:
        """A third party with no block sees normal names for both members."""
        stranger = AccountFactory(username="stranger")
        stranger_sheet = _make_played_sheet(stranger, "Stranger")
        CharacterCovenantRoleFactory(
            character_sheet=stranger_sheet,
            covenant=self.cov,
            covenant_role=self.role,
        )
        client = APIClient()
        client.force_authenticate(user=stranger)
        response = client.get(f"/api/covenants/character-roles/?covenant={self.cov.pk}")
        self.assertEqual(response.status_code, 200)
        rows = response.data["results"]
        for row in rows:
            self.assertNotEqual(row["display_name"], "a member has blocked you")
