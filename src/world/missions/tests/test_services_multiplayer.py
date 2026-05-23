"""Tests for the Phase-4 multi-person orchestrator.

Covers:
  * Task 4.1 ``build_group_option_list`` — owner-tagged union across all
    participants; AUTHORED visibility scoped per participant.
  * Task 4.2 ``select_group_choice`` — COINFLIP / VOTE / JOINT decisions.
  * Task 4.3 ``group_resolve_node`` — actor attribution (moral consequence
    follows the actor), JOINT per-participant deeds + single combined
    routing, ``contract_holder``.

Real factory objects, no ORM mocks. ``force_check_outcome`` pins rolled
outcome tiers deterministically; COINFLIP uses the codebase RNG
convention (``random.choice``) so its test asserts "one of the distinct
picks" rather than a fixed value.
"""

from unittest.mock import patch

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory
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
from world.missions.models import MissionDeedRewardLine, MissionOptionRouteReward
from world.missions.services import (
    build_group_option_list,
    build_option_list,
    contract_holder,
    group_resolve_node,
    select_group_choice,
)
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


class BuildGroupOptionListTests(TestCase):
    """Union across participants; owner-tagged; AUTHORED scoped per viewer."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.char_a = CharacterFactory()
        cls.char_b = CharacterFactory()
        CharacterSheetFactory(character=cls.char_a)
        CharacterSheetFactory(character=cls.char_b)

        cls.template = MissionTemplateFactory(slug="grp-opt-tmpl")
        cls.instance = MissionInstanceFactory(template=cls.template)
        cls.node = MissionNodeFactory(template=cls.template, key="entry", is_entry=True)
        cls.p_a = MissionParticipantFactory(
            instance=cls.instance, character=cls.char_a, is_contract_holder=True
        )
        cls.p_b = MissionParticipantFactory(instance=cls.instance, character=cls.char_b)

        # A owns dist_a, B owns dist_b (disjoint).
        cls.dist_a = DistinctionFactory(slug="grp-dist-a")
        cls.dist_b = DistinctionFactory(slug="grp-dist-b")
        CharacterDistinctionFactory(character=cls.char_a, distinction=cls.dist_a)
        CharacterDistinctionFactory(character=cls.char_b, distinction=cls.dist_b)

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


class SelectGroupChoiceTests(TestCase):
    """COINFLIP / VOTE / JOINT decision logic."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.template = MissionTemplateFactory(slug="sgc-tmpl")
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

    def _coinflip_node(self) -> object:
        self.node.conflict_mode = ConflictMode.COINFLIP
        self.node.save()
        return self.node

    def _vote_node(self) -> object:
        self.node.conflict_mode = ConflictMode.VOTE
        self.node.save()
        return self.node

    def _joint_node(self) -> object:
        self.node.conflict_mode = ConflictMode.JOINT
        self.node.joint_combine = JointCombine.ANY
        self.node.save()
        return self.node

    def test_coinflip_all_same_pick_is_that_option(self) -> None:
        node = self._coinflip_node()
        picks = {self.holder: self.opt1, self.p2: self.opt1}
        gc = select_group_choice(node, picks)
        self.assertFalse(gc.is_joint)
        self.assertEqual(gc.option, self.opt1)
        # Deterministic actor tiebreak: lowest-pk picker of the winner.
        self.assertEqual(gc.actor, self.holder)

    def test_coinflip_distinct_picks_returns_one_of_them(self) -> None:
        node = self._coinflip_node()
        picks = {self.holder: self.opt1, self.p2: self.opt2}
        gc = select_group_choice(node, picks)
        self.assertFalse(gc.is_joint)
        self.assertIn(gc.option, {self.opt1, self.opt2})
        # Actor must be a participant who picked the winning option.
        self.assertEqual(picks[gc.actor], gc.option)

    def test_vote_plurality_winner(self) -> None:
        node = self._vote_node()
        picks = {self.holder: self.opt1, self.p2: self.opt1, self.p3: self.opt2}
        gc = select_group_choice(node, picks)
        self.assertEqual(gc.option, self.opt1)

    def test_vote_tie_broken_by_contract_holder_pick(self) -> None:
        node = self._vote_node()
        # 1-1 tie; holder picked opt2 → opt2 wins, holder is actor.
        picks = {self.holder: self.opt2, self.p2: self.opt1}
        gc = select_group_choice(node, picks)
        self.assertEqual(gc.option, self.opt2)
        self.assertEqual(gc.actor, self.holder)

    def test_vote_tie_no_holder_in_tie_lowest_option_pk(self) -> None:
        node = self._vote_node()
        # Holder absent from picks; 1-1 tie between opt1/opt2 →
        # lowest option pk (opt1 created first).
        picks = {self.p2: self.opt1, self.p3: self.opt2}
        gc = select_group_choice(node, picks)
        self.assertEqual(gc.option, self.opt1)
        self.assertEqual(gc.actor, self.p2)

    def test_joint_carries_all_attempts(self) -> None:
        node = self._joint_node()
        picks = {self.holder: self.opt1, self.p2: self.opt2}
        gc = select_group_choice(node, picks)
        self.assertTrue(gc.is_joint)
        self.assertIsNone(gc.option)
        self.assertIsNone(gc.actor)
        self.assertEqual(
            {(p, o) for p, o in gc.attempts},
            {(self.holder, self.opt1), (self.p2, self.opt2)},
        )


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

        cls.template = MissionTemplateFactory(slug="grp-cv-tmpl", risk_tier=2)
        cls.instance = MissionInstanceFactory(template=cls.template)
        cls.entry = MissionNodeFactory(
            template=cls.template,
            key="entry",
            is_entry=True,
            conflict_mode=ConflictMode.VOTE,
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
            deeds = group_resolve_node(self.instance, self.entry, picks)
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

        cls.template = MissionTemplateFactory(slug="grp-joint-tmpl", risk_tier=2)
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
            deeds = group_resolve_node(instance, node, picks)
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
            deeds = group_resolve_node(instance, node, picks)
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
            group_resolve_node(instance, node, picks)
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
            deeds = group_resolve_node(instance, node, picks)
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
            group_resolve_node(instance, node, picks)
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
            group_resolve_node(instance, node, picks)
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
            deeds = group_resolve_node(instance, node, picks)
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
            group_resolve_node(instance, node, picks)
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

        cls.template = MissionTemplateFactory(slug="grp-joint-term-rwd", risk_tier=2)
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
            deeds = group_resolve_node(instance, node, picks)
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
            deeds = group_resolve_node(instance, node, picks)
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
            deeds = group_resolve_node(instance, node, picks)
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
