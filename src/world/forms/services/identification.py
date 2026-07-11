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
from world.forms.types import IdentificationOdds, IdentificationOutcome, IdentificationResult
from world.scenes.action_constants import DIFFICULTY_VALUES, DifficultyChoice
from world.societies.constants import FameTier

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.checks.types import CheckResult
    from world.scenes.models import Persona, PersonaDiscovery

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
# PLACEHOLDER combine rule: this module adds the two eases together. That's an implementer
# choice, not a spec mandate — contrast world.scenes.social_difficulty._exploitable_easing,
# which deliberately takes max() across its easing sources ("two exploitable conditions never
# stack"). Additive stacking here is unreviewed; revisit alongside the other PLACEHOLDER
# magnitudes during playtest tuning.
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

    Familiarity eases the baseline (Decision 2, both stack — PLACEHOLDER additive combine rule,
    see the comment above ``_ACTIVE_RELATIONSHIP_EASE``): an active ``CharacterRelationship``
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


# --- attempt_identification (#1107 Task 2) -----------------------------------------------------
#
# The check + PersonaDiscovery-write orchestrator. ``identification_difficulty`` above is pure
# computation (no roll, no write); this is where the roll happens and the ``PersonaDiscovery`` row
# gets written on success.

# The check-resolution spine's canonical "botch" threshold — mirrors
# world.magic.services.sanctum_install.CRITICAL_FAILURE_SUCCESS_LEVEL and world.combat.escalation's
# "<=-2 botch" convention: CheckOutcome.success_level at/below this is a Critical Failure (a botch),
# not a plain miss.
_BOTCH_SUCCESS_LEVEL = -2

# Player-facing copy. FAILURE and AUTO_FAIL deliberately share the exact same string (the oracle
# rule — a player must never be able to tell "you rolled and missed" apart from "this was never
# rollable"); see IdentificationResult.player_message and the dedicated indistinguishability test.
_FAILURE_MESSAGE = "You can't place who's really underneath — nothing about them gives it away."
_ALREADY_KNOWN_MESSAGE = "You already know exactly who this is."


def _success_message(true_name: str) -> str:
    return f"It clicks — that's unmistakably {true_name}."


def _botch_message(functionary_name: str) -> str:
    return f"You'd swear that's {functionary_name}... but you're wrong."


def _failure_result() -> IdentificationResult:
    return IdentificationResult(
        outcome=IdentificationOutcome.FAILURE, player_message=_FAILURE_MESSAGE
    )


def _auto_fail_result() -> IdentificationResult:
    return IdentificationResult(
        outcome=IdentificationOutcome.AUTO_FAIL, player_message=_FAILURE_MESSAGE
    )


def _already_known_result(
    existing: PersonaDiscovery, true_persona: Persona | None
) -> IdentificationResult:
    return IdentificationResult(
        outcome=IdentificationOutcome.ALREADY_KNOWN,
        revealed_name=true_persona.name if true_persona is not None else "",
        persona_discovery=existing,
        player_message=_ALREADY_KNOWN_MESSAGE,
    )


def _target_persona_pair(target_character) -> tuple[Persona | None, Persona | None]:
    """(presented, true) persona pair for ``target_character`` — what the viewer currently
    perceives them as, vs. who they really are (the TRUE/PRIMARY persona).

    ``(None, None)`` when the target has no ``CharacterSheet`` or is somehow missing its PRIMARY
    persona (a broken invariant elsewhere — ``attempt_identification`` degrades to a plain
    failure rather than propagate the crash into a check-resolution seam).
    """
    from world.scenes.models import Persona  # noqa: PLC0415
    from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415

    target_sheet = getattr(target_character, "sheet_data", None)  # noqa: GETATTR_LITERAL
    if target_sheet is None:
        return None, None
    try:
        presented = active_persona_for_sheet(target_sheet)
        true_persona = target_sheet.primary_persona
    except Persona.DoesNotExist:
        return None, None
    return presented, true_persona


def _target_difficulty(
    odds: IdentificationOdds, guess_name: str | None, true_persona: Persona | None
) -> int:
    """``odds.difficulty``, eased by ``odds.guess_ease`` when ``guess_name`` case-insensitively
    names the target's TRUE persona (Decision 3). Clamped at 0."""
    guess_correct = (
        guess_name is not None
        and true_persona is not None
        and guess_name.strip().casefold() == true_persona.name.strip().casefold()
    )
    return max(0, odds.difficulty - (odds.guess_ease if guess_correct else 0))


