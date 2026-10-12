"""Adding, removing, and spawning opponents; pull expiry; break-bar config."""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from django.db.models import Q

from world.combat import services as _svc
from world.combat.constants import (
    BAR_UNITS_PER_ROUND,
    PACING_FLOOR_ROUND_PADDING,
    CombatManeuver,
    OpponentStatus,
    OpponentTier,
    ParticipantStatus,
)
from world.combat.models import (
    BossPhase,
    CombatEncounter,
    CombatOpponent,
    CombatParticipant,
    CombatRoundAction,
    CreatureTemplate,
    ThreatPool,
)
from world.fatigue.constants import EffortLevel
from world.scenes.constants import RoundStatus

if TYPE_CHECKING:
    from evennia.accounts.models import AccountDB
    from evennia.objects.models import ObjectDB

    from world.areas.positioning.models import Position
    from world.scenes.models import Persona
    from world.stories.models import Story


def _parley_gate_met(
    participant: CombatParticipant,
    opponent: CombatOpponent,
) -> bool:
    """Return whether parley's precondition is met (#2015).

    Parley is gated: the opponent must be faltering or broken (morale below
    ``FALTER_MORALE_THRESHOLD``), OR the participant's persona must hold an
    ``NPCStanding`` with ``affection >= PARLEY_DISPOSITION_FLOOR`` toward the
    opponent's persona. A steady, unknown opponent cannot be parleyed with —
    but mindless targets are not rejected here (they roll with resistance at
    resolve time; a breakthrough grants a fleeting mind).
    """
    from world.combat.constants import PARLEY_DISPOSITION_FLOOR  # noqa: PLC0415
    from world.combat.morale import OpponentMoraleState, morale_state_for  # noqa: PLC0415

    if morale_state_for(opponent) != OpponentMoraleState.STEADY:
        return True

    # Steady opponent: check durable standing toward the opponent's persona.
    if opponent.persona_id is None:
        return False

    from world.npc_services.models import NPCStanding  # noqa: PLC0415
    from world.scenes.services import (  # noqa: PLC0415
        MissingPrimaryPersonaError,
        persona_for_character,
    )

    try:
        pc_persona = persona_for_character(participant.character_sheet.character)
    except MissingPrimaryPersonaError:
        # Half-set-up actor with no primary persona — no standing to check.
        return False

    return NPCStanding.objects.filter(
        persona=pc_persona,
        npc_persona_id=opponent.persona_id,
        affection__gte=PARLEY_DISPOSITION_FLOOR,
    ).exists()


def declare_parley(
    participant: CombatParticipant,
    opponent: CombatOpponent,
) -> CombatRoundAction:
    """Declare a parley maneuver — talk a foe down mid-fight, auto-ready (#2015).

    PARLEY is gated (see ``_parley_gate_met``): the opponent must be faltering/
    broken or the participant must hold sufficient standing. At round-tick it
    rolls a charm/Persuasion(Seduction) check against the target's Composure; on
    success it routes through ``apply_social_disposition_delta`` and, on a
    decisive success, calms the opponent (Calm condition → NEUTRAL allegiance).
    This function only records the declaration.
    """
    from world.combat.berserk_compulsion import reject_if_berserk  # noqa: PLC0415
    from world.vitals.services import is_dead  # noqa: PLC0415

    reject_if_berserk(participant, "parley")
    encounter = participant.encounter
    if encounter.status != RoundStatus.DECLARING:
        msg = (
            f"Cannot parley: encounter status is "
            f"'{encounter.get_status_display()}', expected 'Declaring'."
        )
        raise ValueError(msg)

    if participant.status != ParticipantStatus.ACTIVE:
        msg = "Cannot parley: participant is no longer active in this encounter."
        raise ValueError(msg)

    if is_dead(participant.character_sheet):
        msg = "Cannot parley: character is dead."
        raise ValueError(msg)

    if opponent.encounter_id != encounter.pk or opponent.status != OpponentStatus.ACTIVE:
        msg = "Parley target must be an active opponent in this encounter."
        raise ValueError(msg)

    if not _parley_gate_met(participant, opponent):
        msg = (
            "Cannot parley: the opponent's nerve is steady and you hold no "
            "standing with them. Break their resolve first, or build rapport."
        )
        raise ValueError(msg)

    action, _ = CombatRoundAction.objects.update_or_create(
        participant=participant,
        round_number=encounter.round_number,
        defaults={
            "focused_action": None,
            "focused_category": None,
            "effort_level": EffortLevel.MEDIUM,
            "focused_opponent_target": opponent,
            "focused_ally_target": None,
            "maneuver": CombatManeuver.PARLEY,
            "physical_passive": None,
            "social_passive": None,
            "mental_passive": None,
            "combo_upgrade": None,
            "is_ready": True,
        },
    )
    return action


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


