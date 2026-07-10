"""Tests for GroupStoryRequest model, lifecycle services, and the read-only ViewSet (#2119).

Player->GM recruitment loop: a covenant officer posts an open, broadcast ask
for a GM; any registered GM may claim it, creating the GROUP-scope Story and
seating the covenant's active members at the GM's table in one step.
"""

from __future__ import annotations

from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from evennia_extensions.factories import AccountFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.covenants.factories import CharacterCovenantRoleFactory, CovenantFactory
from world.gm.constants import GMTableStatus
from world.gm.factories import GMProfileFactory, GMTableFactory
from world.gm.models import GMTableMembership
from world.scenes.constants import PersonaType
from world.scenes.factories import PersonaFactory
from world.scenes.services import set_active_persona
from world.stories.constants import GroupStoryRequestStatus, StoryScope
from world.stories.exceptions import GroupStoryRequestError
from world.stories.factories import GroupStoryRequestFactory
from world.stories.models import GroupStoryProgress, GroupStoryRequest
from world.stories.services.tables import (
    claim_group_story_request,
    request_gm_for_covenant,
    withdraw_group_story_request,
)

# ---------------------------------------------------------------------------
# Model tests
# ---------------------------------------------------------------------------


class GroupStoryRequestModelTest(TestCase):
    def test_round_trip_via_factory(self):
        request = GroupStoryRequestFactory()
        assert request.pk is not None
        assert request.status == GroupStoryRequestStatus.PENDING
        assert request.claimed_by is None
        assert request.created_story is None
        assert request.responded_at is None
        assert request.message == ""

    def test_str_representation(self):
        request = GroupStoryRequestFactory()
        s = str(request)
        assert "GroupStoryRequest" in s
        assert "pending" in s

    def test_ordering_is_newest_first(self):
        older = GroupStoryRequestFactory()
        newer = GroupStoryRequestFactory()
        pks = list(GroupStoryRequest.objects.values_list("pk", flat=True))
        assert pks.index(newer.pk) < pks.index(older.pk)


class GroupStoryRequestUniquePendingConstraintTest(TestCase):
    """Partial unique constraint: one PENDING request per covenant."""

    def test_two_pending_requests_same_covenant_raises(self):
        covenant = CovenantFactory()
        account = AccountFactory()
        GroupStoryRequest.objects.create(covenant=covenant, requested_by_account=account)
        with transaction.atomic(), self.assertRaises(IntegrityError):
            GroupStoryRequest.objects.create(covenant=covenant, requested_by_account=account)

    def test_pending_and_withdrawn_same_covenant_is_ok(self):
        covenant = CovenantFactory()
        account = AccountFactory()
        GroupStoryRequest.objects.create(
            covenant=covenant,
            requested_by_account=account,
            status=GroupStoryRequestStatus.WITHDRAWN,
        )
        second = GroupStoryRequest.objects.create(
            covenant=covenant,
            requested_by_account=account,
            status=GroupStoryRequestStatus.PENDING,
        )
        assert second.pk is not None

    def test_two_pending_requests_different_covenants_is_ok(self):
        cov1 = CovenantFactory()
        cov2 = CovenantFactory()
        account = AccountFactory()
        r1 = GroupStoryRequest.objects.create(covenant=cov1, requested_by_account=account)
        r2 = GroupStoryRequest.objects.create(covenant=cov2, requested_by_account=account)
        assert r1.pk != r2.pk


# ---------------------------------------------------------------------------
# Service tests
# ---------------------------------------------------------------------------


class RequestGMForCovenantServiceTest(TestCase):
    def test_happy_path_creates_pending_request(self):
        covenant = CovenantFactory()
        account = AccountFactory()
        request = request_gm_for_covenant(
            covenant=covenant, requested_by_account=account, message="We seek a GM!"
        )
        assert request.pk is not None
        assert request.status == GroupStoryRequestStatus.PENDING
        assert request.covenant_id == covenant.pk
        assert request.requested_by_account_id == account.pk
        assert request.message == "We seek a GM!"

    def test_rejects_dissolved_covenant(self):
        from django.utils import timezone

        covenant = CovenantFactory(dissolved_at=timezone.now())
        account = AccountFactory()
        with self.assertRaises(GroupStoryRequestError):
            request_gm_for_covenant(covenant=covenant, requested_by_account=account)


class ClaimGroupStoryRequestServiceTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.gm = GMProfileFactory()
        cls.gm_table = GMTableFactory(gm=cls.gm, status=GMTableStatus.ACTIVE)
        cls.covenant = CovenantFactory()
        cls.requester_account = AccountFactory()

    def _make_pending_request(self, covenant=None):
        return GroupStoryRequestFactory(
            covenant=covenant or self.covenant,
            requested_by_account=self.requester_account,
        )

    def test_happy_path_creates_group_story_and_progress(self):
        request = self._make_pending_request()
        claimed = claim_group_story_request(
            request=request, gm_profile=self.gm, title="A Test Tale"
        )
        assert claimed.status == GroupStoryRequestStatus.ACCEPTED
        assert claimed.claimed_by_id == self.gm.pk
        assert claimed.responded_at is not None
        story = claimed.created_story
        assert story is not None
        assert story.scope == StoryScope.GROUP
        assert story.covenant_id == self.covenant.pk
        assert story.primary_table_id == self.gm_table.pk
        assert story.title == "A Test Tale"
        assert GroupStoryProgress.objects.filter(story=story, gm_table=self.gm_table).exists()

    def test_default_title_uses_covenant_name(self):
        request = self._make_pending_request()
        claimed = claim_group_story_request(request=request, gm_profile=self.gm)
        assert self.covenant.name in claimed.created_story.title

    def test_seats_all_active_covenant_members(self):
        """Every active CharacterCovenantRole's persona joins the GM's table (Decision 4)."""
        sheet1 = CharacterSheetFactory()
        sheet2 = CharacterSheetFactory()
        CharacterCovenantRoleFactory(character_sheet=sheet1, covenant=self.covenant)
        CharacterCovenantRoleFactory(character_sheet=sheet2, covenant=self.covenant)

        request = self._make_pending_request()
        claim_group_story_request(request=request, gm_profile=self.gm)

        active_memberships = GMTableMembership.objects.filter(
            table=self.gm_table, left_at__isnull=True
        )
        seated_persona_ids = set(active_memberships.values_list("persona_id", flat=True))
        assert sheet1.primary_persona.pk in seated_persona_ids
        assert sheet2.primary_persona.pk in seated_persona_ids

    def test_departed_member_is_not_seated(self):
        sheet = CharacterSheetFactory()
        membership = CharacterCovenantRoleFactory(character_sheet=sheet, covenant=self.covenant)
        from django.utils import timezone as dj_timezone

        membership.left_at = dj_timezone.now()
        membership.save(update_fields=["left_at"])

        request = self._make_pending_request()
        claim_group_story_request(request=request, gm_profile=self.gm)

        assert not GMTableMembership.objects.filter(
            table=self.gm_table, persona=sheet.primary_persona
        ).exists()

    def test_temporary_active_persona_is_skipped_not_fatal(self):
        """A member whose active_persona is TEMPORARY is skipped, not a fatal error."""
        sheet = CharacterSheetFactory()
        temp_persona = PersonaFactory(character_sheet=sheet, persona_type=PersonaType.TEMPORARY)
        set_active_persona(sheet, temp_persona)
        CharacterCovenantRoleFactory(character_sheet=sheet, covenant=self.covenant)

        other_sheet = CharacterSheetFactory()
        CharacterCovenantRoleFactory(character_sheet=other_sheet, covenant=self.covenant)

        request = self._make_pending_request()
        # Must not raise, despite one member's active persona being TEMPORARY.
        claimed = claim_group_story_request(request=request, gm_profile=self.gm)
        assert claimed.status == GroupStoryRequestStatus.ACCEPTED

        assert not GMTableMembership.objects.filter(
            table=self.gm_table, persona=temp_persona
        ).exists()
        assert GMTableMembership.objects.filter(
            table=self.gm_table, persona=other_sheet.primary_persona
        ).exists()

    def test_rejects_non_pending_request(self):
        request = self._make_pending_request()
        request.status = GroupStoryRequestStatus.WITHDRAWN
        request.save(update_fields=["status", "updated_at"])
        with self.assertRaises(GroupStoryRequestError):
            claim_group_story_request(request=request, gm_profile=self.gm)

    def test_rejects_when_gm_has_no_active_table(self):
        gm_no_table = GMProfileFactory()
        request = self._make_pending_request()
        with self.assertRaises(GroupStoryRequestError):
            claim_group_story_request(request=request, gm_profile=gm_no_table)

    def test_explicit_table_overrides_default(self):
        other_table = GMTableFactory(gm=self.gm, status=GMTableStatus.ACTIVE)
        request = self._make_pending_request()
        claimed = claim_group_story_request(request=request, gm_profile=self.gm, table=other_table)
        assert claimed.created_story.primary_table_id == other_table.pk


