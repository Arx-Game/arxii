"""Reflections (#5124): a pose or a journal entry that says what it reflects on.

A reflection names one thing, either a kindled deed the character has not reflected on or
the resonance that is unsettling them, and whether they Embrace or Disown it. Recording one
changes nothing in the aura: the rite of settling carries every waiting reflection out later.

``reflectable_for`` is the one read the web composer and the telnet ``reflect`` listing share,
``resolve_reflection_target`` names what a player typed, and ``record_reflection`` writes the
row. A pose or entry that carries a reflection validates it first (``resolve_reflection_target``
or ``validate_reflection``), posts, then records, so a refused reflection never costs the
writing.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.db import IntegrityError, transaction

from world.magic.constants import GainSource, ReflectionChoice
from world.magic.exceptions import (
    DeedAlreadyReflectedError,
    ReflectionError,
    ResonanceNotUnsettlingError,
)
from world.magic.models import Reflection, Resonance, ResonanceGrant
from world.magic.services.drift import drift_for
from world.magic.types.reflection import (
    PendingReflection,
    Reflectable,
    ReflectableDeed,
    ReflectionTarget,
    unsettling_label,
)

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.journals.models import JournalEntry
    from world.scenes.models import Interaction

_NO_TARGET = "Name a deed or the resonance that is unsettling you."
_NOT_A_DEED = "That is not a deed you can reflect on."
_CHOICES = {choice.lower(): choice for choice in ReflectionChoice.values}
_BAD_CHOICE = "Say whether you embrace or disown it."


def unsettling_resonance(sheet: CharacterSheet) -> Resonance | None:
    """The resonance that is unsettling ``sheet``, or None when they are settled (#5123)."""
    reading = drift_for(sheet)
    return reading.leading_excess_resonance if reading.steps_past > 0 else None


def _deed_what(grant: ResonanceGrant) -> str:
    """What held when the deed was done, in the words staff wrote for the situation."""
    situation = grant.source_kindling_situation
    if situation is None:
        return ""
    return situation.reason_text or situation.get_situation_display()


def deed_label(grant: ResonanceGrant) -> str:
    """The line a player reads for a deed: what held, then what it earned."""
    earned = f"{grant.amount} {grant.resonance.name}"
    what = _deed_what(grant)
    return f"{what} · {earned}" if what else earned


def recorded_line(reflection: Reflection) -> str:
    """The line the writer reads once a reflection is recorded (no one else is told)."""
    if reflection.grant is not None:
        on = _deed_what(reflection.grant) or f"your {reflection.grant.resonance.name}"
    else:
        on = f"your {reflection.resonance.name}"
    return (
        f"Your reflection on {on} is recorded. "
        "It waits with your other reflections for the rite of settling."
    )


def _unreflected_deeds(sheet: CharacterSheet) -> list[ResonanceGrant]:
    """Kindled-deed grants on ``sheet`` with no reflection yet, newest first."""
    return list(
        ResonanceGrant.objects.filter(
            character_sheet=sheet,
            source=GainSource.KINDLED_DEED,
            reflections__isnull=True,
        )
        .select_related("resonance", "source_kindling_situation")
        .order_by("-granted_at", "-pk")
    )


def _waiting_on(sheet: CharacterSheet, resonance: Resonance) -> bool:
    return Reflection.objects.filter(
        character_sheet=sheet, resonance=resonance, rite__isnull=True
    ).exists()


def reflectable_for(sheet: CharacterSheet) -> Reflectable:
    """What ``sheet`` can reflect on now: their unreflected kindled deeds and the unsettling
    resonance (None when settled)."""
    unsettling = unsettling_resonance(sheet)
    return Reflectable(
        deeds=tuple(
            ReflectableDeed(grant=g, label=deed_label(g)) for g in _unreflected_deeds(sheet)
        ),
        unsettling=unsettling,
        unsettling_has_waiting=unsettling is not None and _waiting_on(sheet, unsettling),
    )


def parse_reflection_choice(text: str) -> str:
    """``embrace`` or ``disown`` (any case) as a ``ReflectionChoice`` value.

    Raises:
        ReflectionError: The word is neither.
    """
    choice = _CHOICES.get(text.strip().lower())
    if choice is None:
        raise ReflectionError(_BAD_CHOICE)
    return choice


def validate_reflection(
    sheet: CharacterSheet, *, grant_id: int | None = None, resonance_id: int | None = None
) -> ReflectionTarget:
    """Check a reflection's target before any writing is posted.

    Exactly one of ``grant_id`` or ``resonance_id``. A deed must be a kindled-deed grant on
    ``sheet`` with no reflection yet; a resonance must be the one unsettling ``sheet`` now.

    Raises:
        DeedAlreadyReflectedError: The deed already carries a reflection.
        ResonanceNotUnsettlingError: The resonance is not the one unsettling ``sheet``.
        ReflectionError: No target, two targets, or not a deed of this character's.
    """
    if (grant_id is None) == (resonance_id is None):
        raise ReflectionError(_NO_TARGET)
    if grant_id is not None:
        grant = (
            ResonanceGrant.objects.filter(
                pk=grant_id, character_sheet=sheet, source=GainSource.KINDLED_DEED
            )
            .select_related("resonance", "source_kindling_situation")
            .first()
        )
        if grant is None:
            raise ReflectionError(_NOT_A_DEED)
        if Reflection.objects.filter(grant=grant).exists():
            raise DeedAlreadyReflectedError
        return ReflectionTarget(grant=grant)
    unsettling = unsettling_resonance(sheet)
    if unsettling is None or unsettling.pk != resonance_id:
        raise ResonanceNotUnsettlingError
    return ReflectionTarget(resonance=unsettling)


def resolve_reflection_target(sheet: CharacterSheet, token: str) -> ReflectionTarget:
    """Name what a player typed: a deed's number from the ``reflect`` list, or the name of the
    resonance unsettling them.

    Raises:
        ReflectionError: Nothing the player can reflect on matches ``token``.
    """
    text = token.strip().lstrip("#")
    if not text:
        raise ReflectionError(_NO_TARGET)
    if text.isdigit():
        return validate_reflection(sheet, grant_id=int(text))
    unsettling = unsettling_resonance(sheet)
    if unsettling is None:
        raise ResonanceNotUnsettlingError
    if unsettling.name.lower() != text.lower():
        msg = f"'{token.strip()}' is not a deed or what is unsettling you."
        raise ReflectionError(msg)
    return ReflectionTarget(resonance=unsettling)


def record_reflection(
    sheet: CharacterSheet,
    *,
    writing: Interaction | JournalEntry | None,
    grant: ResonanceGrant | None = None,
    resonance: Resonance | None = None,
    choice: str,
) -> Reflection:
    """Record that ``writing`` reflects on a deed or the unsettling resonance.

    The target is checked again here (see ``validate_reflection``). A newer reflection on a
    resonance replaces any older one still waiting on it. ``writing`` is None only when a
    pose was spoken in an ephemeral scene, which keeps no row to link: the reflection is
    still recorded.

    Raises:
        DeedAlreadyReflectedError: The deed already carries a reflection.
        ResonanceNotUnsettlingError: The resonance is not the one unsettling ``sheet``.
        ReflectionError: No target, two targets, or a choice that is neither.
    """
    from world.journals.models import JournalEntry  # noqa: PLC0415

    if choice not in ReflectionChoice.values:
        raise ReflectionError(_BAD_CHOICE)
    target = validate_reflection(
        sheet,
        grant_id=grant.pk if grant is not None else None,
        resonance_id=resonance.pk if resonance is not None else None,
    )
    links = {}
    if isinstance(writing, JournalEntry):
        links["journal_entry"] = writing
    elif writing is not None:
        links["interaction"] = writing
    try:
        with transaction.atomic():
            if target.resonance is not None:
                for older in list(
                    Reflection.objects.filter(
                        character_sheet=sheet, resonance=target.resonance, rite__isnull=True
                    )
                ):
                    older.delete()
            return Reflection.objects.create(
                character_sheet=sheet,
                choice=choice,
                grant=target.grant,
                resonance=target.resonance,
                **links,
            )
    except IntegrityError:
        # Two posts raced for the same deed; the unique constraint kept one.
        raise DeedAlreadyReflectedError from None


def pending_reflection_from(sheet: CharacterSheet, params: Any) -> PendingReflection | None:
    """The reflection a pose or entry asked for, checked, or None when it asked for none.

    ``params`` is the action's kwargs or a serializer's validated data: ``reflect_choice``
    (``EMBRACE`` or ``DISOWN``, any case) with exactly one of ``reflect_grant_id`` or
    ``reflect_resonance_id``. Absent or empty means no reflection.

    Raises:
        ReflectionError: The choice is missing or wrong, or the target fails
            ``validate_reflection``.
    """
    choice = params.get("reflect_choice")
    grant_id = params.get("reflect_grant_id")
    resonance_id = params.get("reflect_resonance_id")
    if not choice and grant_id is None and resonance_id is None:
        return None
    target = validate_reflection(sheet, grant_id=grant_id, resonance_id=resonance_id)
    return PendingReflection(target=target, choice=parse_reflection_choice(choice or ""))


def record_pending_reflection(
    sheet: CharacterSheet,
    pending: PendingReflection,
    *,
    writing: Interaction | JournalEntry | None,
) -> Reflection:
    """Record a ``pending_reflection_from`` result against the writing that carries it."""
    return record_reflection(
        sheet,
        writing=writing,
        grant=pending.target.grant,
        resonance=pending.target.resonance,
        choice=pending.choice,
    )


__all__ = [
    "deed_label",
    "parse_reflection_choice",
    "pending_reflection_from",
    "record_pending_reflection",
    "record_reflection",
    "recorded_line",
    "reflectable_for",
    "resolve_reflection_target",
    "unsettling_label",
    "unsettling_resonance",
    "validate_reflection",
]
