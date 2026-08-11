"""Superuser-only admin surface for credited-row load conflicts (#3017).

Mirrors the ``content_load_views`` pattern: ``@staff_member_required`` plus an
explicit ``is_superuser`` check, ``resolve_content_root()`` for the private
content-repo path, and the same error-message-plus-redirect idiom on every
bail-out. Where this differs is the shape of the fix: a load conflict is a
credited row (``written_by`` set) whose incoming corpus value differs from
what's on disk - ``content_fixtures._upsert_fixture_object`` freezes the row
rather than overwriting it. The only way back to the repo version is here:
list every current conflict (``core_management.load_conflicts
.scan_load_conflicts``), inspect one row's field-by-field diff, and - only
after typing the row's own natural key back, character for character - delete
the row and reload it from the corpus in one transaction. There is
deliberately no bulk-resolve anywhere: a credited row is a human's editorial
pass, and clearing it is a one-row, one-confirmation action every time.
"""

from __future__ import annotations

from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.core.exceptions import PermissionDenied
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST

# Repeated bail-out message across every view below — extracted to satisfy
# the duplicated-literal SonarCloud smell (python:S1192).
MSG_CONTENT_REPO_PATH_NOT_SET = (
    "CONTENT_REPO_PATH is not set. Add it to src/.env pointing at your "
    "local checkout of the private content repository."
)


def _detail_url(model_label: str, key: str) -> str:
    """Build the conflict-detail URL for one ``(model_label, key)`` pair."""
    query = urlencode({"model": model_label, "key": key})
    return f"{reverse('admin_content_conflict_detail')}?{query}"


def _instance_for_conflict(model, content_root, conflict):
    """Fetch the live DB row a conflict refers to, by natural key.

    Re-runs just enough of the scan plumbing to recompute the lookup dict
    (never the display string, which is lossy for a multi-field natural key):
    locates the matching corpus object, re-extracts its natural key the same
    way ``load_conflicts._scan_object`` does, then reuses
    ``_find_existing_case_insensitive`` - the exact lookup the real load path
    uses - to fetch the row. Raises ``ContentError`` if the corpus entry or
    the DB row is gone (a second admin tab resolved it first, or the corpus
    changed underneath this request).
    """
    from core_management.content_fixtures import (  # noqa: PLC0415
        ContentError,
        _extract_natural_key,
        _find_existing_case_insensitive,
    )

    entry = _locate_corpus_entry(content_root, conflict.model_label, conflict.natural_key)
    if entry is None:
        gone_from_corpus_msg = (
            f"{conflict.model_name} [{conflict.natural_key}] is no longer in the corpus. "
            "Nothing was changed."
        )
        raise ContentError(gone_from_corpus_msg)
    obj, source_path = entry
    fields = dict(obj["fields"])
    fields.pop("pk", None)
    lookup = _extract_natural_key(model, fields, source_path)
    instance = _find_existing_case_insensitive(model, lookup)
    if instance is None:
        gone_from_db_msg = (
            f"{conflict.model_name} [{conflict.natural_key}] no longer exists in the "
            "database. Nothing was changed."
        )
        raise ContentError(gone_from_db_msg)
    return instance


def _reload_single_entry(model_label: str, natural_key: str, content_root) -> str:
    """Re-run ``build_all`` and upsert exactly the one entry this conflict names.

    Returns the outcome string ``_upsert_fixture_object`` returns
    (``"created"``, ``"updated"``, ``"skipped"``, ``"deferred"``, or
    ``"conflict"``) - the caller (``content_conflict_resolve``) treats
    anything other than ``"created"`` as a failed reload and rolls the whole
    transaction back, since the row was just deleted specifically to make
    room for a fresh corpus-sourced create.
    """
    from core_management.content_fixtures import (  # noqa: PLC0415
        BuildResult,
        ContentError,
        _upsert_fixture_object,
        resolve_fixture_model,
    )

    model = resolve_fixture_model(model_label)
    entry = _locate_corpus_entry(content_root, model_label, natural_key)
    if entry is None:
        gone_from_corpus_msg = (
            f"{model_label} [{natural_key}] is no longer in the corpus - reload cannot recreate it."
        )
        raise ContentError(gone_from_corpus_msg)
    obj, source_path = entry
    return _upsert_fixture_object(model, obj, source_path, BuildResult())


