"""Journeys: a skill stops at its level band's skill cap, the way a stat does (#4585).

Staff author a skill cap per level band beside the stat cap (``MaturationStatCap``),
in the shown units a player reads (a cap of 3 is a skill shown at 3.0, stored 30).
Ysmay is a level-1 character, so the first band's row binds her. She trains, rolls
and buys breakthroughs; at the cap development stops and the surplus dissipates, as
at an XP wall, with a message naming the cap. A band with a blank cap, or no row at
all, caps nothing. Staff edit mode refuses a value above the cap.

The expected numbers come from the rules the skills docs state: weekly training pays
``5 x AP x path level`` development points, a skill level costs ``(value - 9) x 100``
of them, and a high-effort roll earns 20.
"""

from __future__ import annotations

from decimal import Decimal

from evennia_extensions.factories import AccountFactory
from integration_tests.harness import JourneyCase
from world.action_points.models import ActionPointConfig
from world.character_creation.sheet_writers import set_skill_values
from world.checks.factories import CheckCategoryFactory, CheckTypeFactory, CheckTypeTraitFactory
from world.checks.models import CheckType
from world.checks.services import perform_check
from world.classes.models import PathStage
from world.fatigue.constants import EffortLevel
from world.progression.factories import ExperiencePointsDataFactory
from world.progression.models import (
    DevelopmentPoints,
    DevelopmentTransaction,
    ExperiencePointsData,
    MaturationStatCap,
    TraitRatingUnlock,
    TraitXPCost,
    XPCostChart,
    XPCostEntry,
)
from world.progression.models.rewards import cumulative_dp_for_level
from world.progression.services.awards import award_development_points
from world.progression.types import DevelopmentSource
from world.roster.services.staff_characters import mint_gm_character
from world.skills.factories import SkillFactory
from world.skills.models import CharacterSkillValue
from world.skills.services import run_weekly_skill_cron
from world.traits.factories import CheckSystemSetupFactory, StatTraitFactory
from world.traits.models import (
    CharacterTraitValue,
    PointConversionRange,
    ResultChart,
    Trait,
    TraitChangeSource,
    TraitType,
)

CAP_MESSAGE = "the cap for your current level band"


class _BandCapCase(JourneyCase):
    """Ysmay, level 1 (the first band), and one skill she trains and rolls."""

    def setUp(self) -> None:
        super().setUp()
        Trait.flush_instance_cache()
        CharacterTraitValue.flush_instance_cache()
        ResultChart.clear_cache()
        CheckSystemSetupFactory.create()
        PointConversionRange.objects.get_or_create(
            trait_type=TraitType.SKILL,
            min_value=1,
            defaults={"max_value": 100, "points_per_level": 1},
        )
        ActionPointConfig.objects.update_or_create(
            name="Default", defaults={"is_active": True, "weekly_regen": 80}
        )
        self.hall = self.make_room("The Drill Hall")
        self.ysmay = self.make_player("Ysmay", room=self.hall)
        self.sheet = self.ysmay.sheet_data
        self.skill = SkillFactory()

    def band_caps_skills_at(self, cap: int | None) -> None:
        """Staff author the first band's row with ``skill_cap`` (shown units)."""
        MaturationStatCap.objects.create(path_stage=PathStage.PROSPECT, stat_cap=5, skill_cap=cap)

    def made_with(self, rating: int) -> None:
        set_skill_values(
            self.sheet,
            {self.skill: rating},
            {},
            source=TraitChangeSource.CHARACTER_CREATION,
            enforce_caps=False,
        )

    def skill_row(self) -> CharacterSkillValue:
        return CharacterSkillValue.objects.get(character=self.sheet, skill=self.skill)

    def rolls_at(self) -> int:
        return CharacterTraitValue.objects.get(character=self.sheet, trait=self.skill.trait).value

    def train_a_week(self) -> DevelopmentTransaction:
        """She plans 80 AP of training (400 points at level 1) and the week ticks."""
        self.assertIn(
            f"Training allocation set for {self.skill.name}.",
            self.telnet(self.ysmay, f"training add skill={self.skill.pk} ap=80"),
        )
        run_weekly_skill_cron()
        return DevelopmentTransaction.objects.filter(
            character_sheet=self.sheet, source=DevelopmentSource.TRAINING
        ).latest("pk")

    def author_breakthrough(self, target: int, *, xp_cost: int = 100) -> None:
        chart = XPCostChart.objects.create(name=f"Breakthroughs {target}")
        XPCostEntry.objects.create(chart=chart, level=target, xp_cost=xp_cost)
        TraitXPCost.objects.create(trait=self.skill.trait, cost_chart=chart)
        TraitRatingUnlock.objects.create(trait=self.skill.trait, target_rating=target)
        ExperiencePointsDataFactory(
            account=self.account_of(self.ysmay), total_earned=150, total_spent=0
        )


