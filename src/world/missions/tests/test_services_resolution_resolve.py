"""Tests for ``resolve_option`` (Phase 3, Tasks 3.3 / 3.4 / 3.5).

CHECK options roll a check (difficulty = template.risk_tier), match the
route for the rolled outcome tier, apply the route consequence (authored or
synthetic fallback), additively apply a permitted binding rider, then route
or complete. BRANCH options skip the check entirely. Terminal routes (null
destination) complete the run WITHOUT emitting any reward lines.

Real factory objects, no ORM mocks. ``force_check_outcome`` pins the rolled
outcome tier deterministically. ``apply_resolution`` (the reuse boundary) is
spied to assert the consequence/rider composition without wiring the full
ConsequenceEffect machinery.
"""

from unittest.mock import patch

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import CheckTypeFactory, ConsequenceFactory
from world.checks.test_helpers import force_check_outcome
from world.distinctions.factories import CharacterDistinctionFactory, DistinctionFactory
from world.missions.constants import (
    DeedRewardKind,
    DeedRewardSink,
    MissionStatus,
    OptionKind,
    OptionProduces,
    OptionSource,
)
from world.missions.factories import (
    AffordanceBindingFactory,
    AffordanceFactory,
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
    SOURCE_DISTINCTION,
    MissionDeedRecord,
    MissionDeedRewardLine,
    MissionOptionRouteReward,
)
from world.missions.services import resolve_option
from world.traits.factories import CheckOutcomeFactory

_APPLY = "world.missions.services.resolution.apply_resolution"