class WithdrawGroupStoryRequestServiceTest(TestCase):
    def test_happy_path_withdraws_request(self):
        request = GroupStoryRequestFactory()
        withdrawn = withdraw_group_story_request(request=request)
        assert withdrawn.status == GroupStoryRequestStatus.WITHDRAWN
        assert withdrawn.responded_at is not None

    def test_rejects_non_pending_request(self):
        request = GroupStoryRequestFactory(status=GroupStoryRequestStatus.ACCEPTED)
        with self.assertRaises(GroupStoryRequestError):
            withdraw_group_story_request(request=request)


# ---------------------------------------------------------------------------
# ViewSet tests — leak-scoping (see spec's "Verified leak analysis" table)
# ---------------------------------------------------------------------------


class GroupStoryRequestViewSetListTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.covenant = CovenantFactory()
        cls.member_account = AccountFactory()
        cls.member_sheet = CharacterSheetFactory()
        CharacterCovenantRoleFactory(character_sheet=cls.member_sheet, covenant=cls.covenant)
        from world.roster.factories import (
            PlayerDataFactory,
            RosterEntryFactory,
            RosterTenureFactory,
        )

        entry = RosterEntryFactory(character_sheet=cls.member_sheet)
        player_data = PlayerDataFactory(account=cls.member_account)
        RosterTenureFactory(roster_entry=entry, player_data=player_data, end_date=None)

        cls.requester_account = AccountFactory()
        cls.pending_request = GroupStoryRequestFactory(
            covenant=cls.covenant, requested_by_account=cls.requester_account
        )

        cls.gm_profile = GMProfileFactory()
        cls.gm_account = cls.gm_profile.account

        cls.claiming_gm_profile = GMProfileFactory()
        cls.claimed_request = GroupStoryRequestFactory(
            status=GroupStoryRequestStatus.ACCEPTED,
            claimed_by=cls.claiming_gm_profile,
        )

        cls.staff_account = AccountFactory(is_staff=True)
        cls.stranger_account = AccountFactory()

    def _url(self):
        return reverse("groupstoryrequest-list")

    def _ids(self, resp):
        return [r["id"] for r in resp.data["results"]]

    def test_staff_sees_all_requests(self):
        self.client.force_authenticate(user=self.staff_account)
        resp = self.client.get(self._url())
        assert resp.status_code == status.HTTP_200_OK
        ids = self._ids(resp)
        assert self.pending_request.pk in ids
        assert self.claimed_request.pk in ids

    def test_any_gm_sees_pending_open_queue(self):
        """Any registered GM sees the broadcast PENDING queue (Decision 8's whole point)."""
        self.client.force_authenticate(user=self.gm_account)
        resp = self.client.get(self._url())
        assert resp.status_code == status.HTTP_200_OK
        assert self.pending_request.pk in self._ids(resp)

    def test_gm_sees_own_claimed_request(self):
        self.client.force_authenticate(user=self.claiming_gm_profile.account)
        resp = self.client.get(self._url())
        assert resp.status_code == status.HTTP_200_OK
        assert self.claimed_request.pk in self._ids(resp)

    def test_gm_does_not_see_other_gms_claimed_request(self):
        self.client.force_authenticate(user=self.gm_account)
        resp = self.client.get(self._url())
        assert resp.status_code == status.HTTP_200_OK
        assert self.claimed_request.pk not in self._ids(resp)

    def test_covenant_member_sees_own_covenant_request(self):
        self.client.force_authenticate(user=self.member_account)
        resp = self.client.get(self._url())
        assert resp.status_code == status.HTTP_200_OK
        assert self.pending_request.pk in self._ids(resp)

    def test_stranger_does_not_see_non_pending_other_covenant_request(self):
        """A non-member, non-GM, non-staff stranger cannot see an unrelated claimed request."""
        self.client.force_authenticate(user=self.stranger_account)
        resp = self.client.get(self._url())
        assert resp.status_code == status.HTTP_200_OK
        assert self.claimed_request.pk not in self._ids(resp)

    def test_stranger_sees_the_open_broadcast_queue(self):
        """PENDING requests are visible to any GM, but a non-GM stranger sees only their
        own covenants' requests — not the broadcast queue (that's GM-only visibility)."""
        self.client.force_authenticate(user=self.stranger_account)
        resp = self.client.get(self._url())
        assert resp.status_code == status.HTTP_200_OK
        assert self.pending_request.pk not in self._ids(resp)
