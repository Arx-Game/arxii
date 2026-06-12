"""Achievement counter increment helpers for combat events.

Damage / KO / Death events in combat increment named StatTracker counters
on the source and target CharacterSheets. The achievement engine reads
these aggregates to evaluate requirements.

Counters tracked:
- ``combat.damage_dealt`` — per-PC running total of damage dealt to opponents.
- ``combat.damage_received`` — per-PC running total of damage taken.
- ``combat.opponents_defeated`` — per-PC count of opponents defeated.
- ``combat.knockouts_dealt`` — per-PC count of KOs caused by their actions.
- ``combat.killshots`` — per-PC count of deaths caused by their actions.
- ``combat.times_kod`` — per-PC count of KO transitions suffered.

Phase 3 — combat-resolution-loop PR.

Note on persistence: this PR persists *aggregates only*. There is no per-event
audit log (no ``ActionDamage`` / ``ActionConsequence`` rows). Aggregate
queries via StatTracker / achievement requirements answer "total damage by
X" and "killshot count by X" — the typical metrics. Per-event audit is
additive future work if a replay UI or structured forensics surface needs it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.achievements.models import StatDefinition

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet


# ---------------------------------------------------------------------------
# Stat key constants — passed to StatDefinition.objects.get_or_create.
# ---------------------------------------------------------------------------

STAT_KEY_DAMAGE_DEALT = "combat.damage_dealt"
STAT_KEY_DAMAGE_RECEIVED = "combat.damage_received"
STAT_KEY_OPPONENTS_DEFEATED = "combat.opponents_defeated"
STAT_KEY_KNOCKOUTS_DEALT = "combat.knockouts_dealt"
STAT_KEY_KILLSHOTS = "combat.killshots"
STAT_KEY_TIMES_KOD = "combat.times_kod"
STAT_KEY_ENCOUNTERS_WON = "combat.encounters_won"
STAT_KEY_ENCOUNTERS_LOST = "combat.encounters_lost"
STAT_KEY_ENCOUNTERS_FLED = "combat.encounters_fled"

_STAT_KEY_DISPLAY: dict[str, tuple[str, str]] = {
    STAT_KEY_DAMAGE_DEALT: (
        "Damage Dealt",
        "Total damage dealt to opponents across all combat encounters.",
    ),
    STAT_KEY_DAMAGE_RECEIVED: (
        "Damage Received",
        "Total damage received from opponents across all combat encounters.",
    ),
    STAT_KEY_OPPONENTS_DEFEATED: (
        "Opponents Defeated",
        "Number of opponents defeated by your actions.",
    ),
    STAT_KEY_KNOCKOUTS_DEALT: (
        "Knockouts Dealt",
        "Number of times your actions knocked out another participant.",
    ),
    STAT_KEY_KILLSHOTS: (
        "Killshots",
        "Number of times your actions killed another participant.",
    ),
    STAT_KEY_TIMES_KOD: (
        "Times Knocked Out",
        "Number of times you have been knocked out in combat.",
    ),
    STAT_KEY_ENCOUNTERS_WON: (
        "Encounters Won",
        "Combat encounters that ended in victory while you still stood.",
    ),
    STAT_KEY_ENCOUNTERS_LOST: (
        "Encounters Lost",
        "Combat encounters that ended in defeat.",
    ),
    STAT_KEY_ENCOUNTERS_FLED: (
        "Encounters Fled",
        "Combat encounters you escaped before the end.",
    ),
}


def _get_or_create_stat_def(key: str) -> StatDefinition:
    """Lazily fetch the StatDefinition row for a combat counter key.

    Created with player-facing name + description on first access. Stored in
    SharedMemoryModel cache thereafter.
    """
    name, description = _STAT_KEY_DISPLAY[key]
    stat_def, _ = StatDefinition.objects.get_or_create(
        key=key,
        defaults={"name": name, "description": description},
    )
    return stat_def


def increment_combat_counter(
    character_sheet: CharacterSheet,
    key: str,
    amount: int = 1,
) -> int:
    """Increment a combat counter on the given character sheet.

    Lazily creates the StatDefinition row if it doesn't exist yet.
    Returns the new counter value. Atomic (delegates to StatHandler.increment).

    Combat code calls this at apply-sites (apply_damage_to_*, KO/Death
    transitions). It does NOT write event-log rows — only aggregates.
    """
    if amount <= 0:
        return character_sheet.stats.get(_get_or_create_stat_def(key))
    stat_def = _get_or_create_stat_def(key)
    return character_sheet.stats.increment(stat_def, amount)
