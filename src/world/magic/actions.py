"""Runtime action objects for magic system rituals.

Spec A §4.3. PerformRitualAction composes validation, component consumption,
and dispatch into a single atomic unit. It is NOT a model — it is a transient
object that executes and exits.
"""

import importlib

from django.db import transaction

from world.character_sheets.models import CharacterSheet
from world.items.models import ItemInstance
from world.magic.constants import RitualExecutionKind
from world.magic.exceptions import RitualComponentError
from world.magic.models import Ritual


class PerformRitualAction:
    """Runtime action object for performing a Ritual.

    Spec A §4.3. Validates the provided ItemInstances against the ritual's
    RitualComponentRequirement rows, atomically consumes them, dispatches
    to the ritual's service function or flow definition, and (in future phases)
    emits a RitualPerformed event and renders narrative_prose.

    Usage::

        action = PerformRitualAction(
            actor=character_sheet,
            ritual=ritual,
            components_provided=[item_instance, ...],
            kwargs={"thread": thread, "amount": 50},
        )
        result = action.execute()  # returns service result or None for FLOW

    Args:
        actor: The CharacterSheet performing the ritual.
        ritual: The Ritual to perform.
        components_provided: ItemInstance rows the player is contributing.
        kwargs: Ritual-specific parameters forwarded to the service or flow.
    """

    def __init__(
        self,
        *,
        actor: CharacterSheet,
        ritual: Ritual,
        components_provided: list[ItemInstance],
        kwargs: dict,
    ) -> None:
        self.actor = actor
        self.ritual = ritual
        self.components_provided = components_provided
        self.kwargs = kwargs

    @transaction.atomic
    def execute(self) -> object:
        """Validate components, consume them, and dispatch the ritual.

        Steps (Spec A §4.3):
          1. Validate components_provided satisfy all ritual.requirements.
          2. Atomically consume the components.
          3. Site-property bonus — deferred to Spec D.
          4. Dispatch: SERVICE or FLOW.
          5. Emit RitualPerformed event — deferred (no event class yet).
          6. Render narrative_prose — deferred (ImbuingProseTemplate selection
             lands in a future phase; returns ritual.narrative_prose as-is).

        Returns:
            The service function's return value for SERVICE rituals, or None
            for FLOW rituals.

        Raises:
            RitualComponentError: If the provided components do not satisfy
                all of the ritual's requirements.
        """
        matched_pks = self._validate_components()
        self._consume_components(matched_pks)

        # Step 3: site_property bonus — deferred to Spec D.

        if self.ritual.execution_kind == RitualExecutionKind.SERVICE:
            result = self._dispatch_service()
        else:
            self._dispatch_flow()
            result = None

        # Step 5: emit RitualPerformed event — deferred (no event class yet).
        # Step 6: narrative_prose rendering — deferred (ImbuingProseTemplate
        #   selection / substitution lands in a future phase per Spec A §4.3).

        return result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _validate_components(self) -> list[int]:
        """Check that components_provided satisfy all requirements.

        For each RitualComponentRequirement, tallies matching ItemInstances
        from components_provided (same template; quality_tier >= min if set;
        total quantity >= required).

        Returns:
            List of ItemInstance PKs that will be consumed (one per
            required-item slot, pruned to the minimum needed quantity).

        Raises:
            RitualComponentError: On the first unsatisfied requirement.
        """
        requirements = self.ritual.requirements.all().select_related(
            "item_template", "min_quality_tier"
        )
        consumed_pks: list[int] = []

        for req in requirements:
            # Find instances matching this requirement (template + quality).
            candidates = [
                inst
                for inst in self.components_provided
                if inst.template_id == req.item_template_id
                and self._meets_quality(inst, req)
                and inst.pk not in consumed_pks
            ]
            # Sum quantity across matching instances (ItemInstance.quantity
            # represents stack size for stackable items).
            total_qty = sum(inst.quantity for inst in candidates)
            if total_qty < req.quantity:
                msg = (
                    f"Ritual '{self.ritual.name}' requires {req.quantity}x "
                    f"'{req.item_template}' but only {total_qty} provided."
                )
                raise RitualComponentError(msg)

            # Record PKs to consume (greedy: take from candidates in order).
            remaining = req.quantity
            for inst in candidates:
                if remaining <= 0:
                    break
                consumed_pks.append(inst.pk)
                remaining -= inst.quantity

        return consumed_pks

    @staticmethod
    def _meets_quality(inst: ItemInstance, req: object) -> bool:
        """Return True if inst satisfies req.min_quality_tier (if any)."""
        if req.min_quality_tier_id is None:  # type: ignore[union-attr]
            return True
        if inst.quality_tier_id is None:
            return False
        return inst.quality_tier.sort_order >= req.min_quality_tier.sort_order  # type: ignore[union-attr]

    def _consume_components(self, pks: list[int]) -> None:
        """Delete the consumed ItemInstance rows (bulk)."""
        if pks:
            ItemInstance.objects.filter(pk__in=pks).delete()

    def _dispatch_service(self) -> object:
        """Import and call the ritual's service function.

        Convention (Spec A §4.3 + plan line 3013): dispatches as
        ``func(character_sheet=self.actor, **self.kwargs)`` because the
        existing service functions (e.g. spend_resonance_for_imbuing) use
        ``character_sheet=`` as their first kwarg, not ``actor=``.
        """
        path = self.ritual.service_function_path
        module_path, func_name = path.rsplit(".", 1)
        module = importlib.import_module(module_path)
        func = getattr(module, func_name)
        return func(character_sheet=self.actor, **self.kwargs)

    def _dispatch_flow(self) -> None:
        """Execute the ritual's FlowDefinition via a manual FlowExecution run.

        The plan referenced ``from flows.engine import trigger_flow`` which does
        not exist. Instead we construct FlowStack + SceneDataManager +
        FlowExecution + DispatchResult directly, matching the pattern used
        by the existing flow infrastructure.
        """
        from flows.flow_execution import FlowExecution  # noqa: PLC0415
        from flows.flow_stack import FlowStack  # noqa: PLC0415
        from flows.scene_data_manager import SceneDataManager  # noqa: PLC0415
        from flows.trigger_handler import DispatchResult  # noqa: PLC0415

        flow_def = self.ritual.flow
        stack = FlowStack(owner=self.actor, originating_event="RitualPerformed")
        context = SceneDataManager()
        execution = FlowExecution(
            flow_definition=flow_def,
            context=context,
            flow_stack=stack,
            origin=None,
            variable_mapping={"actor": self.actor, **self.kwargs},
            dispatch_result=DispatchResult(),
        )
        stack.execute_flow(execution)
