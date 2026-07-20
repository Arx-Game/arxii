"""Boon services (#2540): the structured social ask — validation, band, fulfillment.

A Boon names what an asker wants from a target (money, a held item, a vault item, or a
deed) and rides the ``SceneActionRequest`` consent flow. This module owns the ask-time
eligibility validation (dial 1), the NPC-side relative-cost difficulty band (dial 2),
fulfillment on a granted ask, and the per-Boon affection cost (the dial-3 drain).

Fulfillment fires via the ``boon`` action resolver (``register_resolver``), which both
resolution paths invoke — NPC auto-accept at dispatch and a piloted target's later
accept. It must NOT ride ``BoonAction.execute()``: the consent paths never call
``execute()`` (the Blackmail mint asymmetry), and it must not ride a seeded
``SHIFT_AFFECTION`` ``ConsequenceEffect`` either — the consent path resolves with a
sceneless ``ResolutionContext``, where scene-keyed data effects skip.

Only ``MONEY`` fulfillment moves value in this slice: it routes through the single
currency mutation point (``transfer``), target purse → asker purse. ``HELD_ITEM``
awaits an item-ownership-transfer seam, ``VAULT_ITEM`` awaits the org vault (#2540
Layer 4), and ``DEED`` is RP-only (no mechanical transfer). Idempotent: a fulfilled
Boon is a no-op (claimed under row lock, so concurrent fulfills cannot double-move).
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
    from world.character_sheets.models import CharacterSheet
    from world.scenes.action_models import SceneActionRequest
    from world.scenes.models import Persona
    from world.scenes.types import EnhancedSceneActionResult

logger = logging.getLogger(__name__)

BOON_ACTION_KEY = "boon"

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


@dataclass(frozen=True)
class BoonAsk:
    """The structured payload of a boon ask, passed into ``create_action_request``.

    MONEY asks carry a ``sum_tier`` (never a raw amount — #2540 ruling); the concrete
    coppers are computed from the target's purse at validation time.
    """

    kind: str
    sum_tier: str = ""
    item_instance_id: int | None = None
    deed_text: str = ""


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


def validate_boon_ask(*, ask: BoonAsk, target_persona: Persona | None) -> None:
    """Ask-time eligibility (dial 1): an ask the target could not grant never exists.

    Raises ``ValidationError`` on: no target, an unknown kind, a MONEY ask with no
    valid sum tier or against a penniless target (options only present when grantable
    — #2540 ruling), a HELD_ITEM ask for an item the target does not hold, an empty
    DEED, or a VAULT_ITEM ask for an item outside the target's withdraw authority.
    """
    if target_persona is None:
        msg = "A boon is asked of someone — it needs a target."
        raise ValidationError(msg)
    if ask.kind not in BoonKind.values:
        msg = "Unknown boon kind."
        raise ValidationError(msg)
    if ask.kind == BoonKind.MONEY:
        _validate_money_ask(ask, target_persona.character_sheet)
    elif ask.kind == BoonKind.HELD_ITEM:
        _validate_held_item_ask(ask, target_persona.character_sheet)
    elif ask.kind == BoonKind.VAULT_ITEM:
        _validate_vault_item_ask(ask, target_persona)
    elif not ask.deed_text.strip():
        msg = "A deed boon needs the deed spelled out."
        raise ValidationError(msg)


def _validate_money_ask(ask: BoonAsk, target_sheet: CharacterSheet) -> None:
    """A money ask names a sum tier; the option only exists when the purse could pay it."""
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


def _validate_held_item_ask(ask: BoonAsk, target_sheet: CharacterSheet) -> None:
    from world.items.models import ItemInstance  # noqa: PLC0415

    if ask.item_instance_id is None:
        msg = "A held-item boon names the item asked for."
        raise ValidationError(msg)
    held = ItemInstance.objects.filter(
        pk=ask.item_instance_id, holder_character_sheet=target_sheet
    ).exists()
    if not held:
        msg = "They do not hold that item."
        raise ValidationError(msg)


def _validate_vault_item_ask(ask: BoonAsk, target_persona: Persona) -> None:
    """Dial-1 eligibility for a vault ask: the target must hold withdraw authority.

    A granted vault boon is the target *exercising* their org-vault authority on the
    asker's behalf (#2540 Layer 4) — so the ask is only eligible when the named item
    sits in a vault the target can withdraw from.
    """
    from world.items.org_vault_models import VaultHolding  # noqa: PLC0415
    from world.items.services.org_vault import can_access_vault  # noqa: PLC0415

    if ask.item_instance_id is None:
        msg = "A vault boon names the item asked for."
        raise ValidationError(msg)
    holding = (
        VaultHolding.objects.filter(item_instance_id=ask.item_instance_id)
        .select_related("vault")
        .first()
    )
    if holding is None or not can_access_vault(holding.vault, target_persona):
        msg = "They cannot draw that from any vault."
        raise ValidationError(msg)


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
    )


def boon_cost_tier_shift(boon: Boon, target_sheet: CharacterSheet) -> int:  # noqa: ARG001
    """Dial 2: how many difficulty tiers this ask's relative cost adds.

    For MONEY the chosen sum tier IS the band (#2540 ruling — relative by construction).
    ``target_sheet`` stays in the signature for the item kinds' future appraisal-vs-means
    computation.
    """
    if boon.kind == BoonKind.MONEY:
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
    the boon's request has no target persona, or (from ``transfer``) if a MONEY boon's
    target cannot cover it — ask-time validation makes that unreachable unless the
    target's purse shrank between ask and accept.
    """
    boon = Boon.objects.select_for_update().get(pk=boon.pk)
    if boon.fulfilled_at is not None:
        return False

    request = boon.action_request
    if request.target_persona_id is None:
        msg = "A boon rides a targeted ask; this request has no target persona."
        raise ValidationError(msg)

    if boon.kind == BoonKind.MONEY and boon.amount > 0:
        from world.currency.services import get_or_create_purse, transfer  # noqa: PLC0415

        asker_sheet = request.initiator_persona.character_sheet
        target_sheet = request.target_persona.character_sheet
        transfer(
            amount=boon.amount,
            reason="boon",
            from_purse=get_or_create_purse(target_sheet),
            to_purse=get_or_create_purse(asker_sheet),
        )
    elif boon.kind == BoonKind.VAULT_ITEM and boon.item_instance_id is not None:
        _fulfill_vault_item(boon, request)
    # HELD_ITEM fulfillment: follow-up slice (needs the ownership-transfer seam, #2540).

    boon.fulfilled_at = timezone.now()
    boon.save(update_fields=["fulfilled_at"])
    return True


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


register_resolver(BOON_ACTION_KEY, _resolve_boon)
