"""Applicable-pull computation for the unified combat UI thread-pull picker."""

from dataclasses import dataclass

from world.character_sheets.models import CharacterSheet
from world.magic.constants import InapplicabilityReason, TargetKind
from world.magic.models import Thread
from world.magic.models.techniques import Technique


@dataclass(frozen=True)
class PullActionContext:
    """Caller-supplied context describing the action a pull is being chosen for."""

    technique: Technique | None
    effect_type_id: int | None
    target_object_id: int | None
    target_persona_id: int | None
    scene_id: int | None


@dataclass(frozen=True)
class ThreadApplicability:
    """Per-thread applicability row returned to the API layer."""

    thread: Thread
    applicable: bool
    reason: str | None  # InapplicabilityReason value; None when applicable


def compute_thread_applicability(
    sheet: CharacterSheet,
    context: PullActionContext,
) -> list[ThreadApplicability]:
    """Return per-thread applicability + reason for the given action context.

    Returns one row per active (non-retired) Thread owned by the character sheet.

    Current rule set (first match wins):
    - ANCHORED_ON_OTHER_TECHNIQUE: TECHNIQUE-kind threads whose target_technique
      differs from the context technique are inapplicable.

    The following InapplicabilityReason values are defined in the enum for future
    phases but not yet wired here (their data dependencies are not yet available):
    - WRONG_AFFINITY: requires an affinity on Technique (not yet modelled).
    - ANCHOR_TARGET_NOT_PRESENT: requires scene-presence query.
    - PREREQUISITE_UNMET: requires prerequisite evaluation infrastructure.
    - LOCATION_MISMATCH: requires room-property query at action time.
    - THREAD_RETIRED: filtered out by the queryset below; never returned.
    """
    threads = (
        Thread.objects.filter(owner=sheet, retired_at__isnull=True)
        .select_related("resonance", "target_technique")
        .order_by("pk")
    )
    out: list[ThreadApplicability] = []
    for thread in threads:
        applicable, reason = _check_applicability(thread, context)
        out.append(ThreadApplicability(thread=thread, applicable=applicable, reason=reason))
    return out


def _check_applicability(
    thread: Thread,
    context: PullActionContext,
) -> tuple[bool, str | None]:
    """Run the applicability rules for one thread. Returns (applicable, reason)."""
    # Rule: anchored-on-other-technique.
    # A TECHNIQUE-kind thread is only applicable when the context technique
    # matches the thread's anchor technique. When the context has no technique
    # (technique=None), a TECHNIQUE-kind thread is always inapplicable because
    # the action isn't using any technique that the thread is anchored to.
    if thread.target_kind == TargetKind.TECHNIQUE:
        if context.technique is None or thread.target_technique_id != context.technique.pk:
            return False, InapplicabilityReason.ANCHORED_ON_OTHER_TECHNIQUE.value

    return True, None
