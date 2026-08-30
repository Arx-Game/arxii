"""Required-content sentinel: registry vocabulary and batching collector (#3444).

Some code paths hard-depend on a specific authored database row existing (a named
`ConditionTemplate`, a tuning config singleton, ...) rather than on the shape of a
table. Nothing enforces that dependency at the database layer, so when the row is
missing the failure surfaces far from its cause - a `DoesNotExist` deep in a check
resolver, or a silent no-op. This module is the registry of those dependencies and
the collector that probes each one, so an admin dashboard (a later task) can report
the gap directly instead of a staff member reconstructing it from a stack trace.

Add a row to `_declarations()` when you add a code path that hard-depends on a
specific authored row. Each row names its consumer (`file:line function()`) and
the consequence a player or staff member experiences when the row is absent.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from enum import StrEnum

from django.apps import apps


class DependencyTier(StrEnum):
    """How severely a missing row degrades the game.

    `REQUIRED` rows are load-bearing for a code path a player or staff member
    can hit today; `TUNING` rows are config the game runs without, just with
    worse numbers (a fallback constant, an unconfigured knob).
    """

    REQUIRED = "required"
    TUNING = "tuning"


@dataclass(frozen=True, slots=True)
class ProbeResult:
    """The outcome of resolving one `ContentProbe`."""

    present: bool
    missing: tuple[str, ...] = ()
    detail: str = ""


class ContentProbe:
    """Base class for a single row-presence check.

    A subclass declares what it checks (which rows, which model); `resolve()`
    performs the check and reports the result. `model_label()` is the display/
    grouping seam: a probe that names a model returns that model's label, so
    the collector (and a later panel) can report or group by model without
    knowing each probe's concrete type. `participates_in_name_batch()` is the
    narrower seam that actually drives collector batching: only a
    `NamedRowsProbe` shares a single `values_list` query across declarations
    naming the same model - `AnyRowProbe` also has a `model_label()` (it names
    a model too) but resolves its own `.exists()` query per declaration, so it
    must not be folded into that batch.
    """

    def model_label(self) -> str | None:
        """The `arxii` app model label this probe checks, or `None` if it isn't
        one the collector can batch (e.g. a `CustomProbe`)."""
        return None

    def participates_in_name_batch(self) -> bool:
        """Whether the collector should pool this probe's `model_label()` into
        the shared known-names query rather than let the probe resolve itself."""
        return False

    def resolve(self, known_names: frozenset[str] | None) -> ProbeResult:
        """Resolve this probe against `known_names` (pre-fetched, lowercased row
        names for this probe's model), or `None` when the probe fetches its own
        data (an `AnyRowProbe`'s `.exists()`, a `CustomProbe`'s callable)."""
        raise NotImplementedError


@dataclass(frozen=True, slots=True)
class NamedRowsProbe(ContentProbe):
    """Checks that every one of `names` exists as a row on `label`.

    Matching is case-insensitive to match `ConditionTemplate.get_by_name`'s
    natural-key lookup (`world/conditions/models.py:503-511`) - a probe that
    compared case-sensitively could report a false fault for a row the game
    resolves at runtime without trouble.
    """

    label: str
    names: tuple[str, ...]

    def model_label(self) -> str | None:
        return self.label

    def participates_in_name_batch(self) -> bool:
        return True

    def resolve(self, known_names: frozenset[str] | None) -> ProbeResult:
        known = known_names or frozenset()
        missing = tuple(name for name in self.names if name.lower() not in known)
        if missing:
            detail = f"Missing {self.label} row(s): {', '.join(missing)}."
        else:
            detail = ""
        return ProbeResult(present=not missing, missing=missing, detail=detail)


@dataclass(frozen=True, slots=True)
class AnyRowProbe(ContentProbe):
    """Checks that `label` has at least one row - a singleton/config table that
    must be seeded at all, with no specific name to check."""

    label: str

    def model_label(self) -> str | None:
        return self.label

    def resolve(self, known_names: frozenset[str] | None) -> ProbeResult:
        del known_names  # This probe fetches its own existence check.
        model = apps.get_model("arxii", self.label)
        exists = model.objects.exists()
        detail = "" if exists else f"No {self.label} rows exist."
        return ProbeResult(present=exists, detail=detail)


@dataclass(frozen=True, slots=True)
class CustomProbe(ContentProbe):
    """Delegates to an arbitrary callable for checks a name/existence probe
    can't express (a composite condition, a cross-model invariant)."""

    fn: Callable[[], ProbeResult]

    def resolve(self, known_names: frozenset[str] | None) -> ProbeResult:
        del known_names  # This probe delegates entirely to `fn`.
        return self.fn()


@dataclass(frozen=True, slots=True)
class ContentDependency:
    """One registry row: a code path's hard dependency on authored content."""

    key: str
    label: str
    tier: DependencyTier
    consumer: str
    consequence: str
    probe: ContentProbe


@dataclass(frozen=True, slots=True)
class DependencyRow:
    """A `ContentDependency` paired with its resolved `ProbeResult`."""

    dependency: ContentDependency
    result: ProbeResult


@dataclass(frozen=True, slots=True)
class RequiredContentSnapshot:
    """The collector's output: every dependency, sorted by tier and presence."""

    missing_required: list[DependencyRow]
    present_required: list[DependencyRow]
    missing_tuning: list[DependencyRow]
    present_tuning: list[DependencyRow]


def build_registry(dependencies: Iterable[ContentDependency]) -> tuple[ContentDependency, ...]:
    """Freeze `dependencies` into a tuple, rejecting a duplicate `key`.

    A duplicate key would silently merge two distinct dependencies under one
    report row, so this raises rather than dedupe or last-write-wins.
    """
    registry: list[ContentDependency] = []
    seen_keys: set[str] = set()
    for dependency in dependencies:
        if dependency.key in seen_keys:
            message = f"Duplicate content dependency key: {dependency.key!r}"
            raise ValueError(message)
        seen_keys.add(dependency.key)
        registry.append(dependency)
    return tuple(registry)


def _declarations() -> tuple[ContentDependency, ...]:
    """Every hard-coded row dependency the sentinel tracks.

    Empty for now - Task 2 fills this in with the real registry rows. Kept as
    its own module-level function (rather than a module constant) so tests can
    intercept it with `mock.patch.object(required_content, "_declarations", ...)`
    without touching the real registry.
    """
    return ()


def collect_required_content() -> RequiredContentSnapshot:
    """Resolve every declared `ContentDependency` into a `RequiredContentSnapshot`.

    Batches every `NamedRowsProbe` sharing a model label onto a single
    `values_list("name", flat=True)` query - one per distinct label, never one
    per declaration - and passes the lowercased result to each such probe's
    `resolve()`. `AnyRowProbe` and `CustomProbe` resolve themselves.
    """
    dependencies = build_registry(_declarations())

    named_labels: set[str] = set()
    for dependency in dependencies:
        probe = dependency.probe
        label = probe.model_label()
        if probe.participates_in_name_batch() and label is not None:
            named_labels.add(label)

    known_names_by_label: dict[str, frozenset[str]] = {}
    for label in named_labels:
        model = apps.get_model("arxii", label)
        known_names_by_label[label] = frozenset(
            name.lower() for name in model.objects.values_list("name", flat=True)
        )

    missing_required: list[DependencyRow] = []
    present_required: list[DependencyRow] = []
    missing_tuning: list[DependencyRow] = []
    present_tuning: list[DependencyRow] = []

    for dependency in dependencies:
        probe = dependency.probe
        known_names: frozenset[str] | None = None
        probe_label = probe.model_label()
        if probe.participates_in_name_batch() and probe_label is not None:
            known_names = known_names_by_label[probe_label]
        result = probe.resolve(known_names)
        row = DependencyRow(dependency=dependency, result=result)
        if dependency.tier == DependencyTier.REQUIRED:
            (present_required if result.present else missing_required).append(row)
        else:
            (present_tuning if result.present else missing_tuning).append(row)

    return RequiredContentSnapshot(
        missing_required=missing_required,
        present_required=present_required,
        missing_tuning=missing_tuning,
        present_tuning=present_tuning,
    )
