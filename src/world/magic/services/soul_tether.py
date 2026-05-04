"""Soul Tether services (Spec B §16).

Public functions:
- accept_soul_tether: formation Ritual Capstone (§12).
- dissolve_soul_tether: stub dissolution (§13).
- request_sineating: Sinner asks (§7).
- resolve_sineating: Sineater @reply resolution (§7).
- perform_soul_tether_rescue: stage-3+ rescue ritual (§9).

Reactive subscribers (registered as TriggerDefinition rows backed by
FlowDefinition + SERVICE step):
- soul_tether_redirect_handler: drains Hollow on CORRUPTION_ACCRUING (§5).
- soul_tether_stage_advance_prompt: fires PROMPT_PLAYER on
  CONDITION_STAGE_ADVANCE_CHECK_ABOUT_TO_FIRE (§8).
- resolve_stage_advance_prompt: Sineater @reply resolution for the
  stage-advance prompt (§8).
"""

from __future__ import annotations

from typing import Any

from world.character_sheets.models import CharacterSheet
from world.magic.models.affinity import Resonance
from world.magic.types.soul_tether import (
    RescueOutcome,
    SineatingResult,
    SoulTetherRole,
)


def accept_soul_tether(  # noqa: PLR0913
    initiator_sheet: CharacterSheet,
    partner_sheet: CharacterSheet,
    sinner_role: SoulTetherRole,
    resonance: Resonance,
    writeup: str,
    ritual_components: list[Any],
) -> Any:
    """Form a Soul Tether (Spec B §12.4)."""
    raise NotImplementedError


def dissolve_soul_tether(
    relationship_id: int,
    initiator_sheet: CharacterSheet,
) -> None:
    """Dissolve a Soul Tether — MVP stub (Spec B §13)."""
    raise NotImplementedError


def request_sineating(
    sinner_sheet: CharacterSheet,
    sineater_sheet: CharacterSheet,
    resonance: Resonance,
    max_units: int,
    scene: Any,
) -> str:
    """Sinner-initiated Sineating request — fires PROMPT_PLAYER, returns prompt id (Spec B §7.2)."""
    raise NotImplementedError


def resolve_sineating(
    prompt_id: str,
    units_accepted: int,
) -> SineatingResult:
    """Resolve a Sineating prompt with the Sineater's chosen amount (Spec B §7.2)."""
    raise NotImplementedError


def perform_soul_tether_rescue(
    sineater_sheet: CharacterSheet,
    sinner_sheet: CharacterSheet,
    resonance: Resonance,
    components: list[Any],
) -> RescueOutcome:
    """Perform a stage-3+ rescue ritual (Spec B §9.4)."""
    raise NotImplementedError


def soul_tether_redirect_handler(payload: Any) -> None:
    """Subscriber for CORRUPTION_ACCRUING — drains Hollow, cancels event (Spec B §5.2)."""
    raise NotImplementedError


def soul_tether_stage_advance_prompt(payload: Any) -> None:
    """Subscriber for CONDITION_STAGE_ADVANCE_CHECK_ABOUT_TO_FIRE (Spec B §8.1)."""
    raise NotImplementedError


def resolve_stage_advance_prompt(
    prompt_id: str,
    units_committed: int,
) -> None:
    """Resolve the stage-advance bonus prompt with the Sineater's commitment (Spec B §8.1)."""
    raise NotImplementedError
