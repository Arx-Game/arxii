"""Tests for the training allocation system."""

from django.db import IntegrityError
from django.test import TestCase

from world.action_points.models import ActionPointConfig, ActionPointPool
from world.character_sheets.factories import GuiseFactory
from world.classes.factories import CharacterClassLevelFactory
from world.progression.models.rewards import DevelopmentTransaction
from world.progression.types import DevelopmentSource
from world.skills.factories import (
    CharacterSkillValueFactory,
    CharacterSpecializationValueFactory,
    SkillFactory,
    SpecializationFactory,
)
from world.skills.models import TrainingAllocation
from world.skills.services import (
    _apply_development_to_skill,
    apply_weekly_rust,
    calculate_training_development,
    create_training_allocation,
    process_weekly_training,
    remove_training_allocation,
    run_weekly_skill_cron,
    update_training_allocation,
)


class TrainingAllocationModelTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        cls.guise = GuiseFactory()
        cls.character = cls.guise.character
        cls.skill = SkillFactory()
        cls.specialization = SpecializationFactory(parent_skill=cls.skill)
        cls.mentor = GuiseFactory()

    def test_create_skill_allocation(self) -> None:
        """Can create an allocation for a skill with a mentor."""
        alloc = TrainingAllocation.objects.create(
            character=self.character,
            skill=self.skill,
            mentor=self.mentor,
            ap_amount=20,
        )
        self.assertEqual(alloc.character, self.character)
        self.assertEqual(alloc.skill, self.skill)
        self.assertIsNone(alloc.specialization)
        self.assertEqual(alloc.mentor, self.mentor)
        self.assertEqual(alloc.ap_amount, 20)

    def test_create_specialization_allocation(self) -> None:
        """Can create an allocation for a specialization."""
        alloc = TrainingAllocation.objects.create(
            character=self.character,
            specialization=self.specialization,
            ap_amount=10,
        )
        self.assertIsNone(alloc.skill)
        self.assertEqual(alloc.specialization, self.specialization)
        self.assertIsNone(alloc.mentor)

    def test_create_self_study(self) -> None:
        """Null mentor means self-study."""
        alloc = TrainingAllocation.objects.create(
            character=self.character,
            skill=self.skill,
            ap_amount=5,
        )
        self.assertIsNone(alloc.mentor)

    def test_unique_skill_per_character(self) -> None:
        """Cannot create two allocations for same skill+character."""
        TrainingAllocation.objects.create(
            character=self.character,
            skill=self.skill,
            ap_amount=10,
        )
        with self.assertRaises(IntegrityError):
            TrainingAllocation.objects.create(
                character=self.character,
                skill=self.skill,
                ap_amount=5,
            )

    def test_unique_specialization_per_character(self) -> None:
        """Cannot create two allocations for same specialization+character."""
        TrainingAllocation.objects.create(
            character=self.character,
            specialization=self.specialization,
            ap_amount=10,
        )
        with self.assertRaises(IntegrityError):
            TrainingAllocation.objects.create(
                character=self.character,
                specialization=self.specialization,
                ap_amount=5,
            )

    def test_str_skill(self) -> None:
        """String representation includes character and skill name."""
        alloc = TrainingAllocation.objects.create(
            character=self.character,
            skill=self.skill,
            ap_amount=10,
        )
        result = str(alloc)
        self.assertIn(self.character.db_key, result)

    def test_rejects_both_skill_and_specialization(self) -> None:
        """Cannot set both skill and specialization."""
        with self.assertRaises(IntegrityError):
            TrainingAllocation.objects.create(
                character=self.character,
                skill=self.skill,
                specialization=self.specialization,
                ap_amount=10,
            )

    def test_rejects_neither_skill_nor_specialization(self) -> None:
        """Must set either skill or specialization."""
        with self.assertRaises(IntegrityError):
            TrainingAllocation.objects.create(
                character=self.character,
                ap_amount=10,
            )


