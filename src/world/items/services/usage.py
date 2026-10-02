"""Service: using items and consuming charges (issue #509)."""

from __future__ import annotations

import contextlib
import logging
from typing import TYPE_CHECKING

from django.db import transaction
from django.utils import timezone
from evennia.objects.models import ObjectDB

if TYPE_CHECKING:
    from world.forms.models import CharacterFormState, FormTrait, FormTraitOption
    from world.items.models import ItemTemplate

from world.checks.consequence_resolution import (
    apply_pool_deterministically,
    apply_resolution,
    resolve_pool_consequences,
    select_consequence,
)
from world.checks.types import ResolutionContext
from world.items.constants import OwnershipEventType
from world.items.exceptions import (
    BlendNotSupported,
    ItemNotAttuned,
    ItemNotUsable,
    MakeoverNotPermitted,
    NoChargesRemaining,
    NotReachable,
    StyleChoiceRequired,
    StyleNotKnown,
    VaultFull,
)
from world.items.models import EquippedItem, ItemInstance, OwnershipEvent
from world.items.types import UseItemResult

logger = logging.getLogger(__name__)


def hard_delete_item_instance(item_instance: ItemInstance) -> None:
    """Permanently remove an instance and its whole footprint: its own ledger
    rows first (so no OwnershipEvent is orphaned to a null FK), then the backing
    game_object if present (CASCADE removes the row) else the row directly.

    Used by both the destruction-at-0-charges path (#509) and the time-based
    soft-delete cleanup (#1025). Caller owns the transaction."""
    item_instance.ownership_events.all().delete()
    if item_instance.game_object_id is not None:
        item_instance.game_object.delete()  # CASCADE removes the ItemInstance row
    else:
        item_instance.delete()


def destroy_consumed_item_instance(
    item_instance: ItemInstance,
    *,
    preserve: bool | None = None,
    note: str,
    event_type: str = OwnershipEventType.CONSUMED,
) -> None:
    """THE rule for an instance used up entirely (#509, #1025, #4099). Call it, never
    ``ItemInstance.delete()``, whenever consumption empties an instance.

    - ``preserve`` (default ``item_instance.differs_from_template``): the instance carries
      per-instance data or provenance, so it is SOFT-deleted: ``destroyed_at`` is stamped,
      its game object leaves play (``location = None``, kept, not deleted) and a CONSUMED
      ``OwnershipEvent`` records ``note``.
    - otherwise a bare throwaway: ``hard_delete_item_instance`` removes the whole
      footprint, game object included.

    Either way nothing is left on the holder: a bare ``ItemInstance.delete()`` leaves the
    game object (``game_object`` cascades the other way) sitting in the character's
    inventory as a ghost. The holder's ``carried_items`` cache is invalidated. Pass
    ``preserve`` explicitly only when the caller knows better than
    ``differs_from_template``: it captured the answer before writing an event of its own
    (``consume_item_charges``), or a PROTECT reference forbids a hard delete (a project
    contribution). ``event_type`` is the ledger entry the soft-delete writes: CONSUMED
    for use, TRANSFERRED (to no receiver) for an item that changed hands out of play,
    such as one sold to a fence. Mutates the instance in place and saves with
    ``update_fields`` (ADR-0008); caller owns the transaction.

    **A soft-deleted item is held by nobody** (#4099 re-review ruling): the soft-delete
    clears ``holder_character_sheet`` and ``contained_in``, so no "fetch by pk, then
    compare the holder" check and no container-chain walk can treat it as anyone's.
    The last holder is the event's ``from_character_sheet`` (read it with
    ``provenance.last_holder``). A destroyed container's contents are never destroyed
    with it: they spill to where the container was (``_spill_contents``).
    """
    if preserve is None:
        preserve = item_instance.differs_from_template
    # An item leaving play is no longer worn: unequip through the canonical service,
    # which also invalidates the wearer's equipped_items handler.
    from world.items.services.equip import unequip_item  # noqa: PLC0415

    for equipped in EquippedItem.objects.filter(item_instance=item_instance).select_related(
        "character"
    ):
        unequip_item(equipped_item=equipped)
    game_object = item_instance.game_object
    holder_object = game_object.location if game_object is not None else None
    _spill_contents(item_instance, landing=holder_object)
    if preserve:
        _take_out_of_play(item_instance, event_type=event_type, note=note)
    else:
        hard_delete_item_instance(item_instance)
    if holder_object is not None and hasattr(holder_object, "carried_items"):
        holder_object.carried_items.invalidate()


