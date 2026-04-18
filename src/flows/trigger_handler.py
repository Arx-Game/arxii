"""Populate-once trigger provider for typeclass owners.

Installed as a ``cached_property`` on Character, Room, Object. Populates
from ``Trigger`` rows on first access, stays synced via explicit sync
hooks. Dispatch itself lives in ``flows.emit.emit_event`` — this handler
is a pure provider that exposes ``triggers_for(event_name)``.
"""

from collections import defaultdict
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from flows.models.triggers import Trigger

logger = logging.getLogger(__name__)


class DispatchResult:
    """Result container for a single dispatch walk.

    Preserved across the unified-dispatch rewrite so flow steps that
    consult ``execution.dispatch_result`` still have a type to reference.
    A later task may relocate this to ``flows.emit``.
    """

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
        # Ownerless handlers (e.g., a bare provider with no associated typeclass)
        # have no DB rows to fetch — short-circuit so unit tests can construct
        # a TriggerHandler without hitting the ORM.
        if self.owner is None:
            self._populated = True
            return

        # Deferred import: this module is imported by typeclasses during
        # Evennia startup, before the flows app registry is ready.
        from flows.models.triggers import Trigger  # noqa: PLC0415

        self._by_event.clear()
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
