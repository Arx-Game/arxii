"""GM Story Reward convergence helper (#2123).

Centralizes the "players served" scaling formula and the self-dealing guard so
``record_gm_marked_outcome``, ``resolve_episode``, and ``complete_story`` (the
three rev-1 convergence points) all compute the award identically. Delegates
the actual XP-granting + weekly-cap bookkeeping to
``world.gm.services.award_gm_story_reward`` — this module only resolves
"how many players did this GM serve" from a story scope + progress anchor.

Per ADR-0010 (FK direction: specific depends on general), this module lives in
the more specific ``world.stories`` app and imports the more general/reusable
``world.gm`` primitives (GM identity, table membership, the reward service) —
never the reverse.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.gm.services import award_gm_story_reward
from world.stories.constants import StoryScope

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.gm.models import GMProfile, GMTable

# A GROUP-scope award never scales past this many players, regardless of table size.
MAX_GROUP_PLAYERS_SERVED = 8


def players_served_for_scope(
    *,
    scope: str,
    gm_profile: GMProfile,
    character_sheet: CharacterSheet | None = None,
    gm_table: GMTable | None = None,
) -> int:
    """Return the players-served count for the award formula.

    CHARACTER: 1, unless the credited GM's own account owns the character
        (self-dealing — a GM running their own solo arc gets no reward) or no
        character_sheet was resolvable, in which case 0.
    GROUP: the count of currently-active ``GMTableMembership`` rows on
        ``gm_table``, excluding the GM's own persona if seated, capped at
        ``MAX_GROUP_PLAYERS_SERVED``. 0 when no gm_table was resolvable.
    GLOBAL (or any other value): 0 — no players-served formula fits a
        world-scope story yet (deferred, per the spec's Scope/follow-ups).
    """
    if scope == StoryScope.CHARACTER:
        if character_sheet is None:
            return 0
        if character_sheet.character.db_account_id == gm_profile.account_id:
            return 0
        return 1
    if scope == StoryScope.GROUP:
        if gm_table is None:
            return 0
        from world.gm.models import GMTableMembership  # noqa: PLC0415

        count = (
            GMTableMembership.objects.filter(table=gm_table, left_at__isnull=True)
            .exclude(persona__character_sheet__character__db_account=gm_profile.account_id)
            .count()
        )
        return min(count, MAX_GROUP_PLAYERS_SERVED)
    return 0


def credit_gm_story_reward(  # noqa: PLR0913
    *,
    resolved_by: GMProfile | None,
    scope: str,
    character_sheet: CharacterSheet | None,
    gm_table: GMTable | None,
    per_player_xp: int,
    event_cap: int,
    label: str,
) -> None:
    """Compute players_served and fire the GM Story Reward award; no-ops safely.

    No-ops when ``resolved_by`` is None (no GM identity resolved by the
    caller) or when ``players_served_for_scope`` returns 0 (self-dealing,
    GLOBAL scope, or an unresolvable anchor). ``label`` becomes the aggregate
    (never player-naming) tail of the XP transaction description.
    """
    if resolved_by is None:
        return
    players_served = players_served_for_scope(
        scope=scope,
        gm_profile=resolved_by,
        character_sheet=character_sheet,
        gm_table=gm_table,
    )
    if players_served <= 0:
        return
    award_gm_story_reward(
        gm_profile=resolved_by,
        players_served=players_served,
        per_player_xp=per_player_xp,
        event_cap=event_cap,
        description=f"GM reward: {label} for {players_served} player(s)",
    )
