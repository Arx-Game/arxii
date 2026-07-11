"""Route a social-action graded outcome to the right disposition tier (#1591)."""

from __future__ import annotations

# Per success-tier disposition deltas (ADR-0019: tier-sourced, not hardcoded
# check difficulty). success_level is a SmallIntegerField on a -10..+10 scale
# (world/traits/models.py:484; checks/AGENT_GLOSSARY.md:16); >0 = success,
# <=0 = no positive movement. Thresholds: >=5 critical, >=3 strong, >=1 marginal.
_TIER_DELTA = {5: 5, 3: 3, 1: 1}

# Qualitative band per tier delta (#2158) — this path is warming-only (no
# negative deltas exist in _TIER_DELTA), so the band never needs a "cools"
# branch.
_SHIFT_BAND = {1: "slightly", 3: "noticeably", 5: "considerably"}


def disposition_shift_band(delta: int) -> str:
    """The qualitative magnitude word for a disposition delta (#2158).

    Mirrors this codebase's established per-domain qualitative-band pattern
    (``world.locations.character_comfort._band_for``) — never a raw number in
    player-facing text.
    """
    return _SHIFT_BAND.get(delta, "slightly")


def apply_social_disposition_delta(actor, target_persona_id, result) -> str | None:
    """Apply a tiered disposition delta after a social action resolves.

    Persona-bearing NPCs (``target_persona_id`` resolves to a ``Persona``)
    move durable ``NPCStanding.affection``. The persona-less mook path is
    deferred — ``execute()`` has no session-scoped ephemeral store in scope,
    so Task 7's promotion seam will wire that path.

    Returns a ready-to-display message (e.g. "Their regard for you warms
    noticeably.") when a delta was applied, or None when nothing moved —
    callers (#2158) surface this directly as a toast; no caller should
    reconstruct wording from a raw delta.
    """
    from world.npc_services.services import adjust_npc_affection  # noqa: PLC0415
    from world.scenes.services import (  # noqa: PLC0415
        MissingPrimaryPersonaError,
        persona_for_character,
    )

    success_level = _success_level(result)
    delta = _delta_for_tier(success_level)
    if delta == 0 or target_persona_id is None:
        return None

    from world.scenes.action_services import _persona_is_npc  # noqa: PLC0415
    from world.scenes.models import Persona  # noqa: PLC0415

    target_persona = Persona.objects.filter(pk=target_persona_id).first()
    if target_persona is None or not _persona_is_npc(target_persona):
        return None

    # Persona-bearing NPC → durable NPCStanding.
    try:
        pc_persona = persona_for_character(actor)
    except MissingPrimaryPersonaError:
        # A half-set-up actor should not crash the action.
        return None

    adjust_npc_affection(pc_persona, target_persona, delta=delta)
    target_name = target_persona.character_sheet.character.db_key
    return f"{target_name}'s regard for you warms {disposition_shift_band(delta)}."


def _success_level(result) -> int:
    main = getattr(result, "main_result", None)  # noqa: GETATTR_LITERAL
    if main is not None and getattr(main, "check_result", None) is not None:  # noqa: GETATTR_LITERAL
        return main.check_result.success_level or 0
    return 0


def _delta_for_tier(success_level: int) -> int:
    for threshold, delta in sorted(_TIER_DELTA.items(), reverse=True):
        if success_level >= threshold:
            return delta
    return 0
