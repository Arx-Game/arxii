"""Tests for the scene highlight reel (#1241, #2161).

The reel features one sealed "top moment" + a ranked index of the rest:
- Featured = the highest-ranked GM-tagged pose; a tagged pose headlines even with zero
  votes/reactions (storyteller curation has primacy). With no tags, falls back to the
  single most-ranked pose.
- Ranking (#2161) is all-time ``WeeklyVote`` count first (persistent rows, not the
  weekly-reset ``Interaction.vote_count`` counter), reaction count as tie-break, and
  recency last.
- Index = remaining poses with >= 1 vote or reaction, ranked as above, capped at 10,
  with the featured pose excluded.
- Source set is filtered through ``Interaction.visible_to`` so a pose the viewer cannot
  see never appears — not even as a sealed slot.
- Payload carries interaction ids + ``vote_count``/``reaction_count`` (the featured card
  stays otherwise sealed; the frontend reveals a pose via the existing
  interaction-detail endpoint).
"""

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from evennia_extensions.factories import AccountFactory
from world.game_clock.week_services import advance_game_week, get_current_game_week
from world.magic.factories import DramaticMomentTagFactory
from world.progression.constants import VoteTargetType
from world.progression.models.voting import WeeklyVote
from world.scenes.constants import InteractionVisibility, ScenePrivacyMode
from world.scenes.factories import (
    InteractionFactory,
    InteractionReactionFactory,
    SceneFactory,
)