def _delete_and_reload(model, model_label: str, content_root, conflict) -> str | None:
    """Delete the conflict's row and reload it from the corpus in one transaction.

    Returns ``None`` on success, or a user-facing error message on failure -
    the transaction has already rolled back by the time this returns, so a
    ``ProtectedError``, a ``ContentError`` from either helper, or a raw
    database error all leave the original row untouched. Split out of
    ``content_conflict_resolve`` (ruff C901) so that view's own branching
    (superuser gate, content-root check, digest check, typed-key check) stays
    separate from this transaction's three-way exception handling.
    """
    from django.db import (  # noqa: PLC0415
        Error as DjangoDbError,
        transaction,
    )
    from django.db.models import ProtectedError  # noqa: PLC0415

    from core_management.content_fixtures import (  # noqa: PLC0415
        OUTCOME_CREATED,
        ContentError,
    )

    try:
        with transaction.atomic():
            instance = _instance_for_conflict(model, content_root, conflict)
            instance.delete()
            outcome = _reload_single_entry(model_label, conflict.natural_key, content_root)
            if outcome != OUTCOME_CREATED:
                reload_failed_msg = (
                    f"Reload after delete did not recreate the row (outcome: {outcome}). "
                    "Transaction rolled back; the original row is untouched."
                )
                raise ContentError(reload_failed_msg)
    except ProtectedError as exc:
        return f"Cannot delete: other rows protect this one ({exc.args[0]})."
    except ContentError as exc:
        return str(exc)
    except DjangoDbError as exc:
        # Mirrors content_load_views.content_load_run: an unmigrated or
        # unreachable DB is the one environmental failure mode left once
        # ContentError/ProtectedError are both ruled out.
        return (
            f"Database error while resolving conflict: {exc} "
            "(hint: run `arx manage migrate` to bring the dev DB schema up to date)."
        )
    return None


def _locate_corpus_entry(content_root, model_label: str, natural_key: str):
    """Find the corpus fixture object matching ``(model_label, natural_key)``.

    Returns ``(obj, source_path)`` or ``None``. Computes each candidate's
    natural-key display string on a throwaway copy of its fields (mirroring
    ``load_conflicts._scan_object``, never mutating the real ``obj``) so the
    match is against exactly the same string ``scan_load_conflicts`` would
    have shown for this row.
    """
    from core_management.content_fixtures import (  # noqa: PLC0415
        ContentError,
        _extract_natural_key,
        build_all,
        resolve_fixture_model,
    )

    model = resolve_fixture_model(model_label)
    result = build_all(content_root)
    for output_path, objects in result.fixtures.items():
        paths = result.source_paths.get(output_path, [])
        for obj, source_path in zip(objects, paths, strict=False):
            if obj.get("model") != model_label:
                continue
            fields = dict(obj["fields"])
            fields.pop("pk", None)
            try:
                lookup = _extract_natural_key(model, fields, source_path)
            except ContentError:
                continue
            if ", ".join(str(v) for v in lookup.values()) == natural_key:
                return obj, source_path
    return None


@staff_member_required
@require_GET
def content_conflicts(request: HttpRequest) -> HttpResponse:
    """List every current credited-row load conflict under the content repo."""
    if not request.user.is_superuser:
        raise PermissionDenied

    from core_management.content_repo import resolve_content_root  # noqa: PLC0415
    from core_management.load_conflicts import scan_load_conflicts  # noqa: PLC0415

    content_root = resolve_content_root()
    if content_root is None:
        messages.error(
            request,
            MSG_CONTENT_REPO_PATH_NOT_SET,
        )
        return HttpResponseRedirect(reverse("admin_game_setup"))

    conflicts = scan_load_conflicts(content_root)
    context = {
        "title": "Load conflicts",
        "conflicts": conflicts,
        # Pre-built (conflict, detail_url) pairs so the template never has to
        # assemble a querystring itself - keeps every template line well
        # under the 100-char limit without splitting a URL across lines
        # (which would embed whitespace inside an href attribute value).
        "conflict_rows": [
            {"conflict": c, "detail_url": _detail_url(c.model_label, c.natural_key)}
            for c in conflicts
        ],
    }
    return render(request, "admin/content_conflicts.html", context)


