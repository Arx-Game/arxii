"""Being pact services (#4341): signing, crediting, the period check, breach, ease-out.

The numbers follow the demo: a pact with Hesk owes 8 favor every 2 game weeks; its
condition has four stages from severity 1, 11, 21 and 31 (Sworn, Strained, Soured,
Breached); a wholly missed period adds 10. Resist rolls are forced through
``force_check_outcome``; periods are graded by the real lifecycle tick.
"""

from __future__ import annotations

from datetime import timedelta

from django.test import TestCase, tag
from django.utils import timezone

from evennia_extensions.factories import ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.test_helpers import force_check_outcome
from world.conditions.services import advance_condition_severity
from world.magic.constants import GainSource
from world.magic.services.resonance import grant_resonance
from world.narrative.models import NarrativeMessageDelivery
from world.pacts.constants import CharacterPactCommitmentKind, CharacterPactEnding
from world.pacts.exceptions import NoActivePact, PactAlreadyHeld
from world.pacts.factories import PactOfferCommitmentFactory, PactOfferFactory, make_pact_condition
from world.pacts.models import CharacterPact, PactCredit, PactPeriodDetails
from world.pacts.services import (
    pact_cards_for,
    pact_offer_summary,
    renounce_pact,
    sign_being_pact,
)
from world.projects.constants import ProjectStatus
from world.projects.services import scan_active_projects
from world.traits.factories import CheckOutcomeFactory
from world.worship.constants import BeingResonanceTier, PledgeCreditSource
from world.worship.factories import (
    BeingResonanceFactory,
    PledgeFactory,
    WorshippedBeingFactory,
    make_chosen,
)
from world.worship.invocation_services import get_devotion_config
from world.worship.models import DevotionStanding, PatronageValence, PledgeCredit
from world.worship.pledge_services import deed_favor_used_this_week, take_pledge
from world.worship.services import bump_devotion

_OUTCOMES = (
    ("Critical Success", 2),
    ("Success", 1),
    ("Partial Success", 0),
    ("Failure", -1),
    ("Critical Failure", -2),
)


