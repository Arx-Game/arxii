"""Superuser-only content session page + one-pull-request-per-session flow (#3018).

The session branch (``core_management.content_session.SESSION_BRANCH``) is the
scratch space every row export (``content_row_export_views.py``) commits into,
one small commit per row. This module is the operator's view onto that
accumulated state - the branch name, the commit list, the full diff against
``origin/main`` - and the one action that turns it into review: pushing the
branch and opening (or reusing) its pull request.

Two views: ``content_session`` (GET) renders the page; ``content_session_pr``
(POST) reads the posted title/body, calls ``core_management.content_session
.open_session_pr``, and redirects back to the session page with a flash on
success. ``open_session_pr``, ``session_diff`` and ``session_state`` are
imported at module scope (not the local-import idiom the sibling row-export
views use) so a test can mock ``open_session_pr`` directly at this module's
import site without needing a real GitHub-shaped remote.

A dirty working tree (``SessionState.dirty``) always means a row export is
sitting uncommitted, pending confirm or discard (see
``content_session.ensure_session_branch``'s docstring) - the page renders
those ``git status --short`` lines verbatim so the operator can see which
files, and when the *same browser session* holds the row-export module's
pending-export record (#3018 review), names that row with a link straight to
its diff page instead of leaving the operator to go hunting for it.
"""

from __future__ import annotations

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.core.exceptions import PermissionDenied
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from core_management.content_push import ContentPushError
from core_management.content_session import (
    SessionState,
    open_session_pr,
    session_diff,
    session_state,
)
from web.admin.content_row_export_views import (
    _diff_url,
    _pending_export,
    _pending_export_display_name,
)

_CONTENT_ROOT_UNSET_MSG = (
    "CONTENT_REPO_PATH is not set. Add it to src/.env pointing at your "
    "local checkout of the private content repository."
)

_DEFAULT_PR_BODY = "Authored in the Arx II admin; exported row by row with per-row diffs reviewed."


def _default_pr_title() -> str:
    """Return the PR form's default title, dated for today."""
    return f"Content session {timezone.now().date().isoformat()}"


def _pending_row_display(request: HttpRequest, state: SessionState) -> dict | None:
    """Return the pending row's display info, or ``None`` if there isn't one to show.

    Only shown when the tree is actually dirty - a stale pending-export
    session record with a clean tree (the row was already confirmed or
    discarded from another tab) has nothing left to point at.
    """
    if not state.dirty:
        return None
    pending = _pending_export(request)
    if pending is None:
        return None
    return {
        "model_name": _pending_export_display_name(pending["model_label"]),
        "natural_key": pending["natural_key"],
        "diff_url": _diff_url(pending["model_label"], pending["pk"]),
    }


def _session_context(
    request: HttpRequest, state: SessionState, pr_title: str, pr_body: str
) -> dict:
    """Build the ``content_session.html`` template context shared by both views.

    ``diff_text`` is deliberately not set here - both callers overwrite it
    right after, since computing it needs ``content_root`` too and the two
    callers already have it in scope.
    """
    return {
        "title": "Content session",
        "state": state,
        "dirty_text": "\n".join(state.dirty),
        "pending_row": _pending_row_display(request, state),
        "pr_title": pr_title,
        "pr_body": pr_body,
        "pr_url": reverse("admin_content_session_pr"),
    }


@staff_member_required
@require_GET
def content_session(request: HttpRequest) -> HttpResponse:
    """Show the session branch's commits, diff, and the open-pull-request form.

    When the checkout isn't currently on the session branch (no export has
    started one yet, or its pull request already merged and the branch was
    recycled), the diff is left empty rather than computed - the template
    renders a plain "no session yet" state instead of an empty diff block.
    """
    if not request.user.is_superuser:
        raise PermissionDenied

    from core_management.content_repo import resolve_content_root  # noqa: PLC0415

    content_root = resolve_content_root()
    if content_root is None:
        messages.error(request, _CONTENT_ROOT_UNSET_MSG)
        return HttpResponseRedirect(reverse("admin_game_setup"))

    state = session_state(content_root)
    context = _session_context(request, state, _default_pr_title(), _DEFAULT_PR_BODY)
    context["diff_text"] = session_diff(content_root) if state.on_session else ""
    return render(request, "admin/content_session.html", context)


@staff_member_required
@require_POST
def content_session_pr(request: HttpRequest) -> HttpResponse:
    """Push the session branch and open (or reuse) its pull request.

    Success redirects back to the session page with a flash naming the pull
    request's URL. A ``ContentPushError`` from the push/API call instead
    renders the session page directly (not a redirect) with the posted
    title/body still in the form - a redirect would lose them, since the GET
    view always recomputes the dated default (#3018 review).
    """
    if not request.user.is_superuser:
        raise PermissionDenied

    from core_management.content_repo import resolve_content_root  # noqa: PLC0415

    content_root = resolve_content_root()
    if content_root is None:
        messages.error(request, _CONTENT_ROOT_UNSET_MSG)
        return HttpResponseRedirect(reverse("admin_game_setup"))

    title = request.POST.get("title", "")
    body = request.POST.get("body", "")

    try:
        url = open_session_pr(content_root, title=title, body=body)
    except ContentPushError as exc:
        messages.error(request, str(exc))
        state = session_state(content_root)
        context = _session_context(request, state, title, body)
        context["diff_text"] = session_diff(content_root) if state.on_session else ""
        return render(request, "admin/content_session.html", context)

    messages.success(request, f"Opened the session pull request: {url}")
    return HttpResponseRedirect(reverse("admin_content_session"))
