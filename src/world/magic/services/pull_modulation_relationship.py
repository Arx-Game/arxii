"""Relationship-bond (RELATIONSHIP_TRACK) pull modulation: scale by the owner's
own bond strength to the thread's threaded person, when the live target IS that
person or is hostile toward them (#1849).

Deliberately different in shape from Court modulation
(`pull_modulation_court.py`): no `RegardPolarity` gate (this rewards ANY PC-to-PC
relationship investment unconditionally — rival or lover alike — unlike Court's
NPC-preference sign-matching), and a saturating curve rather than a fixed ratio
(CharacterRelationship values are unbounded, unlike NpcRegard's 0..REGARD_MAX).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.magic.constants import TargetKind

if TYPE_CHECKING:
    from evennia_extensions.models import ObjectDB
    from world.character_sheets.models import CharacterSheet
    from world.magic.models import RelationshipBondPullTuning, Thread, ThreadPullEffect


def get_relationship_bond_pull_tuning() -> RelationshipBondPullTuning:
    """Get-or-create the relationship-bond pull tuning config singleton (pk=1)."""
    from world.magic.models import RelationshipBondPullTuning  # noqa: PLC0415

    cfg = RelationshipBondPullTuning.objects.cached_singleton()
    if cfg is None:
        cfg, _ = RelationshipBondPullTuning.objects.get_or_create(pk=1)
    return cfg


def _relationship_pull_would_trigger(x_sheet: CharacterSheet, y_sheet: CharacterSheet) -> bool:
    """Whether a relationship-bond pull directed at ``x_sheet`` should be
    empowered, given the thread's threaded person is ``y_sheet``.

    Shared by ``relationship_bond_modulation`` and the picker's
    ``_relationship_pull_would_have_effect`` (#1849) so the trigger rule can't
    diverge between the two call sites — mirrors ``_regard_polarity_matches``'s
    role for Court modulation.

    True when:
    - ``x_sheet == y_sheet`` (direct: the live target IS the threaded person), or
    - ``x_sheet`` holds an active, mutually-consented, net-negative
      ``CharacterRelationship`` toward ``y_sheet`` (indirect: X is hostile to Y).
    """
    from world.relationships.models import CharacterRelationship  # noqa: PLC0415

    if x_sheet.pk == y_sheet.pk:
        return True
    hostile = CharacterRelationship.objects.filter(
        source=x_sheet, target=y_sheet, is_active=True, is_pending=False
    ).first()
    return hostile is not None and hostile.affection < 0


def _thread_relationship_target(thread: Thread) -> CharacterSheet:
    """Resolve the threaded person from either RELATIONSHIP_TRACK or CAPSTONE FK.

    RELATIONSHIP_TRACK threads store the relationship via
    ``target_relationship_track.relationship``; RELATIONSHIP_CAPSTONE threads
    store it via ``target_capstone.relationship``. Both point at the same
    ``CharacterRelationship`` — only the FK access path differs (#2021).
    """
    if thread.target_kind == TargetKind.RELATIONSHIP_CAPSTONE:
        return thread.target_capstone.relationship.target
    return thread.target_relationship_track.relationship.target


def relationship_bond_modulation(
    thread: Thread,
    target: ObjectDB,
    effect_row: ThreadPullEffect,  # noqa: ARG001 (no polarity read; kept for call-site parity)
    base_scaled: int,
) -> int:
    """Empower ``base_scaled`` by the owner's own bond to the thread's threaded
    person, when the live ``target`` IS that person or is hostile toward them.

    Returns ``base_scaled`` unchanged when there is no resolvable target sheet,
    neither trigger condition holds, or the owner has no active/consented bond
    to the threaded person.

    No ``can_perceive`` gate here, deliberately — mirrors ``court_regard_modulation``,
    which also has none. The privacy concern (#1849, #1831) is specific to the
    ADVISORY PICKER (`_relationship_pull_would_have_effect` / `_court_pull_would_have_effect`),
    which can be probed for free against arbitrary personas without committing to a
    cast. By the time THIS function runs, the caster has already committed a real
    technique cast against an already-resolved live target — not a free enumeration
    vector — so gating resolution too would be redundant, and Court's own resolution
    path (`court_regard_modulation`) confirms this is the established precedent.
    """
    from world.magic.services.threads import _soft_cap  # noqa: PLC0415
    from world.relationships.models import CharacterRelationship  # noqa: PLC0415

    x_sheet = getattr(target, "sheet_data", None)  # noqa: GETATTR_LITERAL
    if x_sheet is None:
        return base_scaled

    y_sheet = _thread_relationship_target(thread)

    if not _relationship_pull_would_trigger(x_sheet, y_sheet):
        return base_scaled

    bond = CharacterRelationship.objects.filter(
        source=thread.owner, target=y_sheet, is_active=True, is_pending=False
    ).first()
    if bond is None:
        return base_scaled

    tuning = get_relationship_bond_pull_tuning()
    score = tuning.coefficient * bond.developed_absolute_value
    bonus = _soft_cap(score, tuning.cap, tuning.half_saturation)
    return base_scaled + bonus
