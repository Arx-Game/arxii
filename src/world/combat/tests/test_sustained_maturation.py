"""Tests for PC sustained-action maturation at the round seam (#2705).

Covers ``_mature_sustained_actions`` / ``_mature_one_sustained_action`` /
``_mature_sustained_technique`` directly (the break / lose-holder / hold
branches, the clone + ``extra_targets`` copy) plus one integration test
through ``resolve_round`` proving the declaring round skips resolving the
sustaining participant's action while the maturation round runs it
(Task 4c's skip-wiring).

``test_windup_lifecycle.py`` (the NPC sibling this maturation logic pairs
with — the maturation call-site sits in the very same ``resolve_round`` pass)
is run alongside this module as this task's regression oracle.
"""

from __future__ import annotations

from unittest import mock

from django.test import TestCase

from world.checks.factories import CheckCategoryFactory, CheckTypeFactory
from world.checks.test_helpers import force_check_outcome
from world.combat.constants import (
    CONCENTRATION_CHECK_TYPE_NAME,
    ParticipantStatus,
    SustainedKind,
)
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
    SustainedActionFactory,
)
from world.combat.models import (
    CombatParticipant,
    CombatRoundAction,
    CombatRoundActionTarget,
    SustainedAction,
)
from world.combat.services import (
    _apply_sustained_erosion_rider,
    _mature_one_sustained_action,
    _mature_sustained_actions,
    declare_action,
    resolve_round,
)
from world.fatigue.constants import EffortLevel
from world.magic.factories import EffectTypeFactory, GiftFactory, RitualFactory, TechniqueFactory
from world.scenes.constants import RoundStatus
from world.traits.factories import CheckOutcomeFactory
from world.vitals.constants import CharacterLifeState
from world.vitals.models import CharacterVitals


def _make_participant(encounter, **kwargs) -> CombatParticipant:
    participant = CombatParticipantFactory(encounter=encounter, **kwargs)
    CharacterVitals.objects.create(
        character_sheet=participant.character_sheet, health=100, max_health=100
    )
    return participant


