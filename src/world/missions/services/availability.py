"""Front-door availability service (Phase 5a).

``offer_missions`` is the canonical "what does this giver have for this
character right now" query. It composes the existing pieces — the Phase-0
predicate evaluator, ``select_weighted``, the per-(giver,character)
cooldown, the character's level via ``CharacterSheet.current_level``, and
the active ``stories.Era`` arc-scope rule — into one deterministic-shape
weighted draw of up to ``count`` templates. Pure service function; no
views, no serializers, no JSON in/out beyond the authored
``availability_rule`` predicate tree.

Design references: design plan §8 ("front door — availability & the giver
loop"). The percent-replace mechanic respects an active ``Era`` per draw
slot and reverts automatically when the era concludes (no lifecycle here —
we only call ``EraManager.get_active()``).
"""

from __future__ import annotations

from dataclasses import dataclass
import random
from typing import TYPE_CHECKING

from django.db.models import Q
from django.utils import timezone

from world.checks.outcome_utils import select_weighted
from world.missions.constants import ArcScope
from world.missions.predicates import CharacterPredicateContext, evaluate
from world.stories.models import Era

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.missions.models import MissionGiver, MissionTemplate


def _character_level(character: ObjectDB) -> int | None:
    """Return the acting character's level, or None if it cannot be derived.

    Uses ``CharacterSheet.current_level`` (the documented "highest level
    across all class assignments" derived field). A character without a
    sheet — i.e. a programmer-error path — yields ``None`` rather than
    raising; the caller treats ``None`` as "level-band filter skipped"
    (see ``_passes_level_band``). Played characters always have a sheet
    per character_sheets/CLAUDE.md, so this only kicks in for malformed
    test/edge cases.
    """
    from world.character_sheets.models import CharacterSheet  # noqa: PLC0415

    try:
        sheet = character.sheet_data
    except CharacterSheet.DoesNotExist:
        return None
    return int(sheet.current_level)


def _passes_level_band(
    template: MissionTemplate,
    character_level: int | None,
    risk_dial: int,
) -> bool:
    """True if the character's level sits in the template band (widened by risk_dial).

    Rule: ``level_band_min <= character_level <= level_band_max + risk_dial``.
    The risk dial lifts ONLY the upper bound — design §8 "the player has a
    risk-appetite dial to stretch toward higher-risk/higher-reward". A
    negative ``risk_dial`` narrows the upper bound (we clamp at min).

    When ``character_level`` is ``None`` the filter is skipped (returns
    True) — see ``_character_level`` for why.
    """
    if character_level is None:
        return True
    upper = max(template.level_band_min, template.level_band_max + risk_dial)
    return template.level_band_min <= character_level <= upper


def _arc_scope_matches(template: MissionTemplate, giver: MissionGiver) -> bool:
    """True if ``template``'s ``arc_scope`` covers ``giver``.

    GLOBAL — always; ORG — when ``giver.org`` matches the template's
    authored organization (we use the giver's org as the org of record,
    since templates carry no per-org FK in Phase 5a — see DESIGN note);
    GIVER — when this template is explicitly attached to this giver
    (``giver.templates.filter(pk=template.pk)``).
    """
    if template.arc_scope == ArcScope.GLOBAL:
        return True
    if template.arc_scope == ArcScope.ORG:
        # DESIGN: Phase 5a treats ORG-scope as "applies via a giver that
        # fronts for ANY organization". A future per-template org FK would
        # let us require exact match; until then we approximate with
        # "giver.org is not null" (an ORG arc by definition needs an
        # org-fronting giver).
        return giver.org_id is not None
    if template.arc_scope == ArcScope.GIVER:
        return giver.templates.filter(pk=template.pk).exists()
    return False


