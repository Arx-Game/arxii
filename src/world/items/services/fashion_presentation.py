"""Service: fashion presentation + peer judging (Outfits Phase C, #514).

A character ``present_outfit`` at an event hosted by a society; the society's
*taste* (its current FashionStyle's in-vogue facets) shapes the difficulty, and
the character's worn items feed a perception-relative fashion bonus into a
graded check. The graded outcome floors the presentation's ``base_score``.

Peers then ``judge_presentation``; each endorsement is heavily weighted into the
presentation's ``acclaim``, which rolls up into the presenter's primary
persona's ``prestige_from_fashion`` (and thence ``total_prestige``).

Deferred (YAGNI): the presentation outcome is a single graded grade, not a
ConsequencePool resolution. Masquerade-aware attribution credits the presenter's
PRIMARY persona for now; crediting the *presented* persona is a future
follow-up.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import IntegrityError, transaction

from world.checks.models import CheckType
from world.checks.services import perform_check
from world.items.constants import (
    FASHION_PRESENTATION_BASE_DIFFICULTY,
    FASHION_PRESENTATION_CHECK_TYPE_NAME,
    FASHION_PRESENTATION_ENDORSEMENT_WEIGHT,
    get_fashion_modifier_target,
)
from world.items.exceptions import FashionPresentationError
from world.items.models import FashionPresentation
from world.items.services.trendsetter import bump_vogue_momentum
from world.magic.models.endorsement import PresentationEndorsement
from world.magic.services.gain import account_for_sheet
from world.mechanics.services import get_modifier_total

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.checks.types import CheckResult
    from world.events.models import Event
    from world.items.models import Outfit
    from world.scenes.models import Persona
    from world.societies.models import Society


def _score_from_outcome(check_result: CheckResult) -> int:
    """Floor a graded check outcome at zero.

    ``success_level`` is the graded tier (e.g. 3/2/1/0/-1/-2). A botch must not
    produce negative acclaim, so the floor is zero. (YAGNI: a richer
    ConsequencePool resolution is deferred.)
    """
    return max(0, check_result.success_level)


def _difficulty_from_taste(society: Society) -> int:
    """Derive the presentation difficulty from the society's current taste.

    Base difficulty plus one point per in-vogue facet in the society's current
    fashion style — a richer, more saturated trend is harder to impress. With
    no current style, only the authored base difficulty applies. Difficulty is
    never a bare per-call constant: it derives from the authored facets.
    """
    style = society.current_fashion_style
    if style is None:
        return FASHION_PRESENTATION_BASE_DIFFICULTY
    return FASHION_PRESENTATION_BASE_DIFFICULTY + style.in_vogue_facets.count()


@transaction.atomic
def present_outfit(
    presenter: CharacterSheet,
    event: Event,
    outfit: Outfit | None = None,
) -> FashionPresentation:
    """Record ``presenter`` modelling an outfit at ``event``, judged by its host.

    The host society's taste shapes the difficulty; the presenter's worn items
    feed a perception-relative fashion bonus into the graded presentation check.
    The graded outcome floors ``base_score`` (== initial ``acclaim``).

    Args:
        presenter: The CharacterSheet presenting.
        event: The Event being presented at; its ``host_society`` judges.
        outfit: Optional record-keeping FK; the check reads equipped items, not
            this FK.

    Returns:
        The created FashionPresentation row.

    Raises:
        FashionPresentationError: The event has no host society to judge.
    """
    society = event.host_society
    if society is None:
        msg = "This event has no host society to judge fashion."
        raise FashionPresentationError(msg)

    target = get_fashion_modifier_target()
    bonus = get_modifier_total(presenter, target, perceiving_society=society)
    difficulty = _difficulty_from_taste(society)
    check_type = CheckType.objects.get(name=FASHION_PRESENTATION_CHECK_TYPE_NAME)

    result = perform_check(
        presenter.character,
        check_type,
        target_difficulty=difficulty,
        extra_modifiers=bonus,
    )
    base = _score_from_outcome(result)

    return FashionPresentation.objects.create(
        event=event,
        presenter=presenter,
        outfit=outfit,
        perceiving_society=society,
        base_score=base,
        acclaim=base,
    )


@transaction.atomic
def judge_presentation(
    judge: CharacterSheet,
    presentation: FashionPresentation,
) -> PresentationEndorsement:
    """Record ``judge`` endorsing ``presentation`` and roll up the effects.

    Creates a ``PresentationEndorsement``, recomputes the presentation's
    ``acclaim`` (heavily weighted by peer endorsements), and folds the result
    into the presenter's primary persona's fashion prestige.

    Args:
        judge: The CharacterSheet doing the judging.
        presentation: The presentation being judged.

    Returns:
        The created PresentationEndorsement.

    Raises:
        FashionPresentationError: Self-judging, alt-judging, or a duplicate.
    """
    presenter = presentation.presenter
    if judge == presenter:
        msg = "You cannot judge your own presentation."
        raise FashionPresentationError(msg)

    judge_account = account_for_sheet(judge)
    presenter_account = account_for_sheet(presenter)
    if judge_account is not None and judge_account == presenter_account:
        msg = "You cannot judge a presentation by your own character."
        raise FashionPresentationError(msg)

    persona = presenter.primary_persona
    try:
        with transaction.atomic():
            endorsement = PresentationEndorsement.objects.create(
                presentation=presentation,
                endorser_sheet=judge,
                endorsee_sheet=presenter,
                persona_snapshot=persona,
            )
    except IntegrityError as exc:
        msg = "You have already judged this presentation."
        raise FashionPresentationError(msg) from exc

    recompute_acclaim(presentation)
    recompute_persona_prestige_from_fashion(persona)
    bump_vogue_momentum(presentation)
    return endorsement


def recompute_acclaim(presentation: FashionPresentation) -> int:
    """Recompute and persist ``presentation.acclaim``.

    ``acclaim = base_score + WEIGHT * sum(endorsement weights)``. Returns the
    new value.
    """
    endorsement_weight = sum(e.weight for e in presentation.endorsements.all())
    presentation.acclaim = (
        presentation.base_score + FASHION_PRESENTATION_ENDORSEMENT_WEIGHT * endorsement_weight
    )
    presentation.save(update_fields=["acclaim"])
    return presentation.acclaim


def recompute_persona_prestige_from_fashion(persona: Persona) -> int:
    """Sum acclaim across the persona's presentations into its fashion prestige.

    Mirrors ``recompute_persona_prestige_from_items``: sets the axis field then
    re-sums ``total_prestige`` from all five prestige axes. Returns the new
    ``prestige_from_fashion`` value.
    """
    sheet = persona.character_sheet
    if sheet is None:
        return persona.prestige_from_fashion

    total = 0
    for presentation in FashionPresentation.objects.filter(presenter=sheet):
        total += presentation.acclaim

    if total == persona.prestige_from_fashion:
        return total

    persona.prestige_from_fashion = total
    persona.total_prestige = (
        persona.prestige_from_dwellings
        + persona.prestige_from_items
        + persona.prestige_from_orgs
        + persona.prestige_from_deeds
        + persona.prestige_from_fashion
    )
    persona.save(update_fields=["prestige_from_fashion", "total_prestige"])
    return total
