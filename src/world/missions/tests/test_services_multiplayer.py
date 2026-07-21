"""Tests for the Phase-4 multi-person orchestrator.

Covers:
  * Task 4.1 ``build_group_option_list`` — owner-tagged union across all
    participants; AUTHORED visibility scoped per participant.
  * Task 4.2 ``_tally_group_winner`` — GROUP_VOTE winner (plurality of
    votes, random tie) + actor = picker (#1036).
  * Task 4.3 ``resolve_group_node`` — ballot-driven; actor attribution
    (moral consequence follows the actor), JOINT per-participant deeds +
    single combined routing, ``contract_holder``.

Real factory objects, no ORM mocks. ``force_check_outcome`` pins rolled
outcome tiers deterministically; COINFLIP uses the codebase RNG
convention (``random.choice``) so its test asserts "one of the distinct
picks" rather than a fixed value.
"""

from unittest.mock import patch

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory, ObjectDBFactory, RoomProfileFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import CheckTypeFactory, ConsequenceFactory
from world.checks.test_helpers import force_check_outcome
from world.checks.types import CheckResult
from world.distinctions.factories import CharacterDistinctionFactory, DistinctionFactory
from world.mechanics.factories import ChallengeApproachFactory, ChallengeTemplateFactory
from world.missions.constants import (
    ConflictMode,
    DeedRewardKind,
    DeedRewardSink,
    JointCombine,
    MissionStatus,
    NodeLocationMode,
    OptionKind,
    OptionSource,
)
from world.missions.factories import (
    MissionInstanceFactory,
    MissionNodeFactory,
    MissionOptionFactory,
    MissionOptionRouteFactory,
    MissionOptionRouteRewardFactory,
    MissionParticipantFactory,
    MissionTemplateFactory,
)
from world.missions.models import (
    MissionDeedRewardLine,
    MissionGroupBallot,
    MissionOptionRouteReward,
)
from world.missions.services import (
    build_group_option_list,
    build_option_list,
    contract_holder,
    resolve_group_node,
)
from world.missions.services.multiplayer import _tally_group_winner
from world.traits.factories import CheckOutcomeFactory

_PERFORM_CHECK = "world.missions.services.resolution.perform_check"


def _result_for(check_type: object, outcome: object) -> CheckResult:
    """A minimal deterministic CheckResult (no dice) for patched checks."""
    return CheckResult(
        check_type=check_type,
        outcome=outcome,
        chart=None,
        roller_rank=None,
        target_rank=None,
        rank_difference=0,
        trait_points=0,
        aspect_bonus=0,
        total_points=0,
    )


def _seed_and_resolve(instance, node, picks, votes=None):
    """Seed MissionGroupBallot rows from ``picks`` (+optional ``votes``), then resolve.

    Mirrors the play surface's ballot collection for the engine tests (#1036):
    GROUP_VOTE tallies the votes (fallback to picks), JOINT runs every pick.
    """
    votes = votes or {}
    for participant, option in picks.items():
        MissionGroupBallot.objects.create(
            instance=instance,
            node=node,
            participant=participant,
            picked_option=option,
            voted_option=votes.get(participant),
        )
    return resolve_group_node(instance, node)


