"""Tests for ConsequenceOutcome and ConsequenceOutcomeModifier models.

The FK to scenes.Interaction is declared db_constraint=False because
scenes_interaction is range-partitioned — the composite FK on (id, timestamp)
is added by a raw-SQL migration, not Django's ORM.  These tests confirm the
ORM wiring only; the postgres-tagged test covers the CheckConstraint.
"""

from __future__ import annotations

from django.test import TestCase, tag

from actions.factories import ConsequencePoolFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.constants import ModifierSourceKind
from world.checks.factories import CheckTypeFactory, ConsequenceFactory
from world.scenes.factories import InteractionFactory


class ConsequenceOutcomeBasicTests(TestCase):
    """ORM-level wiring — no DB-level constraints exercised here."""

    @classmethod
    def setUpTestData(cls) -> None:
        from world.checks.outcome_models import ConsequenceOutcome, ConsequenceOutcomeModifier

        cls.ConsequenceOutcome = ConsequenceOutcome
        cls.ConsequenceOutcomeModifier = ConsequenceOutcomeModifier

        cls.sheet = CharacterSheetFactory()
        cls.check_type = CheckTypeFactory()
        cls.pool = ConsequencePoolFactory()
        cls.consequence = ConsequenceFactory()
        cls.interaction = InteractionFactory()

    def test_create_with_combat_interaction(self) -> None:
        """Create an outcome linked via combat_interaction; challenge_record is null."""
        outcome = self.ConsequenceOutcome.objects.create(
            character=self.sheet,
            check_type=self.check_type,
            pool=self.pool,
            selected_consequence=self.consequence,
            modifier_total=3,
            summary="Test outcome",
            combat_interaction=self.interaction,
            combat_interaction_timestamp=self.interaction.timestamp,
        )
        self.assertEqual(outcome.combat_interaction_id, self.interaction.pk)
        self.assertEqual(outcome.combat_interaction_timestamp, self.interaction.timestamp)
        self.assertIsNone(outcome.challenge_record_id)

    def test_modifiers_reverse_relation(self) -> None:
        """Two ConsequenceOutcomeModifier rows attach to the outcome."""
        outcome = self.ConsequenceOutcome.objects.create(
            character=self.sheet,
            check_type=self.check_type,
            pool=self.pool,
            combat_interaction=self.interaction,
            combat_interaction_timestamp=self.interaction.timestamp,
        )
        self.ConsequenceOutcomeModifier.objects.create(
            outcome=outcome,
            source_kind=ModifierSourceKind.ROLLMOD,
            source_label="Tier bonus",
            value=2,
        )
        self.ConsequenceOutcomeModifier.objects.create(
            outcome=outcome,
            source_kind=ModifierSourceKind.CONDITION,
            source_label="Stunned",
            value=-1,
        )
        self.assertEqual(outcome.modifiers.count(), 2)

    def test_interaction_field_is_nullable(self) -> None:
        """interaction FK is nullable on the ORM (db_constraint=False)."""
        field = self.ConsequenceOutcome._meta.get_field("combat_interaction")
        self.assertFalse(field.db_constraint)
        self.assertTrue(field.null)

    def test_combat_interaction_timestamp_field_present(self) -> None:
        """Denormalized timestamp field is present and indexed."""
        field = self.ConsequenceOutcome._meta.get_field("combat_interaction_timestamp")
        self.assertTrue(field.null)
        self.assertTrue(field.db_index)

    def test_created_at_auto_populated(self) -> None:
        """created_at is set automatically on creation."""
        outcome = self.ConsequenceOutcome.objects.create(
            character=self.sheet,
            check_type=self.check_type,
            pool=self.pool,
            combat_interaction=self.interaction,
            combat_interaction_timestamp=self.interaction.timestamp,
        )
        self.assertIsNotNone(outcome.created_at)

    def test_modifier_value_negative_allowed(self) -> None:
        """Modifier value can be negative."""
        outcome = self.ConsequenceOutcome.objects.create(
            character=self.sheet,
            check_type=self.check_type,
            pool=self.pool,
            combat_interaction=self.interaction,
            combat_interaction_timestamp=self.interaction.timestamp,
        )
        mod = self.ConsequenceOutcomeModifier.objects.create(
            outcome=outcome,
            source_kind=ModifierSourceKind.FATIGUE,
            source_label="Exhausted",
            value=-5,
        )
        mod.refresh_from_db()
        self.assertEqual(mod.value, -5)


