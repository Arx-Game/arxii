"""Tests for MissionOptionRouteReward + MissionDeedRewardLine.recipient (Phase 5b.0).

Phase 5b.0 closes the Phase-3 gap: the engine now emits
``MissionDeedRewardLine`` rows at terminal routes from an *authored* source
(``MissionOptionRouteReward``) using the template's ``reward_group_rule`` for
distribution across participants. ``recipient`` on the line names exactly
which character's ledger the row pays into.
"""

from django.core.exceptions import ValidationError
from django.test import TestCase

from evennia_extensions.factories import CharacterFactory
from world.checks.factories import CheckTypeFactory
from world.items.factories import ItemTemplateFactory
from world.magic.factories import ResonanceFactory
from world.missions.constants import (
    DeedRewardKind,
    DeedRewardSink,
    OptionKind,
    OptionSource,
)
from world.missions.factories import (
    MissionDeedRecordFactory,
    MissionDeedRewardLineFactory,
    MissionNodeFactory,
    MissionOptionFactory,
    MissionOptionRouteFactory,
    MissionOptionRouteRewardFactory,
    MissionTemplateFactory,
)
from world.missions.models import (
    MissionDeedRewardLine,
    MissionOptionRoute,
    MissionOptionRouteReward,
)
from world.npc_services.constants import OfferKind
from world.npc_services.factories import (
    MissionOfferDetailsFactory,
    NPCServiceOfferFactory,
)
from world.traits.factories import CheckOutcomeFactory


class MissionOptionRouteRewardTests(TestCase):
    """Authored reward template attached to a terminal MissionOptionRoute."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.template = MissionTemplateFactory(name="route-reward-tmpl")
        cls.entry = MissionNodeFactory(template=cls.template, key="entry", is_entry=True)
        cls.success = CheckOutcomeFactory(name="RewardSuccess", success_level=3)
        cls.sneak = CheckTypeFactory(name="RewardSneak")
        cls.check_option = MissionOptionFactory(
            node=cls.entry,
            order=0,
            option_kind=OptionKind.CHECK,
            source_kind=OptionSource.AUTHORED,
            authored_check_type=cls.sneak,
        )
        cls.terminal_route = MissionOptionRouteFactory(
            option=cls.check_option,
            outcome_tier=cls.success,
            target_node=None,  # terminal
        )

    def test_route_reward_round_trips(self) -> None:
        reward = MissionOptionRouteRewardFactory(
            route=self.terminal_route,
            kind=DeedRewardKind.IMMEDIATE,
            sink=DeedRewardSink.MONEY,
            amount=500,
            ref="bounty",
        )
        fetched = MissionOptionRouteReward.objects.get(pk=reward.pk)
        self.assertEqual(fetched.route, self.terminal_route)
        self.assertEqual(fetched.kind, DeedRewardKind.IMMEDIATE)
        self.assertEqual(fetched.sink, DeedRewardSink.MONEY)
        self.assertEqual(fetched.amount, 500)
        self.assertEqual(fetched.ref, "bounty")

    def test_contract_holder_only_defaults_to_false(self) -> None:
        reward = MissionOptionRouteRewardFactory(
            route=self.terminal_route,
            kind=DeedRewardKind.IMMEDIATE,
            sink=DeedRewardSink.LEGEND_POINTS,
            amount=10,
        )
        self.assertFalse(reward.contract_holder_only)

    def test_contract_holder_only_can_be_set(self) -> None:
        reward = MissionOptionRouteRewardFactory(
            route=self.terminal_route,
            kind=DeedRewardKind.POST_CRON,
            sink=DeedRewardSink.RUMOR,
            amount=None,
            ref="heist-rumor",
            contract_holder_only=True,
        )
        reward.refresh_from_db()
        self.assertTrue(reward.contract_holder_only)

    def test_route_delete_cascades_to_reward_templates(self) -> None:
        # Use a fresh route so the shared cls.terminal_route stays usable in
        # other tests in this class (queryset delete bypasses cascade
        # constraints we want, but the Python ref on cls would still be
        # stale after this test if we deleted the shared row).
        local_route = MissionOptionRouteFactory(
            option=self.check_option,
            outcome_tier=self.success,
            target_node=None,
        )
        reward = MissionOptionRouteRewardFactory(
            route=local_route,
            kind=DeedRewardKind.IMMEDIATE,
            sink=DeedRewardSink.MONEY,
            amount=100,
        )
        MissionOptionRoute.objects.filter(pk=local_route.pk).delete()
        self.assertFalse(MissionOptionRouteReward.objects.filter(pk=reward.pk).exists())

    def test_save_calls_clean(self) -> None:
        # House pattern (mirrors MissionTemplate / MissionNode / MissionOption
        # / MissionParticipant): the model's save() override invokes clean()
        # so authored model-level invariants always run on the real write
        # path. We exercise this by patching clean() and asserting save()
        # calls it.
        reward = MissionOptionRouteRewardFactory.build(
            route=self.terminal_route,
            kind=DeedRewardKind.IMMEDIATE,
            sink=DeedRewardSink.MONEY,
            amount=100,
        )
        called = {"n": 0}

        def _spy_clean() -> None:
            called["n"] += 1

        reward.clean = _spy_clean  # type: ignore[method-assign]
        reward.save()
        self.assertGreaterEqual(called["n"], 1)
        # Also confirm clean() raising aborts the save (no row written).
        reward2 = MissionOptionRouteRewardFactory.build(
            route=self.terminal_route,
            kind=DeedRewardKind.IMMEDIATE,
            sink=DeedRewardSink.LEGEND_POINTS,
            amount=5,
        )

        def _raise() -> None:
            msg = "nope"
            raise ValidationError(msg)

        reward2.clean = _raise  # type: ignore[method-assign]
        with self.assertRaises(ValidationError):
            reward2.save()
        self.assertIsNone(reward2.pk)

    def test_related_name_reward_templates(self) -> None:
        reward = MissionOptionRouteRewardFactory(
            route=self.terminal_route,
            kind=DeedRewardKind.IMMEDIATE,
            sink=DeedRewardSink.MONEY,
            amount=50,
        )
        self.assertIn(reward, list(self.terminal_route.reward_templates.all()))


class MissionDeedRewardLineRecipientTests(TestCase):
    """The persisted reward line names the character whose ledger pays out."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.template = MissionTemplateFactory(name="reward-recipient-tmpl")
        cls.node = MissionNodeFactory(template=cls.template, key="entry", is_entry=True)
        cls.actor = CharacterFactory(db_key="RecipientActor")
        cls.deed = MissionDeedRecordFactory(node=cls.node, actor=cls.actor)

    def test_reward_line_has_recipient_field(self) -> None:
        field_names = {f.name for f in MissionDeedRewardLine._meta.get_fields()}
        self.assertIn("recipient", field_names)

    def test_recipient_round_trips(self) -> None:
        helper = CharacterFactory(db_key="Helper")
        line = MissionDeedRewardLineFactory(
            deed=self.deed,
            kind=DeedRewardKind.IMMEDIATE,
            sink=DeedRewardSink.MONEY,
            amount=42,
            recipient=helper,
        )
        line.refresh_from_db()
        self.assertEqual(line.recipient, helper)


