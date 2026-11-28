"""Journeys for an Academy skill course (#4457).

A course is enrolled once, for coin and one Golden Hare, and the enrolling acceptance runs
the first session. Every later acceptance of the same offer is one session: AP, then a
training roll whose outcome scales the development, at most one session per course per
game week. A refusal charges nothing. Each journey stands a learner in front of the
Academy's teacher, takes the course through the real ``hire`` command (or the web
dispatch once), then reads back what she was told and what she still holds.

The expected numbers come from the course the spec authors (40 development, 10 a
session, 6 AP a session, 2 silver), the authored outcome multipliers (botch and failure 0,
partial 0.5, success 1.0, critical 1.5) and the skill rule that a step costs a tenth of its
level band on the shared curve: 10 development for each step from 10 to 19. Names are
invented.
"""

from __future__ import annotations

from decimal import Decimal

from django.utils import timezone
from evennia.utils.ansi import strip_ansi

from evennia_extensions.factories import RoomProfileFactory
from integration_tests.harness import JourneyCase
from integration_tests.tradition_teaching_helpers import (
    TEACHER_LINE,
    author_the_three_skills,
    hold_rating,
    tradition_teaching,
)
from world.action_points.models import ActionPointConfig, ActionPointPool
from world.character_creation.sheet_writers import set_skill_values
from world.checks.factories import CheckCategoryFactory, CheckTypeFactory, CheckTypeTraitFactory
from world.checks.services import difficulty_points, perform_check
from world.checks.test_helpers import force_check_outcome
from world.currency.models import FavorTokenDetails
from world.currency.services import (
    get_or_create_purse,
    get_or_create_treasury,
    mint_favor_token,
    redeem_favor_token,
    transfer,
)
from world.distinctions.factories import DistinctionEffectFactory, DistinctionFactory
from world.distinctions.services import grant_distinction
from world.distinctions.types import DistinctionOrigin
from world.game_clock.week_services import advance_game_week
from world.magic.constants import GainSource
from world.magic.factories import (
    AffinityFactory,
    CharacterAuraFactory,
    CharacterGiftFactory,
    CharacterTraditionFactory,
    GiftFactory,
    ResonanceFactory,
    TraditionFactory,
    TraditionGiftGrantFactory,
)
from world.magic.models import TrainingOutcomeAward
from world.magic.services.resonance import grant_resonance
from world.magic.services.teaching_fit import get_teaching_config
from world.magic.services.tradition_membership import join_tradition
from world.mechanics.constants import SELF_TEACHING_CATEGORY_NAME, SELF_TEACHING_TARGET_NAME
from world.mechanics.test_helpers import lever_target
from world.narrative.models import NarrativeMessageDelivery
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
from world.progression.models.rewards import DevelopmentPoints
from world.progression.services.dev_cost import cumulative_dp_for_level
from world.skills.factories import SkillFactory
from world.skills.models import TrainingAllocation
from world.skills.services import run_weekly_skill_cron
from world.societies.constants import ObligationState
from world.societies.factories import OrganizationFactory, OrganizationObligationFactory
from world.traits.factories import (
    CheckOutcomeFactory,
    CheckSystemSetupFactory,
    ensure_level_ladder,
)
from world.traits.models import (
    CharacterTraitValue,
    CheckOutcome,
    PointConversionRange,
    TraitCategory,
    TraitChangeSource,
    TraitType,
)

TOTAL = 40
SESSION = 10
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
        self.occult = SkillFactory(name="Occult", category=TraitCategory.MAGIC)
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
            check_difficulty_level=0,
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

    def occult_rating(self) -> int:
        """Her Occult rating: the one row the sheet shows and a check reads (#5010)."""
        return CharacterTraitValue.objects.get(character=self.sheet, trait=self.occult).value

    def occult_ledger(self) -> DevelopmentPoints:
        return DevelopmentPoints.objects.get(character_sheet=self.sheet, trait=self.occult)

    def occult_banked(self) -> int:
        """Development banked toward her next Occult level (#5010)."""
        rating = self.occult_rating()
        return self.occult_ledger().total_earned - cumulative_dp_for_level(rating)

    def holdings(self) -> tuple[int, int, int, int]:
        return self.ap(), self.purse(), self.hares(), self.enrollments()


