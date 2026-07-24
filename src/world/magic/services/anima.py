"""Anima resource service functions for the magic system."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from django.db import transaction

from world.magic.models import CharacterAnima
from world.magic.types.ritual import AnimaRegenTickSummary, RitualOutcome

if TYPE_CHECKING:
    from evennia.accounts.models import AccountDB
    from evennia.objects.models import ObjectDB

    from world.character_sheets.models import CharacterSheet
    from world.magic.models.rituals import Ritual
    from world.roster.models import RosterEntry
    from world.scenes.models import Scene
    from world.skills.models import Skill
    from world.traits.models import Trait

logger = logging.getLogger(__name__)


def deduct_anima(character: ObjectDB, effective_cost: int, *, lethal: bool = True) -> int:
    """Deduct anima from character, returning the overburn deficit.

    Uses select_for_update inside transaction.atomic for race-condition
    safety, following the ActionPointPool.spend() pattern.
    Returns 0 if no overburn, positive int if life force is drawn.

    ``lethal`` defaults to ``True`` so existing callers are unaffected. In a
    NON-LETHAL encounter (``lethal=False``) the effective cost is clamped to the
    caster's currently available anima, so the deduction never draws life force
    past zero and the returned deficit is always ``0`` (no overburn).
    """
    if effective_cost <= 0:
        return 0

    with transaction.atomic():
        anima = CharacterAnima.objects.select_for_update().get(character=character)
        if not lethal:
            # Non-lethal: never spend past available anima — no life-force draw.
            effective_cost = min(effective_cost, anima.current)
        deficit = max(effective_cost - anima.current, 0)
        anima.current = max(anima.current - effective_cost, 0)
        anima.save(update_fields=["current"])
    return deficit


def get_character_anima_ritual(character):  # noqa: OBJECTDB_PARAM — Evennia character
    """The character's authored SCENE_ACTION ritual (with check_config), or None."""
    from world.magic.constants import RitualExecutionKind  # noqa: PLC0415
    from world.magic.models.rituals import Ritual  # noqa: PLC0415

    return (
        Ritual.objects.filter(
            author_account=character.db_account,
            execution_kind=RitualExecutionKind.SCENE_ACTION,
        )
        .select_related("check_config")
        .first()
    )


def get_character_cast_check(character):  # noqa: OBJECTDB_PARAM — Evennia character
    """The CheckType a character's technique casts roll, or None for fallback."""
    ritual = get_character_anima_ritual(character)
    if ritual is None or not hasattr(ritual, "check_config"):
        return None
    return ritual.check_config.check_type


def resolve_cast_check_type(character, template):  # noqa: OBJECTDB_PARAM — Evennia character
    """The CheckType a technique cast rolls, for EVERY cast path (ADR-0096).

    Precedence: the caster's provisioned personal magic check always wins;
    an ActionTemplate's ``check_type`` is a fallback, never an override.
    Returns None only when the caster is unprovisioned AND ``template`` is None
    (callers that require a concrete check guard ``template is None`` first).
    """
    personal = get_character_cast_check(character)
    if personal is not None:
        return personal
    return template.check_type if template is not None else None


@transaction.atomic
def perform_anima_ritual(
    character_sheet: CharacterSheet,
    scene: Scene,
) -> RitualOutcome:
    """Perform the character's personalised anima ritual once per scene.

    Scope 6 §5.1. Outcome-tiered recovery budget: reduce Soulfray severity
    first at ritual_severity_cost_per_point per point, then refill anima
    with leftover budget. Crit always tops anima to max regardless.
    """
    from world.checks.services import perform_check  # noqa: PLC0415
    from world.magic.exceptions import (  # noqa: PLC0415
        CharacterEngagedForRitual,
        NoRitualConfigured,
        RitualAlreadyPerformedThisScene,
        RitualScenePrerequisiteFailed,
    )
    from world.magic.models.anima import AnimaRitualPerformance  # noqa: PLC0415
    from world.mechanics.engagement import CharacterEngagement  # noqa: PLC0415

    character = character_sheet.character
    ritual = get_character_anima_ritual(character)
    if ritual is None or not hasattr(ritual, "check_config"):
        raise NoRitualConfigured

    config = ritual.check_config
    if config.check_type is None:
        raise NoRitualConfigured

    if CharacterEngagement.objects.filter(character=character).exists():
        raise CharacterEngagedForRitual

    if not scene.is_active or not _scene_participant(scene, character):
        raise RitualScenePrerequisiteFailed

    if AnimaRitualPerformance.objects.filter(ritual=ritual, scene=scene).exists():
        raise RitualAlreadyPerformedThisScene

    check_result = perform_check(
        character,
        check_type=config.check_type,
        target_difficulty=config.target_difficulty,
    )
    outcome = check_result.outcome

    return apply_anima_ritual_outcome(
        ritual=ritual,
        outcome=outcome,
        scene=scene,
        character_sheet=character_sheet,
    )