def _take_out_of_play(item_instance: ItemInstance, *, event_type: str, note: str) -> None:
    """The soft-delete: stamped, held by nobody, uncontained, game object out of play.

    The ledger event records who held it last. Shared by
    ``destroy_consumed_item_instance`` and ``forfeit_item_instance`` so both soft-delete
    paths clear the same pointers.
    """
    former_holder = item_instance.holder_character_sheet
    item_instance.destroyed_at = timezone.now()
    item_instance.holder_character_sheet = None
    item_instance.contained_in = None
    item_instance.save(
        update_fields=[
            "destroyed_at",
            "holder_character_sheet",
            "contained_in",
            "quantity",
            "charges",
        ]
    )
    game_object = item_instance.game_object
    if game_object is not None:
        # Relocate, never delete: the preserved row keeps its game object. The
        # location setter persists db_location itself; no second full save.
        game_object.location = None
    OwnershipEvent.objects.create(
        item_instance=item_instance,
        event_type=event_type,
        from_character_sheet=former_holder,
        notes=note,
    )


def _spill_contents(
    container: ItemInstance,
    *,
    # A landing is wherever the container was: a carrying character or a room.
    landing: ObjectDB | None,  # noqa: OBJECTDB_PARAM
) -> None:
    """A destroyed container's contents spill out; they are never destroyed with it.

    Mirrors ``take_out`` (``flows/service_functions/inventory.py``). Each content moves
    up one level. For a pouch inside a bag, ``contained_in`` becomes the bag and the
    game object moves into the bag's game object. Otherwise ``contained_in`` is cleared
    and the game object moves to ``landing``, where the container was: the carrier, so
    it stays in their inventory, or the room.

    If the container was nowhere (no landing), contents go to the former holder's
    character, else to their own Evennia ``home``. Holders are untouched. A spill into a
    vault room respects its capacity, as ``drop`` does (``VaultFull``). A refused
    ``move_to`` raises ``NotReachable``, as ``take_out`` does. Only containers are
    queried.
    """
    if not container.template.is_container:
        return
    contents = list(
        ItemInstance.objects.filter(contained_in=container).select_related("game_object")
    )
    if not contents:
        return
    parent = container.contained_in
    holder_sheet = container.holder_character_sheet
    fallback = holder_sheet.character if holder_sheet is not None else None
    for content in contents:
        content.contained_in = parent
        content.save(update_fields=["contained_in"])
        game_object = content.game_object
        if game_object is None:
            continue
        if parent is not None and parent.game_object is not None:
            target = parent.game_object
        else:
            target = landing or fallback or game_object.home
        if target is None:
            logger.warning(
                "Spilled item %s has no landing, holder or home; it stays where it was.",
                content.pk,
            )
            continue
        _assert_spill_fits(target)
        if not game_object.move_to(target, quiet=True):
            raise NotReachable


def _assert_spill_fits(
    target: ObjectDB,  # noqa: OBJECTDB_PARAM - a spill lands on a character or a room
) -> None:
    """A spill into a vault room respects its capacity, exactly as ``drop`` does."""
    if hasattr(target, "carried_items"):
        return  # a character, not a room
    from evennia_extensions.models import RoomProfile  # noqa: PLC0415
    from world.room_features.vault_services import (  # noqa: PLC0415
        vault_capacity_remaining,
        vault_for_room,
    )

    profile = RoomProfile.objects.filter(objectdb=target).first()
    vault = vault_for_room(profile) if profile is not None else None
    if vault is not None and vault_capacity_remaining(vault) <= 0:
        raise VaultFull


