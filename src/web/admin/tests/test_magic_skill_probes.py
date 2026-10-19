"""Required-content probes for the magical skills mapping (#4450).

Unmapped config means "no extra skill term" rather than a failure, so these are
TUNING rows: staff see which magical activities, Paths and Minor Gifts still add
no skill to their roll.
"""

from __future__ import annotations

from django.test import TestCase

from web.admin.tuning import required_content as rc
from world.classes.factories import PathFactory
from world.magic.constants import GiftKind, MagicActivity
from world.magic.factories import GiftFactory, MagicActivitySkillFactory
from world.skills.factories import SkillFactory


def _dependency(key: str) -> rc.ContentDependency:
    """The shipped declaration itself, never a hand-copied duplicate."""
    return next(dep for dep in rc._declarations() if dep.key == key)


class MagicSkillProbeDeclarationTests(TestCase):
    def test_all_three_are_tuning_tier_with_admin_links(self) -> None:
        keys = ("magic-activity-skills", "path-technique-skills", "minor-gift-technique-skills")
        for key in keys:
            dependency = _dependency(key)
            self.assertEqual(dependency.tier, rc.DependencyTier.TUNING)
            row = rc.DependencyRow(dependency, dependency.probe.resolve(None))
            self.assertIsNotNone(row.admin_url, key)


class UnmappedActivityProbeTests(TestCase):
    def _resolve(self) -> rc.ProbeResult:
        return _dependency("magic-activity-skills").probe.resolve(None)

    def test_probe_lists_unmapped_activities(self) -> None:
        result = self._resolve()
        self.assertFalse(result.present)
        self.assertEqual(len(result.missing), len(MagicActivity))
        self.assertIn(MagicActivity.CEREMONY.label, result.missing)

        MagicActivitySkillFactory(activity=MagicActivity.CEREMONY, skill=SkillFactory())

        result = self._resolve()
        self.assertNotIn(MagicActivity.CEREMONY.label, result.missing)
        self.assertEqual(len(result.missing), len(MagicActivity) - 1)

    def test_an_activity_mapped_only_to_an_inactive_skill_is_listed(self) -> None:
        """The roll skips an inactive skill's row, so the dashboard does too."""
        MagicActivitySkillFactory(
            activity=MagicActivity.CEREMONY, skill=SkillFactory(is_active=False)
        )

        self.assertIn(MagicActivity.CEREMONY.label, self._resolve().missing)

    def test_present_once_every_activity_is_mapped(self) -> None:
        skill = SkillFactory()
        for activity in MagicActivity:
            MagicActivitySkillFactory(activity=activity, skill=skill)
        self.assertTrue(self._resolve().present)


class PathTechniqueSkillProbeTests(TestCase):
    def _resolve(self) -> rc.ProbeResult:
        return _dependency("path-technique-skills").probe.resolve(None)

    def test_probe_lists_paths_without_technique_skill(self) -> None:
        bare = PathFactory(technique_skill=None)
        mapped = PathFactory(technique_skill=SkillFactory())
        inactive = PathFactory(technique_skill=None, is_active=False)

        result = self._resolve()

        self.assertFalse(result.present)
        self.assertIn(bare.name, result.missing)
        self.assertNotIn(mapped.name, result.missing)
        self.assertNotIn(inactive.name, result.missing)

    def test_a_path_whose_technique_skill_is_inactive_is_listed(self) -> None:
        """An inactive technique skill adds no term, so the Path still adds none."""
        path = PathFactory(technique_skill=SkillFactory(is_active=False))

        self.assertIn(path.name, self._resolve().missing)

    def test_present_when_every_active_path_has_one(self) -> None:
        PathFactory(technique_skill=SkillFactory())
        self.assertTrue(self._resolve().present)


class MinorGiftTechniqueSkillProbeTests(TestCase):
    def _resolve(self) -> rc.ProbeResult:
        return _dependency("minor-gift-technique-skills").probe.resolve(None)

    def test_probe_lists_minor_gifts_without_technique_skill(self) -> None:
        minor = GiftFactory(kind=GiftKind.MINOR, technique_skill=None)
        major = GiftFactory(kind=GiftKind.MAJOR, technique_skill=None)
        mapped = GiftFactory(kind=GiftKind.MINOR, technique_skill=SkillFactory())

        result = self._resolve()

        self.assertFalse(result.present)
        self.assertIn(minor.name, result.missing)
        self.assertNotIn(major.name, result.missing)
        self.assertNotIn(mapped.name, result.missing)

    def test_a_minor_gift_whose_technique_skill_is_inactive_is_listed(self) -> None:
        """An inactive technique skill adds no term, so the Gift still adds none."""
        gift = GiftFactory(kind=GiftKind.MINOR, technique_skill=SkillFactory(is_active=False))

        self.assertIn(gift.name, self._resolve().missing)

    def test_present_when_only_a_major_gift_lacks_one(self) -> None:
        GiftFactory(kind=GiftKind.MAJOR, technique_skill=None)
        self.assertTrue(self._resolve().present)