def apply_anima_ritual_outcome(
    *,
    ritual: Ritual,
    outcome: object,
    scene: Scene,
    character_sheet: CharacterSheet,
) -> RitualOutcome:
    """Apply a pre-computed check outcome to anima/soulfray + create audit row.

    Extracted from perform_anima_ritual() so SceneActionRequest can drive the
    check and pass the outcome here.

    Args:
        ritual: The Ritual (SCENE_ACTION kind) being performed.
        outcome: The check outcome / result object (must have success_level).
        scene: The scene in which the ritual is performed.
        character_sheet: The character performing the ritual.

    Returns:
        RitualOutcome describing what was recovered and reduced.
    """
    from world.conditions.models import ConditionInstance, ConditionTemplate  # noqa: PLC0415
    from world.conditions.services import decay_condition_severity  # noqa: PLC0415
    from world.magic.audere import SOULFRAY_CONDITION_NAME  # noqa: PLC0415
    from world.magic.models.anima import AnimaRitualPerformance  # noqa: PLC0415
    from world.magic.models.soulfray import SoulfrayConfig  # noqa: PLC0415

    character = character_sheet.character

    config = SoulfrayConfig.objects.cached_singleton()
    budget = _budget_for_outcome(outcome)

    anima = CharacterAnima.objects.select_for_update().get(character=character)

    soulfray_template = ConditionTemplate.get_by_name(SOULFRAY_CONDITION_NAME)
    soulfray_inst = (
        ConditionInstance.objects.select_for_update()
        .filter(target=character, condition=soulfray_template, resolved_at__isnull=True)
        .first()
    )

    severity_reduced = 0
    soulfray_resolved = False
    stage_after = None
    if soulfray_inst is not None:
        stage_after = soulfray_inst.current_stage
        while budget >= config.ritual_severity_cost_per_point and soulfray_inst.severity > 0:
            decay_result = decay_condition_severity(soulfray_inst, amount=1)
            severity_reduced += 1
            budget -= config.ritual_severity_cost_per_point
            stage_after = decay_result.new_stage
            if decay_result.resolved:
                soulfray_resolved = True
                break

    # Chosen patronage favor bonus (#2550): additive to the leftover budget
    # after soulfray reduction, before the anima refill. Both call paths
    # (perform_anima_ritual direct + _resolve_anima_ritual web) converge here.
    from world.worship.services import (  # noqa: PLC0415
        best_patronage_favor,
        get_chosen_favor_config,
    )

    favor = best_patronage_favor(character_sheet)
    chosen_config = get_chosen_favor_config()
    if favor >= chosen_config.anima_recovery_threshold:
        budget += chosen_config.anima_recovery_bonus

    anima_before = anima.current
    anima.current = min(anima.current + max(0, budget), anima.maximum)

    success_level = int(outcome.success_level)  # type: ignore[union-attr]
    if success_level >= 2:  # noqa: PLR2004 - chart success degrees
        anima.current = anima.maximum

    anima.save(update_fields=["current"])
    anima_recovered = anima.current - anima_before

    performance = AnimaRitualPerformance.objects.create(
        ritual=ritual,
        scene=scene,
        was_successful=success_level >= 1,
        anima_recovered=anima_recovered,
        outcome=outcome,
        severity_reduced=severity_reduced,
        target_character=None,
    )

    return RitualOutcome(
        performance=performance,
        outcome=outcome,  # type: ignore[arg-type]
        severity_reduced=severity_reduced,
        anima_recovered=anima_recovered,
        soulfray_stage_after=stage_after,
        soulfray_resolved=soulfray_resolved,
    )


