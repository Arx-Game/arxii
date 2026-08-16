"""Authoring backlog: one flat worst-first queue across every credited model (#3019).

``build_backlog`` scans every model ``credited_content_models()`` returns, skips
the ones with no prose fields at all, and pulls one row per instance with exactly
one ``values_list`` per model (pk, natural-key field values, the two credit FK
ids, and every prose field value). An FK-typed natural-key field spans one hop
into the related row's own first natural-key field (see ``_display_column``) so
the identity string shows a name, not a raw related pk - still one query per
model, since the span becomes a SQL join rather than a per-row lookup. Rows sort
worst-first: placeholder-marked first, then unwritten, then unreviewed - so the
top of the queue is always the thing most worth a writer's attention next.

Within a worst-first tier rows group by domain, then by model, then by pk. The
model term is what keeps a tier readable: sorting a tier straight to identity
interleaves every model in the domain into one alphabetical soup, so a writer
scrolling `magic` used to meet an `EffectType`, then a `PortalAnchorKind`, then
a `Technique`, with no two adjacent rows sharing a shape. Grouping by model
keeps like with like, and pk within a model is authoring order - the sequence
the rows were actually written in, which for an ordered set like
``OriginTemplateSlot`` tracks its own ``sort_order``. Alphabetical-by-identity
is arbitrary even inside one model, so it is not the tiebreak anywhere.

A model still appears in up to three separate clumps down the page, one per
tier; the queue panel's model filter (`web.admin.authoring.views`) is what
collapses that to a single model's rows, worst-first, with nothing else
interleaved.

Scale ceiling: today's corpus is on the order of 2k rows and 70k prose words
across credited models, and this whole module does one full Python-side scan
and sort per call with no caching - fine at that size. If the corpus grows an
order of magnitude beyond that, this needs either a cache or a DB-side
aggregation instead of a full re-scan per request.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from core.app_domains import credited_content_models, domain_of
from core_management.content_export import _natural_key_fields
from core_management.content_fixtures import PLACEHOLDER_MARK
from core_management.prose_fields import prose_fields_for

if TYPE_CHECKING:
    from django.db.models import QuerySet


@dataclass
class BacklogRow:
    """One credited-model instance's place in the authoring backlog."""

    model_label: str
    model_name: str
    domain: str
    pk: int
    identity: str
    words: int
    has_placeholder: bool
    written: bool
    reviewed: bool


@dataclass
class DomainStats:
    """Per-domain rollup of the backlog rows scanned for that domain."""

    domain: str
    rows: int
    unwritten: int
    unreviewed: int
    words_total: int
    words_unwritten: int


def _display_column(model: type, field_name: str) -> str:
    """Return the ``values_list`` column that displays one natural-key field.

    A scalar field displays as itself. An FK-typed field spans one hop into
    the related row's own first natural-key field instead - a bare related
    pk ("5, Sleeper") tells a writer nothing, while "The Sleeper's Rest,
    Sleeper" does. Only one hop: composite related keys use just the related
    model's first field, and a related field that is itself FK-typed is left
    as its raw id rather than resolved recursively. This is a display
    string, not an identity computation, and one legible component beats an
    id - full recursive resolution is not worth the complexity here.
    """
    field = model._meta.get_field(field_name)  # noqa: SLF001
    if not field.is_relation:
        return field_name
    related_key_fields = _natural_key_fields(field.related_model)
    if not related_key_fields:
        return field_name
    return f"{field_name}__{related_key_fields[0]}"


def _row_identity(pk: int, key_fields: list[str] | None, key_values: tuple) -> str:
    """Natural-key display string for one row, falling back to ``str(pk)``.

    Mirrors the ``", ".join(str(v) for v in ...)`` idiom used at
    ``content_conflict_views._locate_corpus_entry`` and
    ``content_export.export_single_row`` for the same "how do we show a row's
    identity" question. ``key_values`` are already display-resolved (see
    ``_display_column``) by the time they reach here.
    """
    if not key_fields:
        return str(pk)
    return ", ".join(str(v) for v in key_values)


def _rows_for_model(model: type, scope: Callable[[QuerySet], QuerySet] | None) -> list[BacklogRow]:
    prose_names = prose_fields_for(model)
    if not prose_names:
        return []

    key_fields = _natural_key_fields(model)
    key_count = len(key_fields) if key_fields else 0
    key_columns = [_display_column(model, name) for name in (key_fields or [])]
    columns = ["pk", *key_columns, "written_by_id", "reviewed_by_id", *prose_names]

    queryset = model.objects.all()
    if scope is not None:
        queryset = scope(queryset)

    domain = domain_of(model)
    model_name = model.__name__
    model_label = f"{domain}.{model_name}"

    rows: list[BacklogRow] = []
    for values in queryset.values_list(*columns):
        pk = values[0]
        key_values = values[1 : 1 + key_count]
        written_by_id = values[1 + key_count]
        reviewed_by_id = values[2 + key_count]
        prose_values = values[3 + key_count :]

        words = sum(len(str(v).split()) for v in prose_values if v)
        has_placeholder = any(isinstance(v, str) and PLACEHOLDER_MARK in v for v in prose_values)

        rows.append(
            BacklogRow(
                model_label=model_label,
                model_name=model_name,
                domain=domain,
                pk=pk,
                identity=_row_identity(pk, key_fields, key_values),
                words=words,
                has_placeholder=has_placeholder,
                written=written_by_id is not None,
                reviewed=reviewed_by_id is not None,
            )
        )
    return rows


def _aggregate(rows: list[BacklogRow]) -> list[DomainStats]:
    counts: dict[str, dict[str, int]] = {}
    for row in rows:
        tally = counts.setdefault(
            row.domain,
            {"rows": 0, "unwritten": 0, "unreviewed": 0, "words_total": 0, "words_unwritten": 0},
        )
        tally["rows"] += 1
        tally["words_total"] += row.words
        if not row.written:
            tally["unwritten"] += 1
            tally["words_unwritten"] += row.words
        if not row.reviewed:
            tally["unreviewed"] += 1
    return sorted(
        (DomainStats(domain=domain, **tally) for domain, tally in counts.items()),
        key=lambda s: s.domain,
    )


def build_backlog(
    scope: Callable[[QuerySet], QuerySet] | None = None,
) -> tuple[list[BacklogRow], list[DomainStats]]:
    """Scan every credited content model once and return rows plus per-domain stats.

    ``scope``, when given, is applied to every model's queryset before it is
    read - the seam a GM-restricted variant of the workbench can use to narrow
    the backlog without this module knowing anything about who's asking.
    """
    rows: list[BacklogRow] = []
    for model in credited_content_models():
        rows.extend(_rows_for_model(model, scope))

    rows.sort(
        key=lambda r: (
            not r.has_placeholder,
            r.written,
            r.reviewed,
            r.domain,
            r.model_name,
            r.pk,
        )
    )
    return rows, _aggregate(rows)
