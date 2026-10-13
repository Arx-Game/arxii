"""Adding and removing opponents."""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.combat.constants import OpponentStatus, OpponentTier
from world.combat.models import (
    BossPhase,
    CombatEncounter,
    CombatOpponent,
    PendingOpponentAttack,
    ThreatPool,
)
from world.combat.services.damage.engagement_lock import _break_engagement_lock_on_defeat
from world.combat.services.encounter.completion import (
    _check_encounter_completion,
    complete_encounter,
)
from world.combat.services.encounter.encounter_outcome import _classify_encounter_outcome
from world.combat.services.npc.windup_narration import _broadcast_windup_fizzled
from world.scenes.constants import RoundStatus

if TYPE_CHECKING:
    from evennia.accounts.models import AccountDB
    from evennia.objects.models import ObjectDB

    from world.areas.positioning.models import Position
    from world.scenes.models import Persona
    from world.stories.models import Story


def _resolve_opponent_stat_fields(  # noqa: PLR0913
    block: object | None,
    *,
    soak_value: int | None,
    probing_threshold: int | None,
    swarm_count: int | None,
    body_toughness: int | None,
    bodies_per_attack: int | None,
    barrier_strength: int | None,
) -> tuple[int, int | None, int | None, int | None, int | None, int | None]:
    """Return resolved (soak, probing, swarm, body_toughness, bodies_per_attack, barrier)
    from either the auto-scaling block or manual-mode defaults."""
    if block is not None:
        return (
            soak_value if soak_value is not None else block.soak_value,
            probing_threshold if probing_threshold is not None else block.probing_threshold,
            swarm_count if swarm_count is not None else block.swarm_count,
            body_toughness if body_toughness is not None else block.body_toughness,
            bodies_per_attack if bodies_per_attack is not None else block.bodies_per_attack,
            barrier_strength if barrier_strength is not None else block.barrier_strength,
        )
    return (
        soak_value if soak_value is not None else 0,
        probing_threshold,
        swarm_count,
        body_toughness,
        bodies_per_attack,
        barrier_strength,
    )


def _resolve_objectdb_for_opponent(
    encounter: CombatEncounter,
    name: str,
    persona: Persona | None,
    existing_objectdb: ObjectDB | None,
) -> tuple[object, bool]:
    """Resolve the ObjectDB and ephemeral flag for a new CombatOpponent.

    Three sources (checked in order):
    - existing_objectdb: pre-existing OD — not ephemeral, must be a Character.
    - persona: reuses persona's character OD — not ephemeral.
    - neither: creates a fresh CombatNPC in encounter.room — ephemeral.
    """
    from evennia.utils.create import create_object  # noqa: PLC0415

    from typeclasses.characters import Character  # noqa: PLC0415
    from world.combat.typeclasses.combat_npc import CombatNPC  # noqa: PLC0415

    if existing_objectdb is not None:
        if not isinstance(existing_objectdb, Character):
            msg = (
                f"existing_objectdb must be a Character typeclass instance "
                f"(got {type(existing_objectdb).__name__}). "
                f"Combat damage paths require character.conditions handler access."
            )
            raise TypeError(msg)
        return existing_objectdb, False

    if persona is not None:
        return persona.character_sheet.character, False

    if encounter.room is None:
        msg = "Cannot create ephemeral CombatNPC: encounter has no room."
        raise ValueError(msg)
    return create_object(CombatNPC, key=name, location=encounter.room, nohome=True), True


def _acting_story_for_encounter(encounter: CombatEncounter) -> Story | None:
    """The Story an ``add_opponent`` custody check acts on behalf of (#2001 Task 5).

    ``CombatEncounter.story_beat`` is set when this encounter resolves a
    specific Beat (#1760) — walking beat->episode->chapter->story mirrors
    ``custody_verdict_for_stake``'s ``stake.beat.episode.chapter.story``, so a
    GM running an encounter for the very story that protects the spawned NPC
    is never treated as "a different story". None when the encounter isn't
    wired to a beat (legacy/ad-hoc combat) — the custody seam then falls back
    to the participation/clearance rules alone.
    """
    if encounter.story_beat is None:
        return None
    return encounter.story_beat.episode.chapter.story


