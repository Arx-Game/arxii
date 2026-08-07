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
from world.progression.services.awards import get_or_create_xp_tracker
from world.progression.types import ProgressionReason

if TYPE_CHECKING:
    from world.achievements.constants import AccessChangeSource
    from world.character_sheets.models import CharacterSheet
    from world.currency.models import OrganizationTreasury
    from world.magic.models import (
        Gift,
        GiftUnlock,
        Technique,
        TechniqueProgress,
        TechniqueTeachingOffer,
    )
    from world.roster.models import RosterTenure


def get_gift_acquisition_config() -> GiftAcquisitionConfig:
    """Lazily create and return the singleton GiftAcquisitionConfig (pk=1)."""
    config = GiftAcquisitionConfig.objects.cached_singleton()
    if config is None:
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


def resolve_owned_gift(sheet: CharacterSheet, gift: Gift) -> Gift | None:
    """The gift the character actually holds that reaches ``gift``'s techniques (#2891).

    ``gift`` itself when it is directly held; otherwise the held descendant gift
    whose lineage contains ``gift`` — a Vulpi holder reaching a Khati technique.
    ``None`` when the character reaches ``gift`` by no route.

    This is the single answer to both "does the learner own this?" and "which
    gift's thread and cap govern this technique?". The two questions have the
    same answer and must not drift apart: the whole point of ``Gift.parent`` is
    that a subspecies character carries ONE ``CharacterGift`` and ONE GIFT
    thread, so the held gift is what caps and thread depth are read from.
    """
    from world.magic.models import CharacterGift  # noqa: PLC0415

    held = [cg.gift for cg in CharacterGift.objects.filter(character=sheet).select_related("gift")]
    # A direct hold wins over reaching it through a descendant.
    for candidate in held:
        if candidate.pk == gift.pk:
            return candidate
    return next((candidate for candidate in held if gift.pk in candidate.lineage_ids), None)