class HighlightReelTestMixin:
    """Shared helpers for building reel fixtures and calling the endpoint."""

    def _react(self, interaction, n):
        """Give ``interaction`` ``n`` reactions from distinct accounts."""
        for _ in range(n):
            InteractionReactionFactory(interaction=interaction)

    def _vote(self, interaction, game_week, *, processed=False):
        """Cast one all-time ``WeeklyVote`` on ``interaction`` from a fresh voter."""
        return WeeklyVote.objects.create(
            voter=AccountFactory(),
            game_week=game_week,
            target_type=VoteTargetType.INTERACTION,
            target_id=interaction.pk,
            author_account=AccountFactory(),
            processed=processed,
        )

    def _tag(self, interaction):
        """GM-tag ``interaction`` (pose-anchored DramaticMomentTag)."""
        return DramaticMomentTagFactory(
            interaction=interaction,
            interaction_timestamp=interaction.timestamp,
            scene=interaction.scene,
        )

    def _reel(self, account, scene):
        self.client.force_authenticate(account)
        url = reverse("scene-highlight-reel", kwargs={"pk": scene.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        return response.data

    def _index_ids(self, data):
        return [entry["interaction_id"] for entry in data["index"]]


class HighlightReelFeaturedSelectionTest(HighlightReelTestMixin, APITestCase):
    def setUp(self):
        self.viewer = AccountFactory()
        self.scene = SceneFactory()

    def test_tagged_pose_headlines_over_higher_reacted_untagged(self):
        tagged = InteractionFactory(scene=self.scene)
        self._react(tagged, 2)
        self._tag(tagged)
        loud = InteractionFactory(scene=self.scene)
        self._react(loud, 5)
        quiet = InteractionFactory(scene=self.scene)
        self._react(quiet, 1)

        data = self._reel(self.viewer, self.scene)

        # Curation primacy: the tagged pose headlines even though `loud` has more reactions.
        self.assertEqual(data["featured"]["interaction_id"], tagged.pk)
        # Index ranks the rest by reaction count; featured excluded.
        self.assertEqual(self._index_ids(data), [loud.pk, quiet.pk])
        self.assertEqual([e["rank"] for e in data["index"]], [1, 2])

    def test_tagged_pose_with_zero_reactions_still_headlines(self):
        tagged = InteractionFactory(scene=self.scene)  # 0 reactions
        self._tag(tagged)
        reacted = InteractionFactory(scene=self.scene)
        self._react(reacted, 3)

        data = self._reel(self.viewer, self.scene)

        self.assertEqual(data["featured"]["interaction_id"], tagged.pk)
        self.assertEqual(self._index_ids(data), [reacted.pk])

    def test_highest_reacted_among_multiple_tagged_headlines(self):
        low_tagged = InteractionFactory(scene=self.scene)
        self._react(low_tagged, 1)
        self._tag(low_tagged)
        high_tagged = InteractionFactory(scene=self.scene)
        self._react(high_tagged, 4)
        self._tag(high_tagged)
        loudest_untagged = InteractionFactory(scene=self.scene)
        self._react(loudest_untagged, 10)

        data = self._reel(self.viewer, self.scene)

        # Among the tagged poses, the highest-reacted one headlines.
        self.assertEqual(data["featured"]["interaction_id"], high_tagged.pk)
        # The untagged crowd-favourite still ranks the index by reactions.
        self.assertEqual(self._index_ids(data), [loudest_untagged.pk, low_tagged.pk])

    def test_no_tags_falls_back_to_top_reacted(self):
        top = InteractionFactory(scene=self.scene)
        self._react(top, 3)
        second = InteractionFactory(scene=self.scene)
        self._react(second, 1)

        data = self._reel(self.viewer, self.scene)

        self.assertEqual(data["featured"]["interaction_id"], top.pk)
        self.assertEqual(self._index_ids(data), [second.pk])


class HighlightReelIndexTest(HighlightReelTestMixin, APITestCase):
    def setUp(self):
        self.viewer = AccountFactory()
        self.scene = SceneFactory()

    def test_index_excludes_zero_reaction_poses_and_caps_at_ten(self):
        # 12 reacted poses (12, 11, ... 1 reactions) + a zero-reaction pose, no tags.
        reacted = []
        for i in range(12):
            itx = InteractionFactory(scene=self.scene)
            self._react(itx, 12 - i)
            reacted.append(itx)
        silent = InteractionFactory(scene=self.scene)  # 0 reactions

        data = self._reel(self.viewer, self.scene)

        # Featured = most-reacted; index = next 10, capped (so the 12th-ranked is dropped).
        self.assertEqual(data["featured"]["interaction_id"], reacted[0].pk)
        self.assertEqual(len(data["index"]), 10)
        self.assertEqual(self._index_ids(data), [itx.pk for itx in reacted[1:11]])
        # A zero-reaction pose is never a highlight.
        self.assertNotIn(silent.pk, self._index_ids(data))
        self.assertNotEqual(data["featured"]["interaction_id"], silent.pk)

    def test_empty_reel_when_no_reactions_and_no_tags(self):
        InteractionFactory(scene=self.scene)
        InteractionFactory(scene=self.scene)

        data = self._reel(self.viewer, self.scene)

        self.assertIsNone(data["featured"])
        self.assertEqual(data["index"], [])


class HighlightReelVisibilityTest(HighlightReelTestMixin, APITestCase):
    """A pose the viewer cannot see never reaches the reel — not even as a sealed slot."""

    def setUp(self):
        self.scene = SceneFactory(privacy_mode=ScenePrivacyMode.PUBLIC)

    def test_hidden_pose_absent_for_outsider_present_for_writer(self):
        writer = AccountFactory()
        public_pose = InteractionFactory(scene=self.scene)  # room-heard, visible to all
        self._react(public_pose, 1)
        # Very-private pose pinned to `writer` as its party (#1219 writer_account).
        hidden_pose = InteractionFactory(
            scene=self.scene,
            visibility=InteractionVisibility.VERY_PRIVATE,
            writer_account=writer,
        )
        self._react(hidden_pose, 5)  # the loudest pose, but private to its party

        # Outsider (authenticated, no presence/party) only perceives the public pose.
        outsider = AccountFactory()
        outsider_data = self._reel(outsider, self.scene)
        self.assertEqual(outsider_data["featured"]["interaction_id"], public_pose.pk)
        self.assertNotIn(hidden_pose.pk, self._index_ids(outsider_data))

        # The writer is a pinned party, so the very-private pose headlines for them.
        writer_data = self._reel(writer, self.scene)
        self.assertEqual(writer_data["featured"]["interaction_id"], hidden_pose.pk)
        self.assertEqual(self._index_ids(writer_data), [public_pose.pk])


class HighlightReelVoteRankingTest(HighlightReelTestMixin, APITestCase):
    """#2161 — all-time ``WeeklyVote`` counts dominate ranking; reactions tie-break.

    ``WeeklyVote`` rows are the persistent, all-time signal (they survive as
    ``processed=True`` after weekly settlement), unlike ``Interaction.vote_count``, a
    weekly counter reset to 0 at settlement. The reel ranks on the persistent rows.
    """

    def setUp(self):
        self.viewer = AccountFactory()
        self.scene = SceneFactory()

    def test_votes_across_weeks_outrank_higher_reaction_count(self):
        week1 = get_current_game_week()
        week2 = advance_game_week()

        voted = InteractionFactory(scene=self.scene)
        self._vote(voted, week1, processed=True)
        self._vote(voted, week1, processed=True)
        self._vote(voted, week2)
        self._react(voted, 1)

        loud = InteractionFactory(scene=self.scene)
        self._react(loud, 5)

        data = self._reel(self.viewer, self.scene)

        # 3 all-time votes (spanning two weeks, two of them already processed) beat 5
        # raw reactions on the untouched pose.
        self.assertEqual(data["featured"]["interaction_id"], voted.pk)
        self.assertEqual(data["featured"]["vote_count"], 3)
        self.assertEqual(data["featured"]["reaction_count"], 1)
        self.assertEqual(self._index_ids(data), [loud.pk])
        self.assertEqual(data["index"][0]["vote_count"], 0)
        self.assertEqual(data["index"][0]["reaction_count"], 5)

    def test_reaction_count_breaks_vote_ties(self):
        week = get_current_game_week()

        higher_reacted = InteractionFactory(scene=self.scene)
        self._vote(higher_reacted, week)
        self._vote(higher_reacted, week)
        self._react(higher_reacted, 4)

        lower_reacted = InteractionFactory(scene=self.scene)
        self._vote(lower_reacted, week)
        self._vote(lower_reacted, week)
        self._react(lower_reacted, 1)

        data = self._reel(self.viewer, self.scene)

        # Equal vote counts (2 each) -- reaction count breaks the tie.
        self.assertEqual(data["featured"]["interaction_id"], higher_reacted.pk)
        self.assertEqual(data["featured"]["vote_count"], 2)
        self.assertEqual(self._index_ids(data), [lower_reacted.pk])

    def test_zero_votes_keeps_reaction_ranked_fallback(self):
        top = InteractionFactory(scene=self.scene)
        self._react(top, 3)
        second = InteractionFactory(scene=self.scene)
        self._react(second, 1)

        data = self._reel(self.viewer, self.scene)

        # No WeeklyVote rows anywhere -- pre-feature reaction-ranked fallback holds.
        self.assertEqual(data["featured"]["interaction_id"], top.pk)
        self.assertEqual(data["featured"]["vote_count"], 0)
        self.assertEqual(data["featured"]["reaction_count"], 3)
        self.assertEqual(self._index_ids(data), [second.pk])
        self.assertEqual(data["index"][0]["vote_count"], 0)
        self.assertEqual(data["index"][0]["reaction_count"], 1)

    def test_gm_tagged_featured_logic_unchanged_by_votes(self):
        week = get_current_game_week()

        tagged = InteractionFactory(scene=self.scene)  # 0 votes, 0 reactions
        self._tag(tagged)
        heavily_voted = InteractionFactory(scene=self.scene)
        self._vote(heavily_voted, week)
        self._vote(heavily_voted, week)
        self._vote(heavily_voted, week)

        data = self._reel(self.viewer, self.scene)

        # Curation primacy holds even against a pose with real all-time votes.
        self.assertEqual(data["featured"]["interaction_id"], tagged.pk)
        self.assertEqual(self._index_ids(data), [heavily_voted.pk])

    def test_reel_entries_expose_vote_and_reaction_counts(self):
        week = get_current_game_week()

        pose = InteractionFactory(scene=self.scene)
        self._vote(pose, week)
        self._vote(pose, week)
        self._react(pose, 4)
        other = InteractionFactory(scene=self.scene)
        self._react(other, 1)

        data = self._reel(self.viewer, self.scene)

        self.assertIn("vote_count", data["featured"])
        self.assertIn("reaction_count", data["featured"])
        self.assertEqual(data["featured"]["vote_count"], 2)
        self.assertEqual(data["featured"]["reaction_count"], 4)
        entry = data["index"][0]
        self.assertEqual(entry["interaction_id"], other.pk)
        self.assertEqual(entry["vote_count"], 0)
        self.assertEqual(entry["reaction_count"], 1)
