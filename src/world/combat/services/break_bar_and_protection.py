"""Clash resolution, boss break-bar assessment, strain and clash config, armor soak and cover."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterator
from typing import TYPE_CHECKING

from django.db import transaction

from world.combat.constants import (
    ENTITY_TYPE_PC,
    BreakContributionKind,
    EngagementLockStatus,
    OpponentStatus,
    OpponentTier,
    StrikeDelivery,
)
from world.combat.models import (
    BreakBarContribution,
    Clash,
    ClashContributionDeclaration,
    CombatEncounter,
    CombatOpponent,
    CombatOpponentAction,
    CombatParticipant,
    EngagementLock,
)
from world.combat.services.reactive_and_upkeep import (
    _boss_new_debuff_events,
    _has_active_behavior_altering_condition,
    _newly_suppressed_lieutenants,
    _outcome_damaged_boss,
    _pc_lock_hold_contributors,
    _persist_break_bar_events,
    _record_story_break_recognition,
)
from world.combat.types import ActionOutcome, ClashRoundResult, PreparedClashContribution

if TYPE_CHECKING:
    from typeclasses.characters import Character
    from world.areas.positioning.models import RampartElementProfile
    from world.character_sheets.models import CharacterSheet
    from world.combat.models import ClashConfig, StrainConfig
    from world.conditions.models import DamageType
    from world.items.models import ItemInstance
    from world.magic.models import Technique


def _resolve_clashes(
    encounter: CombatEncounter,
    round_number: int,
    resolution_order: list[tuple[str, CombatParticipant | CombatOpponent]],  # noqa: ARG001
) -> list[ClashRoundResult]:
    """Post-pass: detect clash opportunities, then drive one round per active Clash.

    Called after all combat-action resolution for the round.  Two phases:

    1. **Opportunity detection** — ``detect_clash_opportunities`` inspects the
       round's declared PC + NPC actions and creates ``Clash`` rows for newly-
       emerged opportunities.  Newly-created clashes participate in the same
       round's post-pass so that the first round of a clash is resolved
       immediately.

    2. **Per-clash round driver** — for each ACTIVE Clash (including any just
       created in step 1), gather the PC's ``ClashContributionDeclaration`` rows,
       build ``PreparedClashContribution`` objects, and call ``run_clash_round``.
       Clashes are iterated in ``Clash.pk`` order for deterministic resolution.

       TODO(Phase 5 / initiative ordering): order PC-initiated clashes by the
       initiating participant's initiative slot, mirroring how
       ``_resolve_declared_challenges`` follows ``resolution_order``.  NPC-initiated
       clashes (WARD, LOCK/ESCAPING) don't have a PC initiator in the same sense;
       they can resolve at a fixed NPC slot or after all PC-initiated clashes.
       For v1, pk order is sufficient and deterministic.

    3. **Declaration cleanup** — all ``ClashContributionDeclaration`` rows for
       this round are deleted atomically after all clashes are processed, inside
       the caller's ``@transaction.atomic`` block.

    ``npc_attack_affinity`` is resolved at post-pass time from
    ``clash.triggering_threat_entry``.  ``ThreatPoolEntry`` has no affinity field
    (confirmed in Task 5.3 investigation) — ``npc_attack_affinity`` is always
    ``None`` in v1, so ``affinity_tilt`` always returns 0.  When a future task
    adds an affinity field to ``ThreatPoolEntry``, update this function to read it.

    Runs inside the outer ``@transaction.atomic`` on ``resolve_round`` — no
    separate ``@transaction.atomic`` decorator is needed here.

    Args:
        encounter: The active ``CombatEncounter`` being resolved.
        round_number: The current encounter round number (1-indexed).
        resolution_order: PC/NPC action resolution order (reserved for future
            initiative-based clash ordering; unused in v1).

    Returns:
        A list of ``ClashRoundResult`` objects, one per Clash that was driven
        this round.  May be empty when no Clashes are active.
    """
    from world.combat.clash import (  # noqa: PLC0415
        detect_clash_opportunities,
        run_clash_round,
    )
    from world.combat.constants import ClashStatus  # noqa: PLC0415

    # 1. Detect new opportunities this round (creates Clash rows).
    detect_clash_opportunities(encounter=encounter, round_number=round_number)

    # 2. Find all ACTIVE clashes (includes any just created in step 1).
    # TODO(Phase 5 / initiative ordering): order by initiating participant's
    # initiative slot instead of pk for PC-initiated clashes.
    active_clashes = list(
        Clash.objects.filter(
            encounter=encounter,
            status=ClashStatus.ACTIVE,
        ).select_related("npc_opponent", "triggering_threat_entry")
    )

    if not active_clashes:
        return []

    # 3. Gather all declarations for this round and group by clash_id.
    declarations = list(
        ClashContributionDeclaration.objects.filter(
            encounter=encounter,
            round_number=round_number,
        ).select_related(
            "clash",
            "participant__character_sheet",
            "technique",
            "technique__action_template",
        )
    )
    decls_by_clash: dict[int, list[ClashContributionDeclaration]] = defaultdict(list)
    for decl in declarations:
        decls_by_clash[decl.clash_id].append(decl)

    # 4. Load configs once (singleton reads; SharedMemoryModel caches them).
    # get_clash_config / get_strain_config are defined later in this module;
    # Python resolves names at call time so the forward reference is fine.
    config_clash = get_clash_config()
    config_strain = get_strain_config()

    # 5. Drive one round per active clash.
    outcomes: list[ClashRoundResult] = []
    for clash in active_clashes:
        clash_decls = decls_by_clash.get(clash.pk, [])

        # Build PreparedClashContribution objects for this clash's declarations.
        # npc_attack_affinity: ThreatPoolEntry has no affinity field in v1 — pass None.
        # When a future task adds an affinity field, read it here from
        # clash.triggering_threat_entry.
        pc_contributions: list[PreparedClashContribution] = [
            PreparedClashContribution(
                character_sheet=decl.participant.character_sheet,
                action_slot=decl.action_slot,
                technique=decl.technique,
                strain_commitment=decl.strain_commitment,
                npc_attack_affinity=None,  # ThreatPoolEntry has no affinity field in v1
            )
            for decl in clash_decls
        ]

        result = run_clash_round(
            clash=clash,
            round_number=round_number,
            pc_contributions=pc_contributions,
            config_clash=config_clash,
            config_strain=config_strain,
        )
        outcomes.append(result)

        # When the clash resolved this round, broadcast a durable, Narrator-
        # authored OUTCOME line for the break/lock/ward result (#644). Mirrors
        # the per-action broadcast in _resolve_pc_action.
        if result.resolution is not None:
            from world.combat.interaction_services import (  # noqa: PLC0415
                broadcast_action_outcome,
                render_clash_outcome_narration,
            )

            opponent_label = clash.npc_opponent.name if clash.npc_opponent_id else "?"
            consequence = result.resolution.consequence_applied
            narration = render_clash_outcome_narration(
                flavor_label=clash.get_flavor_display(),
                opponent_label=opponent_label,
                resolution_tier=result.resolution.resolution,
                consequence_label=consequence.label if consequence is not None else None,
            )
            broadcast_action_outcome(encounter=encounter, narration=narration)

    # 6. Delete all declarations for this round (inside caller's atomic block).
    ClashContributionDeclaration.objects.filter(
        encounter=encounter,
        round_number=round_number,
    ).delete()

    return outcomes


def assess_break_bar(
    encounter: CombatEncounter,
    action_outcomes: list[ActionOutcome],
) -> None:
    """Assess break-bar depletion for all boss opponents with a break bar (#2642).

    Diversity-weighted, not per-hit: five feeds (DAMAGE / COMBO / HOLD / DEBUFF /
    SUPPRESSION — ``BreakContributionKind``) are each persisted as a
    ``BreakBarContribution`` row. Depletion sums 1 unit per distinct (actor, kind)
    pair this round, doubled for a pair's first-ever (kind, effect_type)
    occurrence in the encounter, plus the landed combo's flat ``bonus_damage``.
    The result is divided by ``1 + active_unsuppressed_reinforcers`` (the
    lieutenant gate) — floored at 1 unit whenever any depletion occurred, never
    a hard block. When the bar reaches 0, the vulnerability window opens and a
    break celebration broadcasts, naming every distinct contributor.

    Called from resolve_round's post-pass, AFTER the clash post-pass resolves
    this round's clashes (so the HOLD feed can see a LOCK-clash win that
    resolved this same round).

    When the bar reaches 0 a BOSS_BREAK dramatic surge also fires for every
    ACTIVE PC (#3445), once per boss per phase - the re-break loop does not
    repeat it.
    """
    round_number = encounter.round_number
    bosses = list(
        CombatOpponent.objects.filter(
            encounter=encounter,
            status=OpponentStatus.ACTIVE,
            tier=OpponentTier.BOSS,
            break_bar_threshold__gt=0,
            vulnerability_rounds_remaining=0,
        )
    )
    if not bosses:
        return

    for boss in bosses:
        _assess_boss_break_bar(encounter, boss, round_number, action_outcomes)


def _assess_boss_break_bar(
    encounter: CombatEncounter,
    boss: CombatOpponent,
    round_number: int,
    action_outcomes: list[ActionOutcome],
) -> None:
    """Assess and apply one boss's break-bar depletion for this round (#2642)."""
    events, combo_bonus = _break_bar_events_this_round(
        encounter, boss, round_number, action_outcomes
    )
    if not events and combo_bonus <= 0:
        return

    raw_depletion = _persist_break_bar_events(boss, round_number, events) + combo_bonus
    if raw_depletion <= 0:
        return

    active_reinforcers = _active_reinforcer_count(boss, round_number)
    # Proportional gate — floor at 1 unit whenever depletion occurred; never a
    # hard block (#2642).
    bar_damage = max(raw_depletion // (1 + active_reinforcers), 1)

    boss.break_bar_current = max(0, boss.break_bar_current - bar_damage)
    broke_this_round = boss.break_bar_current == 0
    if broke_this_round:
        boss.vulnerability_rounds_remaining = boss.vulnerability_rounds
    boss.save(update_fields=["break_bar_current", "vulnerability_rounds_remaining"])
    if broke_this_round:
        _broadcast_break_celebration(encounter, boss)
        _record_story_break_recognition(encounter, boss, round_number)
        from world.combat.escalation import apply_boss_break_surge  # noqa: PLC0415

        apply_boss_break_surge(opponent=boss)


def _break_bar_events_this_round(
    encounter: CombatEncounter,
    boss: CombatOpponent,
    round_number: int,
    action_outcomes: list[ActionOutcome],
) -> tuple[list[tuple[str, int | None, int | None]], int]:
    """Gather this round's break-bar feed events for *boss*.

    Returns ``(events, combo_bonus)`` where each event is
    ``(kind, participant_id, effect_type_id)`` — one per qualifying feed,
    persisted 1:1 as a ``BreakBarContribution`` row by the caller. Combo's flat
    ``bonus_damage`` depletion is returned separately (additive, not part of
    the diversity-unit pool).
    """
    events: list[tuple[str, int | None, int | None]] = []
    combo_bonus = 0

    # Combo path: first landed combo this round (unchanged bonus_damage depletion,
    # plus its own COMBO diversity-unit contribution).
    for outcome in action_outcomes:
        if outcome.combo_used is not None and _outcome_damaged_boss(outcome, boss.pk):
            combo_bonus = outcome.combo_used.bonus_damage
            events.append(
                (BreakContributionKind.COMBO, outcome.participant_id, outcome.effect_type_id)
            )
            break

    # DAMAGE feed: every qualifying PC damage outcome this round.
    events.extend(
        (BreakContributionKind.DAMAGE, outcome.participant_id, outcome.effect_type_id)
        for outcome in action_outcomes
        if (
            outcome.entity_type == ENTITY_TYPE_PC
            and outcome.participant_id is not None
            and outcome.effect_type_id is not None
            and _outcome_damaged_boss(outcome, boss.pk)
        )
    )

    # HOLD feed: PC-side LOCK-clash win against this boss, resolved this round.
    events.extend(
        (BreakContributionKind.HOLD, participant_id, None)
        for participant_id in _pc_lock_hold_contributors(encounter, boss, round_number)
    )

    round_started_at = encounter.round_started_at

    # DEBUFF feed: new behavior-altering condition landed on the boss this round.
    events.extend(
        (BreakContributionKind.DEBUFF, participant_id, None)
        for participant_id in _boss_new_debuff_events(boss, encounter, round_started_at)
    )

    # SUPPRESSION feed: a reinforcing lieutenant became suppressed this round.
    events.extend(
        (BreakContributionKind.SUPPRESSION, participant_id, None)
        for _lieutenant, participant_id in _newly_suppressed_lieutenants(
            encounter, boss, round_number, round_started_at
        )
    )

    return events, combo_bonus


def _active_reinforcer_count(boss: CombatOpponent, round_number: int) -> int:
    """Count *boss*'s active, unsuppressed, acting lieutenants this round (the gate divisor, #2642).

    Active = ``OpponentStatus.ACTIVE``, morale not BREAK, no behavior-altering
    condition on the lieutenant's ObjectDB, not pinned in an ACTIVE
    ``EngagementLock``, and it acted this round (has a ``CombatOpponentAction``
    row). A parked/idle lieutenant does not gate.
    """
    from world.combat.morale import OpponentMoraleState, morale_state_for  # noqa: PLC0415

    lieutenants = list(CombatOpponent.objects.filter(reinforces=boss, status=OpponentStatus.ACTIVE))
    if not lieutenants:
        return 0

    acted_ids = set(
        CombatOpponentAction.objects.filter(
            opponent__in=lieutenants,
            round_number=round_number,
        ).values_list("opponent_id", flat=True)
    )

    count = 0
    for lieutenant in lieutenants:
        if lieutenant.pk not in acted_ids:
            continue
        if morale_state_for(lieutenant) == OpponentMoraleState.BREAK:
            continue
        if lieutenant.objectdb_id is not None and _has_active_behavior_altering_condition(
            lieutenant.objectdb_id
        ):
            continue
        if EngagementLock.objects.filter(
            opponent=lieutenant, status=EngagementLockStatus.ACTIVE
        ).exists():
            continue
        count += 1
    return count


def _broadcast_break_celebration(encounter: CombatEncounter, boss: CombatOpponent) -> None:
    """Broadcast the break moment naming every distinct contributor this encounter (#2642).

    Mirrors ``render_combo_finisher_narration``'s contributor-naming style.
    Broadcasts on both channels — the persisted-interaction/WS payload (web)
    and ``room.msg_contents`` (telnet parity) — since a boss wall breaking is
    exactly the kind of PLAY moment that needs telnet parity.
    """
    from world.combat.interaction_services import (  # noqa: PLC0415
        broadcast_action_outcome,
        join_labels,
    )

    contributor_labels = _break_bar_contributor_labels(boss)
    if not contributor_labels:
        return

    names = join_labels(contributor_labels)
    narration = f"{boss.name}'s wall breaks — {names} broke through!"
    broadcast_action_outcome(encounter=encounter, narration=narration)
    room = encounter.room
    if room is not None:
        room.msg_contents(narration)


def _break_bar_contributor_labels(boss: CombatOpponent) -> list[str]:
    """Distinct PC labels credited on any ``BreakBarContribution`` row for *boss* this encounter."""
    from world.scenes.services import persona_names_for_sheets  # noqa: PLC0415

    participant_ids = (
        BreakBarContribution.objects.filter(opponent=boss, participant__isnull=False)
        .values_list("participant_id", flat=True)
        .distinct()
    )
    participants = list(
        CombatParticipant.objects.filter(pk__in=participant_ids).select_related(
            "character_sheet__character"
        )
    )
    # Persona display name, not str(CombatParticipant) -> str(CharacterSheet)
    # ("Sheet for {key}") -- #4091 fix round 3.
    persona_names = persona_names_for_sheets(p.character_sheet_id for p in participants)
    return [
        persona_names.get(p.character_sheet_id, p.character_sheet.character.key)
        for p in participants
    ]


# ---------------------------------------------------------------------------
# Clash tuning singleton accessors
# ---------------------------------------------------------------------------


def get_strain_config() -> StrainConfig:
    """Get-or-create the StrainConfig singleton (pk=1)."""
    from world.combat.models import (  # noqa: PLC0415
        StrainConfig,
    )

    cfg = StrainConfig.objects.cached_singleton()
    if cfg is None:
        cfg, _ = StrainConfig.objects.get_or_create(pk=1)
    return cfg


def get_clash_config() -> ClashConfig:
    """Get-or-create the ClashConfig singleton (pk=1)."""
    from world.combat.models import (  # noqa: PLC0415
        ClashConfig,
    )

    cfg = ClashConfig.objects.cached_singleton()
    if cfg is None:
        cfg, _ = ClashConfig.objects.get_or_create(pk=1)
    return cfg


# ---------------------------------------------------------------------------
# Player-facing clash contribution declaration (Task 7.1a)
# ---------------------------------------------------------------------------


@transaction.atomic
def declare_clash_contribution(
    *,
    participant: CombatParticipant,
    clash: Clash,
    action_slot: str,
    technique: Technique,
    strain_commitment: int,
) -> ClashContributionDeclaration:
    """Write (or overwrite) a PC's clash contribution declaration for the current round.

    Performs the atomic write.  All user-input validation lives in
    ``DeclareClashContributionSerializer`` — this function trusts its inputs and
    performs only defensive programmer-error assertions.

    The declaration is keyed on ``(encounter, round_number, participant, clash)``.
    Calling a second time in the same round replaces the prior declaration
    (idempotent re-declaration).

    Args:
        participant: The PC participant making the contribution.
        clash: The active ``Clash`` the contribution targets.
        action_slot: ``ClashActionSlot`` value (FOCUSED or PASSIVE).
        technique: The ``Technique`` the PC commits to the clash.
        strain_commitment: Extra anima committed on top of the technique cost floor.

    Returns:
        The created-or-updated ``ClashContributionDeclaration`` instance.

    Raises:
        ValueError: If ``clash.encounter`` does not match ``participant.encounter``
            (programmer error — the serializer enforces this for user input).
    """
    round_number = participant.encounter.round_number

    # Defensive assertion: catches programmer errors where the wrong clash or
    # participant is passed (the serializer already validates this for user input).
    if clash.encounter_id != participant.encounter_id:
        msg = (
            f"declare_clash_contribution: clash.encounter_id ({clash.encounter_id}) "
            f"does not match participant.encounter_id ({participant.encounter_id}). "
            "This is a programmer error — pass clashes and participants from the same encounter."
        )
        raise ValueError(msg)

    declaration, _ = ClashContributionDeclaration.objects.update_or_create(
        encounter=participant.encounter,
        round_number=round_number,
        participant=participant,
        clash=clash,
        defaults={
            "action_slot": action_slot,
            "technique": technique,
            "strain_commitment": strain_commitment,
        },
    )
    return declaration


# ---------------------------------------------------------------------------
# Equipped-gear combat contribution helpers (#508, Task 7)
# ---------------------------------------------------------------------------
#
# Pure read helpers over ``character.equipped_items`` (the iterable
# CharacterEquipmentHandler, whose rows arrive with item_instance + template +
# quality_tier select_related, so reading effective_* during iteration is
# query-free). They do NOT mutate combat damage logic — that wiring is Tasks
# 8/9. ``_select_equipped_weapon`` is kept separate so the weapon-durability
# decrement task can reuse the same selection.


def _combat_target_bonus(sheet: object, target_name: str, level_override: int | None = None) -> int:
    """get_modifier_total for a named combat ModifierTarget; 0 if the row isn't seeded.

    Combat never hard-depends on seed order (mirrors covenant_level_bonus's
    config-is-None → 0). The target's stat category routes the covenant-role
    equipment walk into the total.

    When ``level_override`` is not supplied, computes the bond-adjusted level via
    ``bond_adjusted_level(sheet)`` (#1165). An unbonded sheet returns None, which
    falls through to ``sheet.current_level`` inside ``covenant_role_bonus`` — zero
    query overhead for the common (non-bonded) case because bond_adjusted_level
    returns None after the fast active-bond check.

    When ``level_override`` is supplied explicitly (e.g. caller already computed
    it), that value is passed directly without a redundant bond lookup.
    """
    from typing import cast  # noqa: PLC0415

    from world.covenants.mentorship import bond_adjusted_level  # noqa: PLC0415
    from world.mechanics.models import ModifierTarget  # noqa: PLC0415
    from world.mechanics.services import get_modifier_total  # noqa: PLC0415

    try:
        target = ModifierTarget.objects.get(name=target_name)
    except ModifierTarget.DoesNotExist:
        return 0
    sheet_typed = cast("CharacterSheet", sheet)
    override = level_override if level_override is not None else bond_adjusted_level(sheet_typed)
    return get_modifier_total(sheet, target, level_override=override)


def _equipped_armor_soak_pieces(
    character: Character,
) -> Iterator[tuple[ItemInstance, int]]:
    """Yield (item_instance, soak) for each worn armor piece with positive soak."""
    from world.items.constants import ARMOR_ARCHETYPES  # noqa: PLC0415

    for equipped in list(character.equipped_items):
        inst = equipped.item_instance
        if inst.template.gear_archetype in ARMOR_ARCHETYPES:
            soak = inst.effective_armor_soak
            if soak > 0:
                yield inst, soak


def effective_soak_from_armor(character: Character) -> int:
    """Sum effective armor soak across the character's equipped armor pieces."""
    return sum(soak for _, soak in _equipped_armor_soak_pieces(character))


def _resonant_armor_soak(character: Character) -> int:
    """The character's un-blended resonant armor-soak pool (#1174).

    eager CharacterModifier total + equipment_walk_total_unblended for the armor_soak
    target. 0 when the sheet or the seeded target row is absent (combat never hard-depends
    on seed order). This is the pool the incompatible-armor ``max`` competes against.
    """
    from world.items.constants import ARMOR_SOAK_TARGET_NAME  # noqa: PLC0415
    from world.mechanics.models import ModifierTarget  # noqa: PLC0415
    from world.mechanics.services import (  # noqa: PLC0415
        equipment_walk_total_unblended,
        get_modifier_breakdown,
    )

    sheet = character.character_sheet
    if sheet is None:
        return 0
    try:
        target = ModifierTarget.objects.get(name=ARMOR_SOAK_TARGET_NAME)
    except ModifierTarget.DoesNotExist:
        return 0
    eager = get_modifier_breakdown(sheet, target).total
    return eager + equipment_walk_total_unblended(sheet, target)


def _split_armor_soak_by_compatibility(
    character: Character,
) -> tuple[int, int, list[ItemInstance], list[ItemInstance]]:
    """Split worn armor's effective soak into role-compatible vs incompatible buckets (#1174).

    A piece is compatible when ANY engaged PRIMARY covenant role is gear-compatible with
    its archetype (existing GearArchetypeCompatibility). With no engaged primary role,
    all armor is incompatible (it then competes via ``max`` against a 0 resonant pool →
    armor-only). PRIMARY-only (#2641, Layer 3 — chassis): a secondary vow never widens
    gear compatibility.

    Returns ``(compat_soak, incompat_soak, compat_pieces, incompat_pieces)`` where the
    piece lists are the ItemInstances whose physical soak fell in each bucket (for
    durability wear).
    """
    from world.covenants.services import is_gear_compatible  # noqa: PLC0415

    engaged_roles = (
        character.covenant_roles.currently_engaged_primary_roles()
        if hasattr(character, "covenant_roles")
        else []
    )
    compat_soak = incompat_soak = 0
    compat_pieces: list[ItemInstance] = []
    incompat_pieces: list[ItemInstance] = []
    for inst, soak in _equipped_armor_soak_pieces(character):
        archetype = inst.template.gear_archetype
        if any(is_gear_compatible(role, archetype) for role in engaged_roles):
            compat_soak += soak
            compat_pieces.append(inst)
        else:
            incompat_soak += soak
            incompat_pieces.append(inst)
    return compat_soak, incompat_soak, compat_pieces, incompat_pieces


def apply_equipped_armor_soak(character: Character, damage: int) -> int:
    """Reduce ``damage`` by role-gated equipped-armor soak (#1174, #2533).

    Worn armor is split by covenant-role compatibility. Compatible soak is then scaled
    by ``gear_additive_fraction`` (#2533) — the character's engaged defense profile(s)
    dial how much of their COMPATIBLE armor stays additive with their vow's own
    defense; 1 (no profile, or every engaged profile at the default 10 tenths) is the
    legacy fully-additive behavior. The resonant soak pool (covenant role base + facet
    + mantle + motif + covenant-level, un-blended) then competes with *incompatible*
    armor via ``max``; the (possibly scaled) compatible armor adds on top:

        compat_soak = int(compat_soak * gear_additive_fraction(character))
        soak = compat_soak + max(incompat_physical, resonant)

    Because ``resonant`` scales on character level and physical armor does not, a role
    incompatible with heavy armor sees its resonant protection overtake platemail past
    low levels. Durability wears only on armor whose physical soak contributes to the
    result (all compatible pieces, regardless of the scaled soak's magnitude; incompatible
    pieces only when they win the ``max`` — unchanged by the #2533 fraction). Returns
    post-soak damage, floored at 0.
    """
    if damage <= 0:
        return damage

    from world.covenants.services import gear_additive_fraction  # noqa: PLC0415
    from world.items.services.durability import decrement_item_durability  # noqa: PLC0415

    compat_soak, incompat_soak, compat_pieces, incompat_pieces = _split_armor_soak_by_compatibility(
        character
    )
    compat_soak = int(compat_soak * gear_additive_fraction(character))
    resonant = _resonant_armor_soak(character)

    incompatible_wins = incompat_soak >= resonant
    soak = compat_soak + (incompat_soak if incompatible_wins else resonant)
    if soak <= 0:
        return damage

    # Wear only armor whose physical soak actually contributed.
    contributors = list(compat_pieces)
    if incompatible_wins:
        contributors += incompat_pieces
    for inst in contributors:
        decrement_item_durability(item_instance=inst)

    return max(0, damage - soak)


def apply_position_cover(character: Character, damage: int, damage_type: DamageType | None) -> int:
    """Subtract attack-cover from damage.

    Reads the character's current position and sums PositionShelter rows with
    applies_to_attacks=True for the given damage type. No-op when the character
    is unpositioned (lenient — matching technique_can_reach) or when damage_type
    is None (untyped damage has no cover).

    Args:
        character: The target character taking damage.
        damage: The incoming damage amount (after armor soak, before condition interactions).
        damage_type: The damage type of the incoming attack (None = untyped, no cover).

    Returns:
        The damage after cover reduction, floored at 0.
    """
    if damage <= 0 or damage_type is None:
        return damage
    from world.areas.positioning.services import (  # noqa: PLC0415
        position_of,
        position_shelter_value,
    )

    position = position_of(character)
    if position is None:
        return damage
    cover = position_shelter_value(position, damage_type, attacks_only=True)
    return max(0, damage - cover)


def _rampart_resist(
    profile: RampartElementProfile,
    damage_type: DamageType | None,
    *,
    delivery: str,
    is_area: bool,
) -> int:
    """The resist term for one intercepted strike: base row + MISSILE_WARD adjustment."""
    from world.areas.positioning.constants import RampartSignature  # noqa: PLC0415

    resist = 0
    if damage_type is not None:
        resist = sum(
            profile.resistances.filter(damage_type=damage_type).values_list("value", flat=True)
        )
    if profile.signature_behavior == RampartSignature.MISSILE_WARD:
        if delivery == StrikeDelivery.MISSILE:
            resist += profile.signature_value
        if is_area:
            resist -= profile.signature_value
    return resist
