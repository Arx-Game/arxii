"""Reference search pane: DB prose search plus opt-in file corpora (#3019 Task 7).

A writer drafting one row often wants to check how a name or phrase is used
elsewhere - in the database (other credited rows' prose) and, opt-in, in the
raw text corpora that live outside the database entirely: this repo's own
staff docs (design notes, world bibles) and the maintainers' Arx I dump. The
DB search is on by default (it is cheap, one bounded query per credited
model); both file corpora are off by default (they can be large, slow, and
in the Arx I case live outside this repo altogether).

``file_search`` is a deliberately minimal port of the private lore repo's
``tools/write_editor/reference.py`` search semantics (fixed-string,
case-insensitive, per-line, a result cap, a wall-clock search budget, an
``is_relative_to`` escape guard) - that module cannot be imported across
repos (it lives in a different git checkout entirely, and this app has no
dependency on it), so this file re-implements just the slice this pane
needs rather than the lore repo's ripgrep-backed engine, domain catalog, and
CLI. The duplication is deliberate, not an oversight.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path
import time

from django.db.models import Q

from core.app_domains import credited_content_models, domain_of
from core_management.content_repo import resolve_content_root
from core_management.prose_fields import prose_fields_for

#: Only these suffixes are ever opened - the file corpora are prose/notes
#: trees, not something this pane should be walking binaries or code in.
_TEXT_SUFFIXES = frozenset({".md", ".txt", ".json"})

_DEFAULT_CAP = 200
_DEFAULT_BUDGET_SECONDS = 30

#: A 2MB text file is not a reference doc - it is exactly the kind of file
#: the Arx I dump's largest offenders are (see the module docstring:
#: event-logs/objects), and scanning one line by line is exactly what the
#: wall-clock budget below cannot survive if a single file eats the whole
#: 30s on its own. Skipped outright before it is ever opened.
_MAX_FILE_BYTES = 2 * 1024 * 1024

#: Directory names under a content root that carry staff-only prose - never
#: shipped to players, but useful cross-reference material for a writer.
_STAFF_DOC_DIRS = ("design", "world_bibles")


@dataclass
class DbSearchHit:
    """One credited-content row whose prose matched the query."""

    label: str  # str(instance)
    pk: int


@dataclass
class DbSearchGroup:
    """One credited model's `DbSearchHit` rows, for the grouped-by-model display."""

    model_name: str
    model_label: str
    hits: list[DbSearchHit] = field(default_factory=list)


@dataclass
class FileSearchHit:
    """One matching line from a file corpus search."""

    root_label: str  # which root this came from, for display (e.g. "design")
    path: str  # relative to its root
    line: int
    text: str


def db_search(query: str, *, cap: int = _DEFAULT_CAP) -> list[DbSearchGroup]:
    """`icontains` search across every credited model's prose fields, grouped by model.

    Fixed-string, case-insensitive (SQL `LIKE` under `icontains`) - no regex,
    matching the file-search side's fixed-string contract. Mirrors
    `web.admin.authoring.relations.prose_mentions`'s bounded-materialization
    idiom: `cap` is a running total across every model combined, and each
    model's queryset is sliced to what remains of that total *before* it is
    ever iterated - so no single model, however large, is asked to fetch
    more rows than could still fit under the cap. A model with zero matches
    contributes no group at all (never an empty one).
    """
    query = query.strip()
    if not query:
        return []

    groups: list[DbSearchGroup] = []
    remaining = cap
    for model in credited_content_models():
        if remaining <= 0:
            break
        prose_names = prose_fields_for(model)
        if not prose_names:
            continue
        field_query = Q()
        for field_name in prose_names:
            field_query |= Q(**{f"{field_name}__icontains": query})
        queryset = model.objects.filter(field_query)
        hits = [DbSearchHit(label=str(value), pk=value.pk) for value in queryset[:remaining]]
        if not hits:
            continue
        groups.append(
            DbSearchGroup(
                model_name=model.__name__,
                model_label=f"{domain_of(model)}.{model.__name__}",
                hits=hits,
            )
        )
        remaining -= len(hits)
    return groups