class EnrollingInACourse(_AcademyCourseCase):
    def test_enroll_charges_once_and_runs_first_session(self) -> None:
        told = self.take_course("success")

        # 10 -> 11 costs 10: the 10 a session lands on 11.
        self.assertIn(
            f"Success. Occult rises from 10 to 11. The course has 30 of {TOTAL} left.", told
        )
        self.assertEqual(self.ap(), STARTING_AP - SESSION_AP)
        self.assertEqual(self.purse(), STARTING_COIN - COIN)
        self.assertEqual(get_or_create_treasury(self.academy).balance, COIN)
        self.assertEqual(self.hares(), 0)
        enrollment = self.open_enrollment()
        self.assertEqual(enrollment.development_remaining, 30)
        self.assertIsNotNone(enrollment.last_session_week)
        self.assertEqual(self.occult_rating(), 11)

        # The next roll that adds Occult as a skill term is worth her new rating.
        roll = CheckTypeFactory(name="Read the wards", category=CheckCategoryFactory())
        CheckTypeTraitFactory(check_type=roll, trait=self.occult, weight=Decimal("1.0"))
        self.assertEqual(perform_check(self.ysmay, roll).trait_points, 11)

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
        self.assertIn("Success. Occult rises from 10 to 11.", resolved.detail.message)
        self.assertEqual(self.holdings(), (STARTING_AP - SESSION_AP, STARTING_COIN - COIN, 0, 1))
        self.assertEqual(self.open_enrollment().development_remaining, 30)
        self.assertEqual(self.occult_rating(), 11)

    def test_free_course_charges_no_coin(self) -> None:
        self.course.coin_cost = 0
        self.course.save()

        told = self.take_course("success")

        self.assertIn("Success. Occult rises from 10 to 11.", told)
        self.assertEqual(self.purse(), STARTING_COIN)
        self.assertEqual(get_or_create_treasury(self.academy).balance, 0)
        self.assertEqual(self.hares(), 0)
        self.assertEqual(self.ap(), STARTING_AP - SESSION_AP)
        self.assertEqual(self.open_enrollment().development_remaining, 30)
        self.assertEqual(self.occult_rating(), 11)


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
        self.assertEqual(self.occult_rating(), 19)