def _invalidate_caches(item_instance: ItemInstance) -> None:
    for attr in ("effective_weapon_damage", "effective_armor_soak"):
        with contextlib.suppress(AttributeError):
            delattr(item_instance, attr)
    for equipped in EquippedItem.objects.filter(item_instance=item_instance):
        # EquippedItem.character is a CharacterSheet; the cached handler hangs off its
        # Character typeclass, not the sheet's related manager.
        equipped.character.character.equipped_items.invalidate()


@transaction.atomic
def consume_item_charges(*, item_instance: ItemInstance, amount: int = 1) -> ItemInstance:
    """Spend ``amount`` charges atomically (row-locked). Logs ACTIVATED; at 0
    charges logs CONSUMED and destroys the instance — soft-delete if it carries
    per-instance data (``differs_from_template``), else hard-delete. Raises
    NoChargesRemaining when already empty."""
    locked = ItemInstance.objects.select_for_update().get(pk=item_instance.pk)
    if locked.charges <= 0:
        raise NoChargesRemaining
    # Capture BEFORE logging ACTIVATED: differs_from_template counts any
    # non-CREATED ownership event, so the event we are about to write would
    # otherwise flip a bare throwaway into the soft-delete branch.
    preserve = locked.differs_from_template
    locked.charges = max(0, locked.charges - amount)
    locked.save(update_fields=["charges"])
    OwnershipEvent.objects.create(
        item_instance=locked,
        event_type=OwnershipEventType.ACTIVATED,
        from_character_sheet=locked.holder_character_sheet,
    )
    _invalidate_caches(locked)
    if locked.charges == 0:
        destroy_consumed_item_instance(
            locked, preserve=preserve, note="Consumed: final charge spent."
        )
    return locked


@transaction.atomic
def forfeit_item_instance(*, item_instance: ItemInstance, note: str = "") -> ItemInstance:
    """Soft-forfeit an instance: pull it out of play as a story consequence.

    Used by stake resolution (#1770 PR2 — an ITEM stake's branch fired). Always
    a soft-delete (stamps ``destroyed_at``, relocates the game_object out of
    play) — a forfeited item is story-significant provenance, never
    hard-deleted. Writes a TRANSFERRED OwnershipEvent with no receiver: the
    item changed hands away from its holder to the story (the most honest
    existing event type; CONSUMED implies use, which this is not).
    Idempotent: already-forfeited/destroyed instances return unchanged.
    """
    locked = ItemInstance.objects.select_for_update().get(pk=item_instance.pk)
    if locked.destroyed_at is not None:
        return locked
    # Always preserved: a forfeited item is story-significant provenance. The shared
    # helper clears holder and container (#4099), spills any contents and unequips.
    destroy_consumed_item_instance(
        locked,
        preserve=True,
        note=note or "Forfeited — staked and lost.",
        event_type=OwnershipEventType.TRANSFERRED,
    )
    _invalidate_caches(locked)
    return locked


def _apply_on_use_pool(template: ItemTemplate, user: ObjectDB, context: ResolutionContext) -> tuple:
    """Apply an item's on-use pool, returning ``(check_result, applied)``.

    Deterministic pools (no check type) apply directly; check-gated pools
    roll a consequence selection first. When the template has no on-use pool,
    both return values are ``None`` / ``[]``.

    Args:
        template: The item template whose pool (if any) to apply.
        user: The acting character's ``ObjectDB``.
        context: The resolution context for consequence application.

    Returns:
        A ``(check_result, applied_effects)`` tuple.
    """
    if template.on_use_pool_id is None:
        return None, []
    if template.on_use_check_type_id is None:
        applied = apply_pool_deterministically(pool=template.on_use_pool, context=context)
        return None, applied
    pending = select_consequence(
        user,
        template.on_use_check_type,
        template.on_use_difficulty,
        resolve_pool_consequences(template.on_use_pool),
    )
    applied = apply_resolution(pending, context)
    return pending.check_result, applied


