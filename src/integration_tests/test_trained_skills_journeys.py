"""Journeys: a skill the character trained shows the same on the sheet and in her rolls (#4496).

A skill's rating lives in two stores: the sheet shows ``CharacterSkillValue`` and a
check reads ``CharacterTraitValue``. Ysmay raises a skill every way the game lets her
after creation (a weekly training tick, an XP breakthrough, a level-up from use), and
after each one the number on her sheet and the skill points a check on that skill is
worth are the same. Rust never changes a rating, and a tick leaves it alone.

The expected numbers come from the rules the issue and the skills docs state: weekly
training pays ``5 x AP x path level`` development points, a skill level costs
``(value - 9) x 100`` of them, a high-effort roll earns 20, a skill is worth one check
point per rating point, and a week of rust is ``path level + 5``.
"""

from __future__ import annotations

from decimal import Decimal

from integration_tests.harness import JourneyCase
from world.action_points.models import ActionPointConfig
from world.character_creation.sheet_writers import set_skill_values
from world.checks.factories import CheckCategoryFactory, CheckTypeFactory, CheckTypeTraitFactory
from world.checks.models import CheckType
from world.checks.services import perform_check
from world.fatigue.constants import EffortLevel
from world.progression.factories import ExperiencePointsDataFactory
from world.progression.models import TraitRatingUnlock, TraitXPCost, XPCostChart, XPCostEntry
from world.skills.factories import SkillFactory
from world.skills.models import CharacterSkillValue, Skill
from world.skills.services import run_weekly_skill_cron
from world.traits.factories import CheckSystemSetupFactory
from world.traits.models import (
    CharacterTraitChange,
    CharacterTraitValue,
    PointConversionRange,
    ResultChart,
    Trait,
    TraitChangeSource,
    TraitType,
)


class _TrainedSkillCase(JourneyCase):
    """Ysmay, one skill the character sheet shows, and a check that rolls on it."""

    def setUp(self) -> None:
        super().setUp()
        Trait.flush_instance_cache()
        CharacterTraitValue.flush_instance_cache()
        ResultChart.clear_cache()
        CheckSystemSetupFactory.create()
        # One check point per rating point, so a skill's points are its rating.
        PointConversionRange.objects.get_or_create(
            trait_type=TraitType.SKILL,
            min_value=1,
            defaults={"max_value": 100, "points_per_level": 1},
        )
        ActionPointConfig.objects.update_or_create(
            name="Default", defaults={"is_active": True, "weekly_regen": 80}
        )
        self.lantern = self.make_room("The Lantern")
        self.ysmay = self.make_player("Ysmay", room=self.lantern)
        self.sheet = self.ysmay.sheet_data
        self.skill = SkillFactory()

    def made_with(self, skill: Skill, rating: int) -> None:
        """Ysmay leaves character creation with ``skill`` at ``rating`` in both stores."""
        set_skill_values(
            self.sheet,
            {skill: rating},
            {},
            source=TraitChangeSource.CHARACTER_CREATION,
            enforce_caps=False,
        )

    def check_on(self, skill: Skill) -> CheckType:
        check_type = CheckTypeFactory(
            name=f"Roll {skill.name}", category=CheckCategoryFactory(name=f"Rolls {skill.pk}")
        )
        CheckTypeTraitFactory(check_type=check_type, trait=skill.trait, weight=Decimal("1.0"))
        return check_type

    def roll_points(self, skill: Skill, effort: str | None = None) -> int:
        """The skill points a check on ``skill`` is worth to Ysmay right now."""
        result = perform_check(self.ysmay, self.check_on(skill), effort_level=effort)
        return result.trait_points

    def sheet_shows(self, skill: Skill) -> int:
        """The rating her character sheet shows for ``skill``, read through the REST API."""
        response = self.api(self.account_of(self.ysmay)).get(
            f"/api/character-sheets/{self.sheet.pk}/"
        )
        self.assertEqual(response.status_code, 200, response.content)
        shown = {row["skill"]["id"]: row["value"] for row in response.json()["skills"]}
        return shown[skill.pk]

    def assertSheetAndRollAgree(self, skill: Skill, rating: int) -> None:  # noqa: N802
        self.assertEqual(self.sheet_shows(skill), rating, "the sheet")
        self.assertEqual(self.roll_points(skill), rating, "a check's skill points")