class SessionsOfACourse(_AcademyCourseCase):
    """After enrolling, each acceptance is one session at most once a game week."""

    def setUp(self) -> None:
        super().setUp()
        self.take_course("success")  # enrolled, Occult 11, 30 left

    def test_same_week_refused_charges_nothing(self) -> None:
        before = self.holdings()
        told = self.take_course("success")
        self.assertIn(
            "You have already trained in this course this week. Nothing was charged.", told
        )
        self.assertEqual(self.holdings(), before)
        self.assertEqual(self.open_enrollment().development_remaining, 30)
        self.assertEqual(self.occult_rating(), 11)

    def test_next_week_session_charges_ap_only(self) -> None:
        advance_game_week()
        told = self.take_course("failure")

        self.assertIn(
            f"Failure. You learn nothing this session; {SESSION_AP} AP spent. "
            f"The course has 30 of {TOTAL} left.",
            told,
        )
        self.assertEqual(
            self.holdings(),
            (STARTING_AP - 2 * SESSION_AP, STARTING_COIN - COIN, 0, 1),
        )
        self.assertEqual(self.open_enrollment().development_remaining, 30)
        self.assertEqual(self.occult_rating(), 11)

    def test_critical_and_completion(self) -> None:
        advance_game_week()
        told = self.take_course("critical")  # 15: 11 -> 12 (10), 5 banked
        self.assertIn(
            f"Critical Success. Occult rises from 11 to 12. The course has 15 of {TOTAL} left.",
            told,
        )

        advance_game_week()
        told = self.take_course("success")  # 5 + 10 = 15: 12 -> 13 (10), 5 banked
        self.assertIn(
            f"Success. Occult rises from 12 to 13. The course has 5 of {TOTAL} left.", told
        )

        advance_game_week()
        told = self.take_course("success")  # the last 5: 5 + 5 = 10, 13 -> 14
        self.assertIn("Success. Occult rises from 13 to 14. The course is complete.", told)
        self.assertEqual(self.occult_rating(), 14)
        finished = SkillCourseEnrollment.objects.get(character_sheet=self.sheet)
        self.assertIsNotNone(finished.completed_at)
        self.assertEqual(finished.development_remaining, 0)
        self.assertEqual(self.ap(), STARTING_AP - 4 * SESSION_AP)

        # Taking it again is a new enrollment: a new Hare and the coin again.
        self.give_hare()
        advance_game_week()
        told = self.take_course("success")
        self.assertIn(f"The course has 30 of {TOTAL} left.", told)
        self.assertEqual(self.hares(), 0)
        self.assertEqual(self.purse(), STARTING_COIN - 2 * COIN)
        self.assertEqual(self.enrollments(), 2)
        self.assertEqual(self.open_enrollment().development_remaining, 30)

    def test_partial_applies_half(self) -> None:
        advance_game_week()
        told = self.take_course("partial")  # 10 x 0.5 = 5 of the 10 to 12
        self.assertIn(
            f"Partial Success. Occult stays at 11, closer to 12. "
            f"The course has 25 of {TOTAL} left.",
            told,
        )
        self.assertEqual(self.ap(), STARTING_AP - 2 * SESSION_AP)
        self.assertEqual(self.open_enrollment().development_remaining, 25)
        self.assertEqual(self.occult_banked(), 5)

    def test_botch_spends_ap_and_teaches_nothing(self) -> None:
        advance_game_week()
        told = self.take_course("botch")
        self.assertIn(
            f"Botch. You learn nothing this session; {SESSION_AP} AP spent. "
            f"The course has 30 of {TOTAL} left.",
            told,
        )
        self.assertEqual(
            self.holdings(),
            (STARTING_AP - 2 * SESSION_AP, STARTING_COIN - COIN, 0, 1),
        )
        self.assertEqual(self.open_enrollment().development_remaining, 30)
        self.assertEqual(self.occult_rating(), 11)

    def test_retaking_a_course_finished_this_week_waits_for_the_week(self) -> None:
        enrollment = self.open_enrollment()
        enrollment.development_remaining = 5
        enrollment.save()
        advance_game_week()
        told = self.take_course("success")  # the last 5: 11 -> 11 + 5 of 10
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
        self.assertIn(f"The course has 30 of {TOTAL} left.", told)
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
        self.assertIn("Success. Occult rises from 11 to 12.", told)
        self.assertEqual(self.ap(), STARTING_AP - SESSION_AP)
        self.assertEqual(self.open_enrollment().development_remaining, 20)

    def test_missing_award_row_teaches_nothing(self) -> None:
        TrainingOutcomeAward.objects.filter(outcome_tier=self.outcomes["success"]).delete()
        advance_game_week()
        told = self.take_course("success")
        self.assertIn(f"Success. You learn nothing this session; {SESSION_AP} AP spent.", told)
        self.assertEqual(self.ap(), STARTING_AP - 2 * SESSION_AP)
        self.assertEqual(self.open_enrollment().development_remaining, 30)
        self.assertEqual(self.occult_rating(), 11)


