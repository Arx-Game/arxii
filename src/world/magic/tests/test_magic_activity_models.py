"""Config models behind magical skills (#4450).

The activity-to-skill table, the three ``technique_skill`` / ``skill`` fields and the
Gift rule that only a Minor Gift carries one. The rolls that read these rows are tested
in the check-engine and cast-path suites; this file covers what the schema guarantees.
"""

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.test import TestCase

from world.classes.factories import PathFactory
from world.magic.constants import GiftKind, MagicActivity
from world.magic.factories import GiftFactory, MagicActivitySkillFactory, TechniqueFactory
from world.skills.factories import SkillFactory

MAJOR_GIFT_MESSAGE = (
    "A Major Gift's techniques take the caster's Path technique skill. Set it on the Path instead."
)


class MagicActivitySkillTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.skill = SkillFactory()

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


class GiftTechniqueSkillTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.skill = SkillFactory()

    def test_gift_technique_skill_rejected_on_major(self) -> None:
        gift = GiftFactory(kind=GiftKind.MAJOR)
        gift.technique_skill = self.skill
        with self.assertRaises(ValidationError) as ctx:
            gift.full_clean()
        self.assertEqual(ctx.exception.message_dict["technique_skill"], [MAJOR_GIFT_MESSAGE])
        with self.assertRaises(IntegrityError), transaction.atomic():
            gift.save()

    def test_gift_technique_skill_allowed_on_minor(self) -> None:
        gift = GiftFactory(kind=GiftKind.MINOR, technique_skill=self.skill)
        gift.full_clean()
        gift.refresh_from_db()
        self.assertEqual(gift.technique_skill, self.skill)


class SkillDeleteNullsTechniqueSkillTests(TestCase):
    def test_skill_delete_nulls_path_gift_technique(self) -> None:
        skill = SkillFactory()
        path = PathFactory(technique_skill=skill)
        gift = GiftFactory(kind=GiftKind.MINOR, technique_skill=skill)
        technique = TechniqueFactory(skill=skill)
        skill.delete()
        for row in (path, gift, technique):
            row.refresh_from_db()
        self.assertIsNone(path.technique_skill)
        self.assertIsNone(gift.technique_skill)
        self.assertIsNone(technique.skill)
