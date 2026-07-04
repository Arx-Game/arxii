"""Applicable-pull computation for the unified combat UI thread-pull picker.

See docs/superpowers/specs/2026-05-23-unified-combat-ui-design.md §5.
"""

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
    - COURT_LEADER_NO_STAKE: COVENANT_ROLE threads (#1831) with a target_persona_id
      in context are inapplicable when no candidate ThreadPullEffect would be
      empowered by the Court leader's signed regard for that target (leader
      indifferent, or every candidate effect's polarity mismatches the regard
      sign). No-op when no leader is resolvable — the base pull is unmodulated.
      Gated on perception: the requester must be able to perceive the target
      persona's character or this never fires (nothing leaks about the
      leader's private regard for an unperceivable target — see
      ``_court_pull_would_have_effect``).

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

    # Rule: Court-leader-no-stake (#1831). A COVENANT_ROLE thread's pull only
    # gets a Court-leader-regard empowerment bonus when some candidate effect's
    # polarity matches the leader's signed regard sign for the live target
    # (see court_regard_modulation). When no candidate effect would ever be
    # empowered against this target, flag the thread inapplicable so the
    # player doesn't spend resonance expecting a boost that won't happen.
    if thread.target_kind == TargetKind.COVENANT_ROLE and context.target_persona_id is not None:
        if not _court_pull_would_have_effect(thread, context.target_persona_id):
            return False, InapplicabilityReason.COURT_LEADER_NO_STAKE.value

    return True, None


def _court_pull_would_have_effect(thread: Thread, target_persona_id: int) -> bool:
    """Whether some candidate pull effect on ``thread`` would be Court-empowered
    against the persona identified by ``target_persona_id``.

    Returns True (don't block) when no Court leader is resolvable — the base
    pull is unmodulated in that case, so there is no "no stake" signal to give.
    Returns False only when a leader IS resolvable and every candidate effect's
    polarity mismatches the sign of the leader's regard for the target (or the
    leader is indifferent — regard 0).

    Perception gate (#1831 security fix): the leader's signed regard for a
    target is private (ADR-0033/#1717). Before any regard/polarity logic runs,
    the target persona must resolve to a character the requester can actually
    perceive (``world.conditions.services.can_perceive`` — same-location and
    not concealed-and-undetected). When the target can't be resolved, has no
    character, or isn't perceivable, this returns True (treat as applicable,
    no special reason) so nothing about the leader's regard leaks through the
    picker's inapplicability signal.
    """
    from world.conditions.services import can_perceive  # noqa: PLC0415
    from world.magic.services.pull_effects import get_pull_effects_for_thread  # noqa: PLC0415
    from world.magic.services.pull_modulation_court import (  # noqa: PLC0415
        _regard_polarity_matches,
        _resolve_court_leader_persona,
    )
    from world.npc_services.regard import get_regard  # noqa: PLC0415
    from world.scenes.models import Persona  # noqa: PLC0415

    target_persona = Persona.objects.filter(pk=target_persona_id).first()
    if target_persona is None:
        return True
    # character_sheet is a non-null FK and character is its non-null OneToOne PK,
    # so a resolvable persona always has a character (same access as cast_services).
    target_character = target_persona.character_sheet.character

    requester_character = thread.owner.character
    if not can_perceive(requester_character, target_character):
        return True

    leader_persona = _resolve_court_leader_persona(thread)
    if leader_persona is None:
        return True
    regard = get_regard(leader_persona, target_persona)
    if regard == 0:
        return False

    rows = get_pull_effects_for_thread(thread, min_thread_level__lte=thread.level)
    return any(_regard_polarity_matches(row.regard_polarity, regard) for row in rows)
