"""Periodic task definitions for the game clock scheduler."""

from __future__ import annotations

from datetime import timedelta
import logging

from django.db import models

from world.game_clock.task_registry import (
    CronDefinition,
    CronPhase,
    register_task,
)

logger = logging.getLogger("world.game_clock.tasks")


def weekly_rollover_task() -> None:
    """Unified weekly rollover: advance GameWeek then run all weekly processors.

    This is the single orchestrator for all weekly systems. It:
    1. Advances the GameWeek (closes current, creates next)
    2. Processes votes → XP for the closed week
    3. Generates new random scene targets
    4. Processes skill development audit + rust
    5. Resets journal weekly XP trackers
    6. Resets relationship weekly counters
    7. Applies weekly AP regeneration

    Individual weekly tasks are kept registered as fallbacks but this
    orchestrator is the primary entry point.
    """
    from world.game_clock.week_services import advance_game_week

    try:
        new_week = advance_game_week()
    except Exception:
        logger.exception("Failed to advance game week")
        return

    logger.info("Weekly rollover: advanced to %s", new_week)

    # Process each weekly system, catching errors individually so one
    # failure doesn't block the others.
    processors = [
        ("vote XP", _run_vote_processing),
        ("random scene generation", _run_random_scene_generation),
        ("skill development", _run_skill_development),
        ("journal weekly reset", batch_journal_weekly_reset),
        ("relationship weekly reset", batch_relationship_weekly_reset),
        ("AP weekly regen", batch_ap_weekly_regen),
        ("weekly economy", _run_weekly_economy),
        ("domain food consumption", _run_domain_food_consumption),
        ("domain crisis wait rolls", _run_crisis_wait_tick),
        ("social engagement kudos grant", _run_social_engagement_grant),
        ("idle table summary", _run_idle_table_summary),
    ]

    for name, processor in processors:
        try:
            processor()
            logger.info("Weekly rollover: %s complete", name)
        except Exception:
            logger.exception("Weekly rollover: %s failed", name)


def _run_weekly_economy() -> None:
    from world.currency.services import run_weekly_economy

    run_weekly_economy()


def _run_domain_food_consumption() -> None:
    from world.agriculture.services import domain_consumption_tick

    domain_consumption_tick()


def _run_crisis_wait_tick() -> None:
    """Weekly self-resolve/worsen rolls for consciously-ignored crises (#2238)."""
    from world.societies.houses.crisis_services import crisis_wait_tick

    crisis_wait_tick()


def _run_idle_table_summary() -> None:
    """Log a summary of idle GM tables for staff awareness (#2004)."""
    from world.gm.services import idle_tables

    tables = list(idle_tables())
    if not tables:
        return
    names = ", ".join(f"{t.name} (GM: {t.gm.account.username})" for t in tables)
    logger.info("Idle table summary: %d idle table(s): %s", len(tables), names)


def _run_social_engagement_grant() -> None:
    from world.progression.services.engagement import grant_social_engagement_kudos

    grant_social_engagement_kudos()


def _run_vote_processing() -> None:
    from world.progression.services.vote_processing import weekly_vote_processing_task

    weekly_vote_processing_task()


def _run_random_scene_generation() -> None:
    from world.progression.services.random_scene import weekly_random_scene_generation_task

    weekly_random_scene_generation_task()


def _run_skill_development() -> None:
    from world.progression.services.skill_development import weekly_skill_development_task

    weekly_skill_development_task()


def _fetch_ap_modifier_map(
    target_names: list[str],
) -> tuple[dict[int, dict[int, int]], dict[str, int]]:
    """Fetch AP ModifierTarget instances by name and batch-aggregate their values.

    Uses ModifierTarget.objects.get() for SharedMemoryModel cache hits.
    Returns (modifier_lookup, target_pk_map) where:
      - modifier_lookup: {object_db_id: {target_pk: total_value}}
      - target_pk_map: {target_name: target_pk}
    Returns empty dicts if any target doesn't exist (no modifiers configured yet).
    """
    from world.mechanics.models import CharacterModifier, ModifierTarget

    targets: list[ModifierTarget] = []
    target_pk_map: dict[str, int] = {}
    for name in target_names:
        try:
            target = ModifierTarget.objects.get(name=name)
        except ModifierTarget.DoesNotExist:
            return {}, {}
        targets.append(target)
        target_pk_map[name] = target.pk

    mod_lookup = CharacterModifier.objects.totals_by_character_for_targets(targets)
    return mod_lookup, target_pk_map