class CalculateTrainingDevelopmentTests(TestCase):
    """Tests for calculate_training_development formula."""

    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        cls.student_guise = GuiseFactory()
        cls.student = cls.student_guise.character
        cls.skill = SkillFactory()

        # Student has skill value 40
        cls.student_skill = CharacterSkillValueFactory(
            character=cls.student,
            skill=cls.skill,
            value=40,
        )

        # Mentor guise + character
        cls.mentor_guise = GuiseFactory()
        cls.mentor = cls.mentor_guise.character

        # Mentor has skill value 100
        CharacterSkillValueFactory(
            character=cls.mentor,
            skill=cls.skill,
            value=100,
        )

        # Teaching skill for mentor (value=20)
        cls.teaching_skill = SkillFactory()
        cls.teaching_skill.trait.name = "Teaching"
        cls.teaching_skill.trait.save()
        CharacterSkillValueFactory(
            character=cls.mentor,
            skill=cls.teaching_skill,
            value=20,
        )

        # Path level for student = 5
        CharacterClassLevelFactory(character=cls.student, level=5)

    def test_self_study_base_gain(self) -> None:
        """Self-study: base_gain = 5 * AP * path_level."""
        alloc = TrainingAllocation.objects.create(
            character=self.student,
            skill=self.skill,
            ap_amount=20,
        )
        result = calculate_training_development(alloc)
        # 5 * 20 * 5 = 500
        self.assertEqual(result, 500)

    def test_with_mentor(self) -> None:
        """With mentor: base_gain + mentor_bonus."""
        alloc = TrainingAllocation.objects.create(
            character=self.student,
            skill=self.skill,
            mentor=self.mentor_guise,
            ap_amount=20,
        )
        result = calculate_training_development(alloc)
        # base = 5 * 20 * 5 = 500
        # mentor_total = 100 (skill) + 20 (teaching) = 120
        # student_total = 40
        # ratio = 120 / 40 = 3.0
        # effective_AP = 20 + 20 = 40
        # relationship_tier = 0 (stub), so (0 + 1) = 1
        # mentor_bonus = 40 * 3.0 * 1 = 120
        # total = 500 + 120 = 620
        self.assertEqual(result, 620)

    def test_no_path_level_defaults_to_one(self) -> None:
        """Character with no class levels uses path_level=1."""
        student_guise = GuiseFactory()
        student = student_guise.character
        CharacterSkillValueFactory(character=student, skill=self.skill, value=20)
        alloc = TrainingAllocation.objects.create(
            character=student,
            skill=self.skill,
            ap_amount=10,
        )
        result = calculate_training_development(alloc)
        # 5 * 10 * 1 = 50
        self.assertEqual(result, 50)

    def test_returns_integer(self) -> None:
        """Result is always an integer (truncated)."""
        alloc = TrainingAllocation.objects.create(
            character=self.student,
            skill=self.skill,
            mentor=self.mentor_guise,
            ap_amount=7,
        )
        result = calculate_training_development(alloc)
        self.assertIsInstance(result, int)

    def test_zero_student_skill_uses_floor(self) -> None:
        """Student with 0 skill uses 1 to prevent division by zero."""
        student_guise = GuiseFactory()
        student = student_guise.character
        # No CharacterSkillValue created — defaults to 0 -> floor to 1
        CharacterClassLevelFactory(character=student, level=1)
        alloc = TrainingAllocation.objects.create(
            character=student,
            skill=self.skill,
            mentor=self.mentor_guise,
            ap_amount=10,
        )
        result = calculate_training_development(alloc)
        # base = 5 * 10 * 1 = 50
        # mentor_total = 100 + 20 = 120
        # student_total = 0 -> 1
        # ratio = 120
        # effective_AP = 10 + 20 = 30
        # mentor_bonus = 30 * 120 * 1 = 3600
        # total = 50 + 3600 = 3650
        self.assertEqual(result, 3650)