def validate_item_use_bound(*, item_instance: ItemInstance, user: ObjectDB) -> None:
    """Reject unusable, depleted or unattuned items without choosing inputs."""
    template = item_instance.template
    if (
        template.on_use_pool_id is None
        and not template.appearance_effects.exists()
        and not template.disguise_kit_effects.exists()
    ):
        raise ItemNotUsable
    if template.is_consumable and item_instance.charges <= 0:
        raise NoChargesRemaining
    if template.requires_attunement:
        acting_sheet = user.character_sheet
        acting_sheet_pk = acting_sheet.pk if acting_sheet is not None else None
        if item_instance.attuned_to_character_sheet_id != acting_sheet_pk:
            raise ItemNotAttuned


def validate_item_use_target(
    *, item_instance: ItemInstance, user: ObjectDB, target: ObjectDB | None
) -> None:
    """Retain cosmetic consent; its category lookup can lazily create a row."""
    if item_instance.template.appearance_effects.exists() and target is not None and target != user:
        _require_makeover_consent(user, target)


def validate_item_use_option(
    *, item_instance: ItemInstance, user: ObjectDB, option_id: int | None
) -> FormTraitOption | None:
    """Resolve the existing first choose-at-use option and actor knowledge."""
    if not item_instance.template.appearance_effects.exists():
        return None
    chosen_option = _resolve_choose_at_use_option(item_instance.template, option_id)
    _require_style_knowledge(user, chosen_option)
    return chosen_option


def validate_item_use_blend(*, item_instance: ItemInstance, blend: bool) -> None:
    """Check all cosmetic traits support the existing requested blend."""
    if blend and item_instance.template.appearance_effects.exists():
        _require_blendable(item_instance.template)


def _run_pre_charge_gates(
    *,
    locked: ItemInstance,
    user: ObjectDB,
    target: ObjectDB | None,
    option_id: int | None,
    blend: bool,
) -> FormTraitOption | None:
    """Run every existing service refusal in order before effects or charges."""
    validate_item_use_bound(item_instance=locked, user=user)
    if not locked.template.appearance_effects.exists():
        return None
    validate_item_use_target(item_instance=locked, user=user, target=target)
    chosen_option = validate_item_use_option(item_instance=locked, user=user, option_id=option_id)
    validate_item_use_blend(item_instance=locked, blend=blend)
    return chosen_option


@transaction.atomic
def use_item(  # noqa: PLR0913
    *,
    item_instance: ItemInstance,
    user: ObjectDB,
    target: ObjectDB | None = None,
    descriptor: str | None = None,
    option_id: int | None = None,
    blend: bool = False,
) -> UseItemResult:
    """Use an item with an on-use pool: apply its effects (deterministic when the
    template has no on_use_check_type, else check-gated). Consumables spend one
    charge (regardless of check outcome) and are destroyed at zero; non-consumable
    usable items are reusable and keep their charges. user/target are ObjectDBs.

    ``descriptor`` (#2632, cosmetic items only) is free-text presentation flavor
    for the restyled trait — "raven shot through with silver streaks" over a
    normalized hair color, the multi-color/ornate-work channel. An appearance
    use REPLACES the trait's presentation: the descriptor becomes the given
    text, or is cleared when none is given (you dyed over the old look).

    ``option_id`` (#2632) selects the target value for a CHOOSE-AT-USE cosmetic
    (an appearance effect with a null ``target_option`` — the one Styling Kit
    picks the style; Ariwn Lenses take "a drop of dye" in any color). Required
    for such items; ignored for fixed-option cosmetics.

    ``blend=True`` (#2632) ADDS the color instead of replacing — green dye onto
    black hair yields the trait's composite value (multihued/mismatched) with
    the ACTUAL components kept as ordered rows, so the normalized layer renders
    "Black-Green" honestly even under descriptor concealment. Only traits with
    a composite option blend (BlendNotSupported otherwise, checked pre-charge).

    Exotic (requires_teaching) choose-at-use options are gated on the ACTING
    character knowing them (StyleNotKnown, pre-charge); a successful
    application teaches the recipient — you learn a look by having it done."""
    locked = ItemInstance.objects.select_for_update().get(pk=item_instance.pk)
    template = locked.template
    chosen_option = _run_pre_charge_gates(
        locked=locked,
        user=user,
        target=target,
        option_id=option_id,
        blend=blend,
    )

    context = ResolutionContext(character=user, target=target)
    check_result, applied = _apply_on_use_pool(template, user, context)

    if template.is_consumable:
        consumed = consume_item_charges(item_instance=locked, amount=1)
        charges_remaining = consumed.charges
        destroyed = consumed.charges == 0
        soft_deleted = destroyed and consumed.destroyed_at is not None
    else:
        # Reusable on-use item: record activation, keep the item, spend no charge.
        OwnershipEvent.objects.create(
            item_instance=locked,
            event_type=OwnershipEventType.ACTIVATED,
            from_character_sheet=locked.holder_character_sheet,
        )
        _invalidate_caches(locked)
        charges_remaining = locked.charges
        destroyed = False
        soft_deleted = False

    appearance_changes = _apply_appearance_effects(
        template, user, target, descriptor, chosen_option, blend=blend
    )

    _apply_disguise_kit_effects(template, user, locked)

    return UseItemResult(
        applied_effects=applied,
        charges_remaining=charges_remaining,
        destroyed=destroyed,
        soft_deleted=soft_deleted,
        check_result=check_result,
        appearance_changes=appearance_changes,
    )


