"""Resolve the evidence revision through independently verified migration merges.

The historical evidence contract is HEAD^1. A migration bot merge adds no new
reviewed feature, so replay its deterministic transformation and retain the
original head's contract. Commit names alone never authorize carry-forward.
"""

from __future__ import annotations

import argparse
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


def reviewed_revision(repo: Path, head: str, main_ref: str = "origin/main") -> str:
    """Retain HEAD^1 semantics while peeling only proven migration bot updates."""
    if not SHA.fullmatch(head):
        message = "head must be a full commit SHA"
        raise RefusalError(message)
    current = head
    while is_migration_update(repo, current):
        try:
            previous = verify_migration_update(repo, current, main_ref)
        except NothingToDoError as exc:
            message = f"migration update {current} cannot be reproduced: {exc}"
            raise RefusalError(message) from exc
        print(
            f"Verified migration update {current}; retaining evidence from {previous}",
            file=sys.stderr,
        )
        current = previous
    return git("rev-parse", f"{current}^1", cwd=repo).strip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("head")
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--main-ref", default="origin/main")
    args = parser.parse_args()
    try:
        print(reviewed_revision(args.repo, args.head, args.main_ref))
    except (RefusalError, RuntimeError) as exc:
        print(f"Cannot carry review evidence forward: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
