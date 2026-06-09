"""
Tests for collect_check_modifiers() aggregator.

Verifies that the function correctly collects CONDITION and ROLLMOD contributions,
omits zero rollmod, and returns a ModifierBreakdown with the right total.

Setup note
----------
Mutable fixtures (the CharacterSheet whose rollmod changes per test) are
created in setUp() rather than setUpTestData().  setUpTestData deepcopies
objects for each method, which carries stale cached relations (including the
reverse ``sheet_data`` on ObjectDB).  Per-method setUp avoids this and keeps
the identity map clean.  Immutable lookup rows (CheckType, ConditionTemplate,
ConditionCheckModifier) live in setUpTestData for speed.
"""

from django.test import TestCase
from evennia.objects.models import ObjectDB

from world.character_sheets.factories import CharacterSheetFactory
from world.checks.constants import ModifierSourceKind
from world.checks.factories import CheckTypeFactory
from world.conditions.factories import (
    ConditionCheckModifierFactory,
    ConditionInstanceFactory,
    ConditionTemplateFactory,
)


class CollectCheckModifiersTest(TestCase):
    """Tests for collect_check_modifiers() combining conditions + rollmod."""

    @classmethod
    def setUpTestData(cls):
        # Immutable lookup rows — safe to share across methods.
        cls.check_type = CheckTypeFactory(name="combat-attack-collect")
        cls.frightened = ConditionTemplateFactory(name="frightened-collect")
        # Condition gives -3 to the check type
        ConditionCheckModifierFactory(
            condition=cls.frightened,
            check_type=cls.check_type,
            modifier_value=-3,
        )

    def setUp(self):
        # Mutable per-test: fresh ObjectDB + CharacterSheet (rollmod=0 default).
        self.target = ObjectDB.objects.create(db_key="CollectModTarget")
        self.sheet = CharacterSheetFactory(character=self.target)

    def test_condition_and_rollmod_combined_total(self):
        """An active -3 condition + rollmod=2 gives total == -1."""
        from world.checks.services import collect_check_modifiers

        ConditionInstanceFactory(target=self.target, condition=self.frightened)
        self.sheet.rollmod = 2
        self.sheet.save(update_fields=["rollmod"])

        breakdown = collect_check_modifiers(self.sheet, self.check_type)

        assert breakdown.total == -1

    def test_condition_contribution_present(self):
        """A CONDITION contribution of -3 is included."""
        from world.checks.services import collect_check_modifiers

        ConditionInstanceFactory(target=self.target, condition=self.frightened)
        self.sheet.rollmod = 2
        self.sheet.save(update_fields=["rollmod"])

        breakdown = collect_check_modifiers(self.sheet, self.check_type)

        condition_contributions = [
            c for c in breakdown.contributions if c.source_kind == ModifierSourceKind.CONDITION
        ]
        assert len(condition_contributions) == 1
        assert condition_contributions[0].value == -3

    def test_rollmod_contribution_present(self):
        """A non-zero rollmod emits exactly one ROLLMOD contribution."""
        from world.checks.services import collect_check_modifiers

        ConditionInstanceFactory(target=self.target, condition=self.frightened)
        self.sheet.rollmod = 2
        self.sheet.save(update_fields=["rollmod"])

        breakdown = collect_check_modifiers(self.sheet, self.check_type)

        rollmod_contributions = [
            c for c in breakdown.contributions if c.source_kind == ModifierSourceKind.ROLLMOD
        ]
        assert len(rollmod_contributions) == 1
        assert rollmod_contributions[0].value == 2

    def test_only_condition_and_rollmod_contributions(self):
        """With scene=None and no equipment, ONLY condition + rollmod contributions appear."""
        from world.checks.services import collect_check_modifiers

        ConditionInstanceFactory(target=self.target, condition=self.frightened)
        self.sheet.rollmod = 2
        self.sheet.save(update_fields=["rollmod"])

        breakdown = collect_check_modifiers(self.sheet, self.check_type, scene=None)

        kinds = {c.source_kind for c in breakdown.contributions}
        assert kinds == {ModifierSourceKind.CONDITION, ModifierSourceKind.ROLLMOD}
        assert len(breakdown.contributions) == 2

    def test_zero_rollmod_omitted(self):
        """When rollmod is 0, no ROLLMOD contribution is emitted."""
        from world.checks.services import collect_check_modifiers

        ConditionInstanceFactory(target=self.target, condition=self.frightened)
        # rollmod is 0 by default from CharacterSheetFactory

        breakdown = collect_check_modifiers(self.sheet, self.check_type)

        rollmod_contributions = [
            c for c in breakdown.contributions if c.source_kind == ModifierSourceKind.ROLLMOD
        ]
        assert rollmod_contributions == []

    def test_no_conditions_no_rollmod_empty_breakdown(self):
        """No active conditions, rollmod=0 → empty contributions, total==0."""
        from world.checks.services import collect_check_modifiers

        # No ConditionInstances; rollmod=0 by default
        breakdown = collect_check_modifiers(self.sheet, self.check_type)

        assert breakdown.contributions == []
        assert breakdown.total == 0


class CollectCheckModifiersMockCheckTypeTest(TestCase):
    """Regression: collect_check_modifiers must not raise when check_type is a MagicMock.

    Combat resolver tests (e.g. AnimaDeductionTest) pass MagicMock() as
    offense_check_type to bypass the check-roll pipeline.  The EQUIPMENT branch
    introduced in #851 previously crashed with:

        TypeError: Field 'id' expected a number but got []

    because it unconditionally filtered ItemCheckModifier by check_type=<MagicMock>,
    and Django tried to coerce the mock's pk to an integer.  The guard added in
    the fix short-circuits the equipment (and scene) query when check_type is not
    a real Django Model instance, so mock callers get a graceful empty breakdown
    instead of a TypeError.
    """

    def setUp(self):
        self.target = ObjectDB.objects.create(db_key="MockCheckTypeTarget")
        self.sheet = CharacterSheetFactory(character=self.target)

    def test_mock_check_type_does_not_raise(self):
        """collect_check_modifiers with MagicMock check_type must not raise."""
        from unittest.mock import MagicMock

        from world.checks.services import collect_check_modifiers

        mock_check_type = MagicMock()
        # Must not raise TypeError regardless of active conditions or equipped items.
        breakdown = collect_check_modifiers(self.sheet, mock_check_type)
        # EQUIPMENT branch skipped → no EQUIPMENT contributions
        equipment_kinds = [
            c for c in breakdown.contributions if c.source_kind == ModifierSourceKind.EQUIPMENT
        ]
        assert equipment_kinds == []

    def test_mock_check_type_total_is_zero_with_no_conditions_or_rollmod(self):
        """With no conditions/rollmod and a mock check_type, total must be 0."""
        from unittest.mock import MagicMock

        from world.checks.services import collect_check_modifiers

        mock_check_type = MagicMock()
        breakdown = collect_check_modifiers(self.sheet, mock_check_type)
        assert breakdown.total == 0