@staff_member_required
@require_GET
def content_conflict_detail(request: HttpRequest) -> HttpResponse:
    """Show one conflict's field-by-field diff and the typed-confirmation form."""
    if not request.user.is_superuser:
        raise PermissionDenied

    from core_management.content_repo import resolve_content_root  # noqa: PLC0415
    from core_management.load_conflicts import find_load_conflict  # noqa: PLC0415

    content_root = resolve_content_root()
    if content_root is None:
        messages.error(
            request,
            MSG_CONTENT_REPO_PATH_NOT_SET,
        )
        return HttpResponseRedirect(reverse("admin_game_setup"))

    model_label = request.GET.get("model", "")
    key = request.GET.get("key", "")
    conflict = find_load_conflict(content_root, model_label, key)
    if conflict is None:
        messages.info(request, f"{model_label} [{key}] is no longer in conflict.")
        return HttpResponseRedirect(reverse("admin_content_conflicts"))

    context = {
        "title": "Load conflict",
        "conflict": conflict,
        "model_label": model_label,
        "key": key,
        "resolve_url": reverse("admin_content_conflict_resolve"),
    }
    return render(request, "admin/content_conflict_detail.html", context)


@staff_member_required
@require_POST
def content_conflict_resolve(request: HttpRequest) -> HttpResponse:
    """Delete a credited row and reload it from the corpus, after typed confirmation.

    Runs entirely inside one transaction: the delete and the reload either
    both land or neither does. A wrong typed key never touches the row at
    all - the mismatch check runs before the transaction opens. Same for a
    stale digest (#3017 review): the detail page hands back a hash of the
    diff it rendered, and if the corpus or the DB row changed between that
    GET and this POST, the row is still a genuine conflict - so a bare
    re-fetch-and-compare wouldn't catch it - but the diff the operator typed
    the key against is no longer the diff this POST would apply. Refuse and
    send them back to review the current diff.
    """
    if not request.user.is_superuser:
        raise PermissionDenied

    from core_management.content_fixtures import resolve_fixture_model  # noqa: PLC0415
    from core_management.content_repo import resolve_content_root  # noqa: PLC0415
    from core_management.load_conflicts import find_load_conflict  # noqa: PLC0415

    content_root = resolve_content_root()
    if content_root is None:
        messages.error(
            request,
            MSG_CONTENT_REPO_PATH_NOT_SET,
        )
        return HttpResponseRedirect(reverse("admin_game_setup"))

    model_label = request.POST.get("model", "")
    key = request.POST.get("key", "")
    detail_url = _detail_url(model_label, key)

    conflict = find_load_conflict(content_root, model_label, key)
    if conflict is None:
        messages.info(request, f"{model_label} [{key}] is no longer in conflict.")
        return HttpResponseRedirect(reverse("admin_content_conflicts"))

    if request.POST.get("digest", "") != conflict.digest:
        messages.error(
            request, "The corpus or row changed since you reviewed this diff. Review it again."
        )
        return HttpResponseRedirect(detail_url)

    if request.POST.get("typed_key", "") != conflict.natural_key:
        messages.error(request, "Typed key does not match. Nothing was changed.")
        return HttpResponseRedirect(detail_url)

    model = resolve_fixture_model(model_label)
    error_msg = _delete_and_reload(model, model_label, content_root, conflict)
    if error_msg is not None:
        messages.error(request, error_msg)
        return HttpResponseRedirect(detail_url)

    messages.success(
        request, f"{conflict.model_name} [{conflict.natural_key}] now matches the repo."
    )
    return HttpResponseRedirect(reverse("admin_content_conflicts"))
