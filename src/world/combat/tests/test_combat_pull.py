"""Tests for Resonance Pivot Spec A Phase 6: CombatPull + CombatPullResolvedEffect.

Spec §2.1 lines 459-540, §3.8 lines 1016-1104.
"""

from django.core.exceptions import ValidationError
from django.db.utils import IntegrityError
from django.test import TestCase

from world.combat.factories import (
    CombatParticipantFactory,
    CombatPullFactory,
    CombatPullResolvedEffectFactory,
)
from world.combat.models import CombatPull, CombatPullResolvedEffect
from world.conditions.factories import CapabilityTypeFactory
from world.magic.constants import EffectKind, VitalBonusTarget
from world.magic.factories import ResonanceFactory, ThreadFactory


class CombatPullShapeTests(TestCase):
    """Plan-mandated tests for CombatPull row shape and uniqueness."""

    def test_unique_together_participant_round(self) -> None:
        p = CombatParticipantFactory()
        CombatPullFactory(participant=p, encounter=p.encounter, round_number=1)
        with self.assertRaises(IntegrityError):
            CombatPullFactory(participant=p, encounter=p.encounter, round_number=1)

    def test_different_rounds_coexist(self) -> None:
        p = CombatParticipantFactory()
        CombatPullFactory(participant=p, encounter=p.encounter, round_number=1)
        CombatPullFactory(participant=p, encounter=p.encounter, round_number=2)
        self.assertEqual(CombatPull.objects.filter(participant=p).count(), 2)


class CombatPullResolvedEffectCascadeTests(TestCase):
    """Plan-mandated cascade-delete behavior."""

    def test_cascading_delete_with_pull(self) -> None:
        pull = CombatPullFactory()
        CombatPullResolvedEffectFactory(pull=pull)
        CombatPullResolvedEffectFactory(pull=pull)
        self.assertEqual(pull.resolved_effects.count(), 2)
        pull.delete()
        self.assertEqual(CombatPullResolvedEffect.objects.count(), 0)


