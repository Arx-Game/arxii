"""Tests for Task 8: Renew the Oath rite seed (factory + wire helper).

Verifies that:
- CovenantRiteFactory builds a well-formed CovenantRite with the correct
  service function path, ritual name, and UNTIL_END_OF_COMBAT condition.
- wire_covenant_rite_content() is idempotent: two calls yield exactly one
  Ritual row and one CovenantRite row.
"""

from __future__ import annotations

from django.test import TestCase

from world.conditions.constants import DurationType
from world.covenants.factories import CovenantRiteFactory, wire_covenant_rite_content
from world.covenants.models import CovenantRite
from world.magic.models import Ritual


class CovenantRiteFactoryTests(TestCase):
    """CovenantRiteFactory smoke tests."""

    def test_ritual_service_function_path(self) -> None:
        """The backing ritual must dispatch to perform_covenant_rite."""
        rite = CovenantRiteFactory()
        self.assertEqual(
            rite.ritual.service_function_path,
            "world.covenants.services.perform_covenant_rite",
        )

    def test_ritual_name(self) -> None:
        """The backing ritual must be named 'Renew the Oath'."""
        rite = CovenantRiteFactory()
        self.assertEqual(rite.ritual.name, "Renew the Oath")

    def test_granted_condition_duration_type(self) -> None:
        """granted_condition must default to UNTIL_END_OF_COMBAT duration."""
        rite = CovenantRiteFactory()
        self.assertEqual(
            rite.granted_condition.default_duration_type,
            DurationType.UNTIL_END_OF_COMBAT,
        )

    def test_gate_fields(self) -> None:
        """min_covenant_level, min_members_present, base_severity defaults."""
        rite = CovenantRiteFactory()
        self.assertEqual(rite.min_covenant_level, 2)
        self.assertEqual(rite.min_members_present, 2)
        self.assertEqual(rite.base_severity, 2)
        self.assertEqual(rite.severity_per_extra_participant, 1)
        self.assertIsNone(rite.max_severity)

    def test_covenant_type_is_durance(self) -> None:
        """Reference rite scopes to DURANCE covenant type."""
        from world.covenants.constants import CovenantType

        rite = CovenantRiteFactory()
        self.assertEqual(rite.covenant_type, CovenantType.DURANCE)


class WireCovenantRiteContentIdempotencyTests(TestCase):
    """wire_covenant_rite_content() must be idempotent."""

    def test_single_call_creates_ritual_and_rite(self) -> None:
        """One call produces exactly one Ritual and one CovenantRite."""
        wire_covenant_rite_content()
        self.assertEqual(Ritual.objects.filter(name="Renew the Oath").count(), 1)
        self.assertEqual(CovenantRite.objects.filter(ritual__name="Renew the Oath").count(), 1)

    def test_double_call_does_not_duplicate(self) -> None:
        """Two calls still yield exactly one Ritual and one CovenantRite."""
        wire_covenant_rite_content()
        wire_covenant_rite_content()
        self.assertEqual(Ritual.objects.filter(name="Renew the Oath").count(), 1)
        self.assertEqual(CovenantRite.objects.filter(ritual__name="Renew the Oath").count(), 1)

    def test_returns_covenant_rite(self) -> None:
        """wire_covenant_rite_content returns the CovenantRite instance."""
        result = wire_covenant_rite_content()
        self.assertIsInstance(result, CovenantRite)
        self.assertEqual(result.ritual.name, "Renew the Oath")
