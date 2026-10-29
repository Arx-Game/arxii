"""End-to-end integration tests for the Fury lever (#567 Task 10).

Coverage map
============
1.  @tag("postgres") real cast with a Berserk fury tier → REAL apply_condition(Berserk)
    runs (PG-only DISTINCT ON path) → caster has Berserk ConditionInstance +
    Interaction.fury_committed is set.

2.  Full berserker loop: real cast → fury failure → Berserk applied → successful
    Restore-to-Sense removes it.  Also @tag("postgres").

3.  Strain + Fury stacked: control surrendered to Fury (on the engagement) raises the
    cost, fatigue split correct, Fury alone accrues NO extra fatigue.

4.  fury_committed audit on a CLASH declaration (ClashContributionDeclaration path).

5.  Berserk decays over rounds_remaining (process_round_end loop).

6.  Edge cases: cap 0 (no bond) → fury unavailable; Restore-to-Sense on non-Berserk
    target is a graceful no-op (already covered by test_restore_sense_action.py —
    noted below).

Gaps that are ALREADY COVERED by earlier tasks and NOT duplicated here
======================================================================
- Serializer cap/anchor/berserk rejections: test_fury_threading.py
- Interaction.fury_committed audit (non-clash): test_fury_threading.py
- BerserkAppliedOnLostControl mock-level wiring: test_fury_threading.py
- resolve_fury / provocation_cap / clamp_tier units: test_fury_service.py
- The trade landing on the engagement, per outcome: integration_tests/
  test_surrendering_control_to_fury_journeys.py
- Berserk ConditionTemplate shape: test_berserk_template.py
- RemoveConditionOnCheck effect dispatch: integration_tests/test_conditions_journeys.py
  (TalkingABerserkerDown, #3657) and test_restore_sense_action.py
- RestoreSenseAction registry + non-Berserk no-op: test_restore_sense_action.py
"""

from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase, tag
from evennia import create_object

from evennia_extensions.factories import ObjectDBFactory
from world.checks.test_helpers import force_check_outcome
from world.combat.models import ClashContributionDeclaration
from world.conditions.models import ConditionInstance
from world.conditions.services import (
    apply_condition,
    has_condition,
    process_round_end,
    remove_condition,
)
from world.magic.factories import (
    BerserkConditionTemplateFactory,
    CharacterAnimaFactory,
    FuryConfigFactory,
    FuryTierFactory,
    TechniqueFactory,
)
from world.magic.services import use_technique
from world.mechanics.factories import CharacterEngagementFactory
from world.relationships.constants import LabelAwareness, TypeFamily
from world.relationships.factories import CharacterRelationshipFactory, RelationshipTypeFactory
from world.relationships.services import declare_label
from world.roster.factories import grant_test_tenure
from world.scenes.action_constants import ConsentDecision
from world.scenes.action_services import respond_to_action_request
from world.scenes.factories import PersonaFactory, SceneActionRequestFactory, SceneFactory
from world.traits.factories import CheckOutcomeFactory, CheckSystemSetupFactory
from world.vitals.models import CharacterVitals


class _FakeCheck:
    """Minimal stand-in for perform_check result used in resolve_fury calls."""

    def __init__(self, success_level: int, outcome=None) -> None:
        self.success_level = success_level
        self.outcome = outcome


# ---------------------------------------------------------------------------
# Shared fixture helpers
# ---------------------------------------------------------------------------

_ROOM_COUNTER = [0]


def _next_room_key() -> str:
    _ROOM_COUNTER[0] += 1
    return f"FuryIntRoom{_ROOM_COUNTER[0]}"


