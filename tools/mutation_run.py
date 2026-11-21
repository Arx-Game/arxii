"""The mutation run (#4248): which test group notices each small change to one file.

Run via: just mutate <source-file> --kept <label>... --units <label>... [options]
         uv run python tools/mutation_run.py <source-file> --kept <label>... --units <label>...

Example:
    just mutate src/world/magic/services/primum.py --functions points_to_power \\
        --kept integration_tests.fuzz.test_primum_curve_fuzz \\
        --units world.magic.tests.test_primum_math

cosmic-ray (pinned, run through ``uvx`` so it is never a project dependency) generates
small changes to the source file and applies them one at a time. Each change is tried
against two groups of tests that the caller names: the kept group (journeys and
properties) and the units group. The driver never infers which tests belong to which
group. It reports, per change, whether the kept group, only the units group, or neither
group failed. A run changes the source file on disk, so the file must be committed and
nothing else may touch the worktree while it runs. Every exit path, an interrupt
included, writes the original bytes back.

Output goes to ``--out`` (default ``.mutation/<source file stem>/``): ``changes.csv``,
``unit_tests.csv`` and ``report.md``, plus the session databases and configs. Exit 0
means the report was written. Exit 2 is a refusal with one sentence on stderr. The
report is a measurement and never a gate.
"""

from __future__ import annotations

import argparse
import ast
from collections import Counter
from collections.abc import Sequence
from contextlib import closing
import csv
from dataclasses import dataclass
import os
from pathlib import Path
import re
import shlex
import shutil
import signal
import sqlite3
import subprocess
import sys
import time
from types import FrameType
import uuid

_REPO_ROOT = Path(__file__).resolve().parent.parent

COSMIC_RAY = ("uvx", "--from", "cosmic-ray==8.9.0", "cosmic-ray")

# The changes worth grading, each with cosmic-ray's ``core/`` prefix. Bitwise and shift
# operators and the two variable operators are left out because their changes are noise.
# cosmic-ray 8.9.0 has no operator for ``in`` and ``not in``, so those two are absent.
OPERATORS: tuple[str, ...] = tuple(
    f"core/{name}"
    for name in (
        "ReplaceBinaryOperator_Add_Sub",
        "ReplaceBinaryOperator_Sub_Add",
        "ReplaceBinaryOperator_Mul_FloorDiv",
        "ReplaceBinaryOperator_Div_Mul",
        "ReplaceBinaryOperator_FloorDiv_Mul",
        "ReplaceBinaryOperator_Mod_FloorDiv",
        "ReplaceBinaryOperator_Pow_Mul",
        "ReplaceComparisonOperator_Lt_LtE",
        "ReplaceComparisonOperator_LtE_Lt",
        "ReplaceComparisonOperator_Gt_GtE",
        "ReplaceComparisonOperator_GtE_Gt",
        "ReplaceComparisonOperator_Lt_GtE",
        "ReplaceComparisonOperator_LtE_Gt",
        "ReplaceComparisonOperator_Gt_LtE",
        "ReplaceComparisonOperator_GtE_Lt",
        "ReplaceComparisonOperator_Eq_NotEq",
        "ReplaceComparisonOperator_NotEq_Eq",
        "ReplaceComparisonOperator_Is_IsNot",
        "ReplaceComparisonOperator_IsNot_Is",
        "ReplaceUnaryOperator_Delete_USub",
        "ReplaceUnaryOperator_Delete_Not",
        "ReplaceUnaryOperator_USub_UAdd",
        "AddNot",
        "ReplaceTrueWithFalse",
        "ReplaceFalseWithTrue",
        "ReplaceAndWithOr",
        "ReplaceOrWithAnd",
        "ReplaceBreakWithContinue",
        "ReplaceContinueWithBreak",
        "ExceptionReplacer",
        "NumberReplacer",
        "ZeroIterationForLoop",
        "RemoveDecorator",
    )
)

# The files a run owns inside ``--out``. They are removed at start, the directory never is.
_OUT_FILES = (
    "session.sqlite",
    "kept.sqlite",
    "units.sqlite",
    "kept.toml",
    "units.toml",
    "changes.csv",
    "unit_tests.csv",
    "report.md",
)

# SQLite leaves these beside a database that a killed process was writing.
_SQLITE_SIDE_FILES = ("-journal", "-wal", "-shm")
_LABEL_RE = re.compile(r"^[\w.]+$")
_NAME_RE = re.compile(r"^\w+$")
_LINES_RE = re.compile(r"^(\d+)-(\d+)$")
_TEST_ID_RE = re.compile(r"^test\w* \(([\w.]+)\)", re.MULTILINE)
_FAILING_RE = re.compile(r"^(?:FAIL|ERROR): (\w+) \(([\w.]+)\)", re.MULTILINE)
# A failure with one of these method names ran no test of its own: the class failed to set up.
_CLASS_LEVEL_METHODS = frozenset({"setUpClass", "setUpTestData", "tearDownClass"})
_RAN_RE = re.compile(r"^Ran (\d+) tests?\b", re.MULTILINE)

