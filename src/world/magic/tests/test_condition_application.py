"""Tests for world.magic.services.condition_application.apply_technique_conditions.

Condition application calls bulk_apply_conditions which uses PG-only DISTINCT ON
internally.  Tests that exercise the real apply path are tagged @tag("postgres")
and cannot run on the SQLite fast tier.

Tests that mock bulk_apply_conditions can run on SQLite.
"""

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from django.test import TestCase
from django.test.utils import tag

from world.character_sheets.factories import CharacterSheetFactory
from world.conditions.factories import ConditionTemplateFactory
from world.conditions.types import AppliedConditionResult, ApplyConditionResult
from world.magic.factories import (
    GiftFactory,
    TechniqueAppliedConditionFactory,
    TechniqueFactory,
    TechniqueRemovedConditionFactory,
)
from world.magic.models.techniques import ConditionTargetKind
from world.magic.services.condition_application import apply_technique_conditions


class ApplyTechniqueConditionsEmptyTest(TestCase):
    """Tests that don't touch bulk_apply_conditions — safe on SQLite."""

    def setUp(self) -> None:
        self.sheet = CharacterSheetFactory()
        self.caster_od = self.sheet.character
        self.technique = TechniqueFactory(gift=GiftFactory())

    def test_no_rows_returns_empty_list(self) -> None:
        """Technique with no condition_applications returns []."""
        result = apply_technique_conditions(
            technique=self.technique,
            success_level=2,
            eff_intensity=5,
            targets_by_kind={},
            source_character=self.caster_od,
        )
        self.assertEqual(result, [])

    def test_skips_row_below_minimum_sl(self) -> None:
        """Row with minimum_success_level=3 is skipped when success_level=2."""
        cond = ConditionTemplateFactory(name="HighGateCondition")
        TechniqueAppliedConditionFactory(
            technique=self.technique,
            condition=cond,
            target_kind=ConditionTargetKind.SELF,
            minimum_success_level=3,
        )
        # No real bulk_apply call expected — if it were called it would fail on SQLite.
        with patch("world.magic.services.condition_application.bulk_apply_conditions") as mock_bulk:
            result = apply_technique_conditions(
                technique=self.technique,
                success_level=2,
                eff_intensity=5,
                targets_by_kind={ConditionTargetKind.SELF: [self.caster_od]},
                source_character=self.caster_od,
            )
        mock_bulk.assert_not_called()
        self.assertEqual(result, [])

    def test_empty_target_list_for_kind_skips(self) -> None:
        """When targets_by_kind has no entry for a row's target_kind, it is skipped."""
        cond = ConditionTemplateFactory(name="EnemyCondition")
        TechniqueAppliedConditionFactory(
            technique=self.technique,
            condition=cond,
            target_kind=ConditionTargetKind.ENEMY,
            minimum_success_level=1,
        )
        with patch("world.magic.services.condition_application.bulk_apply_conditions") as mock_bulk:
            result = apply_technique_conditions(
                technique=self.technique,
                success_level=2,
                eff_intensity=5,
                targets_by_kind={},  # no ENEMY entry
                source_character=self.caster_od,
            )
        mock_bulk.assert_not_called()
        self.assertEqual(result, [])