def count_techniques_for_gift(sheet: CharacterSheet, gift: Gift) -> int:
    """Count CharacterTechnique + in-progress TechniqueProgress rows for ``gift``.

    Counts every technique drawing on ``gift``'s thread — its own and its
    ancestors' (#2891). One thread means one cap: an inherited Khati technique
    is not a second budget alongside the Vulpi ones. Callers pass the *held*
    gift (see ``resolve_owned_gift``), so the lineage walked here is the held
    gift's.

    Variants (TechniqueVariant) are derived on read (ADR-0055) — they are
    never stored as CharacterTechnique rows, so all CharacterTechnique rows
    for this gift are base techniques that count against the cap.

    In-progress TechniqueProgress meters also count against the cap (#2711) —
    a character training toward a technique has committed a slot even though
    the CharacterTechnique row doesn't exist yet.
    """
    from world.magic.models import (  # noqa: PLC0415
        CharacterTechnique,
        TechniqueProgress,
    )

    lineage_ids = gift.lineage_ids
    learned = CharacterTechnique.objects.filter(
        character=sheet,
        technique__gift_id__in=lineage_ids,
    ).count()
    in_progress = TechniqueProgress.objects.filter(
        character_sheet=sheet,
        technique__gift_id__in=lineage_ids,
    ).count()
    return learned + in_progress


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
def charge_and_learn(  # noqa: PLR0913 - shared core for two front doors; params co-equal
    learner: CharacterSheet,
    technique: Technique,
    *,
    base_ap_cost: int,
    source: AccessChangeSource,
    gold_cost: int = 0,
    gold_treasury: OrganizationTreasury | None = None,
    teacher_tenure: RosterTenure | None = None,
    teacher_banked_ap: int = 0,
) -> TechniqueProgress:
    """Shared charge+acquire core for technique acquisition (#1587, #2440, #2711).

    One seam, two front doors: ``accept_technique_offer`` (player-to-player
    teaching) and the Academy TRAIN offer handler
    (``world.npc_services.effects.run_train_offer``) both delegate here.

    Creates a ``TechniqueProgress`` meter instead of minting immediately
    (#2711). The learner fills the meter in subsequent sessions via
    ``contribute_to_technique_progress``. The teacher's banked AP and any
    gold/Hare are consumed at meter creation (commitment).

    If the learner doesn't yet have the technique's gift, this implicitly
    acquires it (via grant_gift_to_character). The first technique from
    a not-yet-acquired gift costs more AP (config.first_technique_ap_multiplier)
    and requires a CharacterGiftUnlock receipt (the XP gate).

    "Have the gift" means reaching it through ``resolve_owned_gift`` (#2891): a
    character holding a child gift already reaches its ancestors' techniques, so
    an inherited technique needs no receipt and mints no second gift or thread.

    The Unbound magic-learning AP surcharge (#2442) is applied per-session
    by ``contribute_to_technique_progress``, not to the meter total.

    Cross-path friction (#2711): when the teacher's ``Path.style`` differs
    from the learner's, ``total_required`` is multiplied by
    ``config.cross_path_cost_multiplier``. Null style on either side =
    no surcharge (fail-open).

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
        The new TechniqueProgress meter. The learner trains via
        ``contribute_to_technique_progress`` in subsequent sessions.

    Raises:
        GiftUnlockMissing: First technique from a gift with no receipt.
        TechniqueCapExceeded: At the cap for this gift at current thread level.
        ValueError: Learner already knows this technique.
    """
    from world.action_points.models import ActionPointPool  # noqa: PLC0415
    from world.magic.exceptions import (  # noqa: PLC0415
        GiftUnlockMissing,
        TechniqueCapExceeded,
    )
    from world.magic.models import (  # noqa: PLC0415
        CharacterTechnique,
        TechniqueProgress,
    )
    from world.magic.services.technique_progress import (  # noqa: PLC0415
        is_cross_path_learning,
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

    # 2. Check if learner reaches the gift — directly, or through a held
    # descendant gift whose lineage contains it (#2891). Without the lineage
    # walk a Vulpi holder learning a shared Khati technique would read as
    # not-having-the-gift here, and step 4 would mint a SECOND CharacterGift
    # and a second GIFT thread — the exact double AP+XP cost Gift.parent
    # exists to remove.
    owned_gift = resolve_owned_gift(sheet, gift)
    has_gift = owned_gift is not None
    # Caps and thread depth are read from the gift the character actually
    # holds, since that is where their one GIFT thread hangs.
    cap_gift = owned_gift if owned_gift is not None else gift

    # 3. Compute total_required from base_ap_cost × existing multipliers.
    config = get_gift_acquisition_config()
    if not has_gift:
        # Check the XP gate (CharacterGiftUnlock receipt).
        if not CharacterGiftUnlock.objects.filter(character=sheet, unlock__gift=gift).exists():
            raise GiftUnlockMissing
        total_required = base_ap_cost * config.first_technique_ap_multiplier
    elif gift.kind == GiftKind.MAJOR:
        total_required = base_ap_cost * config.major_gift_ap_multiplier
    else:
        total_required = base_ap_cost

    # 3b. Cross-path multiplier (#2711).
    cross_path = is_cross_path_learning(teacher_tenure, sheet)
    if cross_path:
        total_required = int(total_required * config.cross_path_cost_multiplier)

    # 4. Implicit gift acquisition (first technique).
    if not has_gift:
        grant_gift_to_character(sheet, gift)

    # 5. Check technique cap (after acquisition so the thread exists for depth).
    current_count = count_techniques_for_gift(sheet, cap_gift)
    cap = get_technique_cap_for_gift(sheet, cap_gift)
    if current_count >= cap:
        raise TechniqueCapExceeded

    # 6. Consume teacher's banked AP (teaching path only). Learner AP is
    # no longer spent here — it's spent per-session via
    # contribute_to_technique_progress (#2711).
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

    # 7. Create the progress meter. The learner trains in subsequent
    # sessions via contribute_to_technique_progress (#2711).
    return TechniqueProgress.objects.create(
        character_sheet=sheet,
        technique=technique,
        total_required=total_required,
        teacher_tenure=teacher_tenure,
        source=source,
        is_cross_path=cross_path,
    )


def accept_technique_offer(
    learner: CharacterSheet,
    offer: TechniqueTeachingOffer,
) -> TechniqueProgress:
    """Accept a TechniqueTeachingOffer — creates a training meter (#1587, #2711).

    Creates a ``TechniqueProgress`` meter instead of minting immediately
    (#2711). The learner fills the meter in subsequent sessions via
    ``contribute_to_technique_progress``.

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
        The new TechniqueProgress meter.

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