class ResolveCheckOptionTests(TestCase):
    """CHECK routing, consequence fallback, riders, random sets."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.character = CharacterFactory()
        cls.sheet = CharacterSheetFactory(character=cls.character)

        cls.template = MissionTemplateFactory(slug="resolve-tmpl", risk_tier=4)
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
            deed = resolve_option(self.instance, self.entry, self.check_option, self.actor, None)
        self.instance.refresh_from_db()
        self.assertEqual(self.instance.current_node, self.node_a)
        self.assertEqual(deed.outcome, self.success)
        self.assertEqual(deed.actor, self.character)
        # Authored consequence applied (no rider configured → exactly one call).
        self.assertEqual(mocked.call_count, 1)
        pending = mocked.call_args_list[0].args[0]
        self.assertEqual(pending.selected_consequence, self.success_conseq)

    def test_fail_routes_to_b_with_synthetic_fallback(self) -> None:
        with force_check_outcome(self.failure), patch(_APPLY) as mocked:
            deed = resolve_option(self.instance, self.entry, self.check_option, self.actor, None)
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
            deed = resolve_option(self.instance, self.entry, self.check_option, self.actor, None)
        self.assertTrue(MissionDeedRecord.objects.filter(pk=deed.pk).exists())

    def test_rider_applied_when_node_allows_it(self) -> None:
        rider = ConsequenceFactory(outcome_tier=self.success)
        self.entry.allowed_riders.add(rider)
        dist = DistinctionFactory(slug="rider-dist")
        CharacterDistinctionFactory(character=self.character, distinction=dist)
        aff = AffordanceFactory(name="rider-aff")
        binding = AffordanceBindingFactory(
            source_kind=SOURCE_DISTINCTION,
            source_distinction=dist,
            affordance=aff,
            produces=OptionProduces.CHECK,
            check_type=self.sneak,
            rider=rider,
        )
        with force_check_outcome(self.success), patch(_APPLY) as mocked:
            resolve_option(self.instance, self.entry, self.check_option, self.actor, binding)
        # Two calls: route consequence THEN rider (additive composition).
        self.assertEqual(mocked.call_count, 2)
        self.assertEqual(
            mocked.call_args_list[0].args[0].selected_consequence,
            self.success_conseq,
        )
        self.assertEqual(
            mocked.call_args_list[1].args[0].selected_consequence,
            rider,
        )

    def test_rider_suppressed_when_deny_all_riders(self) -> None:
        rider = ConsequenceFactory(outcome_tier=self.success)
        self.entry.allowed_riders.add(rider)
        self.entry.deny_all_riders = True
        self.entry.save()
        binding = AffordanceBindingFactory(
            source_kind=SOURCE_DISTINCTION,
            source_distinction=DistinctionFactory(slug="deny-dist"),
            affordance=AffordanceFactory(name="deny-aff"),
            produces=OptionProduces.CHECK,
            check_type=self.sneak,
            rider=rider,
        )
        with force_check_outcome(self.success), patch(_APPLY) as mocked:
            resolve_option(self.instance, self.entry, self.check_option, self.actor, binding)
        self.assertEqual(mocked.call_count, 1)

    def test_rider_suppressed_when_not_in_allowed_riders(self) -> None:
        rider = ConsequenceFactory(outcome_tier=self.success)
        # rider deliberately NOT added to entry.allowed_riders.
        binding = AffordanceBindingFactory(
            source_kind=SOURCE_DISTINCTION,
            source_distinction=DistinctionFactory(slug="notallowed-dist"),
            affordance=AffordanceFactory(name="notallowed-aff"),
            produces=OptionProduces.CHECK,
            check_type=self.sneak,
            rider=rider,
        )
        with force_check_outcome(self.success), patch(_APPLY) as mocked:
            resolve_option(self.instance, self.entry, self.check_option, self.actor, binding)
        self.assertEqual(mocked.call_count, 1)

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
            resolve_option(self.instance, self.entry, self.check_option, self.actor, None)
        self.instance.refresh_from_db()
        self.assertIn(self.instance.current_node, {self.node_a, self.node_b})

    def test_deed_actor_is_acting_participants_character(self) -> None:
        with force_check_outcome(self.success):
            deed = resolve_option(self.instance, self.entry, self.check_option, self.actor, None)
        self.assertEqual(deed.actor, self.actor.character)

    def test_misconfigured_check_without_check_type_raises(self) -> None:
        bad_option = MissionOptionFactory(
            node=self.entry,
            order=9,
            option_kind=OptionKind.CHECK,
            source_kind=OptionSource.AFFORDANCE,
        )
        with self.assertRaises(ValueError):
            resolve_option(self.instance, self.entry, bad_option, self.actor, None)


class ResolveBranchOptionTests(TestCase):
    """BRANCH path: no check, deed outcome None, routes via branch_target."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.template = MissionTemplateFactory(slug="branch-tmpl")
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
            deed = resolve_option(self.instance, self.entry, option, self.actor, None)
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
        deed = resolve_option(self.instance, self.entry, option, self.actor, None)
        self.instance.refresh_from_db()
        self.assertEqual(self.instance.current_node, self.target)
        self.assertIsNone(deed.outcome)


class TerminalCompletionTests(TestCase):
    """Terminal route → COMPLETE, completed_at set, NO reward lines."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.character = CharacterFactory()
        cls.sheet = CharacterSheetFactory(character=cls.character)
        cls.template = MissionTemplateFactory(slug="terminal-tmpl", risk_tier=2)
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
        deed = resolve_option(self.instance, self.entry, option, self.actor, None)
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
            deed = resolve_option(self.instance, self.entry, option, self.actor, None)
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
        deed = resolve_option(self.instance, self.entry, option, self.actor, None)
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
        cls.template = MissionTemplateFactory(slug="emit-int-tmpl", risk_tier=2)
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
            deed = resolve_option(self.instance, self.entry, option, self.actor, None)
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
        deed = resolve_option(self.instance, self.entry, option, self.actor, None)
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
            deed = resolve_option(self.instance, self.entry, option, self.actor, None)
        self.assertEqual(MissionDeedRewardLine.objects.filter(deed=deed).count(), 0)
