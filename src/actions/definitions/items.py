"""Item-specific actions: equip, unequip, put_in, take_out, use_item."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar

from evennia.objects.models import ObjectDB

from actions.base import Action
from actions.constants import ActionCategory, TargetKind
from actions.definitions.item_helpers import (
    MENU_TARGET_KEY,
    emit_typed_item_intent,
    resolve_item_instance,
    resolve_typed_item,
)
from actions.definitions.use_item_helpers import (
    BLEND_KEY,
    OPTION_ID_KEY,
    SUPPORTED_KINDS,
    UNAVAILABLE,
    USE_TARGET_KEY,
    UseIntentPayload,
    _UseBlend,
    _UseBound,
    _UseOption,
    _UseTarget,
    candidate_options,
    candidate_targets,
    scalar_values,
    source_values,
    target_label,
    use_source,
    use_target,
)
from actions.prerequisites import (
    CanStealPrerequisite,
    MinimumGMLevelPrerequisite,
    Prerequisite,
)
from actions.target_menu_types import MenuTargetKind, MenuTargetRequest
from actions.target_resolution import resolve_menu_target
from actions.types import ActionContext, ActionResult, TargetType
from flows.constants import EventName
from flows.emit import emit_event
from flows.events.payloads import ActionIntentPayload
from flows.object_states.character_state import CharacterState
from flows.object_states.item_state import ItemState
from flows.scene_data_manager import SceneDataManager
from flows.service_functions.communication import message_location
from flows.service_functions.inventory import (
    equip,
    put_in,
    set_container_policy,
    steal,
    take_out,
    take_requires_steal,
    unequip,
    validate_equip,
    validate_put_in,
    validate_put_in_item,
    validate_steal,
    validate_take_out,
    validate_unequip,
)
from world.gm.constants import GMLevel
from world.items.constants import ContainerAccessPolicy
from world.items.exceptions import (
    InventoryError,
    ItemError,
    MakeoverRequiresConsent,
    NotReachable,
)
from world.items.models import ItemInstance
from world.items.services.usage import use_item
from world.items.types import UseItemResult
from world.scenes.persona_display import viewer_context_for_account

_EQUIPMENT_TARGET_UNAVAILABLE = "That isn't available."
_EQUIPMENT_TARGET_KEY = "target"


def _equipment_item(actor, kwargs):
    if MENU_TARGET_KEY in kwargs:
        resolved = resolve_typed_item(actor, kwargs)
        return resolved.item if resolved is not None else None
    return resolve_item_instance(kwargs.get("target"))


def _equipment_states(actor, item, sdm=None):
    # Construct read state only; initialization hooks belong to execution.
    sdm = sdm if sdm is not None else SceneDataManager()
    return CharacterState(actor, context=sdm), ItemState(item, context=sdm)


@dataclass
class _EquipmentPrerequisite(Prerequisite):
    action: Any = None

    def is_met(self, actor, target=None, context=None):
        context = context or {}
        kwargs = dict(context.get("kwargs", {}))
        if MENU_TARGET_KEY not in kwargs and _EQUIPMENT_TARGET_KEY not in kwargs:
            kwargs["target"] = target
        item = _equipment_item(actor, kwargs)
        if MENU_TARGET_KEY in kwargs:
            if item is None or not self.action.is_applicable(actor, kwargs=kwargs):
                return False, _EQUIPMENT_TARGET_UNAVAILABLE
        elif kwargs.get("target") is None:
            return False, self.action.missing_target_message
        elif item is None:
            return False, self.action.invalid_target_message
        character, item_state = _equipment_states(actor, item, context.get("scene_data"))
        try:
            self.action.validate(character, item_state)
        except ItemError as exc:
            return False, exc.user_message
        return True, ""


class _EquipmentAction(Action):
    """Share equipment lifecycle adaptation, not inventory gameplay rules."""

    def get_prerequisites(self) -> list[Prerequisite]:
        return [*super().get_prerequisites(), _EquipmentPrerequisite(action=self)]

    def _emit_intent(self, context: ActionContext, actor: ObjectDB | None) -> ActionResult | None:
        return emit_typed_item_intent(context, actor, super()._emit_intent)

    def _execute_equipment(self, actor, context, kwargs, mutate, message):
        item = _equipment_item(actor, kwargs)
        if MENU_TARGET_KEY in kwargs:
            if item is None or not self.is_applicable(actor, kwargs=kwargs):
                return ActionResult(success=False, message=_EQUIPMENT_TARGET_UNAVAILABLE)
        elif kwargs.get("target") is None:
            return ActionResult(success=False, message=self.missing_target_message)
        elif item is None:
            return ActionResult(success=False, message=self.invalid_target_message)
        sdm = context.scene_data if context else SceneDataManager()
        actor_state = sdm.initialize_state_for_object(actor)
        item_state = ItemState(item, context=sdm)
        try:
            mutate(actor_state, item_state)
        except ItemError as exc:
            return ActionResult(success=False, message=exc.user_message)
        message_location(actor_state, message, mapping={"target": item.display_name})
        return ActionResult(success=True)


@dataclass
class EquipAction(_EquipmentAction):
    """Equip carried equipment, retaining legacy auto-swap and no-op behavior."""

    key: str = "equip"
    name: str = "Equip"
    icon: str = "shirt"
    category: str = "items"
    action_category: ActionCategory = ActionCategory.PHYSICAL
    target_type: TargetType = TargetType.SINGLE
    objectdb_target_kwargs: ClassVar[frozenset[str]] = frozenset({"target"})
    missing_target_message: ClassVar[str] = "Equip what?"
    invalid_target_message: ClassVar[str] = "That can't be equipped."
    validate = staticmethod(validate_equip)

    def is_applicable(self, actor: ObjectDB, *, kwargs: dict[str, Any]) -> bool:
        item = _equipment_item(actor, kwargs)
        if item is None or item.game_object is None or not item.template.cached_slots:
            return False
        _, state = _equipment_states(actor, item)
        return (
            state.is_in_possession(actor)
            and not item.equipped_slots.filter(character=actor.sheet_data).exists()
        )

    def execute(
        self, actor: ObjectDB, context: ActionContext | None = None, **kwargs: Any
    ) -> ActionResult:
        return self._execute_equipment(
            actor, context, kwargs, equip, "$You() $conj(equip) {target}."
        )


@dataclass
class UnequipAction(_EquipmentAction):
    """Remove actual worn equipment without moving the underlying item."""

    key: str = "unequip"
    name: str = "Unequip"
    icon: str = "shirt-off"
    category: str = "items"
    action_category: ActionCategory = ActionCategory.PHYSICAL
    target_type: TargetType = TargetType.SINGLE
    objectdb_target_kwargs: ClassVar[frozenset[str]] = frozenset({"target"})
    missing_target_message: ClassVar[str] = "Remove what?"
    invalid_target_message: ClassVar[str] = "That can't be removed."
    validate = staticmethod(validate_unequip)

    def is_applicable(self, actor: ObjectDB, *, kwargs: dict[str, Any]) -> bool:
        item = _equipment_item(actor, kwargs)
        return (
            item is not None
            and item.game_object is not None
            and item.equipped_slots.filter(character=actor.sheet_data).exists()
        )

    def execute(
        self, actor: ObjectDB, context: ActionContext | None = None, **kwargs: Any
    ) -> ActionResult:
        return self._execute_equipment(
            actor, context, kwargs, unequip, "$You() $conj(remove) {target}."
        )


_PUT_UNAVAILABLE = "That isn't available."
_PUT_CONTAINER = "container_item_id"
_PUT_LEGACY_CONTAINERS = frozenset({"container", "container_id"})


@dataclass
class _PutInIntentPayload(ActionIntentPayload):
    """Typed insertion intent exposes its selected destination item."""

    container_item_id: Any = None


def _put_source_kwargs(kwargs):
    return {key: value for key, value in kwargs.items() if key != _PUT_CONTAINER}


def _put_item(actor, kwargs):
    if MENU_TARGET_KEY in kwargs:
        if _PUT_LEGACY_CONTAINERS.intersection(kwargs):
            return None
        resolved = resolve_typed_item(actor, _put_source_kwargs(kwargs))
        return resolved.item if resolved is not None else None
    return resolve_item_instance(kwargs.get("target"))


def _put_container(actor, kwargs, item):
    if MENU_TARGET_KEY not in kwargs:
        return resolve_item_instance(kwargs.get("container"))
    if _PUT_LEGACY_CONTAINERS.intersection(kwargs):
        return None
    value = kwargs.get(_PUT_CONTAINER)
    if type(value) is not int or value <= 0:
        return None
    resolved = resolve_menu_target(actor, MenuTargetRequest(MenuTargetKind.ITEMS, value))
    if resolved is None or resolved.item is None or resolved.game_object is None:
        return None
    container = resolved.item
    if container == item or not container.template.is_container:
        return None
    return container


def _put_pair(action, actor, kwargs):
    typed = MENU_TARGET_KEY in kwargs
    if typed and not action.is_applicable(actor, kwargs=kwargs):
        return None, None, _PUT_UNAVAILABLE
    if not typed and (kwargs.get("target") is None or kwargs.get("container") is None):
        return None, None, "Put what into what?"
    item = _put_item(actor, kwargs)
    if item is None:
        return None, None, _PUT_UNAVAILABLE if typed else "That can't be put away."
    container = _put_container(actor, kwargs, item)
    if container is None:
        return None, None, _PUT_UNAVAILABLE if typed else "That isn't a container."
    return item, container, ""


@dataclass
class _PutInItemPrerequisite(Prerequisite):
    action: Any = None

    def is_met(self, actor, target=None, context=None):
        kwargs = (context or {}).get("kwargs", {})
        if MENU_TARGET_KEY in kwargs and not self.action.is_applicable(actor, kwargs=kwargs):
            return False, _PUT_UNAVAILABLE
        return True, ""


@dataclass
class _PutInContainerPrerequisite(Prerequisite):
    required_input_names: ClassVar[frozenset[str]] = frozenset({_PUT_CONTAINER})
    action: Any = None

    def is_met(self, actor, target=None, context=None):
        context = context or {}
        kwargs = dict(context.get("kwargs", {}))
        if MENU_TARGET_KEY not in kwargs and _EQUIPMENT_TARGET_KEY not in kwargs:
            kwargs[_EQUIPMENT_TARGET_KEY] = target
        if MENU_TARGET_KEY in kwargs and not self.action.is_applicable(actor, kwargs=kwargs):
            return True, ""
        item, container, reason = _put_pair(self.action, actor, kwargs)
        if reason:
            return False, reason
        sdm = context.get("scene_data")
        sdm = sdm if sdm is not None else SceneDataManager()
        try:
            validate_put_in(
                CharacterState(actor, context=sdm),
                ItemState(item, context=sdm),
                ItemState(container, context=sdm),
            )
        except InventoryError as exc:
            return False, exc.user_message
        return True, ""


@dataclass
class PutInAction(Action):
    """Insert a physical directly carried item with a declared container choice."""

    key: str = "put_in"
    name: str = "Put In"
    icon: str = "box"
    category: str = "items"
    action_category: ActionCategory = ActionCategory.PHYSICAL
    target_type: TargetType = TargetType.SINGLE
    objectdb_target_kwargs: ClassVar[frozenset[str]] = frozenset({"target", "container"})
    required_input_names: ClassVar[frozenset[str]] = frozenset({_PUT_CONTAINER})

    def get_prerequisites(self) -> list[Prerequisite]:
        return [
            *super().get_prerequisites(),
            _PutInItemPrerequisite(action=self),
            _PutInContainerPrerequisite(action=self),
        ]

    def is_applicable(self, actor: ObjectDB, *, kwargs: dict[str, Any]) -> bool:
        item = _put_item(actor, kwargs)
        if item is None:
            return False
        sdm = SceneDataManager()
        try:
            validate_put_in_item(CharacterState(actor, context=sdm), ItemState(item, context=sdm))
        except InventoryError:
            return False
        return True

    def _emit_intent(self, context: ActionContext, actor: ObjectDB | None) -> ActionResult | None:
        if actor is None or MENU_TARGET_KEY not in context.kwargs:
            return super()._emit_intent(context, actor)
        # Only the selected destination is separated; source assertions remain.
        source_context = ActionContext(
            action=self,
            actor=actor,
            target=context.target,
            kwargs=_put_source_kwargs(context.kwargs),
            scene_data=context.scene_data,
        )

        def emit_put_intent(bound_context, bound_actor):
            from flows.constants import EventName  # noqa: PLC0415
            from flows.emit import emit_event  # noqa: PLC0415

            original = bound_context.kwargs.get("target")
            intent = _PutInIntentPayload(
                actor=bound_actor,
                action_key=self.key,
                target=original,
                container_item_id=context.kwargs.get(_PUT_CONTAINER),
            )
            stack = emit_event(EventName.ACTION_INTENT, intent, location=bound_actor.location)
            if stack.was_cancelled():
                return ActionResult(
                    success=False, message=intent.cancel_message or "Something prevents you."
                )
            if intent.target is not original:
                bound_context.kwargs["target"] = intent.target
            context.kwargs[_PUT_CONTAINER] = intent.container_item_id
            return None

        cancelled = emit_typed_item_intent(source_context, actor, emit_put_intent)
        context.kwargs[MENU_TARGET_KEY] = source_context.kwargs.get(MENU_TARGET_KEY)
        return cancelled

    def container_candidate_page(
        self, actor: ObjectDB, *, kwargs: dict[str, Any], after_pk: int | None, page_size: int
    ) -> tuple[tuple[dict[str, Any], ...], int | None]:
        """Read one stable page of visible carried containers."""
        if MENU_TARGET_KEY not in kwargs or not self.is_applicable(actor, kwargs=kwargs):
            return (), None
        from django.db.models import Q  # noqa: PLC0415

        scope = Q(game_object__db_location=actor)
        if actor.location is not None:
            scope |= Q(game_object__db_location=actor.location)
        base = (
            ItemInstance.objects.in_play()
            .filter(scope, contained_in__isnull=True, template__is_container=True)
            .select_related("game_object")
            .order_by("pk")
        )
        if after_pk is not None:
            base = base.filter(pk__gt=after_pk)
        page = list(base[: page_size + 1])
        has_more = len(page) > page_size
        containers = page[:page_size]
        rows = []
        item = _put_item(actor, kwargs)
        for container in containers:
            values = {**kwargs, _PUT_CONTAINER: container.pk}
            if _put_container(actor, values, item) is None:
                continue
            resolved = resolve_menu_target(
                actor, MenuTargetRequest(MenuTargetKind.ITEMS, container.pk)
            )
            if resolved is None:
                continue
            checked = self.check_availability(
                actor, context={"kwargs": values}, pending_inputs=frozenset()
            )
            rows.append(
                {
                    "container_item_id": container.pk,
                    "name": resolved.label,
                    "_carried_by_actor": (
                        container.game_object is not None
                        and container.game_object.db_location_id == actor.pk
                    ),
                    "available": checked.available,
                    "reasons": list(checked.reasons),
                }
            )
        next_pk = containers[-1].pk if has_more and containers else None
        return tuple(rows), next_pk

    def container_candidates(
        self, actor: ObjectDB, *, kwargs: dict[str, Any]
    ) -> tuple[dict[str, Any], ...]:
        """Read visible root containers with this action's complete pair checks."""

        rows = []
        after_pk = None
        while True:
            page, next_pk = self.container_candidate_page(
                actor, kwargs=kwargs, after_pk=after_pk, page_size=25
            )
            rows.extend(page)
            if next_pk is None:
                return tuple(rows)
            after_pk = next_pk

    def execute(
        self, actor: ObjectDB, context: ActionContext | None = None, **kwargs: Any
    ) -> ActionResult:
        item, container, reason = _put_pair(self, actor, kwargs)
        if reason:
            return ActionResult(success=False, message=reason)
        sdm = context.scene_data if context else SceneDataManager()
        item_state = ItemState(item, context=sdm)
        container_state = ItemState(container, context=sdm)
        try:
            validate_put_in(CharacterState(actor, context=sdm), item_state, container_state)
        except InventoryError as exc:
            return ActionResult(success=False, message=exc.user_message)
        actor_state = sdm.initialize_state_for_object(actor)
        try:
            put_in(actor_state, item_state, container_state)
        except InventoryError as exc:
            return ActionResult(success=False, message=exc.user_message)
        message_location(
            actor_state,
            "$You() $conj(put) {target} into {container}.",
            mapping={
                "target": item_state.instance.display_name,
                "container": container_state.instance.display_name,
            },
        )
        return ActionResult(success=True)


