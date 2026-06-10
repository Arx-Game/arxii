"""#742 — Diegetic ranking display services (#676 Phase I).

Read-side queries and rendering for the in-world ranking displays
(heralds, plaques, academy boards):

* ``get_society_prestige_top_n`` / ``get_academy_legend_top_n`` — runtime
  queries that return the top-N rows for the herald to read aloud.
* ``render_ranking_display`` — the typeclass ``return_appearance`` hook
  uses this. Gates ``SOCIETY_PRESTIGE`` rankings against the viewer's
  society membership.

Author-visible IC prose is tagged ``PLACEHOLDER`` so the user can grep
and rewrite it in their own voice.
"""

from __future__ import annotations

from dataclasses import dataclass

from world.societies.constants import FAME_TIER_MULTIPLIERS, FAME_TIER_ORDER
from world.societies.models import (
    OrganizationMembership,
    PersonaLegendSummary,
    RankingBandLabel,
    RankingDisplay,
)


@dataclass(frozen=True)
class RankingRow:
    """One row in a rendered ranking. ``rank`` is 1-based dense rank.

    ``value`` is the ordering quantity and is INTERNAL ONLY — it must
    never render (#761; hidden-mechanics rule). ``band_label`` is the
    qualitative phrase the world speaks ("" when no band is authored).
    """

    rank: int
    persona_name: str
    value: float
    band_label: str = ""


def band_labels_for(society) -> list[RankingBandLabel]:
    """Active band labels for ``society``, falling back to the global set.

    Per-society rows win when ANY exist; otherwise the ``society=null``
    global/default rows apply (also the Academy's set). No authored rows
    → empty list → boards render plain ordered names.
    """
    if society is not None:
        scoped = list(
            RankingBandLabel.objects.filter(society=society, is_active=True).order_by(
                "rank_min", "pk"
            )
        )
        if scoped:
            return scoped
    return list(
        RankingBandLabel.objects.filter(society__isnull=True, is_active=True).order_by(
            "rank_min", "pk"
        )
    )


def _label_for_rank(rank: int, bands: list[RankingBandLabel]) -> str:
    for band in bands:
        if band.rank_min <= rank <= band.rank_max:
            return band.label
    return ""


def _perceived_multiplier(fame_tier: str, society) -> float:
    """The fame-tier prestige multiplier as ``society`` perceives it (#761).

    Applies the society's ``fame_perception_offset`` to the tier before
    looking up the multiplier — the same lens the renown tab applies
    (``renown_serializers._apply_perception_offset``), so the diegetic
    board and the tab can no longer disagree.
    """
    offset = (society.fame_perception_offset or 0) if society is not None else 0
    tier_index = FAME_TIER_ORDER.index(fame_tier)
    adjusted = FAME_TIER_ORDER[max(0, tier_index + offset)]
    return FAME_TIER_MULTIPLIERS[adjusted]


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------


def get_society_prestige_top_n(society, *, n: int = 10) -> list[RankingRow]:
    """Top-N members of ``society`` by PERCEIVED prestige (#761).

    Ordering quantity = ``total_prestige × fame-tier multiplier``, where
    the tier is read through the society's ``fame_perception_offset`` —
    the same lens the renown tab uses, fixing the board/tab disagreement
    (#761 gap 2). Computed in Python over the member set (the boards are
    top-N reads at human frequency; revisit with a query-time expression
    if member counts ever make this hot). The numeric value stays
    internal — only the qualitative band label ever renders.
    """
    from world.scenes.models import Persona  # noqa: PLC0415

    members = Persona.objects.filter(
        pk__in=OrganizationMembership.objects.filter(organization__society=society).values_list(
            "persona_id", flat=True
        )
    )
    scored = sorted(
        ((p.total_prestige * _perceived_multiplier(p.fame_tier, society), p.name) for p in members),
        key=lambda pair: (-pair[0], pair[1]),
    )[:n]
    bands = band_labels_for(society)
    return [
        RankingRow(
            rank=index,
            persona_name=name,
            value=score,
            band_label=_label_for_rank(index, bands),
        )
        for index, (score, name) in enumerate(scored, start=1)
    ]