# Signing applies a staged condition, whose first-stage lookup is a PostgreSQL
# DISTINCT ON (ADR-0012), so every test here runs on the parity tier.
@tag("postgres")
class PactTestBase(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.outcomes = {
            name: CheckOutcomeFactory(name=name, success_level=level) for name, level in _OUTCOMES
        }
        cls.being = WorshippedBeingFactory(name="Hesk")
        cls.offer = PactOfferFactory(
            being=cls.being,
            name="Hesk pact",
            condition=make_pact_condition(resist_difficulty=40),
            onlooker_line="[onlooker line]",
        )
        cls.commitment = PactOfferCommitmentFactory(offer=cls.offer, amount=8)
        PactOfferCommitmentFactory(
            offer=cls.offer, kind=CharacterPactCommitmentKind.CUSTOM, amount=0, notes="[promise]"
        )
        cls.room = ObjectDBFactory(db_key="Hollow", db_typeclass_path="typeclasses.rooms.Room")
        cls.sheet = CharacterSheetFactory()
        cls.sheet.character.db_location = cls.room
        cls.sheet.character.save(update_fields=["db_location"])

    def _sign(self, sheet=None) -> CharacterPact:
        return sign_being_pact(sheet or self.sheet, self.offer)

    def _period(self, pact: CharacterPact) -> PactPeriodDetails:
        return PactPeriodDetails.objects.get(pact=pact, project__status=ProjectStatus.ACTIVE)

    def _tick(self, pact: CharacterPact, *, earned: int = 0, severity: int | None = None) -> None:
        """Set the period's earnings (and the condition's severity), end it, run the tick."""
        if severity is not None:
            instance = pact.condition_instance
            advance_condition_severity(instance, severity - instance.severity)
        project = self._period(pact).project
        project.current_progress = earned
        project.time_limit = timezone.now() - timedelta(minutes=1)
        project.save(update_fields=["current_progress", "time_limit"])
        scan_active_projects()

    def _graded(self, pact: CharacterPact) -> PactPeriodDetails:
        return PactPeriodDetails.objects.filter(pact=pact, severity_change__isnull=False).latest(
            "pk"
        )

    def _told(self, sheet=None) -> str:
        return "\n".join(
            NarrativeMessageDelivery.objects.filter(
                recipient_character_sheet=sheet or self.sheet
            ).values_list("message__body", flat=True)
        )


class SigningTests(PactTestBase):
    def test_sign_marks_a_pact_patronage_applies_the_first_stage_and_opens_a_period(self) -> None:
        pact = self._sign()

        standing = DevotionStanding.objects.get(character_sheet=self.sheet, being=self.being)
        self.assertEqual(standing.valence, PatronageValence.PACT)
        self.assertIsNotNone(standing.established_at)
        self.assertEqual(pact.condition_instance.current_stage.name, "Sworn")
        self.assertEqual(pact.condition_instance.severity, 1)
        project = self._period(pact).project
        self.assertEqual(project.threshold_target, 8)
        self.assertEqual(project.time_limit.date(), (timezone.now() + timedelta(days=14)).date())
        with self.assertRaises(PactAlreadyHeld) as raised:
            self._sign()
        self.assertIn("Hesk", raised.exception.user_message)

    def test_a_chosen_keeps_her_devotional_patronage(self) -> None:
        chosen = CharacterSheetFactory()
        make_chosen(chosen, self.being)

        self._sign(chosen)

        standing = DevotionStanding.objects.get(character_sheet=chosen, being=self.being)
        self.assertEqual(standing.valence, PatronageValence.DEVOTIONAL)

    def test_offer_summary_and_card(self) -> None:
        summary = pact_offer_summary(self.offer)
        self.assertEqual(summary.favor_per_period, (8,))
        self.assertEqual(summary.promises, ("[promise]",))
        self.assertEqual(
            [(s.name, s.threshold) for s in summary.stages],
            [("Sworn", 1), ("Strained", 11), ("Soured", 21), ("Breached", 31)],
        )

        self._sign()
        bump_devotion(self.sheet, self.being, 3, source=None)

        (card,) = pact_cards_for(self.sheet)
        self.assertEqual((card.earned, card.required, card.severity), (3, 8, 1))
        self.assertEqual((card.stage_name, card.next_stage_threshold), ("Sworn", 11))
        self.assertEqual([(s.label, s.favor) for s in card.sources], [("Other", 3)])
        self.assertTrue(card.is_active)


class CreditTests(PactTestBase):
    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        cls.hesk_res = BeingResonanceFactory(being=cls.being, tier=BeingResonanceTier.FAVORED)

    def _deed(self, amount: int) -> None:
        grant_resonance(self.sheet, self.hesk_res.resonance, amount, source=GainSource.COMPROMISE)

    def test_bump_devotion_credits_the_open_period(self) -> None:
        pact = self._sign()

        bump_devotion(self.sheet, self.being, 3)
        bump_devotion(self.sheet, WorshippedBeingFactory(), 5)  # another being: not counted

        self.assertEqual(self._period(pact).project.current_progress, 3)
        self.assertEqual(PactCredit.objects.get().credited, 3)

    def test_deeds_share_the_weekly_cap_between_a_pledge_and_a_pact(self) -> None:
        ombrin = WorshippedBeingFactory(name="Ombrin")
        BeingResonanceFactory(
            being=ombrin, resonance=self.hesk_res.resonance, tier=BeingResonanceTier.FAVORED
        )
        take_pledge(self.sheet, PledgeFactory(being=ombrin, favor_target=20))
        pact = self._sign()

        self._deed(6)  # Ombrin's pledge takes 6 base, Hesk's pact the 2 left of the cap
        self._deed(6)  # the cap is spent

        self.assertEqual(PledgeCredit.objects.get(source=PledgeCreditSource.DEED).base, 6)
        self.assertEqual(self._period(pact).project.current_progress, 2)
        self.assertEqual(deed_favor_used_this_week(self.sheet), 8)

    def test_pact_only_deeds_count_base_favor_against_the_cap(self) -> None:
        """A Chosen earns at 200%: the cap still counts base favor, not credited."""
        make_chosen(self.sheet, self.being)
        pact = self._sign()

        self._deed(5)  # 5 base, 10 credited
        self.assertEqual(deed_favor_used_this_week(self.sheet), 5)
        self._deed(5)  # 3 base left, 6 credited

        self.assertEqual(self._period(pact).project.current_progress, 16)
        self.assertEqual(
            deed_favor_used_this_week(self.sheet), get_devotion_config().weekly_deed_favor_cap
        )


class PeriodCheckTests(PactTestBase):
    def test_a_met_period_eases_capped_at_twice_per_miss_and_floored_at_the_first_stage(
        self,
    ) -> None:
        # (severity before, earned, severity after): 10*9//8 = 11; 10*16//8 = 20 (the cap);
        # 24 earned would ease 20 but stops at the first stage's 1.
        for before, earned, after in ((15, 9, 4), (25, 16, 5), (5, 24, 1)):
            with self.subTest(before=before, earned=earned):
                pact = self._sign(CharacterSheetFactory())
                self._tick(pact, earned=earned, severity=before)

                pact.condition_instance.refresh_from_db()
                self.assertEqual(pact.condition_instance.severity, after)
                graded = self._graded(pact)
                self.assertEqual(graded.severity_change, after - before)
                self.assertIsNone(graded.resist_outcome)
                self.assertEqual(graded.project.status, ProjectStatus.COMPLETED)
                self.assertEqual(self._period(pact).project.threshold_target, 8)

    def test_a_short_period_inside_the_stage_rolls_nothing(self) -> None:
        pact = self._sign()

        self._tick(pact, earned=1)  # 7 short: rise 9 (8.75 up), to 10, still Sworn

        graded = self._graded(pact)
        self.assertEqual((graded.severity_change, graded.stage_after.name), (9, "Sworn"))
        self.assertIsNone(graded.resist_outcome)
        self.assertEqual(graded.project.status, ProjectStatus.FAILED)
        self.assertIn("1 of 8 favor this period, 7 short.", self._told())
        self.assertIn("Severity rises by 9 (to 10). No stage change.", self._told())

    def test_a_short_period_reaching_a_worse_stage_rolls_its_resist_by_tier(self) -> None:
        # From severity 5, 5 short is a rise of 7 (to 12), reaching Strained at 11.
        cases = (
            ("Critical Success", 5, "Sworn", "Critical Success"),
            ("Success", 10, "Sworn", "Success"),
            ("Partial Success", 9, "Sworn", "Partial Success"),
            ("Failure", 12, "Strained", "Failure"),
            ("Critical Failure", 12, "Strained", "Failure"),
        )
        config = get_devotion_config()
        for forced, after, stage, recorded in cases:
            with self.subTest(forced=forced):
                sheet = CharacterSheetFactory()
                pact = self._sign(sheet)
                standing = pact.devotion_standing
                standing.favor = config.favor_ease_low_threshold
                standing.save(update_fields=["favor"])
                with force_check_outcome(self.outcomes[forced]) as capture:
                    self._tick(pact, earned=3, severity=5)

                self.assertEqual(capture.target_difficulty, 40 - config.favor_ease_low_points)
                graded = self._graded(pact)
                self.assertEqual(graded.severity_change, after - 5)
                self.assertEqual(graded.stage_after.name, stage)
                self.assertEqual(graded.resist_outcome.name, recorded)
                self.assertIn("reach Strained", self._told(sheet))

    def test_breach_on_the_last_stage_ends_the_pact_and_eases_out(self) -> None:
        pact = self._sign()

        with force_check_outcome(self.outcomes["Failure"]):
            self._tick(pact, earned=0, severity=25)

        pact.refresh_from_db()
        self.assertEqual(pact.dissolution_reason, CharacterPactEnding.BREACH)
        self.assertEqual(pact.condition_instance.current_stage.name, "Breached")
        self.assertIsNotNone(pact.devotion_standing.released_at)
        period = self._period(pact)
        self.assertIsNone(period.commitment)
        self.assertIn("Hesk is no longer your patron.", self._told())
        self.assertIn("Breached eases by 10 each period", self._told())

    def test_a_chosen_who_breaches_keeps_her_patronage(self) -> None:
        chosen = CharacterSheetFactory()
        make_chosen(chosen, self.being)
        pact = self._sign(chosen)

        with force_check_outcome(self.outcomes["Failure"]):
            self._tick(pact, earned=0, severity=25)

        pact.refresh_from_db()
        self.assertEqual(pact.dissolution_reason, CharacterPactEnding.BREACH)
        self.assertIsNone(pact.devotion_standing.released_at)
        self.assertIn("Your pact with Hesk has ended.", self._told(chosen))


class RenounceTests(PactTestBase):
    def test_renounce_releases_and_the_condition_eases_out_to_nothing(self) -> None:
        pact = self._sign()
        commitment_period = self._period(pact)
        advance_condition_severity(pact.condition_instance, 11)  # to 12, Strained

        renounce_pact(self.sheet, self.being)

        pact.refresh_from_db()
        self.assertEqual(pact.dissolution_reason, CharacterPactEnding.RENOUNCED)
        self.assertIsNotNone(pact.devotion_standing.released_at)
        commitment_period.project.refresh_from_db()
        self.assertEqual(commitment_period.project.status, ProjectStatus.CANCELLED)
        self.assertEqual(len(pact_cards_for(self.sheet)), 1)
        with self.assertRaises(NoActivePact):
            renounce_pact(self.sheet, self.being)

        self._tick(pact)  # 12 -> 2
        self.assertEqual(pact.condition_instance.severity, 2)
        self._tick(pact)  # 2 -> gone

        pact.refresh_from_db()
        self.assertIsNone(pact.condition_instance)
        self.assertFalse(
            PactPeriodDetails.objects.filter(
                pact=pact, project__status=ProjectStatus.ACTIVE
            ).exists()
        )
        self.assertEqual(pact_cards_for(self.sheet), [])
