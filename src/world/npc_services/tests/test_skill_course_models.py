"""Schema for Academy skill courses and the schooling floor (#4457)."""

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from world.character_creation.factories import SchoolingLineFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.npc_services.constants import OfferKind
from world.npc_services.factories import (
    NPCServiceOfferFactory,
    SkillCourseEnrollmentFactory,
    SkillCourseOfferDetailsFactory,
)


class SchoolingFloorConstraintTests(TestCase):
    def test_rank_zero_floor_refused(self):
        with transaction.atomic(), self.assertRaises(IntegrityError):
            SchoolingLineFactory(rank=0, magic_skill_floor=10)

    def test_ranked_line_carries_a_floor(self):
        line = SchoolingLineFactory(rank=2, magic_skill_floor=20)
        line.refresh_from_db()
        self.assertEqual(line.magic_skill_floor, 20)


class SkillCourseOfferDetailsTests(TestCase):
    def test_session_cannot_exceed_total(self):
        with transaction.atomic(), self.assertRaises(IntegrityError):
            SkillCourseOfferDetailsFactory(total_development=100, session_development=200)

    def test_clean_refuses_offer_ap_cost(self):
        offer = NPCServiceOfferFactory(kind=OfferKind.SKILL_COURSE, ap_cost=3)
        details = SkillCourseOfferDetailsFactory.build(offer=offer)
        with self.assertRaises(ValidationError) as ctx:
            details.full_clean(exclude=["skill", "check_type"])
        self.assertIn("offer", ctx.exception.message_dict)

    def test_clean_accepts_free_offer(self):
        offer = NPCServiceOfferFactory(kind=OfferKind.SKILL_COURSE, ap_cost=0)
        SkillCourseOfferDetailsFactory(offer=offer).full_clean()


class SkillCourseEnrollmentTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.sheet = CharacterSheetFactory()
        cls.course = SkillCourseOfferDetailsFactory()

    def test_one_open_enrollment_per_course(self):
        first = SkillCourseEnrollmentFactory(character_sheet=self.sheet, course=self.course)
        with transaction.atomic(), self.assertRaises(IntegrityError):
            SkillCourseEnrollmentFactory(character_sheet=self.sheet, course=self.course)
        first.completed_at = timezone.now()
        first.save()
        SkillCourseEnrollmentFactory(character_sheet=self.sheet, course=self.course)
