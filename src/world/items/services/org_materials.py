"""Org material-stock stewardship services (#696 gap 6).

The discretionary side of an org's ``OrgMaterialStock``: a steward hands stock
value to one chosen member (``grant_material_stock``) or sets the per-category
liquidation rate the auto-sell pays (``set_asking_price``). Both gate on
``houses.services.can_steward_org`` (an org leader or the ``domain-steward``
office holder) - the same standing that runs the house's domains. Grants land
in the recipient's existing ``MaterialBucket`` via ``credit_materials``, so the
crafting-spend path is untouched; every grant writes one ``OrgMaterialLedgerEntry``
GRANT row (the SALE rows come from ``currency.services.auto_sell_excess_materials``).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import transaction

from world.items.constants import MAX_ASKING_PRICE_PCT, OrgMaterialLedgerKind
from world.items.exceptions import (
    AskingPriceOutOfBounds,
    GrantRecipientNotMember,
    InsufficientMaterialStock,
    MaterialStewardshipRequired,
)
from world.items.materials_models import OrgMaterialLedgerEntry, OrgMaterialStock

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.items.models import MaterialCategory
    from world.scenes.models import Persona
    from world.societies.models import Organization


def _require_steward(persona: Persona, organization: Organization) -> None:
    """Raise ``MaterialStewardshipRequired`` unless ``persona`` may steward the org."""
    from world.societies.houses.services import can_steward_org  # noqa: PLC0415

    if not can_steward_org(persona, organization):
        raise MaterialStewardshipRequired


def _is_active_member(sheet: CharacterSheet, organization: Organization) -> bool:
    """Whether any of ``sheet``'s personas holds an active membership in ``organization``."""
    from world.societies.models import OrganizationMembership  # noqa: PLC0415

    return OrganizationMembership.objects.filter(
        organization=organization,
        persona__character_sheet=sheet,
        left_at__isnull=True,
        exiled_at__isnull=True,
    ).exists()


@transaction.atomic
def grant_material_stock(
    *,
    organization: Organization,
    material_category: MaterialCategory,
    value: int,
    to_sheet: CharacterSheet,
    granted_by: Persona,
) -> OrgMaterialLedgerEntry:
    """Grant ``value`` of the org's ``material_category`` stock to one member (#696 gap 6).

    The discretionary sibling of ``distribute_material_allowance``'s automatic
    even split: ``granted_by`` (gated on ``can_steward_org``) picks the recipient
    and the amount. ``to_sheet`` must hold an active membership in the org. The
    stock row is read under ``select_for_update`` (the same locking discipline the
    allowance and auto-sell legs use, since all three debit the same table) and
    ``InsufficientMaterialStock`` is raised - nothing moves - when the stock falls
    short of ``value``. On success the recipient's ``MaterialBucket`` is credited
    via ``credit_materials`` and one GRANT ledger row records the movement.
    """
    from world.items.gems.buckets import credit_materials  # noqa: PLC0415

    if value <= 0:
        msg = "Cannot grant a non-positive material value."
        raise ValueError(msg)
    _require_steward(granted_by, organization)
    if not _is_active_member(to_sheet, organization):
        raise GrantRecipientNotMember
    stock = (
        OrgMaterialStock.objects.select_for_update()
        .filter(organization=organization, material_category=material_category)
        .first()
    )
    if stock is None or stock.value < value:
        raise InsufficientMaterialStock
    # Canonical SharedMemoryModel mutation (ADR-0008): mutate the cached attr then save.
    stock.value -= value
    stock.save(update_fields=["value"])
    credit_materials(to_sheet, material_category, value)
    return OrgMaterialLedgerEntry.objects.create(
        organization=organization,
        material_category=material_category,
        kind=OrgMaterialLedgerKind.GRANT,
        value=value,
        counterparty_sheet=to_sheet,
    )


def set_asking_price(
    *,
    organization: Organization,
    material_category: MaterialCategory,
    pct: int,
    by: Persona,
) -> OrgMaterialStock:
    """Set the org's per-category asking price the auto-sell liquidates at (#696 gap 6).

    Gated on ``can_steward_org`` (same standing as the grant). ``pct`` is bounded
    0..``MAX_ASKING_PRICE_PCT``; 0 means "never sell" (the auto-sell's zero-copper
    guard skips the row). A category with no stock row yet gets one at zero value -
    a house may price a material before its first collection lands.
    """
    _require_steward(by, organization)
    if not isinstance(pct, int) or pct < 0 or pct > MAX_ASKING_PRICE_PCT:
        raise AskingPriceOutOfBounds
    stock, created = OrgMaterialStock.objects.get_or_create(
        organization=organization,
        material_category=material_category,
        defaults={"asking_price_pct": pct},
    )
    if not created and stock.asking_price_pct != pct:
        stock.asking_price_pct = pct
        stock.save(update_fields=["asking_price_pct"])
    return stock