@transaction.atomic
def provision_player_anima_ritual(  # noqa: PLR0913
    account: AccountDB,
    character_sheet: CharacterSheet,
    roster_entry: RosterEntry,
    *,
    ritual_name: str,
    stat: Trait | None = None,
    skill: Skill | None = None,
) -> Ritual | None:
    """Create a SCENE_ACTION Ritual + sidecar + CharacterRitualKnowledge for a player.

    Called during character creation finalization (Phase 8 §8.1; explicit
    stat/skill wiring #2426). When ``stat``/``skill`` are provided (the
    player's CG Anima Check pick), they are used as-is — no default
    resolution. When omitted (legacy/test-only callers), falls back to
    Willpower for the stat and the character's highest-valued skill (or the
    first active skill) for the skill. Both can be changed post-CG via the
    ritual management UI. Description and narrative prose are derived from
    ``ritual_name``.

    Returns the created Ritual, or None when no suitable stat/skill can be
    resolved (logged as a warning — finalization is not blocked).

    Args:
        account: The player account (author_account on the Ritual).
        character_sheet: The character's CharacterSheet.
        roster_entry: The character's RosterEntry (for CharacterRitualKnowledge).
        ritual_name: Name for the Ritual row (also seeds description/narrative prose).
        stat: Explicit Anima Check stat; falls back to Willpower when None.
        skill: Explicit Anima Check skill; falls back to the character's
            highest-valued skill (or first active skill) when None.
    """
    from world.magic.constants import RitualExecutionKind  # noqa: PLC0415
    from world.magic.models import CharacterRitualKnowledge  # noqa: PLC0415
    from world.magic.models.ritual_check_config import RitualCheckConfig  # noqa: PLC0415
    from world.magic.models.rituals import Ritual  # noqa: PLC0415
    from world.skills.models import CharacterSkillValue, Skill  # noqa: PLC0415
    from world.traits.models import Trait, TraitType  # noqa: PLC0415

    character = character_sheet.character

    # 1. Resolve stat — explicit CG pick wins; else default to Willpower.
    stat_trait = stat
    if stat_trait is None:
        try:
            stat_trait = Trait.objects.get(name="willpower", trait_type=TraitType.STAT)
        except Trait.DoesNotExist:
            logger.warning(
                "provision_player_anima_ritual: Willpower stat not found; skipping ritual "
                "creation for character %s",
                character.pk,
            )
            return None

    # 2. Resolve skill — explicit CG pick wins; else the character's highest CG
    #    skill value.
    if skill is None:
        skill_value = (
            CharacterSkillValue.objects.filter(character_id=character.pk).order_by("-value").first()
        )
        if skill_value is not None:
            skill = skill_value.skill
        else:
            # Fallback: first active skill in the database (edge case for test accounts).
            skill = Skill.objects.filter(is_active=True).first()

    if skill is None:
        logger.warning(
            "provision_player_anima_ritual: No skill available; skipping ritual "
            "creation for character %s",
            character.pk,
        )
        return None

    # 3. Create the Ritual row (no service_function_path, no flow — SCENE_ACTION).
    # Description and narrative prose are placeholder text editable post-CG.
    ritual = Ritual.objects.create(
        name=ritual_name,
        description=(
            "A personal ritual for restoring anima. "
            "Edit this description to match your character's practice."
        ),
        narrative_prose=f"{ritual_name} is performed to restore anima.",
        execution_kind=RitualExecutionKind.SCENE_ACTION,
        service_function_path="",
        author_account=account,
    )

    # 4. Synthesize the character's personal magic check (#1306) — rolled by this
    # ritual AND by the character's technique casts. Idempotent.
    from world.magic.seeds_checks import (  # noqa: PLC0415
        ensure_character_magic_check_type,
    )

    check_type = ensure_character_magic_check_type(character_sheet, stat=stat_trait, skill=skill)

    RitualCheckConfig.objects.create(
        ritual=ritual,
        stat=stat_trait,
        skill=skill,
        check_type=check_type,
    )

    # 5. Grant knowledge so the ritual appears in the scene action menu.
    CharacterRitualKnowledge.objects.get_or_create(
        roster_entry=roster_entry,
        ritual=ritual,
        defaults={"learned_from": None},
    )

    return ritual


