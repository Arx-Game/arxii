"""Speech comprehension services (#2993): garbling + fluency resolution.

Two fluency reads (#4090): ``fluency_value`` is trained fluency, the only one the speak
gate, the speaker's band, teaching and self-study read. ``comprehension_value`` is what a
LISTENER understands: trained fluency plus active-condition bonuses, so a condition grants
understanding and never speech.

Deterministic garble (seed_key) is what lets live delivery, WS push, and
scene-log reads all agree on which words leaked - and lets a player who later
learns the language re-read old logs in the clear (live recompute; see the
#2993 ADR for the deliberate divergence from ADR-0170 snapshotting).
"""

from __future__ import annotations

import random
from typing import TYPE_CHECKING
import zlib

from world.species.language_constants import BAND_KEEP_RATIO, Fluency, fluency_band
from world.species.types import ConditionFluencyBonus

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.species.models import Language

_COMPREHENSION_ORDER = [Fluency.NONE, Fluency.BROKEN, Fluency.CONVERSATIONAL, Fluency.FLUENT]


def garble_text(text: str, keep_ratio: float, *, seed_key: str | None = None) -> str:
    """Word-survival garble. seed_key=None -> SystemRandom (mutter's behavior)."""
    words = text.split()
    if not words or keep_ratio <= 0.0:
        return "..."
    if keep_ratio >= 1.0:
        return text
    if seed_key is None:
        rng: random.Random = random.SystemRandom()  # NOSONAR game RNG, not crypto
    else:
        rng = random.Random(zlib.crc32(seed_key.encode()))  # noqa: S311 # NOSONAR game RNG, not crypto
    kept_flags = [rng.random() < keep_ratio for _ in words]  # NOSONAR game RNG, not crypto
    if not any(kept_flags):
        kept_flags[rng.randrange(len(words))] = True  # NOSONAR game RNG, not crypto
    parts: list[str] = []
    for word, kept in zip(words, kept_flags, strict=True):
        if kept:
            parts.append(word)
        elif not parts or parts[-1] != "...":
            parts.append("...")
    return " ".join(parts)


def speech_seed(language_id: int, text: str) -> str:
    """Stable seed so every channel (live, WS, log) garbles identically."""
    return f"{language_id}:{text}"


def fluency_value(sheet: CharacterSheet, language: Language) -> int:
    """The sheet's 1-100 fluency in language (0 = none/no trait link)."""
    if language.trait_id is None:
        return 0
    from world.traits.models import CharacterTraitValue  # noqa: PLC0415

    row = CharacterTraitValue.objects.filter(character=sheet, trait_id=language.trait_id).first()
    return row.value if row else 0


def comprehension_value(sheet: CharacterSheet, language: Language) -> int:
    """Listener-side fluency: trained plus active-condition bonuses, floored at 0 (#4090).

    Only the LISTENER reads this. The speak gate, the speaker's own band, teaching and
    self-study keep reading ``fluency_value`` (trained), so a condition grants
    understanding and never speech. Only active conditions count (``CharacterModifier``
    rows from distinctions or equipment do not), through the one ``ModifierTarget`` that
    ``ModifierTarget.get_for_trait`` returns for the language's trait. The condition read
    is the pure batched one (two queries, never tears down an expired condition).
    """
    trained = fluency_value(sheet, language)
    if language.trait_id is None:
        return trained
    from world.conditions.services import condition_modifier_totals_by_sheet  # noqa: PLC0415
    from world.mechanics.models import ModifierTarget  # noqa: PLC0415

    target = ModifierTarget.get_for_trait(language.trait)
    if target is None:
        return trained
    bonus = condition_modifier_totals_by_sheet([sheet.pk], target).get(sheet.pk, 0)
    return max(0, trained + bonus)


def condition_language_bonuses(sheet: CharacterSheet) -> dict[int, ConditionFluencyBonus]:
    """Every language an active condition on *sheet* changes, keyed by Language pk (#4090).

    Backs the sheet's temporary rows. Two queries: the active conditions (the same pure
    read ``comprehension_value`` uses, so an expired in-game-time condition is skipped and
    never torn down), then the language-trait effects on their templates and current
    stages. Only the target ``ModifierTarget.get_for_trait`` picks for a language counts,
    matching ``comprehension_value``. Languages whose contributions sum to 0 are left out;
    ``sources`` lists each contributing condition's name once, in the order read.
    """
    from django.db.models import Q  # noqa: PLC0415

    from world.conditions.models import ConditionModifierEffect  # noqa: PLC0415
    from world.conditions.services import (  # noqa: PLC0415
        active_condition_instances_by_sheet,
        scaled_condition_effect_value,
    )
    from world.mechanics.models import ModifierTarget  # noqa: PLC0415
    from world.traits.models import TraitType  # noqa: PLC0415

    instances = active_condition_instances_by_sheet([sheet.pk])
    if not instances:
        return {}
    condition_ids = {instance.condition_id for instance in instances}
    stage_ids = {instance.current_stage_id for instance in instances if instance.current_stage_id}
    effects = [
        effect
        for effect in ConditionModifierEffect.objects.filter(
            Q(condition_id__in=condition_ids) | Q(stage_id__in=stage_ids),
            modifier_target__target_trait__trait_type=TraitType.LANGUAGE,
            modifier_target__target_trait__language__isnull=False,
        ).select_related("modifier_target__target_trait__language")
        if ModifierTarget.get_for_trait(effect.modifier_target.target_trait)
        == effect.modifier_target
    ]
    totals: dict[int, int] = {}
    sources: dict[int, list[str]] = {}
    for instance in instances:
        for effect in effects:
            on_condition = effect.condition_id == instance.condition_id
            on_stage = effect.stage_id is not None and effect.stage_id == instance.current_stage_id
            if not (on_condition or on_stage):
                continue
            value = scaled_condition_effect_value(effect, instance)
            if value == 0:
                continue
            language_id = effect.modifier_target.target_trait.language.pk
            totals[language_id] = totals.get(language_id, 0) + value
            names = sources.setdefault(language_id, [])
            if instance.condition.name not in names:
                names.append(instance.condition.name)
    return {
        language_id: ConditionFluencyBonus(
            language_id=language_id, total=total, sources=tuple(sources[language_id])
        )
        for language_id, total in totals.items()
        if total != 0
    }


def effective_band(speaker_band: Fluency, listener_band: Fluency) -> Fluency:
    """min(speaker, listener) - a broken speaker is hard for everyone."""
    s = _COMPREHENSION_ORDER.index(speaker_band)
    lo = _COMPREHENSION_ORDER.index(listener_band)
    return _COMPREHENSION_ORDER[min(s, lo)]


def render_speech(
    text: str,
    *,
    language: Language,
    speaker_band: Fluency,
    listener_value: int,
) -> str:
    """The text as a listener with listener_value fluency comprehends it."""
    band = effective_band(speaker_band, fluency_band(listener_value))
    if band == Fluency.FLUENT:
        return text
    return garble_text(text, BAND_KEEP_RATIO[band], seed_key=speech_seed(language.pk, text))
