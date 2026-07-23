"""Tests for ThreadCrossingThreshold + polymorphic requirement FK (#1885).

Covers:
- ThreadCrossingThreshold model constraints + clean() validation
- The polymorphic unlock-target CheckConstraint (neither/both rejected)
- check_requirements_for_thread_crossing service (met/unmet/fail-open)
- Related-name resolution (no collision between class_level_unlock and
  thread_crossing_threshold reverse accessors)
"""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.classes.factories import CharacterClassFactory
from world.classes.services import stage_for_level
from world.items.factories import ItemTemplateFactory
from world.magic.constants import TargetKind
from world.magic.models import ThreadCrossingThreshold
from world.progression.models import (
    ClassLevelUnlock,
    ItemRequirement,
    TraitRequirement,
)
from world.progression.services.spends import (
    check_requirements_for_thread_crossing,
    check_requirements_for_unlock,
)


class ThreadCrossingThresholdModelTests(TestCase):
    """Model-level constraints and clean() validation."""

    def test_create_valid_crossing_level_3(self) -> None:
        threshold = ThreadCrossingThreshold(target_kind=TargetKind.GIFT, level=3)
        threshold.save()
        assert threshold.stage == stage_for_level(3)
        assert threshold.pk is not None

    def test_create_valid_crossing_level_6(self) -> None:
        threshold = ThreadCrossingThreshold.objects.create(
            target_kind=TargetKind.COVENANT_ROLE, level=6
        )
        assert threshold.stage == stage_for_level(6)

    def test_create_valid_crossing_level_21(self) -> None:
        threshold = ThreadCrossingThreshold.objects.create(target_kind=TargetKind.TRAIT, level=21)
        assert threshold.stage == stage_for_level(21)

    def test_clean_rejects_non_crossing_level_4(self) -> None:
        """Level 4 is not a crossing — stage_for_level(4) == stage_for_level(3)."""
        threshold = ThreadCrossingThreshold(
            target_kind=TargetKind.GIFT, level=4, stage=stage_for_level(4)
        )
        with self.assertRaises(ValidationError) as ctx:
            threshold.clean()
        assert "not a PathStage crossing" in str(ctx.exception)

    def test_clean_rejects_non_crossing_level_5(self) -> None:
        threshold = ThreadCrossingThreshold(
            target_kind=TargetKind.GIFT, level=5, stage=stage_for_level(5)
        )
        with self.assertRaises(ValidationError):
            threshold.clean()

    def test_clean_rejects_non_crossing_level_7(self) -> None:
        threshold = ThreadCrossingThreshold(
            target_kind=TargetKind.GIFT, level=7, stage=stage_for_level(7)
        )
        with self.assertRaises(ValidationError):
            threshold.clean()

    def test_clean_rejects_stage_mismatch(self) -> None:
        """Stage field must match stage_for_level(level)."""
        threshold = ThreadCrossingThreshold(
            target_kind=TargetKind.GIFT, level=3, stage=stage_for_level(6)
        )
        with self.assertRaises(ValidationError) as ctx:
            threshold.clean()
        assert "does not match" in str(ctx.exception)

    def test_unique_target_kind_level(self) -> None:
        ThreadCrossingThreshold.objects.create(target_kind=TargetKind.GIFT, level=3)
        with self.assertRaises(IntegrityError), transaction.atomic():
            ThreadCrossingThreshold.objects.create(target_kind=TargetKind.GIFT, level=3)

    def test_different_kinds_same_level_allowed(self) -> None:
        """A GIFT level-3 and a COVENANT_ROLE level-3 are distinct rows."""
        t1 = ThreadCrossingThreshold.objects.create(target_kind=TargetKind.GIFT, level=3)
        t2 = ThreadCrossingThreshold.objects.create(target_kind=TargetKind.COVENANT_ROLE, level=3)
        assert t1.pk != t2.pk

    def test_str_representation(self) -> None:
        threshold = ThreadCrossingThreshold(
            target_kind=TargetKind.GIFT, level=3, stage=stage_for_level(3)
        )
        assert "GIFT" in str(threshold)
        assert "3" in str(threshold)


