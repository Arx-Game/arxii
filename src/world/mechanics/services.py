"""
Mechanics Service Functions

Service layer for modifier aggregation, calculation, and management.
"""

from __future__ import annotations

from collections.abc import Iterable
from contextlib import contextmanager
import contextvars
from decimal import Decimal
from typing import TYPE_CHECKING

from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from django.db.models import Prefetch, Q

from typeclasses.characters import Character
from world.checks.services import chart_has_success_outcomes, preview_check_difficulty
from world.conditions.services import get_all_capability_values
from world.distinctions.models import CharacterDistinction
from world.magic.constants import EffectKind, TargetKind
from world.magic.models import (
    Motif,
    MotifResonance,
    Resonance,
    StylePresentationEndorsement,
    TechniqueCapabilityGrant,
    ThreadPullEffect,
)
from world.mechanics.constants import (
    EQUIPMENT_RELEVANT_CATEGORIES,
    POWER_CATEGORY_NAME,
    POWER_MULTIPLIER_TARGET_NAME,
    RESONANCE_CATEGORY_NAME,
    SOURCE_TYPE_DISTINCTION,
    SOURCE_TYPE_UNKNOWN,
    CapabilitySourceType,
    DifficultyIndicator,
)
from world.mechanics.models import (
    AestheticAxisConfig,
    Application,
    ChallengeApproach,
    ChallengeInstance,
    ChallengeTemplate,
    CharacterModifier,
    ModifierSource,
    ModifierTarget,
    ObjectProperty,
    Prerequisite,
    Property,
    PropertyDamageModifier,
    TraitCapabilityDerivation,
)
from world.mechanics.types import (
    AvailableAction,
    CapabilitySource,
    ModifierBreakdown,
    ModifierSourceDetail,
    PrerequisiteEvaluation,
)
from world.traits.models import CharacterTraitValue

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.checks.models import CheckType
    from world.conditions.models import DamageType
    from world.covenants.models import CovenantRole
    from world.items.models import ItemInstance
    from world.mechanics.engagement import CharacterEngagement


# ---------------------------------------------------------------------------
# Coherence memoization (#1267)
# ---------------------------------------------------------------------------

_coherence_cache: contextvars.ContextVar[dict[tuple[int, int], int] | None] = (
    contextvars.ContextVar("motif_coherence_cache", default=None)
)


@contextmanager
def coherence_cache_scope():
    """Context manager that memoizes ``motif_coherence_bonus`` per (sheet, resonance).

    Within this scope, ``motif_coherence_bonus`` results are cached by
    ``(sheet.pk, resonance_id)`` so that repeated calls for the same
    character+resonance — e.g. across ``survivability_baseline`` calls for DR +
    wound/death/knockout saves in one damage event — pay the wardrobe walk
    exactly once. The cache dies with the context manager: no invalidation
    needed, no stale-read risk across events.
    """
    token = _coherence_cache.set({})
    try:
        yield
    finally:
        _coherence_cache.reset(token)


def get_aesthetic_config() -> AestheticAxisConfig:
    """Lazy-create and return the singleton aesthetic-axis config (pk=1)."""
    config = AestheticAxisConfig.objects.cached_singleton()
    if config is None:
        config, _ = AestheticAxisConfig.objects.get_or_create(pk=1)
    return config


def _flat_source_contributions(
    other_mods: list, has_immunity: bool
) -> tuple[list[ModifierSourceDetail], int, int]:
    """Non-distinction modifiers as flat addends; immunity still blocks their negatives.

    Returns ``(source_details, total_delta, blocked_count)``. These sources are outside the
    distinction amplification graph — they neither amplify nor get amplified.
    """
    sources: list[ModifierSourceDetail] = []
    total = 0
    blocked_count = 0
    for mod in other_mods:
        base_value = mod.value
        blocked = has_immunity and base_value < 0
        if blocked:
            blocked_count += 1
        else:
            total += base_value
        sources.append(
            ModifierSourceDetail(
                source_name=mod.source.source_display,
                base_value=base_value,
                amplification=0,
                final_value=0 if blocked else base_value,
                is_amplifier=False,
                blocked_by_immunity=blocked,
            )
        )
    return sources, total, blocked_count


def get_modifier_breakdown(character, modifier_target: ModifierTarget) -> ModifierBreakdown:
    """
    Get detailed breakdown of all modifiers for a target.

    Applies amplification and immunity rules:
    - Amplifying sources add their bonus to all OTHER sources
    - Immunity blocks all negative modifiers

    Args:
        character: CharacterSheet instance
        modifier_target: The ModifierTarget to aggregate

    Returns:
        ModifierBreakdown with sources, calculations, and total
    """
    # Get all modifiers for this character and target. Materialize once: the rows are
    # iterated twice below, so a bare ``.exists()`` pre-check would add a needless query.
    modifiers = list(
        CharacterModifier.objects.filter(
            character=character,
            target=modifier_target,
        ).select_related("source__distinction_effect__distinction")
    )

    # Distinction-sourced rows carry the amplify/immunity semantics (they dereference
    # ``distinction_effect``); *recognized* non-distinction sources — residence comfort,
    # achievement rewards, future equipment — contribute a flat value. Rows that are neither
    # (an UNKNOWN source: an orphaned distinction whose effect was SET_NULL, or a bare marker-less
    # source) still contribute nothing, preserving #909 — they're in neither list.
    distinction_mods = [mod for mod in modifiers if mod.source.distinction_effect is not None]
    other_mods = [
        mod
        for mod in modifiers
        if mod.source.source_type not in (SOURCE_TYPE_DISTINCTION, SOURCE_TYPE_UNKNOWN)
    ]

    if not distinction_mods and not other_mods:
        return ModifierBreakdown(
            modifier_target_name=modifier_target.name,
            sources=[],
            total=0,
            has_immunity=False,
            negatives_blocked=0,
        )

    # Collect amplifiers and check for immunity (distinction sources only).
    amplifiers: list[tuple[int, int]] = []  # (modifier_id, amplify_bonus)
    has_immunity = False

    for mod in distinction_mods:
        effect = mod.source.distinction_effect
        if effect.amplifies_sources_by:
            amplifiers.append((mod.id, effect.amplifies_sources_by))
        if effect.grants_immunity_to_negative:
            has_immunity = True

    # Calculate each source's contribution
    sources: list[ModifierSourceDetail] = []
    total = 0
    negatives_blocked = 0

    for mod in distinction_mods:
        effect = mod.source.distinction_effect
        base_value = mod.value
        is_amplifier = bool(effect.amplifies_sources_by)

        # Calculate amplification from OTHER sources
        amplification = 0
        for amp_id, amp_bonus in amplifiers:
            if amp_id != mod.id:
                amplification += amp_bonus

        final_value = base_value + amplification

        # Check if blocked by immunity
        blocked = has_immunity and final_value < 0

        if blocked:
            negatives_blocked += 1
        else:
            total += final_value

        sources.append(
            ModifierSourceDetail(
                source_name=effect.distinction.name,
                base_value=base_value,
                amplification=amplification,
                final_value=final_value,
                is_amplifier=is_amplifier,
                blocked_by_immunity=blocked,
            )
        )

    # Non-distinction sources are flat addends (outside the amplification graph).
    flat_sources, flat_total, flat_blocked = _flat_source_contributions(other_mods, has_immunity)
    sources.extend(flat_sources)
    total += flat_total
    negatives_blocked += flat_blocked

    return ModifierBreakdown(
        modifier_target_name=modifier_target.name,
        sources=sources,
        total=total,
        has_immunity=has_immunity,
        negatives_blocked=negatives_blocked,
    )


def _crafted_modifier_total(character: object, modifier_target: ModifierTarget) -> int:
    """Sum per-instance crafted item modifiers for equipped items (#1567).

    ``character`` is a CharacterSheet; ``character.character`` is the ObjectDB
    Character whose ``equipped_items`` handler caches the crafted recipe rows.
    Returns 0 when the character has no typeclass handler (raw ObjectDB fixtures).
    """
    char = character.character
    if char is None:
        return 0
    try:
        return char.equipped_items.crafted_modifier_total(modifier_target)
    except AttributeError:
        return 0


