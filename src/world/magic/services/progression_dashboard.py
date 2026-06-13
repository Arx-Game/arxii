"""Progression dashboard resolver service.

Builds a per-stage view of magic milestones for a character, gated by
Codex discovery tier (known/uncovered/unknown) and eligibility checks.
"""

from __future__ import annotations

from dataclasses import dataclass

from world.character_sheets.models import CharacterSheet
from world.classes.models import PathStage
from world.codex.constants import CodexKnowledgeStatus
from world.codex.models import CharacterCodexKnowledge
from world.magic.constants import MagicMilestoneKind, MilestoneDiscoveryTier, MilestoneEligibility
from world.magic.models import MagicProgressionMilestone
from world.magic.models.anima import CharacterAnima
from world.magic.models.aura import CharacterResonance
from world.magic.models.gifts import CharacterGift
from world.magic.models.motifs import Motif
from world.magic.models.weaving import CharacterThreadWeavingUnlock
from world.magic.services.alterations import has_pending_alterations
from world.magic.services.threads import _current_path_stage


@dataclass
class MilestoneView:
    kind: str  # MagicMilestoneKind value
    tier: str  # MilestoneDiscoveryTier value
    title: str
    summary: str
    eligibility: str | None  # MilestoneEligibility value; None unless tier == KNOWN
    missing: list[str]
    xp_cost: int | None
    route_name: str | None
    codex_entry_id: int | None


@dataclass
class StageView:
    stage: int
    stage_label: str
    is_current: bool
    milestones: list[MilestoneView]  # KNOWN + UNCOVERED only, ordered by sort_order
    has_undiscovered: bool  # True if any UNKNOWN milestone at this stage


@dataclass
class _Prefetched:
    """Prefetched per-sheet facts to avoid queries-in-loops."""

    resonance_exists: bool
    weaving_exists: bool
    motif_exists: bool
    anima_exists: bool
    gift_count: int


def _prefetch_facts(sheet: CharacterSheet) -> _Prefetched:
    """Load all per-sheet 'already-have' facts in one pass before the loop."""
    resonance_exists = CharacterResonance.objects.filter(character_sheet=sheet).exists()
    weaving_exists = CharacterThreadWeavingUnlock.objects.filter(character=sheet).exists()
    motif_exists = Motif.objects.filter(character=sheet).exists()

    # CharacterAnima.character is a FK to ObjectDB — query via sheet.character
    try:
        anima_exists = CharacterAnima.objects.filter(character=sheet.character).exists()
    except Exception:  # noqa: BLE001
        anima_exists = False

    try:
        gift_count = CharacterGift.objects.filter(character=sheet).count()
    except Exception:  # noqa: BLE001
        gift_count = 0

    return _Prefetched(
        resonance_exists=resonance_exists,
        weaving_exists=weaving_exists,
        motif_exists=motif_exists,
        anima_exists=anima_exists,
        gift_count=gift_count,
    )


def _knowledge_tier(roster_entry: object | None, entry: object | None) -> str:
    """Return MilestoneDiscoveryTier for a codex entry given the character's roster entry."""
    if entry is None:
        return MilestoneDiscoveryTier.UNKNOWN
    if entry.is_public:
        return MilestoneDiscoveryTier.KNOWN
    if roster_entry is None:
        return MilestoneDiscoveryTier.UNKNOWN
    row = CharacterCodexKnowledge.objects.filter(
        roster_entry=roster_entry, entry=entry
    ).first()
    if row is None:
        return MilestoneDiscoveryTier.UNKNOWN
    if row.status == CodexKnowledgeStatus.KNOWN:
        return MilestoneDiscoveryTier.KNOWN
    return MilestoneDiscoveryTier.UNCOVERED


