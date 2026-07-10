"""Tests for the seven-template tutorial chain seeder T1-T7 (#1035).

Uses ``seed_dev_database()`` (the Big Button) rather than
``seed_tutorial_dev()`` in isolation for the first pass — the T4 board giver
is reused from ``seed_missions_dev()`` (the "missions" cluster), whose own
authored CHECK options need the "checks" cluster's CheckOutcome catalog and
the "character_creation" cluster's "wits" stat Trait, exactly as a real
deploy seeds them (cluster ordering in ``world.seeds.clusters``). The
idempotency assertion then calls ``seed_tutorial_dev()`` directly a second
time (it was already invoked once via the "tutorial" cluster inside
``seed_dev_database()``), mirroring ``test_seed_missions.py``'s
``test_rerun_is_idempotent_no_op`` pattern.
"""

from __future__ import annotations

from datetime import timedelta

from django.test import TestCase

from world.missions.constants import DeedRewardSink, ExternalAct, GiverKind, OptionKind
from world.missions.models import (
    MissionGiver,
    MissionNode,
    MissionOption,
    MissionOptionRoute,
    MissionTemplate,
)
from world.npc_services.constants import OfferKind
from world.npc_services.models import MissionOfferDetails, NPCRole, NPCServiceOffer
from world.seeds.character_creation import ensure_canonical_fallback_room
from world.seeds.database import seed_dev_database
from world.seeds.game_content.tutorial import seed_tutorial_dev

_T1_NAME = "Arrival"
_T2_NAME = "What the Walls Remember"
_T3_NAME = "First Spark"
_T4_NAME = "A Simple Job"
_T5_NAME = "The Loom"
_T6_NAME = "Sworn Together"
_T7_NAME = "The Long Dark"


def _gate_for(template: MissionTemplate) -> dict:
    return {"leaf": "has_completed_mission", "params": {"template_id": template.pk}}


