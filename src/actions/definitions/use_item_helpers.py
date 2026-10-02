"""Ordinary Use's typed arguments and independent read-safe prerequisites."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar

from django.db.models import Q
from evennia.objects.models import ObjectDB

from actions.constants import TargetKind
from actions.definitions.item_helpers import (
    MENU_TARGET_KEY,
    resolve_item_instance,
    resolve_typed_item,
)
from actions.prerequisites import (
    NOT_HOLDING_MESSAGE,
    OnUseTargetPrerequisite,
    Prerequisite,
    room_use_is_visible,
)
from actions.target_menu_types import MenuTargetKind, MenuTargetRequest
from actions.target_resolution import _room_menu_label, resolve_menu_target
from flows.events.payloads import ActionIntentPayload
from flows.object_states.item_state import ItemState
from world.conditions.services import can_perceive
from world.forms.models import FormTraitOption
from world.items.exceptions import ItemError
from world.items.models import ItemInstance
from world.items.services.usage import (
    validate_item_use_blend,
    validate_item_use_bound,
    validate_item_use_option,
    validate_item_use_target,
)
from world.scenes.models import Persona
from world.scenes.persona_display import resolve_display_for_viewer, viewer_context_for_account
from world.scenes.services import active_persona_for_sheet

USE_TARGET_KEY = "use_target"
OPTION_ID_KEY = "option_id"
BLEND_KEY = "blend"
OPTION_INVALID = "option_id must be a number."
DESCRIPTOR_INVALID = "descriptor must be text."
BLEND_INVALID = "blend must be true or false."
UNAVAILABLE = "That isn't available."
SUPPORTED_KINDS = frozenset({TargetKind.ITEM, TargetKind.CHARACTER, TargetKind.ROOM})
COMPETING_FIELDS = frozenset(
    {
        "item",
        "item_id",
        "item_instance_id",
        "item_name",
        "target",
        "target_id",
        "target_persona_id",
        "owner_id",
        "container_id",
        "owner_persona_id",
        "container_item_id",
        "pending_inputs",
    }
)


def source_values(kwargs: dict[str, Any]) -> dict[str, Any]:
    """Keep source assertions separate from effect-target input."""
    return {
        key: value
        for key, value in kwargs.items()
        if key not in {"use_target", "option_id", "descriptor", "blend"}
    }


def use_source(actor: ObjectDB, kwargs: dict[str, Any]) -> ItemInstance | None:
    """Resolve current source without granting possession."""
    if MENU_TARGET_KEY in kwargs:
        resolved = resolve_typed_item(actor, source_values(kwargs))
        return resolved.item if resolved is not None else None
    return resolve_item_instance(kwargs.get("item"))


def scalar_values(kwargs: dict[str, Any]) -> tuple[int | None, str | None, bool]:
    """Normalize presentation fields, keeping legacy coercion off typed wire."""
    if MENU_TARGET_KEY in kwargs:
        if COMPETING_FIELDS.intersection(kwargs) or set(kwargs).difference(
            {MENU_TARGET_KEY, "use_target", "option_id", "descriptor", "blend"}
        ):
            raise ValueError(UNAVAILABLE)
        option = kwargs.get("option_id")
        if OPTION_ID_KEY in kwargs and (type(option) is not int or option <= 0):
            raise ValueError(OPTION_INVALID)
        descriptor = kwargs.get("descriptor")
        if descriptor is not None and not isinstance(descriptor, str):
            raise ValueError(DESCRIPTOR_INVALID)
        blend = kwargs.get("blend", False)
        if type(blend) is not bool:
            raise ValueError(BLEND_INVALID)
    else:
        raw = kwargs.get("option_id")
        try:
            option = int(raw) if raw is not None else None
        except (TypeError, ValueError) as exc:
            raise ValueError(OPTION_INVALID) from exc
        descriptor = kwargs.get("descriptor") or ""
        if not isinstance(descriptor, str):
            raise ValueError(DESCRIPTOR_INVALID)
        blend = bool(kwargs.get("blend"))
    return option, (descriptor or "").strip() or None, blend


def use_target(
    actor: ObjectDB, kwargs: dict[str, Any], item: ItemInstance
) -> tuple[ObjectDB | None, str]:
    """Resolve explicit effect-target identity in this action's actual scope."""
    if MENU_TARGET_KEY not in kwargs:
        value = kwargs.get("target")
        return (value, "") if value is None or isinstance(value, ObjectDB) else (None, UNAVAILABLE)
    kind = item.template.on_use_target_kind
    if kind is None:
        return (
            (None, "") if USE_TARGET_KEY not in kwargs else (None, "That can't be used on others.")
        )
    if USE_TARGET_KEY not in kwargs:
        return None, "Use it on what?"
    wire = kwargs["use_target"]
    if not isinstance(wire, dict) or set(wire) != {"kind", "target_id"}:
        return None, UNAVAILABLE
    pk = wire["target_id"]
    if type(pk) is not int or pk <= 0:
        return None, UNAVAILABLE
    if kind == TargetKind.ITEM:
        if wire["kind"] != MenuTargetKind.ITEMS:
            return None, UNAVAILABLE
        resolved = resolve_menu_target(actor, MenuTargetRequest(MenuTargetKind.ITEMS, pk))
        if resolved is None or resolved.game_object is None:
            return None, UNAVAILABLE
        return resolved.game_object, ""
    if wire["kind"] != MenuTargetKind.OBJECTS or kind not in {
        TargetKind.CHARACTER,
        TargetKind.ROOM,
    }:
        return None, UNAVAILABLE
    return _object_use_target(actor, pk, kind)