def _eligible_templates(
    giver: MissionGiver,
    character: ObjectDB,
    risk_dial: int,
    *,
    arc_filter: bool,
    active_era: Era | None,
) -> list[MissionTemplate]:
    """Compute the eligible draw pool.

    Shared by both the ambient and arc-eligible sub-pools — ``arc_filter``
    flips the era/arc-scope narrowing on or off. Filters applied (all
    ``AND``):

      * the giver's authored ``templates`` M2M, ``is_active``
      * NOT under a live cooldown for this character
      * Phase-0 ``availability_rule`` predicate evaluates True
      * level band (widened by ``risk_dial``); skipped when level is None
      * (arc_filter only) ``created_in_era == active_era`` AND
        ``_arc_scope_matches(template, giver)``
    """
    now = timezone.now()
    qs = giver.templates.filter(is_active=True).exclude(
        Q(givers__standings__character=character)
        & Q(givers__standings__giver=giver)
        & Q(givers__standings__available_at__gt=now),
    )
    if arc_filter and active_era is not None:
        qs = qs.filter(created_in_era=active_era)
    elif arc_filter:
        # arc_filter requested but no active era — empty subpool.
        return []

    ctx = CharacterPredicateContext(character)
    level = _character_level(character)

    eligible: list[MissionTemplate] = []
    # SharedMemoryModel identity map — iterating the queryset materializes
    # template rows once; predicate evaluation walks already-cached FKs.
    for template in qs.distinct():
        if not evaluate(template.availability_rule or {}, ctx):
            continue
        if not _passes_level_band(template, level, risk_dial):
            continue
        if arc_filter and not _arc_scope_matches(template, giver):
            continue
        eligible.append(template)
    return eligible


@dataclass(frozen=True)
class _WeightedTemplate:
    """Thin adapter exposing ``MissionTemplate.base_weight`` as ``weight``.

    ``world.checks.outcome_utils.select_weighted`` looks up ``.weight`` on
    each item. ``MissionTemplate`` carries ``base_weight`` (the named field
    is intentional — front-door availability weight is *not* a check-
    outcome weight). This wrapper lets us reuse ``select_weighted`` without
    inventing a parallel draw function.
    """

    template: MissionTemplate
    weight: int


def _draw_without_replacement(
    pool: list[MissionTemplate],
    count: int,
) -> list[MissionTemplate]:
    """Weighted draw of up to ``count`` templates from ``pool`` without replacement.

    Weighting is by ``template.base_weight`` via ``select_weighted`` (with
    the ``_WeightedTemplate`` adapter — see its docstring for the field
    rename rationale).
    """
    drawn: list[MissionTemplate] = []
    remaining = [_WeightedTemplate(template=t, weight=max(t.base_weight, 1)) for t in pool]
    while remaining and len(drawn) < count:
        pick = select_weighted(remaining)
        drawn.append(pick.template)
        remaining.remove(pick)
    return drawn


def offer_missions(
    giver: MissionGiver,
    character: ObjectDB,
    risk_dial: int = 0,
    count: int = 5,
) -> list[MissionTemplate]:
    """Return up to ``count`` templates the giver offers this character right now.

    Pipeline (design §8):

    1. Compute the ambient eligible pool (predicate / cooldown / level /
       active+M2M); the arc-eligible pool when an Era is active and
       ``arc_scope`` covers this giver.
    2. Draw ``count`` slots without replacement from the ambient pool by
       ``base_weight``.
    3. For each drawn slot, independently roll the *picked* template's
       ``percent_replace``. On hit, draw a replacement from the
       arc-eligible pool (still respecting predicate/level/cooldown). If
       the arc-eligible pool is empty or no era is active, keep the
       ambient pick (no-op).

    Returned order is the draw order. No deduping with prior calls — each
    offer is a fresh sample (the cooldown is the durable gate that stops
    re-offers).
    """
    if count <= 0:
        return []
    active_era = Era.objects.get_active()
    ambient_pool = _eligible_templates(
        giver, character, risk_dial, arc_filter=False, active_era=active_era
    )
    if not ambient_pool:
        return []
    arc_pool = (
        _eligible_templates(giver, character, risk_dial, arc_filter=True, active_era=active_era)
        if active_era is not None
        else []
    )

    slots = _draw_without_replacement(ambient_pool, count)
    if not arc_pool:
        return slots

    # Per-slot independent percent_replace roll — the picked template's
    # own knob governs whether *this* slot gets replaced.
    arc_remaining = [_WeightedTemplate(template=t, weight=max(t.base_weight, 1)) for t in arc_pool]
    final: list[MissionTemplate] = []
    for picked in slots:
        # random.random is fine here; gameplay weighting, not crypto.
        if (
            arc_remaining
            and picked.percent_replace > 0
            and random.random() * 100.0 < picked.percent_replace  # noqa: S311
        ):
            replacement = select_weighted(arc_remaining)
            arc_remaining.remove(replacement)
            final.append(replacement.template)
        else:
            final.append(picked)
    return final
