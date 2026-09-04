"""End-to-end journey test for #3565: story beats run on the mission scenario graph.

One story, all in one place: a Lead GM authors a beat's scenario graph through
the Studio authoring API (entry node + BRANCH "negotiate" + BRANCH "fight" +
CHECK "sneak", each with terminal routes), wires the routing episodes via
``save-with-outcomes``, runs it into a live scene via ``run_beat``, the party
group-votes to a terminal, and the beat's outcome/outcome_key drives
``get_eligible_transitions`` to the right next episode. Replayed a second time
on a fresh beat through the "fight" branch to prove the option-key routing
picks the OTHER edge. Finally, the player-facing story log is checked to never
leak the option key or an ``outcome_key`` field (GM-authoring internals must
stay off the player-facing log).

Covers Tasks 1-7 together (scenario authoring, Studio permissions, transition
save-with-outcomes, run_beat, scene scenario view, group-vote play, story log
visibility) as a single connected journey rather than in isolation.
"""

from __future__ import annotations

from unittest import mock

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from actions.definitions.gm_story import RunBeatAction
from evennia_extensions.factories import AccountFactory, CharacterFactory, ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import CheckTypeFactory
from world.gm.constants import GMLevel
from world.gm.factories import GMProfileFactory, GMTableFactory, seed_default_gm_level_caps
from world.missions.constants import OptionKind, OptionSource
from world.missions.models import MissionNode
from world.roster.factories import RosterTenureFactory
from world.scenes.factories import SceneFactory, SceneParticipationFactory
from world.stories.constants import BeatKind, BeatOutcome, BeatPredicateType, StoryScope
from world.stories.factories import (
    BeatFactory,
    ChapterFactory,
    EpisodeFactory,
    StoryFactory,
    StoryParticipationFactory,
    StoryProgressFactory,
)
from world.stories.models import Beat, BeatCompletion
from world.stories.services.transitions import get_eligible_transitions
from world.stories.types import StoryStatus
from world.traits.factories import CheckOutcomeFactory


def _make_room(label: str = "Room") -> object:
    return ObjectDBFactory(db_key=label, db_typeclass_path="typeclasses.rooms.Room")


def _make_actor_with_account(db_key: str, room: object, account: object) -> tuple[object, object]:
    """Create a PC in *room* whose ``active_account`` is *account* (mirrors
    ``actions/tests/test_gm_story_run_beat.py``'s fixture helper).
    """
    char = CharacterFactory(db_key=db_key, location=room)
    sheet = CharacterSheetFactory(character=char)
    entry = RosterTenureFactory(
        roster_entry__character_sheet=sheet,
        player_data__account=account,
        end_date=None,
    ).roster_entry
    return char, entry.character_sheet