class ACourseAtABoundary(_AcademyCourseCase):
    """Development past a boundary waits in the course until she breaks through."""

    def test_boundary_keeps_remainder(self) -> None:
        # Enrolled, at 18 with 8 of the 10 to 19 banked, and 30 of the course left.
        self.made_with_occult(18)
        ledger = self.occult_ledger()
        ledger.total_earned = cumulative_dp_for_level(18) + 8
        ledger.save()
        SkillCourseEnrollmentFactory(
            character_sheet=self.sheet, course=self.course, development_remaining=30
        )
        purse_before, hares_before = self.purse(), self.hares()

        told = self.take_course("success")
        self.assertIn(
            f"Success. Occult rises from 18 to 19. The course has 28 of {TOTAL} left. "
            "Break through to continue the course.",
            told,
        )
        self.assertEqual(self.occult_rating(), 19)
        self.assertEqual(self.open_enrollment().development_remaining, 28)
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
        self.assertEqual(self.open_enrollment().development_remaining, 28)

        # She buys the breakthrough with XP.
        chart = XPCostChart.objects.create(name="Breakthroughs")
        XPCostEntry.objects.create(chart=chart, level=20, xp_cost=100)
        TraitXPCost.objects.create(trait=self.occult, cost_chart=chart)
        TraitRatingUnlock.objects.create(trait=self.occult, target_rating=20)
        ExperiencePointsDataFactory(
            account=self.account_of(self.ysmay), total_earned=150, total_spent=0
        )
        self.assertIn(
            "Breakthrough! Occult rises to",
            self.telnet(self.ysmay, f"progression unlock skill={self.occult.pk}"),
        )
        self.assertEqual(self.occult_rating(), 20)

        advance_game_week()
        told = self.take_course("success")
        # 20 -> 21 costs 15, so the full 10 is banked toward it.
        self.assertIn(
            f"Success. Occult stays at 20, closer to 21. The course has 18 of {TOTAL} left.",
            told,
        )
        self.assertEqual(self.open_enrollment().development_remaining, 18)
        self.assertEqual(self.occult_banked(), SESSION)