class CalculateSpecializationTrainingTests(TestCase):
    """Tests for specialization training development calculation."""

    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        cls.student_guise = GuiseFactory()
        cls.student = cls.student_guise.character

        cls.skill = SkillFactory()
        cls.spec = SpecializationFactory(parent_skill=cls.skill)

        # Student: parent=30, spec=10, total=40
        CharacterSkillValueFactory(character=cls.student, skill=cls.skill, value=30)
        CharacterSpecializationValueFactory(
            character=cls.student,
            specialization=cls.spec,
            value=10,
        )

        # Mentor: parent=50, spec=50, teaching=20
        cls.mentor_guise = GuiseFactory()
        cls.mentor = cls.mentor_guise.character
        CharacterSkillValueFactory(character=cls.mentor, skill=cls.skill, value=50)
        CharacterSpecializationValueFactory(
            character=cls.mentor,
            specialization=cls.spec,
            value=50,
        )
        cls.teaching_skill = SkillFactory()
        cls.teaching_skill.trait.name = "Teaching"
        cls.teaching_skill.trait.save()
        CharacterSkillValueFactory(
            character=cls.mentor,
            skill=cls.teaching_skill,
            value=20,
        )

        CharacterClassLevelFactory(character=cls.student, level=5)

    def test_specialization_with_mentor(self) -> None:
        """Spec training uses parent+spec for both student and mentor."""
        alloc = TrainingAllocation.objects.create(
            character=self.student,
            specialization=self.spec,
            mentor=self.mentor_guise,
            ap_amount=20,
        )
        result = calculate_training_development(alloc)
        # base = 5 * 20 * 5 = 500
        # student_total = 30 + 10 = 40
        # mentor_total = 50 + 50 + 20 = 120
        # ratio = 120 / 40 = 3.0
        # effective_AP = 20 + 20 = 40
        # relationship = (0 + 1) = 1
        # mentor_bonus = 40 * 3.0 * 1 = 120
        # total = 500 + 120 = 620
        self.assertEqual(result, 620)

    def test_specialization_self_study(self) -> None:
        """Specialization self-study only uses base gain."""
        alloc = TrainingAllocation.objects.create(
            character=self.student,
            specialization=self.spec,
            ap_amount=10,
        )
        result = calculate_training_development(alloc)
        # 5 * 10 * 5 = 250
        self.assertEqual(result, 250)


class CreateTrainingAllocationTests(TestCase):
    """Tests for create_training_allocation service."""

    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        cls.guise = GuiseFactory()
        cls.character = cls.guise.character
        cls.skill = SkillFactory()
        cls.mentor = GuiseFactory()

    def test_creates_allocation(self) -> None:
        """Creates a valid allocation."""
        alloc = create_training_allocation(
            character=self.character,
            skill=self.skill,
            ap_amount=20,
        )
        self.assertEqual(alloc.character, self.character)
        self.assertEqual(alloc.skill, self.skill)
        self.assertEqual(alloc.ap_amount, 20)

    def test_with_mentor(self) -> None:
        """Creates allocation with mentor."""
        alloc = create_training_allocation(
            character=self.character,
            skill=self.skill,
            mentor=self.mentor,
            ap_amount=10,
        )
        self.assertEqual(alloc.mentor, self.mentor)

    def test_rejects_exceeding_weekly_budget(self) -> None:
        """Raises ValueError if total AP would exceed weekly regen."""
        config = ActionPointConfig.get_active()
        budget = config.weekly_regen if config else 100
        create_training_allocation(
            character=self.character,
            skill=self.skill,
            ap_amount=budget,
        )
        skill2 = SkillFactory()
        with self.assertRaises(ValueError):
            create_training_allocation(
                character=self.character,
                skill=skill2,
                ap_amount=1,
            )

    def test_rejects_zero_ap(self) -> None:
        """Raises ValueError for 0 AP."""
        with self.assertRaises(ValueError):
            create_training_allocation(
                character=self.character,
                skill=self.skill,
                ap_amount=0,
            )


class UpdateTrainingAllocationTests(TestCase):
    """Tests for update_training_allocation service."""

    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        cls.guise = GuiseFactory()
        cls.character = cls.guise.character
        cls.skill = SkillFactory()

    def test_updates_ap_amount(self) -> None:
        """Can update the AP amount."""
        alloc = create_training_allocation(
            character=self.character,
            skill=self.skill,
            ap_amount=20,
        )
        updated = update_training_allocation(alloc, ap_amount=30)
        self.assertEqual(updated.ap_amount, 30)

    def test_updates_mentor(self) -> None:
        """Can change mentor."""
        alloc = create_training_allocation(
            character=self.character,
            skill=self.skill,
            ap_amount=20,
        )
        mentor = GuiseFactory()
        updated = update_training_allocation(alloc, mentor=mentor)
        self.assertEqual(updated.mentor, mentor)

    def test_rejects_exceeding_budget_on_update(self) -> None:
        """Raises ValueError if updated total exceeds budget."""
        config = ActionPointConfig.get_active()
        budget = config.weekly_regen if config else 100
        alloc = create_training_allocation(
            character=self.character,
            skill=self.skill,
            ap_amount=budget,
        )
        with self.assertRaises(ValueError):
            update_training_allocation(alloc, ap_amount=budget + 1)