def get_modifier_total(
    character,
    modifier_target: ModifierTarget,
    *,
    perceiving_society: object | None = None,
    level_override: int | None = None,
) -> int:
    """Get total modifier value for a target.

    Combines the eager modifier total (CharacterModifier rows, distinctions, etc.) with the
    equipment walk (Spec D §5.5) for equipment-relevant categories. The equipment walk adds
    passive_facet_bonuses and covenant_role_bonus when the target's category is in
    EQUIPMENT_RELEVANT_CATEGORIES (stat, magic, affinity, resonance).

    When ``perceiving_society`` is provided, the perception-relative fashion outfit bonus
    (#513) for that society is also added. The fashion bonus reflects how well the
    character's worn items align with the society's current FashionStyle. When omitted
    (the default), fashion contributes nothing and behavior is identical to before —
    all existing society-blind callers are 100% unaffected.

    When ``level_override`` is provided, the covenant-role bonus uses that level instead
    of ``character.current_level``. Only the combat path supplies this (bond-adjusted
    level for mentor/sidekick pairs, #1165). All non-combat callers omit it → unchanged.

    Args:
        character: CharacterSheet instance
        modifier_target: The ModifierTarget to aggregate
        perceiving_society: Optional Society instance. When supplied, the outfit-vs-fashion
            bonus for that society is included in the total. Defaults to None (no fashion
            contribution).
        level_override: Optional integer. When supplied, overrides sheet.current_level for
            the covenant-role bonus calculation. Defaults to None (use current_level).

    Returns:
        Total modifier value (eager + equipment + optional fashion contributions,
        amplification/immunity applied to the eager portion)
    """
    eager_total = get_modifier_breakdown(character, modifier_target).total
    equipment_total = equipment_walk_total(
        character, modifier_target, level_override=level_override
    )
    crafted_total = _crafted_modifier_total(character, modifier_target)
    fashion_total = 0
    if perceiving_society is not None:
        fashion_total = fashion_outfit_bonus(character, modifier_target, perceiving_society)
    return eager_total + equipment_total + crafted_total + fashion_total


def power_flat_bonus_for_resonance(sheet: object, resonance_id: int) -> int:
    """Sum POWER-category flat modifiers (distinctions) applicable to ``resonance_id``.

    A distinction expresses "potency" for a resonance by authoring a ``DistinctionEffect`` on
    a POWER-category ``ModifierTarget`` gated by ``target_resonance`` — the same seam a
    technique cast reads via ``_partition_power_targets``/``_derive_power``'s FLAT stage
    (``magic/services/techniques.py``). This helper lets a standalone thread-pull fold those
    modifiers into its own magnitude (#1834 Task 7). Mirrors cast semantics exactly: a target
    matches when ``target_resonance_id`` is null (unscoped — applies to every resonance) OR
    equals ``resonance_id`` (scoped to this resonance specifically); a target scoped to a
    *different* resonance never matches. The unscoped ``power_multiplier`` target is excluded —
    its percent-delta semantics don't apply to a flat pull bonus. "power" is not an
    equipment-relevant category, so ``get_modifier_total`` here is always just the eager
    CharacterModifier total.

    Not full parity with a cast: this only sums the distinction-authored ``CharacterModifier``
    side. ``_derive_power``'s FLAT stage also sums condition-sourced POWER contributions
    (``get_condition_modifier_breakdown``), which a standalone pull never sees.

    Args:
        sheet: CharacterSheet instance.
        resonance_id: PK of the Resonance the pull is keyed to.

    Returns:
        Integer total (0 if no matching POWER-category target or no modifier).
    """
    targets = (
        ModifierTarget.objects.filter(category__name=POWER_CATEGORY_NAME)
        .filter(Q(target_resonance_id=resonance_id) | Q(target_resonance_id__isnull=True))
        .exclude(name=POWER_MULTIPLIER_TARGET_NAME)
    )
    return sum(get_modifier_total(sheet, target) for target in targets)


def equipment_walk_total(
    character: object, target: ModifierTarget, level_override: int | None = None
) -> int:
    """Sum facet + covenant-role + covenant-level + mantle passive bonuses (Spec D §5.5).

    Returns 0 unless target.category is equipment-relevant. The eager CharacterModifier
    total is NOT included here — callers add that separately (avoids double counting).

    When ``level_override`` is provided, the covenant-role bonus uses that level instead
    of ``character.current_level``. Only the combat path supplies this (bond-adjusted
    level for mentor/sidekick pairs, #1165). All other components are unaffected.
    """
    if target.category.name not in EQUIPMENT_RELEVANT_CATEGORIES:
        return 0
    return (
        passive_facet_bonuses(character, target)
        + passive_facet_crossing_bonuses(character, target)
        + covenant_role_bonus(character, target, level_override=level_override)
        + covenant_level_bonus(character, target)
        + vow_stat_scaling_bonus(character, target)
        + vow_gear_scaling_bonus(character, target)
        + passive_mantle_bonuses(character, target)
        + passive_mantle_crossing_bonuses(character, target)
        + passive_motif_style_bonuses(character, target)
    )


# =============================================================================
# Passive Facet Bonuses (Spec D §5.2)
# =============================================================================


def passive_facet_bonuses(sheet: object, target: ModifierTarget) -> int:
    """Sum tier-0 FLAT_BONUS contributions from equipped item facets (Spec D §5.2).

    For each FACET-kind thread the character owns, look up equipped items that
    carry the thread's anchor facet. For each matching (item, item_facet) pair,
    compute the contribution from every tier-0 FLAT_BONUS ThreadPullEffect that
    maps this thread's resonance to ``target`` via the ModifierTarget.target_resonance
    OneToOne. Sum all contributions and return the integer total.

    This composes with the existing ``passive_vital_bonuses`` pattern — same shape,
    keyed by ModifierTarget instead of vital_target. See CharacterThreadHandler in
    world/magic/handlers.py for the parallel.

    Args:
        sheet: CharacterSheet instance (the character whose threads and items are used).
        target: The ModifierTarget to aggregate bonuses for.

    Returns:
        Integer total of all passive facet contributions for ``target``.
    """
    char = sheet.character
    # Defensive: raw ObjectDB fixtures (without _typeclass_path) don't have
    # Character typeclass handlers. Skip the walk gracefully.
    if not isinstance(char, Character):  # threads/equipped_items are Character-only
        return 0
    total = 0
    for thread in char.threads.threads_of_kind(TargetKind.FACET):
        matching = char.equipped_items.item_facets_for(thread.target_facet)
        if not matching:
            continue
        effects = _thread_pull_effects_for(
            thread.resonance, target, target_kind=TargetKind.FACET, tier=0
        )
        for effect in effects:
            for item_facet in matching:
                total += _facet_effect_contribution(
                    effect=effect,
                    thread=thread,
                    item=item_facet.item_instance,
                    item_facet=item_facet,
                )
    return total


def passive_facet_crossing_bonuses(sheet: object, target: ModifierTarget) -> int:
    """Sum ConditionModifierEffect from FACET thread crossing choices (wear-gated).

    For each FACET-kind thread with crossing choices, checks if the character
    is wearing an item with the anchor facet. If so, reads the choice's
    option.condition_template's ConditionModifierEffect rows for ``target``
    and sums them.

    Composes with ``passive_facet_bonuses`` in ``equipment_walk_total`` —
    the crossing buff is a personal layer on top of the global tier-0 passive.
    """
    from world.conditions.models import ConditionModifierEffect  # noqa: PLC0415
    from world.magic.constants import TargetKind  # noqa: PLC0415
    from world.magic.models.crossing import CrossingChoice  # noqa: PLC0415

    char = sheet.character
    if not isinstance(char, Character):  # threads/equipped_items are Character-only
        return 0
    total = 0
    for thread in char.threads.threads_of_kind(TargetKind.FACET):
        matching = char.equipped_items.item_facets_for(thread.target_facet)
        if not matching:
            continue
        choices = CrossingChoice.objects.filter(thread=thread).select_related(
            "option__condition_template"
        )
        for choice in choices:
            template = choice.option.condition_template
            effects = ConditionModifierEffect.objects.filter(
                condition=template,
                modifier_target=target,
            )
            for effect in effects:
                total += effect.value
    return total


