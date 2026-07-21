"""E2E: a servant invokes the thread bond mid-pull for emergency aid (#1718).

Exercises the real ``commit_combat_pull`` seam (the same one ``cast``/``clash``
converge on) with a genuine ``CombatEncounter``/``CombatParticipant`` pair —
this is the emergency draw's actual entry point per the task brief: it rides
the existing pull-declaration grammar as an optional ``beseech=<n>`` token, so
the real seam to prove end-to-end is ``commit_combat_pull`` itself, not
``request_technique_cast`` (which has no pull-declaration surface of its own
beyond forwarding a pre-built ``CastPullDeclaration``).

Two real-fixture requirements the brief's sketch omitted (found by reading the
actual code, not guessing):

- ``CharacterSheetFactory`` already auto-provisions a PRIMARY persona per sheet
  (post_generation hook) — calling ``PersonaFactory(..., persona_type="primary")``
  again would collide with the partial-unique constraint. Use
  ``sheet.primary_persona`` instead (mirrors ``test_court_grant_petition_e2e.py``).
- ``swear_court_pact`` only creates the ``CourtPact`` row; it does NOT seat the
  servant on the Court's ``CovenantRole`` or engage it. ``_anchor_in_action``
  (``world/magic/services/resonance.py``) requires a COVENANT_ROLE thread's
  role to be among the owner's ``currently_engaged_roles()`` before a pull on
  it is even attempted — otherwise ``commit_combat_pull`` raises
  ``ActionDispatchError(PULL_INVALID)`` wrapping ``CovenantRoleNotEngagedError``
  before the emergency-draw code ever runs. ``make_engaged_member`` (the
  existing test helper built for exactly this "pull-eligibility" need) seats
  and engages the membership directly via ``set_engaged_membership``.
"""

from __future__ import annotations

from django.test import TestCase
from evennia.utils.idmapper import models as idmapper_models

from actions.factories import ConsequencePoolEntryFactory, ConsequencePoolFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.constants import EffectTarget, EffectType
from world.checks.factories import ConsequenceEffectFactory, ConsequenceFactory
from world.checks.test_helpers import force_check_outcome
from world.combat.constants import ParticipantStatus
from world.combat.factories import CombatEncounterFactory, CombatParticipantFactory
from world.combat.pull_helpers import commit_combat_pull
from world.conditions.factories import ConditionTemplateFactory
from world.conditions.services import get_condition_instance
from world.covenants.constants import CovenantType
from world.covenants.factories import (
    CovenantFactory,
    make_engaged_member,
    wire_court_grant_petition_content,
    wire_court_role_powers_catalog,
)
from world.covenants.services import get_court_grant_config, swear_court_pact
from world.magic.constants import TargetKind
from world.magic.factories import (
    CharacterAnimaFactory,
    CharacterResonanceFactory,
    ThreadPullCostFactory,
)
from world.magic.models import Thread
from world.magic.services.resonance import spend_resonance_for_imbuing
from world.magic.types.pull import CastPullDeclaration
from world.npc_services.models import NPCStanding
from world.scenes.constants import RoundStatus
from world.traits.factories import CheckOutcomeFactory


