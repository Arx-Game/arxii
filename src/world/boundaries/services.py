"""Boundary-owned reads (#1771 task 5).

Everything here operates purely on models this app owns (``PlayerBoundary``,
``TreasuredSubject``) plus ``world.consent`` (``VisibilityMixin``) and
``world.scenes``/``world.character_sheets``/``world.roster``. This module
NEVER imports ``world.stories`` (ADR-0010 FK direction specific->general —
``stories`` depends on ``boundaries``, never the reverse). Sign-off
grant/withdraw and the GM stake-availability tally operate on stories-owned
models (``Beat``, ``TreasuredSignoff``) and reuse the stories-owned
``check_stake_boundaries``, so those live in
``world.stories.services.boundaries`` instead — see that module.

Privacy invariant (ADR-0033, shared with the stories boundary seam): a
HARD_LINE ``PlayerBoundary`` is never returned by anything in this module.
``scene_lines_and_veils`` only ever queries ``kind=BoundaryKind.ADVISORY``
rows, so a hard line cannot appear in its output even in principle.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.boundaries.constants import BoundaryKind
from world.boundaries.models import PlayerBoundary, TreasuredSubject
from world.boundaries.types import (
    SceneLinesAndVeils,
    SharedAdvisoryBoundary,
    SharedTreasuredSubject,
)
from world.consent.models import VisibilityMixin

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.roster.models import RosterTenure
    from world.scenes.models import Scene


def _scene_participant_sheets(scene: Scene) -> list[CharacterSheet]:
    """The distinct ``CharacterSheet``s of a scene's active participants.

    Reuses ``Scene.persona_handler.active_participant_personas()`` (the
    established, query-free-per-participant resolver already used by
    ``Scene.finish_scene()`` for the same "which sheets are in this scene"
    need) rather than re-deriving participant identity from
    ``SceneParticipation.account`` by hand.
    """
    seen: set[int] = set()
    sheets: list[CharacterSheet] = []
    for persona in scene.persona_handler.active_participant_personas():
        sheet = persona.character_sheet
        if sheet.pk not in seen:
            seen.add(sheet.pk)
            sheets.append(sheet)
    return sheets


def _sheet_player_and_tenure_ids(sheets: list[CharacterSheet]) -> tuple[set[int], set[int]]:
    """(player_data ids, tenure ids) for whichever sheets have a live tenure.

    Query-free beyond the first access per ``roster_entry`` (mirrors the
    ``roster_entry.current_tenure`` pattern at
    ``character_sheets/serializers.py:251`` — a small local mirror, not an
    import from ``world.stories``, since ``boundaries`` must stay
    dependency-free of ``stories``).
    """
    player_ids: set[int] = set()
    tenure_ids: set[int] = set()
    for sheet in sheets:
        entry = getattr(sheet, "roster_entry", None)  # noqa: GETATTR_LITERAL — OneToOne reverse may not exist
        tenure = entry.current_tenure if entry else None
        if tenure is not None:
            player_ids.add(tenure.player_data_id)
            tenure_ids.add(tenure.pk)
    return player_ids, tenure_ids


def _shared_advisory_boundaries(
    player_ids: set[int], viewer_tenure: RosterTenure
) -> tuple[SharedAdvisoryBoundary, ...]:
    """Anonymized, viewer-visible ADVISORY boundaries for ``player_ids``.

    Only ``kind=ADVISORY`` is ever queried — a HARD_LINE row cannot reach this
    function's output. PRIVATE-visibility rows are excluded at the DB level
    (never shared, regardless of viewer); the remaining PUBLIC/CHARACTERS/
    GROUPS candidates are filtered through ``is_visible_to`` per row (bounded
    by the count of shareable rows across the scene's participants, not by
    any stakes/sheets loop).
    """
    if not player_ids:
        return ()
    candidates = (
        PlayerBoundary.objects.filter(kind=BoundaryKind.ADVISORY, owner_id__in=player_ids)
        .exclude(visibility_mode=VisibilityMixin.VisibilityMode.PRIVATE)
        .select_related("theme")
    )
    return tuple(
        SharedAdvisoryBoundary(
            theme_name=boundary.theme.name if boundary.theme_id else "",
            detail=boundary.detail,
        )
        for boundary in candidates
        if boundary.is_visible_to(viewer_tenure)
    )


def _shared_treasured_subjects(
    tenure_ids: set[int], viewer_tenure: RosterTenure
) -> tuple[SharedTreasuredSubject, ...]:
    """Anonymized, viewer-visible ``TreasuredSubject`` rows for ``tenure_ids``."""
    if not tenure_ids:
        return ()
    candidates = TreasuredSubject.objects.filter(owner_id__in=tenure_ids).exclude(
        visibility_mode=VisibilityMixin.VisibilityMode.PRIVATE
    )
    return tuple(
        SharedTreasuredSubject(
            subject_kind=subject.subject_kind,
            subject_label=subject.subject_label,
            detail=subject.detail,
        )
        for subject in candidates
        if subject.is_visible_to(viewer_tenure)
    )


def scene_lines_and_veils(scene: Scene, viewer_tenure: RosterTenure) -> SceneLinesAndVeils:
    """A scene's shared "lines & veils" aggregate for ``viewer_tenure``.

    Over ``scene.participants``, collects each participant's SHARED (visible
    to ``viewer_tenure`` via ``VisibilityMixin.is_visible_to``) ADVISORY
    ``PlayerBoundary`` rows and shared ``TreasuredSubject`` rows, and returns
    an ANONYMIZED union — theme/detail (or subject_kind/label/detail) present,
    owner stripped. HARD_LINE rows are structurally excluded (never queried);
    PRIVATE-visibility rows are excluded regardless of viewer.
    """
    sheets = _scene_participant_sheets(scene)
    if not sheets:
        return SceneLinesAndVeils()

    player_ids, tenure_ids = _sheet_player_and_tenure_ids(sheets)
    return SceneLinesAndVeils(
        advisories=_shared_advisory_boundaries(player_ids, viewer_tenure),
        treasured_subjects=_shared_treasured_subjects(tenure_ids, viewer_tenure),
    )