def _require_makeover_consent(user: ObjectDB, target: ObjectDB) -> None:
    """Raise MakeoverNotPermitted unless the target consents to styling (#2632).

    An NPC target (no active tenure) never blocks; a player target's makeover
    consent category gates (default allowlist — you opt your stylists in).
    """
    from world.consent.services import (  # noqa: PLC0415
        consent_blocks_targeting,
        makeover_category,
    )
    from world.roster.models import RosterTenure  # noqa: PLC0415

    def _active_tenure_for_sheet(sheet: object) -> RosterTenure | None:
        # Mirrors flows.service_functions.inventory's sheet→active-tenure resolution.
        return RosterTenure.objects.filter(
            roster_entry__character_sheet=sheet, end_date__isnull=True
        ).first()

    target_sheet = target.character_sheet
    if target_sheet is None:
        msg = "You can only restyle a character."
        raise MakeoverNotPermitted(msg)
    owner_tenure = _active_tenure_for_sheet(target_sheet)
    if owner_tenure is None:
        return  # NPC — no consent gate
    user_sheet = user.character_sheet
    actor_tenure = _active_tenure_for_sheet(user_sheet) if user_sheet else None
    if consent_blocks_targeting(
        owner_tenure=owner_tenure,
        category=makeover_category(),
        actor_tenure=actor_tenure,
    ):
        raise MakeoverNotPermitted


def _resolve_choose_at_use_option(
    template: ItemTemplate, option_id: int | None
) -> FormTraitOption | None:
    """Resolve the chosen option for a choose-at-use cosmetic (#2632).

    A choose-at-use effect (null ``target_option``) requires ``option_id`` to
    name an option OF THAT EFFECT'S TRAIT; fixed-option templates ignore
    ``option_id`` entirely. Raises StyleChoiceRequired on a missing or
    mismatched choice — callers run this before spending any charge.
    """
    from world.forms.models import FormTraitOption  # noqa: PLC0415

    open_effect = template.appearance_effects.filter(target_option__isnull=True).first()
    if open_effect is None:
        return None
    option = (
        FormTraitOption.objects.filter(pk=option_id, trait_id=open_effect.trait_id).first()
        if option_id is not None
        else None
    )
    if option is None:
        raise StyleChoiceRequired
    return option


def _require_style_knowledge(user: ObjectDB, chosen_option: FormTraitOption | None) -> None:
    """Gate exotic options on the ACTING character's knowledge (#2632).

    Applies to the chosen option of a choose-at-use cosmetic; fixed-option
    templates are authored content and don't gate. Runs pre-charge.
    """
    from world.forms.services import knows_style  # noqa: PLC0415

    if chosen_option is None or not chosen_option.requires_teaching:
        return
    sheet = user.character_sheet
    if sheet is None or not knows_style(sheet, chosen_option):
        raise StyleNotKnown


