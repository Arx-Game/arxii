"""Viewer-scoped typed menu reads; action checks remain execution authority."""

from __future__ import annotations

from typing import Any

from django.core import signing

from actions.constants import ActionBackend, Pipeline
from actions.definitions.use_item_helpers import target_label
from actions.player_interface import _avail_to_player_action
from actions.registry import get_action
from actions.services import get_effective_consequences
from actions.target_menu_serializers import MenuEntrySerializer
from actions.target_menu_types import (
    AUTHOR_ENTRY_CONTEXT,
    INPUT_USE_TARGET,
    MenuTargetKind,
    MenuTargetRequest,
)
from actions.target_resolution import resolve_menu_target
from actions.types import ActionRef
from world.items.models import ItemInstance
from world.mechanics.models import ApproachConsequence, ChallengeTemplateConsequence
from world.mechanics.services import get_available_actions
from world.scenes.models import Persona

ACTION_GIVE = "give"
ACTION_PUT_IN = "put_in"
ACTION_USE_ITEM = "use_item"
INPUT_DESCRIPTOR = "descriptor"
INPUT_BLEND = "blend"

GROUPS = (
    ("perception", "Perception"),
    ("items", "Item handling"),
    ("movement", "Movement and places"),
    ("authored", "Authored actions"),
)
ORDINARY = (
    ("get", "Get"),
    ("drop", "Drop"),
    ("equip", "Equip"),
    ("unequip", "Unequip"),
    ("give", "Give"),
    ("put_in", "Put in"),
    ("take_out", "Take out"),
    ("steal", "Steal"),
    ("use_item", "Use"),
)
CANDIDATE_PAGE_SIZE = 25
CURSOR_SALT = "actions.target-menu.candidates.v1"
CURSOR_TUPLE_SIZE = 3
CURSOR_POSITION = "after"
CURSOR_ITEM_PK = "after_pk"
MAX_CANDIDATE_CURSOR_LENGTH = 2048


class InvalidCandidateCursor(ValueError):
    """A candidate cursor is malformed or does not match this menu request."""


NO_CHOICES = {
    "give": "No recipient is currently available.",
    "put_in": "No container is currently available.",
    "use_item": "No valid target or option is currently available.",
}


def target_wire(request: MenuTargetRequest) -> dict[str, Any]:
    """Keep assertions explicit and omit absent assertion keys."""
    wire = {"kind": request.kind.value, "target_id": request.target_id}
    wire.update(
        {
            name: value
            for name, value in (
                ("owner_persona_id", request.owner_persona_id),
                ("container_item_id", request.container_item_id),
            )
            if value is not None
        }
    )
    return wire


def _input(
    name: str,
    kind: str,
    *,
    required: bool = True,
    target_kind: str | None = None,
    default: Any = None,
) -> dict[str, Any]:
    return {
        "name": name,
        "kind": kind,
        "required": required,
        "target_kind": target_kind,
        "default": default,
    }


def _candidate(
    key: str, label: str, values: dict[str, Any], checked: dict[str, Any]
) -> dict[str, Any]:
    return {
        "key": key,
        "label": label,
        "kwargs": values,
        "available": checked["available"],
        "reasons": list(checked["reasons"]),
    }


