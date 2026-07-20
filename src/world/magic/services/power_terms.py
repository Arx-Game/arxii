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
    from world.magic.models import (
        AuraPowerConfig,
        CovenantRoleBlendConfig,
        LevelPowerConfig,
        Technique,
        Thread,
    )


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
    """Immutable snapshot of cast context passed to every power term provider.

    ``situation_ctx`` (#2536, Task 4): the SUBJECT's live resolution context —
    a ``CombatRoundContext`` (``world/combat/round_context.py``) when the cast
    is resolving inside combat, or ``None`` for a non-combat/standalone cast.
    Threaded straight through from ``_derive_power``'s own ``situation_ctx``
    parameter to ``perks.services.applicable_perks`` via
    ``vow_situational_power_term`` below — combat-positioning situations
    (``AT_RANGE``/``IN_MELEE``/...) only ever hold when this is a real
    ``CombatRoundContext``; DB-state situations (``TARGET_DISTRACTED``,
    ``DURING_NEGOTIATION``, ...) hold regardless. Defaulted so every existing
    constructor (non-combat call sites, every test fixture) stays valid
    unchanged.

    ``target_sheet`` (#2536, Task 4 review fix): the cast's primary target's
    ``CharacterSheet``, or ``None`` when the cast has no target (SELF casts,
    non-combat casts, an NPC-only opponent with no linked ``CharacterSheet``).
    Threaded straight through to ``perks.services.applicable_perks``'s
    ``target=`` kwarg via ``vow_situational_power_term`` below — this is what
    lets the four target-keyed situations (``TARGET_DISTRACTED``,
    ``TARGET_SWAYED_BY_ALLY``, ``TARGET_FOCUSED_ELSEWHERE``,
    ``TARGET_FAVORABLY_DISPOSED``) fire for ``POWER_BONUS``. For a
    multi-target/AoE cast, only the FIRST/primary resolved target is threaded
    — per-target perk evaluation for AoE casts is a legitimate slice-2+
    refinement, not built here. Defaulted so every existing constructor stays
    valid unchanged.
    """

    sheet: CharacterSheet
    technique: Technique | None
    applicable_threads: Sequence[ApplicableThread]
    situation_ctx: object | None = None
    target_sheet: object | None = None


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


def get_covenant_role_blend_config() -> CovenantRoleBlendConfig:
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


def covenant_role_specialty_power_term(ctx: PowerTermContext) -> int:
    """Per-vow technique-specialty boost (#2443, Layer 2).

    Always-on flat bonus when the cast technique carries a TechniqueFunction
    the engaged vow specializes in: Σ over engaged roles, over matching
    specialty rows, of total_thread_level × row.multiplier_tenths / 10.

    Row collection per engaged (resolved) role: the ANCHOR role's rows PLUS
    the resolved sub-role's own rows when it differs — sub-roles build upward
    (add), never replace (#2443 spec §3; contrast the anchor-only rule in
    covenant_role_action_scaling_bonus).
    """
    from decimal import Decimal  # noqa: PLC0415

    from world.covenants.models import CovenantRoleTechniqueSpecialty  # noqa: PLC0415
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
    functions = {tag.function for tag in ctx.technique.cached_function_tags}
    if not functions:
        return 0
    total_threads = total_thread_level_across_all_kinds(ctx.sheet)
    if total_threads == 0:
        return 0

    role_ids: set[int] = set()
    for role in engaged_roles:
        role_ids.add(role.pk)
        if role.parent_role_id is not None:
            role_ids.add(role.parent_role_id)

    rows = CovenantRoleTechniqueSpecialty.objects.filter(
        covenant_role_id__in=role_ids,
        function__in=functions,
    )
    total = Decimal(0)
    for row in rows:
        total += Decimal(total_threads) * row.multiplier_tenths / 10
    return int(total)


