"""Authoring Workbench dashboard: worst-first backlog queue across every credited
content model (#3019).

The dashboard page (`authoring_dashboard`) renders a skeleton of two
HTMX-loaded panels - domain stats and the queue itself - both scanning the
same `build_backlog()` result (Task 2, `web.admin.authoring.backlog`). The
queue panel caps its display at 100 rows and applies `?domain=`, `?model=`,
`?status=`, and `?q=` filters over the already-sorted rows in a single
Python-side scan (no per-filter rescans, no extra DB queries -
`build_backlog()` is the only query-issuing call in either fragment). The
`?model=` options come from `_model_options`, built off those same scanned
rows and narrowed to the picked domain, so the dropdown can never offer a
model with no rows behind it. Each visible row also carries a stock-admin
change-form link (`_queue_row`): the workbench editor only exposes prose
fields, so that link is how an author reaches the row's other fields.

#3828 turned the page into a writing pass. `QueueFilters` is the one
parser/serializer of the four filter params; an absent `?status=` means
`unwritten` (To write) and `unreviewed` means written-and-not-reviewed (To
review). The queue's title carries the filtered count, its response sets
`HX-Replace-Url` so a reload keeps the filters, and each row link hands the
editor `queue=` (the filter querystring) and `pos=` (its index), which
`_queue_nav` turns into the editor's Next control: the row after this one, or
the row that shifted into its slot once a stamp has removed it.

Task 4 gates the dashboard on a linked `ContentContributor` (see
`web.admin.authoring.contributors`): an unlinked account gets the setup panel
in place of the stats/queue skeleton, and `authoring_setup` is the plain-POST
handler that panel submits to.

Task 5 (`authoring_editor` + the three POST views below) is the row editor
itself: one credited-content instance at a time, addressed by
`?model=<label>&pk=`. `_resolve_target` is the shared gate every one of the
four views runs first - unknown model, a model outside
`credited_content_models()`, or a missing row all render the same
flash-in-fragment error line instead of the form. `Save` writes only
`prose_fields_for(model)` keys present in the POST (a mechanical field
smuggled into the POST body is never assigned, even under the same key
name), then `full_clean()` + `save()` - a validation failure re-renders the
fragment with the error and saves nothing. `Save and credit` runs that same
prose save first (only if the POST actually carries prose keys), then stamps
`written_by`/`written_on` from the operator's own `ContentContributor` (see
`current_contributor`); an operator with no linked contributor gets the
setup-gate guidance instead of a stamp - the same defensive read the
dashboard gate uses, since this editor is reachable by direct URL and isn't
itself behind that gate. `Mark reviewed` only ever stamps
`reviewed_by`/`reviewed_on` - it never touches authorship, and never applies
pending prose edits, so a reviewer can confirm review without accidentally
overwriting someone else's in-flight prose edit sitting in the textarea.

Task 6 (`authoring_related_fragment` + `authoring_mentions_fragment`) adds two
read-only panels below the editor, both driven by `web.admin.authoring
.relations` and gated through the same `_resolve_target`. The related-entries
panel loads automatically (`_editor_panel.html`'s `hx-trigger="load"`); the
mentions search only runs when the operator clicks the button, since an
OR-`icontains` scan across every credited model's prose fields is real work
a page load shouldn't pay for unconditionally. Each row's links are built
here, not carried on `RelatedEntry` itself: a workbench editor link only for
neighbor models `credited_content_models()` covers (`entry.credited is not
None` is the same signal), and an admin change-form link gated on the model
actually having a registered `ModelAdmin` - three credited models
(`NPCRole`, `BuildingKind`, `DecorationKind`) carry `CreditedContent`
but were never `@admin.register`ed, so an unconditional `reverse()` there
would 500 the moment one of them turned up as a neighbor.

Task 7 (`authoring_reference`) is the dashboard-level reference search pane -
independent of any one row, driven by `web.admin.authoring.reference`. A
plain query box plus three checkboxes: DB search (every credited model's
prose, default on) and two opt-in file corpora, staff docs and the Arx I
dump (both default off - slow, and off the DB entirely). `_reference_toggle`
tells "never submitted" (the panel's first `hx-trigger="load"` fetch, no
querystring at all) from "submitted with this box unchecked" (an unchecked
HTML checkbox is simply absent from its own form's querystring) by keying
off whether `q` is present at all - `q` is always sent by the panel's own
form, checked or not, so its presence alone marks a real submission.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import HttpRequest, HttpResponse, QueryDict
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import urlencode
from django.views.decorators.http import require_POST

from core.app_domains import credited_content_models, domain_of, resolve_model_by_name
from core_management.prose_fields import prose_fields_for
from web.admin.authoring.backlog import BacklogRow, build_backlog
from web.admin.authoring.contributors import current_contributor, link_contributor
from web.admin.authoring.links import admin_change_url
from web.admin.authoring.reference import db_search, file_search, reference_roots
from web.admin.authoring.relations import RelatedEntry, prose_mentions, related_entries
from web.admin.constants import DEFAULT_BACKLOG_STATUS, BacklogStatusFilter
from web.admin.tuning.views import superuser_required
from world.character_creation.models import Beginnings, OriginTemplate
from world.contributors.models import ContentContributor
from world.distinctions.models import Distinction
from world.magic.models import GlimpseTag

_QUEUE_DISPLAY_CAP = 100

#: The four CreditedContent columns - never assignable from the prose form,
#: and never shown in the mechanical-fields summary (they get their own
#: labeled rows in the template instead).
_CREDIT_FIELD_NAMES = frozenset({"written_by", "written_on", "reviewed_by", "reviewed_on"})

_FREEZE_SENTENCE = (
    "This row is now credited: content loads will not overwrite it until the corpus catches up."
)

#: Rendered only inside the `content_exportable` branch (see
#: `_editor_panel.html`) - a non-exportable credited model (the three
#: builder-domain models) shows "This model stays in the database only..."
#: instead, so this clause must never render alongside that one (#3019
#: review: the two used to be one contradictory sentence).
_EXPORT_SENTENCE = "Export it to the content repo to close the loop."

#: HX-Trigger event name the stats/queue panels listen for (see
#: `dashboard.html`'s `hx-trigger="load, authoring-backlog-changed
#: from:body"`) so a credit or review stamp refreshes them without a full
#: page reload (#3019 review, Minor 5).
_BACKLOG_CHANGED_EVENT = "authoring-backlog-changed"


def _setup_required(request: HttpRequest) -> bool:
    return current_contributor(request.user) is None


def _builders_context() -> dict[str, object]:
    """The Builders panel's four option lists (#3675 Task 10): one query each.

    ``upbringings`` is a list of plain dicts rather than the model rows
    themselves - the panel's option text ("{beginning} - {name}") needs a
    span into a related row, and building that string here keeps the
    template from doing it (and from tripping over `Beginnings` not being in
    scope there).
    """
    return {
        "distinctions": list(Distinction.objects.filter(is_active=True).order_by("name")),
        "beginnings": list(Beginnings.objects.filter(is_active=True).order_by("name")),
        "upbringings": [
            {"pk": template.pk, "label": f"{template.beginning.name} › {template.name}"}
            for template in OriginTemplate.objects.filter(is_active=True)
            .select_related("beginning")
            .order_by("beginning__name", "name")
        ],
        "glimpse_tag_count": GlimpseTag.objects.filter(is_active=True).count(),
    }


#: The headline noun for each status: "212 to write", "60 to review" (#3828).
_COUNT_NOUNS = {
    BacklogStatusFilter.UNWRITTEN: "to write",
    BacklogStatusFilter.UNREVIEWED: "to review",
    BacklogStatusFilter.PLACEHOLDER: "with placeholder text",
    BacklogStatusFilter.ALL: "rows",
}


@dataclass(frozen=True)
class QueueFilters:
    """The queue's four filter params, parsed once and serialised back the same way.

    Every surface that carries the queue's state - the fragment's own form,
    the `HX-Replace-Url` the fragment answers with, the `queue=` param each
    row link hands the editor (#3828) - goes through this one class, so no
    two of them can disagree about what an absent `status` means.
    """

    domain: str = ""
    model: str = ""
    status: str = DEFAULT_BACKLOG_STATUS
    query: str = ""

    @classmethod
    def from_params(cls, params: QueryDict) -> QueueFilters:
        return cls(
            domain=params.get("domain") or "",
            model=params.get("model") or "",
            status=params.get("status") or DEFAULT_BACKLOG_STATUS,
            query=(params.get("q") or "").strip(),
        )

    def as_query(self) -> str:
        """Urlencoded form, omitting empties and the default status - the URL a reload sees."""
        pairs = {"domain": self.domain, "model": self.model, "q": self.query}
        if self.status != DEFAULT_BACKLOG_STATUS:
            pairs["status"] = self.status
        return urlencode({key: value for key, value in pairs.items() if value})

    @property
    def count_noun(self) -> str:
        return _COUNT_NOUNS.get(self.status, "rows")

    @property
    def scope_label(self) -> str:
        return self.domain or "all domains"

    def matches(self, row: BacklogRow) -> bool:
        """One row's pass/fail against every active filter, checked in one call.

        Called from a single list comprehension over the full row list in
        `_filtered_rows`, so the combined filter set is one scan regardless of
        how many filters are actually set.
        """
        if self.domain and row.domain != self.domain:
            return False
        if self.model and row.model_label != self.model:
            return False
        if self.query and self.query.lower() not in row.identity.lower():
            return False
        return _status_matches(row, self.status)


def _status_matches(row: BacklogRow, status: str) -> bool:
    """One row against the status filter alone; `all` or an unknown value matches every row.

    Split out of `QueueFilters.matches` so neither carries a branch per
    filter *and* a branch per status value - the combined form tripped
    ruff's return-count ceiling once the model filter joined it.
    """
    if status == BacklogStatusFilter.PLACEHOLDER:
        return row.has_placeholder
    if status == BacklogStatusFilter.UNWRITTEN:
        return not row.written
    if status == BacklogStatusFilter.UNREVIEWED:
        return row.written and not row.reviewed
    return True


def _filtered_rows(rows: list[BacklogRow], filters: QueueFilters) -> list[BacklogRow]:
    return [row for row in rows if filters.matches(row)]


def _model_options(rows: list[BacklogRow], domain: str) -> list[dict]:
    """The `<option>` set for the model filter, narrowed to `domain` when one is picked.

    Built off the same already-scanned `rows` the queue renders, so the
    dropdown can never offer a model the backlog has no rows for. Each option
    carries the full `domain.Model` label as its value (`model_label` is what
    `_row_matches` compares) but shows the bare model name, since the domain
    is already its own adjacent filter.
    """
    seen: dict[str, str] = {}
    for row in rows:
        if domain and row.domain != domain:
            continue
        seen.setdefault(row.model_label, row.model_name)
    return [
        {"label": label, "name": name} for label, name in sorted(seen.items(), key=lambda p: p[1])
    ]


def _editor_url(model_label: str, pk: object, filters: QueueFilters, pos: int) -> str:
    """The editor deep-link for one row, carrying the list it came from (#3828).

    `queue` is the filter querystring the row was listed under and `pos` its
    index in that list; the editor's Next control (`_queue_nav`) needs both to
    find the row that follows this one, and to keep finding it after this row
    has been credited out of the list. `links.workbench_editor_url` is the
    context-free form the stock change form uses.
    """
    query = urlencode({"model": model_label, "pk": pk, "queue": filters.as_query(), "pos": pos})
    return f"{reverse('admin_authoring_editor')}?{query}"


def _queue_row(row: BacklogRow, pos: int, filters: QueueFilters) -> dict:
    """One queue row plus its two links, mirroring `_entry_row` below.

    The links are built here rather than on `BacklogRow` itself for the same
    reason the related-entries pane builds its own: `backlog.py` is the data
    tier and knows nothing about the admin registry or URL routing.
    """
    return {
        "row": row,
        "editor_url": _editor_url(row.model_label, row.pk, filters, pos),
        "admin_url": admin_change_url(row.model_label, row.pk),
    }


@superuser_required
def authoring_dashboard(request: HttpRequest) -> HttpResponse:
    """Authoring Workbench dashboard: setup panel first, stats + queue after.

    An unlinked account sees the setup panel in place of the stats/queue
    skeleton (#3019 Task 4) - every downstream panel assumes a contributor
    identity, so the gate wires one up before any of them ever load.
    """
    context = {"title": "Authoring Workbench", "setup_required": _setup_required(request)}
    if context["setup_required"]:
        context["unlinked_contributors"] = ContentContributor.objects.filter(
            player_data__isnull=True
        )
        context["suggested_name"] = request.user.username
    else:
        context["builders"] = _builders_context()
    return render(request, "admin/authoring/dashboard.html", context)


@superuser_required
def authoring_stats_fragment(request: HttpRequest) -> HttpResponse:
    """Per-domain rollup panel: rows / to write / to review / word counts."""
    _, stats = build_backlog()
    context = {"stats": stats}
    return render(request, "admin/authoring/_stats_panel.html", context)


@superuser_required
def authoring_queue_fragment(request: HttpRequest) -> HttpResponse:
    """Worst-first queue panel: filtered, capped at `_QUEUE_DISPLAY_CAP` rows.

    `domain`/`status`/`q` query params re-render this same fragment via
    `hx-get` (see `_queue_panel.html`), so the filter form lives inside the
    fragment template the same way the tuning panels' forms do.
    """
    rows, _ = build_backlog()
    domains = sorted({row.domain for row in rows})
    filters = QueueFilters.from_params(request.GET)

    filtered = _filtered_rows(rows, filters)
    total = len(filtered)
    visible = filtered[:_QUEUE_DISPLAY_CAP]

    context = {
        "rows": [_queue_row(row, pos, filters) for pos, row in enumerate(visible)],
        "total": total,
        "count_noun": filters.count_noun,
        "scope_label": filters.scope_label,
        "display_cap": _QUEUE_DISPLAY_CAP,
        "capped": total > _QUEUE_DISPLAY_CAP,
        "domains": domains,
        "selected_domain": filters.domain,
        "models": _model_options(rows, filters.domain),
        "selected_model": filters.model,
        "selected_status": filters.status,
        "status_choices": BacklogStatusFilter.choices,
        "query": filters.query,
    }
    response = render(request, "admin/authoring/_queue_panel.html", context)
    # Replace (not push) the page URL with the live filters, so a reload comes
    # back to the same list without each keystroke in the search box becoming
    # its own history entry (#3828). `dashboard.html` forwards that querystring
    # into the first queue load.
    response["HX-Replace-Url"] = _dashboard_url(filters)
    return response


def _dashboard_url(filters: QueueFilters) -> str:
    query = filters.as_query()
    return f"{reverse('admin_authoring')}?{query}" if query else reverse("admin_authoring")


@dataclass
class _EditorTarget:
    """The resolved `?model=&pk=` pair every editor view starts from.

    Bundled into one value (ruff PLR0913) rather than passed as four separate
    `model`/`instance`/`model_label`/`pk` arguments through every helper and
    view below. `error`, when set, means `model`/`instance` did not both
    resolve - the caller renders the flash-in-fragment error line instead of
    the form.
    """

    model: type | None
    instance: object | None
    model_label: str
    pk: str
    error: str | None = None


def _resolve_target(model_label: str, pk: str) -> _EditorTarget:
    """Resolve `?model=&pk=` into an `_EditorTarget`, error set on any failure.

    Shared by all four editor views: an unresolvable label, a model outside
    `credited_content_models()`, or a missing row all set `.error` (the
    missing-row case still carries `.model`, so the message can name it). A
    non-numeric or otherwise unusable `pk` is treated the same as "missing"
    rather than surfacing a raw `ValueError`/`OverflowError` as a 500 - the
    same coherent-error idiom `link_contributor` uses for an absurd
    `existing_pk`.
    """
    try:
        model = resolve_model_by_name(model_label) if model_label else None
    except LookupError:
        model = None
    if model is None:
        return _EditorTarget(None, None, model_label, pk, error="Unknown model.")
    if model not in credited_content_models():
        return _EditorTarget(
            None, None, model_label, pk, error=f"{model.__name__} is not a credited content model."
        )
    try:
        instance = model.objects.filter(pk=pk).first()
    except (ValueError, TypeError, OverflowError):
        instance = None
    if instance is None:
        return _EditorTarget(
            model, None, model_label, pk, error=f"{model.__name__} #{pk} does not exist."
        )
    return _EditorTarget(model, instance, model_label, pk)


def _mechanical_fields(model: type, instance: object, prose_names: list[str]) -> list[dict]:
    """Every concrete field on this row that isn't prose or a credit column.

    An FK-typed field's value here is the related model instance, not its
    id - the template drops it straight into `{{ field.value }}`, and Django's
    template engine calls `str()` on any object it renders, so an FK shows
    its natural display string for free.
    """
    prose_set = set(prose_names)
    fields = []
    for field in model._meta.fields:  # noqa: SLF001
        if field.primary_key or field.name in prose_set or field.name in _CREDIT_FIELD_NAMES:
            continue
        fields.append({"name": field.name, "value": getattr(instance, field.name)})
    return fields


@dataclass
class _EditorFlags:
    """The response-shape flags every editor view needs to hand its fragment.

    Bundled into one value (ruff PLR0913) rather than passed as five separate
    keyword arguments through `_render_editor_fragment` and
    `_build_editor_context` alike.
    """

    error: str | None = None
    saved: bool = False
    credited: bool = False
    reviewed: bool = False
    needs_setup: bool = False
    field_errors: dict[str, list[str]] | None = None


#: The end-of-list line per status (#3828); `_queue_nav` appends " in <domain>" when
#: a domain filter is set, and the widen link clears it.
_EXHAUSTED_TEXT = {
    BacklogStatusFilter.UNWRITTEN: "Nothing left to write",
    BacklogStatusFilter.UNREVIEWED: "Nothing left to review",
    BacklogStatusFilter.PLACEHOLDER: "No placeholder text left",
    BacklogStatusFilter.ALL: "Nothing left",
}


@dataclass
class _QueueNav:
    """Where this row sits in the list the writer opened it from, and what comes after (#3828).

    `position` is 1-based and `None` once the row has left the list (it was
    just credited or reviewed out of it, or a change-form deep link opened a
    row the default filter never showed). `next_url` is the editor link for
    the successor; when there is none, `exhausted_text` says so and
    `widen_url` (only when a domain filter was set) reopens the dashboard
    with that domain cleared.
    """

    total: int
    count_noun: str
    scope_label: str
    position: int | None = None
    next_url: str | None = None
    next_identity: str = ""
    exhausted_text: str = ""
    widen_url: str | None = None


def _nav_params(params: QueryDict) -> tuple[QueueFilters, int | None]:
    """The `queue=` filter querystring and `pos=` index an editor request carries.

    `queue` is one opaque param holding the queue's own querystring (see
    `_editor_url`) rather than the four filter params spread out, because the
    editor already uses `model` for the row's own label and the queue uses it
    for the model filter. A non-numeric or absent `pos` is `None`.
    """
    filters = QueueFilters.from_params(QueryDict(params.get("queue", "")))
    raw_pos = params.get("pos", "")
    return filters, int(raw_pos) if raw_pos.isdigit() else None


def _queue_nav(target: _EditorTarget, filters: QueueFilters, pos: int | None) -> _QueueNav:
    """Resolve the successor of `target` in the filtered queue (#3828).

    Three cases, in order:

    - the row is in the filtered list at index `i`: the successor is
      `filtered[i + 1]`, so skipping a row moves past it, never back to the head;
    - the row is not in the list but `pos` is known: it was just credited or
      reviewed out of the list, and `filtered[pos]` is the row that shifted up
      into its slot - the same row the arrow pointed at before the stamp;
    - neither: a deep link with no queue context, and the head of the list is
      the most useful place to send the writer.

    One `build_backlog()` scan per editor request, the same cost the queue panel
    already pays; the module docstring of `backlog.py` owns the scale ceiling.
    """
    rows, _ = build_backlog()
    filtered = _filtered_rows(rows, filters)
    label = f"{domain_of(target.model)}.{target.model.__name__}"
    current_pk = target.instance.pk
    index = next(
        (i for i, row in enumerate(filtered) if row.model_label == label and row.pk == current_pk),
        None,
    )
    if index is not None:
        next_pos = index + 1
    elif pos is not None:
        next_pos = pos
    else:
        next_pos = 0

    nav = _QueueNav(
        total=len(filtered),
        count_noun=filters.count_noun,
        scope_label=filters.scope_label,
        position=None if index is None else index + 1,
    )
    if next_pos < len(filtered):
        successor = filtered[next_pos]
        nav.next_url = _editor_url(successor.model_label, successor.pk, filters, next_pos)
        nav.next_identity = successor.identity
        return nav

    text = _EXHAUSTED_TEXT.get(filters.status, "Nothing left")
    nav.exhausted_text = f"{text} in {filters.domain}." if filters.domain else f"{text}."
    if filters.domain:
        nav.widen_url = _dashboard_url(replace(filters, domain="", model=""))
    return nav


def _build_editor_context(target: _EditorTarget, flags: _EditorFlags, params: QueryDict) -> dict:
    filters, pos = _nav_params(params)
    context = {
        "model_label": target.model_label,
        "pk": target.pk,
        "error": flags.error or target.error,
        "saved": flags.saved,
        "credited": flags.credited,
        "reviewed": flags.reviewed,
        "needs_setup": flags.needs_setup,
        "freeze_sentence": _FREEZE_SENTENCE,
        "export_sentence": _EXPORT_SENTENCE,
        # Carried back on every POST as hidden inputs, so a Save or a credit
        # re-renders with the arrow still pointing at the right row (#3828).
        "queue_query": filters.as_query(),
        "pos": "" if pos is None else pos,
    }
    if target.model is not None and target.instance is not None:
        context["nav"] = _queue_nav(target, filters, pos)
        field_errors = flags.field_errors or {}
        prose_names = prose_fields_for(target.model)
        prose_set = set(prose_names)
        context["instance"] = target.instance
        context["prose_fields"] = [
            {
                "name": name,
                "value": getattr(target.instance, name) or "",
                "errors": field_errors.get(name),
            }
            for name in prose_names
        ]
        context["mechanical_fields"] = _mechanical_fields(
            target.model, target.instance, prose_names
        )
        # A full_clean() failure keyed on a mechanical field (or Django's own
        # "__all__" non-field-error key) has no textarea to show it next to -
        # without this, that failure mode re-renders with every input
        # looking untouched and no visible sign anything went wrong (#3019
        # review). Collected here, not in `_apply_prose_edits`, so both the
        # save and credit views get it for free through the same context
        # builder.
        context["general_errors"] = [
            f"{field}: {message}"
            for field, messages in field_errors.items()
            if field not in prose_set
            for message in messages
        ]
    return context


def _render_editor_fragment(
    request: HttpRequest, target: _EditorTarget, flags: _EditorFlags | None = None
) -> HttpResponse:
    # The queue context (`queue=`/`pos=`) rides the GET querystring on open and
    # the POST body (hidden inputs) on every action, so read whichever this is.
    params = request.POST if request.method == "POST" else request.GET
    context = _build_editor_context(target, flags or _EditorFlags(), params)
    return render(request, "admin/authoring/_editor_panel.html", context)


def _apply_prose_edits(
    instance: object, model: type, post_data: QueryDict
) -> dict[str, list[str]] | None:
    """Assign posted `prose_fields_for(model)` keys, `full_clean()`, `save()`.

    Any POST key outside that set - a mechanical field smuggled in under its
    own name - is never read here at all, so it can't reach `setattr` no
    matter what the request body carries. Returns `full_clean()`'s
    `message_dict` on failure (nothing saved) or `None` on success.
    """
    for name in prose_fields_for(model):
        if name in post_data:
            setattr(instance, name, post_data[name])
    try:
        instance.full_clean()
    except ValidationError as exc:
        return exc.message_dict
    instance.save()
    return None


@superuser_required
def authoring_editor(request: HttpRequest) -> HttpResponse:
    """GET the row editor fragment for `?model=<label>&pk=` (#3019 Task 5)."""
    target = _resolve_target(request.GET.get("model", ""), request.GET.get("pk", ""))
    return _render_editor_fragment(request, target)


@superuser_required
@require_POST
def authoring_editor_save(request: HttpRequest) -> HttpResponse:
    """Save this row's prose fields only, re-rendering with a saved notice or errors."""
    target = _resolve_target(request.POST.get("model", ""), request.POST.get("pk", ""))
    if target.error:
        return _render_editor_fragment(request, target)

    field_errors = _apply_prose_edits(target.instance, target.model, request.POST)
    flags = _EditorFlags(saved=field_errors is None, field_errors=field_errors)
    return _render_editor_fragment(request, target, flags)


@superuser_required
@require_POST
def authoring_editor_credit(request: HttpRequest) -> HttpResponse:
    """Save prose (if posted), then stamp `written_by`/`written_on` for the operator.

    An operator with no linked `ContentContributor` gets the same setup-gate
    guidance the dashboard shows an unlinked account, instead of a stamp -
    this editor is reachable by direct URL and isn't itself behind the
    dashboard's setup gate, so the defensive check has to live here too.
    """
    target = _resolve_target(request.POST.get("model", ""), request.POST.get("pk", ""))
    if target.error:
        return _render_editor_fragment(request, target)

    contributor = current_contributor(request.user)
    if contributor is None:
        return _render_editor_fragment(request, target, _EditorFlags(needs_setup=True))

    prose_posted = any(name in request.POST for name in prose_fields_for(target.model))
    if prose_posted:
        field_errors = _apply_prose_edits(target.instance, target.model, request.POST)
        if field_errors is not None:
            return _render_editor_fragment(request, target, _EditorFlags(field_errors=field_errors))

    target.instance.written_by = contributor
    target.instance.written_on = timezone.now().date()
    target.instance.save()
    response = _render_editor_fragment(request, target, _EditorFlags(credited=True))
    response["HX-Trigger"] = _BACKLOG_CHANGED_EVENT
    return response


@superuser_required
@require_POST
def authoring_editor_review(request: HttpRequest) -> HttpResponse:
    """Stamp `reviewed_by`/`reviewed_on` for the operator; authorship untouched.

    Never applies pending prose edits sitting in the form - a reviewer
    confirming review should not silently overwrite an in-flight prose edit
    that wasn't explicitly saved.
    """
    target = _resolve_target(request.POST.get("model", ""), request.POST.get("pk", ""))
    if target.error:
        return _render_editor_fragment(request, target)

    contributor = current_contributor(request.user)
    if contributor is None:
        return _render_editor_fragment(request, target, _EditorFlags(needs_setup=True))

    target.instance.reviewed_by = contributor
    target.instance.reviewed_on = timezone.now().date()
    target.instance.save()
    response = _render_editor_fragment(request, target, _EditorFlags(reviewed=True))
    response["HX-Trigger"] = _BACKLOG_CHANGED_EVENT
    return response


def _workbench_url(entry: RelatedEntry) -> str | None:
    """Editor deep-link for `entry`, or `None` when its model isn't credited.

    `entry.credited is not None` is the same signal `_resolve_target` gates
    on (`model in credited_content_models()`): `RelatedEntry.credited` is set
    from `isinstance(value, CreditedContent)`, and every concrete
    `CreditedContent` subclass is exactly what `credited_content_models()`
    enumerates - so this never needs to re-import or re-call that function.
    """
    if entry.credited is None:
        return None
    return f"{reverse('admin_authoring_editor')}?model={entry.model_label}&pk={entry.pk}"


def _entry_row(entry: RelatedEntry) -> dict:
    return {
        "entry": entry,
        "workbench_url": _workbench_url(entry),
        "admin_url": admin_change_url(entry.model_label, entry.pk),
    }


@superuser_required
def authoring_related_fragment(request: HttpRequest) -> HttpResponse:
    """GET the related-entries panel for `?model=<label>&pk=` (#3019 Task 6).

    Loads automatically below the editor (`_editor_panel.html`'s
    `hx-trigger="load"`) - a structural FK/M2M walk is cheap enough to run
    unconditionally, unlike the mentions search below.
    """
    target = _resolve_target(request.GET.get("model", ""), request.GET.get("pk", ""))
    if target.error:
        return render(request, "admin/authoring/_related_panel.html", {"error": target.error})

    entries, truncated = related_entries(target.instance)
    context = {"rows": [_entry_row(entry) for entry in entries], "truncated": truncated}
    return render(request, "admin/authoring/_related_panel.html", context)


@superuser_required
def authoring_mentions_fragment(request: HttpRequest) -> HttpResponse:
    """GET the prose-mentions panel for `?model=<label>&pk=` (#3019 Task 6).

    Only ever runs from the editor's "Search for mentions" button click, not
    on load - an OR-`icontains` scan of every credited model's prose fields
    is real query work, unlike the structural related-entries walk above.
    Searches for `str(target.instance)` (its natural display name) and
    excludes the row being edited from its own results.
    """
    target = _resolve_target(request.GET.get("model", ""), request.GET.get("pk", ""))
    if target.error:
        return render(request, "admin/authoring/_mentions_panel.html", {"error": target.error})

    mentions = prose_mentions(str(target.instance), exclude=(target.model, target.instance.pk))
    context = {"rows": [_entry_row(entry) for entry in mentions]}
    return render(request, "admin/authoring/_mentions_panel.html", context)


def _reference_toggle(request: HttpRequest, name: str, *, default: bool, submitted: bool) -> bool:
    """This checkbox's checked state: `default` before any submission, else read from GET.

    An unchecked HTML checkbox sends nothing at all, so `name not in
    request.GET` is ambiguous between "never submitted" and "submitted
    unchecked" on its own - `submitted` (whether `q` is present) resolves
    that ambiguity for every checkbox on the panel in one place.
    """
    if not submitted:
        return default
    return request.GET.get(name) == "1"


@superuser_required
def authoring_reference(request: HttpRequest) -> HttpResponse:
    """GET the reference search pane fragment (#3019 Task 7).

    Query input plus three checkboxes: DB search (every credited model's
    prose, default on) and two opt-in file corpora, staff docs and the Arx I
    dump (both default off - see `web.admin.authoring.reference`'s module
    docstring for why). An empty query renders the empty prompt and runs no
    search at all, DB or file; an unchecked file-corpus box means
    `reference_roots` is asked for that root not at all, so it never even
    reaches the "does this directory exist" check.
    """
    submitted = "q" in request.GET
    query = (request.GET.get("q") or "").strip()
    search_db = _reference_toggle(request, "db", default=True, submitted=submitted)
    staff_docs = _reference_toggle(request, "staff_docs", default=False, submitted=submitted)
    arx1 = _reference_toggle(request, "arx1", default=False, submitted=submitted)

    db_groups = []
    file_hits = []
    if query:
        if search_db:
            db_groups = db_search(query)
        roots = reference_roots(staff_docs=staff_docs, arx1=arx1)
        if roots:
            file_hits = file_search(query, roots)

    context = {
        "query": query,
        "search_db": search_db,
        "staff_docs": staff_docs,
        "arx1": arx1,
        "db_groups": db_groups,
        "file_hits": file_hits,
    }
    return render(request, "admin/authoring/_reference_panel.html", context)


@superuser_required
@require_POST
def authoring_setup(request: HttpRequest) -> HttpResponse:
    """Create-or-pick a contributor and link it to the account (#3019 Task 4).

    A plain form POST from `_setup_panel.html`, not an HTMX fragment - the
    happy path is a full-page redirect back to the dashboard, which now
    renders the normal stats/queue skeleton once the link exists.

    Two ways a repeat submit can land here, both handled without a 500: a
    sequential re-POST from an already-linked account (a stale tab, a slow
    double-click that landed after the first response) is caught by the
    `current_contributor` check right below and flashed as a no-op; a truly
    concurrent double-submit that gets past that check on both requests races
    unique-constraint writes inside `link_contributor`, which resolves it
    itself - idempotent success if the race linked this same account, a
    coherent "someone else just took it" `ValueError` otherwise. Either way
    this view only ever sees a `ValueError` or a contributor, never a raw
    `IntegrityError`.
    """
    if current_contributor(request.user) is not None:
        messages.info(request, "Your author credit is already linked.")
        return redirect("admin_authoring")

    name = request.POST.get("name", "")
    existing_pk_raw = request.POST.get("existing_pk", "")
    existing_pk = int(existing_pk_raw) if existing_pk_raw.isdigit() else None

    try:
        contributor = link_contributor(request.user, name=name, existing_pk=existing_pk)
    except ValueError as exc:
        messages.error(request, str(exc))
        return redirect("admin_authoring")

    messages.success(request, f'Linked your author credit to "{contributor.name}".')
    return redirect("admin_authoring")