class ApplyTechniqueConditionsMockedBulkTest(TestCase):
    """Tests that mock bulk_apply_conditions — safe on SQLite."""

    def setUp(self) -> None:
        self.sheet = CharacterSheetFactory()
        self.caster_od = self.sheet.character
        self.technique = TechniqueFactory(gift=GiftFactory())
        self.cond = ConditionTemplateFactory(name="TestCond", default_duration_value=2)

    def test_self_condition_targets_caster(self) -> None:
        """SELF-kind row applies to the caster's ObjectDB."""
        TechniqueAppliedConditionFactory(
            technique=self.technique,
            condition=self.cond,
            target_kind=ConditionTargetKind.SELF,
            minimum_success_level=1,
        )
        with patch("world.magic.services.condition_application.bulk_apply_conditions") as mock_bulk:
            mock_bulk.return_value = [ApplyConditionResult(success=True)]
            results = apply_technique_conditions(
                technique=self.technique,
                success_level=1,
                eff_intensity=0,
                targets_by_kind={ConditionTargetKind.SELF: [self.caster_od]},
                source_character=self.caster_od,
            )

        self.assertEqual(len(results), 1)
        self.assertIsInstance(results[0], AppliedConditionResult)
        self.assertEqual(results[0].target, self.caster_od)
        self.assertEqual(results[0].condition, self.cond)
        self.assertTrue(results[0].success)

    def test_success_false_mirrors_bulk_result(self) -> None:
        """AppliedConditionResult.success reflects bulk result's success field."""
        TechniqueAppliedConditionFactory(
            technique=self.technique,
            condition=self.cond,
            target_kind=ConditionTargetKind.SELF,
            minimum_success_level=1,
        )
        with patch("world.magic.services.condition_application.bulk_apply_conditions") as mock_bulk:
            mock_bulk.return_value = [ApplyConditionResult(success=False)]
            results = apply_technique_conditions(
                technique=self.technique,
                success_level=1,
                eff_intensity=0,
                targets_by_kind={ConditionTargetKind.SELF: [self.caster_od]},
                source_character=self.caster_od,
            )

        self.assertEqual(len(results), 1)
        self.assertFalse(results[0].success)

    def test_severity_computed_from_eff_intensity(self) -> None:
        """base_severity + floor(multiplier × eff_intensity) reaches bulk_apply."""
        TechniqueAppliedConditionFactory(
            technique=self.technique,
            condition=self.cond,
            target_kind=ConditionTargetKind.SELF,
            minimum_success_level=1,
            base_severity=2,
            severity_intensity_multiplier=Decimal("1.0"),
            severity_per_extra_sl=0,
        )
        with patch("world.magic.services.condition_application.bulk_apply_conditions") as mock_bulk:
            mock_bulk.return_value = [ApplyConditionResult(success=True)]
            apply_technique_conditions(
                technique=self.technique,
                success_level=1,
                eff_intensity=5,
                targets_by_kind={ConditionTargetKind.SELF: [self.caster_od]},
                source_character=self.caster_od,
            )
        call_args = mock_bulk.call_args[0][0]
        # base_severity=2 + floor(1.0 × 5) = 7
        self.assertEqual(call_args[0].severity, 7)

    def test_duration_falls_back_to_condition_default(self) -> None:
        """When base_duration_rounds is None, falls back to condition.default_duration_value."""
        TechniqueAppliedConditionFactory(
            technique=self.technique,
            condition=self.cond,  # default_duration_value=2
            target_kind=ConditionTargetKind.SELF,
            minimum_success_level=1,
            base_duration_rounds=None,
            duration_intensity_multiplier=Decimal(0),
            duration_per_extra_sl=0,
        )
        with patch("world.magic.services.condition_application.bulk_apply_conditions") as mock_bulk:
            mock_bulk.return_value = [ApplyConditionResult(success=True)]
            apply_technique_conditions(
                technique=self.technique,
                success_level=1,
                eff_intensity=0,
                targets_by_kind={ConditionTargetKind.SELF: [self.caster_od]},
                source_character=self.caster_od,
            )
        call_args = mock_bulk.call_args[0][0]
        self.assertEqual(call_args[0].duration_rounds, 2)

    def test_multiple_targets_for_same_row(self) -> None:
        """When targets_by_kind has multiple targets for a row's kind, each gets an entry."""
        sheet2 = CharacterSheetFactory()
        target2 = sheet2.character
        TechniqueAppliedConditionFactory(
            technique=self.technique,
            condition=self.cond,
            target_kind=ConditionTargetKind.ALLY,
            minimum_success_level=1,
        )
        with patch("world.magic.services.condition_application.bulk_apply_conditions") as mock_bulk:
            mock_bulk.return_value = [
                ApplyConditionResult(success=True),
                ApplyConditionResult(success=True),
            ]
            results = apply_technique_conditions(
                technique=self.technique,
                success_level=1,
                eff_intensity=0,
                targets_by_kind={ConditionTargetKind.ALLY: [self.caster_od, target2]},
                source_character=self.caster_od,
            )

        self.assertEqual(len(results), 2)
        call_args = mock_bulk.call_args[0][0]
        self.assertEqual(len(call_args), 2)
        self.assertEqual(call_args[0].target, self.caster_od)
        self.assertEqual(call_args[1].target, target2)

    def test_source_technique_forwarded_to_bulk(self) -> None:
        """source_technique kwarg passed to bulk_apply_conditions matches the technique."""
        TechniqueAppliedConditionFactory(
            technique=self.technique,
            condition=self.cond,
            target_kind=ConditionTargetKind.SELF,
            minimum_success_level=1,
        )
        with patch("world.magic.services.condition_application.bulk_apply_conditions") as mock_bulk:
            mock_bulk.return_value = [ApplyConditionResult(success=True)]
            apply_technique_conditions(
                technique=self.technique,
                success_level=1,
                eff_intensity=0,
                targets_by_kind={ConditionTargetKind.SELF: [self.caster_od]},
                source_character=self.caster_od,
            )
        self.assertEqual(mock_bulk.call_args.kwargs["source_technique"], self.technique)
        self.assertEqual(mock_bulk.call_args.kwargs["source_character"], self.caster_od)


