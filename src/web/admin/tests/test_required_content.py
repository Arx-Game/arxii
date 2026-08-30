"""Tests for the required-content sentinel registry and collector (#3444)."""

from __future__ import annotations

from contextlib import contextmanager
from unittest import mock

from django.test import TestCase

from web.admin.tuning import required_content as rc
from world.conditions.factories import ConditionTemplateFactory


def _dep(key: str, probe: rc.ContentProbe, tier: rc.DependencyTier) -> rc.ContentDependency:
    return rc.ContentDependency(
        key=key,
        label=f"label for {key}",
        tier=tier,
        consumer="world/example.py:1 example()",
        consequence="Example breaks.",
        probe=probe,
    )


class TestBuildRegistry(TestCase):
    def test_duplicate_key_rejected(self) -> None:
        probe = rc.AnyRowProbe(label="ConditionTemplate")
        deps = [
            _dep("dup", probe, rc.DependencyTier.REQUIRED),
            _dep("dup", probe, rc.DependencyTier.REQUIRED),
        ]
        with self.assertRaises(ValueError):
            rc.build_registry(deps)

    def test_distinct_keys_accepted(self) -> None:
        probe = rc.AnyRowProbe(label="ConditionTemplate")
        deps = [
            _dep("a", probe, rc.DependencyTier.REQUIRED),
            _dep("b", probe, rc.DependencyTier.TUNING),
        ]
        self.assertEqual(len(rc.build_registry(deps)), 2)


class TestNamedRowsProbe(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        ConditionTemplateFactory(name="Mounted")

    def test_present_when_row_exists(self) -> None:
        probe = rc.NamedRowsProbe(label="ConditionTemplate", names=("Mounted",))
        result = probe.resolve(frozenset({"mounted"}))
        self.assertTrue(result.present)
        self.assertEqual(result.missing, ())

    def test_missing_names_reported(self) -> None:
        probe = rc.NamedRowsProbe(label="ConditionTemplate", names=("Mounted", "Unhorsed"))
        result = probe.resolve(frozenset({"mounted"}))
        self.assertFalse(result.present)
        self.assertEqual(result.missing, ("Unhorsed",))

    def test_matching_is_case_insensitive(self) -> None:
        probe = rc.NamedRowsProbe(label="ConditionTemplate", names=("MOUNTED",))
        self.assertTrue(probe.resolve(frozenset({"mounted"})).present)


class TestCustomProbe(TestCase):
    def test_delegates_to_callable(self) -> None:
        probe = rc.CustomProbe(fn=lambda: rc.ProbeResult(present=False, detail="nope"))
        result = probe.resolve(None)
        self.assertFalse(result.present)
        self.assertEqual(result.detail, "nope")


class DeclarationPatchMixin:
    @contextmanager
    def patch_declarations(self, deps):
        with mock.patch.object(rc, "_declarations", return_value=deps):
            yield


class TestCollector(DeclarationPatchMixin, TestCase):
    """The collector must batch per model, not per declaration."""

    @classmethod
    def setUpTestData(cls) -> None:
        ConditionTemplateFactory(name="Mounted")

    def test_snapshot_separates_tiers_and_presence(self) -> None:
        deps = (
            _dep(
                "present-required",
                rc.NamedRowsProbe(label="ConditionTemplate", names=("Mounted",)),
                rc.DependencyTier.REQUIRED,
            ),
            _dep(
                "missing-required",
                rc.NamedRowsProbe(label="ConditionTemplate", names=("Nonexistent",)),
                rc.DependencyTier.REQUIRED,
            ),
            _dep(
                "missing-tuning",
                rc.AnyRowProbe(label="LevelPowerConfig"),
                rc.DependencyTier.TUNING,
            ),
        )
        with self.patch_declarations(deps):
            snapshot = rc.collect_required_content()
        self.assertEqual(
            [r.dependency.key for r in snapshot.missing_required], ["missing-required"]
        )
        self.assertEqual(
            [r.dependency.key for r in snapshot.present_required], ["present-required"]
        )
        self.assertEqual([r.dependency.key for r in snapshot.missing_tuning], ["missing-tuning"])

    def test_named_probes_batch_to_one_query_per_model(self) -> None:
        deps = tuple(
            _dep(
                f"cond-{index}",
                rc.NamedRowsProbe(label="ConditionTemplate", names=(f"Name {index}",)),
                rc.DependencyTier.REQUIRED,
            )
            for index in range(6)
        )
        with self.patch_declarations(deps):
            # One SELECT for the single distinct model label, regardless of
            # how many declarations name it.
            with self.assertNumQueries(1):
                rc.collect_required_content()