class PolymorphicRequirementFKTests(TestCase):
    """CheckConstraint: exactly one of class_level_unlock / thread_crossing_threshold."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.character_class = CharacterClassFactory()
        cls.class_unlock = ClassLevelUnlock.objects.create(
            character_class=cls.character_class, target_level=4
        )
        cls.threshold = ThreadCrossingThreshold.objects.create(target_kind=TargetKind.GIFT, level=3)

    def test_item_requirement_with_class_level_unlock(self) -> None:
        """Existing Durance path still works — class_level_unlock set, threshold null."""
        template = ItemTemplateFactory()
        req = ItemRequirement.objects.create(
            class_level_unlock=self.class_unlock, item_template=template
        )
        assert req.class_level_unlock_id == self.class_unlock.pk
        assert req.thread_crossing_threshold_id is None

    def test_item_requirement_with_thread_crossing_threshold(self) -> None:
        """New thread-crossing path — threshold set, class_level_unlock null."""
        template = ItemTemplateFactory()
        req = ItemRequirement.objects.create(
            thread_crossing_threshold=self.threshold, item_template=template
        )
        assert req.thread_crossing_threshold_id == self.threshold.pk
        assert req.class_level_unlock_id is None

    def test_neither_set_is_rejected(self) -> None:
        template = ItemTemplateFactory()
        with self.assertRaises(IntegrityError), transaction.atomic():
            ItemRequirement.objects.create(item_template=template)

    def test_both_set_is_rejected(self) -> None:
        template = ItemTemplateFactory()
        with self.assertRaises(IntegrityError), transaction.atomic():
            ItemRequirement.objects.create(
                class_level_unlock=self.class_unlock,
                thread_crossing_threshold=self.threshold,
                item_template=template,
            )

    def test_trait_requirement_with_thread_crossing_threshold(self) -> None:
        """A different requirement type also attaches to a threshold."""
        from world.traits.factories import TraitFactory

        trait = TraitFactory()
        req = TraitRequirement.objects.create(
            thread_crossing_threshold=self.threshold,
            trait=trait,
            minimum_value=10,
        )
        assert req.thread_crossing_threshold_id == self.threshold.pk
        assert req.class_level_unlock_id is None

    def test_related_name_no_collision(self) -> None:
        """The %(class)s_requirements auto-prefix yields distinct reverse accessors.

        ItemRequirement → itemrequirement_requirements on both ClassLevelUnlock
        and ThreadCrossingThreshold. Each target only sees requirements pointing
        at it — no cross-contamination.
        """
        template = ItemTemplateFactory()
        ItemRequirement.objects.create(class_level_unlock=self.class_unlock, item_template=template)
        ItemRequirement.objects.create(
            thread_crossing_threshold=self.threshold, item_template=template
        )

        # ClassLevelUnlock sees only its requirement
        class_reqs = self.class_unlock.itemrequirement_requirements.all()
        assert class_reqs.count() == 1
        assert class_reqs.first().class_level_unlock_id == self.class_unlock.pk

        # ThreadCrossingThreshold sees only its requirement
        threshold_reqs = self.threshold.itemrequirement_requirements.all()
        assert threshold_reqs.count() == 1
        assert threshold_reqs.first().thread_crossing_threshold_id == self.threshold.pk


class CheckRequirementsForThreadCrossingTests(TestCase):
    """Service-layer: check_requirements_for_thread_crossing."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.threshold = ThreadCrossingThreshold.objects.create(target_kind=TargetKind.GIFT, level=3)
        cls.template = ItemTemplateFactory()

    def setUp(self) -> None:
        self.sheet = CharacterSheetFactory()
        self.character = self.sheet.character
        self.sheet = CharacterSheetFactory(character=self.character)

    def test_fail_open_no_requirements(self) -> None:
        """No requirements authored on threshold → (True, [])."""
        met, messages = check_requirements_for_thread_crossing(self.character, self.threshold)
        assert met is True
        assert messages == []

    def test_unmet_requirement(self) -> None:
        ItemRequirement.objects.create(
            thread_crossing_threshold=self.threshold,
            item_template=self.template,
            quantity=1,
        )
        met, messages = check_requirements_for_thread_crossing(self.character, self.threshold)
        assert met is False
        assert len(messages) == 1
        assert "Need" in messages[0]

    def test_met_requirement(self) -> None:
        from world.items.factories import ItemInstanceFactory

        ItemRequirement.objects.create(
            thread_crossing_threshold=self.threshold,
            item_template=self.template,
            quantity=1,
        )
        ItemInstanceFactory(template=self.template, holder_character_sheet=self.sheet)
        met, messages = check_requirements_for_thread_crossing(self.character, self.threshold)
        assert met is True
        assert messages == []

    def test_durance_path_unaffected(self) -> None:
        """check_requirements_for_unlock against ClassLevelUnlock still works."""
        from world.classes.factories import CharacterClassFactory

        character_class = CharacterClassFactory()
        unlock = ClassLevelUnlock.objects.create(character_class=character_class, target_level=4)
        ItemRequirement.objects.create(
            class_level_unlock=unlock, item_template=self.template, quantity=1
        )
        met, messages = check_requirements_for_unlock(self.character, unlock)
        assert met is False
        assert len(messages) == 1