# cosmic-ray records exactly this text as the output of a test run that it had to stop.
_TIMEOUT_MARKER = "timeout"
# Every child process of a run carries this variable, so a sweep can find stragglers.
_TOKEN_ENV = "ARXII_MUTATION_RUN"
_TOKEN = uuid.uuid4().hex

_DEFAULT_MAX_MINUTES = 60
_TAIL_LINES = 20
_PERCENT = 100
_GRACE_SECONDS = 3.0

_SAMPLE_REASON = "left out by --sample"
_BARE_STAR_REASON = "a bare * in a parameter list"
_CHANGES_HEADER = (
    "job_id",
    "function",
    "line",
    "operator",
    "before",
    "after",
    "kept",
    "units",
    "category",
    "kept_failing",
    "units_failing",
)
_CATEGORIES = ("guarded", "units_only", "unguarded", "apart")
_LIST_TITLES = {
    "guarded": "Guarded",
    "units_only": "Units only",
    "unguarded": "Unguarded",
    "apart": "Timed out or broke the run",
}

RawResult = tuple[str, str | None, str | None, str | None]

_live: list[subprocess.Popen[str]] = []
_received_signal: list[int] = []


class Refusal(Exception):
    """A run that cannot proceed. The message is the one sentence shown on stderr."""


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:  # ty: ignore[invalid-method-override]
        raise Refusal(f"Fix the command line: {message}.")


@dataclass(frozen=True)
class Args:
    source: str
    kept: tuple[str, ...]
    units: tuple[str, ...]
    functions: tuple[str, ...]
    lines: tuple[int, int] | None
    sample: int | None
    tier: str
    out: str | None
    max_minutes: int | None


@dataclass(frozen=True)
class Change:
    job_id: str
    operator: str
    row: int
    col: int
    function: str
    occurrence: int


@dataclass(frozen=True)
class GroupOutcome:
    """How one test group fared against one change."""

    # The state is one of caught, missed, timeout or broken.
    state: str
    failing: tuple[str, ...]


@dataclass(frozen=True)
class Row:
    change: Change
    before: str
    after: str
    kept: GroupOutcome
    units: GroupOutcome
    category: str


@dataclass(frozen=True)
class Baseline:
    seconds: float
    output: str


@dataclass(frozen=True)
class Measured:
    """Everything the two groups produced, read back before the source file is restored."""

    out: Path
    changes: list[Change]
    dropped: dict[str, int]
    generated: int
    kept_seconds: float
    units_seconds: float
    marked: set[str]
    baseline_ids: set[str]
    results: dict[str, dict[str, RawResult]]
    # Per group: how many changes were run again for an empty output, and how many stayed empty.
    retries: dict[str, tuple[int, int]]


# ---------------------------------------------------------------------------
# Arguments
# ---------------------------------------------------------------------------


def _parse_lines(text: str) -> tuple[int, int]:
    match = _LINES_RE.match(text)
    if not match or int(match.group(1)) > int(match.group(2)) or int(match.group(1)) < 1:
        raise argparse.ArgumentTypeError("expected two line numbers like 434-435, low first")
    return int(match.group(1)), int(match.group(2))


def _parse_functions(text: str) -> tuple[str, ...]:
    names = tuple(name for name in text.split(",") if name)
    if not names or not all(_NAME_RE.match(name) for name in names):
        raise argparse.ArgumentTypeError("expected function names separated by commas")
    return names


def _positive(text: str) -> int:
    if not text.isdigit() or int(text) < 1:
        raise argparse.ArgumentTypeError("expected a whole number of at least 1")
    return int(text)


def _parse_args(argv: Sequence[str]) -> Args:
    parser = _Parser(
        prog="mutation_run.py",
        description="Which test group notices each small change to one source file.",
    )
    parser.add_argument("source", help="the .py file to change, relative to the repo root")
    parser.add_argument(
        "--kept", nargs="+", required=True, metavar="LABEL", help="kept test labels"
    )
    parser.add_argument("--units", nargs="+", required=True, metavar="LABEL", help="unit labels")
    scope = parser.add_mutually_exclusive_group()
    scope.add_argument("--functions", type=_parse_functions, help="function names, comma separated")
    scope.add_argument("--lines", type=_parse_lines, help="inclusive line range such as 434-435")
    parser.add_argument("--sample", type=_positive, help="keep N changes spaced evenly in the file")
    parser.add_argument("--tier", choices=("sqlite", "postgres"), default="sqlite")
    parser.add_argument("--out", help="output directory (default .mutation/<source stem>/)")
    parser.add_argument("--max-minutes", type=_positive, help="refuse a longer estimated run")
    ns = parser.parse_args(list(argv))
    return Args(
        source=ns.source,
        kept=tuple(ns.kept),
        units=tuple(ns.units),
        functions=ns.functions or (),
        lines=ns.lines,
        sample=ns.sample,
        tier=ns.tier,
        out=ns.out,
        max_minutes=ns.max_minutes,
    )


