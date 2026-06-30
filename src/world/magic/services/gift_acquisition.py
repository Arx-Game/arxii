"""Post-CG gift acquisition services (#1587).

spend_xp_on_gift_unlock: the XP gate (ADR-0053 — gate removal only).
accept_technique_offer: the acquisition step (implicitly acquires the
gift on the first technique learned from it).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import transaction

from world.character_sheets.models import CharacterSheet
from world.magic.constants import TargetKind
from world.magic.exceptions import XPInsufficient
from world.magic.models import (
    CharacterGiftUnlock,
    GiftAcquisitionConfig,
)
from world.magic.services.alterations import enforce_advancement_gate
from world.progression.models import XPTransaction
from world.progression.services.awards import get_or_create_xp_tracker
from world.progression.types import ProgressionReason

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.magic.models import (
        CharacterTechnique,
        Gift,
        GiftUnlock,
        TechniqueTeachingOffer,
    )


def get_gift_acquisition_config() -> GiftAcquisitionConfig:
    """Lazily create and return the singleton GiftAcquisitionConfig (pk=1)."""
    config, _ = GiftAcquisitionConfig.objects.get_or_create(pk=1)
    return config


# ---------------------------------------------------------------------------
# XP-cost computation + XP-gate service
# ---------------------------------------------------------------------------


def compute_gift_unlock_xp_cost(unlock: GiftUnlock, learner: CharacterSheet) -> int:
    """Compute XP cost for a learner to acquire a GiftUnlock.

    Returns ``unlock.xp_cost`` for path-neutral unlocks (no paths set)
    and for learners whose path history intersects the unlock's paths.
    Returns ``int(unlock.xp_cost * unlock.out_of_path_multiplier)``
    for out-of-Path learners. Mirrors ``compute_thread_weaving_xp_cost``.
    """
    unlock_paths = set(unlock.paths.all())
    if not unlock_paths:
        return unlock.xp_cost

    learner_paths = {h.path for h in learner.character.path_history.select_related("path")}
    if learner_paths & unlock_paths:
        return unlock.xp_cost

    return int(unlock.xp_cost * unlock.out_of_path_multiplier)


@transaction.atomic
def spend_xp_on_gift_unlock(
    learner: CharacterSheet,
    unlock: GiftUnlock,
    *,
    teacher=None,
) -> CharacterGiftUnlock:
    """Spend XP to purchase a GiftUnlock receipt (the gate, ADR-0053).

    Does NOT acquire the gift — acquisition is a separate step
    (``accept_technique_offer``). Mirrors ``accept_thread_weaving_unlock``
    minus the AP.

    Args:
        learner: The character purchasing the unlock.
        unlock: The authored GiftUnlock to purchase.
        teacher: Optional RosterTenure that facilitated the purchase.

    Returns:
        The new CharacterGiftUnlock receipt.

    Raises:
        XPInsufficient: If the learner doesn't have enough XP.
    """
    enforce_advancement_gate(learner)

    xp_cost = compute_gift_unlock_xp_cost(unlock, learner)
    account = learner.character.account
    if account is None:
        msg = "Learner character has no linked account; cannot spend XP."
        raise XPInsufficient(msg)

    xp_tracker = get_or_create_xp_tracker(account)
    if not xp_tracker.can_spend(xp_cost):
        msg = (
            f"Need {xp_cost} XP to unlock {unlock.gift.name}, have {xp_tracker.current_available}."
        )
        raise XPInsufficient(msg)

    xp_tracker.spend_xp(xp_cost)

    XPTransaction.objects.create(
        account=account,
        amount=-xp_cost,
        reason=ProgressionReason.XP_PURCHASE,
        description=f"Gift unlock: {unlock.gift.name}",
        character=learner.character,
        gm=None,
    )

    return CharacterGiftUnlock.objects.create(
        character=learner,
        unlock=unlock,
        xp_spent=xp_cost,
        teacher=teacher,
    )


# ---------------------------------------------------------------------------
# Technique cap helpers
# ---------------------------------------------------------------------------


def count_techniques_for_gift(sheet: CharacterSheet, gift: Gift) -> int:
    """Count CharacterTechnique rows for ``gift``.

    Variants (TechniqueVariant) are derived on read (ADR-0055) — they are
    never stored as CharacterTechnique rows, so all CharacterTechnique rows
    for this gift are base techniques that count against the cap.
    """
    from world.magic.models import CharacterTechnique  # noqa: PLC0415

    return CharacterTechnique.objects.filter(
        character=sheet,
        technique__gift=gift,
    ).count()


def _gift_thread_depth(sheet: CharacterSheet, gift: Gift) -> int:
    """Depth of the character's GIFT thread for ``gift`` (0 if none).

    depth = max(1, thread.level // 10) when a thread exists; 0 otherwise.
    A level-0 thread (freshly provisioned) has depth max(1, 0) = 1.
    """
    character = sheet.character
    thread = next(
        (
            t
            for t in character.threads.all()
            if t.target_kind == TargetKind.GIFT and t.target_gift_id == gift.pk
        ),
        None,
    )
    if thread is None:
        return 0
    return max(1, thread.level // 10)


def get_technique_cap_for_gift(sheet: CharacterSheet, gift: Gift) -> int:
    """Max techniques a character can learn for ``gift`` at current thread level.

    Returns ``config.techniques_per_thread_level × depth``. A character
    with no GIFT thread (gift not yet acquired) has depth 0 → cap 0.
    """
    config = get_gift_acquisition_config()
    depth = _gift_thread_depth(sheet, gift)
    return config.techniques_per_thread_level * depth


# ---------------------------------------------------------------------------
# Acquisition step
# ---------------------------------------------------------------------------


def _resolve_resonance_for(gift: Gift, claimed_ids: set[int]):
    """Resonance for a newly-granted gift's latent thread.

    Prefer a claimed resonance in the gift's supported set; otherwise
    the gift's first supported resonance; None if the gift supports none.
    Lifted from path_magic._grant_resonance_for.
    """
    supported = gift.cached_resonances
    if not supported:
        return None
    return next((r for r in supported if r.pk in claimed_ids), supported[0])


@transaction.atomic
def accept_technique_offer(
    learner: CharacterSheet,
    offer: TechniqueTeachingOffer,
) -> CharacterTechnique:
    """Accept a TechniqueTeachingOffer — the acquisition step (#1587).

    If the learner doesn't yet have the technique's gift, this implicitly
    acquires it (via grant_gift_to_character). The first technique from
    a not-yet-acquired gift costs more AP (config.first_technique_ap_multiplier)
    and requires a CharacterGiftUnlock receipt (the XP gate).

    Args:
        learner: The character accepting the offer.
        offer: The TechniqueTeachingOffer being accepted.

    Returns:
        The new CharacterTechnique.

    Raises:
        GiftUnlockMissing: First technique from a gift with no receipt.
        TechniqueCapExceeded: At the cap for this gift at current thread level.
    """
    from world.achievements.constants import AccessChangeSource  # noqa: PLC0415
    from world.achievements.discovery import announce_access_change  # noqa: PLC0415
    from world.action_points.models import ActionPointPool  # noqa: PLC0415
    from world.magic.exceptions import (  # noqa: PLC0415
        GiftUnlockMissing,
        TechniqueCapExceeded,
    )
    from world.magic.models import (  # noqa: PLC0415
        CharacterGift,
        CharacterResonance,
        CharacterTechnique,
    )
    from world.magic.specialization.services import (  # noqa: PLC0415
        grant_gift_to_character,
    )

    # Lock the learner's sheet row to serialize first-acquisition (concurrency).
    sheet = CharacterSheet.objects.select_for_update().get(pk=learner.pk)

    technique = offer.technique
    gift = technique.gift

    # 1. Check learner doesn't already know this technique.
    if CharacterTechnique.objects.filter(character=sheet, technique=technique).exists():
        msg = f"{sheet} already knows {technique.name}."
        raise ValueError(msg)

    # 2. Check if learner has the gift.
    has_gift = CharacterGift.objects.filter(character=sheet, gift=gift).exists()

    # 3. Compute AP cost.
    config = get_gift_acquisition_config()
    if not has_gift:
        # Check the XP gate (CharacterGiftUnlock receipt).
        if not CharacterGiftUnlock.objects.filter(character=sheet, unlock__gift=gift).exists():
            raise GiftUnlockMissing
        ap_cost = offer.learn_ap_cost * config.first_technique_ap_multiplier
    else:
        ap_cost = offer.learn_ap_cost

    # 4. Implicit gift acquisition (first technique).
    if not has_gift:
        claimed_ids = set(
            CharacterResonance.objects.filter(character_sheet=sheet).values_list(
                "resonance_id", flat=True
            )
        )
        resonance = _resolve_resonance_for(gift, claimed_ids)
        grant_gift_to_character(sheet, gift, resonance=resonance)

    # 5. Check technique cap (after acquisition so the thread exists for depth).
    current_count = count_techniques_for_gift(sheet, gift)
    cap = get_technique_cap_for_gift(sheet, gift)
    if current_count >= cap:
        raise TechniqueCapExceeded

    # 6. Spend learner AP. Consume teacher's banked AP.
    # Gold transfer deferred — mirrors TODO in CodexTeachingOffer
    # and accept_thread_weaving_unlock; no economy system exists yet.
    learner_pool = ActionPointPool.get_or_create_for_character(sheet.character)
    if not learner_pool.can_afford(ap_cost):
        from world.magic.exceptions import MagicError  # noqa: PLC0415

        msg = f"Insufficient action points (need {ap_cost}, have {learner_pool.current})."
        raise MagicError(msg)
    learner_pool.spend(ap_cost)
    teacher_pool = ActionPointPool.get_or_create_for_character(offer.teacher.character)
    teacher_pool.consume_banked(offer.banked_ap)

    # 7. Mint CharacterTechnique.
    ct = CharacterTechnique.objects.create(character=sheet, technique=technique)

    # 8. Announce.
    announce_access_change(
        sheet,
        gained=[technique],
        lost=[],
        source=AccessChangeSource.GIFT_ACQUISITION,
    )

    return ct
