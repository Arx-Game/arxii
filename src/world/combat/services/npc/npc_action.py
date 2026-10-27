"""Resolving an NPC action against its target."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from world.combat import services as _svc
from world.combat.constants import ENTITY_TYPE_NPC, OpponentStatus, ParticipantStatus, TargetingMode
from world.combat.models import (
    CombatEncounter,
    CombatOpponent,
    CombatOpponentAction,
    CombatParticipant,
)
from world.combat.services.npc.area_attacks import cover_place
from world.combat.services.npc.npc_attack import resolve_npc_attack
from world.combat.services.npc.npc_movement import broadcast_cannot_reach, refit_targets
from world.combat.services.sent_flying.sent_flying import _trigger_sent_flying
from world.combat.types import ActionOutcome

if TYPE_CHECKING:
    from collections.abc import Callable

    from evennia.objects.models import ObjectDB

    from world.character_sheets.models import CharacterSheet
    from world.checks.models import CheckType
    from world.checks.types import CheckResult
    from world.conditions.models import ConditionTemplate
    from world.scenes.models import Interaction

    PerformCheckFn = Callable[..., CheckResult]


def _npc_action_target_label(
    label_targets: list[CombatParticipant] | list[CombatOpponent],
) -> str | None:
    """Join display labels for an NPC action's targets, batched (#4091 fix round 3).

    ``label_targets`` holds either PC ``CombatParticipant``s (the normal
    PC-facing path) or NPC ``CombatOpponent``s (the ALLY-summon/charmed-NPC
    opponent-target path) — never a mix. A PC target gets its persona name
    (never ``str(CombatParticipant)``'s ``"Sheet for {key}"``); an opponent
    target's ``.name`` was already correct.
    """
    if not label_targets:
        return None
    if isinstance(label_targets[0], CombatParticipant):
        from world.scenes.services import persona_names_for_sheets  # noqa: PLC0415

        persona_names = persona_names_for_sheets(p.character_sheet_id for p in label_targets)
        names = [
            persona_names.get(p.character_sheet_id, p.character_sheet.character.key)
            for p in label_targets
        ]
    else:
        names = [t.name for t in label_targets]
    return ", ".join(names)


def _resolve_npc_taunt_on_target(
    target_participant: CombatParticipant,
    *,
    opponent: CombatOpponent,
    potency: int,
) -> None:
    """An NPC taunt entry against one player character: they roll, the NPC does not (#4737).

    The entry only supplies ``potency``. The targeted player character rolls the tuned
    check (Taunt Received, Composure) against it, and the roll's degree picks the surge
    band. A quiet no-op with no escalation curve (ADR-0098) or no tuning authored, and
    when the target could not surge this round (no combat engagement, or already taunted
    this round): no roll is made, nothing is spent, nothing is printed.
    """
    from world.combat.constants import SurgeTriggerKind  # noqa: PLC0415
    from world.combat.surge_rolls import (  # noqa: PLC0415
        apply_rolled_surge,
        rolled_surge_possible,
        surge_roll_for_participant,
        surge_tuning_for,
    )

    encounter = opponent.encounter
    if encounter.escalation_curve is None:
        return
    tuning = surge_tuning_for(SurgeTriggerKind.TAUNT_RECEIVED)
    if tuning is None:
        return
    if not rolled_surge_possible(
        encounter, target_participant, SurgeTriggerKind.TAUNT_RECEIVED, None
    ):
        return
    result = surge_roll_for_participant(target_participant, tuning.check_type, potency)
    apply_rolled_surge(
        encounter=encounter,
        participant=target_participant,
        trigger_kind=SurgeTriggerKind.TAUNT_RECEIVED,
        outcome=result.outcome,
        potency=potency,
        subject_sheet=None,
        source_character=opponent.objectdb,
        tuning=tuning,
    )


def _npc_outgoing_damage(opponent: CombatOpponent, npc_action: CombatOpponentAction) -> int:
    """An undefended NPC hit's amount, after the attacker's damage-dealt rows (#4742)."""
    from world.conditions.services import scaled_outgoing_damage  # noqa: PLC0415

    return scaled_outgoing_damage(
        opponent.objectdb,
        int(npc_action.threat_entry.base_damage * npc_action.damage_scale),
        npc_action.threat_entry.damage_type,
    )


def _resolve_npc_action_on_target(  # noqa: PLR0913 - per-target resolution needs full context
    target_participant: CombatParticipant,
    *,
    opponent: CombatOpponent,
    npc_action: CombatOpponentAction,
    defense_check_type: CheckType | None,
    defense_check_fn: PerformCheckFn | None,
    conditions: list,
    outcome: ActionOutcome,
    condition_applications: list,
    get_npc_action_interaction: Callable[[], Interaction],
) -> None:
    """Resolve one NPC action against a single target, recording results in place.

    Skips escaped (non-ACTIVE) and dead targets. Applies damage (via a defense
    check when one is configured, else flat threat damage), runs the
    survivability pipeline, and queues any conditions for bulk apply by
    appending to ``outcome`` and ``condition_applications``.
    """
    from world.vitals.services import is_dead  # noqa: PLC0415

    # A successful escape protects for the rest of the round (#878). The
    # idmapper guarantees this is the same instance _resolve_flee just
    # mutated, so the status write is visible without a re-fetch.
    if target_participant.status != ParticipantStatus.ACTIVE:
        return

    # Damage recipients: any not-dead target is valid. Unconscious / dying
    # PCs still take damage (incapacitation/dying are conditions, not a gate
    # on damage application). Only the dead are excluded.
    if is_dead(target_participant.character_sheet):
        return

    # A taunt entry deals no damage and has no defense roll (#4737): the target rolls
    # against its potency instead.
    if npc_action.threat_entry.taunt_potency is not None:
        _resolve_npc_taunt_on_target(
            target_participant, opponent=opponent, potency=npc_action.threat_entry.taunt_potency
        )
        return

    # Survivability pipeline — knockout, death, wound checks.
    # coherence_cache_scope memoizes motif_coherence_bonus per (sheet, resonance)
    # so DR (inside apply_damage_to_participant / resolve_npc_attack) + the three
    # save baselines (inside process_damage_consequences) share one wardrobe walk (#1267).
    from world.magic.services import coherence_cache_scope  # noqa: PLC0415
    from world.vitals.services import process_damage_consequences  # noqa: PLC0415

    with coherence_cache_scope():
        if defense_check_type is not None:
            defense = resolve_npc_attack(
                npc_action,
                target_participant,
                defense_check_type,
                perform_check_fn=defense_check_fn,
            )
            dmg_result = defense.damage_result
        else:
            dmg_result = _svc.apply_damage_to_participant(
                target_participant,
                _npc_outgoing_damage(opponent, npc_action),
                damage_type=npc_action.threat_entry.damage_type,
                source=opponent,
                on_hit_pool=npc_action.threat_entry.on_hit_consequence_pool,
                delivery=npc_action.threat_entry.delivery,
                is_area=npc_action.threat_entry.targeting_mode != TargetingMode.SINGLE,
            )
        outcome.damage_results.append(dmg_result)

        consequence = process_damage_consequences(
            character_sheet=target_participant.character_sheet,
            damage_dealt=dmg_result.damage_dealt,
            damage_type=npc_action.threat_entry.damage_type,
            combat_interaction_factory=get_npc_action_interaction,
            source_character=opponent.objectdb,
        )
    outcome.damage_consequences.append(consequence)

    # Sent Flying trigger (#2638): a sends_flying attack that connects with
    # damage > 0 launches its victim airborne — the plummet-pattern's
    # "in-flight" clone (see the "Sent Flying" function family: _trigger_sent_flying
    # onward, defined above swarm_kills).
    if npc_action.threat_entry.sends_flying and dmg_result.damage_dealt > 0:
        _trigger_sent_flying(target_participant, npc_action, dmg_result.damage_dealt)

    # Nemesis/toxic-NPC-bond regard hook (#2039): a notable (persona-backed)
    # NPC opponent critically harming a PC (death- or permanent-wound-eligible
    # hit) records an NPC_HARMED_PC_INTEREST regard event. A mook/persona-less
    # opponent's hit — or any non-critical hit from a notable NPC — is
    # deliberately a no-op: no NpcRegard row is ever created for it.
    if opponent.persona_id is not None and (
        dmg_result.death_eligible or dmg_result.permanent_wound_eligible
    ):
        from world.npc_services.constants import NpcRegardEventReason  # noqa: PLC0415
        from world.npc_services.regard import (  # noqa: PLC0415
            get_regard_event_config,
            record_npc_regard_event,
        )
        from world.scenes.models import Persona  # noqa: PLC0415

        try:
            pc_persona = target_participant.character_sheet.primary_persona
        except Persona.DoesNotExist:
            pc_persona = None
        if pc_persona is not None:
            cfg = get_regard_event_config()
            record_npc_regard_event(
                holder_persona=opponent.persona,
                target=pc_persona,
                amount=cfg.combat_harm_amount,
                reason=NpcRegardEventReason.NPC_HARMED_PC_INTEREST,
                source_npc_combat_action=npc_action,
            )

    # Collect condition applications for bulk apply
    if dmg_result.damage_dealt > 0 and conditions:
        target_obj = target_participant.character_sheet.character
        condition_applications.extend((target_obj, ct) for ct in conditions)


def _allegiance_credit_sheet(
    opponent: CombatOpponent, encounter: CombatEncounter
) -> CharacterSheet | None:
    """Who gets damage/defeat credit for an NPC fighting on the party's behalf (#4091).

    A summon credits its summoner. A charmed or turned NPC credits the PC who applied
    the designating allegiance condition, only while that PC is an ACTIVE participant.
    """
    if opponent.summoned_by_id is not None:
        return opponent.summoned_by
    if opponent.objectdb_id is None:
        return None

    from world.npc_services.allegiance import allegiance_instance_on  # noqa: PLC0415

    instance = allegiance_instance_on(opponent.objectdb)
    if instance is None or instance.source_character_id is None:
        return None
    participant = (
        CombatParticipant.objects.filter(
            encounter=encounter,
            status=ParticipantStatus.ACTIVE,
            character_sheet__character_id=instance.source_character_id,
        )
        .select_related("character_sheet")
        .first()
    )
    return participant.character_sheet if participant is not None else None


def _resolve_npc_action_on_opponent_target(  # noqa: PLR0913 - needs full resolution context
    target_opponent: CombatOpponent,
    *,
    opponent: CombatOpponent,
    npc_action: CombatOpponentAction,
    outcome: ActionOutcome,
    conditions: list,
    condition_applications: list,
) -> None:
    """Resolve one NPC action against a single OPPONENT target (#1584 Task 7b, #4091).

    Routes an ALLY summon's, or a charmed/turned NPC's, attack at a hostile opponent.
    Damage only — the PC survivability pipeline (``process_damage_consequences``)
    stays PC-only here; ``apply_damage_to_opponent`` already sets
    ``OpponentStatus.DEFEATED`` internally. Damage/defeat achievement credit goes to
    ``_allegiance_credit_sheet`` (the summoner, or the PC who won the attacker over);
    null-safe when neither applies. A threat entry's ``conditions_applied`` now lands
    on an opponent target too, when the hit dealt damage (#4091) — the bulk apply
    after the resolution loops in ``_resolve_npc_action`` covers it.

    A taunt entry (``taunt_potency``) acts on player characters only: here it is skipped
    entirely, with no zero-damage hit and no taunt line.
    """
    # Mirror the participant guard: skip an escaped/defeated (non-ACTIVE) target.
    if target_opponent.status != OpponentStatus.ACTIVE:
        return
    if npc_action.threat_entry.taunt_potency is not None:
        return

    dmg_result = _svc.apply_damage_to_opponent(
        target_opponent,
        _npc_outgoing_damage(opponent, npc_action),
        damage_type=npc_action.threat_entry.damage_type,
        source_sheet=_allegiance_credit_sheet(opponent, opponent.encounter),
    )
    outcome.damage_results.append(dmg_result)
    if dmg_result.damage_dealt > 0 and conditions and target_opponent.objectdb_id is not None:
        condition_applications.extend((target_opponent.objectdb, ct) for ct in conditions)


def _npc_action_narration(
    opponent: CombatOpponent,
    npc_action: CombatOpponentAction,
    target_label: str | None,
    outcome: ActionOutcome,
) -> str:
    """The one outcome line for an NPC action: a plain taunt line, or the damage line (#4737)."""
    from world.combat.interaction_services import (  # noqa: PLC0415
        render_action_outcome_narration,
        render_taunt_narration,
    )

    entry = npc_action.threat_entry
    if entry.taunt_potency is not None:
        return render_taunt_narration(
            actor_label=opponent.name, target_label=target_label, hit_text=entry.hit_narration
        )
    return render_action_outcome_narration(
        actor_label=opponent.name,
        technique_name=entry.name,
        target_label=target_label,
        outcome=outcome,
        hit_text=entry.hit_narration,
        miss_text=entry.miss_narration,
    )


def _action_targets(
    npc_action: CombatOpponentAction,
) -> tuple[list[CombatParticipant], list[CombatOpponent]]:
    """The participant and opponent targets of ``npc_action``, from the prefetch when present."""
    try:
        targets: list[CombatParticipant] = npc_action.cached_targets
    except AttributeError:
        targets = list(npc_action.targets.all())
    try:
        opponent_targets: list[CombatOpponent] = npc_action.cached_opponent_targets
    except AttributeError:
        opponent_targets = list(npc_action.opponent_targets.all())
    return targets, opponent_targets


def _resolve_npc_action(
    opponent: CombatOpponent,
    npc_action: CombatOpponentAction,
    defense_check_type: CheckType | None,
    defense_check_fn: PerformCheckFn | None,
) -> ActionOutcome:
    """Resolve a single NPC's action against its targets.

    Exactly one target relation is populated per action: participant ``targets``
    (the normal PC-facing path — applies damage, knockout/death transitions, and
    threat-entry conditions) or ``opponent_targets`` (an ALLY summon, or a charmed/
    turned NPC, attacking a hostile opponent — damage plus threat-entry conditions
    on a damaging hit; #1584, #4091). No survivability pipeline either way for the
    opponent-target path.

    When ``defense_check_type`` is None (production), the defense check type is
    sourced from ``npc_action.threat_entry.defense_check_type`` (#1994). A
    non-None external param (test override) takes precedence.

    Before any damage, ``refit_targets`` re-checks reach against live positions
    (#4607). When no target is left the row is skipped with
    ``"{name} cannot reach anyone."`` and an empty outcome.
    """
    # Source from threat entry when no external override is provided (#1994).
    effective_defense_check_type = defense_check_type or npc_action.threat_entry.defense_check_type
    outcome = ActionOutcome(entity_type=ENTITY_TYPE_NPC, entity_label=str(opponent))

    # A place-covering attack hits whoever stands in its place now (#4676).
    cover_place(npc_action)

    # Reach is live (#4607): drop the stored targets this strike no longer reaches
    # (a PC stepped away at declaration, or this opponent's advance fell short).
    if not refit_targets(npc_action):
        broadcast_cannot_reach(opponent)
        return outcome

    targets, opponent_targets = _action_targets(npc_action)

    # A taunt entry acts on player characters only (#4737): aimed at opponents alone it does
    # nothing, so there is nothing to resolve and no line to print.
    if npc_action.threat_entry.taunt_potency is not None and not targets:
        return outcome

    # Exactly one relation is populated; use whichever for narration labels.
    label_targets: list = targets or opponent_targets

    # Pre-fetch conditions from the threat entry
    try:
        conditions = npc_action.threat_entry.cached_conditions
    except AttributeError:
        conditions = list(npc_action.threat_entry.conditions_applied.all())

    from world.combat.interaction_services import (  # noqa: PLC0415
        create_npc_action_interaction,
        personas_for_participants,
    )

    # #3787 Task 5 - who this NPC action struck. Batched once (no queries in a
    # loop): `targets` may hold several PC participants hit by one NPC action.
    # `opponent_targets` (the ALLY-summon-vs-NPC path) are NPCs with no Persona,
    # so they never contribute a target.
    npc_target_personas = personas_for_participants(targets)

    # Lazy factory: mint the ACTION-mode Interaction only when the first
    # survivability tier actually fires (#864). Memoised so all targets of this
    # NPC action share one row.
    npc_action_label = _npc_action_target_label(label_targets)
    _npc_interaction_cache: list[Interaction] = []

    def _get_npc_action_interaction() -> Interaction:
        if not _npc_interaction_cache:
            _npc_interaction_cache.append(
                create_npc_action_interaction(
                    opponent_action=npc_action,
                    target_label=npc_action_label,
                    target_personas=npc_target_personas,
                )
            )
        return _npc_interaction_cache[0]

    condition_applications: list[tuple[ObjectDB, ConditionTemplate]] = []

    for target_participant in targets:
        _resolve_npc_action_on_target(
            target_participant,
            opponent=opponent,
            npc_action=npc_action,
            defense_check_type=effective_defense_check_type,
            defense_check_fn=defense_check_fn,
            conditions=conditions,
            outcome=outcome,
            condition_applications=condition_applications,
            get_npc_action_interaction=_get_npc_action_interaction,
        )

    # Opponent-target path (#1584, #4091): an ALLY summon or a charmed/turned NPC
    # attacking a hostile opponent. Damage, plus threat-entry conditions on a
    # damaging hit (fed into the same bulk-apply call below); no survivability
    # pipeline.
    for target_opponent in opponent_targets:
        _resolve_npc_action_on_opponent_target(
            target_opponent,
            opponent=opponent,
            npc_action=npc_action,
            outcome=outcome,
            conditions=conditions,
            condition_applications=condition_applications,
        )

    # Bulk-apply all conditions from this NPC action
    if condition_applications:
        from world.conditions.services import bulk_apply_conditions  # noqa: PLC0415
        from world.conditions.types import BulkConditionApplication  # noqa: PLC0415

        bulk_apply_conditions(
            [BulkConditionApplication(target=t, template=ct) for (t, ct) in condition_applications],
            source_character=opponent.objectdb,
        )

    # Broadcast a durable, Narrator-authored OUTCOME line for the NPC action.
    from world.combat.interaction_services import (  # noqa: PLC0415
        broadcast_action_outcome,
    )

    # Same label_targets as npc_action_label above -- reuse rather than
    # re-running persona_names_for_sheets for the identical list.
    npc_target_label = npc_action_label
    npc_narration = _npc_action_narration(opponent, npc_action, npc_target_label, outcome)
    broadcast_action_outcome(
        encounter=opponent.encounter,
        narration=npc_narration,
        target_personas=npc_target_personas,
    )

    return outcome
