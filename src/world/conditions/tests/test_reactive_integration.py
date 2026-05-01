"""Integration tests for reactive event emission in condition services.

All scenarios exercise the unified-dispatch model: ``emit_event(name, payload,
location)`` gathers triggers from the room and its contents, sorts by priority
desc, and dispatches on a single FlowStack. Self-targeting is expressed as a
filter (``SELF_FILTER``) rather than an old PERSONAL scope; bystander semantics
use ``NOT_SELF_FILTER``.

Tests verify:
- CONDITION_PRE_APPLY emitted with correct payload
- Cancellation of CONDITION_PRE_APPLY prevents application
- CONDITION_APPLIED emitted after successful application
- CONDITION_REMOVED emitted with correct instance_id (captured before delete)
- CONDITION_REMOVED not emitted when no instance to remove
- CONDITION_STAGE_CHANGED emitted only when stage actually changes
- CONDITION_STAGE_CHANGED NOT emitted when amount doesn't cross threshold
- bulk_apply_conditions per-item cancellation skips that item
- Bystander observer reacts to OTHER characters being afflicted
"""

from django.test import TestCase
from evennia.objects.models import ObjectDB

from evennia_extensions.factories import CharacterFactory
from flows.constants import EventName
from flows.consts import FlowActionChoices
from flows.events.payloads import (
    ConditionAppliedPayload,
    ConditionPreApplyPayload,
    ConditionRemovedPayload,
    ConditionStageChangedPayload,
)
from flows.factories import FlowDefinitionFactory, FlowStepDefinitionFactory
from world.conditions.factories import (
    ConditionInstanceFactory,
    ConditionStageFactory,
    ConditionTemplateFactory,
    ReactiveConditionFactory,
)
from world.conditions.models import ConditionInstance
from world.conditions.services import (
    advance_condition_severity,
    apply_condition,
    bulk_apply_conditions,
    remove_condition,
)
from world.conditions.types import BulkConditionApplication

# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


SELF_FILTER = {"path": "target", "op": "==", "value": "self"}
NOT_SELF_FILTER = {"path": "target", "op": "!=", "value": "self"}


def _create_room(key: str = "TestRoom") -> ObjectDB:
    return ObjectDB.objects.create(
        db_key=key,
        db_typeclass_path="typeclasses.rooms.Room",
    )


def _make_cancel_flow():
    """Return a FlowDefinition with a single CANCEL_EVENT step."""
    flow = FlowDefinitionFactory()
    FlowStepDefinitionFactory(
        flow=flow,
        parent_id=None,
        action=FlowActionChoices.CANCEL_EVENT,
        parameters={},
    )
    return flow


def _make_set_field_flow(field: str, value):
    """Return a FlowDefinition that sets payload.<field> to value."""
    flow = FlowDefinitionFactory()
    FlowStepDefinitionFactory(
        flow=flow,
        parent_id=None,
        action=FlowActionChoices.MODIFY_PAYLOAD,
        parameters={"field": field, "op": "set", "value": value},
    )
    return flow


def _target_in_room(room=None):
    """Return a Character in a room, for use as apply_condition target."""
    if room is None:
        room = _create_room()
    char = CharacterFactory()
    char.location = room
    return char


# ---------------------------------------------------------------------------
# CONDITION_PRE_APPLY / CONDITION_APPLIED emission
# ---------------------------------------------------------------------------


