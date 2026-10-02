"""Item-specific actions: equip, unequip, put_in, take_out, use_item."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar

from evennia.objects.models import ObjectDB

from actions.base import Action
from actions.constants import ActionCategory
from actions.definitions.item_helpers import (
    MENU_TARGET_KEY,
    emit_typed_item_intent,
    resolve_item_instance,
    resolve_typed_item,
)
from actions.prerequisites import (
    CanStealPrerequisite,
    HoldsItemPrerequisite,
    ItemUsablePrerequisite,
    MinimumGMLevelPrerequisite,
    OnUseTargetPrerequisite,
    Prerequisite,
)
from actions.types import ActionContext, ActionResult, TargetType
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
    unequip,
    validate_equip,
    validate_unequip,
)
from world.gm.constants import GMLevel
from world.items.constants import ContainerAccessPolicy
from world.items.exceptions import InventoryError, ItemError, NotReachable
from world.items.services.usage import use_item

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


@dataclass
class PutInAction(Action):
    """Place an item into a container."""

    key: str = "put_in"
    name: str = "Put In"
    icon: str = "box"
    category: str = "items"
    action_category: ActionCategory = ActionCategory.PHYSICAL
    target_type: TargetType = TargetType.SINGLE

    objectdb_target_kwargs: ClassVar[frozenset[str]] = frozenset({"target", "container"})

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        target = kwargs.get("target")
        container = kwargs.get("container")
        if target is None or container is None:
            return ActionResult(success=False, message="Put what into what?")

        item_instance = resolve_item_instance(target)
        if item_instance is None:
            return ActionResult(success=False, message="That can't be put away.")

        container_instance = resolve_item_instance(container)
        if container_instance is None:
            return ActionResult(success=False, message="That isn't a container.")

        sdm = context.scene_data if context else SceneDataManager()
        actor_state = sdm.initialize_state_for_object(actor)
        item_state = ItemState(item_instance, context=sdm)
        container_state = ItemState(container_instance, context=sdm)

        try:
            put_in(actor_state, item_state, container_state)
        except InventoryError as exc:
            return ActionResult(success=False, message=exc.user_message)

        message_location(
            actor_state,
            "$You() $conj(put) {target} into {container}.",
            mapping={
                "target": item_state,
                "container": container_state,
            },
        )

        return ActionResult(success=True)


@dataclass
class TakeOutAction(Action):
    """Remove an item from its container into the character's possession."""

    key: str = "take_out"
    name: str = "Take Out"
    icon: str = "box-open"
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
        if target is None:
            return ActionResult(success=False, message="Take what out?")

        item_instance = resolve_item_instance(target)
        if item_instance is None:
            return ActionResult(success=False, message="That can't be taken out.")

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
            mapping={"target": item_state},
        )

        return ActionResult(success=True)