class RemoveTrainingAllocationTests(TestCase):
    """Tests for remove_training_allocation service."""

    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        cls.guise = GuiseFactory()
        cls.character = cls.guise.character
        cls.skill = SkillFactory()

    def test_removes_allocation(self) -> None:
        """Deletes the allocation."""
        alloc = create_training_allocation(
            character=self.character,
            skill=self.skill,
            ap_amount=20,
        )
        remove_training_allocation(alloc)
        self.assertFalse(TrainingAllocation.objects.filter(pk=alloc.pk).exists())


class ProcessWeeklyTrainingTests(TestCase):
    """Tests for process_weekly_training cron function."""

    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        cls.student_guise = GuiseFactory()
        cls.student = cls.student_guise.character
        cls.skill = SkillFactory()

    def setUp(self) -> None:
        super().setUp()
        from world.classes.models import CharacterClassLevel

        # Clean up any leftover allocations and class levels from prior tests
        TrainingAllocation.objects.filter(character=self.student).delete()
        CharacterClassLevel.objects.filter(character=self.student).delete()

        # Create fresh mutable data each test
        self.student_skill, _ = self.student.skill_values.update_or_create(
            skill=self.skill,
            defaults={"value": 10, "development_points": 0, "rust_points": 0},
        )
        CharacterClassLevelFactory(character=self.student, level=1)

    def test_awards_development_points(self) -> None:
        """Training awards development points to the skill."""
        TrainingAllocation.objects.create(
            character=self.student,
            skill=self.skill,
            ap_amount=10,
        )
        trained_skills = process_weekly_training()
        self.student_skill.refresh_from_db()
        # base = 5 * 10 * 1 = 50
        self.assertEqual(self.student_skill.development_points, 50)
        self.assertIn(self.student.pk, trained_skills)

    def test_levels_up_on_threshold(self) -> None:
        """Skill levels up when dev points exceed cost."""
        TrainingAllocation.objects.create(
            character=self.student,
            skill=self.skill,
            ap_amount=20,
        )
        process_weekly_training()
        self.student_skill.refresh_from_db()
        # base = 5 * 20 * 1 = 100. Cost 10->11 = 100. Level up!
        self.assertEqual(self.student_skill.value, 11)
        self.assertEqual(self.student_skill.development_points, 0)

    def test_overflow_carries_over(self) -> None:
        """Excess dev points carry into next level."""
        self.student_skill.development_points = 50
        self.student_skill.save()
        TrainingAllocation.objects.create(
            character=self.student,
            skill=self.skill,
            ap_amount=20,
        )
        process_weekly_training()
        self.student_skill.refresh_from_db()
        # Had 50 + gained 100 = 150. Cost 10->11 = 100. Overflow = 50.
        self.assertEqual(self.student_skill.value, 11)
        self.assertEqual(self.student_skill.development_points, 50)

    def test_multiple_level_ups(self) -> None:
        """Can gain multiple levels in one week with enough dev points."""
        from world.classes.models import CharacterClassLevel

        ccl = CharacterClassLevel.objects.get(character=self.student)
        ccl.level = 5
        ccl.save()
        TrainingAllocation.objects.create(
            character=self.student,
            skill=self.skill,
            ap_amount=20,
        )
        process_weekly_training()
        self.student_skill.refresh_from_db()
        # base = 5 * 20 * 5 = 500. Cost 10->11=100, 11->12=200. Total=300.
        # 500-300 = 200 left, cost 12->13=300. Can't. So level 12, 200 dev.
        self.assertEqual(self.student_skill.value, 12)
        self.assertEqual(self.student_skill.development_points, 200)

    def test_stops_at_x9_boundary(self) -> None:
        """Dev points are wasted at X9 boundaries (19, 29, etc.)."""
        self.student_skill.value = 19
        self.student_skill.save()
        TrainingAllocation.objects.create(
            character=self.student,
            skill=self.skill,
            ap_amount=10,
        )
        process_weekly_training()
        self.student_skill.refresh_from_db()
        # At boundary, points wasted
        self.assertEqual(self.student_skill.value, 19)
        self.assertEqual(self.student_skill.development_points, 0)

    def test_consumes_ap(self) -> None:
        """AP is consumed from the character's pool."""
        pool, _ = ActionPointPool.objects.get_or_create(
            character=self.student,
            defaults={"current": 100, "maximum": 200},
        )
        pool.current = 100
        pool.save()
        TrainingAllocation.objects.create(
            character=self.student,
            skill=self.skill,
            ap_amount=20,
        )
        process_weekly_training()
        pool.refresh_from_db()
        self.assertEqual(pool.current, 80)

    def test_returns_trained_skills_set(self) -> None:
        """Returns dict mapping character PKs to sets of trained skill PKs."""
        TrainingAllocation.objects.create(
            character=self.student,
            skill=self.skill,
            ap_amount=10,
        )
        result = process_weekly_training()
        self.assertIn(self.skill.pk, result[self.student.pk])

    def test_creates_development_transaction(self) -> None:
        """Each allocation creates a DevelopmentTransaction audit record."""
        TrainingAllocation.objects.create(
            character=self.student,
            skill=self.skill,
            ap_amount=10,
        )
        process_weekly_training()
        txn = DevelopmentTransaction.objects.get(character=self.student)
        self.assertEqual(txn.trait, self.skill.trait)
        self.assertEqual(txn.source, DevelopmentSource.TRAINING)
        self.assertEqual(txn.amount, 50)  # 5 * 10 * 1
        self.assertIn("Weekly training", txn.description)

    def test_logs_warning_on_missing_ap_pool(self) -> None:
        """Logs a warning when character has no AP pool."""
        TrainingAllocation.objects.create(
            character=self.student,
            skill=self.skill,
            ap_amount=10,
        )
        with self.assertLogs("world.skills.services", level="WARNING") as cm:
            process_weekly_training()
        self.assertTrue(any("No AP pool" in msg for msg in cm.output))

    def test_logs_warning_on_insufficient_ap(self) -> None:
        """Logs a warning when AP pool has insufficient points."""
        pool, _ = ActionPointPool.objects.get_or_create(
            character=self.student,
            defaults={"current": 0, "maximum": 200},
        )
        pool.current = 0
        pool.save()
        TrainingAllocation.objects.create(
            character=self.student,
            skill=self.skill,
            ap_amount=10,
        )
        with self.assertLogs("world.skills.services", level="WARNING") as cm:
            process_weekly_training()
        self.assertTrue(any("Insufficient AP" in msg for msg in cm.output))

    def test_specialization_training_creates_transaction_with_parent_trait(self) -> None:
        """Specialization training records transaction under parent skill's trait."""
        spec = SpecializationFactory(parent_skill=self.skill)
        TrainingAllocation.objects.create(
            character=self.student,
            specialization=spec,
            ap_amount=10,
        )
        process_weekly_training()
        txn = DevelopmentTransaction.objects.get(character=self.student)
        self.assertEqual(txn.trait, self.skill.trait)
        self.assertEqual(txn.source, DevelopmentSource.TRAINING)