class ConditionPreApplyEmissionTest(TestCase):
    """apply_condition emits CONDITION_PRE_APPLY then CONDITION_APPLIED in order."""

    def test_pre_apply_emitted(self) -> None:
        target = _target_in_room()
        template = ConditionTemplateFactory()
        captured: list[tuple[str, object]] = []

        import world.conditions.services as svc_mod

        original = svc_mod.emit_event

        def capturing(name, payload, **kw):
            captured.append((name, payload))
            return original(name, payload, **kw)

        svc_mod.emit_event = capturing
        try:
            apply_condition(target, template)
        finally:
            svc_mod.emit_event = original

        names = [n for n, _ in captured]
        self.assertIn(EventName.CONDITION_PRE_APPLY, names)

    def test_pre_apply_payload_correct(self) -> None:
        target = _target_in_room()
        template = ConditionTemplateFactory()
        captured: list[ConditionPreApplyPayload] = []

        import world.conditions.services as svc_mod

        original = svc_mod.emit_event

        def capturing(name, payload, **kw):
            if name == EventName.CONDITION_PRE_APPLY:
                captured.append(payload)
            return original(name, payload, **kw)

        svc_mod.emit_event = capturing
        try:
            apply_condition(target, template)
        finally:
            svc_mod.emit_event = original

        self.assertEqual(len(captured), 1)
        p = captured[0]
        self.assertIsInstance(p, ConditionPreApplyPayload)
        self.assertIs(p.target, target)
        self.assertIs(p.template, template)

    def test_pre_then_applied_order(self) -> None:
        target = _target_in_room()
        template = ConditionTemplateFactory()
        order: list[str] = []

        import world.conditions.services as svc_mod

        original = svc_mod.emit_event

        def ordering(name, payload, **kw):
            if name in (EventName.CONDITION_PRE_APPLY, EventName.CONDITION_APPLIED):
                order.append(name)
            return original(name, payload, **kw)

        svc_mod.emit_event = ordering
        try:
            apply_condition(target, template)
        finally:
            svc_mod.emit_event = original

        self.assertIn(EventName.CONDITION_PRE_APPLY, order)
        self.assertIn(EventName.CONDITION_APPLIED, order)
        self.assertLess(
            order.index(EventName.CONDITION_PRE_APPLY),
            order.index(EventName.CONDITION_APPLIED),
        )

    def test_applied_payload_has_instance(self) -> None:
        target = _target_in_room()
        template = ConditionTemplateFactory()
        captured: list[ConditionAppliedPayload] = []

        import world.conditions.services as svc_mod

        original = svc_mod.emit_event

        def capturing(name, payload, **kw):
            if name == EventName.CONDITION_APPLIED:
                captured.append(payload)
            return original(name, payload, **kw)

        svc_mod.emit_event = capturing
        try:
            apply_condition(target, template)
        finally:
            svc_mod.emit_event = original

        self.assertEqual(len(captured), 1)
        p = captured[0]
        self.assertIsInstance(p, ConditionAppliedPayload)
        self.assertIsNotNone(p.instance)
        self.assertIs(p.target, target)


# ---------------------------------------------------------------------------
# PRE cancellation
# ---------------------------------------------------------------------------


class ConditionPreApplyCancellationTest(TestCase):
    """Cancelling CONDITION_PRE_APPLY prevents condition creation."""

    def test_cancel_returns_success_false(self) -> None:
        target = _target_in_room()
        template = ConditionTemplateFactory()
        cancel_flow = _make_cancel_flow()
        ReactiveConditionFactory(
            event_name=EventName.CONDITION_PRE_APPLY,
            filter_condition=SELF_FILTER,
            flow_definition=cancel_flow,
            target=target,
        )

        result = apply_condition(target, template)

        self.assertFalse(result.success)

    def test_cancel_creates_no_instance(self) -> None:
        target = _target_in_room()
        template = ConditionTemplateFactory()
        cancel_flow = _make_cancel_flow()
        ReactiveConditionFactory(
            event_name=EventName.CONDITION_PRE_APPLY,
            filter_condition=SELF_FILTER,
            flow_definition=cancel_flow,
            target=target,
        )
        before = ConditionInstance.objects.filter(target=target, condition=template).count()

        apply_condition(target, template)

        after = ConditionInstance.objects.filter(target=target, condition=template).count()
        self.assertEqual(before, after)

    def test_cancel_result_message(self) -> None:
        target = _target_in_room()
        template = ConditionTemplateFactory()
        cancel_flow = _make_cancel_flow()
        ReactiveConditionFactory(
            event_name=EventName.CONDITION_PRE_APPLY,
            filter_condition=SELF_FILTER,
            flow_definition=cancel_flow,
            target=target,
        )

        result = apply_condition(target, template)

        self.assertIn("cancel", result.message.lower())


# ---------------------------------------------------------------------------
# CONDITION_REMOVED emission
# ---------------------------------------------------------------------------


