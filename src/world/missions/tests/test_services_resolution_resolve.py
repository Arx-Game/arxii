"""Tests for ``resolve_option``.

CHECK options roll a check (AUTHORED difficulty = template.risk_tier;
CHALLENGE difficulty = the challenge's severity), match the route for the
rolled outcome tier, apply the route consequence (authored or synthetic
fallback), then route or complete. BRANCH options skip the check entirely.
Terminal routes (null destination) complete the run WITHOUT emitting any
reward lines.

Real factory objects, no ORM mocks. ``force_check_outcome`` pins the rolled
outcome tier deterministically. ``apply_resolution`` (the reuse boundary) is
spied to assert the consequence composition without wiring the full
ConsequenceEffect machinery.
"""

from unittest.mock import patch

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import CheckTypeFactory, ConsequenceFactory
from world.checks.test_helpers import force_check_outcome
from world.mechanics.factories import ChallengeApproachFactory, ChallengeTemplateFactory
from world.missions.constants import (
    DeedRewardKind,
    DeedRewardSink,
    MissionStatus,
    OptionKind,
    OptionSource,
)
from world.missions.factories import (
    MissionDeedRewardLineFactory,
    MissionInstanceFactory,
    MissionNodeFactory,
    MissionOptionFactory,
    MissionOptionRouteCandidateFactory,
    MissionOptionRouteFactory,
    MissionOptionRouteRewardFactory,
    MissionParticipantFactory,
    MissionTemplateFactory,
)
from world.missions.models import (
    MissionDeedRecord,
    MissionDeedRewardLine,
    MissionOptionRouteReward,
)
from world.missions.services import resolve_option
from world.traits.factories import CheckOutcomeFactory

_APPLY = "world.missions.services.resolution.apply_resolution"