def _already_have(kind: str, prefetched: _Prefetched) -> bool:
    """Return True if the character already has the milestone's unlock."""
    if kind == MagicMilestoneKind.RESONANCE_DISCOVERY:
        return prefetched.resonance_exists
    if kind == MagicMilestoneKind.THREAD_WEAVING:
        return prefetched.weaving_exists
    if kind == MagicMilestoneKind.MOTIF:
        return prefetched.motif_exists
    if kind == MagicMilestoneKind.ANIMA_RITUAL:
        return prefetched.anima_exists
    if kind == MagicMilestoneKind.SECOND_GIFT:
        return prefetched.gift_count >= 2  # noqa: PLR2004 — "second" gift is domain meaning
    # TECHNIQUE_DEVELOPMENT, STAGE_CROSSING, and any future kinds default to False
    return False


def _resolve_eligibility(
    sheet: CharacterSheet,
    milestone: MagicProgressionMilestone,
    current_stage: int,
    prefetched: _Prefetched,
) -> tuple[str, list[str], int | None]:
    """Compute eligibility, missing requirements list, and xp_cost for a KNOWN milestone."""
    if has_pending_alterations(sheet):
        return MilestoneEligibility.LOCKED, ["Resolve your Mage Scars first"], None
    if sheet.is_protagonism_locked:
        return MilestoneEligibility.LOCKED, ["Progression is locked"], None
    if current_stage < milestone.stage:
        stage_label = PathStage(milestone.stage).label
        return MilestoneEligibility.LOCKED, [f"Reach {stage_label}"], None
    if _already_have(milestone.kind, prefetched):
        return MilestoneEligibility.ALREADY_HAVE, [], None
    return MilestoneEligibility.ELIGIBLE, [], None


def build_progression_dashboard(sheet: CharacterSheet) -> list[StageView]:
    """Return one StageView per PathStage (all six, ascending), with milestones
    gated by Codex discovery tier and eligibility checks.

    No queries run inside the per-stage / per-milestone loops.
    """
    roster_entry = getattr(sheet, "roster_entry", None)
    current_stage = _current_path_stage(sheet)

    # Load all milestones in a single query.
    all_milestones = list(
        MagicProgressionMilestone.objects.select_related("codex_entry").order_by(
            "stage", "sort_order", "kind"
        )
    )

    # Prefetch per-sheet "already-have" facts before the loop.
    prefetched = _prefetch_facts(sheet)

    # Group milestones by stage for efficient per-stage access.
    milestones_by_stage: dict[int, list[MagicProgressionMilestone]] = {}
    for milestone in all_milestones:
        milestones_by_stage.setdefault(milestone.stage, []).append(milestone)

    result: list[StageView] = []
    for stage_value, stage_label in PathStage.choices:
        stage_milestones = milestones_by_stage.get(stage_value, [])
        milestone_views: list[MilestoneView] = []
        has_undiscovered = False

        for milestone in stage_milestones:
            entry = milestone.codex_entry
            tier = _knowledge_tier(roster_entry, entry)

            if tier == MilestoneDiscoveryTier.UNKNOWN:
                has_undiscovered = True
                continue  # collapsed into the per-stage mystery flag

            if tier == MilestoneDiscoveryTier.KNOWN:
                eligibility, missing, xp_cost = _resolve_eligibility(
                    sheet, milestone, current_stage, prefetched
                )
                summary = entry.summary if entry is not None else ""
                title = entry.name if entry is not None else milestone.get_kind_display()
            else:
                # UNCOVERED: teaser only
                eligibility = None
                missing = []
                xp_cost = None
                summary = ""
                title = entry.name if entry is not None else milestone.get_kind_display()

            milestone_views.append(
                MilestoneView(
                    kind=milestone.kind,
                    tier=tier,
                    title=title,
                    summary=summary,
                    eligibility=eligibility,
                    missing=missing,
                    xp_cost=xp_cost,
                    route_name=milestone.route_name or None,
                    codex_entry_id=entry.pk if entry is not None else None,
                )
            )

        result.append(
            StageView(
                stage=stage_value,
                stage_label=stage_label,
                is_current=(stage_value == current_stage),
                milestones=milestone_views,
                has_undiscovered=has_undiscovered,
            )
        )

    return result
