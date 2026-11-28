"""Glimpse guided-flow write services (#2427).

Single write path for a character's Glimpse: tag picks per axis, the prose
story, and distinction provenance links. Every mutation recomputes
``CharacterAura.glimpse_state`` so the cached state never drifts from the
prose + tag rows (the field is a cache of truth, mirroring the ``is_secret``
FK-presence precedent).

``write_glimpse`` (#5292) is the way a Glimpse is written on a character in play, by
the player or by staff. It holds the rule for what a player may write, and it gives
the card an answer carries. ``set_glimpse_tags`` and ``set_glimpse_prose`` stay the
plain writes under it, which character creation's finalize also calls.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from django.core.exceptions import ValidationError
from django.db import transaction

from world.magic.constants import (
    GLIMPSE_AXIS_CONFIG,
    GLIMPSE_CARD_AXES,
    GlimpseMemory,
    GlimpseState,
    GlimpseTagAxis,
    glimpse_axes_asked,
)
from world.magic.models.glimpse import CharacterGlimpseTag

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from world.character_creation.models import DistinctionOffer
    from world.distinctions.models import CharacterDistinction
    from world.magic.models.affinity import Affinity
    from world.magic.models.aura import CharacterAura
    from world.magic.models.glimpse import GlimpseTag


def refresh_glimpse_state(aura: CharacterAura) -> GlimpseState:
    """Recompute and persist ``glimpse_state`` from prose + tag rows."""
    if aura.glimpse_story.strip():
        state = GlimpseState.COMPLETE
    elif CharacterGlimpseTag.objects.filter(aura=aura).exists():
        state = GlimpseState.TAGS_ONLY
    else:
        state = GlimpseState.NOT_STARTED
    if aura.glimpse_state != state:
        aura.glimpse_state = state
        aura.save()
    return state


def check_axis_tags(tags: Sequence[GlimpseTag], *, axis: GlimpseTagAxis) -> None:
    """Raise unless ``tags`` may be saved as one axis's answer.

    The axis's select-arity (``GLIMPSE_AXIS_CONFIG``), that every tag belongs to ``axis``,
    and that a tag which stands alone (``GlimpseTag.stands_alone``, #5193) is the only one.
    ``write_glimpse`` runs this for every axis before it saves anything.
    """
    rule = GLIMPSE_AXIS_CONFIG[GlimpseTagAxis(axis)]
    if not rule.multi and len(tags) > 1:
        msg = f"{GlimpseTagAxis(axis).label} accepts a single tag."
        raise ValidationError(msg)
    alone = [tag.name for tag in tags if tag.stands_alone]
    if alone and len(tags) > 1:
        msg = f"{alone[0]} cannot be chosen with another {GlimpseTagAxis(axis).label} tag."
        raise ValidationError(msg)
    wrong = [tag.name for tag in tags if tag.axis != axis]
    if wrong:
        msg = f"Tags not on the {GlimpseTagAxis(axis).label} axis: {', '.join(wrong)}."
        raise ValidationError(msg)


@transaction.atomic
def set_glimpse_tags(
    aura: CharacterAura, tags: Sequence[GlimpseTag], *, axis: GlimpseTagAxis
) -> None:
    """Replace the character's chosen tags for one axis.

    Enforces ``check_axis_tags``. An empty ``tags`` clears the axis.
    """
    check_axis_tags(tags, axis=axis)

    CharacterGlimpseTag.objects.filter(aura=aura, tag__axis=axis).delete()
    CharacterGlimpseTag.objects.bulk_create(CharacterGlimpseTag(aura=aura, tag=tag) for tag in tags)
    # The queryset delete and the bulk create run no row's save() or delete(), so the
    # aura's cached list is dropped here; the sheet reads it (#5193).
    aura.__dict__.pop("cached_glimpse_tags", None)
    refresh_glimpse_state(aura)


def tags_closed_to_path(tags: Sequence[GlimpseTag], path_id: int | None) -> list[GlimpseTag]:
    """The tags among ``tags`` that are restricted to paths other than ``path_id`` (#5292).

    A tag with no path listed is open to every path (``GlimpseTag.paths``). The answer
    catalogue is already narrowed by path for the page; this is the rule for an answer
    sent some other way, so The Choosing's card cannot be had off the Chosen's path.
    One query for the list, none when it is empty.
    """
    from world.magic.models.glimpse import GlimpseTag  # noqa: PLC0415

    if not tags:
        return []
    allowed: dict[int, set[int]] = {}
    rows = GlimpseTag.paths.through.objects.filter(glimpsetag_id__in=[tag.pk for tag in tags])
    for tag_id, tag_path_id in rows.values_list("glimpsetag_id", "path_id"):
        allowed.setdefault(tag_id, set()).add(tag_path_id)
    return [tag for tag in tags if tag.pk in allowed and path_id not in allowed[tag.pk]]


def keep_stand_alone(tags: Sequence[GlimpseTag]) -> list[GlimpseTag]:
    """One axis's tags as they may be saved: a tag that stands alone is kept alone (#5193).

    For a writer that must not fail on picks it did not validate one by one (character
    creation's finalize reads a draft's whole list): the first stand-alone tag, in the
    order given, replaces the rest. Tags with no stand-alone tag among them come back
    unchanged.
    """
    for tag in tags:
        if tag.stands_alone:
            return [tag]
    return list(tags)


def set_glimpse_prose(aura: CharacterAura, text: str, *, edited_by: object | None = None) -> None:
    """Write the glimpse story prose and recompute the state.

    Versioned (#4224) through ``update_profile_text`` on the sheet's true profile, like
    every other prose field, so a rewrite never loses the earlier Glimpse; that write
    also recomputes the state.
    """
    from world.character_sheets.services import (  # noqa: PLC0415
        ensure_true_profile,
        update_profile_text,
    )
    from world.character_sheets.types import ProfileTextField  # noqa: PLC0415

    update_profile_text(
        ensure_true_profile(aura.character),
        ProfileTextField.GLIMPSE,
        text,
        edited_by=edited_by,
    )


def _refuse_player_write(
    aura: CharacterAura,
    memory: str,
    answers: Mapping[GlimpseTagAxis, Sequence[GlimpseTag]],
    answered: Mapping[str, set[int]],
) -> None:
    """Raise for a write a player may not make (#5292); staff are never asked.

    With no memory the Glimpse is a story's to settle, so the player writes none of
    it. After a blackout there is nothing to say of the axes it took. An axis that has
    its answer is final: the answer gave a card, and a player gives a card back only
    through an approved sheet update request (``remove_distinction``), so a second
    answer would stack a second bonus.
    """
    if memory == GlimpseMemory.NO_MEMORY:
        msg = "This character has no memory of their Glimpse."
        raise ValidationError(msg)
    remembered = glimpse_axes_asked(memory)
    for axis, tags in answers.items():
        label = GlimpseTagAxis(axis).label
        if axis not in remembered:
            msg = f"This character blacked out, and has no answer to {label}."
            raise ValidationError(msg)
        held = answered.get(axis)
        if held and held != {tag.pk for tag in tags}:
            msg = f"{label} is already answered, and the answer is final."
            raise ValidationError(msg)
    picked = [tag for tags in answers.values() for tag in tags]
    closed = tags_closed_to_path(picked, _current_path_id(aura)) if picked else []
    if closed:
        msg = f"{closed[0].name} is not an answer this character's path can give."
        raise ValidationError(msg)


def _current_path_id(aura: CharacterAura) -> int | None:
    """The character's current path, read from the rows."""
    from world.progression.models import CharacterPathHistory  # noqa: PLC0415

    return (
        CharacterPathHistory.objects.filter(character_id=aura.character_id)
        .order_by("-selected_at")
        .values_list("path_id", flat=True)
        .first()
    )


#: What the player is told when staff change how much of the Glimpse is remembered (#5292).
#: PLACEHOLDER: Apostate rewrite.
GLIMPSE_MEMORY_NEWS = {
    GlimpseMemory.REMEMBERED: (
        "The memory of your Glimpse has returned. You can write it from your character sheet."
    ),
    GlimpseMemory.BLACKED_OUT: (
        "You blacked out during your Glimpse: what you saw in yourself and how it felt are lost."
    ),
    GlimpseMemory.NO_MEMORY: "You have no memory of your Glimpse.",
}


def set_glimpse_memory(aura: CharacterAura, memory: str) -> None:
    """Staff set how much of the Glimpse the character remembers (#5292).

    The switch a story flips when it returns a lost Glimpse: set to remembered, the
    player (or staff) can then write the answers, which give their cards. The card that
    marked the mystery stays as history; staff take it away, if they want it gone, in
    the staff sheet editor. The character is told of a change, so a returned memory
    does not wait to be noticed on the sheet.
    """
    from world.magic.models.aura import CharacterAura  # noqa: PLC0415
    from world.narrative.constants import NarrativeCategory  # noqa: PLC0415
    from world.narrative.services import send_narrative_message  # noqa: PLC0415

    memory = GlimpseMemory(memory)
    # Compared against the row: the identity-mapped instance may be another process's past.
    stored = CharacterAura.objects.filter(pk=aura.pk).values_list("glimpse_memory", flat=True).get()
    aura.glimpse_memory = memory
    aura.save()
    if stored != memory:
        send_narrative_message(
            recipients=[aura.character],
            body=GLIMPSE_MEMORY_NEWS[memory],
            category=NarrativeCategory.STORY,
            sender_account=None,
        )


def player_can_finish_glimpse(aura: CharacterAura, *, path_id: int | None) -> bool:
    """Whether the player still has some of the Glimpse to write (#5292).

    True while the story is blank, or while an axis the player may write has no answer
    and has an answer the character's path can pick (The Choosing is the Chosen's
    alone). Never with no memory: a story settles that Glimpse. Read by the sheet for
    its "Finish your Glimpse" door; ``write_glimpse`` is what enforces the rule.
    """
    from django.db.models import Q  # noqa: PLC0415

    from world.magic.models.glimpse import GlimpseTag  # noqa: PLC0415

    writable = glimpse_axes_asked(aura.glimpse_memory)
    if not writable:
        return False
    if not aura.glimpse_story.strip():
        return True
    unanswered = writable - {row.tag.axis for row in aura.cached_glimpse_tags}
    if not unanswered:
        return False
    for_path = Q(paths__isnull=True)
    if path_id is not None:
        for_path |= Q(paths=path_id)
    return GlimpseTag.objects.filter(for_path, is_active=True, axis__in=unanswered).exists()


def glimpse_card_lines(tags: Sequence[GlimpseTag]) -> list[DistinctionOffer]:
    """The active lines that say which card each of these answers gives (#5292)."""
    from world.character_creation.constants import OfferChapter  # noqa: PLC0415
    from world.character_creation.models import DistinctionOffer  # noqa: PLC0415

    card_tag_ids = [tag.pk for tag in tags if tag.axis in GLIMPSE_CARD_AXES]
    if not card_tag_ids:
        return []
    return list(
        DistinctionOffer.objects.filter(
            is_active=True, chapter=OfferChapter.GLIMPSE, glimpse_tag_id__in=card_tag_ids
        )
        .select_related("distinction", "glimpse_tag")
        .order_by("sort_order", "id")
    )


def _cards_owed(aura: CharacterAura, tags: Sequence[GlimpseTag]) -> list[DistinctionOffer]:
    """The lines of ``tags`` whose card the character does not hold, one for each card."""
    from world.distinctions.models import CharacterDistinction  # noqa: PLC0415

    lines = glimpse_card_lines(tags)
    if not lines:
        return []
    held_ids = set(
        CharacterDistinction.objects.filter(
            character=aura.character, distinction_id__in=[line.distinction_id for line in lines]
        ).values_list("distinction_id", flat=True)
    )
    owed: list[DistinctionOffer] = []
    for line in lines:
        if line.distinction_id not in held_ids:
            held_ids.add(line.distinction_id)
            owed.append(line)
    return owed


def give_glimpse_cards(
    aura: CharacterAura, *, required: Sequence[GlimpseTag] = ()
) -> list[CharacterDistinction]:
    """Make sure the character holds the card of every answered axis; return the new ones.

    A card already held is left as it is, so this is safe to call on every write. That
    is also what gives a card to a character who answered before the card existed
    (#5292): their next write of the Glimpse, or staff's, brings it. A new card comes
    as it would from staff's sheet editor: through ``grant_distinction``, the one way a
    card is gained in play, with its secret where the card is secret by default, its
    codex entries, and the mark that it was born in the Glimpse.

    A card the character cannot hold beside one they have (an exclusion between cards)
    is skipped when it is owed from an earlier answer, so an old answer never blocks a
    later write. For an answer in ``required`` (the ones this write saves),
    ``DistinctionExclusionError`` propagates; ``write_glimpse`` checks those before it
    saves anything, so that is a race lost, not the ordinary refusal.
    """
    from world.character_creation.sheet_writers import grant_distinction_codex  # noqa: PLC0415
    from world.distinctions.exceptions import DistinctionExclusionError  # noqa: PLC0415
    from world.distinctions.services import (  # noqa: PLC0415
        grant_distinction,
        mint_distinction_secret,
    )
    from world.distinctions.types import DistinctionOrigin  # noqa: PLC0415

    # Read from the rows, not the aura's cached list: another process may have written.
    answered = CharacterGlimpseTag.objects.filter(aura=aura).select_related("tag")
    required_ids = {tag.pk for tag in required}
    sheet = aura.character
    given: list[CharacterDistinction] = []
    for line in _cards_owed(aura, [row.tag for row in answered]):
        try:
            card = grant_distinction(
                sheet,
                line.distinction,
                origin=DistinctionOrigin.GAMEPLAY,
                rank=1,
                source_description=line.glimpse_tag.name,
            )
        except DistinctionExclusionError:
            if line.glimpse_tag_id in required_ids:
                raise
            continue
        if line.distinction.secret_by_default:
            mint_distinction_secret(card)
        link_distinction_to_glimpse(card, aura)
        given.append(card)
    grant_distinction_codex(sheet, [card.distinction for card in given])
    return given


def write_glimpse(
    aura: CharacterAura,
    *,
    by_staff: bool,
    answers: Mapping[GlimpseTagAxis, Sequence[GlimpseTag]] | None = None,
    story: str | None = None,
    edited_by: object | None = None,
) -> list[CharacterDistinction]:
    """Write answers and/or the story of a Glimpse on a character in play (#5292).

    The one way in for the sheet's Glimpse editor and for staff. Returns the cards the
    write gave. All of it happens or none of it: the aura's row is locked first, so two
    requests at once cannot both answer one axis, and every refusal (the player's rule,
    an axis's arity, an exclusion between cards) is raised before anything is saved.

    A player (``by_staff=False``) is refused any write with no memory, a write to an
    axis a blackout took, a new answer to an axis that has one, and an answer their
    path cannot give. Staff skip those: they settle a Glimpse a story returned, and
    correct one. When staff change an answer the new answer's card is given and the old
    card stays, until staff take it away in the staff sheet editor.

    A TONE or TRIGGER answer nudges the aura the first time that axis is answered,
    as it does at finalize, and never again for a changed answer.

    The aura and its shares are identity-mapped (ADR-0008): a rollback restores their
    rows but not the cached instances. If the write fails after it began to save (a
    race lost on a card, a fault), they are evicted, so the next read is the row and a
    refused story or a nudge that did not happen is not shown or saved later.
    """
    saved = False
    shares = list(aura.cached_shares)
    try:
        with transaction.atomic():
            given = _write_glimpse(
                aura, by_staff=by_staff, answers=answers or {}, story=story, edited_by=edited_by
            )
        saved = True
        return given
    finally:
        if not saved:
            for share in shares:
                share.flush_from_cache(force=True)
            aura.flush_from_cache(force=True)


def _write_glimpse(
    aura: CharacterAura,
    *,
    by_staff: bool,
    answers: Mapping[GlimpseTagAxis, Sequence[GlimpseTag]],
    story: str | None,
    edited_by: object | None,
) -> list[CharacterDistinction]:
    """``write_glimpse`` inside its transaction: every check, then every write."""
    from world.distinctions.exceptions import DistinctionExclusionError  # noqa: PLC0415
    from world.distinctions.services import check_distinction_exclusions  # noqa: PLC0415
    from world.magic.models.aura import CharacterAura  # noqa: PLC0415

    # Lock the row and read the state from the database, not from the identity-mapped
    # instance: staff may have changed it in another process. The instance is brought
    # level, because a later full save of it would write its own value back.
    memory = (
        CharacterAura.objects.select_for_update()
        .filter(pk=aura.pk)
        .values_list("glimpse_memory", flat=True)
        .get()
    )
    aura.glimpse_memory = memory
    answered: dict[str, set[int]] = {}
    for axis, tag_id in CharacterGlimpseTag.objects.filter(aura=aura).values_list(
        "tag__axis", "tag_id"
    ):
        answered.setdefault(axis, set()).add(tag_id)
    if not by_staff:
        _refuse_player_write(aura, memory, answers, answered)
    for axis, tags in answers.items():
        check_axis_tags(tags, axis=axis)
    picked = [tag for tags in answers.values() for tag in tags]
    try:
        for line in _cards_owed(aura, picked):
            check_distinction_exclusions(aura.character, line.distinction)
    except DistinctionExclusionError as exc:
        raise ValidationError(exc.user_message) from exc

    first_answers: list[GlimpseTag] = []
    for axis, tags in answers.items():
        set_glimpse_tags(aura, tags, axis=axis)
        if not answered.get(axis):
            first_answers.extend(tags)
    if story is not None:
        set_glimpse_prose(aura, story, edited_by=edited_by)
    apply_glimpse_affinity_nudge(aura, tags=first_answers)
    try:
        return give_glimpse_cards(aura, required=picked)
    except DistinctionExclusionError as exc:
        raise ValidationError(exc.user_message) from exc


def link_distinction_to_glimpse(
    character_distinction: CharacterDistinction, aura: CharacterAura
) -> None:
    """Mark a distinction as born in this character's Glimpse."""
    if character_distinction.character_id != aura.character_id:
        msg = "Distinction and aura belong to different characters."
        raise ValidationError(msg)
    character_distinction.from_glimpse = aura
    character_distinction.save()


def unlink_distinction_from_glimpse(character_distinction: CharacterDistinction) -> None:
    """Clear a distinction's Glimpse provenance."""
    character_distinction.from_glimpse = None
    character_distinction.save()


#: Per-tag affinity nudge in percentage points.  Each TONE or TRIGGER tag with
#: an ``affinity`` FK shifts the matching affinity by this amount at CG
#: finalize; the total is re-normalized so the three percentages still sum to
#: 100.00.  The magnitude is intentionally small — the Glimpse is a *nudge*,
#: not a rewrite of the aura the character's resonance history already
#: produces.
GLIMPSE_AFFINITY_NUDGE_PERCENT = 3

#: The axes whose answer nudges the aura.
GLIMPSE_NUDGE_AXES = frozenset({GlimpseTagAxis.TONE, GlimpseTagAxis.TRIGGER})


def apply_glimpse_affinity_nudge(
    aura: CharacterAura, *, tags: Sequence[GlimpseTag] | None = None
) -> None:
    """Apply a small nudge to who the character is from TONE/TRIGGER Glimpse tags.

    ``tags`` (#5292) names the answers to apply, for an answer first written in play:
    only those nudge, and an aura that holds no share yet is left alone (a nudge moves
    a settled self, it does not make one). With no ``tags`` every TONE and TRIGGER
    answer on the aura applies, which is what finalize wants.

    The nudge moves the settled shares only (#5123): the aura a character has is their
    resonance history, which a tag does not change.

    Reads the character's chosen TONE and TRIGGER tags (single-select axes where the
    emotional register / trigger story most directly maps to an affinity). For each tag
    that carries an ``affinity`` FK, shifts that affinity by
    ``GLIMPSE_AFFINITY_NUDGE_PERCENT`` percentage points, then re-normalizes so the
    settled shares still sum to 100.00.

    Called at CG finalize, after tags are set and the aura is settled, and by
    ``write_glimpse`` for an axis first answered in play. Tags without an ``affinity``
    (including all CONSEQUENCE, WITNESS, and SENSORY tags) are inert; the nudge only
    fires on TONE and TRIGGER.

    Not idempotent: calling it twice doubles the nudge. Each caller applies an answer
    once.
    """
    from world.magic.models.glimpse import GlimpseTag  # noqa: PLC0415

    if tags is None:
        tag_ids = list(
            CharacterGlimpseTag.objects.filter(aura=aura, tag__axis__in=GLIMPSE_NUDGE_AXES)
            .exclude(tag__affinity__isnull=True)
            .values_list("tag_id", flat=True)
        )
    else:
        if not aura.cached_shares:
            return
        tag_ids = [
            tag.pk for tag in tags if tag.axis in GLIMPSE_NUDGE_AXES and tag.affinity_id is not None
        ]
    if not tag_ids:
        return

    affinity_counts: dict[int, int] = {}
    affinities: dict[int, Affinity] = {}
    for tag in GlimpseTag.objects.filter(pk__in=tag_ids).select_related("affinity"):
        if tag.affinity is None:
            continue
        affinities[tag.affinity.pk] = tag.affinity
        affinity_counts[tag.affinity.pk] = affinity_counts.get(tag.affinity.pk, 0) + 1

    if not affinity_counts:
        return

    from world.magic.services.aura import set_settled_shares  # noqa: PLC0415
    from world.magic.types import AffinityShare  # noqa: PLC0415

    values: dict[int, Decimal] = {}
    for share in aura.cached_shares:
        affinities[share.affinity_id] = share.affinity
        values[share.affinity_id] = Decimal(share.settled_percent)
    for pk in affinity_counts:
        values.setdefault(pk, Decimal(0))
    _spread_nudges(values, affinity_counts)

    # Clamp to [0, 100] and scale so the shares sum to 100; set_aura_shares fixes the
    # last cent of rounding.
    clamped = {pk: max(Decimal(0), min(Decimal(100), v)) for pk, v in values.items()}
    total = sum(clamped.values())
    if total == 0:
        return
    set_settled_shares(
        aura,
        [
            AffinityShare(affinity=affinities[pk], percent=v * Decimal(100) / total)
            for pk, v in sorted(clamped.items())
            if v > 0
        ],
    )


def _spread_nudges(values: dict[int, Decimal], affinity_counts: dict[int, int]) -> None:
    """Add each tagged affinity's nudge to it and take it evenly from the other shares."""
    nudge = Decimal(GLIMPSE_AFFINITY_NUDGE_PERCENT)
    for pk, count in affinity_counts.items():
        shift = nudge * count
        values[pk] += shift
        others = [k for k in values if k != pk]
        if not others:
            continue
        per_other = shift / Decimal(len(others))
        for other in others:
            values[other] -= per_other
