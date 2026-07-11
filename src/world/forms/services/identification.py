"""Identification difficulty service (#1107 slice 5, Apostate's 2026-07-03 ruling).

A viewer can try to figure out who's really under a mask/disguise: an Identification check
(intellect + Investigation, seeded in ``world.seeds.investigation_checks``) rolled against the
target's disguise baseline, staged by familiarity. This module owns the **difficulty table**
(``identification_difficulty``) — pure computation, no ``perform_check`` call and no
``PersonaDiscovery`` write; those live in ``attempt_identification`` (#1107 Task 2).

Forms owns disguise data (``DisguiseKind``/``ConcealmentLevel``/``CharacterFormState``), so this
module lives here; it reads ``scenes`` (``Persona``/``active_persona_for_sheet``) and
``relationships`` (``CharacterRelationship``) read-only, per the FK-direction tenet (ADR-0010) —
those are the general primitives forms depends on, not the reverse. Imports of those apps are
lazy (function-local) to avoid a forms<->scenes import cycle at module load, matching
``world.forms.services.get_presented_appearance``'s existing convention.

All magnitudes below are PLACEHOLDER (pending playtest tuning), mirroring the tagging convention
in ``world.seeds.social_actions``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.forms.models import ConcealmentLevel, DisguiseKind
from world.forms.types import IdentificationOdds
from world.scenes.action_constants import DIFFICULTY_VALUES, DifficultyChoice
from world.societies.constants import FameTier

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet

# --- Baseline difficulty (#1107 slice 5) — PLACEHOLDER magnitudes -----------------------------
#
# Anchored to the shared DIFFICULTY_VALUES tier scale (world.scenes.action_constants) so
# Identification reads on the same Trivial..Harrowing ladder players see on every other check.
# MAGICAL x FULL deliberately sits ABOVE Harrowing: a fully-concealing magical illusion against a
# total stranger is meant to be unbeatable by this check alone (the illusion-piercing contest —
# perception vs. disguise / dispel — is the senior dev's domain, #1110 slice 3); familiarity/fame
# eases are what make an Identification attempt against it winnable at all.
_TRIVIAL = DIFFICULTY_VALUES[DifficultyChoice.TRIVIAL]
_EASY = DIFFICULTY_VALUES[DifficultyChoice.EASY]
_NORMAL = DIFFICULTY_VALUES[DifficultyChoice.NORMAL]
_HARD = DIFFICULTY_VALUES[DifficultyChoice.HARD]
_DAUNTING = DIFFICULTY_VALUES[DifficultyChoice.DAUNTING]
_HARROWING = DIFFICULTY_VALUES[DifficultyChoice.HARROWING]

_BASELINE_BY_KIND_AND_LEVEL: dict[tuple[str, str], int] = {
    (DisguiseKind.MUNDANE, ConcealmentLevel.NONE): _EASY,
    (DisguiseKind.MUNDANE, ConcealmentLevel.DESCRIPTOR): _NORMAL,
    (DisguiseKind.MUNDANE, ConcealmentLevel.FULL): _HARD,
    (DisguiseKind.MAGICAL, ConcealmentLevel.NONE): _NORMAL,
    (DisguiseKind.MAGICAL, ConcealmentLevel.DESCRIPTOR): _DAUNTING,
    (DisguiseKind.MAGICAL, ConcealmentLevel.FULL): _HARROWING + 10,  # past Harrowing on purpose
}

# A name-only mask (a TEMPORARY fake-name Persona with no physical overlay, #1127) — the wearer's
# face/body is unchanged, so a familiar glance can catch it. The easiest applicable band.
_MASK_FLOOR_DIFFICULTY = _TRIVIAL

# Familiarity eases — subtracted from the baseline (Decision 2). Both apply and stack when both
# are true (an active relationship with a now-famous person eases on both counts).
_ACTIVE_RELATIONSHIP_EASE = 20  # "I know this person" — a large, flat ease.
_FAME_TIER_EASE: dict[str, int] = {
    FameTier.NORMAL: 0,
    FameTier.TALKED_ABOUT: 5,
    FameTier.CELEBRITY: 10,
    FameTier.HOUSEHOLD_NAME: 15,
    FameTier.WORLD_FAMOUS: 20,
}

# The ease a *correct* named guess applies (Decision 3) — exposed on IdentificationOdds but
# applied only by attempt_identification (#1107 Task 2), which alone knows the guess.
_GUESS_CORRECT_EASE = 15

# Past this many points beyond Harrowing (the hardest authored tier), Identification is
# unrollable — auto-fail rather than waste a roll (Decision 4).
AUTO_FAIL_GAP = 10
_AUTO_FAIL_THRESHOLD = _HARROWING + AUTO_FAIL_GAP


def _presents_fake_name(target_character) -> bool:
    """Whether the target's currently active persona is a fake-name mask (no overlay needed)."""
    from world.scenes.models import Persona  # noqa: PLC0415
    from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415

    sheet = getattr(target_character, "sheet_data", None)  # noqa: GETATTR_LITERAL
    if sheet is None:
        return False
    try:
        persona = active_persona_for_sheet(sheet)
    except Persona.DoesNotExist:
        return False
    return persona.is_fake_name


