"""Journeys for an Academy skill course (#4457).

A course is enrolled once, for coin and one Golden Hare, and the enrolling acceptance runs
the first session. Every later acceptance of the same offer is one session: AP, then a
training roll whose outcome scales the development, at most one session per course per
game week. A refusal charges nothing. Each journey stands a learner in front of the
Academy's teacher, takes the course through the real ``hire`` command (or the web
dispatch once), then reads back what she was told and what she still holds.

The expected numbers come from the course the spec authors (1500 development, 300 a
session, 6 AP a session, 2 silver), the authored outcome multipliers (botch and failure 0,
partial 0.5, success 1.0, critical 1.5) and the skill rule that a level costs
``(value - 9) x 100`` development. Names are invented.
"""

from __future__ import annotations

from decimal import Decimal

from django.utils import timezone
from evennia.utils.ansi import strip_ansi

from evennia_extensions.factories import RoomProfileFactory
from integration_tests.harness import JourneyCase
from world.action_points.models import ActionPointPool
from world.character_creation.sheet_writers import set_skill_values
from world.checks.factories import CheckCategoryFactory, CheckTypeFactory, CheckTypeTraitFactory
from world.checks.services import perform_check
from world.checks.test_helpers import force_check_outcome
from world.currency.models import FavorTokenDetails
from world.currency.services import (
    get_or_create_purse,
    get_or_create_treasury,
    mint_favor_token,
    redeem_favor_token,
    transfer,
)
from world.game_clock.week_services import advance_game_week
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
from world.magic.models import TrainingOutcomeAward
from world.npc_services.constants import OfferKind
from world.npc_services.factories import (
    FunctionaryFactory,
    NPCRoleFactory,
    NPCServiceOfferFactory,
    SkillCourseEnrollmentFactory,
    SkillCourseOfferDetailsFactory,
)
from world.npc_services.models import SkillCourseEnrollment
from world.progression.factories import ExperiencePointsDataFactory
from world.progression.models import TraitRatingUnlock, TraitXPCost, XPCostChart, XPCostEntry
from world.skills.factories import SkillFactory, SkillTraitFactory
from world.skills.models import CharacterSkillValue
from world.societies.constants import ObligationState
from world.societies.factories import OrganizationFactory, OrganizationObligationFactory
from world.traits.factories import CheckOutcomeFactory, CheckSystemSetupFactory
from world.traits.models import (
    CharacterTraitValue,
    CheckOutcome,
    PointConversionRange,
    TraitCategory,
    TraitChangeSource,
    TraitType,
)

TOTAL = 1500
SESSION = 300
SESSION_AP = 6
COIN = 20  # 2 silver, written in coppers
STARTING_AP = 200
STARTING_COIN = 100


