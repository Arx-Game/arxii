"""Gemit reach (#1450) — scoped broadcast, audience resolution, and history scoping.

The push itself goes over ``SESSION_HANDLER`` (no connected sessions in tests, so it's a no-op);
these tests cover the persisted record, the membership-based audience resolution, and the
non-leaking history list.
"""

from types import SimpleNamespace

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APITestCase

from evennia_extensions.factories import AccountFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.narrative.constants import GemitReach
from world.narrative.services import (
    _eligible_persona_ids,
    _session_in_audience,
    broadcast_gemit,
)
from world.roster.factories import PlayerDataFactory, RosterEntryFactory, RosterTenureFactory
from world.societies.factories import (
    OrganizationFactory,
    OrganizationMembershipFactory,
    SocietyFactory,
)

GEMITS_URL = "/api/narrative/gemits/"


class GemitReachServiceTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.society = SocietyFactory(name="The Compact")
        cls.org = OrganizationFactory(society=cls.society)
        cls.member_sheet = CharacterSheetFactory()
        cls.member_persona = cls.member_sheet.primary_persona
        OrganizationMembershipFactory(organization=cls.org, persona=cls.member_persona)

    def test_game_wide_gemit_defaults_reach_and_has_no_targets(self) -> None:
        gemit = broadcast_gemit(body="To all the realm.", sender_account=None)
        assert gemit.reach == GemitReach.GAME_WIDE
        assert gemit.reach_societies.count() == 0
        assert gemit.reach_organizations.count() == 0

    def test_specified_gemit_records_reach_and_society_targets(self) -> None:
        gemit = broadcast_gemit(
            body="Compact business.",
            sender_account=None,
            reach=GemitReach.SPECIFIED,
            societies=[self.society],
        )
        assert gemit.reach == GemitReach.SPECIFIED
        assert list(gemit.reach_societies.all()) == [self.society]

    def test_specified_gemit_records_org_targets(self) -> None:
        gemit = broadcast_gemit(
            body="Org business.",
            sender_account=None,
            reach=GemitReach.SPECIFIED,
            organizations=[self.org],
        )
        assert gemit.reach == GemitReach.SPECIFIED
        assert list(gemit.reach_organizations.all()) == [self.org]

    def test_specified_gemit_can_mix_society_and_org_targets(self) -> None:
        other_org = OrganizationFactory()
        gemit = broadcast_gemit(
            body="A House and a Society together.",
            sender_account=None,
            reach=GemitReach.SPECIFIED,
            societies=[self.society],
            organizations=[other_org],
        )
        assert gemit.reach == GemitReach.SPECIFIED
        assert list(gemit.reach_societies.all()) == [self.society]
        assert list(gemit.reach_organizations.all()) == [other_org]

    def test_eligible_persona_ids_for_society_are_its_members(self) -> None:
        eligible = _eligible_persona_ids(GemitReach.SPECIFIED, [self.society], [])
        assert eligible == {self.member_persona.id}

    def test_eligible_persona_ids_for_organization_are_its_members(self) -> None:
        eligible = _eligible_persona_ids(GemitReach.SPECIFIED, [], [self.org])
        assert eligible == {self.member_persona.id}

    def test_eligible_persona_ids_unions_societies_and_orgs(self) -> None:
        other_org = OrganizationFactory()
        other_sheet = CharacterSheetFactory()
        OrganizationMembershipFactory(organization=other_org, persona=other_sheet.primary_persona)
        eligible = _eligible_persona_ids(GemitReach.SPECIFIED, [self.society], [other_org])
        assert eligible == {self.member_persona.id, other_sheet.primary_persona.id}

    def test_game_wide_has_no_eligibility_set(self) -> None:
        assert _eligible_persona_ids(GemitReach.GAME_WIDE, [], []) == set()

    def test_session_in_audience_matches_active_persona_member(self) -> None:
        session = SimpleNamespace(puppet=self.member_sheet.character)
        assert _session_in_audience(session, {self.member_persona.id}) is True

    def test_session_with_no_puppet_is_not_in_audience(self) -> None:
        assert _session_in_audience(SimpleNamespace(puppet=None), {self.member_persona.id}) is False

    def test_non_member_session_is_not_in_audience(self) -> None:
        outsider = CharacterSheetFactory()
        session = SimpleNamespace(puppet=outsider.character)
        assert _session_in_audience(session, {self.member_persona.id}) is False


class GemitHistoryScopingTests(APITestCase):
    """A scoped gemit appears in the history only for its audience; game-wide for everyone."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.society = SocietyFactory(name="The Compact")
        cls.org = OrganizationFactory(society=cls.society)

        cls.member_account = AccountFactory()
        member_entry = RosterEntryFactory()
        RosterTenureFactory(
            roster_entry=member_entry, player_data=PlayerDataFactory(account=cls.member_account)
        )
        OrganizationMembershipFactory(
            organization=cls.org, persona=member_entry.character_sheet.primary_persona
        )

        cls.outsider_account = AccountFactory()
        outsider_entry = RosterEntryFactory()
        RosterTenureFactory(
            roster_entry=outsider_entry,
            player_data=PlayerDataFactory(account=cls.outsider_account),
        )
        cls.staff = AccountFactory(is_staff=True)

        cls.game_wide = broadcast_gemit(body="Everyone hears this.", sender_account=None)
        cls.society_gemit = broadcast_gemit(
            body="Only the Compact.",
            sender_account=None,
            reach=GemitReach.SPECIFIED,
            societies=[cls.society],
        )

    def _bodies_for(self, account: object) -> set[str]:
        self.client.force_authenticate(user=account)
        response = self.client.get(GEMITS_URL)
        assert response.status_code == status.HTTP_200_OK
        return {row["body"] for row in response.data["results"]}

    def test_member_sees_the_society_gemit(self) -> None:
        assert self._bodies_for(self.member_account) == {
            "Everyone hears this.",
            "Only the Compact.",
        }

    def test_outsider_sees_only_the_game_wide_gemit(self) -> None:
        assert self._bodies_for(self.outsider_account) == {"Everyone hears this."}

    def test_staff_sees_every_gemit(self) -> None:
        assert self._bodies_for(self.staff) == {"Everyone hears this.", "Only the Compact."}