def passive_mantle_bonuses(sheet: object, target: ModifierTarget) -> int:
    """Sum tier-0 FLAT_BONUS contributions from attuned mantle threads (Spec D §5.2).

    The MANTLE analogue of ``passive_facet_bonuses``. For each MANTLE-kind thread
    the character owns, look up every tier-0 FLAT_BONUS ThreadPullEffect that maps
    the thread's resonance to ``target`` via the ModifierTarget.target_resonance
    OneToOne, then sum the contributions.

    Unlike facets, a mantle thread has no ItemFacet / equipped item to join — the
    bonus comes from the thread itself. The contribution is therefore
    ``flat_bonus_amount × max(1, thread.level)`` with NO item-quality or
    attachment-quality multipliers.

    Args:
        sheet: CharacterSheet instance (the character whose threads are walked).
        target: The ModifierTarget to aggregate bonuses for.

    Returns:
        Integer total of all passive mantle contributions for ``target``.
    """
    char = sheet.character
    # Defensive: raw ObjectDB fixtures (without _typeclass_path) don't have
    # Character typeclass handlers. Skip the walk gracefully.
    if not isinstance(char, Character):  # threads/equipped_items are Character-only
        return 0
    total = 0
    for thread in char.threads.threads_of_kind(TargetKind.MANTLE):
        effects = _thread_pull_effects_for(
            thread.resonance, target, target_kind=TargetKind.MANTLE, tier=0
        )
        for effect in effects:
            base = effect.flat_bonus_amount or 0
            total += base * max(1, thread.level)
    return total


def passive_mantle_crossing_bonuses(sheet: object, target: ModifierTarget) -> int:
    """Sum ConditionModifierEffect from MANTLE thread crossing choices (always-on).

    For each MANTLE-kind thread with crossing choices, reads the choice's
    option.condition_template's ConditionModifierEffect rows for ``target``
    and sums them. Always-on -- the thread IS the attunement bond, so the
    crossing buff is active regardless of whether the mantle item is equipped.

    Composes with ``passive_mantle_bonuses`` in ``equipment_walk_total`` --
    the crossing buff is a personal layer on top of the global tier-0 passive.
    """
    from world.conditions.models import ConditionModifierEffect  # noqa: PLC0415
    from world.magic.constants import TargetKind  # noqa: PLC0415
    from world.magic.models.crossing import CrossingChoice  # noqa: PLC0415

    char = sheet.character
    if not isinstance(char, Character):  # threads/equipped_items are Character-only
        return 0
    total = 0
    for thread in char.threads.threads_of_kind(TargetKind.MANTLE):
        choices = CrossingChoice.objects.filter(thread=thread).select_related(
            "option__condition_template"
        )
        for choice in choices:
            template = choice.option.condition_template
            effects = ConditionModifierEffect.objects.filter(
                condition=template,
                modifier_target=target,
            )
            for effect in effects:
                total += effect.value
    return total


def motif_coherence_bonus(sheet: object, resonance_id: int) -> int:
    """Per-resonance fashion-coherence bonus from worn styles bound to the character's Motif.

    Computes coverage × quality × full-combo × perception-breadth for ``resonance_id``.
    Decoupled from ``ModifierTarget`` so it can be called by the survivability amplifier
    (and any other caller) with a bare resonance pk.

    **Composition rule — style × facet coexistence:** An item that carries both an
    ``ItemStyle`` and an ``ItemFacet`` contributes to this walker (style coherence)
    AND to ``passive_facet_bonuses`` (facet resonance) simultaneously. The two walkers
    are independent; their results are summed by ``equipment_walk_total``.

    **Dilution-only rule — unbound styles are inert:** The walker iterates only the
    character's ``MotifResonanceStyle`` bindings for ``resonance_id``. A worn
    ``ItemStyle`` that does not appear in those bindings is completely invisible to this
    walker — it neither increases coverage nor applies any penalty. Characters may freely
    wear items tagged with unrelated styles without degrading their coherence bonus.

    Args:
        sheet: CharacterSheet instance.
        resonance_id: PK of the Resonance to compute coherence for.

    Returns:
        Integer bonus (truncated), or 0 if no binding or no matching worn styles.
    """
    cache = _coherence_cache.get()
    if cache is not None:
        key = (sheet.pk, resonance_id)
        if key in cache:
            return cache[key]
    result = _compute_motif_coherence_bonus(sheet, resonance_id)
    if cache is not None:
        cache[(sheet.pk, resonance_id)] = result
    return result


def _compute_motif_coherence_bonus(sheet: object, resonance_id: int) -> int:
    """Compute the per-resonance coherence bonus without caching (see ``motif_coherence_bonus``).

    Computes coverage × quality × full-combo × perception-breadth for ``resonance_id``.
    Returns 0 if no binding or no matching worn styles.
    """
    from world.items.services.styles import audacity_multiplier_for  # noqa: PLC0415

    char = sheet.character
    # Defensive: raw ObjectDB fixtures (without _typeclass_path) don't have
    # Character typeclass handlers. Skip the walk gracefully.
    if not hasattr(char, "equipped_items"):
        return 0
    try:
        motif = sheet.motif  # CharacterSheet OneToOne, related_name "motif"
    except Motif.DoesNotExist:
        # Reverse OneToOne raises DoesNotExist, NOT AttributeError — getattr default won't catch it.
        return 0
    try:
        mr = motif.resonances.get(resonance_id=resonance_id)
    except MotifResonance.DoesNotExist:
        return 0
    bound = list(mr.style_assignments.all())
    config = get_aesthetic_config()
    covered = 0
    quality_aggregate = Decimal(0)
    for binding in bound:
        worn = char.equipped_items.item_styles_for(binding.style)
        if worn:
            covered += 1
            # Daring styles are mechanically, not just narratively, rewarded (#2029):
            # each matched binding's quality contribution is scaled by its style's
            # audacity multiplier before being aggregated.
            quality_aggregate += worn_quality_aggregate(worn) * audacity_multiplier_for(
                binding.style
            )
    if not bound or covered == 0:
        return 0
    coverage = Decimal(covered) / Decimal(len(bound))
    bonus = Decimal(config.base_magnitude) * coverage * quality_aggregate
    if covered == len(bound):
        bonus *= Decimal(str(config.full_combination_bonus))
    # Perception-breadth amplification: distinct STYLE_PRESENTATION endorsers for this
    # resonance scale the bonus from factor=1 (0 endorsers) to factor=perception_multiplier
    # (n >= perception_breadth_cap). Computed in a single aggregate query — no N+1.
    cap = config.perception_breadth_cap
    if cap > 0:
        n = (
            StylePresentationEndorsement.objects.filter(
                endorsee_sheet=sheet,
                resonance_id=resonance_id,
            )
            .values("endorser_sheet")
            .distinct()
            .count()
        )
        factor = Decimal(1) + (Decimal(str(config.perception_multiplier)) - Decimal(1)) * (
            Decimal(min(n, cap)) / Decimal(cap)
        )
        bonus *= factor
    return int(bonus)


def passive_motif_style_bonuses(sheet: object, target: ModifierTarget) -> int:
    """Coherence bonus for ``target``'s resonance (Spec D §5.3). Thin wrapper over
    ``motif_coherence_bonus`` — see it for the dilution-only and style×facet rules.

    Args:
        sheet: CharacterSheet instance.
        target: The ModifierTarget to aggregate the style coherence bonus for.

    Returns:
        Integer bonus (truncated), or 0 if no binding or no matching worn styles.
    """
    if target.target_resonance_id is None:
        return 0
    return motif_coherence_bonus(sheet, target.target_resonance_id)


def _thread_pull_effects_for(
    resonance: object,
    target: ModifierTarget,
    *,
    target_kind: str,
    tier: int,
) -> list[ThreadPullEffect]:
    """Return tier FLAT_BONUS pull effects for an anchor kind, gated by resonance→target link.

    Gate: a ModifierTarget contributes only when its ``target_resonance`` OneToOne
    points to ``resonance``. Targets in the stat/magic/affinity categories lack this
    link and return [] — other linking mechanisms may be added later. Shared by the
    FACET and MANTLE passive walks (``target_kind`` selects which).

    Args:
        resonance: The Resonance instance from the thread.
        target: The ModifierTarget being aggregated.
        target_kind: The TargetKind to filter on (FACET or MANTLE).
        tier: Effect tier to filter on (0 = passive always-on).

    Returns:
        List of ThreadPullEffect rows (may be empty).
    """
    # ModifierTarget owns the FK; .target_resonance_id is the FK column, so
    # this is a direct PK compare with no extra query.
    if target.target_resonance_id is None or target.target_resonance_id != resonance.pk:
        return []
    return list(
        ThreadPullEffect.objects.filter(
            target_kind=target_kind,
            resonance=resonance,
            tier=tier,
            effect_kind=EffectKind.FLAT_BONUS,
            target_gift__isnull=True,  # FACET/MANTLE kinds only; exclude gift-specific rows
        ).exclude(flat_bonus_amount__isnull=True)
    )


