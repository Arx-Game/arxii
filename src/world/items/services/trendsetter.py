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

import logging
from typing import TYPE_CHECKING

from django.db import transaction
from django.db.models import Sum

from world.items.constants import (
    FASHION_LIVING_STYLE_NAME_TEMPLATE,
    FASHION_TREND_FACET_COUNT,
    FASHION_VOGUE_DECAY_FLAT,
    FASHION_VOGUE_DECAY_RATE,
    FASHION_VOGUE_MOMENTUM_STEP,
    get_fashion_modifier_target,
)
from world.items.models import (
    FacetVogueMomentum,
    FashionPresentation,
    FashionStyle,
    FashionStyleBonus,
    Trendsetter,
)

if TYPE_CHECKING:
    from world.societies.models import Society

logger = logging.getLogger(__name__)


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
    if not hasattr(character, "equipped_items"):
        return
    handler = character.equipped_items

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


@transaction.atomic
def run_trendsetter_ceremony(society: Society) -> Trendsetter | None:
    """Crown a season's trendsetter and rewrite a society's living vogue (#514).

    Reads the society's accumulated ``FacetVogueMomentum`` to choose the new
    in-vogue facets, crowns the highest-acclaim presenter's primary persona,
    and points the society at a living ``FashionStyle`` whose in-vogue facets
    are the top-N momentum facets. Returns the ``Trendsetter`` row, or ``None``
    when nothing is trending / nobody presented.
    """
    top_facets = list(
        FacetVogueMomentum.objects.filter(society=society, points__gt=0).order_by("-points")[
            :FASHION_TREND_FACET_COUNT
        ]
    )
    if not top_facets:
        return None

    top_presenter = (
        FashionPresentation.objects.filter(perceiving_society=society)
        .values("presenter")
        .annotate(total=Sum("acclaim"))
        .order_by("-total")
        .first()
    )
    if top_presenter is None:
        return None

    from world.character_sheets.models import CharacterSheet  # noqa: PLC0415

    presenter_sheet = CharacterSheet.objects.get(pk=top_presenter["presenter"])
    crowned_persona = presenter_sheet.primary_persona

    style, _created = FashionStyle.objects.get_or_create(
        name=FASHION_LIVING_STYLE_NAME_TEMPLATE.format(society=society.name),
    )
    style.in_vogue_facets.set([m.facet for m in top_facets])

    # Best-effort: wire a bonus so the new trend actually buffs presentations.
    # If the fashion ModifierTarget is unauthored, skip silently (loud warning) —
    # the crowning still happens.
    from world.mechanics.models import ModifierTarget  # noqa: PLC0415

    try:
        target = get_fashion_modifier_target()
        FashionStyleBonus.objects.get_or_create(
            fashion_style=style,
            target=target,
            defaults={"weight": 1},
        )
    except ModifierTarget.DoesNotExist:
        logger.warning(
            "Fashion ModifierTarget unauthored; crowned trendsetter for %s "
            "without a FashionStyleBonus.",
            society,
        )

    society.current_fashion_style = style
    society.save(update_fields=["current_fashion_style"])

    trendsetter = Trendsetter.objects.create(
        society=society,
        persona=crowned_persona,
        fashion_style=style,
    )
    # TODO(#514): broadcast a celebratory IC announcement of the crowning.
    logger.info("Trendsetter crowned: %s sets the vogue in %s", crowned_persona, society)
    return trendsetter


def run_all_trendsetter_ceremonies() -> list[Trendsetter]:
    """Run the ceremony for every society with positive vogue momentum (cron entry)."""
    from world.societies.models import Society  # noqa: PLC0415

    crowned: list[Trendsetter] = []
    societies = Society.objects.filter(facet_momentum__points__gt=0).distinct()
    for society in societies:
        result = run_trendsetter_ceremony(society)
        if result is not None:
            crowned.append(result)
    return crowned
