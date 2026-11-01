"""Renumber a PR's migrations after main's tip when ``max_migration.txt`` is the only conflict.

Since #2906 collapsed every first-party app into ``arxii`` there is one migration
sequence and one ``max_migration.txt``, so any two migration-bearing PRs conflict.
This is the deterministic fix CI applies (#4879), and it does nothing else:

1. **Preconditions.** Against its merge base the PR adds one or more migration files
   forming a single linear chain off the base's tip, changes ``max_migration.txt``
   to that chain's last name, and touches no other file in the migrations
   directory. No tracked ``.py`` file outside the chain names one of its
   migrations. Main has moved its own tip since the merge base.
2. **Merge.** ``git merge --no-commit <main>``. A merge, never a rebase, so the PR's
   published history (and the evidence URLs pointing into it) survives. Any
   conflicted path besides ``max_migration.txt`` is a refusal.
3. **Transform.** Rename the chain to ``<main tip + 1>``, ``<main tip + 2>``, ... and
   rewrite each file's single in-app dependency to its new predecessor (main's tip
   for the first). Only that string literal changes; it is spliced in place, quote
   style kept. This is ``django-linear-migrations``' ``rebase_migration`` applied link
   by link: that tool handles one migration only (on a chain it re-points the tip and
   orphans the rest) and guesses the sides from ``MERGE_HEAD``; here both sides are
   read explicitly from the two refs.
4. **Postconditions**, re-derived from the index independently of the transform: the
   migrations directory differs from main by exactly the renamed chain plus
   ``max_migration.txt``; each renamed file's AST equals the PR's original except for
   that one dependency name; the graph has one ``arxii`` leaf and no migrations are
   missing.

On any refusal or failed check the merge is aborted and the tree is left as it was.
Exit codes: 0 resolved (a merge commit was made), 3 nothing to do, 4 refused.
The JSON result is printed, and also written to ``--result`` when given.
"""

from __future__ import annotations

import argparse
import ast
from dataclasses import asdict, dataclass, field
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

APP_LABEL = "arxii"
MIGRATIONS_DIR = "src/world/migrations"
MAX_MIGRATION = "max_migration.txt"
MIGRATION_FILE = re.compile(r"^(\d{4})_(\w+)\.py$")
GIT = shutil.which("git") or "git"

EXIT_RESOLVED = 0
EXIT_NOTHING_TO_DO = 3
EXIT_REFUSED = 4


class RefusalError(Exception):
    """The PR is outside the one shape this script will touch."""


class NothingToDoError(Exception):
    """There is no max_migration.txt conflict to resolve."""


@dataclass
class Rename:
    old: str
    new: str


@dataclass
class Plan:
    main_tip: str
    renames: list[Rename]
    warnings: list[str] = field(default_factory=list)


@dataclass
class Result:
    status: str
    reason: str = ""
    main_tip: str = ""
    renames: list[Rename] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------- git