def worn_quality_aggregate(rows: Iterable[object]) -> Decimal:
    """Sum (item_quality_multiplier × attachment_quality_multiplier) over worn rows.

    Works for any row type that exposes ``item_instance`` (with an optional
    ``quality_tier.stat_multiplier``) and ``attachment_quality_tier.stat_multiplier``
    — including ``ItemFacet`` and ``ItemStyle`` rows. Returns Decimal(0) for an
    empty iterable.

    Decimal(str(...)) coercion guards against float stat_multiplier values from
    factories or .values() queries; DecimalField normally returns Decimal, but
    this is belt-and-suspenders consistent with the surrounding arithmetic.
    """
    total = Decimal(0)
    for row in rows:
        item = row.item_instance
        item_mult = (
            Decimal(str(item.quality_tier.stat_multiplier))
            if item.quality_tier is not None
            else Decimal(1)
        )
        attach_mult = Decimal(str(row.attachment_quality_tier.stat_multiplier))
        total += item_mult * attach_mult
    return total


def fashion_outfit_bonus(sheet: object, target: ModifierTarget, society: object) -> int:
    """Perception-relative outfit bonus vs. a society's current fashion (#513).

    Worn items carrying facets that are in vogue for ``society.current_fashion_style``
    contribute, scaled by item + attachment quality and the authored
    FashionStyleBonus.weight for ``target``. Society-parameterized; consumers
    (events #514, combat #512) supply the perceiving society. Returns 0 when no
    current style, no FashionStyleBonus row for ``target``, or no worn matches.
    """
    from world.items.constants import FASHION_MATCH_BASE  # noqa: PLC0415
    from world.items.models import FashionStyleBonus  # noqa: PLC0415

    style = society.current_fashion_style
    if style is None:
        return 0
    try:
        bonus = style.bonuses.get(target=target)
    except FashionStyleBonus.DoesNotExist:
        return 0
    char = sheet.character
    if not hasattr(char, "equipped_items"):
        return 0
    match_value = Decimal(0)
    for facet in style.in_vogue_facets.all():
        match_value += Decimal(FASHION_MATCH_BASE) * worn_quality_aggregate(
            char.equipped_items.item_facets_for(facet)
        )
    for s in style.in_vogue_styles.all():
        match_value += Decimal(FASHION_MATCH_BASE) * worn_quality_aggregate(
            char.equipped_items.item_styles_for(s)
        )
    return int(match_value * Decimal(str(bonus.weight)))


def _facet_effect_contribution(
    *,
    effect: ThreadPullEffect,
    thread: object,
    item: object,
    item_facet: object,
) -> int:
    """Compute one (item, facet) contribution to a tier-0 FLAT_BONUS effect.

    Formula: base × item_quality_multiplier × attachment_quality_multiplier × max(1, level).

    Decimal(str(...)) coercion guards against float stat_multiplier values from
    factories or .values() queries; DecimalField normally returns Decimal, but
    this is belt-and-suspenders consistent with the resonance.py FACET branch.

    Args:
        effect: The ThreadPullEffect row (FLAT_BONUS, tier 0).
        thread: The Thread instance (supplies ``level``).
        item: The ItemInstance (supplies ``quality_tier.stat_multiplier``).
        item_facet: The ItemFacet (supplies ``attachment_quality_tier.stat_multiplier``).

    Returns:
        Integer contribution (truncated via int()).
    """
    base = effect.flat_bonus_amount or 0
    item_mult = (
        Decimal(str(item.quality_tier.stat_multiplier))
        if item.quality_tier is not None
        else Decimal(1)
    )
    # Non-nullable FK — always present
    attach_mult = Decimal(str(item_facet.attachment_quality_tier.stat_multiplier))
    level_mult = max(1, thread.level)
    return int(base * item_mult * attach_mult * level_mult)


# =============================================================================
# Covenant Role Bonus (Spec D §5.6)
# =============================================================================


def covenant_role_bonus(
    sheet: object, target: ModifierTarget, level_override: int | None = None
) -> int:
    """Sum covenant-role contributions across equipped items, gated on engagement.

    Per spec 2026-05-09 §3.6: role bonuses apply only when the character is
    "engaged" with the covenant where they hold the role. Multiple engaged
    roles (e.g., one Durance + one Battle) stack additively.

    Per slot (marginal blend — combat already counts the gear's base stat directly):
    - Compatible gear (GearArchetypeCompatibility row exists): role_bonus stacks on top.
    - Incompatible gear (no row): max(0, role_bonus - gear_stat) — only the role's
      surplus beyond what the gear already provides; never negative.

    At low character levels an incompatible item may fully suppress the role bonus;
    at high levels role_bonus dominates and the incompatibility cost shrinks.

    When ``level_override`` is provided, it replaces ``sheet.current_level`` for the
    role bonus calculation. Only the combat path supplies this (bond-adjusted level
    for mentor/sidekick pairs, #1165). All non-combat callers omit it → unchanged.

    Args:
        sheet: CharacterSheet instance.
        target: The ModifierTarget to aggregate bonuses for.
        level_override: Optional integer. When supplied, overrides sheet.current_level
            for the role bonus scaling. Defaults to None (use current_level).

    Returns:
        Integer total of all engaged-covenant-role contributions across equipped items.
    """
    from world.covenants.services import (  # noqa: PLC0415
        is_gear_compatible,
    )

    char = sheet.character
    # Defensive: raw ObjectDB fixtures (without _typeclass_path) don't have
    # Character typeclass handlers. Skip the walk gracefully.
    if not hasattr(char, "covenant_roles") or not hasattr(char, "equipped_items"):
        return 0
    engaged_roles = char.covenant_roles.currently_engaged_roles()
    if not engaged_roles:
        return 0

    character_level = level_override if level_override is not None else sheet.current_level
    total = 0
    for role in engaged_roles:
        role_bonus = role_base_bonus_for_target(role, target, character_level)
        for equipped in char.equipped_items:
            item = equipped.item_instance
            gear_stat = item_mundane_stat_for_target(item, target)
            archetype = item.template.gear_archetype
            if is_gear_compatible(role, archetype):
                total += (
                    role_bonus  # compatible: role bonus stacks on the gear combat already counts
                )
            else:
                total += max(
                    0, role_bonus - gear_stat
                )  # incompatible: only the role's surplus over gear
    return total


def covenant_role_base_total(sheet: object, target: ModifierTarget) -> int:
    """Raw engaged-covenant-role bonus for ``target`` — no per-gear marginal blend (#1174).

    Σ over engaged roles of ``current_level * bonus_per_level``. Unlike
    ``covenant_role_bonus`` (which subtracts the equipped gear stat per slot), this is
    the role's intrinsic resonant contribution, used by the armor-soak seam to pool all
    resonant soak before its compatible-additive / incompatible-max blend.
    """
    char = sheet.character
    if not hasattr(char, "covenant_roles"):
        return 0
    engaged_roles = char.covenant_roles.currently_engaged_roles()
    if not engaged_roles:
        return 0
    return sum(
        role_base_bonus_for_target(role, target, sheet.current_level) for role in engaged_roles
    )


def equipment_walk_total_unblended(sheet: object, target: ModifierTarget) -> int:
    """``equipment_walk_total`` with the covenant-role component as its raw base (#1174).

    Mirrors ``equipment_walk_total`` source-for-source EXCEPT it swaps the per-slot-blended
    ``covenant_role_bonus`` for ``covenant_role_base_total``. The armor-soak seam needs the
    un-blended resonant pool so it can run its own compatible-additive / incompatible-max
    blend over the whole pool. Keep the source list in sync with ``equipment_walk_total``.
    """
    if target.category.name not in EQUIPMENT_RELEVANT_CATEGORIES:
        return 0
    return (
        passive_facet_bonuses(sheet, target)
        + covenant_role_base_total(sheet, target)
        + covenant_level_bonus(sheet, target)
        + vow_stat_scaling_bonus(sheet, target)
        + vow_gear_scaling_bonus(sheet, target)
        + passive_mantle_bonuses(sheet, target)
        + passive_mantle_crossing_bonuses(sheet, target)
        + passive_motif_style_bonuses(sheet, target)
    )


