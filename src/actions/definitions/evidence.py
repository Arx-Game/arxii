"""Evidence actions (#1825) — the criminal's post-crime moves, through the action seam.

Thin wrappers over ``world.justice.evidence``: **gather** claims the evidence lying at
a crime scene (a Skulduggery check that mints a real inventory item), **dispose**
destroys gathered evidence (dampening the deed's future pursuit-heat spread). The
tamper path is a Project (``world.justice.frame_jobs``), not an action here.

REST-dispatch note: ``evidence_id`` arrives as a plain int from the web dispatcher —
each ``execute()`` resolves it itself (the ``objectdb_target_kwargs`` machinery only
covers the websocket path, and CrimeEvidence is not an ObjectDB anyway).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from actions.base import Action
from actions.constants import ActionCategory
from actions.types import ActionResult, TargetType

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from actions.types import ActionContext
    from world.justice.models import CrimeEvidence

# PLACEHOLDER cost magnitudes — tuned in a later author pass.
_EVIDENCE_AP_COST = 1
_EVIDENCE_FATIGUE_COST = 1


def _resolve_evidence(evidence_id: Any) -> CrimeEvidence | None:
    from world.justice.models import CrimeEvidence  # noqa: PLC0415

    if isinstance(evidence_id, CrimeEvidence):
        return evidence_id
    if not isinstance(evidence_id, int):
        return None
    return CrimeEvidence.objects.filter(pk=evidence_id).first()


@dataclass
class GatherEvidenceAction(Action):
    """Gather the evidence a crime left at this scene (#1825)."""

    key: str = "gather_evidence"
    name: str = "Gather Evidence"
    icon: str = "hand"
    category: str = "items"
    action_category: ActionCategory = ActionCategory.PHYSICAL
    target_type: TargetType = TargetType.SELF

    ap_cost: int = _EVIDENCE_AP_COST
    fatigue_cost: int = _EVIDENCE_FATIGUE_COST
    fatigue_category: str = ActionCategory.PHYSICAL

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.justice.evidence import EvidenceError, gather_evidence  # noqa: PLC0415

        evidence = _resolve_evidence(kwargs.get("evidence_id"))
        if evidence is None:
            return ActionResult(success=False, message="There's no such evidence.")
        try:
            result = gather_evidence(actor, evidence)
        except EvidenceError as exc:
            return ActionResult(success=False, message=exc.user_message)
        if not result.success:
            return ActionResult(
                success=True,
                message="PLACEHOLDER You paw through the scene but come away with nothing usable.",
            )
        return ActionResult(
            success=True,
            message="PLACEHOLDER You quietly pocket what the crime left behind.",
            data={"evidence_id": evidence.pk},
        )


@dataclass
class DisposeEvidenceAction(Action):
    """Destroy gathered evidence, erasing the trail it would have fed (#1825)."""

    key: str = "dispose_evidence"
    name: str = "Dispose of Evidence"
    icon: str = "fire"
    category: str = "items"
    action_category: ActionCategory = ActionCategory.PHYSICAL
    target_type: TargetType = TargetType.SELF

    ap_cost: int = _EVIDENCE_AP_COST
    fatigue_cost: int = _EVIDENCE_FATIGUE_COST
    fatigue_category: str = ActionCategory.PHYSICAL

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.justice.evidence import EvidenceError, dispose_evidence  # noqa: PLC0415

        evidence = _resolve_evidence(kwargs.get("evidence_id"))
        if evidence is None:
            return ActionResult(success=False, message="There's no such evidence.")
        try:
            result = dispose_evidence(actor, evidence)
        except EvidenceError as exc:
            return ActionResult(success=False, message=exc.user_message)
        if not result.success:
            return ActionResult(
                success=True,
                message="PLACEHOLDER You can't quite bring yourself to make it disappear cleanly.",
            )
        return ActionResult(
            success=True,
            message="PLACEHOLDER The evidence is gone — as far as anyone can prove.",
        )