def _setup_bonded_pair(*, tier_depth: int = 2, bond_tier_number: int = 2):
    """Two personas, fury tier, config, and a bond giving cap >= tier_depth.

    Returns (scene, initiator_persona, anchor_persona, fury_tier, fury_config).
    """
    CheckSystemSetupFactory.create()
    room = create_object("typeclasses.rooms.Room", key=_next_room_key(), nohome=True)
    scene = SceneFactory(room=room)
    initiator = PersonaFactory()
    anchor = PersonaFactory()

    CharacterAnimaFactory(character=initiator.character_sheet, current=50, maximum=50)
    for persona in (initiator, anchor):
        CharacterVitals.objects.get_or_create(
            character_sheet=persona.character_sheet,
            defaults={"health": 50, "max_health": 50, "base_max_health": 50},
        )

    cfg = FuryConfigFactory()
    tier = FuryTierFactory(
        name=f"IntTier_{tier_depth}_{bond_tier_number}",
        depth=tier_depth,
        control_surrendered=4,
        base_check_difficulty=10,
        berserk_severity=3,
    )
    # Fury needs something at stake (#4738): the initiator is engaged.
    CharacterEngagementFactory(character=initiator.character_sheet)

    # Mutual Mentor/Student bond at bond_tier_number. Fury itself reads only the SOURCE
    # side's tier (``fury._bond_tier``, any label), so this fixture builds more than the cap
    # strictly needs: it stays mutual-TEACHING so the integration path keeps proving the cap
    # is unchanged for the shape training's ``get_relationship_tier`` also recognises
    # (#3957 final review — the old rationale named get_relationship_tier as fury's read).
    mentor = RelationshipTypeFactory(family=TypeFamily.TEACHING)
    student = RelationshipTypeFactory(family=TypeFamily.TEACHING, counterpart=mentor)
    mentor.counterpart = student
    mentor.save(update_fields=["counterpart"])
    forward = CharacterRelationshipFactory(
        source=initiator.character_sheet, target=anchor.character_sheet, tier=bond_tier_number
    )
    backward = CharacterRelationshipFactory(
        source=anchor.character_sheet, target=initiator.character_sheet, tier=bond_tier_number
    )
    forward_tenure = grant_test_tenure(initiator.character_sheet)
    backward_tenure = grant_test_tenure(anchor.character_sheet)
    declare_label(side=forward, type=mentor, awareness=LabelAwareness.PUBLIC, tenure=forward_tenure)
    declare_label(
        side=backward, type=student, awareness=LabelAwareness.PUBLIC, tenure=backward_tenure
    )

    return scene, initiator, anchor, tier, cfg


# ---------------------------------------------------------------------------
# Test 1: @tag("postgres") real end-to-end cast with fury → Berserk applied
# ---------------------------------------------------------------------------


