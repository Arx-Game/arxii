"""Tests for interpose cost-on-fire and DEFEND + INTERPOSE composition (#1273, Task 7).

Three assertions:
(a) An interpose that **fires** charges the interposer's fatigue pool (cost-on-fire).
(b) An armed-but-never-triggered interpose costs nothing (readiness is free).
(c) A shielded ally (DEFEND halves) who is also covered by a fired INTERPOSE has
    both reductions applied on the same hit: amount → halved by DEFEND → further
    reduced by INTERPOSE.

Pipeline order (deterministic):
    emit_event(DAMAGE_PRE_APPLY) → DEFEND MODIFY_PAYLOAD fires (× 0.5)
    → emit_event returns
    → _try_interpose fires (dispatches challenge, applies outcome_fn)
    → apply_fatigue on interposer (only if result is not None)

Tagged @tag("postgres"): apply_condition (capability grant) uses DISTINCT ON in
get_available_actions, which is PG-only. SQLite-safe unit tests are untagged.
"""

from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase, tag

from world.combat.constants import (
    INTERPOSE_BASE_FATIGUE_COST,
    ActionCategory,
    CombatManeuver,
    ParticipantStatus,
)
from world.combat.factories import (
    CombatEncounterFactory,
    CombatParticipantFactory,
    CombatRoundAction,
)
from world.combat.interpose_content import ensure_interpose_content
from world.combat.services import apply_damage_to_participant
from world.fatigue.constants import EffortLevel
from world.fatigue.models import FatiguePool
from world.scenes.constants import RoundStatus
from world.vitals.models import CharacterVitals

# ---------------------------------------------------------------------------
# Shared helper
# ---------------------------------------------------------------------------


def _make_vitals(participant, health: int = 100, max_health: int = 100) -> CharacterVitals:
    vitals, _ = CharacterVitals.objects.get_or_create(
        character_sheet=participant.character_sheet,
        defaults={"health": health, "max_health": max_health},
    )
    vitals.health = health
    vitals.max_health = max_health
    vitals.save()
    return vitals


def _guardian_fatigue(guardian_participant) -> int:
    """Return current physical fatigue for the guardian (0 if no pool yet)."""
    pool = FatiguePool.objects.filter(character_sheet=guardian_participant.character_sheet).first()
    if pool is None:
        return 0
    return pool.get_current(ActionCategory.PHYSICAL)


# ---------------------------------------------------------------------------
# (b) SQLite-safe: armed-but-never-triggered interpose → no fatigue charge
# ---------------------------------------------------------------------------


class InterposeArmedButNotFiredCostsNothingTest(TestCase):
    """An INTERPOSE declaration that never fires must not accrue fatigue.

    We set up an INTERPOSE CombatRoundAction but never call _try_interpose
    (the encounter is DECLARING, not RESOLVING, so the guard short-circuits).
    The guardian's fatigue pool must remain at 0.
    """

    def setUp(self) -> None:
        from evennia.utils.idmapper import models as idmapper_models

        idmapper_models.flush_cache()
        ensure_interpose_content()

        self.encounter = CombatEncounterFactory(status=RoundStatus.DECLARING, round_number=1)
        self.guardian_participant = CombatParticipantFactory(
            encounter=self.encounter, status=ParticipantStatus.ACTIVE
        )
        self.ally_participant = CombatParticipantFactory(
            encounter=self.encounter, status=ParticipantStatus.ACTIVE
        )
        _make_vitals(self.guardian_participant)
        _make_vitals(self.ally_participant)

        # Declare INTERPOSE — but encounter is DECLARING, so it can never fire.
        CombatRoundAction.objects.create(
            participant=self.guardian_participant,
            round_number=1,
            maneuver=CombatManeuver.INTERPOSE,
            focused_ally_target=self.ally_participant,
            is_ready=True,
        )

    def test_armed_interpose_charges_no_fatigue(self) -> None:
        """A declared-but-unfired INTERPOSE must leave the guardian's fatigue at 0."""
        # The encounter is DECLARING → apply_damage_to_participant would guard out
        # of _try_interpose before it queries CombatRoundAction, so fatigue is 0.
        # apply_damage_to_participant: encounter is DECLARING so _try_interpose no-ops.
        apply_damage_to_participant(self.ally_participant, 40)

        self.assertEqual(
            _guardian_fatigue(self.guardian_participant),
            0,
            "An armed-but-unfired INTERPOSE must not charge the guardian any fatigue.",
        )


