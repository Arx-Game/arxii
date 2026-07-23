"""Post-CG gift acquisition services (#1587).

spend_xp_on_gift_unlock: the XP gate (ADR-0053 — gate removal only).
charge_and_learn: the shared charge+acquire core (implicitly acquires the
gift on the first technique learned) — one seam, two front doors:
accept_technique_offer (player-to-player teaching, #1587) and the Academy
TRAIN offer handler (world.npc_services.effects.run_train_offer, #2440).
charge_and_learn also applies the Unbound magic-learning AP surcharge (#2442,
magic_learning_ap_cost_surcharge_percent) — TIME, not power; resonance
earning/spending is untouched.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from django.db import transaction

from world.character_sheets.models import CharacterSheet
from world.magic.constants import GiftKind, TargetKind
from world.magic.exceptions import XPInsufficient
from world.magic.models import (
    CharacterGiftUnlock,
    GiftAcquisitionConfig,
)
from world.magic.services.alterations import enforce_advancement_gate
from world.magic.services.threads import thread_level_multiplier
from world.progression.models import XPTransaction
from world.progression.selectors import current_path_for_character
from world.progression.services.awards import get_or_create_xp_tracker
from world.progression.types import ProgressionReason

if TYPE_CHECKING:
    from world.achievements.constants import AccessChangeSource
    from world.character_sheets.models import CharacterSheet
    from world.currency.models import OrganizationTreasury
    from world.magic.models import (
        CharacterTechnique,
        Gift,
        GiftUnlock,
        Technique,
        TechniqueTeachingOffer,
    )
    from world.roster.models import RosterTenure


def get_gift_acquisition_config() -> GiftAcquisitionConfig:
    """Lazily create and return the singleton GiftAcquisitionConfig (pk=1)."""
    config = GiftAcquisitionConfig.objects.cached_singleton()
    if config is None:
        config, _ = GiftAcquisitionConfig.objects.get_or_create(pk=1)
    return config


def can_learn_technique(learner: CharacterSheet, technique: Technique) -> bool:
    """True if the learner's current path permits this technique's style.

    Checks ``technique.style.allowed_paths`` (M2M, blank = all paths)
    against the learner's current path. A character with no path
    history (pre-awakening / NPCs) is unrestricted.

    Cross-path learning (#2538): if the learner's current path is NOT in
    ``allowed_paths``, checks whether the learner meets the TraitRequirements
    of any path that IS in ``allowed_paths``. If so, the technique is
    learnable — the character has qualified via stat/skill investment even
    without taking that path. Derive-on-read (ADR-0014).

    Args:
        learner: The character sheet wanting to learn the technique.
        technique: The technique being learned.

    Returns:
        True if the technique's style is permitted for the learner's path.
    """
    path = current_path_for_character(learner.character)
    if path is None:
        return True
    allowed = technique.style.cached_allowed_paths
    if not allowed:
        return True
    if path in allowed:
        return True
    # Cross-path learning: check if the character meets any allowed path's
    # TraitRequirements (#2538). Reuses the same requirement rows authored
    # for hybrid path entry gating. Only applies when the allowed path has
    # authored requirements — a path with no requirements is NOT open to
    # cross-learning (its allowed_paths restriction stands as-is).
    from world.progression.models import TraitRequirement  # noqa: PLC0415
    from world.progression.services.spends import check_requirements_for_path  # noqa: PLC0415

    for allowed_path in allowed:
        if allowed_path.pk == path.pk:
            continue
        # Only cross-learn via paths that have authored requirements
        if not TraitRequirement.objects.filter(path=allowed_path, is_active=True).exists():
            continue
        met, _ = check_requirements_for_path(learner.character, allowed_path)
        if met:
            return True
    return False


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

    learner_paths = {h.path for h in learner.path_history.select_related("path")}
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
        character=learner,
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

    depth = max(1, round(thread_level_multiplier(thread.level))) (#1718) when a
    thread exists; 0 otherwise. This is a discrete technique-count multiplier,
    not the continuous combat-scaling factor `thread_level_multiplier` was
    designed for — `thread_level_multiplier` ramps linearly from 0.1 to 1.0
    across levels 1-9 (for smooth effect-magnitude scaling), which rounds to 0
    for levels 1-5. The `max(1, ...)` floor preserves this function's own
    invariant (stated above and previously true for all levels 1-25 under the
    old `max(1, level // 10)` formula): once a GIFT thread exists at level >= 1,
    depth never drops below 1. A freshly provisioned level-0 thread has depth
    round(thread_level_multiplier(0)) = round(1) = 1.
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
    # round(), not int() truncation: consistent with the site-wide #1718 decision
    # (see resonance.py); the return type here is `int` (a technique-count cap).
    # max(1, ...): depth is a discrete count multiplier that must never drop
    # below 1 for an existing thread, unlike the continuous combat-scaling use
    # of thread_level_multiplier elsewhere (see docstring above).
    return max(1, round(thread_level_multiplier(thread.level)))


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


def magic_learning_ap_cost_surcharge_percent(learner: CharacterSheet) -> int:
    """Live AP surcharge percent for magic-learning activities (#2442).

    Resolves the learner's ``magic_learning_ap_cost`` modifier through the live
    post-CG ``CharacterModifier`` resolution path
    (``world.mechanics.services.get_modifier_total``) — the same seam every other
    distinction-authored modifier is read through, NOT the CG-draft
    ``CharacterDraft._get_distinction_bonus`` helper (that only reads a draft's
    in-progress ``draft_data``, never a committed ``CharacterDistinction``). The
    "Unbound" drawback distinction (``world.seeds.character_creation
    .ensure_unbound_drawback_distinction``) is the sole authored source today
    (+50); 0 for a learner who has shed it (or never held it — e.g. via
    ``world.magic.services.tradition_membership.join_tradition``) and 0 (no
    surcharge) if the seed target row doesn't exist yet on this DB — mirrors the
    defensive-tolerance convention elsewhere in the #2441/#2442 cluster (e.g.
    ``tradition_membership._reapply_unbound_drawback``).
    """
    from world.magic.constants import (  # noqa: PLC0415
        MAGIC_LEARNING_AP_COST_TARGET_NAME,
        MAGIC_MODIFIER_CATEGORY_NAME,
    )
    from world.mechanics.models import ModifierTarget  # noqa: PLC0415
    from world.mechanics.services import get_modifier_total  # noqa: PLC0415

    target = ModifierTarget.objects.filter(
        name=MAGIC_LEARNING_AP_COST_TARGET_NAME,
        category__name=MAGIC_MODIFIER_CATEGORY_NAME,
    ).first()
    if target is None:
        return 0
    return get_modifier_total(learner, target)


@transaction.atomic
def charge_and_learn(  # noqa: C901, PLR0913 - shared core for two front doors; params co-equal
    learner: CharacterSheet,
    technique: Technique,
    *,
    base_ap_cost: int,
    source: AccessChangeSource,
    gold_cost: int = 0,
    gold_treasury: OrganizationTreasury | None = None,
    teacher_tenure: RosterTenure | None = None,
    teacher_banked_ap: int = 0,
) -> CharacterTechnique:
    """Shared charge+acquire core for technique acquisition (#1587, #2440).

    One seam, two front doors: ``accept_technique_offer`` (player-to-player
    teaching) and the Academy TRAIN offer handler
    (``world.npc_services.effects.run_train_offer``) both delegate here.

    If the learner doesn't yet have the technique's gift, this implicitly
    acquires it (via grant_gift_to_character). The first technique from
    a not-yet-acquired gift costs more AP (config.first_technique_ap_multiplier)
    and requires a CharacterGiftUnlock receipt (the XP gate).

    After the has-gift/major-gift multiplier, the Unbound magic-learning AP
    surcharge (#2442) scales the result: ``ceil(ap_cost × (100 + surcharge%) /
    100)``, where ``surcharge%`` is the learner's live ``magic_learning_ap_cost``
    modifier total (``magic_learning_ap_cost_surcharge_percent``, +50 while the
    "Unbound" drawback distinction is held, 0 once shed via
    ``world.magic.services.tradition_membership.join_tradition``).

    Args:
        learner: The character learning the technique.
        technique: The technique being learned.
        base_ap_cost: AP cost before the has-gift/major-gift multiplier is
            applied (``TechniqueTeachingOffer.learn_ap_cost`` /
            ``TrainOfferDetails.learn_ap_cost``).
        source: The AccessChangeSource for the announce message.
        gold_cost: Coin charged to the learner's purse (0 = free). Credited
            to ``gold_treasury`` via ``currency.transfer``.
        gold_treasury: Destination treasury for ``gold_cost``. Required
            (non-None) whenever ``gold_cost`` > 0.
        teacher_tenure: The player teacher whose banked AP is consumed
            (teaching-offer path only). None for NPC-trained acquisition —
            no banked-AP consumption happens.
        teacher_banked_ap: AP consumed from ``teacher_tenure``'s pool.
            Meaningless when ``teacher_tenure`` is None.

    Returns:
        The new CharacterTechnique.

    Raises:
        GiftUnlockMissing: First technique from a gift with no receipt.
        TechniqueCapExceeded: At the cap for this gift at current thread level.
        TechniqueStyleForbidden: Learner's path doesn't permit the style.
        MagicError: Insufficient action points.
        ValueError: Learner already knows this technique.
    """
    from world.action_points.models import ActionPointPool  # noqa: PLC0415
    from world.magic.exceptions import (  # noqa: PLC0415
        GiftUnlockMissing,
        MagicError,
        TechniqueCapExceeded,
        TechniqueStyleForbidden,
    )
    from world.magic.models import (  # noqa: PLC0415
        CharacterGift,
        CharacterResonance,
        CharacterTechnique,
    )
    from world.magic.services.technique_acquisition import (  # noqa: PLC0415
        learn_technique,
    )
    from world.magic.specialization.services import (  # noqa: PLC0415
        grant_gift_to_character,
    )

    # Lock the learner's sheet row to serialize first-acquisition (concurrency).
    sheet = CharacterSheet.objects.select_for_update().get(pk=learner.pk)

    gift = technique.gift

    # 1. Check learner doesn't already know this technique.
    if CharacterTechnique.objects.filter(character=sheet, technique=technique).exists():
        msg = f"{sheet} already knows {technique.name}."
        raise ValueError(msg)

    # 1b. Check path-style restriction (shared gate).
    if not can_learn_technique(sheet, technique):
        raise TechniqueStyleForbidden

    # 2. Check if learner has the gift.
    has_gift = CharacterGift.objects.filter(character=sheet, gift=gift).exists()

    # 3. Compute AP cost.
    config = get_gift_acquisition_config()
    if not has_gift:
        # Check the XP gate (CharacterGiftUnlock receipt).
        if not CharacterGiftUnlock.objects.filter(character=sheet, unlock__gift=gift).exists():
            raise GiftUnlockMissing
        ap_cost = base_ap_cost * config.first_technique_ap_multiplier
    elif gift.kind == GiftKind.MAJOR:
        ap_cost = base_ap_cost * config.major_gift_ap_multiplier
    else:
        ap_cost = base_ap_cost

    # 3b. Unbound magic-learning AP surcharge (#2442) — TIME, not power; applies
    # identically to both front doors (accept_technique_offer and #2440 TRAIN),
    # since both delegate here. ceil() so a fractional surcharge never rounds down
    # to a free ride.
    surcharge_percent = magic_learning_ap_cost_surcharge_percent(sheet)
    ap_cost = math.ceil(ap_cost * (100 + surcharge_percent) / 100)

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

    # 6. Spend learner AP. Consume teacher's banked AP (teaching path only).
    learner_pool = ActionPointPool.get_or_create_for_character(sheet.character)
    if not learner_pool.can_afford(ap_cost):
        msg = f"Insufficient action points (need {ap_cost}, have {learner_pool.current})."
        raise MagicError(msg)
    learner_pool.spend(ap_cost)
    if teacher_tenure is not None:
        teacher_pool = ActionPointPool.get_or_create_for_character(teacher_tenure.character)
        teacher_pool.consume_banked(teacher_banked_ap)

    # 6b. Spend learner gold (Academy TRAIN path only — teaching-offer gold
    # is still deferred, mirrors TODO in CodexTeachingOffer and
    # accept_thread_weaving_unlock; no economy system existed until #2428).
    if gold_cost > 0:
        from world.currency.services import (  # noqa: PLC0415
            get_or_create_purse,
            transfer,
        )

        transfer(
            amount=gold_cost,
            reason=f"Technique training: {technique.name}",
            from_purse=get_or_create_purse(sheet),
            to_treasury=gold_treasury,
        )

    # 7-8. Delegate mint + announce to the shared commit seam.
    # AP is already spent above (step 6); learn_technique receives ap_cost=0.
    # The gift-owned check in learn_technique passes because step 4 acquired
    # the gift if needed. The gate/cap/duplicate checks re-run idempotently.
    return learn_technique(
        sheet,
        technique,
        source=source,
        ap_cost=0,
        location=sheet.character.location,
    )


def accept_technique_offer(
    learner: CharacterSheet,
    offer: TechniqueTeachingOffer,
) -> CharacterTechnique:
    """Accept a TechniqueTeachingOffer — the acquisition step (#1587).

    If the learner doesn't yet have the technique's gift, this implicitly
    acquires it (via grant_gift_to_character). The first technique from
    a not-yet-acquired gift costs more AP (config.first_technique_ap_multiplier)
    and requires a CharacterGiftUnlock receipt (the XP gate).

    Delegates the charge+acquire core to ``charge_and_learn`` — the same
    seam the Academy TRAIN offer handler uses (#2440).

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

    return charge_and_learn(
        learner,
        offer.technique,
        base_ap_cost=offer.learn_ap_cost,
        source=AccessChangeSource.GIFT_ACQUISITION,
        teacher_tenure=offer.teacher,
        teacher_banked_ap=offer.banked_ap,
    )