def _enforce_opponent_custody_gate(
    objectdb: object,
    is_ephemeral: bool,
    encounter: CombatEncounter,
    acting_account: AccountDB | None,
) -> None:
    """Custody APPEAR gate for ``add_opponent`` (#2001 Task 5).

    Gated ONLY when the opponent resolves to an EXISTING ``CharacterSheet``
    (``existing_objectdb``/``persona`` path) — a freshly-created ephemeral
    ``CombatNPC`` (``is_ephemeral`` True) has no ``CharacterSheet`` and is
    never gated. ``acting_account=None`` is the system-initiated carve-out
    (duels/cast_seed/magic-summon/companion-materialize callers pass no GM
    account) — the check is SKIPPED entirely, never called with
    ``actor_account=None`` (which inside ``check_subject_custody`` would mean
    "no clearance possible", blocking system spawns it should never touch).

    Raises:
        NPCUnderCustodyError: When ``check_subject_custody`` refuses the
            acting GM at ``CustodyScope.APPEAR``. The disclosure-safe message
            mirrors ``StakeSerializer``'s custody gate (ADR-0033 posture —
            never the protecting story's identity).
    """
    if is_ephemeral or acting_account is None:
        return
    sheet = objectdb.character_sheet
    if sheet is None:
        return

    from world.combat.scaling import NPCUnderCustodyError  # noqa: PLC0415
    from world.stories.constants import CustodyScope  # noqa: PLC0415
    from world.stories.services.custody import (  # noqa: PLC0415
        check_subject_custody,
        subject_identity_for_sheet,
    )

    verdict = check_subject_custody(
        subject_identity=subject_identity_for_sheet(sheet),
        actor_account=acting_account,
        scope=CustodyScope.APPEAR,
        acting_story=_acting_story_for_encounter(encounter),
    )
    if verdict.allowed:
        return

    if verdict.custodian_gm_username:
        msg = (
            "This NPC is under another story's custody — request clearance "
            f"from GM {verdict.custodian_gm_username}."
        )
    else:
        msg = (
            "This NPC is under another story's custody — request clearance "
            "from the story's GM via staff."
        )
    raise NPCUnderCustodyError(msg, user_message=msg)


def add_opponent(  # noqa: PLR0913 - opponent creation requires all stat fields
    encounter: CombatEncounter,
    *,
    name: str,
    tier: str,
    threat_pool: ThreatPool | None,
    max_health: int | None = None,
    description: str = "",
    soak_value: int | None = None,
    probing_threshold: int | None = None,
    swarm_count: int | None = None,
    body_toughness: int | None = None,
    bodies_per_attack: int | None = None,
    barrier_strength: int | None = None,
    auto_phases: bool = True,
    persona: Persona | None = None,
    existing_objectdb: ObjectDB | None = None,
    acting_account: AccountDB | None = None,
    position: Position | None = None,
    level: int | None = None,
) -> CombatOpponent:
    """Create a CombatOpponent. Three sources for the ObjectDB:

    - existing_objectdb: pre-existing OD (PvP, named NPC w/o persona). Never ephemeral.
    - persona: reuses persona's character ObjectDB. Never ephemeral.
    - neither: creates a new CombatNPC OD scoped to this encounter. Ephemeral.

    When ``max_health`` is omitted (the opt-in signal), the scaling formula
    fills in every omitted stat field via
    ``compute_opponent_stat_block(tier, encounter)``.  Passing ``max_health``
    selects manual mode: the formula is never called and other omitted stats
    keep their legacy defaults (e.g. ``soak_value`` → 0).  Explicitly-passed
    values always win over the formula.  Pass ``auto_phases=False`` to skip
    automatic ``BossPhase`` creation for BOSS-tier opponents (manual mode also
    creates no phases, since no block is computed).

    ``acting_account`` (#2001 Task 5): the GM account running this spawn, used
    ONLY for the custody APPEAR gate on an existing/persona-sourced opponent's
    CharacterSheet (see ``_enforce_opponent_custody_gate``). Left at the
    default ``None`` by every system-initiated caller (duels, cast_seed, magic
    summon effect handlers, companion materialize) — deliberately un-gated.
    Raises ``NPCUnderCustodyError`` (a ``ValueError``) when refused.

    ``position`` (#2005) places the resolved objectdb there via
    ``place_in_position`` — the unchecked staging primitive, not the validated
    voluntary-entry one — once the opponent's objectdb is known. The room match
    is validated *before* the ``CombatOpponent`` row is persisted, so a
    cross-room ``position`` raises ``PositionError`` with no saved-but-unplaced
    opponent left behind. Omitted (default) leaves the opponent unplaced,
    matching legacy behavior.

    ``level`` (#2707) resolves in this order: an explicit value always wins
    (how a GM authors a deliberately under- or over-levelled boss); otherwise,
    in auto-scaling mode, the encounter's average party level as already
    resolved onto ``block.level`` by ``compute_opponent_stat_block``; otherwise
    (manual mode, no block) falls back to 1. Level and tier are independent
    axes — a level 3 boss and a level 20 mook are both coherent.
    """
    from world.combat.scaling import compute_opponent_stat_block  # noqa: PLC0415

    # The formula is triggered by an absent max_health (auto-scaling mode).
    # Callers that pass max_health explicitly are in "manual mode": omitted
    # secondary stats fall back to their legacy defaults (soak=0, etc.).
    block = compute_opponent_stat_block(tier, encounter) if max_health is None else None
    resolved_max_health: int = max_health if max_health is not None else block.max_health

    (
        resolved_soak,
        resolved_probing,
        resolved_swarm,
        resolved_body_toughness,
        resolved_bodies_per_attack,
        resolved_barrier_strength,
    ) = _resolve_opponent_stat_fields(
        block,
        soak_value=soak_value,
        probing_threshold=probing_threshold,
        swarm_count=swarm_count,
        body_toughness=body_toughness,
        bodies_per_attack=bodies_per_attack,
        barrier_strength=barrier_strength,
    )

    # Action economy: auto-scaling stamps from the tier template; manual mode
    # defaults to 1 (the legacy behavior for hand-built opponents).
    resolved_actions_per_round: int = block.actions_per_round if block is not None else 1

    # Level (#2707): explicit value always wins; otherwise auto-scaling mode
    # takes the encounter's average party level already resolved onto the
    # block; otherwise (manual mode) falls back to 1.
    default_level: int = block.level if block is not None else 1
    resolved_level: int = level if level is not None else default_level

    objectdb, is_ephemeral = _resolve_objectdb_for_opponent(
        encounter, name, persona, existing_objectdb
    )
    _enforce_opponent_custody_gate(objectdb, is_ephemeral, encounter, acting_account)

    if position is not None and position.room_id != objectdb.db_location_id:
        # Validate the room match before persisting the CombatOpponent row below —
        # the resolved objectdb is known now, so a bad position fails fast instead
        # of leaving a saved-but-unplaced opponent behind a failure ActionResult
        # (Task 4 fold-in, #2005). The post-save place_in_position call further
        # down re-checks the identical invariant; it can no longer fail once
        # execution reaches it.
        from world.areas.positioning.exceptions import PositionError  # noqa: PLC0415

        msg = "That position is not in the same room as the opponent."
        raise PositionError(msg)

    opp = CombatOpponent(
        encounter=encounter,
        name=name,
        tier=tier,
        level=resolved_level,
        max_health=resolved_max_health,
        health=resolved_max_health,
        threat_pool=threat_pool,
        description=description,
        soak_value=resolved_soak,
        probing_threshold=resolved_probing,
        swarm_count=resolved_swarm,
        # Bodies-at-start mirrors the initial count so a percentage-remaining
        # display has a denominator; null for non-swarm tiers (resolved_swarm None).
        max_swarm_count=resolved_swarm,
        body_toughness=resolved_body_toughness,
        bodies_per_attack=resolved_bodies_per_attack,
        barrier_strength=resolved_barrier_strength,
        actions_per_round=resolved_actions_per_round,
        persona=persona,
        objectdb=objectdb,
        objectdb_is_ephemeral=is_ephemeral,
    )
    opp.full_clean()
    opp.save()

    if position is not None:
        from typing import cast  # noqa: PLC0415

        from world.areas.positioning.services import place_in_position  # noqa: PLC0415

        # _resolve_objectdb_for_opponent is annotated tuple[object, bool];
        # every branch actually returns an ObjectDB (Character or CombatNPC).
        place_in_position(cast("ObjectDB", objectdb), position)

    # --- Auto-generate BossPhase rows from the computed block ---
    if tier == OpponentTier.BOSS and auto_phases and block is not None and block.phases:
        BossPhase.objects.bulk_create(
            [
                BossPhase(
                    opponent=opp,
                    phase_number=spec.phase_number,
                    health_trigger_percentage=spec.health_trigger_percentage,
                    soak_value=spec.soak_value,
                    probing_threshold=spec.probing_threshold,
                    threat_pool=None,
                )
                for spec in block.phases
            ]
        )

    from world.combat.escalation import check_hated_foe_surges_for_new_opponent  # noqa: PLC0415

    check_hated_foe_surges_for_new_opponent(opp)

    return opp


