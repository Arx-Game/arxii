"""Service: using items and consuming charges (issue #509)."""

from __future__ import annotations

import contextlib

from django.db import transaction
from django.utils import timezone

from world.checks.consequence_resolution import (
    apply_pool_deterministically,
    apply_resolution,
    resolve_pool_consequences,
    select_consequence,
)
from world.checks.types import ResolutionContext
from world.items.constants import OwnershipEventType
from world.items.exceptions import ItemNotUsable, NoChargesRemaining
from world.items.models import EquippedItem, ItemInstance, OwnershipEvent
from world.items.types import UseItemResult


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
                game_object.location = None
                game_object.save()
            OwnershipEvent.objects.create(
                item_instance=locked,
                event_type=OwnershipEventType.CONSUMED,
                from_character_sheet=locked.holder_character_sheet,
                notes="Consumed — final charge spent (preserved).",
            )
        else:
            OwnershipEvent.objects.create(
                item_instance=locked,
                event_type=OwnershipEventType.CONSUMED,
                from_character_sheet=locked.holder_character_sheet,
                notes=f"Consumed and destroyed: {locked.display_name} ({locked.template.name}).",
            )
            if locked.game_object_id is not None:
                locked.game_object.delete()  # CASCADE removes the ItemInstance row
            else:
                locked.delete()
    return locked


@transaction.atomic
def use_item(*, item_instance: ItemInstance, user, target=None) -> UseItemResult:
    """Use a consumable: apply its on-use pool's effects (deterministic when the
    template has no on_use_check_type, else check-gated) and spend one charge.
    The charge is spent regardless of check outcome. user/target are ObjectDBs."""
    locked = ItemInstance.objects.select_for_update().get(pk=item_instance.pk)
    template = locked.template
    if not template.is_consumable or template.on_use_pool_id is None:
        raise ItemNotUsable
    if locked.charges <= 0:
        raise NoChargesRemaining

    context = ResolutionContext(character=user, target=target)
    check_result = None
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

    consumed = consume_item_charges(item_instance=locked, amount=1)
    return UseItemResult(
        applied_effects=applied,
        charges_remaining=consumed.charges,
        destroyed=(consumed.charges == 0),
        soft_deleted=(consumed.charges == 0 and consumed.destroyed_at is not None),
        check_result=check_result,
    )
