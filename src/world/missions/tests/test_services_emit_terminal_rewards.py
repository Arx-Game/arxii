"""Tests for ``emit_terminal_rewards`` (Phase 5b.0).

The terminal-route reward emitter walks
``route.reward_templates`` and creates one persisted
``MissionDeedRewardLine`` per (template × recipient) — distribution governed
by ``instance.template.reward_group_rule`` and the per-template
``contract_holder_only`` toggle.

ALL_EQUAL is implemented in Phase 5b.0. BY_ROLE and BY_PARTICIPATION are
stub-sealed: they MUST raise NotImplementedError so missions authored
against unbuilt distribution rules surface early rather than silently
degrading to ALL_EQUAL (Phase-6 work).

Real factory objects, no ORM mocks.
"""

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory
from world.missions.constants import (
    DeedRewardKind,
    DeedRewardSink,
    OptionKind,
    OptionSource,
    RewardGroupRule,
)
from world.missions.factories import (
    MissionDeedRecordFactory,
    MissionInstanceFactory,
    MissionNodeFactory,
    MissionOptionFactory,
    MissionOptionRouteFactory,
    MissionOptionRouteRewardFactory,
    MissionParticipantFactory,
    MissionTemplateFactory,
)
from world.missions.models import MissionDeedRewardLine
from world.missions.services import emit_terminal_rewards


def _make_terminal_route(option: object) -> object:
    """A terminal MissionOptionRoute (null outcome_tier, null target_node)."""
    return MissionOptionRouteFactory(
        option=option,
        outcome_tier=None,
        target_node=None,
    )