def _iter_text_files(root: Path, deadline: float):
    """Yield every `_TEXT_SUFFIXES` file under `root` up to `_MAX_FILE_BYTES`, never leaving `root`.

    `os.walk` does not follow symlinked directories by default (`followlinks`
    defaults to `False`), so a symlinked subdirectory pointing outside `root`
    is never descended into. A symlinked *file* sitting directly in a walked
    directory would still be listed, though, so each candidate is resolved
    and re-checked with `is_relative_to` before it is opened - the same
    escape guard the lore repo's `write_editor.reference._targets`/
    `read_file` use, applied per file here instead of per configured domain.

    `deadline` (a `time.monotonic()` value, matching `file_search`'s own) is
    checked at both the per-directory and per-file level, not just inside
    `file_search`'s own line loop - without this, a root with tens of
    thousands of files (the Arx I dump again) keeps enumerating candidates
    for the full walk even after the search budget is already spent, before
    `file_search` ever gets another chance to look at the clock.
    """
    for base, _dirs, names in os.walk(root):
        if time.monotonic() > deadline:
            return
        for name in names:
            if time.monotonic() > deadline:
                return
            candidate = Path(base) / name
            if candidate.suffix not in _TEXT_SUFFIXES:
                continue
            try:
                if candidate.stat().st_size > _MAX_FILE_BYTES:
                    continue
            except OSError:
                continue
            resolved = candidate.resolve()
            if not resolved.is_relative_to(root):
                continue
            yield resolved


def file_search(
    query: str,
    roots: list[Path],
    *,
    cap: int = _DEFAULT_CAP,
    budget_seconds: int = _DEFAULT_BUDGET_SECONDS,
) -> list[FileSearchHit]:
    """Fixed-string, case-insensitive, per-line search across `roots`.

    Stops as soon as `cap` hits have been collected or `budget_seconds` of
    wall-clock time (`time.monotonic`) has elapsed, whichever comes first -
    a hard ceiling on both result volume and search time, since a corpus
    root can be large (the Arx I dump in particular). Each hit records the
    file's path relative to the root it was found under, its 1-based line
    number, and that line's text, stripped and trimmed to 200 characters.

    Contract: no single file scan can exceed the budget by more than one
    line - the deadline is re-checked on every line, not just between files
    - and files over 2MB are skipped outright before they are ever opened
    (see `_iter_text_files`), so neither a single oversized line nor a
    single oversized file can blow through `budget_seconds` on its own; a
    deadline hit mid-file returns whatever hits were already collected
    rather than finishing that file's remaining lines.
    """
    needle = query.strip().casefold()
    hits: list[FileSearchHit] = []
    if not needle:
        return hits

    deadline = time.monotonic() + budget_seconds
    for raw_root in roots:
        root = raw_root.resolve()
        root_label = root.name
        for path in _iter_text_files(root, deadline):
            if len(hits) >= cap or time.monotonic() > deadline:
                return hits
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for line_no, line in enumerate(text.splitlines(), start=1):
                if time.monotonic() > deadline:
                    return hits
                if needle not in line.casefold():
                    continue
                hits.append(
                    FileSearchHit(
                        root_label=root_label,
                        path=str(path.relative_to(root)),
                        line=line_no,
                        text=line.strip()[:200],
                    )
                )
                if len(hits) >= cap:
                    return hits
    return hits


def reference_roots(*, staff_docs: bool, arx1: bool) -> list[Path]:
    """Resolve the opt-in file corpora into existing directories, silently.

    `staff_docs` adds `resolve_content_root()/design` and `/world_bibles`
    when they exist; `arx1` adds `resolve_content_root().parent/'arx1'` when
    it exists (`CONTENT_REPO_PATH` points at the `arx2/` checkout, so
    `arx1/` is its sibling directory, not something under it). A missing
    `CONTENT_REPO_PATH`, or any individual root that does not exist, is
    silently omitted rather than raised - an operator without the content
    repo configured still gets DB search working, and an unchecked or
    absent corpus is not an error.
    """
    roots: list[Path] = []
    content_root = resolve_content_root()
    if content_root is None:
        return roots

    if staff_docs:
        for name in _STAFF_DOC_DIRS:
            candidate = content_root / name
            if candidate.is_dir():
                roots.append(candidate)

    if arx1:
        # resolve() first: CONTENT_REPO_PATH may itself be a symlink, and
        # its sibling directory only lives next to where that symlink
        # actually points, not next to the symlink itself.
        candidate = content_root.resolve().parent / "arx1"
        if candidate.is_dir():
            roots.append(candidate)

    return roots