class _AcademyCourseCase(JourneyCase):
    """Ysmay before Magister Cadwen, who teaches Occult at the Shroudwatch Academy."""

    def setUp(self) -> None:
        super().setUp()
        CheckSystemSetupFactory.create()
        # One check point per rating point, so a skill's points in a roll are its rating.
        PointConversionRange.objects.get_or_create(
            trait_type=TraitType.SKILL,
            min_value=1,
            defaults={"max_value": 100, "points_per_level": 1},
        )
        self.outcomes = {
            "botch": CheckOutcomeFactory(name="Botch", success_level=-2),
            "failure": CheckOutcome.objects.get(name="Failure"),
            "partial": CheckOutcome.objects.get(name="Partial Success"),
            "success": CheckOutcome.objects.get(name="Success"),
            "critical": CheckOutcome.objects.get(name="Critical Success"),
        }
        for key, multiplier in (
            ("botch", "0"),
            ("failure", "0"),
            ("partial", "0.5"),
            ("success", "1.0"),
            ("critical", "1.5"),
        ):
            TrainingOutcomeAward.objects.update_or_create(
                outcome_tier=self.outcomes[key],
                defaults={"dev_point_multiplier": Decimal(multiplier)},
            )

        self.hall = self.make_room("The Shroudwatch Hall")
        self.academy = OrganizationFactory(name="Shroudwatch Academy")
        self.role = NPCRoleFactory(name="Academy Teacher", faction_affiliation=self.academy)
        FunctionaryFactory(
            role=self.role,
            room=RoomProfileFactory(objectdb=self.hall),
            name_override="Magister Cadwen",
        )
        self.occult = SkillFactory(
            trait=SkillTraitFactory(name="Occult", category=TraitCategory.MAGIC)
        )
        self.offer = NPCServiceOfferFactory(
            role=self.role,
            kind=OfferKind.SKILL_COURSE,
            label="Course: Occult",
            is_final=True,
            ap_cost=0,
        )
        self.course = SkillCourseOfferDetailsFactory(
            offer=self.offer,
            skill=self.occult,
            total_development=TOTAL,
            session_development=SESSION,
            session_ap_cost=SESSION_AP,
            coin_cost=COIN,
            check_type=CheckTypeFactory(),
            check_difficulty=0,
        )

        self.ysmay = self.make_player("Ysmay", room=self.hall)
        self.sheet = self.ysmay.sheet_data
        self.set_ap(STARTING_AP)
        transfer(
            amount=STARTING_COIN,
            reason="a purse for the journey",
            to_purse=get_or_create_purse(self.sheet),
        )
        self.hare = self.give_hare()
        # She came in owing the Academy a Hare and has paid it off.
        OrganizationObligationFactory(
            debtor=self.sheet,
            creditor=self.academy,
            state=ObligationState.SETTLED,
            settled_at=timezone.now(),
        )

    # -- what she does --------------------------------------------------------

    def take_course(self, outcome: str | None = None) -> str:
        """Ask Magister Cadwen for the course, with the session's roll pinned to ``outcome``."""
        self.telnet(self.ysmay, "hire Magister Cadwen")
        if outcome is None:
            return strip_ansi(self.telnet(self.ysmay, f"hire offer {self.offer.pk}"))
        with force_check_outcome(self.outcomes[outcome]):
            return strip_ansi(self.telnet(self.ysmay, f"hire offer {self.offer.pk}"))

    # -- the world around her ---------------------------------------------------

    def set_ap(self, amount: int) -> None:
        pool = ActionPointPool.get_or_create_for_character(self.ysmay)
        pool.current = amount
        pool.save()

    def give_hare(self) -> FavorTokenDetails:
        return mint_favor_token(self.academy, self.sheet, provenance_note="a deed for the Academy")

    def made_with_occult(self, rating: int) -> None:
        set_skill_values(
            self.sheet,
            {self.occult: rating},
            {},
            source=TraitChangeSource.CHARACTER_CREATION,
            enforce_caps=False,
        )

    # -- what she holds -----------------------------------------------------------

    def ap(self) -> int:
        return ActionPointPool.get_or_create_for_character(self.ysmay).current

    def purse(self) -> int:
        return get_or_create_purse(self.sheet).balance

    def hares(self) -> int:
        return FavorTokenDetails.objects.filter(
            issuing_organization=self.academy,
            redeemed_at__isnull=True,
            item_instance__holder_character_sheet=self.sheet,
        ).count()

    def enrollments(self) -> int:
        return SkillCourseEnrollment.objects.filter(character_sheet=self.sheet).count()

    def open_enrollment(self) -> SkillCourseEnrollment:
        return SkillCourseEnrollment.objects.get(
            character_sheet=self.sheet, course=self.course, completed_at__isnull=True
        )

    def occult_stores(self) -> tuple[int, int]:
        """Her Occult rating as the sheet shows it and as a check reads it."""
        sheet_row = CharacterSkillValue.objects.get(character=self.sheet, skill=self.occult)
        trait_row = CharacterTraitValue.objects.get(character=self.sheet, trait=self.occult.trait)
        return sheet_row.value, trait_row.value

    def holdings(self) -> tuple[int, int, int, int]:
        return self.ap(), self.purse(), self.hares(), self.enrollments()