_TAKING_UNAVAILABLE = "That isn't available."
_STEAL_TARGET_KINDS = frozenset({MenuTargetKind.ITEMS, MenuTargetKind.OBJECTS})
_TAKE_OUT_TARGET_KINDS = frozenset({MenuTargetKind.ITEMS})


def _taking_item(actor, kwargs, action):
    if MENU_TARGET_KEY in kwargs:
        resolved = resolve_typed_item(actor, kwargs, allowed_kinds=action.allowed_target_kinds)
        return resolved.item if resolved is not None else None
    return resolve_item_instance(kwargs.get("target"))


def _taking_check(action, actor, target=None, context=None):
    context = context or {}
    kwargs = dict(context.get("kwargs", {}))
    if MENU_TARGET_KEY not in kwargs and _EQUIPMENT_TARGET_KEY not in kwargs:
        kwargs["target"] = target
    item = _taking_item(actor, kwargs, action)
    if MENU_TARGET_KEY in kwargs:
        if item is None or not action.is_applicable(actor, kwargs=kwargs):
            return False, _TAKING_UNAVAILABLE
    elif kwargs.get("target") is None:
        return False, action.missing_target_message
    elif item is None:
        return False, action.invalid_target_message
    sdm = context.get("scene_data")
    sdm = sdm if sdm is not None else SceneDataManager()
    try:
        action.validate(CharacterState(actor, context=sdm), ItemState(item, context=sdm))
    except InventoryError as exc:
        return False, exc.user_message
    return True, ""


