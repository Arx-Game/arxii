"""Tests for apply_stage_entry_aftermath (Scope 6 §5.6).

Stage-entry aftermath hook: when a condition ascends to a new stage,
apply that stage's on_entry_conditions to the same target.
"""

from django.test import TestCase
from evennia.objects.models import ObjectDB

from evennia_extensions.factories import CharacterFactory
from flows.events.payloads import ConditionStageChangedPayload
from world.conditions.factories import (
    ConditionInstanceFactory,
    ConditionStageFactory,
    ConditionTemplateFactory,
)
from world.conditions.models import ConditionInstance, ConditionStageOnEntry
from world.conditions.services import (
    advance_condition_severity,
    apply_stage_entry_aftermath,
    decay_condition_severity,
)


def _create_room(key: str = "TestRoom") -> ObjectDB:
    return ObjectDB.objects.create(
        db_key=key,
        db_typeclass_path="typeclasses.rooms.Room",
    )


def _target_with_location():
    """Return a Character in a room, for use as condition target.

    emit_event is guarded on getattr(target, "location", None) — giving the
    target a real location ensures CONDITION_STAGE_CHANGED events fire.
    """
    room = _create_room()
    char = CharacterFactory()
    char.location = room
    return char


class ApplyStageEntryAftermathTests(TestCase):
    def test_ascending_applies_on_entry_aftermath(self):
        """Ascending to a stage with on_entry_conditions creates aftermath instances."""
        template = ConditionTemplateFactory(has_progression=True)
        stage1 = ConditionStageFactory(condition=template, stage_order=1, severity_threshold=1)
        stage2 = ConditionStageFactory(condition=template, stage_order=2, severity_threshold=5)

        aftermath_template = ConditionTemplateFactory()
        ConditionStageOnEntry.objects.create(
            stage=stage2,
            condition=aftermath_template,
            severity=1,
        )

        target = _target_with_location()
        inst = ConditionInstanceFactory(
            target=target,
            condition=template,
            current_stage=stage1,
            severity=3,
        )

        payload = ConditionStageChangedPayload(
            target=target,
            instance=inst,
            old_stage=stage1,
            new_stage=stage2,
        )
        apply_stage_entry_aftermath(payload)

        aftermath = ConditionInstance.objects.filter(
            target=target,
            condition=aftermath_template,
            resolved_at__isnull=True,
        ).first()
        self.assertIsNotNone(aftermath)
        self.assertEqual(aftermath.severity, 1)

    def test_descending_does_not_auto_remove_existing_aftermath(self):
        """Aftermath instances are NOT removed when the stage descends.

        Treatment is the cleanup path, not auto-removal on decay.
        This also exercises the inline wiring in advance_condition_severity.
        """
        template = ConditionTemplateFactory(has_progression=True)
        stage1 = ConditionStageFactory(condition=template, stage_order=1, severity_threshold=1)
        _stage2 = ConditionStageFactory(condition=template, stage_order=2, severity_threshold=3)
        stage3 = ConditionStageFactory(condition=template, stage_order=3, severity_threshold=6)

        aftermath_template = ConditionTemplateFactory()
        ConditionStageOnEntry.objects.create(
            stage=stage3,
            condition=aftermath_template,
            severity=1,
        )

        target = _target_with_location()
        inst = ConditionInstanceFactory(
            target=target,
            condition=template,
            current_stage=stage1,
            severity=3,
        )

        # Advance to stage3 via inline wiring (not direct hook call)
        advance_condition_severity(inst, amount=4)
        inst.refresh_from_db()
        self.assertEqual(inst.current_stage, stage3)

        # Aftermath should have been applied by inline wiring
        aftermath = ConditionInstance.objects.filter(
            target=target,
            condition=aftermath_template,
            resolved_at__isnull=True,
        ).first()
        self.assertIsNotNone(aftermath, "Inline wiring must have applied aftermath on ascent")

        # Decay back to stage1
        decay_condition_severity(inst, amount=5)
        inst.refresh_from_db()
        self.assertEqual(inst.current_stage, stage1)

        # Aftermath should still be present — no auto-removal on descent
        aftermath.refresh_from_db()
        self.assertIsNone(aftermath.resolved_at, "Aftermath must not be auto-removed on descent")

    def test_sideways_is_noop(self):
        """Payload with old_stage == new_stage does not create aftermath instances."""
        template = ConditionTemplateFactory(has_progression=True)
        stage2 = ConditionStageFactory(condition=template, stage_order=2, severity_threshold=5)

        aftermath_template = ConditionTemplateFactory()
        ConditionStageOnEntry.objects.create(
            stage=stage2,
            condition=aftermath_template,
            severity=1,
        )

        target = _target_with_location()
        inst = ConditionInstanceFactory(
            target=target,
            condition=template,
            current_stage=stage2,
            severity=5,
        )

        # old_stage == new_stage → sideways → no-op
        payload = ConditionStageChangedPayload(
            target=target,
            instance=inst,
            old_stage=stage2,
            new_stage=stage2,
        )
        apply_stage_entry_aftermath(payload)

        count = ConditionInstance.objects.filter(
            target=target,
            condition=aftermath_template,
            resolved_at__isnull=True,
        ).count()
        self.assertEqual(count, 0)

    def test_idempotent_same_stage_does_not_stack_beyond_assoc_severity(self):
        """Calling hook twice does not raise aftermath beyond assoc severity=1."""
        template = ConditionTemplateFactory(has_progression=True)
        stage1 = ConditionStageFactory(condition=template, stage_order=1, severity_threshold=1)
        stage3 = ConditionStageFactory(condition=template, stage_order=3, severity_threshold=6)

        aftermath_template = ConditionTemplateFactory()
        ConditionStageOnEntry.objects.create(
            stage=stage3,
            condition=aftermath_template,
            severity=1,
        )

        target = _target_with_location()
        inst = ConditionInstanceFactory(
            target=target,
            condition=template,
            current_stage=stage1,
            severity=6,
        )

        payload = ConditionStageChangedPayload(
            target=target,
            instance=inst,
            old_stage=stage1,
            new_stage=stage3,
        )
        apply_stage_entry_aftermath(payload)
        apply_stage_entry_aftermath(payload)  # second call — idempotent

        aftermaths = ConditionInstance.objects.filter(
            target=target,
            condition=aftermath_template,
            resolved_at__isnull=True,
        )
        self.assertEqual(aftermaths.count(), 1)
        self.assertEqual(aftermaths.first().severity, 1)

    def test_multi_condition_stage_applies_all_aftermaths_in_one_fire(self):
        """A stage with two on_entry_conditions applies both in a single hook call."""
        template = ConditionTemplateFactory(has_progression=True)
        stage1 = ConditionStageFactory(condition=template, stage_order=1, severity_threshold=1)
        stage3 = ConditionStageFactory(condition=template, stage_order=3, severity_threshold=6)

        aftermath_a = ConditionTemplateFactory()
        aftermath_b = ConditionTemplateFactory()
        ConditionStageOnEntry.objects.create(stage=stage3, condition=aftermath_a, severity=1)
        ConditionStageOnEntry.objects.create(stage=stage3, condition=aftermath_b, severity=2)

        target = _target_with_location()
        inst = ConditionInstanceFactory(
            target=target,
            condition=template,
            current_stage=stage1,
            severity=6,
        )

        payload = ConditionStageChangedPayload(
            target=target,
            instance=inst,
            old_stage=stage1,
            new_stage=stage3,
        )
        apply_stage_entry_aftermath(payload)

        a_inst = ConditionInstance.objects.filter(
            target=target, condition=aftermath_a, resolved_at__isnull=True
        ).first()
        b_inst = ConditionInstance.objects.filter(
            target=target, condition=aftermath_b, resolved_at__isnull=True
        ).first()
        self.assertIsNotNone(a_inst, "aftermath_a should be applied")
        self.assertIsNotNone(b_inst, "aftermath_b should be applied")
        self.assertEqual(a_inst.severity, 1)
        self.assertEqual(b_inst.severity, 2)