def _roll_outcome_result(
    result: CheckResult,
    presented_persona: Persona | None,
    true_persona: Persona | None,
    viewer_sheet: CharacterSheet,
) -> IdentificationResult:
    """SUCCESS / BOTCH_FAKE_ID / FAILURE from a resolved ``perform_check`` ``CheckResult``.

    SUCCESS writes (idempotently) the ``PersonaDiscovery`` row; a botch
    (``success_level <= _BOTCH_SUCCESS_LEVEL``) fake-IDs a random active Functionary — never a PC
    (the spec's oracle rule) — degrading to a plain ``FAILURE`` when none exists to blame.
    """
    from world.npc_services.functionaries import random_active_functionary  # noqa: PLC0415
    from world.scenes.services import record_persona_discovery  # noqa: PLC0415

    if result.success_level > 0:
        discovery = record_persona_discovery(presented_persona, true_persona, viewer_sheet)
        revealed = true_persona.name if true_persona is not None else ""
        return IdentificationResult(
            outcome=IdentificationOutcome.SUCCESS,
            revealed_name=revealed,
            persona_discovery=discovery,
            player_message=_success_message(revealed),
        )
    if result.success_level <= _BOTCH_SUCCESS_LEVEL:
        functionary = random_active_functionary()
        if functionary is not None:
            return IdentificationResult(
                outcome=IdentificationOutcome.BOTCH_FAKE_ID,
                revealed_name=functionary.display_name,
                player_message=_botch_message(functionary.display_name),
            )
    return _failure_result()


def attempt_identification(
    viewer_character, target_character, guess_name: str | None = None
) -> IdentificationResult:
    """Roll an Identification check for ``viewer_character`` against ``target_character`` (#1107
    Task 2), writing a ``PersonaDiscovery`` row on success.

    Short-circuits BEFORE rolling in three cases:

    - ``ALREADY_KNOWN`` — the viewer already holds a ``PersonaDiscovery`` linking the target's
      currently-presented persona to their TRUE (PRIMARY) persona.
    - a target with nothing to identify (``odds.applicable is False``) degrades to ``FAILURE`` —
      a defensive fallback; ``IdentifyAction``'s prerequisites (#1107 Task 3) are the intended
      gate that keeps a caller from reaching this at all in that case.
    - ``AUTO_FAIL`` — ``identification_difficulty`` says the gap is unrollable (Decision 4); no
      roll is wasted, and this is player-indistinguishable from a plain ``FAILURE``.

    Otherwise rolls ``perform_check`` against the seeded Identification ``CheckType``, easing the
    target difficulty when ``guess_name`` correctly names the target's TRUE persona (Decision 3,
    see ``_target_difficulty``), and resolves SUCCESS/BOTCH_FAKE_ID/FAILURE from the roll (see
    ``_roll_outcome_result``). SUCCESS writes the ``PersonaDiscovery`` via
    ``world.scenes.services.record_persona_discovery`` — the same writer
    ``world.clues.services`` uses for GM-authored piercing (#2120), so the pair-normalization
    logic isn't duplicated.
    """
    from world.checks.models import CheckType  # noqa: PLC0415
    from world.checks.services import perform_check  # noqa: PLC0415
    from world.forms.constants import IDENTIFICATION_CHECK_TYPE_NAME  # noqa: PLC0415
    from world.scenes.services import persona_discovery_between  # noqa: PLC0415

    viewer_sheet = getattr(viewer_character, "sheet_data", None)  # noqa: GETATTR_LITERAL
    if viewer_sheet is None:
        return _failure_result()

    presented_persona, true_persona = _target_persona_pair(target_character)

    existing = persona_discovery_between(presented_persona, true_persona, viewer_sheet)
    if existing is not None:
        return _already_known_result(existing, true_persona)

    odds = identification_difficulty(viewer_sheet, target_character)
    if not odds.applicable:
        return _failure_result()
    if odds.auto_fail:
        return _auto_fail_result()

    target_difficulty = _target_difficulty(odds, guess_name, true_persona)
    check_type = CheckType.objects.get(name=IDENTIFICATION_CHECK_TYPE_NAME)
    result = perform_check(viewer_character, check_type, target_difficulty=target_difficulty)

    return _roll_outcome_result(result, presented_persona, true_persona, viewer_sheet)