class RecordConsequenceOutcomeTests(TestCase):
    """Tests for the record_consequence_outcome service-function writer."""

    @classmethod
    def setUpTestData(cls) -> None:
        from world.checks.outcome_models import ConsequenceOutcome, ConsequenceOutcomeModifier

        cls.ConsequenceOutcome = ConsequenceOutcome
        cls.ConsequenceOutcomeModifier = ConsequenceOutcomeModifier

        cls.sheet = CharacterSheetFactory()
        cls.check_type = CheckTypeFactory()
        cls.pool = ConsequencePoolFactory()
        cls.consequence = ConsequenceFactory()
        cls.interaction = InteractionFactory()

    def test_record_consequence_outcome_persists_record_and_modifiers(self) -> None:
        """record_consequence_outcome creates one ConsequenceOutcome and two modifier rows."""
        from world.checks.services import record_consequence_outcome
        from world.checks.types import ModifierBreakdown, ModifierContribution

        breakdown = ModifierBreakdown(
            contributions=[
                ModifierContribution(
                    source_kind=ModifierSourceKind.ROLLMOD,
                    source_label="Roll modifier",
                    value=2,
                ),
                ModifierContribution(
                    source_kind=ModifierSourceKind.CONDITION,
                    source_label="Inspired",
                    value=3,
                ),
            ]
        )

        outcome = record_consequence_outcome(
            character_sheet=self.sheet,
            check_type=self.check_type,
            pool=self.pool,
            selected_consequence=self.consequence,
            breakdown=breakdown,
            combat_interaction=self.interaction,
            summary="Test summary",
        )

        # One ConsequenceOutcome row created.
        self.assertEqual(self.ConsequenceOutcome.objects.count(), 1)

        # modifier_total equals breakdown.total (2 + 3 = 5).
        self.assertEqual(outcome.modifier_total, breakdown.total)

        # Two modifier rows attached.
        self.assertEqual(outcome.modifiers.count(), 2)

        # Modifier rows match contributions.
        mods = list(outcome.modifiers.order_by("value"))
        self.assertEqual(mods[0].source_kind, ModifierSourceKind.ROLLMOD)
        self.assertEqual(mods[0].source_label, "Roll modifier")
        self.assertEqual(mods[0].value, 2)
        self.assertEqual(mods[1].source_kind, ModifierSourceKind.CONDITION)
        self.assertEqual(mods[1].source_label, "Inspired")
        self.assertEqual(mods[1].value, 3)

        # combat_interaction_timestamp is populated and equals interaction.timestamp.
        self.assertIsNotNone(outcome.combat_interaction_timestamp)
        self.assertEqual(outcome.combat_interaction_timestamp, self.interaction.timestamp)

    def test_record_consequence_outcome_neither_source_raises(self) -> None:
        """Passing neither combat_interaction nor challenge_record raises ValueError."""
        from world.checks.services import record_consequence_outcome
        from world.checks.types import ModifierBreakdown

        with self.assertRaises(ValueError):
            record_consequence_outcome(
                character_sheet=self.sheet,
                check_type=self.check_type,
                pool=self.pool,
                selected_consequence=None,
                breakdown=ModifierBreakdown(),
            )

    def test_record_consequence_outcome_both_sources_raises(self) -> None:
        """Passing both combat_interaction and challenge_record raises ValueError."""
        from unittest.mock import MagicMock

        from world.checks.services import record_consequence_outcome
        from world.checks.types import ModifierBreakdown

        fake_record = MagicMock()
        with self.assertRaises(ValueError):
            record_consequence_outcome(
                character_sheet=self.sheet,
                check_type=self.check_type,
                pool=self.pool,
                selected_consequence=None,
                breakdown=ModifierBreakdown(),
                combat_interaction=self.interaction,
                challenge_record=fake_record,
            )


@tag("postgres")
class ConsequenceOutcomeConstraintTests(TestCase):
    """DB-level CheckConstraint: exactly one source must be set.

    These tests run on PostgreSQL only — SQLite does not enforce CHECK
    constraints at the DB level.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        cls.sheet = CharacterSheetFactory()
        cls.check_type = CheckTypeFactory()
        cls.pool = ConsequencePoolFactory()
        cls.interaction = InteractionFactory()

    def test_both_null_rejected(self) -> None:
        """Both combat_interaction and challenge_record null → IntegrityError."""
        from django.db import IntegrityError, transaction

        from world.checks.outcome_models import ConsequenceOutcome

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                ConsequenceOutcome.objects.create(
                    character=self.sheet,
                    check_type=self.check_type,
                    pool=self.pool,
                    combat_interaction=None,
                    challenge_record=None,
                )

    def test_both_set_rejected(self) -> None:
        """Both combat_interaction and challenge_record set → IntegrityError."""
        from django.db import IntegrityError, transaction

        from world.checks.outcome_models import ConsequenceOutcome
        from world.mechanics.models import (
            ChallengeApproach,
            ChallengeInstance,
            CharacterChallengeRecord,
        )

        # Build a minimal CharacterChallengeRecord via direct ORM.
        challenge_instance = ChallengeInstance.objects.first()
        if challenge_instance is None:
            self.skipTest("No ChallengeInstance available — seeded on full DB only")

        approach = ChallengeApproach.objects.filter(challenge=challenge_instance.template).first()
        if approach is None:
            self.skipTest("No ChallengeApproach available — seeded on full DB only")

        record = CharacterChallengeRecord.objects.create(
            character=self.sheet.character,
            challenge_instance=challenge_instance,
            approach=approach,
        )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                ConsequenceOutcome.objects.create(
                    character=self.sheet,
                    check_type=self.check_type,
                    pool=self.pool,
                    combat_interaction=self.interaction,
                    combat_interaction_timestamp=self.interaction.timestamp,
                    challenge_record=record,
                )