class EnrollingInACourse(_AcademyCourseCase):
    def test_enroll_charges_once_and_runs_first_session(self) -> None:
        told = self.take_course("success")

        # 10 -> 11 costs 100 and 11 -> 12 costs 200: the 300 a session lands on 12.
        self.assertIn(
            f"Success. Occult rises from 10 to 12. The course has 1200 of {TOTAL} left.", told
        )
        self.assertEqual(self.ap(), STARTING_AP - SESSION_AP)
        self.assertEqual(self.purse(), STARTING_COIN - COIN)
        self.assertEqual(get_or_create_treasury(self.academy).balance, COIN)
        self.assertEqual(self.hares(), 0)
        enrollment = self.open_enrollment()
        self.assertEqual(enrollment.development_remaining, 1200)
        self.assertIsNotNone(enrollment.last_session_week)
        self.assertEqual(self.occult_stores(), (12, 12))

        # The next roll that adds Occult as a skill term is worth her new rating.
        roll = CheckTypeFactory(name="Read the wards", category=CheckCategoryFactory())
        CheckTypeTraitFactory(check_type=roll, trait=self.occult.trait, weight=Decimal("1.0"))
        self.assertEqual(perform_check(self.ysmay, roll).trait_points, 12)

    def test_web_path_enrolls_as_telnet_does(self) -> None:
        started = self.web(self.ysmay, "npc_start", role_id=self.role.pk)
        self.assertTrue(started.detail.success, started.detail.message)
        with force_check_outcome(self.outcomes["success"]):
            resolved = self.web(
                self.ysmay,
                "npc_resolve",
                session=started.detail.data["session"],
                offer_id=self.offer.pk,
            )

        self.assertTrue(resolved.detail.success, resolved.detail.message)
        self.assertIn("Success. Occult rises from 10 to 12.", resolved.detail.message)
        self.assertEqual(self.holdings(), (STARTING_AP - SESSION_AP, STARTING_COIN - COIN, 0, 1))
        self.assertEqual(self.open_enrollment().development_remaining, 1200)
        self.assertEqual(self.occult_stores(), (12, 12))

    def test_free_course_charges_no_coin(self) -> None:
        self.course.coin_cost = 0
        self.course.save()

        told = self.take_course("success")

        self.assertIn("Success. Occult rises from 10 to 12.", told)
        self.assertEqual(self.purse(), STARTING_COIN)
        self.assertEqual(get_or_create_treasury(self.academy).balance, 0)
        self.assertEqual(self.hares(), 0)
        self.assertEqual(self.ap(), STARTING_AP - SESSION_AP)
        self.assertEqual(self.open_enrollment().development_remaining, 1200)
        self.assertEqual(self.occult_stores(), (12, 12))


class RefusedEnrollments(_AcademyCourseCase):
    """Each refusal says why and takes nothing: AP, purse, Hares and enrollments unchanged."""

    def assertNothingCharged(self, before: tuple[int, int, int, int]) -> None:  # noqa: N802
        self.assertEqual(self.holdings(), before)
        self.assertEqual(get_or_create_treasury(self.academy).balance, 0)

    def test_no_hare(self) -> None:
        # The Academy already called her one Hare in for something else.
        redeem_favor_token(self.hare, redeemer_org=self.academy)
        before = self.holdings()
        told = self.take_course("success")
        self.assertIn(
            "You carry no Golden Hare for Shroudwatch Academy to call in. Nothing was charged.",
            told,
        )
        self.assertNothingCharged(before)

    def test_owed_obligation(self) -> None:
        OrganizationObligationFactory(debtor=self.sheet, creditor=self.academy)
        before = self.holdings()
        told = self.take_course("success")
        self.assertIn(
            "Shroudwatch Academy won't take you on further until your debt is settled.", told
        )
        self.assertNothingCharged(before)

    def test_short_of_coin(self) -> None:
        transfer(
            amount=90,
            reason="spent elsewhere",
            from_purse=get_or_create_purse(self.sheet),
        )
        before = self.holdings()
        told = self.take_course("success")
        self.assertIn("Enrolling costs 2s and you have 1s. Nothing was charged.", told)
        self.assertNothingCharged(before)

    def test_short_of_ap(self) -> None:
        self.set_ap(5)
        before = self.holdings()
        told = self.take_course("success")
        self.assertIn("A session costs 6 AP and you have 5. Nothing was charged.", told)
        self.assertNothingCharged(before)

    def test_skill_at_a_boundary(self) -> None:
        self.made_with_occult(19)
        before = self.holdings()
        told = self.take_course("success")
        self.assertIn(
            "Occult is at 19 and needs a breakthrough before a course can raise it. "
            "Nothing was charged.",
            told,
        )
        self.assertNothingCharged(before)
        self.assertEqual(self.occult_stores(), (19, 19))


