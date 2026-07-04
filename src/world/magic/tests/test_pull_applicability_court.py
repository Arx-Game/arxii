"""Tests for the COURT_LEADER_NO_STAKE picker inapplicability signal (#1831 Task 6).

A COVENANT_ROLE thread pull only gets a Court-leader-regard EMPOWERMENT bonus
(see ``court_regard_modulation``) when some candidate effect's polarity matches
the leader's signed regard sign for the live target. When none would be
empowered — leader indifferent (regard 0), or every candidate effect's
polarity mismatches the regard sign — the picker should flag the thread as
inapplicable so the player doesn't burn resonance expecting a boost that
won't happen. The label must stay generic (never leak the leader or the
opinion's sign).
"""

from __future__ import annotations

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.covenants.constants import CovenantType
from world.covenants.factories import (
    CharacterCovenantRoleFactory,
    CovenantFactory,
    CovenantRoleFactory,
)
from world.magic.constants import InapplicabilityReason, RegardPolarity, TargetKind
from world.magic.factories import ThreadFactory, ThreadPullEffectFactory
from world.magic.services.pull_applicability import (
    PullActionContext,
    compute_thread_applicability,
)
from world.npc_services.factories import NpcRegardFactory
from world.scenes.services import active_persona_for_sheet


def _context(target_persona_id: int | None) -> PullActionContext:
    return PullActionContext(
        technique=None,
        effect_type_id=None,
        target_persona_id=target_persona_id,
        scene_id=None,
    )


