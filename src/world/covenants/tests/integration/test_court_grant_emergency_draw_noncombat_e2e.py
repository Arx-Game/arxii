"""E2E: ``beseech=`` also works on a non-combat cast (#1718 review fix).

Sibling of ``test_court_grant_emergency_draw_e2e.py``, which proves the
in-combat entry point (``commit_combat_pull``). A task-8 review found that the
*non-combat* immediate-cast entry point — ``request_technique_cast`` (the seam
telnet ``cast``/``declare`` outside combat converges on, via
``CastTechniqueAction.execute`` → ``use_technique`` →
``world.magic.services.techniques._charge_cast_pull``) — silently dropped
``CastPullDeclaration.beseech_bonus``: it built its ``PullActionContext`` and
called ``spend_resonance_for_pull`` without ever invoking
``world.combat.pull_helpers._resolve_emergency_draw``, so a non-combat
``beseech=N`` cast rolled no petition check, granted no bonus, and gave the
player no error — a silent no-op.

This test exercises the fixed non-combat path directly (no
``CombatEncounter``/``CombatParticipant`` at all) and asserts the identical
observable outcomes the combat E2E test asserts: the bonus never persists to
``Thread.level``, a successful petition applies the bonus and (when it exceeds
the servant's ``court_grant_ceiling``) incurs NPC debt, and a failed petition
still commits the base pull with no bonus and no debt.
"""

from __future__ import annotations

from evennia.utils.idmapper import models as idmapper_models

from world.character_sheets.factories import CharacterSheetFactory
from world.checks.test_helpers import force_check_outcome
from world.covenants.constants import CovenantType
from world.covenants.factories import (
    CovenantFactory,
    make_engaged_member,
    wire_court_grant_petition_content,
    wire_court_role_powers_catalog,
)
from world.covenants.services import swear_court_pact
from world.magic.constants import TargetKind
from world.magic.factories import CharacterResonanceFactory, ThreadPullCostFactory
from world.magic.models import Thread
from world.magic.services.resonance import spend_resonance_for_imbuing
from world.magic.types.pull import CastPullDeclaration
from world.npc_services.models import NPCStanding
from world.scenes.action_constants import ActionRequestStatus
from world.scenes.cast_services import request_technique_cast
from world.scenes.tests.cast_test_helpers import (
    CastScenarioMixin,
    grant_technique,
    make_benign_castable_technique,
)
from world.traits.factories import CheckOutcomeFactory


class EmergencyDrawNonCombatE2ETests(CastScenarioMixin):
    """A ``beseech=N`` self-cast outside combat rolls the shared petition check."""

    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()

        cls.master_sheet = CharacterSheetFactory()
        cls.covenant = CovenantFactory(covenant_type=CovenantType.COURT, leader=cls.master_sheet)

        cls.role, cls.flat_bonus_rows = wire_court_role_powers_catalog()
        cls.resonance = cls.flat_bonus_rows[0].resonance

        swear_court_pact(
            covenant=cls.covenant, servant_sheet=cls.caster.character_sheet, granted_pull_cap=2
        )
        # Seat + engage the caster on the Court's role — required by
        # _anchor_in_action's COVENANT_ROLE branch before any pull is attempted
        # (mirrors the in-combat E2E fixture).
        make_engaged_member(
            character_sheet=cls.caster.character_sheet,
            covenant=cls.covenant,
            covenant_role=cls.role,
        )

        cls.thread = Thread.objects.create(
            owner=cls.caster.character_sheet,
            resonance=cls.resonance,
            target_kind=TargetKind.COVENANT_ROLE,
            target_covenant_role=cls.role,
            level=0,
            developed_points=0,
            name="Cord of the Shadowblade",
        )

        cls.character_resonance = CharacterResonanceFactory(
            character_sheet=cls.caster.character_sheet, resonance=cls.resonance, balance=20
        )
        ThreadPullCostFactory(tier=1, resonance_cost=1, anima_per_thread=0)

        # The FLAT_BONUS row (wire_court_role_powers_catalog) is authored at
        # min_thread_level=1 — the pull-effect eligibility check reads the thread's
        # REAL level (never the beseech-boosted effective level), so the thread
        # must actually be imbued to level 1 for there to be an applicable effect.
        spend_resonance_for_imbuing(cls.caster.character_sheet, cls.thread, 1)
        cls.thread.refresh_from_db()
        cls.starting_thread_level = cls.thread.level
        assert cls.starting_thread_level == 1

        # Wires CourtGrantConfig.petition_check_type — required or
        # _resolve_emergency_draw degrades to (None, 0).
        wire_court_grant_petition_content()

        cls.technique = make_benign_castable_technique()
        grant_technique(cls.caster, cls.technique)

    def setUp(self) -> None:
        super().setUp()
        idmapper_models.flush_cache()

    def _self_cast_with_beseech(self, *, beseech_bonus: int):
        declaration = CastPullDeclaration(
            resonance=self.resonance, tier=1, threads=(self.thread,), beseech_bonus=beseech_bonus
        )
        return request_technique_cast(
            scene=self.scene,
            initiator_persona=self.caster,
            technique=self.technique,
            cast_pull=declaration,
        )

    def test_over_ceiling_draw_applies_bonus_and_incurs_debt(self) -> None:
        success_outcome = CheckOutcomeFactory(name="beseech_success_noncombat", success_level=1)
        with force_check_outcome(success_outcome):
            cast = self._self_cast_with_beseech(beseech_bonus=8)

        self.assertEqual(cast.request.status, ActionRequestStatus.RESOLVED)

        self.thread.refresh_from_db()
        self.assertEqual(
            self.thread.level,
            self.starting_thread_level,
            "emergency bonus must never persist to Thread.level",
        )

        standing = NPCStanding.objects.get(
            persona=self.caster.character_sheet.primary_persona,
            npc_persona=self.master_sheet.primary_persona,
        )
        self.assertGreater(standing.debt, 0)
        self.assertEqual(
            standing.consecutive_failed_petitions,
            0,
            "A successful petition must reset the consecutive-failure streak.",
        )

    def test_failed_draw_commits_the_pull_with_no_bonus(self) -> None:
        """A failed petition check still resolves the cast, with no bonus applied."""
        failure_outcome = CheckOutcomeFactory(name="beseech_failure_noncombat", success_level=0)
        with force_check_outcome(failure_outcome):
            cast = self._self_cast_with_beseech(beseech_bonus=8)

        self.assertEqual(cast.request.status, ActionRequestStatus.RESOLVED)

        self.thread.refresh_from_db()
        self.assertEqual(self.thread.level, self.starting_thread_level)

        standing = NPCStanding.objects.get(
            persona=self.caster.character_sheet.primary_persona,
            npc_persona=self.master_sheet.primary_persona,
        )
        self.assertEqual(
            standing.debt, 0, "A failed emergency draw must not incur debt — no bonus applied."
        )
        self.assertEqual(standing.consecutive_failed_petitions, 1)

        # The base pull itself still commits (resonance debited) even though
        # the emergency bonus was denied. Starting balance 20, minus 1 already
        # spent imbuing the thread to level 1 in setUpTestData, minus this
        # pull's tier-1 cost of 1.
        self.character_resonance.refresh_from_db()
        self.assertEqual(self.character_resonance.balance, 20 - 1 - 1)