class CombatPullResolvedEffectCleanTests(TestCase):
    """Per-EffectKind clean() validation. Mirrors ThreadPullEffect.clean()."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.pull = CombatPullFactory()
        cls.thread = ThreadFactory()
        cls.capability = CapabilityTypeFactory()

    # FLAT_BONUS ---------------------------------------------------------

    def test_flat_bonus_happy_path(self) -> None:
        eff = CombatPullResolvedEffectFactory.build(
            pull=self.pull,
            source_thread=self.thread,
            kind=EffectKind.FLAT_BONUS,
            authored_value=2,
            level_multiplier=2,
            scaled_value=4,
            granted_capability=None,
            narrative_snippet="",
            vital_target=None,
            source_thread_level=2,
            source_tier=1,
        )
        eff.full_clean()  # no exception

    def test_flat_bonus_requires_scaled_value(self) -> None:
        eff = CombatPullResolvedEffectFactory.build(
            pull=self.pull,
            source_thread=self.thread,
            kind=EffectKind.FLAT_BONUS,
            scaled_value=None,
        )
        with self.assertRaises(ValidationError):
            eff.clean()

    def test_flat_bonus_rejects_capability(self) -> None:
        eff = CombatPullResolvedEffectFactory.build(
            pull=self.pull,
            source_thread=self.thread,
            kind=EffectKind.FLAT_BONUS,
            scaled_value=4,
            granted_capability=self.capability,
        )
        with self.assertRaises(ValidationError):
            eff.clean()

    def test_flat_bonus_rejects_narrative(self) -> None:
        eff = CombatPullResolvedEffectFactory.build(
            pull=self.pull,
            source_thread=self.thread,
            kind=EffectKind.FLAT_BONUS,
            scaled_value=4,
            narrative_snippet="not allowed",
        )
        with self.assertRaises(ValidationError):
            eff.clean()

    def test_flat_bonus_rejects_vital_target(self) -> None:
        eff = CombatPullResolvedEffectFactory.build(
            pull=self.pull,
            source_thread=self.thread,
            kind=EffectKind.FLAT_BONUS,
            scaled_value=4,
            vital_target=VitalBonusTarget.MAX_HEALTH,
        )
        with self.assertRaises(ValidationError):
            eff.clean()

    # INTENSITY_BUMP -----------------------------------------------------

    def test_intensity_bump_happy_path(self) -> None:
        eff = CombatPullResolvedEffectFactory.build(
            pull=self.pull,
            source_thread=self.thread,
            kind=EffectKind.INTENSITY_BUMP,
            authored_value=1,
            level_multiplier=2,
            scaled_value=2,
        )
        eff.full_clean()

    def test_intensity_bump_requires_scaled_value(self) -> None:
        eff = CombatPullResolvedEffectFactory.build(
            pull=self.pull,
            source_thread=self.thread,
            kind=EffectKind.INTENSITY_BUMP,
            scaled_value=None,
        )
        with self.assertRaises(ValidationError):
            eff.clean()

    def test_intensity_bump_rejects_capability(self) -> None:
        eff = CombatPullResolvedEffectFactory.build(
            pull=self.pull,
            source_thread=self.thread,
            kind=EffectKind.INTENSITY_BUMP,
            scaled_value=2,
            granted_capability=self.capability,
        )
        with self.assertRaises(ValidationError):
            eff.clean()

    # VITAL_BONUS --------------------------------------------------------

    def test_vital_bonus_happy_path(self) -> None:
        eff = CombatPullResolvedEffectFactory.build(
            pull=self.pull,
            source_thread=self.thread,
            kind=EffectKind.VITAL_BONUS,
            authored_value=5,
            level_multiplier=2,
            scaled_value=10,
            vital_target=VitalBonusTarget.MAX_HEALTH,
        )
        eff.full_clean()

    def test_vital_bonus_requires_vital_target(self) -> None:
        eff = CombatPullResolvedEffectFactory.build(
            pull=self.pull,
            source_thread=self.thread,
            kind=EffectKind.VITAL_BONUS,
            scaled_value=10,
            vital_target=None,
        )
        with self.assertRaises(ValidationError):
            eff.clean()

    def test_vital_bonus_requires_scaled_value(self) -> None:
        eff = CombatPullResolvedEffectFactory.build(
            pull=self.pull,
            source_thread=self.thread,
            kind=EffectKind.VITAL_BONUS,
            scaled_value=None,
            vital_target=VitalBonusTarget.MAX_HEALTH,
        )
        with self.assertRaises(ValidationError):
            eff.clean()

    def test_vital_bonus_rejects_capability(self) -> None:
        eff = CombatPullResolvedEffectFactory.build(
            pull=self.pull,
            source_thread=self.thread,
            kind=EffectKind.VITAL_BONUS,
            scaled_value=10,
            vital_target=VitalBonusTarget.MAX_HEALTH,
            granted_capability=self.capability,
        )
        with self.assertRaises(ValidationError):
            eff.clean()

    # CAPABILITY_GRANT ---------------------------------------------------

    def test_capability_grant_happy_path(self) -> None:
        eff = CombatPullResolvedEffectFactory.build(
            pull=self.pull,
            source_thread=self.thread,
            kind=EffectKind.CAPABILITY_GRANT,
            authored_value=None,
            scaled_value=None,
            level_multiplier=2,
            granted_capability=self.capability,
            narrative_snippet="",
            vital_target=None,
        )
        eff.full_clean()

    def test_capability_grant_requires_capability(self) -> None:
        eff = CombatPullResolvedEffectFactory.build(
            pull=self.pull,
            source_thread=self.thread,
            kind=EffectKind.CAPABILITY_GRANT,
            scaled_value=None,
            granted_capability=None,
        )
        with self.assertRaises(ValidationError):
            eff.clean()

    def test_capability_grant_rejects_scaled_value(self) -> None:
        eff = CombatPullResolvedEffectFactory.build(
            pull=self.pull,
            source_thread=self.thread,
            kind=EffectKind.CAPABILITY_GRANT,
            scaled_value=4,
            granted_capability=self.capability,
        )
        with self.assertRaises(ValidationError):
            eff.clean()

    def test_capability_grant_rejects_narrative(self) -> None:
        eff = CombatPullResolvedEffectFactory.build(
            pull=self.pull,
            source_thread=self.thread,
            kind=EffectKind.CAPABILITY_GRANT,
            scaled_value=None,
            granted_capability=self.capability,
            narrative_snippet="not allowed",
        )
        with self.assertRaises(ValidationError):
            eff.clean()

    # NARRATIVE_ONLY -----------------------------------------------------

    def test_narrative_only_happy_path(self) -> None:
        eff = CombatPullResolvedEffectFactory.build(
            pull=self.pull,
            source_thread=self.thread,
            kind=EffectKind.NARRATIVE_ONLY,
            authored_value=None,
            scaled_value=None,
            level_multiplier=2,
            granted_capability=None,
            narrative_snippet="A whisper of frost.",
            vital_target=None,
        )
        eff.full_clean()

    def test_narrative_only_requires_snippet(self) -> None:
        eff = CombatPullResolvedEffectFactory.build(
            pull=self.pull,
            source_thread=self.thread,
            kind=EffectKind.NARRATIVE_ONLY,
            scaled_value=None,
            narrative_snippet="",
        )
        with self.assertRaises(ValidationError):
            eff.clean()

    def test_narrative_only_rejects_scaled_value(self) -> None:
        eff = CombatPullResolvedEffectFactory.build(
            pull=self.pull,
            source_thread=self.thread,
            kind=EffectKind.NARRATIVE_ONLY,
            scaled_value=3,
            narrative_snippet="A whisper of frost.",
        )
        with self.assertRaises(ValidationError):
            eff.clean()

    def test_narrative_only_rejects_capability(self) -> None:
        eff = CombatPullResolvedEffectFactory.build(
            pull=self.pull,
            source_thread=self.thread,
            kind=EffectKind.NARRATIVE_ONLY,
            scaled_value=None,
            narrative_snippet="A whisper of frost.",
            granted_capability=self.capability,
        )
        with self.assertRaises(ValidationError):
            eff.clean()


class CombatPullResolvedEffectCheckConstraintTests(TestCase):
    """DB-level CheckConstraint mirrors — bypass clean() via .objects.create()."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.pull = CombatPullFactory()
        cls.thread = ThreadFactory()
        cls.capability = CapabilityTypeFactory()

    def _base_kwargs(self) -> dict:
        return {
            "pull": self.pull,
            "source_thread": self.thread,
            "level_multiplier": 2,
            "source_thread_level": 2,
            "source_tier": 1,
        }

    def test_flat_bonus_requires_scaled_value_db(self) -> None:
        with self.assertRaises(IntegrityError):
            CombatPullResolvedEffect.objects.create(
                **self._base_kwargs(),
                kind=EffectKind.FLAT_BONUS,
                scaled_value=None,
            )

    def test_intensity_bump_requires_scaled_value_db(self) -> None:
        with self.assertRaises(IntegrityError):
            CombatPullResolvedEffect.objects.create(
                **self._base_kwargs(),
                kind=EffectKind.INTENSITY_BUMP,
                scaled_value=None,
            )

    def test_vital_bonus_requires_target_db(self) -> None:
        with self.assertRaises(IntegrityError):
            CombatPullResolvedEffect.objects.create(
                **self._base_kwargs(),
                kind=EffectKind.VITAL_BONUS,
                scaled_value=10,
                vital_target=None,
            )

    def test_capability_grant_requires_capability_db(self) -> None:
        with self.assertRaises(IntegrityError):
            CombatPullResolvedEffect.objects.create(
                **self._base_kwargs(),
                kind=EffectKind.CAPABILITY_GRANT,
                granted_capability=None,
            )

    def test_narrative_only_requires_snippet_db(self) -> None:
        with self.assertRaises(IntegrityError):
            CombatPullResolvedEffect.objects.create(
                **self._base_kwargs(),
                kind=EffectKind.NARRATIVE_ONLY,
                narrative_snippet="",
            )