@dataclass
class _TakeOutPrerequisite(Prerequisite):
    def is_met(self, actor, target=None, context=None):
        return _taking_check(TakeOutAction(), actor, target, context)


class _TakingAction(Action):
    """Adapt current typed identity without replacing inventory rules."""

    allowed_target_kinds: ClassVar[frozenset[MenuTargetKind]]
    missing_target_message: ClassVar[str]
    invalid_target_message: ClassVar[str]

    def _emit_intent(self, context: ActionContext, actor: ObjectDB | None) -> ActionResult | None:
        return emit_typed_item_intent(
            context, actor, super()._emit_intent, allowed_kinds=self.allowed_target_kinds
        )

    def _target_failure(self, actor, kwargs, item):
        if MENU_TARGET_KEY in kwargs:
            if item is None or not self.is_applicable(actor, kwargs=kwargs):
                return ActionResult(success=False, message=_TAKING_UNAVAILABLE)
        elif kwargs.get("target") is None:
            return ActionResult(success=False, message=self.missing_target_message)
        elif item is None:
            return ActionResult(success=False, message=self.invalid_target_message)
        return None


@dataclass
class TakeOutAction(_TakingAction):
    """Remove a contained item, retaining the existing servant reach fallback."""

    key: str = "take_out"
    name: str = "Take Out"
    icon: str = "box-open"
    category: str = "items"
    action_category: ActionCategory = ActionCategory.PHYSICAL
    target_type: TargetType = TargetType.SINGLE
    objectdb_target_kwargs: ClassVar[frozenset[str]] = frozenset({"target"})
    allowed_target_kinds: ClassVar[frozenset[MenuTargetKind]] = _TAKE_OUT_TARGET_KINDS
    missing_target_message: ClassVar[str] = "Take what out?"
    invalid_target_message: ClassVar[str] = "That can't be taken out."

    def get_prerequisites(self) -> list[Prerequisite]:
        return [*super().get_prerequisites(), _TakeOutPrerequisite()]

    def is_applicable(self, actor: ObjectDB, *, kwargs: dict[str, Any]) -> bool:
        item = _taking_item(actor, kwargs, self)
        return item is not None and item.game_object is not None and item.contained_in is not None

    @staticmethod
    def validate(character: CharacterState, item: ItemState) -> None:
        try:
            validate_take_out(character, item)
        except NotReachable:
            from world.npc_services.servant_fetch import can_servant_fetch  # noqa: PLC0415

            if not can_servant_fetch(actor=character.obj, item_instance=item.instance):
                raise

    def execute(
        self, actor: ObjectDB, context: ActionContext | None = None, **kwargs: Any
    ) -> ActionResult:
        item_instance = _taking_item(actor, kwargs, self)
        failure = self._target_failure(actor, kwargs, item_instance)
        if failure is not None:
            return failure
        sdm = context.scene_data if context else SceneDataManager()
        actor_state = sdm.initialize_state_for_object(actor)
        item_state = ItemState(item_instance, context=sdm)
        try:
            take_out(actor_state, item_state)
        except NotReachable:
            from world.npc_services.servant_fetch import (  # noqa: PLC0415
                can_servant_fetch,
                servant_fetch_item,
            )

            if can_servant_fetch(actor=actor, item_instance=item_instance):
                servant_fetch_item(actor=actor, item_instance=item_instance)
                return ActionResult(
                    success=True, message="A servant bows and departs to fetch that."
                )
            return ActionResult(success=False, message=NotReachable.user_message)
        except InventoryError as exc:
            return ActionResult(success=False, message=exc.user_message)
        message_location(
            actor_state,
            "$You() $conj(take) {target} out.",
            mapping={"target": item_instance.display_name},
        )
        return ActionResult(success=True)


