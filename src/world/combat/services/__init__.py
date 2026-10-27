"""Combat encounter services, grouped into subpackages and single-concept modules (#4318).

Import from this package exactly as before: ``from world.combat.services import X``.
Every name is re-exported here. Names tests patch on this package are called as
``_svc.<name>`` from inside the modules, so the patch still intercepts those calls.
"""

import random

from flows.emit import emit_event
from world.checks.services import collect_check_modifiers, perform_check
from world.combat.models import ClashContributionDeclaration
from world.combat.services.boss.boss_phase import (
    _apply_phase_transition,
    _stamp_break_bar,
    _stamp_enrage,
    _surge_on_phase_transition,
    check_and_advance_boss_phase,
)
from world.combat.services.boss.boss_phase_config import (
    _clone_authored_phases,
    _stamp_phase_break_bar_config,
    minimum_break_bar_threshold,
)
from world.combat.services.boss.break_bar import (
    _assess_boss_break_bar,
    _break_bar_contributor_labels,
    _break_bar_events_this_round,
    _broadcast_break_celebration,
    _outcome_damaged_boss,
    _persist_break_bar_events,
    assess_break_bar,
)
from world.combat.services.boss.break_bar_contributions import (
    _boss_new_debuff_events,
    _newly_suppressed_lieutenants,
    _participant_id_for_objectdb,
    _pc_lock_hold_contributors,
)
from world.combat.services.boss.creature_spawn import (
    spawn_from_creature_template,
)
from world.combat.services.boss.opponent import (
    _acting_story_for_encounter,
    _enforce_opponent_custody_gate,
    _resolve_objectdb_for_opponent,
    _resolve_opponent_stat_fields,
    add_opponent,
    remove_opponent,
)
from world.combat.services.boss.phase_narration import (
    _narrate_phase_transition,
)
from world.combat.services.boss.reinforcements import (
    _active_reinforcer_count,
    _spawn_reinforcements,
)
from world.combat.services.boss.story_recognition import (
    _record_story_break_recognition,
    _record_story_envoy_rescue,
)
from world.combat.services.combos.combo_detection import (
    _available_combo_for_action,
    _build_round_combo,
    _combo_composition_is_eligible,
    _combo_passes_clash_prereqs,
    _prefetch_clash_state,
    detect_available_combos,
    scan_round_combos,
)
from world.combat.services.combos.combo_outcome import (
    _apply_combo_rider,
    _broadcast_combo_finisher_narration,
    _damage_multiplier_for_success,
    _group_combo_outcomes,
    _process_combo_outcomes,
    _signature_clause_for,
)
from world.combat.services.combos.combo_upgrade import (
    _revalidate_combo_upgrades,
    revert_combo_upgrade,
    upgrade_action_to_combo,
)
from world.combat.services.combos.resolution_order import (
    _action_matches_slot,
    _best_slot_assignment,
    _fill_slots,
    _participant_has_archetype,
    _unused_matches,
    get_resolution_order,
)
from world.combat.services.damage.challenges import (
    _bind_interpose_challenges_any_ally,
    _ensure_interpose_challenges,
    _ensure_reactive_challenges,
    _ensure_succor_challenges,
)
from world.combat.services.damage.companion_defend import (
    _fire_on_hit_pool,
    _try_companion_defend,
)
from world.combat.services.damage.condition_interaction import (
    _apply_condition_damage_interactions,
)
from world.combat.services.damage.damage import (
    _emit_post_damage_events,
    _run_pre_apply_interceptors,
    apply_damage_to_participant,
)
from world.combat.services.damage.damage_totals import (
    _opponent_damage_totals,
)
from world.combat.services.damage.defeat import (
    _emit_companion_fall,
    _resolve_opponent_defeat,
)
from world.combat.services.damage.engagement_lock import (
    _break_engagement_lock_on_defeat,
    _maybe_trigger_lock_interference,
)
from world.combat.services.damage.execute import (
    _apply_execute_multiplier,
    _opponent_health_before_pct,
)
from world.combat.services.damage.interception import (
    _dispatch_interpose_action,
    _emit_opponent_pre_apply,
    _fire_rampart_retaliation,
    _guardian_can_fire_technique_interpose,
    _rampart_resist,
    _redirect_to_opponent,
    _resolve_opponent_pre_apply,
    _resolve_technique_redirect,
    _try_guardian_shield_opponent,
    _try_interpose,
    _try_interpose_for_opponent,
    _try_technique_interpose,
    apply_damage_to_opponent,
    apply_rampart_interception,
    dispatch_interpose,
)
from world.combat.services.damage.interpose_dispatch import (
    _grade_interpose_damage,
    _narrate_reaction_declined,
    _narrate_technique_interpose_fizzle,
    _settle_technique_interpose_cost,
    apply_interpose_outcome,
)
from world.combat.services.damage.passive_techniques import (
    _apply_passive_technique,
    _refresh_participant_trigger_handlers,
    _resolve_passive_actions,
)
from world.combat.services.damage.probing import (
    increment_probing,
)
from world.combat.services.damage.soak import (
    _effective_resistance_for_opponent,
    _effective_soak_for_opponent,
)
from world.combat.services.damage.swarm import (
    _apply_swarm_damage,
    _zero_opponent_damage_result,
    swarm_attack_count,
    swarm_kills,
)
from world.combat.services.damage.vulnerability import (
    _is_vulnerable,
    _vulnerability_intensity_bonus,
)
from world.combat.services.declarations.await_opening import declare_await_opening
from world.combat.services.declarations.cast_position import (
    resolve_cast_position_params,
)
from world.combat.services.declarations.charge import (
    _resolve_charge_movement,
    declare_charge,
)
from world.combat.services.declarations.cover import (
    _combatants_at_position,
    apply_position_cover,
    declare_cover,
)
from world.combat.services.declarations.declaration_phase import (
    begin_declaration_phase,
)
from world.combat.services.declarations.declaration_validation import (
    _supplied_target_kind,
    _validate_no_pending_sustained,
    _validate_passive_slot,
    _validate_strain_commitment,
    _validate_target_kind_alignment,
    _validate_technique_reach,
)
from world.combat.services.declarations.declare_action import (
    declare_action,
)
from world.combat.services.declarations.demoralize import (
    _resolve_demoralize,
    declare_demoralize,
)
from world.combat.services.declarations.flee import (
    _resolve_flee,
    declare_flee,
)
from world.combat.services.declarations.hostility import (
    combatants_hostile_to,
)
from world.combat.services.declarations.interpose_declaration import (
    declare_interpose,
)
from world.combat.services.declarations.joust import (
    _JOUST_PARTICIPANT_COUNT,
    _joust_offense_check,
    _resolve_joust,
    _resolve_joust_pass,
    declare_joust,
)
from world.combat.services.declarations.mark import (
    declare_mark,
)
from world.combat.services.declarations.parley import (
    _parley_gate_met,
    _resolve_parley,
    declare_parley,
)
from world.combat.services.declarations.rally import (
    _resolve_rally,
    declare_rally,
)
from world.combat.services.declarations.redirect import (
    _redirect_away,
    _redirect_to_object,
    _validate_redirect_declaration,
)
from world.combat.services.declarations.social_check import (
    _record_combat_consequence,
    _resolve_social_check,
    _social_combat_difficulty,
    _social_verb_success_level,
)
from world.combat.services.declarations.succor import (
    declare_succor,
    dispatch_succor,
)
from world.combat.services.declarations.sustained_declaration import (
    _sync_sustained_technique_declaration,
    try_declare_sustained_ritual,
)
from world.combat.services.declarations.taunt import (
    _resolve_taunt,
    declare_taunt,
)
from world.combat.services.declarations.use_item import (
    _resolve_use_item,
    declare_use_item,
)
from world.combat.services.encounter.aftermath import (
    _apply_aftermath_rules,
    _apply_opponent_aftermath_pools,
)
from world.combat.services.encounter.anima import (
    _get_anima,
)
from world.combat.services.encounter.behavior_conditions import (
    _has_active_behavior_altering_condition,
    _new_behavior_altering_conditions,
)
from world.combat.services.encounter.bonds import (
    _dissolve_graduated_bonds,
)
from world.combat.services.encounter.check_types import (
    get_concentration_check_type,
    get_penetration_check_type,
)
from world.combat.services.encounter.companion_defeat import (
    _resolve_companion_defeats,
)
from world.combat.services.encounter.completion import (
    _check_encounter_completion,
    _hand_off_acute_peril_to_scene_round,
    cleanup_completed_encounter,
    complete_encounter,
    end_encounter,
    maybe_pause_encounter_for_disconnect,
)
from world.combat.services.encounter.completion_counters import (
    _increment_completion_counters,
)
from world.combat.services.encounter.config import (
    get_clash_config,
    get_flee_config,
    get_social_maneuver_config,
    get_strain_config,
)
from world.combat.services.encounter.death_gate import (
    _character_has_death_deferred,
    _emit_death_gate,
)
from world.combat.services.encounter.encounter_outcome import (
    _broadcast_encounter_outcome,
    _classify_encounter_outcome,
    _emit_encounter_completed,
)
from world.combat.services.encounter.encounter_risk import (
    _maybe_warn_solo_boss_entry,
    acknowledge_encounter_risk,
)
from world.combat.services.encounter.encounter_settings import (
    _UNSET,
    update_encounter_settings,
)
from world.combat.services.encounter.encounter_setup import (
    finalize_new_encounter,
)
from world.combat.services.encounter.engagement import (
    _ensure_combat_engagement,
    active_combat_engagement_for,
)
from world.combat.services.encounter.levels import (
    _bulk_primary_levels,
)
from world.combat.services.encounter.npc_identity import (
    delete_ephemeral_npc,
    has_persistent_identity_references,
    is_combat_npc_typeclass,
)
from world.combat.services.encounter.participant import (
    _create_participant,
    add_participant,
    join_encounter,
    leave_encounter,
    remove_participant,
)
from world.combat.services.encounter.pulls import (
    expire_pulls_for_round,
)
from world.combat.services.encounter.readiness import (
    maybe_resolve_on_ready,
    toggle_action_ready,
)
from world.combat.services.encounter.sustained_absorption import (
    roll_sustained_absorption_budget,
)
from world.combat.services.encounter.threat import (
    _accumulate_damage_threat,
    accumulate_threat,
    get_or_create_threat_record,
)
from world.combat.services.equipment.armor_soak import (
    _equipped_armor_soak_pieces,
    _resonant_armor_soak,
    _split_armor_soak_by_compatibility,
    apply_equipped_armor_soak,
    effective_soak_from_armor,
)
from world.combat.services.equipment.combat_target_bonus import (
    _combat_target_bonus,
)
from world.combat.services.equipment.elevation import (
    elevation_bonus,
)
from world.combat.services.equipment.equipped_weapon import (
    _equipped_weapon_archetype,
    _select_equipped_weapon,
    _weapon_augmented_budget,
    _wear_equipped_weapon,
    effective_weapon_profile,
)
from world.combat.services.npc.companion_orders import (
    _COMPANION_HOLD,
    _apply_companion_order,
    _get_companion_order,
)
from world.combat.services.npc.narration import (
    _broadcast_commitment_line,
    _dual_dispatch_combat_narration,
)
from world.combat.services.npc.npc_action import (
    _allegiance_credit_sheet,
    _npc_action_target_label,
    _resolve_npc_action,
    _resolve_npc_action_on_opponent_target,
    _resolve_npc_action_on_target,
)
from world.combat.services.npc.npc_attack import (
    _execute_npc_attack,
    resolve_npc_attack,
)
from world.combat.services.npc.npc_cooldowns import (
    _batch_fetch_cooldown_data,
    _build_cooldown_q_filters,
    _collect_cooldown_actions,
    _collect_cooldown_pending,
)
from world.combat.services.npc.npc_movement import (
    advance_opponent,
    refit_targets,
)
from world.combat.services.npc.npc_selection import (
    ensure_opponent_plans,
    plan_opponent_round,
    select_npc_actions,
)
from world.combat.services.npc.npc_targeting import (
    _get_eligible_entries,
    _npc_action_target_pool,
    _select_opponent_targets,
    _select_targets,
    _select_targets_core,
    _set_npc_action_targets,
    _TargetT,
)
from world.combat.services.npc.sustained import (
    _apply_sustained_erosion_rider,
    _mature_one_sustained_action,
    _mature_sustained_actions,
    _mature_sustained_ritual,
    _mature_sustained_technique,
)
from world.combat.services.npc.sustained_narration import (
    _broadcast_sustained_broken,
    _broadcast_sustained_erosion,
    _broadcast_sustained_held,
    _broadcast_sustained_telegraph,
)
from world.combat.services.npc.windup import (
    _apply_windup_interception_rider,
    _create_pending_opponent_attack,
    _declare_windup_attack,
    _mature_one_pending_attack,
    _mature_pending_opponent_attacks,
    _select_windup_targets,
    windup_damage_scale,
)
from world.combat.services.npc.windup_narration import (
    _broadcast_windup_fizzled,
    _broadcast_windup_telegraph,
    _broadcast_windup_wreck,
    _find_windup_caller,
)
from world.combat.services.rounds.action_resolution import (
    _resolve_actions,
)
from world.combat.services.rounds.boss_transitions import (
    _check_boss_transitions,
)
from world.combat.services.rounds.certain_death import (
    _cancel_pending_certain_death_if_abandoned,
)
from world.combat.services.rounds.clash import (
    _resolve_clashes,
)
from world.combat.services.rounds.clash_contribution import (
    declare_clash_contribution,
)
from world.combat.services.rounds.declared_challenges import (
    _resolve_declared_challenges,
)
from world.combat.services.rounds.held_back import (
    _narrate_held_back,
)
from world.combat.services.rounds.maneuvers import (
    _STANDALONE_MANEUVER_RESOLVERS,
)
from world.combat.services.rounds.resolution import (
    resolve_round,
)
from world.combat.services.rounds.round_start import (
    _fire_round_start,
)
from world.combat.services.rounds.sustained_break import (
    _break_pending_sustained_actions,
)
from world.combat.services.sent_flying.sent_flying import (
    _broadcast_sent_flying_catch,
    _broadcast_sent_flying_launch,
    _clear_sent_flying_marker,
    _resolve_one_sent_flying_landing,
    _resolve_sent_flying_markers,
    _sent_flying_windup_caller,
    _trigger_sent_flying,
)
from world.combat.services.sent_flying.sent_flying_catch import (
    _try_catch_sent_flying,
)
from world.combat.services.techniques.allegiance_break import (
    _attempt_allegiance_breaks_for_action,
)
from world.combat.services.techniques.audere import (
    _block_if_participant_mid_audere_majora_crossing,
    _end_audere_kind_and_delete_offers,
    _release_and_delete_withheld_majora_offers,
)
from world.combat.services.techniques.cast_audience import (
    _resolve_combat_cast_audience,
)
from world.combat.services.techniques.entrance_moment import (
    _maybe_suggest_entrance_dramatic_moment,
)
from world.combat.services.techniques.insight import (
    _maybe_produce_insight_for_cast,
)
from world.combat.services.techniques.intensity import (
    _sum_active_flat_bonuses,
    compute_intensity_for_clash,
)
from world.combat.services.techniques.npc_regard import (
    _maybe_record_npc_regard_on_defeat,
)
from world.combat.services.techniques.pc_action import (
    _resolve_pc_action,
    _run_combat_technique_pipeline,
)
from world.combat.services.techniques.pc_broadcast import (
    _record_and_broadcast_pc_action,
)
from world.combat.services.techniques.spectacle import (
    _maybe_apply_spectacle_for_action,
)
from world.combat.services.techniques.technique_resolution import (
    _build_combat_result,
    resolve_combat_technique,
)
from world.combat.services.techniques.technique_resolver import (
    CombatTechniqueResolver,
)
from world.combat.services.techniques.technique_targets import (
    _build_affected_targets,
    _check_combat_target_prerequisites,
    _resolve_condition_target,
    _resolve_enemy_condition_targets,
    _resolve_primary_target_sheet,
)
from world.combat.services.techniques.weakness_selection import (
    _maybe_create_weakness_selection_for_cast,
)
from world.combat.services.upkeep.upkeep import (
    _debit_ally_paid_upkeep,
    _drain_participant_upkeep,
    _narrate_upkeep_lapse,
    _pay_upkeep,
    drain_reactive_upkeep,
)
from world.magic.services.soulfray import accumulate_soulfray

