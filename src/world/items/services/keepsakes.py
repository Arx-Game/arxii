"""Declaring an item a keepsake (#4530, #4462 section 6.4).

A player marks an item they hold as standing for something in their character's life: a tie,
one of their own deeds, a being, an organization, a person or a place, with a few sentences
of their own and a choice to show them on examine. The game scores the **subject** (see
``world.items.services.meaning``), never the words. A keepsake counts after
``DevotionConfig.keepsake_wait_days``, a character holds at most
``keepsakes_per_character`` on items still in play, and an item has at most one keepsake per
character. Releasing one frees the slot; declaring again restarts the wait, so releasing and
re-declaring right before giving an item up earns nothing.

One service for every surface: the declare and release actions (web and telnet) call these,
and the item panel's read endpoint calls ``keepsake_choices``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from django.db import transaction
from django.utils import timezone

from world.items.constants import KeepsakeSubject
from world.items.exceptions import KeepsakeRefused
from world.items.models import Keepsake

if TYPE_CHECKING:
    from django.db.models import QuerySet

    from world.character_sheets.models import CharacterSheet
    from world.items.models import ItemInstance
    from world.worship.models import DevotionConfig

#: The longest a player's words may be: one to three sentences.
KEEPSAKE_TEXT_MAX_LENGTH = 600
#: The longest a place's name may be.
KEEPSAKE_LABEL_MAX_LENGTH = 100

MSG_NOT_HELD = "You can only keep an item you are holding."
MSG_ALREADY_KEPT = "You already keep that as a keepsake; release it first to change it."
MSG_NO_WORDS = "Write a sentence or two about what it stands for."
MSG_TOO_LONG = f"Keep it to {KEEPSAKE_TEXT_MAX_LENGTH} characters or fewer."
MSG_NO_SUCH_SUBJECT = "That is not something you can keep it for."
MSG_PLACE_NAME = "Name the place."
MSG_NOT_A_KEEPSAKE = "That is not one of your keepsakes."
MSG_NO_TENURE = "Only a character with a player can mark an item treasured."


@dataclass(frozen=True)
class KeepsakeSubjectRef:
    """What a keepsake stands for, before it is validated: a kind and the row's pk (or, for
    a place, its name)."""

    kind: str
    pk: int | None = None
    label: str = ""


@dataclass(frozen=True)
class KeepsakeStatus:
    """A character's keepsakes in use against their limit, for the item panel and the
    commands."""

    used: int
    limit: int
    wait_days: int


def _devotion_config() -> DevotionConfig:
    from world.worship.invocation_services import get_devotion_config  # noqa: PLC0415

    return get_devotion_config()


def live_keepsakes(sheet: CharacterSheet) -> QuerySet[Keepsake]:
    """The character's keepsakes on items still in play."""
    return Keepsake.objects.filter(
        character_sheet=sheet, item_instance__destroyed_at__isnull=True
    ).select_related("item_instance")


def keepsake_status(sheet: CharacterSheet) -> KeepsakeStatus:
    config = _devotion_config()
    return KeepsakeStatus(
        used=live_keepsakes(sheet).count(),
        limit=config.keepsakes_per_character,
        wait_days=config.keepsake_wait_days,
    )


def _subject_fields(sheet: CharacterSheet, subject: KeepsakeSubjectRef) -> dict[str, object]:
    """The Keepsake field values for ``subject``, refusing anything the character cannot
    keep an item for (a tie that is not theirs, a deed credited to someone else)."""
    from world.relationships.models import CharacterRelationship  # noqa: PLC0415
    from world.scenes.models import Persona  # noqa: PLC0415
    from world.societies.models import LegendEntry, Organization  # noqa: PLC0415
    from world.worship.models import WorshippedBeing  # noqa: PLC0415

    kind = subject.kind
    if kind == KeepsakeSubject.PLACE:
        label = subject.label.strip()
        if not label or len(label) > KEEPSAKE_LABEL_MAX_LENGTH:
            raise KeepsakeRefused(MSG_PLACE_NAME)
        return {"subject_label": label}
    found = {
        KeepsakeSubject.TIE: (
            "subject_relationship",
            CharacterRelationship.objects.filter(
                source=sheet, target__isnull=False, is_active=True
            ),
        ),
        KeepsakeSubject.DEED: (
            "subject_deed",
            LegendEntry.objects.filter(persona__character_sheet=sheet, is_active=True),
        ),
        KeepsakeSubject.BEING: ("subject_being", WorshippedBeing.objects.filter(is_active=True)),
        KeepsakeSubject.ORGANIZATION: ("subject_organization", Organization.objects.all()),
        KeepsakeSubject.PERSON: (
            "subject_persona",
            Persona.objects.exclude(character_sheet=sheet),
        ),
    }.get(kind)
    if found is None or subject.pk is None:
        raise KeepsakeRefused(MSG_NO_SUCH_SUBJECT)
    field, queryset = found
    row = queryset.filter(pk=subject.pk).first()
    if row is None:
        raise KeepsakeRefused(MSG_NO_SUCH_SUBJECT)
    return {field: row}


