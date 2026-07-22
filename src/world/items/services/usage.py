"""Service: using items and consuming charges (issue #509)."""

from __future__ import annotations

import contextlib
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
from world.items.exceptions import ItemNotUsable, MakeoverNotPermitted, NoChargesRemaining
from world.items.models import EquippedItem, ItemInstance, OwnershipEvent
from world.items.types import UseItemResult


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


def _invalidate_caches(item_instance: ItemInstance) -> None:
    for attr in ("effective_weapon_damage", "effective_armor_soak"):
        with contextlib.suppress(AttributeError):
            delattr(item_instance, attr)
    for equipped in EquippedItem.objects.filter(item_instance=item_instance):
        equipped.character.equipped_items.invalidate()


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
        if preserve:
            locked.destroyed_at = timezone.now()
            locked.save(update_fields=["destroyed_at"])
            game_object = locked.game_object
            if game_object is not None:
                # Deliberately relocate-but-not-delete the game_object: the
                # ItemInstance is preserved (soft-delete) for its per-instance
                # data/provenance, so we keep the row and just pull it out of
                # play (mirrors the hard-delete branch, which DOES delete).
                game_object.location = None
                game_object.save()
            OwnershipEvent.objects.create(
                item_instance=locked,
                event_type=OwnershipEventType.CONSUMED,
                from_character_sheet=locked.holder_character_sheet,
                notes="Consumed — final charge spent (preserved).",
            )
        else:
            # Bare throwaway: nothing worth preserving — remove the whole
            # footprint (no dangling CONSUMED row). #1025 convergence.
            hard_delete_item_instance(locked)
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
    holder = locked.holder_character_sheet
    locked.destroyed_at = timezone.now()
    locked.save(update_fields=["destroyed_at"])
    game_object = locked.game_object
    if game_object is not None:
        # Relocate-but-not-delete, mirroring the consume soft-delete branch:
        # the row is preserved for provenance; the object leaves play.
        game_object.location = None
        game_object.save()
    OwnershipEvent.objects.create(
        item_instance=locked,
        event_type=OwnershipEventType.TRANSFERRED,
        from_character_sheet=holder,
        notes=note or "Forfeited — staked and lost.",
    )
    _invalidate_caches(locked)
    return locked


@transaction.atomic
def use_item(
    *, item_instance: ItemInstance, user: ObjectDB, target: ObjectDB | None = None
) -> UseItemResult:
    """Use an item with an on-use pool: apply its effects (deterministic when the
    template has no on_use_check_type, else check-gated). Consumables spend one
    charge (regardless of check outcome) and are destroyed at zero; non-consumable
    usable items are reusable and keep their charges. user/target are ObjectDBs."""
    locked = ItemInstance.objects.select_for_update().get(pk=item_instance.pk)
    template = locked.template
    has_appearance_effects = template.appearance_effects.exists()
    has_disguise_kit_effects = template.disguise_kit_effects.exists()
    if (
        template.on_use_pool_id is None
        and not has_appearance_effects
        and not has_disguise_kit_effects
    ):
        raise ItemNotUsable
    if template.is_consumable and locked.charges <= 0:
        raise NoChargesRemaining

    # Styling someone else (#2632): consent-gate BEFORE any charge is spent,
    # so a refused makeover never burns a dye.
    if has_appearance_effects and target is not None and target != user:
        _require_makeover_consent(user, target)

    context = ResolutionContext(character=user, target=target)
    check_result = None
    applied: list = []
    if template.on_use_pool_id is not None:
        if template.on_use_check_type_id is None:
            applied = apply_pool_deterministically(pool=template.on_use_pool, context=context)
        else:
            pending = select_consequence(
                user,
                template.on_use_check_type,
                template.on_use_difficulty,
                resolve_pool_consequences(template.on_use_pool),
            )
            applied = apply_resolution(pending, context)
            check_result = pending.check_result

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

    appearance_changes = _apply_appearance_effects(template, user, target)

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


def _apply_appearance_effects(
    template: ItemTemplate, user: ObjectDB, target: ObjectDB | None = None
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
    changes = []
    for effect in effects:
        try:
            change_appearance(
                recipient,
                effect.trait,
                effect.target_option,
                persona=persona,
                actor_persona=actor_persona,
                note=template.name,
            )
            changes.append((effect.trait, effect.target_option))
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
        character=user,
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
    return CharacterFormState.objects.get(character=user)