def has_performed_anima_ritual_in_scene(
    *,
    ritual: Ritual,
    scene: Scene,
) -> bool:
    """Return True when the given ritual has already been performed in this scene.

    Used by the menu contributor to enforce the once-per-scene cap without
    re-running the full gate logic in perform_anima_ritual().
    """
    from world.magic.models.anima import AnimaRitualPerformance  # noqa: PLC0415

    return AnimaRitualPerformance.objects.filter(ritual=ritual, scene=scene).exists()


def _budget_for_outcome(outcome: object) -> int:
    """Return the anima/severity budget for an outcome row.

    Raises AnimaRitualBudgetAward.DoesNotExist if the tier has no authored row —
    every one of the 5 canonical CheckOutcome tiers must be seeded (unlike
    GangTurfReputationAward's "missing row = 0" convention; a missing anima
    budget must not silently grant 0 recovery on a legitimate ritual attempt).
    """
    from world.magic.models.soulfray import AnimaRitualBudgetAward  # noqa: PLC0415

    return AnimaRitualBudgetAward.objects.get(outcome_tier=outcome).budget


def _scene_participant(scene: Scene, character: ObjectDB) -> bool:
    """Return True when *character*'s account has a SceneParticipation in *scene*.

    Mirrors conditions.services._scene_participant — same roster-tenure path.
    """
    from world.roster.models import RosterEntry  # noqa: PLC0415
    from world.scenes.models import SceneParticipation  # noqa: PLC0415

    try:
        entry = RosterEntry.objects.get(character_sheet_id=character.pk)
    except RosterEntry.DoesNotExist:
        return False
    tenure = entry.tenures.filter(end_date__isnull=True).first()
    if tenure is None:
        return False
    account_id = tenure.player_data.account_id
    return SceneParticipation.objects.filter(scene=scene, account_id=account_id).exists()


def anima_regen_tick() -> AnimaRegenTickSummary:
    """Scheduler entry point. Daily anima regen across all characters.

    Per spec §5.5. Skips engaged characters and characters whose active
    condition stages carry the blocking Property. Skip sets are bulk-
    fetched in 2 queries before the loop to avoid N+1.
    """
    from django.db.models import F  # noqa: PLC0415, I001
    from world.conditions.models import ConditionInstance  # noqa: PLC0415
    from world.magic.models.anima import AnimaConfig  # noqa: PLC0415
    from world.mechanics.engagement import CharacterEngagement  # noqa: PLC0415
    from world.mechanics.models import Property  # noqa: PLC0415

    config = AnimaConfig.get_singleton()
    blocker = Property.objects.get(name=config.daily_regen_blocking_property_key)

    engaged_ids = set(
        CharacterEngagement.objects.values_list("character_id", flat=True),
    )
    blocked_ids = set(
        ConditionInstance.objects.filter(
            resolved_at__isnull=True,
            current_stage__properties=blocker,
        )
        .values_list("target_id", flat=True)
        .distinct(),
    )

    qs = CharacterAnima.objects.filter(
        current__lt=F("maximum"),
    ).select_related("character")

    examined = 0
    regenerated = 0
    engagement_blocked = 0
    condition_blocked = 0
    to_update = []

    for row in qs:
        examined += 1
        char_id = row.character_id
        if char_id in engaged_ids:
            engagement_blocked += 1
            continue
        if char_id in blocked_ids:
            condition_blocked += 1
            continue
        regen = (row.maximum * config.daily_regen_percent) // 100
        if regen <= 0:
            continue
        row.current = min(row.current + regen, row.maximum)
        to_update.append(row)
        regenerated += 1

    # Bulk update all at once
    if to_update:
        CharacterAnima.objects.bulk_update(to_update, ["current"], batch_size=1000)

    return AnimaRegenTickSummary(
        examined=examined,
        regenerated=regenerated,
        engagement_blocked=engagement_blocked,
        condition_blocked=condition_blocked,
    )
