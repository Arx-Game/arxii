"""Tests for the mission-accept risk gate + stakes activation at issue (#1770 PR4).

Covers: the MISSION_RISK_ACK_TIER gate in issue_mission (typed error, no
state written), acknowledge_mission_risk idempotency, the two-phase
acknowledge_risk opt-in inside the npc_resolve action, and
activate_stakes_for_instance (mission acceptance as the commit moment).
"""

from __future__ import annotations

from unittest import mock

from django.test import TestCase

from actions.definitions.npc_services import resolve_npc_offer
from evennia_extensions.factories import CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.missions.constants import MISSION_RISK_ACK_TIER
from world.missions.factories import MissionInstanceFactory, MissionNodeFactory
from world.missions.models import MissionInstance, MissionRiskAcknowledgement
from world.missions.services.beat import activate_stakes_for_instance
from world.missions.services.offer_handler import (
    MissionRiskUnacknowledgedError,
    acknowledge_mission_risk,
    issue_mission,
)
from world.npc_services.constants import OfferKind
from world.npc_services.factories import (
    MissionOfferDetailsFactory,
    NPCRoleFactory,
    NPCServiceOfferFactory,
)
from world.npc_services.services import start_interaction
from world.societies.constants import RenownRisk
from world.stories.constants import StakeSeverity
from world.stories.factories import BeatFactory, StakeFactory
from world.stories.models import StakeContractActivation
from world.stories.types import StakeBoundaryReport


def _make_pc():
    character = CharacterFactory()
    sheet = CharacterSheetFactory(character=character)
    return character, sheet.primary_persona


def _make_mission_offer(*, risk_tier: int):
    from world.missions.factories import MissionTemplateFactory

    role = NPCRoleFactory()
    template = MissionTemplateFactory(risk_tier=risk_tier)
    MissionNodeFactory(template=template, key="entry", is_entry=True)
    offer = NPCServiceOfferFactory(
        role=role,
        kind=OfferKind.MISSION,
        label=f"mission-{template.name}",
    )
    MissionOfferDetailsFactory(offer=offer, mission_template=template)
    return offer, template


class IssueMissionRiskGateTests(TestCase):
    def test_risky_template_without_ack_raises_and_writes_nothing(self):
        _character, persona = _make_pc()
        offer, template = _make_mission_offer(risk_tier=MISSION_RISK_ACK_TIER)

        with self.assertRaises(MissionRiskUnacknowledgedError) as ctx:
            issue_mission(offer, persona)

        self.assertEqual(ctx.exception.risk_tier, template.risk_tier)
        self.assertFalse(MissionInstance.objects.exists())

    def test_low_risk_template_needs_no_ack(self):
        _character, persona = _make_pc()
        offer, _template = _make_mission_offer(risk_tier=MISSION_RISK_ACK_TIER - 1)

        result = issue_mission(offer, persona)

        self.assertTrue(MissionInstance.objects.filter(pk=result.object_pk).exists())

    def test_acknowledged_risky_template_issues(self):
        _character, persona = _make_pc()
        offer, template = _make_mission_offer(risk_tier=MISSION_RISK_ACK_TIER + 1)

        ack = acknowledge_mission_risk(offer, persona)
        result = issue_mission(offer, persona)

        self.assertEqual(ack.acknowledged_risk_tier, template.risk_tier)
        self.assertTrue(MissionInstance.objects.filter(pk=result.object_pk).exists())

    def test_acknowledge_mission_risk_is_idempotent(self):
        _character, persona = _make_pc()
        offer, _template = _make_mission_offer(risk_tier=MISSION_RISK_ACK_TIER)

        first = acknowledge_mission_risk(offer, persona)
        second = acknowledge_mission_risk(offer, persona)

        self.assertEqual(first.pk, second.pk)
        self.assertEqual(MissionRiskAcknowledgement.objects.count(), 1)

    def test_acknowledge_non_mission_offer_is_a_noop(self):
        _character, persona = _make_pc()
        offer = NPCServiceOfferFactory(role=NPCRoleFactory(), label="permit")

        self.assertIsNone(acknowledge_mission_risk(offer, persona))
        self.assertFalse(MissionRiskAcknowledgement.objects.exists())