def _select_pools_to_regen(  # noqa: PLR0913 - regen computation needs full pool context
    pools: list,
    *,
    base_regen: int,
    locked_character_ids: set[int],
    mod_lookup: dict,
    regen_pk: int | None,
    max_pk: int | None,
) -> list:
    """Apply effective regen to each eligible pool and collect those that changed.

    Skips protagonism-locked characters and pools already at/over their
    effective maximum or with zero effective regen. Mutates ``pool.current``
    in place on the pools that regenerate and returns that list.
    """
    to_update = []
    for pool in pools:
        if pool.character_id in locked_character_ids:
            continue

        mods = mod_lookup.get(pool.character_id, {})
        effective_regen = max(0, base_regen + (mods.get(regen_pk, 0) if regen_pk else 0))
        effective_max = max(1, pool.maximum + (mods.get(max_pk, 0) if max_pk else 0))

        if pool.current >= effective_max or effective_regen == 0:
            continue

        pool.current = min(effective_max, pool.current + effective_regen)
        to_update.append(pool)
    return to_update


def _apply_ap_regen(regen_target_name: str, base_regen: int, *, stamp_daily: bool = False) -> int:
    """Shared batch regen logic for daily and weekly AP regeneration.

    Fetches all pools, computes per-character effective regen/max with modifiers,
    and bulk-updates in 3 queries total. Returns the number of pools updated.

    Protagonism-locked characters (terminal corruption stage 5) are skipped
    silently — their AP does not regenerate while subsumed.

    With ``stamp_daily``, regenerated pools also get ``last_daily_regen``
    set to now (admin-display field; the scheduler's ScheduledTaskRecord
    remains the authoritative timing record).
    """
    from django.utils import timezone

    from world.action_points.models import ActionPointPool
    from world.conditions.models import ConditionInstance

    pools = list(ActionPointPool.objects.all())
    if not pools:
        return 0

    # Resolve the set of character ObjectDB PKs whose sheet is protagonism-locked.
    # One query: ConditionInstance rows where the target is at stage 5 of a Corruption condition.
    locked_character_ids: set[int] = set(
        ConditionInstance.objects.filter(
            condition__corruption_resonance__isnull=False,
            current_stage__stage_order=5,
        ).values_list("target_id", flat=True)
    )

    mod_lookup, pks = _fetch_ap_modifier_map([regen_target_name, "ap_maximum"])
    regen_pk = pks.get(regen_target_name)
    max_pk = pks.get("ap_maximum")

    to_update: list[ActionPointPool] = _select_pools_to_regen(
        pools,
        base_regen=base_regen,
        locked_character_ids=locked_character_ids,
        mod_lookup=mod_lookup,
        regen_pk=regen_pk,
        max_pk=max_pk,
    )

    if to_update:
        fields = ["current"]
        if stamp_daily:
            now = timezone.now()
            for pool in to_update:
                pool.last_daily_regen = now
            fields.append("last_daily_regen")
        ActionPointPool.objects.bulk_update(to_update, fields, batch_size=500)
    return len(to_update)


def batch_ap_daily_regen() -> None:
    """Apply daily AP regen to all character pools.

    The scheduler's ``ScheduledTaskRecord.last_run_at`` is the authoritative
    timing record; the pool-level ``last_daily_regen`` stamped here is for
    admin display only.
    """
    from world.action_points.models import ActionPointConfig

    base_regen = ActionPointConfig.get_daily_regen()
    count = _apply_ap_regen("ap_daily_regen", base_regen, stamp_daily=True)
    logger.info("AP daily regen: %d pools regenerated", count)


def batch_ap_weekly_regen() -> None:
    """Apply weekly AP regen to all character pools.

    Weekly timing is tracked by the scheduler's ``ScheduledTaskRecord``;
    there is no per-pool weekly timestamp (unlike ``last_daily_regen`` which
    exists for admin display of daily regen history).
    """
    from world.action_points.models import ActionPointConfig

    base_regen = ActionPointConfig.get_weekly_regen()
    count = _apply_ap_regen("ap_weekly_regen", base_regen)
    logger.info("AP weekly regen: %d pools regenerated", count)