def _require_blendable(template: ItemTemplate) -> None:
    """Blends need the trait to declare a composite option (#2632). Pre-charge."""
    from world.forms.models import FormTrait  # noqa: PLC0415

    trait_ids = template.appearance_effects.values_list("trait_id", flat=True)
    if FormTrait.objects.filter(pk__in=trait_ids, composite_option__isnull=True).exists():
        raise BlendNotSupported


def _apply_appearance_effects(  # noqa: PLR0913
    template: ItemTemplate,
    user: ObjectDB,
    target: ObjectDB | None = None,
    descriptor: str | None = None,
    chosen_option: FormTraitOption | None = None,
    blend: bool = False,
) -> list[tuple[FormTrait, FormTraitOption]]:
    """Apply cosmetic appearance effects declared on the item template.

    Applies to ``target`` when one is given (PC stylists, #2632 — consent was
    checked before any charge was spent), else to the user (self-makeover).
    The stylist is recorded as ``actor_persona`` so the dye-history note shows
    who did the work.

    Returns a list of (FormTrait, FormTraitOption) pairs that were changed.
    Empty list if the template has no appearance effects or the recipient
    has no sheet (e.g., character creation never ran).
    """
    effects = list(template.appearance_effects.select_related("trait", "target_option"))
    if not effects:
        return []
    from world.forms.services import NonCosmeticTraitError, change_appearance  # noqa: PLC0415
    from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415

    recipient = target if target is not None else user
    sheet = recipient.character_sheet
    if sheet is None:
        return []

    persona = active_persona_for_sheet(sheet)
    actor_sheet = user.character_sheet
    actor_persona = active_persona_for_sheet(actor_sheet) if actor_sheet is not None else persona
    from world.forms.services import learn_style  # noqa: PLC0415

    changes = []
    for effect in effects:
        applied_option = effect.target_option or chosen_option
        if applied_option is None:
            continue  # choose-at-use with no resolution; use_item validated earlier
        try:
            change_appearance(
                recipient,
                effect.trait,
                applied_option,
                persona=persona,
                actor_persona=actor_persona,
                # Replace-or-clear (#2632): the use's flavor text, or "" so a
                # stale descriptor never describes a dyed-over look.
                descriptor=(descriptor or "").strip(),
                note=template.name,
                blend=blend,
            )
            changes.append((effect.trait, applied_option))
            # Learned by having it done (#2632): a successful exotic
            # application teaches the recipient. Idempotent; no-op for
            # ungated options and for a self-use by someone who knows it.
            learn_style(sheet, applied_option, taught_by_label=actor_persona.name)
        except NonCosmeticTraitError:
            pass  # defense-in-depth; clean() should prevent this
    return changes


def _apply_disguise_kit_effects(
    template: ItemTemplate, user: ObjectDB, kit_instance: ItemInstance
) -> CharacterFormState | None:
    """Apply disguise-kit effects declared on the item template (#2249).

    For each ``DisguiseKitEffect`` row on the template, finds or creates the
    matching DISGUISE ``CharacterForm`` for the user, then calls
    ``apply_disguise`` with the kit instance so its ``QualityTier`` is stamped
    onto ``CharacterFormState.applied_kit_instance`` for the kit-quality bonus
    in ``identification_difficulty``.

    Returns the updated ``CharacterFormState``, or ``None`` when the template
    has no disguise-kit effects or the character has no sheet.
    """
    effects = list(template.disguise_kit_effects.all())
    if not effects:
        return None
    from world.forms.models import CharacterForm, CharacterFormState, FormType  # noqa: PLC0415
    from world.forms.services import apply_disguise  # noqa: PLC0415

    sheet = user.character_sheet
    if sheet is None:
        return None

    # Build or reuse a DISGUISE form for this character.
    disguise_form, _ = CharacterForm.objects.get_or_create(
        character=user.sheet_data,
        form_type=FormType.DISGUISE,
        is_player_created=True,
    )
    for effect in effects:
        apply_disguise(
            user,
            disguise_form,
            kind=effect.disguise_kind,
            concealment_level=effect.concealment_level,
            kit_instance=kit_instance,
        )
    return CharacterFormState.objects.get(character_id=user.pk)
