"""Glimpse guided-flow write services (#2427).

Single write path for a character's Glimpse: tag picks per axis, the prose
story, and distinction provenance links. Every mutation recomputes
``CharacterAura.glimpse_state`` so the cached state never drifts from the
prose + tag rows (the field is a cache of truth, mirroring the ``is_secret``
FK-presence precedent).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.core.exceptions import ValidationError
from django.db import transaction

from world.magic.constants import GLIMPSE_AXIS_CONFIG, GlimpseState, GlimpseTagAxis
from world.magic.models.glimpse import CharacterGlimpseTag

if TYPE_CHECKING:
    from collections.abc import Sequence

    from world.distinctions.models import CharacterDistinction
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


@transaction.atomic
def set_glimpse_tags(
    aura: CharacterAura, tags: Sequence[GlimpseTag], *, axis: GlimpseTagAxis
) -> None:
    """Replace the character's chosen tags for one axis.

    Enforces the axis's select-arity (``GLIMPSE_AXIS_CONFIG``) and that every
    tag belongs to ``axis``. An empty ``tags`` clears the axis.
    """
    rule = GLIMPSE_AXIS_CONFIG[GlimpseTagAxis(axis)]
    if not rule.multi and len(tags) > 1:
        msg = f"{GlimpseTagAxis(axis).label} accepts a single tag."
        raise ValidationError(msg)
    wrong = [tag.name for tag in tags if tag.axis != axis]
    if wrong:
        msg = f"Tags not on the {GlimpseTagAxis(axis).label} axis: {', '.join(wrong)}."
        raise ValidationError(msg)

    CharacterGlimpseTag.objects.filter(aura=aura, tag__axis=axis).delete()
    CharacterGlimpseTag.objects.bulk_create(CharacterGlimpseTag(aura=aura, tag=tag) for tag in tags)
    refresh_glimpse_state(aura)


def set_glimpse_prose(aura: CharacterAura, text: str) -> None:
    """Write the glimpse story prose and recompute the state."""
    aura.glimpse_story = text
    aura.save()
    refresh_glimpse_state(aura)


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
    """Apply a small aura affinity nudge from TONE/TRIGGER Glimpse tags.

    Reads the character's chosen TONE and TRIGGER tags (single-select axes
    where the emotional register / trigger story most directly maps to an
    affinity). For each tag that carries an ``affinity`` FK, shifts that
    affinity by ``GLIMPSE_AFFINITY_NUDGE_PERCENT`` percentage points, then
    re-normalizes so the three values still sum to 100.00.

    Called once at CG finalize, after tags are set but before the final
    ``recompute_aura`` call. Tags without an ``affinity`` (including all
    CONSEQUENCE, WITNESS, and SENSORY tags) are inert — the nudge only fires
    on TONE and TRIGGER.

    Idempotent: calling it twice doubles the nudge, but in practice it is
    called exactly once from ``_finalize_glimpse_data``.
    """
    from world.magic.models.glimpse import GlimpseTag  # noqa: PLC0415

    nudge_axes = {GlimpseTagAxis.TONE, GlimpseTagAxis.TRIGGER}
    tag_ids = list(
        CharacterGlimpseTag.objects.filter(aura=aura, tag__axis__in=nudge_axes)
        .exclude(tag__affinity__isnull=True)
        .values_list("tag_id", flat=True)
    )
    if not tag_ids:
        return

    # Count how many tags nudge each affinity.
    affinity_counts: dict[str, int] = {}
    for tag in GlimpseTag.objects.filter(pk__in=tag_ids).select_related("affinity"):
        if tag.affinity is None:
            continue
        name = tag.affinity.name.lower()
        affinity_counts[name] = affinity_counts.get(name, 0) + 1

    if not affinity_counts:
        return

    from decimal import Decimal  # noqa: PLC0415

    nudge = Decimal(GLIMPSE_AFFINITY_NUDGE_PERCENT)

    # Apply nudges: add to the tagged affinity, subtract proportionally from
    # the others to keep the sum at 100.00.
    celestial = Decimal(aura.celestial)
    primal = Decimal(aura.primal)
    abyssal = Decimal(aura.abyssal)

    values = {"celestial": celestial, "primal": primal, "abyssal": abyssal}

    for affinity_name, count in affinity_counts.items():
        shift = nudge * count
        values[affinity_name] += shift
        # Subtract evenly from the other two to keep sum == 100.
        others = [k for k in values if k != affinity_name]
        per_other = shift / Decimal(len(others))
        for other in others:
            values[other] -= per_other

    # Clamp to [0, 100] and fix rounding so the three sum to exactly 100.00.
    for k, v in values.items():
        values[k] = max(Decimal(0), min(Decimal(100), v))

    celestial = values["celestial"].quantize(Decimal("0.01"))
    primal = values["primal"].quantize(Decimal("0.01"))
    abyssal = (Decimal("100.00") - celestial - primal).quantize(Decimal("0.01"))

    aura.celestial = celestial
    aura.primal = primal
    aura.abyssal = abyssal
    aura.save()