def spawn_from_creature_template(
    encounter: CombatEncounter,
    template: CreatureTemplate,
    *,
    position: Position | None = None,
    acting_account: AccountDB | None = None,
) -> CombatOpponent:
    """Spawn a CombatOpponent from a CreatureTemplate bestiary entry (#2016).

    Thin wrapper over add_opponent. Clones CreaturePhaseTemplate rows into
    BossPhase rows on the spawned opponent if present. Stamps break-bar
    config and vulnerability fields from BreakBarConfig.
    """
    from world.combat.models import CreaturePhaseTemplate  # noqa: PLC0415

    has_authored_phases = CreaturePhaseTemplate.objects.filter(creature_template=template).exists()

    opp = _svc.add_opponent(
        encounter,
        name=template.name,
        tier=template.tier,
        threat_pool=template.threat_pool,
        soak_value=template.soak_override,
        probing_threshold=template.probing_override,
        auto_phases=not has_authored_phases,
        position=position,
        acting_account=acting_account,
    )
    opp.creature_template = template
    opp.save(update_fields=["creature_template"])

    if has_authored_phases:
        _clone_authored_phases(encounter, opp, template)

    return opp


def _clone_authored_phases(
    encounter: CombatEncounter,
    opp: CombatOpponent,
    template: CreatureTemplate,
) -> None:
    """Clone CreaturePhaseTemplate rows into BossPhase rows and stamp break-bar config."""
    from world.combat.models import CreaturePhaseTemplate  # noqa: PLC0415
    from world.combat.scaling import (  # noqa: PLC0415
        compute_party_multiplier,
        compute_party_profile,
    )

    phase_templates = CreaturePhaseTemplate.objects.filter(creature_template=template).order_by(
        "phase_number"
    )
    BossPhase.objects.filter(opponent=opp).delete()

    profile = compute_party_profile(encounter)
    party_mult = compute_party_multiplier(profile.party_size, profile.avg_level)

    for pt in phase_templates:
        phase = BossPhase.objects.create(
            opponent=opp,
            phase_number=pt.phase_number,
            threat_pool=pt.threat_pool,
            soak_value=pt.soak_value,
            probing_threshold=pt.probing_threshold,
            health_trigger_percentage=pt.health_trigger_percentage,
            description=pt.description,
            actions_per_round=pt.actions_per_round,
            damage_multiplier=pt.damage_multiplier,
            extra_actions=pt.extra_actions,
            reinforcement_template=pt.reinforcement_template,
            reinforcement_count=pt.reinforcement_count,
        )
        if hasattr(pt, "break_bar"):
            _stamp_phase_break_bar_config(phase, pt.break_bar, party_mult, opp, pt.phase_number)


def minimum_break_bar_threshold() -> int:
    """Pacing floor for a boss's break-bar threshold (#2642, batch-3 F-7a).

    ``(soulfray_stage_count + PACING_FLOOR_ROUND_PADDING) * BAR_UNITS_PER_ROUND`` —
    ensures the anima -> Soulfray -> audere arc has room to play out before the
    wall breaks (median 6-8 rounds, tail ~10). Returns 0 (no clamp) when Soulfray
    has not been authored yet (stage_count == 0) — a bare/test DB should not be
    forced onto a floor derived from unauthored content.
    """
    from world.conditions.models import ConditionStage  # noqa: PLC0415
    from world.magic.audere import SOULFRAY_CONDITION_NAME  # noqa: PLC0415

    stage_count = ConditionStage.objects.filter(condition__name=SOULFRAY_CONDITION_NAME).count()
    if stage_count == 0:
        return 0
    return (stage_count + PACING_FLOOR_ROUND_PADDING) * BAR_UNITS_PER_ROUND


def _stamp_phase_break_bar_config(
    phase: BossPhase,
    config: object,
    party_mult: Decimal,
    opp: CombatOpponent,
    phase_number: int,
) -> None:
    """Stamp BreakBarConfig values onto a BossPhase (and onto the opponent for phase 1)."""
    authored_threshold = round(Decimal(config.max_threshold) * party_mult)
    threshold = max(authored_threshold, minimum_break_bar_threshold())
    phase.break_bar_threshold = threshold
    phase.vulnerability_rounds = config.vulnerability_rounds
    phase.vulnerability_intensity_bonus = config.intensity_bonus
    phase.save(
        update_fields=[
            "break_bar_threshold",
            "vulnerability_rounds",
            "vulnerability_intensity_bonus",
        ]
    )
    if phase_number == 1:
        opp.break_bar_threshold = threshold
        opp.break_bar_current = threshold
        opp.vulnerability_rounds = config.vulnerability_rounds
        opp.vulnerability_intensity_bonus = config.intensity_bonus
        opp.save(
            update_fields=[
                "break_bar_threshold",
                "break_bar_current",
                "vulnerability_rounds",
                "vulnerability_intensity_bonus",
            ]
        )