class SeedTutorialDevTests(TestCase):
    """Row shape of the T1-T7 chain + idempotency."""

    @classmethod
    def setUpTestData(cls) -> None:
        seed_dev_database()
        cls.t1 = MissionTemplate.objects.get(name=_T1_NAME)
        cls.t2 = MissionTemplate.objects.get(name=_T2_NAME)
        cls.t3 = MissionTemplate.objects.get(name=_T3_NAME)
        cls.t4 = MissionTemplate.objects.get(name=_T4_NAME)
        cls.t5 = MissionTemplate.objects.get(name=_T5_NAME)
        cls.t6 = MissionTemplate.objects.get(name=_T6_NAME)
        cls.t7 = MissionTemplate.objects.get(name=_T7_NAME)

    # -- idempotency ---------------------------------------------------

    def test_rerun_is_idempotent_no_op(self) -> None:
        template_count = MissionTemplate.objects.count()
        node_count = MissionNode.objects.count()
        option_count = MissionOption.objects.count()
        giver_count = MissionGiver.objects.count()
        role_count = NPCRole.objects.count()
        offer_count = NPCServiceOffer.objects.count()

        seed_tutorial_dev()
        seed_tutorial_dev()

        self.assertEqual(MissionTemplate.objects.count(), template_count)
        self.assertEqual(MissionNode.objects.count(), node_count)
        self.assertEqual(MissionOption.objects.count(), option_count)
        self.assertEqual(MissionGiver.objects.count(), giver_count)
        self.assertEqual(NPCRole.objects.count(), role_count)
        self.assertEqual(NPCServiceOffer.objects.count(), offer_count)

    def test_rerun_preserves_staff_edit_to_template(self) -> None:
        self.t1.summary = "Staff-rewritten arrival summary."
        self.t1.save(update_fields=["summary"])

        seed_tutorial_dev()

        self.t1.refresh_from_db()
        self.assertEqual(self.t1.summary, "Staff-rewritten arrival summary.")

    # -- risk-tier ladder (review fold-in: T6 was mis-seeded at 3) -------

    def test_risk_tier_ladder_across_all_seven_templates(self) -> None:
        """Approved chain table: T1-T7 risk tiers are 1/1/1/2/2/2/4.

        Asserted as a single ladder (rather than one assertion per template
        scattered across this file) so the full shape can't silently drift —
        a future edit to any one template's risk_tier breaks this test loudly.
        """
        self.assertEqual(
            [t.risk_tier for t in (self.t1, self.t2, self.t3, self.t4, self.t5, self.t6, self.t7)],
            [1, 1, 1, 2, 2, 2, 4],
        )

    # -- role-cooldown (review fold-in, #1035 Task 6): the anti-spam
    # NPCRoleCooldown gate must not block same-session chain progression --

    def test_tutor_offers_carry_zero_role_cooldown(self) -> None:
        """T3/T5/T6/T7 all seed role_cooldown_duration=timedelta(0).

        Curated single-path chain: availability_rule + the per-(persona,
        role) one-in-flight gate already prevent double-dipping, so leaving
        this at the factory-default cooldown (1 day) would block a real
        player finishing T3 from accepting T5/T6/T7 in the same session
        (reviewer-verified bug on commit a159b6c9e). Asserted as a single
        ladder across all four so seed drift on any one breaks this loudly.
        """
        details = [
            MissionOfferDetails.objects.get(mission_template=t)
            for t in (self.t3, self.t5, self.t6, self.t7)
        ]
        self.assertEqual(
            [d.role_cooldown_duration for d in details],
            [timedelta(0)] * 4,
        )

    # -- T1 Arrival ------------------------------------------------------

    def test_t1_arrival_shape(self) -> None:
        self.assertEqual(self.t1.risk_tier, 1)
        self.assertEqual(self.t1.availability_rule, {})
        giver = MissionGiver.objects.get(giver_kind=GiverKind.ROOM_TRIGGER, templates=self.t1)
        room = ensure_canonical_fallback_room()
        self.assertEqual(giver.target_id, room.pk)

    # -- T2 What the Walls Remember --------------------------------------

    def test_t2_environmental_detail_giver_and_gate(self) -> None:
        giver = MissionGiver.objects.get(
            giver_kind=GiverKind.ENVIRONMENTAL_DETAIL, templates=self.t2
        )
        self.assertIsNotNone(giver.target_id)
        self.assertEqual(self.t2.availability_rule, _gate_for(self.t1))

    # -- T3 First Spark ---------------------------------------------------

    def test_t3_external_act_on_entry_node_and_npc_offer(self) -> None:
        entry = self.t3.nodes.get(is_entry=True)
        option = entry.options.get()
        self.assertEqual(option.option_kind, OptionKind.EXTERNAL_ACT)
        self.assertEqual(option.required_act, ExternalAct.TECHNIQUE_CAST)
        self.assertEqual(self.t3.availability_rule, _gate_for(self.t2))

        details = MissionOfferDetails.objects.get(mission_template=self.t3)
        self.assertEqual(details.offer.kind, OfferKind.MISSION)

    # -- T4 A Simple Job ---------------------------------------------------

    def test_t4_board_giver_report_to_role_and_gate(self) -> None:
        giver = MissionGiver.objects.get(giver_kind=GiverKind.BOARD, templates=self.t4)
        # Reuses the starter mission board's own giver (#2121), not a new one.
        self.assertGreater(giver.templates.count(), 1)
        self.assertIsNotNone(self.t4.report_to_role_id)
        self.assertEqual(self.t4.availability_rule, _gate_for(self.t3))

    def test_t4_terminal_route_carries_followon_summons_to_t5(self) -> None:
        entry = self.t4.nodes.get(is_entry=True)
        option = entry.options.get()
        route = option.routes.get(outcome_tier__isnull=True)
        summons_line = route.reward_templates.get(sink=DeedRewardSink.FOLLOW_ON_SUMMONS)
        self.assertTrue(summons_line.contract_holder_only)
        t5_details = MissionOfferDetails.objects.get(mission_template=self.t5)
        self.assertEqual(summons_line.followon_offer_id, t5_details.offer_id)

    # -- T5 The Loom --------------------------------------------------------

    def test_t5_thread_woven_on_entry_node_and_gate(self) -> None:
        entry = self.t5.nodes.get(is_entry=True)
        option = entry.options.get()
        self.assertEqual(option.option_kind, OptionKind.EXTERNAL_ACT)
        self.assertEqual(option.required_act, ExternalAct.THREAD_WOVEN)
        self.assertTrue(entry.is_entry)
        self.assertEqual(self.t5.availability_rule, _gate_for(self.t4))

    # -- T6 Sworn Together ----------------------------------------------------

    def test_t6_covenant_sworn_on_entry_node_and_gate(self) -> None:
        entry = self.t6.nodes.get(is_entry=True)
        option = entry.options.get()
        self.assertEqual(option.option_kind, OptionKind.EXTERNAL_ACT)
        self.assertEqual(option.required_act, ExternalAct.COVENANT_SWORN)
        self.assertTrue(entry.is_entry)
        self.assertEqual(self.t6.availability_rule, _gate_for(self.t5))

    # -- T7 The Long Dark -----------------------------------------------------

    def test_t7_legend_line_draw_priority_and_gate(self) -> None:
        self.assertEqual(self.t7.risk_tier, 4)
        self.assertEqual(self.t7.availability_rule, _gate_for(self.t6))

        entry = self.t7.nodes.get(is_entry=True)
        option = entry.options.get()
        route = option.routes.get(outcome_tier__isnull=True)
        self.assertTrue(route.reward_templates.filter(sink=DeedRewardSink.LEGEND_POINTS).exists())

        details = MissionOfferDetails.objects.get(mission_template=self.t7)
        self.assertGreater(details.draw_priority, 0)

    # -- durable-act entry-node guard is honored by the seeder itself ---------

    def test_all_external_act_options_sit_on_entry_nodes(self) -> None:
        for template in (self.t3, self.t5, self.t6):
            option = MissionOption.objects.get(
                node__template=template, option_kind=OptionKind.EXTERNAL_ACT
            )
            self.assertTrue(option.node.is_entry)