def remove_opponent(opponent: CombatOpponent) -> None:
    """Pull an opponent out of a live encounter (GM action, #3382).

    Reuses the defeat teardown seam minus defeat consequences: no legend/loot/
    aftermath, no narrated defeat. Raises ValueError if the opponent is not
    ACTIVE (already defeated/fled/removed — nothing to tear down twice).
    """
    from world.combat.constants import LockBreakReason  # noqa: PLC0415

    if opponent.status != OpponentStatus.ACTIVE:
        msg = f"Opponent {opponent.pk} is not ACTIVE (status={opponent.status})."
        raise ValueError(msg)

    opponent.status = OpponentStatus.REMOVED
    opponent.save(update_fields=["status"])

    # Break the active engagement lock immediately, same as a defeat teardown
    # (decision 2) — a GM pull is a harder cut than fleeing, not a softer one.
    _break_engagement_lock_on_defeat(opponent, reason=LockBreakReason.REMOVED)

    # Fizzle any pending wind-up this opponent had committed to — it never
    # deletes the CombatOpponent row (decision 5), so CASCADE never fires and
    # a stale PendingOpponentAttack would otherwise still resolve next round.
    for pending in PendingOpponentAttack.objects.filter(opponent=opponent):
        _broadcast_windup_fizzled(pending, reason="is called off")
        pending.delete()

    encounter = opponent.encounter
    if encounter.status != RoundStatus.COMPLETED and _check_encounter_completion(encounter):
        complete_encounter(encounter, outcome=_classify_encounter_outcome(encounter))
