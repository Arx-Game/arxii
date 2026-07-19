"""Idempotent bootstrap of the shared ambient-room-reaction Trigger/Flow (#2471).

One TriggerDefinition (event=MOVED) + one FlowDefinition (one CALL_SERVICE_FUNCTION
step -> world.narrative.services.emit_room_ambient_reaction), shared by every
room-level Trigger installed during grid-bundle import
(core_management.grid_import._import_ambient_lines).

This is CONFIG, not lore-repo content (ADR-0142): the mechanism is one fixed row,
identical in every environment. The per-room content it dispatches to
(AmbientEmoteLine rows) is what's lore-repo-authored — see world.narrative.models.
Called from world.seeds.database.seed_dev_database() alongside
world.magic.seeds_cast.ensure_technique_cast_content(), before the content/grid load
runs (this Trigger row must exist before grid-bundle import tries to reference it).
"""

from __future__ import annotations

AMBIENT_REACTION_FLOW_NAME = "ambient_room_reaction"
AMBIENT_REACTION_TRIGGER_NAME = "moved_ambient_room_reaction"


def ensure_ambient_reaction_content() -> object:
    """Create (or return) the shared TriggerDefinition driving ambient room reactions."""
    from flows.constants import EventName  # noqa: PLC0415
    from flows.consts import FlowActionChoices  # noqa: PLC0415
    from flows.factories import FlowStepDefinitionFactory  # noqa: PLC0415
    from flows.models import FlowDefinition  # noqa: PLC0415
    from flows.models.triggers import TriggerDefinition  # noqa: PLC0415

    flow, _ = FlowDefinition.objects.get_or_create(name=AMBIENT_REACTION_FLOW_NAME)
    if not flow.steps.exists():
        FlowStepDefinitionFactory(
            flow=flow,
            action=FlowActionChoices.CALL_SERVICE_FUNCTION,
            variable_name="world.narrative.services.emit_room_ambient_reaction",
            parameters={"payload": "@payload"},
        )
    trigger_def, _ = TriggerDefinition.objects.get_or_create(
        name=AMBIENT_REACTION_TRIGGER_NAME,
        defaults={
            "event_name": EventName.MOVED,
            "flow_definition": flow,
        },
    )
    return trigger_def