def _validate_declaration(
    sheet: CharacterSheet, item: ItemInstance, text: str, config: DevotionConfig
) -> str:
    """Refuse a declaration that cannot be made; returns the trimmed words."""
    if item.destroyed_at is not None or item.holder_character_sheet_id != sheet.pk:
        raise KeepsakeRefused(MSG_NOT_HELD)
    if Keepsake.objects.filter(item_instance=item, character_sheet=sheet).exists():
        raise KeepsakeRefused(MSG_ALREADY_KEPT)
    words = text.strip()
    if not words:
        raise KeepsakeRefused(MSG_NO_WORDS)
    if len(words) > KEEPSAKE_TEXT_MAX_LENGTH:
        raise KeepsakeRefused(MSG_TOO_LONG)
    if live_keepsakes(sheet).count() >= config.keepsakes_per_character:
        msg = f"You keep {config.keepsakes_per_character} keepsakes already; release one first."
        raise KeepsakeRefused(msg)
    return words


@transaction.atomic
def declare_keepsake(  # noqa: PLR0913 - the declaration's parts are keyword-only and distinct
    sheet: CharacterSheet,
    item: ItemInstance,
    *,
    subject: KeepsakeSubjectRef,
    text: str,
    shown_on_examine: bool = False,
    treasured: bool = False,
) -> Keepsake:
    """Declare ``item`` a keepsake of ``sheet`` standing for ``subject``.

    The words are the player's and are stored as written; nothing ever scores them. With
    ``treasured`` the item is also flagged treasured for consent (the stakes boundary), the
    same flag the Boundaries page sets. Raises ``KeepsakeRefused`` with the reason.
    """
    config = _devotion_config()
    words = _validate_declaration(sheet, item, text, config)
    fields = _subject_fields(sheet, subject)
    if treasured:
        _mark_treasured(sheet, item)
    keepsake = Keepsake.objects.create(
        item_instance=item,
        character_sheet=sheet,
        subject_kind=subject.kind,
        text=words,
        shown_on_examine=shown_on_examine,
        **fields,
    )
    del item.cached_shown_keepsakes  # examine's keepsake line reads it
    return keepsake


def _mark_treasured(sheet: CharacterSheet, item: ItemInstance) -> None:
    """Flag ``item`` treasured for the character's player, once."""
    from world.boundaries.constants import TreasuredSubjectKind  # noqa: PLC0415
    from world.boundaries.models import TreasuredSubject  # noqa: PLC0415

    entry = sheet.roster_entry_or_none
    tenure = entry.current_tenure if entry is not None else None
    if tenure is None:
        raise KeepsakeRefused(MSG_NO_TENURE)
    TreasuredSubject.objects.get_or_create(
        owner=tenure,
        subject_kind=TreasuredSubjectKind.ITEM,
        subject_item=item,
        defaults={"subject_label": str(item)[:200]},
    )


@transaction.atomic
def release_keepsake(sheet: CharacterSheet, item: ItemInstance) -> None:
    """Stop keeping ``item`` as a keepsake. Frees the slot; a later declaration starts the
    wait over. Raises ``KeepsakeRefused`` when it is not one of the character's keepsakes."""
    deleted, _ = Keepsake.objects.filter(item_instance=item, character_sheet=sheet).delete()
    if not deleted:
        raise KeepsakeRefused(MSG_NOT_A_KEEPSAKE)
    del item.cached_shown_keepsakes  # examine's keepsake line reads it