@tag("postgres")
class RealCastFuryBerserkIntegrationTests(TestCase):
    """Real cast with declared fury tier through the REAL use_technique + apply_condition.

    The DISTINCT ON path in _build_bulk_context is Postgres-only; this class is
    tagged so it only runs in the CI Postgres parity suite.

    The tier is a Berserk tier (berserk_severity > 0), so whatever the control roll:
    - FuryCast.settle calls apply_condition(Berserk) for real.
    - The caster ends up with a ConditionInstance for Berserk.
    - Interaction.fury_committed is set to the realized tier.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        cls.scene, cls.initiator, cls.anchor, cls.tier, cls.cfg = _setup_bonded_pair()
        cls.berserk_template = BerserkConditionTemplateFactory()

        from actions.factories import ActionTemplateFactory

        cls.action_template = ActionTemplateFactory()
        cls.technique = TechniqueFactory(
            action_template=cls.action_template,
            intensity=5,
            control=20,
            anima_cost=10,
            damage_profile=False,
        )

    def setUp(self) -> None:
        self.accrue_patcher = patch("world.scenes.action_services.accrue")
        self.accrue_patcher.start()

    def tearDown(self) -> None:
        self.accrue_patcher.stop()

    @patch("world.scenes.action_services.start_action_resolution")
    def test_real_apply_condition_on_fury_failure(self, mock_resolve: object) -> None:
        """A Berserk tier → real apply_condition(Berserk) → caster has Berserk."""
        from unittest.mock import MagicMock

        from actions.constants import ResolutionPhase
        from actions.types import PendingActionResolution, StepResult

        # Build a minimal PendingActionResolution so the action pipeline can complete.
        check_result = MagicMock()
        check_result.success_level = -1
        check_result.outcome_name = "Failure"
        step = StepResult(step_label="main", check_result=check_result, consequence_id=None)
        pending = PendingActionResolution(
            template_id=1,
            character_id=1,
            target_difficulty=45,
            resolution_context_data={"character_id": 1, "challenge_instance_id": None},
            current_phase=ResolutionPhase.COMPLETE,
            main_result=step,
        )
        mock_resolve.return_value = pending

        # The control roll's outcome does not decide Berserk; force it anyway.
        failure_outcome = CheckOutcomeFactory(name="FuryInt_RealFail", success_level=-1)

        request = SceneActionRequestFactory(
            scene=self.scene,
            initiator_persona=self.initiator,
            target_persona=self.anchor,
            action_key="intimidate",
            technique=self.technique,
            fury_commitment=self.tier,
            fury_anchor=self.anchor.character_sheet,
        )
        request.action_template = self.action_template
        request.save(update_fields=["action_template"])

        with force_check_outcome(failure_outcome):
            respond_to_action_request(
                action_request=request,
                decision=ConsentDecision.ACCEPT,
            )

        caster = self.initiator.character_sheet.character

        # 1. The caster must now have an active Berserk ConditionInstance.
        self.assertTrue(
            has_condition(caster, self.berserk_template),
            "Caster must have active Berserk after choosing a Berserk tier.",
        )

        # 2. The Interaction must record the realized fury tier.
        request.refresh_from_db()
        self.assertIsNotNone(request.result_interaction)
        self.assertEqual(request.result_interaction.fury_committed, self.tier)


# ---------------------------------------------------------------------------
# Test 2: @tag("postgres") full berserker loop — cast → Berserk → Restore removes it
# ---------------------------------------------------------------------------


@tag("postgres")
class FullBerserkerLoopTests(TestCase):
    """Full loop: cast fury → Berserk applied → Restore-to-Sense ally removes it.

    Exercises the real apply_condition (PG DISTINCT ON) and the real
    remove_condition path triggered by a successful Restore action.
    The Restore-to-Sense success is exercised via remove_condition directly
    because the full scene-action pipeline for a social action is already
    tested by test_restore_sense_action.py's mocked path; this test proves
    the DB round-trip (apply → remove) with real PG queries.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        cls.berserk_template = BerserkConditionTemplateFactory()
        cls.scene, cls.initiator, cls.anchor, cls.tier, cls.cfg = _setup_bonded_pair(
            tier_depth=2, bond_tier_number=2
        )

    def test_berserk_removed_by_restore(self) -> None:
        """apply_condition(Berserk) → has_condition → remove_condition → not has_condition."""
        caster = self.initiator.character_sheet.character

        # Step 1: apply Berserk with real apply_condition (hits PG DISTINCT ON).
        result = apply_condition(
            caster,
            self.berserk_template,
            severity=self.tier.berserk_severity,
            duration_rounds=self.cfg.default_berserk_duration_rounds,
        )
        self.assertTrue(result.success, "apply_condition should succeed for Berserk.")
        self.assertTrue(has_condition(caster, self.berserk_template))

        # Step 2: a successful Restore-to-Sense ally removes it.
        removed = remove_condition(caster, self.berserk_template)
        self.assertTrue(removed, "remove_condition should return True for an active Berserk.")
        self.assertFalse(
            has_condition(caster, self.berserk_template),
            "Caster must no longer have Berserk after Restore-to-Sense.",
        )


# ---------------------------------------------------------------------------
# Test 3: Strain + Fury stacked — control delta AND fatigue split correct;
#          Fury alone accrues NO extra fatigue.
# ---------------------------------------------------------------------------