@tag("postgres")
class ApplyTechniqueConditionsPostgresTest(TestCase):
    """Real bulk_apply_conditions path — requires Postgres (DISTINCT ON).

    Tests here call the real bulk_apply_conditions via apply_technique_conditions
    and assert observable side effects (condition present on the target).
    """

    def setUp(self) -> None:
        from evennia.objects.models import ObjectDB

        self.sheet = CharacterSheetFactory()
        # Ensure the caster has an ObjectDB location so bulk_apply_conditions
        # can resolve context without errors.
        room = ObjectDB.objects.create(
            db_key="TestRoom",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        self.sheet.character.location = room
        self.sheet.character.save()
        self.caster_od = self.sheet.character
        self.technique = TechniqueFactory(gift=GiftFactory())

    def test_self_condition_present_on_caster_after_apply(self) -> None:
        """A SELF-targeted condition row results in a ConditionInstance on the caster."""
        from world.conditions.services import get_active_conditions

        cond = ConditionTemplateFactory(name="SelfTestCond", default_duration_value=2)
        TechniqueAppliedConditionFactory(
            technique=self.technique,
            condition=cond,
            target_kind=ConditionTargetKind.SELF,
            minimum_success_level=1,
            base_severity=1,
        )

        results = apply_technique_conditions(
            technique=self.technique,
            success_level=1,
            eff_intensity=0,
            targets_by_kind={ConditionTargetKind.SELF: [self.caster_od]},
            source_character=self.caster_od,
        )

        self.assertEqual(len(results), 1)
        self.assertTrue(results[0].success)
        self.assertEqual(results[0].target, self.caster_od)
        self.assertEqual(results[0].condition, cond)

        active = get_active_conditions(self.caster_od)
        self.assertTrue(
            any(inst.condition == cond for inst in active),
            "Condition was not found active on caster after apply.",
        )


class RemoveTechniqueConditionsTest(TestCase):
    """Unit tests for remove_technique_conditions (dispel/cleanse, #1585).

    The real remove_condition path routes through get_active_conditions, which uses
    PG-only DISTINCT ON. These gate-logic tests mock remove_condition + perform_check
    so they run on the SQLite fast tier; the end-to-end journey (real apply + remove
    through request_technique_cast) lives in
    world/magic/tests/integration/test_dispel_cast_e2e.py.
    """

    def setUp(self) -> None:
        self.sheet = CharacterSheetFactory()
        self.caster_od = self.sheet.character
        self.technique = TechniqueFactory(gift=GiftFactory())

    def test_no_rows_returns_empty_list(self) -> None:
        """Technique with no removed_conditions returns []."""
        from world.magic.services.condition_application import remove_technique_conditions

        result = remove_technique_conditions(
            technique=self.technique,
            success_level=2,
            targets_by_kind={},
            source_character=self.caster_od,
        )
        self.assertEqual(result, [])

    def test_skips_row_below_minimum_sl(self) -> None:
        """Row with minimum_success_level=3 is skipped when success_level=2."""
        from unittest.mock import patch

        from world.magic.services.condition_application import remove_technique_conditions

        cond = ConditionTemplateFactory(name="HighGateDispel")
        TechniqueRemovedConditionFactory(
            technique=self.technique,
            condition=cond,
            target_kind=ConditionTargetKind.ALLY,
            minimum_success_level=3,
        )
        with (
            patch("world.magic.services.condition_application.remove_condition") as mock_remove,
            patch("world.magic.services.condition_application.perform_check"),
        ):
            result = remove_technique_conditions(
                technique=self.technique,
                success_level=2,
                targets_by_kind={ConditionTargetKind.ALLY: [self.caster_od]},
                source_character=self.caster_od,
            )
        self.assertEqual(result, [])
        mock_remove.assert_not_called()

    def test_can_be_dispelled_false_is_noop(self) -> None:
        """A condition with can_be_dispelled=False is skipped, not removed."""
        from unittest.mock import patch

        from world.magic.services.condition_application import remove_technique_conditions

        cond = ConditionTemplateFactory(name="PlotLocked", can_be_dispelled=False)
        TechniqueRemovedConditionFactory(
            technique=self.technique,
            condition=cond,
            target_kind=ConditionTargetKind.ALLY,
        )
        with (
            patch("world.magic.services.condition_application.remove_condition") as mock_remove,
            patch("world.magic.services.condition_application.get_condition_instance") as mock_get,
        ):
            mock_get.return_value = object()  # condition is present
            result = remove_technique_conditions(
                technique=self.technique,
                success_level=1,
                targets_by_kind={ConditionTargetKind.ALLY: [self.caster_od]},
                source_character=self.caster_od,
            )
        self.assertEqual(len(result), 1)
        self.assertFalse(result[0].success)
        self.assertEqual(result[0].skipped_reason, "not_dispellable")
        mock_remove.assert_not_called()

    def test_absent_condition_is_noop(self) -> None:
        """A condition not present on the target is a not_present no-op."""
        from unittest.mock import patch

        from world.magic.services.condition_application import remove_technique_conditions

        cond = ConditionTemplateFactory(name="AbsentDispel", can_be_dispelled=True)
        TechniqueRemovedConditionFactory(
            technique=self.technique,
            condition=cond,
            target_kind=ConditionTargetKind.ALLY,
        )
        with (
            patch("world.magic.services.condition_application.remove_condition") as mock_remove,
            patch("world.magic.services.condition_application.get_condition_instance") as mock_get,
        ):
            mock_get.return_value = None  # condition absent
            result = remove_technique_conditions(
                technique=self.technique,
                success_level=1,
                targets_by_kind={ConditionTargetKind.ALLY: [self.caster_od]},
                source_character=self.caster_od,
            )
        self.assertEqual(len(result), 1)
        self.assertFalse(result[0].success)
        self.assertEqual(result[0].skipped_reason, "not_present")
        mock_remove.assert_not_called()

    def test_opposed_cure_check_failure_resists(self) -> None:
        """When cure_check_type is set and the check fails (SL<=0), removal is resisted."""
        from unittest.mock import patch

        from world.checks.factories import CheckTypeFactory
        from world.magic.services.condition_application import remove_technique_conditions

        cure_check = CheckTypeFactory()
        cond = ConditionTemplateFactory(
            name="ResistedDispel",
            can_be_dispelled=True,
            cure_check_type=cure_check,
            cure_difficulty=15,
        )
        TechniqueRemovedConditionFactory(
            technique=self.technique,
            condition=cond,
            target_kind=ConditionTargetKind.ALLY,
        )
        fake_result = SimpleNamespace(success_level=0)
        with (
            patch(
                "world.magic.services.condition_application.perform_check", return_value=fake_result
            ),
            patch("world.magic.services.condition_application.remove_condition") as mock_remove,
            patch("world.magic.services.condition_application.get_condition_instance") as mock_get,
        ):
            mock_get.return_value = object()
            result = remove_technique_conditions(
                technique=self.technique,
                success_level=1,
                targets_by_kind={ConditionTargetKind.ALLY: [self.caster_od]},
                source_character=self.caster_od,
            )
        self.assertEqual(len(result), 1)
        self.assertFalse(result[0].success)
        self.assertEqual(result[0].skipped_reason, "resisted")
        mock_remove.assert_not_called()

    def test_opposed_cure_check_success_removes(self) -> None:
        """When cure_check_type is set and the check succeeds (SL>0), removal proceeds."""
        from unittest.mock import patch

        from world.checks.factories import CheckTypeFactory
        from world.magic.services.condition_application import remove_technique_conditions

        cure_check = CheckTypeFactory()
        cond = ConditionTemplateFactory(
            name="CuredDispel",
            can_be_dispelled=True,
            cure_check_type=cure_check,
            cure_difficulty=15,
        )
        TechniqueRemovedConditionFactory(
            technique=self.technique,
            condition=cond,
            target_kind=ConditionTargetKind.ALLY,
            remove_all_stacks=False,
        )
        fake_result = SimpleNamespace(success_level=2)
        with (
            patch(
                "world.magic.services.condition_application.perform_check", return_value=fake_result
            ),
            patch("world.magic.services.condition_application.remove_condition") as mock_remove,
            patch("world.magic.services.condition_application.get_condition_instance") as mock_get,
        ):
            mock_get.return_value = object()
            mock_remove.return_value = True
            result = remove_technique_conditions(
                technique=self.technique,
                success_level=1,
                targets_by_kind={ConditionTargetKind.ALLY: [self.caster_od]},
                source_character=self.caster_od,
            )
        self.assertEqual(len(result), 1)
        self.assertTrue(result[0].success)
        mock_remove.assert_called_once_with(self.caster_od, cond, remove_all_stacks=False)

    def test_null_cure_check_uncontested(self) -> None:
        """When cure_check_type is null, no opposed check is rolled; removal proceeds."""
        from unittest.mock import patch

        from world.magic.services.condition_application import remove_technique_conditions

        cond = ConditionTemplateFactory(name="UncontestedDispel", can_be_dispelled=True)
        TechniqueRemovedConditionFactory(
            technique=self.technique,
            condition=cond,
            target_kind=ConditionTargetKind.ALLY,
        )
        with (
            patch("world.magic.services.condition_application.perform_check") as mock_check,
            patch("world.magic.services.condition_application.remove_condition") as mock_remove,
            patch("world.magic.services.condition_application.get_condition_instance") as mock_get,
        ):
            mock_get.return_value = object()
            mock_remove.return_value = True
            result = remove_technique_conditions(
                technique=self.technique,
                success_level=1,
                targets_by_kind={ConditionTargetKind.ALLY: [self.caster_od]},
                source_character=self.caster_od,
            )
        self.assertEqual(len(result), 1)
        self.assertTrue(result[0].success)
        mock_check.assert_not_called()
