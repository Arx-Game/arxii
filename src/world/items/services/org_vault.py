"""Org-vault custody services (#2540 Layer 4): the sole mutators of VaultHolding.

Deposit/withdraw follow the ``transfer`` discipline — atomic, row-locked on the item,
audited (``OrgVaultEvent``). Custody is logical: a vaulted item's holder goes null and
its ``game_object`` is dematerialized (row-only, the established pattern), so custody
never depends on a destructible physical object. WHERE these may be performed (a bank
room / bank-access room feature) is the action layer's prerequisite gate, not this
layer's concern.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.core.exceptions import ValidationError
from django.db import transaction

from world.items.constants import OrgVaultEventKind
from world.items.models import ItemInstance
from world.items.org_vault_models import OrganizationVault, OrgVaultEvent, VaultHolding

if TYPE_CHECKING:
    from world.scenes.models import Persona
    from world.societies.models import Organization


def get_or_create_org_vault(organization: Organization) -> OrganizationVault:
    vault, _ = OrganizationVault.objects.get_or_create(organization=organization)
    return vault


def _active_membership_tier(vault: OrganizationVault, persona: Persona) -> int | None:
    """The persona's active rank tier in the vault's org, or None when not a member."""
    from world.societies.models import OrganizationMembership  # noqa: PLC0415

    membership = (
        OrganizationMembership.objects.filter(
            persona=persona,
            organization_id=vault.organization_id,
            left_at__isnull=True,
            exiled_at__isnull=True,
        )
        .select_related("rank")
        .first()
    )
    return membership.rank.tier if membership is not None else None


def can_access_vault(vault: OrganizationVault, persona: Persona) -> bool:
    """Withdraw authority: an active membership at tier <= ``withdraw_rank_max``.

    The ``can_spend_treasury`` twin — the predicate VAULT_ITEM boons, the collection
    return leg, and the embezzlement branch all gate on.
    """
    tier = _active_membership_tier(vault, persona)
    return tier is not None and tier <= vault.withdraw_rank_max


@transaction.atomic
def deposit_item_to_vault(
    *, organization: Organization, persona: Persona, item_instance: ItemInstance, reason: str = ""
) -> VaultHolding:
    """An active member deposits an item they hold into the org's custody.

    Raises ``ValidationError`` when the persona is not an active member, does not hold
    the item, or the item is already vaulted. The item's holder goes null and any
    materialized ``game_object`` is deleted (custody is the row, not the prop).
    """
    vault = get_or_create_org_vault(organization)
    if _active_membership_tier(vault, persona) is None:
        msg = "Only a member may deposit into this vault."
        raise ValidationError(msg)
    item = ItemInstance.objects.select_for_update().get(pk=item_instance.pk)
    if item.holder_character_sheet_id != persona.character_sheet_id:
        msg = "You can only deposit an item you hold."
        raise ValidationError(msg)
    if VaultHolding.objects.filter(item_instance=item).exists():
        msg = "That item is already in a vault."
        raise ValidationError(msg)

    if item.game_object is not None:
        item.game_object.delete()
        item.game_object = None
    item.holder_character_sheet = None
    item.save(update_fields=["holder_character_sheet", "game_object"])
    holding = VaultHolding.objects.create(vault=vault, item_instance=item, deposited_by=persona)
    OrgVaultEvent.objects.create(
        vault=vault,
        item_instance=item,
        kind=OrgVaultEventKind.DEPOSIT,
        actor_persona=persona,
        reason=reason,
    )
    return holding


@transaction.atomic
def withdraw_item_from_vault(
    *,
    organization: Organization,
    persona: Persona,
    item_instance: ItemInstance,
    to_persona: Persona | None = None,
    reason: str = "",
) -> ItemInstance:
    """A withdraw-authorized member takes an item out of the org's custody.

    ``to_persona`` lets an authorized member direct the item to someone else's hands —
    the VAULT_ITEM boon shape: the target exercises their authority on the asker's
    behalf. Raises ``ValidationError`` when the persona lacks withdraw authority or
    the item is not in this org's vault. The item lands row-only in the recipient's
    inventory (materialization is a separate, existing step).
    """
    vault = get_or_create_org_vault(organization)
    if not can_access_vault(vault, persona):
        msg = "You do not have the standing to withdraw from this vault."
        raise ValidationError(msg)
    item = ItemInstance.objects.select_for_update().get(pk=item_instance.pk)
    holding = VaultHolding.objects.filter(vault=vault, item_instance=item).first()
    if holding is None:
        msg = "That item is not in this vault."
        raise ValidationError(msg)

    recipient = to_persona or persona
    holding.delete()
    item.holder_character_sheet = recipient.character_sheet
    item.save(update_fields=["holder_character_sheet"])
    OrgVaultEvent.objects.create(
        vault=vault,
        item_instance=item,
        kind=OrgVaultEventKind.WITHDRAW,
        actor_persona=persona,
        reason=reason,
    )
    return item