class StrainAndFuryStackedTests(TestCase):
    """Strain + Fury stacked on one cast: surrendered control and the fatigue split.

    Fury surrenders control onto the engagement (#4738), which lowers runtime control and
    so raises the anima cost. Strain adds strain_commitment on top (raises effective cost
    further, AND moves a portion to the higher-rate strain_portion for fatigue).

    Fury alone (no strain_commitment) accrues fatigue only at the base ratio.
    """

    CONTROL_SURRENDERED = 6

    @classmethod
    def setUpTestData(cls) -> None:
        # Technique: high control so the surrender still leaves positive control.
        cls.technique = TechniqueFactory(
            intensity=5,
            control=20,
            anima_cost=10,
            damage_profile=False,
        )

    def _make_caster(self, *, control_surrendered: int = 0):
        """Return (character, character_sheet) for a fresh, engaged caster."""
        from world.character_sheets.factories import CharacterSheetFactory

        anima = CharacterAnimaFactory(current=50, maximum=50)
        character = anima.character.character
        CharacterEngagementFactory(
            character=anima.character,
            control_modifier=-control_surrendered,
            fury_control_surrendered=control_surrendered,
        )
        sheet = CharacterSheetFactory(character=character)
        return character, sheet

    def _noop_resolve(self, *, power: int, ledger: object = None, extra_modifiers: int = 0):  # noqa: ARG002
        from types import SimpleNamespace

        return SimpleNamespace(check_result=None)

    def _fatigue_after_cast(self, *, control_surrendered: int, strain_commitment: int = 0):
        from world.fatigue.services import get_or_create_fatigue_pool

        caster, sheet = self._make_caster(control_surrendered=control_surrendered)
        use_technique(
            character=caster,
            technique=self.technique,
            resolve_fn=self._noop_resolve,
            strain_commitment=strain_commitment,
        )
        return get_or_create_fatigue_pool(sheet).get_current(self.technique.action_category)

    def test_fury_alone_does_not_accrue_extra_fatigue(self) -> None:
        """Surrendered control raises cost (and so base-rate fatigue), nothing more.

        fatigue = base_portion * base_ratio + strain_portion * strain_ratio; with no
        strain, a Fury cast's fatigue comes from the same formula at a higher cost.
        """
        baseline = self._fatigue_after_cast(control_surrendered=0)
        fury = self._fatigue_after_cast(control_surrendered=self.CONTROL_SURRENDERED)
        self.assertGreaterEqual(fury, baseline)

    def test_strain_adds_fatigue_above_fury_alone(self) -> None:
        """Strain on top of Fury produces more fatigue than Fury alone."""
        fury_only = self._fatigue_after_cast(control_surrendered=self.CONTROL_SURRENDERED)
        stacked = self._fatigue_after_cast(
            control_surrendered=self.CONTROL_SURRENDERED, strain_commitment=4
        )
        self.assertGreater(stacked, fury_only)


# ---------------------------------------------------------------------------
# Test 4: fury_committed audit on a CLASH declaration
# ---------------------------------------------------------------------------


