"""Tests for TreatmentAttempt's partial unique constraint (Slice A §4.10)."""

from __future__ import annotations

from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone as tz


class TreatmentAttemptUniqueConstraintTests(TestCase):
    """Constraint fires for once_per_scene_per_helper=True treatments only."""

    @classmethod
    def setUpTestData(cls) -> None:
        from evennia_extensions.factories import CharacterFactory
        from world.conditions.factories import TreatmentTemplateFactory
        from world.scenes.factories import SceneFactory
        from world.traits.factories import CheckOutcomeFactory

        cls.helper = CharacterFactory(db_key="TreatmentTestHelper")
        cls.target = CharacterFactory(db_key="TreatmentTestTarget")
        cls.scene = SceneFactory()
        cls.outcome = CheckOutcomeFactory()
        cls.treatment_unique = TreatmentTemplateFactory(once_per_scene_per_helper=True)
        cls.treatment_repeat = TreatmentTemplateFactory(once_per_scene_per_helper=False)

    def test_unique_treatment_blocks_duplicate(self) -> None:
        from world.conditions.models import TreatmentAttempt

        kwargs = {
            "helper": self.helper,
            "target": self.target,
            "scene": self.scene,
            "treatment": self.treatment_unique,
            "outcome": self.outcome,
            "once_per_scene_guard": True,
            "created_at": tz.now(),
        }
        TreatmentAttempt.objects.create(**kwargs)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                TreatmentAttempt.objects.create(**kwargs)

    def test_repeat_treatment_permits_duplicate(self) -> None:
        from world.conditions.models import TreatmentAttempt

        kwargs = {
            "helper": self.helper,
            "target": self.target,
            "scene": self.scene,
            "treatment": self.treatment_repeat,
            "outcome": self.outcome,
            "once_per_scene_guard": False,
            "created_at": tz.now(),
        }
        # Two attempts of a repeat-allowed treatment — should not raise.
        TreatmentAttempt.objects.create(**kwargs)
        TreatmentAttempt.objects.create(**kwargs)

    def test_different_treatments_same_helper_target_scene_allowed(self) -> None:
        from world.conditions.models import TreatmentAttempt

        TreatmentAttempt.objects.create(
            helper=self.helper,
            target=self.target,
            scene=self.scene,
            treatment=self.treatment_unique,
            outcome=self.outcome,
            once_per_scene_guard=True,
            created_at=tz.now(),
        )
        # Different treatment on the same helper/target/scene — allowed.
        TreatmentAttempt.objects.create(
            helper=self.helper,
            target=self.target,
            scene=self.scene,
            treatment=self.treatment_repeat,
            outcome=self.outcome,
            once_per_scene_guard=False,
            created_at=tz.now(),
        )
