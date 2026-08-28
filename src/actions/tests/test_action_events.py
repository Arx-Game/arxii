"""Journey tests for generic action intent/result events (#3418).

The seam under test is ``Action.run()`` — the single telnet+web chokepoint.
Interception content is REAL authored rows (TriggerDefinition / Trigger /
FlowDefinition / FlowStepDefinition); the concrete Action is a test-local
probe so the tests exercise the run() lifecycle without inventory fixtures,
plus one real-registry action (GetAction) proving end-to-end.
"""

from dataclasses import dataclass, field
from typing import Any

from django.test import TestCase
from evennia.objects.models import ObjectDB

from actions.base import Action
from actions.definitions.movement import GetAction
from actions.prerequisites import Prerequisite
from actions.types import ActionContext, ActionResult, TargetType
from evennia_extensions.factories import CharacterFactory, ObjectDBFactory
from flows.constants import EventName
from flows.consts import FlowActionChoices
from flows.factories import (
    FlowDefinitionFactory,
    FlowStepDefinitionFactory,
    TriggerDefinitionFactory,
    TriggerFactory,
)
from flows.models.flows import FlowDefinition


@dataclass
class _ProbeAction(Action):
    """Minimal registry-shaped action; records whether/what it executed."""

    key: str = "get"
    name: str = "Probe"
    icon: str = "hand"
    category: str = "test"
    target_type: TargetType = TargetType.SINGLE
    executed: bool = False
    seen_kwargs: dict[str, Any] = field(default_factory=dict)

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        self.executed = True
        self.seen_kwargs = dict(kwargs)
        return ActionResult(success=True, message="done")


class _AlwaysFails(Prerequisite):
    def is_met(self, actor, target=None, context=None):
        return False, "You are simply not ready."


@dataclass
class _GatedProbeAction(_ProbeAction):
    def get_prerequisites(self) -> list[Prerequisite]:
        return [_AlwaysFails()]


def _cancel_flow(message: str | None = None) -> FlowDefinition:
    """An authored flow that (optionally sets cancel_message and) cancels."""
    flow = FlowDefinitionFactory()
    if message is not None:
        root = FlowStepDefinitionFactory(
            flow=flow,
            parent_id=None,
            action=FlowActionChoices.MODIFY_PAYLOAD,
            parameters={"field": "cancel_message", "op": "set", "value": message},
        )
        FlowStepDefinitionFactory(
            flow=flow,
            parent_id=root.pk,
            action=FlowActionChoices.CANCEL_EVENT,
            parameters={},
        )
    else:
        FlowStepDefinitionFactory(
            flow=flow,
            parent_id=None,
            action=FlowActionChoices.CANCEL_EVENT,
            parameters={},
        )
    return flow


def _noop_flow() -> FlowDefinition:
    """An authored flow whose only observable is the trigger fire-count.

    A step-less ``FlowDefinition`` is a genuine no-op: ``FlowExecution``'s
    entry step resolves to ``None`` (no ``FlowStepDefinition`` rows), so
    ``FlowStack.execute_flow`` completes its while-loop immediately without
    executing anything, cancelling anything, or raising. ``emit_event``
    still calls ``handler.note_fired(trigger.pk)`` right after the (no-op)
    flow execution, so the trigger's fire-count is the only observable
    here. (``SET_CONTEXT_VALUE`` was tried first but requires
    ``variable_name`` to already be bound in the flow's variable mapping —
    it is not a bare no-op.)
    """
    return FlowDefinitionFactory()


def _room(key: str) -> ObjectDB:
    return ObjectDBFactory(db_key=key, db_typeclass_path="typeclasses.rooms.Room")