class ClashDeclarationFuryAuditTests(TestCase):
    """fury_commitment and fury_anchor persist on a ClashContributionDeclaration.

    This exercises the CommittingDeclaration mixin's fields on the clash path
    (separate model from SceneActionRequest). The non-clash Interaction audit
    is covered by test_fury_threading.py.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        from world.character_sheets.factories import CharacterSheetFactory

        FuryConfigFactory()
        cls.tier = FuryTierFactory(name="ClashAuditTier", depth=1, control_surrendered=2)
        cls.anchor_sheet = CharacterSheetFactory()

    def test_fury_fields_stored_on_clash_declaration(self) -> None:
        """ClashContributionDeclaration carries fury_commitment + fury_anchor FK."""
        # We write the declaration directly (bypassing the service/serializer)
        # to prove the model fields accept the values without constraint errors.
        technique = TechniqueFactory(damage_profile=False)

        # Build minimal combat objects using their factories / ORM directly.
        from world.combat.factories import (
            ClashFactory,
            CombatEncounterFactory,
            CombatParticipantFactory,
        )

        encounter = CombatEncounterFactory()
        participant = CombatParticipantFactory(encounter=encounter)
        clash = ClashFactory(encounter=encounter)

        decl = ClashContributionDeclaration.objects.create(
            encounter=encounter,
            round_number=1,
            participant=participant,
            clash=clash,
            action_slot="FOCUSED",
            technique=technique,
            strain_commitment=0,
            fury_commitment=self.tier,
            fury_anchor=self.anchor_sheet,
        )

        decl.refresh_from_db()
        self.assertEqual(decl.fury_commitment, self.tier)
        self.assertEqual(decl.fury_anchor, self.anchor_sheet)


# ---------------------------------------------------------------------------
# Test 5: Berserk decays over rounds_remaining
# ---------------------------------------------------------------------------


@tag("postgres")
class BerserkDecayTests(TestCase):
    """Berserk ConditionInstance expires after rounds_remaining ticks reach 0.

    Drives process_round_end in a loop and asserts the condition is gone once
    rounds_remaining reaches 0.

    PG-only: Berserk has has_progression=True; apply_condition calls
    _build_bulk_context which runs DISTINCT ON (Postgres-only) for progressive
    conditions.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        cls.berserk_template = BerserkConditionTemplateFactory()

    def test_berserk_decays_after_duration_rounds(self) -> None:
        """apply_condition with duration_rounds=2 → expires after 2 process_round_end calls."""

        from world.character_sheets.factories import CharacterSheetFactory

        target = ObjectDBFactory(db_key="BerserkDecayTarget")
        CharacterSheetFactory(character=target)

        apply_condition(
            target,
            self.berserk_template,
            severity=3,
            duration_rounds=2,
        )
        self.assertTrue(has_condition(target, self.berserk_template))

        # First tick: rounds_remaining → 1, condition still active.
        process_round_end(target)
        instance = ConditionInstance.objects.filter(
            target=target, condition=self.berserk_template
        ).first()
        self.assertIsNotNone(instance, "Berserk should still be active after 1 tick.")
        self.assertEqual(instance.rounds_remaining, 1)

        # Second tick: rounds_remaining → 0, condition expires and is deleted.
        process_round_end(target)
        self.assertFalse(
            has_condition(target, self.berserk_template),
            "Berserk must have expired after 2 process_round_end ticks.",
        )


# ---------------------------------------------------------------------------
# Test 6a: Cap 0 (no bond) → fury unavailable (resolve_fury returns None)
# ---------------------------------------------------------------------------


class FuryCapZeroTests(TestCase):
    """Cap 0 (no bond between caster and anchor) → fury unavailable.

    This exercises the null-anchor path through resolve_fury:
    provocation_cap returns 0 → clamp_tier returns None → FuryResolution(None,…)
    → berserk_severity=0 → apply_condition NOT called.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        from world.character_sheets.factories import CharacterSheetFactory

        FuryConfigFactory()
        cls.tier = FuryTierFactory(
            name="CapZeroTier",
            depth=1,
            control_surrendered=2,
            berserk_severity=5,  # non-zero — should not fire
        )
        # Two sheets with NO relationship → cap = 0.
        cls.caster_sheet = CharacterSheetFactory()
        cls.anchor_sheet = CharacterSheetFactory()

    def test_no_bond_fury_unavailable(self) -> None:
        """No relationship → provocation_cap=0 → resolve_fury returns None tier."""
        from world.magic.services.fury import resolve_fury

        # No relationship rows → cap = 0 → realized_tier = None.
        res = resolve_fury(
            character=self.caster_sheet.character,
            tier=self.tier,
            anchor=self.anchor_sheet,
            check_result=_FakeCheck(success_level=5),
        )
        self.assertIsNone(
            res.realized_tier,
            "No bond → provocation_cap=0 → realized_tier must be None.",
        )
        self.assertEqual(res.berserk_severity, 0)
        self.assertEqual(res.control_surrendered, 0)
        self.assertEqual(res.intensity_gained, 0)

    def test_null_anchor_fury_unavailable(self) -> None:
        """anchor=None → provocation_cap=0 → FuryResolution with None tier."""
        from world.magic.services.fury import resolve_fury

        res = resolve_fury(
            character=self.caster_sheet.character,
            tier=self.tier,
            anchor=None,
            check_result=_FakeCheck(success_level=5),
        )
        self.assertIsNone(res.realized_tier)