@dataclass
class StealAction(_TakingAction):
    """Deliberate take denial bypass; readable scope is distinct from theft eligibility."""

    key: str = "steal"
    name: str = "Steal"
    icon: str = "hand-grab"
    category: str = "items"
    action_category: ActionCategory = ActionCategory.PHYSICAL
    target_type: TargetType = TargetType.SINGLE
    objectdb_target_kwargs: ClassVar[frozenset[str]] = frozenset({"target"})
    allowed_target_kinds: ClassVar[frozenset[MenuTargetKind]] = _STEAL_TARGET_KINDS
    missing_target_message: ClassVar[str] = "Steal what?"
    invalid_target_message: ClassVar[str] = "That can't be stolen."
    validate = staticmethod(validate_steal)

    def get_prerequisites(self) -> list[Prerequisite]:
        return [*super().get_prerequisites(), CanStealPrerequisite()]

    def is_applicable(self, actor: ObjectDB, *, kwargs: dict[str, Any]) -> bool:
        item = _taking_item(actor, kwargs, self)
        if item is None or item.game_object is None:
            return False
        sheet = actor.character_sheet
        if sheet is None or item.holder_character_sheet_id == sheet.pk:
            return False
        if ItemState(item, context=SceneDataManager()).is_in_possession(actor):
            return False
        return take_requires_steal(sheet, item)

    def execute(
        self, actor: ObjectDB, context: ActionContext | None = None, **kwargs: Any
    ) -> ActionResult:
        item_instance = _taking_item(actor, kwargs, self)
        failure = self._target_failure(actor, kwargs, item_instance)
        if failure is not None:
            return failure
        sdm = context.scene_data if context else SceneDataManager()
        actor_state = sdm.initialize_state_for_object(actor)
        item_state = ItemState(item_instance, context=sdm)
        try:
            steal(actor_state, item_state)
        except InventoryError as exc:
            return ActionResult(success=False, message=exc.user_message)
        message_location(
            actor_state,
            "$You() $conj(take) {target}.",
            mapping={"target": item_instance.display_name},
        )
        return ActionResult(success=True)