# ---------------------------------------------------------------------------
# (a) PG-only: fired interpose charges fatigue; (c) DEFEND + INTERPOSE compose
# ---------------------------------------------------------------------------


@tag("postgres")  # get_available_actions uses DISTINCT ON → PG-only
class InterposeFiredChargesFatigueTest(TestCase):
    """A fired INTERPOSE charges the interposer's physical fatigue pool.

    The check is mocked (clean-block SUCCESS) so the test is deterministic.
    We verify the guardian's FatiguePool.physical_current > 0 after the fire.
    """

    def setUp(self) -> None:
        from evennia import create_object
        from evennia.utils.idmapper import models as idmapper_models

        from world.character_sheets.factories import CharacterSheetFactory
        from world.conditions.factories import (
            ConditionCapabilityEffectFactory,
            ConditionTemplateFactory,
        )
        from world.conditions.models import CapabilityType
        from world.conditions.services import apply_condition
        from world.mechanics.models import ChallengeInstance, ChallengeTemplate
        from world.traits.factories import CheckSystemSetupFactory
        from world.traits.models import ResultChart

        idmapper_models.flush_cache()
        ensure_interpose_content()
        CheckSystemSetupFactory.create()
        ResultChart.clear_cache()

        self.room = create_object("typeclasses.rooms.Room", key="CostTestRoom", nohome=True)
        self.encounter = CombatEncounterFactory(
            status=RoundStatus.RESOLVING,
            round_number=1,
            room=self.room,
        )

        guardian_sheet = CharacterSheetFactory()
        self.guardian_participant = CombatParticipantFactory(
            encounter=self.encounter,
            character_sheet=guardian_sheet,
            status=ParticipantStatus.ACTIVE,
        )
        self.guardian = guardian_sheet.character
        self.guardian.db_location = self.room
        self.guardian.save(update_fields=["db_location"])

        ally_sheet = CharacterSheetFactory()
        self.ally_participant = CombatParticipantFactory(
            encounter=self.encounter,
            character_sheet=ally_sheet,
            status=ParticipantStatus.ACTIVE,
        )
        self.ally = ally_sheet.character
        self.ally.db_location = self.room
        self.ally.save(update_fields=["db_location"])

        telekinesis = CapabilityType.objects.get(name="telekinesis")
        grant_template = ConditionTemplateFactory(name="TKGuardFatigue")
        ConditionCapabilityEffectFactory(condition=grant_template, capability=telekinesis, value=10)
        apply_condition(self.guardian, grant_template)

        _make_vitals(self.ally_participant, health=100, max_health=100)
        _make_vitals(self.guardian_participant, health=100, max_health=100)

        self.interpose_action = CombatRoundAction.objects.create(
            participant=self.guardian_participant,
            round_number=1,
            maneuver=CombatManeuver.INTERPOSE,
            focused_ally_target=self.ally_participant,
            is_ready=True,
            effort_level=EffortLevel.MEDIUM,
        )

        template = ChallengeTemplate.objects.get(name="Interpose")
        ChallengeInstance.objects.get_or_create(
            template=template,
            target_object=self.ally,
            is_active=True,
            defaults={"location": self.room, "is_revealed": True},
        )

    @patch("world.mechanics.challenge_resolution.perform_check")
    def test_fired_interpose_charges_fatigue(self, mock_check) -> None:
        """A fired INTERPOSE accrues physical fatigue on the guardian."""
        from world.checks.types import CheckResult
        from world.traits.factories import CheckOutcomeFactory

        success = CheckOutcomeFactory(name="CostCleanBlock", success_level=2)
        mock_check.return_value = CheckResult(
            check_type=None,
            outcome=success,
            chart=None,
            roller_rank=None,
            target_rank=None,
            rank_difference=0,
            trait_points=0,
            aspect_bonus=0,
            total_points=0,
        )

        # guardian fatigue is 0 before the fire
        FatiguePool.flush_instance_cache()
        self.assertEqual(
            _guardian_fatigue(self.guardian_participant),
            0,
            "Guardian fatigue must be 0 before any action.",
        )

        apply_damage_to_participant(self.ally_participant, 40)

        FatiguePool.flush_instance_cache()
        fatigue_after = _guardian_fatigue(self.guardian_participant)
        self.assertGreater(
            fatigue_after,
            0,
            "A fired INTERPOSE must charge the guardian's physical fatigue pool.",
        )

    @patch("world.mechanics.challenge_resolution.perform_check")
    def test_unfired_interpose_charges_no_fatigue(self, mock_check) -> None:
        """Patch _try_interpose to skip firing; guardian fatigue must stay 0."""
        # If the encounter has no room (no emit_event), _try_interpose still runs
        # but dispatch_interpose returns None → no fatigue charged.
        with patch("world.combat.services.dispatch_interpose", return_value=None):
            apply_damage_to_participant(self.ally_participant, 40)

        FatiguePool.flush_instance_cache()
        self.assertEqual(
            _guardian_fatigue(self.guardian_participant),
            0,
            "When dispatch_interpose returns None, no fatigue must be charged.",
        )
        mock_check.assert_not_called()