@dataclass
class StealAction(Action):
    """Take an item that plain take/take_out refuses — with consequences (#1909).

    ``CanStealPrerequisite`` gates availability on the same target-side
    ``steal_permitted`` predicate the ``steal`` service re-checks at
    execution time (visibility = eligibility).
    """

    key: str = "steal"
    name: str = "Steal"
    icon: str = "hand-grab"
    category: str = "items"
    action_category: ActionCategory = ActionCategory.PHYSICAL
    target_type: TargetType = TargetType.SINGLE

    objectdb_target_kwargs: ClassVar[frozenset[str]] = frozenset({"target"})

    def get_prerequisites(self) -> list[Prerequisite]:
        return [CanStealPrerequisite()]

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        target = kwargs.get("target")
        if target is None:
            return ActionResult(success=False, message="Steal what?")

        item_instance = resolve_item_instance(target)
        if item_instance is None:
            return ActionResult(success=False, message="That can't be stolen.")

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
            mapping={"target": item_state},
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

    def get_prerequisites(self) -> list[Prerequisite]:
        return [
            HoldsItemPrerequisite(),
            ItemUsablePrerequisite(),
            OnUseTargetPrerequisite(),
        ]

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        item_obj = kwargs.get("item")
        item_instance = resolve_item_instance(item_obj) if item_obj is not None else None
        if item_instance is None:
            return ActionResult(success=False, message="Use what?")

        target = kwargs.get("target")  # validated by prerequisites; None = self-use
        # #2632 — optional free-text presentation flavor for cosmetic uses
        # (multi-color hair, ornate work). Ignored by non-cosmetic items.
        descriptor = (kwargs.get("descriptor") or "").strip() or None
        # #2632 — choose-at-use cosmetics (Styling Kit / Ariwn Lenses): the
        # wearer names the FormTraitOption. Ignored by fixed-option items.
        option_raw = kwargs.get("option_id")
        try:
            option_id = int(option_raw) if option_raw is not None else None
        except (TypeError, ValueError):
            return ActionResult(success=False, message="option_id must be a number.")
        # #2632 — blend adds the color (green dye onto black = Black-Green)
        # instead of replacing; only composite-capable traits accept it.
        blend = bool(kwargs.get("blend"))

        # TechniqueGrant hook: if the item template has a grant, learn the technique.
        from world.magic.models import TechniqueGrant  # noqa: PLC0415

        grant = (
            TechniqueGrant.objects.filter(item_template=item_instance.template)
            .select_related("technique")
            .first()
        )
        # Prerequisite pre-check (#4097 fix round 2): run BEFORE use_item() so an
        # item carrying a gated TechniqueGrant is never consumed on a refusal.
        # use_item() is its own @transaction.atomic block that commits the moment
        # it returns, so a post-use raise can't be rolled back to un-consume the
        # item — the check has to happen before the charge, not after.
        if grant is not None:
            from world.magic.exceptions import UltimateNotLearnable  # noqa: PLC0415
            from world.magic.services.gift_acquisition import (  # noqa: PLC0415
                enforce_not_ultimate,
            )
            from world.progression.services.spends import (  # noqa: PLC0415
                check_requirements_for_technique,
            )

            # Ultimate pre-check (#4098 fix round 1): a TechniqueGrant naming an
            # ultimate must refuse before the item is consumed — without this the
            # post-use learn_technique() call below raises UltimateNotLearnable
            # (a MagicError) and is silently swallowed, so the item would still
            # be used up for nothing instead of cleanly refusing.
            try:
                enforce_not_ultimate(grant.technique)
            except UltimateNotLearnable as exc:
                return ActionResult(success=False, message=exc.user_message)

            met, failed = check_requirements_for_technique(actor, grant.technique)
            if not met:
                from world.magic.exceptions import TechniqueRequirementsNotMet  # noqa: PLC0415

                return ActionResult(
                    success=False, message=TechniqueRequirementsNotMet(failed).user_message
                )

        try:
            result = use_item(
                item_instance=item_instance,
                user=actor,
                target=target,
                descriptor=descriptor,
                option_id=option_id,
                blend=blend,
            )
        except ItemError as exc:
            return ActionResult(success=False, message=exc.user_message)

        if grant is not None:
            # Success predicate: check_result is None (no check) or success_level > 0.
            check_ok = result.check_result is None or result.check_result.success_level > 0
            if check_ok:
                import contextlib  # noqa: PLC0415

                from world.achievements.constants import AccessChangeSource  # noqa: PLC0415
                from world.magic.exceptions import MagicError  # noqa: PLC0415
                from world.magic.services.technique_acquisition import (  # noqa: PLC0415
                    learn_technique,
                )

                # Partial-failure policy: item consumed, technique didn't take.
                # The use still succeeded; the user_message is not surfaced here
                # because the item's on-use effects already happened.
                with contextlib.suppress(MagicError):
                    learn_technique(
                        actor.sheet_data,
                        grant.technique,
                        source=AccessChangeSource.TECHNIQUE_GRANT,
                        ap_cost=grant.acquisition_ap_cost,
                    )

        sdm = context.scene_data if context else SceneDataManager()
        actor_state = sdm.initialize_state_for_object(actor)
        item_state = ItemState(item_instance, context=sdm)
        message_location(
            actor_state,
            "$You() $conj(use) {item}.",
            mapping={"item": item_state},
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