@dataclass
class SetContainerPolicyAction(Action):
    """Owner-only: set who may take items out of a container (#1909)."""

    key: str = "set_container_policy"
    name: str = "Set Container Policy"
    icon: str = "lock"
    category: str = "items"
    action_category: ActionCategory = ActionCategory.PHYSICAL
    target_type: TargetType = TargetType.SINGLE

    objectdb_target_kwargs: ClassVar[frozenset[str]] = frozenset({"target"})

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        target = kwargs.get("target")
        policy = kwargs.get("policy")
        if target is None or not policy:
            return ActionResult(success=False, message="Set the access policy on what?")

        item_instance = resolve_item_instance(target)
        if item_instance is None:
            return ActionResult(success=False, message="That isn't a container.")

        valid_policies = {choice.value for choice in ContainerAccessPolicy}
        if policy not in valid_policies:
            return ActionResult(success=False, message="That's not a valid access policy.")

        sdm = context.scene_data if context else SceneDataManager()
        actor_state = sdm.initialize_state_for_object(actor)
        container_state = ItemState(item_instance, context=sdm)

        try:
            set_container_policy(actor_state, container_state, policy)
        except InventoryError as exc:
            return ActionResult(success=False, message=exc.user_message)

        message_location(
            actor_state,
            "$You() $conj(set) {container}'s access policy.",
            mapping={"container": container_state},
        )

        return ActionResult(success=True)


@dataclass
class ActivatePermitAction(Action):
    """Activate a BuildingPermit at the actor's current location.

    Resolves the permit's ``BuildingPermitDetails`` and runs
    ``activate_permit`` (which validates the site + spawns the
    BUILDING_CONSTRUCTION project + writes ownership-event audit rows
    + sets the permit's ``consumed_at``).

    Inputs (kwargs):
    - ``target`` — the BuildingPermit ItemInstance (or anything
      ``resolve_item_instance`` accepts)
    - ``target_size`` — int 1-10
    - ``target_grandeur`` — int 1-10
    """

    key: str = "activate_permit"
    name: str = "Activate Permit"
    icon: str = "scroll"
    category: str = "items"
    action_category: ActionCategory = ActionCategory.PHYSICAL
    target_type: TargetType = TargetType.SINGLE

    objectdb_target_kwargs: ClassVar[frozenset[str]] = frozenset({"target"})

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.buildings.services import (  # noqa: PLC0415
            PermitValidationError,
            activate_permit,
        )
        from world.scenes.services import (  # noqa: PLC0415
            MissingPrimaryPersonaError,
            persona_for_character,
        )

        target = kwargs.get("target")
        if target is None:
            return ActionResult(success=False, message="Activate which permit?")
        target_size = kwargs.get("target_size")
        target_grandeur = kwargs.get("target_grandeur")
        if target_size is None or target_grandeur is None:
            return ActionResult(
                success=False,
                message="Specify target_size and target_grandeur (1-10 each).",
            )

        item_instance = resolve_item_instance(target)
        if item_instance is None:
            return ActionResult(success=False, message="That can't be activated.")
        permit_details = item_instance.building_permit_details_or_none
        if permit_details is None:
            return ActionResult(success=False, message="That's not a building permit.")

        try:
            persona = persona_for_character(actor)
        except MissingPrimaryPersonaError:
            return ActionResult(
                success=False,
                message="You don't have a persona to activate this permit with.",
            )

        site_room = actor.location
        if site_room is None:
            return ActionResult(success=False, message="You aren't anywhere to activate this.")

        try:
            project = activate_permit(
                permit_details=permit_details,
                site_room=site_room,
                acting_persona=persona,
                target_size=target_size,
                target_grandeur=target_grandeur,
            )
        except PermitValidationError as exc:
            return ActionResult(success=False, message=exc.user_message)

        return ActionResult(
            success=True,
            message=(f"Permit activated — construction project #{project.pk} opened."),
        )


def _check_technique_grant(actor: ObjectDB, grant) -> ActionResult | None:
    """Refuse a gated item grant before the item can be consumed."""
    from world.magic.exceptions import UltimateNotLearnable  # noqa: PLC0415
    from world.magic.services.gift_acquisition import enforce_not_ultimate  # noqa: PLC0415
    from world.progression.services.spends import check_requirements_for_technique  # noqa: PLC0415

    try:
        enforce_not_ultimate(grant.technique)
    except UltimateNotLearnable as exc:
        return ActionResult(success=False, message=exc.user_message)
    met, failed = check_requirements_for_technique(actor, grant.technique)
    if not met:
        from world.magic.exceptions import TechniqueRequirementsNotMet  # noqa: PLC0415

        return ActionResult(success=False, message=TechniqueRequirementsNotMet(failed).user_message)
    return None


def _prepare_technique_grant(
    actor: ObjectDB, item_instance: ItemInstance
) -> tuple[Any, ActionResult | None]:
    """Load and preflight an item's technique grant before its use is committed."""
    from world.magic.models import TechniqueGrant  # noqa: PLC0415

    grant = (
        TechniqueGrant.objects.filter(item_template=item_instance.template)
        .select_related("technique")
        .first()
    )
    return grant, _check_technique_grant(actor, grant) if grant is not None else None


def _learn_technique_grant(actor: ObjectDB, grant, result) -> None:
    """Learn an item-granted technique after successful item effects."""
    if result.check_result is not None and result.check_result.success_level <= 0:
        return
    import contextlib  # noqa: PLC0415

    from world.achievements.constants import AccessChangeSource  # noqa: PLC0415
    from world.magic.exceptions import MagicError  # noqa: PLC0415
    from world.magic.services.technique_acquisition import learn_technique  # noqa: PLC0415

    with contextlib.suppress(MagicError):
        learn_technique(
            actor.sheet_data,
            grant.technique,
            source=AccessChangeSource.TECHNIQUE_GRANT,
            ap_cost=grant.acquisition_ap_cost,
        )


