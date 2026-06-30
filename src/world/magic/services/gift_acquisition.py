"""Post-CG gift acquisition services (#1587).

spend_xp_on_gift_unlock: the XP gate (ADR-0053 — gate removal only).
accept_technique_offer: the acquisition step (implicitly acquires the
gift on the first technique learned from it).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import transaction

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
    from world.magic.models import Gift, GiftUnlock


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