def batch_journal_weekly_reset() -> None:
    """Reset stale weekly journal XP trackers for non-current game weeks."""
    from world.game_clock.week_services import get_current_game_week
    from world.journals.models import WeeklyJournalXP

    current_week = get_current_game_week()
    count = (
        WeeklyJournalXP.objects.exclude(game_week=current_week)
        .filter(
            models.Q(posts_this_week__gt=0)
            | models.Q(praised_this_week=True)
            | models.Q(was_praised_this_week=True)
            | models.Q(retorted_this_week=True)
            | models.Q(was_retorted_this_week=True),
        )
        .update(
            posts_this_week=0,
            praised_this_week=False,
            was_praised_this_week=False,
            retorted_this_week=False,
            was_retorted_this_week=False,
            game_week=current_week,
        )
    )
    logger.info("Journal weekly reset: %d trackers reset", count)


def batch_relationship_weekly_reset() -> None:
    """Reset stale weekly relationship counters for non-current game weeks."""
    from world.game_clock.week_services import get_current_game_week
    from world.relationships.models import CharacterRelationship

    current_week = get_current_game_week()
    count = (
        CharacterRelationship.objects.exclude(game_week=current_week)
        .filter(
            models.Q(developments_this_week__gt=0) | models.Q(changes_this_week__gt=0),
        )
        .update(
            developments_this_week=0,
            changes_this_week=0,
            game_week=current_week,
        )
    )
    logger.info("Relationship weekly reset: %d relationships reset", count)


def batch_form_expiration_cleanup() -> None:
    """Delete expired real-time temporary form changes."""
    from django.utils import timezone

    from world.forms.models import DurationType, TemporaryFormChange

    count, _ = TemporaryFormChange.objects.filter(
        duration_type=DurationType.REAL_TIME,
        expires_at__lt=timezone.now(),
    ).delete()
    logger.info("Form expiration cleanup: %d expired changes deleted", count)


def batch_condition_expiration_cleanup() -> None:
    """Delete expired time-based conditions."""
    from django.utils import timezone

    from world.conditions.models import ConditionInstance

    count, _ = ConditionInstance.objects.filter(
        expires_at__lt=timezone.now(),
    ).delete()
    logger.info("Condition expiration cleanup: %d expired conditions deleted", count)


def batch_relationship_temp_condition_cleanup() -> None:
    """Delete expired temporary relationship-conditions (Very Attracted drop-off) (#1697)."""
    from django.utils import timezone

    from world.relationships.models import TemporaryRelationshipCondition

    count, _ = TemporaryRelationshipCondition.objects.filter(
        expires_at__lt=timezone.now(),
    ).delete()
    logger.info("Relationship temp-condition cleanup: %d expired rows deleted", count)


def abandon_stale_ceremonies() -> None:
    """Auto-abandon OPEN ceremonies whose container has closed (#2289, Decision 12).

    Bounded per ADR-0131's no-open-ended-timers: an OPEN ceremony is abandoned
    when its linked scene has finished, its linked event has completed or been
    cancelled, or a real day has passed since it opened (the IC-day-rollover
    proxy) — whichever comes first. Abandonment awards nothing and closes the
    funeral ghost container.
    """
    from django.db.models import Q
    from django.utils import timezone

    from world.ceremonies.constants import CeremonyStatus
    from world.ceremonies.models import Ceremony
    from world.ceremonies.services import abandon_ceremony
    from world.events.constants import EventStatus

    cutoff = timezone.now() - timedelta(days=1)
    stale = Ceremony.objects.filter(status=CeremonyStatus.OPEN).filter(
        Q(scene__isnull=False, scene__date_finished__isnull=False)
        | Q(event__isnull=False, event__status__in=[EventStatus.COMPLETED, EventStatus.CANCELLED])
        | Q(opened_at__lt=cutoff)
    )
    count = 0
    for ceremony in stale:
        abandon_ceremony(ceremony=ceremony)
        count += 1
    if count:
        logger.info("Ceremony auto-abandon: %d stale rites closed", count)