class SessionsOfACourse(_AcademyCourseCase):
    """After enrolling, each acceptance is one session at most once a game week."""

    def setUp(self) -> None:
        super().setUp()
        self.take_course("success")  # enrolled, Occult 12, 1200 left

    def test_same_week_refused_charges_nothing(self) -> None:
        before = self.holdings()
        told = self.take_course("success")
        self.assertIn(
            "You have already trained in this course this week. Nothing was charged.", told
        )
        self.assertEqual(self.holdings(), before)
        self.assertEqual(self.open_enrollment().development_remaining, 1200)
        self.assertEqual(self.occult_stores(), (12, 12))

    def test_next_week_session_charges_ap_only(self) -> None:
        advance_game_week()
        told = self.take_course("failure")

        self.assertIn(
            f"Failure. You learn nothing this session; {SESSION_AP} AP spent. "
            f"The course has 1200 of {TOTAL} left.",
            told,
        )
        self.assertEqual(
            self.holdings(),
            (STARTING_AP - 2 * SESSION_AP, STARTING_COIN - COIN, 0, 1),
        )
        self.assertEqual(self.open_enrollment().development_remaining, 1200)
        self.assertEqual(self.occult_stores(), (12, 12))

    def test_critical_and_completion(self) -> None:
        advance_game_week()
        told = self.take_course("critical")  # 450: 12 -> 13 (300), 150 banked
        self.assertIn(
            f"Critical Success. Occult rises from 12 to 13. The course has 750 of {TOTAL} left.",
            told,
        )

        advance_game_week()
        told = self.take_course("success")  # 150 + 300 = 450: 13 -> 14 (400), 50 banked
        self.assertIn(
            f"Success. Occult rises from 13 to 14. The course has 450 of {TOTAL} left.", told
        )

        advance_game_week()
        told = self.take_course("success")  # 50 + 300 = 350 of the 500 to 15
        self.assertIn(
            f"Success. Occult stays at 14, closer to 15. The course has 150 of {TOTAL} left.", told
        )

        advance_game_week()
        told = self.take_course("success")  # the last 150: 500, 14 -> 15
        self.assertIn("Success. Occult rises from 14 to 15. The course is complete.", told)
        self.assertEqual(self.occult_stores(), (15, 15))
        finished = SkillCourseEnrollment.objects.get(character_sheet=self.sheet)
        self.assertIsNotNone(finished.completed_at)
        self.assertEqual(finished.development_remaining, 0)
        self.assertEqual(self.ap(), STARTING_AP - 5 * SESSION_AP)

        # Taking it again is a new enrollment: a new Hare and the coin again.
        self.give_hare()
        advance_game_week()
        told = self.take_course("success")
        self.assertIn(f"The course has 1200 of {TOTAL} left.", told)
        self.assertEqual(self.hares(), 0)
        self.assertEqual(self.purse(), STARTING_COIN - 2 * COIN)
        self.assertEqual(self.enrollments(), 2)
        self.assertEqual(self.open_enrollment().development_remaining, 1200)

    def test_partial_applies_half(self) -> None:
        advance_game_week()
        told = self.take_course("partial")  # 300 x 0.5 = 150 of the 300 to 13
        self.assertIn(
            f"Partial Success. Occult stays at 12, closer to 13. "
            f"The course has 1050 of {TOTAL} left.",
            told,
        )
        self.assertEqual(self.ap(), STARTING_AP - 2 * SESSION_AP)
        self.assertEqual(self.open_enrollment().development_remaining, 1050)
        row = CharacterSkillValue.objects.get(character=self.sheet, skill=self.occult)
        self.assertEqual(row.development_points, 150)

    def test_botch_spends_ap_and_teaches_nothing(self) -> None:
        advance_game_week()
        told = self.take_course("botch")
        self.assertIn(
            f"Botch. You learn nothing this session; {SESSION_AP} AP spent. "
            f"The course has 1200 of {TOTAL} left.",
            told,
        )
        self.assertEqual(
            self.holdings(),
            (STARTING_AP - 2 * SESSION_AP, STARTING_COIN - COIN, 0, 1),
        )
        self.assertEqual(self.open_enrollment().development_remaining, 1200)
        self.assertEqual(self.occult_stores(), (12, 12))

    def test_retaking_a_course_finished_this_week_waits_for_the_week(self) -> None:
        enrollment = self.open_enrollment()
        enrollment.development_remaining = 100
        enrollment.save()
        advance_game_week()
        told = self.take_course("success")  # the last 100: 12 -> 12 + 100 of 300
        self.assertIn("The course is complete.", told)

        self.give_hare()
        before = self.holdings()
        told = self.take_course("success")
        self.assertIn(
            "You have already trained in this course this week. Nothing was charged.", told
        )
        self.assertEqual(self.holdings(), before)
        self.assertEqual(get_or_create_treasury(self.academy).balance, COIN)

        advance_game_week()
        told = self.take_course("success")
        self.assertIn(f"The course has 1200 of {TOTAL} left.", told)
        self.assertEqual(self.enrollments(), 2)
        self.assertEqual(self.hares(), 0)

    def test_refusal_does_not_use_the_week(self) -> None:
        advance_game_week()
        self.set_ap(3)
        told = self.take_course("success")
        self.assertIn("A session costs 6 AP and you have 3. Nothing was charged.", told)
        self.assertEqual(self.ap(), 3)

        self.set_ap(STARTING_AP)
        told = self.take_course("success")
        self.assertIn("Success. Occult rises from 12 to 13.", told)
        self.assertEqual(self.ap(), STARTING_AP - SESSION_AP)
        self.assertEqual(self.open_enrollment().development_remaining, 900)

    def test_missing_award_row_teaches_nothing(self) -> None:
        TrainingOutcomeAward.objects.filter(outcome_tier=self.outcomes["success"]).delete()
        advance_game_week()
        told = self.take_course("success")
        self.assertIn(f"Success. You learn nothing this session; {SESSION_AP} AP spent.", told)
        self.assertEqual(self.ap(), STARTING_AP - 2 * SESSION_AP)
        self.assertEqual(self.open_enrollment().development_remaining, 1200)
        self.assertEqual(self.occult_stores(), (12, 12))


