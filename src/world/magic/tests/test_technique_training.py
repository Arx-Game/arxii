"""Tests for check-based technique training (#2727)."""

from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase

from world.action_points.models import ActionPointPool
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.test_helpers import force_check_outcome
from world.magic.factories import TechniqueFactory
from world.magic.models import (
    CharacterTechnique,
    TechniqueProgress,
    TrainingOutcomeAward,
)
from world.magic.services.technique_training import resolve_training_check
from world.seeds.modifier_values import seed_pool_and_cap_lanes
from world.traits.factories import ensure_level_ladder
from world.traits.models import CheckOutcome

# Canonical outcome tiers (name -> success_level), matching seeds/checks.py.
_CANONICAL_OUTCOMES = [
    ("Critical Failure", -2),
    ("Failure", -1),
    ("Partial Success", 0),
    ("Success", 1),
    ("Critical Success", 2),
]


def _ensure_outcome(name: str, success_level: int) -> CheckOutcome:
    outcome, _ = CheckOutcome.objects.get_or_create(
        name=name, defaults={"success_level": success_level}
    )
    return outcome


class ResolveTrainingCheckTest(TestCase):
    def setUp(self):
        ensure_level_ladder()
        seed_pool_and_cap_lanes()
        self.sheet = CharacterSheetFactory()
        self.technique = TechniqueFactory()
        self.pool = ActionPointPool.get_or_create_for_character(self.sheet.character)
        self.pool.current = 500
        self.pool.save()
        from world.magic.constants import TargetKind
        from world.magic.factories import ResonanceFactory
        from world.magic.models import CharacterGift, Thread

        CharacterGift.objects.create(character=self.sheet, gift=self.technique.gift)
        Thread.objects.create(
            owner=self.sheet,
            resonance=ResonanceFactory(),
            target_kind=TargetKind.GIFT,
            target_gift=self.technique.gift,
            level=0,
        )
        self.progress = TechniqueProgress.objects.create(
            character_sheet=self.sheet,
            technique=self.technique,
            total_required=50,
            source="gift_acquisition",
        )
        self.outcomes = {name: _ensure_outcome(name, sl) for name, sl in _CANONICAL_OUTCOMES}
        self._seed_award_rows()
        self._seed_check_content()

    def _seed_award_rows(self):
        multipliers = {
            "Critical Failure": Decimal("0.00"),
            "Failure": Decimal("0.00"),
            "Partial Success": Decimal("0.50"),
            "Success": Decimal("1.00"),
            "Critical Success": Decimal("1.50"),
        }
        for name, mult in multipliers.items():
            TrainingOutcomeAward.objects.update_or_create(
                outcome_tier=self.outcomes[name],
                defaults={"dev_point_multiplier": mult},
            )

    def _seed_check_content(self):
        """Minimal CheckType so the service can resolve a check."""
        from world.checks.models import CheckCategory, CheckType, CheckTypeTrait
        from world.traits.models import Trait, TraitCategory, TraitType

        arcane_trait, _ = Trait.objects.get_or_create(
            name="Arcane Theory",
            defaults={
                "trait_type": TraitType.SKILL,
                "category": TraitCategory.MAGIC,
                "is_public": True,
                "tooltip": "Understanding the theoretical underpinnings of magical techniques.",
                "display_order": 0,
                "is_active": True,
            },
        )
        intellect_trait, _ = Trait.objects.get_or_create(
            name="intellect",
            defaults={
                "trait_type": TraitType.STAT,
                "category": TraitCategory.MENTAL,
                "is_public": True,
            },
        )
        category, _ = CheckCategory.objects.get_or_create(
            name="Magic",
            defaults={"description": "Magic checks.", "display_order": 40},
        )
        check_type, _ = CheckType.objects.get_or_create(
            name="Technique Training",
            category=category,
            defaults={"is_active": True, "display_order": 10},
        )
        w = Decimal("1.0")
        CheckTypeTrait.objects.update_or_create(
            check_type=check_type, trait=intellect_trait, defaults={"weight": w}
        )
        CheckTypeTrait.objects.update_or_create(
            check_type=check_type, trait=arcane_trait, defaults={"weight": w}
        )

    def test_full_success_contributes_full_amount(self):
        with force_check_outcome(self.outcomes["Success"]):
            result = resolve_training_check(self.sheet, self.progress, ap_to_invest=20)
        self.assertEqual(result.dev_points_contributed, 20)
        self.assertEqual(result.ap_spent, 20)
        self.progress.refresh_from_db()
        self.assertEqual(self.progress.points_accumulated, 20)

    def test_botch_contributes_zero_ap_still_spent(self):
        with force_check_outcome(self.outcomes["Critical Failure"]):
            result = resolve_training_check(self.sheet, self.progress, ap_to_invest=20)
        self.assertEqual(result.dev_points_contributed, 0)
        self.assertEqual(result.ap_spent, 20)
        self.pool.refresh_from_db()
        self.assertEqual(self.pool.current, 480)  # 500 - 20
        self.progress.refresh_from_db()
        self.assertEqual(self.progress.points_accumulated, 0)

    def test_partial_success_halves(self):
        with force_check_outcome(self.outcomes["Partial Success"]):
            result = resolve_training_check(self.sheet, self.progress, ap_to_invest=20)
        self.assertEqual(result.dev_points_contributed, 10)
        self.assertEqual(result.ap_spent, 20)

    def test_critical_success_bonus(self):
        with force_check_outcome(self.outcomes["Critical Success"]):
            result = resolve_training_check(self.sheet, self.progress, ap_to_invest=20)
        self.assertEqual(result.dev_points_contributed, 30)
        self.assertEqual(result.ap_spent, 20)

    def test_meter_completes_on_fill(self):
        with force_check_outcome(self.outcomes["Success"]):
            result = resolve_training_check(self.sheet, self.progress, ap_to_invest=50)
        self.assertIsNotNone(result.technique_acquired)
        self.assertIsInstance(result.technique_acquired, CharacterTechnique)

    def test_missing_award_row_yields_zero(self):
        TrainingOutcomeAward.objects.filter(outcome_tier__name="Success").delete()
        with force_check_outcome(self.outcomes["Success"]):
            result = resolve_training_check(self.sheet, self.progress, ap_to_invest=20)
        self.assertEqual(result.dev_points_contributed, 0)
        self.assertEqual(result.dev_point_multiplier, Decimal(0))

    def test_higher_technique_tier_harder(self):
        """A higher-tier technique produces a higher target_difficulty."""
        from world.magic.constants import TargetKind
        from world.magic.factories import ResonanceFactory
        from world.magic.models import CharacterGift, Thread

        high_tech = TechniqueFactory(level=20)  # T4
        CharacterGift.objects.create(character=self.sheet, gift=high_tech.gift)
        Thread.objects.create(
            owner=self.sheet,
            resonance=ResonanceFactory(),
            target_kind=TargetKind.GIFT,
            target_gift=high_tech.gift,
            level=0,
        )
        high_progress = TechniqueProgress.objects.create(
            character_sheet=self.sheet,
            technique=high_tech,
            total_required=500,
            source="gift_acquisition",
        )
        difficulties = []

        def capture_check(character, check_type, target_difficulty=0, **kwargs):
            difficulties.append(target_difficulty)
            from world.checks.types import CheckResult

            return CheckResult(
                check_type=check_type,
                outcome=self.outcomes["Success"],
                chart=None,
                roller_rank=None,
                target_rank=None,
                rank_difference=0,
                trait_points=0,
                aspect_bonus=0,
                total_points=0,
            )

        with patch(
            "world.magic.services.technique_training.perform_check_with_modifiers",
            side_effect=capture_check,
        ):
            resolve_training_check(self.sheet, high_progress, ap_to_invest=20)
            resolve_training_check(self.sheet, self.progress, ap_to_invest=20)

        self.assertGreater(difficulties[0], difficulties[1])

    def test_self_study_harder_than_with_teacher(self):
        """Self-study (teacher=None) produces higher difficulty than with a teacher."""
        difficulties = []

        def capture_check(character, check_type, target_difficulty=0, **kwargs):
            difficulties.append(target_difficulty)
            from world.checks.types import CheckResult

            return CheckResult(
                check_type=check_type,
                outcome=self.outcomes["Success"],
                chart=None,
                roller_rank=None,
                target_rank=None,
                rank_difference=0,
                trait_points=0,
                aspect_bonus=0,
                total_points=0,
            )

        # A mock teacher with a high check rating.
        mock_teacher = type("MockTeacher", (), {"character": self.sheet.character})()

        with patch(
            "world.magic.services.technique_training.perform_check_with_modifiers",
            side_effect=capture_check,
        ):
            with patch(
                "world.magic.services.technique_training.compute_check_rating",
                return_value=100,
            ):
                resolve_training_check(
                    self.sheet, self.progress, ap_to_invest=20, teacher=mock_teacher
                )
            resolve_training_check(self.sheet, self.progress, ap_to_invest=20)

        self.assertGreater(difficulties[1], difficulties[0])

    def _academy_progress(self, instruction_bonus: int) -> TechniqueProgress:
        """The meter an Academy TRAIN offer opens, as ``run_train_offer`` stores it."""
        self.progress.source = "academy_training"
        self.progress.instruction_bonus = instruction_bonus
        self.progress.save()
        return self.progress

    def _roll_calls(self, progress: TechniqueProgress) -> dict:
        """Run one session and return the kwargs and the result of the roll it made."""
        from world.checks.services import perform_check_with_modifiers as real_roll

        seen: dict = {}

        def recording_roll(character, check_type, **kwargs):
            result = real_roll(character, check_type, **kwargs)
            seen.update(kwargs, total_points=result.total_points)
            return result

        with (
            force_check_outcome(self.outcomes["Success"]),
            patch(
                "world.magic.services.technique_training.perform_check_with_modifiers",
                side_effect=recording_roll,
            ),
        ):
            resolve_training_check(self.sheet, progress, ap_to_invest=1)
        return seen

    def test_academy_instruction_adds_its_bonus_to_the_roll_once(self):
        """A meter's bonus raises the roll's points by exactly that bonus, labelled.

        Kept as a unit test because no surface shows a roll's points or its modifier lines,
        so the Academy journey can only read the modifier total (``CheckCapture``).
        """
        without = self._roll_calls(self._academy_progress(0))
        with_bonus = self._roll_calls(self._academy_progress(12))

        self.assertEqual(with_bonus["total_points"] - without["total_points"], 12)
        self.assertEqual(without["extra_contributions"], [])
        (line,) = with_bonus["extra_contributions"]
        self.assertEqual((line.source_label, line.value), ("Academy instruction", 12))

    def test_academy_instruction_lifts_the_self_study_penalty(self):
        """Paying for instruction lifts the self-study penalty, even with a bonus of 0.

        Kept as a unit test because it compares against a self-study meter, which no
        journey can open without writing the meter by hand.
        """
        self_study = self._roll_calls(self.progress)
        academy = self._roll_calls(self._academy_progress(0))

        self.assertLess(academy["target_difficulty"], self_study["target_difficulty"])

    def _style_skill(self, name: str):
        from world.skills.factories import MagicSkillFactory

        return MagicSkillFactory(name=name)

    def _technique_in_style(self, skill):
        from world.magic.factories import GiftFactory, TechniqueStyleFactory

        style = TechniqueStyleFactory(name=f"{skill.name} style", skill=skill)
        return TechniqueFactory(gift=GiftFactory(style=style))

    def test_a_style_skill_staff_already_mapped_counts_once(self):
        """Kept as a unit test: a journey would need staff to map the skill first."""
        from world.magic.constants import MagicActivity
        from world.magic.factories import MagicActivitySkillFactory
        from world.magic.services.magic_skills import technique_learning_terms

        steel = self._style_skill("Steelwork")
        MagicActivitySkillFactory(
            activity=MagicActivity.TECHNIQUE_LEARNING, skill=steel, weight=Decimal("0.50")
        )
        terms = technique_learning_terms(
            self.sheet.character, self._technique_in_style(steel), self._training_check_type()
        )

        self.assertEqual([(t.trait.pk, t.weight) for t in terms], [(steel.pk, Decimal("0.50"))])

    def test_a_style_skill_the_check_type_already_weights_counts_once(self):
        """Kept as a unit test: a journey would need the check type authored with the skill."""
        from world.checks.models import CheckTypeTrait
        from world.magic.services.magic_skills import technique_learning_terms

        steel = self._style_skill("Steelwork")
        check_type = self._training_check_type()
        CheckTypeTrait.objects.create(check_type=check_type, trait=steel, weight=Decimal("1.0"))

        terms = technique_learning_terms(
            self.sheet.character, self._technique_in_style(steel), check_type
        )

        self.assertEqual(terms, ())

    def _training_check_type(self):
        from world.checks.models import CheckType

        return CheckType.objects.get(name="Technique Training")