def auto_settle_estates() -> None:
    """Settle estates past the window deadline (#1985) — the sweeper door.

    Player-first, timer-backed (spec Decision 2): the funeral and will-reading
    doors get the full window; if nobody acts, the estate resolves on its own
    so one idler never blocks everyone else's RP.
    """
    from django.utils import timezone

    from world.estates.constants import SettlementDoor, SettlementStatus
    from world.estates.models import EstateSettlement
    from world.estates.services import execute_settlement

    due = EstateSettlement.objects.filter(
        status=SettlementStatus.PENDING,
        deadline__lt=timezone.now(),
    ).select_related("character_sheet")
    count = 0
    for settlement in due:
        execute_settlement(settlement.character_sheet, via=SettlementDoor.AUTO)
        count += 1
    if count:
        logger.info("Estate sweeper: %d settlements executed", count)


def auto_retire_dead_characters() -> None:
    """Auto-retire dead characters past the grace window (#2287).

    The no-staff-needed backstop of the death off-ramp: a dead character whose
    player never fires ``retire`` is released ``auto_retire_days`` after death.
    """
    from django.utils import timezone

    from world.vitals.constants import CharacterLifeState
    from world.vitals.models import CharacterVitals
    from world.vitals.services import get_vitals_consequence_config, retire_character

    config = get_vitals_consequence_config()
    cutoff = timezone.now() - timedelta(days=config.auto_retire_days)
    stale = CharacterVitals.objects.filter(
        life_state=CharacterLifeState.DEAD,
        retired_at__isnull=True,
        died_at__lt=cutoff,
    ).select_related("character_sheet")
    count = 0
    for vitals in stale:
        retire_character(vitals.character_sheet)
        count += 1
    if count:
        logger.info("Auto-retire: %d dead characters released", count)


