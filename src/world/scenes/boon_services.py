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

from world.scenes.action_constants import BoonKind
from world.scenes.action_resolvers import register_resolver
from world.scenes.boon_models import Boon

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.scenes.action_models import SceneActionRequest
    from world.scenes.models import Persona
    from world.scenes.types import EnhancedSceneActionResult

logger = logging.getLogger(__name__)

BOON_ACTION_KEY = "boon"

# Dial 2 — relative-cost band (#2540 addendum): a MONEY ask's difficulty shift derives
# from the amount as a fraction of the target's purse, in percent. Each (threshold_pct,
# tier_shift) row reads "asks up to this fraction shift the check this many tiers".
# PLACEHOLDER thresholds and shifts — magnitudes are Apostate's tuning call.
BOON_MONEY_BAND_TIERS: tuple[tuple[int, int], ...] = (
    (5, 0),  # trivial — pocket change to them
    (20, 1),  # notable
    (50, 2),  # painful
    (100, 3),  # ruinous
)
# PLACEHOLDER flat shifts for the non-money kinds until item appraisal-vs-means and the
# vault land: asking for a named possession is painful; a deed is notable.
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
    """The structured payload of a boon ask, passed into ``create_action_request``."""

    kind: str
    amount: int = 0
    item_instance_id: int | None = None
    deed_text: str = ""


def validate_boon_ask(*, ask: BoonAsk, target_persona: Persona | None) -> None:
    """Ask-time eligibility (dial 1): reject an ask the target could not fulfill.

    Raises ``ValidationError`` on: no target, an unknown kind, a MONEY ask the target
    cannot cover (so a granted boon can never hit insufficient funds), a HELD_ITEM ask
    for an item the target does not hold, an empty DEED, or a VAULT_ITEM ask (stubbed
    until the org vault, #2540 Layer 4).
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
        msg = "Vault boons await the org vault system."
        raise ValidationError(msg)
    elif not ask.deed_text.strip():
        msg = "A deed boon needs the deed spelled out."
        raise ValidationError(msg)


def _validate_money_ask(ask: BoonAsk, target_sheet: CharacterSheet) -> None:
    from world.currency.services import get_or_create_purse  # noqa: PLC0415

    if ask.amount <= 0:
        msg = "A money boon asks for a positive number of coppers."
        raise ValidationError(msg)
    if ask.amount > get_or_create_purse(target_sheet).balance:
        msg = "They could not cover that even if they wanted to."
        raise ValidationError(msg)


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


def create_boon_for_request(request: SceneActionRequest, ask: BoonAsk) -> Boon:
    """Persist the validated ask payload on its request (before NPC auto-resolve fires)."""
    return Boon.objects.create(
        action_request=request,
        kind=ask.kind,
        amount=ask.amount,
        item_instance_id=ask.item_instance_id,
        deed_text=ask.deed_text,
    )


def boon_cost_tier_shift(boon: Boon, target_sheet: CharacterSheet) -> int:
    """Dial 2: how many difficulty tiers this ask's relative cost adds."""
    if boon.kind == BoonKind.MONEY:
        from world.currency.services import get_or_create_purse  # noqa: PLC0415

        balance = get_or_create_purse(target_sheet).balance
        if balance <= 0:
            return BOON_MONEY_BAND_TIERS[-1][1]
        pct = boon.amount * 100 // balance
        for threshold_pct, shift in BOON_MONEY_BAND_TIERS:
            if pct <= threshold_pct:
                return shift
        return BOON_MONEY_BAND_TIERS[-1][1]
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
    # HELD_ITEM / VAULT_ITEM fulfillment: follow-up slices (see #2540).

    boon.fulfilled_at = timezone.now()
    boon.save(update_fields=["fulfilled_at"])
    return True


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