class CombatPullFactoryDefaultTests(TestCase):
    """Smoke tests — the default factories produce instances passing full_clean()."""

    def test_combat_pull_factory_default_valid(self) -> None:
        pull = CombatPullFactory()
        pull.full_clean()

    def test_combat_pull_resolved_effect_factory_default_valid(self) -> None:
        eff = CombatPullResolvedEffectFactory()
        eff.full_clean()

    def test_resolved_effect_default_kind_is_flat_bonus(self) -> None:
        eff = CombatPullResolvedEffectFactory()
        self.assertEqual(eff.kind, EffectKind.FLAT_BONUS)
        # FLAT_BONUS contract: scaled_value populated, others empty.
        self.assertIsNotNone(eff.scaled_value)
        self.assertIsNone(eff.granted_capability)
        self.assertEqual(eff.narrative_snippet, "")
        self.assertIsNone(eff.vital_target)


class CombatPullEncounterIndexTests(TestCase):
    """Verify the index on (encounter, round_number) is queryable."""

    def test_encounter_round_query(self) -> None:
        p1 = CombatParticipantFactory()
        # Reuse the same encounter for a sibling participant.
        p2 = CombatParticipantFactory(encounter=p1.encounter)
        CombatPullFactory(
            participant=p1,
            encounter=p1.encounter,
            round_number=3,
            resonance=ResonanceFactory(),
        )
        CombatPullFactory(
            participant=p2,
            encounter=p1.encounter,
            round_number=3,
            resonance=ResonanceFactory(),
        )
        self.assertEqual(
            CombatPull.objects.filter(encounter=p1.encounter, round_number=3).count(),
            2,
        )