def _choices(  # noqa: C901
    actor: Any,
    action: Any,
    values: dict[str, Any],
    *,
    after_pk: int | None = None,
    after: tuple[int, int, int] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any] | None]:
    """Adapt action-owned candidates without inventing permission predicates."""
    if action.key == ACTION_GIVE:
        page_rows, next_offset = action.recipient_candidate_page(
            actor, kwargs=values, after_pk=after_pk, page_size=CANDIDATE_PAGE_SIZE
        )
        rows = []
        for row in page_rows:
            persona = Persona.objects.get(pk=row["recipient_persona_id"])
            name = target_label(actor, persona.character_sheet.character)
            rows.append(
                _candidate(str(persona.pk), name, {"recipient_persona_id": persona.pk}, row)
            )
        cursor_data = {CURSOR_ITEM_PK: next_offset} if next_offset is not None else None
        return [_input("recipient_persona_id", "recipient")], rows, cursor_data
    if action.key == ACTION_PUT_IN:
        page_rows, next_offset = action.container_candidate_page(
            actor, kwargs=values, after_pk=after_pk, page_size=CANDIDATE_PAGE_SIZE
        )
        rows = []
        for row in page_rows:
            item = ItemInstance.objects.get(pk=row["container_item_id"])
            # The menu chooser is carried containers, not every service-supported destination.
            if item.game_object is None or item.game_object.location != actor:
                continue
            rows.append(_candidate(str(item.pk), row["name"], {"container_item_id": item.pk}, row))
        cursor_data = {CURSOR_ITEM_PK: next_offset} if next_offset is not None else None
        return [_input("container_item_id", "container")], rows, cursor_data
    if action.key != ACTION_USE_ITEM:
        return [], [], None
    spec = action.use_input_spec(actor, kwargs=values)
    inputs = [
        _input(
            name,
            "target" if name == INPUT_USE_TARGET else "option",
            target_kind=spec["target_kind"] if name == INPUT_USE_TARGET else None,
        )
        for name in spec["required_inputs"]
    ]
    if spec[INPUT_DESCRIPTOR]:
        inputs.append(_input(INPUT_DESCRIPTOR, "text", required=False))
    if spec[INPUT_BLEND]:
        inputs.append(_input(INPUT_BLEND, "boolean", required=False, default=False))
    rows = []
    next_offset = None
    if spec["required_inputs"]:
        page, next_after = action.use_candidate_page(
            actor, kwargs=values, after=after, page_size=CANDIDATE_PAGE_SIZE
        )
        next_offset = {CURSOR_POSITION: next_after} if next_after is not None else None
        for row in page:
            extra = {}
            if row["use_target"] is not None:
                extra["use_target"] = row["use_target"]
            if row["option_id"] is not None:
                extra["option_id"] = row["option_id"]
            label = " · ".join(part for part in (row["target_name"], row["option_name"]) if part)
            target_id = row["use_target"]["target_id"] if row["use_target"] else 0
            stable_key = f"{target_id}:{row['option_id'] or 0}"
            rows.append(_candidate(stable_key, label, extra, row))
    return inputs, rows, next_offset


def _ordinary_entry(  # noqa: PLR0913
    actor: Any,
    key: str,
    label: str,
    group: str,
    values: dict[str, Any],
    *,
    after_pk: int | None = None,
    after: tuple[int, int, int] | None = None,
) -> dict[str, Any] | None:
    action = get_action(key)
    if not action.is_applicable(actor, kwargs=values):
        return None
    inputs, candidates, next_offset = _choices(
        actor, action, values, after_pk=after_pk, after=after
    )
    pending = frozenset(row["name"] for row in inputs if row["required"])
    checked = action.check_availability(actor, context={"kwargs": values}, pending_inputs=pending)
    reasons = list(checked.reasons)
    available = checked.available
    if pending and next_offset is None and not any(row["available"] for row in candidates):
        available = False
        if not reasons:
            reasons = next(
                (list(row["reasons"]) for row in candidates if row["reasons"]), [NO_CHOICES[key]]
            )
    return {
        "key": key,
        "action_key": key,
        "label": label,
        "group": group,
        "ref": ActionRef(backend=ActionBackend.REGISTRY, registry_key=key),
        "kwargs": values,
        "available": available,
        "reasons": reasons,
        "inputs": inputs,
        "candidates": candidates,
        "next_candidate_cursor": next_offset,
        "action": None,
        "risk": None,
    }


def _risk_row(stage: str, consequence: Any) -> dict[str, Any]:
    return {
        "stage": stage,
        "tier": str(consequence.outcome_tier.name),
        "character_loss": consequence.character_loss,
    }