class ACourseAtABoundary(_AcademyCourseCase):
    """Development past a boundary waits in the course until she breaks through."""

    def test_boundary_keeps_remainder(self) -> None:
        # Enrolled, at 18 with 800 of the 900 to 19 banked, and 1200 of the course left.
        self.made_with_occult(18)
        row = CharacterSkillValue.objects.get(character=self.sheet, skill=self.occult)
        row.development_points = 800
        row.save()
        SkillCourseEnrollmentFactory(
            character_sheet=self.sheet, course=self.course, development_remaining=1200
        )
        purse_before, hares_before = self.purse(), self.hares()

        told = self.take_course("success")
        self.assertIn(
            f"Success. Occult rises from 18 to 19. The course has 1100 of {TOTAL} left. "
            "Break through to continue the course.",
            told,
        )
        self.assertEqual(self.occult_stores(), (19, 19))
        self.assertEqual(self.open_enrollment().development_remaining, 1100)
        self.assertEqual((self.purse(), self.hares()), (purse_before, hares_before))

        advance_game_week()
        before = self.holdings()
        told = self.take_course("success")
        self.assertIn(
            "Occult is at 19 and needs a breakthrough before the course can continue. "
            "Nothing was charged.",
            told,
        )
        self.assertEqual(self.holdings(), before)
        self.assertEqual(self.open_enrollment().development_remaining, 1100)

        # She buys the breakthrough with XP.
        chart = XPCostChart.objects.create(name="Breakthroughs")
        XPCostEntry.objects.create(chart=chart, level=20, xp_cost=100)
        TraitXPCost.objects.create(trait=self.occult.trait, cost_chart=chart)
        TraitRatingUnlock.objects.create(trait=self.occult.trait, target_rating=20)
        ExperiencePointsDataFactory(
            account=self.account_of(self.ysmay), total_earned=150, total_spent=0
        )
        self.assertIn(
            "Breakthrough! Occult rises to",
            self.telnet(self.ysmay, f"progression unlock skill={self.occult.pk}"),
        )
        self.assertEqual(self.occult_stores(), (20, 20))

        advance_game_week()
        told = self.take_course("success")
        # 20 -> 21 costs 1100, so the full 300 is banked toward it.
        self.assertIn(
            f"Success. Occult stays at 20, closer to 21. The course has 800 of {TOTAL} left.",
            told,
        )
        self.assertEqual(self.open_enrollment().development_remaining, 800)
        row = CharacterSkillValue.objects.get(character=self.sheet, skill=self.occult)
        self.assertEqual(row.development_points, SESSION)