class MissionOptionRouteRewardResonanceTests(TestCase):
    """Tests for the #1737 resonance FK on MissionOptionRouteReward."""

    @classmethod
    def setUpTestData(cls):
        cls.route = MissionOptionRouteFactory()
        cls.resonance = ResonanceFactory()

    def test_resonance_sink_requires_resonance_fk(self):
        reward = MissionOptionRouteRewardFactory.build(
            route=self.route,
            candidate=None,
            kind=DeedRewardKind.POST_CRON,
            sink=DeedRewardSink.RESONANCE,
            amount=15,
            resonance=None,
        )
        with self.assertRaises(ValidationError):
            reward.clean()

    def test_resonance_sink_with_resonance_fk_is_valid(self):
        reward = MissionOptionRouteRewardFactory.build(
            route=self.route,
            candidate=None,
            kind=DeedRewardKind.POST_CRON,
            sink=DeedRewardSink.RESONANCE,
            amount=15,
            resonance=self.resonance,
        )
        reward.clean()  # must not raise

    def test_non_resonance_sink_forbids_resonance_fk(self):
        reward = MissionOptionRouteRewardFactory.build(
            route=self.route,
            candidate=None,
            kind=DeedRewardKind.IMMEDIATE,
            sink=DeedRewardSink.MONEY,
            amount=10,
            resonance=self.resonance,
        )
        with self.assertRaises(ValidationError):
            reward.clean()