class ActionIntentEventTests(TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.room = _room("Shrine")
        self.char = CharacterFactory()
        self.char.location = self.room

    def test_intent_cancel_blocks_with_authored_message(self) -> None:
        trig_def = TriggerDefinitionFactory(
            event_name=EventName.ACTION_INTENT,
            flow_definition=_cancel_flow("The shrine's wards flare."),
        )
        TriggerFactory(trigger_definition=trig_def, obj=self.room)
        probe = _ProbeAction()

        result = probe.run(self.char)

        self.assertFalse(result.success)
        self.assertEqual(result.message, "The shrine's wards flare.")
        self.assertFalse(probe.executed)

    def test_intent_cancel_default_message(self) -> None:
        trig_def = TriggerDefinitionFactory(
            event_name=EventName.ACTION_INTENT, flow_definition=_cancel_flow()
        )
        TriggerFactory(trigger_definition=trig_def, obj=self.room)

        result = _ProbeAction().run(self.char)

        self.assertFalse(result.success)
        self.assertEqual(result.message, "Something prevents you.")

    def test_intent_fires_before_prerequisite_gate(self) -> None:
        """Cancel wins over a failing prerequisite: intent is 'wants to', not 'can'."""
        trig_def = TriggerDefinitionFactory(
            event_name=EventName.ACTION_INTENT,
            flow_definition=_cancel_flow("Refused at the door."),
        )
        TriggerFactory(trigger_definition=trig_def, obj=self.room)

        result = _GatedProbeAction().run(self.char)

        self.assertEqual(result.message, "Refused at the door.")

    def test_intent_cancel_skips_unaffordable_ap_cost(self) -> None:
        """A cancelled intent returns before the AP charge is ever consulted."""
        trig_def = TriggerDefinitionFactory(
            event_name=EventName.ACTION_INTENT,
            flow_definition=_cancel_flow("Halt."),
        )
        TriggerFactory(trigger_definition=trig_def, obj=self.room)
        probe = _ProbeAction(ap_cost=10_000_000)

        result = probe.run(self.char)

        self.assertEqual(result.message, "Halt.")  # not the AP-failure message

    def test_modify_payload_redirects_target(self) -> None:
        decoy = ObjectDBFactory(db_key="decoy")
        real = ObjectDBFactory(db_key="real")
        flow = FlowDefinitionFactory()
        FlowStepDefinitionFactory(
            flow=flow,
            parent_id=None,
            action=FlowActionChoices.MODIFY_PAYLOAD,
            parameters={"field": "target", "op": "set", "value": decoy.pk},
        )
        trig_def = TriggerDefinitionFactory(
            event_name=EventName.ACTION_INTENT, flow_definition=flow
        )
        TriggerFactory(trigger_definition=trig_def, obj=self.room)
        probe = _ProbeAction()

        result = probe.run(self.char, target=real)

        self.assertTrue(result.success)
        self.assertEqual(probe.seen_kwargs["target"], decoy.pk)

    def test_action_key_filter_discriminates_verbs(self) -> None:
        get_def = TriggerDefinitionFactory(
            event_name=EventName.ACTION_INTENT,
            flow_definition=_noop_flow(),
            base_filter_condition={"path": "action_key", "op": "==", "value": "get"},
        )
        drop_def = TriggerDefinitionFactory(
            event_name=EventName.ACTION_INTENT,
            flow_definition=_noop_flow(),
            base_filter_condition={"path": "action_key", "op": "==", "value": "drop"},
        )
        get_trig = TriggerFactory(trigger_definition=get_def, obj=self.room)
        drop_trig = TriggerFactory(trigger_definition=drop_def, obj=self.room)

        _ProbeAction().run(self.char)  # key == "get"

        handler = self.room.trigger_handler
        self.assertEqual(handler.fire_count(get_trig.pk), 1)
        self.assertEqual(handler.fire_count(drop_trig.pk), 0)

    def test_account_authorized_action_emits_nothing(self) -> None:
        trig_def = TriggerDefinitionFactory(
            event_name=EventName.ACTION_INTENT, flow_definition=_cancel_flow("nope")
        )
        trig = TriggerFactory(trigger_definition=trig_def, obj=self.room)

        result = _ProbeAction().run(None)

        self.assertTrue(result.success)
        self.assertEqual(self.room.trigger_handler.fire_count(trig.pk), 0)

    def test_real_registry_action_intercepted_end_to_end(self) -> None:
        """GetAction through run(): the cancel lands before any inventory logic."""
        trig_def = TriggerDefinitionFactory(
            event_name=EventName.ACTION_INTENT,
            flow_definition=_cancel_flow("The offering is not yours to take."),
        )
        TriggerFactory(trigger_definition=trig_def, obj=self.room)
        bauble = ObjectDBFactory(db_key="offering bowl")

        result = GetAction().run(self.char, target=bauble)

        self.assertFalse(result.success)
        self.assertEqual(result.message, "The offering is not yours to take.")


class ActionResultEventTests(TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.room = _room("Shrine")
        self.char = CharacterFactory()
        self.char.location = self.room
        ok_def = TriggerDefinitionFactory(
            event_name=EventName.ACTION_RESULT,
            flow_definition=_noop_flow(),
            base_filter_condition={"path": "success", "op": "==", "value": True},
        )
        fail_def = TriggerDefinitionFactory(
            event_name=EventName.ACTION_RESULT,
            flow_definition=_noop_flow(),
            base_filter_condition={"path": "success", "op": "==", "value": False},
        )
        self.ok_trig = TriggerFactory(trigger_definition=ok_def, obj=self.room)
        self.fail_trig = TriggerFactory(trigger_definition=fail_def, obj=self.room)

    def _counts(self) -> tuple[int, int]:
        handler = self.room.trigger_handler
        return handler.fire_count(self.ok_trig.pk), handler.fire_count(self.fail_trig.pk)

    def test_result_fires_on_success(self) -> None:
        _ProbeAction().run(self.char)
        self.assertEqual(self._counts(), (1, 0))

    def test_result_fires_on_prerequisite_failure(self) -> None:
        result = _GatedProbeAction().run(self.char)
        self.assertFalse(result.success)
        self.assertEqual(self._counts(), (0, 1))

    def test_no_result_after_intent_cancel(self) -> None:
        cancel_def = TriggerDefinitionFactory(
            event_name=EventName.ACTION_INTENT, flow_definition=_cancel_flow("no")
        )
        TriggerFactory(trigger_definition=cancel_def, obj=self.room)

        _ProbeAction().run(self.char)

        self.assertEqual(self._counts(), (0, 0))

    def test_result_fires_on_cost_failure(self) -> None:
        """An unaffordable AP cost fails before execute(); ACTION_RESULT still fires.

        ``self.char`` (a bare ``CharacterFactory``) has no ``character_sheet``, so
        ``ActionPointPool.get_or_create_for_character`` returns ``None`` and
        ``_charge_costs`` returns the AP-failure ``ActionResult`` without ever
        reaching ``execute()`` — no intent-cancel trigger is involved here.
        """
        probe = _ProbeAction(ap_cost=10_000_000)

        result = probe.run(self.char)

        self.assertFalse(result.success)
        self.assertFalse(probe.executed)
        self.assertEqual(self._counts(), (0, 1))

    def test_none_result_message_coerced_to_empty_string(self) -> None:
        """GetAction returns ActionResult(success=True) with message=None on
        success; a bare success=True filter still fires without a TypeError
        from a None message reaching comparison operators.

        The additional ``message contains ""`` trigger below is the load-bearing
        assertion: ``"" in None`` raises ``TypeError`` while ``"" in "<any str>"``
        is always ``True``, so this trigger only fires (without the whole
        ``emit_event`` call blowing up with an uncaught ``TypeError``) if
        ``_emit_result`` actually coerced ``result.message`` to ``""`` before
        building the payload.
        """
        message_probe_def = TriggerDefinitionFactory(
            event_name=EventName.ACTION_RESULT,
            flow_definition=_noop_flow(),
            base_filter_condition={
                "and": [
                    {"path": "success", "op": "==", "value": True},
                    {"path": "message", "op": "contains", "value": ""},
                ]
            },
        )
        message_probe_trig = TriggerFactory(trigger_definition=message_probe_def, obj=self.room)

        @dataclass
        class _NoMessageProbe(_ProbeAction):
            def execute(self, actor, context=None, **kwargs):
                return ActionResult(success=True)

        _NoMessageProbe().run(self.char)
        self.assertEqual(self._counts(), (1, 0))
        self.assertEqual(self.room.trigger_handler.fire_count(message_probe_trig.pk), 1)
