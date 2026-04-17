"""Populate-once trigger handler for typeclass owners.

Replaces the old flows.trigger_registry.TriggerRegistry. Installed as a
cached_property on Character, Room, Object. Populates from Trigger rows
on first access, stays synced via explicit sync hooks.
"""

from collections import defaultdict
import logging
from typing import TYPE_CHECKING, Any

from flows.filters.errors import FilterPathError
from flows.filters.evaluator import evaluate_filter

if TYPE_CHECKING:
    from flows.models.triggers import Trigger

logger = logging.getLogger(__name__)


class DispatchResult:
    def __init__(self) -> None:
        self.cancelled = False
        self.fired: list[int] = []  # Trigger pks that fired


class TriggerHandler:
    """Active trigger rows for a typeclass owner, indexed by event name."""

    def __init__(self, owner: Any) -> None:
        self.owner = owner
        self._by_event: dict[str, list[Trigger]] = defaultdict(list)
        self._populated = False

    def _populate(self) -> None:
        # Deferred import: this module is imported by typeclasses during
        # Evennia startup, before the flows app registry is ready.
        from flows.models.triggers import Trigger  # noqa: PLC0415

        qs = Trigger.objects.filter(obj=self.owner).select_related(
            "trigger_definition__event",
            "trigger_definition__flow_definition",
            "source_condition__condition",
            "source_stage",
        )
        for trigger in qs:
            event_name = trigger.trigger_definition.event.name
            self._by_event[event_name].append(trigger)
        self._populated = True

    def triggers_for(self, event_name: str) -> list["Trigger"]:
        if not self._populated:
            self._populate()
        return [t for t in self._by_event.get(event_name, []) if self._is_active(t)]

    def _is_active(self, trigger: "Trigger") -> bool:
        """Stage-scoped triggers are active only when the condition is at that stage."""
        if trigger.source_stage is None:
            return True
        current = trigger.source_condition.current_stage
        return current is not None and current.pk == trigger.source_stage.pk

    # ---- sync hooks (called by service functions) ----

    def on_trigger_added(self, trigger: "Trigger") -> None:
        if not self._populated:
            return  # lazy — will populate on first use
        event_name = trigger.trigger_definition.event.name
        self._by_event[event_name].append(trigger)

    def on_trigger_removed(self, trigger_pk: int) -> None:
        if not self._populated:
            return
        for event_name, triggers in self._by_event.items():
            self._by_event[event_name] = [t for t in triggers if t.pk != trigger_pk]

    def on_stage_changed(self, condition_pk: int, new_stage: Any) -> None:
        """No structural change — ``_is_active`` re-checks on each dispatch."""
        # Intentional no-op: stage activation is computed at dispatch time.
        # This hook exists so future subclasses (line-of-sight rooms) can
        # maintain additional indexes.
        return

    # ---- dispatch ----

    def dispatch(
        self,
        event_name: str,
        payload: Any,
        *,
        flow_stack: Any = None,
    ) -> DispatchResult:
        """Walk active triggers for event_name, evaluate filters, execute flows."""
        result = DispatchResult()
        for trigger in sorted(
            self.triggers_for(event_name),
            key=lambda t: -t.priority,
        ):
            if self._usage_cap_reached(trigger):
                continue
            try:
                matched = evaluate_filter(
                    trigger.additional_filter_condition,
                    payload,
                    self_ref=self.owner,
                )
            except FilterPathError:
                logger.warning(
                    "FilterPathError on trigger %s during dispatch of %s",
                    trigger.pk,
                    event_name,
                )
                continue
            if not matched:
                continue
            result.fired.append(trigger.pk)
            self._execute_flow(trigger, payload, flow_stack, result)
            if result.cancelled:
                break
        return result

    def _execute_flow(
        self,
        trigger: "Trigger",
        payload: Any,
        flow_stack: Any,
        result: DispatchResult,
    ) -> None:
        """Execute the trigger's flow definition within the given FlowStack."""
        from flows.flow_execution import FlowExecution  # noqa: PLC0415 — Evennia startup order
        from flows.flow_stack import FlowStack  # noqa: PLC0415 — same reason
        from flows.scene_data_manager import SceneDataManager  # noqa: PLC0415 — same reason

        flow_def = trigger.trigger_definition.flow_definition
        if flow_stack is None:
            flow_stack = FlowStack(
                owner=self.owner,
                originating_event=trigger.trigger_definition.event.name,
            )
        context = SceneDataManager()
        execution = FlowExecution(
            flow_definition=flow_def,
            context=context,
            flow_stack=flow_stack,
            origin=trigger,
            variable_mapping={
                "payload": payload,
                "owner": self.owner,
                "trigger": trigger,
            },
            dispatch_result=result,
        )
        flow_stack.execute_flow(execution)

    def _usage_cap_reached(self, trigger: "Trigger") -> bool:
        """Usage-cap stub. Real implementation lands at Task 42 Test 24.

        Spec § Integration test 24 (Usage cap is pre-filter) requires that
        TriggerData.max_uses_per_scene is consulted BEFORE filter evaluation.
        For now: return False.
        """
        return False