class ConditionRemovedEmissionTest(TestCase):
    """remove_condition emits CONDITION_REMOVED with correct instance_id."""

    def test_removed_emitted_after_delete(self) -> None:
        target = _target_in_room()
        template = ConditionTemplateFactory()
        apply_condition(target, template)
        instance = ConditionInstance.objects.get(target=target, condition=template)
        expected_pk = instance.pk
        captured: list[ConditionRemovedPayload] = []

        import world.conditions.services as svc_mod

        original = svc_mod.emit_event

        def capturing(name, payload, **kw):
            if name == EventName.CONDITION_REMOVED:
                captured.append(payload)
            return original(name, payload, **kw)

        svc_mod.emit_event = capturing
        try:
            remove_condition(target, template)
        finally:
            svc_mod.emit_event = original

        self.assertEqual(len(captured), 1)
        p = captured[0]
        self.assertIsInstance(p, ConditionRemovedPayload)
        self.assertEqual(p.instance_id, expected_pk)
        self.assertIs(p.template, template)

    def test_removed_not_emitted_when_no_instance(self) -> None:
        target = _target_in_room()
        template = ConditionTemplateFactory()
        # No condition applied — nothing to remove
        fired: list[bool] = []

        import world.conditions.services as svc_mod

        original = svc_mod.emit_event

        def capturing(name, payload, **kw):
            if name == EventName.CONDITION_REMOVED:
                fired.append(True)
            return original(name, payload, **kw)

        svc_mod.emit_event = capturing
        try:
            result = remove_condition(target, template)
        finally:
            svc_mod.emit_event = original

        self.assertFalse(result)
        self.assertEqual(fired, [])


# ---------------------------------------------------------------------------
# CONDITION_STAGE_CHANGED emission
# ---------------------------------------------------------------------------


class ConditionStageChangedEmissionTest(TestCase):
    """advance_condition_severity emits CONDITION_STAGE_CHANGED only on stage change."""

    def _make_instance_with_stage(self, threshold: int = 10):
        """Create a ConditionInstance with a severity-threshold stage."""
        template = ConditionTemplateFactory(has_progression=True)
        stage = ConditionStageFactory(
            condition=template,
            stage_order=1,
            severity_threshold=threshold,
        )
        target = _target_in_room()
        instance = ConditionInstanceFactory(
            target=target,
            condition=template,
            current_stage=None,
            severity=0,
        )
        return instance, stage

    def test_stage_changed_emitted_when_threshold_crossed(self) -> None:
        instance, _stage = self._make_instance_with_stage(threshold=10)
        captured: list[ConditionStageChangedPayload] = []

        import world.conditions.services as svc_mod

        original = svc_mod.emit_event

        def capturing(name, payload, **kw):
            if name == EventName.CONDITION_STAGE_CHANGED:
                captured.append(payload)
            return original(name, payload, **kw)

        svc_mod.emit_event = capturing
        try:
            result = advance_condition_severity(instance, 15)  # crosses threshold=10
        finally:
            svc_mod.emit_event = original

        self.assertTrue(result.stage_changed)
        self.assertEqual(len(captured), 1)
        p = captured[0]
        self.assertIsInstance(p, ConditionStageChangedPayload)
        self.assertIs(p.instance, instance)

    def test_stage_changed_not_emitted_below_threshold(self) -> None:
        instance, _stage = self._make_instance_with_stage(threshold=10)
        fired: list[bool] = []

        import world.conditions.services as svc_mod

        original = svc_mod.emit_event

        def capturing(name, payload, **kw):
            if name == EventName.CONDITION_STAGE_CHANGED:
                fired.append(True)
            return original(name, payload, **kw)

        svc_mod.emit_event = capturing
        try:
            result = advance_condition_severity(instance, 5)  # below threshold=10
        finally:
            svc_mod.emit_event = original

        self.assertFalse(result.stage_changed)
        self.assertEqual(fired, [])

    def test_stage_changed_payload_has_old_and_new_stage(self) -> None:
        instance, stage = self._make_instance_with_stage(threshold=10)
        old_stage = instance.current_stage  # None before
        captured: list[ConditionStageChangedPayload] = []

        import world.conditions.services as svc_mod

        original = svc_mod.emit_event

        def capturing(name, payload, **kw):
            if name == EventName.CONDITION_STAGE_CHANGED:
                captured.append(payload)
            return original(name, payload, **kw)

        svc_mod.emit_event = capturing
        try:
            advance_condition_severity(instance, 15)
        finally:
            svc_mod.emit_event = original

        p = captured[0]
        self.assertEqual(p.old_stage, old_stage)
        self.assertEqual(p.new_stage, stage)