class MissionOptionRouteRewardItemTemplateTests(TestCase):
    """Tests for the #707 item_template FK on MissionOptionRouteReward.

    Mirrors ``MissionOptionRouteRewardResonanceTests`` above: item_template
    is required when sink=ITEM, and forbidden otherwise — the same
    bidirectional shape as the resonance/RESONANCE validation.
    """

    @classmethod
    def setUpTestData(cls):
        cls.route = MissionOptionRouteFactory()
        cls.item_template = ItemTemplateFactory()

    def test_item_sink_requires_item_template_fk(self):
        reward = MissionOptionRouteRewardFactory.build(
            route=self.route,
            candidate=None,
            kind=DeedRewardKind.IMMEDIATE,
            sink=DeedRewardSink.ITEM,
            amount=None,
            item_template=None,
        )
        with self.assertRaises(ValidationError):
            reward.clean()

    def test_item_sink_with_item_template_fk_is_valid(self):
        reward = MissionOptionRouteRewardFactory.build(
            route=self.route,
            candidate=None,
            kind=DeedRewardKind.IMMEDIATE,
            sink=DeedRewardSink.ITEM,
            amount=None,
            item_template=self.item_template,
        )
        reward.clean()  # must not raise

    def test_non_item_sink_forbids_item_template_fk(self):
        reward = MissionOptionRouteRewardFactory.build(
            route=self.route,
            candidate=None,
            kind=DeedRewardKind.IMMEDIATE,
            sink=DeedRewardSink.MONEY,
            amount=10,
            item_template=self.item_template,
        )
        with self.assertRaises(ValidationError):
            reward.clean()


class MissionOptionRouteRewardFollowOnSummonsTests(TestCase):
    """Tests for the #2082 follow-on-summons fields on MissionOptionRouteReward.

    Mirrors the resonance/ITEM validation shape: followon_offer is required
    when sink=FOLLOW_ON_SUMMONS, forbidden otherwise. contract_holder_only
    must be True for FOLLOW_ON_SUMMONS (targets one actor). The authoring
    fields (followon_message, followon_expiry_hours) are sink-gated too.
    """

    @classmethod
    def setUpTestData(cls):
        cls.route = MissionOptionRouteFactory()
        cls.offer = NPCServiceOfferFactory(kind=OfferKind.MISSION)
        MissionOfferDetailsFactory(offer=cls.offer)

    def test_summons_sink_requires_followon_offer(self):
        reward = MissionOptionRouteRewardFactory.build(
            route=self.route,
            candidate=None,
            kind=DeedRewardKind.IMMEDIATE,
            sink=DeedRewardSink.FOLLOW_ON_SUMMONS,
            contract_holder_only=True,
            followon_offer=None,
        )
        with self.assertRaises(ValidationError):
            reward.clean()

    def test_summons_sink_with_offer_is_valid(self):
        reward = MissionOptionRouteRewardFactory.build(
            route=self.route,
            candidate=None,
            kind=DeedRewardKind.IMMEDIATE,
            sink=DeedRewardSink.FOLLOW_ON_SUMMONS,
            contract_holder_only=True,
            followon_offer=self.offer,
            followon_message="Come at once.",
            followon_expiry_hours=24,
        )
        reward.clean()  # must not raise

    def test_summons_sink_requires_contract_holder_only(self):
        reward = MissionOptionRouteRewardFactory.build(
            route=self.route,
            candidate=None,
            kind=DeedRewardKind.IMMEDIATE,
            sink=DeedRewardSink.FOLLOW_ON_SUMMONS,
            contract_holder_only=False,
            followon_offer=self.offer,
        )
        with self.assertRaises(ValidationError):
            reward.clean()

    def test_non_summons_sink_forbids_followon_offer(self):
        reward = MissionOptionRouteRewardFactory.build(
            route=self.route,
            candidate=None,
            kind=DeedRewardKind.IMMEDIATE,
            sink=DeedRewardSink.MONEY,
            amount=10,
            followon_offer=self.offer,
        )
        with self.assertRaises(ValidationError):
            reward.clean()

    def test_non_summons_sink_forbids_followon_message(self):
        reward = MissionOptionRouteRewardFactory.build(
            route=self.route,
            candidate=None,
            kind=DeedRewardKind.IMMEDIATE,
            sink=DeedRewardSink.MONEY,
            amount=10,
            followon_message="Come at once.",
        )
        with self.assertRaises(ValidationError):
            reward.clean()

    def test_non_summons_sink_forbids_followon_expiry_hours(self):
        reward = MissionOptionRouteRewardFactory.build(
            route=self.route,
            candidate=None,
            kind=DeedRewardKind.IMMEDIATE,
            sink=DeedRewardSink.MONEY,
            amount=10,
            followon_expiry_hours=24,
        )
        with self.assertRaises(ValidationError):
            reward.clean()