class EmitTerminalRewardsAllEqualTests(TestCase):
    """ALL_EQUAL is the Phase-5b.0 default distribution rule."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.template = MissionTemplateFactory(
            slug="emit-all-equal-tmpl",
            reward_group_rule=RewardGroupRule.ALL_EQUAL,
        )
        cls.node = MissionNodeFactory(template=cls.template, key="entry", is_entry=True)
        cls.option = MissionOptionFactory(
            node=cls.node,
            order=0,
            option_kind=OptionKind.BRANCH,
            source_kind=OptionSource.AUTHORED,
        )

    def test_single_participant_all_equal_one_line(self) -> None:
        instance = MissionInstanceFactory(template=self.template)
        holder_char = CharacterFactory(db_key="SoloHolder")
        holder = MissionParticipantFactory(
            instance=instance,
            character=holder_char,
            is_contract_holder=True,
        )
        route = _make_terminal_route(self.option)
        MissionOptionRouteRewardFactory(
            route=route,
            kind=DeedRewardKind.IMMEDIATE,
            sink=DeedRewardSink.MONEY,
            amount=500,
            contract_holder_only=False,
        )
        deed = MissionDeedRecordFactory(
            instance=instance,
            actor=holder_char,
            node=self.node,
            option=self.option,
        )

        created = emit_terminal_rewards(instance, route, deed)
        self.assertEqual(len(created), 1)
        line = created[0]
        self.assertEqual(line.deed, deed)
        self.assertEqual(line.recipient, holder_char)
        self.assertEqual(line.kind, DeedRewardKind.IMMEDIATE)
        self.assertEqual(line.sink, DeedRewardSink.MONEY)
        self.assertEqual(line.amount, 500)
        # And the row is persisted.
        self.assertEqual(MissionDeedRewardLine.objects.filter(deed=deed).count(), 1)
        # Side test: verify holder factory was not unused.
        self.assertEqual(holder.character, holder_char)

    def test_multi_participant_all_equal_one_line_per_participant(self) -> None:
        instance = MissionInstanceFactory(template=self.template)
        char_h = CharacterFactory(db_key="MultiHolder")
        char_a = CharacterFactory(db_key="HelperA")
        char_b = CharacterFactory(db_key="HelperB")
        MissionParticipantFactory(instance=instance, character=char_h, is_contract_holder=True)
        MissionParticipantFactory(instance=instance, character=char_a)
        MissionParticipantFactory(instance=instance, character=char_b)
        route = _make_terminal_route(self.option)
        MissionOptionRouteRewardFactory(
            route=route,
            kind=DeedRewardKind.IMMEDIATE,
            sink=DeedRewardSink.MONEY,
            amount=300,
            contract_holder_only=False,
        )
        deed = MissionDeedRecordFactory(
            instance=instance, actor=char_h, node=self.node, option=self.option
        )

        created = emit_terminal_rewards(instance, route, deed)
        self.assertEqual(len(created), 3)
        recipients = sorted(line.recipient_id for line in created)
        self.assertEqual(recipients, sorted([char_h.id, char_a.id, char_b.id]))
        for line in created:
            self.assertEqual(line.amount, 300)
            self.assertEqual(line.sink, DeedRewardSink.MONEY)
            self.assertEqual(line.kind, DeedRewardKind.IMMEDIATE)

    def test_contract_holder_only_emits_single_line_to_holder(self) -> None:
        instance = MissionInstanceFactory(template=self.template)
        char_h = CharacterFactory(db_key="ContractHolder")
        char_a = CharacterFactory(db_key="ContractHelperA")
        char_b = CharacterFactory(db_key="ContractHelperB")
        MissionParticipantFactory(instance=instance, character=char_h, is_contract_holder=True)
        MissionParticipantFactory(instance=instance, character=char_a)
        MissionParticipantFactory(instance=instance, character=char_b)
        route = _make_terminal_route(self.option)
        MissionOptionRouteRewardFactory(
            route=route,
            kind=DeedRewardKind.POST_CRON,
            sink=DeedRewardSink.LEGEND_POINTS,
            amount=50,
            contract_holder_only=True,
        )
        # Actor is intentionally NOT the holder — the recipient field must
        # name the holder, not the actor.
        deed = MissionDeedRecordFactory(
            instance=instance, actor=char_a, node=self.node, option=self.option
        )

        created = emit_terminal_rewards(instance, route, deed)
        self.assertEqual(len(created), 1)
        self.assertEqual(created[0].recipient, char_h)
        self.assertEqual(created[0].amount, 50)
        self.assertEqual(created[0].sink, DeedRewardSink.LEGEND_POINTS)
        self.assertEqual(created[0].kind, DeedRewardKind.POST_CRON)

    def test_mixed_broadcast_and_contract_holder_only(self) -> None:
        instance = MissionInstanceFactory(template=self.template)
        char_h = CharacterFactory(db_key="MixHolder")
        char_a = CharacterFactory(db_key="MixA")
        char_b = CharacterFactory(db_key="MixB")
        MissionParticipantFactory(instance=instance, character=char_h, is_contract_holder=True)
        MissionParticipantFactory(instance=instance, character=char_a)
        MissionParticipantFactory(instance=instance, character=char_b)
        route = _make_terminal_route(self.option)
        # 1 broadcast row + 1 contract_holder_only row.
        MissionOptionRouteRewardFactory(
            route=route,
            kind=DeedRewardKind.IMMEDIATE,
            sink=DeedRewardSink.MONEY,
            amount=100,
            contract_holder_only=False,
        )
        MissionOptionRouteRewardFactory(
            route=route,
            kind=DeedRewardKind.IMMEDIATE,
            sink=DeedRewardSink.MONEY,
            amount=200,
            ref="contract-bonus",
            contract_holder_only=True,
        )
        deed = MissionDeedRecordFactory(
            instance=instance, actor=char_h, node=self.node, option=self.option
        )

        created = emit_terminal_rewards(instance, route, deed)
        # 3 broadcast lines + 1 contractual line = 4.
        self.assertEqual(len(created), 4)
        broadcast = [line for line in created if line.amount == 100]
        contractual = [line for line in created if line.amount == 200]
        self.assertEqual(len(broadcast), 3)
        self.assertEqual(len(contractual), 1)
        self.assertEqual(contractual[0].recipient, char_h)
        self.assertEqual(contractual[0].ref, "contract-bonus")
        broadcast_recipients = sorted(line.recipient_id for line in broadcast)
        self.assertEqual(broadcast_recipients, sorted([char_h.id, char_a.id, char_b.id]))

    def test_no_reward_templates_returns_empty_list(self) -> None:
        instance = MissionInstanceFactory(template=self.template)
        char_h = CharacterFactory(db_key="NoRewardHolder")
        MissionParticipantFactory(instance=instance, character=char_h, is_contract_holder=True)
        route = _make_terminal_route(self.option)
        deed = MissionDeedRecordFactory(
            instance=instance, actor=char_h, node=self.node, option=self.option
        )

        created = emit_terminal_rewards(instance, route, deed)
        self.assertEqual(created, [])
        self.assertEqual(MissionDeedRewardLine.objects.filter(deed=deed).count(), 0)


class EmitTerminalRewardsStubSealedRulesTests(TestCase):
    """BY_ROLE and BY_PARTICIPATION must hard-fail until Phase 6 builds them."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.node_template = MissionNodeFactory(
            template=MissionTemplateFactory(slug="stub-template"),
            key="stub-entry",
            is_entry=True,
        )

    def _setup_for_rule(self, rule: str) -> tuple[object, object, object, object]:
        template = MissionTemplateFactory(
            slug=f"stub-{rule}-tmpl",
            reward_group_rule=rule,
        )
        node = MissionNodeFactory(template=template, key="entry", is_entry=True)
        option = MissionOptionFactory(
            node=node,
            order=0,
            option_kind=OptionKind.BRANCH,
            source_kind=OptionSource.AUTHORED,
        )
        instance = MissionInstanceFactory(template=template)
        char_h = CharacterFactory(db_key=f"StubHolder-{rule}")
        MissionParticipantFactory(instance=instance, character=char_h, is_contract_holder=True)
        route = _make_terminal_route(option)
        MissionOptionRouteRewardFactory(
            route=route,
            kind=DeedRewardKind.IMMEDIATE,
            sink=DeedRewardSink.MONEY,
            amount=100,
            contract_holder_only=False,
        )
        deed = MissionDeedRecordFactory(instance=instance, actor=char_h, node=node, option=option)
        return instance, route, deed, char_h

    def test_by_role_raises_not_implemented(self) -> None:
        instance, route, deed, _ = self._setup_for_rule(RewardGroupRule.BY_ROLE)
        with self.assertRaises(NotImplementedError):
            emit_terminal_rewards(instance, route, deed)
        # Nothing was persisted.
        self.assertEqual(MissionDeedRewardLine.objects.filter(deed=deed).count(), 0)

    def test_by_participation_raises_not_implemented(self) -> None:
        instance, route, deed, _ = self._setup_for_rule(RewardGroupRule.BY_PARTICIPATION)
        with self.assertRaises(NotImplementedError):
            emit_terminal_rewards(instance, route, deed)
        self.assertEqual(MissionDeedRewardLine.objects.filter(deed=deed).count(), 0)

    def test_stub_sealed_rules_skip_contract_holder_only_too(self) -> None:
        # Defensive: BY_ROLE/BY_PARTICIPATION must hard-fail at any
        # broadcast template, even if the route also has contract-only rows
        # that *would* succeed on their own — we do not want partial
        # emission. The whole call must abort.
        template = MissionTemplateFactory(
            slug="stub-partial-tmpl",
            reward_group_rule=RewardGroupRule.BY_ROLE,
        )
        node = MissionNodeFactory(template=template, key="entry", is_entry=True)
        option = MissionOptionFactory(
            node=node,
            order=0,
            option_kind=OptionKind.BRANCH,
            source_kind=OptionSource.AUTHORED,
        )
        instance = MissionInstanceFactory(template=template)
        char_h = CharacterFactory(db_key="StubPartialHolder")
        MissionParticipantFactory(instance=instance, character=char_h, is_contract_holder=True)
        route = _make_terminal_route(option)
        MissionOptionRouteRewardFactory(
            route=route,
            kind=DeedRewardKind.IMMEDIATE,
            sink=DeedRewardSink.MONEY,
            amount=100,
            contract_holder_only=True,
        )
        MissionOptionRouteRewardFactory(
            route=route,
            kind=DeedRewardKind.IMMEDIATE,
            sink=DeedRewardSink.MONEY,
            amount=200,
            contract_holder_only=False,
        )
        deed = MissionDeedRecordFactory(instance=instance, actor=char_h, node=node, option=option)
        with self.assertRaises(NotImplementedError):
            emit_terminal_rewards(instance, route, deed)
        # No partial writes: the contract-only row must NOT have been
        # persisted. Implementation strategy: wrap the whole emission in an
        # atomic block, OR compute everything before any DB write.
        self.assertEqual(MissionDeedRewardLine.objects.filter(deed=deed).count(), 0)


