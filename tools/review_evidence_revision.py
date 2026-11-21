"""Verify that a report revision remains valid through independently checked updates."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

from auto_rebase_migration import (
    GIT,
    MIGRATIONS_DIR,
    NothingToDoError,
    RefusalError,
    apply_doc_renames,
    apply_renames,
    git,
    merge_main,
    plan,
    verify_against_main,
    verify_doc_renames,
)

BOT_EMAIL = "41898282+github-actions[bot]@users.noreply.github.com"
BOT_NAME = "arx-migration-rebase"
BOT_SUBJECT = "Merge origin/main; renumber this branch's migrations after "
SHA = re.compile(r"^[0-9a-f]{40}$")


def is_migration_update(repo: Path, revision: str) -> bool:
    """Recognize candidates; their trees still need full independent verification."""
    identity = git("show", "-s", "--format=%an%n%ae%n%s", revision, cwd=repo).splitlines()
    return (
        len(identity) == len((BOT_NAME, BOT_EMAIL, BOT_SUBJECT))
        and identity[0] == BOT_NAME
        and identity[1] == BOT_EMAIL
        and identity[2].startswith(BOT_SUBJECT)
    )


def verify_migration_update(repo: Path, revision: str, main_ref: str) -> str:
    """Reproduce a candidate's complete tree without executing any PR code.

    Use a disposable shared clone with hooks disabled. The trusted transformer
    reads migration ASTs and docs as data; graph loading and linting are omitted
    here because those execute PR code/config and already belong to normal CI.
    """
    parents = git("show", "-s", "--format=%P", revision, cwd=repo).split()
    merge_parents = 2
    if len(parents) != merge_parents:
        message = f"migration update {revision} must have exactly two parents"
        raise RefusalError(message)
    previous, merged_main = parents
    ancestor = subprocess.run(  # noqa: S603 - fixed git argv, no shell
        [GIT, "merge-base", "--is-ancestor", merged_main, main_ref],
        cwd=repo,
        check=False,
        capture_output=True,
    )
    if ancestor.returncode:
        message = f"migration update {revision} did not merge an ancestor of main"
        raise RefusalError(message)
    with tempfile.TemporaryDirectory(prefix="evidence-migration-") as directory:
        replay = Path(directory) / "repo"
        git(
            "-c",
            "init.templateDir=",
            "clone",
            "--shared",
            "--no-checkout",
            "--quiet",
            str(repo.resolve()),
            str(replay),
            cwd=repo,
        )
        git("config", "core.hooksPath", "/dev/null", cwd=replay)
        git("config", "user.name", "Evidence verifier", cwd=replay)
        git("config", "user.email", "evidence@localhost", cwd=replay)
        git("checkout", "--quiet", "--detach", previous, cwd=replay)
        expected = plan(replay, merged_main, MIGRATIONS_DIR)
        merge_main(replay, merged_main, f"{MIGRATIONS_DIR}/max_migration.txt")
        apply_renames(replay, expected, MIGRATIONS_DIR)
        verify_against_main(replay, expected, merged_main, MIGRATIONS_DIR)
        before, after = apply_doc_renames(replay, expected)
        verify_doc_renames(replay, expected, before, after)
        actual_tree = git("rev-parse", f"{revision}^{{tree}}", cwd=repo).strip()
        if after != actual_tree:
            message = f"migration update {revision} differs from the reproduced tree"
            raise RefusalError(message)
    return previous


def verify_clean_main_merge(repo: Path, revision: str, main_ref: str) -> str | None:
    """Peel a conflict-free main merge only when its entire tree is reproducible."""
    parents = git("show", "-s", "--format=%P", revision, cwd=repo).split()
    merge_parents = 2
    if len(parents) != merge_parents:
        return None
    previous, merged_main = parents
    ancestor = subprocess.run(  # noqa: S603 - fixed git argv, no shell
        [GIT, "merge-base", "--is-ancestor", merged_main, main_ref],
        cwd=repo,
        check=False,
        capture_output=True,
    )
    if ancestor.returncode:
        return None
    # A fresh clone does not inherit the source repository's merge drivers or hooks.
    with tempfile.TemporaryDirectory(prefix="evidence-clean-merge-") as directory:
        replay = Path(directory) / "repo"
        git(
            "-c",
            "init.templateDir=",
            "clone",
            "--shared",
            "--no-checkout",
            "--quiet",
            str(repo.resolve()),
            str(replay),
            cwd=repo,
        )
        result = subprocess.run(  # noqa: S603 - fixed git argv, no shell
            [GIT, "merge-tree", "--write-tree", previous, merged_main],
            cwd=replay,
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode:
            print(
                f"Merge {revision} has conflicts or could not be reproduced; "
                "review its changes and refresh the evidence.",
                file=sys.stderr,
            )
            return None
        expected = result.stdout.splitlines()[0]
        actual = git("rev-parse", f"{revision}^{{tree}}", cwd=repo).strip()
        if expected != actual:
            print(
                f"Merge {revision} differs from the independently reproduced merge; "
                "review its changes and refresh the evidence.",
                file=sys.stderr,
            )
            return None
    return previous


def cannot_change_a_rendered_screen(path: bytes | str) -> bool:
    """Say whether a changed path is one that can never alter what a screen renders.

    A reviewer compared pictures of the running application with the approved demo, so a
    commit may be carried over only when every path it touches is listed here. A path that
    matches no group is application code and voids the report. Each group is matched by
    directory or file extension only, never by a file name such as `conftest.py` or
    `factories.py`: a factories module can be imported by a seed, so it stays application
    code unless it sits inside a tests directory, which nothing in production imports.
    The caller diffs with `--no-renames`, so a file moved out of application code shows up
    as a deletion of that file and is refused.
    """
    text = os.fsdecode(path)
    parts = text.split("/")
    directories = parts[:-1]  # a tests segment must be a whole directory, never a file name
    name = parts[-1]
    top = parts[0]
    # The temporary evidence directories hold only the report and its pictures; the journey
    # harness, its fixtures and its live seeds are imported only by tests (and by
    # test_settings, which installs the app for the test runner); browser specs and their
    # support files run Playwright against a server and are not bundled into the application;
    # the frontend test setup runs under vitest; documents and GitHub configuration are never
    # read by the running application.
    neutral_prefixes = (
        "docs/reviews/",
        ".github/issue-evidence/",
        "src/integration_tests/",
        "frontend/e2e/",
        "frontend/src/test/",
        "docs/",
        ".github/",
    )
    return (
        text.startswith(neutral_prefixes)
        # A directory named exactly tests under src/ or tools/ holds unit tests and their
        # helpers, and production code does not import from one. src/world/seeds/ is
        # production code and is not matched, only a tests directory inside it would be.
        or (top in {"src", "tools"} and "tests" in directories)
        # Frontend unit test files and __tests__ directories run under vitest and are not
        # imported by application modules.
        or (top == "frontend" and name.endswith((".test.ts", ".test.tsx")))
        or (top == "frontend" and "__tests__" in directories)
        # Any Markdown file, including the CLAUDE.md files that sit beside the code, is
        # documentation that nothing in the application reads.
        or name.endswith(".md")
    )


def verify_commit_cannot_change_a_screen(repo: Path, revision: str) -> str:
    """Carry a report across a single-parent commit that touches only neutral paths."""
    parents = git("show", "-s", "--format=%P", revision, cwd=repo).split()
    if len(parents) != 1:
        message = f"cannot verify update {revision}; review the changes and refresh evidence"
        raise RefusalError(message)
    parent = parents[0]
    changes = subprocess.run(  # noqa: S603 - fixed git argv, no shell
        [GIT, "diff", "--no-renames", "--name-only", "-z", parent, revision, "--"],
        cwd=repo,
        check=True,
        capture_output=True,
    ).stdout.split(b"\0")
    if any(path and not cannot_change_a_rendered_screen(path) for path in changes):
        message = f"update {revision} changes reviewed content; review it and refresh evidence"
        raise RefusalError(message)
    return parent


def reviewed_revision(
    repo: Path, head: str, main_ref: str = "origin/main", *, anchor: str | None = None
) -> str:
    """Validate an anchor through proven safe updates, or retain legacy parent semantics."""
    if not SHA.fullmatch(head):
        message = "head must be a full commit SHA"
        raise RefusalError(message)
    if anchor is not None and not SHA.fullmatch(anchor):
        message = "reviewed revision must be a full commit SHA"
        raise RefusalError(message)
    current = head
    while current != anchor:
        if is_migration_update(repo, current):
            try:
                previous = verify_migration_update(repo, current, main_ref)
            except NothingToDoError as exc:
                message = f"migration update {current} cannot be reproduced: {exc}"
                raise RefusalError(message) from exc
        else:
            previous = verify_clean_main_merge(repo, current, main_ref)
            if previous is None:
                if anchor is None:
                    break
                previous = verify_commit_cannot_change_a_screen(repo, current)
        print(
            f"Verified safe update {current}; retaining evidence from {previous}", file=sys.stderr
        )
        current = previous
    if anchor is not None:
        return current
    return git("rev-parse", f"{current}^1", cwd=repo).strip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("head")
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--reviewed-revision", help="revision named by the review report")
    parser.add_argument("--report", type=Path, help="validated review report")
    parser.add_argument("--main-ref", default="origin/main")
    args = parser.parse_args()
    try:
        anchor = args.reviewed_revision
        if args.report:
            from validate_review_evidence import _field  # noqa: PLC0415

            anchor = _field(
                args.report.read_text(encoding="utf-8").splitlines(), "Reviewed revision"
            ).strip("`")
        print(reviewed_revision(args.repo, args.head, args.main_ref, anchor=anchor))
    except (RefusalError, RuntimeError) as exc:
        print(f"Cannot carry review evidence forward: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