@dataclass
class UseItemAction(Action):
    """Use a held consumable item, applying its on-use pool's effects."""

    key: str = "use_item"
    name: str = "Use"
    icon: str = "flask-conical"
    category: str = "items"
    action_category: ActionCategory = ActionCategory.PHYSICAL
    target_type: TargetType = TargetType.SINGLE

    objectdb_target_kwargs: ClassVar[frozenset[str]] = frozenset({"item", "target"})

    required_input_names: ClassVar[frozenset[str]] = frozenset({"use_target", "option_id"})

    def get_prerequisites(self) -> list[Prerequisite]:
        return [*super().get_prerequisites(), _UseBound(), _UseTarget(), _UseOption(), _UseBlend()]

    def is_applicable(self, actor: ObjectDB, *, kwargs: dict[str, Any]) -> bool:
        item = use_source(actor, kwargs)
        return item is not None and (
            item.template.on_use_pool_id is not None
            or item.template.appearance_effects.exists()
            or item.template.disguise_kit_effects.exists()
        )

    def use_input_spec(self, actor: ObjectDB, *, kwargs: dict[str, Any]) -> dict[str, Any]:
        item = use_source(actor, kwargs)
        if item is None:
            return {
                "required_inputs": [],
                "target_kind": None,
                "cosmetic": False,
                "descriptor": False,
                "blend": False,
            }
        template = item.template
        cosmetic = template.appearance_effects.exists()
        missing = []
        if template.on_use_target_kind is not None and USE_TARGET_KEY not in kwargs:
            missing.append("use_target")
        if (
            template.appearance_effects.filter(target_option__isnull=True).exists()
            and OPTION_ID_KEY not in kwargs
        ):
            missing.append("option_id")
        blend = (
            cosmetic
            and not template.appearance_effects.filter(
                trait__composite_option__isnull=True
            ).exists()
        )
        return {
            "required_inputs": missing,
            "target_kind": template.on_use_target_kind,
            "cosmetic": cosmetic,
            "descriptor": cosmetic,
            "blend": blend,
        }

    def use_candidate_page(  # noqa: C901, PLR0912, PLR0915
        self,
        actor: ObjectDB,
        *,
        kwargs: dict[str, Any],
        after: tuple[int, int, int] | None,
        page_size: int,
    ) -> tuple[tuple[dict[str, Any], ...], tuple[int, int, int] | None]:
        """Read a bounded target/option product page in lexicographic ID order."""
        from django.db.models import Q  # noqa: PLC0415

        from world.forms.models import FormTraitOption  # noqa: PLC0415

        if MENU_TARGET_KEY not in kwargs:
            return (), None
        item = use_source(actor, kwargs)
        if item is None or not self.is_applicable(actor, kwargs=kwargs):
            return (), None
        kind = item.template.on_use_target_kind
        if kind is not None and kind not in SUPPORTED_KINDS:
            return (), None
        account = actor.db_account
        viewer_context = (
            viewer_context_for_account(account)
            if kind == TargetKind.CHARACTER and account is not None
            else (set(), set())
        )

        effect = item.template.appearance_effects.filter(target_option__isnull=True).first()
        if effect is None:
            option_ids = None
        elif OPTION_ID_KEY in kwargs:
            option_id = kwargs[OPTION_ID_KEY]
            if type(option_id) is not int or option_id <= 0:
                return (), None
            option = (
                FormTraitOption.objects.filter(pk=option_id, trait_id=effect.trait_id)
                .values_list("pk", "sort_order", "display_name")
                .first()
            )
            if option is None:
                return (), None
            option_ids = (option,)
        else:
            option_ids = (
                FormTraitOption.objects.filter(trait_id=effect.trait_id)
                .order_by("sort_order", "pk")
                .values_list("pk", "sort_order", "display_name")
            )

        page_option_rows = None
        cursor_option_rows = None
        if option_ids is not None and not isinstance(option_ids, tuple):
            page_option_rows = tuple(option_ids[: page_size + 1])
            if not page_option_rows:
                return (), None
            if after is not None:
                cursor_option_rows = tuple(
                    option_ids.filter(
                        Q(sort_order__gt=after[1]) | Q(sort_order=after[1], pk__gt=after[2])
                    )[: page_size + 1]
                )

        fixed_target = USE_TARGET_KEY in kwargs or kind is None
        target_kind = kind
        if fixed_target:
            wire = kwargs.get(USE_TARGET_KEY)
            target_id = wire.get("target_id", 0) if isinstance(wire, dict) else 0
            target_ids = (target_id,)
        elif kind == TargetKind.ITEM:
            scope = Q(game_object__db_location=actor)
            if actor.location is not None:
                scope |= Q(game_object__db_location=actor.location)
            target_ids = (
                ItemInstance.objects.in_play()
                .filter(scope, contained_in__isnull=True, game_object__isnull=False)
                .order_by("pk")
                .values_list("pk", flat=True)
            )
        elif actor.location is not None:
            scope = Q(db_location=actor.location)
            if kind == TargetKind.ROOM:
                scope |= Q(pk=actor.location.pk)
            target_ids = ObjectDB.objects.filter(scope).order_by("pk").values_list("pk", flat=True)
        else:
            return (), None

        if fixed_target:
            target_iterator = iter(target_ids)
        else:
            if after is not None and after[0] > 0:
                target_ids = target_ids.filter(pk__gte=after[0])
            target_iterator = target_ids.iterator(chunk_size=page_size)

        rows = []
        raw_count = 0
        last_pair = after
        has_more = False
        for raw_target_id in target_iterator:
            target_id = int(raw_target_id)
            if option_ids is None:
                if after is not None and after[0] == target_id:
                    continue
                page_options = ((None, 0, ""),)
            elif isinstance(option_ids, tuple):
                page_options = tuple(
                    option
                    for option in option_ids
                    if after is None
                    or target_id != after[0]
                    or (option[1], option[0]) > (after[1], after[2])
                )
            else:
                remaining = page_size - raw_count
                options = (
                    cursor_option_rows
                    if after is not None and target_id == after[0]
                    else page_option_rows
                )
                page_options = options[: remaining + 1]
            if not page_options:
                continue
            for option_id, option_sort_order, option_name in page_options:
                if raw_count >= page_size:
                    has_more = True
                    break
                raw_count += 1
                last_pair = (target_id, option_sort_order, option_id or 0)
                if fixed_target:
                    wire = kwargs.get(USE_TARGET_KEY)
                elif target_kind == TargetKind.ITEM:
                    wire = {"kind": "items", "target_id": target_id}
                else:
                    wire = {"kind": "objects", "target_id": target_id}
                values = dict(kwargs)
                if wire is not None:
                    values[USE_TARGET_KEY] = dict(wire)
                if option_id is not None:
                    values[OPTION_ID_KEY] = option_id
                target, reason = use_target(actor, values, item)
                if reason:
                    continue
                checked = self.check_availability(
                    actor, context={"kwargs": values}, pending_inputs=frozenset()
                )
                rows.append(
                    {
                        "use_target": wire,
                        "target_name": (
                            "Yourself"
                            if target is None
                            else target_label(actor, target, viewer_context=viewer_context)
                        ),
                        "option_id": option_id,
                        "option_name": option_name,
                        "available": checked.available,
                        "reasons": list(checked.reasons),
                    }
                )
            if has_more:
                break
            if fixed_target:
                break
        return tuple(rows), last_pair if has_more else None

    def use_candidates(
        self, actor: ObjectDB, *, kwargs: dict[str, Any]
    ) -> tuple[dict[str, Any], ...]:
        if MENU_TARGET_KEY not in kwargs:
            return ()
        item = use_source(actor, kwargs)
        if item is None or not self.is_applicable(actor, kwargs=kwargs):
            return ()
        kind = item.template.on_use_target_kind
        if kind is not None and kind not in SUPPORTED_KINDS:
            return ()
        targets = candidate_targets(actor, kwargs, item)
        options = candidate_options(kwargs, item)
        rows = []
        for wire, label in targets:
            for option_id, option_label in options:
                values = dict(kwargs)
                if wire is not None:
                    values["use_target"] = dict(wire)
                if option_id is not None:
                    values["option_id"] = option_id
                checked = self.check_availability(
                    actor, context={"kwargs": values}, pending_inputs=frozenset()
                )
                rows.append(
                    {
                        "use_target": wire,
                        "target_name": label,
                        "option_id": option_id,
                        "option_name": option_label,
                        "available": checked.available,
                        "reasons": list(checked.reasons),
                    }
                )
        return tuple(rows)

    def _emit_intent(self, context: ActionContext, actor: ObjectDB | None) -> ActionResult | None:
        if actor is None or MENU_TARGET_KEY not in context.kwargs:
            return super()._emit_intent(context, actor)
        # The existing adapter owns source redirect conversion and assertions.
        bound_context = ActionContext(
            action=self,
            actor=actor,
            target=context.target,
            kwargs=source_values(context.kwargs),
            scene_data=context.scene_data,
        )

        def emit_use_intent(
            source_context: ActionContext, _bound_actor: ObjectDB | None
        ) -> ActionResult | None:
            item = use_source(actor, context.kwargs)
            effect_target, _ = (
                use_target(actor, context.kwargs, item) if item is not None else (None, UNAVAILABLE)
            )
            original_item = source_context.kwargs.get("target")
            original_wire = context.kwargs.get("use_target")
            intent = UseIntentPayload(
                actor=actor,
                action_key=self.key,
                target=effect_target,
                item_target=original_item,
                use_target=original_wire,
                option_id=context.kwargs.get("option_id"),
                descriptor=context.kwargs.get("descriptor"),
                blend=context.kwargs.get("blend", False),
            )
            stack = emit_event(EventName.ACTION_INTENT, intent, location=actor.location)
            if stack.was_cancelled():
                return ActionResult(
                    success=False, message=intent.cancel_message or "Something prevents you."
                )
            source_context.kwargs["target"] = intent.item_target
            if intent.use_target is not original_wire:
                context.kwargs["use_target"] = intent.use_target
            elif intent.target is not effect_target:
                redirected = intent.target
                if type(redirected) is int and redirected > 0:
                    redirected = ObjectDB.objects.filter(pk=redirected).first()
                if isinstance(redirected, ObjectDB):
                    redirected_item = resolve_item_instance(redirected)
                    is_item = (
                        item is not None and item.template.on_use_target_kind == TargetKind.ITEM
                    )
                    context.kwargs["use_target"] = (
                        {"kind": "items", "target_id": redirected_item.pk}
                        if is_item and redirected_item is not None
                        else {"kind": "objects", "target_id": redirected.pk}
                    )
                else:
                    context.kwargs["use_target"] = None
            for name, value in (
                ("option_id", intent.option_id),
                ("descriptor", intent.descriptor),
                ("blend", intent.blend),
            ):
                if (
                    name in context.kwargs
                    or (value is not None and name != BLEND_KEY)
                    or (name == BLEND_KEY and value is not False)
                ):
                    context.kwargs[name] = value
            return None

        cancelled = emit_typed_item_intent(bound_context, actor, emit_use_intent)
        context.kwargs[MENU_TARGET_KEY] = bound_context.kwargs.get(MENU_TARGET_KEY)
        return cancelled

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        for initialize in (False, True):
            checked = self.check_availability(
                actor,
                target=kwargs.get("target"),
                context={"kwargs": kwargs, "scene_data": context.scene_data if context else None},
                pending_inputs=frozenset(),
            )
            if not checked.available:
                return ActionResult(success=False, message="; ".join(checked.reasons))
            if not initialize:
                sdm = context.scene_data if context else SceneDataManager()
                sdm.initialize_state_for_object(actor)
        item_instance = use_source(actor, kwargs)
        if item_instance is None:
            return ActionResult(success=False, message=UNAVAILABLE)
        target, reason = use_target(actor, kwargs, item_instance)
        if reason:
            return ActionResult(success=False, message=reason)
        try:
            option_id, descriptor, blend = scalar_values(kwargs)
        except ValueError as exc:
            return ActionResult(success=False, message=str(exc))

        # Preflight grants before use_item() commits item consumption.
        grant, refusal = _prepare_technique_grant(actor, item_instance)
        if refusal is not None:
            return refusal

        result = self._use(
            actor,
            item_instance,
            target,
            option_id=option_id,
            descriptor=descriptor,
            blend=blend,
            consent=kwargs.get("makeover_consent"),
        )
        if isinstance(result, ActionResult):
            return result

        if grant is not None:
            _learn_technique_grant(actor, grant, result)

        sdm = context.scene_data if context else SceneDataManager()
        actor_state = sdm.initialize_state_for_object(actor)
        message_location(
            actor_state,
            "$You() $conj(use) {item}.",
            mapping={"item": item_instance.display_name},
        )
        return ActionResult(
            success=True,
            data={
                "charges_remaining": result.charges_remaining,
                "destroyed": result.destroyed,
                "applied_effect_count": len(result.applied_effects),
                "appearance_changes": len(result.appearance_changes),
            },
        )

    def _use(  # noqa: PLR0913 - the validated use inputs, one keyword each
        self,
        actor: ObjectDB,
        item_instance: ItemInstance,
        target: ObjectDB | None,
        *,
        option_id: int | None,
        descriptor: str | None,
        blend: bool,
        consent: object,
    ) -> UseItemResult | ActionResult:
        """Run ``use_item``; a refusal, or an ask recorded instead (#4187), is an ActionResult."""
        try:
            return use_item(
                item_instance=item_instance,
                user=actor,
                target=target,
                descriptor=descriptor,
                option_id=option_id,
                blend=blend,
                consent=consent,
            )
        except MakeoverRequiresConsent:
            # Restyling someone on "Ask me": record the ask instead. Nothing was
            # spent; the grant path re-enters this action with the accepted row.
            return self._offer_makeover(actor, target, item_instance, option_id, blend, descriptor)
        except ItemError as exc:
            return ActionResult(success=False, message=exc.user_message)

    @staticmethod
    def _offer_makeover(  # noqa: PLR0913 - the validated use inputs, as use_item took them
        actor: ObjectDB,
        target: ObjectDB | None,
        item_instance: ItemInstance,
        option_id: int | None,
        blend: bool,
        descriptor: str | None,
    ) -> ActionResult:
        from world.items.services.makeover_requests import (  # noqa: PLC0415
            offer_line,
            offer_makeover,
        )

        if target is None:
            return ActionResult(success=False, message=UNAVAILABLE)
        try:
            request = offer_makeover(
                user=actor,
                target=target,
                item_instance=item_instance,
                option_id=option_id,
                blend=blend,
                descriptor=descriptor,
            )
        except ItemError as exc:
            return ActionResult(success=False, message=exc.user_message)
        return ActionResult(
            success=True,
            message=offer_line(request),
            data={"makeover_request_id": request.pk},
        )