class EmitTerminalRewardsGuardTests(TestCase):
    """Defensive guards on the caller contract."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.template = MissionTemplateFactory(slug="guard-tmpl")
        cls.node = MissionNodeFactory(template=cls.template, key="entry", is_entry=True)
        cls.dest = MissionNodeFactory(template=cls.template, key="dest")
        cls.option = MissionOptionFactory(
            node=cls.node,
            order=0,
            option_kind=OptionKind.BRANCH,
            source_kind=OptionSource.AUTHORED,
        )

    def test_non_terminal_route_raises(self) -> None:
        # Caller bug guard: emit_terminal_rewards must only be called for
        # terminal routes. Passing a route with a non-null target_node is a
        # caller bug and should fail loudly, not silently emit lines that
        # would otherwise belong to the destination's terminal route.
        instance = MissionInstanceFactory(template=self.template)
        char_h = CharacterFactory(db_key="GuardHolder")
        MissionParticipantFactory(instance=instance, character=char_h, is_contract_holder=True)
        non_terminal_route = MissionOptionRouteFactory(
            option=self.option,
            outcome_tier=None,
            target_node=self.dest,  # non-null = NOT terminal
        )
        deed = MissionDeedRecordFactory(
            instance=instance, actor=char_h, node=self.node, option=self.option
        )
        with self.assertRaises(ValueError):
            emit_terminal_rewards(instance, non_terminal_route, deed)

    def test_missing_contract_holder_raises(self) -> None:
        # An active mission must always have a contract holder. If a
        # contract_holder_only row is on the route and no holder exists,
        # the emitter must hard-fail rather than silently dropping the
        # reward.
        instance = MissionInstanceFactory(template=self.template)
        # Only a non-holder participant — pathological state, used to
        # exercise the assertion.
        non_holder_char = CharacterFactory(db_key="NoHolder")
        MissionParticipantFactory(
            instance=instance, character=non_holder_char, is_contract_holder=False
        )
        route = _make_terminal_route(self.option)
        MissionOptionRouteRewardFactory(
            route=route,
            kind=DeedRewardKind.IMMEDIATE,
            sink=DeedRewardSink.MONEY,
            amount=10,
            contract_holder_only=True,
        )
        deed = MissionDeedRecordFactory(
            instance=instance, actor=non_holder_char, node=self.node, option=self.option
        )
        with self.assertRaises(ValueError):
            emit_terminal_rewards(instance, route, deed)
