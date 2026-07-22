"""Tests for ConditionInstance.source_vow stamping at apply time (#2643).

Stamped from the applier's FIRST engaged covenant role, resolved to its ANCHOR
(``parent_role`` when the engaged role resolved to a sub-role, else the role
itself) — never a resolved sub-role. Null when the applier has no engaged role.
"""

from __future__ import annotations

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.conditions.factories import ConditionTemplateFactory
from world.conditions.models import ConditionInstance
from world.conditions.services import (
    _resolve_source_vow_anchor,
    apply_condition,
    bulk_apply_conditions,
)
from world.conditions.types import BulkConditionApplication
from world.covenants.factories import CharacterCovenantRoleFactory, CovenantRoleFactory


class ResolveSourceVowAnchorUnitTests(TestCase):
    """Direct unit tests of the private resolver (no DB engagement setup needed
    for the "no roles"/"stub" cases)."""

    def test_none_source_character_returns_none(self):
        self.assertIsNone(_resolve_source_vow_anchor(None))

    def test_character_with_no_covenant_roles_handler_returns_none(self):
        class _NoHandler:
            pass

        self.assertIsNone(_resolve_source_vow_anchor(_NoHandler()))

    def test_anchor_is_parent_role_when_first_engaged_role_is_a_subrole(self):
        class _StubHandler:
            def __init__(self, roles):
                self._roles = roles

            def currently_engaged_roles(self):
                return self._roles

        class _StubCharacter:
            def __init__(self, roles):
                self.covenant_roles = _StubHandler(roles)

        parent = CovenantRoleFactory()
        sub = CovenantRoleFactory(parent_role=parent)

        anchor = _resolve_source_vow_anchor(_StubCharacter([sub]))

        self.assertEqual(anchor, parent)


class SourceVowStampingIntegrationTests(TestCase):
    """Full apply-time stamping via apply_condition / bulk_apply_conditions."""

    def setUp(self):
        self.applier = CharacterFactory()
        self.applier_sheet = CharacterSheetFactory(character=self.applier)
        self.target = CharacterFactory()
        self.condition = ConditionTemplateFactory(name="vow-stamp-test")

    def test_no_engaged_role_stamps_null(self):
        result = apply_condition(
            target=self.target, condition=self.condition, source_character=self.applier
        )

        self.assertIsNotNone(result.instance)
        self.assertIsNone(result.instance.source_vow)

    def test_engaged_role_is_stamped_via_apply_condition(self):
        role = CovenantRoleFactory()
        CharacterCovenantRoleFactory(
            character_sheet=self.applier_sheet, covenant_role=role, engaged=True
        )

        result = apply_condition(
            target=self.target, condition=self.condition, source_character=self.applier
        )

        self.assertIsNotNone(result.instance)
        self.assertEqual(result.instance.source_vow_id, role.pk)

    def test_non_engaged_role_is_not_stamped(self):
        role = CovenantRoleFactory()
        CharacterCovenantRoleFactory(
            character_sheet=self.applier_sheet, covenant_role=role, engaged=False
        )

        result = apply_condition(
            target=self.target, condition=self.condition, source_character=self.applier
        )

        self.assertIsNotNone(result.instance)
        self.assertIsNone(result.instance.source_vow)

    def test_bulk_apply_conditions_stamps_the_batch_shared_vow(self):
        role = CovenantRoleFactory()
        CharacterCovenantRoleFactory(
            character_sheet=self.applier_sheet, covenant_role=role, engaged=True
        )
        other_target = CharacterFactory()

        applications = [
            BulkConditionApplication(target=self.target, template=self.condition, severity=1),
            BulkConditionApplication(target=other_target, template=self.condition, severity=1),
        ]
        results = bulk_apply_conditions(applications, source_character=self.applier)

        self.assertEqual(len(results), 2)
        for result in results:
            self.assertEqual(result.instance.source_vow_id, role.pk)

        self.assertEqual(
            ConditionInstance.objects.filter(source_vow_id=role.pk).count(),
            2,
        )
