"""Death-permission gate for the acute-peril dying state (#1479, Task 3).

Determines whether a lethal outcome is structurally permitted for a given
victim/source pair. Two hard rules apply before any risk math:

- PC source (ADR-0023): PvP is structurally non-lethal — death never permitted.
- Active death_deferred condition: a deferred-death condition blocks the outcome.
- Absent/None source: treated as a non-lethal environmental context — not permitted.

A non-PC (significant-NPC) source with no death-deferral active on the victim
is the only configuration that returns True.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from actions.models.consequence_pools import ConsequencePool
    from world.character_sheets.models import CharacterSheet


def is_pc_source(source_character: "ObjectDB | None") -> bool:  # noqa: OBJECTDB_PARAM
    """Return True when source_character is a player-controlled character.

    Uses the canonical PC-detection convention: a character is player-controlled
    iff ``character.db_account`` is not None (mirrors ``_persona_is_npc`` in
    ``world.scenes.action_services``). Returns False for None sources.
    """
    if source_character is None:
        return False
    return source_character.db_account is not None


def death_is_permitted(
    *,
    victim_sheet: "CharacterSheet",
    source_character: "ObjectDB | None",  # noqa: OBJECTDB_PARAM
) -> bool:
    """Return True only when death is a structurally valid outcome.

    Returns False (not permitted) when ANY of:
    - source_character is None (absent/non-lethal environmental context).
    - source_character is a PC (ADR-0023: PvP is non-lethal).
    - The victim carries an active death_deferred condition.

    Returns True only for a non-PC source with no active death_deferred on
    the victim (i.e. a significant-NPC attacker in a lethal encounter).
    """
    if source_character is None:
        return False

    if is_pc_source(source_character):
        return False

    from world.conditions.services import has_death_deferred  # noqa: PLC0415

    if has_death_deferred(victim_sheet.character):
        return False

    return True


def select_abandonment_pool(
    source_character: "ObjectDB | None",  # noqa: OBJECTDB_PARAM
) -> "ConsequencePool":
    """Return the abandonment ConsequencePool appropriate for the source type.

    Routes to one of three pre-authored pools by source character kind:
    - PC source → ``abandonment_pvp`` pool (ADR-0023: die row filtered at runtime).
    - Non-PC (NPC) source → ``abandonment_enemy`` pool.
    - None source → ``abandonment_environmental`` pool.

    The pools must be seeded in the database (via
    ``world.vitals.factories.create_abandonment_pools``) before this
    function is called.  Raises ``ConsequencePool.DoesNotExist`` if the
    named pool is absent — treat that as a seeding gap, not a logic error.
    """
    from actions.models import ConsequencePool  # noqa: PLC0415
    from world.vitals.factories import (  # noqa: PLC0415
        POOL_ABANDONMENT_ENEMY,
        POOL_ABANDONMENT_ENVIRONMENTAL,
        POOL_ABANDONMENT_PVP,
    )

    if is_pc_source(source_character):
        pool_name = POOL_ABANDONMENT_PVP
    elif source_character is not None:
        pool_name = POOL_ABANDONMENT_ENEMY
    else:
        pool_name = POOL_ABANDONMENT_ENVIRONMENTAL

    return ConsequencePool.objects.get(name=pool_name)