# ---------------------------------------------------------------------------
# Child processes
# ---------------------------------------------------------------------------


def _spawn(argv: Sequence[str], *, capture: bool) -> subprocess.Popen[str]:
    """Start a child in its own session, tagged so that a sweep can find it later."""
    env = {**os.environ, _TOKEN_ENV: _TOKEN}
    proc: subprocess.Popen[str] = subprocess.Popen(
        list(argv),
        cwd=_REPO_ROOT,
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE if capture else sys.stderr,
        stderr=subprocess.STDOUT if capture else None,
        text=True,
        start_new_session=True,
    )
    _live.append(proc)
    return proc


def _run_captured(argv: Sequence[str], timeout_seconds: float) -> tuple[int, str]:
    proc = _spawn(argv, capture=True)
    try:
        output, _ = proc.communicate(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        _kill_everything()
        raise Refusal(
            f"A command ran past {timeout_seconds / 60:.0f} minutes and was stopped; "
            "narrow the test labels or raise --max-minutes."
        ) from None
    return proc.returncode, output or ""


def _run_streamed(argv: Sequence[str]) -> int:
    proc = _spawn(argv, capture=False)
    return proc.wait()


def _tagged_pids() -> list[int]:
    needle = f"{_TOKEN_ENV}={_TOKEN}".encode()
    found: list[int] = []
    for proc_dir in Path("/proc").iterdir():
        entry = proc_dir.name
        if not entry.isdigit() or int(entry) == os.getpid():
            continue
        try:
            environ = (proc_dir / "environ").read_bytes()
        except OSError:
            continue
        if needle in environ:
            found.append(int(entry))
    return found


def _signal_pids(pids: Sequence[int], sig: int) -> None:
    for pid in pids:
        try:
            os.kill(pid, sig)
        except OSError:
            continue


def _kill_everything() -> None:
    """Stop every child, then every straggler that still carries the run's tag.

    The children's own process groups go first so that cosmic-ray cannot start another
    change. cosmic-ray starts each test command in a session of its own, which is why the
    tag sweep is needed after the groups are gone.
    """
    for proc in _live:
        if proc.poll() is None:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except OSError:
                proc.kill()
    deadline = time.monotonic() + _GRACE_SECONDS
    _signal_pids(_tagged_pids(), signal.SIGTERM)
    while _tagged_pids() and time.monotonic() < deadline:
        time.sleep(0.1)
    _signal_pids(_tagged_pids(), signal.SIGKILL)
    for proc in _live:
        try:
            proc.wait(timeout=_GRACE_SECONDS)
        except subprocess.TimeoutExpired:
            continue
    _live.clear()


def _on_signal(signum: int, _frame: FrameType | None) -> None:
    """Raise KeyboardInterrupt for the first signal and ignore every later one.

    A later signal can arrive while the first is unwinding toward the cleanup. Raising again
    there could skip the restore of the source file, so it is dropped.
    """
    first = not _received_signal
    _received_signal.append(signum)
    if first:
        raise KeyboardInterrupt


# ---------------------------------------------------------------------------
# Start-up checks
# ---------------------------------------------------------------------------


def _resolve_source(raw: str) -> Path:
    path = Path(raw)
    path = (path if path.is_absolute() else _REPO_ROOT / path).resolve()
    if not path.is_file():
        raise Refusal(f"The source file {raw} does not exist; give a path from the repo root.")
    if path.suffix != ".py":
        raise Refusal(f"The source file {raw} is not a .py file; name a Python module.")
    if not path.is_relative_to(_REPO_ROOT):
        raise Refusal(f"The source file {raw} is outside the repo; name a file inside it.")
    return path


def _check_labels(labels: Sequence[str]) -> None:
    for label in labels:
        if not _LABEL_RE.match(label):
            raise Refusal(f"The test label {label!r} is not a dotted test path; fix the label.")


def _check_clean(path: Path) -> None:
    result = subprocess.run(
        ["git", "status", "--porcelain", "--", str(path)],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise Refusal("git could not report the source file's status; run from a git checkout.")
    if result.stdout.strip():
        raise Refusal("The source file has uncommitted changes; commit or discard them first.")


def _check_operators() -> None:
    returncode, output = _run_captured([*COSMIC_RAY, "operators"], timeout_seconds=600)
    if returncode != 0:
        raise Refusal("cosmic-ray could not list its operators; run it by hand to see why.")
    known = {line.strip() for line in output.splitlines()}
    unknown = [name for name in OPERATORS if name not in known]
    if unknown:
        raise Refusal(
            f"cosmic-ray does not know the operator {unknown[0]}; fix OPERATORS in "
            "tools/mutation_run.py."
        )


def _test_command(tier: str, labels: Sequence[str], extra: Sequence[str] = ()) -> str:
    flags = ["--sqlite", "--exclude-tag", "postgres"] if tier == "sqlite" else ["--keepdb"]
    parts = ["uv", "run", "arx", "test", *flags, *extra, *labels]
    return f"echo yes | {shlex.join(parts)} 2>&1"


def _print_tail(output: str) -> None:
    """Show the last lines of a runner's output, which is where its failure reads."""
    print("\n".join(output.splitlines()[-_TAIL_LINES:]), file=sys.stderr)


def _baseline(command: str, name: str, timeout_seconds: float, *, must_pass: bool) -> Baseline:
    started = time.monotonic()
    returncode, output = _run_captured(["sh", "-c", command], timeout_seconds)
    seconds = time.monotonic() - started
    if must_pass:
        if returncode != 0:
            _print_tail(output)
            raise Refusal(
                f"The {name} group fails on unchanged code; fix its labels or its tests first."
            )
        ran = _RAN_RE.search(output)
        if not ran or int(ran.group(1)) == 0:
            _print_tail(output)
            raise Refusal(f"The {name} group ran no tests; check its labels.")
    return Baseline(seconds=seconds, output=output)


# ---------------------------------------------------------------------------
# Changes: generate, filter, run
# ---------------------------------------------------------------------------


def _write_config(path: Path, source: Path, timeout_seconds: float, command: str) -> None:
    lines = [
        "[cosmic-ray]",
        f"module-path = {_toml_string(str(source))}",
        f"timeout = {timeout_seconds:.1f}",
        "excluded-modules = []",
        f"test-command = {_toml_string(f'sh -c {shlex.quote(command)}')}",
        "",
        "[cosmic-ray.distributor]",
        'name = "local"',
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def _toml_string(text: str) -> str:
    escaped = text.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _annotation_spans(source: str) -> list[tuple[int, int, int, int]]:
    """Return the (row, column) start and end of every type annotation in the source.

    The rows count from 1 and the columns count characters from 0, the same coordinates
    cosmic-ray records. The ``ast`` module counts UTF-8 bytes, so each column is converted.
    """
    lines = source.split("\n")

    def column(row: int, byte_offset: int) -> int:
        return len(lines[row - 1].encode()[:byte_offset].decode(errors="ignore"))

    spans: list[tuple[int, int, int, int]] = []
    for node in ast.walk(ast.parse(source)):
        annotation: ast.expr | None = None
        if isinstance(node, ast.arg | ast.AnnAssign):
            annotation = node.annotation
        elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            annotation = node.returns
        if annotation is None or annotation.end_lineno is None or annotation.end_col_offset is None:
            continue
        spans.append(
            (
                annotation.lineno,
                column(annotation.lineno, annotation.col_offset),
                annotation.end_lineno,
                column(annotation.end_lineno, annotation.end_col_offset),
            )
        )
    return spans


def _in_annotation(change: Change, spans: Sequence[tuple[int, int, int, int]]) -> bool:
    return any((r1, c1) <= (change.row, change.col) < (r2, c2) for r1, c1, r2, c2 in spans)


def _is_bare_star(change: Change, lines: Sequence[str]) -> bool:
    """Tell whether the change sits on the bare ``*`` that ends the positional parameters.

    cosmic-ray reads that ``*`` as a multiplication and turns it into ``//``, which is a
    syntax error. The text at the change must be a single ``*`` and the next character after
    it that is not a space must be a comma or a closing bracket. A real multiplication is
    never followed directly by either, so no real operator is dropped. Only the character after
    the position is checked for a second star, because no change is ever recorded at the second
    star of ``**``: the position of the power operator is its first star.
    """
    line = lines[change.row - 1] if 0 < change.row <= len(lines) else ""
    if line[change.col : change.col + 1] != "*" or line[change.col + 1 : change.col + 2] == "*":
        return False
    return line[change.col + 1 :].lstrip()[:1] in (",", ")")


def _read_changes(session: Path) -> list[Change]:
    with closing(sqlite3.connect(session)) as con:
        rows = con.execute(
            "SELECT job_id, operator_name, start_pos_row, start_pos_col, definition_name, "
            "occurrence FROM mutation_specs"
        ).fetchall()
    return [Change(j, op, r, c, fn or "(module level)", occ) for j, op, r, c, fn, occ in rows]


def _delete_changes(session: Path, job_ids: Sequence[str]) -> None:
    con = sqlite3.connect(session)
    try:
        with con:
            con.executemany("DELETE FROM mutation_specs WHERE job_id = ?", [(j,) for j in job_ids])
            con.executemany("DELETE FROM work_items WHERE job_id = ?", [(j,) for j in job_ids])
    finally:
        con.close()


def _file_order(change: Change) -> tuple[int, int, str, int]:
    return (change.row, change.col, change.operator, change.occurrence)


def _filter_changes(
    session: Path, source_text: str, args: Args
) -> tuple[list[Change], dict[str, int], int]:
    """Drop out-of-scope changes from the session and return the rest in file order.

    The second value counts each reason for a drop, the third is how many were generated.
    """
    generated = _read_changes(session)
    dropped: dict[str, int] = {}
    remaining = list(generated)
    allowed = set(OPERATORS)

    def drop(reason: str, keep: list[Change]) -> list[Change]:
        keep_ids = {c.job_id for c in keep}
        gone = [c for c in remaining if c.job_id not in keep_ids]
        dropped[reason] = len(gone)
        _delete_changes(session, [c.job_id for c in gone])
        return keep

    remaining = drop(
        "operator not on the allowlist", [c for c in remaining if c.operator in allowed]
    )
    spans = _annotation_spans(source_text)
    remaining = drop(
        "inside a type annotation", [c for c in remaining if not _in_annotation(c, spans)]
    )
    lines = source_text.split("\n")
    remaining = drop(_BARE_STAR_REASON, [c for c in remaining if not _is_bare_star(c, lines)])

    if args.functions:
        unmatched = [n for n in args.functions if not any(c.function == n for c in remaining)]
        if unmatched:
            raise Refusal(
                f"The function {unmatched[0]} matches no change in the file; check its spelling."
            )
        names = set(args.functions)
        remaining = drop("outside --functions", [c for c in remaining if c.function in names])
    elif args.lines:
        low, high = args.lines
        remaining = drop("outside --lines", [c for c in remaining if low <= c.row <= high])

    remaining.sort(key=_file_order)
    total = len(remaining)
    if args.sample is not None and total > args.sample:
        keep = [remaining[i * total // args.sample] for i in range(args.sample)]
        remaining = drop(_SAMPLE_REASON, keep)
    return remaining, dropped, len(generated)


def _failing_ids(output: str, unit_ids: Sequence[str] | None) -> tuple[str, ...]:
    """Read the failing test ids from a runner's output.

    A class-level failure (the class could not set up) names the class, not a test. For the
    units group, ``unit_ids`` is every test id of the baseline, and the class id is replaced
    by each baseline id inside that class, because none of them ran. A class with no baseline
    id is dropped. For the kept group ``unit_ids`` is None and the class id stays as shown.
    """
    found: list[str] = []
    for method, dotted in _FAILING_RE.findall(output):
        if unit_ids is not None and method in _CLASS_LEVEL_METHODS:
            found.extend(test for test in unit_ids if test.startswith(f"{dotted}."))
        else:
            found.append(dotted)
    return tuple(dict.fromkeys(found))


def _classify(result: RawResult | None, unit_ids: Sequence[str] | None = None) -> GroupOutcome:
    """Turn one recorded result into caught, missed, timeout or broken."""
    if result is None:
        return GroupOutcome("broken", ())
    worker_outcome, output, test_outcome, _diff = result
    output = output or ""
    if worker_outcome != "NORMAL":
        return GroupOutcome("broken", ())
    if test_outcome == "KILLED" and output == _TIMEOUT_MARKER:
        return GroupOutcome("timeout", ())
    failing = _failing_ids(output, unit_ids)
    if not _RAN_RE.search(output) or any("_FailedTest" in name for name in failing):
        return GroupOutcome("broken", failing)
    if test_outcome == "KILLED":
        return GroupOutcome("caught", failing)
    if test_outcome == "SURVIVED":
        return GroupOutcome("missed", ())
    return GroupOutcome("broken", failing)


def _read_results(
    session: Path,
) -> dict[str, RawResult]:
    with closing(sqlite3.connect(session)) as con:
        rows = con.execute(
            "SELECT job_id, worker_outcome, output, test_outcome, diff FROM work_results"
        ).fetchall()
    return {job: (worker, output, test, diff) for job, worker, output, test, diff in rows}


def _diff_lines(diff: str | None) -> tuple[str, str]:
    before = after = ""
    for line in (diff or "").splitlines():
        if line.startswith("-") and not line.startswith("---") and not before:
            before = line[1:].strip()
        elif line.startswith("+") and not line.startswith("+++") and not after:
            after = line[1:].strip()
    return before, after


def _categorise(kept: GroupOutcome, units: GroupOutcome, marked: set[str]) -> str:
    if {kept.state, units.state} & {"timeout", "broken"}:
        return "apart"
    if kept.state == "caught" or marked & set(units.failing):
        return "guarded"
    if units.state == "caught":
        return "units_only"
    return "unguarded"


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


def _write_changes_csv(path: Path, rows: Sequence[Row]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(_CHANGES_HEADER)
        for row in rows:
            writer.writerow(
                [
                    row.change.job_id,
                    row.change.function,
                    row.change.row,
                    row.change.operator,
                    row.before,
                    row.after,
                    row.kept.state,
                    row.units.state,
                    row.category,
                    " ".join(row.kept.failing),
                    " ".join(row.units.failing),
                ]
            )


def _unit_test_tallies(rows: Sequence[Row]) -> dict[str, tuple[int, int]]:
    """Count, for each unit test that failed on a change outside ``apart``, two numbers.

    The first is how many such changes the test caught. The second is how many of those
    the kept group did not catch.
    """
    tallies: dict[str, tuple[int, int]] = {}
    for row in rows:
        if row.category == "apart":
            continue
        for test in row.units.failing:
            caught, missed = tallies.get(test, (0, 0))
            tallies[test] = (caught + 1, missed + (1 if row.category != "guarded" else 0))
    return tallies


def _write_unit_tests_csv(
    path: Path, tallies: dict[str, tuple[int, int]], marked: set[str]
) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["test", "caught", "kept_missed", "note"])
        for test in sorted(tallies):
            caught, missed = tallies[test]
            note = "regression, not graded" if test in marked else ""
            writer.writerow([test, caught, missed, note])


def _share(prefix: str, numerator: int, denominator: int) -> str:
    if denominator == 0:
        return f"{prefix}: none."
    percent = round(_PERCENT * numerator / denominator)
    return f"{prefix}: {numerator} of {denominator} ({percent}%)."


def _list_line(row: Row, category: str) -> str:
    head = f"line {row.change.row}, {row.change.function}: {row.before} -> {row.after}"
    if category == "apart":
        return f"- {head} [kept {row.kept.state}, units {row.units.state}]"
    if category == "guarded":
        tests = row.kept.failing or row.units.failing
    elif category == "units_only":
        tests = row.units.failing
    else:
        tests = ()
    return f"- {head} [{', '.join(tests) if tests else 'no test failed'}]"


def _shares(
    rows: Sequence[Row], tallies: dict[str, tuple[int, int]], marked: set[str]
) -> list[str]:
    units_caught = [row for row in rows if row.category != "apart" and row.units.state == "caught"]
    guarded = sum(1 for row in units_caught if row.category == "guarded")
    graded = [test for test in tallies if test not in marked]
    clean = sum(1 for test in graded if tallies[test][1] == 0)
    return [
        _share(
            "Of the changes any unit test caught, the share that are guarded",
            guarded,
            len(units_caught),
        ),
        _share(
            "Of the unmarked unit tests that caught at least one change, the share that caught "
            "nothing the kept group missed",
            clean,
            len(graded),
        ),
    ]


def _retry_lines(retries: dict[str, tuple[int, int]]) -> list[str]:
    """Say, only when it happened, how many changes were run again for an empty output."""
    if not any(done for done, _ in retries.values()):
        return []
    parts = ", ".join(
        f"{done} in the {group} group ({empty} still empty)"
        for group, (done, empty) in retries.items()
        if done
    )
    return [f"Changes whose test run printed nothing were run a second time: {parts}.", ""]


def _write_report(
    *, command: str, source: Path, args: Args, rows: Sequence[Row], measured: Measured
) -> None:
    tallies = _unit_test_tallies(rows)
    counts = Counter(row.category for row in rows)
    if sum(counts[c] for c in _CATEGORIES) != len(rows):
        raise AssertionError("The four category counts do not add up to the total.")
    sampled_from = len(rows) + measured.dropped.get(_SAMPLE_REASON, 0)
    sampled = (
        f"sampled {len(rows)} of {sampled_from}" if len(rows) < sampled_from else "not sampled"
    )

    out: list[str] = [
        f"# Mutation run: {source.relative_to(_REPO_ROOT)}",
        "",
        f"Command as run: `{command}`",
        "",
        f"Tier: {args.tier}. Kept group: {' '.join(args.kept)}. "
        f"Units group: {' '.join(args.units)}.",
        f"One kept run took {measured.kept_seconds:.0f} seconds and one units run took "
        f"{measured.units_seconds:.0f} seconds on unchanged code.",
        "",
        "## Counts",
        "",
        f"- Changes graded: {len(rows)}",
        *[f"- {_LIST_TITLES[c]}: {counts[c]}" for c in _CATEGORIES],
        "",
        *_retry_lines(measured.retries),
        "## Filters",
        "",
        f"- Changes generated by cosmic-ray: {measured.generated}",
        *[f"- Dropped, {reason}: {count}" for reason, count in measured.dropped.items()],
        f"- Sampling: {sampled}.",
        "",
        "## Shares",
        "",
        *_shares(rows, tallies, measured.marked),
        "",
    ]
    for category in _CATEGORIES:
        out += [f"## {_LIST_TITLES[category]}", ""]
        members = [row for row in rows if row.category == category]
        out += [_list_line(row, category) for row in members] or ["none"]
        out.append("")
    out += [
        "A class-level set-up failure in the units group is counted against every test in "
        'that class. A change listed under "Units only" with no test named was caught only by '
        "a class-level set-up failure in a class that has no listed test.",
        "",
    ]
    silent = sorted(measured.baseline_ids - set(tallies))
    out += [
        "## Unit tests that caught no change",
        "",
        "These are not counted as redundant, because they may not exercise the changed code.",
        "",
        *([f"- {test}" for test in silent] or ["none"]),
        "",
    ]
    (measured.out / "report.md").write_text("\n".join(out), encoding="utf-8")


# ---------------------------------------------------------------------------
# The run
# ---------------------------------------------------------------------------


def _prepare_out(args: Args, source: Path) -> Path:
    raw = Path(args.out) if args.out else Path(".mutation") / source.stem
    out = (raw if raw.is_absolute() else _REPO_ROOT / raw).resolve()
    out.mkdir(parents=True, exist_ok=True)
    for name in _OUT_FILES:
        (out / name).unlink(missing_ok=True)
        if name.endswith(".sqlite"):
            for suffix in _SQLITE_SIDE_FILES:
                (out / f"{name}{suffix}").unlink(missing_ok=True)
    return out


def _baselines(args: Args, limit: int) -> tuple[Baseline, Baseline, Baseline, Baseline]:
    """Run each group once on unchanged code: kept, units timed, units ids, marked ids.

    The kept group runs first, so it takes any cold schema-cache miss of the runner and its
    timing can read high. That only makes the estimate and the timeouts conservative. The
    timed units run uses the default verbosity, which is what every graded run uses. It also
    warms the cache before the verbosity 2 runs, because a cache miss at verbosity 2 costs
    minutes where a miss at the default verbosity costs under one.
    """
    print("Baseline: kept group on unchanged code.", file=sys.stderr)
    kept = _baseline(_test_command(args.tier, args.kept), "kept", limit, must_pass=True)
    print("Baseline: units group on unchanged code.", file=sys.stderr)
    units = _baseline(_test_command(args.tier, args.units), "units", limit, must_pass=True)
    print("Baseline: unit test ids.", file=sys.stderr)
    ids_cmd = _test_command(args.tier, args.units, ["--verbosity", "2"])
    ids = _baseline(ids_cmd, "units", limit, must_pass=True)
    print("Baseline: marked regression tests among the units.", file=sys.stderr)
    marked_cmd = _test_command(args.tier, args.units, ["--tag", "regression", "--verbosity", "2"])
    marked = _baseline(marked_cmd, "regression", limit, must_pass=False)
    return kept, units, ids, marked


def _generate(
    args: Args, source: Path, original: bytes, out: Path, timeouts: dict[str, float]
) -> tuple[list[Change], dict[str, int], int]:
    for group, labels in (("kept", args.kept), ("units", args.units)):
        _write_config(
            out / f"{group}.toml", source, timeouts[group], _test_command(args.tier, labels)
        )
    session = out / "session.sqlite"
    if _run_streamed([*COSMIC_RAY, "init", str(out / "kept.toml"), str(session)]) != 0:
        raise Refusal("cosmic-ray could not generate the changes; run it by hand to see why.")
    return _filter_changes(session, original.decode("utf-8"), args)


def _exec_session(group: str, config: Path, session: Path) -> None:
    argv = [*COSMIC_RAY, "exec", str(config), str(session)]
    if _run_streamed(argv) != 0:
        raise Refusal(f"cosmic-ray failed while running the {group} group; see its output.")


def _job_ids_with_empty_output(session: Path) -> list[str]:
    with closing(sqlite3.connect(session)) as con:
        rows = con.execute(
            "SELECT job_id FROM work_results WHERE output = '' OR output IS NULL"
        ).fetchall()
    return [job for (job,) in rows]


def _retry_empty(group: str, config: Path, session: Path) -> tuple[int, int]:
    """Run once more every change whose test run recorded no output at all.

    A real import break always leaves a traceback, so an empty output means the test process
    was killed from outside. The result rows are deleted and cosmic-ray runs the work items
    that have no result. The two values returned are how many changes were retried and how
    many of those are still empty afterwards.
    """
    empty = _job_ids_with_empty_output(session)
    if not empty:
        return 0, 0
    print(f"Retrying {len(empty)} change(s) whose test run produced no output.", file=sys.stderr)
    con = sqlite3.connect(session)
    try:
        with con:
            con.executemany("DELETE FROM work_results WHERE job_id = ?", [(j,) for j in empty])
    finally:
        con.close()
    _exec_session(group, config, session)
    missing = set(empty) - set(_read_results(session))
    if missing:
        raise Refusal(
            f"cosmic-ray did not run {len(missing)} deleted result(s) of the {group} group "
            "again; the retry needs another mechanism."
        )
    return len(empty), len(set(empty) & set(_job_ids_with_empty_output(session)))


def _execute(out: Path, group: str, count: int) -> tuple[dict[str, RawResult], tuple[int, int]]:
    config, session = out / f"{group}.toml", out / f"{group}.sqlite"
    shutil.copyfile(out / "session.sqlite", session)
    print(f"Running the {group} group against {count} changes.", file=sys.stderr)
    _exec_session(group, config, session)
    retried = _retry_empty(group, config, session)
    return _read_results(session), retried


def _measure(args: Args, source: Path, original: bytes, max_minutes: int) -> Measured:
    out = _prepare_out(args, source)
    _check_operators()
    kept_base, units_base, ids_base, marked_base = _baselines(args, max_minutes * 60)
    timeouts = {"kept": 3 * kept_base.seconds + 60, "units": 3 * units_base.seconds + 60}
    changes, dropped, generated = _generate(args, source, original, out, timeouts)
    estimate = len(changes) * (kept_base.seconds + units_base.seconds) / 60
    reasons = ", ".join(f"{count} dropped ({reason})" for reason, count in dropped.items())
    print(
        f"{generated} changes generated, {reasons}, {len(changes)} to run. "
        f"Estimated {estimate:.0f} minutes (limit {max_minutes}).",
        file=sys.stderr,
    )
    if not changes:
        raise Refusal("No change is left after the filters; widen --functions or --lines.")
    if estimate > max_minutes:
        raise Refusal(
            f"The estimate of {estimate:.0f} minutes is over {max_minutes}; narrow "
            "--functions or --lines, or pass --sample."
        )
    executed = {group: _execute(out, group, len(changes)) for group in ("kept", "units")}
    results = {group: done[0] for group, done in executed.items()}
    retries = {group: done[1] for group, done in executed.items()}
    return Measured(
        out=out,
        changes=changes,
        dropped=dropped,
        generated=generated,
        kept_seconds=kept_base.seconds,
        units_seconds=units_base.seconds,
        marked=set(_TEST_ID_RE.findall(marked_base.output)),
        baseline_ids=set(_TEST_ID_RE.findall(ids_base.output)),
        results=results,
        retries=retries,
    )


def _grade(measured: Measured) -> list[Row]:
    rows: list[Row] = []
    unit_ids = sorted(measured.baseline_ids)
    for change in measured.changes:
        kept_result = measured.results["kept"].get(change.job_id)
        units_result = measured.results["units"].get(change.job_id)
        kept = _classify(kept_result)
        units = _classify(units_result, unit_ids)
        diff = (kept_result or units_result or ("", "", "", ""))[3]
        before, after = _diff_lines(diff)
        category = _categorise(kept, units, measured.marked)
        rows.append(Row(change, before, after, kept, units, category))
    return rows


def _run(args: Args, command_line: str) -> int:
    _check_labels([*args.kept, *args.units])
    source = _resolve_source(args.source)
    _check_clean(source)
    max_minutes = args.max_minutes or _DEFAULT_MAX_MINUTES
    original = source.read_bytes()
    try:
        measured = _measure(args, source, original, max_minutes)
    finally:
        _cleanup(source, original)

    rows = _grade(measured)
    tallies = _unit_test_tallies(rows)
    out = measured.out
    _write_changes_csv(out / "changes.csv", rows)
    _write_unit_tests_csv(out / "unit_tests.csv", tallies, measured.marked)
    _write_report(command=command_line, source=source, args=args, rows=rows, measured=measured)
    print(f"Report written to {out / 'report.md'}", file=sys.stderr)
    return 0


def _cleanup(source: Path, original: bytes) -> None:
    """Stop every child, then put the source file back as it was. Signals wait until done."""
    for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
        signal.signal(sig, signal.SIG_IGN)
    _kill_everything()
    if source.read_bytes() != original:
        source.write_bytes(original)


def main(argv: Sequence[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
        signal.signal(sig, _on_signal)
    command_line = shlex.join(["python", "tools/mutation_run.py", *argv])
    try:
        return _run(_parse_args(argv), command_line)
    except Refusal as refusal:
        print(str(refusal), file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        number = _received_signal[0] if _received_signal else int(signal.SIGINT)
        print("Interrupted; the source file was restored.", file=sys.stderr)
        return 128 + number


if __name__ == "__main__":
    sys.exit(main())