def covenant_level_bonus(sheet: object, target: ModifierTarget) -> int:
    """Sum the authored covenant-level passive bonus across engaged memberships (#762).

    A ``CovenantLevelBonus`` row authored against ``target`` grants each engaged
    member a derive-on-read modifier of ``covenant.level * bonus_per_level``.
    Bonuses stack additively across the character's engaged covenants, mirroring
    ``covenant_role_bonus`` (spec 2026-05-09 §3.6). No CharacterModifier rows are
    persisted. Most targets have no row → returns 0.

    Args:
        sheet: CharacterSheet instance.
        target: The ModifierTarget to aggregate the level bonus for.

    Returns:
        Integer total of the engaged-covenant level bonus for ``target``.
    """
    char = sheet.character
    # Defensive: raw ObjectDB fixtures (without _typeclass_path) lack the
    # Character typeclass handlers. Skip gracefully.
    if not hasattr(char, "covenant_roles"):
        return 0
    # Engagement gate FIRST, via the (already-warm) cached handler — adds no
    # new query when the character isn't engaged, so get_modifier_total's query
    # budget stays flat for the common case. The authored-config lookup only
    # fires for engaged members. Mirrors covenant_role_bonus's early-out.
    if not char.covenant_roles.currently_engaged_roles():
        return 0

    from world.covenants.models import (  # noqa: PLC0415
        CharacterCovenantRole,
        CovenantLevelBonus,
    )

    config = CovenantLevelBonus.objects.filter(modifier_target=target).first()
    if config is None:
        return 0

    # Batched query — no per-membership round trips (no-queries-in-loops standard).
    memberships = CharacterCovenantRole.objects.filter(
        character_sheet=sheet,
        engaged=True,
        left_at__isnull=True,
    ).select_related("covenant")
    return sum(m.covenant.level * config.bonus_per_level for m in memberships)


def role_base_bonus_for_target(
    role: CovenantRole,
    target: ModifierTarget,
    character_level: int,
) -> int:
    """Authored covenant-role bonus for ``target``, scaled by character level (#985).

    Reads the ``CovenantRoleBonus`` row for ``(role, target)`` and returns
    ``character_level * bonus_per_level``. No row → 0 (most targets). Mirrors
    ``covenant_level_bonus``'s authored-config lookup; reached only after
    ``covenant_role_bonus``'s engaged-roles early-out.
    """
    from world.covenants.models import CovenantRoleBonus  # noqa: PLC0415

    config = CovenantRoleBonus.objects.filter(covenant_role=role, modifier_target=target).first()
    if config is None:
        return 0
    return character_level * config.bonus_per_level


def vow_stat_scaling_bonus(sheet: object, target: ModifierTarget) -> int:
    """Sum the vow-driven stat scaling across engaged roles (#2022).

    Unlike ``covenant_role_bonus`` (which scales by ``character_level``), this
    scales by the character's **COVENANT_ROLE thread level** — so a deepened
    vow is a substantially stronger character. For each engaged role, reads
    the ``VowStatScaling`` row for ``(role, target)`` and returns
    ``thread_level * bonus_per_level``. No row → 0 (most targets).

    Gated on engagement (the #2051 continuous enforcement ensures the engaged
    flag tracks co-presence). When the vow dims, the stat scaling drops — the
    character's stats collapse toward their base.
    """
    from world.covenants.models import (  # noqa: PLC0415
        VowStatScaling,
    )
    from world.covenants.services import _covenant_role_thread_level  # noqa: PLC0415

    char = sheet.character
    if not hasattr(char, "covenant_roles"):
        return 0
    engaged_roles = char.covenant_roles.currently_engaged_roles()
    if not engaged_roles:
        return 0

    configs = VowStatScaling.objects.filter(
        covenant_role__in=engaged_roles,
        modifier_target=target,
    )
    if not configs:
        return 0
    total = 0
    for config in configs:
        thread_level = _covenant_role_thread_level(sheet, config.covenant_role)
        total += thread_level * config.bonus_per_level
    return total


def vow_gear_scaling_bonus(
    sheet: object,  # noqa: ARG001
    target: ModifierTarget,  # noqa: ARG001
) -> int:
    """Vow-driven equipment amplification — inert pending Layer 3 (#2533).

    ``VowGearScaling`` has never been seeded, so this consumer has always
    returned 0 in real games; it also keyed on the removed
    ``CovenantRole.archetype``. #2529 short-circuits it to its actual runtime
    behavior; #2533 (per-vow defense styles + gear substitution) decides the
    model's real fate. Do not wire it back up without that design.
    """
    return 0


def item_mundane_stat_for_target(item: ItemInstance, target: ModifierTarget) -> int:
    """Mundane combat stat an equipped item contributes to ``target`` (#985, §5.6).

    Reads the per-instance derived combat stats shipped by #508 — quality-scaled
    and already 0 for the wrong archetype. weapon_damage / armor_soak targets only;
    every other target → 0. (No ItemCombatStat model exists — #508 put these
    directly on ItemTemplate/ItemInstance.)
    """
    from world.items.constants import (  # noqa: PLC0415
        ARMOR_SOAK_TARGET_NAME,
        WEAPON_DAMAGE_TARGET_NAME,
    )

    if target.name == WEAPON_DAMAGE_TARGET_NAME:
        return item.effective_weapon_damage
    if target.name == ARMOR_SOAK_TARGET_NAME:
        return item.effective_armor_soak
    return 0


def create_distinction_modifiers(
    character_distinction: CharacterDistinction,
) -> list[CharacterModifier]:
    """
    Create ModifierSource + CharacterModifier records for all effects of a distinction.

    Called when a CharacterDistinction is created.

    Resonance-CATEGORY effects are skipped here — distinction resonance now flows
    through ``reconcile_distinction_resonance_grants`` (the ``DistinctionResonanceGrant``
    sidecar), not a resonance-targeted ``CharacterModifier`` row (#1834). Every other
    effect still materializes a modifier as before.

    Args:
        character_distinction: The character's distinction instance

    Returns:
        List of created CharacterModifier records
    """
    from world.magic.services.distinction_resonance import (  # noqa: PLC0415
        reconcile_distinction_resonance_grants,
    )

    distinction = character_distinction.distinction
    rank = character_distinction.rank
    character = character_distinction.character.sheet_data

    created_modifiers = []

    for effect in distinction.effects.select_related("target__category").all():
        if effect.target.category.name == RESONANCE_CATEGORY_NAME:
            continue

        # Create the source linking effect template to character instance
        source = ModifierSource.objects.create(
            distinction_effect=effect,
            character_distinction=character_distinction,
        )

        # Calculate value at current rank
        value = effect.get_value_at_rank(rank)

        modifier = CharacterModifier.objects.create(
            character=character,
            target=effect.target,
            value=value,
            source=source,
        )
        created_modifiers.append(modifier)

    reconcile_distinction_resonance_grants(character_distinction)

    return created_modifiers


@transaction.atomic
def delete_distinction_modifiers(character_distinction: CharacterDistinction) -> int:
    """
    Delete all modifier records for a distinction.

    Called when a CharacterDistinction is removed.

    Args:
        character_distinction: The character's distinction instance

    Returns:
        Count of deleted CharacterModifier records
    """
    # Get modifiers BEFORE deleting (evaluate queryset once) so the caller gets an
    # accurate count. Aura no longer reads these rows — it derives from
    # CharacterResonance.lifetime_earned via magic.services.recompute_aura instead
    # (the CharacterModifier reader was removed in #1836); distinction resonance is
    # tracked separately via DistinctionResonanceGrant + reconcile (#1834).
    modifiers = list(
        CharacterModifier.objects.filter(
            source__character_distinction=character_distinction
        ).select_related("target__category", "source__distinction_effect")
    )

    # Delete sources (which cascades to modifiers)
    sources = ModifierSource.objects.filter(character_distinction=character_distinction)
    sources.delete()
    return len(modifiers)