class CourtLeaderNoStakeApplicabilityTests(TestCase):
    """Applicability rule for COVENANT_ROLE threads gated on Court-leader regard."""

    def _setup_leader_and_role(self) -> tuple:
        leader_sheet = CharacterSheetFactory()
        covenant = CovenantFactory(covenant_type=CovenantType.COURT, leader=leader_sheet)
        role = CovenantRoleFactory(covenant_type=CovenantType.COURT)
        return leader_sheet, covenant, role

    def _servant_thread(self, *, covenant, role, engaged: bool = True) -> object:
        servant = CharacterSheetFactory()
        CharacterCovenantRoleFactory(
            character_sheet=servant,
            covenant=covenant,
            covenant_role=role,
            engaged=engaged,
        )
        return ThreadFactory(
            owner=servant,
            target_kind=TargetKind.COVENANT_ROLE,
            target_covenant_role=role,
            target_trait=None,
        )

    def _regard(self, *, leader_sheet, target_sheet, value: int) -> None:
        NpcRegardFactory(
            holder_persona=active_persona_for_sheet(leader_sheet),
            target_persona=active_persona_for_sheet(target_sheet),
            value=value,
        )

    def test_offensive_only_thread_inapplicable_vs_positive_regard_ally(self) -> None:
        leader_sheet, covenant, role = self._setup_leader_and_role()
        thread = self._servant_thread(covenant=covenant, role=role)
        ThreadPullEffectFactory(
            target_kind=TargetKind.COVENANT_ROLE,
            resonance=thread.resonance,
            regard_polarity=RegardPolarity.OFFENSIVE,
        )
        target_sheet = CharacterSheetFactory()
        self._regard(leader_sheet=leader_sheet, target_sheet=target_sheet, value=500)
        context = _context(active_persona_for_sheet(target_sheet).pk)

        rows = compute_thread_applicability(thread.owner, context)

        self.assertEqual(len(rows), 1)
        self.assertFalse(rows[0].applicable)
        self.assertEqual(rows[0].reason, InapplicabilityReason.COURT_LEADER_NO_STAKE.value)

    def test_offensive_only_thread_inapplicable_vs_indifferent_target(self) -> None:
        _leader_sheet, covenant, role = self._setup_leader_and_role()
        thread = self._servant_thread(covenant=covenant, role=role)
        ThreadPullEffectFactory(
            target_kind=TargetKind.COVENANT_ROLE,
            resonance=thread.resonance,
            regard_polarity=RegardPolarity.OFFENSIVE,
        )
        target_sheet = CharacterSheetFactory()  # no NpcRegard row -> regard 0
        context = _context(active_persona_for_sheet(target_sheet).pk)

        rows = compute_thread_applicability(thread.owner, context)

        self.assertEqual(len(rows), 1)
        self.assertFalse(rows[0].applicable)
        self.assertEqual(rows[0].reason, InapplicabilityReason.COURT_LEADER_NO_STAKE.value)

    def test_offensive_only_thread_applicable_vs_negative_regard_target(self) -> None:
        leader_sheet, covenant, role = self._setup_leader_and_role()
        thread = self._servant_thread(covenant=covenant, role=role)
        ThreadPullEffectFactory(
            target_kind=TargetKind.COVENANT_ROLE,
            resonance=thread.resonance,
            regard_polarity=RegardPolarity.OFFENSIVE,
        )
        target_sheet = CharacterSheetFactory()
        self._regard(leader_sheet=leader_sheet, target_sheet=target_sheet, value=-500)
        context = _context(active_persona_for_sheet(target_sheet).pk)

        rows = compute_thread_applicability(thread.owner, context)

        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0].applicable)
        self.assertIsNone(rows[0].reason)

    def test_neutral_effect_thread_applicable_vs_any_nonzero_regard(self) -> None:
        leader_sheet, covenant, role = self._setup_leader_and_role()
        thread = self._servant_thread(covenant=covenant, role=role)
        ThreadPullEffectFactory(
            target_kind=TargetKind.COVENANT_ROLE,
            resonance=thread.resonance,
            regard_polarity=RegardPolarity.NEUTRAL,
        )
        target_sheet = CharacterSheetFactory()
        self._regard(leader_sheet=leader_sheet, target_sheet=target_sheet, value=200)
        context = _context(active_persona_for_sheet(target_sheet).pk)

        rows = compute_thread_applicability(thread.owner, context)

        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0].applicable)
        self.assertIsNone(rows[0].reason)

    def test_neutral_effect_thread_inapplicable_vs_indifferent_target(self) -> None:
        _leader_sheet, covenant, role = self._setup_leader_and_role()
        thread = self._servant_thread(covenant=covenant, role=role)
        ThreadPullEffectFactory(
            target_kind=TargetKind.COVENANT_ROLE,
            resonance=thread.resonance,
            regard_polarity=RegardPolarity.NEUTRAL,
        )
        target_sheet = CharacterSheetFactory()  # no regard row -> 0
        context = _context(active_persona_for_sheet(target_sheet).pk)

        rows = compute_thread_applicability(thread.owner, context)

        self.assertEqual(len(rows), 1)
        self.assertFalse(rows[0].applicable)
        self.assertEqual(rows[0].reason, InapplicabilityReason.COURT_LEADER_NO_STAKE.value)

    def test_non_covenant_role_thread_unaffected(self) -> None:
        """A TRAIT-kind thread never gets the new reason, regardless of target_persona_id."""
        sheet = CharacterSheetFactory()
        ThreadFactory(owner=sheet)  # TRAIT kind
        target_sheet = CharacterSheetFactory()
        context = _context(active_persona_for_sheet(target_sheet).pk)

        rows = compute_thread_applicability(sheet, context)

        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0].applicable)
        self.assertIsNone(rows[0].reason)

    def test_no_target_persona_id_unaffected(self) -> None:
        """No target_persona_id in context -> COVENANT_ROLE thread stays applicable."""
        _leader_sheet, covenant, role = self._setup_leader_and_role()
        thread = self._servant_thread(covenant=covenant, role=role)
        ThreadPullEffectFactory(
            target_kind=TargetKind.COVENANT_ROLE,
            resonance=thread.resonance,
            regard_polarity=RegardPolarity.OFFENSIVE,
        )
        context = _context(None)

        rows = compute_thread_applicability(thread.owner, context)

        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0].applicable)
        self.assertIsNone(rows[0].reason)

    def test_no_leader_resolvable_unaffected(self) -> None:
        """No engaged Court leader -> base pull is unmodulated; not flagged as no-stake."""
        servant = CharacterSheetFactory()
        covenant = CovenantFactory(covenant_type=CovenantType.COURT, leader=None)
        role = CovenantRoleFactory(covenant_type=CovenantType.COURT)
        CharacterCovenantRoleFactory(
            character_sheet=servant, covenant=covenant, covenant_role=role, engaged=True
        )
        thread = ThreadFactory(
            owner=servant,
            target_kind=TargetKind.COVENANT_ROLE,
            target_covenant_role=role,
            target_trait=None,
        )
        ThreadPullEffectFactory(
            target_kind=TargetKind.COVENANT_ROLE,
            resonance=thread.resonance,
            regard_polarity=RegardPolarity.OFFENSIVE,
        )
        target_sheet = CharacterSheetFactory()
        context = _context(active_persona_for_sheet(target_sheet).pk)

        rows = compute_thread_applicability(servant, context)

        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0].applicable)
        self.assertIsNone(rows[0].reason)