class ApplyWeeklyRustTests(TestCase):
    """Tests for apply_weekly_rust function."""

    def setUp(self) -> None:
        super().setUp()
        self.guise = GuiseFactory()
        self.character = self.guise.character
        self.skill = SkillFactory()
        self.skill_value = CharacterSkillValueFactory(
            character=self.character,
            skill=self.skill,
            value=11,
            rust_points=0,
        )
        CharacterClassLevelFactory(character=self.character, level=5)

    def test_adds_rust_to_unused_skill(self) -> None:
        """Unused skill gains character_level + 5 rust."""
        apply_weekly_rust(trained_skills={})
        self.skill_value.refresh_from_db()
        # level 5 + 5 = 10 rust
        self.assertEqual(self.skill_value.rust_points, 10)

    def test_no_rust_on_trained_skill(self) -> None:
        """Trained skill gets no rust."""
        trained = {self.character.pk: {self.skill.pk}}
        apply_weekly_rust(trained_skills=trained)
        self.skill_value.refresh_from_db()
        self.assertEqual(self.skill_value.rust_points, 0)

    def test_rust_caps_at_level_cost(self) -> None:
        """Rust cannot exceed current level's development cost."""
        # Skill 11: cost = (11-9)*100 = 200
        self.skill_value.rust_points = 195
        self.skill_value.save()
        apply_weekly_rust(trained_skills={})
        self.skill_value.refresh_from_db()
        # Would add 10, but cap is 200, so 200
        self.assertEqual(self.skill_value.rust_points, 200)

    def test_rust_accumulates_over_weeks(self) -> None:
        """Rust accumulates across multiple calls."""
        apply_weekly_rust(trained_skills={})
        apply_weekly_rust(trained_skills={})
        self.skill_value.refresh_from_db()
        # 10 + 10 = 20
        self.assertEqual(self.skill_value.rust_points, 20)