def _object_use_target(actor: ObjectDB, pk: int, kind: str) -> tuple[ObjectDB | None, str]:
    """Validate current character or room presence and public identity."""
    target = ObjectDB.objects.filter(pk=pk).first()
    if target is None:
        return None, UNAVAILABLE
    if kind == TargetKind.ROOM:
        return (target, "") if room_use_is_visible(actor, target) else (None, UNAVAILABLE)
    if not can_perceive(actor, target):
        return None, UNAVAILABLE
    if kind == TargetKind.CHARACTER:
        if (
            actor.location is None
            or target.location != actor.location
            or not target.is_typeclass("typeclasses.characters.Character", exact=False)
            or target.character_sheet is None
        ):
            return None, UNAVAILABLE
        try:
            active_persona_for_sheet(target.character_sheet)
        except Persona.DoesNotExist:
            return None, UNAVAILABLE
    return target, ""


def target_label(actor: ObjectDB, target: ObjectDB) -> str:
    """Project current public target label without initializing flow state."""
    if target.is_typeclass("typeclasses.characters.Character", exact=False):
        persona = active_persona_for_sheet(target.character_sheet)
        account = actor.db_account
        personas, sheets = (
            viewer_context_for_account(account) if account is not None else (set(), set())
        )
        name, _ = resolve_display_for_viewer(
            persona,
            viewer_persona_ids=personas,
            viewer_sheet_ids=sheets,
            is_staff=bool(account is not None and account.is_staff),
        )
        return name
    instance = resolve_item_instance(target)
    if instance is not None:
        return instance.display_name
    return _room_menu_label(actor.location, target, actor, None)


def candidate_targets(
    actor: ObjectDB, kwargs: dict[str, Any], item: ItemInstance
) -> list[tuple[dict[str, Any] | None, str]]:
    """Enumerate the current supported effect-target dimension."""
    kind = item.template.on_use_target_kind
    if USE_TARGET_KEY in kwargs or kind is None:
        target, reason = use_target(actor, kwargs, item)
        if reason:
            return []
        return [
            (
                kwargs.get("use_target"),
                "Yourself" if target is None else target_label(actor, target),
            )
        ]
    wires = []
    if kind == TargetKind.ITEM:
        scope = Q(game_object__db_location=actor)
        if actor.location is not None:
            scope |= Q(game_object__db_location=actor.location)
        wires = [
            {"kind": "items", "target_id": candidate.pk}
            for candidate in ItemInstance.objects.in_play()
            .filter(scope, contained_in__isnull=True, game_object__isnull=False)
            .order_by("pk")
        ]
    elif actor.location is not None:
        scope = Q(db_location=actor.location)
        if kind == TargetKind.ROOM:
            scope |= Q(pk=actor.location.pk)
        wires = [
            {"kind": "objects", "target_id": candidate.pk}
            for candidate in ObjectDB.objects.filter(scope).order_by("pk")
        ]
    targets = []
    for wire in wires:
        target, reason = use_target(actor, {**kwargs, "use_target": wire}, item)
        if not reason:
            targets.append((wire, target_label(actor, target)))
    return targets


