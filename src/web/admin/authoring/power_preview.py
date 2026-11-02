"""The power preview: a technique's DE with and without a vow's added effects (#4930).

Slice 6 of #4843. The vow page's rail and the kit view's Preview column read it. Each
figure is ``evaluate_technique``'s ``baseline_de`` (damage equivalent per cast, the
technique's own power, no fully matched anchor) at the Techniques tuning panel's default
context and reference (``technique_analytics.default_context_and_reference``), rounded
to a whole number for display. The vow's effects are priced by the evaluator's vow term
at a stated thread level; situational perks, stat scaling and the vow's specialty power
are not priced.

Query discipline: one context/reference read (cached), then the evaluator's own
per-technique cost. A technique's payloads are prefetched once and its rows are read
from the cached lists, so pricing it again with another set of effects costs nothing for
damage; an applied condition costs the evaluator's per-row lookups each time.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from typing import TYPE_CHECKING
from urllib.parse import urlencode

from django.urls import reverse

from web.admin.tuning import technique_analytics
from world.covenants.added_effects import (
    effect_rides_technique,
    payload_prefetches,
    techniques_by_function,
)
from world.covenants.models import VowAddedEffect
from world.magic.models import Technique
from world.magic.services import de_valuation, technique_power_eval
from world.magic.services.technique_effects import technique_payload_prefetches

if TYPE_CHECKING:
    from world.covenants.models import CovenantRole, VowFocusPick
    from world.magic.services.de_valuation import MatchupBand
    from world.magic.types.technique_power import EvalContext, ReferenceFrame

#: How many techniques the vow page's rail prices; the rest are counted.
PREVIEW_TECHNIQUES = 3

#: The line under the figures: what DE is, and where the party view lives.
EXPLANATION = (
    "DE is damage equivalent per cast, from the technique power evaluator. Run the fight "
    "simulator for party win rate with the vow on and off."
)
NOT_PRICED = "Situational perks and stat scaling are not priced."


@dataclass(frozen=True)
class PreviewFrame:
    """One evaluation run's context, reference, bands, power delta and multiplier cache."""

    context: EvalContext
    reference: ReferenceFrame
    bands: list[MatchupBand]
    amplified_delta: int
    multiplier_cache: dict[int, Decimal] = field(default_factory=dict)


def preview_frame() -> PreviewFrame:
    """The Techniques panel's default context and reference, with its bands, read once."""
    context, reference = technique_analytics.default_context_and_reference()
    return PreviewFrame(
        context=context,
        reference=reference,
        bands=de_valuation.matchup_bands(context),
        amplified_delta=technique_power_eval.amplified_power_delta(context),
    )


def preview_de(
    technique: Technique,
    frame: PreviewFrame,
    effects: Sequence[VowAddedEffect] = (),
    level: int = 0,
) -> int:
    """``technique``'s baseline DE with ``effects`` at shown thread level ``level``, rounded."""
    report = technique_power_eval.evaluate_technique(
        technique,
        frame.context,
        frame.reference,
        _multiplier_cache=frame.multiplier_cache,
        _bands=frame.bands,
        _amplified_delta=frame.amplified_delta,
        vow_effects=effects,
        vow_thread_level=level,
    )
    return round(report.baseline_de)


def priced_techniques(pks: Sequence[int]) -> dict[int, Technique]:
    """The techniques ``pks`` name, with every payload the evaluator reads: fixed queries."""
    rows = (
        Technique.objects.filter(pk__in=pks)
        .select_related("gift", "effect_type")
        .prefetch_related(*technique_payload_prefetches())
    )
    return {technique.pk: technique for technique in rows}


@dataclass(frozen=True)
class PreviewLine:
    """One figure: what is priced, and its DE."""

    label: str
    de: int


@dataclass(frozen=True)
class TechniquePreview:
    """One technique the vow rides, priced with no vow, the base vow, and each pick."""

    name: str
    url: str
    lines: list[PreviewLine]
    #: Blank for a technique with no action template: the fight simulator cannot cast it.
    simulator_url: str


