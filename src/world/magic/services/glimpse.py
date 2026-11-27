"""Glimpse guided-flow write services (#2427).

Single write path for a character's Glimpse: tag picks per axis, the prose
story, and distinction provenance links. Every mutation recomputes
``CharacterAura.glimpse_state`` so the cached state never drifts from the
prose + tag rows (the field is a cache of truth, mirroring the ``is_secret``
FK-presence precedent).
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from django.core.exceptions import ValidationError
from django.db import transaction

from world.magic.constants import GLIMPSE_AXIS_CONFIG, GlimpseState, GlimpseTagAxis
from world.magic.models.glimpse import CharacterGlimpseTag

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping, Sequence

    from world.distinctions.models import CharacterDistinction
    from world.magic.models.affinity import Affinity
    from world.magic.models.aura import CharacterAura
    from world.magic.models.glimpse import GlimpseTag
    from world.magic.types import AffinityShare


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


@transaction.atomic
def set_glimpse_tags(
    aura: CharacterAura, tags: Sequence[GlimpseTag], *, axis: GlimpseTagAxis
) -> None:
    """Replace the character's chosen tags for one axis.

    Enforces the axis's select-arity (``GLIMPSE_AXIS_CONFIG``), that every tag
    belongs to ``axis``, and that a tag which stands alone (``GlimpseTag.stands_alone``,
    #5193) is the only one. An empty ``tags`` clears the axis.
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

    CharacterGlimpseTag.objects.filter(aura=aura, tag__axis=axis).delete()
    CharacterGlimpseTag.objects.bulk_create(CharacterGlimpseTag(aura=aura, tag=tag) for tag in tags)
    # The queryset delete and the bulk create run no row's save() or delete(), so the
    # aura's cached list is dropped here; the sheet reads it (#5193).
    aura.__dict__.pop("cached_glimpse_tags", None)
    refresh_glimpse_state(aura)


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


def apply_glimpse_affinity_nudge(aura: CharacterAura) -> None:
    """Apply a small nudge to who the character is from TONE/TRIGGER Glimpse tags.

    The nudge moves the settled shares only (#5123): the aura a character has is their
    resonance history, which a tag does not change.

    Reads the character's chosen TONE and TRIGGER tags (single-select axes where the
    emotional register / trigger story most directly maps to an affinity). For each tag
    that carries an ``affinity`` FK, shifts that affinity by
    ``GLIMPSE_AFFINITY_NUDGE_PERCENT`` percentage points, then re-normalizes so the
    settled shares still sum to 100.00.

    Called once at CG finalize, after tags are set and the aura is settled. Tags without
    an ``affinity`` (including all CONSEQUENCE, WITNESS, and SENSORY tags) are inert; the
    nudge only fires on TONE and TRIGGER.

    Idempotent: calling it twice doubles the nudge, but in practice it is
    called exactly once from ``_finalize_glimpse_data``.
    """
    from world.magic.models.glimpse import GlimpseTag  # noqa: PLC0415
    from world.magic.services.aura import set_settled_shares  # noqa: PLC0415

    # Only a TONE or TRIGGER tag with an affinity nudges, so a character with none pays
    # this one query and nothing more.
    tag_ids = list(
        CharacterGlimpseTag.objects.filter(
            aura=aura, tag__axis__in={GlimpseTagAxis.TONE, GlimpseTagAxis.TRIGGER}
        )
        .exclude(tag__affinity__isnull=True)
        .values_list("tag_id", flat=True)
    )
    if not tag_ids:
        return
    tags = list(GlimpseTag.objects.filter(pk__in=tag_ids).select_related("affinity"))
    settled = {
        share.affinity_id: (share.affinity, Decimal(share.settled_percent))
        for share in aura.cached_shares
    }
    nudged = glimpse_nudged_shares(settled, tags)
    if nudged is not None:
        set_settled_shares(aura, nudged)


def glimpse_nudged_shares(
    settled: Mapping[int, tuple[Affinity, Decimal]], tags: Iterable[GlimpseTag]
) -> list[AffinityShare] | None:
    """The settled shares after the Glimpse's nudge, or None when no tag nudges (#5206).

    ``settled`` maps an affinity pk to the affinity and its settled percent; ``tags`` are
    the character's chosen Glimpse tags. Each TONE or TRIGGER tag with an ``affinity``
    shifts that affinity by ``GLIMPSE_AFFINITY_NUDGE_PERCENT`` points, taken evenly from
    the others, then the shares are clamped to 0-100 and scaled to sum to 100. The pure half
    of ``apply_glimpse_affinity_nudge``; the waiting sheet computes a new character's aura
    with it before the character exists.
    """
    from world.magic.types import AffinityShare  # noqa: PLC0415

    nudge_axes = {GlimpseTagAxis.TONE, GlimpseTagAxis.TRIGGER}
    affinity_counts: dict[int, int] = {}
    affinities: dict[int, Affinity] = {}
    for tag in tags:
        if tag.axis not in nudge_axes or tag.affinity_id is None:
            continue
        affinities[tag.affinity_id] = tag.affinity
        affinity_counts[tag.affinity_id] = affinity_counts.get(tag.affinity_id, 0) + 1
    if not affinity_counts:
        return None

    values: dict[int, Decimal] = {}
    for pk, (affinity, percent) in settled.items():
        affinities[pk] = affinity
        values[pk] = Decimal(percent)
    for pk in affinity_counts:
        values.setdefault(pk, Decimal(0))
    _spread_nudges(values, affinity_counts)

    # Clamp to [0, 100] and scale so the shares sum to 100; set_settled_shares fixes the
    # last cent of rounding.
    clamped = {pk: max(Decimal(0), min(Decimal(100), v)) for pk, v in values.items()}
    total = sum(clamped.values())
    if total == 0:
        return None
    return [
        AffinityShare(affinity=affinities[pk], percent=v * Decimal(100) / total)
        for pk, v in sorted(clamped.items())
        if v > 0
    ]


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