def candidate_options(kwargs: dict[str, Any], item: ItemInstance) -> list[tuple[int | None, str]]:
    """Match the service's first-null effect or its honest no-choice dimension."""
    effect = item.template.appearance_effects.filter(target_option__isnull=True).first()
    if effect is None:
        return [(None, "")]
    if OPTION_ID_KEY in kwargs:
        option_id = kwargs[OPTION_ID_KEY]
        if type(option_id) is not int or option_id <= 0:
            return []
        option = FormTraitOption.objects.filter(pk=option_id, trait_id=effect.trait_id).first()
        return [] if option is None else [(option_id, option.display_name)]
    return [
        (option.pk, option.display_name)
        for option in FormTraitOption.objects.filter(trait=effect.trait).order_by(
            "sort_order", "pk"
        )
    ]


@dataclass
class UseIntentPayload(ActionIntentPayload):
    """Use intent's item source and explicit effect-target wire."""

    item_target: Any = None
    use_target: Any = None
    option_id: Any = None
    descriptor: Any = None
    blend: Any = False


@dataclass
class _UseBound(Prerequisite):
    def is_met(
        self, actor: ObjectDB, target: ObjectDB | None = None, context: dict[str, Any] | None = None
    ) -> tuple[bool, str]:
        kwargs = (context or {}).get("kwargs", {})
        failures = []
        try:
            scalar_values(kwargs)
        except ValueError as exc:
            failures.append(str(exc))
        item = use_source(actor, kwargs)
        if item is None:
            failures.append(UNAVAILABLE if MENU_TARGET_KEY in kwargs else "Use what?")
            return False, "; ".join(failures)
        typed = MENU_TARGET_KEY in kwargs
        if (
            typed
            and item.template.on_use_target_kind is not None
            and item.template.on_use_target_kind not in SUPPORTED_KINDS
        ):
            failures.append("That can't be used on that.")
        if item.game_object is None:
            held = (
                typed
                and item.contained_in is None
                and actor.character_sheet is not None
                and item.holder_character_sheet_id == actor.character_sheet.pk
            )
        else:
            held = ItemState(item, context=None).is_in_possession(actor)
        if not held:
            failures.append(NOT_HOLDING_MESSAGE)
        try:
            validate_item_use_bound(item_instance=item, user=actor)
        except ItemError as exc:
            failures.append(exc.user_message)
        return not failures, "; ".join(failures)


@dataclass
class _UseTarget(Prerequisite):
    required_input_names: ClassVar[frozenset[str]] = frozenset({"use_target"})

    def is_met(
        self, actor: ObjectDB, target: ObjectDB | None = None, context: dict[str, Any] | None = None
    ) -> tuple[bool, str]:
        kwargs = (context or {}).get("kwargs", {})
        item = use_source(actor, kwargs)
        if item is None:
            return True, ""
        effect_target, reason = use_target(actor, kwargs, item)
        if reason:
            return False, reason
        met, reason = OnUseTargetPrerequisite().is_met(
            actor, effect_target, {"kwargs": {"item": item}}
        )
        if not met:
            return False, reason
        try:
            validate_item_use_target(item_instance=item, user=actor, target=effect_target)
        except ItemError as exc:
            return False, exc.user_message
        return True, ""


@dataclass
class _UseOption(Prerequisite):
    required_input_names: ClassVar[frozenset[str]] = frozenset({"option_id"})

    def is_met(
        self, actor: ObjectDB, target: ObjectDB | None = None, context: dict[str, Any] | None = None
    ) -> tuple[bool, str]:
        kwargs = (context or {}).get("kwargs", {})
        item = use_source(actor, kwargs)
        if item is None:
            return True, ""
        try:
            raw = kwargs.get("option_id")
            if MENU_TARGET_KEY in kwargs:
                if OPTION_ID_KEY in kwargs and (type(raw) is not int or raw <= 0):
                    return True, ""  # Bound parsing supplies malformed-option refusal.
                option = raw
            else:
                option = int(raw) if raw is not None else None
            validate_item_use_option(item_instance=item, user=actor, option_id=option)
        except (TypeError, ValueError):
            return True, ""  # Bound parsing supplies malformed-option refusal.
        except ItemError as exc:
            return False, exc.user_message
        return True, ""


@dataclass
class _UseBlend(Prerequisite):
    def is_met(
        self, actor: ObjectDB, target: ObjectDB | None = None, context: dict[str, Any] | None = None
    ) -> tuple[bool, str]:
        kwargs = (context or {}).get("kwargs", {})
        item = use_source(actor, kwargs)
        if item is None:
            return True, ""
        # Scalar parsing elsewhere must not mask a decidable blend check.
        blend = kwargs.get("blend", False)
        if MENU_TARGET_KEY in kwargs and type(blend) is not bool:
            return True, ""
        try:
            validate_item_use_blend(item_instance=item, blend=bool(blend))
        except ItemError as exc:
            return False, exc.user_message
        return True, ""