class TheTrainersMenu(_AcademyCourseCase):
    """The menu says what an offer costs before it is spent, in telnet and on the web."""

    ENROLL = "Enroll: 2s · 1 Golden Hare · 6 AP a session, the first one now"
    NEXT = f"Next session · {SESSION_AP} AP · 30 of {TOTAL} left"
    NEXT_WEEK = f"Next session next week · {SESSION_AP} AP · 30 of {TOTAL} left"

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

    def test_the_web_menu_reads_the_affinity_from_her_aura(self) -> None:
        """Affinity fit is her aura's dominant affinity, which resonance she earns moves (#4681)."""
        gift = GiftFactory(name="Lantern Gift")
        CharacterGiftFactory(character=self.sheet, gift=gift)
        dawn = AffinityFactory(name="Dawn")
        tradition = TraditionFactory(name="House of Dawn")
        TraditionGiftGrantFactory(tradition=tradition, gift=gift)
        tradition.favored_affinities.add(dawn)
        self.role.teaches_tradition = tradition
        self.role.save()
        aura = CharacterAuraFactory(character=self.sheet, celestial="0", primal="80", abyssal="20")

        before = self.web_offers()["Course: Occult"]["price"]["fit_line"]
        grant_resonance(
            self.sheet, ResonanceFactory(affinity=dawn), 100, source=GainSource.STAFF_GRANT
        )
        after = self.web_offers()["Course: Occult"]["price"]["fit_line"]

        self.assertEqual(aura.dominant_affinity.name, "Dawn")
        self.assertEqual(before, "Fits your Lantern Gift. Sessions are easier for you.")
        self.assertEqual(
            after, "Fits your Lantern Gift and its Dawn affinity. Sessions are easier for you."
        )

    def test_telnet_fit_line_follows_the_aura(self) -> None:
        """The same fit line on telnet names the affinity her aura leads with (#4681)."""
        gift = GiftFactory(name="Lantern Gift")
        CharacterGiftFactory(character=self.sheet, gift=gift)
        dawn = AffinityFactory(name="Dawn")
        tradition = TraditionFactory(name="House of Dawn")
        TraditionGiftGrantFactory(tradition=tradition, gift=gift)
        tradition.favored_affinities.add(dawn)
        self.role.teaches_tradition = tradition
        self.role.save()
        CharacterAuraFactory(character=self.sheet, celestial="0", primal="80", abyssal="20")

        before = self.menu()
        self.telnet(self.ysmay, "hire end")
        grant_resonance(
            self.sheet, ResonanceFactory(affinity=dawn), 100, source=GainSource.STAFF_GRANT
        )
        after = self.menu()

        self.assertIn("Fits your Lantern Gift. Sessions are easier for you.", before)
        self.assertNotIn("Dawn affinity", before)
        self.assertIn(
            "Fits your Lantern Gift and its Dawn affinity. Sessions are easier for you.", after
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
                "outsider_line": None,
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
        self.assertEqual((price["development_remaining"], price["development_total"]), (30, TOTAL))


class TheTrainersTradition(_AcademyCourseCase):
    """A course in a skill a Tradition's list governs, taught by Magister Cadwen (#5326).

    Magister Cadwen now teaches in the Ashen Court, which ticks Villainy, and offers a course
    in it. Ysmay belongs to the Dawn Vigil, which does not, so she is an outsider: the menu
    says sessions are harder and the session's check carries the extra points staff set (4).
    Whether the trainer's Tradition teaches the skill is checked when she enrolls and never
    again, so a course she has paid for keeps running.
    """

    ENROLL = "Enroll: 2s · 1 Golden Hare · 6 AP a session, the first one now"
    OUTSIDER_LINE = "Your Tradition does not teach this. Sessions are harder for you."
    EXTRA = 4

    def setUp(self) -> None:
        super().setUp()
        ensure_level_ladder()
        skills = author_the_three_skills()
        self.villainy = skills["Villainy"]
        self.dawn = tradition_teaching("Dawn Vigil", skills["Heroism"])
        self.ashen = tradition_teaching("Ashen Court", self.villainy)
        config = get_teaching_config()
        config.other_tradition_course_difficulty = self.EXTRA
        config.course_ease_gift_fit = 0
        config.course_ease_affinity_fit = 0
        config.save()
        self.role.teaches_tradition = self.ashen
        self.role.save()
        self.villainy_offer = NPCServiceOfferFactory(
            role=self.role,
            kind=OfferKind.SKILL_COURSE,
            label="Course: Villainy",
            is_final=True,
            ap_cost=0,
        )
        SkillCourseOfferDetailsFactory(
            offer=self.villainy_offer,
            skill=self.villainy,
            total_development=TOTAL,
            session_development=SESSION,
            session_ap_cost=SESSION_AP,
            coin_cost=COIN,
            check_type=CheckTypeFactory(),
            check_difficulty_level=1,
        )
        CharacterTraditionFactory(character=self.sheet, tradition=self.dawn)

    def take_villainy(self):
        """Ask for the Villainy course with the roll pinned to Success.

        Returns what she was told and the capture of the one check the session rolled.
        """
        self.telnet(self.ysmay, "hire Magister Cadwen")
        with force_check_outcome(self.outcomes["success"]) as capture:
            told = strip_ansi(self.telnet(self.ysmay, f"hire offer {self.villainy_offer.pk}"))
        return told, capture

    def test_an_outsider_reads_the_harder_line_and_rolls_the_extra_difficulty(self) -> None:
        self.assertRegex(
            self.menu(),
            rf"Course: Villainy.*{self.ENROLL}\s+Taught in the manner of Ashen Court\s+"
            rf"{self.OUTSIDER_LINE}",
        )
        price = self.web_offers()["Course: Villainy"]["price"]
        self.assertEqual(price["outsider_line"], self.OUTSIDER_LINE)

        _told, capture = self.take_villainy()

        self.assertEqual(capture.target_difficulty, difficulty_points(1) + self.EXTRA)

    def test_a_student_whose_tradition_teaches_the_skill_rolls_as_before(self) -> None:
        join_tradition(self.sheet, self.ashen)

        self.assertNotIn("Sessions are harder", self.menu())
        self.assertIsNone(self.web_offers()["Course: Villainy"]["price"]["outsider_line"])

        _told, capture = self.take_villainy()

        self.assertEqual(capture.target_difficulty, difficulty_points(1))

    def test_a_change_of_tradition_changes_only_the_next_sessions_difficulty(self) -> None:
        _told, first = self.take_villainy()
        self.assertEqual(first.target_difficulty, difficulty_points(1) + self.EXTRA)

        join_tradition(self.sheet, self.ashen)
        self.telnet(self.ysmay, "hire end")
        advance_game_week()
        ap_before = self.ap()
        told, second = self.take_villainy()

        # The course she paid for runs on: it is her own Tradition that changed the roll.
        self.assertNotIn("Nothing was charged", told)
        self.assertEqual(self.ap(), ap_before - SESSION_AP)
        self.assertEqual(second.target_difficulty, difficulty_points(1))
        self.assertEqual(self.enrollments(), 1)

    def holdings_of_skill(self) -> tuple[dict[int, int], dict[int, tuple[int, int]]]:
        """Every rating she holds and every development ledger row, as the sheet reads them."""
        ratings = dict(
            CharacterTraitValue.objects.filter(character=self.sheet).values_list(
                "trait_id", "value"
            )
        )
        development = {
            row.trait_id: (row.total_earned, row.rust_debt)
            for row in DevelopmentPoints.objects.filter(character_sheet=self.sheet)
        }
        return ratings, development

    def test_a_student_who_changes_tradition_mid_course_keeps_everything_and_rolls_harder(
        self,
    ) -> None:
        """A student of the Ashen Court (which teaches Villainy) takes two sessions with the
        Academy's trainer and reads no caution line. She then changes to the Dawn Vigil, which
        does not teach it. Her ratings and development stay, her third session still runs
        (the trainer's Tradition was checked at enrollment, never per session) with nothing
        charged again, the menu now reads the caution line, and that session rolls harder."""
        join_tradition(self.sheet, self.ashen)
        self.assertNotIn(self.OUTSIDER_LINE, self.menu())
        _told, first = self.take_villainy()
        self.assertEqual(first.target_difficulty, difficulty_points(1))
        self.telnet(self.ysmay, "hire end")
        advance_game_week()
        self.assertNotIn(self.OUTSIDER_LINE, self.menu())
        _told, second = self.take_villainy()
        self.assertEqual(second.target_difficulty, difficulty_points(1))
        self.telnet(self.ysmay, "hire end")
        advance_game_week()
        held_before = self.holdings_of_skill()
        purse_before, hares_before = self.purse(), self.hares()

        join_tradition(self.sheet, self.dawn)

        self.assertEqual(self.holdings_of_skill(), held_before)
        self.assertRegex(
            self.menu(),
            rf"Course: Villainy.*\s+Taught in the manner of Ashen Court\s+{self.OUTSIDER_LINE}",
        )
        self.assertEqual(
            self.web_offers()["Course: Villainy"]["price"]["outsider_line"], self.OUTSIDER_LINE
        )
        self.telnet(self.ysmay, "hire end")
        ap_before = self.ap()

        told, third = self.take_villainy()

        self.assertNotIn("closed", told)
        self.assertNotIn("Nothing was charged", told)
        self.assertEqual(third.target_difficulty, difficulty_points(1) + self.EXTRA)
        self.assertEqual(self.ap(), ap_before - SESSION_AP)
        self.assertEqual((self.purse(), self.hares()), (purse_before, hares_before))
        self.assertEqual(self.enrollments(), 1)

    def test_enrolling_is_refused_when_the_trainers_tradition_does_not_teach_it(self) -> None:
        # Staff untick Villainy on the Ashen Court after the course was authored.
        self.ashen.taught_skills.remove(self.villainy)
        before = self.holdings()

        told, _capture = self.take_villainy()

        self.assertIn(
            "Academy Teacher's Tradition no longer teaches Villainy, so this course is "
            "closed. Look for a trainer whose Tradition teaches it. Nothing was charged.",
            told,
        )
        self.assertEqual(self.holdings(), before)
        self.assertEqual(get_or_create_treasury(self.academy).balance, 0)
        # A course she cannot take draws no harder line: that line is for a course she can.
        self.assertNotIn("Sessions are harder", self.menu())
        self.assertIsNone(self.web_offers()["Course: Villainy"]["price"]["outsider_line"])

    def test_enrolling_is_refused_when_the_trainer_teaches_no_tradition(self) -> None:
        self.role.teaches_tradition = None
        self.role.save()
        before = self.holdings()

        told, _capture = self.take_villainy()

        self.assertIn(
            "Academy Teacher teaches no Tradition, so this course is closed. Look for a "
            "trainer whose Tradition teaches Villainy. Nothing was charged.",
            told,
        )
        self.assertEqual(self.holdings(), before)

    def test_a_course_already_paid_for_keeps_running_when_the_tradition_stops_teaching(
        self,
    ) -> None:
        self.take_villainy()
        self.ashen.taught_skills.remove(self.villainy)
        self.telnet(self.ysmay, "hire end")
        advance_game_week()
        ap_before = self.ap()

        told, _capture = self.take_villainy()

        self.assertNotIn("closed", told)
        self.assertEqual(self.ap(), ap_before - SESSION_AP)
        self.assertEqual(self.enrollments(), 1)

    def test_a_course_in_an_ordinary_magic_skill_is_open_on_a_trainer_with_no_tradition(
        self,
    ) -> None:
        """Occult is no list's skill, so any Tradition, and none, teaches it."""
        self.role.teaches_tradition = None
        self.role.save()

        told = self.take_course("success")

        self.assertNotIn("closed", told)
        self.assertEqual(self.enrollments(), 1)
        # The Villainy course on this same trainer is closed (the role names no Tradition), so
        # its row draws no harder line either: the line is for a course she can take.
        self.assertNotIn("Sessions are harder", self.menu())
        self.assertIsNone(self.web_offers()["Course: Villainy"]["price"]["outsider_line"])


class ASelfTaughtCharacterOnTheUnboundEntry(_AcademyCourseCase):
    """A character on the self-taught Tradition trains Villainy alone only with the effect (#5326).

    Staff author a Tradition for the self-taught (here "Unbound"), and a distinction that
    character carries (the Unbound drawback) with one effect on the self-teaching target, the
    same rows the Distinction Builder writes. No code names the Tradition or the distinction.
    With the effect she allocates action points to Villainy with no mentor and the weekly run
    pays it as self-study pays; without it she is refused with the teacher line. She may also
    take a course from a trainer whose Tradition teaches the skill, and the menu says sessions
    are harder for her because her own Tradition does not teach it.
    """

    ENROLL = "Enroll: 2s · 1 Golden Hare · 6 AP a session, the first one now"
    OUTSIDER_LINE = "Your Tradition does not teach this. Sessions are harder for you."
    EXTRA = 3

    def setUp(self) -> None:
        super().setUp()
        ensure_level_ladder()
        ActionPointConfig.objects.update_or_create(
            name="Default", defaults={"is_active": True, "weekly_regen": 80}
        )
        self.villainy = author_the_three_skills()["Villainy"]
        self.unbound = tradition_teaching("Unbound")
        self.ashen = tradition_teaching("Ashen Court", self.villainy)
        config = get_teaching_config()
        config.other_tradition_course_difficulty = self.EXTRA
        config.course_ease_gift_fit = 0
        config.course_ease_affinity_fit = 0
        config.save()
        self.role.teaches_tradition = self.ashen
        self.role.save()
        self.villainy_offer = NPCServiceOfferFactory(
            role=self.role,
            kind=OfferKind.SKILL_COURSE,
            label="Course: Villainy",
            is_final=True,
            ap_cost=0,
        )
        SkillCourseOfferDetailsFactory(
            offer=self.villainy_offer,
            skill=self.villainy,
            total_development=TOTAL,
            session_development=SESSION,
            session_ap_cost=SESSION_AP,
            coin_cost=COIN,
            check_type=CheckTypeFactory(),
            check_difficulty_level=1,
        )
        CharacterTraditionFactory(character=self.sheet, tradition=self.unbound)
        hold_rating(self.sheet, self.villainy, 11)
        # Staff author the exception on the drawback in the Distinction Builder: one effect on
        # the self-teaching target. She does not carry the drawback until a test grants it.
        self.drawback = DistinctionFactory(name="Without a Teacher")
        DistinctionEffectFactory(
            distinction=self.drawback,
            target=lever_target(SELF_TEACHING_CATEGORY_NAME, SELF_TEACHING_TARGET_NAME),
            value_per_rank=1,
        )

    def villainy_row(self) -> TrainingAllocation | None:
        return TrainingAllocation.objects.filter(character=self.sheet, skill=self.villainy).first()

    def notices(self) -> list[str]:
        return list(
            NarrativeMessageDelivery.objects.filter(recipient_character_sheet=self.sheet)
            .order_by("pk")
            .values_list("message__body", flat=True)
        )

    def test_she_trains_villainy_alone_only_with_the_distinction_and_the_week_pays_it(self) -> None:
        add = f"training add skill={self.villainy.pk} ap=3"

        # Without the distinction she is refused, exactly as anyone else is.
        self.assertIn(TEACHER_LINE.format(skill="Villainy"), self.telnet(self.ysmay, add))
        self.assertIsNone(self.villainy_row())

        grant_distinction(self.sheet, self.drawback, origin=DistinctionOrigin.GM_AWARD)

        self.assertIn("Training allocation set for Villainy.", self.telnet(self.ysmay, add))
        self.assertIsNotNone(self.villainy_row())
        ap_before = self.ap()

        run_weekly_skill_cron()

        # Alone, 5 x 3 AP x path level 1 is 15 development points: a step from 11 to 12, with
        # 5 kept. No skip line, and the three action points were spent.
        self.assertEqual(self.villainy_rating(), 12)
        self.assertEqual(self.ap(), ap_before - 3)
        self.assertEqual([line for line in self.notices() if "did not run" in line], [])

    def villainy_rating(self) -> int:
        return CharacterTraitValue.objects.get(character=self.sheet, trait=self.villainy).value

    def test_she_may_take_a_course_from_a_trainer_whose_tradition_teaches_it(self) -> None:
        self.assertRegex(
            strip_ansi(self.telnet(self.ysmay, "hire Magister Cadwen")),
            rf"Course: Villainy.*{self.ENROLL}\s+Taught in the manner of Ashen Court\s+"
            rf"{self.OUTSIDER_LINE}",
        )
        self.telnet(self.ysmay, "hire end")

        self.telnet(self.ysmay, "hire Magister Cadwen")
        with force_check_outcome(self.outcomes["success"]) as capture:
            self.telnet(self.ysmay, f"hire offer {self.villainy_offer.pk}")

        self.assertEqual(self.enrollments(), 1)
        self.assertEqual(capture.target_difficulty, difficulty_points(1) + self.EXTRA)
