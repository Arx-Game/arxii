"""Speech comprehension services (#2993): garbling + fluency resolution.

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
