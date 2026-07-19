"""Power term providers for _derive_power (#637).

Each provider is a callable ``(PowerTermContext) -> int`` registered in
``_PROVIDERS``. ``_derive_power`` calls every provider and sums their
contributions on top of the CharacterModifier/condition modifier totals.

Adding a new term: write a function, register it below.  The function owns
its own config query (a singleton model or constants) and returns 0 when
unconfigured so the term is opt-in for staff.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.magic.models import AuraPowerConfig, LevelPowerConfig, Technique, Thread


@dataclass(frozen=True)
class ApplicableThread:
    """A thread that is in-scope for a given cast, with its pull tier.

    ``pull_tier`` is 0 when the thread is passive (not actively pulled),
    or 1–3 when the caster has pulled it at that tier for this action.
    """

    thread: Thread
    pull_tier: int  # 0 = passive, 1–3 = actively pulled


@dataclass(frozen=True)
class PowerTermContext:
    """Immutable snapshot of cast context passed to every power term provider."""

    sheet: CharacterSheet
    technique: Technique | None
    applicable_threads: Sequence[ApplicableThread]


PowerTermProvider = Callable[[PowerTermContext], int]


# ---------------------------------------------------------------------------
# Singleton accessor
# ---------------------------------------------------------------------------


def get_level_power_config() -> LevelPowerConfig | None:
    """Return the LevelPowerConfig singleton, or None if no row exists yet."""
    from world.magic.models import LevelPowerConfig  # noqa: PLC0415

    return LevelPowerConfig.objects.filter(pk=1).first()


def get_aura_power_config() -> AuraPowerConfig | None:
    """Return the AuraPowerConfig singleton, or None if no row exists yet."""
    from world.magic.models import AuraPowerConfig  # noqa: PLC0415

    return AuraPowerConfig.objects.filter(pk=1).first()


# ---------------------------------------------------------------------------
# Providers
# ---------------------------------------------------------------------------


def level_power_term(ctx: PowerTermContext) -> int:
    """Flat bonus from character level and technique level per LevelPowerConfig."""
    config = get_level_power_config()
    if config is None:
        return 0
    char_contribution = ctx.sheet.current_level * config.character_level_bonus
    tech_contribution = 0
    if ctx.technique is not None:
        tech_contribution = ctx.technique.level * config.technique_level_bonus
    return char_contribution + tech_contribution


def _apply_standing_cap(standing: int, current_level: int) -> int:
    """Apply the per-level StandingCapBand to a raw resonance-standing value (#853).

    Selects the band with the greatest ``min_level`` <= ``current_level``. No
    matching band returns ``standing`` unchanged (uncapped). HARD clamps to the
    band cap; SOFT keeps ``diminish_pct`` percent of the excess above the cap.
    """
    from world.magic.constants import StandingCapMode  # noqa: PLC0415
    from world.magic.models import StandingCapBand  # noqa: PLC0415

    band = (
        StandingCapBand.objects.filter(min_level__lte=current_level).order_by("-min_level").first()
    )
    if band is None or standing <= band.cap:
        return standing
    if band.mode == StandingCapMode.HARD:
        return band.cap
    return band.cap + (standing - band.cap) * band.diminish_pct // 100


def _aura_alignment(ctx: PowerTermContext, config: AuraPowerConfig, resonances: list) -> int:
    """Affinity-alignment contribution: caster's CharacterAura % per distinct affinity."""
    from world.magic.models.aura import CharacterAura  # noqa: PLC0415

    if not config.affinity_alignment_bonus:
        return 0
    aura = CharacterAura.objects.filter(character=ctx.sheet.character).first()
    if aura is None:
        return 0
    alignment = 0
    affinities = {r.affinity for r in resonances}
    for affinity in affinities:
        pct = getattr(aura, affinity.name.lower(), None)
        if pct is not None:
            alignment += int(pct / 100 * config.affinity_alignment_bonus)
    return alignment


def _aura_standing(ctx: PowerTermContext, config: AuraPowerConfig, resonances: list) -> int:
    """Resonance-standing contribution: summed lifetime_earned x bonus, per-level cap-banded."""
    from world.magic.models.aura import CharacterResonance  # noqa: PLC0415

    if not config.resonance_standing_bonus:
        return 0
    resonance_ids = [r.pk for r in resonances]
    total_earned = sum(
        cr.lifetime_earned
        for cr in CharacterResonance.objects.filter(
            character_sheet=ctx.sheet, resonance_id__in=resonance_ids
        )
    )
    standing = total_earned * config.resonance_standing_bonus
    return _apply_standing_cap(standing, ctx.sheet.current_level)


def aura_power_term(ctx: PowerTermContext) -> int:
    """Aura contribution to power: affinity-alignment + resonance standing (#768).

    Affinity axis: caster's CharacterAura % in each distinct affinity of the
    technique's resonances, proportional to ``affinity_alignment_bonus``.
    Standing axis ("aura farming"): summed CharacterResonance.lifetime_earned
    in those resonances x ``resonance_standing_bonus``, then capped per character
    level by the applicable ``StandingCapBand`` (HARD clamp / SOFT diminish; #853).
    Returns 0 when unconfigured or when the cast has no technique.
    """
    config = get_aura_power_config()
    if config is None or ctx.technique is None:
        return 0

    from world.magic.specialization.services import gift_resonances_for  # noqa: PLC0415

    resonances = list(gift_resonances_for(ctx.sheet.character, ctx.technique.gift))
    if not resonances:
        return 0

    alignment = _aura_alignment(ctx, config, resonances)
    standing = _aura_standing(ctx, config, resonances)

    return int(alignment + standing)


def thread_power_term(ctx: PowerTermContext) -> int:
    """Out-of-combat per-thread INTENSITY_BUMP contribution (#768).

    Mirrors the combat CombatPull INTENSITY_BUMP path: for each applicable
    thread, resolve its pull effects across tiers 0..pull_tier (the existing
    charge-free ``resolve_pull_effects`` scaler) and sum INTENSITY_BUMP
    scaled values. Tier-0 passive contributions are included because the
    resolver always covers tier 0.
    """
    from world.magic.constants import EffectKind  # noqa: PLC0415
    from world.magic.services.resonance import resolve_pull_effects  # noqa: PLC0415

    total = 0
    for applicable in ctx.applicable_threads:
        resolved = resolve_pull_effects([applicable.thread], applicable.pull_tier, in_combat=False)
        total += sum(
            r.scaled_value
            for r in resolved
            if r.kind == EffectKind.INTENSITY_BUMP and r.scaled_value
        )
    return total


def touchstone_power_term(ctx: PowerTermContext) -> int:
    """Flat bonus from attuned touchstones matching the technique's gift resonance (#2023).

    Scans the character's equipped items for touchstones whose ``tied_resonance``
    matches any of the technique's gift resonances. The bonus is modest and
    tier-scaled via ``TouchstoneCastConfig``.
    """
    if ctx.technique is None:
        return 0
    from world.magic.services.touchstone import touchstone_cast_bonus  # noqa: PLC0415
    from world.magic.specialization.services import gift_resonances_for  # noqa: PLC0415

    resonances = gift_resonances_for(ctx.sheet.character, ctx.technique.gift)
    if not resonances:
        return 0
    return sum(touchstone_cast_bonus(ctx.sheet, resonance) for resonance in resonances)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


def enhancement_overlap_term(ctx: PowerTermContext) -> int:
    """Flat bonus when an enhancement technique overlaps the character's existing kit (#2022).

    Role-granted enhancement techniques (``Technique.enhances_effect_type`` is set)
    are primarily passive boosts to the character's existing techniques that serve
    the same role function. When the character also has a technique whose
    ``effect_type`` matches this technique's ``enhances_effect_type``, the cast
    gains a flat intensity bonus — the vow amplifies what the character already
    does.

    Returns 0 when the technique has no ``enhances_effect_type`` or when the
    character has no matching technique. The bonus amount is a fixed constant
    (the enhancement is a rider, not a replacement).
    """
    from world.magic.models import CharacterTechnique  # noqa: PLC0415

    if ctx.technique is None or ctx.technique.enhances_effect_type_id is None:
        return 0
    has_overlap = CharacterTechnique.objects.filter(
        character_id=ctx.sheet.pk,
        technique__effect_type_id=ctx.technique.enhances_effect_type_id,
    ).exists()
    if not has_overlap:
        return 0
    return _ENHANCEMENT_OVERLAP_BONUS


# Flat intensity bonus when an enhancement technique overlaps existing kit.
# Tunable — a small rider that makes a well-matched vow feel rewarding without
# being a replacement for a standalone technique.
_ENHANCEMENT_OVERLAP_BONUS: int = 2


def get_covenant_role_blend_config():
    """Return the CovenantRoleBlendConfig singleton, lazy-creating pk=1."""
    from world.magic.models import CovenantRoleBlendConfig  # noqa: PLC0415

    config, _ = CovenantRoleBlendConfig.objects.get_or_create(pk=1)
    return config


def covenant_role_blend_power_term(ctx: PowerTermContext) -> int:
    """Baseline blend boost for engaged covenant roles (#2529, Layer 1).

    Always-on floor: Σ over engaged roles of
    ``total_thread_level × blend_weight[technique.archetype_alignment]
    × multiplier``. Situational perks (Layer 4, #2536) layer on top; this
    term is the floor that keeps every engaged vow relevant, not the fantasy.
    Kept as its own provider so the contribution stays attributable
    (#2536's presentation contract).
    """
    from decimal import Decimal  # noqa: PLC0415

    from world.magic.services.threads import (  # noqa: PLC0415
        total_thread_level_across_all_kinds,
    )

    if ctx.technique is None:
        return 0
    character = ctx.sheet.character
    if not hasattr(character, "covenant_roles"):
        return 0
    engaged_roles = character.covenant_roles.currently_engaged_roles()
    if not engaged_roles:
        return 0
    total_threads = total_thread_level_across_all_kinds(ctx.sheet)
    if total_threads == 0:
        return 0
    config = get_covenant_role_blend_config()
    alignment = ctx.technique.archetype_alignment
    total = Decimal(0)
    for role in engaged_roles:
        weight = role.blend_weight_for(alignment)
        if not weight:
            continue
        total += Decimal(total_threads) * weight * config.multiplier_tenths / 10
    return int(total)


_PROVIDERS: list[PowerTermProvider] = [
    level_power_term,
    aura_power_term,
    thread_power_term,
    touchstone_power_term,
    enhancement_overlap_term,
    covenant_role_blend_power_term,
]


def get_power_term_providers() -> list[PowerTermProvider]:
    return list(_PROVIDERS)
