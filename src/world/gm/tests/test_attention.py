"""GET /api/gm/attention/ (#4188): what is waiting on one GM, as counts."""

from __future__ import annotations

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from evennia_extensions.factories import AccountFactory, CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.character_sheets.types import ProfileTextField
from world.events.factories import EventFactory
from world.gm.factories import GMProfileFactory, GMTableFactory, GMTableMembershipFactory
from world.gm.services import gm_attention, submit_profile_text_request
from world.scenes.factories import PersonaFactory
from world.stories.constants import (
    AssistantClaimStatus,
    CrossoverInviteStatus,
    SessionRequestStatus,
    StoryGMOfferStatus,
)
from world.stories.factories import (
    AssistantGMClaimFactory,
    SessionRequestFactory,
    StoryFactory,
    StoryGMOfferFactory,
)
from world.stories.models import CrossoverInvite


def _membership_at(table, account):
    """An ACTIVE membership at ``table`` for a persona whose character ``account`` plays."""
    character = CharacterFactory()
    character.db_account = account
    character.save()
    sheet = CharacterSheetFactory(character=character)
    return GMTableMembershipFactory(table=table, persona=PersonaFactory(character_sheet=sheet))


class GMAttentionCountsTest(APITestCase):
    """Each count against rows that should and should not be counted."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.account = AccountFactory()
        cls.gm = GMProfileFactory(account=cls.account)
        cls.table = GMTableFactory(gm=cls.gm)
        cls.other_gm = GMProfileFactory()
        cls.other_table = GMTableFactory(gm=cls.other_gm)

    def test_empty(self) -> None:
        attention = gm_attention(self.account)
        self.assertEqual(attention.total, 0)
        self.assertEqual(attention.story_offers, 0)
        self.assertEqual(attention.my_claims, 0)

    def test_story_offers_counts_pending_offers_to_this_gm(self) -> None:
        StoryGMOfferFactory(offered_to=self.gm)
        StoryGMOfferFactory(offered_to=self.gm, status=StoryGMOfferStatus.DECLINED)
        StoryGMOfferFactory(offered_to=self.other_gm)
        self.assertEqual(gm_attention(self.account).story_offers, 1)

    def test_crossover_invites_counts_pending_received_invites(self) -> None:
        mine = StoryFactory()
        mine.owners.add(self.account)
        theirs = StoryFactory()
        theirs.owners.add(self.other_gm.account)
        event = EventFactory()
        # Received and pending: counted.
        CrossoverInvite.objects.create(event=event, from_gm=self.other_gm, to_story=mine)
        # Received but withdrawn: not counted.
        CrossoverInvite.objects.create(
            event=EventFactory(),
            from_gm=self.other_gm,
            to_story=mine,
            status=CrossoverInviteStatus.WITHDRAWN,
        )
        # Sent by this GM: theirs to answer, not mine.
        CrossoverInvite.objects.create(event=event, from_gm=self.gm, to_story=theirs)
        self.assertEqual(gm_attention(self.account).crossover_invites, 1)

    def test_crossover_invite_to_my_own_story_from_me_is_not_waiting(self) -> None:
        """An invite I sent to a story I also own is mine to withdraw, not to answer."""
        mine = StoryFactory()
        mine.owners.add(self.account)
        CrossoverInvite.objects.create(event=EventFactory(), from_gm=self.gm, to_story=mine)
        self.assertEqual(gm_attention(self.account).crossover_invites, 0)

    def test_sheet_update_requests_counts_the_pending_review_pool(self) -> None:
        player = AccountFactory()
        at_my_table = _membership_at(self.table, player)
        submit_profile_text_request(
            at_my_table,
            field=ProfileTextField.BACKGROUND,
            proposed_text="New text.",
            reasoning="Reason.",
        )
        # A request at another GM's table, from a persona not at mine: not counted.
        elsewhere = _membership_at(self.other_table, AccountFactory())
        submit_profile_text_request(
            elsewhere,
            field=ProfileTextField.BACKGROUND,
            proposed_text="Other text.",
            reasoning="Reason.",
        )
        self.assertEqual(gm_attention(self.account).sheet_update_requests, 1)

    def test_claims_and_session_requests_read_the_lead_gm_queue(self) -> None:
        story = StoryFactory(primary_table=self.table)
        AssistantGMClaimFactory(beat__episode__chapter__story=story)
        AssistantGMClaimFactory(
            beat__episode__chapter__story=story, status=AssistantClaimStatus.REJECTED
        )
        SessionRequestFactory(episode__chapter__story=story, assigned_gm=self.gm)
        SessionRequestFactory(
            episode__chapter__story=story,
            assigned_gm=self.gm,
            status=SessionRequestStatus.CANCELLED,
        )
        # Another GM's story: not in my queue.
        other_story = StoryFactory(primary_table=self.other_table)
        AssistantGMClaimFactory(beat__episode__chapter__story=other_story)
        attention = gm_attention(self.account)
        self.assertEqual(attention.claims_to_approve, 1)
        self.assertEqual(attention.session_requests, 1)

    def test_my_claims_counts_my_open_claims_only(self) -> None:
        AssistantGMClaimFactory(assistant_gm=self.gm)
        AssistantGMClaimFactory(assistant_gm=self.gm, status=AssistantClaimStatus.APPROVED)
        AssistantGMClaimFactory(assistant_gm=self.gm, status=AssistantClaimStatus.COMPLETED)
        AssistantGMClaimFactory(assistant_gm=self.gm, status=AssistantClaimStatus.CANCELLED)
        AssistantGMClaimFactory(assistant_gm=self.other_gm)
        self.assertEqual(gm_attention(self.account).my_claims, 2)

    def test_total_is_the_sum(self) -> None:
        StoryGMOfferFactory(offered_to=self.gm)
        AssistantGMClaimFactory(assistant_gm=self.gm)
        attention = gm_attention(self.account)
        self.assertEqual(attention.total, 2)


class GMAttentionViewTest(APITestCase):
    """The endpoint: the counts plus ``total``, GMs only."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.account = AccountFactory()
        cls.gm = GMProfileFactory(account=cls.account)
        cls.staff_without_profile = AccountFactory(is_staff=True)
        cls.player = AccountFactory()

    def test_gm_reads_the_counts_and_total(self) -> None:
        StoryGMOfferFactory(offered_to=self.gm)
        self.client.force_authenticate(user=self.account)
        resp = self.client.get(reverse("gm:gm-attention"))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(
            resp.data,
            {
                "story_offers": 1,
                "crossover_invites": 0,
                "sheet_update_requests": 0,
                "claims_to_approve": 0,
                "my_claims": 0,
                "session_requests": 0,
                "total": 1,
            },
        )

    def test_player_without_profile_is_refused(self) -> None:
        self.client.force_authenticate(user=self.player)
        resp = self.client.get(reverse("gm:gm-attention"))
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_staff_without_profile_is_refused(self) -> None:
        """Decision 8: the badge needs a GMProfile; staff see only the Staff row."""
        self.client.force_authenticate(user=self.staff_without_profile)
        resp = self.client.get(reverse("gm:gm-attention"))
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_anonymous_is_refused(self) -> None:
        resp = self.client.get(reverse("gm:gm-attention"))
        self.assertIn(resp.status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN))