class TrainingASkillByTheWeek(_TrainedSkillCase):
    """She plans a week of training, the weekly tick runs, and the new rating rolls."""

    def test_a_training_tick_raises_the_sheet_and_the_roll_together(self) -> None:
        self.made_with(self.skill, 11)
        self.assertSheetAndRollAgree(self.skill, 11)

        self.assertIn(
            f"Training allocation set for {self.skill.name}.",
            self.telnet(self.ysmay, f"training add skill={self.skill.pk} ap=40"),
        )
        # 5 x 40 AP x path level 1 = 200 development points; 11 -> 12 costs 200.
        run_weekly_skill_cron()

        self.assertSheetAndRollAgree(self.skill, 12)
        change = CharacterTraitChange.objects.filter(
            character_sheet=self.sheet, trait=self.skill.trait
        ).latest("pk")
        self.assertEqual(
            (change.old_value, change.new_value, change.source),
            (11, 12, TraitChangeSource.DEVELOPMENT_LEVEL_UP),
        )

    def test_a_tick_that_buys_part_of_a_level_changes_neither(self) -> None:
        self.made_with(self.skill, 11)
        self.telnet(self.ysmay, f"training add skill={self.skill.pk} ap=10")
        run_weekly_skill_cron()  # 50 of the 200 points a level costs
        self.assertSheetAndRollAgree(self.skill, 11)

    def test_a_character_who_trained_before_the_fix_is_not_lowered(self) -> None:
        """Alpha rows once written by training alone: sheet 14, roll 11. The next tick
        keeps the 14 she earned and brings the roll up to it."""
        self.made_with(self.skill, 11)
        CharacterSkillValue.objects.filter(character=self.sheet, skill=self.skill).update(value=14)
        self.telnet(self.ysmay, f"training add skill={self.skill.pk} ap=10")
        run_weekly_skill_cron()
        self.assertSheetAndRollAgree(self.skill, 14)


class BuyingABreakthrough(_TrainedSkillCase):
    """A skill parked at an XP boundary is bought past it, and the roll follows."""

    def test_a_breakthrough_raises_the_sheet_and_the_roll_together(self) -> None:
        self.made_with(self.skill, 19)
        chart = XPCostChart.objects.create(name="Breakthroughs")
        XPCostEntry.objects.create(chart=chart, level=20, xp_cost=100)
        TraitXPCost.objects.create(trait=self.skill.trait, cost_chart=chart)
        TraitRatingUnlock.objects.create(trait=self.skill.trait, target_rating=20)
        ExperiencePointsDataFactory(
            account=self.account_of(self.ysmay), total_earned=150, total_spent=0
        )
        self.assertSheetAndRollAgree(self.skill, 19)

        told = self.telnet(self.ysmay, f"progression unlock skill={self.skill.pk}")

        self.assertIn(f"Breakthrough! {self.skill.name} rises to", told)
        self.assertSheetAndRollAgree(self.skill, 20)
        change = CharacterTraitChange.objects.filter(
            character_sheet=self.sheet, trait=self.skill.trait
        ).latest("pk")
        self.assertEqual(
            (change.old_value, change.new_value, change.source),
            (19, 20, TraitChangeSource.XP_BREAKTHROUGH),
        )

    def test_a_breakthrough_she_cannot_afford_changes_neither(self) -> None:
        self.made_with(self.skill, 19)
        chart = XPCostChart.objects.create(name="Breakthroughs")
        XPCostEntry.objects.create(chart=chart, level=20, xp_cost=100)
        TraitXPCost.objects.create(trait=self.skill.trait, cost_chart=chart)
        TraitRatingUnlock.objects.create(trait=self.skill.trait, target_rating=20)
        ExperiencePointsDataFactory(
            account=self.account_of(self.ysmay), total_earned=40, total_spent=0
        )
        told = self.telnet(self.ysmay, f"progression unlock skill={self.skill.pk}")
        self.assertIn("Insufficient XP (need 100, have 40)", told)
        self.assertSheetAndRollAgree(self.skill, 19)


class LevellingASkillByUse(_TrainedSkillCase):
    """She rolls the skill with effort until it levels, and the sheet follows the roll."""

    def test_a_level_up_from_use_raises_the_sheet_and_the_roll_together(self) -> None:
        self.made_with(self.skill, 10)
        check_type = self.check_on(self.skill)
        # A high-effort roll earns 20 development points; 10 -> 11 costs 100.
        for _ in range(5):
            self.assertEqual(self.sheet_shows(self.skill), 10)
            perform_check(self.ysmay, check_type, effort_level=EffortLevel.HIGH)

        self.assertSheetAndRollAgree(self.skill, 11)

    def test_a_character_who_levelled_by_use_before_the_fix_is_not_lowered(self) -> None:
        """Alpha rows once written by use alone: roll 14, sheet 11. The next roll with
        effort keeps the 14 she earned and brings the sheet up to it."""
        self.made_with(self.skill, 11)
        CharacterTraitValue.objects.filter(character=self.sheet, trait=self.skill.trait).update(
            value=14
        )
        CharacterTraitValue.flush_instance_cache()
        perform_check(self.ysmay, self.check_on(self.skill), effort_level=EffortLevel.HIGH)
        self.assertSheetAndRollAgree(self.skill, 14)


class RustOnAnUntrainedSkill(_TrainedSkillCase):
    """A week of rust builds up on a skill she did not train and moves no rating."""

    def test_rust_leaves_the_sheet_and_the_roll_equal(self) -> None:
        trained = SkillFactory()
        self.made_with(trained, 11)
        self.made_with(self.skill, 12)
        self.telnet(self.ysmay, f"training add skill={trained.pk} ap=10")

        run_weekly_skill_cron()

        rusty = CharacterSkillValue.objects.get(character=self.sheet, skill=self.skill)
        self.assertEqual(rusty.rust_points, 6)  # path level 1 + 5
        self.assertSheetAndRollAgree(self.skill, 12)
        self.assertSheetAndRollAgree(trained, 11)
