"""Schema for Academy skill courses and the schooling floor (#4457)."""

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from evennia_extensions.factories import AccountFactory
from world.character_creation.factories import SchoolingLineFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.npc_services.constants import OfferKind
from world.npc_services.factories import (
    NPCRoleFactory,
    NPCServiceOfferFactory,
    SkillCourseEnrollmentFactory,
    SkillCourseOfferDetailsFactory,
)
from world.skills.factories import SkillFactory
from world.societies.factories import OrganizationFactory
from world.traits.models import TraitCategory


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

    def test_zero_total_development_refused(self):
        with transaction.atomic(), self.assertRaises(IntegrityError):
            SkillCourseOfferDetailsFactory(total_development=0, session_development=0)

    def test_zero_session_development_refused(self):
        with (
            transaction.atomic(),
            self.assertRaisesMessage(IntegrityError, "course_session_development_positive"),
        ):
            SkillCourseOfferDetailsFactory(total_development=100, session_development=0)

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


class SkillCourseOfferDetailsAdminTests(TestCase):
    """The add and change pages draw the demo's form, with its two derived rows."""

    @classmethod
    def setUpTestData(cls):
        cls.staff = AccountFactory(is_staff=True, is_superuser=True)
        role = NPCRoleFactory(
            name="Academy Trainer",
            faction_affiliation=OrganizationFactory(name="Shroudwatch Academy"),
        )
        cls.course = SkillCourseOfferDetailsFactory(
            offer=NPCServiceOfferFactory(role=role, kind=OfferKind.SKILL_COURSE),
            skill=SkillFactory(trait__name="occult", trait__category=TraitCategory.MAGIC),
        )

    def setUp(self):
        self.client.force_login(self.staff)

    def test_add_page_renders_the_fields_in_the_demo_order(self):
        response = self.client.get(reverse("admin:arxii_skillcourseofferdetails_add"))

        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        labels = [
            "Offer",
            "Skill",
            "Sold by",
            "Total development",
            "Session development",
            "Session AP cost",
            "Coin cost (coppers)",
            "Check type",
            "Check difficulty",
        ]
        positions = [body.index(f"{label}:</label>") for label in labels]
        self.assertEqual(positions, sorted(positions))

    def test_change_page_names_who_sells_it_and_the_skill_category(self):
        url = reverse("admin:arxii_skillcourseofferdetails_change", args=[self.course.pk])

        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Sold by")
        self.assertContains(
            response, "Derived, read-only: Academy Trainer, for Shroudwatch Academy."
        )
        self.assertContains(response, "Derived, read-only: category Magic.")

    def test_a_role_with_no_house_says_so(self):
        course = SkillCourseOfferDetailsFactory(
            offer=NPCServiceOfferFactory(
                role=NPCRoleFactory(name="Hedge Tutor", faction_affiliation=None),
                kind=OfferKind.SKILL_COURSE,
            )
        )
        url = reverse("admin:arxii_skillcourseofferdetails_change", args=[course.pk])

        self.assertContains(self.client.get(url), "Derived, read-only: Hedge Tutor (no house).")