def register_all_tasks() -> None:
    """Register all periodic tasks with the scheduler."""
    register_task(
        CronDefinition(
            task_key="ap.daily_regen",
            callable=batch_ap_daily_regen,
            interval=timedelta(hours=24),
            description="Apply daily AP regeneration.",
        )
    )
    register_task(
        CronDefinition(
            task_key="ap.weekly_regen",
            callable=batch_ap_weekly_regen,
            interval=timedelta(days=7),
            description="Apply weekly AP regeneration.",
        )
    )
    register_task(
        CronDefinition(
            task_key="journals.weekly_reset",
            callable=batch_journal_weekly_reset,
            interval=timedelta(hours=24),
            description="Batch-reset stale weekly journal XP trackers.",
        )
    )
    register_task(
        CronDefinition(
            task_key="relationships.weekly_reset",
            callable=batch_relationship_weekly_reset,
            interval=timedelta(hours=24),
            description="Reset stale weekly relationship counters.",
        )
    )
    register_task(
        CronDefinition(
            task_key="forms.expiration_cleanup",
            callable=batch_form_expiration_cleanup,
            interval=timedelta(hours=1),
            description="Delete expired real-time temporary form changes.",
        )
    )
    register_task(
        CronDefinition(
            task_key="conditions.expiration_cleanup",
            callable=batch_condition_expiration_cleanup,
            interval=timedelta(hours=1),
            description="Delete expired time-based conditions.",
        )
    )
    register_task(
        CronDefinition(
            task_key="relationships.temp_condition_cleanup",
            callable=batch_relationship_temp_condition_cleanup,
            interval=timedelta(hours=1),
            description="Delete expired temporary relationship-conditions (Very Attracted).",
        )
    )

    from world.secrets.gossip import gossip_decay_tick

    register_task(
        CronDefinition(
            # Decay regional gossip heat toward the floor (#1572). Cadence is a PLACEHOLDER —
            # the spec's intent is ~1 per IC day; 24h-real matches the other daily sweeps and
            # is tunable in Apostate's later magnitude pass.
            task_key="secrets.gossip_decay",
            callable=gossip_decay_tick,
            interval=timedelta(hours=24),
            description="Decay regional gossip heat by 1 toward the floor (#1572).",
        )
    )

    from world.justice.services import heat_decay_tick

    register_task(
        CronDefinition(
            # Decay persona pursuit heat toward zero and drop cold rows (#1765).
            # Cadence + magnitude are PLACEHOLDER for the tuning pass.
            task_key="justice.heat_decay",
            callable=heat_decay_tick,
            interval=timedelta(hours=24),
            description="Decay persona pursuit heat toward zero (#1765).",
        )
    )

    from world.scenes.tasks import block_finalize_task

    register_task(
        CronDefinition(
            task_key="scenes.block_finalize",
            callable=block_finalize_task,
            interval=timedelta(hours=1),
            description="Finalize player blocks whose lift grace period has elapsed (#1278).",
        )
    )

    from world.projects.services import scan_active_projects

    register_task(
        CronDefinition(
            task_key="projects.lifecycle_tick",
            callable=scan_active_projects,
            interval=timedelta(minutes=15),
            description=(
                "Scan ACTIVE Projects; transition completion-ready ones to RESOLVING. "
                "Interval is tunable; final cadence likely per-IC-day post-balance pass."
            ),
        )
    )

    from world.missions.services.cron import (
        apply_mission_reward_batch,
        resolve_expired_group_votes,
    )

    register_task(
        CronDefinition(
            task_key="missions.reward_batch",
            callable=apply_mission_reward_batch,
            interval=timedelta(hours=1),
            description=(
                "Apply queued POST_CRON mission rewards (LP/Resonance). Phase "
                "5b.2 stub-seals both grant entry points pending payload "
                "enrichment — see DESIGN §13.3."
            ),
        )
    )

    register_task(
        CronDefinition(
            task_key="missions.group_vote_sweep",
            callable=resolve_expired_group_votes,
            interval=timedelta(minutes=2),
            description=(
                "#1036 backstop: resolve group-decision nodes whose vote window "
                "elapsed with the party gone (the play surface resolves the common "
                "case lazily on access). Cheap when nothing is expired."
            ),
        )
    )

    # #676 Phase A: Renown decay (fame on personas, accumulated on orgs)
    from world.societies.tasks import register_all_tasks as register_renown_tasks

    register_renown_tasks()

    # #514 Outfits Phase C: seasonal trendsetter ceremony + vogue-momentum decay
    from world.items.tasks import register_all_tasks as register_fashion_tasks

    register_fashion_tasks()

    _register_weekly_money_tasks()

    # #1930: Weekly mothball sweep — long owner inactivity hides a
    # building from the grid and freezes its upkeep/condition accrual;
    # the owner's return restores it.
    from world.buildings.mothball_services import sweep_building_mothballs

    register_task(
        CronDefinition(
            task_key="buildings.mothball_sweep",
            callable=sweep_building_mothballs,
            interval=timedelta(days=7),
            description=(
                "Weekly mothball sweep: hide buildings whose owners have "
                "been inactive 90+ days (freeze accrual); restore them on "
                "the owner's return."
            ),
        )
    )

    from world.fatigue.tasks import fatigue_dawn_reset_task

    register_task(
        CronDefinition(
            task_key="fatigue.dawn_reset",
            callable=fatigue_dawn_reset_task,
            interval=timedelta(hours=8),
            description="Reset fatigue pools at IC dawn.",
        )
    )

    from world.combat.tasks import check_and_resolve_timed_encounters

    register_task(
        CronDefinition(
            task_key="combat.timer_check",
            callable=check_and_resolve_timed_encounters,
            interval=timedelta(seconds=30),
            description="Auto-resolve expired timed combat rounds.",
        )
    )

    from world.conditions.services import batch_chronic_effect_tick, decay_all_conditions_tick
    from world.locations.tasks import decayed_modifier_cleanup_task
    from world.magic.services.anima import anima_regen_tick
    from world.magic.services.gain import resonance_daily_tick, resonance_weekly_settlement_tick

    register_task(
        CronDefinition(
            task_key="locations.decayed_modifier_cleanup",
            callable=decayed_modifier_cleanup_task,
            interval=timedelta(hours=24),
            description="Delete LocationStatModifier rows that have decayed to zero.",
        )
    )
    register_task(
        CronDefinition(
            task_key="magic.anima_regen_daily",
            callable=anima_regen_tick,
            interval=timedelta(hours=24),
            description=(
                "Daily anima pool regeneration (skips engaged characters and "
                "characters whose active condition stages carry blocks_anima_regen)."
            ),
        )
    )
    register_task(
        CronDefinition(
            task_key="conditions.decay_daily",
            callable=decay_all_conditions_tick,
            interval=timedelta(hours=24),
            description="Passive decay for conditions with passive_decay_per_day > 0.",
        )
    )
    register_task(
        CronDefinition(
            task_key="conditions.chronic_daily",
            callable=batch_chronic_effect_tick,
            interval=timedelta(hours=24),
            description="Long-term capped chronic-effect damage (slow poison, etc.).",
        )
    )
    register_task(
        CronDefinition(
            task_key="magic.resonance_daily",
            callable=resonance_daily_tick,
            interval=timedelta(hours=24),
            description="Daily resonance trickle (residence + outfit stub).",
        )
    )
    register_task(
        CronDefinition(
            task_key="magic.resonance_weekly_settlement",
            callable=resonance_weekly_settlement_tick,
            interval=timedelta(days=7),
            description=(
                "Weekly pose-endorsement settlement. Idempotent — only sheets with "
                "unsettled endorsements are processed."
            ),
        )
    )

    from world.skills.services import run_weekly_skill_cron

    register_task(
        CronDefinition(
            task_key="skills.weekly_training",
            callable=run_weekly_skill_cron,
            interval=timedelta(days=7),
            anchor_weekday=0,
            anchor_hour_utc=5,
            description=("Process deliberate skill-training allocations and apply weekly rust."),
        )
    )

    from world.magic.services.sanctum_cron import sanctum_resonance_generation_tick

    register_task(
        CronDefinition(
            task_key="sanctum.resonance_generation_tick",
            callable=sanctum_resonance_generation_tick,
            interval=timedelta(hours=24),
            description=(
                "Pay per-day Sanctum resonance income to woven weavers. Reads "
                "effective_value(room, resonance) for the cascade-summed pool "
                "× LEVEL_MULTIPLIERS[level-1] × K. Plan 4 §F."
            ),
        )
    )

    _register_room_ward_upkeep_task()

    _register_agriculture_tasks()

    # Unified weekly rollover — orchestrates all weekly systems in sequence.
    # Advances the GameWeek, then processes votes, random scenes, skills,
    # journals, relationships, and AP regen.
    register_task(
        CronDefinition(
            task_key="weekly_rollover",
            callable=weekly_rollover_task,
            interval=timedelta(days=7),
            # Sunday midnight EST (= Monday 05:00 UTC) — the Arx 1 rollover
            # moment, per Apostate's #932 ruling. EST fixed (no DST shift).
            anchor_weekday=0,
            anchor_hour_utc=5,
            # #2609: income lands before upkeep drains (ADR-0150).
            phase=CronPhase.ECONOMY,
            description="Weekly rollover: advance GameWeek and process all weekly systems.",
        )
    )
    # Lazy import: weather depends on game_clock.services, so import the callable here rather
    # than at module top to avoid an import cycle at registration time.
    from world.weather.tasks import roll_and_echo_weather

    _register_late_tasks(roll_and_echo_weather)


