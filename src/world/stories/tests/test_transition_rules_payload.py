"""Routing rules ride the transition payload, GM-only (#3563)."""

from types import SimpleNamespace

from django.contrib.auth.models import AnonymousUser
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from evennia_extensions.factories import AccountFactory
from world.gm.factories import GMProfileFactory, GMTableFactory
from world.stories.constants import BeatOutcome, BeatPredicateType, StakeResolutionColumn
from world.stories.factories import (
    BeatFactory,
    ChapterFactory,
    EpisodeFactory,
    StakeFactory,
    StoryFactory,
    TransitionFactory,
    TransitionRequiredOutcomeFactory,
)
from world.stories.serializers import TransitionSerializer


class TransitionRulesPayloadTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.lead_gm_account = AccountFactory()
        cls.lead_gm_profile = GMProfileFactory(account=cls.lead_gm_account)
        cls.gm_table = GMTableFactory(gm=cls.lead_gm_profile)
        cls.staff_account = AccountFactory(is_staff=True)
        cls.player_account = AccountFactory()
        cls.story = StoryFactory(owners=[cls.lead_gm_account], primary_table=cls.gm_table)
        cls.chapter = ChapterFactory(story=cls.story)
        cls.ep1 = EpisodeFactory(chapter=cls.chapter, order=1)
        cls.ep2 = EpisodeFactory(chapter=cls.chapter, order=2)
        cls.beat = BeatFactory(
            episode=cls.ep1,
            predicate_type=BeatPredicateType.OUTCOME_TIER,
            internal_description="Hostage exchange",
        )
        cls.stake = StakeFactory(beat=cls.beat, player_summary="The hostage")
        cls.transition = TransitionFactory(source_episode=cls.ep1, target_episode=cls.ep2, order=1)
        cls.beat_rule = TransitionRequiredOutcomeFactory(
            transition=cls.transition,
            beat=cls.beat,
            required_outcome=BeatOutcome.SUCCESS,
            required_outcome_key="negotiate",
        )
        cls.stake_rule = TransitionRequiredOutcomeFactory(
            transition=cls.transition,
            beat=cls.beat,
            stake=cls.stake,
            required_outcome="",
            required_stake_column=StakeResolutionColumn.LOSS,
        )

    def _detail(self, account):
        self.client.force_authenticate(user=account)
        return self.client.get(reverse("transition-detail", args=[self.transition.pk]))

    def test_lead_gm_sees_beat_and_stake_rules(self) -> None:
        response = self._detail(self.lead_gm_account)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        rules = response.data["required_outcomes"]
        self.assertEqual(len(rules), 2)
        by_id = {rule["id"]: rule for rule in rules}
        beat_row = by_id[self.beat_rule.pk]
        self.assertEqual(beat_row["beat"], self.beat.pk)
        self.assertEqual(beat_row["beat_title"], "Hostage exchange")
        self.assertEqual(beat_row["required_outcome"], BeatOutcome.SUCCESS)
        self.assertEqual(beat_row["required_outcome_key"], "negotiate")
        self.assertIsNone(beat_row["stake"])
        self.assertEqual(beat_row["stake_summary"], "")
        stake_row = by_id[self.stake_rule.pk]
        self.assertEqual(stake_row["stake"], self.stake.pk)
        self.assertEqual(stake_row["stake_summary"], "The hostage")
        self.assertEqual(stake_row["required_stake_column"], StakeResolutionColumn.LOSS)

    def test_staff_sees_rules(self) -> None:
        response = self._detail(self.staff_account)
        self.assertIn("required_outcomes", response.data)

    def test_player_payload_has_no_rules_key(self) -> None:
        response = self._detail(self.player_account)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertNotIn("required_outcomes", response.data)

    def test_no_request_context_strips_rules(self) -> None:
        data = TransitionSerializer(self.transition, context={}).data
        self.assertNotIn("required_outcomes", data)

    def test_anonymous_context_strips_rules(self) -> None:
        request = SimpleNamespace(user=AnonymousUser())
        data = TransitionSerializer(self.transition, context={"request": request}).data
        self.assertNotIn("required_outcomes", data)

    def test_list_query_count_does_not_grow_with_transitions(self) -> None:
        """Adding transitions costs at most one more query, never one per row.

        ``before`` and ``after`` aren't expected exactly equal: the four
        transitions created below are never-before-fetched rows, and their
        very first fetch legitimately costs one query the identity-mapped
        original transition (warmed by the call below) doesn't pay again.
        What must NOT happen is that cost scaling with the row count -- a
        naive ``transition.required_outcomes.all()`` per instance (no
        prefetch) would cost one query PER new transition (verified locally:
        4 new transitions => +4 queries without the ``Prefetch`` in
        ``TransitionViewSet.queryset``, vs. +1 with it, batched via a single
        ``IN (...)`` query). So the bound here is "at most one more query
        total", not "one per new row".
        """
        self.client.force_authenticate(user=self.lead_gm_account)
        url = reverse("transition-list") + f"?story={self.story.pk}"
        self.client.get(url)  # warm per-instance caches (gm_profile, owner_account_ids, ...)
        with CaptureQueriesContext(connection) as before:
            self.client.get(url)
        for order in range(2, 6):
            extra = TransitionFactory(source_episode=self.ep1, target_episode=self.ep2, order=order)
            TransitionRequiredOutcomeFactory(
                transition=extra, beat=self.beat, required_outcome=BeatOutcome.FAILURE
            )
        with CaptureQueriesContext(connection) as after:
            response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertLessEqual(len(after) - len(before), 1, [q["sql"] for q in after])

    def test_save_with_outcomes_response_carries_fresh_rules(self) -> None:
        self.client.force_authenticate(user=self.lead_gm_account)
        payload = {
            "existing_id": self.transition.pk,
            "source_episode": self.ep1.pk,
            "target_episode": self.ep2.pk,
            "outcomes": [{"beat": self.beat.pk, "required_outcome": BeatOutcome.FAILURE}],
        }
        response = self.client.post(
            reverse("transition-save-with-outcomes"), payload, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        rules = response.data["required_outcomes"]
        self.assertEqual([r["required_outcome"] for r in rules], [BeatOutcome.FAILURE])