class ResolveCheckOptionTests(TestCase):
    """CHECK routing, consequence fallback, random sets."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.character = CharacterFactory()
        cls.sheet = CharacterSheetFactory(character=cls.character)

        cls.template = MissionTemplateFactory(name="resolve-tmpl", risk_tier=4)
        cls.instance = MissionInstanceFactory(template=cls.template)
        cls.entry = MissionNodeFactory(template=cls.template, key="entry", is_entry=True)
        cls.node_a = MissionNodeFactory(template=cls.template, key="a")
        cls.node_b = MissionNodeFactory(template=cls.template, key="b")
        cls.actor = MissionParticipantFactory(
            instance=cls.instance,
            character=cls.character,
            is_contract_holder=True,
        )

        cls.success = CheckOutcomeFactory(name="Success", success_level=3)
        cls.failure = CheckOutcomeFactory(name="Failure", success_level=-3)
        cls.sneak = CheckTypeFactory(name="ResolveSneak")

        cls.check_option = MissionOptionFactory(
            node=cls.entry,
            order=0,
            option_kind=OptionKind.CHECK,
            source_kind=OptionSource.AUTHORED,
            authored_check_type=cls.sneak,
        )
        cls.success_conseq = ConsequenceFactory(outcome_tier=cls.success)
        cls.success_route = MissionOptionRouteFactory(
            option=cls.check_option,
            outcome_tier=cls.success,
            target_node=cls.node_a,
            consequence=cls.success_conseq,
        )
        # Fail route carries NO consequence → synthetic fallback path.
        cls.fail_route = MissionOptionRouteFactory(
            option=cls.check_option,
            outcome_tier=cls.failure,
            target_node=cls.node_b,
        )

    def test_success_routes_to_a_and_emits_deed(self) -> None:
        with force_check_outcome(self.success), patch(_APPLY) as mocked:
            deed = resolve_option(self.instance, self.entry, self.check_option, self.actor)
        self.instance.refresh_from_db()
        self.assertEqual(self.instance.current_node, self.node_a)
        self.assertEqual(deed.outcome, self.success)
        self.assertEqual(deed.actor, self.character)
        # Authored consequence applied (exactly one call).
        self.assertEqual(mocked.call_count, 1)
        pending = mocked.call_args_list[0].args[0]
        self.assertEqual(pending.selected_consequence, self.success_conseq)

    def test_fail_routes_to_b_with_synthetic_fallback(self) -> None:
        with force_check_outcome(self.failure), patch(_APPLY) as mocked:
            deed = resolve_option(self.instance, self.entry, self.check_option, self.actor)
        self.instance.refresh_from_db()
        self.assertEqual(self.instance.current_node, self.node_b)
        self.assertEqual(deed.outcome, self.failure)
        # Synthetic fallback consequence: unsaved (pk is None), tier = rolled.
        pending = mocked.call_args_list[0].args[0]
        self.assertIsNone(pending.selected_consequence.pk)
        self.assertEqual(pending.selected_consequence.outcome_tier, self.failure)

    def test_synthetic_fallback_does_not_crash_and_emits_deed(self) -> None:
        # No mock here: apply_resolution must genuinely no-op on the unsaved
        # fallback (returns []) and the deed must still be emitted.
        with force_check_outcome(self.failure):
            deed = resolve_option(self.instance, self.entry, self.check_option, self.actor)
        self.assertTrue(MissionDeedRecord.objects.filter(pk=deed.pk).exists())

    def test_random_set_route_picks_a_candidate(self) -> None:
        rand_outcome = CheckOutcomeFactory(name="Partial", success_level=1)
        rand_route = MissionOptionRouteFactory(
            option=self.check_option,
            outcome_tier=rand_outcome,
            target_node=None,
            is_random_set=True,
        )
        MissionOptionRouteCandidateFactory(route=rand_route, target_node=self.node_a, weight=1)
        MissionOptionRouteCandidateFactory(route=rand_route, target_node=self.node_b, weight=1)
        with force_check_outcome(rand_outcome):
            resolve_option(self.instance, self.entry, self.check_option, self.actor)
        self.instance.refresh_from_db()
        self.assertIn(self.instance.current_node, {self.node_a, self.node_b})

    def test_deed_actor_is_acting_participants_character(self) -> None:
        with force_check_outcome(self.success):
            deed = resolve_option(self.instance, self.entry, self.check_option, self.actor)
        self.assertEqual(deed.actor, self.actor.character)


class ResolveChallengeOptionTests(TestCase):
    """CHALLENGE option: approach check (or auto-success) → route on outcome.

    Routes live on the CHALLENGE MissionOption and are keyed by outcome
    tier, shared across the challenge's approaches. The chosen approach
    supplies the check type; an auto_succeeds approach skips the roll and
    lands in the top tier.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        cls.character = CharacterFactory()
        cls.sheet = CharacterSheetFactory(character=cls.character)
        cls.template = MissionTemplateFactory(name="ch-resolve-tmpl", risk_tier=4)
        cls.instance = MissionInstanceFactory(template=cls.template)
        cls.entry = MissionNodeFactory(template=cls.template, key="entry", is_entry=True)
        cls.node_a = MissionNodeFactory(template=cls.template, key="a")
        cls.node_b = MissionNodeFactory(template=cls.template, key="b")
        cls.actor = MissionParticipantFactory(
            instance=cls.instance,
            character=cls.character,
            is_contract_holder=True,
        )
        cls.top = CheckOutcomeFactory(name="ChResolveCritical", success_level=5)
        cls.failure = CheckOutcomeFactory(name="ChResolveFailure", success_level=-3)

        cls.challenge = ChallengeTemplateFactory(name="ChResolve Pit", severity=7)
        cls.normal_approach = ChallengeApproachFactory(
            challenge_template=cls.challenge,
            check_type=CheckTypeFactory(name="ChResolveClimb"),
            is_default=True,
        )
        cls.auto_approach = ChallengeApproachFactory(
            challenge_template=cls.challenge,
            check_type=CheckTypeFactory(name="ChResolveFly"),
            auto_succeeds=True,
            is_default=True,
        )
        cls.option = MissionOptionFactory(
            node=cls.entry,
            order=0,
            option_kind=OptionKind.CHECK,
            source_kind=OptionSource.CHALLENGE,
            challenge=cls.challenge,
        )
        # Routes on the CHALLENGE option, keyed by outcome tier — shared by
        # every approach the challenge defines.
        cls.top_route = MissionOptionRouteFactory(
            option=cls.option,
            outcome_tier=cls.top,
            target_node=cls.node_a,
        )
        cls.fail_route = MissionOptionRouteFactory(
            option=cls.option,
            outcome_tier=cls.failure,
            target_node=cls.node_b,
        )

    def test_normal_approach_rolls_and_routes_on_outcome(self) -> None:
        with force_check_outcome(self.failure):
            deed = resolve_option(
                self.instance,
                self.entry,
                self.option,
                self.actor,
                chosen_approach=self.normal_approach,
            )
        self.instance.refresh_from_db()
        self.assertEqual(self.instance.current_node, self.node_b)
        self.assertEqual(deed.outcome, self.failure)

    def test_auto_success_approach_skips_roll_and_lands_top_tier(self) -> None:
        with patch("world.missions.services.resolution.perform_check") as pc:
            deed = resolve_option(
                self.instance,
                self.entry,
                self.option,
                self.actor,
                chosen_approach=self.auto_approach,
            )
        pc.assert_not_called()
        self.instance.refresh_from_db()
        self.assertEqual(self.instance.current_node, self.node_a)
        self.assertEqual(deed.outcome, self.top)

    def test_challenge_option_without_chosen_approach_raises(self) -> None:
        with self.assertRaises(ValueError):
            resolve_option(self.instance, self.entry, self.option, self.actor)

    def test_two_approaches_share_routes_by_outcome_tier(self) -> None:
        # Two distinct non-auto approaches on the same CHALLENGE option,
        # both forced to the failure tier, route through the SAME
        # MissionOptionRoute keyed on that tier — routes hang off the
        # MissionOption (not per-approach), so the rolled outcome is the
        # only thing that picks the route.
        other_approach = ChallengeApproachFactory(
            challenge_template=self.challenge,
            check_type=CheckTypeFactory(name="ChResolveScramble"),
            is_default=True,
        )
        inst_1 = MissionInstanceFactory(template=self.template, current_node=self.entry)
        actor_1 = MissionParticipantFactory(
            instance=inst_1, character=self.character, is_contract_holder=True
        )
        char_2 = CharacterFactory()
        CharacterSheetFactory(character=char_2)
        inst_2 = MissionInstanceFactory(template=self.template, current_node=self.entry)
        actor_2 = MissionParticipantFactory(
            instance=inst_2, character=char_2, is_contract_holder=True
        )

        with force_check_outcome(self.failure):
            resolve_option(
                inst_1,
                self.entry,
                self.option,
                actor_1,
                chosen_approach=self.normal_approach,
            )
        with force_check_outcome(self.failure):
            resolve_option(
                inst_2,
                self.entry,
                self.option,
                actor_2,
                chosen_approach=other_approach,
            )

        inst_1.refresh_from_db()
        inst_2.refresh_from_db()
        # Both used the same fail_route → both landed at node_b.
        self.assertEqual(inst_1.current_node, self.node_b)
        self.assertEqual(inst_2.current_node, self.node_b)