def _risk(avail: Any) -> dict[str, Any]:
    """Project authored candidates, never select effects or infer safety from missing metadata."""
    approach = avail.resolved_challenge_approach
    instance = avail.resolved_challenge_instance
    template = instance.template if instance is not None else avail.resolved_default_template
    if approach is None or template is None:
        return {"known": False, "character_loss_possible": None, "outcomes": []}
    rows = []
    if approach.action_template is not None:
        action_template = approach.action_template
        pools = []
        if action_template.pipeline == Pipeline.GATED:
            pools.extend(
                (f"gate:{gate.gate_role}", gate.consequence_pool)
                for gate in action_template.gates.select_related("consequence_pool").order_by(
                    "step_order", "pk"
                )
                if gate.consequence_pool is not None
            )
        if action_template.consequence_pool is not None:
            pools.append(("main", action_template.consequence_pool))
        for stage, pool in pools:
            for weighted in get_effective_consequences(pool):
                if weighted.weight > 0:
                    rows.extend([_risk_row(stage, weighted.consequence)])
    else:
        overrides = list(
            ApproachConsequence.objects.filter(approach=approach)
            .select_related("consequence__outcome_tier")
            .order_by("pk")
        )
        overridden = {link.consequence.outcome_tier_id for link in overrides}
        links = list(
            ChallengeTemplateConsequence.objects.filter(challenge_template=template)
            .select_related("consequence__outcome_tier")
            .order_by("pk")
        )
        consequences = [link.consequence for link in overrides]
        consequences.extend(
            link.consequence for link in links if link.consequence.outcome_tier_id not in overridden
        )
        rows = [
            _risk_row("main", consequence) for consequence in consequences if consequence.weight > 0
        ]
    # Empty authored outcomes are not a positive claim of safety.
    return {
        "known": bool(rows),
        "character_loss_possible": any(row["character_loss"] for row in rows) if rows else None,
        "outcomes": rows,
    }


def _authored_entries(actor: Any, resolved: Any) -> list[dict[str, Any]]:
    if (
        resolved.request.kind is MenuTargetKind.PLACES
        or resolved.game_object is None
        or actor.location is None
    ):
        return []
    result = []
    for index, avail in enumerate(get_available_actions(actor, actor.location)):
        instance = avail.resolved_challenge_instance
        if instance is None:
            target = avail.target_object
        else:
            if (
                instance.location != actor.location
                or not instance.is_active
                or not instance.is_revealed
            ):
                continue
            target = instance.target_object
        if target is None or target != resolved.game_object or avail.resolved_check_type is None:
            continue
        # Selection must precede conversion: CHALLENGE refs do not carry ObjectDB targets.
        action = _avail_to_player_action(avail)
        result.append(
            {
                "key": f"authored:{index}",
                "action_key": AUTHOR_ENTRY_CONTEXT,
                "label": action.display_name,
                "group": "authored",
                "ref": action.ref,
                "kwargs": {},
                "available": action.prerequisite_met,
                "reasons": list(action.prerequisite_reasons),
                "inputs": [],
                "candidates": [],
                "action": action,
                "risk": _risk(avail),
            }
        )
    return result


