"""Value objects for boundaries services (#1771).

Frozen dataclasses only — never dicts (repo standard). These carry the
ANONYMIZED read surfaces the ``boundaries`` app exposes to GM/scene tooling;
none of them may ever gain an owner-identifying field (see
``world.boundaries.services.scene_lines_and_veils``).
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class SharedAdvisoryBoundary:
    """One participant's shared ADVISORY ``PlayerBoundary``, owner stripped.

    Never built from a HARD_LINE row — callers only ever query
    ``kind=BoundaryKind.ADVISORY`` rows to populate this type.
    """

    theme_name: str
    detail: str


@dataclass(frozen=True)
class SharedTreasuredSubject:
    """One participant's shared ``TreasuredSubject``, owner stripped."""

    subject_kind: str
    subject_label: str
    detail: str


@dataclass(frozen=True)
class SceneLinesAndVeils:
    """A scene's anonymized union of shared advisory boundaries + treasured subjects.

    Built by ``scene_lines_and_veils`` from every participant's rows that are
    (a) not PRIVATE visibility and (b) visible to the requesting viewer per
    ``VisibilityMixin.is_visible_to``. Hard lines never appear here — see the
    module docstring on ``services.py``.
    """

    advisories: tuple[SharedAdvisoryBoundary, ...] = field(default_factory=tuple)
    treasured_subjects: tuple[SharedTreasuredSubject, ...] = field(default_factory=tuple)
