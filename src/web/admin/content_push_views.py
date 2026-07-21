"""Superuser-only push-to-content-repo surface.

Mirrors the content-export pattern: the private content repository (never
named here) is located via the ``CONTENT_REPO_PATH`` environment variable.
Drives ``core_management.content_push.push_content_to_repo`` the same way
``tools/push_content.py`` does.

The GET preview shows a git status/diff summary so the operator can review
what will be committed before clicking the button. The POST runs the
commit + push.
"""

from __future__ import annotations

from pathlib import Path
import subprocess

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.core.exceptions import PermissionDenied
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST

from core_management.content_repo import resolve_content_root

_CONFIRM_TEMPLATE = "admin/content_push_confirm.html"

GIT_TRUE = "true"


def _git(repo: Path, *args: str) -> tuple[int, str, str]:
    """Run a git command in ``repo``, returning (returncode, stdout, stderr)."""
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return result.returncode, result.stdout.strip(), result.stderr.strip()


def _is_git_repo(path: Path) -> bool:
    """Return True if ``path`` is inside a git working tree."""
    code, out, _ = _git(path, "rev-parse", "--is-inside-work-tree")
    return code == 0 and out == GIT_TRUE


@staff_member_required
@require_GET
def content_push_preview(request: HttpRequest) -> HttpResponse:
    """Show a preview of what would be committed and pushed."""
    if not request.user.is_superuser:
        raise PermissionDenied

    content_root = resolve_content_root()
    context = {
        "title": "Push content to lore repo",
        "content_repo_configured": bool(content_root),
        "branch": "",
        "has_changes": False,
        "status_lines": "",
        "diff_stat": "",
        "file_count": 0,
    }

    if not content_root:
        return render(request, _CONFIRM_TEMPLATE, context)

    if not _is_git_repo(content_root):
        context["error"] = f"{content_root} is not a git repository."
        return render(request, _CONFIRM_TEMPLATE, context)

    _, branch, _ = _git(content_root, "branch", "--show-current")
    context["branch"] = branch

    _, status_out, _ = _git(content_root, "status", "--short")
    context["status_lines"] = status_out
    context["has_changes"] = bool(status_out)

    _, diff_out, _ = _git(content_root, "diff", "HEAD", "--stat")
    context["diff_stat"] = diff_out

    # Count changed files.
    if status_out:
        context["file_count"] = len([line for line in status_out.splitlines() if line.strip()])

    return render(request, _CONFIRM_TEMPLATE, context)


@staff_member_required
@require_POST
def content_push_run(request: HttpRequest) -> HttpResponse:
    """Commit and push fixture changes to the lore repo. Superuser-only."""
    if not request.user.is_superuser:
        raise PermissionDenied

    from core_management.content_push import (  # noqa: PLC0415
        ContentPushError,
        push_content_to_repo,
    )

    try:
        result = push_content_to_repo()
    except ContentPushError as exc:
        messages.error(request, str(exc))
        return HttpResponseRedirect(reverse("admin_game_setup"))

    if not result.committed:
        messages.info(request, "No changes to commit — working tree is clean.")
        return HttpResponseRedirect(reverse("admin_game_setup"))

    msg = f"Content push: {result.files_staged} file(s) committed"
    if result.commit_sha:
        msg += f" ({result.commit_sha})"
    if result.rebased:
        msg += ", rebased on remote"
    if result.pushed:
        msg += ", pushed to origin main."
    else:
        msg += ", push FAILED."
    messages.success(request, msg)

    for err in result.errors:
        messages.error(request, err)

    return HttpResponseRedirect(reverse("admin_game_setup"))
