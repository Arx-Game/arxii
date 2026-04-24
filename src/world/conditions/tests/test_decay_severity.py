"""Tests for decay_condition_severity (Scope 6 §5.3).

Inverse of advance_condition_severity — walks stage down when severity
crosses thresholds going down, sets resolved_at when severity reaches 0,
and emits CONDITION_STAGE_CHANGED only on actual stage change.
"""

from django.test import TestCase
from evennia.objects.models import ObjectDB

from evennia_extensions.factories import CharacterFactory
from flows.constants import EventName
from flows.events.payloads import ConditionStageChangedPayload
from world.conditions.factories import (
    ConditionInstanceFactory,
    ConditionStageFactory,
    ConditionTemplateFactory,
)
from world.conditions.services import (
    advance_condition_severity,
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


class DecayConditionSeverityTests(TestCase):
    def test_decay_within_stage_keeps_stage_unchanged(self):
        template = ConditionTemplateFactory()
        stage1 = ConditionStageFactory(condition=template, severity_threshold=1)
        inst = ConditionInstanceFactory(
            condition=template,
            current_stage=stage1,
            severity=3,
        )
        result = decay_condition_severity(inst, amount=1)
        self.assertEqual(result.previous_stage, stage1)
        self.assertEqual(result.new_stage, stage1)
        self.assertEqual(result.new_severity, 2)
        self.assertFalse(result.resolved)

    def test_decay_across_stage_boundary_downward_emits_event(self):
        template = ConditionTemplateFactory()
        stage1 = ConditionStageFactory(condition=template, severity_threshold=1)
        stage2 = ConditionStageFactory(condition=template, severity_threshold=6)
        target = _target_with_location()
        inst = ConditionInstanceFactory(
            target=target,
            condition=template,
            current_stage=stage2,
            severity=6,
        )

        captured: list[ConditionStageChangedPayload] = []

        import world.conditions.services as svc_mod

        original = svc_mod.emit_event

        def capturing(name, payload, **kw):
            if name == EventName.CONDITION_STAGE_CHANGED:
                captured.append(payload)
            return original(name, payload, **kw)

        svc_mod.emit_event = capturing
        try:
            result = decay_condition_severity(inst, amount=1)
        finally:
            svc_mod.emit_event = original

        self.assertEqual(result.previous_stage, stage2)
        self.assertEqual(result.new_stage, stage1)
        self.assertEqual(result.new_severity, 5)
        self.assertFalse(result.resolved)

        self.assertEqual(len(captured), 1)
        payload = captured[0]
        self.assertIsInstance(payload, ConditionStageChangedPayload)
        self.assertEqual(payload.old_stage, stage2)
        self.assertEqual(payload.new_stage, stage1)

    def test_decay_to_zero_sets_resolved_at_and_emits_stage_event(self):
        template = ConditionTemplateFactory()
        stage1 = ConditionStageFactory(condition=template, severity_threshold=1)
        target = _target_with_location()
        inst = ConditionInstanceFactory(
            target=target,
            condition=template,
            current_stage=stage1,
            severity=1,
        )

        captured: list[ConditionStageChangedPayload] = []

        import world.conditions.services as svc_mod

        original = svc_mod.emit_event

        def capturing(name, payload, **kw):
            if name == EventName.CONDITION_STAGE_CHANGED:
                captured.append(payload)
            return original(name, payload, **kw)

        svc_mod.emit_event = capturing
        try:
            result = decay_condition_severity(inst, amount=1)
        finally:
            svc_mod.emit_event = original

        self.assertEqual(result.previous_stage, stage1)
        self.assertIsNone(result.new_stage)
        self.assertEqual(result.new_severity, 0)
        self.assertTrue(result.resolved)

        inst.refresh_from_db()
        self.assertIsNotNone(inst.resolved_at)
        self.assertIsNone(inst.current_stage)

        self.assertEqual(len(captured), 1)
        payload = captured[0]
        self.assertEqual(payload.old_stage, stage1)
        self.assertIsNone(payload.new_stage)

    def test_decay_amount_exceeds_severity_clamps_at_zero(self):
        template = ConditionTemplateFactory()
        stage1 = ConditionStageFactory(condition=template, severity_threshold=1)
        inst = ConditionInstanceFactory(
            condition=template,
            current_stage=stage1,
            severity=2,
        )
        result = decay_condition_severity(inst, amount=10)
        self.assertEqual(result.new_severity, 0)
        self.assertTrue(result.resolved)
        inst.refresh_from_db()
        self.assertEqual(inst.severity, 0)

    def test_symmetry_advance_then_decay_returns_to_start(self):
        template = ConditionTemplateFactory()
        stage1 = ConditionStageFactory(condition=template, severity_threshold=1)
        stage2 = ConditionStageFactory(condition=template, severity_threshold=6)
        target = _target_with_location()
        inst = ConditionInstanceFactory(
            target=target,
            condition=template,
            current_stage=stage1,
            severity=3,
        )

        advance_result = advance_condition_severity(inst, amount=4)
        self.assertEqual(advance_result.new_stage, stage2)
        self.assertEqual(inst.severity, 7)

        decay_result = decay_condition_severity(inst, amount=4)
        self.assertEqual(decay_result.new_severity, 3)
        self.assertEqual(decay_result.new_stage, stage1)

        inst.refresh_from_db()
        self.assertEqual(inst.severity, 3)
        self.assertEqual(inst.current_stage, stage1)

    def test_advance_after_decay_to_zero_clears_resolved_at(self):
        """Reviving a resolved instance via advance must clear resolved_at."""
        template = ConditionTemplateFactory()
        stage1 = ConditionStageFactory(condition=template, severity_threshold=1)
        inst = ConditionInstanceFactory(
            condition=template,
            current_stage=stage1,
            severity=1,
        )

        # Decay to zero → resolved_at should be set
        decay_result = decay_condition_severity(inst, amount=1)
        self.assertTrue(decay_result.resolved)
        self.assertEqual(inst.severity, 0)
        inst.refresh_from_db()
        self.assertIsNotNone(inst.resolved_at)

        # Advance by 1 → resolved_at must be cleared, severity must be > 0
        advance_result = advance_condition_severity(inst, amount=1)
        self.assertEqual(advance_result.total_severity, 1)
        inst.refresh_from_db()
        self.assertIsNone(inst.resolved_at)
        self.assertEqual(inst.severity, 1)