class NpcResolveTwoPhaseTests(TestCase):
    """The two-phase opt-in lives inside the npc_resolve action."""

    def _session_and_offer(self, *, risk_tier: int):
        character, persona = _make_pc()
        offer, _template = _make_mission_offer(risk_tier=risk_tier)
        session = start_interaction(
            role=offer.role,
            persona=persona,
            character=character,
        )
        return character, session, offer

    def test_resolve_without_ack_returns_informed_consent_prompt(self):
        character, session, offer = self._session_and_offer(risk_tier=MISSION_RISK_ACK_TIER)

        result = resolve_npc_offer.run(actor=character, session=session, offer_id=offer.pk)

        self.assertFalse(result.success)
        self.assertTrue(result.data["requires_risk_acknowledgement"])
        self.assertEqual(result.data["risk_tier"], MISSION_RISK_ACK_TIER)
        self.assertIn("acknowledge_risk=yes", result.message)
        self.assertFalse(MissionInstance.objects.exists())

    def test_resolve_with_acknowledge_kwarg_writes_ack_and_issues(self):
        character, session, offer = self._session_and_offer(risk_tier=MISSION_RISK_ACK_TIER)

        result = resolve_npc_offer.run(
            actor=character,
            session=session,
            offer_id=offer.pk,
            acknowledge_risk="yes",
        )

        self.assertTrue(result.success)
        self.assertTrue(MissionRiskAcknowledgement.objects.filter(offer=offer).exists())
        self.assertEqual(MissionInstance.objects.count(), 1)

    def test_low_risk_resolve_has_no_gate(self):
        character, session, offer = self._session_and_offer(risk_tier=1)

        result = resolve_npc_offer.run(actor=character, session=session, offer_id=offer.pk)

        self.assertTrue(result.success)
        self.assertFalse(MissionRiskAcknowledgement.objects.exists())

    def test_ineligible_offer_never_mints_an_ack_row(self):
        """#1770 PR4 review: eligibility is validated BEFORE any ack is written."""
        character, session, offer = self._session_and_offer(risk_tier=MISSION_RISK_ACK_TIER)
        # Make the offer ineligible for this session (rapport gate).
        offer.rapport_requirement = 10_000
        offer.save(update_fields=["rapport_requirement"])

        result = resolve_npc_offer.run(
            actor=character,
            session=session,
            offer_id=offer.pk,
            acknowledge_risk="yes",
        )

        self.assertFalse(result.success)
        self.assertFalse(MissionRiskAcknowledgement.objects.exists())
        self.assertFalse(MissionInstance.objects.exists())


class ActivateStakesForInstanceTests(TestCase):
    """Mission acceptance is the stakes commit moment (pillar 9)."""

    def _staked_beat(self):
        beat = BeatFactory(risk=RenownRisk.HIGH, target_level=4)
        StakeFactory(beat=beat, severity=StakeSeverity.DIRE)
        return beat

    def test_activation_written_for_staked_linked_beat(self):
        sheet = CharacterSheetFactory()
        beat = self._staked_beat()
        instance = MissionInstanceFactory(source_beat=beat)

        activate_stakes_for_instance(instance, [sheet])

        self.assertTrue(
            StakeContractActivation.objects.filter(beat=beat, resolved_at__isnull=True).exists()
        )

    def test_free_run_and_unstaked_beat_are_noops(self):
        sheet = CharacterSheetFactory()
        free_run = MissionInstanceFactory(source_beat=None)
        activate_stakes_for_instance(free_run, [sheet])

        unstaked = BeatFactory(risk=RenownRisk.NONE)
        linked = MissionInstanceFactory(source_beat=unstaked)
        activate_stakes_for_instance(linked, [sheet])

        self.assertFalse(StakeContractActivation.objects.exists())

    def test_blocked_boundary_skips_activation(self):
        sheet = CharacterSheetFactory()
        beat = self._staked_beat()
        instance = MissionInstanceFactory(source_beat=beat)
        blocked = StakeBoundaryReport(allowed=False, blocked_reason_private="private")

        with mock.patch(
            "world.stories.services.boundaries.check_stake_boundaries",
            return_value=blocked,
        ):
            activate_stakes_for_instance(instance, [sheet])

        self.assertFalse(StakeContractActivation.objects.exists())

    def test_issue_mission_invokes_activation_seam(self):
        _character, persona = _make_pc()
        offer, _template = _make_mission_offer(risk_tier=1)

        with mock.patch("world.missions.services.beat.activate_stakes_for_instance") as mocked:
            result = issue_mission(offer, persona)

        mocked.assert_called_once()
        instance_arg, sheets_arg = mocked.call_args.args
        self.assertEqual(instance_arg.pk, result.object_pk)
        self.assertEqual(list(sheets_arg), [persona.character_sheet])


class IssueMissionBeatLinkTests(TestCase):
    def test_unstaked_linked_beat_sets_source_beat_no_ack(self):
        _character, persona = _make_pc()
        offer, _template = _make_mission_offer(risk_tier=MISSION_RISK_ACK_TIER - 1)
        beat = BeatFactory(risk=RenownRisk.NONE)
        details = offer.mission_offer_details
        details.source_beat = beat
        details.save(update_fields=["source_beat"])

        result = issue_mission(offer, persona)  # no ack: unstaked + low tier

        instance = MissionInstance.objects.get(pk=result.object_pk)
        self.assertEqual(instance.source_beat_id, beat.pk)
