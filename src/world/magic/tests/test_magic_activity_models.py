"""Config models behind magical skills (#4450).

The activity-to-skill table and the two cast skill fields (a casting style's ``skill``,
#5002, and a technique's own ``skill``). The rolls that read these rows are tested
in the check-engine and cast-path suites; this file covers what the schema guarantees.
"""

from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.test import TestCase

from world.magic.constants import MagicActivity
from world.magic.factories import (
    MagicActivitySkillFactory,
    TechniqueFactory,
    TechniqueStyleFactory,
)
from world.skills.factories import MagicSkillFactory


class MagicActivitySkillTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.skill = MagicSkillFactory()

    def test_unique_activity_skill(self) -> None:
        MagicActivitySkillFactory(activity=MagicActivity.ANIMA_RITUAL, skill=self.skill)
        with self.assertRaises(IntegrityError), transaction.atomic():
            MagicActivitySkillFactory(activity=MagicActivity.ANIMA_RITUAL, skill=self.skill)

    def test_same_skill_may_serve_two_activities(self) -> None:
        MagicActivitySkillFactory(activity=MagicActivity.ANIMA_RITUAL, skill=self.skill)
        other = MagicActivitySkillFactory(activity=MagicActivity.DISPELLING, skill=self.skill)
        self.assertEqual(other.weight, 1)

    def test_skill_delete_blocked_by_activity_row(self) -> None:
        MagicActivitySkillFactory(activity=MagicActivity.CEREMONY, skill=self.skill)
        with self.assertRaises(ProtectedError):
            self.skill.delete()


class SkillDeleteNullsCastSkillTests(TestCase):
    def test_skill_delete_nulls_style_and_technique(self) -> None:
        skill = MagicSkillFactory()
        style = TechniqueStyleFactory(skill=skill)
        technique = TechniqueFactory(skill=skill)
        skill.delete()
        for row in (style, technique):
            row.refresh_from_db()
        self.assertIsNone(style.skill)
        self.assertIsNone(technique.skill)