class _SustainedMaturationTestBase(TestCase):
    """Shared buff-effect Technique factory shape (no target required)."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.gift = GiftFactory()
        cls.effect_type = EffectTypeFactory(base_power=None)

    def _make_technique(self, **kwargs):
        return TechniqueFactory(gift=self.gift, effect_type=self.effect_type, **kwargs)


# ---------------------------------------------------------------------------
# _mature_sustained_technique: the clone (downgrades < budget)
# ---------------------------------------------------------------------------


class SustainedMaturationCloneTests(_SustainedMaturationTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.encounter = CombatEncounterFactory(status=RoundStatus.RESOLVING, round_number=2)
        self.participant = _make_participant(self.encounter)
        self.technique = self._make_technique(windup_rounds=2)
        self.opponent = CombatOpponentFactory(encounter=self.encounter)
        self.declared_action = CombatRoundAction.objects.create(
            participant=self.participant,
            round_number=1,
            focused_action=self.technique,
            focused_opponent_target=self.opponent,
            is_ready=False,
        )

    @mock.patch("world.scenes.interaction_services._broadcast_to_location")
    def test_holds_and_clones_into_maturation_round(self, mock_broadcast) -> None:  # noqa: ARG002
        sustained = SustainedActionFactory(
            encounter=self.encounter,
            participant=self.participant,
            technique=self.technique,
            declared_action=self.declared_action,
            declared_round=1,
            resolves_round=2,
            absorption_budget=3,
            downgrades=1,
        )

        _mature_sustained_actions(self.encounter, round_number=2)

        self.assertFalse(SustainedAction.objects.filter(pk=sustained.pk).exists())
        clone = CombatRoundAction.objects.get(participant=self.participant, round_number=2)
        self.assertEqual(clone.focused_action_id, self.technique.pk)
        self.assertEqual(clone.focused_opponent_target_id, self.opponent.pk)
        self.assertTrue(clone.is_ready)
        self.assertIsNone(clone.interaction_id)
        self.assertIsNone(clone.interaction_timestamp)
        self.assertIsNone(clone.combo_upgrade_id)
        self.assertIsNone(clone.succor_resolution)
        self.assertNotEqual(clone.pk, self.declared_action.pk)
        # The declaring round-1 row is a genuinely separate DB row, untouched.
        original_reread = CombatRoundAction.objects.get(pk=self.declared_action.pk)
        self.assertEqual(original_reread.round_number, 1)

    @mock.patch("world.scenes.interaction_services._broadcast_to_location")
    def test_declaring_round_row_survives_untouched_in_the_idmapper_cache(
        self,
        mock_broadcast,  # noqa: ARG002
    ) -> None:
        """Regression guard for the plan's original ``clone.pk = None`` recipe.

        That recipe mutated the fetched declaring-round instance in place and
        re-saved it — since ``CombatRoundAction`` is a ``SharedMemoryModel``
        (idmapper identity map), that reassigns a NEW pk to the SAME cached
        Python object while leaving the idmapper's cache entry for the
        ORIGINAL pk pointing at that now-mutated object. A verified real bug:
        any later ``.objects.get(pk=<original pk>)`` in-process would then
        silently return the maturation round's data. Assert directly that
        re-fetching the declaring row by its original pk still reports
        round_number == 1, not 2.
        """
        SustainedActionFactory(
            encounter=self.encounter,
            participant=self.participant,
            technique=self.technique,
            declared_action=self.declared_action,
            declared_round=1,
            resolves_round=2,
            absorption_budget=3,
            downgrades=0,
        )
        original_pk = self.declared_action.pk

        _mature_sustained_actions(self.encounter, round_number=2)

        refetched = CombatRoundAction.objects.get(pk=original_pk)
        self.assertEqual(refetched.round_number, 1)


class SustainedMaturationExtraTargetsTests(_SustainedMaturationTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.encounter = CombatEncounterFactory(status=RoundStatus.RESOLVING, round_number=2)
        self.participant = _make_participant(self.encounter)
        self.technique = self._make_technique(windup_rounds=2)
        self.primary_opponent = CombatOpponentFactory(encounter=self.encounter)
        self.extra_opponent = CombatOpponentFactory(encounter=self.encounter)
        self.declared_action = CombatRoundAction.objects.create(
            participant=self.participant,
            round_number=1,
            focused_action=self.technique,
            focused_opponent_target=self.primary_opponent,
            is_ready=False,
        )
        CombatRoundActionTarget.objects.bulk_create(
            [
                CombatRoundActionTarget(
                    action=self.declared_action, opponent=self.primary_opponent
                ),
                CombatRoundActionTarget(action=self.declared_action, opponent=self.extra_opponent),
            ]
        )

    @mock.patch("world.scenes.interaction_services._broadcast_to_location")
    def test_extra_targets_copied_onto_clone(self, mock_broadcast) -> None:  # noqa: ARG002
        SustainedActionFactory(
            encounter=self.encounter,
            participant=self.participant,
            technique=self.technique,
            declared_action=self.declared_action,
            declared_round=1,
            resolves_round=2,
            absorption_budget=3,
            downgrades=0,
        )

        _mature_sustained_actions(self.encounter, round_number=2)

        clone = CombatRoundAction.objects.get(participant=self.participant, round_number=2)
        cloned_opponent_ids = set(clone.extra_targets.values_list("opponent_id", flat=True))
        self.assertEqual(cloned_opponent_ids, {self.primary_opponent.pk, self.extra_opponent.pk})
        # The declaring round's own extra_targets rows are untouched (still 2).
        original_targets = CombatRoundActionTarget.objects.filter(action_id=self.declared_action.pk)
        self.assertEqual(original_targets.count(), 2)


# ---------------------------------------------------------------------------
# Broken: downgrades >= budget
# ---------------------------------------------------------------------------


class SustainedMaturationBrokenTests(_SustainedMaturationTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.encounter = CombatEncounterFactory(status=RoundStatus.RESOLVING, round_number=2)
        self.participant = _make_participant(self.encounter)
        self.technique = self._make_technique(windup_rounds=2)
        self.declared_action = CombatRoundAction.objects.create(
            participant=self.participant,
            round_number=1,
            focused_action=self.technique,
            is_ready=False,
        )

    @mock.patch("world.scenes.interaction_services._broadcast_to_location")
    def test_downgrades_equal_to_budget_breaks(self, mock_broadcast) -> None:
        sustained = SustainedActionFactory(
            encounter=self.encounter,
            participant=self.participant,
            technique=self.technique,
            declared_action=self.declared_action,
            declared_round=1,
            resolves_round=2,
            absorption_budget=2,
            downgrades=2,
        )

        _mature_one_sustained_action(sustained, round_number=2)

        self.assertFalse(SustainedAction.objects.filter(pk=sustained.pk).exists())
        self.assertFalse(
            CombatRoundAction.objects.filter(participant=self.participant, round_number=2).exists()
        )
        self.assertTrue(mock_broadcast.called)

    @mock.patch("world.scenes.interaction_services._broadcast_to_location")
    def test_downgrades_greater_than_budget_breaks(self, mock_broadcast) -> None:
        sustained = SustainedActionFactory(
            encounter=self.encounter,
            participant=self.participant,
            technique=self.technique,
            declared_action=self.declared_action,
            declared_round=1,
            resolves_round=2,
            absorption_budget=2,
            downgrades=5,
        )

        _mature_one_sustained_action(sustained, round_number=2)

        self.assertFalse(SustainedAction.objects.filter(pk=sustained.pk).exists())
        self.assertFalse(
            CombatRoundAction.objects.filter(participant=self.participant, round_number=2).exists()
        )
        self.assertTrue(mock_broadcast.called)

    @mock.patch("world.scenes.interaction_services._broadcast_to_location")
    def test_broken_cost_is_not_refunded(self, mock_broadcast) -> None:  # noqa: ARG002
        """D-ruling: nothing about a broken commitment restores anything.

        There is no refundable cost on the TECHNIQUE side today (the anima
        cost was already spent at declaration via the normal fatigue/anima
        path, off this row entirely), so the only thing to assert here is the
        negative: maturation does not create, restore, or credit anything —
        it only deletes the row and broadcasts.
        """
        sustained = SustainedActionFactory(
            encounter=self.encounter,
            participant=self.participant,
            technique=self.technique,
            declared_action=self.declared_action,
            declared_round=1,
            resolves_round=2,
            absorption_budget=1,
            downgrades=1,
        )

        _mature_one_sustained_action(sustained, round_number=2)

        self.assertEqual(CombatRoundAction.objects.filter(participant=self.participant).count(), 1)


# ---------------------------------------------------------------------------
# Broken: the holder can no longer hold it together (left / died)
# ---------------------------------------------------------------------------


class SustainedMaturationLostHolderTests(_SustainedMaturationTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.encounter = CombatEncounterFactory(status=RoundStatus.RESOLVING, round_number=2)
        self.participant = _make_participant(self.encounter)
        self.technique = self._make_technique(windup_rounds=2)
        self.declared_action = CombatRoundAction.objects.create(
            participant=self.participant,
            round_number=1,
            focused_action=self.technique,
            is_ready=False,
        )

    @mock.patch("world.scenes.interaction_services._broadcast_to_location")
    def test_participant_left_encounter_breaks_with_no_clone(self, mock_broadcast) -> None:
        self.participant.status = ParticipantStatus.FLED
        self.participant.save(update_fields=["status"])
        sustained = SustainedActionFactory(
            encounter=self.encounter,
            participant=self.participant,
            technique=self.technique,
            declared_action=self.declared_action,
            declared_round=1,
            resolves_round=2,
            absorption_budget=3,
            downgrades=0,
        )

        _mature_one_sustained_action(sustained, round_number=2)

        self.assertFalse(SustainedAction.objects.filter(pk=sustained.pk).exists())
        self.assertFalse(
            CombatRoundAction.objects.filter(participant=self.participant, round_number=2).exists()
        )
        self.assertTrue(mock_broadcast.called)

    @mock.patch("world.scenes.interaction_services._broadcast_to_location")
    def test_participant_dead_breaks_with_no_clone(self, mock_broadcast) -> None:
        vitals = CharacterVitals.objects.get(character_sheet=self.participant.character_sheet)
        vitals.health = 0
        vitals.life_state = CharacterLifeState.DEAD
        vitals.save(update_fields=["health", "life_state"])
        sustained = SustainedActionFactory(
            encounter=self.encounter,
            participant=self.participant,
            technique=self.technique,
            declared_action=self.declared_action,
            declared_round=1,
            resolves_round=2,
            absorption_budget=3,
            downgrades=0,
        )

        _mature_one_sustained_action(sustained, round_number=2)

        self.assertFalse(SustainedAction.objects.filter(pk=sustained.pk).exists())
        self.assertFalse(
            CombatRoundAction.objects.filter(participant=self.participant, round_number=2).exists()
        )
        self.assertTrue(mock_broadcast.called)


# ---------------------------------------------------------------------------
# RITUAL branch: not implemented until Task 5
# ---------------------------------------------------------------------------


class SustainedMaturationRitualNotImplementedTests(TestCase):
    @mock.patch("world.scenes.interaction_services._broadcast_to_location")
    def test_ritual_kind_raises_not_implemented(self, mock_broadcast) -> None:  # noqa: ARG002
        encounter = CombatEncounterFactory(status=RoundStatus.RESOLVING, round_number=2)
        participant = _make_participant(encounter)
        sustained = SustainedActionFactory(
            encounter=encounter,
            participant=participant,
            sustained_kind=SustainedKind.RITUAL,
            technique=None,
            ritual=RitualFactory(),
            declared_action=None,
            declared_round=1,
            resolves_round=2,
            absorption_budget=3,
            downgrades=0,
        )

        with self.assertRaises(NotImplementedError):
            _mature_one_sustained_action(sustained, round_number=2)


# ---------------------------------------------------------------------------
# Data-integrity gap: TECHNIQUE with no declared_action
# ---------------------------------------------------------------------------


class SustainedMaturationMissingDeclaredActionTests(TestCase):
    @mock.patch("world.scenes.interaction_services._broadcast_to_location")
    def test_missing_declared_action_breaks_rather_than_crashing(self, mock_broadcast) -> None:
        encounter = CombatEncounterFactory(status=RoundStatus.RESOLVING, round_number=2)
        participant = _make_participant(encounter)
        gift = GiftFactory()
        effect_type = EffectTypeFactory(base_power=None)
        technique = TechniqueFactory(gift=gift, effect_type=effect_type, windup_rounds=2)
        sustained = SustainedActionFactory(
            encounter=encounter,
            participant=participant,
            technique=technique,
            declared_action=None,
            declared_round=1,
            resolves_round=2,
            absorption_budget=3,
            downgrades=0,
        )

        _mature_one_sustained_action(sustained, round_number=2)

        self.assertFalse(SustainedAction.objects.filter(pk=sustained.pk).exists())
        self.assertFalse(
            CombatRoundAction.objects.filter(participant=participant, round_number=2).exists()
        )
        self.assertTrue(mock_broadcast.called)


# ---------------------------------------------------------------------------
# Critical-Failure budget of 0: the first landing hit breaks it before it
# ever reaches maturation
# ---------------------------------------------------------------------------


class SustainedMaturationCriticalFailureBudgetTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.concentration_category = CheckCategoryFactory(name="maturation-composure-checks")
        cls.concentration_check_type = CheckTypeFactory(
            name=CONCENTRATION_CHECK_TYPE_NAME, category=cls.concentration_category
        )
        cls.gift = GiftFactory()
        cls.effect_type = EffectTypeFactory(base_power=None)

    @mock.patch("world.scenes.interaction_services._broadcast_to_location")
    def test_critical_failure_budget_zero_breaks_on_first_hit(self, mock_broadcast) -> None:  # noqa: ARG002
        encounter = CombatEncounterFactory(status=RoundStatus.DECLARING, round_number=1)
        participant = _make_participant(encounter)
        technique = TechniqueFactory(gift=self.gift, effect_type=self.effect_type, windup_rounds=2)

        crit_fail_outcome = CheckOutcomeFactory(success_level=-2)
        with force_check_outcome(crit_fail_outcome):
            declare_action(participant, focused_action=technique, effort_level=EffortLevel.MEDIUM)

        sustained = SustainedAction.objects.get()
        self.assertEqual(sustained.absorption_budget, 0)

        # A single landing hit is already >= budget (0).
        _apply_sustained_erosion_rider(participant, 10)
        sustained.refresh_from_db()
        self.assertEqual(sustained.downgrades, 1)

        # Advance to the maturation round and mature it.
        encounter.round_number = 2
        encounter.status = RoundStatus.RESOLVING
        encounter.save(update_fields=["round_number", "status"])

        _mature_one_sustained_action(sustained, round_number=2)

        self.assertFalse(SustainedAction.objects.filter(pk=sustained.pk).exists())
        self.assertFalse(
            CombatRoundAction.objects.filter(participant=participant, round_number=2).exists()
        )


# ---------------------------------------------------------------------------
# Integration through resolve_round: the declaring round does NOT resolve
# the technique; the maturation round DOES (Task 4c skip-wiring)
# ---------------------------------------------------------------------------


class SustainedDeclaringRoundSkipTests(TestCase):
    """Full ``resolve_round`` round-trip proving the skip + maturation wiring.

    ``_run_combat_technique_pipeline`` is patched (not run for real) so the
    test needs no fully-wired magic action_template/check pipeline — only
    that it is/isn't CALLED for the sustaining participant in each round,
    which is exactly what Task 4c's wiring controls.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        cls.concentration_category = CheckCategoryFactory(name="skip-wiring-composure-checks")
        cls.concentration_check_type = CheckTypeFactory(
            name=CONCENTRATION_CHECK_TYPE_NAME, category=cls.concentration_category
        )
        cls.gift = GiftFactory()
        cls.effect_type = EffectTypeFactory(base_power=None)

    def setUp(self) -> None:
        self.encounter = CombatEncounterFactory(status=RoundStatus.DECLARING, round_number=1)
        self.participant = _make_participant(self.encounter)
        # An ACTIVE ENEMY opponent with no threat_pool: keeps
        # _check_encounter_completion from closing the encounter after round
        # 1 (an encounter with zero active ENEMY opponents auto-completes),
        # while select_npc_actions skips it entirely (it excludes
        # threat_pool__isnull=True), so it never fires an action of its own
        # to interfere with what this test is isolating.
        CombatOpponentFactory(encounter=self.encounter, threat_pool=None)
        self.technique = TechniqueFactory(
            gift=self.gift, effect_type=self.effect_type, windup_rounds=1
        )

    def _combat_technique_result(self):
        from world.combat.types import CombatTechniqueResult
        from world.magic.types import TechniqueUseResult

        return CombatTechniqueResult(
            damage_results=[],
            applied_conditions=[],
            technique_use_result=mock.MagicMock(spec=TechniqueUseResult),
        )

    @mock.patch("world.scenes.interaction_services._broadcast_to_location")
    @mock.patch("world.combat.services._run_combat_technique_pipeline")
    def test_declaring_round_skips_maturation_round_resolves(
        self,
        mock_pipeline,
        mock_broadcast,  # noqa: ARG002
    ) -> None:
        mock_pipeline.return_value = self._combat_technique_result()

        declare_action(
            self.participant, focused_action=self.technique, effort_level=EffortLevel.MEDIUM
        )
        sustained = SustainedAction.objects.get()
        self.assertEqual(sustained.declared_round, 1)
        self.assertEqual(sustained.resolves_round, 2)

        # Round 1 (the declaring round): the pipeline must NOT run for this
        # participant — the CombatRoundAction on the board is the declaration
        # of the commitment, not an action to resolve.
        resolve_round(self.encounter)
        mock_pipeline.assert_not_called()
        self.assertTrue(SustainedAction.objects.filter(pk=sustained.pk).exists())

        # Advance to round 2 (the maturation round) without going through
        # begin_declaration_phase (mirrors WindupMaturationTests' pattern in
        # test_windup_lifecycle.py) — set status/round_number directly.
        self.encounter.refresh_from_db()
        self.encounter.round_number = 2
        self.encounter.status = RoundStatus.DECLARING
        self.encounter.save(update_fields=["round_number", "status"])

        resolve_round(self.encounter)

        mock_pipeline.assert_called_once()
        self.assertFalse(SustainedAction.objects.filter(pk=sustained.pk).exists())