@dataclass
class GrantItemAction(Action):
    """JUNIOR-tier GM action: grant an ItemTemplate to a target character (#707, #2117).

    Ad-hoc narrative item grant -- for story-earned moments where a GM
    hand-awards a specific touchstone or reagent. No shop/merchant system
    exists in this codebase; this action IS the acquisition channel. Wraps
    ``world.items.services.narrative_grants.grant_touchstone_item_to_character``
    (the same service the Mission ITEM reward sink calls).

    Dispatch convention
    -------------------
    REGISTRY ActionRef: ``registry_key="grant_item"``, ``target_name=<str>``,
    ``template_name=<str>``. Resolution (target search + template lookup)
    happens in ``execute()``, mirroring the pre-#2117 ``CmdGrantItem._run``
    lookups exactly (including the global-search breadth, unchanged by this
    fix -- see the #2117 spec's deferred-follow-up note).

    Gated on ``MinimumGMLevelPrerequisite(GMLevel.JUNIOR)`` (staff bypass
    preserved) -- creates a permanent ItemInstance with no shop/economy
    backstop to reverse it, the same "proven, not just approved" bar as
    ``SetSituationAction``.
    """

    key: str = "grant_item"
    name: str = "Grant Item"
    icon: str = "gift"
    category: str = "gm"
    action_category: ActionCategory = ActionCategory.PHYSICAL
    target_type: TargetType = TargetType.SELF

    def get_prerequisites(self) -> list[Prerequisite]:
        return [MinimumGMLevelPrerequisite(GMLevel.JUNIOR)]

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.items.models import ItemTemplate  # noqa: PLC0415
        from world.items.services.narrative_grants import (  # noqa: PLC0415
            grant_touchstone_item_to_character,
        )

        target_name = (kwargs.get("target_name") or "").strip()
        template_name = (kwargs.get("template_name") or "").strip()
        if not target_name or not template_name:
            return ActionResult(
                success=False,
                message="Usage: grant_item <character>=<item template name>",
            )

        target = actor.search(target_name, global_search=True)
        if target is None:
            # search() already messaged the actor with a not-found/ambiguous notice.
            return ActionResult(success=False)

        sheet = target.character_sheet
        if sheet is None:
            return ActionResult(success=False, message="That is not a character.")

        template = ItemTemplate.objects.filter(name__iexact=template_name).first()
        if template is None:
            return ActionResult(
                success=False,
                message=f"No item template found named '{template_name}'.",
            )

        granted_by = actor.account
        grant_touchstone_item_to_character(
            character_sheet=sheet, template=template, granted_by=granted_by
        )
        return ActionResult(success=True, message=f"Granted '{template.name}' to {target.key}.")