def _register_weekly_money_tasks() -> None:
    """Register the anchored weekly-money tasks that must run in band order.

    All three share the Sunday-rollover anchor and are ordered by ``CronPhase``
    (ADR-0150): building upkeep (UPKEEP) drains after income lands, and the
    Somehow Always Broke drain (#2613) runs in two bands around it — SNAPSHOT
    records each holder's opening balance BEFORE income, then DRAIN empties the
    purse down to just this week's income AFTER upkeep has paid. Extracted from
    ``register_all_tasks`` to keep it under the ruff PLR0915 statement limit.
    """
    # #1930: Weekly building-upkeep sweep — deducts upkeep from owner wallets;
    # misses accrue bounded arrears then slide the condition tier.
    from world.buildings.upkeep_services import apply_weekly_upkeep_all_buildings
    from world.currency.services import run_purse_drains, snapshot_purse_drains

    register_task(
        CronDefinition(
            task_key="buildings.weekly_upkeep",
            callable=apply_weekly_upkeep_all_buildings,
            interval=timedelta(days=7),
            # #2609: shares the rollover's anchor so upkeep and the economy
            # pass fall due in the same tick, and sits in UPKEEP so it drains
            # AFTER income lands (see ADR-0150). Both halves are required —
            # a phase only orders tasks that are already due together.
            anchor_weekday=0,
            anchor_hour_utc=5,
            phase=CronPhase.UPKEEP,
            description=(
                "Weekly upkeep sweep: all-or-nothing deduction from the "
                "owner wallet; misses accrue capped arrears then slide the "
                "building's condition tier; above-normal tiers dwell-decay."
            ),
        )
    )

    register_task(
        CronDefinition(
            task_key="currency.purse_drain_snapshot",
            callable=snapshot_purse_drains,
            interval=timedelta(days=7),
            anchor_weekday=0,
            anchor_hour_utc=5,
            phase=CronPhase.SNAPSHOT,
            description=(
                "Records each Somehow Always Broke holder's opening purse "
                "balance before weekly income lands."
            ),
        )
    )
    register_task(
        CronDefinition(
            task_key="currency.purse_drains",
            callable=run_purse_drains,
            interval=timedelta(days=7),
            anchor_weekday=0,
            anchor_hour_utc=5,
            phase=CronPhase.DRAIN,
            description=(
                "Drains each Somehow Always Broke holder's purse down to this "
                "week's income, after obligations have paid."
            ),
        )
    )


