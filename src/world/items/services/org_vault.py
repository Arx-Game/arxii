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
from django.utils import timezone

from world.items.constants import OrgVaultEventKind, VaultTransitResolution
from world.items.models import ItemInstance
from world.items.org_vault_models import (
    OrganizationVault,
    OrgVaultEvent,
    VaultHolding,
    VaultTransit,
)

if TYPE_CHECKING:
    from collections.abc import Collection

    from world.roster.models import RosterTenure
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


def _persona_tenure(persona: Persona | None) -> RosterTenure | None:
    """persona → character_sheet → roster_entry → current_tenure, or None on any gap."""
    from django.core.exceptions import ObjectDoesNotExist  # noqa: PLC0415

    if persona is None:
        return None
    try:
        entry = persona.character_sheet.roster_entry
    except (AttributeError, ObjectDoesNotExist):
        return None
    return entry.current_tenure if entry is not None else None


def can_embezzle_from(organization: Organization, carrier_persona: Persona) -> bool:
    """The authority-side half of the embezzlement double-gate (#2540 rulings 2026-07-20).

    "Who has to deal with this" (Apostate): the **highest-ranked active piloted
    member** is the consent authority — walk the ladder from the top, skip everything
    non-piloted, and the first piloted tier's ``embezzlement`` consent decides. A
    piloted story-NPC head therefore answers for the house even when an opted-out PC
    Voice serves below (the Voice is never consulted, never has to engage); an
    unpiloted NPC head defers to the next piloted member down, whose opt-out blocks.

    Boundaries: the carrier must themselves be piloted (NPC collectors never skim —
    ruled); the carrier is excluded from the authority set (the register protects you
    from OTHERS), so when the carrier IS the topmost piloted member there is no
    unwilling player in the loop and the skim is allowed — self-dealing under
    non-piloted oversight is exactly the story. Ties at the deciding tier resolve
    strict-all (any objecting co-equal blocks). The carrier-side half of the gate is
    the explicit opt-in via ``keep_item_ids``.
    """
    from world.consent.models import SocialConsentCategory  # noqa: PLC0415
    from world.consent.services import consent_blocks_targeting  # noqa: PLC0415
    from world.societies.models import OrganizationMembership  # noqa: PLC0415

    def _piloted(persona: Persona) -> bool:
        return persona.character_sheet.character.db_account is not None

    if not _piloted(carrier_persona):
        return False  # NPC collectors never skim
    category = SocialConsentCategory.objects.filter(key="embezzlement").first()
    if category is None:
        return False  # unseeded resolves strict, mirroring theft's fallback
    memberships = OrganizationMembership.objects.filter(
        organization=organization,
        left_at__isnull=True,
        exiled_at__isnull=True,
    ).select_related("rank", "persona__character_sheet__character__db_account")
    authorities = [
        membership
        for membership in memberships
        if _piloted(membership.persona) and membership.persona_id != carrier_persona.pk
    ]
    if not authorities:
        return True  # the carrier is the topmost piloted stakeholder — nobody unwilling
    deciding_tier = min(membership.rank.tier for membership in authorities)
    carrier_tenure = _persona_tenure(carrier_persona)
    for membership in authorities:
        if membership.rank.tier != deciding_tier:
            continue  # below the deciding tier — never consulted, never has to engage
        authority_tenure = _persona_tenure(membership.persona)
        if authority_tenure is None or consent_blocks_targeting(
            owner_tenure=authority_tenure, category=category, actor_tenure=carrier_tenure
        ):
            return False
    return True


@transaction.atomic
def resolve_vault_transit(
    *,
    organization: Organization,
    carrier_persona: Persona,
    keep_item_ids: Collection[int] = (),
) -> list[VaultTransit]:
    """Complete the collection mission's return leg for one carrier (#2540 ruling).

    Every open transit row the carrier holds for this org's vault resolves: items in
    ``keep_item_ids`` resolve KEPT (embezzled — requires the consent double-gate; the
    stone stays in the carrier's hands and NO vault event is booked), the rest resolve
    DEPOSITED (custody converts to a ``VaultHolding`` + audited DEPOSIT event).
    Raises ``ValidationError`` when a keep is requested but the double-gate fails.
    """
    vault = get_or_create_org_vault(organization)
    keep_ids = set(keep_item_ids)
    if keep_ids and not can_embezzle_from(organization, carrier_persona):
        msg = "Skimming this house's collection is not on the table."
        raise ValidationError(msg)
    transits = list(
        VaultTransit.objects.filter(
            vault=vault,
            carrier_character_sheet=carrier_persona.character_sheet,
            resolved_at__isnull=True,
        ).select_related("item_instance")
    )
    now = timezone.now()
    for transit in transits:
        item = ItemInstance.objects.select_for_update().get(pk=transit.item_instance_id)
        if item.pk in keep_ids:
            transit.resolution = VaultTransitResolution.KEPT
        else:
            if item.game_object is not None:
                item.game_object.delete()
                item.game_object = None
            item.holder_character_sheet = None
            item.save(update_fields=["holder_character_sheet", "game_object"])
            VaultHolding.objects.create(
                vault=vault, item_instance=item, deposited_by=carrier_persona
            )
            OrgVaultEvent.objects.create(
                vault=vault,
                item_instance=item,
                kind=OrgVaultEventKind.DEPOSIT,
                actor_persona=carrier_persona,
                reason="collection deposit",
            )
            transit.resolution = VaultTransitResolution.DEPOSITED
        transit.resolved_at = now
        transit.save(update_fields=["resolution", "resolved_at"])
    return transits


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
