"""Authoring Workbench dashboard: worst-first backlog queue across every credited
content model (#3019).

The dashboard page (`authoring_dashboard`) renders a skeleton of two
HTMX-loaded panels - domain stats and the queue itself - both scanning the
same `build_backlog()` result (Task 2, `web.admin.authoring.backlog`). The
queue panel caps its display at 100 rows and applies `?domain=`, `?status=`,
and `?q=` filters over the already-sorted rows in a single Python-side scan
(no per-filter rescans, no extra DB queries - `build_backlog()` is the only
query-issuing call in either fragment).

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
"""

from __future__ import annotations

from dataclasses import dataclass

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import HttpRequest, HttpResponse, QueryDict
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from core.app_domains import credited_content_models, resolve_model_by_name
from core_management.prose_fields import prose_fields_for
from web.admin.authoring.backlog import BacklogRow, build_backlog
from web.admin.authoring.contributors import current_contributor, link_contributor
from web.admin.constants import BacklogStatusFilter
from web.admin.tuning.views import superuser_required
from world.contributors.models import ContentContributor

_QUEUE_DISPLAY_CAP = 100

#: The four CreditedContent columns - never assignable from the prose form,
#: and never shown in the mechanical-fields summary (they get their own
#: labeled rows in the template instead).
_CREDIT_FIELD_NAMES = frozenset({"written_by", "written_on", "reviewed_by", "reviewed_on"})

_FREEZE_SENTENCE = (
    "This row is now credited: content loads will not overwrite it until the corpus "
    "catches up. Export it to the content repo to close the loop."
)


def _setup_required(request: HttpRequest) -> bool:
    return current_contributor(request.user) is None


def _row_matches(row: BacklogRow, domain: str, status: str, query: str) -> bool:
    """One row's pass/fail against every active filter, checked in one call.

    Called from a single list comprehension over the full row list in
    `_filtered_rows`, so the combined filter set is one scan regardless of
    how many of `domain`/`status`/`query` are actually set.
    """
    if domain and row.domain != domain:
        return False
    if status == BacklogStatusFilter.PLACEHOLDER and not row.has_placeholder:
        return False
    if status == BacklogStatusFilter.UNWRITTEN and row.written:
        return False
    if status == BacklogStatusFilter.UNREVIEWED and row.reviewed:
        return False
    if query and query not in row.identity.lower():
        return False
    return True


def _filtered_rows(rows: list[BacklogRow], request: HttpRequest) -> list[BacklogRow]:
    domain = request.GET.get("domain") or ""
    status = request.GET.get("status") or ""
    query = (request.GET.get("q") or "").strip().lower()
    return [row for row in rows if _row_matches(row, domain, status, query)]


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
    return render(request, "admin/authoring/dashboard.html", context)


@superuser_required
def authoring_stats_fragment(request: HttpRequest) -> HttpResponse:
    """Per-domain rollup panel: rows/unwritten/unreviewed/word counts."""
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

    filtered = _filtered_rows(rows, request)
    total = len(filtered)
    visible = filtered[:_QUEUE_DISPLAY_CAP]

    context = {
        "rows": visible,
        "total": total,
        "display_cap": _QUEUE_DISPLAY_CAP,
        "capped": total > _QUEUE_DISPLAY_CAP,
        "domains": domains,
        "selected_domain": request.GET.get("domain", ""),
        "selected_status": request.GET.get("status", ""),
        "query": request.GET.get("q", ""),
    }
    return render(request, "admin/authoring/_queue_panel.html", context)


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


def _build_editor_context(target: _EditorTarget, flags: _EditorFlags) -> dict:
    context = {
        "model_label": target.model_label,
        "pk": target.pk,
        "error": flags.error or target.error,
        "saved": flags.saved,
        "credited": flags.credited,
        "reviewed": flags.reviewed,
        "needs_setup": flags.needs_setup,
        "freeze_sentence": _FREEZE_SENTENCE,
    }
    if target.model is not None and target.instance is not None:
        field_errors = flags.field_errors or {}
        prose_names = prose_fields_for(target.model)
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
    return context


def _render_editor_fragment(
    request: HttpRequest, target: _EditorTarget, flags: _EditorFlags | None = None
) -> HttpResponse:
    context = _build_editor_context(target, flags or _EditorFlags())
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
    return _render_editor_fragment(request, target, _EditorFlags(credited=True))


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
    return _render_editor_fragment(request, target, _EditorFlags(reviewed=True))


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