def get_academy_legend_top_n(*, n: int = 10) -> list[RankingRow]:
    """Top-N personas by ``persona_legend`` across all realms.

    Reads ``PersonaLegendSummary`` MV. Public ranking (Legend is
    magical and universally known per spec), so no viewer gate.
    """
    rows = list(
        PersonaLegendSummary.objects.select_related("persona").order_by(
            "-persona_legend", "persona__name"
        )[:n]
    )
    bands = band_labels_for(None)
    return [
        RankingRow(
            rank=position,
            persona_name=row.persona.name,
            value=row.persona_legend,
            band_label=_label_for_rank(position, bands),
        )
        for position, row in enumerate(rows, start=1)
    ]


def viewer_is_member_of_society(viewer_persona, society) -> bool:
    """True iff ``viewer_persona`` holds any membership in an org in ``society``.

    Per spec: per-society rankings are gated by the viewer's society
    membership ("you see what your character would know"). The viewer's
    persona must currently belong to at least one organization whose
    ``Organization.society`` equals the scoped society.
    """
    if viewer_persona is None or society is None:
        return False
    return OrganizationMembership.objects.filter(
        persona=viewer_persona,
        organization__society=society,
    ).exists()


# ---------------------------------------------------------------------------
# Render
# ---------------------------------------------------------------------------


_EMPTY_NARRATION = "The display shows no names worth recording."
_CLOAKED_NARRATION = (
    "PLACEHOLDER: The herald glances past you. Whatever names are on the scroll "
    "are meant for ears that belong to this society — you would know none of them."
)


def render_ranking_display(display: RankingDisplay, viewer_persona) -> str:
    """Render ``display`` for ``viewer_persona``. Returns IC prose text.

    Per spec:
    * ``SOCIETY_PRESTIGE`` is gated — the viewer must be a member of
      the scoped society to see anything. Non-members get a cloaked
      message (they see that there IS a ranking, but no names).
    * ``ACADEMY_LEGEND`` is public — anyone can read it.

    All prose is tagged ``PLACEHOLDER`` so the user can grep + rewrite
    in their own voice.
    """
    if display.ranking_type == RankingDisplay.RankingType.SOCIETY_PRESTIGE:
        return _render_society_prestige(display, viewer_persona)
    if display.ranking_type == RankingDisplay.RankingType.ACADEMY_LEGEND:
        return _render_academy_legend(display)
    return _EMPTY_NARRATION


def _render_society_prestige(display: RankingDisplay, viewer_persona) -> str:
    if display.scope_society is None:
        return _EMPTY_NARRATION
    if not viewer_is_member_of_society(viewer_persona, display.scope_society):
        return _CLOAKED_NARRATION
    rows = get_society_prestige_top_n(display.scope_society, n=display.top_n)
    if not rows:
        return _EMPTY_NARRATION
    society_name = display.scope_society.name
    return _format_rows(
        header=f"PLACEHOLDER: The herald reads aloud — '{society_name}' top {len(rows)}:",
        rows=rows,
    )


def _render_academy_legend(display: RankingDisplay) -> str:
    rows = get_academy_legend_top_n(n=display.top_n)
    if not rows:
        return _EMPTY_NARRATION
    return _format_rows(
        header=f"PLACEHOLDER: Engraved tablets shimmer — the {len(rows)} most-legendary:",
        rows=rows,
    )


def _format_rows(*, header: str, rows: list[RankingRow]) -> str:
    """Format a ranking as IC narration — names + qualitative bands ONLY.

    The world never speaks raw numbers (#761; exact figures live in the
    player's own ledger, never in an IC mouth). With no authored band
    labels the board reads as a plain ordered list of names.
    """
    lines = [header]
    for row in rows:
        suffix = f" — {row.band_label}" if row.band_label else ""
        lines.append(f"  {row.persona_name}{suffix}")
    return "\n".join(lines)