class EmergencyDrawE2ETests(TestCase):
    def setUp(self) -> None:
        idmapper_models.flush_cache()

        self.master_sheet = CharacterSheetFactory()
        self.covenant = CovenantFactory(covenant_type=CovenantType.COURT, leader=self.master_sheet)
        self.servant_sheet = CharacterSheetFactory()
        # CharacterSheetFactory auto-provisions a PRIMARY persona per sheet — reuse it
        # rather than creating a second PRIMARY persona, which would collide on the
        # partial unique constraint (mirrors test_court_grant_petition_e2e.py).

        self.role, self.flat_bonus_rows = wire_court_role_powers_catalog()
        self.resonance = self.flat_bonus_rows[0].resonance

        swear_court_pact(
            covenant=self.covenant, servant_sheet=self.servant_sheet, granted_pull_cap=2
        )
        # Seat + engage the servant on the Court's role — required by
        # _anchor_in_action's COVENANT_ROLE branch before any pull is attempted.
        make_engaged_member(
            character_sheet=self.servant_sheet,
            covenant=self.covenant,
            covenant_role=self.role,
        )

        self.thread = Thread.objects.create(
            owner=self.servant_sheet,
            resonance=self.resonance,
            target_kind=TargetKind.COVENANT_ROLE,
            target_covenant_role=self.role,
            level=0,
            developed_points=0,
            name="Cord of the Shadowblade",
        )

        CharacterResonanceFactory(
            character_sheet=self.servant_sheet, resonance=self.resonance, balance=20
        )
        CharacterAnimaFactory(character=self.servant_sheet.character, current=10, maximum=20)
        ThreadPullCostFactory(tier=1, resonance_cost=1, anima_per_thread=0)

        # wire_court_role_powers_catalog's FLAT_BONUS row is authored at
        # min_thread_level=1 (the pact-granted-cap IS the real gate, #1589 final
        # review) — the pull-effect eligibility check reads the thread's REAL
        # level (never the beseech-boosted effective level), so the thread must
        # actually be imbued to level 1 (within the pact's granted_pull_cap=2)
        # for there to be any applicable effect to scale at all. The emergency
        # draw only affects the multiplier of an ALREADY-unlocked effect.
        spend_resonance_for_imbuing(self.servant_sheet, self.thread, 1)
        self.thread.refresh_from_db()
        self.starting_thread_level = self.thread.level
        self.assertEqual(self.starting_thread_level, 1)

        # Wires CourtGrantConfig.petition_check_type — required by
        # _resolve_emergency_draw or it degrades to (None, 0).
        wire_court_grant_petition_content()

        self.encounter = CombatEncounterFactory(status=RoundStatus.DECLARING, round_number=1)
        self.participant = CombatParticipantFactory(
            encounter=self.encounter,
            character_sheet=self.servant_sheet,
            status=ParticipantStatus.ACTIVE,
        )

    def test_over_ceiling_draw_applies_bonus_and_incurs_debt(self) -> None:
        declaration = CastPullDeclaration(
            resonance=self.resonance, tier=1, threads=(self.thread,), beseech_bonus=8
        )
        success_outcome = CheckOutcomeFactory(name="beseech_success", success_level=1)
        with force_check_outcome(success_outcome):
            commit_combat_pull(declaration, self.participant, self.encounter, technique_id=0)

        self.thread.refresh_from_db()
        self.assertEqual(
            self.thread.level,
            self.starting_thread_level,
            "emergency bonus must never persist to Thread.level",
        )

        standing = NPCStanding.objects.get(
            persona=self.servant_sheet.primary_persona,
            npc_persona=self.master_sheet.primary_persona,
        )
        self.assertGreater(standing.debt, 0)
        self.assertEqual(
            standing.consecutive_failed_petitions,
            0,
            "A successful petition must reset the consecutive-failure streak.",
        )

    def test_failed_draw_commits_the_pull_with_no_bonus(self) -> None:
        """A failed petition check still commits the base pull, but with no bonus applied."""
        declaration = CastPullDeclaration(
            resonance=self.resonance, tier=1, threads=(self.thread,), beseech_bonus=8
        )
        failure_outcome = CheckOutcomeFactory(name="beseech_failure", success_level=0)
        with force_check_outcome(failure_outcome):
            commit_combat_pull(declaration, self.participant, self.encounter, technique_id=0)

        self.thread.refresh_from_db()
        self.assertEqual(self.thread.level, self.starting_thread_level)

        standing = NPCStanding.objects.get(
            persona=self.servant_sheet.primary_persona,
            npc_persona=self.master_sheet.primary_persona,
        )
        self.assertEqual(
            standing.debt, 0, "A failed emergency draw must not incur debt — no bonus applied."
        )
        self.assertEqual(standing.consecutive_failed_petitions, 1)

        # The base pull itself still commits (resonance debited) even though
        # the emergency bonus was denied.
        from world.combat.models import CombatPull

        self.assertTrue(
            CombatPull.objects.filter(
                participant=self.participant, round_number=self.encounter.round_number
            ).exists(),
            "The base pull must still commit even when the emergency draw fails.",
        )

    def test_combat_emergency_draw_threads_situation_ctx(self) -> None:
        """#2536 Task 5 review fix: the combat emergency-draw petition check must
        thread a live SituationContext into perform_check.

        The combat call site (commit_combat_pull) has participant + encounter on
        hand, so a CHECK_BONUS situational perk scoped to the Court petition
        CheckType (spec §4's named use case) must be able to fire — which it
        cannot unless the resolution context reaches perform_check. Spies on the
        real perform_check (wrapped, not stubbed) and asserts the threaded
        SituationContext carries a live CombatRoundContext for this participant.
        """
        from unittest.mock import patch

        from world.checks import services as checks_services
        from world.combat.round_context import CombatRoundContext
        from world.covenants.perks.context import SituationContext

        declaration = CastPullDeclaration(
            resonance=self.resonance, tier=1, threads=(self.thread,), beseech_bonus=8
        )
        success_outcome = CheckOutcomeFactory(name="beseech_ctx_success", success_level=1)
        real_perform_check = checks_services.perform_check
        with (
            force_check_outcome(success_outcome),
            patch("world.checks.services.perform_check", wraps=real_perform_check) as spy,
        ):
            commit_combat_pull(declaration, self.participant, self.encounter, technique_id=0)

        config = get_court_grant_config()
        petition_calls = [
            call
            for call in spy.call_args_list
            if len(call.args) > 1 and call.args[1] == config.petition_check_type
        ]
        self.assertEqual(
            len(petition_calls), 1, "the emergency draw rolls the petition check exactly once"
        )
        situation_ctx = petition_calls[0].kwargs.get("situation_ctx")
        self.assertIsInstance(
            situation_ctx,
            SituationContext,
            "the combat petition check must thread a SituationContext (was never wired)",
        )
        self.assertEqual(situation_ctx.holder, self.servant_sheet)
        self.assertEqual(situation_ctx.subject, self.servant_sheet)
        self.assertIsNone(
            situation_ctx.target,
            "a Court-favor petition is not directed at the pull's combat target",
        )
        self.assertIsInstance(situation_ctx.resolution, CombatRoundContext)
        self.assertEqual(situation_ctx.resolution.participant, self.participant)

    def test_escalation_pool_fires_after_consecutive_failure_threshold(self) -> None:
        """Regression (#1718 final-review Finding 2).

        The emergency-draw channel must fire the master's escalation
        ConsequencePool on threshold-crossing exactly like the formal petition
        channel does (mirrors the analogous test in
        ``test_court_grant_petition_e2e.py``) — previously it recorded the
        failure streak but never fired escalation.
        """
        condition = ConditionTemplateFactory(name="Master's Wrath")
        failure_outcome = CheckOutcomeFactory(name="beseech_wrath_failure", success_level=0)
        consequence = ConsequenceFactory(outcome_tier=failure_outcome)
        ConsequenceEffectFactory(
            consequence=consequence,
            effect_type=EffectType.APPLY_CONDITION,
            target=EffectTarget.SELF,
            condition_template=condition,
            condition_severity=1,
        )
        pool = ConsequencePoolFactory()
        ConsequencePoolEntryFactory(pool=pool, consequence=consequence)

        config = get_court_grant_config()
        config.petition_failure_escalation_threshold = 1
        config.escalation_consequence_pool = pool
        config.save(
            update_fields=["petition_failure_escalation_threshold", "escalation_consequence_pool"]
        )

        declaration = CastPullDeclaration(
            resonance=self.resonance, tier=1, threads=(self.thread,), beseech_bonus=8
        )
        with force_check_outcome(failure_outcome):
            commit_combat_pull(declaration, self.participant, self.encounter, technique_id=0)

        instance = get_condition_instance(self.servant_sheet.character, condition)
        self.assertIsNotNone(
            instance,
            "the master's escalation ConsequencePool must fire via the emergency-draw"
            " channel too, not only the formal petition channel",
        )