# ---------------------------------------------------------------------------
# bulk_apply_conditions cancellation
# ---------------------------------------------------------------------------


class BulkApplyConditionsCancellationTest(TestCase):
    """bulk_apply_conditions: PRE cancellation skips specific (target, template) pair."""

    def test_cancelled_pair_not_applied(self) -> None:
        target1 = _target_in_room()
        target2 = _target_in_room()
        template = ConditionTemplateFactory()

        cancel_flow = _make_cancel_flow()
        ReactiveConditionFactory(
            event_name=EventName.CONDITION_PRE_APPLY,
            filter_condition=SELF_FILTER,
            flow_definition=cancel_flow,
            target=target1,
        )

        bulk_apply_conditions(
            [
                BulkConditionApplication(target=target1, template=template),
                BulkConditionApplication(target=target2, template=template),
            ],
        )

        # target1 cancelled, target2 should succeed
        self.assertFalse(
            ConditionInstance.objects.filter(target=target1, condition=template).exists()
        )
        self.assertTrue(
            ConditionInstance.objects.filter(target=target2, condition=template).exists()
        )


# ---------------------------------------------------------------------------
# Bystander reaction — unified dispatch lets observers react to OTHER chars
# ---------------------------------------------------------------------------


class BystanderConditionReactionTest(TestCase):
    """A bystander in the same room reacts when OTHER characters are afflicted.

    Under unified dispatch, CONDITION_PRE_APPLY is emitted at the target's
    room. Triggers owned by the target fire (self-filter), AND triggers owned
    by other room-mates can fire (no target filter, or ``target != self``).

    This replaces the old ROOM-scope tests (removed with the scope field) and
    exercises the filter DSL's target-discrimination semantics.
    """

    def setUp(self):
        self.room = _create_room("BystanderRoom")
        self.watcher = _target_in_room(self.room)
        self.subject = _target_in_room(self.room)

        # Watcher's bystander trigger: MODIFY_PAYLOAD on the mutable pre-apply
        # payload — set the `source` field to a sentinel when someone ELSE is
        # the target. `source` starts as None in apply_condition.
        mark_flow = _make_set_field_flow("source", "BYSTANDER_SAW")
        ReactiveConditionFactory(
            event_name=EventName.CONDITION_PRE_APPLY,
            filter_condition=NOT_SELF_FILTER,
            flow_definition=mark_flow,
            target=self.watcher,
        )

    def test_bystander_reacts_when_subject_afflicted(self):
        """Condition applied to subject → watcher's bystander trigger fires."""
        template = ConditionTemplateFactory()
        captured: list[ConditionPreApplyPayload] = []

        import world.conditions.services as svc_mod

        original = svc_mod.emit_event

        def capturing(name, payload, **kw):
            if name == EventName.CONDITION_PRE_APPLY:
                captured.append(payload)
            return original(name, payload, **kw)

        svc_mod.emit_event = capturing
        try:
            apply_condition(self.subject, template)
        finally:
            svc_mod.emit_event = original

        # Bystander trigger ran on the pre-apply payload and wrote the sentinel
        self.assertEqual(len(captured), 1)
        self.assertEqual(captured[0].source, "BYSTANDER_SAW")

    def test_bystander_does_not_react_to_own_affliction(self):
        """Condition applied to watcher → watcher's NOT_SELF filter rejects."""
        template = ConditionTemplateFactory()
        captured: list[ConditionPreApplyPayload] = []

        import world.conditions.services as svc_mod

        original = svc_mod.emit_event

        def capturing(name, payload, **kw):
            if name == EventName.CONDITION_PRE_APPLY:
                captured.append(payload)
            return original(name, payload, **kw)

        svc_mod.emit_event = capturing
        try:
            apply_condition(self.watcher, template)
        finally:
            svc_mod.emit_event = original

        # Watcher IS the target — NOT_SELF_FILTER rejects, source stays None
        self.assertEqual(len(captured), 1)
        self.assertIsNone(captured[0].source)
