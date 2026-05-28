from django.test import TestCase

from actions.base import Action
from actions.constants import TargetKind
from actions.types import StrainAvailability, TargetFilters, TargetSpec, TargetType


class TargetSpecTests(TestCase):
    def test_default_filters(self) -> None:
        f = TargetFilters()
        self.assertFalse(f.in_same_scene)
        self.assertFalse(f.in_same_zone)
        self.assertFalse(f.exclude_self)
        self.assertFalse(f.must_be_conscious)

    def test_target_spec_construction(self) -> None:
        spec = TargetSpec(
            kind=TargetKind.PERSONA,
            cardinality=TargetType.SINGLE,
            filters=TargetFilters(in_same_scene=True, exclude_self=True),
        )
        self.assertEqual(spec.kind, TargetKind.PERSONA)
        self.assertEqual(spec.cardinality, TargetType.SINGLE)
        self.assertTrue(spec.filters.in_same_scene)

    def test_strain_availability_defaults(self) -> None:
        a = StrainAvailability(cap=10)
        self.assertEqual(a.cap, 10)
        self.assertEqual(a.default, 0)


class ActionBaseClassFieldsTests(TestCase):
    def test_action_has_target_kind_default_none(self) -> None:
        self.assertIsNone(Action.target_kind)

    def test_action_has_target_filters_default_none(self) -> None:
        self.assertIsNone(Action.target_filters)