def _register_late_tasks(roll_and_echo_weather: object) -> None:
    """Register summons expiry, weather, and area quality cron tasks.

    Extracted from ``register_all_tasks`` to keep that function under the
    ruff PLR0915 statement limit.
    """
    from world.npc_services.summons import expire_summonses

    register_task(
        CronDefinition(
            task_key="npc_services.summons_expiry",
            callable=expire_summonses,
            interval=timedelta(minutes=5),
            description=(
                "#2050: expire past-due PENDING summonses. Each expiry counts "
                "as a refusal (affection drop + streak bump). Cheap when nothing "
                "is past due."
            ),
        )
    )
    register_task(
        CronDefinition(
            task_key="weather.roll",
            callable=roll_and_echo_weather,
            interval=timedelta(hours=2),
            description="Roll regional weather (every 2 real hrs ≈ 6 IC hrs) and echo to rooms.",
        )
    )
    register_task(
        CronDefinition(
            task_key="vitals.auto_retire",
            callable=auto_retire_dead_characters,
            interval=timedelta(hours=6),
            description="Auto-retire dead characters past the grace window (#2287).",
        )
    )
    register_task(
        CronDefinition(
            task_key="ceremonies.auto_abandon",
            callable=abandon_stale_ceremonies,
            interval=timedelta(hours=1),
            description="Auto-abandon OPEN ceremonies whose container closed (#2289).",
        )
    )
    register_task(
        CronDefinition(
            task_key="estates.auto_settle",
            callable=auto_settle_estates,
            interval=timedelta(hours=1),
            description="Settle estates past the window deadline (#1985).",
        )
    )
    _register_area_quality_decay_task()


def _register_room_ward_upkeep_task() -> None:
    """Register the daily ward resonance-upkeep tick (#2177).

    Extracted from ``register_all_tasks`` to keep that function under the
    ruff PLR0915 statement limit.
    """
    from world.room_features.services import room_ward_upkeep_tick

    register_task(
        CronDefinition(
            task_key="room_features.ward_upkeep_tick",
            callable=room_ward_upkeep_tick,
            interval=timedelta(hours=24),
            description=(
                "Drain each active RoomWardDetails.resonance_reserve by "
                "level * 5; lapse the ward (stops reacting, not dissolved) "
                "when depleted. #2177."
            ),
        )
    )


def _register_agriculture_tasks() -> None:
    """Register agriculture + roster cron tasks (#1864, #671).

    Extracted from ``register_all_tasks`` to keep that function under the
    ruff PLR0915 statement limit.
    """
    from world.agriculture.services import field_production_tick
    from world.roster.services.activity import sweep_activity_states

    register_task(
        CronDefinition(
            task_key="agriculture.field_production",
            callable=field_production_tick,
            interval=timedelta(hours=24),
            description="Daily Field production: accrue food into uncollected pools.",
        )
    )
    register_task(
        CronDefinition(
            task_key="roster.activity_sweep",
            callable=sweep_activity_states,
            interval=timedelta(days=7),
            description=(
                "Weekly inactivity-detection sweep (#671). Flips activity_state"
                " ACTIVE↔INACTIVE based on decay_tier and expires HIATUS when"
                " activity_state_until has passed."
            ),
        )
    )


def _register_area_quality_decay_task() -> None:
    """Register the weekly area quality decay/regain tick (#1889)."""
    from world.areas.cleanup_services import cleanup_quality_decay_tick

    register_task(
        CronDefinition(
            task_key="areas.quality_decay",
            callable=cleanup_quality_decay_tick,
            interval=timedelta(days=7),
            description=(
                "Weekly area quality sweep: decay above-normal quality "
                "after CLEANUP_DWELL_DAYS; regain below-normal quality "
                "after CLEANUP_REGAIN_WEEKS. #1889."
            ),
        )
    )
