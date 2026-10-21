"""Required-content probes for the magical skills mapping (#4450, #4457).

Unmapped config means "no extra skill term" rather than a failure, so these are
TUNING rows: staff see which magical activities, Paths and Minor Gifts still add
no skill to their roll, and (#4457) which schooling stances set no Magic skill floor,
which Magic skills have no Academy course, and which Path suggestions name a Magic skill.
"""

from __future__ import annotations

from django.test import TestCase

from web.admin.tuning import required_content as rc
from world.character_creation.factories import SchoolingLineFactory
from world.classes.factories import PathFactory
from world.magic.constants import GiftKind, MagicActivity
from world.magic.factories import GiftFactory, MagicActivitySkillFactory
from world.npc_services.constants import OfferKind
from world.npc_services.factories import (
    NPCRoleFactory,
    NPCServiceOfferFactory,
    SkillCourseOfferDetailsFactory,
)
from world.skills.factories import PathSkillSuggestionFactory, SkillFactory, SkillTraitFactory
from world.skills.models import Skill
from world.societies.factories import OrganizationFactory
from world.traits.models import TraitCategory


def _dependency(key: str) -> rc.ContentDependency:
    """The shipped declaration itself, never a hand-copied duplicate."""
    return next(dep for dep in rc._declarations() if dep.key == key)


class MagicSkillProbeDeclarationTests(TestCase):
    def test_all_three_are_tuning_tier_with_admin_links(self) -> None:
        keys = (
            "magic-activity-skills",
            "path-technique-skills",
            "minor-gift-technique-skills",
            "schooling-magic-skill-floors",
            "magic-skill-courses",
            "path-suggestions-name-magic-skills",
        )
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


def _magic_skill(**kwargs: object) -> Skill:
    return SkillFactory(trait=SkillTraitFactory(category=TraitCategory.MAGIC), **kwargs)


class SchoolingMagicSkillFloorProbeTests(TestCase):
    def _resolve(self) -> rc.ProbeResult:
        return _dependency("schooling-magic-skill-floors").probe.resolve(None)

    def test_listed_while_a_stance_sets_no_floor_and_absent_once_authored(self) -> None:
        first = SchoolingLineFactory(rank=1, magic_skill_floor=0)
        SchoolingLineFactory(rank=2, magic_skill_floor=30)

        result = self._resolve()

        self.assertFalse(result.present)
        self.assertEqual(result.missing, ("Rank 1",))

        first.magic_skill_floor = 20
        first.save()

        self.assertTrue(self._resolve().present)

    def test_rank_zero_and_a_missing_rank_are_not_listed(self) -> None:
        """Rank 0 grants nothing, and a missing row is REQUIRED elsewhere."""
        SchoolingLineFactory(rank=0, magic_skill_floor=0)
        SchoolingLineFactory(rank=1, magic_skill_floor=20)

        self.assertTrue(self._resolve().present)


class MagicSkillCourseProbeTests(TestCase):
    def _resolve(self) -> rc.ProbeResult:
        return _dependency("magic-skill-courses").probe.resolve(None)

    def _course(self, skill: Skill, *, affiliated: bool = True) -> None:
        role = NPCRoleFactory(faction_affiliation=OrganizationFactory() if affiliated else None)
        offer_row = NPCServiceOfferFactory(role=role, kind=OfferKind.SKILL_COURSE)
        SkillCourseOfferDetailsFactory(offer=offer_row, skill=skill)

    def test_listed_until_the_skill_has_a_course_on_an_affiliated_role(self) -> None:
        ritualism = _magic_skill()
        theology = _magic_skill()

        result = self._resolve()

        self.assertFalse(result.present)
        self.assertEqual(set(result.missing), {ritualism.trait.name, theology.trait.name})

        self._course(ritualism)

        self.assertEqual(self._resolve().missing, (theology.trait.name,))

        self._course(theology)

        self.assertTrue(self._resolve().present)

    def test_a_course_on_a_role_with_no_faction_does_not_count(self) -> None:
        skill = _magic_skill()
        self._course(skill, affiliated=False)

        self.assertEqual(self._resolve().missing, (skill.trait.name,))

    def test_an_inactive_or_non_magic_skill_is_not_listed(self) -> None:
        _magic_skill(is_active=False)
        SkillFactory()

        self.assertTrue(self._resolve().present)


class PathSuggestionsNameMagicSkillsProbeTests(TestCase):
    def _resolve(self) -> rc.ProbeResult:
        return _dependency("path-suggestions-name-magic-skills").probe.resolve(None)

    def test_listed_as_path_colon_skill_and_absent_once_removed(self) -> None:
        path = PathFactory()
        magic = _magic_skill()
        suggestion = PathSkillSuggestionFactory(character_path=path, skill=magic)
        PathSkillSuggestionFactory(character_path=path, skill=SkillFactory())

        result = self._resolve()

        self.assertFalse(result.present)
        self.assertEqual(result.missing, (f"{path.name}: {magic.trait.name}",))

        suggestion.delete()

        self.assertTrue(self._resolve().present)
