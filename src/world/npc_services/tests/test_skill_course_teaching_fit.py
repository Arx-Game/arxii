"""An Academy course taught under a Tradition is easier for a student who fits it (#4659)."""

from unittest.mock import MagicMock, patch

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from world.character_sheets.factories import CharacterSheetFactory
from world.game_clock.week_services import get_current_game_week
from world.magic.constants import TargetKind
from world.magic.factories import (
    AffinityFactory,
    CharacterGiftFactory,
    GiftFactory,
    ResonanceFactory,
    ThreadFactory,
    TraditionFactory,
    TraditionGiftGrantFactory,
)
from world.magic.models import Affinity, TraditionGiftGrant
from world.magic.services.teaching_fit import get_teaching_config, student_traits
from world.npc_services.effects import _run_course_session
from world.npc_services.factories import (
    NPCRoleFactory,
    SkillCourseEnrollmentFactory,
    SkillCourseOfferDetailsFactory,
)
from world.npc_services.services import (
    _menu_teaching_fits,
    _offer_price,
    _offer_price_payload,
    format_offer_price,
)

DIFFICULTY = 10


class SkillCourseTeachingFitTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.gift = GiftFactory(name="Lantern Gift")
        cls.affinity = AffinityFactory(name="Dawn")
        cls.other_affinity = AffinityFactory(name="Dusk")
        cls.tradition = TraditionFactory(name="House of Dawn")
        cls.tradition.favored_affinities.add(cls.affinity)
        TraditionGiftGrantFactory(tradition=cls.tradition, gift=cls.gift)
        cls.role = NPCRoleFactory(teaches_tradition=cls.tradition)
        cls.course = SkillCourseOfferDetailsFactory(
            offer__role=cls.role, check_difficulty=DIFFICULTY
        )
        cls.week = get_current_game_week()

    def _student(self, *, gift=None, affinity=None):
        """A student holding ``gift`` (a fresh one when only ``affinity`` is given),
        with a GIFT thread on it at a resonance of ``affinity``."""
        sheet = CharacterSheetFactory()
        if gift is None and affinity is not None:
            gift = GiftFactory()
        if gift is not None:
            CharacterGiftFactory(character=sheet, gift=gift)
        if affinity is not None:
            ThreadFactory(
                owner=sheet,
                resonance=ResonanceFactory(affinity=affinity),
                target_kind=TargetKind.GIFT,
                target_trait=None,
                target_gift=gift,
            )
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
        sheet = self._student(gift=self.gift, affinity=self.affinity)
        self.assertEqual(self._difficulty_rolled(sheet), DIFFICULTY - 4)

    def test_one_fit_rolls_two_easier(self) -> None:
        sheet = self._student(gift=self.gift, affinity=self.other_affinity)
        self.assertEqual(self._difficulty_rolled(sheet), DIFFICULTY - 2)

    def test_non_fitting_student_rolls_at_course_difficulty(self) -> None:
        sheet = self._student(gift=GiftFactory(), affinity=self.other_affinity)
        self.assertEqual(self._difficulty_rolled(sheet), DIFFICULTY)

    def test_student_with_no_gift_thread_is_neutral_on_affinity(self) -> None:
        sheet = self._student()
        self.assertEqual(self._difficulty_rolled(sheet), DIFFICULTY)

    def test_role_without_tradition_is_neutral(self) -> None:
        course = SkillCourseOfferDetailsFactory(
            offer__role=NPCRoleFactory(teaches_tradition=None), check_difficulty=DIFFICULTY
        )
        sheet = self._student(gift=self.gift, affinity=self.affinity)
        self.assertEqual(self._difficulty_rolled(sheet, course), DIFFICULTY)
        price = _offer_price(course.offer, sheet, {}, None)
        self.assertIsNone(price.teaching_line)
        self.assertIsNone(price.fit_line)

    def test_menu_lines_name_the_tradition_then_gift_and_affinity(self) -> None:
        sheet = self._student(gift=self.gift, affinity=self.affinity)
        payload = _offer_price_payload(self.course.offer, sheet, {}, None)
        self.assertEqual(payload["teaching_line"], "Taught in the manner of House of Dawn")
        self.assertEqual(
            payload["fit_line"],
            "Fits your Lantern Gift and its Dawn affinity. Sessions are easier for you.",
        )

    def test_fit_line_with_only_the_gift(self) -> None:
        sheet = self._student(gift=self.gift, affinity=self.other_affinity)
        price = _offer_price(self.course.offer, sheet, {}, None)
        self.assertEqual(price.fit_line, "Fits your Lantern Gift. Sessions are easier for you.")

    def test_fit_line_with_only_the_affinity(self) -> None:
        sheet = self._student(affinity=self.affinity)
        price = _offer_price(self.course.offer, sheet, {}, None)
        self.assertEqual(
            price.fit_line, "Fits your Gift's Dawn affinity. Sessions are easier for you."
        )

    def test_non_fitting_student_sees_only_the_tradition(self) -> None:
        sheet = self._student()
        price = _offer_price(self.course.offer, sheet, {}, None)
        self.assertEqual(price.teaching_line, "Taught in the manner of House of Dawn")
        self.assertIsNone(price.fit_line)

    def test_enrolled_student_still_sees_both_lines(self) -> None:
        sheet = self._student(gift=self.gift)
        enrollment = SkillCourseEnrollmentFactory(character_sheet=sheet, course=self.course)
        price = _offer_price(self.course.offer, sheet, {self.course.offer_id: enrollment}, None)
        self.assertEqual(price.teaching_line, "Taught in the manner of House of Dawn")
        self.assertEqual(price.fit_line, "Fits your Lantern Gift. Sessions are easier for you.")
        self.assertNotIn("House of Dawn", format_offer_price(price))

    def test_fit_line_is_dropped_when_staff_ease_nothing(self) -> None:
        """No "easier" claim when both course eases are 0; the Tradition line stays."""
        config = get_teaching_config()
        config.course_ease_gift_fit = 0
        config.course_ease_affinity_fit = 0
        config.save()
        sheet = self._student(gift=self.gift, affinity=self.affinity)
        price = _offer_price(self.course.offer, sheet, {}, None)
        self.assertEqual(price.teaching_line, "Taught in the manner of House of Dawn")
        self.assertIsNone(price.fit_line)
        self.assertEqual(self._difficulty_rolled(sheet), DIFFICULTY)

    def _fit_queries_for_menu(self, offers, sheet) -> int:
        """Fit queries (Gift grant and favored Affinity) one menu serialization makes."""
        tables = (TraditionGiftGrant._meta.db_table, Affinity._meta.db_table)
        with CaptureQueriesContext(connection) as ctx:
            fits = _menu_teaching_fits(offers, student_traits(sheet))
            payloads = [_offer_price_payload(o, sheet, {}, None, fits) for o in offers]
        for payload in payloads:
            self.assertEqual(
                payload["fit_line"],
                "Fits your Lantern Gift and its Dawn affinity. Sessions are easier for you.",
            )
        return sum(
            1 for q in ctx.captured_queries if any(f'FROM "{t}"' in q["sql"] for t in tables)
        )

    def test_menu_resolves_the_fit_once_per_tradition_not_per_course(self) -> None:
        """Two courses under one Tradition cost no more fit queries than one (#4671 review)."""
        sheet = self._student(gift=self.gift, affinity=self.affinity)
        second = SkillCourseOfferDetailsFactory(offer__role=self.role)

        one = self._fit_queries_for_menu([self.course.offer], sheet)
        two = self._fit_queries_for_menu([self.course.offer, second.offer], sheet)

        self.assertGreater(one, 0)
        self.assertEqual(two, one)