@transaction.atomic
def update_distinction_rank(character_distinction: CharacterDistinction) -> None:
    """
    Update CharacterModifier values when rank changes.

    Recalculates value for each effect using the new rank. Also reconciles the
    distinction's resonance grants at the new rank (#1834) — resonance-CATEGORY
    effects never get a CharacterModifier row (skipped at create time), so this
    is the only path that tops off the rank-scaled resonance seed on a rank change.

    Args:
        character_distinction: The character's distinction instance (with updated rank)
    """
    from world.magic.services.distinction_resonance import (  # noqa: PLC0415
        reconcile_distinction_resonance_grants,
    )

    new_rank = character_distinction.rank

    # Get all modifiers for this distinction
    modifiers = CharacterModifier.objects.filter(
        source__character_distinction=character_distinction
    ).select_related("target__category", "source__distinction_effect")

    for modifier in modifiers:
        effect = modifier.source.distinction_effect
        new_value = effect.get_value_at_rank(new_rank)

        # Update the modifier — aura no longer reads these rows directly (see
        # delete_distinction_modifiers); no denormalized resonance-total adjustment
        # is required either way.
        modifier.value = new_value
        modifier.save()

    reconcile_distinction_resonance_grants(character_distinction)


# =============================================================================
# Capability Source Aggregation
# =============================================================================


def get_capability_sources_for_character(
    character: ObjectDB,
) -> list[CapabilitySource]:
    """Collect all Capability sources for a character (per-source, not aggregated)."""
    sources: list[CapabilitySource] = []
    sources.extend(_get_technique_sources(character))
    sources.extend(_get_trait_sources(character))
    sources.extend(_get_condition_sources(character))
    return sources


def _get_technique_sources(character: ObjectDB) -> list[CapabilitySource]:
    """Get Capability sources from character's known Techniques."""
    grants = (
        TechniqueCapabilityGrant.objects.filter(
            technique__character_grants__character__character=character,
        )
        .select_related(
            "technique",
            "technique__gift",
            "capability",
            "prerequisite",
            "prerequisite__property",
        )
        .prefetch_related(
            Prefetch(
                "technique__gift__resonances",
                queryset=Resonance.objects.prefetch_related(
                    Prefetch(
                        "properties",
                        queryset=Property.objects.all(),
                        to_attr="cached_properties",
                    ),
                ),
                to_attr="cached_resonances",
            ),
        )
    )

    sources: list[CapabilitySource] = []
    for grant in grants:
        value = grant.calculate_value()
        if value <= 0:
            continue

        # Effect property IDs come from the Gift's resonances' modifier_target links
        effect_property_ids = _get_technique_effect_property_ids(grant.technique)

        sources.append(
            CapabilitySource(
                capability_name=grant.capability.name,
                capability_id=grant.capability_id,
                value=value,
                source_type=CapabilitySourceType.TECHNIQUE,
                source_name=grant.technique.name,
                source_id=grant.technique_id,
                effect_property_ids=effect_property_ids,
                prerequisite=grant.prerequisite,
            )
        )

    return sources


def _get_technique_effect_property_ids(technique: object) -> list[int]:
    """
    Derive effect Property IDs from a Technique's Gift resonances.

    Each Resonance has a M2M to Property. Collects all Property IDs
    from the technique's gift's resonances via prefetched cached_properties.

    Expects technique.gift.cached_resonances[*].cached_properties to be
    pre-populated via the _get_technique_sources() prefetch chain.

    Intentionally reads the authored supported set (cached_resonances), NOT
    the per-character cast-time resonance. The cast-time value is resolved via
    gift_resonances_for(character, gift) at the cast sites (ADR-0052); this is
    the inventory/capability walk that enumerates what the technique *can* do,
    not what it *does* for a specific character.
    """
    if not hasattr(technique, "gift_id") or not technique.gift_id:
        return []

    property_ids: list[int] = []
    for resonance in technique.gift.cached_resonances:
        property_ids.extend(p.id for p in resonance.cached_properties)
    return property_ids


def _get_trait_sources(character: ObjectDB) -> list[CapabilitySource]:
    """Get Capability sources derived from character traits."""
    derivations = TraitCapabilityDerivation.objects.select_related("trait", "capability").all()

    if not derivations:
        return []

    trait_ids = [d.trait_id for d in derivations]
    trait_values = dict(
        CharacterTraitValue.objects.filter(
            character=character,
            trait_id__in=trait_ids,
        ).values_list("trait_id", "value")
    )

    sources: list[CapabilitySource] = []
    for derivation in derivations:
        tv = trait_values.get(derivation.trait_id)
        if not tv or tv <= 0:
            continue

        value = derivation.calculate_value(tv)
        if value <= 0:
            continue

        sources.append(
            CapabilitySource(
                capability_name=derivation.capability.name,
                capability_id=derivation.capability_id,
                value=value,
                source_type=CapabilitySourceType.TRAIT,
                source_name=derivation.trait.name,
                source_id=derivation.trait_id,
            )
        )

    return sources


def _get_condition_sources(character: ObjectDB) -> list[CapabilitySource]:
    """Get Capability sources from active conditions."""
    try:
        sheet = character.sheet_data
    except ObjectDoesNotExist:
        # No CharacterSheet → no capability mods from conditions can be derived;
        # capabilities are character-specific and conditions on a sheet-less
        # object don't materialize as CharacterModifier rows.
        return []
    cap_values = get_all_capability_values(sheet)

    sources: list[CapabilitySource] = []
    for cap_id, value in cap_values.items():
        if value <= 0:
            continue

        sources.append(
            CapabilitySource(
                capability_name="",  # Not needed for PK-based matching
                capability_id=cap_id,
                value=value,
                source_type=CapabilitySourceType.CONDITION,
                source_name="",  # Conditions aggregate; no single source name
                source_id=0,
            )
        )

    return sources


# =============================================================================
# Action Generation
# =============================================================================


def get_available_actions(
    character: ObjectDB,
    location: ObjectDB,
    capability_sources: list[CapabilitySource] | None = None,
) -> list[AvailableAction]:
    """Generate available Actions for a character at a location."""
    if capability_sources is None:
        capability_sources = get_capability_sources_for_character(character)

    if not capability_sources:
        return []

    # Build lookup: capability_id -> list of sources
    cap_id_to_sources: dict[int, list[CapabilitySource]] = {}
    for src in capability_sources:
        cap_id_to_sources.setdefault(src.capability_id, []).append(src)

    challenge_instances = (
        ChallengeInstance.objects.filter(
            location=location,
            is_active=True,
            is_revealed=True,
        )
        .select_related("template", "target_object")
        .prefetch_related(
            Prefetch(
                "template__properties",
                queryset=Property.objects.all(),
                to_attr="cached_properties",
            ),
            Prefetch(
                "template__approaches",
                queryset=ChallengeApproach.objects.select_related(
                    "application__capability",
                    "application__capability__prerequisite",
                    "application__capability__prerequisite__property",
                    "application__target_property",
                    "application__required_effect_property",
                    "check_type",
                    "required_effect_property",
                    "action_template",
                    "action_template__check_type",
                ),
                to_attr="cached_approaches",
            ),
        )
    )

    actions: list[AvailableAction] = []

    for ci in challenge_instances:
        template = ci.template
        challenge_property_ids = {p.id for p in template.cached_properties}
        _match_approaches(
            character, ci, template, challenge_property_ids, cap_id_to_sources, actions
        )

    actions.extend(_bare_object_actions(character, location, cap_id_to_sources))

    return actions


