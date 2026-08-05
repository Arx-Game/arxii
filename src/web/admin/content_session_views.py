"""Superuser-only content session page + one-pull-request-per-session flow (#3018).

The session branch (``core_management.content_session.SESSION_BRANCH``) is the
scratch space every row export (``content_row_export_views.py``) commits into,
one small commit per row. This module is the operator's view onto that
accumulated state - the branch name, the commit list, the full diff against
``origin/main`` - and the one action that turns it into review: pushing the
branch and opening (or reusing) its pull request.

Two views: ``content_session`` (GET) renders the page; ``content_session_pr``
(POST) reads the posted title/body, calls ``core_management.content_session
.open_session_pr``, and redirects back to the session page with a flash
either way. ``open_session_pr``, ``session_diff`` and ``session_state`` are
imported at module scope (not the local-import idiom the sibling row-export
views use) so a test can mock ``open_session_pr`` directly at this module's
import site without needing a real GitHub-shaped remote.
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
from core_management.content_session import open_session_pr, session_diff, session_state

_CONTENT_ROOT_UNSET_MSG = (
    "CONTENT_REPO_PATH is not set. Add it to src/.env pointing at your "
    "local checkout of the private content repository."
)

_DEFAULT_PR_BODY = "Authored in the Arx II admin; exported row by row with per-row diffs reviewed."


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
    diff_text = session_diff(content_root) if state.on_session else ""

    context = {
        "title": "Content session",
        "state": state,
        "diff_text": diff_text,
        "pr_title": f"Content session {timezone.now().date().isoformat()}",
        "pr_body": _DEFAULT_PR_BODY,
        "pr_url": reverse("admin_content_session_pr"),
    }
    return render(request, "admin/content_session.html", context)


@staff_member_required
@require_POST
def content_session_pr(request: HttpRequest) -> HttpResponse:
    """Push the session branch and open (or reuse) its pull request.

    Always redirects back to the session page - success flashes the pull
    request's URL, and a ``ContentPushError`` from the push/API call flashes
    as an error instead of raising.
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
        return HttpResponseRedirect(reverse("admin_content_session"))

    messages.success(request, f"Opened the session pull request: {url}")
    return HttpResponseRedirect(reverse("admin_content_session"))