def build_target_menu(  # noqa: C901, PLR0912, PLR0915
    actor: Any,
    request: MenuTargetRequest,
    *,
    inputs_for: str | None = None,
    candidate_cursor: str | None = None,
    account_id: int | None = None,
) -> dict[str, Any] | None:
    """Compose a current read projection and validate executable kwargs before output."""
    resolved = resolve_menu_target(actor, request)
    if resolved is None:
        return None
    values = {"menu_target": target_wire(request)}
    outer_target = target_wire(request)
    effective_source = (
        target_wire(
            MenuTargetRequest(
                MenuTargetKind.ITEMS,
                resolved.item.pk,
                request.owner_persona_id,
                request.container_item_id,
            )
        )
        if resolved.item is not None
        else outer_target
    )
    after = None
    after_pk = None
    if candidate_cursor is not None:
        if len(candidate_cursor) > MAX_CANDIDATE_CURSOR_LENGTH:
            raise InvalidCandidateCursor
        if inputs_for is None:
            raise InvalidCandidateCursor
        try:
            payload = signing.loads(candidate_cursor, salt=CURSOR_SALT)
        except signing.BadSignature as exc:
            raise InvalidCandidateCursor from exc
        if (
            payload.get("action"),
            payload.get("input_mode"),
            payload.get("account"),
            payload.get("actor"),
            payload.get("outer_target"),
            payload.get("effective_source"),
        ) != (
            inputs_for,
            inputs_for,
            account_id,
            actor.pk,
            outer_target,
            effective_source,
        ):
            raise InvalidCandidateCursor
        if CURSOR_POSITION in payload:
            position = payload[CURSOR_POSITION]
            if (
                not isinstance(position, list)
                or len(position) != CURSOR_TUPLE_SIZE
                or any(type(value) is not int or value < 0 for value in position)
            ):
                raise InvalidCandidateCursor
            after = (position[0], position[1], position[2])
        elif CURSOR_ITEM_PK in payload:
            if type(payload[CURSOR_ITEM_PK]) is not int or payload[CURSOR_ITEM_PK] < 1:
                raise InvalidCandidateCursor
            after_pk = payload[CURSOR_ITEM_PK]
        else:
            raise InvalidCandidateCursor
    entries = []
    if resolved.item is not None:
        # OBJECTS item binding uses the real relation, never an equal integer assumption.
        item_request = MenuTargetRequest(
            MenuTargetKind.ITEMS,
            resolved.item.pk,
            request.owner_persona_id,
            request.container_item_id,
        )
        item_values = {"menu_target": target_wire(item_request)}
        item_actions = (
            ("look_at_item", "Look", "perception"),
            *((key, label, "items") for key, label in ORDINARY),
        )
        if inputs_for is not None:
            item_actions = tuple(row for row in item_actions if row[0] == inputs_for)
        for key, label, group in item_actions:
            entry = _ordinary_entry(
                actor,
                key,
                label,
                group,
                item_values,
                after_pk=after_pk if key == inputs_for else None,
                after=after if key == inputs_for else None,
            )
            if entry is not None:
                entries.append(entry)
    elif request.kind in (MenuTargetKind.OBJECTS, MenuTargetKind.EXITS):
        entry = _ordinary_entry(actor, "look", "Look", "perception", values)
        if entry is not None:
            entries.append(entry)
    if request.kind is MenuTargetKind.PLACES:
        for key, label in (("join_place", "Join"), ("leave_place", "Leave")):
            entry = _ordinary_entry(actor, key, label, "movement", values)
            if entry is not None:
                entries.append(entry)
    elif request.kind is MenuTargetKind.EXITS:
        entry = _ordinary_entry(actor, "traverse_exit", "Go", "movement", values)
        if entry is not None:
            entries.append(entry)
    if inputs_for is None:
        entries.extend(_authored_entries(actor, resolved))
    if inputs_for is not None and not any(entry["key"] == inputs_for for entry in entries):
        return None
    for entry in entries:
        next_offset = entry.pop("next_candidate_cursor", None)
        cursor_payload = next_offset
        entry["next_candidate_cursor"] = (
            signing.dumps(
                {
                    "action": entry["key"],
                    "input_mode": entry["key"],
                    "account": account_id,
                    "actor": actor.pk,
                    "outer_target": outer_target,
                    "effective_source": effective_source,
                    **cursor_payload,
                },
                salt=CURSOR_SALT,
            )
            if cursor_payload is not None
            else None
        )
        _ = MenuEntrySerializer(entry, context={"action_key": entry["action_key"]}).data
    return {
        "actor_id": actor.pk,
        "target": target_wire(request),
        "label": resolved.label,
        "groups": [
            {"key": key, "label": label}
            for key, label in GROUPS
            if any(entry["group"] == key for entry in entries)
        ],
        "entries": entries,
    }