class ResolveTrainingCheckMissingCheckTypeTest(TestCase):
    """#3043: no silent objects.first() fallback when "Technique Training" is unauthored.

    The old fallback picked an arbitrary, unrelated CheckType on
    ``DoesNotExist`` -- every training roll on a real deploy (where the
    content half of #3043, ArxII-lore#72, hasn't shipped yet) silently rolled
    the wrong check. This proves the fix fails loudly instead, even when
    other CheckType rows exist to be picked by ``objects.first()``.
    """

    def setUp(self):
        from world.checks.factories import CheckTypeFactory
        from world.magic.constants import TargetKind
        from world.magic.factories import ResonanceFactory
        from world.magic.models import CharacterGift, Thread

        self.sheet = CharacterSheetFactory()
        self.technique = TechniqueFactory()
        self.pool = ActionPointPool.get_or_create_for_character(self.sheet.character)
        self.pool.current = 500
        self.pool.save()

        CharacterGift.objects.create(character=self.sheet, gift=self.technique.gift)
        Thread.objects.create(
            owner=self.sheet,
            resonance=ResonanceFactory(),
            target_kind=TargetKind.GIFT,
            target_gift=self.technique.gift,
            level=0,
        )
        self.progress = TechniqueProgress.objects.create(
            character_sheet=self.sheet,
            technique=self.technique,
            total_required=50,
            source="gift_acquisition",
        )
        # An unrelated CheckType exists (proves the old objects.first()
        # fallback would have silently picked it up), but none named
        # "Technique Training".
        CheckTypeFactory(name="Unrelated Check")

    def test_raises_technique_training_not_configured(self):
        from world.magic.exceptions import TechniqueTrainingNotConfigured

        with self.assertRaises(TechniqueTrainingNotConfigured):
            resolve_training_check(self.sheet, self.progress, ap_to_invest=20)