class ScenarioJourneyTests(APITestCase):
    """GM authors a scenario, runs it, the party votes, the episode routes (#3565)."""

    def setUp(self) -> None:
        seed_default_gm_level_caps()
        self.room = _make_room("JourneyRoom")

        # -- Lead GM (JUNIOR, cap seeded) with a story, and a scene at the room. --
        self.gm_account = AccountFactory(username="journey-gm")
        self.gm_profile = GMProfileFactory(account=self.gm_account, level=GMLevel.JUNIOR)
        self.gm_table = GMTableFactory(gm=self.gm_profile)
        self.gm_actor, self.gm_sheet = _make_actor_with_account(
            "journey_gm_actor", self.room, self.gm_account
        )

        self.player1_account = AccountFactory(username="journey-player1")
        self.player1_actor, self.player1_sheet = _make_actor_with_account(
            "journey_player1_actor", self.room, self.player1_account
        )
        # Story-log player-tier access reads the raw db_account FK (not the
        # roster-tenure-derived active_account) -- see
        # world.stories.permissions._story_log_user_has_access.
        self.player1_actor.db_account = self.player1_account
        self.player1_actor.save()

        self.player2_account = AccountFactory(username="journey-player2")
        self.player2_actor, self.player2_sheet = _make_actor_with_account(
            "journey_player2_actor", self.room, self.player2_account
        )

        self.scene = SceneFactory(location=self.room, is_active=True)
        SceneParticipationFactory(scene=self.scene, account=self.gm_account, is_gm=True)
        SceneParticipationFactory(scene=self.scene, account=self.player1_account, is_gm=False)
        SceneParticipationFactory(scene=self.scene, account=self.player2_account, is_gm=False)

        self.story = StoryFactory(
            owners=[self.gm_account],
            scope=StoryScope.CHARACTER,
            primary_table=self.gm_table,
            status=StoryStatus.ACTIVE,
        )
        StoryParticipationFactory(story=self.story, character=self.player1_sheet, is_active=True)
        self.chapter = ChapterFactory(story=self.story)
        self.episode = EpisodeFactory(chapter=self.chapter, order=1)
        self.episode_a = EpisodeFactory(chapter=self.chapter, order=2)
        self.episode_b = EpisodeFactory(chapter=self.chapter, order=3)
        self.progress = StoryProgressFactory(
            story=self.story,
            character_sheet=self.gm_sheet,
            current_episode=self.episode,
            is_active=True,
        )

        # -- Step 1: a SITUATION beat, predicate_type left at the (OUTCOME_TIER) default. --
        self.beat = BeatFactory(
            episode=self.episode,
            kind=BeatKind.SITUATION,
            predicate_type=BeatPredicateType.OUTCOME_TIER,
            required_mission=None,
        )
        self.assertEqual(
            Beat._meta.get_field("predicate_type").default, BeatPredicateType.OUTCOME_TIER
        )
        self.assertEqual(self.beat.predicate_type, BeatPredicateType.OUTCOME_TIER)

        self.client.force_authenticate(self.gm_account)

        # -- Step 2: GM authors the scenario graph as the beat's body. --
        create_resp = self.client.post(
            f"/api/beats/{self.beat.pk}/scenario/",
            {"name": "The Sunken Chapel", "summary": "A choice at the threshold.", "risk_tier": 1},
            format="json",
        )
        self.assertEqual(create_resp.status_code, status.HTTP_201_CREATED, create_resp.data)
        self.template_id = create_resp.data["id"]
        self.entry_node = MissionNode.objects.get(template_id=self.template_id, key="start")
        self.assertTrue(self.entry_node.is_entry)

        self.check_type = CheckTypeFactory()
        self.negotiate_option = self._create_option(
            key="negotiate",
            order=0,
            option_kind=OptionKind.BRANCH,
            authored_ic_framing="Talk your way past.",
        )
        self.fight_option = self._create_option(
            key="fight",
            order=1,
            option_kind=OptionKind.BRANCH,
            authored_ic_framing="Force the issue.",
        )
        self.sneak_option = self._create_option(
            key="sneak",
            order=2,
            option_kind=OptionKind.CHECK,
            authored_ic_framing="Slip past unseen.",
            authored_check_type=self.check_type.pk,
        )

        # Terminal routes: negotiate is a bare success (beat_outcome left blank,
        # derives SUCCESS from the tier-less terminal); fight is an authored
        # FAILURE terminal (#3560/#3565's beat_outcome override).
        self._create_route(option=self.negotiate_option, outcome_tier=None, beat_outcome="")
        self._create_route(option=self.fight_option, outcome_tier=None, beat_outcome="failure")

        # The CHECK option is authored (two tier routes, both terminal) but not
        # played in this journey -- per the brief, coverage of playing a CHECK
        # option lives in test_services_resolution_beat.py.
        self.sneak_success_tier = CheckOutcomeFactory(name="SneakSuccess", success_level=3)
        self.sneak_failure_tier = CheckOutcomeFactory(name="SneakFailure", success_level=-3)
        self._create_route(option=self.sneak_option, outcome_tier=self.sneak_success_tier.pk)
        self._create_route(option=self.sneak_option, outcome_tier=self.sneak_failure_tier.pk)

        # -- Step 3: wire the routing episodes off the SAME beat's two endings. --
        to_a = self.client.post(
            "/api/transitions/save-with-outcomes/",
            {
                "source_episode": self.episode.pk,
                "target_episode": self.episode_a.pk,
                "order": 0,
                "outcomes": [
                    {
                        "beat": self.beat.pk,
                        "required_outcome": BeatOutcome.SUCCESS,
                        "required_outcome_key": "negotiate",
                    }
                ],
            },
            format="json",
        )
        self.assertEqual(to_a.status_code, status.HTTP_201_CREATED, to_a.data)
        self.transition_to_a = to_a.data["id"]

        to_b = self.client.post(
            "/api/transitions/save-with-outcomes/",
            {
                "source_episode": self.episode.pk,
                "target_episode": self.episode_b.pk,
                "order": 1,
                "outcomes": [
                    {
                        "beat": self.beat.pk,
                        "required_outcome": BeatOutcome.FAILURE,
                        "required_outcome_key": "fight",
                    }
                ],
            },
            format="json",
        )
        self.assertEqual(to_b.status_code, status.HTTP_201_CREATED, to_b.data)
        self.transition_to_b = to_b.data["id"]

    def _create_option(
        self,
        *,
        key: str,
        order: int,
        option_kind: str,
        authored_ic_framing: str,
        authored_check_type: int | None = None,
    ) -> int:
        body = {
            "node": self.entry_node.pk,
            "order": order,
            "key": key,
            "option_kind": option_kind,
            "source_kind": OptionSource.AUTHORED,
            "authored_ic_framing": authored_ic_framing,
        }
        if authored_check_type is not None:
            body["authored_check_type"] = authored_check_type
        resp = self.client.post("/api/missions/options/", body, format="json")
        assert resp.status_code == status.HTTP_201_CREATED, resp.data
        return resp.data["id"]

    def _create_route(
        self,
        *,
        option: int,
        outcome_tier: int | None,
        beat_outcome: str | None = None,
        target_node: int | None = None,
    ) -> dict:
        body = {
            "option": option,
            "outcome_tier": outcome_tier,
            "target_node": target_node,
        }
        if beat_outcome is not None:
            body["beat_outcome"] = beat_outcome
        resp = self.client.post("/api/missions/routes/", body, format="json")
        assert resp.status_code == status.HTTP_201_CREATED, resp.data
        return resp.data

    def _run_beat_for_scene(self, beat: Beat) -> int:
        """Run *beat* into ``self.scene`` and return the scenario instance id."""
        result = RunBeatAction().run(self.gm_actor, beat_id=beat.pk)
        self.assertTrue(result.success, result.message)
        return result.data["scenario_instance_id"]

    def _journal_url(self, instance_id: int, action_name: str) -> str:
        return f"/api/missions/journal/{instance_id}/{action_name}/"

    def _group_pick(self, instance_id: int, actor: object, option_id: int) -> dict:
        with mock.patch("world.missions.views._acting_character", return_value=actor):
            resp = self.client.post(
                self._journal_url(instance_id, "group-pick"),
                {"option_id": option_id},
                format="json",
            )
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        return resp.data

    def _group_vote(self, instance_id: int, actor: object, option_id: int) -> dict:
        with mock.patch("world.missions.views._acting_character", return_value=actor):
            resp = self.client.post(
                self._journal_url(instance_id, "group-vote"),
                {"option_id": option_id},
                format="json",
            )
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        return resp.data

    # ------------------------------------------------------------------
    # Step 4-7 + 9: the negotiate run.
    # ------------------------------------------------------------------

    def test_negotiate_run_routes_to_episode_a(self) -> None:
        instance_id = self._run_beat_for_scene(self.beat)

        # -- Step 5: the scene's scenario view surfaces both BRANCH options. --
        self.client.force_authenticate(self.player1_account)
        scenario_url = reverse("scene-scenario", kwargs={"pk": self.scene.pk})
        scenario_resp = self.client.get(scenario_url)
        self.assertEqual(scenario_resp.status_code, status.HTTP_200_OK, scenario_resp.data)
        self.assertEqual(scenario_resp.data["instance_id"], instance_id)
        group_beat = scenario_resp.data["group_beat"]["group_beat"]
        self.assertIsNotNone(group_beat)
        branch_ids = {
            row["option_id"] for row in group_beat["options"] if row["kind"] == OptionKind.BRANCH
        }
        self.assertEqual(branch_ids, {self.negotiate_option, self.fight_option})

        # -- Step 6: the party picks + votes "negotiate". --
        self._group_pick(instance_id, self.player1_actor, self.negotiate_option)
        pick2 = self._group_pick(instance_id, self.player2_actor, self.negotiate_option)
        self._group_pick_resolved_or_voting(pick2)

        self._group_vote(instance_id, self.player1_actor, self.negotiate_option)
        vote2 = self._group_vote(instance_id, self.player2_actor, self.negotiate_option)
        self.assertIsNotNone(vote2["resolved"])
        self.assertTrue(vote2["resolved"]["is_terminal"])

        # -- Step 7: beat outcome + completion + routing. --
        self.beat.refresh_from_db()
        self.assertEqual(self.beat.outcome, BeatOutcome.SUCCESS)
        self.assertEqual(self.beat.outcome_key, "negotiate")
        completion = BeatCompletion.objects.get(beat=self.beat)
        self.assertEqual(completion.outcome_key, "negotiate")

        self.progress.refresh_from_db()
        eligible = get_eligible_transitions(self.progress)
        self.assertEqual([t.pk for t in eligible], [self.transition_to_a])

    def _group_pick_resolved_or_voting(self, pick_result: dict) -> None:
        """Accept either "still picking" or an immediate resolve for the 2nd pick."""
        if pick_result.get("resolved") is not None:
            return
        self.assertIsNotNone(pick_result["group_beat"])
        self.assertEqual(pick_result["group_beat"]["phase"], "vote")

    # ------------------------------------------------------------------
    # Step 8: a second, fresh beat replays the SAME graph through "fight".
    # ------------------------------------------------------------------

    def test_fight_run_on_fresh_beat_routes_to_episode_b(self) -> None:
        # A brand-new Beat, never run before, reusing the SAME authored graph
        # (same template/entry/options/routes built in setUp) -- proves the
        # option-key routing is per-beat, not baked into the graph itself.
        second_beat = Beat.objects.create(
            episode=self.episode,
            kind=BeatKind.SITUATION,
            predicate_type=BeatPredicateType.OUTCOME_TIER,
            required_mission_id=self.template_id,
            internal_description="Replay of the same scenario graph.",
        )
        to_a2 = self.client.post(
            "/api/transitions/save-with-outcomes/",
            {
                "source_episode": self.episode.pk,
                "target_episode": self.episode_a.pk,
                "order": 2,
                "outcomes": [
                    {
                        "beat": second_beat.pk,
                        "required_outcome": BeatOutcome.SUCCESS,
                        "required_outcome_key": "negotiate",
                    }
                ],
            },
            format="json",
        )
        self.assertEqual(to_a2.status_code, status.HTTP_201_CREATED, to_a2.data)
        to_b2 = self.client.post(
            "/api/transitions/save-with-outcomes/",
            {
                "source_episode": self.episode.pk,
                "target_episode": self.episode_b.pk,
                "order": 3,
                "outcomes": [
                    {
                        "beat": second_beat.pk,
                        "required_outcome": BeatOutcome.FAILURE,
                        "required_outcome_key": "fight",
                    }
                ],
            },
            format="json",
        )
        self.assertEqual(to_b2.status_code, status.HTTP_201_CREATED, to_b2.data)
        transition_to_b2 = to_b2.data["id"]

        instance_id = self._run_beat_for_scene(second_beat)

        self._group_pick(instance_id, self.player1_actor, self.fight_option)
        self._group_pick(instance_id, self.player2_actor, self.fight_option)
        self._group_vote(instance_id, self.player1_actor, self.fight_option)
        vote2 = self._group_vote(instance_id, self.player2_actor, self.fight_option)
        self.assertIsNotNone(vote2["resolved"])

        second_beat.refresh_from_db()
        self.assertEqual(second_beat.outcome, BeatOutcome.FAILURE)
        self.assertEqual(second_beat.outcome_key, "fight")

        self.progress.refresh_from_db()
        eligible = get_eligible_transitions(self.progress)
        self.assertEqual([t.pk for t in eligible], [transition_to_b2])

    # ------------------------------------------------------------------
    # Step 9: the player-facing story log never leaks the option key.
    # ------------------------------------------------------------------

    def test_player_story_log_hides_option_key(self) -> None:
        instance_id = self._run_beat_for_scene(self.beat)
        self._group_pick(instance_id, self.player1_actor, self.negotiate_option)
        self._group_pick(instance_id, self.player2_actor, self.negotiate_option)
        self._group_vote(instance_id, self.player1_actor, self.negotiate_option)
        self._group_vote(instance_id, self.player2_actor, self.negotiate_option)
        self.beat.refresh_from_db()
        self.assertEqual(self.beat.outcome, BeatOutcome.SUCCESS)

        self.client.force_authenticate(self.player1_account)
        log_resp = self.client.get(reverse("story-log", kwargs={"pk": self.story.pk}))
        self.assertEqual(log_resp.status_code, status.HTTP_200_OK, log_resp.data)
        entries = log_resp.data["entries"]
        self.assertTrue(entries)
        for entry in entries:
            self.assertNotIn("outcome_key", entry)
            for value in entry.values():
                self.assertNotIn("negotiate", str(value))
