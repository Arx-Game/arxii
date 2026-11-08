"""TDD tests for TrainTechniqueAction (#2739).

Step 1: write failing tests before implementing the action. Setup mirrors
world/magic/tests/test_technique_training.py's ResolveTrainingCheckTest (the
seam this action wraps) — same check-content seeding, same canonical outcome
tiers — since this action is the seam's first production caller.
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase

from actions.definitions.technique_training import TrainTechniqueAction
from evennia_extensions.factories import ObjectDBFactory
from world.action_points.models import ActionPointPool
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.test_helpers import force_check_outcome
from world.magic.constants import TargetKind
from world.magic.factories import ResonanceFactory, TechniqueFactory
from world.magic.models import (
    CharacterGift,
    CharacterTechnique,
    TechniqueProgress,
    Thread,
    TrainingOutcomeAward,
)
from world.roster.factories import RosterTenureFactory
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


class TrainTechniqueActionTestBase(TestCase):
    def setUp(self):
        self.room = ObjectDBFactory(
            db_key="TrainingRoom", db_typeclass_path="typeclasses.rooms.Room"
        )
        self.learner = CharacterSheetFactory()
        self.learner.character.location = self.room
        self.learner.character.save()

        self.pool = ActionPointPool.get_or_create_for_character(self.learner.character)
        self.pool.current = 500
        self.pool.save()

        self.technique = TechniqueFactory()
        CharacterGift.objects.create(character=self.learner, gift=self.technique.gift)
        Thread.objects.create(
            owner=self.learner,
            resonance=ResonanceFactory(),
            target_kind=TargetKind.GIFT,
            target_gift=self.technique.gift,
            level=0,
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
        """Minimal CheckType so the seam can resolve a check."""
        from world.checks.models import CheckCategory, CheckType, CheckTypeTrait
        from world.skills.models import Skill
        from world.traits.models import Trait, TraitCategory, TraitType

        arcane_trait, _ = Trait.objects.get_or_create(
            name="Arcane Theory",
            defaults={
                "trait_type": TraitType.SKILL,
                "category": TraitCategory.MAGIC,
                "is_public": True,
            },
        )
        Skill.objects.get_or_create(
            trait=arcane_trait,
            defaults={
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

    def _make_progress(self, *, total_required=50, teacher_tenure=None):
        return TechniqueProgress.objects.create(
            character_sheet=self.learner,
            technique=self.technique,
            total_required=total_required,
            source="gift_acquisition",
            teacher_tenure=teacher_tenure,
        )

    def _run(self, **kwargs):
        return TrainTechniqueAction().run(self.learner.character, **kwargs)


class TrainTechniqueActionHappyPathTests(TrainTechniqueActionTestBase):
    def test_happy_session_advances_meter(self):
        progress = self._make_progress(total_required=50)
        with force_check_outcome(self.outcomes["Success"]):
            result = self._run(technique_id=self.technique.pk, ap_to_invest=20)
        self.assertTrue(result.success, result.message)
        progress.refresh_from_db()
        self.assertEqual(progress.points_accumulated, 20)
        self.assertFalse(result.data["technique_acquired"])

    def test_completion_mints_character_technique(self):
        progress = self._make_progress(total_required=20)
        with force_check_outcome(self.outcomes["Success"]):
            result = self._run(technique_id=self.technique.pk, ap_to_invest=20)
        self.assertTrue(result.success, result.message)
        self.assertTrue(result.data["technique_acquired"])
        self.assertTrue(
            CharacterTechnique.objects.filter(
                character=self.learner, technique=self.technique
            ).exists()
        )
        self.assertFalse(TechniqueProgress.objects.filter(pk=progress.pk).exists())

    def test_self_study_with_no_teacher_tenure(self):
        self._make_progress(total_required=50)
        with force_check_outcome(self.outcomes["Success"]):
            result = self._run(technique_id=self.technique.pk, ap_to_invest=20)
        self.assertTrue(result.success, result.message)
        self.assertTrue(result.data["self_study"])

    def test_teacher_absent_falls_back_to_self_study(self):
        """Tenure set but not co-present -> still succeeds, self-study branch."""
        teacher_tenure = RosterTenureFactory()
        elsewhere = ObjectDBFactory(
            db_key="ElsewhereRoom", db_typeclass_path="typeclasses.rooms.Room"
        )
        teacher_tenure.character.location = elsewhere
        teacher_tenure.character.save()
        self._make_progress(total_required=50, teacher_tenure=teacher_tenure)

        with force_check_outcome(self.outcomes["Success"]):
            result = self._run(technique_id=self.technique.pk, ap_to_invest=20)

        self.assertTrue(result.success, result.message)
        self.assertTrue(result.data["self_study"])

    def test_teacher_co_present_is_not_self_study(self):
        teacher_tenure = RosterTenureFactory()
        teacher_tenure.character.location = self.room
        teacher_tenure.character.save()
        self._make_progress(total_required=50, teacher_tenure=teacher_tenure)

        with force_check_outcome(self.outcomes["Success"]):
            result = self._run(technique_id=self.technique.pk, ap_to_invest=20)

        self.assertTrue(result.success, result.message)
        self.assertFalse(result.data["self_study"])

    def test_omitted_ap_defaults_to_positive_amount(self):
        self._make_progress(total_required=50)
        with force_check_outcome(self.outcomes["Success"]):
            result = self._run(technique_id=self.technique.pk)
        self.assertTrue(result.success, result.message)


class TrainTechniqueActionFailureTests(TrainTechniqueActionTestBase):
    def test_no_meter_fails_cleanly(self):
        result = self._run(technique_id=self.technique.pk, ap_to_invest=20)
        self.assertFalse(result.success)
        self.assertTrue(result.message)

    def test_non_positive_ap_rejected(self):
        self._make_progress(total_required=50)
        result = self._run(technique_id=self.technique.pk, ap_to_invest=0)
        self.assertFalse(result.success)

    def test_cap_exceeded_maps_to_failure_result_not_raise(self):
        self._make_progress(total_required=500)
        from world.magic.services.gift_acquisition import get_gift_acquisition_config

        config = get_gift_acquisition_config()
        config.weekly_training_cap = 5
        config.save()

        with force_check_outcome(self.outcomes["Success"]):
            first = self._run(technique_id=self.technique.pk, ap_to_invest=5)
            second = self._run(technique_id=self.technique.pk, ap_to_invest=5)

        self.assertTrue(first.success, first.message)
        self.assertFalse(second.success)
        self.assertTrue(second.message)

    def test_ap_short_maps_to_failure_result_not_raise(self):
        self._make_progress(total_required=500)
        self.pool.current = 2
        self.pool.save()

        with force_check_outcome(self.outcomes["Success"]):
            result = self._run(technique_id=self.technique.pk, ap_to_invest=20)

        self.assertFalse(result.success)
        self.assertTrue(result.message)

    def test_already_known_completion_maps_to_failure_result_not_raise(self):
        """A stale open meter for a technique already learned by another route.

        (e.g. a staff grant or a TechniqueGrant item) mints nothing further —
        learn_technique's bare ValueError must be caught, not escape as a
        traceback (#2739 review finding).
        """
        progress = self._make_progress(total_required=20)
        CharacterTechnique.objects.create(character=self.learner, technique=self.technique)

        with force_check_outcome(self.outcomes["Success"]):
            result = self._run(technique_id=self.technique.pk, ap_to_invest=20)

        self.assertFalse(result.success)
        self.assertIn("already knows", result.message)
        # contribute_to_technique_progress is @transaction.atomic, so the
        # ValueError rolls back everything the session would have written
        # (meter progress, AP spend) -- the meter survives untouched and no
        # duplicate CharacterTechnique appears.
        self.assertTrue(TechniqueProgress.objects.filter(pk=progress.pk).exists())
        self.assertEqual(
            CharacterTechnique.objects.filter(
                character=self.learner, technique=self.technique
            ).count(),
            1,
        )

    def test_meter_deleted_mid_session_maps_to_failure_result_not_raise(self):
        """A concurrent session completes+deletes the meter before this one's seam call.

        contribute_to_technique_progress re-gets TechniqueProgress by pk under
        select_for_update (technique_progress.py:132-138) -- two concurrent
        sessions serialize on the weekly-tracker lock rather than racing on the
        meter row itself, but if the first session's contribution completes
        (and deletes) the meter while the second is blocked on that lock, the
        second's re-get raises TechniqueProgress.DoesNotExist instead of
        returning a stale row. A true concurrency repro is out of scope here;
        this simulates the same observable seam-raise deterministically by
        monkeypatching resolve_training_check to raise it directly (#2739
        final-review finding).
        """
        self._make_progress(total_required=20)

        # execute() does a local `from world.magic.services.technique_training
        # import resolve_training_check` (a lint-suppressed local import) --
        # it re-imports the name fresh from the source module on every call,
        # so the patch target is the source module's attribute, not a
        # module-level binding on actions.definitions.technique_training
        # (there isn't one).
        with patch(
            "world.magic.services.technique_training.resolve_training_check",
            side_effect=TechniqueProgress.DoesNotExist,
        ):
            result = self._run(technique_id=self.technique.pk, ap_to_invest=20)

        self.assertFalse(result.success)
        self.assertTrue(result.message)


class TrainTechniqueActionMissingCheckTypeTests(TestCase):
    """#3043: a missing "Technique Training" CheckType surfaces as a clean failure.

    Setup deliberately skips ``_seed_check_content`` -- mirrors a real deploy
    where the content half of #3043 (ArxII-lore#72) hasn't shipped yet.
    """

    def setUp(self):
        self.room = ObjectDBFactory(
            db_key="TrainingRoom", db_typeclass_path="typeclasses.rooms.Room"
        )
        self.learner = CharacterSheetFactory()
        self.learner.character.location = self.room
        self.learner.character.save()

        self.pool = ActionPointPool.get_or_create_for_character(self.learner.character)
        self.pool.current = 500
        self.pool.save()

        self.technique = TechniqueFactory()
        CharacterGift.objects.create(character=self.learner, gift=self.technique.gift)
        Thread.objects.create(
            owner=self.learner,
            resonance=ResonanceFactory(),
            target_kind=TargetKind.GIFT,
            target_gift=self.technique.gift,
            level=0,
        )
        self.progress = TechniqueProgress.objects.create(
            character_sheet=self.learner,
            technique=self.technique,
            total_required=50,
            source="gift_acquisition",
        )

    def test_missing_check_type_surfaces_as_clean_failure_result(self):
        result = TrainTechniqueAction().run(
            self.learner.character, technique_id=self.technique.pk, ap_to_invest=20
        )
        self.assertFalse(result.success)
        self.assertEqual(result.message, "Technique training is not configured on this server yet.")