class BuildGroupOptionListTests(TestCase):
    """Union across participants; owner-tagged; AUTHORED scoped per viewer."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.char_a = CharacterFactory()
        cls.char_b = CharacterFactory()
        CharacterSheetFactory(character=cls.char_a)
        CharacterSheetFactory(character=cls.char_b)

        cls.template = MissionTemplateFactory(name="grp-opt-tmpl")
        cls.instance = MissionInstanceFactory(template=cls.template)
        cls.node = MissionNodeFactory(template=cls.template, key="entry", is_entry=True)
        cls.p_a = MissionParticipantFactory(
            instance=cls.instance, character=cls.char_a, is_contract_holder=True
        )
        cls.p_b = MissionParticipantFactory(instance=cls.instance, character=cls.char_b)

        # A owns dist_a, B owns dist_b (disjoint).
        cls.dist_a = DistinctionFactory(slug="grp-dist-a")
        cls.dist_b = DistinctionFactory(slug="grp-dist-b")
        CharacterDistinctionFactory(character=cls.char_a.sheet_data, distinction=cls.dist_a)
        CharacterDistinctionFactory(character=cls.char_b.sheet_data, distinction=cls.dist_b)

        # AUTHORED option visible only to A (requires dist_a).
        cls.a_only = MissionOptionFactory(
            node=cls.node,
            order=0,
            option_kind=OptionKind.BRANCH,
            source_kind=OptionSource.AUTHORED,
            visibility_rule={
                "leaf": "has_distinction",
                "params": {"slug": "grp-dist-a"},
            },
            authored_ic_framing="A-only path.",
        )
        # AUTHORED option visible only to B (requires dist_b).
        cls.b_only = MissionOptionFactory(
            node=cls.node,
            order=1,
            option_kind=OptionKind.BRANCH,
            source_kind=OptionSource.AUTHORED,
            visibility_rule={
                "leaf": "has_distinction",
                "params": {"slug": "grp-dist-b"},
            },
            authored_ic_framing="B-only path.",
        )
        # Ungated AUTHORED option visible to both.
        cls.open_option = MissionOptionFactory(
            node=cls.node,
            order=2,
            option_kind=OptionKind.BRANCH,
            source_kind=OptionSource.AUTHORED,
            authored_ic_framing="Open path.",
        )

    def test_union_has_both_disjoint_owned_sets_owner_tagged(self) -> None:
        options = build_group_option_list(self.instance, self.node)
        a_framings = {o.ic_framing for o in options if o.owner == self.char_a}
        b_framings = {o.ic_framing for o in options if o.owner == self.char_b}
        self.assertEqual(a_framings, {"A-only path.", "Open path."})
        self.assertEqual(b_framings, {"B-only path.", "Open path."})

    def test_gated_option_appears_once_owned_by_passing_participant(self) -> None:
        options = build_group_option_list(self.instance, self.node)
        a_only_entries = [o for o in options if o.option == self.a_only]
        self.assertEqual(len(a_only_entries), 1)
        self.assertEqual(a_only_entries[0].owner, self.char_a)

    def test_stable_order_by_participant_then_per_viewer_order(self) -> None:
        options = build_group_option_list(self.instance, self.node)
        owners_in_order = [o.owner for o in options]
        # All of participant A's entries (lower pk) precede participant B's.
        first_b = owners_in_order.index(self.char_b)
        self.assertTrue(all(o == self.char_a for o in owners_in_order[:first_b]))

    def test_single_participant_build_option_list_unchanged(self) -> None:
        # Phase-3 behavior preserved through the shared-helper refactor.
        single = build_option_list(self.instance, self.node, self.p_a)
        self.assertEqual(
            {o.ic_framing for o in single},
            {"A-only path.", "Open path."},
        )


class TallyGroupWinnerTests(TestCase):
    """GROUP_VOTE winner: plurality of votes (fallback to picks), random tie,
    actor = a *picker* of the winning option (holder preferred) (#1036)."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.template = MissionTemplateFactory(name="tally-tmpl")
        cls.instance = MissionInstanceFactory(template=cls.template)
        cls.holder = MissionParticipantFactory(
            instance=cls.instance,
            character=CharacterFactory(),
            is_contract_holder=True,
        )
        cls.p2 = MissionParticipantFactory(instance=cls.instance, character=CharacterFactory())
        cls.p3 = MissionParticipantFactory(instance=cls.instance, character=CharacterFactory())
        cls.node = MissionNodeFactory(template=cls.template, key="n", is_entry=True)
        cls.opt1 = MissionOptionFactory(node=cls.node, order=0)
        cls.opt2 = MissionOptionFactory(node=cls.node, order=1)

    def _ballots(self, picks, votes=None):
        votes = votes or {}
        return [
            MissionGroupBallot.objects.create(
                instance=self.instance,
                node=self.node,
                participant=participant,
                picked_option=option,
                voted_option=votes.get(participant),
            )
            for participant, option in picks.items()
        ]

    def test_no_votes_falls_back_to_pick_plurality(self) -> None:
        ballots = self._ballots({self.holder: self.opt1, self.p2: self.opt1, self.p3: self.opt2})
        option, actor = _tally_group_winner(ballots)
        self.assertEqual(option, self.opt1)
        self.assertEqual(actor, self.holder)  # holder picked the winner

    def test_votes_win_over_picks_and_actor_is_a_picker(self) -> None:
        # Picks favour opt1, but the cast votes all go to opt2 → opt2 wins.
        ballots = self._ballots(
            {self.holder: self.opt1, self.p2: self.opt1, self.p3: self.opt2},
            votes={self.holder: self.opt2, self.p2: self.opt2, self.p3: self.opt2},
        )
        option, actor = _tally_group_winner(ballots)
        self.assertEqual(option, self.opt2)
        # Actor must be the only PICKER of opt2 (p3), never a mere voter.
        self.assertEqual(actor, self.p3)

    def test_tie_breaks_at_random_among_tied(self) -> None:
        ballots = self._ballots({self.holder: self.opt1, self.p2: self.opt2})
        option, actor = _tally_group_winner(ballots)
        self.assertIn(option, {self.opt1, self.opt2})
        # Actor always picked whatever won.
        picked_by_actor = {b.picked_option for b in ballots if b.participant == actor}
        self.assertIn(option, picked_by_actor)

    def test_actor_prefers_holder_among_pickers(self) -> None:
        ballots = self._ballots({self.holder: self.opt1, self.p2: self.opt1})
        _, actor = _tally_group_winner(ballots)
        self.assertEqual(actor, self.holder)


class ContractHolderTests(TestCase):
    """contract_holder returns the single holding participant."""

    def test_returns_the_holder(self) -> None:
        instance = MissionInstanceFactory()
        holder = MissionParticipantFactory(
            instance=instance,
            character=CharacterFactory(),
            is_contract_holder=True,
        )
        MissionParticipantFactory(instance=instance, character=CharacterFactory())
        self.assertEqual(contract_holder(instance), holder)


class GroupResolveCoinflipVoteTests(TestCase):
    """COINFLIP/VOTE: one deed, actor == winning participant's character."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.char_h = CharacterFactory()
        cls.char_2 = CharacterFactory()
        CharacterSheetFactory(character=cls.char_h)
        CharacterSheetFactory(character=cls.char_2)

        cls.template = MissionTemplateFactory(name="grp-cv-tmpl", risk_tier=2)
        cls.instance = MissionInstanceFactory(template=cls.template)
        cls.entry = MissionNodeFactory(
            template=cls.template,
            key="entry",
            is_entry=True,
            conflict_mode=ConflictMode.GROUP_VOTE,
        )
        cls.dest = MissionNodeFactory(template=cls.template, key="dest")
        cls.holder = MissionParticipantFactory(
            instance=cls.instance,
            character=cls.char_h,
            is_contract_holder=True,
        )
        cls.p2 = MissionParticipantFactory(instance=cls.instance, character=cls.char_2)

        cls.success = CheckOutcomeFactory(name="GrpSuccess", success_level=3)
        cls.sneak = CheckTypeFactory(name="GrpSneak")
        cls.opt_h = MissionOptionFactory(
            node=cls.entry,
            order=0,
            option_kind=OptionKind.CHECK,
            source_kind=OptionSource.AUTHORED,
            authored_check_type=cls.sneak,
        )
        MissionOptionRouteFactory(
            option=cls.opt_h,
            outcome_tier=cls.success,
            target_node=cls.dest,
            consequence=ConsequenceFactory(outcome_tier=cls.success),
        )

    def test_vote_deed_actor_is_winning_participants_character(self) -> None:
        # Both pick holder's option → holder wins, holder is actor.
        picks = {self.holder: self.opt_h, self.p2: self.opt_h}
        with force_check_outcome(self.success):
            deeds = _seed_and_resolve(self.instance, self.entry, picks)
        self.assertEqual(len(deeds), 1)
        self.assertEqual(deeds[0].actor, self.char_h)
        self.instance.refresh_from_db()
        self.assertEqual(self.instance.current_node, self.dest)


class GroupResolveJointTests(TestCase):
    """JOINT: N per-participant deeds, per-actor attribution, single
    combined routing via ANY/ALL/COUNT."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.char_h = CharacterFactory()
        cls.char_2 = CharacterFactory()
        CharacterSheetFactory(character=cls.char_h)
        CharacterSheetFactory(character=cls.char_2)

        cls.template = MissionTemplateFactory(name="grp-joint-tmpl", risk_tier=2)
        cls.instance = MissionInstanceFactory(template=cls.template)
        cls.success = CheckOutcomeFactory(name="JSuccess", success_level=3)
        cls.failure = CheckOutcomeFactory(name="JFailure", success_level=-3)
        cls.sneak = CheckTypeFactory(name="JSneak")

        cls.win_node = MissionNodeFactory(template=cls.template, key="win")
        cls.lose_node = MissionNodeFactory(template=cls.template, key="lose")

    def _make_joint_node(self, combine: str, count: int | None = None) -> object:
        return MissionNodeFactory(
            template=self.template,
            key=f"j-{combine}-{count}",
            conflict_mode=ConflictMode.JOINT,
            joint_combine=combine,
            joint_count=count,
        )

    def _holder_option_with_routes(self, node: object) -> object:
        opt = MissionOptionFactory(
            node=node,
            order=0,
            option_kind=OptionKind.CHECK,
            source_kind=OptionSource.AUTHORED,
            authored_check_type=self.sneak,
        )
        MissionOptionRouteFactory(option=opt, outcome_tier=self.success, target_node=self.win_node)
        MissionOptionRouteFactory(option=opt, outcome_tier=self.failure, target_node=self.lose_node)
        return opt

    def _setup_participants(self, instance: object) -> tuple[object, object]:
        holder = MissionParticipantFactory(
            instance=instance,
            character=self.char_h,
            is_contract_holder=True,
        )
        p2 = MissionParticipantFactory(instance=instance, character=self.char_2)
        return holder, p2

    def _outcome_by_character(self, mapping: dict[object, object]) -> object:
        """A perform_check side effect: deterministic outcome per roller.

        ``perform_check(character, check_type, ...)`` → CheckResult whose
        outcome is ``mapping[character]``. Pins EVERY participant's check
        (force_check_outcome is single-shot and cannot pin two rolls).
        """

        def _side_effect(character: object, check_type: object, **_kw: object):
            return _result_for(check_type, mapping[character])

        return _side_effect

    def test_joint_any_one_success_routes_to_win_with_per_actor_deeds(
        self,
    ) -> None:
        instance = MissionInstanceFactory(template=self.template)
        holder, p2 = self._setup_participants(instance)
        node = self._make_joint_node(JointCombine.ANY)
        opt = self._holder_option_with_routes(node)
        picks = {holder: opt, p2: opt}
        # holder succeeds, p2 fails → ANY ⇒ combined success ⇒ win_node.
        with patch(
            _PERFORM_CHECK,
            side_effect=self._outcome_by_character(
                {self.char_h: self.success, self.char_2: self.failure}
            ),
        ):
            deeds = _seed_and_resolve(instance, node, picks)
        self.assertEqual(len(deeds), 2)
        # Per-actor attribution: each deed records its own participant; the
        # success deed belongs to the holder, the failure deed to p2 — no
        # cross-attribution.
        by_actor = {d.actor: d for d in deeds}
        self.assertEqual(set(by_actor), {self.char_h, self.char_2})
        self.assertEqual(by_actor[self.char_h].outcome, self.success)
        self.assertEqual(by_actor[self.char_2].outcome, self.failure)
        instance.refresh_from_db()
        self.assertEqual(instance.current_node, self.win_node)

    def test_joint_all_requires_every_success(self) -> None:
        instance = MissionInstanceFactory(template=self.template)
        holder, p2 = self._setup_participants(instance)
        node = self._make_joint_node(JointCombine.ALL)
        opt = self._holder_option_with_routes(node)
        picks = {holder: opt, p2: opt}
        # holder succeeds, p2 fails → ALL ⇒ combined failure ⇒ lose_node.
        with patch(
            _PERFORM_CHECK,
            side_effect=self._outcome_by_character(
                {self.char_h: self.success, self.char_2: self.failure}
            ),
        ):
            deeds = _seed_and_resolve(instance, node, picks)
        self.assertEqual(len(deeds), 2)
        instance.refresh_from_db()
        self.assertEqual(instance.current_node, self.lose_node)

    def test_joint_all_all_success_routes_to_win(self) -> None:
        instance = MissionInstanceFactory(template=self.template)
        holder, p2 = self._setup_participants(instance)
        node = self._make_joint_node(JointCombine.ALL)
        opt = self._holder_option_with_routes(node)
        picks = {holder: opt, p2: opt}
        with patch(
            _PERFORM_CHECK,
            side_effect=self._outcome_by_character(
                {self.char_h: self.success, self.char_2: self.success}
            ),
        ):
            _seed_and_resolve(instance, node, picks)
        instance.refresh_from_db()
        self.assertEqual(instance.current_node, self.win_node)

    def test_joint_count_threshold(self) -> None:
        instance = MissionInstanceFactory(template=self.template)
        holder, p2 = self._setup_participants(instance)
        node = self._make_joint_node(JointCombine.COUNT, count=2)
        opt = self._holder_option_with_routes(node)
        picks = {holder: opt, p2: opt}
        # Need >=2 successes; only 1 success → combined failure ⇒ lose_node.
        with patch(
            _PERFORM_CHECK,
            side_effect=self._outcome_by_character(
                {self.char_h: self.success, self.char_2: self.failure}
            ),
        ):
            deeds = _seed_and_resolve(instance, node, picks)
        self.assertEqual(len(deeds), 2)
        instance.refresh_from_db()
        self.assertEqual(instance.current_node, self.lose_node)

    def test_joint_count_threshold_met_routes_to_win(self) -> None:
        instance = MissionInstanceFactory(template=self.template)
        holder, p2 = self._setup_participants(instance)
        node = self._make_joint_node(JointCombine.COUNT, count=2)
        opt = self._holder_option_with_routes(node)
        picks = {holder: opt, p2: opt}
        with patch(
            _PERFORM_CHECK,
            side_effect=self._outcome_by_character(
                {self.char_h: self.success, self.char_2: self.success}
            ),
        ):
            _seed_and_resolve(instance, node, picks)
        instance.refresh_from_db()
        self.assertEqual(instance.current_node, self.win_node)

    def test_joint_single_combined_routing_not_per_attempt(self) -> None:
        # Each attempt transiently routes; final position is the SINGLE
        # combined decision (lose_node here, ALL with one failure) and the
        # run stays ACTIVE (no transient terminal leaks through).
        instance = MissionInstanceFactory(template=self.template)
        holder, p2 = self._setup_participants(instance)
        node = self._make_joint_node(JointCombine.ALL)
        opt = self._holder_option_with_routes(node)
        picks = {holder: opt, p2: opt}
        with patch(
            _PERFORM_CHECK,
            side_effect=self._outcome_by_character(
                {self.char_h: self.failure, self.char_2: self.failure}
            ),
        ):
            _seed_and_resolve(instance, node, picks)
        instance.refresh_from_db()
        self.assertEqual(instance.current_node, self.lose_node)
        self.assertEqual(instance.status, MissionStatus.ACTIVE)

    def test_joint_with_challenge_holder_routes_via_option_routes(self) -> None:
        # JOINT with a CHALLENGE-sourced holder option: each participant's
        # pick fans out via challenge_options_for_character (an is_default
        # approach reaches both characters without capability setup), and
        # _approach_for_pick recovers the per-participant approach for the
        # per-attempt resolve_option call. The combined-success decision
        # routes via the CHALLENGE option's outcome-tier route, exactly
        # like an AUTHORED option.
        instance = MissionInstanceFactory(template=self.template)
        holder, _p2 = self._setup_participants(instance)
        node = self._make_joint_node(JointCombine.ALL)
        challenge = ChallengeTemplateFactory(name="JointChallenge", severity=2)
        ChallengeApproachFactory(
            challenge_template=challenge,
            check_type=self.sneak,
            is_default=True,
        )
        opt = MissionOptionFactory(
            node=node,
            order=0,
            option_kind=OptionKind.CHECK,
            source_kind=OptionSource.CHALLENGE,
            challenge=challenge,
        )
        MissionOptionRouteFactory(option=opt, outcome_tier=self.success, target_node=self.win_node)
        MissionOptionRouteFactory(option=opt, outcome_tier=self.failure, target_node=self.lose_node)
        picks = {holder: opt, _p2: opt}
        with patch(
            _PERFORM_CHECK,
            side_effect=self._outcome_by_character(
                {self.char_h: self.success, self.char_2: self.success}
            ),
        ):
            deeds = _seed_and_resolve(instance, node, picks)
        self.assertEqual(len(deeds), 2)
        instance.refresh_from_db()
        self.assertEqual(instance.current_node, self.win_node)

    def test_joint_never_transiently_terminates_instance(self) -> None:
        # Phase-5a I-1: JOINT per-attempt resolution must be routing-free
        # (advance=False). The instance must never be touched (status,
        # current_node, completed_at) by any per-attempt write — even when
        # a participant picks an option with a TERMINAL route for their
        # rolled tier — and the combined decision is the only thing that
        # routes/terminates.
        instance = MissionInstanceFactory(template=self.template)
        holder, p2 = self._setup_participants(instance)
        node = self._make_joint_node(JointCombine.ALL)
        # Holder option: success → win_node, failure → terminal (null).
        holder_opt = MissionOptionFactory(
            node=node,
            order=0,
            option_kind=OptionKind.CHECK,
            source_kind=OptionSource.AUTHORED,
            authored_check_type=self.sneak,
        )
        MissionOptionRouteFactory(
            option=holder_opt,
            outcome_tier=self.success,
            target_node=self.win_node,
        )
        MissionOptionRouteFactory(
            option=holder_opt,
            outcome_tier=self.failure,
            target_node=None,  # TERMINAL — under advance=True this would
            # transiently complete the run mid-loop.
        )
        picks = {holder: holder_opt, p2: holder_opt}

        # Spy on the resolution helpers to confirm:
        #   * _finish_terminal is called AT MOST ONCE (the combined decision)
        #   * No per-attempt write to instance.completed_at occurs
        with (
            patch(
                _PERFORM_CHECK,
                side_effect=self._outcome_by_character(
                    {self.char_h: self.success, self.char_2: self.success}
                ),
            ),
            patch(
                "world.missions.services.multiplayer._finish_terminal",
                wraps=__import__(
                    "world.missions.services.resolution",
                    fromlist=["_finish_terminal"],
                )._finish_terminal,
            ) as term_spy,
        ):
            _seed_and_resolve(instance, node, picks)
        # ALL-success → combined success → win_node (non-terminal route);
        # finish_terminal is NOT called by the combined decision either.
        instance.refresh_from_db()
        self.assertEqual(instance.current_node, self.win_node)
        self.assertEqual(instance.status, MissionStatus.ACTIVE)
        self.assertEqual(term_spy.call_count, 0)


class GroupResolveJointTerminalRewardTests(TestCase):
    """JOINT terminal: reward emission happens ONCE (not per-attempt)."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.char_h = CharacterFactory()
        cls.char_2 = CharacterFactory()
        CharacterSheetFactory(character=cls.char_h)
        CharacterSheetFactory(character=cls.char_2)

        cls.template = MissionTemplateFactory(name="grp-joint-term-rwd", risk_tier=2)
        cls.success = CheckOutcomeFactory(name="JTermSuccess", success_level=3)
        cls.failure = CheckOutcomeFactory(name="JTermFailure", success_level=-3)
        cls.sneak = CheckTypeFactory(name="JTermSneak")

    def setUp(self) -> None:
        # SharedMemoryModel idmap hygiene: each test in this class creates
        # fresh MissionOptionRouteReward + MissionDeedRewardLine rows whose
        # PKs collide with prior tests' rows on the SQLite tier (PK
        # autoincrement resets after rollback; PG sequences don't). Without
        # a flush, ``route.reward_templates.all()`` returns stale cached
        # instances with the prior test's amount / recipient_id values.
        MissionOptionRouteReward.flush_instance_cache()
        MissionDeedRewardLine.flush_instance_cache()

    def _outcome_by_character(self, mapping: dict[object, object]) -> object:
        def _side_effect(character: object, check_type: object, **_kw: object):
            return _result_for(check_type, mapping[character])

        return _side_effect

    def test_joint_terminal_emits_rewards_once_on_holder_deed(self) -> None:
        instance = MissionInstanceFactory(template=self.template)
        holder = MissionParticipantFactory(
            instance=instance, character=self.char_h, is_contract_holder=True
        )
        p2 = MissionParticipantFactory(instance=instance, character=self.char_2)
        node = MissionNodeFactory(
            template=self.template,
            key="j-terminal",
            conflict_mode=ConflictMode.JOINT,
            joint_combine=JointCombine.ANY,
        )
        opt = MissionOptionFactory(
            node=node,
            order=0,
            option_kind=OptionKind.CHECK,
            source_kind=OptionSource.AUTHORED,
            authored_check_type=self.sneak,
        )
        # Success → terminal (target_node None) with an authored broadcast
        # reward. Failure → non-terminal lose_node.
        lose_node = MissionNodeFactory(template=self.template, key="lose")
        terminal_route = MissionOptionRouteFactory(
            option=opt, outcome_tier=self.success, target_node=None
        )
        MissionOptionRouteFactory(option=opt, outcome_tier=self.failure, target_node=lose_node)
        MissionOptionRouteRewardFactory(
            route=terminal_route,
            kind=DeedRewardKind.IMMEDIATE,
            sink=DeedRewardSink.MONEY,
            amount=420,
            contract_holder_only=False,
        )
        picks = {holder: opt, p2: opt}
        with patch(
            _PERFORM_CHECK,
            side_effect=self._outcome_by_character(
                {self.char_h: self.success, self.char_2: self.success}
            ),
        ):
            deeds = _seed_and_resolve(instance, node, picks)
        instance.refresh_from_db()
        self.assertEqual(instance.status, MissionStatus.COMPLETE)
        # Emission MUST anchor on the holder's deed, NOT any per-attempt
        # deed of a non-holder participant.
        holder_deed = next(d for d in deeds if d.actor == self.char_h)
        non_holder_deed = next(d for d in deeds if d.actor == self.char_2)
        self.assertEqual(MissionDeedRewardLine.objects.filter(deed=non_holder_deed).count(), 0)
        # Broadcast → one line per participant (2), all on the holder's deed.
        holder_lines = list(MissionDeedRewardLine.objects.filter(deed=holder_deed))
        self.assertEqual(len(holder_lines), 2)
        recipients = sorted(line.recipient_id for line in holder_lines)
        self.assertEqual(recipients, sorted([self.char_h.id, self.char_2.id]))
        for line in holder_lines:
            self.assertEqual(line.amount, 420)

    def test_joint_non_terminal_combined_emits_no_reward_lines(self) -> None:
        # JOINT combined result routes to a non-terminal node → NO rewards
        # are emitted, even if the holder's option's terminal route HAS
        # reward templates (those fire only when the combined result lands
        # on that terminal route).
        instance = MissionInstanceFactory(template=self.template)
        holder = MissionParticipantFactory(
            instance=instance, character=self.char_h, is_contract_holder=True
        )
        p2 = MissionParticipantFactory(instance=instance, character=self.char_2)
        node = MissionNodeFactory(
            template=self.template,
            key="j-non-terminal",
            conflict_mode=ConflictMode.JOINT,
            joint_combine=JointCombine.ALL,
        )
        opt = MissionOptionFactory(
            node=node,
            order=0,
            option_kind=OptionKind.CHECK,
            source_kind=OptionSource.AUTHORED,
            authored_check_type=self.sneak,
        )
        lose_node = MissionNodeFactory(template=self.template, key="lose")
        terminal_route = MissionOptionRouteFactory(
            option=opt, outcome_tier=self.success, target_node=None
        )
        MissionOptionRouteFactory(option=opt, outcome_tier=self.failure, target_node=lose_node)
        # Authored reward on the (unused-this-time) terminal route.
        MissionOptionRouteRewardFactory(
            route=terminal_route,
            kind=DeedRewardKind.IMMEDIATE,
            sink=DeedRewardSink.MONEY,
            amount=999,
        )
        picks = {holder: opt, p2: opt}
        # ALL with one failure → combined failure → lose_node (non-terminal)
        with patch(
            _PERFORM_CHECK,
            side_effect=self._outcome_by_character(
                {self.char_h: self.success, self.char_2: self.failure}
            ),
        ):
            deeds = _seed_and_resolve(instance, node, picks)
        # Sanity reference holds for later; for clarity also assert there
        # are exactly two deeds (one per participant).
        self.assertEqual(len(deeds), 2)
        instance.refresh_from_db()
        self.assertEqual(instance.current_node, lose_node)
        self.assertEqual(instance.status, MissionStatus.ACTIVE)
        # No reward lines emitted anywhere.
        deed_pks = [d.pk for d in deeds]
        self.assertEqual(MissionDeedRewardLine.objects.filter(deed_id__in=deed_pks).count(), 0)

    def test_joint_per_attempt_does_not_emit_rewards(self) -> None:
        # Defensive: per-attempt resolve_option calls use advance=False, so
        # no per-attempt deed should ever carry reward lines, regardless of
        # whether the participant's rolled outcome maps to a terminal route
        # on their option's own route-set. The single combined decision is
        # the ONLY emission point.
        instance = MissionInstanceFactory(template=self.template)
        holder = MissionParticipantFactory(
            instance=instance, character=self.char_h, is_contract_holder=True
        )
        p2 = MissionParticipantFactory(instance=instance, character=self.char_2)
        node = MissionNodeFactory(
            template=self.template,
            key="j-per-attempt-guard",
            conflict_mode=ConflictMode.JOINT,
            joint_combine=JointCombine.ALL,
        )
        opt = MissionOptionFactory(
            node=node,
            order=0,
            option_kind=OptionKind.CHECK,
            source_kind=OptionSource.AUTHORED,
            authored_check_type=self.sneak,
        )
        # Holder option: success → terminal, failure → terminal. So if
        # advance=False were NOT honored, each per-attempt resolve_option
        # would have emitted rewards on its per-attempt deed.
        success_route = MissionOptionRouteFactory(
            option=opt, outcome_tier=self.success, target_node=None
        )
        failure_route = MissionOptionRouteFactory(
            option=opt, outcome_tier=self.failure, target_node=None
        )
        MissionOptionRouteRewardFactory(
            route=success_route,
            kind=DeedRewardKind.IMMEDIATE,
            sink=DeedRewardSink.MONEY,
            amount=100,
        )
        MissionOptionRouteRewardFactory(
            route=failure_route,
            kind=DeedRewardKind.IMMEDIATE,
            sink=DeedRewardSink.MONEY,
            amount=50,
        )
        picks = {holder: opt, p2: opt}
        # ALL with one success + one failure → combined failure → terminal
        # via failure_route. Combined decision emits ONE set of rewards.
        with patch(
            _PERFORM_CHECK,
            side_effect=self._outcome_by_character(
                {self.char_h: self.success, self.char_2: self.failure}
            ),
        ):
            deeds = _seed_and_resolve(instance, node, picks)
        instance.refresh_from_db()
        self.assertEqual(instance.status, MissionStatus.COMPLETE)
        holder_deed = next(d for d in deeds if d.actor == self.char_h)
        non_holder_deed = next(d for d in deeds if d.actor == self.char_2)
        self.assertEqual(MissionDeedRewardLine.objects.filter(deed=non_holder_deed).count(), 0)
        holder_lines = list(MissionDeedRewardLine.objects.filter(deed=holder_deed))
        # Combined failure → failure_route emits per ALL_EQUAL (2 participants).
        self.assertEqual(len(holder_lines), 2)
        for line in holder_lines:
            self.assertEqual(line.amount, 50)


class GroupOptionListLocationTests(TestCase):
    """#887: build_group_option_list applies the location conjunct per participant."""

    @staticmethod
    def _room(name):
        room = ObjectDBFactory(db_key=name, db_typeclass_path="typeclasses.rooms.Room")
        profile = RoomProfileFactory(objectdb=room)
        return room, profile

    @staticmethod
    def _pc_in(room):
        character = CharacterFactory()
        CharacterSheetFactory(character=character)
        if room is not None:
            character.db_location = room
            character.save(update_fields=["db_location"])
        return character

    def _group_with_option(self, location_mode, *, node_room_profile=None):
        template = MissionTemplateFactory(name=f"grp-loc-{location_mode}")
        node = MissionNodeFactory(
            template=template, key="entry", is_entry=True, location_mode=location_mode
        )
        if node_room_profile is not None:
            node.locations.add(node_room_profile)
        option = MissionOptionFactory(
            node=node,
            order=0,
            option_kind=OptionKind.BRANCH,
            source_kind=OptionSource.AUTHORED,
            authored_ic_framing="A located deed",
        )
        instance = MissionInstanceFactory(template=template)
        return template, node, option, instance

    def test_rooms_node_surfaces_option_only_to_participants_in_that_room(self):
        room_a, profile_a = self._room("Throne Room")
        room_b, _ = self._room("Cellar")
        char_a = self._pc_in(room_a)
        char_b = self._pc_in(room_b)
        _t, node, option, instance = self._group_with_option(
            NodeLocationMode.ROOMS, node_room_profile=profile_a
        )
        MissionParticipantFactory(instance=instance, character=char_a, is_contract_holder=True)
        MissionParticipantFactory(instance=instance, character=char_b)

        presented = build_group_option_list(instance, node)
        owners = {entry.owner for entry in presented if entry.option == option}
        # Only the participant standing in room_a (the node's live room) sees it.
        self.assertEqual(owners, {char_a})

    def test_anywhere_node_surfaces_option_to_all_regardless_of_room(self):
        room_a, _ = self._room("Hall")
        char_a = self._pc_in(room_a)
        char_b = self._pc_in(None)  # placeless
        _t, node, option, instance = self._group_with_option(NodeLocationMode.ANYWHERE)
        MissionParticipantFactory(instance=instance, character=char_a, is_contract_holder=True)
        MissionParticipantFactory(instance=instance, character=char_b)

        presented = build_group_option_list(instance, node)
        owners = {entry.owner for entry in presented if entry.option == option}
        self.assertEqual(owners, {char_a, char_b})


class ResolveGroupNodePauseGateTests(TestCase):
    """The pause gate (#1899) is the first line of ``resolve_group_node`` —
    both the lazy on-access path and the cron backstop sweep call into this
    single function, so gating here covers both callers.
    """

    def test_paused_instance_returns_empty_list(self) -> None:
        instance = MissionInstanceFactory(is_paused=True)
        node = MissionNodeFactory()

        result = resolve_group_node(instance, node)

        assert result == []

    def test_unpaused_instance_with_no_ballots_returns_empty_list(self) -> None:
        """Baseline: confirms the pause check doesn't break the pre-existing
        no-ballots-means-nothing-to-resolve behavior."""
        instance = MissionInstanceFactory(is_paused=False)
        node = MissionNodeFactory()

        result = resolve_group_node(instance, node)

        assert result == []


class _PausableJointNodeMixin:
    """Builds a JOINT node whose single-participant pick WOULD fully resolve
    (CHECK option + outcome-tier route + patched perform_check) when unpaused.

    Deviation from the task-10 brief's literal snippet: the brief's
    ``MissionOptionFactory(node=node)`` default (a BRANCH/AUTHORED option with
    no routes) can never reach ``_combined_route`` successfully under JOINT —
    it raises ``ValueError`` ("route-set incompleteness") before the pause
    gate is even relevant, which would make the failing-test step fail for
    the wrong reason and the passing-test step trivially/coincidentally
    "pass" without the gate doing any work. This mixin gives JOINT a resolvable
    CHECK option + route so the *only* thing standing between "ballot intact"
    and "ballot resolved+deleted" is the pause gate itself.
    """

    def _build_pausable_joint_fixture(self, *, is_paused: bool):
        template = MissionTemplateFactory(name=f"pause-gate-{is_paused}")
        success = CheckOutcomeFactory(name=f"PauseGateSuccess-{is_paused}", success_level=3)
        check_type = CheckTypeFactory(name=f"PauseGateCheck-{is_paused}")
        win_node = MissionNodeFactory(template=template, key="win")
        node = MissionNodeFactory(
            template=template,
            key="joint",
            conflict_mode=ConflictMode.JOINT,
            joint_combine=JointCombine.ANY,
        )
        option = MissionOptionFactory(
            node=node,
            option_kind=OptionKind.CHECK,
            source_kind=OptionSource.AUTHORED,
            authored_check_type=check_type,
        )
        MissionOptionRouteFactory(option=option, outcome_tier=success, target_node=win_node)
        instance = MissionInstanceFactory(template=template, is_paused=is_paused)
        participant = MissionParticipantFactory(instance=instance, is_contract_holder=True)
        ballot = MissionGroupBallot.objects.create(
            instance=instance, node=node, participant=participant, picked_option=option
        )
        return instance, node, ballot, success


class ResolveGroupIfReadyPauseGateTests(TestCase, _PausableJointNodeMixin):
    def test_paused_instance_never_resolves_via_unanimity_path(self) -> None:
        from world.missions.services.play import _resolve_group_if_ready

        instance, node, ballot, success = self._build_pausable_joint_fixture(is_paused=True)

        with patch(_PERFORM_CHECK, return_value=_result_for(None, success)):
            result = _resolve_group_if_ready(instance, node)

        # Every participant has picked (JOINT "unanimity"), so absent the pause
        # gate this would resolve via ``resolve_group_node`` and return deeds.
        # Regression (#1899 whole-branch review): ``_resolve_group_if_ready``
        # must short-circuit to ``None`` — the "not ready yet" sentinel every
        # play-surface caller (group_beat/submit_group_pick/cast_group_vote)
        # relies on — BEFORE ever calling ``resolve_group_node``. Previously
        # this returned resolve_group_node's own ``[]`` pause sentinel, which
        # is ``not None`` and so every caller wrongly reported the beat as
        # resolved. The ballot must also survive untouched either way.
        assert result is None
        assert MissionGroupBallot.objects.filter(pk=ballot.pk).exists()  # not resolved/deleted


class ResolveExpiredGroupVotesPauseGateTests(TestCase, _PausableJointNodeMixin):
    def test_paused_instance_not_resolved_by_cron_sweep(self) -> None:
        """Regression (#1899 spec review): the cron sweep bypasses
        _resolve_group_if_ready entirely and calls resolve_group_node
        directly — must be covered by the same gate."""
        from datetime import timedelta

        from django.utils import timezone

        from world.missions.constants import GROUP_VOTE_TIMEOUT_SECONDS
        from world.missions.services.cron import resolve_expired_group_votes

        instance, node, ballot, success = self._build_pausable_joint_fixture(is_paused=True)
        instance.current_node = node
        instance.save(update_fields=["current_node"])
        ballot.created_at = timezone.now() - timedelta(seconds=GROUP_VOTE_TIMEOUT_SECONDS + 60)
        ballot.save(update_fields=["created_at"])

        with patch(_PERFORM_CHECK, return_value=_result_for(None, success)):
            resolve_expired_group_votes()

        assert MissionGroupBallot.objects.filter(pk=ballot.pk).exists()  # not resolved/deleted