def _baseline_difficulty(target_character) -> int | None:
    """The target's presentation baseline, or ``None`` when there's nothing to identify."""
    form_state = getattr(target_character, "form_state", None)  # noqa: GETATTR_LITERAL
    if form_state is not None and form_state.active_fake_overlay_id is not None:
        overlay = form_state.active_fake_overlay
        return _BASELINE_BY_KIND_AND_LEVEL[(form_state.overlay_kind, overlay.concealment_level)]
    if _presents_fake_name(target_character):
        return _MASK_FLOOR_DIFFICULTY
    return None


def _relationship_ease(viewer_sheet: CharacterSheet, target_sheet: CharacterSheet) -> int:
    """Ease from an active CharacterRelationship the viewer holds toward the true sheet."""
    from world.relationships.models import CharacterRelationship  # noqa: PLC0415

    holds_relationship = CharacterRelationship.objects.filter(
        source=viewer_sheet, target=target_sheet, is_active=True
    ).exists()
    return _ACTIVE_RELATIONSHIP_EASE if holds_relationship else 0


def _fame_ease(target_sheet: CharacterSheet) -> int:
    """Ease from the target's TRUE (PRIMARY) persona's fame_tier — famous faces are recognized
    even under a mask, regardless of which persona is currently active."""
    from world.scenes.models import Persona  # noqa: PLC0415

    try:
        true_persona = target_sheet.primary_persona
    except Persona.DoesNotExist:
        return 0
    return _FAME_TIER_EASE[true_persona.fame_tier]


def identification_difficulty(viewer_sheet: CharacterSheet, target_character) -> IdentificationOdds:
    """The Identification check's target difficulty for ``viewer_sheet`` vs. ``target_character``.

    Baseline comes from what the target is actively presenting (checked in this order):

    1. An active fake overlay (#1110) — keyed by ``DisguiseKind`` x ``ConcealmentLevel``.
    2. A name-only TEMPORARY mask persona with no overlay — the flat "mask floor".
    3. Neither — ``IdentificationOdds(applicable=False, ...)``: nothing to identify.

    Familiarity eases the baseline (Decision 2, both stack): an active ``CharacterRelationship``
    the viewer holds toward the sheet under the mask, and the ``fame_tier`` of the target's TRUE
    (PRIMARY) persona. ``guess_ease`` is exposed, not applied — a caller subtracts it only when a
    named guess is correct (Decision 3). ``auto_fail=True`` once the post-familiarity difficulty
    is past ``AUTO_FAIL_GAP`` beyond Harrowing — a gap no roll can close (Decision 4).
    """
    baseline = _baseline_difficulty(target_character)
    if baseline is None:
        return IdentificationOdds(
            applicable=False,
            difficulty=0,
            auto_fail=False,
            baseline=0,
            familiarity_ease=0,
            guess_ease=0,
        )

    target_sheet = getattr(target_character, "sheet_data", None)  # noqa: GETATTR_LITERAL
    familiarity_ease = 0
    if target_sheet is not None:
        familiarity_ease += _relationship_ease(viewer_sheet, target_sheet)
        familiarity_ease += _fame_ease(target_sheet)

    raw = baseline - familiarity_ease
    return IdentificationOdds(
        applicable=True,
        difficulty=max(0, raw),
        auto_fail=raw >= _AUTO_FAIL_THRESHOLD,
        baseline=baseline,
        familiarity_ease=familiarity_ease,
        guess_ease=_GUESS_CORRECT_EASE,
    )
