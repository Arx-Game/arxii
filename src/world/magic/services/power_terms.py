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


def aura_power_term(ctx: PowerTermContext) -> int:
    """Aura contribution to power: affinity-alignment + resonance standing (#768).

    Affinity axis: caster's CharacterAura % in each distinct affinity of the
    technique's resonances, proportional to ``affinity_alignment_bonus``.
    Standing axis ("aura farming"): summed CharacterResonance.lifetime_earned
    in those resonances x ``resonance_standing_bonus``, soft-capped.
    Returns 0 when unconfigured or when the cast has no technique.
    """
    from world.magic.models.aura import CharacterAura, CharacterResonance  # noqa: PLC0415

    config = get_aura_power_config()
    if config is None or ctx.technique is None:
        return 0

    resonances = list(ctx.technique.gift.resonances.all())
    if not resonances:
        return 0

    alignment = 0
    if config.affinity_alignment_bonus:
        aura = CharacterAura.objects.filter(character=ctx.sheet.character).first()
        if aura is not None:
            affinities = {r.affinity for r in resonances}
            for affinity in affinities:
                pct = getattr(aura, affinity.name.lower(), None)
                if pct is not None:
                    alignment += int(pct / 100 * config.affinity_alignment_bonus)

    standing = 0
    if config.resonance_standing_bonus:
        resonance_ids = [r.pk for r in resonances]
        total_earned = sum(
            cr.lifetime_earned
            for cr in CharacterResonance.objects.filter(
                character_sheet=ctx.sheet, resonance_id__in=resonance_ids
            )
        )
        standing = total_earned * config.resonance_standing_bonus
        if config.resonance_standing_cap:
            standing = min(standing, config.resonance_standing_cap)

    return int(alignment + standing)


def thread_power_term(_ctx: PowerTermContext) -> int:
    """Contribution from applicable threads (tier-0 passive + active pulls). Returns 0 (stub).

    The full implementation requires knowing which threads are applicable to
    the action and at what pull tier. Applicable threads are passed in via
    ``_ctx.applicable_threads`` — the stub is ready to receive them.
    """
    # TODO: implement per-thread tier contribution once out-of-combat pull
    # mechanics are wired (mirrors the combat CombatPull path)
    return 0


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

_PROVIDERS: list[PowerTermProvider] = [
    level_power_term,
    aura_power_term,
    thread_power_term,
]


def get_power_term_providers() -> list[PowerTermProvider]:
    return list(_PROVIDERS)
