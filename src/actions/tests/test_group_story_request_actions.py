"""Tests for the player-GM recruitment loop Actions (#2119).

RequestGMForCovenantAction / ClaimGroupStoryRequestAction /
WithdrawGroupStoryRequestAction — the Action.run() seam shared by web
dispatch and telnet (covenant.py / gm_ops.py).
"""

from __future__ import annotations

from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APITestCase

from actions.definitions.gm_stories import (
    ClaimGroupStoryRequestAction,
    RequestGMForCovenantAction,
    WithdrawGroupStoryRequestAction,
)
from evennia_extensions.factories import AccountFactory, CharacterFactory, ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.covenants.factories import (
    CharacterCovenantRoleFactory,
    CovenantFactory,
    CovenantManagerRankFactory,
    CovenantRankFactory,
)
from world.gm.constants import GMTableStatus
from world.gm.factories import GMProfileFactory, GMTableFactory
from world.gm.models import GMTableMembership
from world.roster.factories import RosterTenureFactory
from world.stories.constants import GroupStoryRequestStatus, StoryScope
from world.stories.factories import GroupStoryRequestFactory
from world.stories.models import GroupStoryProgress, GroupStoryRequest, Story


def _make_room(label: str = "Room") -> object:
    return ObjectDBFactory(db_key=label, db_typeclass_path="typeclasses.rooms.Room")


def _make_actor_with_account(db_key: str, room: object, account: object) -> tuple[object, object]:
    """Create a PC in *room* whose ``active_account`` is *account*."""
    char = CharacterFactory(db_key=db_key, location=room)
    sheet = CharacterSheetFactory(character=char)
    entry = RosterTenureFactory(
        roster_entry__character_sheet=sheet,
        player_data__account=account,
        end_date=None,
    ).roster_entry
    return char, entry.character_sheet


class RequestGMForCovenantActionTest(TestCase):
    def setUp(self) -> None:
        self.room = _make_room("RequestGMRoom")
        self.covenant = CovenantFactory()
        self.recruiter_rank = CovenantManagerRankFactory(covenant=self.covenant)
        self.base_rank = CovenantRankFactory(covenant=self.covenant)  # can_request_gm=False

        self.recruiter_account = AccountFactory(username="recruiter")
        self.recruiter_actor, self.recruiter_sheet = _make_actor_with_account(
            "recruiter_actor", self.room, self.recruiter_account
        )
        CharacterCovenantRoleFactory(
            character_sheet=self.recruiter_sheet, covenant=self.covenant, rank=self.recruiter_rank
        )

        self.rankless_account = AccountFactory(username="rankless")
        self.rankless_actor, self.rankless_sheet = _make_actor_with_account(
            "rankless_actor", self.room, self.rankless_account
        )
        CharacterCovenantRoleFactory(
            character_sheet=self.rankless_sheet, covenant=self.covenant, rank=self.base_rank
        )

        self.staff_account = AccountFactory(username="reqgmstaff", is_staff=True)
        self.staff_actor, _ = _make_actor_with_account(
            "reqgmstaff_actor", self.room, self.staff_account
        )

    def test_ranked_member_posts_request(self):
        result = RequestGMForCovenantAction().run(
            actor=self.recruiter_actor,
            covenant_id=self.covenant.pk,
            message="We need a GM to run our story!",
        )
        assert result.success
        request = GroupStoryRequest.objects.get(covenant=self.covenant)
        assert request.status == GroupStoryRequestStatus.PENDING
        assert request.requested_by_account_id == self.recruiter_account.pk
        assert request.message == "We need a GM to run our story!"

    def test_unranked_member_is_refused(self):
        result = RequestGMForCovenantAction().run(
            actor=self.rankless_actor, covenant_id=self.covenant.pk
        )
        assert not result.success
        assert not GroupStoryRequest.objects.filter(covenant=self.covenant).exists()

    def test_staff_bypasses_rank_gate(self):
        result = RequestGMForCovenantAction().run(
            actor=self.staff_actor, covenant_id=self.covenant.pk
        )
        assert result.success

    def test_missing_covenant_returns_failure(self):
        result = RequestGMForCovenantAction().run(actor=self.recruiter_actor, covenant_id=999999)
        assert not result.success