@tag("postgres")  # apply_condition uses DISTINCT ON → PG-only
class DefendAndInterposeBothReduceDamageTest(TestCase):
    """DEFEND (Shielded × 0.5) and a fired INTERPOSE both reduce damage on the same hit.

    Pipeline:
        emit_event(DAMAGE_PRE_APPLY) → Shielded MODIFY_PAYLOAD × 0.5 → returns
        → _try_interpose dispatches → INTERPOSE partial (success_level=0) → // 2
        → effective damage = original // 2 // 2

    With raw_damage = 40:
        DEFEND halves → 20
        INTERPOSE partial halves → 10
        ally health: 100 - 10 = 90

    With a clean-block INTERPOSE (success_level=2):
        DEFEND halves → 20
        INTERPOSE clean → 0
        ally health: 100 (unchanged)

    This test uses the partial (success_level=0) branch to exercise both effects
    visibly, and a separate method uses the clean-block branch for the zero-damage case.

    Guardian is NOT double-charged: only the interpose's own fatigue fires;
    the DEFEND passive costs nothing (it charges on the caster's own attack action,
    not on the reactive halve step).
    """

    NPC_RAW_DAMAGE = 40

    def setUp(self) -> None:
        from evennia import create_object
        from evennia.utils.idmapper import models as idmapper_models

        from world.character_sheets.factories import CharacterSheetFactory
        from world.conditions.factories import (
            ConditionCapabilityEffectFactory,
            ConditionTemplateFactory,
        )
        from world.conditions.models import CapabilityType
        from world.conditions.services import apply_condition
        from world.mechanics.models import ChallengeInstance, ChallengeTemplate
        from world.traits.factories import CheckSystemSetupFactory
        from world.traits.models import ResultChart

        idmapper_models.flush_cache()
        ensure_interpose_content()

        from world.combat.defend_content import ensure_defend_content

        ensure_defend_content()
        CheckSystemSetupFactory.create()
        ResultChart.clear_cache()

        self.room = create_object("typeclasses.rooms.Room", key="ComposeTestRoom", nohome=True)
        self.encounter = CombatEncounterFactory(
            status=RoundStatus.RESOLVING,
            round_number=1,
            room=self.room,
        )

        # Guardian: declares INTERPOSE (and will be the "Shielded" condition recipient
        # in the DEFEND scenario — but here, the ally is the one shielded).
        guardian_sheet = CharacterSheetFactory()
        self.guardian_participant = CombatParticipantFactory(
            encounter=self.encounter,
            character_sheet=guardian_sheet,
            status=ParticipantStatus.ACTIVE,
        )
        self.guardian = guardian_sheet.character
        self.guardian.db_location = self.room
        self.guardian.save(update_fields=["db_location"])

        # Ally: the protected target (will be shielded by DEFEND AND covered by INTERPOSE).
        ally_sheet = CharacterSheetFactory()
        self.ally_participant = CombatParticipantFactory(
            encounter=self.encounter,
            character_sheet=ally_sheet,
            status=ParticipantStatus.ACTIVE,
        )
        self.ally = ally_sheet.character
        self.ally.db_location = self.room
        self.ally.save(update_fields=["db_location"])

        # Grant guardian telekinesis for the interpose capability.
        telekinesis = CapabilityType.objects.get(name="telekinesis")
        grant_template = ConditionTemplateFactory(name="TKGuardCompose")
        ConditionCapabilityEffectFactory(condition=grant_template, capability=telekinesis, value=10)
        apply_condition(self.guardian, grant_template)

        # Ally vitals.
        self.ally_vitals = _make_vitals(self.ally_participant, health=100, max_health=100)
        _make_vitals(self.guardian_participant, health=100, max_health=100)

        # Declare INTERPOSE for Ally this round.
        CombatRoundAction.objects.create(
            participant=self.guardian_participant,
            round_number=1,
            maneuver=CombatManeuver.INTERPOSE,
            focused_ally_target=self.ally_participant,
            is_ready=True,
            effort_level=EffortLevel.MEDIUM,
        )

        # Pre-bind the Interpose ChallengeInstance to Ally.
        template = ChallengeTemplate.objects.get(name="Interpose")
        ChallengeInstance.objects.get_or_create(
            template=template,
            target_object=self.ally,
            is_active=True,
            defaults={"location": self.room, "is_revealed": True},
        )

        # Install the Shielded condition on Ally directly (bypasses DEFEND passive
        # technique so this test doesn't depend on the resolve_round passive path).
        from world.conditions.models import ConditionTemplate
        from world.conditions.services import apply_condition

        shielded_template = ConditionTemplate.objects.get(name="Shielded")
        apply_condition(self.ally, shielded_template)

        # apply_condition installs the Shielded reactive Trigger and calls
        # TriggerHandler.on_trigger_added → invalidate(), which defers the cache
        # reset to transaction.on_commit. Inside this TestCase's never-committed
        # atomic transaction that callback never runs, so the ally's already-
        # populated (empty) trigger cache would hide the new trigger from the
        # DAMAGE_PRE_APPLY emit below — and DEFEND's ×0.5 would never fire.
        # Production avoids this via resolve_round's _refresh_participant_trigger_
        # handlers; mirror that here with a synchronous refresh so the freshly
        # installed trigger is visible within this same transaction.
        ally_trigger_handler = self.ally.trigger_handler
        if ally_trigger_handler is not None:
            ally_trigger_handler.refresh()

    @patch("world.mechanics.challenge_resolution.perform_check")
    def test_defend_and_interpose_partial_compose(self, mock_check) -> None:
        """DEFEND (×0.5) then INTERPOSE partial (//2) both reduce ally health.

        40 → (Shielded ×0.5) → 20 → (INTERPOSE partial //2) → 10.
        Ally health: 100 - 10 = 90.
        """
        from world.checks.types import CheckResult
        from world.traits.factories import CheckOutcomeFactory

        # partial: success_level == 0 → pre_payload.amount //= 2
        partial_outcome = CheckOutcomeFactory(name="ComposePartial", success_level=0)
        mock_check.return_value = CheckResult(
            check_type=None,
            outcome=partial_outcome,
            chart=None,
            roller_rank=None,
            target_rank=None,
            rank_difference=0,
            trait_points=0,
            aspect_bonus=0,
            total_points=0,
        )

        result = apply_damage_to_participant(self.ally_participant, self.NPC_RAW_DAMAGE)

        self.ally_vitals.refresh_from_db()
        health_drop = 100 - self.ally_vitals.health

        # DEFEND halves: 40 → 20; INTERPOSE partial halves: 20 → 10.
        expected_drop = (self.NPC_RAW_DAMAGE // 2) // 2  # 10
        self.assertEqual(
            health_drop,
            expected_drop,
            f"DEFEND (×0.5) then INTERPOSE partial (//2) must reduce {self.NPC_RAW_DAMAGE} → "
            f"{self.NPC_RAW_DAMAGE // 2} → {expected_drop}; got health_drop={health_drop}.",
        )
        self.assertEqual(
            result.damage_dealt,
            expected_drop,
            "damage_dealt must match the doubly-reduced amount.",
        )

    @patch("world.mechanics.challenge_resolution.perform_check")
    def test_defend_and_interpose_clean_compose(self, mock_check) -> None:
        """DEFEND (×0.5) then INTERPOSE clean block → 0 damage; ally health unchanged.

        40 → (Shielded ×0.5) → 20 → (INTERPOSE clean block) → 0.
        """
        from world.checks.types import CheckResult
        from world.traits.factories import CheckOutcomeFactory

        clean_outcome = CheckOutcomeFactory(name="ComposeClean", success_level=2)
        mock_check.return_value = CheckResult(
            check_type=None,
            outcome=clean_outcome,
            chart=None,
            roller_rank=None,
            target_rank=None,
            rank_difference=0,
            trait_points=0,
            aspect_bonus=0,
            total_points=0,
        )

        result = apply_damage_to_participant(self.ally_participant, self.NPC_RAW_DAMAGE)

        self.ally_vitals.refresh_from_db()
        self.assertEqual(
            self.ally_vitals.health,
            100,
            "DEFEND + clean INTERPOSE must leave ally at full health.",
        )
        self.assertEqual(result.damage_dealt, 0, "damage_dealt must be 0 for a clean block.")

    @patch("world.mechanics.challenge_resolution.perform_check")
    def test_guardian_charged_once_not_double_charged(self, mock_check) -> None:
        """The guardian's fatigue is charged exactly once (for the interpose), not twice.

        DEFEND is a passive condition — it has no fatigue cost on the trigger step.
        Only the INTERPOSE fire charges fatigue on the guardian.
        """
        from world.checks.types import CheckResult
        from world.traits.factories import CheckOutcomeFactory

        partial_outcome = CheckOutcomeFactory(name="ComposePartialCharge", success_level=0)
        mock_check.return_value = CheckResult(
            check_type=None,
            outcome=partial_outcome,
            chart=None,
            roller_rank=None,
            target_rank=None,
            rank_difference=0,
            trait_points=0,
            aspect_bonus=0,
            total_points=0,
        )

        FatiguePool.flush_instance_cache()
        pre_fatigue = _guardian_fatigue(self.guardian_participant)

        apply_damage_to_participant(self.ally_participant, self.NPC_RAW_DAMAGE)

        FatiguePool.flush_instance_cache()
        post_fatigue = _guardian_fatigue(self.guardian_participant)
        fatigue_delta = post_fatigue - pre_fatigue

        # MEDIUM effort multiplier = 1.0 → actual cost = INTERPOSE_BASE_FATIGUE_COST
        # (with MIN_FATIGUE_COST=1 this is max(1, 3*1.0)=3)
        self.assertGreater(fatigue_delta, 0, "Guardian must be charged fatigue for firing.")
        # Guard against double-charge: only one interpose action was declared.
        # The DEFEND reactive trigger (MODIFY_PAYLOAD) does NOT charge the guardian.
        self.assertEqual(
            fatigue_delta,
            INTERPOSE_BASE_FATIGUE_COST,
            f"Guardian must be charged exactly {INTERPOSE_BASE_FATIGUE_COST} fatigue "
            f"at MEDIUM effort (×1.0); got {fatigue_delta}.",
        )
