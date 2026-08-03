"""Accent removal + item recycling (#2886).

Both are owner-only lifecycle acts on a piece:

* ``remove_item_accent`` — strip one worked-in Accent (no refund; the web
  surface confirms first). Prestige recomputes if the piece is worn.
* ``recycle_item`` — destroy the piece for a PLACEHOLDER fraction of its
  recipe's materials. **Story-protected**: an item with legend attached
  (linked deeds) needs an APPROVED ``RecycleRequest`` (GM sign-off) first —
  a piece the world remembers is not the owner's alone to unmake.
"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from django.db import transaction
from django.utils import timezone

from world.items.constants import SALVAGE_FRACTION, OwnershipEventType, RecycleRequestStatus
from world.items.exceptions import AccentNotPresent, NotItemOwner, RecycleNeedsGMApproval
from world.items.models import ItemInstance, OwnershipEvent, RecycleRequest
from world.items.services.usage import hard_delete_item_instance

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.gm.models import GMProfile
    from world.items.crafting.models import ItemAccent
    from world.mechanics.models import ModifierTarget


@dataclass(frozen=True)
class RecycleResult:
    """Outcome of ``recycle_item``: what was salvaged back."""

    salvaged: tuple[tuple[str, int], ...] = field(default_factory=tuple)


def _assert_owner(item_instance: ItemInstance, actor_sheet: CharacterSheet) -> None:
    if item_instance.holder_character_sheet_id != actor_sheet.pk:
        raise NotItemOwner


def _recompute_wearer_prestige(item_instance: ItemInstance) -> None:
    """Invalidate the wearer's handler + recompute their presented persona."""
    from world.items.models import EquippedItem  # noqa: PLC0415
    from world.items.polish_services import (  # noqa: PLC0415
        recompute_persona_prestige_from_items,
    )
    from world.scenes.models import Persona  # noqa: PLC0415
    from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415

    for equipped in EquippedItem.objects.filter(item_instance=item_instance):
        equipped.character.equipped_items.invalidate()
        try:
            persona = active_persona_for_sheet(equipped.character)
        except Persona.DoesNotExist:
            continue
        recompute_persona_prestige_from_items(persona)


@transaction.atomic
def remove_item_accent(
    *,
    item_instance: ItemInstance,
    target: ModifierTarget,
    actor_sheet: CharacterSheet,
) -> ItemAccent:
    """Strip ``target``'s accent off the piece. Owner-only; no refund.

    Returns the removed row (detached). Raises ``NotItemOwner`` /
    ``AccentNotPresent``.
    """
    from world.items.crafting.models import ItemAccent  # noqa: PLC0415

    _assert_owner(item_instance, actor_sheet)
    accent = ItemAccent.objects.filter(item_instance=item_instance, target=target).first()
    if accent is None:
        raise AccentNotPresent
    accent.delete()
    # Drop the cached accents so display/prestige reads recompute.
    with contextlib.suppress(AttributeError):
        del item_instance.cached_item_accents
    _recompute_wearer_prestige(item_instance)
    return accent


def is_story_protected(item_instance: ItemInstance) -> bool:
    """True when the piece carries legend the owner alone may not unmake."""
    return item_instance.legend_deeds.filter(is_active=True).exists()


def request_recycle_approval(
    *, item_instance: ItemInstance, actor_sheet: CharacterSheet
) -> RecycleRequest:
    """Open (or return the existing pending) GM sign-off request. Owner-only."""
    _assert_owner(item_instance, actor_sheet)
    request, _created = RecycleRequest.objects.get_or_create(
        item_instance=item_instance,
        requested_by=actor_sheet,
        status=RecycleRequestStatus.PENDING,
    )
    return request


@transaction.atomic
def resolve_recycle_request(
    *, request: RecycleRequest, gm_profile: GMProfile, approve: bool
) -> RecycleRequest:
    """GM sign-off (or denial) on a pending recycle request."""
    request.status = RecycleRequestStatus.APPROVED if approve else RecycleRequestStatus.DENIED
    request.resolved_by = gm_profile
    request.resolved_at = timezone.now()
    request.save(update_fields=["status", "resolved_by", "resolved_at"])
    return request


def _salvage_returns(item_instance: ItemInstance) -> list[tuple[object, int]]:
    """(template, quantity) returns: SALVAGE_FRACTION of the recipe requirements."""
    returns: list[tuple[object, int]] = []
    for crafted in item_instance.crafted_recipes.select_related("recipe"):
        for req in crafted.recipe.material_requirements.select_related("item_template"):
            if req.item_template is None:
                continue  # category/bulk requirements salvage nothing (Build 0b)
            amount = int(req.quantity * SALVAGE_FRACTION)
            if amount >= 1:
                returns.append((req.item_template, amount))
    return returns


@transaction.atomic
def recycle_item(*, item_instance: ItemInstance, actor_sheet: CharacterSheet) -> RecycleResult:
    """Destroy the piece for a fraction of its materials. Owner-only.

    Story-protected items (``is_story_protected``) require an APPROVED
    ``RecycleRequest`` from this owner — ``RecycleNeedsGMApproval`` otherwise.
    Salvage lands in the owner's inventory as fresh material instances; the
    piece itself is destroyed via the #1025 footprint rules (soft-delete when
    it carries per-instance data, else hard-delete).
    """
    locked = ItemInstance.objects.select_for_update().get(pk=item_instance.pk)
    _assert_owner(locked, actor_sheet)
    if is_story_protected(locked):
        approved = RecycleRequest.objects.filter(
            item_instance=locked,
            requested_by=actor_sheet,
            status=RecycleRequestStatus.APPROVED,
        ).exists()
        if not approved:
            raise RecycleNeedsGMApproval

    salvaged: list[tuple[str, int]] = []
    for template, amount in _salvage_returns(locked):
        ItemInstance.objects.create(
            template=template,
            holder_character_sheet=actor_sheet,
            quantity=amount,
        )
        salvaged.append((template.name, amount))

    _recompute_wearer_prestige(locked)
    preserve = locked.differs_from_template
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
            notes="Recycled by its owner (preserved for provenance).",
        )
    else:
        hard_delete_item_instance(locked)
    return RecycleResult(salvaged=tuple(salvaged))