class TheTrainersMenu(_AcademyCourseCase):
    """The menu says what an offer costs before it is spent, in telnet and on the web."""

    ENROLL = "Enroll: 2s · 1 Golden Hare · 6 AP a session, the first one now"
    NEXT = f"Next session · {SESSION_AP} AP · 1200 of {TOTAL} left"
    NEXT_WEEK = f"Next session next week · {SESSION_AP} AP · 1200 of {TOTAL} left"

    def menu(self) -> str:
        return strip_ansi(self.telnet(self.ysmay, "hire Magister Cadwen"))

    def web_offers(self) -> dict[str, dict]:
        """The offers the web client is sent when she starts, keyed by label."""
        client = self.api(self.account_of(self.ysmay))
        response = client.post(
            "/api/npc-services/interactions/start/", {"role_id": self.role.pk}, format="json"
        )
        self.assertEqual(response.status_code, 201, response.data)
        client.post("/api/npc-services/interactions/end/", {}, format="json")
        return {offer["label"]: offer for offer in response.data["available_offers"]}

    def test_telnet_names_the_enroll_price_then_the_next_session(self) -> None:
        menu = self.menu()
        self.assertRegex(menu, rf"Course: Occult.*{self.ENROLL}")
        self.assertNotIn("Next session", menu)

        self.take_course("success")
        menu = self.menu()
        # This week's session has run, so the next one waits for the week to turn.
        self.assertRegex(menu, rf"Course: Occult.*{self.NEXT_WEEK}")
        self.assertNotIn("Enroll:", menu)

        self.telnet(self.ysmay, "hire end")
        advance_game_week()
        menu = self.menu()
        self.assertRegex(menu, rf"Course: Occult.*{self.NEXT}")
        self.assertNotIn("next week", menu)

    def test_telnet_prints_the_tradition_line_then_the_fit_line(self) -> None:
        """A tutor who teaches a Tradition says so, then what of her it fits (#4659)."""
        gift = GiftFactory(name="Lantern Gift")
        CharacterGiftFactory(character=self.sheet, gift=gift)
        tradition = TraditionFactory(name="House of Dawn")
        TraditionGiftGrantFactory(tradition=tradition, gift=gift)
        self.role.teaches_tradition = tradition
        self.role.save()

        menu = self.menu()

        self.assertRegex(
            menu,
            rf"Course: Occult.*{self.ENROLL}\s+Taught in the manner of House of Dawn\s+"
            r"Fits your Lantern Gift\. Sessions are easier for you\.",
        )

    def test_the_web_menu_reads_the_affinity_from_her_major_gift_thread(self) -> None:
        """Affinity fit is the resonance on her Major Gift's thread, by foreign key (#4659)."""
        gift = GiftFactory(name="Lantern Gift")
        CharacterGiftFactory(character=self.sheet, gift=gift)
        dawn = AffinityFactory(name="Dawn")
        tradition = TraditionFactory(name="House of Dawn")
        TraditionGiftGrantFactory(tradition=tradition, gift=gift)
        tradition.favored_affinities.add(dawn)
        self.role.teaches_tradition = tradition
        self.role.save()

        before = self.web_offers()["Course: Occult"]["price"]["fit_line"]
        ThreadFactory(
            owner=self.sheet,
            resonance=ResonanceFactory(affinity=dawn),
            target_kind=TargetKind.GIFT,
            target_trait=None,
            target_gift=gift,
        )
        self.sheet.character.threads.invalidate()  # as weaving a thread does
        after = self.web_offers()["Course: Occult"]["price"]["fit_line"]

        self.assertEqual(before, "Fits your Lantern Gift. Sessions are easier for you.")
        self.assertEqual(
            after, "Fits your Lantern Gift and its Dawn affinity. Sessions are easier for you."
        )

    def test_a_free_course_names_only_the_hare(self) -> None:
        self.course.coin_cost = 0
        self.course.save()
        self.assertIn("Enroll: 1 Golden Hare · 6 AP a session, the first one now", self.menu())

    def test_the_web_menu_carries_the_price_line_and_its_parts(self) -> None:
        other = NPCServiceOfferFactory(role=self.role, kind=OfferKind.SETTLE_OBLIGATION)

        offers = self.web_offers()

        self.assertEqual(
            offers["Course: Occult"]["price"],
            {
                "ap": SESSION_AP,
                "coppers": COIN,
                "golden_hares": 1,
                "per_session_ap": SESSION_AP,
                "development_remaining": None,
                "development_total": None,
                "training_points": None,
                "teaching_line": None,
                "fit_line": None,
                "display": self.ENROLL,
            },
        )
        # An offer that is not an Academy course or training names no price.
        self.assertIsNone(offers[other.label]["price"])

    def test_the_web_menu_shows_the_next_session_once_enrolled(self) -> None:
        self.take_course("success")
        self.assertEqual(self.web_offers()["Course: Occult"]["price"]["display"], self.NEXT_WEEK)
        advance_game_week()

        price = self.web_offers()["Course: Occult"]["price"]

        self.assertEqual(price["display"], self.NEXT)
        self.assertEqual((price["coppers"], price["golden_hares"], price["ap"]), (0, 0, SESSION_AP))
        self.assertEqual(
            (price["development_remaining"], price["development_total"]), (1200, TOTAL)
        )