def _bulk_primary_levels(char_ids: list[int]) -> dict[int, int]:
    """Return {character_id: level} for each id in *char_ids* using at most two queries.

    Mirrors the fallback chain in ``get_character_path_level``:
    primary row → highest row → 1.  Characters with no CharacterClassLevel at
    all are omitted from the dict (callers use ``.get(cid, 1)`` for the final
    fallback).
    """
    from world.classes.models import CharacterClassLevel  # noqa: PLC0415

    level_map: dict[int, int] = dict(
        CharacterClassLevel.objects.filter(
            character_id__in=char_ids,
            is_primary=True,
        ).values_list("character_id", "level")
    )

    without_primary = [cid for cid in char_ids if cid not in level_map]
    if without_primary:
        seen: set[int] = set()
        for char_id, lvl in (
            CharacterClassLevel.objects.filter(character_id__in=without_primary)
            .order_by("character_id", "-level")
            .values_list("character_id", "level")
        ):
            if char_id not in seen:
                level_map[char_id] = lvl
                seen.add(char_id)
    return level_map


def _dissolve_graduated_bonds(enc: CombatEncounter) -> None:
    """Dissolve any MentorBond that has graduated for ACTIVE participants in *enc*.

    A bond is "graduated" when the adjusted party's raw primary level is now
    within the covenant band — the bond is mechanically inactive and should be
    persisted as dissolved so future reads skip it cleanly.

    Write-safe: called only from ``begin_declaration_phase`` (encounter start).
    No per-bond queries: bulk-fetches bonds in one query, resolves primary levels
    for all adjusted-party characters in a second bulk query, then determines
    graduation inline — O(1) queries regardless of graduated-bond count.
    """
    from world.covenants.constants import MentorBondAdjusted  # noqa: PLC0415
    from world.covenants.mentorship import dissolve_mentor_bond, is_in_band  # noqa: PLC0415
    from world.covenants.models import MentorBond  # noqa: PLC0415

    sheet_ids = list(
        CombatParticipant.objects.filter(
            encounter=enc,
            status=ParticipantStatus.ACTIVE,
        ).values_list("character_sheet_id", flat=True)
    )
    if not sheet_ids:
        return

    # One bulk query: all active bonds where any participant is either the
    # mentor or the sidekick side. Resolve covenant + both character FKs so
    # no per-bond queries are needed below.
    active_bonds = list(
        MentorBond.objects.active()
        .filter(Q(mentor_sheet_id__in=sheet_ids) | Q(sidekick_sheet_id__in=sheet_ids))
        .select_related(
            "covenant",
            "mentor_sheet__character",
            "sidekick_sheet__character",
        )
    )
    if not active_bonds:
        return

    # Collect the adjusted-party character id for each bond (one id per bond).
    adjusted_char_ids = [
        bond.sidekick_sheet.character_id
        if bond.adjusted_party == MentorBondAdjusted.SIDEKICK
        else bond.mentor_sheet.character_id
        for bond in active_bonds
    ]

    # Two bulk queries at most: primary levels + highest-level fallback.
    level_map = _bulk_primary_levels(adjusted_char_ids)

    for bond, char_id in zip(active_bonds, adjusted_char_ids, strict=True):
        raw = level_map.get(char_id, 1)
        if is_in_band(bond.covenant, raw):
            dissolve_mentor_bond(bond)


def expire_pulls_for_round(encounter: CombatEncounter) -> None:
    """Delete all CombatPull rows from prior rounds and recompute affected max_health.

    Spec A §3.8 lines 1057–1078 + §7.4 lines 2031–2039. Called from
    ``begin_declaration_phase`` immediately after ``round_number`` advances.

    - Collects distinct ``participant_id``s whose pulls are about to expire.
    - Cascade-deletes the stale ``CombatPull`` rows (the FK cascade drops
      their ``CombatPullResolvedEffect`` children).
    - Invalidates each affected participant's ``CharacterCombatPullHandler``
      cache so the next read of ``combat_pulls.active_pull_vital_bonuses``
      reflects the deletion.
    - Calls ``recompute_max_health_with_threads`` per participant so any
      expiring MAX_HEALTH pull goes away via the clamp-not-injure path in
      ``vitals.recompute_max_health`` — characters are never *injured* by
      a pull expiring, only un-bolstered.

    Side-effect-free for participants with no active pulls this encounter.
    """
    from world.combat.models import CombatPull  # noqa: PLC0415
    from world.magic.services import (  # noqa: PLC0415
        recompute_max_health_with_threads,
    )

    stale_pulls = CombatPull.objects.filter(
        encounter=encounter,
        round_number__lt=encounter.round_number,
    )
    affected_participant_ids = list(stale_pulls.values_list("participant_id", flat=True).distinct())
    if not affected_participant_ids:
        return

    stale_pulls.delete()

    # Re-fetch participants so we can walk to character_sheet.character —
    # SharedMemoryModel returns the identity-mapped instances, so this is
    # zero-query once the participants have been loaded in the request.
    participants = CombatParticipant.objects.filter(
        pk__in=affected_participant_ids,
    ).select_related("character_sheet__character")
    for p in participants:
        p.character_sheet.character.combat_pulls.invalidate()
        recompute_max_health_with_threads(p.character_sheet)