class ClaimGroupStoryRequestActionTest(TestCase):
    def setUp(self) -> None:
        self.room = _make_room("ClaimGMRoom")
        self.covenant = CovenantFactory()
        self.requester_account = AccountFactory()

        self.gm_account = AccountFactory(username="claiminggm")
        self.gm_profile = GMProfileFactory(account=self.gm_account)
        self.gm_table = GMTableFactory(gm=self.gm_profile, status=GMTableStatus.ACTIVE)
        self.gm_actor, _ = _make_actor_with_account("claiming_gm_actor", self.room, self.gm_account)

        self.non_gm_account = AccountFactory(username="nongm")
        self.non_gm_actor, _ = _make_actor_with_account(
            "non_gm_actor", self.room, self.non_gm_account
        )

    def _pending_request(self):
        return GroupStoryRequestFactory(
            covenant=self.covenant, requested_by_account=self.requester_account
        )

    def test_gm_claims_request_creates_group_story_and_seats_members(self):
        sheet1 = CharacterSheetFactory()
        sheet2 = CharacterSheetFactory()
        CharacterCovenantRoleFactory(character_sheet=sheet1, covenant=self.covenant)
        CharacterCovenantRoleFactory(character_sheet=sheet2, covenant=self.covenant)

        request = self._pending_request()
        result = ClaimGroupStoryRequestAction().run(
            actor=self.gm_actor, request_id=request.pk, title="Our Grand Tale"
        )
        assert result.success

        request.refresh_from_db()
        assert request.status == GroupStoryRequestStatus.ACCEPTED
        assert request.claimed_by_id == self.gm_profile.pk

        story = request.created_story
        assert story is not None
        assert story.scope == StoryScope.GROUP
        assert story.title == "Our Grand Tale"
        assert story.primary_table_id == self.gm_table.pk
        assert GroupStoryProgress.objects.filter(story=story, gm_table=self.gm_table).exists()

        seated = set(
            GMTableMembership.objects.filter(table=self.gm_table, left_at__isnull=True).values_list(
                "persona_id", flat=True
            )
        )
        assert sheet1.primary_persona.pk in seated
        assert sheet2.primary_persona.pk in seated

    def test_non_gm_actor_is_refused(self):
        request = self._pending_request()
        result = ClaimGroupStoryRequestAction().run(actor=self.non_gm_actor, request_id=request.pk)
        assert not result.success
        request.refresh_from_db()
        assert request.status == GroupStoryRequestStatus.PENDING

    def test_no_active_table_surfaces_failed_result(self):
        gm_no_table_account = AccountFactory(username="gmnotable")
        gm_no_table_profile = GMProfileFactory(account=gm_no_table_account)
        gm_no_table_actor, _ = _make_actor_with_account(
            "gm_no_table_actor", self.room, gm_no_table_account
        )
        request = self._pending_request()
        result = ClaimGroupStoryRequestAction().run(actor=gm_no_table_actor, request_id=request.pk)
        assert not result.success
        assert Story.objects.filter(covenant=self.covenant).count() == 0
        del gm_no_table_profile  # keep the profile alive for the run() call above

    def test_missing_request_returns_failure(self):
        result = ClaimGroupStoryRequestAction().run(actor=self.gm_actor, request_id=999999)
        assert not result.success


class WithdrawGroupStoryRequestActionTest(TestCase):
    def setUp(self) -> None:
        self.room = _make_room("WithdrawGMRoom")
        self.covenant = CovenantFactory()
        self.recruiter_rank = CovenantManagerRankFactory(covenant=self.covenant)

        self.author_account = AccountFactory(username="withdrawauthor")
        self.author_actor, self.author_sheet = _make_actor_with_account(
            "withdraw_author_actor", self.room, self.author_account
        )
        CharacterCovenantRoleFactory(
            character_sheet=self.author_sheet, covenant=self.covenant, rank=self.recruiter_rank
        )

        self.stranger_account = AccountFactory(username="withdrawstranger")
        self.stranger_actor, _ = _make_actor_with_account(
            "withdraw_stranger_actor", self.room, self.stranger_account
        )

        self.staff_account = AccountFactory(username="withdrawstaff", is_staff=True)
        self.staff_actor, _ = _make_actor_with_account(
            "withdraw_staff_actor", self.room, self.staff_account
        )

    def _pending_request(self):
        return GroupStoryRequestFactory(
            covenant=self.covenant, requested_by_account=self.author_account
        )

    def test_author_withdraws_own_request(self):
        request = self._pending_request()
        result = WithdrawGroupStoryRequestAction().run(
            actor=self.author_actor, request_id=request.pk
        )
        assert result.success
        request.refresh_from_db()
        assert request.status == GroupStoryRequestStatus.WITHDRAWN

    def test_staff_can_withdraw(self):
        request = self._pending_request()
        result = WithdrawGroupStoryRequestAction().run(
            actor=self.staff_actor, request_id=request.pk
        )
        assert result.success

    def test_unauthorized_stranger_is_refused(self):
        request = self._pending_request()
        result = WithdrawGroupStoryRequestAction().run(
            actor=self.stranger_actor, request_id=request.pk
        )
        assert not result.success
        request.refresh_from_db()
        assert request.status == GroupStoryRequestStatus.PENDING


