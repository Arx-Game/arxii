"""Resolve a player-typed thread among the character's own (#5123).

One lookup for every verb that names a thread: ``imbue thread=``, ``cast ... pull=`` and
whatever follows. A thread is found by its own name, else by its anchor's name (a Gift
thread is minted with no name, so it answers to its Gift's name), else by its number. The
``threads`` verb prints the name a player can type with ``thread_label``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from commands.exceptions import CommandError

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.magic.models import Thread
    from world.relationships.models import RelationshipLabel

# What reading a thread's anchor label touches, so listing the labels costs no query per thread.
THREAD_LABEL_RELATED = (
    "resonance",
    "target_trait",
    "target_facet",
    "target_gift",
    "target_technique",
    "target_mantle",
    "target_relationship__target__character",
    "target_relationship__target_companion",
    "target_capstone__relationship__target__character",
    "target_capstone__relationship__target_companion",
    "target_sanctum_details__feature_instance__room_profile__objectdb",
)


def active_threads(sheet: CharacterSheet) -> list[Thread]:
    """The character's live threads, with everything their labels read loaded."""
    from world.magic.models import Thread  # noqa: PLC0415

    return list(
        Thread.objects.filter(owner=sheet, retired_at__isnull=True).select_related(
            *THREAD_LABEL_RELATED
        )
    )


def open_labels_for(threads: list[Thread]) -> dict[int, RelationshipLabel]:
    """The open relationship label of each relationship thread, read in one batch."""
    from world.magic.crossing.handlers import open_labels_by_relationship_id  # noqa: PLC0415

    return open_labels_by_relationship_id(threads)


def anchor_labels(threads: list[Thread]) -> dict[int, str]:
    """Each thread's anchor label (a Gift thread's is its Gift's name), keyed by thread id."""
    from world.magic.crossing.handlers import anchor_label_for  # noqa: PLC0415

    open_labels = open_labels_for(threads)
    return {t.pk: anchor_label_for(t, open_labels) for t in threads}


def _names_of(thread: Thread, anchor: str) -> set[str]:
    """The names (lowercase) a thread answers to: its own and its anchor's."""
    own = thread.name.strip().lower()
    return {anchor.lower(), own} - {""}


def shared_name_pks(threads: list[Thread], anchors: dict[int, str]) -> set[int]:
    """Ids of the threads that share a name with another thread.

    Those can be reached by number only, so ``threads`` prints the number for them.
    """
    owners: dict[str, set[int]] = {}
    for thread in threads:
        for name in _names_of(thread, anchors[thread.pk]):
            owners.setdefault(name, set()).add(thread.pk)
    return {pk for pks in owners.values() if len(pks) > 1 for pk in pks}


def thread_label(thread: Thread, anchor: str, *, show_number: bool = False) -> str:
    """The thread as ``threads`` lists it: its own name with its anchor, else the anchor.

    Both parts are names the thread answers to. ``show_number`` adds the number, for a
    thread whose names another thread shares (``shared_name_pks``): the number always
    reaches it.
    """
    name = thread.name.strip()
    label = f"{name} ({anchor})" if name and name.lower() != anchor.lower() else anchor
    return f"{label} [number {thread.pk}]" if show_number else label


def find_thread(sheet: CharacterSheet, typed: str) -> Thread | None:
    """The live thread of ``sheet`` that ``typed`` names, or None when none does.

    A number is the thread's id. Otherwise a thread matches by its own name or its
    anchor's name (any case).

    Raises:
        CommandError: The name fits more than one thread, whether by own names, anchor
            names or one thread's own name and another's anchor; the refusal lists each
            with its number, which always resolves.
    """
    typed = typed.strip()
    threads = active_threads(sheet)
    if typed.isdigit():
        return next((t for t in threads if t.pk == int(typed)), None)
    wanted = typed.lower()
    anchors = anchor_labels(threads)
    matches = [t for t in threads if wanted in _names_of(t, anchors[t.pk])]
    if len(matches) > 1:
        described = "; ".join(
            f"number {t.pk} is {t.resonance.name} {thread_label(t, anchors[t.pk])}, level {t.level}"
            for t in matches
        )
        msg = f"More than one thread answers to '{typed}': {described}. Use the number."
        raise CommandError(msg)
    return matches[0] if matches else None


def resolve_thread(sheet: CharacterSheet, typed: str, *, not_found_msg: str) -> Thread:
    """``find_thread``, refusing with ``not_found_msg`` when nothing matches."""
    thread = find_thread(sheet, typed)
    if thread is None:
        raise CommandError(not_found_msg)
    return thread
