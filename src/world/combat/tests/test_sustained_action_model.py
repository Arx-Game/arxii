"""SustainedAction model tests (#2705 Task 1).

Covers the model shape only: the payload CheckConstraints (RITUAL xor
TECHNIQUE), the resolves-after-declared CheckConstraint, and the two new
authored fields (Technique.windup_rounds / RitualCheckConfig.sustained_rounds)
defaulting to 0 (today's behavior, unchanged). Declaration/erosion/maturation
wiring is out of scope for this task — see test_sustained_declaration.py,
test_sustained_erosion.py, and test_sustained_maturation.py (later tasks).
"""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from world.combat.constants import SustainedKind
from world.combat.factories import (
    CombatEncounterFactory,
    CombatParticipantFactory,
    SustainedActionFactory,
)
from world.combat.models import SustainedAction
from world.magic.factories import RitualCheckConfigFactory, RitualFactory, TechniqueFactory
from world.magic.models.ritual_check_config import RitualCheckConfig


class SustainedActionCleanValidationTests(TestCase):
    """``clean()`` mirrors the DB payload CheckConstraints (Python-layer gate)."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.encounter = CombatEncounterFactory()
        cls.participant = CombatParticipantFactory(encounter=cls.encounter)
        cls.technique = TechniqueFactory()
        cls.ritual = RitualFactory()

    def test_ritual_kind_with_technique_set_raises_on_full_clean(self) -> None:
        sustained = SustainedAction(
            encounter=self.encounter,
            participant=self.participant,
            sustained_kind=SustainedKind.RITUAL,
            ritual=self.ritual,
            technique=self.technique,
            declared_round=1,
            resolves_round=2,
            absorption_budget=2,
        )
        with self.assertRaises(ValidationError):
            sustained.full_clean()

    def test_ritual_kind_with_no_ritual_raises_on_full_clean(self) -> None:
        sustained = SustainedAction(
            encounter=self.encounter,
            participant=self.participant,
            sustained_kind=SustainedKind.RITUAL,
            ritual=None,
            technique=None,
            declared_round=1,
            resolves_round=2,
            absorption_budget=2,
        )
        with self.assertRaises(ValidationError):
            sustained.full_clean()

    def test_technique_kind_with_ritual_set_raises_on_full_clean(self) -> None:
        sustained = SustainedAction(
            encounter=self.encounter,
            participant=self.participant,
            sustained_kind=SustainedKind.TECHNIQUE,
            technique=self.technique,
            ritual=self.ritual,
            declared_round=1,
            resolves_round=2,
            absorption_budget=2,
        )
        with self.assertRaises(ValidationError):
            sustained.full_clean()

    def test_technique_kind_with_no_technique_raises_on_full_clean(self) -> None:
        sustained = SustainedAction(
            encounter=self.encounter,
            participant=self.participant,
            sustained_kind=SustainedKind.TECHNIQUE,
            technique=None,
            ritual=None,
            declared_round=1,
            resolves_round=2,
            absorption_budget=2,
        )
        with self.assertRaises(ValidationError):
            sustained.full_clean()

    def test_valid_ritual_row_passes_full_clean(self) -> None:
        sustained = SustainedAction(
            encounter=self.encounter,
            participant=self.participant,
            sustained_kind=SustainedKind.RITUAL,
            ritual=self.ritual,
            technique=None,
            declared_round=1,
            resolves_round=2,
            absorption_budget=2,
        )
        sustained.full_clean()

    def test_valid_technique_row_passes_full_clean(self) -> None:
        sustained = SustainedAction(
            encounter=self.encounter,
            participant=self.participant,
            sustained_kind=SustainedKind.TECHNIQUE,
            technique=self.technique,
            ritual=None,
            declared_round=1,
            resolves_round=2,
            absorption_budget=2,
        )
        sustained.full_clean()


class SustainedActionDbConstraintTests(TestCase):
    """The DB CheckConstraints reject the same rows clean() rejects, plus the
    resolves-after-declared ordering constraint."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.encounter = CombatEncounterFactory()
        cls.participant = CombatParticipantFactory(encounter=cls.encounter)
        cls.technique = TechniqueFactory()
        cls.ritual = RitualFactory()

    def test_ritual_payload_constraint_rejects_technique_set(self) -> None:
        with self.assertRaises(IntegrityError), transaction.atomic():
            SustainedAction.objects.create(
                encounter=self.encounter,
                participant=self.participant,
                sustained_kind=SustainedKind.RITUAL,
                ritual=self.ritual,
                technique=self.technique,
                declared_round=1,
                resolves_round=2,
                absorption_budget=2,
            )

    def test_ritual_payload_constraint_rejects_no_ritual(self) -> None:
        with self.assertRaises(IntegrityError), transaction.atomic():
            SustainedAction.objects.create(
                encounter=self.encounter,
                participant=self.participant,
                sustained_kind=SustainedKind.RITUAL,
                ritual=None,
                technique=None,
                declared_round=1,
                resolves_round=2,
                absorption_budget=2,
            )

    def test_technique_payload_constraint_rejects_ritual_set(self) -> None:
        with self.assertRaises(IntegrityError), transaction.atomic():
            SustainedAction.objects.create(
                encounter=self.encounter,
                participant=self.participant,
                sustained_kind=SustainedKind.TECHNIQUE,
                technique=self.technique,
                ritual=self.ritual,
                declared_round=1,
                resolves_round=2,
                absorption_budget=2,
            )

    def test_technique_payload_constraint_rejects_no_technique(self) -> None:
        with self.assertRaises(IntegrityError), transaction.atomic():
            SustainedAction.objects.create(
                encounter=self.encounter,
                participant=self.participant,
                sustained_kind=SustainedKind.TECHNIQUE,
                technique=None,
                ritual=None,
                declared_round=1,
                resolves_round=2,
                absorption_budget=2,
            )

    def test_resolves_round_must_be_after_declared_round(self) -> None:
        with self.assertRaises(IntegrityError), transaction.atomic():
            SustainedAction.objects.create(
                encounter=self.encounter,
                participant=self.participant,
                sustained_kind=SustainedKind.TECHNIQUE,
                technique=self.technique,
                ritual=None,
                declared_round=2,
                resolves_round=2,
                absorption_budget=2,
            )

    def test_resolves_round_before_declared_round_also_rejected(self) -> None:
        with self.assertRaises(IntegrityError), transaction.atomic():
            SustainedAction.objects.create(
                encounter=self.encounter,
                participant=self.participant,
                sustained_kind=SustainedKind.TECHNIQUE,
                technique=self.technique,
                ritual=None,
                declared_round=3,
                resolves_round=2,
                absorption_budget=2,
            )

    def test_valid_row_is_created(self) -> None:
        sustained = SustainedAction.objects.create(
            encounter=self.encounter,
            participant=self.participant,
            sustained_kind=SustainedKind.TECHNIQUE,
            technique=self.technique,
            ritual=None,
            declared_round=1,
            resolves_round=2,
            absorption_budget=2,
        )
        self.assertIsNotNone(sustained.pk)


