"""Reflections (#5124): a pose or a journal entry that says what it reflects on.

A reflection names one thing: a deed the character has not reflected on (a kindled deed, or
having succumbed to the Mire), the resonance that is unsettling them, or the Mire a Sineater
carries for one Sinner (a burden, #5177). A deed or the unsettling resonance is Embraced or
Disowned; a burden is Absolved, Condemned or Succumbed to. Recording one changes nothing in
the aura: the rite of settling carries every waiting reflection out later.

``reflectable_for`` is the one read the web composer and the telnet ``reflect`` listing share,
``resolve_reflection_target`` names what a player typed, and ``record_reflection`` writes the
row. A pose or entry that carries a reflection validates it first (``resolve_reflection_target``
or ``validate_reflection``), posts, then records, so a refused reflection never costs the
writing.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.db import IntegrityError, transaction

from world.magic.constants import (
    BURDEN_REFLECTION_CHOICES,
    DEED_REFLECTION_CHOICES,
    GainSource,
    ReflectionChoice,
    ReflectionTargetKind,
)
from world.magic.exceptions import (
    DeedAlreadyReflectedError,
    NotABurdenError,
    ReflectionError,
    ResonanceNotUnsettlingError,
)
from world.magic.models import Reflection, Resonance, ResonanceGrant
from world.magic.services.drift import drift_for
from world.magic.services.kindling import situation_reason
from world.magic.types.reflection import (
    PendingReflection,
    Reflectable,
    ReflectableBurden,
    ReflectableDeed,
    ReflectionTarget,
    burden_label,
    unsettling_label,
)
from world.relationships.models import CharacterRelationship

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.journals.models import JournalEntry
    from world.scenes.models import Interaction

_NO_TARGET = "Name a deed, the resonance that is unsettling you, or the Mire you carry."
_NOT_A_DEED = "That is not a deed you can reflect on."
_CHOICES = {choice.lower(): choice for choice in ReflectionChoice.values}
_BAD_CHOICE = "Say whether you embrace or disown it."
_BAD_BURDEN_CHOICE = "Say whether you absolve, condemn or succumb to it."
# The deeds a player can reflect on: a kindled deed, a gain marked on an act (#5327), or having
# succumbed to the Mire (#5177).
_REFLECTABLE_DEED_SOURCES = (
    GainSource.KINDLED_DEED,
    GainSource.MARKED_ACT,
    GainSource.SUCCUMBED,
)
# The literal a player types before a Sinner's name to name the Mire they carry for them.
BURDEN_PREFIX = "mire:"
_VERB = {
    ReflectionChoice.ABSOLVE: "absolve",
    ReflectionChoice.CONDEMN: "condemn",
    ReflectionChoice.SUCCUMB: "succumb to",
}


def choices_for(kind: ReflectionTargetKind) -> tuple[str, ...]:
    """The choices a reflection on ``kind`` takes: three for a burden, else Embrace or Disown."""
    if kind == ReflectionTargetKind.BURDEN:
        return BURDEN_REFLECTION_CHOICES
    return DEED_REFLECTION_CHOICES


def _bad_choice_line(kind: ReflectionTargetKind | None) -> str:
    return _BAD_BURDEN_CHOICE if kind == ReflectionTargetKind.BURDEN else _BAD_CHOICE


def _name(sheet: CharacterSheet) -> str:
    return sheet.primary_persona.name


def unsettling_resonance(sheet: CharacterSheet | None) -> Resonance | None:
    """The resonance that is unsettling ``sheet``, or None when they are settled (#5123).

    None too for no sheet at all: a character without one is not unsettled by anything.
    """
    if sheet is None:
        return None
    reading = drift_for(sheet)
    return reading.leading_excess_resonance if reading.steps_past > 0 else None


def reflection_where(reflection: Reflection) -> str:
    """Where a reflection was written, as a clause: "in your journal entry of 12 March", "in
    your pose at the Lower Docks" (the pose's place, else its room, else its scene), or "in
    your pose" when no more is known. Blank when the writing left no row to name (a pose in an
    ephemeral scene) (#5177)."""
    entry = reflection.journal_entry
    if entry is not None:
        return f"in your journal entry of {entry.created_at:%-d %B}"
    pose = reflection.interaction
    if pose is None:
        return ""
    if pose.place is not None:
        return f"in your pose at {pose.place.name}"
    scene = pose.scene
    if scene is None:
        return "in your pose"
    room = scene.room
    return f"in your pose at {room.db_key if room is not None else scene.name}"


def _succumbed_what(grant: ResonanceGrant) -> str:
    """What a SUCCUMBED grant was, from the burden reflection it carries (#5177)."""
    reflection = grant.source_reflection
    if reflection is None or reflection.tether is None:
        return "succumbing to the Mire you carried"
    what = f"succumbing to the Mire you carried for {_name(reflection.tether.target)}"
    where = reflection_where(reflection)
    return f"{what}, {where}" if where else what


def deed_what(grant: ResonanceGrant) -> str:
    """What the character did, in her own words.

    The act's label recorded on the grant when it was earned; a grant with none falls back to
    the reason the "Your resonances" panel gives for the situation (``situation_reason``),
    never the situation's type name. Succumbing to the Mire is worded from the burden
    reflection that caused it, naming the Sinner and where it was written (#5177).
    """
    if grant.source == GainSource.SUCCUMBED:
        return _succumbed_what(grant)
    if grant.deed_label:
        return grant.deed_label
    situation = grant.source_kindling_situation
    return situation_reason(situation) if situation is not None else ""


# Words a reason sentence opens with when the opener is not a name ("This mission is about ...").
_COMMON_OPENERS = frozenset(
    {
        "a",
        "an",
        "the",
        "this",
        "that",
        "these",
        "those",
        "your",
        "you",
        "he",
        "she",
        "they",
        "it",
        "we",
        "there",
        "someone",
        "somebody",
        "something",
        "people",
        "everyone",
        "anyone",
        "no",
        "some",
        "any",
        "every",
        "each",
        "all",
    }
)


def deed_in_sentence(grant: ResonanceGrant) -> str:
    """The deed, worded to sit inside another sentence ("Your X from <this> grows").

    A recorded label is the act as authored and stays as it is. The fallback reason is a
    sentence of its own, so its closing full stop goes and its first letter is lowered, unless
    it opens on a name ("Tomas Reeve is here") rather than a common word ("This mission is about
    ..."). Blank when the grant names nothing.
    """
    if grant.source != GainSource.SUCCUMBED and grant.deed_label:
        return grant.deed_label
    text = deed_what(grant).strip().rstrip(".").rstrip()
    if not text:
        return ""
    first = text.split(maxsplit=1)[0]
    return text[0].lower() + text[1:] if first.lower() in _COMMON_OPENERS else text


def deed_label(grant: ResonanceGrant) -> str:
    """The line a player reads for a deed: what held, then what it earned."""
    earned = f"{grant.amount} {grant.resonance.name}"
    what = deed_what(grant)
    if grant.source == GainSource.SUCCUMBED:
        what = what[:1].upper() + what[1:]
    return f"{what} · {earned}" if what else earned


def recorded_line(reflection: Reflection) -> str:
    """The line the writer reads once a reflection is recorded (no one else is told)."""
    if reflection.tether is not None:
        on = f"the Mire you carry for {_name(reflection.tether.target)}"
        verb = _VERB[reflection.choice]
        return (
            f"Your reflection on {on} is recorded: you will {verb} it. "
            "It waits with your other reflections for the rite of settling."
        )
    if reflection.grant is not None:
        on = deed_in_sentence(reflection.grant) or f"your {reflection.grant.resonance.name}"
    else:
        on = f"your {reflection.resonance.name}"
    return (
        f"Your reflection on {on} is recorded. "
        "It waits with your other reflections for the rite of settling."
    )


# What ``deed_what`` reads off a SUCCUMBED grant: the burden reflection, its Sinner, and the
# writing it was written in.
SUCCUMBED_WHAT_RELATED = (
    "source_reflection__tether__target",
    "source_reflection__journal_entry",
    "source_reflection__interaction__place",
    "source_reflection__interaction__scene__location__objectdb",
)


def _unreflected_deeds(sheet: CharacterSheet) -> list[ResonanceGrant]:
    """Deed grants on ``sheet`` (kindled, marked, or succumbing to the Mire) with no reflection
    yet, newest first. A grant a GM or staff undid (#5327) is no longer a deed."""
    return list(
        ResonanceGrant.objects.filter(
            character_sheet=sheet,
            source__in=_REFLECTABLE_DEED_SOURCES,
            reflections__isnull=True,
            nullified_at__isnull=True,
        )
        .select_related("resonance", "source_kindling_situation", *SUCCUMBED_WHAT_RELATED)
        .order_by("-granted_at", "-pk")
    )


def _waiting_on(sheet: CharacterSheet, resonance: Resonance) -> bool:
    return Reflection.objects.filter(
        character_sheet=sheet, resonance=resonance, rite__isnull=True
    ).exists()


def _held_tethers(sheet: CharacterSheet) -> list[CharacterRelationship]:
    """The Sineater's own sides of the tethers on which ``sheet`` holds any Mire (#5177)."""
    return list(
        CharacterRelationship.objects.filter(source=sheet, mire_holdings__amount__gt=0)
        .select_related("target")
        .distinct()
        .order_by("pk")
    )


def _burdens(sheet: CharacterSheet) -> tuple[ReflectableBurden, ...]:
    """One burden per tether on which ``sheet`` carries any Mire, with whether one waits."""
    tethers = _held_tethers(sheet)
    if not tethers:
        return ()
    waiting = set(
        Reflection.objects.filter(
            character_sheet=sheet, tether__in=tethers, rite__isnull=True
        ).values_list("tether_id", flat=True)
    )
    return tuple(
        ReflectableBurden(
            tether=tether,
            label=burden_label(_name(tether.target)),
            has_waiting=tether.pk in waiting,
        )
        for tether in tethers
    )


def reflectable_for(sheet: CharacterSheet | None) -> Reflectable:
    """What ``sheet`` can reflect on now: their unreflected deeds (kindled, or succumbing to
    the Mire), the unsettling resonance (None when settled), and the Mire they carry for each
    Sinner."""
    if sheet is None:
        return Reflectable(deeds=(), unsettling=None)
    unsettling = unsettling_resonance(sheet)
    return Reflectable(
        deeds=tuple(
            ReflectableDeed(grant=g, label=deed_label(g)) for g in _unreflected_deeds(sheet)
        ),
        unsettling=unsettling,
        unsettling_has_waiting=unsettling is not None and _waiting_on(sheet, unsettling),
        burdens=_burdens(sheet),
    )


def parse_reflection_choice(text: str, target: ReflectionTarget | None = None) -> str:
    """A choice word (any case) as a ``ReflectionChoice`` value that fits ``target``.

    With no ``target`` any choice is accepted. Embrace and Disown fit a deed or the unsettling
    resonance; Absolve, Condemn and Succumb fit only a burden.

    Raises:
        ReflectionError: The word is not a choice, or does not fit ``target``.
    """
    choice = _CHOICES.get(text.strip().lower())
    kind = target.kind if target is not None else None
    if choice is None or (kind is not None and choice not in choices_for(kind)):
        raise ReflectionError(_bad_choice_line(kind))
    return choice


def validate_reflection(
    sheet: CharacterSheet,
    *,
    grant_id: int | None = None,
    resonance_id: int | None = None,
    tether_id: int | None = None,
) -> ReflectionTarget:
    """Check a reflection's target before any writing is posted.

    Exactly one of ``grant_id``, ``resonance_id`` or ``tether_id``. A deed must be a kindled,
    marked or succumbed-to-the-Mire grant on ``sheet`` that was not undone and has no
    reflection yet; a resonance must be the
    one unsettling ``sheet`` now; a tether must be ``sheet``'s own side as a Sineater, on which
    they hold some Mire.

    Raises:
        DeedAlreadyReflectedError: The deed already carries a reflection.
        ResonanceNotUnsettlingError: The resonance is not the one unsettling ``sheet``.
        NotABurdenError: The tether is not one ``sheet`` holds Mire on.
        ReflectionError: No target, two targets, or not a deed of this character's.
    """
    if sum(value is not None for value in (grant_id, resonance_id, tether_id)) != 1:
        raise ReflectionError(_NO_TARGET)
    if tether_id is not None:
        tether = next((t for t in _held_tethers(sheet) if t.pk == tether_id), None)
        if tether is None:
            raise NotABurdenError
        return ReflectionTarget(tether=tether)
    if grant_id is not None:
        grant = (
            ResonanceGrant.objects.filter(
                pk=grant_id,
                character_sheet=sheet,
                source__in=_REFLECTABLE_DEED_SOURCES,
                nullified_at__isnull=True,
            )
            .select_related("resonance", "source_kindling_situation", *SUCCUMBED_WHAT_RELATED)
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
    """Name what a player typed: a deed's number from the ``reflect`` list, the name of the
    resonance unsettling them, or ``mire:<Sinner's name>`` for the Mire they carry for a Sinner.

    Raises:
        ReflectionError: Nothing the player can reflect on matches ``token``.
    """
    text = token.strip().lstrip("#")
    if not text:
        raise ReflectionError(_NO_TARGET)
    if text.lower().startswith(BURDEN_PREFIX):
        return _resolve_burden(sheet, text[len(BURDEN_PREFIX) :].strip())
    if text.isdigit():
        return validate_reflection(sheet, grant_id=int(text))
    unsettling = unsettling_resonance(sheet)
    if unsettling is None:
        raise ResonanceNotUnsettlingError
    if unsettling.name.lower() != text.lower():
        msg = f"'{token.strip()}' is not a deed or what is unsettling you."
        raise ReflectionError(msg)
    return ReflectionTarget(resonance=unsettling)


def _resolve_burden(sheet: CharacterSheet, name: str) -> ReflectionTarget:
    """The burden for the Sinner called ``name`` (any case), among the Mire ``sheet`` carries."""
    for tether in _held_tethers(sheet):
        if _name(tether.target).lower() == name.lower():
            return ReflectionTarget(tether=tether)
    msg = f"You carry no Mire for '{name}'."
    raise NotABurdenError(msg)


def record_reflection(  # noqa: PLR0913 - the writing, one of three targets, and the choice
    sheet: CharacterSheet,
    *,
    writing: Interaction | JournalEntry | None,
    grant: ResonanceGrant | None = None,
    resonance: Resonance | None = None,
    tether: CharacterRelationship | None = None,
    choice: str,
) -> Reflection:
    """Record that ``writing`` reflects on a deed, the unsettling resonance or a burden.

    The target is checked again here (see ``validate_reflection``), and so is that ``choice``
    fits it. A newer reflection on a resonance or a burden replaces any older one still
    waiting on it. ``writing`` is None only when a
    pose was spoken in an ephemeral scene, which keeps no row to link: the reflection is
    still recorded.

    Raises:
        DeedAlreadyReflectedError: The deed already carries a reflection.
        ResonanceNotUnsettlingError: The resonance is not the one unsettling ``sheet``.
        NotABurdenError: The tether is not one ``sheet`` holds Mire on.
        ReflectionError: No target, two targets, or a choice that does not fit the target.
    """
    from world.journals.models import JournalEntry  # noqa: PLC0415

    target = validate_reflection(
        sheet,
        grant_id=grant.pk if grant is not None else None,
        resonance_id=resonance.pk if resonance is not None else None,
        tether_id=tether.pk if tether is not None else None,
    )
    if choice not in choices_for(target.kind):
        raise ReflectionError(_bad_choice_line(target.kind))
    links = {}
    if isinstance(writing, JournalEntry):
        links["journal_entry"] = writing
    elif writing is not None:
        links["interaction"] = writing
    try:
        with transaction.atomic():
            if target.resonance is not None or target.tether is not None:
                for older in list(
                    Reflection.objects.filter(
                        character_sheet=sheet,
                        resonance=target.resonance,
                        tether=target.tether,
                        rite__isnull=True,
                    )
                ):
                    older.delete()
            return Reflection.objects.create(
                character_sheet=sheet,
                choice=choice,
                grant=target.grant,
                resonance=target.resonance,
                tether=target.tether,
                **links,
            )
    except IntegrityError:
        # Two posts raced for the same deed; the unique constraint kept one.
        raise DeedAlreadyReflectedError from None


def pending_reflection_from(sheet: CharacterSheet, params: Any) -> PendingReflection | None:
    """The reflection a pose or entry asked for, checked, or None when it asked for none.

    ``params`` is the action's kwargs or a serializer's validated data: ``reflect_choice``
    (any case; ``EMBRACE`` or ``DISOWN`` for a deed or the unsettling resonance, ``ABSOLVE``,
    ``CONDEMN`` or ``SUCCUMB`` for a burden) with exactly one of ``reflect_grant_id``,
    ``reflect_resonance_id`` or ``reflect_tether_id`` (the id of the Sineater's relationship
    side, which a burden option carries). Absent or empty means no reflection.

    Raises:
        ReflectionError: The choice is missing or does not fit the target, or the target
            fails ``validate_reflection``.
    """
    choice = params.get("reflect_choice")
    grant_id = params.get("reflect_grant_id")
    resonance_id = params.get("reflect_resonance_id")
    tether_id = params.get("reflect_tether_id")
    if not choice and grant_id is None and resonance_id is None and tether_id is None:
        return None
    target = validate_reflection(
        sheet, grant_id=grant_id, resonance_id=resonance_id, tether_id=tether_id
    )
    return PendingReflection(target=target, choice=parse_reflection_choice(choice or "", target))


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
        tether=pending.target.tether,
        choice=pending.choice,
    )


__all__ = [
    "BURDEN_PREFIX",
    "SUCCUMBED_WHAT_RELATED",
    "choices_for",
    "deed_in_sentence",
    "deed_label",
    "deed_what",
    "parse_reflection_choice",
    "pending_reflection_from",
    "record_pending_reflection",
    "record_reflection",
    "recorded_line",
    "reflectable_for",
    "reflection_where",
    "resolve_reflection_target",
    "unsettling_label",
    "unsettling_resonance",
    "validate_reflection",
]
