"""Boon services (#2540): the structured social ask — validation, band, fulfillment.

A Boon names what an asker wants from a target (money, a held item, a vault item, or a
deed) and rides the ``SceneActionRequest`` consent flow. This module owns the ask-time
eligibility validation (dial 1), the NPC-side relative-cost difficulty band (dial 2),
fulfillment on a granted ask, and the per-Boon affection cost (the dial-3 drain).

Fulfillment fires via the same resolver (``register_resolver``) registered under every
key in ``BOON_ACTION_KEYS`` — ``boon`` plus the #2540 slice 3 ask flavors
(``boon_con``/``boon_charm``/``boon_menace``) — which both resolution paths invoke —
NPC auto-accept at dispatch and a piloted target's later accept. It must NOT ride
``BoonAction.execute()``: the consent paths never call ``execute()`` (the Blackmail
mint asymmetry), and it must not ride a seeded ``SHIFT_AFFECTION`` ``ConsequenceEffect``
either — the consent path resolves with a sceneless ``ResolutionContext``, where
scene-keyed data effects skip.

Every kind now fulfills: ``MONEY`` through the single currency mutation point
(``transfer``, target purse → asker purse), ``VAULT_ITEM`` through the org vault's
audited withdraw (target as authority, asker as recipient), ``HELD_ITEM`` through a
lean sheet-level hand-over (unequip → object move/dematerialize → holder switch →
``OwnershipEvent(TRANSFERRED)``), ``MATERIAL`` (#2540 slice 3) through the material
bucket's spend/credit pair (``world.items.gems.buckets`` — the module lives under
``gems/`` despite the generalization), and ``DEED`` is RP-only (no mechanical
transfer). Idempotent: a fulfilled Boon is a no-op (claimed under row lock, so
concurrent fulfills cannot double-move).

``validate_boon_ask`` and ``fulfill_boon`` both dispatch on ``kind`` through an
explicit per-kind table (``_BOON_ASK_VALIDATORS`` / ``_BOON_FULFILLERS``) — a kind
with no table entry raises ``ValueError`` loudly rather than silently falling
through to another kind's handling (the original if/elif chains had an implicit
DEED fallthrough on an unrecognized kind; #2540 slice 3 recon trap fix).

MATERIAL asks show tier LABELS only, never a computed value (deliberate asymmetry
with MONEY's ``boon_sum_values`` display seam — see ``BoonUnavailable`` below for why).

2026-08-27 exact-pointer ruling (#2540 slice 3): a HELD_ITEM/VAULT_ITEM ask also
requires the asker to hold a pointer to the named item (``character_has_item_
pointer``) — checked inside ``_validate_held_item_ask``/``_validate_vault_item_ask``,
which both now take the asker's ``CharacterSheet`` from ``validate_boon_ask``. A
pointer-less ask with a valid item id fails with a neutral message
(``BOON_NO_POINTER_TEXT``) that never reveals whether the item exists or is held —
the API cannot be curled around the UI. ``pointer_known_items_for_target`` is the
display-seam counterpart (the boon-options ``pointer_items`` list): the asker's
pointer-known items relevant to one target, computed from the asker's OWN pointers,
never a browse of the target's actual holdings.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import TYPE_CHECKING

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from world.scenes.action_constants import BoonKind, BoonSumTier
from world.scenes.action_resolvers import register_resolver
from world.scenes.boon_models import Boon

if TYPE_CHECKING:
    from collections.abc import Callable

    from world.character_sheets.models import CharacterSheet
    from world.items.models import ItemInstance
    from world.roster.models import RosterEntry
    from world.scenes.action_models import SceneActionRequest
    from world.scenes.models import Persona
    from world.scenes.types import EnhancedSceneActionResult

logger = logging.getLogger(__name__)

# #2540 slice 3 — the ask flavors (con/charm/menace) share the base Boon's structured
# payload, consent category, and resolver: one opt-in and one fulfillment path covers
# every flavor, only the check type + template name differ.
BOON_ACTION_KEYS = frozenset({"boon", "boon_con", "boon_charm", "boon_menace"})

# Money asks are RELATIVE sum tiers (#2540 ruling 2026-07-20): the asker picks
# minor/fair/great *to the target*, the concrete coppers derive from the target's purse
# at ask time (and freeze onto Boon.amount), and the chosen tier IS the dial-2 cost
# band. Raw-amount asks do not exist — nothing to binary-search a purse with, and an
# impossible ask can never be presented. PLACEHOLDER pcts/shifts — Apostate's tuning.
BOON_SUM_TIERS: dict[str, tuple[int, int]] = {
    # sum_tier -> (pct of target's purse, difficulty tier shift)
    BoonSumTier.MINOR: (5, 0),  # pocket change to them
    BoonSumTier.FAIR: (20, 1),  # notable
    BoonSumTier.GREAT: (50, 2),  # painful
}
# PLACEHOLDER flat shifts for the non-money kinds until item appraisal-vs-means lands:
# asking for a named possession is painful; a deed is notable.
BOON_HELD_ITEM_TIER_SHIFT = 2
BOON_DEED_TIER_SHIFT = 1

# Dial 3 drain — every granted Boon costs affection (target's regard for the asker),
# applied per-Boon (stacking, even within one scene) and permanent until rebuilt via
# ordinary social play (developed points never decay, so the >=3-months-real-time
# persistence Apostate ruled is automatic). PLACEHOLDER magnitude (#1699 scale: bump 1,
# flirt 5, seduction 50) — Apostate's tuning call.
BOON_AFFECTION_COST = 15

# #2540 slice 3: the diegetic refusal text for an honestly-unavailable MATERIAL ask
# (empty bucket) — never a validation error, since the ask itself was well-formed.
BOON_MATERIAL_REFUSAL_TEXT = "PLACEHOLDER: they do not have that to give."

# 2026-08-27 exact-pointer ruling: a named-item ask (HELD_ITEM/VAULT_ITEM) is
# ineligible without prior pointer knowledge — this text stays neutral (never reveals
# whether the item exists, whether the target holds it, or anything else) so the API
# can't be curled around the UI to fish for information the asker doesn't have.
BOON_NO_POINTER_TEXT = "PLACEHOLDER: you have no knowledge of any such thing."


class BoonUnavailable(Exception):
    """Honest unavailability (#2540 slice 3 controller ruling) — NOT a validation error.

    Raised at request-creation time, AFTER ``validate_boon_ask`` passes: the ask is
    well-formed (a real category, a real tier) but the target's bucket for it is
    empty. The MATERIAL category picker is deliberately the STATIC public
    ``MaterialCategory`` list, never filtered by the target's actual holdings (a
    holdings-filtered picker would leak wealth OOC) — so this boolean reveal at ask
    time is the ruling's accepted cost, instead.

    No ``SceneActionRequest`` row is ever created for this call — the request never
    lands in a piloted target's consent queue either (no feels-bad "no" roll, no
    consent burn, no affection drain) for BOTH NPC and piloted targets alike.
    """

    def __init__(self, refusal_text: str = BOON_MATERIAL_REFUSAL_TEXT) -> None:
        super().__init__(refusal_text)
        self.refusal_text = refusal_text


@dataclass(frozen=True)
class BoonAsk:
    """The structured payload of a boon ask, passed into ``create_action_request``.

    MONEY asks carry a ``sum_tier`` (never a raw amount — #2540 ruling); the concrete
    coppers are computed from the target's purse at validation time. MATERIAL asks
    (#2540 slice 3) carry both a ``material_category_id`` and a ``sum_tier`` (reusing
    the same MINOR/FAIR/GREAT labels as money) — but, unlike money, no concrete value
    is ever computed or shown at ask time; see ``BoonUnavailable``.
    """

    kind: str
    sum_tier: str = ""
    item_instance_id: int | None = None
    deed_text: str = ""
    material_category_id: int | None = None


def boon_sum_values(target_sheet: CharacterSheet) -> dict[str, int]:
    """The concrete coppers each sum tier means against this target — the UI display seam.

    Returns an empty dict for a penniless target: no money-boon option is presented at
    all (options only show when the target could actually grant them). The OOC reveal
    of these values to the asker is accepted per the ruling; IC, you still can't know
    their purse.
    """
    from world.currency.services import get_or_create_purse  # noqa: PLC0415

    balance = get_or_create_purse(target_sheet).balance
    if balance <= 0:
        return {}
    return {tier: max(1, balance * pct // 100) for tier, (pct, _shift) in BOON_SUM_TIERS.items()}


def validate_boon_ask(
    *, ask: BoonAsk, target_persona: Persona | None, asker_sheet: CharacterSheet
) -> None:
    """Ask-time eligibility (dial 1): an ask the target could not grant never exists.

    Raises ``ValidationError`` on: no target, an unknown kind, a MONEY ask with no
    valid sum tier or against a penniless target (options only present when grantable
    — #2540 ruling), a HELD_ITEM ask for an item the target does not hold OR the asker
    has no pointer to (2026-08-27 exact-pointer ruling — see ``character_has_item_
    pointer``), an empty DEED, a VAULT_ITEM ask for an item outside the target's
    withdraw authority or the asker has no pointer to, or a MATERIAL ask naming an
    unknown category or an invalid sum tier. Dispatches on ``kind`` through the
    explicit ``_BOON_ASK_VALIDATORS`` table — an unrecognized-but-real ``BoonKind``
    member with no table entry raises ``ValueError`` loudly (a coding error, never a
    player-facing failure — every real kind is entered below).

    A MATERIAL ask that names a real category the target's bucket happens to be empty
    of is NOT rejected here — that's honest unavailability, not ineligibility; see
    ``check_boon_availability``/``BoonUnavailable``, called separately at
    request-creation time.

    ``asker_sheet`` is the initiator's sheet (visibility = eligibility, one predicate:
    the server enforces the pointer gate — the API cannot be curled around the UI).
    """
    if target_persona is None:
        msg = "A boon is asked of someone — it needs a target."
        raise ValidationError(msg)
    if ask.kind not in BoonKind.values:
        msg = "Unknown boon kind."
        raise ValidationError(msg)
    validator = _BOON_ASK_VALIDATORS.get(ask.kind)
    if validator is None:
        msg = f"unhandled boon kind {ask.kind}"
        raise ValueError(msg)
    validator(ask, target_persona, asker_sheet)


def _validate_money_ask(
    ask: BoonAsk,
    target_persona: Persona,
    asker_sheet: CharacterSheet,  # noqa: ARG001
) -> None:
    """A money ask names a sum tier; the option only exists when the purse could pay it."""
    target_sheet = target_persona.character_sheet
    if ask.sum_tier not in BOON_SUM_TIERS:
        msg = "A money boon asks for a minor, fair, or great sum."
        raise ValidationError(msg)
    if not boon_sum_values(target_sheet):
        msg = "They have nothing worth asking for."
        raise ValidationError(msg)


def _money_amount_for(ask: BoonAsk, target_sheet: CharacterSheet) -> int:
    """Freeze the tier into concrete coppers at ask time (0 for non-money kinds)."""
    if ask.kind != BoonKind.MONEY:
        return 0
    return boon_sum_values(target_sheet).get(ask.sum_tier, 0)


def _validate_held_item_ask(
    ask: BoonAsk, target_persona: Persona, asker_sheet: CharacterSheet
) -> None:
    """Dial-1 eligibility for a held-item ask — pointer FIRST (oracle-leak fix).

    2026-08-27 fix round 1: the pointer check must run BEFORE the target-holds check,
    and with the SAME error text as "no such item" — otherwise a pointer-less asker
    could iterate item ids and distinguish "not held by them" from "no pointer",
    browsing the target's inventory one probe at a time (the exact thing the gate
    exists to prevent). Only once a pointer is confirmed does "they don't currently
    hold it" become a safe, distinct message — a pointer-holder legitimately knows
    the item exists.
    """
    from world.items.models import ItemInstance  # noqa: PLC0415

    if ask.item_instance_id is None:
        msg = "A held-item boon names the item asked for."
        raise ValidationError(msg)
    item = ItemInstance.objects.filter(pk=ask.item_instance_id).first()
    if item is None or not character_has_item_pointer(sheet=asker_sheet, item=item):
        raise ValidationError(BOON_NO_POINTER_TEXT)
    if item.holder_character_sheet_id != target_persona.character_sheet_id:
        msg = "They do not hold that item."
        raise ValidationError(msg)


def _validate_vault_item_ask(
    ask: BoonAsk, target_persona: Persona, asker_sheet: CharacterSheet
) -> None:
    """Dial-1 eligibility for a vault ask: the target must hold withdraw authority.

    A granted vault boon is the target *exercising* their org-vault authority on the
    asker's behalf (#2540 Layer 4) — so the ask is only eligible when the named item
    sits in a vault the target can withdraw from AND the asker holds a pointer to it
    (2026-08-27 exact-pointer ruling).

    2026-08-27 fix round 1: pointer FIRST, same oracle-leak fix as
    ``_validate_held_item_ask`` — a nonexistent item id, a real item with no asker
    pointer, and a real item pointed-to but held by a third party (not vaulted) must
    all fail identically (``BOON_NO_POINTER_TEXT``) before the vault-authority check
    ever runs, so a pointer-less asker can't distinguish them by probing ids.
    """
    from world.items.models import ItemInstance  # noqa: PLC0415
    from world.items.org_vault_models import VaultHolding  # noqa: PLC0415
    from world.items.services.org_vault import can_access_vault  # noqa: PLC0415

    if ask.item_instance_id is None:
        msg = "A vault boon names the item asked for."
        raise ValidationError(msg)
    item = ItemInstance.objects.filter(pk=ask.item_instance_id).first()
    if item is None or not character_has_item_pointer(sheet=asker_sheet, item=item):
        raise ValidationError(BOON_NO_POINTER_TEXT)
    holding = (
        VaultHolding.objects.filter(item_instance_id=ask.item_instance_id)
        .select_related("vault")
        .first()
    )
    if holding is None or not can_access_vault(holding.vault, target_persona):
        msg = "They cannot draw that from any vault."
        raise ValidationError(msg)


def _validate_deed_ask(
    ask: BoonAsk,
    target_persona: Persona,  # noqa: ARG001
    asker_sheet: CharacterSheet,  # noqa: ARG001
) -> None:
    if not ask.deed_text.strip():
        msg = "A deed boon needs the deed spelled out."
        raise ValidationError(msg)


def _validate_material_ask(
    ask: BoonAsk,
    target_persona: Persona,  # noqa: ARG001
    asker_sheet: CharacterSheet,  # noqa: ARG001
) -> None:
    """A material ask names a real category + a valid sum tier (reusing money's labels).

    Deliberately does NOT check the target's bucket here (the STATIC public category
    picker — #2540 ruling — is never filtered by target holdings, so an empty bucket
    is not an ineligible ask, just an unavailable one; see ``check_boon_availability``).
    Materials are not exact-pointer-gated (no named-item concept — a category, not an
    instance).
    """
    from world.items.models import MaterialCategory  # noqa: PLC0415

    if ask.material_category_id is None:
        msg = "A material boon names the crafting category asked for."
        raise ValidationError(msg)
    if not MaterialCategory.objects.filter(pk=ask.material_category_id).exists():
        msg = "Unknown material category."
        raise ValidationError(msg)
    if ask.sum_tier not in BOON_SUM_TIERS:
        msg = "A material boon asks for a minor, fair, or great sum."
        raise ValidationError(msg)


_BOON_ASK_VALIDATORS: dict[str, Callable[[BoonAsk, Persona, CharacterSheet], None]] = {
    BoonKind.MONEY: _validate_money_ask,
    BoonKind.HELD_ITEM: _validate_held_item_ask,
    BoonKind.VAULT_ITEM: _validate_vault_item_ask,
    BoonKind.DEED: _validate_deed_ask,
    BoonKind.MATERIAL: _validate_material_ask,
}


def check_boon_availability(*, ask: BoonAsk, target_persona: Persona | None) -> None:
    """Honest unavailability (#2540 slice 3 ruling) — call AFTER ``validate_boon_ask``.

    Only MATERIAL asks are checked: MONEY's penniless-target case is already covered
    inside ``validate_boon_ask`` (the option never even presents, since the money-boon
    picker IS filtered by ``boon_sum_values``), and the item/deed kinds have no "empty
    bucket" concept. Raises ``BoonUnavailable`` — never ``ValidationError`` — when a
    well-formed MATERIAL ask names a category the target's bucket holds none of; the
    caller (``create_action_request``) must not create a ``SceneActionRequest`` row
    when this raises. ``target_persona`` stays nullable to mirror ``validate_boon_ask``'s
    signature — in practice this always runs after that raises on ``None``, so the
    no-op branch below is unreachable, but callers shouldn't have to prove it to ty.
    """
    if ask.kind != BoonKind.MATERIAL or target_persona is None:
        return
    from world.items.gems.buckets import material_value  # noqa: PLC0415
    from world.items.models import MaterialCategory  # noqa: PLC0415

    category = MaterialCategory.objects.get(pk=ask.material_category_id)
    if material_value(target_persona.character_sheet, category) == 0:
        raise BoonUnavailable


def create_boon_for_request(request: SceneActionRequest, ask: BoonAsk) -> Boon:
    """Persist the validated ask payload on its request (before NPC auto-resolve fires).

    MONEY asks freeze the tier's concrete coppers onto ``amount`` here — the target's
    purse may move later, but the granted sum is what was asked.
    """
    target_sheet = request.target_persona.character_sheet
    return Boon.objects.create(
        action_request=request,
        kind=ask.kind,
        sum_tier=ask.sum_tier,
        amount=_money_amount_for(ask, target_sheet),
        item_instance_id=ask.item_instance_id,
        deed_text=ask.deed_text,
        material_category_id=ask.material_category_id,
    )


def boon_cost_tier_shift(boon: Boon, target_sheet: CharacterSheet) -> int:  # noqa: ARG001
    """Dial 2: how many difficulty tiers this ask's relative cost adds.

    For MONEY and MATERIAL the chosen sum tier IS the band (#2540 ruling — relative by
    construction; MATERIAL reuses the same MINOR/FAIR/GREAT tier table). ``target_sheet``
    stays in the signature for the item kinds' future appraisal-vs-means computation.
    """
    if boon.kind in (BoonKind.MONEY, BoonKind.MATERIAL):
        _pct, shift = BOON_SUM_TIERS.get(boon.sum_tier, BOON_SUM_TIERS[BoonSumTier.GREAT])
        return shift
    if boon.kind in (BoonKind.HELD_ITEM, BoonKind.VAULT_ITEM):
        return BOON_HELD_ITEM_TIER_SHIFT
    return BOON_DEED_TIER_SHIFT


def npc_boon_tier_shift(request: SceneActionRequest) -> int:
    """The mandatory NPC-side band (#2540 addendum): 0 unless a boon ask against an NPC.

    A piloted defender's difficulty choice rules — the band is consent-time framing for
    them, never a mechanical shift; without it NPCs would be farmable for money.
    """
    boon = Boon.objects.filter(action_request=request).first()
    if boon is None or request.target_persona is None:
        return 0
    if request.target_persona.character_sheet.character.db_account is not None:
        return 0
    return boon_cost_tier_shift(boon, request.target_persona.character_sheet)


@transaction.atomic
def fulfill_boon(boon: Boon) -> bool:
    """Fulfill a granted Boon. True when THIS call fulfilled it; False when already done.

    A DEED boon fulfills without moving value (RP-only). Raises ``ValidationError`` if
    the boon's request has no target persona, or (from the kind-specific fulfiller) if
    the target can no longer cover the grant — ask-time validation makes that
    unreachable unless the target's holdings shrank between ask and accept. Dispatches
    on ``kind`` through the explicit ``_BOON_FULFILLERS`` table — a kind with no table
    entry raises ``ValueError`` loudly (mirrors ``validate_boon_ask``'s dispatch; a
    coding error, never a player-facing failure — every real kind is entered below).
    """
    boon = Boon.objects.select_for_update().get(pk=boon.pk)
    if boon.fulfilled_at is not None:
        return False

    request = boon.action_request
    if request.target_persona_id is None:
        msg = "A boon rides a targeted ask; this request has no target persona."
        raise ValidationError(msg)

    fulfiller = _BOON_FULFILLERS.get(boon.kind)
    if fulfiller is None:
        msg = f"unhandled boon kind {boon.kind}"
        raise ValueError(msg)
    fulfiller(boon, request)

    boon.fulfilled_at = timezone.now()
    boon.save(update_fields=["fulfilled_at"])
    return True


def _fulfill_money(boon: Boon, request: SceneActionRequest) -> None:
    if boon.amount <= 0:
        return
    from world.currency.services import get_or_create_purse, transfer  # noqa: PLC0415

    asker_sheet = request.initiator_persona.character_sheet
    target_sheet = request.target_persona.character_sheet
    transfer(
        amount=boon.amount,
        reason="boon",
        from_purse=get_or_create_purse(target_sheet),
        to_purse=get_or_create_purse(asker_sheet),
    )


def _fulfill_vault_item_kind(boon: Boon, request: SceneActionRequest) -> None:
    if boon.item_instance_id is None:
        return
    _fulfill_vault_item(boon, request)


def _fulfill_held_item_kind(boon: Boon, request: SceneActionRequest) -> None:
    if boon.item_instance_id is None:
        return
    _fulfill_held_item(boon, request)


def _fulfill_deed_kind(boon: Boon, request: SceneActionRequest) -> None:
    """RP-only — no mechanical transfer."""


def _fulfill_material(boon: Boon, request: SceneActionRequest) -> None:
    """The granted material boon: a tier pct of the target's bucket AT FULFILLMENT.

    Unlike MONEY, the amount is NOT frozen at ask time — no computed value is ever
    shown to the asker (#2540 slice 3 ruling, deliberate money asymmetry) — it's
    derived fresh here, against whatever the target's bucket holds right now, minimum
    1 when the bucket is non-empty. Spends the target's bucket then credits the
    asker's — never a bare balance write, so a mid-transfer crash cannot mint or lose
    value. Raises ``ValidationError`` (surfaced by the resolver's #1164 log-and-stamp
    unfulfillable path) if the bucket drained to empty, or below the computed amount,
    between the ask-time honest-availability check and this call — ask-time
    availability only guarantees non-empty AT ASK TIME, not at grant.
    """
    if boon.material_category_id is None:
        return
    from world.items.exceptions import InsufficientMaterialStock  # noqa: PLC0415
    from world.items.gems.buckets import (  # noqa: PLC0415
        credit_materials,
        material_value,
        spend_materials,
    )

    target_sheet = request.target_persona.character_sheet
    asker_sheet = request.initiator_persona.character_sheet
    category = boon.material_category
    bucket = material_value(target_sheet, category)
    if bucket <= 0:
        msg = "They no longer have that to give."
        raise ValidationError(msg)
    pct, _shift = BOON_SUM_TIERS.get(boon.sum_tier, BOON_SUM_TIERS[BoonSumTier.GREAT])
    amount = max(1, bucket * pct // 100)
    try:
        spend_materials(target_sheet, category, amount)
    except InsufficientMaterialStock as exc:
        msg = "They no longer have enough of that to give."
        raise ValidationError(msg) from exc
    credit_materials(asker_sheet, category, amount)


_BOON_FULFILLERS: dict[str, Callable[[Boon, SceneActionRequest], None]] = {
    BoonKind.MONEY: _fulfill_money,
    BoonKind.VAULT_ITEM: _fulfill_vault_item_kind,
    BoonKind.HELD_ITEM: _fulfill_held_item_kind,
    BoonKind.DEED: _fulfill_deed_kind,
    BoonKind.MATERIAL: _fulfill_material,
}


def _fulfill_held_item(boon: Boon, request: SceneActionRequest) -> None:
    """The granted held-item boon: the target hands the named item to the asker.

    A lean sheet-level transfer reusing ``give``'s pieces without its co-location and
    CharacterState requirements (the grant may resolve at consent time, not from a live
    command): unequip if worn, move the physical object to the asker when one exists
    (dematerialize on a failed move — custody is the row, the prop can rematerialize),
    switch the holder, and book an ``OwnershipEvent(TRANSFERRED)`` snapshotting the
    personas each side presented in the scene. Raises ``ValidationError`` (surfaced by
    the resolver's unfulfillable branch) if the target no longer holds the item.
    """
    from world.items.constants import OwnershipEventType  # noqa: PLC0415
    from world.items.models import ItemInstance, OwnershipEvent  # noqa: PLC0415
    from world.items.services.equip import unequip_item  # noqa: PLC0415

    target_sheet = request.target_persona.character_sheet
    asker_sheet = request.initiator_persona.character_sheet
    item = ItemInstance.objects.select_for_update().get(pk=boon.item_instance_id)
    if item.holder_character_sheet_id != target_sheet.pk:
        msg = "They no longer hold the asked item."
        raise ValidationError(msg)

    # Snapshot rows before iteration — unequip_item deletes them as we go (give's pattern).
    for equipped in list(item.equipped_slots.all()):
        unequip_item(equipped_item=equipped)
    if item.game_object is not None:
        asker_character = asker_sheet.character
        if not item.game_object.move_to(asker_character, quiet=True):
            item.game_object.delete()
            item.game_object = None
    item.holder_character_sheet = asker_sheet
    item.save(update_fields=["holder_character_sheet", "game_object"])
    OwnershipEvent.objects.create(
        item_instance=item,
        event_type=OwnershipEventType.TRANSFERRED,
        from_character_sheet=target_sheet,
        to_character_sheet=asker_sheet,
        from_persona_display=request.target_persona,
        to_persona_display=request.initiator_persona,
        notes="boon",
    )


def _fulfill_vault_item(boon: Boon, request: SceneActionRequest) -> None:
    """The granted vault boon: the target withdraws the item to the asker's hands.

    Routes through the vault's own audited withdraw service — the target is the
    authority, the asker the recipient. Raises ``ValidationError`` (surfaced by the
    resolver's unfulfillable branch) if the item left the vault or the target lost
    authority between ask and accept.
    """
    from world.items.org_vault_models import VaultHolding  # noqa: PLC0415
    from world.items.services.org_vault import withdraw_item_from_vault  # noqa: PLC0415

    holding = (
        VaultHolding.objects.filter(item_instance_id=boon.item_instance_id)
        .select_related("vault__organization")
        .first()
    )
    if holding is None:
        msg = "The asked item is no longer in a vault."
        raise ValidationError(msg)
    withdraw_item_from_vault(
        organization=holding.vault.organization,
        persona=request.target_persona,
        item_instance=boon.item_instance,
        to_persona=request.initiator_persona,
        reason="boon",
    )


def character_has_item_pointer(*, sheet: CharacterSheet, item: ItemInstance) -> bool:
    """The 2026-08-27 exact-pointer ruling: a named-item ask needs prior knowledge.

    True when the character's roster entry holds ANY of: a discovered clue whose ITEM
    target names this instance (or names its template with no instance pinned), a KNOWN
    codex entry about it, or known secret knowledge about it (same instance-or-template
    match). NPC pointing is content convention (dialogue names the item), not schema.

    Answers knowledge only — a destroyed item can still be "known", callers that care
    about liveness (an actual boon ask) check that separately.
    """
    from django.db.models import Q  # noqa: PLC0415

    from world.clues.constants import ClueTargetKind  # noqa: PLC0415
    from world.clues.models import CharacterClue  # noqa: PLC0415
    from world.codex.constants import CodexKnowledgeStatus  # noqa: PLC0415
    from world.codex.models import CharacterCodexKnowledge  # noqa: PLC0415
    from world.roster.models import RosterEntry  # noqa: PLC0415
    from world.secrets.models import SecretKnowledge  # noqa: PLC0415

    try:
        roster_entry = sheet.roster_entry
    except RosterEntry.DoesNotExist:
        return False

    if (
        CharacterClue.objects.filter(
            roster_entry=roster_entry,
            clue__target_kind=ClueTargetKind.ITEM,
        )
        .filter(
            Q(clue__target_item_instance=item)
            | Q(
                clue__target_item_instance__isnull=True,
                clue__target_item_template_id=item.template_id,
            )
        )
        .exists()
    ):
        return True

    if (
        CharacterCodexKnowledge.objects.filter(
            roster_entry=roster_entry,
            status=CodexKnowledgeStatus.KNOWN,
        )
        .filter(
            Q(entry__subject_item_instance=item)
            | Q(
                entry__subject_item_instance__isnull=True,
                entry__subject_item_template_id=item.template_id,
            )
        )
        .exists()
    ):
        return True

    return (
        SecretKnowledge.objects.filter(roster_entry=roster_entry)
        .filter(
            Q(secret__subject_item_instance=item)
            | Q(
                secret__subject_item_instance__isnull=True,
                secret__subject_item_template_id=item.template_id,
            )
        )
        .exists()
    )


@dataclass(frozen=True)
class PointerItemOption:
    """One entry of the boon-options ``pointer_items`` list (#2540 slice 3 UI seam)."""

    item_instance_id: int
    name: str
    source: str  # "held" | "vault"


def _asker_pointer_ids(roster_entry: RosterEntry) -> tuple[set[int], set[int]]:
    """The asker's pointer-known item template/instance ids, across all three surfaces.

    Three queries total (one per knowledge surface, mirroring ``character_has_item_
    pointer``'s per-surface shape) — never a query per item. Returns
    ``(template_ids, instance_ids)``: a template id means "any instance of this
    template is known"; an instance id is an exact pin (does NOT also imply its
    template id is known — an instance-pinned pointer names ONLY that instance).
    """
    from world.clues.constants import ClueTargetKind  # noqa: PLC0415
    from world.clues.models import CharacterClue  # noqa: PLC0415
    from world.codex.constants import CodexKnowledgeStatus  # noqa: PLC0415
    from world.codex.models import CharacterCodexKnowledge  # noqa: PLC0415
    from world.secrets.models import SecretKnowledge  # noqa: PLC0415

    rows = [
        *CharacterClue.objects.filter(
            roster_entry=roster_entry, clue__target_kind=ClueTargetKind.ITEM
        ).values_list("clue__target_item_template_id", "clue__target_item_instance_id"),
        *CharacterCodexKnowledge.objects.filter(
            roster_entry=roster_entry,
            status=CodexKnowledgeStatus.KNOWN,
            entry__subject_item_template_id__isnull=False,
        ).values_list("entry__subject_item_template_id", "entry__subject_item_instance_id"),
        *SecretKnowledge.objects.filter(
            roster_entry=roster_entry, secret__subject_item_template_id__isnull=False
        ).values_list("secret__subject_item_template_id", "secret__subject_item_instance_id"),
    ]
    template_ids: set[int] = set()
    instance_ids: set[int] = set()
    for template_id, instance_id in rows:
        if instance_id is not None:
            instance_ids.add(instance_id)
        elif template_id is not None:
            template_ids.add(template_id)
    return template_ids, instance_ids


def _target_accessible_vault_ids(target_persona: Persona) -> list[int]:
    """Vaults the target holds active withdraw authority in — ONE joined query.

    Mirrors ``can_access_vault``'s rule (active membership, rank tier <=
    ``withdraw_rank_max``) inline rather than calling that per-pair predicate per
    membership row, which would be a query-per-membership loop for a list endpoint.
    """
    from django.db.models import F  # noqa: PLC0415

    from world.societies.models import OrganizationMembership  # noqa: PLC0415

    return list(
        OrganizationMembership.objects.filter(
            persona=target_persona,
            left_at__isnull=True,
            exiled_at__isnull=True,
            organization__item_vault__isnull=False,
            rank__tier__lte=F("organization__item_vault__withdraw_rank_max"),
        ).values_list("organization__item_vault__id", flat=True)
    )


def pointer_known_items_for_target(
    *, asker_sheet: CharacterSheet, target_persona: Persona
) -> list[PointerItemOption]:
    """Boon-options display seam (#2540 slice 3): the asker's pointer-known items
    relevant to THIS target — held by them, or sitting in a vault they can withdraw
    from. Computed from the ASKER's pointers only (their clues/codex/secrets); NEVER
    a browse of the target's actual holdings — a pointer the asker holds is the only
    window (visibility = eligibility, one predicate — the same rule
    ``character_has_item_pointer`` enforces at ask time). Batched: a handful of
    queries total, never a query per candidate item.
    """
    from django.db.models import Q  # noqa: PLC0415

    from world.items.models import ItemInstance  # noqa: PLC0415
    from world.items.org_vault_models import VaultHolding  # noqa: PLC0415
    from world.roster.models import RosterEntry  # noqa: PLC0415

    try:
        roster_entry = asker_sheet.roster_entry
    except RosterEntry.DoesNotExist:
        return []

    template_ids, instance_ids = _asker_pointer_ids(roster_entry)
    if not template_ids and not instance_ids:
        return []
    pointer_filter = Q(pk__in=instance_ids) | Q(template_id__in=template_ids)

    options: list[PointerItemOption] = [
        PointerItemOption(item_instance_id=item.pk, name=str(item), source="held")
        for item in ItemInstance.objects.filter(
            holder_character_sheet=target_persona.character_sheet
        ).filter(pointer_filter)
    ]

    vault_ids = _target_accessible_vault_ids(target_persona)
    if vault_ids:
        vault_pointer_filter = Q(item_instance_id__in=instance_ids) | Q(
            item_instance__template_id__in=template_ids
        )
        options.extend(
            PointerItemOption(
                item_instance_id=holding.item_instance_id,
                name=str(holding.item_instance),
                source="vault",
            )
            for holding in VaultHolding.objects.filter(vault_id__in=vault_ids)
            .select_related("item_instance")
            .filter(vault_pointer_filter)
        )
    return options


def _resolve_boon(request: SceneActionRequest, result: EnhancedSceneActionResult) -> None:
    """Post-resolution side-effect for the ``boon`` action key (both consent paths).

    On a successful roll: fulfill the boon, then charge the per-Boon affection cost —
    the granter's regard for the asker drops by ``BOON_AFFECTION_COST``, deduped on the
    Boon row itself so serial asks stack even within one scene.
    """
    from world.relationships.services import apply_affection_shift  # noqa: PLC0415

    boon = Boon.objects.filter(action_request=request).first()
    if boon is None:
        return
    main_result = result.action_resolution.main_result
    check_result = main_result.check_result if main_result is not None else None
    success = (check_result.success_level > 0) if check_result is not None else False
    if not success:
        return
    try:
        newly_fulfilled = fulfill_boon(boon)
    except ValidationError:
        # Coverage evaporated between ask and accept (ask-time validation caps it
        # otherwise). Interim log-and-continue (#1164) — the roll stands, nothing moves.
        logger.warning("boon %s granted but unfulfillable", boon.pk)
        return
    if not newly_fulfilled:
        return
    apply_affection_shift(
        source=request.target_persona.character_sheet,
        target=request.initiator_persona.character_sheet,
        scene=request.scene,
        effect=None,
        boon=boon,
        amount=-BOON_AFFECTION_COST,
    )


for _boon_action_key in BOON_ACTION_KEYS:
    register_resolver(_boon_action_key, _resolve_boon)
