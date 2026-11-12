"""Being pact services (#4341): the branches no journey reaches.

Signing, serving, a short period, a breach and renouncing are journeys
(``integration_tests.test_pacts_with_beings_journeys``).

The numbers follow the demo: a pact with Hesk owes 8 favor every 2 game weeks; its
condition has four stages from severity 1, 11, 21 and 31 (Sworn, Strained, Soured,
Breached); a wholly missed period adds 10. Resist rolls are forced through
``force_check_outcome``; periods are graded by the real lifecycle tick.
"""

from __future__ import annotations

from contextlib import suppress
from datetime import timedelta

from django.db import transaction
from django.test import TestCase, tag
from django.utils import timezone

from evennia_extensions.factories import ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import CheckTypeFactory
from world.checks.test_helpers import force_check_outcome
from world.conditions.services import advance_condition_severity
from world.magic.constants import GainSource
from world.magic.services.resonance import grant_resonance
from world.narrative.models import NarrativeMessageDelivery
from world.pacts.constants import CharacterPactCommitmentKind, CharacterPactEnding
from world.pacts.exceptions import PactOfferUnavailable
from world.pacts.factories import PactOfferCommitmentFactory, PactOfferFactory, make_pact_condition
from world.pacts.models import CharacterPact, PactCredit, PactPeriodDetails
from world.pacts.services import (
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


class _RolledBack(Exception):
    """Raised to roll a test's transaction back."""


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
        # The holder's lines and the room line go out when the tick commits.
        with self.captureOnCommitCallbacks(execute=True):
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
    """A Chosen signing a pact with her own patron keeps her DEVOTIONAL valence. The
    journeys sign only for a character with no patron, so this branch has no journey."""

    def test_a_chosen_keeps_her_devotional_patronage(self) -> None:
        chosen = CharacterSheetFactory()
        make_chosen(chosen, self.being)

        self._sign(chosen)

        standing = DevotionStanding.objects.get(character_sheet=chosen, being=self.being)
        self.assertEqual(standing.valence, PatronageValence.DEVOTIONAL)

    def test_a_resisted_condition_leaves_no_cached_patronage_behind(self) -> None:
        """A refused signing rolls back inside the atomic block; the cached standing keeps
        what the database kept, so the next accept still writes the PACT valence. No
        journey can resist the condition at the close (#4341 review, idmapper-cache)."""
        condition = make_pact_condition(name="Resistible pact")
        condition.resist_check_type = CheckTypeFactory(name="Pact resist")
        condition.resist_difficulty = 10
        condition.save(update_fields=["resist_check_type", "resist_difficulty"])
        offer = PactOfferFactory(being=self.being, name="Resistible", condition=condition)
        PactOfferCommitmentFactory(offer=offer, amount=8)
        standing = DevotionStanding.objects.create(character_sheet=self.sheet, being=self.being)

        with force_check_outcome(self.outcomes["Success"]), self.assertRaises(PactOfferUnavailable):
            sign_being_pact(self.sheet, offer)

        self.assertIsNone(standing.valence)
        self.assertIsNone(DevotionStanding.objects.get(pk=standing.pk).valence)
        self.assertFalse(CharacterPact.objects.filter(character_sheet=self.sheet).exists())

        with force_check_outcome(self.outcomes["Failure"]):
            sign_being_pact(self.sheet, offer)

        self.assertEqual(
            DevotionStanding.objects.get(pk=standing.pk).valence, PatronageValence.PACT
        )


class CreditTests(PactTestBase):
    """How favor and the weekly deed cap split between a pledge and a pact, and a pact
    with no commitment earning nothing. The journeys serve one pact alone, inside the
    cap, so none of these branches is reached by one."""

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

    def test_a_deed_for_a_pledge_and_a_pact_with_one_being_counts_once(self) -> None:
        take_pledge(self.sheet, PledgeFactory(being=self.being, favor_target=20))
        pact = self._sign()

        self._deed(5)

        self.assertEqual(PactCredit.objects.get().base, 0)
        self.assertEqual(self._period(pact).project.current_progress, 5)
        self.assertEqual(deed_favor_used_this_week(self.sheet), 5)

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

    def test_a_pact_with_no_favor_commitment_earns_no_deed_favor(self) -> None:
        """A promise-only pact has no period to credit, so the cap could not count it."""
        offer = PactOfferFactory(being=self.being, name="Promise only")
        PactOfferCommitmentFactory(
            offer=offer, kind=CharacterPactCommitmentKind.CUSTOM, amount=0, notes="[promise]"
        )
        sign_being_pact(self.sheet, offer)

        self._deed(5)

        standing = DevotionStanding.objects.get(character_sheet=self.sheet, being=self.being)
        self.assertEqual(standing.favor, 0)
        self.assertEqual(deed_favor_used_this_week(self.sheet), 0)


class PeriodCheckTests(PactTestBase):
    """The grading arithmetic and its delivery: the ease's cap and floor, the resist
    tier table, a Chosen's breach and a rolled-back tick. A journey walks one path
    through each; the boundaries and the other tiers are reached only here."""

    def test_a_rolled_back_tick_tells_her_nothing(self) -> None:
        """Her lines wait for the commit: a rolled-back grading reported no roll."""
        pact = self._sign()
        project = self._period(pact).project
        project.time_limit = timezone.now() - timedelta(minutes=1)
        project.save(update_fields=["time_limit"])

        with self.captureOnCommitCallbacks(execute=True) as callbacks:
            with suppress(_RolledBack), transaction.atomic():
                scan_active_projects()
                self.assertEqual(self._told(), "")
                raise _RolledBack

        self.assertEqual(callbacks, [])
        self.assertEqual(self._told(), "")
        self.assertEqual(self._period(pact).project.pk, project.pk)

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
                # Easing back out of Strained says the stage went back, as a worsening does.
                went_back = "Sworn now applies." in self._told(pact.character_sheet)
                self.assertEqual(went_back, before >= 11)

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
