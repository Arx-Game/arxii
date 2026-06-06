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

from world.societies.models import (
    OrganizationMembership,
    PersonaLegendSummary,
    RankingDisplay,
)


@dataclass(frozen=True)
class RankingRow:
    """One row in a rendered ranking. ``rank`` is 1-based dense rank."""

    rank: int
    persona_name: str
    value: int


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------


def get_society_prestige_top_n(society, *, n: int = 10) -> list[RankingRow]:
    """Top-N personas by ``total_prestige`` among members of ``society``.

    Runtime aggregate over members. We don't apply the fame-tier
    multiplier here at MVP — the MV had it baked in but at our scale a
    raw-total ordering is fine and lets us drop the MV + nightly cron.
    A future scale-driven re-introduction can multiply at query time.
    """
    from world.scenes.models import Persona  # noqa: PLC0415

    personas = list(
        Persona.objects.filter(
            pk__in=OrganizationMembership.objects.filter(organization__society=society).values_list(
                "persona_id", flat=True
            )
        ).order_by("-total_prestige", "name")[:n]
    )
    return [
        RankingRow(rank=index, persona_name=p.name, value=p.total_prestige)
        for index, p in enumerate(personas, start=1)
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
    return [
        RankingRow(
            rank=position,
            persona_name=row.persona.name,
            value=row.persona_legend,
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
    """Format a ranking as IC narration. Newline-separated; rank prefix."""
    lines = [header, *[f"  {row.rank}. {row.persona_name} ({row.value:,})" for row in rows]]
    return "\n".join(lines)