@dataclass(frozen=True)
class VowPreview:
    """The vow page's Power preview module.

    ``level`` is the stated preview thread level and ``level_note`` says where it comes
    from. ``more`` counts the techniques the vow rides past the priced ones.
    """

    level: int
    level_note: str
    techniques: list[TechniquePreview]
    more: int
    explanation: str = EXPLANATION
    not_priced: str = NOT_PRICED


def simulator_url(technique: Technique, role: CovenantRole) -> str:
    """The Game Tuning dashboard with the simulation form filled for this technique and vow."""
    query = urlencode({"technique": technique.pk, "covenant_role": role.pk})
    return f"{reverse('admin_tuning')}?{query}#panel-simulation"


def _preview_level(picks: Sequence[VowFocusPick]) -> tuple[int, str]:
    if not picks:
        return 1, "Level 1: the vow has no focus picks."
    level = max(pick.pick_level for pick in picks)
    return level, f"Level {level}: the vow's highest pick level."


def _ridden(
    effects: Sequence[VowAddedEffect],
) -> tuple[list[Technique], dict[int, set[str]]]:
    """Every technique an effect rides, by name, with the functions it carries among them."""
    by_function = techniques_by_function({effect.function for effect in effects})
    functions: dict[int, set[str]] = {}
    techniques: dict[int, Technique] = {}
    for function, rows in by_function.items():
        for technique in rows:
            functions.setdefault(technique.pk, set()).add(function)
            techniques[technique.pk] = technique
    ridden = [
        technique
        for technique in techniques.values()
        if any(effect_rides_technique(e, technique, functions[technique.pk]) for e in effects)
    ]
    return sorted(ridden, key=lambda t: (t.name, t.pk)), functions


def vow_power_preview(role: CovenantRole) -> VowPreview:
    """The Power preview for one vow: its first techniques by name, each priced per variant.

    The techniques are the ones the vow's added effects ride (the effect rows of
    "Techniques this vow rides"). Per technique: no vow; the base vow (rows with no focus
    pick that ride it); then each pick with a row riding it, as the base plus that pick.
    One query for the effects (four payload prefetches), one for the function tags, one
    plus the payload prefetches for the priced techniques, one for the picks, then the
    evaluator's own cost per figure.
    """
    from world.covenants.models import VowFocusPick  # noqa: PLC0415

    effects = list(
        VowAddedEffect.objects.filter(covenant_role=role)
        .select_related("focus_pick")
        .prefetch_related(*payload_prefetches())
    )
    picks = list(VowFocusPick.objects.filter(covenant_role=role).order_by("pick_level", "name"))
    level, note = _preview_level(picks)
    ridden, functions = _ridden(effects)
    shown = ridden[:PREVIEW_TECHNIQUES]
    if not shown:
        return VowPreview(level=level, level_note=note, techniques=[], more=0)
    priced = priced_techniques([t.pk for t in shown])
    frame = preview_frame()
    previews = []
    for listed in shown:
        technique = priced[listed.pk]
        riding = [
            e for e in effects if effect_rides_technique(e, technique, functions[technique.pk])
        ]
        base = [e for e in riding if e.focus_pick_id is None]
        lines = [
            PreviewLine(label="no vow", de=preview_de(technique, frame)),
            PreviewLine(
                label=f"with base vow, level {level}",
                de=preview_de(technique, frame, base, level),
            ),
        ]
        for pick in picks:
            own = [e for e in riding if e.focus_pick_id == pick.pk]
            if own:
                lines.append(
                    PreviewLine(
                        label=f"with {pick.name}",
                        de=preview_de(technique, frame, [*base, *own], level),
                    )
                )
        previews.append(
            TechniquePreview(
                name=technique.name,
                url=reverse("admin:arxii_technique_change", args=[technique.pk]),
                lines=lines,
                simulator_url=(
                    simulator_url(technique, role) if technique.action_template_id else ""
                ),
            )
        )
    return VowPreview(
        level=level, level_note=note, techniques=previews, more=len(ridden) - len(shown)
    )