def _build_action_for_source(  # noqa: PLR0913
    character: ObjectDB,
    ci: ChallengeInstance,
    template: ChallengeTemplate,
    approach: ChallengeApproach,
    app: Application,
    source: CapabilitySource,
    cap_prereq_cache: dict[int, PrerequisiteEvaluation | None],
) -> AvailableAction | None:
    """Build the AvailableAction for one (approach, source) pair, or None if it is skipped."""
    if not _source_meets_effect_requirements(app, approach, source):
        return None

    reasons: list[str] = []
    prereq_met = _evaluate_prerequisites(
        character,
        ci.target_object,
        ci.location,
        app,
        source,
        cap_prereq_cache,
        reasons,
    )

    difficulty = None
    if prereq_met:
        difficulty = _get_difficulty_indicator_for_check(
            character,
            approach.check_type,
            template.severity,
        )
        if difficulty == DifficultyIndicator.IMPOSSIBLE:
            return None

    # Resolve check_type and action_template from the already-loaded approach.
    # If the approach has an action_template override, that template's check_type
    # is authoritative; otherwise fall back to the approach's own check_type.
    override_template = approach.action_template  # may be None (null FK)
    if override_template is not None:
        resolved_check_type = override_template.check_type
        resolved_action_template = override_template
    else:
        resolved_check_type = approach.check_type
        resolved_action_template = None

    return AvailableAction(
        application_id=app.id,
        application_name=app.name,
        capability_source=source,
        challenge_instance_id=ci.id,
        challenge_name=template.name,
        approach_id=approach.id,
        check_type_name=approach.check_type.name,
        display_name=approach.display_name or app.name,
        custom_description=approach.custom_description,
        difficulty_indicator=difficulty,
        prerequisite_met=prereq_met,
        prerequisite_reasons=reasons,
        resolved_check_type=resolved_check_type,
        resolved_action_template=resolved_action_template,
        # Carry the already-loaded instances for dispatch_player_action
        # — no additional queries; ci and approach are from prefetched data.
        resolved_challenge_instance=ci,
        resolved_challenge_approach=approach,
    )


def _match_approaches(  # noqa: PLR0913
    character: ObjectDB,
    ci: ChallengeInstance,
    template: ChallengeTemplate,
    challenge_property_ids: set[int],
    cap_id_to_sources: dict[int, list[CapabilitySource]],
    actions: list[AvailableAction],
) -> None:
    """Match approaches on a challenge to capability sources and append actions."""
    cap_prereq_cache: dict[int, PrerequisiteEvaluation | None] = {}

    for approach in template.cached_approaches:
        app = approach.application
        if app.target_property_id not in challenge_property_ids:
            continue

        matching_sources = cap_id_to_sources.get(app.capability_id, [])

        for source in matching_sources:
            action = _build_action_for_source(
                character, ci, template, approach, app, source, cap_prereq_cache
            )
            if action is not None:
                actions.append(action)


def _bare_object_actions(
    character: ObjectDB,
    location: ObjectDB,
    cap_id_to_sources: dict[int, list[CapabilitySource]],
) -> list[AvailableAction]:
    """Synthesize AvailableActions from ObjectProperty tags on objects at *location*.

    The second availability source (#2503): a flammable torch with no authored
    ChallengeInstance still presents "Ignite" to a character with a generation
    capability source, via ``Application.default_template`` (Task 1's curated
    gate — only Applications an author explicitly wired to a world-interaction
    template synthesize a bare-object action). Candidate objects are
    ``location.contents`` plus the location itself (a room can carry its own
    properties, e.g. "dark").

    Query discipline: one ObjectProperty fetch, one Application fetch (with the
    default_template's approaches prefetched), one ChallengeInstance fetch for
    dedup — none of them inside a loop over objects/applications.
    """
    candidate_objs = [*location.contents, location]
    objects_by_id = {obj.id: obj for obj in candidate_objs}

    property_ids_by_object = _object_property_ids(candidate_objs)
    if not property_ids_by_object:
        return []

    all_property_ids = {pid for prop_ids in property_ids_by_object.values() for pid in prop_ids}
    applications = _bare_object_candidate_applications(cap_id_to_sources, all_property_ids)
    if not applications:
        return []

    active_pairs = set(
        ChallengeInstance.objects.filter(
            location=location,
            is_active=True,
            target_object_id__in=objects_by_id,
        ).values_list("target_object_id", "template_id")
    )

    actions: list[AvailableAction] = []
    for obj_id, prop_ids in property_ids_by_object.items():
        actions.extend(
            _bare_object_actions_for_object(
                character,
                location,
                objects_by_id[obj_id],
                prop_ids,
                applications,
                active_pairs,
                cap_id_to_sources,
            )
        )

    return actions


def _object_property_ids(candidate_objs: list[ObjectDB]) -> dict[int, set[int]]:
    """Batch-fetch ObjectProperty rows for *candidate_objs* in one query.

    Returns a mapping of object pk -> set of property pks carried by that object.
    """
    object_properties = ObjectProperty.objects.filter(object__in=candidate_objs).select_related(
        "property", "object"
    )
    property_ids_by_object: dict[int, set[int]] = {}
    for op in object_properties:
        property_ids_by_object.setdefault(op.object_id, set()).add(op.property_id)
    return property_ids_by_object


def _bare_object_candidate_applications(
    cap_id_to_sources: dict[int, list[CapabilitySource]],
    property_ids: set[int],
) -> list[Application]:
    """Fetch Applications eligible for bare-object synthesis, one query + prefetch.

    Gated to Applications with a curated ``default_template`` (Task 1), whose
    ``target_property`` is present among *property_ids*, and whose capability
    the character has a source for.
    """
    return list(
        Application.objects.filter(
            default_template__isnull=False,
            target_property_id__in=property_ids,
            capability_id__in=list(cap_id_to_sources),
        )
        .select_related(
            "default_template",
            "capability",
            "target_property",
            "required_effect_property",
        )
        .prefetch_related(
            Prefetch(
                "default_template__approaches",
                queryset=ChallengeApproach.objects.select_related(
                    "application__capability",
                    "application__target_property",
                    "application__required_effect_property",
                    "check_type",
                    "required_effect_property",
                    "action_template",
                    "action_template__check_type",
                ),
                to_attr="cached_approaches",
            ),
        )
    )


def _bare_object_actions_for_object(  # noqa: PLR0913
    character: ObjectDB,
    location: ObjectDB,
    obj: ObjectDB,
    prop_ids: set[int],
    applications: list[Application],
    active_pairs: set[tuple[int, int]],
    cap_id_to_sources: dict[int, list[CapabilitySource]],
) -> list[AvailableAction]:
    """Match one candidate object's properties against candidate Applications."""
    # Fresh per-object cache: capability-level prerequisites evaluate against the
    # real target object, so a cache shared across objects would be wrong.
    cap_prereq_cache: dict[int, PrerequisiteEvaluation | None] = {}
    actions: list[AvailableAction] = []

    for app in applications:
        if app.target_property_id not in prop_ids:
            continue

        template = app.default_template
        if (obj.id, template.id) in active_pairs:
            continue  # an authored ChallengeInstance already covers this affordance

        matching_approach = next(
            (a for a in template.cached_approaches if a.application_id == app.id),
            None,
        )
        if matching_approach is None:
            continue

        for source in cap_id_to_sources.get(app.capability_id, []):
            action = _build_bare_object_action(
                character, location, obj, template, matching_approach, app, source, cap_prereq_cache
            )
            if action is not None:
                actions.append(action)

    return actions


def _build_bare_object_action(  # noqa: PLR0913
    character: ObjectDB,
    location: ObjectDB,
    target_object: ObjectDB,
    template: ChallengeTemplate,
    approach: ChallengeApproach,
    app: Application,
    source: CapabilitySource,
    cap_prereq_cache: dict[int, PrerequisiteEvaluation | None],
) -> AvailableAction | None:
    """Build the synthesized AvailableAction for one (object, approach, source), or None.

    Mirrors ``_build_action_for_source`` (same effect-requirement/prerequisite/
    difficulty evaluation) but has no ChallengeInstance yet — dispatch mints one
    via ``instantiate_challenge(template, location, target_object)`` (Task 4).
    """
    if not _source_meets_effect_requirements(app, approach, source):
        return None

    reasons: list[str] = []
    prereq_met = _evaluate_prerequisites(
        character,
        target_object,
        location,
        app,
        source,
        cap_prereq_cache,
        reasons,
    )

    difficulty = None
    if prereq_met:
        difficulty = _get_difficulty_indicator_for_check(
            character,
            approach.check_type,
            template.severity,
        )
        if difficulty == DifficultyIndicator.IMPOSSIBLE:
            return None

    override_template = approach.action_template  # may be None (null FK)
    if override_template is not None:
        resolved_check_type = override_template.check_type
        resolved_action_template = override_template
    else:
        resolved_check_type = approach.check_type
        resolved_action_template = None

    return AvailableAction(
        application_id=app.id,
        application_name=app.name,
        capability_source=source,
        challenge_instance_id=None,
        challenge_name=template.name,
        approach_id=approach.id,
        check_type_name=approach.check_type.name,
        display_name=approach.display_name or app.name,
        custom_description=approach.custom_description,
        difficulty_indicator=difficulty,
        prerequisite_met=prereq_met,
        prerequisite_reasons=reasons,
        resolved_check_type=resolved_check_type,
        resolved_action_template=resolved_action_template,
        # No ChallengeInstance yet — dispatch mints one from the fields below.
        resolved_challenge_instance=None,
        resolved_challenge_approach=approach,
        target_object=target_object,
        resolved_default_template=template,
    )


