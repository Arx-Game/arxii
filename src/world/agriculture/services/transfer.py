"""Inter-domain food transfer service (#2219)."""

from __future__ import annotations

import logging

from django.db import transaction

from world.agriculture.models import FoodStockpile, FoodTransfer
from world.agriculture.services.domain import max_food_capacity
from world.agriculture.types import FoodTransferResult

logger = logging.getLogger(__name__)


@transaction.atomic
def transfer_food(
    *,
    source_domain,
    target_domain,
    amount: int,
    acting_persona=None,
    character=None,
) -> FoodTransferResult:
    """Move food from source stockpile to target stockpile (#2219).

    Deducts from source.stored (row-locked), lands into target.stored
    (capped at max_food_capacity; overflow lost), creates a FoodTransfer
    audit row, and emits FOOD_PRE_TRANSFER (cancellable) + FOOD_TRANSFERRED
    (frozen) events.

    Args:
        source_domain: The ``Domain`` losing food.
        target_domain: The ``Domain`` gaining food.
        amount: Food units to move (must be > 0).
        acting_persona: The ``Persona`` authorizing the transfer (may be None
            for system-initiated transfers).
        character: The acting ``Character`` (ObjectDB) for event payloads;
            its ``.location`` scopes the reactive events.

    Returns:
        ``FoodTransferResult`` with amount, landed, overflow, cancelled.

    Raises:
        ValueError: If amount <= 0, source == target, or source has
            insufficient food.
    """
    from flows.constants import EventName  # noqa: PLC0415
    from flows.emit import emit_event  # noqa: PLC0415
    from flows.events.payloads import (  # noqa: PLC0415
        FoodPreTransferPayload,
        FoodTransferredPayload,
    )

    if amount <= 0:
        msg = "Transfer amount must be positive."
        raise ValueError(msg)
    if source_domain.pk == target_domain.pk:
        msg = "Cannot transfer food to the same domain."
        raise ValueError(msg)

    location = getattr(character, "location", None)  # noqa: GETATTR_LITERAL

    # --- Pre-transfer event (cancellable, mutable) ---
    cancelled = False
    if location is not None:
        pre_payload = FoodPreTransferPayload(
            character=character,
            source_domain=source_domain,
            target_domain=target_domain,
            amount=amount,
        )
        stack = emit_event(
            EventName.FOOD_PRE_TRANSFER,
            pre_payload,
            location,
        )
        cancelled = stack.was_cancelled()

    if cancelled:
        return FoodTransferResult(
            amount=amount,
            landed=0,
            overflow=0,
            cancelled=True,
        )

    # --- Lock and deduct source stockpile ---
    try:
        source_stockpile = FoodStockpile.objects.select_for_update().get(domain=source_domain)
    except FoodStockpile.DoesNotExist:
        msg = f"{source_domain.name} has no food stockpile."
        raise ValueError(msg) from None

    if source_stockpile.stored < amount:
        msg = (
            f"{source_domain.name} has only {source_stockpile.stored} food; "
            f"cannot transfer {amount}."
        )
        raise ValueError(msg)

    source_stockpile.stored -= amount
    source_stockpile.save(update_fields=["stored"])

    # --- Land food into target stockpile (capped at Granary capacity) ---
    target_stockpile, _ = FoodStockpile.objects.get_or_create(domain=target_domain)
    target_stockpile = FoodStockpile.objects.select_for_update().get(pk=target_stockpile.pk)
    capacity = max_food_capacity(target_domain)
    headroom = max(0, capacity - target_stockpile.stored)
    landed = min(amount, headroom)
    overflow = amount - landed

    target_stockpile.stored += landed
    target_stockpile.save(update_fields=["stored"])

    # --- Audit row ---
    FoodTransfer.objects.create(
        source_domain=source_domain,
        target_domain=target_domain,
        amount=amount,
        acting_persona=acting_persona,
    )

    # --- Post-transfer event (frozen) ---
    if location is not None:
        post_payload = FoodTransferredPayload(
            character=character,
            source_domain=source_domain,
            target_domain=target_domain,
            amount=amount,
            landed=landed,
            overflow=overflow,
        )
        emit_event(
            EventName.FOOD_TRANSFERRED,
            post_payload,
            location,
        )

    return FoodTransferResult(
        amount=amount,
        landed=landed,
        overflow=overflow,
    )