def vow_situational_power_term(ctx: PowerTermContext) -> int:
    """Per-vow situational-perk power boost (#2536 slice 1, Layer 4).

    Σ over every fired ``POWER_BONUS`` perk (self + engaged covenant-mate
    beneficiaries — see ``perks.services.applicable_perks``) of
    ``total_thread_level_across_all_kinds(ctx.sheet) × magnitude_tenths /
    10``, int-truncated — mirrors ``covenant_role_specialty_power_term``'s
    arithmetic exactly (same thread-level scaling, same integer truncation
    after summing in ``Decimal``).

    Guards: no technique → 0 (perks are cast-scoped); no engaged role on the
    subject → 0 (cheap exit before the resolution query —
    ``applicable_perks``'s own ``_ally_candidates`` also requires the subject
    to hold at least one engaged role before an ally's ``WHOLE_GROUP``/
    ``COVENANT_ALLIES`` perk can reach them, so this guard never skips a case
    ``applicable_perks`` would otherwise have fired).

    ``resolution=ctx.situation_ctx`` — the live ``CombatRoundContext`` in
    combat (threaded by ``resolve_combat_technique``,
    ``world/combat/services.py``, and by ``commit_to_clash``,
    ``world/combat/clash.py``), or ``None`` outside combat; DB-state
    situations still evaluate correctly with ``None`` (see
    ``SituationContext``'s docstring).

    ``target=ctx.target_sheet`` (#2536 Task 4 review fix): the cast's primary
    target's ``CharacterSheet``, threaded from the combat round path
    (``resolve_combat_technique`` resolves it from ``action
    .focused_ally_target``/``.focused_opponent_target.persona`` — see
    ``world/combat/services.py``'s ``_resolve_primary_target_sheet``) or
    ``None`` outside combat / for a SELF cast / for an NPC-only opponent with
    no linked ``CharacterSheet``. This is what lets the four target-keyed
    situations (``TARGET_DISTRACTED``, ``TARGET_SWAYED_BY_ALLY``,
    ``TARGET_FOCUSED_ELSEWHERE``, ``TARGET_FAVORABLY_DISPOSED``) fire for
    ``POWER_BONUS`` — previously hard-inert with ``target=None`` always
    passed, now live whenever the resolver can name a PC/sheet-backed
    primary target. For a multi-target/AoE cast only the FIRST/primary
    resolved target is threaded (see ``PowerTermContext.target_sheet``'s
    docstring) — per-target perk evaluation for AoE is deferred to a future
    slice. Non-target situations (``AT_RANGE``/``IN_MELEE``/``SURROUNDED``/
    ``ALLY_LOW_HEALTH``/``DURING_NEGOTIATION``) are unaffected either way.

    **Clash contributions (#2536 Task 4 review fix):** ``commit_to_clash``
    threads ``situation_ctx`` (a real ``CombatRoundContext`` built from the
    clash's resolved ``CombatParticipant``) but NOT ``target_sheet`` — a
    clash contribution's production caller (``run_clash_round``) never
    supplies an explicit target (a clash is a PC-vs-clash-meter contribution
    against an NPC threat, not a cast at a specific character), so
    target-keyed situations correctly read ``False`` there via
    ``target=None``, exactly as they do for any other targetless cast.
    ``commit_to_clash``'s pre-existing ``targets:`` parameter is forwarded to
    ``use_technique`` unchanged (reactive-event purposes only) but does not
    feed ``target_sheet`` — no production caller populates it, so wiring it
    up now would be speculative; a future clash target concept can extend
    this the same way the round path was extended here.

    ATTRIBUTABILITY (ruling 1): this provider's ledger TERM-stage label is the
    static ``_power_term_label``-derived string ("vow situational power"),
    the SAME limitation every other multi-source provider in this file has
    (the TERM loop in ``_derive_power`` calls ``_power_term_label(provider)``
    once per provider function, not per return value — there is no channel
    for a provider to report which of its several internal contributions
    produced the total). The per-perk NAME the player sees comes from the
    announce path (#2536 Task 6: ``perks.services.announce_fired_perks``,
    called below right after ``fired`` is known — not the power ledger).
    See ADR-0151 (the slice-1 machinery ADR) for the precise slice-2
    refactor this implies if the ledger ever needs dynamic per-source TERM
    labels.
    """
    from decimal import Decimal  # noqa: PLC0415

    from world.covenants.perks.constants import PerkEffectKind  # noqa: PLC0415
    from world.covenants.perks.services import (  # noqa: PLC0415
        announce_fired_perks,
        applicable_perks,
    )
    from world.magic.services.threads import (  # noqa: PLC0415
        total_thread_level_across_all_kinds,
    )

    if ctx.technique is None:
        return 0
    character = ctx.sheet.character
    if not hasattr(character, "covenant_roles"):
        return 0
    if not character.covenant_roles.currently_engaged_roles():
        return 0

    fired = applicable_perks(
        ctx.sheet,
        effect_kind=PerkEffectKind.POWER_BONUS,
        resolution=ctx.situation_ctx,
        target=ctx.target_sheet,
    )
    if not fired:
        return 0

    # #2536 Task 6: announce here, not inside applicable_perks — this
    # provider is the single production entry point for a cast's power
    # derivation (use_technique calls _derive_power exactly once), so this
    # is the ONE place a POWER_BONUS firing can be announced without risking
    # a double-announce. See announce_fired_perks's docstring.
    announce_fired_perks(fired, subject=ctx.sheet, location=character.location)

    total_threads = total_thread_level_across_all_kinds(ctx.sheet)
    if total_threads == 0:
        return 0

    total = Decimal(0)
    for firing in fired:
        total += Decimal(total_threads) * firing.magnitude_tenths / 10
    return int(total)


_PROVIDERS: list[PowerTermProvider] = [
    level_power_term,
    aura_power_term,
    thread_power_term,
    touchstone_power_term,
    enhancement_overlap_term,
    covenant_role_blend_power_term,
    covenant_role_specialty_power_term,
    vow_situational_power_term,
]


def get_power_term_providers() -> list[PowerTermProvider]:
    return list(_PROVIDERS)
