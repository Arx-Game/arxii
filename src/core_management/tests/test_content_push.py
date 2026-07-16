"""Tests for the content push pipeline."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import tempfile
from unittest import mock

from django.test import TestCase

from core_management.content_push import (
    ContentPushError,
    push_content_to_repo,
)


def _init_git_repo(path: Path) -> None:
    """Initialize a bare-ish git repo at ``path`` with an initial commit."""
    subprocess.run(["git", "init", "-b", "main", str(path)], capture_output=True, check=True)
    subprocess.run(
        ["git", "-C", str(path), "config", "user.email", "test@example.com"],
        capture_output=True,
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(path), "config", "user.name", "Test"],
        capture_output=True,
        check=True,
    )
    # Add a dummy origin so the remote check passes (push will fail, but
    # tests that exercise push use a local bare repo instead).
    subprocess.run(
        ["git", "-C", str(path), "remote", "add", "origin", "/dev/null"],
        capture_output=True,
        check=True,
    )
    # Create an initial commit so HEAD exists.
    readme = path / "README.md"
    readme.write_text("# test repo\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(path), "add", "."], capture_output=True, check=True)
    subprocess.run(
        ["git", "-C", str(path), "commit", "-m", "initial"],
        capture_output=True,
        check=True,
    )


class ContentPushTests(TestCase):
    """Tests for push_content_to_repo."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        _init_git_repo(self.root)

    def _write_fixture(self, app: str = "magic", model: str = "effecttype") -> Path:
        """Write a dummy fixture file and return its path."""
        fixtures_dir = self.root / "fixtures" / app
        fixtures_dir.mkdir(parents=True, exist_ok=True)
        path = fixtures_dir / f"{model}.json"
        path.write_text(
            '[{"model": "magic.effecttype", "fields": {"name": "Test"}}]\n', encoding="utf-8"
        )
        return path

    def test_push_commits_and_reports_staged_files(self) -> None:
        """A fixture file is staged, committed, and the result reports it."""
        self._write_fixture()
        result = push_content_to_repo(self.root)
        assert result.committed
        assert result.files_staged >= 1
        assert result.commit_sha  # non-empty
        # The commit should exist in git log.
        log = subprocess.run(
            ["git", "-C", str(self.root), "log", "--oneline", "-1"],
            capture_output=True,
            text=True,
            check=True,
        )
        assert "Update content fixtures" in log.stdout

    def test_push_no_changes_returns_not_committed(self) -> None:
        """When there are no changes, committed=False and files_staged=0."""
        result = push_content_to_repo(self.root)
        assert not result.committed
        assert result.files_staged == 0

    def test_push_raises_on_not_a_git_repo(self) -> None:
        """A non-git directory raises ContentPushError."""
        from pathlib import Path
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ContentPushError) as ctx:
                push_content_to_repo(Path(tmp))
            assert "not a git repository" in str(ctx.exception).lower()

    def test_push_raises_on_wrong_branch(self) -> None:
        """When the repo is not on main, raises ContentPushError."""
        self._write_fixture()
        subprocess.run(
            ["git", "-C", str(self.root), "checkout", "-b", "feature"],
            capture_output=True,
            check=True,
        )
        with self.assertRaises(ContentPushError) as ctx:
            push_content_to_repo(self.root)
        assert "main" in str(ctx.exception)

    def test_push_raises_on_no_remote(self) -> None:
        """When the repo has no origin remote, raises ContentPushError."""
        self._write_fixture()
        # Remove the origin added in setUp.
        subprocess.run(
            ["git", "-C", str(self.root), "remote", "remove", "origin"],
            capture_output=True,
            check=True,
        )
        with self.assertRaises(ContentPushError) as ctx:
            push_content_to_repo(self.root)
        assert "origin" in str(ctx.exception).lower()

    def test_push_raises_on_missing_content_root(self) -> None:
        """When CONTENT_REPO_PATH is not set and no arg given, raises."""
        with mock.patch.dict("os.environ", {}, clear=False):
            os.environ.pop("CONTENT_REPO_PATH", None)
            with self.assertRaises(ContentPushError):
                push_content_to_repo(None)

    def test_push_only_stages_fixtures_dir(self) -> None:
        """Files outside fixtures/ are not staged by the push."""
        self._write_fixture()
        # Write a file outside fixtures/.
        (self.root / "notes.md").write_text("not a fixture", encoding="utf-8")
        result = push_content_to_repo(self.root)
        assert result.committed
        # notes.md should not be in the commit.
        show = subprocess.run(
            ["git", "-C", str(self.root), "show", "--stat", "--name-only", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
        assert "notes.md" not in show.stdout
        assert "fixtures/" in show.stdout

    def test_push_commit_message_includes_file_count(self) -> None:
        """The auto-generated commit message mentions the file count."""
        self._write_fixture()
        self._write_fixture("conditions", "damagetype")
        result = push_content_to_repo(self.root)
        assert result.committed
        assert "file" in result.commit_message.lower()