def find_subject_by_name(sheet: CharacterSheet, kind: str, name: str) -> KeepsakeSubjectRef:
    """Resolve a typed name (telnet) to a subject: a tie by the other character's persona
    name, a deed by its title, a being, an organization or a person by name, a place as
    written. Raises ``KeepsakeRefused`` when it names nothing the character can keep for."""
    from world.relationships.models import CharacterRelationship  # noqa: PLC0415
    from world.scenes.models import Persona  # noqa: PLC0415
    from world.societies.models import LegendEntry, Organization  # noqa: PLC0415
    from world.worship.models import WorshippedBeing  # noqa: PLC0415

    text = name.strip()
    if kind == KeepsakeSubject.PLACE:
        return KeepsakeSubjectRef(kind=kind, label=text)
    row = None
    if kind == KeepsakeSubject.TIE:
        ties = CharacterRelationship.objects.filter(
            source=sheet, target__isnull=False, is_active=True
        ).select_related("target")
        row = next((t for t in ties if t.target.primary_persona.name.lower() == text.lower()), None)
    elif kind == KeepsakeSubject.DEED:
        row = LegendEntry.objects.filter(
            persona__character_sheet=sheet, is_active=True, title__iexact=text
        ).first()
    elif kind == KeepsakeSubject.BEING:
        row = WorshippedBeing.objects.filter(is_active=True, name__iexact=text).first()
    elif kind == KeepsakeSubject.ORGANIZATION:
        row = Organization.objects.filter(name__iexact=text).first()
    elif kind == KeepsakeSubject.PERSON:
        row = Persona.objects.exclude(character_sheet=sheet).filter(name__iexact=text).first()
    if row is None:
        msg = f"You have no '{text}' to keep it for."
        raise KeepsakeRefused(msg)
    return KeepsakeSubjectRef(kind=kind, pk=row.pk)


def subject_choices(sheet: CharacterSheet) -> dict[str, list[tuple[int, str]]]:
    """What the character can keep an item for, by kind, as (pk, label) pairs: their own ties
    and deeds, the beings they hold a standing with or have declared, and the organizations
    they belong to. A person is searched by name (any persona but their own) and a place is
    free text, so neither is listed."""
    from world.relationships.models import CharacterRelationship  # noqa: PLC0415
    from world.societies.models import LegendEntry, OrganizationMembership  # noqa: PLC0415
    from world.worship.models import DevotionStanding, WorshipDeclaration  # noqa: PLC0415

    ties = CharacterRelationship.objects.filter(
        source=sheet, target__isnull=False, is_active=True
    ).select_related("target")
    deeds = LegendEntry.objects.filter(persona__character_sheet=sheet, is_active=True)
    being_ids = set(
        DevotionStanding.objects.filter(character_sheet=sheet, being__is_active=True).values_list(
            "being_id", flat=True
        )
    )
    declaration = WorshipDeclaration.objects.filter(character_sheet=sheet).first()
    if declaration is not None:
        being_ids.add(declaration.public_being_id)
    from world.worship.models import WorshippedBeing  # noqa: PLC0415

    beings = WorshippedBeing.objects.filter(pk__in=being_ids, is_active=True).order_by("name")
    memberships = (
        OrganizationMembership.objects.filter(
            persona__character_sheet=sheet, left_at__isnull=True, exiled_at__isnull=True
        )
        .select_related("organization")
        .order_by("organization__name")
    )
    return {
        KeepsakeSubject.TIE: [(t.pk, t.target.primary_persona.name) for t in ties],
        KeepsakeSubject.DEED: [(d.pk, d.title) for d in deeds],
        KeepsakeSubject.BEING: [(b.pk, b.name) for b in beings],
        KeepsakeSubject.ORGANIZATION: [
            (m.organization_id, m.organization.name) for m in memberships
        ],
    }


@dataclass(frozen=True)
class KeepsakeState:
    """What the item panel's keepsake form needs for one held item (#4530): the keepsake it
    already is, the character's slots, what it can stand for, and the deeds it is a trophy
    of."""

    keepsake: Keepsake | None
    counts_now: bool
    status: KeepsakeStatus
    subjects: dict[str, list[tuple[int, str]]]
    trophy_of: list[str]
    carried_days: int


def keepsake_state(sheet: CharacterSheet, item: ItemInstance) -> KeepsakeState:
    """The keepsake form's data for ``item`` held by ``sheet``."""
    status = keepsake_status(sheet)
    keepsake = Keepsake.objects.filter(item_instance=item, character_sheet=sheet).first()
    counts_now = (
        keepsake is not None and (timezone.now() - keepsake.created_at).days >= status.wait_days
    )
    return KeepsakeState(
        keepsake=keepsake,
        counts_now=counts_now,
        status=status,
        subjects=subject_choices(sheet),
        trophy_of=[deed.title for deed in item.cached_trophy_deeds],
        carried_days=(timezone.now() - item.held_since).days,
    )