class MissionOptionRouteQueryHelperTests(TestCase):
    """Sanity: the chain's routes are structurally reachable via ORM lookups
    the way the reward-emission engine walks them (no orphaned FKs)."""

    @classmethod
    def setUpTestData(cls) -> None:
        seed_dev_database()

    def test_every_chain_template_has_exactly_one_entry_node(self) -> None:
        for name in (_T1_NAME, _T2_NAME, _T3_NAME, _T4_NAME, _T5_NAME, _T6_NAME, _T7_NAME):
            template = MissionTemplate.objects.get(name=name)
            entry_count = MissionNode.objects.filter(template=template, is_entry=True).count()
            self.assertEqual(entry_count, 1)

    def test_every_terminal_route_has_null_target_node(self) -> None:
        for name in (_T1_NAME, _T2_NAME, _T3_NAME, _T4_NAME, _T5_NAME, _T6_NAME, _T7_NAME):
            template = MissionTemplate.objects.get(name=name)
            entry = template.nodes.get(is_entry=True)
            option = entry.options.get()
            route = MissionOptionRoute.objects.get(option=option, outcome_tier__isnull=True)
            self.assertIsNone(route.target_node_id)


class AuditLegendFloorTutorialChainTests(TestCase):
    """``audit_legend_floor`` (#2051 risk-floor guard) reports no violations
    for the seeded T1-T7 chain templates (#1035 review fold-in F2) — a
    regression guard so a future edit to the chain's legend-paying rewards
    can't silently drop below ``LEGEND_RISK_FLOOR_TIER`` without a test
    failing loudly."""

    @classmethod
    def setUpTestData(cls) -> None:
        seed_dev_database()

    def test_no_legend_floor_violations_for_tutorial_chain(self) -> None:
        from world.missions.management.commands.audit_legend_floor import Command

        command = Command()
        violations = command._check_route_rewards() + command._check_renown_awards()

        chain_names = (_T1_NAME, _T2_NAME, _T3_NAME, _T4_NAME, _T5_NAME, _T6_NAME, _T7_NAME)
        chain_violations = [v for v in violations if any(f"'{name}'" in v for name in chain_names)]
        self.assertEqual(chain_violations, [])
