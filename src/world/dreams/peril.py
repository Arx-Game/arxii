"""Dream Peril collapse resolver (#2290).

When a dreamer's mental fatigue collapses while dreamside, this module
resolves the outcome through the Dream Peril consequence pool.

Unlike ``_resolve_peril_via_pool`` (which requires a staged ConditionInstance
with ``resist_check_type``/``resist_difficulty``), this resolver calls
``select_consequence`` directly using the ``DreamPerilConfig`` singleton for
the check type and difficulty.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet


@dataclass(frozen=True)
class DreamPerilResult:
    """Result of a Dream Peril collapse resolution."""

    died: bool
    outcome_label: str
    message: str


def get_dream_peril_config():
    """Lazy-create and return the DreamPerilConfig singleton (pk=1)."""
    from world.dreams.models import DreamPerilConfig  # noqa: PLC0415

    config, _ = DreamPerilConfig.objects.get_or_create(pk=1)
    return config


def resolve_dream_peril_collapse(
    character_sheet: CharacterSheet,
    *,
    source_character=None,
) -> DreamPerilResult:
    """Resolve a dream-side mental fatigue collapse through the Dream Peril pool.

    Args:
        character_sheet: The collapsing dreamer's sheet.
        source_character: The ObjectDB that caused the collapse (PC attacker
            or None for environmental). PC sources cannot kill (ADR-0023).

    Returns:
        DreamPerilResult with died flag, outcome label, and message.
    """
    from actions.models import ConsequencePool  # noqa: PLC0415
    from world.checks.consequence_resolution import (  # noqa: PLC0415
        apply_resolution,
        resolve_pool_consequences,
        select_consequence,
    )
    from world.checks.types import ResolutionContext  # noqa: PLC0415
    from world.vitals.constants import POOL_DREAM_PERIL  # noqa: PLC0415
    from world.vitals.peril_resolution import death_is_permitted  # noqa: PLC0415
    from world.vitals.services import _mark_dead  # noqa: PLC0415

    # Get the Dream Peril pool
    pool = ConsequencePool.objects.filter(name=POOL_DREAM_PERIL).first()
    if pool is None:
        # Pool not seeded — fall back to a no-op recovery
        return DreamPerilResult(
            died=False,
            outcome_label="wake_shaken",
            message="You wake, shaken but unharmed.",
        )

    candidates = resolve_pool_consequences(pool)

    # PC-source death gate (ADR-0023): exclude death for PC sources
    if not death_is_permitted(
        victim_sheet=character_sheet,
        source_character=source_character,
    ):
        candidates = [c for c in candidates if not c.character_loss]

    config = get_dream_peril_config()
    character = character_sheet.character

    # Roll the Dream Peril resist check (stability-based, configured on DreamPerilConfig)
    if config.resist_check_type is None:
        # No check configured — return a safe default (wake shaken)
        return DreamPerilResult(
            died=False,
            outcome_label="wake_shaken",
            message="You wake with a gasp, heart pounding. The dream releases you.",
        )

    pending = select_consequence(
        character,
        config.resist_check_type,
        config.resist_difficulty,
        candidates,
    )

    apply_resolution(
        pending,
        ResolutionContext(character=character, source_character=source_character),
    )

    selected = pending.selected_consequence
    if selected is not None and selected.character_loss:
        _mark_dead(character_sheet)
        return DreamPerilResult(
            died=True,
            outcome_label=selected.label,
            message="Your body fails. The dream takes you forever.",
        )

    label = selected.label if selected is not None else "wake_shaken"
    messages = {
        "wake_shaken": "You wake with a gasp, heart pounding. The dream releases you.",
        "nightmares": "Dark dreams cling to you even as you wake, poisoning your mind.",
        "madness": "Something breaks inside your mind. The world will never look the same.",
    }
    return DreamPerilResult(
        died=False,
        outcome_label=label,
        message=messages.get(label, "You survive the dream, somehow."),
    )