def _evaluate_prerequisites(  # noqa: PLR0913
    character: ObjectDB,
    target_object: ObjectDB,
    location: ObjectDB,
    app: Application,
    source: CapabilitySource,
    cap_prereq_cache: dict[int, PrerequisiteEvaluation | None],
    reasons: list[str],
) -> bool:
    """Evaluate capability-level and source-level prerequisites.

    Returns True if all prerequisites are met. Appends failure reasons.
    Uses cap_prereq_cache to avoid re-evaluating the same capability prerequisite.
    ``cap_prereq_cache`` must be scoped to a single ``target_object``/``location``
    pair (capability-level prerequisites evaluate against the real target, so a
    cache shared across different targets would be incorrect) — callers with
    a fixed ``ci`` (one target per challenge) or a fixed bare object (one target
    per outer loop iteration) already satisfy this.

    Note: source-level prerequisites each trigger an ObjectProperty query.
    For future optimization, consider bulk-fetching ObjectProperty records
    for all relevant entities upfront.
    """
    all_met = True

    # Capability-level prerequisite (shared across all sources of this capability)
    cap_id = app.capability_id
    if cap_id not in cap_prereq_cache:
        cap_prereq = app.capability.prerequisite
        if cap_prereq is not None:
            cap_prereq_cache[cap_id] = cap_prereq.evaluate(
                character,
                target_object,
                location,
            )
        else:
            cap_prereq_cache[cap_id] = None

    cap_result = cap_prereq_cache[cap_id]
    if cap_result is not None and not cap_result.met:
        reasons.append(cap_result.reason)
        all_met = False

    # Source-level prerequisite (specific to this technique grant)
    if source.prerequisite is not None:
        src_result = source.prerequisite.evaluate(
            character,
            target_object,
            location,
        )
        if not src_result.met:
            reasons.append(src_result.reason)
            all_met = False

    return all_met


def _source_meets_effect_requirements(
    app: Application,
    approach: ChallengeApproach,
    source: CapabilitySource,
) -> bool:
    """Check if a source meets the effect property requirements of app and approach."""
    if app.required_effect_property_id:
        if app.required_effect_property_id not in source.effect_property_ids:
            return False

    if approach.required_effect_property_id:
        if approach.required_effect_property_id not in source.effect_property_ids:
            return False

    return True


# Rank difference thresholds for difficulty indicator.
# These use the actual check pipeline's rank system.
_RANK_DIFF_EASY = 3
_RANK_DIFF_MODERATE = 1
_RANK_DIFF_HARD = -1


def _get_difficulty_indicator_for_check(
    character: ObjectDB,
    check_type: CheckType,
    target_difficulty: int,
) -> DifficultyIndicator:
    """
    Determine difficulty indicator using the real check pipeline.

    Calculates the rank difference that would result from a check,
    then classifies it. IMPOSSIBLE means the ResultChart has no success outcomes.
    """
    rank_diff = preview_check_difficulty(character, check_type, target_difficulty)

    if not chart_has_success_outcomes(rank_diff):
        return DifficultyIndicator.IMPOSSIBLE
    if rank_diff >= _RANK_DIFF_EASY:
        return DifficultyIndicator.EASY
    if rank_diff >= _RANK_DIFF_MODERATE:
        return DifficultyIndicator.MODERATE
    if rank_diff >= _RANK_DIFF_HARD:
        return DifficultyIndicator.HARD
    return DifficultyIndicator.VERY_HARD


# =============================================================================
# Engagement Lifecycle
# =============================================================================


def begin_engagement(
    character: ObjectDB,  # noqa: OBJECTDB_PARAM
    engagement_type: str,
    *,
    source: object,
) -> CharacterEngagement:
    """Ensure the character has an engagement; create one if none exists.

    Looks up by character only (the OneToOne makes any narrower get_or_create
    raise IntegrityError). An existing engagement of ANY type is returned
    unchanged — a character already in stakes (challenge/mission) is not
    re-engaged by combat. ``source`` must be a saved Django model instance
    (it must have a valid ``.pk``).
    """
    from django.contrib.contenttypes.models import ContentType  # noqa: PLC0415

    from world.mechanics.engagement import CharacterEngagement  # noqa: PLC0415

    engagement, _ = CharacterEngagement.objects.get_or_create(
        character=character,
        defaults={
            "engagement_type": engagement_type,
            "source_content_type": ContentType.objects.get_for_model(source),
            "source_id": source.pk,
        },
    )
    return engagement


def end_engagement(
    character: ObjectDB,  # noqa: OBJECTDB_PARAM
    engagement_type: str,
    *,
    source: object,
) -> None:
    """Delete the character's engagement iff it matches type AND source.

    Deleting the engagement discards its transient process modifiers
    (intensity/control) by design. No-op when no matching row exists.
    """
    from django.contrib.contenttypes.models import ContentType  # noqa: PLC0415

    from world.mechanics.engagement import CharacterEngagement  # noqa: PLC0415

    CharacterEngagement.objects.filter(
        character=character,
        engagement_type=engagement_type,
        source_content_type=ContentType.objects.get_for_model(source),
        source_id=source.pk,
    ).delete()


def property_damage_bonus(target: ObjectDB, damage_type: DamageType | None) -> int:
    """Sum PropertyDamageModifier.modifier_value for target's active Properties.

    Matches rows keyed on the specific damage_type plus rows with a null
    damage_type (applies to all types). Returns 0 when target carries no
    matching Property (may be negative when a modifier reduces damage).
    """
    property_ids = list(
        ObjectProperty.objects.filter(object=target).values_list("property_id", flat=True)
    )
    if not property_ids:
        return 0
    modifiers = PropertyDamageModifier.objects.filter(property_id__in=property_ids).filter(
        Q(damage_type=damage_type) | Q(damage_type__isnull=True)
    )
    return sum(m.modifier_value for m in modifiers)


def volatile_object_property(target: ObjectDB) -> ObjectProperty | None:
    """Return the ``ObjectProperty`` making *target* volatile (detonatable), or None.

    An object is volatile when it carries an ``ObjectProperty`` whose ``property``
    has a ``PropertyDetonation`` row (#2210 — combat redirect resolution). Returns
    the first matching row (an object is expected to carry at most one detonatable
    property in practice; no ordering guarantee beyond pk if more than one exists).
    """
    return (
        ObjectProperty.objects.filter(object=target, property__detonation__isnull=False)
        .select_related("property__detonation__consequence_pool")
        .first()
    )


def stage_property(target: ObjectDB, property_: Property, value: int = 1) -> ObjectProperty:
    """GM improv: attach or refresh a Property on ``target`` (#2503).

    Mirrors ``actions.effects.effect_handlers._add_property``'s upsert convention
    (``update_or_create`` keyed on ``object``+``property``) as a directly-callable
    service — a GM narrating "this door looks locked" outside any authored
    consequence chain. Idempotent: re-staging the same property on the same
    target updates its value rather than duplicating the row.
    """
    obj_prop, _ = ObjectProperty.objects.update_or_create(
        object=target,
        property=property_,
        defaults={"value": value},
    )
    return obj_prop


def prerequisites_met(prereqs: Iterable[Prerequisite], caster: ObjectDB, target: ObjectDB) -> bool:
    """True if target satisfies every one of prereqs (all() semantics; empty = True).

    Shared by both cast paths' target-prerequisite checks (#1793 second-pass dedup):
    magic's non-combat ``_target_meets_prerequisites``/``_check_target_prerequisites``
    and combat's ``_check_combat_target_prerequisites``/
    ``_filter_by_target_prerequisites`` (all in ``world/magic/services/targeting.py``
    / ``world/combat/services.py`` respectively). For a SELF-relationship caller,
    pass ``caster`` as both ``caster`` and ``target``.
    """
    return all(prereq.evaluate(caster, target, target.location).met for prereq in prereqs)
