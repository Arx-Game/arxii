"""Hazard-response prompt + AFK auto-flee tracking (#2846). Hazard-generic.

The lifecycle: an environmental-hazard condition enters a damaging stage →
``ensure_hazard_prompt`` creates the per-instance ``HazardResponseState`` and
prompts the player once (web ``hazard_prompt`` message + telnet text). The
per-hazard sweep then calls ``observe_hazard`` each tick: an observed health
drop counts as one damage instance, and after
``AUTO_FLEE_AFTER_DAMAGE_OBSERVATIONS`` unanswered instances the supplied
``flee`` callback fires — the AFK guard. A successful tough-it-out
(``mark_endured``) suspends both re-prompting and auto-flee for a window.

Nothing here knows about sunlight: the caller supplies the flee behavior and
the constants live with the hazard (``world.species.sun_constants`` for sun).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict
from typing import TYPE_CHECKING

from django.utils import timezone

from world.conditions.models import ConditionInstance, HazardResponseState

if TYPE_CHECKING:
    from datetime import datetime

HAZARD_ENDURE_ACTION_KEY = "hazard_endure"
HAZARD_RETREAT_ACTION_KEY = "hazard_retreat"


def ensure_hazard_prompt(instance: ConditionInstance) -> HazardResponseState:
    """Get-or-create the response state; prompt the player on first creation."""
    state, created = HazardResponseState.objects.get_or_create(
        condition_instance=instance,
        defaults={"last_health_snapshot": _target_health(instance)},
    )
    if created:
        _emit_prompt(instance)
    return state


def observe_hazard(
    instance: ConditionInstance,
    *,
    flee: Callable[[], bool],
    auto_flee_after: int,
) -> bool:
    """One sweep observation: count a health drop; auto-flee when the guard trips.

    Returns True when the flee callback ran and reported success. Never flees
    on the first damage instance, while an endure window holds, or after the
    player has responded to the prompt.
    """
    state = ensure_hazard_prompt(instance)
    health = _target_health(instance)
    if health < state.last_health_snapshot:
        state.damage_observations += 1
    state.last_health_snapshot = health
    state.save(update_fields=["damage_observations", "last_health_snapshot"])
    if state.responded_at is not None:
        return False
    if state.endured_until is not None and state.endured_until > timezone.now():
        return False
    if state.damage_observations < auto_flee_after:
        return False
    if flee():
        # A successful flee usually removes the hazard condition at the new
        # location, CASCADE-deleting this state row — only mark responded when
        # the row still exists (e.g. the refuge merely downgraded the hazard).
        if HazardResponseState.objects.filter(pk=state.pk).exists():
            state.responded_at = timezone.now()
            state.save(update_fields=["responded_at"])
        return True
    return False


def mark_endured(instance: ConditionInstance, *, until: datetime) -> HazardResponseState:
    """Record a successful tough-it-out: no re-prompt, no auto-flee until *until*."""
    state = ensure_hazard_prompt(instance)
    state.responded_at = timezone.now()
    state.endured_until = until
    state.save(update_fields=["responded_at", "endured_until"])
    return state


def mark_responded(instance: ConditionInstance) -> HazardResponseState:
    """Record that the player answered the prompt (retreat/cover/shade)."""
    state = ensure_hazard_prompt(instance)
    state.responded_at = timezone.now()
    state.save(update_fields=["responded_at"])
    return state


def _target_health(instance: ConditionInstance) -> int:
    """Current health of the instance's target; 0 when vitals are absent."""
    from django.core.exceptions import ObjectDoesNotExist  # noqa: PLC0415

    try:
        sheet = instance.target.character_sheet
        if sheet is None:
            return 0
        return sheet.vitals.health
    except (AttributeError, ObjectDoesNotExist):
        return 0


def _emit_prompt(instance: ConditionInstance) -> None:
    """Deliver the prompt: web ``hazard_prompt`` message + telnet text."""
    from web.webclient.message_types import HazardPromptPayload  # noqa: PLC0415

    character = instance.target
    stage_name = instance.current_stage.name if instance.current_stage else ""
    template = instance.condition
    player_text = template.player_description or f"{template.name} is harming you."
    payload = HazardPromptPayload(
        character_id=character.pk,
        condition_name=template.name,
        stage_name=stage_name,
        severity=instance.severity,
        player_text=player_text,
        endure_action=HAZARD_ENDURE_ACTION_KEY,
        retreat_action=HAZARD_RETREAT_ACTION_KEY,
    )
    text = (
        f"|r{template.name} is burning you ({stage_name}).|n You can flee to "
        "safety, cover up, seek shade, or tough it out — if you do nothing, "
        "your instincts will carry you to safety."
    )
    try:
        character.msg(text)
        character.msg(hazard_prompt=((), asdict(payload)))
    except AttributeError:
        pass
