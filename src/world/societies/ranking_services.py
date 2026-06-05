"""#742 — Diegetic ranking display services (#676 Phase I).

Read-side queries and rendering for the in-world ranking displays
(heralds, plaques, academy boards). Three responsibilities:

* ``get_society_prestige_top_n`` / ``get_academy_legend_top_n`` — read
  the materialized views and return the top-N rows for the herald to
  read aloud (or the plaque to engrave, etc.).
* ``render_ranking_display`` — the main entry point used by the
  typeclass ``return_appearance`` hook. Dispatches on ``ranking_type``
  and gates ``SOCIETY_PRESTIGE`` rankings against the viewer's society
  membership.
* ``refresh_society_prestige_ranking`` — wraps the
  ``REFRESH MATERIALIZED VIEW CONCURRENTLY`` SQL the nightly cron runs.

Author-visible IC prose is tagged ``PLACEHOLDER`` so the user can grep
and rewrite it in their own voice.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging

from django.db import connection, transaction

from world.societies.models import (
    OrganizationMembership,
    PersonaLegendSummary,
    RankingDisplay,
    SocietyPrestigeRanking,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RankingRow:
    """One row in a rendered ranking. ``rank`` is 1-based DENSE_RANK."""

    rank: int
    persona_name: str
    value: int


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------


def get_society_prestige_top_n(society, *, n: int = 10) -> list[RankingRow]:
    """Top-N personas by ``displayed_prestige`` in ``society``.

    Reads ``SocietyPrestigeRanking`` MV. Empty list when the MV is
    empty (no members, or the cron hasn't run yet, or — on SQLite —
    the MV doesn't exist).
    """
    rows = list(
        SocietyPrestigeRanking.objects.filter(society=society)
        .select_related("persona")
        .order_by("rank", "persona__name")[:n]
    )
    return [
        RankingRow(rank=row.rank, persona_name=row.persona.name, value=row.displayed_prestige)
        for row in rows
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


# ---------------------------------------------------------------------------
# Refresh (nightly cron)
# ---------------------------------------------------------------------------


@transaction.atomic
def refresh_society_prestige_ranking() -> None:
    """Refresh the ``societies_societyprestigeranking`` materialized view.

    Uses ``REFRESH MATERIALIZED VIEW CONCURRENTLY`` — supported because
    the migration includes a unique index on ``(society, persona)``.
    CONCURRENTLY lets readers continue to query the view during refresh,
    which matters at scale; at the dev tier it just means we don't
    block the cron tick.

    On SQLite (test tier) this is a no-op: materialized views don't
    exist on SQLite. The vendor check keeps the cron task functional
    when running under either backend.
    """
    if connection.vendor != "postgresql":  # noqa: STRING_LITERAL
        logger.info("ranking.refresh: skipped — backend is %s", connection.vendor)
        return
    with connection.cursor() as cursor:
        cursor.execute("REFRESH MATERIALIZED VIEW CONCURRENTLY societies_societyprestigeranking;")
    logger.info("ranking.refresh: society_prestige_ranking refreshed")