class GMQueueOpenGroupRequestsTest(APITestCase):
    """GET /api/stories/gm-queue/ surfaces the broadcast open-request queue."""

    def test_open_group_request_appears_in_gm_queue(self):
        covenant = CovenantFactory(name="The Open Circle")
        requester_account = AccountFactory()
        request = GroupStoryRequestFactory(
            covenant=covenant, requested_by_account=requester_account
        )

        gm_account = AccountFactory()
        GMProfileFactory(account=gm_account)
        self.client.force_authenticate(user=gm_account)
        resp = self.client.get(reverse("stories-gm-queue"))
        assert resp.status_code == 200
        request_ids = [row["request_id"] for row in resp.data["open_group_requests"]]
        assert request.pk in request_ids


class GroupStoryRequestJourneyTest(TestCase):
    """End-to-end journey per the spec's Testing section: request -> claim -> withdraw path."""

    def test_full_journey(self):
        room = _make_room("JourneyRoom")
        covenant = CovenantFactory()
        recruiter_rank = CovenantManagerRankFactory(covenant=covenant)

        recruiter_account = AccountFactory(username="journey_recruiter")
        recruiter_actor, recruiter_sheet = _make_actor_with_account(
            "journey_recruiter_actor", room, recruiter_account
        )
        CharacterCovenantRoleFactory(
            character_sheet=recruiter_sheet, covenant=covenant, rank=recruiter_rank
        )

        # Second member, to be seated on claim.
        member_sheet = CharacterSheetFactory()
        CharacterCovenantRoleFactory(character_sheet=member_sheet, covenant=covenant)

        # 1. Ranked member creates the request.
        create_result = RequestGMForCovenantAction().run(
            actor=recruiter_actor, covenant_id=covenant.pk, message="Seeking adventure!"
        )
        assert create_result.success
        request = GroupStoryRequest.objects.get(covenant=covenant)

        # 2. A GM claims it.
        gm_account = AccountFactory(username="journey_gm")
        gm_profile = GMProfileFactory(account=gm_account)
        gm_table = GMTableFactory(gm=gm_profile, status=GMTableStatus.ACTIVE)
        gm_actor, _ = _make_actor_with_account("journey_gm_actor", room, gm_account)

        claim_result = ClaimGroupStoryRequestAction().run(actor=gm_actor, request_id=request.pk)
        assert claim_result.success

        request.refresh_from_db()
        assert request.status == GroupStoryRequestStatus.ACCEPTED
        story = request.created_story
        assert story.scope == StoryScope.GROUP
        assert story.primary_table_id == gm_table.pk
        seated = set(
            GMTableMembership.objects.filter(table=gm_table, left_at__isnull=True).values_list(
                "persona_id", flat=True
            )
        )
        assert recruiter_sheet.primary_persona.pk in seated
        assert member_sheet.primary_persona.pk in seated

        # 3. A second request for the same covenant can now be posted and withdrawn.
        second_result = RequestGMForCovenantAction().run(
            actor=recruiter_actor, covenant_id=covenant.pk, message="Round two!"
        )
        assert second_result.success
        second_request = GroupStoryRequest.objects.filter(
            covenant=covenant, status=GroupStoryRequestStatus.PENDING
        ).get()

        withdraw_result = WithdrawGroupStoryRequestAction().run(
            actor=recruiter_actor, request_id=second_request.pk
        )
        assert withdraw_result.success
        second_request.refresh_from_db()
        assert second_request.status == GroupStoryRequestStatus.WITHDRAWN
