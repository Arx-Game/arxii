"""Tests for the row-level content export session (#3018)."""

from __future__ import annotations

from pathlib import Path
import subprocess
import tempfile
from unittest import mock

from django.test import TestCase

from core_management.content_push import ContentPushError
from core_management.content_session import (
    SESSION_BRANCH,
    _remote_slug,
    commit_row_export,
    discard_all_pending,
    discard_row_export,
    ensure_session_branch,
    open_session_pr,
    row_diff,
    row_is_addition_at_head,
    session_diff,
    session_state,
)
from core_management.github_rest import GitHubRestError, github_request
from core_management.tests._git_fixtures import (
    init_origin_and_clone as _init_origin_and_clone,
    run_git as _run,
)


class ContentSessionTests(TestCase):
    """Tests for the branch-as-session git flow."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        self.origin = base / "origin.git"
        self.root = base / "clone"
        _init_origin_and_clone(self.origin, self.root)

    def _write_row(self, name: str = "row.json", content: str = '{"a": 1}\n') -> Path:
        """Write a dummy content row and return its absolute path."""
        path = self.root / "content" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def test_ensure_creates_branch_from_origin_main(self) -> None:
        ensure_session_branch(self.root)
        branch = _run(self.root, "branch", "--show-current").stdout.strip()
        assert branch == SESSION_BRANCH

    def test_ensure_reuses_unmerged_branch(self) -> None:
        ensure_session_branch(self.root)
        path = self._write_row()
        commit_row_export(self.root, [path], "row export")
        log_before = _run(self.root, "log", "--oneline", "-1").stdout

        ensure_session_branch(self.root)

        branch = _run(self.root, "branch", "--show-current").stdout.strip()
        log_after = _run(self.root, "log", "--oneline", "-1").stdout
        assert branch == SESSION_BRANCH
        assert log_before == log_after
        assert "row export" in log_after

    def test_ensure_recreates_after_merge(self) -> None:
        ensure_session_branch(self.root)
        path = self._write_row()
        commit_row_export(self.root, [path], "row export")
        _run(self.root, "push", "-u", "origin", SESSION_BRANCH)

        # Simulate the session PR merging: a second clone fast-forwards
        # origin/main to the session branch's tip and pushes it.
        merger = Path(self.tmp.name) / "merger"
        subprocess.run(
            ["git", "clone", str(self.origin), str(merger)], capture_output=True, check=True
        )
        _run(merger, "config", "user.email", "test@example.com")
        _run(merger, "config", "user.name", "Test")
        _run(merger, "fetch", "origin", SESSION_BRANCH)
        _run(merger, "merge", "--ff-only", f"origin/{SESSION_BRANCH}")
        _run(merger, "push", "origin", "main")

        ensure_session_branch(self.root)

        branch = _run(self.root, "branch", "--show-current").stdout.strip()
        assert branch == SESSION_BRANCH
        log = _run(self.root, "log", "--oneline", "origin/main..HEAD").stdout
        assert log.strip() == ""

    def test_ensure_refuses_dirty_tree_on_merged_session_branch(self) -> None:
        """A dirty working tree must refuse even when the merged-recreate path would fire.

        Without this check, ensure_session_branch would detach off the session
        branch and force-delete it out from under uncommitted local changes.
        """
        ensure_session_branch(self.root)
        path = self._write_row()
        commit_row_export(self.root, [path], "row export")
        _run(self.root, "push", "-u", "origin", SESSION_BRANCH)

        merger = Path(self.tmp.name) / "merger2"
        subprocess.run(
            ["git", "clone", str(self.origin), str(merger)], capture_output=True, check=True
        )
        _run(merger, "config", "user.email", "test@example.com")
        _run(merger, "config", "user.name", "Test")
        _run(merger, "fetch", "origin", SESSION_BRANCH)
        _run(merger, "merge", "--ff-only", f"origin/{SESSION_BRANCH}")
        _run(merger, "push", "origin", "main")

        # Still on SESSION_BRANCH locally, now with an uncommitted change.
        (self.root / "dirty2.txt").write_text("uncommitted", encoding="utf-8")

        with self.assertRaises(ContentPushError) as ctx:
            ensure_session_branch(self.root)
        assert "pending export" in str(ctx.exception)
        assert "Confirm or discard it" in str(ctx.exception)

        branch = _run(self.root, "branch", "--show-current").stdout.strip()
        assert branch == SESSION_BRANCH
        # Nothing was deleted or detached - the session commit is still HEAD.
        log = _run(self.root, "log", "--oneline", "-1").stdout
        assert "row export" in log

    def test_ensure_refuses_dirty_foreign_branch(self) -> None:
        (self.root / "dirty.txt").write_text("uncommitted", encoding="utf-8")

        with self.assertRaises(ContentPushError) as ctx:
            ensure_session_branch(self.root)
        assert "uncommitted changes" in str(ctx.exception)

        branch = _run(self.root, "branch", "--show-current").stdout.strip()
        assert branch == "main"
        status = _run(self.root, "status", "--short").stdout
        assert "dirty.txt" in status

    def test_commit_row_export_commits_named_paths_only(self) -> None:
        ensure_session_branch(self.root)
        target = self._write_row("target.json")
        self._write_row("other.json")

        sha = commit_row_export(self.root, [target], "export target")

        assert sha
        status = _run(self.root, "status", "--short").stdout
        assert "other.json" in status
        assert "target.json" not in status

    def test_discard_restores_tracked_and_removes_new(self) -> None:
        ensure_session_branch(self.root)
        tracked = self._write_row("tracked.json")
        commit_row_export(self.root, [tracked], "seed tracked")
        tracked.write_text('{"a": 2}\n', encoding="utf-8")
        new_file = self._write_row("new.json")

        discard_row_export(self.root, [tracked, new_file])

        assert tracked.read_text(encoding="utf-8") == '{"a": 1}\n'
        assert not new_file.exists()
        status = _run(self.root, "status", "--short").stdout
        assert status.strip() == ""

    def test_discard_all_pending_restores_tracked_and_removes_untracked(self) -> None:
        ensure_session_branch(self.root)
        tracked = self._write_row("tracked.json")
        commit_row_export(self.root, [tracked], "seed tracked")
        tracked.write_text('{"a": 2}\n', encoding="utf-8")
        new_file = self._write_row("brand_new.json")

        discard_all_pending(self.root)

        assert tracked.read_text(encoding="utf-8") == '{"a": 1}\n'
        assert not new_file.exists()
        status = _run(self.root, "status", "--short").stdout
        assert status.strip() == ""

    def test_discard_all_pending_handles_missing_fixtures_directory(self) -> None:
        """One of the two pathspecs having zero tracked entries must not fail the call.

        ``git checkout -- fixtures/ content/`` errors outright if EITHER
        pathspec matches no tracked file - the common case here, since this
        checkout never wrote anything under ``fixtures/`` at all.
        """
        ensure_session_branch(self.root)
        assert not (self.root / "fixtures").exists()
        self._write_row("untracked.json")

        discard_all_pending(self.root)

        status = _run(self.root, "status", "--short").stdout
        assert status.strip() == ""

    def test_discard_all_pending_is_noop_on_clean_tree(self) -> None:
        ensure_session_branch(self.root)

        discard_all_pending(self.root)

        status = _run(self.root, "status", "--short").stdout
        assert status.strip() == ""

    def test_row_and_session_diff_render(self) -> None:
        ensure_session_branch(self.root)
        path = self._write_row("diffme.json")
        commit_row_export(self.root, [path], "seed diffme")
        path.write_text('{"a": 2}\n', encoding="utf-8")

        diff = row_diff(self.root, [path])
        assert diff.strip()
        assert "diffme.json" in diff

        s_diff = session_diff(self.root)
        assert "diffme.json" in s_diff

    def test_row_diff_shows_untracked_addition(self) -> None:
        """A brand-new, never-committed export shows as a full-file addition (#3018).

        Plain ``git diff`` only compares tracked content and renders empty
        for an untracked path - the common case for a row's first-ever
        export, since nothing has been committed for it yet.
        """
        ensure_session_branch(self.root)
        path = self._write_row("untracked.json", '{"a": 1}\n')

        diff = row_diff(self.root, [path])

        assert "untracked.json" in diff
        assert "new file mode" in diff
        assert '+{"a": 1}' in diff
        status = _run(self.root, "status", "--short").stdout
        assert "?? content/" in status

    def test_row_is_addition_at_head_untracked_path_is_addition(self) -> None:
        ensure_session_branch(self.root)
        path = self._write_row("brand_new.json", '[{"model": "m", "fields": {"name": "A"}}]\n')

        assert row_is_addition_at_head(self.root, [path], ["name"], {"name": "A"}) is True

    def test_row_is_addition_at_head_json_key_present_is_not_addition(self) -> None:
        ensure_session_branch(self.root)
        path = self._write_row("known.json", '[{"model": "m", "fields": {"name": "A"}}]\n')
        commit_row_export(self.root, [path], "seed known row")

        assert row_is_addition_at_head(self.root, [path], ["name"], {"name": "A"}) is False

    def test_row_is_addition_at_head_json_key_absent_is_addition(self) -> None:
        ensure_session_branch(self.root)
        path = self._write_row("known2.json", '[{"model": "m", "fields": {"name": "A"}}]\n')
        commit_row_export(self.root, [path], "seed known2 row")

        assert row_is_addition_at_head(self.root, [path], ["name"], {"name": "B"}) is True

    def test_row_is_addition_at_head_folds_case(self) -> None:
        ensure_session_branch(self.root)
        path = self._write_row("cased.json", '[{"model": "m", "fields": {"name": "Alpha"}}]\n')
        commit_row_export(self.root, [path], "seed cased row")

        assert row_is_addition_at_head(self.root, [path], ["name"], {"name": "alpha"}) is False

    def test_row_is_addition_at_head_no_key_fields_fails_closed(self) -> None:
        ensure_session_branch(self.root)
        path = self._write_row("nokey.json", '[{"model": "m", "fields": {"name": "A"}}]\n')
        commit_row_export(self.root, [path], "seed nokey row")

        assert row_is_addition_at_head(self.root, [path], None, {"name": "A"}) is True

    def test_row_is_addition_at_head_unparseable_json_fails_closed(self) -> None:
        ensure_session_branch(self.root)
        path = self._write_row("bad.json", "not json\n")
        commit_row_export(self.root, [path], "seed bad row")

        assert row_is_addition_at_head(self.root, [path], ["name"], {"name": "A"}) is True

    def test_open_session_pr_posts_and_returns_url(self) -> None:
        # origin stays the local bare fixture repo (the push must succeed for
        # real); only the derived owner/repo slug is mocked, so the REST call
        # shape can be asserted without an actual GitHub-shaped remote URL.
        ensure_session_branch(self.root)
        path = self._write_row("pr.json")
        commit_row_export(self.root, [path], "pr row")

        with (
            self.settings(GITHUB_ISSUE_TOKEN="tok"),
            mock.patch(
                "core_management.content_session._remote_slug", return_value=("acme", "lore")
            ),
            mock.patch("core_management.github_rest.requests.get") as mock_get,
            mock.patch("core_management.github_rest.requests.post") as mock_post,
        ):
            mock_get.return_value.status_code = 200
            mock_get.return_value.json.return_value = []
            mock_post.return_value.status_code = 201
            mock_post.return_value.json.return_value = {
                "html_url": "https://github.com/acme/lore/pull/9"
            }
            url = open_session_pr(self.root, title="t", body="b")

        assert url == "https://github.com/acme/lore/pull/9"
        get_url = mock_get.call_args.args[0]
        assert "head=acme:content-export-session" in get_url
        assert "state=open" in get_url
        post_payload = mock_post.call_args.kwargs["json"]
        assert post_payload["head"] == SESSION_BRANCH
        assert post_payload["base"] == "main"
        # The session branch was pushed to origin before the REST calls.
        log = _run(self.origin, "log", "--oneline", "-1", SESSION_BRANCH).stdout
        assert "pr row" in log

    def test_open_session_pr_reuses_open_pr(self) -> None:
        ensure_session_branch(self.root)
        path = self._write_row("pr2.json")
        commit_row_export(self.root, [path], "pr row 2")

        with (
            self.settings(GITHUB_ISSUE_TOKEN="tok"),
            mock.patch(
                "core_management.content_session._remote_slug", return_value=("acme", "lore")
            ),
            mock.patch("core_management.github_rest.requests.get") as mock_get,
            mock.patch("core_management.github_rest.requests.post") as mock_post,
        ):
            mock_get.return_value.status_code = 200
            mock_get.return_value.json.return_value = [
                {"html_url": "https://github.com/acme/lore/pull/3"}
            ]
            url = open_session_pr(self.root, title="t", body="b")

        assert url == "https://github.com/acme/lore/pull/3"
        mock_post.assert_not_called()

    def test_remote_slug_parses_both_url_forms(self) -> None:
        _run(self.root, "remote", "set-url", "origin", "https://github.com/acme/lore.git")
        assert _remote_slug(self.root) == ("acme", "lore")

        _run(self.root, "remote", "set-url", "origin", "git@github.com:acme/lore")
        assert _remote_slug(self.root) == ("acme", "lore")

    def test_remote_slug_failure_message_strips_embedded_credentials(self) -> None:
        token = "ghp_supersecrettoken123"  # noqa: S105 - test fixture value, not a real secret
        _run(
            self.root,
            "remote",
            "set-url",
            "origin",
            f"https://{token}@github.com/acme/lore.git",
        )

        with self.assertRaises(ContentPushError) as ctx:
            _remote_slug(self.root)

        assert token not in str(ctx.exception)

    def test_session_state_reports_branch_commits_and_dirty(self) -> None:
        ensure_session_branch(self.root)
        path = self._write_row("state.json")
        commit_row_export(self.root, [path], "state commit")
        self._write_row("untracked.json")

        state = session_state(self.root)

        assert state.branch == SESSION_BRANCH
        assert state.on_session is True
        assert any("state commit" in line for line in state.commits)
        assert "state.json" in state.diff_stat
        assert any("untracked.json" in line for line in state.dirty)

    def test_github_request_wraps_non_json_success_body(self) -> None:
        """A 2xx response with a non-JSON body raises GitHubRestError, not a bare ValueError."""
        with (
            self.settings(GITHUB_ISSUE_TOKEN="tok"),
            mock.patch("core_management.github_rest.requests.get") as mock_get,
        ):
            mock_get.return_value.status_code = 200
            mock_get.return_value.json.side_effect = ValueError("not json")

            with self.assertRaises(GitHubRestError) as ctx:
                github_request("GET", "/repos/acme/lore/pulls")

        assert "200" in str(ctx.exception)
