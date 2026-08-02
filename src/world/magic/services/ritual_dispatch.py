"""Ritual dispatch switch — SERVICE / FLOW / CEREMONY (#2705).

Split out of ``PerformRitualAction`` (`actions/definitions/ritual.py`) so a
ritual conducted across combat rounds (#2705 Task 5) can consume its
components at declaration (via
``world.magic.services.ritual_components.resolve_and_consume_ritual_components``)
and dispatch later at maturation, sharing this exact switch with the
synchronous non-combat path instead of duplicating it. This is a
behaviour-preserving extraction — the pre-existing ritual action/service
tests (``actions/tests/test_perform_ritual_action.py``,
``world/magic/tests/test_perform_ritual_action_touchstone.py``, the
``test_ritual_telnet_e2e.py`` / ``test_ritual_session_telnet_e2e.py``
integration journeys) are the oracle for that; none of them changed.

All imports below are lazy for the same reason
``actions/definitions/ritual.py`` documents at its own top: importing
``world.magic``/``world.items``/``flows`` eagerly here would pull in much of
the world graph from a module (``actions``) that is imported very early.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.magic.models import Ritual


def dispatch_ritual(*, ritual: Ritual, performer_sheet: CharacterSheet, **kwargs: Any) -> Any:
    """Run a ritual's authored execution payload (SERVICE / FLOW / CEREMONY).

    Split out of ``PerformRitualAction`` so a ritual conducted over several
    combat rounds (#2705) can consume its components at declaration and
    dispatch at maturation, without a second copy of the dispatch switch.

    Returns whatever the underlying dispatch produces: the service
    function's return value for SERVICE, the created ``PendingRitualEffect``
    for CEREMONY, or ``None`` for FLOW (mirrors the pre-extraction shape in
    ``PerformRitualAction.execute()`` exactly).
    """
    from world.magic.constants import RitualExecutionKind  # noqa: PLC0415

    if ritual.execution_kind == RitualExecutionKind.CEREMONY:
        return _begin_ceremony(ritual, performer_sheet)
    if ritual.execution_kind == RitualExecutionKind.SERVICE:
        return _dispatch_service(ritual, performer_sheet, kwargs)
    _dispatch_flow(ritual, performer_sheet, kwargs)
    return None


def _dispatch_service(ritual: Ritual, sheet: CharacterSheet, kwargs: dict[str, Any]) -> Any:
    """Import and call the ritual's service function.

    Convention: the service functions take ``character_sheet=`` as their
    first kwarg (e.g. ``spend_resonance_for_imbuing``), not ``actor=``.
    The ``ritual`` instance is also forwarded so service functions that
    need to resolve authored data linked to the ritual (e.g. a
    ``TechniqueGrant``) can do so. Service functions should accept
    ``**kwargs`` to absorb parameters they don't use.
    """
    import importlib  # noqa: PLC0415

    module_path, func_name = ritual.service_function_path.rsplit(".", 1)
    module = importlib.import_module(module_path)
    func = getattr(module, func_name)
    return func(character_sheet=sheet, ritual=ritual, **kwargs)


def _begin_ceremony(ritual: Ritual, sheet: CharacterSheet) -> Any:
    """Create a PendingRitualEffect for a CEREMONY-kind ritual.

    Raises RitualComponentError (with a dynamic user_message) if a pending
    effect already exists — caught by the caller's except block.
    """
    from world.magic.exceptions import RitualComponentError  # noqa: PLC0415
    from world.magic.models import PendingRitualEffect  # noqa: PLC0415

    if PendingRitualEffect.objects.filter(character=sheet, ritual=ritual).exists():
        exc = RitualComponentError()
        exc.user_message = f"A {ritual.name} is already in progress."
        raise exc
    return PendingRitualEffect.objects.create(character=sheet, ritual=ritual)


def _dispatch_flow(ritual: Ritual, sheet: CharacterSheet, kwargs: dict[str, Any]) -> None:
    """Execute the ritual's FlowDefinition via a manual FlowExecution run."""
    from flows.flow_execution import FlowExecution  # noqa: PLC0415
    from flows.flow_stack import FlowStack  # noqa: PLC0415
    from flows.scene_data_manager import SceneDataManager  # noqa: PLC0415
    from flows.trigger_handler import DispatchResult  # noqa: PLC0415

    stack = FlowStack(owner=sheet, originating_event="RitualPerformed")
    flow_context = SceneDataManager()
    execution = FlowExecution(
        flow_definition=ritual.flow,
        context=flow_context,
        flow_stack=stack,
        origin=None,
        variable_mapping={"actor": sheet, **kwargs},
        dispatch_result=DispatchResult(),
    )
    stack.execute_flow(execution)
