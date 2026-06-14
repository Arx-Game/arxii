"""Service: vogue-momentum accrual + decay (Outfits Phase C, #514).

A society's *taste* drifts over time toward what acclaimed presenters actually
wear. Each peer judgment (``judge_presentation``) nudges the momentum of every
facet worn by the presenter up by a small step, for the perceiving society. A
cron-driven decay tick erodes all momentum toward zero, mirroring the renown
fame-decay pattern (``decay_all_persona_fame``).

The seasonal trendsetter *ceremony* — which reads the accumulated momentum to
choose a society's new in-vogue facets — is a later task; this module ships
only the accrual + decay primitives.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import transaction

from world.items.constants import (
    FASHION_VOGUE_DECAY_FLAT,
    FASHION_VOGUE_DECAY_RATE,
    FASHION_VOGUE_MOMENTUM_STEP,
)
from world.items.models import FacetVogueMomentum

if TYPE_CHECKING:
    from world.items.models import FashionPresentation


@transaction.atomic
def bump_vogue_momentum(presentation: FashionPresentation) -> None:
    """Nudge the momentum of every facet worn by the presenter for the society.

    Each peer judgment of ``presentation`` bumps the worn facets' momentum, so
    what acclaimed presenters wear trends up within the perceiving society.

    Collects the DISTINCT facets across the presenter's equipped items (via the
    character's equipment handler) and increments each one's
    ``FacetVogueMomentum.points`` by ``FASHION_VOGUE_MOMENTUM_STEP``, creating
    rows on first sight. No-op when the presenter has no resolvable character /
    no equipped facets.
    """
    society = presentation.perceiving_society
    character = presentation.presenter.character
    handler = getattr(character, "equipped_items", None)
    if handler is None:
        return

    facet_ids: set[int] = set()
    facets = []
    for item_facet in handler.iter_item_facets():
        if item_facet.facet_id in facet_ids:
            continue
        facet_ids.add(item_facet.facet_id)
        facets.append(item_facet.facet)

    for facet in facets:
        momentum, _created = FacetVogueMomentum.objects.get_or_create(
            society=society,
            facet=facet,
            defaults={"points": 0},
        )
        momentum.points += FASHION_VOGUE_MOMENTUM_STEP
        momentum.save(update_fields=["points"])


@transaction.atomic
def vogue_momentum_decay_tick() -> int:
    """Decay every positive ``FacetVogueMomentum`` toward zero. Returns count touched.

    Mirrors ``decay_all_persona_fame``: a single transaction, iterating only
    rows with positive points (rows already at 0 stay at 0). Each row loses
    ``FASHION_VOGUE_DECAY_FLAT + int(points * FASHION_VOGUE_DECAY_RATE)``,
    floored at 0.
    """
    touched = 0
    for momentum in FacetVogueMomentum.objects.filter(points__gt=0).iterator():
        points = momentum.points
        decayed = points - FASHION_VOGUE_DECAY_FLAT - int(points * FASHION_VOGUE_DECAY_RATE)
        momentum.points = max(0, decayed)
        momentum.save(update_fields=["points"])
        touched += 1
    return touched