class SustainedActionMiscModelTests(TestCase):
    """subject_name / __str__ + the factory build a valid row."""

    def test_factory_builds_valid_row(self) -> None:
        sustained = SustainedActionFactory()
        sustained.full_clean()
        self.assertEqual(sustained.sustained_kind, SustainedKind.TECHNIQUE)
        self.assertIsNone(sustained.ritual)
        self.assertIsNotNone(sustained.technique)

    def test_subject_name_reads_technique_name_for_technique_kind(self) -> None:
        sustained = SustainedActionFactory()
        self.assertEqual(sustained.subject_name, sustained.technique.name)

    def test_subject_name_reads_ritual_name_for_ritual_kind(self) -> None:
        encounter = CombatEncounterFactory()
        participant = CombatParticipantFactory(encounter=encounter)
        ritual = RitualFactory()
        sustained = SustainedAction.objects.create(
            encounter=encounter,
            participant=participant,
            sustained_kind=SustainedKind.RITUAL,
            ritual=ritual,
            technique=None,
            declared_round=1,
            resolves_round=2,
            absorption_budget=2,
        )
        self.assertEqual(sustained.subject_name, ritual.name)

    def test_str_includes_subject_and_resolves_round(self) -> None:
        sustained = SustainedActionFactory()
        text = str(sustained)
        self.assertIn(sustained.subject_name, text)
        self.assertIn(str(sustained.resolves_round), text)


class WindupRoundsDefaultTests(TestCase):
    """New authored fields default to 0 — today's behavior, unchanged (#2705)."""

    def test_technique_windup_rounds_defaults_to_zero(self) -> None:
        technique = TechniqueFactory()
        self.assertEqual(technique.windup_rounds, 0)

    def test_ritual_check_config_sustained_rounds_defaults_to_zero(self) -> None:
        config = RitualCheckConfigFactory()
        self.assertEqual(config.sustained_rounds, 0)
        # RitualCheckConfig import used only for typing/clarity of intent above.
        self.assertIsInstance(config, RitualCheckConfig)
        self.assertIsInstance(config.ritual.check_config_or_none, RitualCheckConfig)