class TrainingStopsAtTheBandCap(_BandCapCase):
    def test_breaks_through_to_the_cap_then_training_only_maintains(self) -> None:
        """Cap 3: she buys 2.9 -> 3.0, then a week of training adds nothing."""
        self.band_caps_skills_at(3)
        self.made_with(29)
        self.author_breakthrough(30)

        told = self.telnet(self.ysmay, f"progression unlock skill={self.skill.pk}")
        self.assertIn(f"Breakthrough! {self.skill.name} rises to 3.0", told)

        transaction = self.train_a_week()
        row = self.skill_row()
        self.assertEqual((row.value, row.development_points), (30, 0))
        self.assertEqual(self.rolls_at(), 30)
        self.assertIn(f"{self.skill.name} is at 3.0, {CAP_MESSAGE}", transaction.description)

    def test_development_that_reaches_the_cap_dissipates_the_rest(self) -> None:
        """Cap 6, at 59 with 4,900 of 5,000 banked: 400 more buys 60 and 300 dissipates."""
        self.band_caps_skills_at(6)
        self.made_with(59)
        row = self.skill_row()
        row.development_points = 4900
        row.save()

        transaction = self.train_a_week()

        row = self.skill_row()
        self.assertEqual((row.value, row.development_points), (60, 0))
        self.assertEqual(self.rolls_at(), 60)
        self.assertIn(f"is at 6.0, {CAP_MESSAGE}", transaction.description)

    def test_a_blank_cap_caps_nothing(self) -> None:
        self.band_caps_skills_at(None)
        self.made_with(30)
        transaction = self.train_a_week()
        row = self.skill_row()
        self.assertEqual((row.value, row.development_points), (30, 400))
        self.assertNotIn(CAP_MESSAGE, transaction.description)

    def test_a_band_with_no_row_caps_nothing(self) -> None:
        self.made_with(30)
        transaction = self.train_a_week()
        self.assertEqual(self.skill_row().development_points, 400)
        self.assertNotIn(CAP_MESSAGE, transaction.description)


class ABreakthroughPastTheCapIsRefused(_BandCapCase):
    def test_a_skill_made_above_the_cap_cannot_break_through(self) -> None:
        """Made at 2.9 under a band cap of 2: buying 3.0 is refused and costs nothing."""
        self.band_caps_skills_at(2)
        self.made_with(29)
        self.author_breakthrough(30)

        told = self.telnet(self.ysmay, f"progression unlock skill={self.skill.pk}")

        self.assertIn(f"{self.skill.name} is at 2.0, {CAP_MESSAGE}", told)
        self.assertEqual(self.skill_row().value, 29)
        xp = ExperiencePointsData.objects.get(account=self.account_of(self.ysmay))
        self.assertEqual(xp.total_spent, 0)


class UseAndAwardsStopAtTheCap(_BandCapCase):
    def _bank_toward(self, trait: Trait, level: int, short_by: int) -> None:
        DevelopmentPoints.objects.update_or_create(
            character_sheet=self.sheet,
            trait=trait,
            defaults={"total_earned": cumulative_dp_for_level(level) - short_by},
        )

    def _check_on_skill(self) -> CheckType:
        check_type = CheckTypeFactory(
            name=f"Roll {self.skill.name}", category=CheckCategoryFactory(name="Band cap rolls")
        )
        CheckTypeTraitFactory(check_type=check_type, trait=self.skill.trait, weight=Decimal(1))
        return check_type

    def test_a_roll_with_effort_at_the_cap_does_not_level_the_skill(self) -> None:
        """Ten points short of 3.1, a high-effort roll (20 points) would level her; the
        cap holds her at 3.0 and the surplus dissipates."""
        self.band_caps_skills_at(3)
        self.made_with(30)
        self._bank_toward(self.skill.trait, 31, short_by=10)

        perform_check(self.ysmay, self._check_on_skill(), effort_level=EffortLevel.HIGH)

        self.assertEqual(self.rolls_at(), 30)
        self.assertEqual(self.skill_row().value, 30)
        tracker = DevelopmentPoints.objects.get(character_sheet=self.sheet, trait=self.skill.trait)
        self.assertEqual(tracker.total_earned, cumulative_dp_for_level(30))

    def test_a_gm_award_at_the_cap_says_so_on_the_record(self) -> None:
        self.band_caps_skills_at(3)
        self.made_with(30)
        self._bank_toward(self.skill.trait, 31, short_by=10)

        record = award_development_points(
            self.sheet, self.skill.trait, DevelopmentSource.SCENE, 50, description="A duel"
        )

        self.assertEqual(self.rolls_at(), 30)
        self.assertTrue(record.description.startswith("A duel "))
        self.assertIn(CAP_MESSAGE, record.description)

    def test_a_stat_is_not_held_by_the_skill_cap(self) -> None:
        """Stats keep their own cap; the skill cap of 3 does not stop a stat at 40 -> 41."""
        self.band_caps_skills_at(3)
        stat = StatTraitFactory(name="band_cap_strength")
        CharacterTraitValue.objects.create(character=self.sheet, trait=stat, value=40)
        self._bank_toward(stat, 41, short_by=10)

        record = award_development_points(
            self.sheet, stat, DevelopmentSource.SCENE, 50, description="Hauling stone"
        )

        self.assertEqual(
            CharacterTraitValue.objects.get(character=self.sheet, trait=stat).value, 41
        )
        self.assertEqual(record.description, "Hauling stone")


class StaffEditRefusesAboveTheCap(JourneyCase):
    def test_staff_cannot_set_a_skill_above_the_band_cap(self) -> None:
        MaturationStatCap.objects.create(path_stage=PathStage.PROSPECT, stat_cap=5, skill_cap=2)
        skill = SkillFactory()
        staff = AccountFactory(is_staff=True)
        sheet = mint_gm_character(staff, "Mirela Vant").character_sheet
        url = f"/api/character-sheets/{sheet.pk}/staff-skills/"

        refused = self.api(staff).patch(url, {"skills": {str(skill.pk): 25}}, format="json")
        self.assertEqual(refused.status_code, 400, refused.content)
        self.assertIn("the skill cap for this character's band", refused.json()["detail"])
        self.assertFalse(CharacterSkillValue.objects.filter(character=sheet).exists())

        allowed = self.api(staff).patch(url, {"skills": {str(skill.pk): 20}}, format="json")
        self.assertEqual(allowed.status_code, 200, allowed.content)
        self.assertEqual(CharacterSkillValue.objects.get(character=sheet, skill=skill).value, 20)