__all__ = [
    "_COMPANION_HOLD",
    "_JOUST_PARTICIPANT_COUNT",
    "_STANDALONE_MANEUVER_RESOLVERS",
    "_UNSET",
    "ClashContributionDeclaration",
    "CombatTechniqueResolver",
    "_TargetT",
    "_accumulate_damage_threat",
    "_acting_story_for_encounter",
    "_action_matches_slot",
    "_active_reinforcer_count",
    "_allegiance_credit_sheet",
    "_apply_aftermath_rules",
    "_apply_combo_rider",
    "_apply_companion_order",
    "_apply_condition_damage_interactions",
    "_apply_execute_multiplier",
    "_apply_opponent_aftermath_pools",
    "_apply_passive_technique",
    "_apply_phase_transition",
    "_apply_sustained_erosion_rider",
    "_apply_swarm_damage",
    "_apply_windup_interception_rider",
    "_assess_boss_break_bar",
    "_attempt_allegiance_breaks_for_action",
    "_available_combo_for_action",
    "_batch_fetch_cooldown_data",
    "_best_slot_assignment",
    "_bind_interpose_challenges_any_ally",
    "_block_if_participant_mid_audere_majora_crossing",
    "_boss_new_debuff_events",
    "_break_bar_contributor_labels",
    "_break_bar_events_this_round",
    "_break_engagement_lock_on_defeat",
    "_break_pending_sustained_actions",
    "_broadcast_break_celebration",
    "_broadcast_combo_finisher_narration",
    "_broadcast_commitment_line",
    "_broadcast_encounter_outcome",
    "_broadcast_sent_flying_catch",
    "_broadcast_sent_flying_launch",
    "_broadcast_sustained_broken",
    "_broadcast_sustained_erosion",
    "_broadcast_sustained_held",
    "_broadcast_sustained_telegraph",
    "_broadcast_windup_fizzled",
    "_broadcast_windup_telegraph",
    "_broadcast_windup_wreck",
    "_build_affected_targets",
    "_build_combat_result",
    "_build_cooldown_q_filters",
    "_build_round_combo",
    "_bulk_primary_levels",
    "_cancel_pending_certain_death_if_abandoned",
    "_character_has_death_deferred",
    "_check_boss_transitions",
    "_check_combat_target_prerequisites",
    "_check_encounter_completion",
    "_classify_encounter_outcome",
    "_clear_sent_flying_marker",
    "_clone_authored_phases",
    "_collect_cooldown_actions",
    "_collect_cooldown_pending",
    "_combat_target_bonus",
    "_combatants_at_position",
    "_combo_composition_is_eligible",
    "_combo_passes_clash_prereqs",
    "_create_participant",
    "_create_pending_opponent_attack",
    "_damage_multiplier_for_success",
    "_debit_ally_paid_upkeep",
    "_declare_windup_attack",
    "_dispatch_interpose_action",
    "_dissolve_graduated_bonds",
    "_drain_participant_upkeep",
    "_dual_dispatch_combat_narration",
    "_effective_resistance_for_opponent",
    "_effective_soak_for_opponent",
    "_emit_companion_fall",
    "_emit_death_gate",
    "_emit_encounter_completed",
    "_emit_opponent_pre_apply",
    "_emit_post_damage_events",
    "_end_audere_kind_and_delete_offers",
    "_enforce_opponent_custody_gate",
    "_ensure_combat_engagement",
    "_ensure_interpose_challenges",
    "_ensure_reactive_challenges",
    "_ensure_succor_challenges",
    "_equipped_armor_soak_pieces",
    "_equipped_weapon_archetype",
    "_execute_npc_attack",
    "_fill_slots",
    "_find_windup_caller",
    "_fire_on_hit_pool",
    "_fire_rampart_retaliation",
    "_fire_round_start",
    "_get_anima",
    "_get_companion_order",
    "_get_eligible_entries",
    "_grade_interpose_damage",
    "_group_combo_outcomes",
    "_guardian_can_fire_technique_interpose",
    "_hand_off_acute_peril_to_scene_round",
    "_has_active_behavior_altering_condition",
    "_increment_completion_counters",
    "_is_vulnerable",
    "_joust_offense_check",
    "_mature_one_pending_attack",
    "_mature_one_sustained_action",
    "_mature_pending_opponent_attacks",
    "_mature_sustained_actions",
    "_mature_sustained_ritual",
    "_mature_sustained_technique",
    "_maybe_apply_spectacle_for_action",
    "_maybe_create_weakness_selection_for_cast",
    "_maybe_produce_insight_for_cast",
    "_maybe_record_npc_regard_on_defeat",
    "_maybe_suggest_entrance_dramatic_moment",
    "_maybe_trigger_lock_interference",
    "_maybe_warn_solo_boss_entry",
    "_narrate_held_back",
    "_narrate_phase_transition",
    "_narrate_reaction_declined",
    "_narrate_technique_interpose_fizzle",
    "_narrate_upkeep_lapse",
    "_new_behavior_altering_conditions",
    "_newly_suppressed_lieutenants",
    "_npc_action_target_label",
    "_npc_action_target_pool",
    "_opponent_damage_totals",
    "_opponent_health_before_pct",
    "_outcome_damaged_boss",
    "_parley_gate_met",
    "_participant_has_archetype",
    "_participant_id_for_objectdb",
    "_pay_upkeep",
    "_pc_lock_hold_contributors",
    "_persist_break_bar_events",
    "_prefetch_clash_state",
    "_process_combo_outcomes",
    "_rampart_resist",
    "_record_and_broadcast_pc_action",
    "_record_combat_consequence",
    "_record_story_break_recognition",
    "_record_story_envoy_rescue",
    "_redirect_away",
    "_redirect_to_object",
    "_redirect_to_opponent",
    "_refresh_participant_trigger_handlers",
    "_release_and_delete_withheld_majora_offers",
    "_resolve_actions",
    "_resolve_charge_movement",
    "_resolve_clashes",
    "_resolve_combat_cast_audience",
    "_resolve_companion_defeats",
    "_resolve_condition_target",
    "_resolve_declared_challenges",
    "_resolve_demoralize",
    "_resolve_enemy_condition_targets",
    "_resolve_flee",
    "_resolve_joust",
    "_resolve_joust_pass",
    "_resolve_npc_action",
    "_resolve_npc_action_on_opponent_target",
    "_resolve_npc_action_on_target",
    "_resolve_objectdb_for_opponent",
    "_resolve_one_sent_flying_landing",
    "_resolve_opponent_defeat",
    "_resolve_opponent_pre_apply",
    "_resolve_opponent_stat_fields",
    "_resolve_parley",
    "_resolve_passive_actions",
    "_resolve_pc_action",
    "_resolve_primary_target_sheet",
    "_resolve_rally",
    "_resolve_sent_flying_markers",
    "_resolve_social_check",
    "_resolve_taunt",
    "_resolve_technique_redirect",
    "_resolve_use_item",
    "_resonant_armor_soak",
    "_revalidate_combo_upgrades",
    "_run_combat_technique_pipeline",
    "_run_pre_apply_interceptors",
    "_select_equipped_weapon",
    "_select_opponent_targets",
    "_select_targets",
    "_select_targets_core",
    "_select_windup_targets",
    "_sent_flying_windup_caller",
    "_set_npc_action_targets",
    "_settle_technique_interpose_cost",
    "_signature_clause_for",
    "_social_combat_difficulty",
    "_social_verb_success_level",
    "_spawn_reinforcements",
    "_split_armor_soak_by_compatibility",
    "_stamp_break_bar",
    "_stamp_enrage",
    "_stamp_phase_break_bar_config",
    "_sum_active_flat_bonuses",
    "_supplied_target_kind",
    "_surge_on_phase_transition",
    "_sync_sustained_technique_declaration",
    "_trigger_sent_flying",
    "_try_catch_sent_flying",
    "_try_companion_defend",
    "_try_guardian_shield_opponent",
    "_try_interpose",
    "_try_interpose_for_opponent",
    "_try_technique_interpose",
    "_unused_matches",
    "_validate_no_pending_sustained",
    "_validate_passive_slot",
    "_validate_redirect_declaration",
    "_validate_strain_commitment",
    "_validate_target_kind_alignment",
    "_validate_technique_reach",
    "_vulnerability_intensity_bonus",
    "_weapon_augmented_budget",
    "_wear_equipped_weapon",
    "_zero_opponent_damage_result",
    "accumulate_soulfray",
    "accumulate_threat",
    "acknowledge_encounter_risk",
    "active_combat_engagement_for",
    "add_opponent",
    "add_participant",
    "advance_opponent",
    "apply_damage_to_opponent",
    "apply_damage_to_participant",
    "apply_equipped_armor_soak",
    "apply_interpose_outcome",
    "apply_position_cover",
    "apply_rampart_interception",
    "assess_break_bar",
    "begin_declaration_phase",
    "check_and_advance_boss_phase",
    "cleanup_completed_encounter",
    "collect_check_modifiers",
    "combatants_hostile_to",
    "complete_encounter",
    "compute_intensity_for_clash",
    "declare_action",
    "declare_await_opening",
    "declare_charge",
    "declare_clash_contribution",
    "declare_cover",
    "declare_demoralize",
    "declare_flee",
    "declare_interpose",
    "declare_joust",
    "declare_mark",
    "declare_parley",
    "declare_rally",
    "declare_succor",
    "declare_taunt",
    "declare_use_item",
    "delete_ephemeral_npc",
    "detect_available_combos",
    "dispatch_interpose",
    "dispatch_succor",
    "drain_reactive_upkeep",
    "effective_soak_from_armor",
    "effective_weapon_profile",
    "elevation_bonus",
    "emit_event",
    "end_encounter",
    "ensure_opponent_plans",
    "expire_pulls_for_round",
    "finalize_new_encounter",
    "get_clash_config",
    "get_concentration_check_type",
    "get_flee_config",
    "get_or_create_threat_record",
    "get_penetration_check_type",
    "get_resolution_order",
    "get_social_maneuver_config",
    "get_strain_config",
    "has_persistent_identity_references",
    "increment_probing",
    "is_combat_npc_typeclass",
    "join_encounter",
    "leave_encounter",
    "maybe_pause_encounter_for_disconnect",
    "maybe_resolve_on_ready",
    "minimum_break_bar_threshold",
    "perform_check",
    "plan_opponent_round",
    "random",
    "refit_targets",
    "remove_opponent",
    "remove_participant",
    "resolve_cast_position_params",
    "resolve_combat_technique",
    "resolve_npc_attack",
    "resolve_round",
    "revert_combo_upgrade",
    "roll_sustained_absorption_budget",
    "scan_round_combos",
    "select_npc_actions",
    "spawn_from_creature_template",
    "swarm_attack_count",
    "swarm_kills",
    "toggle_action_ready",
    "try_declare_sustained_ritual",
    "update_encounter_settings",
    "upgrade_action_to_combo",
    "windup_damage_scale",
]
