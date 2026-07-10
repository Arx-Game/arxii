"""Distinction-specific actions: GM award / rank-up (#2037)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from evennia.objects.models import ObjectDB

from actions.base import Action
from actions.constants import ActionCategory
from actions.prerequisites import MinimumGMLevelPrerequisite, Prerequisite
from actions.types import ActionContext, ActionResult, TargetType
from world.gm.constants import GMLevel


def _coerce_positive_int(value: Any) -> int | None:
    """Return ``value`` as a positive int, or ``None`` if it isn't one.

    Fails loud (returns None -> caller refuses) rather than silently coercing a
    non-positive/garbage rank to something valid.
    """
    try:
        coerced = int(value)
    except (TypeError, ValueError):
        return None
    return coerced if coerced > 0 else None


@dataclass
class GMAwardDistinctionAction(Action):
    """JUNIOR-tier GM action: award or rank up a catalog Distinction (#2037 Decision 4).

    Ad-hoc narrative distinction grant -- for story-earned moments (or a staff
    manual-audit correction, folded into this same action per the spec's
    Decision 1b) where a GM hand-awards or ranks up a Distinction. Mirrors
    ``GrantItemAction`` (``actions/definitions/items.py``) field-for-field: same
    JUNIOR-tier gate, same target-search convention, same catalog-only lookup
    (never freehand). Wraps ``world.distinctions.services.grant_distinction`` --
    the single shared acquisition seam every in-play Distinction source calls.

    Dispatch convention
    -------------------
    REGISTRY ActionRef: ``registry_key="gm_award_distinction"``, ``target_name=<str>``,
    ``distinction_slug=<str>``, optional ``rank=<int>``. Resolution (target search +
    catalog lookup) happens in ``execute()``.

    Gated on ``MinimumGMLevelPrerequisite(GMLevel.JUNIOR)`` (staff bypass
    preserved). No per-scene cap -- a Distinction grant is a rarer, heavier
    action already gated on GM trust level, not a per-scene currency tap.

    Rank validation (#2037 Task 2 review fold-in): an explicit ``rank`` below 1
    or above the resolved distinction's ``max_rank`` is rejected outright (never
    silently clamped), naming ``max_rank`` in the failure message -- the same
    "fail loud rather than silently clamp" bar ``GMApplyConditionAction`` already
    holds for severity/duration overrides.
    """

    key: str = "gm_award_distinction"
    name: str = "Award Distinction"
    icon: str = "medal"
    category: str = "gm"
    action_category: ActionCategory = ActionCategory.PHYSICAL
    target_type: TargetType = TargetType.SELF

    def get_prerequisites(self) -> list[Prerequisite]:
        return [MinimumGMLevelPrerequisite(GMLevel.JUNIOR)]

    def execute(  # noqa: PLR0911
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.distinctions.exceptions import DistinctionExclusionError  # noqa: PLC0415
        from world.distinctions.models import Distinction  # noqa: PLC0415
        from world.distinctions.services import grant_distinction  # noqa: PLC0415
        from world.distinctions.types import DistinctionOrigin  # noqa: PLC0415

        target_name = (kwargs.get("target_name") or "").strip()
        distinction_slug = (kwargs.get("distinction_slug") or "").strip()
        if not target_name or not distinction_slug:
            return ActionResult(
                success=False,
                message="Usage: gm_award_distinction <character>=<distinction slug>[,rank]",
            )

        rank: int | None = None
        rank_raw = kwargs.get("rank")
        if rank_raw is not None:
            rank = _coerce_positive_int(rank_raw)
            if rank is None:
                return ActionResult(success=False, message="rank must be a positive whole number.")

        target = actor.search(target_name, global_search=True)
        if target is None:
            # search() already messaged the actor with a not-found/ambiguous notice.
            return ActionResult(success=False)

        sheet = getattr(target, "sheet_data", None)  # noqa: GETATTR_LITERAL
        if sheet is None:
            return ActionResult(success=False, message="That is not a character.")

        distinction = Distinction.objects.filter(
            slug__iexact=distinction_slug, is_active=True
        ).first()
        if distinction is None:
            return ActionResult(
                success=False,
                message=f"No active distinction found with slug '{distinction_slug}'.",
            )

        if rank is not None and rank > distinction.max_rank:
            return ActionResult(
                success=False,
                message=f"{distinction.name} has a maximum rank of {distinction.max_rank}.",
            )

        try:
            char_distinction = grant_distinction(
                sheet,
                distinction,
                origin=DistinctionOrigin.GM_AWARD,
                rank=rank,
                source_description=f"Awarded by {actor.key}.",
            )
        except DistinctionExclusionError as exc:
            return ActionResult(success=False, message=exc.user_message)

        return ActionResult(
            success=True,
            message=(
                f"Awarded '{distinction.name}' (rank {char_distinction.rank}) to {target.key}."
            ),
        )