class AutoSuccessNoOutcomeTiersTest(TestCase):
    """An auto_succeeds approach raises when no CheckOutcome rows exist."""

    def test_raises_when_no_outcome_tiers(self) -> None:
        character = CharacterFactory()
        CharacterSheetFactory(character=character)
        template = MissionTemplateFactory(name="no-outcomes-tmpl", risk_tier=1)
        instance = MissionInstanceFactory(template=template)
        entry = MissionNodeFactory(template=template, key="entry", is_entry=True)
        actor = MissionParticipantFactory(
            instance=instance, character=character, is_contract_holder=True
        )
        challenge = ChallengeTemplateFactory(name="AutoSuccessNoOutcomes")
        approach = ChallengeApproachFactory(
            challenge_template=challenge,
            check_type=CheckTypeFactory(name="AutoSuccessNoOutcomesCheck"),
            auto_succeeds=True,
            is_default=True,
        )
        option = MissionOptionFactory(
            node=entry,
            order=0,
            option_kind=OptionKind.CHECK,
            source_kind=OptionSource.CHALLENGE,
            challenge=challenge,
        )
        # No CheckOutcome rows created in this class's setup.
        with self.assertRaises(ValueError):
            resolve_option(instance, entry, option, actor, chosen_approach=approach)


class ResolveBranchOptionTests(TestCase):
    """BRANCH path: no check, deed outcome None, routes via branch_target."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.template = MissionTemplateFactory(name="branch-tmpl")
        cls.instance = MissionInstanceFactory(template=cls.template)
        cls.entry = MissionNodeFactory(template=cls.template, key="entry", is_entry=True)
        cls.target = MissionNodeFactory(template=cls.template, key="target")
        cls.actor = MissionParticipantFactory(
            instance=cls.instance,
            character=CharacterFactory(),
            is_contract_holder=True,
        )

    def test_branch_routes_to_target_and_outcome_is_none(self) -> None:
        option = MissionOptionFactory(
            node=self.entry,
            order=0,
            option_kind=OptionKind.BRANCH,
            source_kind=OptionSource.AUTHORED,
            branch_target=self.target,
        )
        with patch("world.missions.services.resolution.perform_check") as pc:
            deed = resolve_option(self.instance, self.entry, option, self.actor)
        pc.assert_not_called()
        self.instance.refresh_from_db()
        self.assertEqual(self.instance.current_node, self.target)
        self.assertIsNone(deed.outcome)

    def test_branch_via_null_tier_route(self) -> None:
        option = MissionOptionFactory(
            node=self.entry,
            order=1,
            option_kind=OptionKind.BRANCH,
            source_kind=OptionSource.AUTHORED,
        )
        MissionOptionRouteFactory(option=option, outcome_tier=None, target_node=self.target)
        deed = resolve_option(self.instance, self.entry, option, self.actor)
        self.instance.refresh_from_db()
        self.assertEqual(self.instance.current_node, self.target)
        self.assertIsNone(deed.outcome)


class TerminalCompletionTests(TestCase):
    """Terminal route → COMPLETE, completed_at set, NO reward lines."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.character = CharacterFactory()
        cls.sheet = CharacterSheetFactory(character=cls.character)
        cls.template = MissionTemplateFactory(name="terminal-tmpl", risk_tier=2)
        cls.instance = MissionInstanceFactory(template=cls.template)
        cls.entry = MissionNodeFactory(template=cls.template, key="entry", is_entry=True)
        cls.actor = MissionParticipantFactory(
            instance=cls.instance,
            character=cls.character,
            is_contract_holder=True,
        )
        cls.success = CheckOutcomeFactory(name="TermSuccess", success_level=3)
        cls.sneak = CheckTypeFactory(name="TermSneak")

    def test_branch_terminal_completes_with_zero_reward_lines(self) -> None:
        option = MissionOptionFactory(
            node=self.entry,
            order=0,
            option_kind=OptionKind.BRANCH,
            source_kind=OptionSource.AUTHORED,
        )
        # No branch_target, no route → terminal.
        deed = resolve_option(self.instance, self.entry, option, self.actor)
        self.instance.refresh_from_db()
        self.assertEqual(self.instance.status, MissionStatus.COMPLETE)
        self.assertIsNotNone(self.instance.completed_at)
        self.assertIsNone(self.instance.current_node)
        self.assertTrue(MissionDeedRecord.objects.filter(pk=deed.pk).exists())
        self.assertEqual(MissionDeedRewardLine.objects.filter(deed=deed).count(), 0)

    def test_check_terminal_route_completes_run(self) -> None:
        option = MissionOptionFactory(
            node=self.entry,
            order=1,
            option_kind=OptionKind.CHECK,
            source_kind=OptionSource.AUTHORED,
            authored_check_type=self.sneak,
        )
        MissionOptionRouteFactory(
            option=option,
            outcome_tier=self.success,
            target_node=None,  # terminal
        )
        with force_check_outcome(self.success):
            deed = resolve_option(self.instance, self.entry, option, self.actor)
        self.instance.refresh_from_db()
        self.assertEqual(self.instance.status, MissionStatus.COMPLETE)
        self.assertIsNotNone(self.instance.completed_at)
        self.assertIsNone(self.instance.current_node)
        self.assertEqual(deed.outcome, self.success)
        self.assertEqual(MissionDeedRewardLine.objects.filter(deed=deed).count(), 0)

    def test_engine_emits_no_lines_when_no_reward_templates(self) -> None:
        # Phase 5b.0: terminal routes WITHOUT authored
        # MissionOptionRouteReward rows still emit zero reward lines.
        # Authoring is opt-in per route; an unrewarded terminal is valid.
        option = MissionOptionFactory(
            node=self.entry,
            order=2,
            option_kind=OptionKind.BRANCH,
            source_kind=OptionSource.AUTHORED,
        )
        deed = resolve_option(self.instance, self.entry, option, self.actor)
        # Manually attaching one still works, but the engine itself created
        # none (the route has no authored reward templates).
        self.assertEqual(MissionDeedRewardLine.objects.filter(deed=deed).count(), 0)
        MissionDeedRewardLineFactory(deed=deed)
        self.assertEqual(MissionDeedRewardLine.objects.filter(deed=deed).count(), 1)


