"""An Academy course taught under a Tradition is easier for a student who fits it (#4659)."""

from unittest.mock import MagicMock, patch

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.game_clock.week_services import get_current_game_week
from world.magic.factories import (
    AffinityFactory,
    CharacterAuraFactory,
    CharacterGiftFactory,
    GiftFactory,
    TraditionFactory,
    TraditionGiftGrantFactory,
)
from world.magic.types.aura import AffinityType
from world.npc_services.effects import _run_course_session
from world.npc_services.factories import (
    NPCRoleFactory,
    SkillCourseEnrollmentFactory,
    SkillCourseOfferDetailsFactory,
)
from world.npc_services.services import _offer_price, _offer_price_payload, format_offer_price

DIFFICULTY = 10


def _aura(sheet, dominant: str) -> None:
    amounts = {"celestial": 0, "primal": 0, "abyssal": 0}
    amounts[dominant] = 100
    CharacterAuraFactory(character=sheet, **amounts)


class SkillCourseTeachingFitTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.gift = GiftFactory(name="Lantern Gift")
        cls.affinity = AffinityFactory(name="Dawn", aura_type=AffinityType.CELESTIAL)
        cls.tradition = TraditionFactory(name="House of Dawn")
        cls.tradition.favored_affinities.add(cls.affinity)
        TraditionGiftGrantFactory(tradition=cls.tradition, gift=cls.gift)
        cls.role = NPCRoleFactory(teaches_tradition=cls.tradition)
        cls.course = SkillCourseOfferDetailsFactory(
            offer__role=cls.role, check_difficulty=DIFFICULTY
        )
        cls.week = get_current_game_week()

    def _student(self, *, gift=None, aura: str | None = None):
        sheet = CharacterSheetFactory()
        if gift is not None:
            CharacterGiftFactory(character=sheet, gift=gift)
        if aura is not None:
            _aura(sheet, aura)
        return sheet

    def _difficulty_rolled(self, sheet, course=None) -> int:
        course = course or self.course
        enrollment = SkillCourseEnrollmentFactory(character_sheet=sheet, course=course)
        result = MagicMock(outcome=None, outcome_name="Failure")
        with patch(
            "world.checks.services.perform_check_with_modifiers", return_value=result
        ) as check:
            _run_course_session(
                course.offer, course, sheet, enrollment, rating=0, week_pk=self.week.pk
            )
        return check.call_args.kwargs["target_difficulty"]

    def test_both_fit_rolls_four_easier(self) -> None:
        sheet = self._student(gift=self.gift, aura=AffinityType.CELESTIAL)
        self.assertEqual(self._difficulty_rolled(sheet), DIFFICULTY - 4)

    def test_one_fit_rolls_two_easier(self) -> None:
        sheet = self._student(gift=self.gift, aura=AffinityType.ABYSSAL)
        self.assertEqual(self._difficulty_rolled(sheet), DIFFICULTY - 2)

    def test_non_fitting_student_rolls_at_course_difficulty(self) -> None:
        sheet = self._student(gift=GiftFactory(), aura=AffinityType.ABYSSAL)
        self.assertEqual(self._difficulty_rolled(sheet), DIFFICULTY)

    def test_student_with_no_aura_row_is_neutral_on_affinity(self) -> None:
        sheet = self._student()
        self.assertEqual(self._difficulty_rolled(sheet), DIFFICULTY)

    def test_role_without_tradition_is_neutral(self) -> None:
        course = SkillCourseOfferDetailsFactory(
            offer__role=NPCRoleFactory(teaches_tradition=None), check_difficulty=DIFFICULTY
        )
        sheet = self._student(gift=self.gift, aura=AffinityType.CELESTIAL)
        self.assertEqual(self._difficulty_rolled(sheet, course), DIFFICULTY)
        self.assertIsNone(_offer_price(course.offer, sheet, {}, None).teaching_line)

    def test_menu_line_names_gift_and_affinity(self) -> None:
        sheet = self._student(gift=self.gift, aura=AffinityType.CELESTIAL)
        payload = _offer_price_payload(self.course.offer, sheet, {}, None)
        self.assertEqual(
            payload["teaching_line"],
            "Taught in the manner of House of Dawn. Teaches well: your Lantern Gift and "
            "your Dawn affinity. Sessions are easier for you.",
        )

    def test_menu_line_with_only_the_affinity(self) -> None:
        sheet = self._student(aura=AffinityType.CELESTIAL)
        line = _offer_price(self.course.offer, sheet, {}, None).teaching_line
        self.assertEqual(
            line,
            "Taught in the manner of House of Dawn. Teaches well: your Dawn affinity. "
            "Sessions are easier for you.",
        )

    def test_menu_line_for_a_non_fitting_student_names_only_the_tradition(self) -> None:
        sheet = self._student()
        line = _offer_price(self.course.offer, sheet, {}, None).teaching_line
        self.assertEqual(line, "Taught in the manner of House of Dawn")

    def test_enrolled_student_still_sees_the_line(self) -> None:
        sheet = self._student(gift=self.gift)
        enrollment = SkillCourseEnrollmentFactory(character_sheet=sheet, course=self.course)
        price = _offer_price(self.course.offer, sheet, {self.course.offer_id: enrollment}, None)
        self.assertIn("Teaches well: your Lantern Gift.", price.teaching_line)
        self.assertNotIn("House of Dawn", format_offer_price(price))
