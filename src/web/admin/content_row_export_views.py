"""Superuser-only row-level content export surface (#3018).

Mirrors ``content_conflict_views.py``'s idiom (``@staff_member_required``
plus an explicit ``is_superuser`` check, ``resolve_content_root()`` for the
private content-repo path, digest-guarded confirm) but drives the opposite
direction: instead of pulling the repo's version of a credited row back into
the database, this writes ONE database row's corpus form out to the lore
checkout's working tree (``core_management.content_export.export_single_row``)
on the fixed session branch (``core_management.content_session``), shows its
git diff, and either commits it as one small export commit or discards it.

Three views, one round trip: ``content_export_row`` (POST from the change
form) writes the row and redirects to ``content_export_row_diff`` (GET),
which renders the diff plus a digest of it; ``content_export_row_confirm``
(POST) re-checks that digest before doing anything; a stale digest (the
working tree changed between the GET and this POST) is refused the same way
a stale conflict-resolve digest is. An addition (the row's natural key isn't
in the corpus yet) requires an explicit "new_row" checkbox acknowledgment,
mirroring the corpus-wide export's addition gate (ADR-0191) at row scope.

``export_single_row`` is deliberately never called twice for the same
pending export - a second call would flip its own ``is_addition`` reading
(the row would already be in the file it just wrote). So the diff and
confirm views never re-export; they recompute the same output path(s)
``export_single_row`` would have used via a small read-only helper below.

At most one pending row export can exist at a time - enforced not here but
one layer down, by ``content_session.ensure_session_branch`` refusing any
dirty working tree (git state is the only truth that holds across browsers/
operators; request-session bookkeeping is not). Addition-ness is derived the
same way, straight from git at both diff-render and confirm time
(``_derive_is_addition``, delegating to ``content_session
.row_is_addition_at_head``) - fixed after review (#3018) found the original
design read it out of the request session instead, which only ever answered
for the browser that ran the export: a second browser opening the same diff
URL directly saw a default of "not an addition" and could commit a genuine
addition with no new-row checkbox at all. This module still keeps one piece
of state in the request session - the identity of the currently pending row
(model, pk, natural key) - purely as a courtesy: when
``ensure_session_branch`` refuses a second export because a first is still
pending, that record is what lets the flash name the pending row and the
redirect send the operator straight to its diff page instead of a dead end.
It is never consulted for anything that gates a commit.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from urllib.parse import urlencode

from django.contrib import admin, messages
from django.contrib.admin.views.decorators import staff_member_required
from django.core.exceptions import PermissionDenied
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST

_CONTENT_ROOT_UNSET_MSG = (
    "CONTENT_REPO_PATH is not set. Add it to src/.env pointing at your "
    "local checkout of the private content repository."
)

# The two values the diff page's ``action`` hidden field can carry.
_ACTION_CONFIRM = "confirm"
_ACTION_DISCARD = "discard"


def _diff_url(model_label: str, pk: object) -> str:
    """Build the row-export diff URL for one ``(model_label, pk)`` pair."""
    query = urlencode({"model": model_label, "pk": pk})
    return f"{reverse('admin_content_export_row_diff')}?{query}"


def _workbench_url(model_label: str, pk: object) -> str:
    """Build the Authoring Workbench editor deep-link for this row.

    Unlike ``_change_url``, this always resolves - ``admin_authoring_editor``
    is a fixed route, not one built per-model off the admin registry - so
    it's the fallback destination every ``_change_url`` call site degrades to
    when a model has no registered ``ModelAdmin`` (#3019 review, Item 2).
    """
    query = urlencode({"model": model_label, "pk": pk})
    return f"{reverse('admin_authoring_editor')}?{query}"


def _change_url(model: type, pk: object) -> str | None:
    """Build this model's admin change-form URL for ``pk``, or ``None`` if it can't.

    ``admin:arxii_<model_name>_change`` may look hardcodable, but every
    first-party model's real Django ``app_label`` is ``arxii`` post-collapse
    (#2906) - reading it off ``model._meta`` rather than assuming the string
    keeps this correct if that ever changes again.

    Returns ``None`` when ``model`` has no registered ``ModelAdmin`` - a
    credited+exportable model is not guaranteed to have one (13 such models
    as of #3019 review, e.g. ``missions.MissionTemplate``,
    ``magic.PortalAnchorKind``), and building this URL for one of them used
    to raise ``NoReverseMatch`` and 500 the diff page. Mirrors
    ``web.admin.authoring.views._admin_change_url``'s registry check. Every
    caller here degrades to ``_workbench_url`` (a route that always exists)
    instead of assuming this resolves.
    """
    if model not in admin.site._registry:  # noqa: SLF001
        return None
    app_label = model._meta.app_label  # noqa: SLF001
    model_name = model._meta.model_name  # noqa: SLF001
    return reverse(f"admin:{app_label}_{model_name}_change", args=[pk])


def _changelist_url(model: type) -> str:
    """Build this model's admin changelist URL - the fallback when ``pk`` is gone."""
    app_label = model._meta.app_label  # noqa: SLF001
    model_name = model._meta.model_name  # noqa: SLF001
    return reverse(f"admin:{app_label}_{model_name}_changelist")


_PENDING_EXPORT_SESSION_KEY = "content_export_row:pending"


def _set_pending_export(request: HttpRequest, model_label: str, pk: object, result) -> None:
    """Record the just-written pending export as the session's single pending record.

    A single key, not one keyed by ``(model_label, pk)``: at most one pending
    export can exist at a time (enforced by ``ensure_session_branch``), so
    there is never a need to remember more than one, and a stray leftover
    key from an abandoned export session can never linger under this
    invariant.

    Carries only the identity needed to name the pending row in a flash
    message (see the module docstring) - no ``is_addition``, which is
    derived fresh from git on every diff render and confirm instead (#3018
    review).
    """
    request.session[_PENDING_EXPORT_SESSION_KEY] = {
        "model_label": model_label,
        "pk": pk,
        "natural_key": result.natural_key,
    }


def _pending_export(request: HttpRequest) -> dict | None:
    """Return the session's pending-export record, or ``None`` if there isn't one."""
    return request.session.get(_PENDING_EXPORT_SESSION_KEY)


def _clear_pending_export(request: HttpRequest) -> None:
    """Forget the session's pending-export record (after a confirm or discard)."""
    request.session.pop(_PENDING_EXPORT_SESSION_KEY, None)


def _derive_is_addition(content_root: Path, model: type, paths: list[Path], fields: dict) -> bool:
    """Return whether this pending row export is an addition, derived from git HEAD.

    Replaces the old request-session lookup (see the module docstring's
    #3018-review note) - delegates the actual git plumbing to
    ``content_session.row_is_addition_at_head``, which fails closed on any
    git/parse trouble so uncertainty here can never suppress the new-row
    checkbox.
    """
    from core_management.content_export import _natural_key_fields  # noqa: PLC0415
    from core_management.content_session import row_is_addition_at_head  # noqa: PLC0415

    key_fields = _natural_key_fields(model)
    return row_is_addition_at_head(content_root, paths, key_fields, fields)


def _pending_export_display_name(model_label: str) -> str:
    """Return the pending export's model class name, falling back to its label.

    Only used for a flash message, so an unresolvable label (a very stale
    session surviving a model rename) degrades to showing the raw label
    rather than raising out of an error-handling path.
    """
    from core.app_domains import resolve_model_by_name  # noqa: PLC0415

    try:
        return resolve_model_by_name(model_label).__name__
    except LookupError:
        return model_label


def _row_export_preview(instance, content_root: Path) -> tuple[list[Path], str, dict]:
    """Recompute ``export_single_row``'s output path(s), key display, and fields.

    Read-only: mirrors that function's path/key derivation exactly (same
    serializer call, same natural-key fields, same markdown-vs-JSON path
    formula) but never writes anything. The diff and confirm views need to
    know where the pending export landed without re-running the write that
    would flip its own addition bookkeeping a second time (see module
    docstring). The returned ``fields`` dict is this row's serialized field
    values - needed by ``_derive_is_addition`` to check the row's own
    natural key against what git's ``HEAD`` copy of the file actually holds.
    """
    from django.core import serializers  # noqa: PLC0415

    from core.app_domains import domain_of  # noqa: PLC0415
    from core_management.content_export import (  # noqa: PLC0415
        _markdown_entry_path,
        _natural_key_fields,
    )
    from core_management.content_fixtures import MARKDOWN_EXPORT_DOMAINS  # noqa: PLC0415

    model = type(instance)
    model_name = model.__name__.lower()
    model_label = f"{domain_of(model)}.{model_name}"
    data = serializers.serialize(
        "json",
        model.objects.filter(pk=instance.pk),
        use_natural_foreign_keys=True,
        use_natural_primary_keys=True,
    )
    records = json.loads(data)
    if not records:
        return [], "", {}
    fields = records[0]["fields"]
    key_fields = _natural_key_fields(model)
    key_display = ", ".join(
        str(v) for v in ([fields.get(f) for f in key_fields] if key_fields else [instance.pk])
    )

    spec = MARKDOWN_EXPORT_DOMAINS.get(model_label)
    if spec is not None:
        return [_markdown_entry_path(content_root, spec, fields)], key_display, fields

    out_path = content_root / "fixtures" / domain_of(model) / f"{model_name}.json"
    return [out_path], key_display, fields


def _resolve_model_and_instance(model_label: str, pk: str):
    """Resolve ``(model, instance)`` for a posted/queried ``(model, pk)`` pair.

    Returns ``(model, instance)`` where either half may be ``None`` - pair
    with ``_bail_on_missing_target`` to turn either gap into a flash +
    redirect (a missing model has nowhere sensible to go but the Game Setup
    hub; a missing instance can still fall back to that model's changelist).
    """
    from core.app_domains import resolve_model_by_name  # noqa: PLC0415

    try:
        model = resolve_model_by_name(model_label)
    except LookupError:
        return None, None
    instance = model.objects.filter(pk=pk).first()
    return model, instance


def _bail_on_missing_target(
    request: HttpRequest, model: type | None, instance: object | None, model_label: str, pk: str
) -> HttpResponse | None:
    """Return a flash-and-redirect response for an unresolved model/instance, else ``None``.

    Shared by all three views so ``content_export_row_confirm`` (which also
    branches on digest and on/off commit outcomes) doesn't pile up enough
    ``return`` statements to trip the complexity linter.
    """
    if model is None:
        messages.error(request, f"{model_label} is not a recognized model.")
        return HttpResponseRedirect(reverse("admin_game_setup"))
    if instance is None:
        messages.error(request, f"{model.__name__} [{pk}] no longer exists.")
        return HttpResponseRedirect(_changelist_url(model))
    return None


@staff_member_required
@require_POST
def content_export_row(request: HttpRequest) -> HttpResponse:
    """Write one database row's corpus form into the session branch's working tree.

    Ensures the session branch first (creating or reusing it - see
    ``content_session.ensure_session_branch``), then exports exactly this
    row. A refusal (the model isn't corpus-owned, or this row is filtered
    out by ``EXPORT_FILTERS``) flashes and sends the operator back to the
    change form without touching git at all. Success redirects to the diff
    page for review before anything is committed.
    """
    if not request.user.is_superuser:
        raise PermissionDenied

    from core_management.content_export import export_single_row  # noqa: PLC0415
    from core_management.content_push import ContentPushError  # noqa: PLC0415
    from core_management.content_repo import resolve_content_root  # noqa: PLC0415
    from core_management.content_session import ensure_session_branch  # noqa: PLC0415

    content_root = resolve_content_root()
    if content_root is None:
        messages.error(request, _CONTENT_ROOT_UNSET_MSG)
        return HttpResponseRedirect(reverse("admin_game_setup"))

    model_label = request.POST.get("model", "")
    pk = request.POST.get("pk", "")
    model, instance = _resolve_model_and_instance(model_label, pk)
    bail = _bail_on_missing_target(request, model, instance, model_label, pk)
    if bail is not None:
        return bail

    try:
        ensure_session_branch(content_root)
    except ContentPushError as exc:
        pending = _pending_export(request)
        if pending is None:
            messages.error(request, str(exc))
            return HttpResponseRedirect(_change_url(model, pk) or _workbench_url(model_label, pk))
        pending_name = _pending_export_display_name(pending["model_label"])
        messages.error(request, f"{exc} Pending: {pending_name} [{pending['natural_key']}].")
        return HttpResponseRedirect(_diff_url(pending["model_label"], pending["pk"]))

    result = export_single_row(instance, content_root=content_root)
    if result.refused is not None:
        messages.error(request, result.refused)
        return HttpResponseRedirect(_change_url(model, pk) or _workbench_url(model_label, pk))

    _set_pending_export(request, result.model_label, pk, result)
    return HttpResponseRedirect(_diff_url(result.model_label, pk))


@staff_member_required
@require_GET
def content_export_row_diff(request: HttpRequest) -> HttpResponse:
    """Show one pending row export's git diff behind a digest the confirm POST checks."""
    if not request.user.is_superuser:
        raise PermissionDenied

    from core_management.content_repo import resolve_content_root  # noqa: PLC0415
    from core_management.content_session import row_diff  # noqa: PLC0415

    content_root = resolve_content_root()
    if content_root is None:
        messages.error(request, _CONTENT_ROOT_UNSET_MSG)
        return HttpResponseRedirect(reverse("admin_game_setup"))

    model_label = request.GET.get("model", "")
    pk = request.GET.get("pk", "")
    model, instance = _resolve_model_and_instance(model_label, pk)
    bail = _bail_on_missing_target(request, model, instance, model_label, pk)
    if bail is not None:
        return bail

    paths, natural_key, fields = _row_export_preview(instance, content_root)
    diff_text = row_diff(content_root, paths)
    if not diff_text.strip():
        messages.info(
            request, f"Nothing to review for {model.__name__} [{natural_key}] - export it first."
        )
        return HttpResponseRedirect(_change_url(model, pk) or _workbench_url(model_label, pk))

    is_addition = _derive_is_addition(content_root, model, paths, fields)
    digest = hashlib.sha256(diff_text.encode("utf-8")).hexdigest()

    context = {
        "title": f"Export {model.__name__}: {natural_key}",
        "model_label": model_label,
        "pk": pk,
        "natural_key": natural_key,
        "diff_text": diff_text,
        "is_addition": is_addition,
        "digest": digest,
        "confirm_url": reverse("admin_content_export_row_confirm"),
        "change_url": _change_url(model, pk),
        "workbench_url": _workbench_url(model_label, pk),
    }
    return render(request, "admin/content_row_export_diff.html", context)


def _run_confirmed_action(
    request: HttpRequest,
    content_root: Path,
    instance: object,
    preview: tuple[list[Path], str, dict],
) -> HttpResponse:
    """Apply ``action=confirm|discard`` once the digest has already checked out.

    Split out of ``content_export_row_confirm`` (ruff PLR0911) so that view's
    own preamble (superuser gate, content-root check, model/instance
    resolution, digest check) stays separate from this branch's several
    possible outcomes. ``preview`` is ``_row_export_preview``'s
    ``(paths, natural_key, fields)`` result, passed through as one value to
    stay under the argument-count ceiling (ruff PLR0913).
    """
    from core_management.content_push import ContentPushError  # noqa: PLC0415
    from core_management.content_session import (  # noqa: PLC0415
        commit_row_export,
        discard_row_export,
    )

    paths, natural_key, fields = preview
    model = type(instance)
    pk = instance.pk
    model_label = request.POST.get("model", "")
    diff_url = _diff_url(model_label, pk)
    action = request.POST.get("action", "")

    if action == _ACTION_DISCARD:
        discard_row_export(content_root, paths)
        _clear_pending_export(request)
        messages.info(request, f"Discarded the pending export of {model.__name__} [{natural_key}].")
        return HttpResponseRedirect(_change_url(model, pk) or _workbench_url(model_label, pk))

    if action != _ACTION_CONFIRM:
        messages.error(request, "Unknown export action.")
        return HttpResponseRedirect(diff_url)

    # Derived straight from git HEAD, not the request session (#3018 review) -
    # only computed here, not for the discard branch above, since discard
    # never needs to know.
    is_addition = _derive_is_addition(content_root, model, paths, fields)
    if is_addition and not request.POST.get("new_row"):
        messages.error(
            request, "Check the new-row box to confirm this export adds a row to the corpus."
        )
        return HttpResponseRedirect(diff_url)

    try:
        sha = commit_row_export(content_root, paths, f"Export {model.__name__} [{natural_key}]")
    except ContentPushError as exc:
        messages.error(request, str(exc))
        return HttpResponseRedirect(diff_url)

    _clear_pending_export(request)
    messages.success(request, f"Committed {model.__name__} [{natural_key}] as {sha}.")
    return HttpResponseRedirect(reverse("admin_content_session"))


@staff_member_required
@require_POST
def content_export_row_confirm(request: HttpRequest) -> HttpResponse:
    """Commit or discard one pending row export, after a matching digest.

    A digest mismatch means the working tree changed since the diff page was
    rendered - refused unconditionally, same as ``content_conflict_resolve``.
    An addition (a row not yet in the corpus) also needs the ``new_row``
    checkbox checked; anything else is refused back to the diff page rather
    than silently committed.
    """
    if not request.user.is_superuser:
        raise PermissionDenied

    from core_management.content_repo import resolve_content_root  # noqa: PLC0415
    from core_management.content_session import row_diff  # noqa: PLC0415

    content_root = resolve_content_root()
    if content_root is None:
        messages.error(request, _CONTENT_ROOT_UNSET_MSG)
        return HttpResponseRedirect(reverse("admin_game_setup"))

    model_label = request.POST.get("model", "")
    pk = request.POST.get("pk", "")
    model, instance = _resolve_model_and_instance(model_label, pk)
    bail = _bail_on_missing_target(request, model, instance, model_label, pk)
    if bail is not None:
        return bail

    paths, natural_key, fields = _row_export_preview(instance, content_root)
    diff_text = row_diff(content_root, paths)
    digest = hashlib.sha256(diff_text.encode("utf-8")).hexdigest()

    if request.POST.get("digest", "") != digest:
        messages.error(
            request, "The working tree changed since you reviewed this diff. Review it again."
        )
        return HttpResponseRedirect(_diff_url(model_label, pk))

    return _run_confirmed_action(request, content_root, instance, (paths, natural_key, fields))