class TerminalRewardEmissionTests(TestCase):
    """Phase 5b.0: terminal routes emit MissionDeedRewardLine rows from
    authored MissionOptionRouteReward templates on the route."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.character = CharacterFactory()
        cls.sheet = CharacterSheetFactory(character=cls.character)
        cls.template = MissionTemplateFactory(name="emit-int-tmpl", risk_tier=2)
        cls.instance = MissionInstanceFactory(template=cls.template)
        cls.entry = MissionNodeFactory(template=cls.template, key="entry", is_entry=True)
        cls.actor = MissionParticipantFactory(
            instance=cls.instance,
            character=cls.character,
            is_contract_holder=True,
        )
        cls.success = CheckOutcomeFactory(name="EmitIntSuccess", success_level=3)
        cls.sneak = CheckTypeFactory(name="EmitIntSneak")

    def setUp(self) -> None:
        # SharedMemoryModel idmap hygiene: each test in this class creates
        # fresh MissionOptionRouteReward rows whose PKs collide with prior
        # tests' rows on the SQLite tier (PK autoincrement resets after
        # rollback; PG sequences don't). Without a flush,
        # ``route.reward_templates.all()`` returns stale cached instances
        # with the prior test's amount value.
        MissionOptionRouteReward.flush_instance_cache()
        MissionDeedRewardLine.flush_instance_cache()

    def test_check_terminal_route_emits_authored_reward_line(self) -> None:
        option = MissionOptionFactory(
            node=self.entry,
            order=0,
            option_kind=OptionKind.CHECK,
            source_kind=OptionSource.AUTHORED,
            authored_check_type=self.sneak,
        )
        terminal_route = MissionOptionRouteFactory(
            option=option,
            outcome_tier=self.success,
            target_node=None,  # terminal
        )
        MissionOptionRouteRewardFactory(
            route=terminal_route,
            kind=DeedRewardKind.IMMEDIATE,
            sink=DeedRewardSink.MONEY,
            amount=750,
            contract_holder_only=False,
        )
        with force_check_outcome(self.success):
            deed = resolve_option(self.instance, self.entry, option, self.actor)
        self.instance.refresh_from_db()
        self.assertEqual(self.instance.status, MissionStatus.COMPLETE)
        lines = list(MissionDeedRewardLine.objects.filter(deed=deed))
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0].amount, 750)
        self.assertEqual(lines[0].recipient, self.character)

    def test_branch_terminal_via_null_route_emits_authored_rewards(self) -> None:
        option = MissionOptionFactory(
            node=self.entry,
            order=1,
            option_kind=OptionKind.BRANCH,
            source_kind=OptionSource.AUTHORED,
        )
        # BRANCH terminal authored via a null-tier route with reward templates.
        terminal_route = MissionOptionRouteFactory(
            option=option,
            outcome_tier=None,
            target_node=None,
        )
        MissionOptionRouteRewardFactory(
            route=terminal_route,
            kind=DeedRewardKind.IMMEDIATE,
            sink=DeedRewardSink.MONEY,
            amount=200,
            contract_holder_only=True,
        )
        deed = resolve_option(self.instance, self.entry, option, self.actor)
        self.instance.refresh_from_db()
        self.assertEqual(self.instance.status, MissionStatus.COMPLETE)
        lines = list(MissionDeedRewardLine.objects.filter(deed=deed))
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0].amount, 200)
        self.assertEqual(lines[0].recipient, self.character)

    def test_non_terminal_route_emits_no_reward_lines(self) -> None:
        # Phase 5b.0 invariant: emission only happens at terminal routes.
        # An authored route reward on a non-terminal route is ignored at
        # this hop (it never fires — those rows are inert on non-terminal
        # routes by design; the Phase 6+ propagation seam will revisit
        # whether non-terminal authored rewards have any meaning).
        dest = MissionNodeFactory(template=self.template, key="non-term-dest")
        option = MissionOptionFactory(
            node=self.entry,
            order=2,
            option_kind=OptionKind.CHECK,
            source_kind=OptionSource.AUTHORED,
            authored_check_type=self.sneak,
        )
        non_terminal_route = MissionOptionRouteFactory(
            option=option,
            outcome_tier=self.success,
            target_node=dest,
        )
        MissionOptionRouteRewardFactory(
            route=non_terminal_route,
            kind=DeedRewardKind.IMMEDIATE,
            sink=DeedRewardSink.MONEY,
            amount=999,
        )
        with force_check_outcome(self.success):
            deed = resolve_option(self.instance, self.entry, option, self.actor)
        self.assertEqual(MissionDeedRewardLine.objects.filter(deed=deed).count(), 0)
