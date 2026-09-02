"""routing_problems rides the episode list and detail, GM-only (#3563)."""

from django.db import connection
from django.db.models import Count
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from evennia_extensions.factories import AccountFactory
from world.gm.factories import GMProfileFactory, GMTableFactory
from world.stories.constants import BeatOutcome, BeatPredicateType, StoryMaturity
from world.stories.factories import (
    BeatFactory,
    ChapterFactory,
    EpisodeFactory,
    StoryFactory,
    TransitionFactory,
    TransitionRequiredOutcomeFactory,
)
from world.stories.models import Episode
from world.stories.serializers import EpisodeDetailSerializer, EpisodeListSerializer


class EpisodeRoutingProblemsTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.lead_gm_account = AccountFactory()
        cls.lead_gm_profile = GMProfileFactory(account=cls.lead_gm_account)
        cls.gm_table = GMTableFactory(gm=cls.lead_gm_profile)
        cls.player_account = AccountFactory()
        cls.story = StoryFactory(owners=[cls.lead_gm_account], primary_table=cls.gm_table)
        cls.chapter = ChapterFactory(story=cls.story)
        cls.dead_end = EpisodeFactory(chapter=cls.chapter, order=1)
        cls.clean = EpisodeFactory(chapter=cls.chapter, order=2)
        cls.beat = BeatFactory(
            episode=cls.dead_end,
            predicate_type=BeatPredicateType.OUTCOME_TIER,
            internal_description="Hostage exchange",
        )
        to_clean = TransitionFactory(source_episode=cls.dead_end, target_episode=cls.clean, order=1)
        TransitionRequiredOutcomeFactory(
            transition=to_clean, beat=cls.beat, required_outcome=BeatOutcome.SUCCESS
        )
        TransitionFactory(source_episode=cls.clean, target_episode=None, order=1)

    def _list(self, account):
        self.client.force_authenticate(user=account)
        return self.client.get(reverse("episode-list") + f"?story={self.story.pk}")

    def test_owner_list_carries_routing_problems(self) -> None:
        response = self._list(self.lead_gm_account)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        by_id = {row["id"]: row for row in response.data["results"]}
        self.assertEqual(
            by_id[self.dead_end.pk]["routing_problems"],
            [f"beat #{self.beat.pk} (Hostage exchange) = FAILURE: no transition accepts it"],
        )
        self.assertEqual(by_id[self.clean.pk]["routing_problems"], [])

    def test_player_list_has_no_routing_problems_key(self) -> None:
        response = self._list(self.player_account)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        for row in response.data["results"]:
            self.assertNotIn("routing_problems", row)

    def test_owner_detail_carries_problems_and_ambiguity_flag(self) -> None:
        self.client.force_authenticate(user=self.lead_gm_account)
        response = self.client.get(reverse("episode-detail", args=[self.dead_end.pk]))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["routing_problems"]), 1)
        self.assertFalse(response.data["routing_ambiguous"])

    def test_player_detail_has_no_routing_problems_key(self) -> None:
        self.client.force_authenticate(user=self.player_account)
        response = self.client.get(reverse("episode-detail", args=[self.dead_end.pk]))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertNotIn("routing_problems", response.data)

    def test_no_request_context_strips_on_both_serializers(self) -> None:
        # The list serializer reads the viewset's scenes_count annotation.
        annotated = Episode.objects.annotate(scenes_count=Count("episode_scenes")).get(
            pk=self.dead_end.pk
        )
        self.assertNotIn("routing_problems", EpisodeListSerializer(annotated, context={}).data)
        self.assertNotIn(
            "routing_problems", EpisodeDetailSerializer(self.dead_end, context={}).data
        )

    def test_pitch_maturity_list_row_never_carries_summary(self) -> None:
        # summary isn't a declared EpisodeListSerializer field; _gm_text_gate
        # must not inject it just because the episode is PITCH-maturity (#3563).
        pitch_episode = EpisodeFactory(chapter=self.chapter, order=3, maturity=StoryMaturity.PITCH)

        player_response = self._list(self.player_account)
        self.assertEqual(player_response.status_code, status.HTTP_200_OK)
        player_row = next(
            row for row in player_response.data["results"] if row["id"] == pitch_episode.pk
        )
        self.assertNotIn("summary", player_row)
        self.assertNotIn("routing_problems", player_row)

        gm_response = self._list(self.lead_gm_account)
        self.assertEqual(gm_response.status_code, status.HTTP_200_OK)
        gm_row = next(row for row in gm_response.data["results"] if row["id"] == pitch_episode.pk)
        self.assertNotIn("summary", gm_row)

    def test_list_query_count_does_not_grow_with_episodes(self) -> None:
        self.client.force_authenticate(user=self.lead_gm_account)
        url = reverse("episode-list") + f"?story={self.story.pk}"
        self.client.get(url)  # warm per-instance caches (gm_profile, owner_account_ids)
        with CaptureQueriesContext(connection) as before:
            self.client.get(url)
        for order in range(3, 8):
            episode = EpisodeFactory(chapter=self.chapter, order=order)
            beat = BeatFactory(episode=episode, predicate_type=BeatPredicateType.OUTCOME_TIER)
            edge = TransitionFactory(source_episode=episode, target_episode=self.clean, order=1)
            TransitionRequiredOutcomeFactory(
                transition=edge, beat=beat, required_outcome=BeatOutcome.SUCCESS
            )
        with CaptureQueriesContext(connection) as after:
            response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(after), len(before), [q["sql"] for q in after])