class RustPayoffTests(TestCase):
    """Tests for rust being paid off during development."""

    def setUp(self) -> None:
        super().setUp()
        self.guise = GuiseFactory()
        self.character = self.guise.character
        self.skill = SkillFactory()
        self.skill_value = CharacterSkillValueFactory(
            character=self.character,
            skill=self.skill,
            value=11,
            development_points=0,
            rust_points=0,
        )

    def test_development_pays_off_rust_first(self) -> None:
        """When rust exists, dev points pay rust before advancing."""
        self.skill_value.rust_points = 50
        self.skill_value.save()
        # Apply 80 dev points: 50 clears rust, 30 goes to development
        _apply_development_to_skill(self.skill_value, 80)
        self.assertEqual(self.skill_value.rust_points, 0)
        self.assertEqual(self.skill_value.development_points, 30)

    def test_partial_rust_payoff(self) -> None:
        """Dev points can partially pay off rust."""
        self.skill_value.rust_points = 100
        self.skill_value.save()
        _apply_development_to_skill(self.skill_value, 60)
        self.assertEqual(self.skill_value.rust_points, 40)
        self.assertEqual(self.skill_value.development_points, 0)

    def test_rust_then_level_up(self) -> None:
        """Dev points clear rust, then overflow levels up skill."""
        self.skill_value.rust_points = 50
        self.skill_value.save()
        # Need 50 for rust + 200 for level (11->12) = 250. Give 300.
        _apply_development_to_skill(self.skill_value, 300)
        self.assertEqual(self.skill_value.rust_points, 0)
        self.assertEqual(self.skill_value.value, 12)
        self.assertEqual(self.skill_value.development_points, 50)


class RunWeeklySkillCronTests(TestCase):
    """Integration test for the full weekly cron cycle."""

    def setUp(self) -> None:
        super().setUp()
        self.guise = GuiseFactory()
        self.character = self.guise.character
        self.trained_skill = SkillFactory()
        self.untrained_skill = SkillFactory()
        self.trained_sv = CharacterSkillValueFactory(
            character=self.character,
            skill=self.trained_skill,
            value=10,
        )
        self.untrained_sv = CharacterSkillValueFactory(
            character=self.character,
            skill=self.untrained_skill,
            value=11,
        )
        CharacterClassLevelFactory(character=self.character, level=1)

    def test_trains_and_rusts(self) -> None:
        """Trained skill advances, untrained skill gets rust."""
        TrainingAllocation.objects.create(
            character=self.character,
            skill=self.trained_skill,
            ap_amount=20,
        )
        run_weekly_skill_cron()
        self.trained_sv.refresh_from_db()
        self.untrained_sv.refresh_from_db()
        # Trained: 5*20*1 = 100 dev. 10->11 costs 100. Level up!
        self.assertEqual(self.trained_sv.value, 11)
        self.assertEqual(self.trained_sv.rust_points, 0)
        # Untrained: level 1 + 5 = 6 rust
        self.assertEqual(self.untrained_sv.rust_points, 6)