def _run(argv: list[str], cwd: Path, stdin: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(  # noqa: S603 - fixed argv built here, no shell
        argv, cwd=cwd, input=stdin, capture_output=True, text=True, check=False
    )


def git(*args: str, cwd: Path, check: bool = True, stdin: str | None = None) -> str:
    proc = _run([GIT, *args], cwd, stdin)
    if check and proc.returncode != 0:
        msg = f"git {' '.join(args)} failed ({proc.returncode}): {proc.stderr.strip()}"
        raise RuntimeError(msg)
    return proc.stdout


def show(rev: str, path: str, cwd: Path) -> str:
    return git("show", f"{rev}:{path}", cwd=cwd)


def max_migration_at(rev: str, migrations_dir: str, cwd: Path) -> str:
    lines = show(rev, f"{migrations_dir}/{MAX_MIGRATION}", cwd).splitlines()
    if len(lines) != 1 or not MIGRATION_FILE.match(lines[0].strip() + ".py"):
        msg = f"{MAX_MIGRATION} at {rev} is not a single migration name: {lines!r}"
        raise RefusalError(msg)
    return lines[0].strip()


def name_status(base: str, rev: str | None, path: str, cwd: Path) -> list[tuple[str, str]]:
    """``(status, path)`` rows; ``rev=None`` compares ``base`` with the index."""
    revs = ["--cached", base] if rev is None else [base, rev]
    out = git("diff", "--no-renames", "--name-status", *revs, "--", path, cwd=cwd)
    rows = []
    for line in out.splitlines():
        status, _, file_path = line.partition("\t")
        rows.append((status, file_path))
    return sorted(rows)


# --------------------------------------------------------------- migration source


def _dependencies_node(source: str, filename: str) -> ast.List | ast.Tuple:
    """Return the ``dependencies = [...]`` literal of the file's Migration class."""
    try:
        module = ast.parse(source)
    except SyntaxError as exc:
        msg = f"{filename} does not parse: {exc}"
        raise RefusalError(msg) from exc
    classes = [n for n in module.body if isinstance(n, ast.ClassDef) and n.name == "Migration"]
    if len(classes) != 1:
        msg = f"{filename} has {len(classes)} Migration classes, expected 1"
        raise RefusalError(msg)
    assigns = [
        n
        for n in classes[0].body
        if isinstance(n, ast.Assign)
        and len(n.targets) == 1
        and isinstance(n.targets[0], ast.Name)
        and n.targets[0].id == "dependencies"
    ]
    if len(assigns) != 1 or not isinstance(assigns[0].value, (ast.List, ast.Tuple)):
        msg = f"{filename} has no single literal `dependencies = [...]`"
        raise RefusalError(msg)
    return assigns[0].value


def _is_in_app_pair(dep: ast.expr) -> bool:
    return (
        isinstance(dep, (ast.Tuple, ast.List))
        and len(dep.elts) == 2  # noqa: PLR2004 - (app_label, migration name)
        and all(isinstance(e, ast.Constant) and isinstance(e.value, str) for e in dep.elts)
        and isinstance(dep.elts[0], ast.Constant)
        and dep.elts[0].value == APP_LABEL
    )


def in_app_dependency(source: str, filename: str) -> ast.Constant:
    """Return the string node naming this file's one ``arxii`` dependency."""
    deps = _dependencies_node(source, filename).elts
    found = [d.elts[1] for d in deps if _is_in_app_pair(d)]  # type: ignore[attr-defined]
    if len(found) != 1 or not isinstance(found[0], ast.Constant):
        msg = f"{filename} has {len(found)} `{APP_LABEL}` dependencies, expected exactly 1"
        raise RefusalError(msg)
    return found[0]


def _offset(lines: list[str], lineno: int, col: int) -> int:
    """Character offset of an ast (line, UTF-8 byte column) position."""
    line = lines[lineno - 1]
    return sum(len(x) for x in lines[: lineno - 1]) + len(line.encode()[:col].decode())


def rewrite_dependency(source: str, filename: str, new_name: str) -> str:
    """Splice ``new_name`` into the in-app dependency literal, keeping its quote style."""
    node = in_app_dependency(source, filename)
    lines = source.splitlines(keepends=True)
    if node.end_lineno is None or node.end_col_offset is None:
        msg = f"{filename}: no end position for the dependency literal"
        raise RefusalError(msg)
    start = _offset(lines, node.lineno, node.col_offset)
    end = _offset(lines, node.end_lineno, node.end_col_offset)
    literal = source[start:end]
    if (
        literal[:1] not in {'"', "'"}
        or literal[-1:] != literal[:1]
        or literal != repr_like(literal[:1], node.value)
    ):
        msg = f"{filename}'s dependency is not a plain one-line string literal: {literal!r}"
        raise RefusalError(msg)
    return source[:start] + repr_like(literal[:1], new_name) + source[end:]


def repr_like(quote: str, value: str) -> str:
    return f"{quote}{value}{quote}"


def _normalised(source: str, filename: str) -> str:
    """AST dump with the in-app dependency name blanked out."""
    node = in_app_dependency(source, filename)
    module = ast.parse(source)
    for sub in ast.walk(module):
        if (
            isinstance(sub, ast.Constant)
            and sub.lineno == node.lineno
            and sub.col_offset == node.col_offset
        ):
            sub.value = "<in-app dependency>"
    return ast.dump(module, include_attributes=False)


def verify_rewrite(original: str, rewritten: str, filename: str, expected_dep: str) -> None:
    """The rewritten file differs from the original in the one dependency name only."""
    if in_app_dependency(rewritten, filename).value != expected_dep:
        msg = f"{filename}: in-app dependency is not {expected_dep}"
        raise RefusalError(msg)
    if _normalised(original, filename) != _normalised(rewritten, filename):
        msg = f"{filename}: the rewrite changed more than the in-app dependency"
        raise RefusalError(msg)


# ---------------------------------------------------------------------- planning


def _added_migrations(repo: Path, merge_base: str, main_ref: str, mdir: str) -> list[str]:
    """Names the PR adds; refuses any other change under the migrations dir."""
    max_path = f"{mdir}/{MAX_MIGRATION}"
    if ("M", max_path) not in name_status(merge_base, main_ref, mdir, repo):
        msg = f"main has not moved {MAX_MIGRATION} since the merge base"
        raise NothingToDoError(msg)
    pr_rows = name_status(merge_base, "HEAD", mdir, repo)
    if ("M", max_path) not in pr_rows:
        msg = f"the PR does not change {MAX_MIGRATION}"
        raise NothingToDoError(msg)
    added = []
    for status, path in pr_rows:
        if path == max_path:
            continue
        in_dir = Path(path).parent.as_posix() == mdir
        if status != "A" or not in_dir or not MIGRATION_FILE.match(Path(path).name):
            msg = f"the PR changes {path} ({status}); only adding NNNN_name.py files is handled"
            raise RefusalError(msg)
        added.append(Path(path).stem)
    return added


def _linear_chain(repo: Path, added: list[str], base_tip: str, mdir: str) -> list[str]:
    deps = {
        name: in_app_dependency(show("HEAD", f"{mdir}/{name}.py", repo), f"{name}.py").value
        for name in added
    }
    chain: list[str] = []
    prev = base_tip
    remaining = dict(deps)
    while remaining:
        nxt = [n for n, d in remaining.items() if d == prev]
        if len(nxt) != 1:
            msg = (
                f"the PR's migrations are not one linear chain off {base_tip}: "
                f"{len(nxt)} of them depend on {prev} (dependencies: {deps})"
            )
            raise RefusalError(msg)
        chain.append(nxt[0])
        prev = nxt[0]
        del remaining[nxt[0]]
    return chain


def _renames(repo: Path, chain: list[str], main_ref: str, main_tip: str, mdir: str) -> list:
    main_names = {
        Path(p).stem
        for p in git("ls-tree", "--name-only", f"{main_ref}:{mdir}", cwd=repo).split()
        if MIGRATION_FILE.match(p)
    }
    main_number = int(main_tip.split("_", 1)[0])
    renames = []
    for i, old in enumerate(chain):
        new = f"{main_number + 1 + i:04d}_{old.split('_', 1)[1]}"
        if new in main_names:
            msg = f"renaming {old} to {new} collides with main's {new}"
            raise RefusalError(msg)
        renames.append(Rename(old=old, new=new))
    return renames


def _outside_mentions(repo: Path, chain: list[str], mdir: str) -> list[str]:
    """Refuse a chain name used in code elsewhere; return non-code mentions as warnings."""
    chain_files = {f"{mdir}/{n}.py" for n in chain} | {f"{mdir}/{MAX_MIGRATION}"}
    warnings = []
    for name in chain:
        out = git("grep", "-l", "-F", name, "HEAD", "--", ".", cwd=repo, check=False)
        hits = [p.removeprefix("HEAD:") for p in out.splitlines()]
        hits = [p for p in hits if p not in chain_files]
        code = [p for p in hits if p.endswith(".py")]
        if code:
            msg = f"{name} is named in code outside its own file, so a rename breaks it: {code}"
            raise RefusalError(msg)
        warnings += [f"{p} mentions {name}" for p in hits]
    return warnings


def plan(repo: Path, main_ref: str, mdir: str) -> Plan:
    """Check every precondition against HEAD (the PR) and ``main_ref``. No writes."""
    merge_base = git("merge-base", "HEAD", main_ref, cwd=repo).strip()
    added = _added_migrations(repo, merge_base, main_ref, mdir)
    base_tip = max_migration_at(merge_base, mdir, repo)
    pr_tip = max_migration_at("HEAD", mdir, repo)
    main_tip = max_migration_at(main_ref, mdir, repo)
    if not added:
        msg = f"the PR changes {MAX_MIGRATION} but adds no migration"
        raise RefusalError(msg)
    chain = _linear_chain(repo, added, base_tip, mdir)
    if chain[-1] != pr_tip:
        msg = f"the PR's {MAX_MIGRATION} names {pr_tip}, not its chain tip {chain[-1]}"
        raise RefusalError(msg)
    if int(main_tip.split("_", 1)[0]) <= int(base_tip.split("_", 1)[0]):
        msg = f"main's tip {main_tip} is not after the merge base's {base_tip}"
        raise RefusalError(msg)
    renames = _renames(repo, chain, main_ref, main_tip, mdir)
    warnings = _outside_mentions(repo, chain, mdir)
    return Plan(main_tip=main_tip, renames=renames, warnings=warnings)


# ---------------------------------------------------------------------- applying


def merge_main(repo: Path, main_ref: str, max_path: str) -> None:
    proc = _run([GIT, "merge", "--no-ff", "--no-commit", main_ref], repo)
    conflicted = set(git("diff", "--name-only", "--diff-filter=U", cwd=repo).split())
    if proc.returncode == 0 and not conflicted:
        msg = "merging main produced no conflict"
        raise NothingToDoError(msg)
    if conflicted != {max_path}:
        others = sorted(conflicted - {max_path})
        msg = f"merging main conflicts on more than {MAX_MIGRATION}: {others or proc.stderr}"
        raise RefusalError(msg)


def apply_renames(repo: Path, the_plan: Plan, mdir: str) -> None:
    prev = the_plan.main_tip
    for rename in the_plan.renames:
        original = (repo / mdir / f"{rename.old}.py").read_text()
        rewritten = rewrite_dependency(original, f"{rename.old}.py", prev)
        git("mv", f"{mdir}/{rename.old}.py", f"{mdir}/{rename.new}.py", cwd=repo)
        (repo / mdir / f"{rename.new}.py").write_text(rewritten)
        prev = rename.new
    (repo / mdir / MAX_MIGRATION).write_text(f"{prev}\n")
    git("add", "--", mdir, cwd=repo)


def verify_against_main(repo: Path, the_plan: Plan, main_ref: str, mdir: str) -> None:
    """Re-derive the outcome from the index, independent of how it got there."""
    max_path = f"{mdir}/{MAX_MIGRATION}"
    rows = name_status(main_ref, None, mdir, repo)
    expected = sorted([("M", max_path)] + [("A", f"{mdir}/{r.new}.py") for r in the_plan.renames])
    if rows != expected:
        msg = f"the migrations differ from main by {rows}, expected exactly {expected}"
        raise RefusalError(msg)
    staged_max = git("show", f":{max_path}", cwd=repo)
    if staged_max != f"{the_plan.renames[-1].new}\n":
        msg = f"{MAX_MIGRATION} holds {staged_max!r}"
        raise RefusalError(msg)
    prev = the_plan.main_tip
    for rename in the_plan.renames:
        original = show("HEAD", f"{mdir}/{rename.old}.py", repo)
        staged = git("show", f":{mdir}/{rename.new}.py", cwd=repo)
        verify_rewrite(original, staged, f"{rename.new}.py", prev)
        prev = rename.new


GRAPH_CHECK = f"""
import sys
sys.path.insert(0, "tools")
import check_migrations as c
c.setup_environment()
import django
django.setup()
from django.db.migrations.loader import MigrationLoader
leaves = [n for a, n in MigrationLoader(None).graph.leaf_nodes() if a == "{APP_LABEL}"]
print("leaves:", leaves)
changes = c.collect_changes(set(c.get_excluded_apps()))
print("missing:", {{k: [m.name for m in v] for k, v in changes.items()}})
sys.exit(0 if len(leaves) == 1 and not changes else 1)
"""


def verify_graph(repo: Path) -> None:
    """One arxii leaf and no missing migrations, loaded in a fresh Django process."""
    proc = _run([sys.executable, "-c", GRAPH_CHECK], repo)
    if proc.returncode != 0:
        msg = f"the migration graph check failed:\n{proc.stdout}{proc.stderr[-2000:]}"
        raise RefusalError(msg)


def commit_message(the_plan: Plan, main_ref: str) -> str:
    lines = [
        f"Merge {main_ref}; renumber this branch's migrations after {the_plan.main_tip}",
        "",
        f"{MAX_MIGRATION} was the only conflict. Renamed by tools/auto_rebase_migration.py",
        "(#4879); in each file only the in-app dependency changed:",
        "",
    ]
    lines += [f"  {r.old} -> {r.new}" for r in the_plan.renames]
    return "\n".join(lines) + "\n"


def _abort(repo: Path) -> None:
    if git("rev-parse", "-q", "--verify", "MERGE_HEAD", cwd=repo, check=False).strip():
        git("merge", "--abort", cwd=repo, check=False)


def run(repo: Path, main_ref: str, mdir: str, *, check_graph: bool) -> Result:
    if git("status", "--porcelain", "--untracked-files=no", cwd=repo).strip():
        return Result(status="refused", reason="the working tree is not clean")
    try:
        the_plan = plan(repo, main_ref, mdir)
        merge_main(repo, main_ref, f"{mdir}/{MAX_MIGRATION}")
        apply_renames(repo, the_plan, mdir)
        verify_against_main(repo, the_plan, main_ref, mdir)
        if check_graph:
            verify_graph(repo)
        # --no-verify: the hooks are the PR's own CI, which this push triggers.
        git(
            "commit",
            "--no-verify",
            "-q",
            "-F",
            "-",
            cwd=repo,
            stdin=commit_message(the_plan, main_ref),
        )
    except NothingToDoError as exc:
        _abort(repo)
        return Result(status="nothing-to-do", reason=str(exc))
    except RefusalError as exc:
        _abort(repo)
        return Result(status="refused", reason=str(exc))
    except Exception:
        _abort(repo)
        raise
    return Result(
        status="resolved",
        main_tip=the_plan.main_tip,
        renames=the_plan.renames,
        warnings=the_plan.warnings,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n", 1)[0])
    parser.add_argument("--main-ref", default="origin/main")
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--migrations-dir", default=MIGRATIONS_DIR)
    parser.add_argument("--result", type=Path, help="also write the JSON result here")
    parser.add_argument(
        "--skip-graph-check", action="store_true", help="tests only: no Django to load"
    )
    args = parser.parse_args(argv)
    result = run(
        args.repo, args.main_ref, args.migrations_dir, check_graph=not args.skip_graph_check
    )
    payload = json.dumps(asdict(result), indent=2)
    print(payload)
    if args.result:
        args.result.write_text(payload + "\n")
    codes = {"resolved": EXIT_RESOLVED, "nothing-to-do": EXIT_NOTHING_TO_DO}
    return codes.get(result.status, EXIT_REFUSED)


if __name__ == "__main__":
    raise SystemExit(main())
