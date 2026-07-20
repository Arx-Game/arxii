"""Worship service functions (#2355).

The single write paths for worship: ceremonies (#2289) and future worship acts
call ``grant_worship`` (being pool + ledger) and ``bump_devotion`` (PC↔god
standing + the God's Favorite achievement check). Explicit calls, no signals.
"""

from typing import TYPE_CHECKING

from django.db.models import Max

from world.worship.constants import (
    GODS_FAVORITE_CHOSEN,
    GODS_FAVORITE_PRINCE,
    GODS_FAVORITE_PRINCESS,
)
from world.worship.models import DevotionStanding, WorshipGrant, WorshippedBeing

if TYPE_CHECKING:
    from world.achievements.models import Achievement
    from world.character_sheets.models import CharacterSheet
    from world.worship.models import DivineInterventionConfig, Miracle, MiraclePerformance


def grant_worship(
    being: WorshippedBeing,
    amount: int,
    *,
    granted_by: "CharacterSheet | None" = None,
    reason: str = "",
) -> WorshipGrant:
    """Add worship to a being's pool and record the audit ledger row."""
    if amount <= 0:
        msg = "Worship grants must be a positive amount."
        raise ValueError(msg)
    being.resonance_pool += amount
    being.lifetime_worship += amount
    being.save(update_fields=["resonance_pool", "lifetime_worship"])
    return WorshipGrant.objects.create(
        being=being, amount=amount, granted_by=granted_by, reason=reason
    )


def gods_favorite_achievement_for(character_sheet: "CharacterSheet") -> "Achievement | None":
    """Resolve the gender-matched God's Favorite achievement row (Decision 6).

    ``female`` → Princess, ``male`` → Prince, anything else (nonbinary keys,
    unspecified, or no gender row) → Chosen. Returns None when the achievement
    rows aren't seeded (bare test DB) — callers skip gracefully.
    """
    from world.achievements.models import Achievement  # noqa: PLC0415

    gender_key = character_sheet.gender.key if character_sheet.gender_id else ""
    name = {
        "female": GODS_FAVORITE_PRINCESS,
        "male": GODS_FAVORITE_PRINCE,
    }.get(gender_key, GODS_FAVORITE_CHOSEN)
    return Achievement.objects.filter(name=name, is_active=True).first()


def bump_devotion(
    character_sheet: "CharacterSheet", being: WorshippedBeing, amount: int
) -> DevotionStanding:
    """Upsert the (sheet, being) standing and run the God's Favorite check.

    Becoming — or tying — the top ``favor`` holder for the being grants the
    gender-matched achievement (leapfroggers earn it too; earlier holders keep
    theirs; ``grant_achievement`` is idempotent per sheet).
    """
    standing, _ = DevotionStanding.objects.get_or_create(
        character_sheet=character_sheet, being=being
    )
    standing.favor += amount
    standing.lifetime_favor += max(amount, 0)
    standing.save(update_fields=["favor", "lifetime_favor"])

    top_other = (
        (
            DevotionStanding.objects.filter(being=being)
            .exclude(pk=standing.pk)
            .aggregate(top=Max("favor"))["top"]
        )
        or 0
    )
    if standing.favor >= top_other:
        achievement = gods_favorite_achievement_for(character_sheet)
        if achievement is not None:
            from world.achievements.services import grant_achievement  # noqa: PLC0415

            grant_achievement(achievement, [character_sheet])

    # Divine intervention trigger installation/removal (#2360)
    cfg = get_divine_intervention_config()
    if standing.favor >= cfg.favor_threshold:
        install_divine_intervention_trigger(character_sheet, being)
    else:
        remove_divine_intervention_trigger(character_sheet, being)

    return standing


def get_divine_intervention_config() -> "DivineInterventionConfig":
    """Lazy-create the singleton (pk=1) divine intervention config (#2360)."""
    from world.worship.models import DivineInterventionConfig  # noqa: PLC0415

    cfg = DivineInterventionConfig.objects.cached_singleton()
    if cfg is None:
        cfg = DivineInterventionConfig.objects.create(pk=1)
    return cfg


def spend_worship_pool(being: WorshippedBeing, amount: int, *, reason: str = "") -> bool:  # noqa: ARG001
    """Deduct ``amount`` from ``being.resonance_pool`` (the spend counterpart to ``grant_worship``).

    Returns ``True`` if the deduction succeeded, ``False`` if the pool was
    insufficient (no partial spend). Raises ``ValueError`` for non-positive amounts.
    Does NOT create an audit row — the caller creates ``MiraclePerformance``.
    """
    if amount <= 0:
        msg = "Worship pool spends must be a positive amount."
        raise ValueError(msg)
    # Re-fetch with lock to avoid race on concurrent miracles.
    locked = WorshippedBeing.objects.select_for_update().filter(pk=being.pk).first()
    if locked is None or locked.resonance_pool < amount:
        return False
    locked.resonance_pool -= amount
    locked.save(update_fields=["resonance_pool"])
    # Propagate to the in-memory instance the caller holds.
    being.resonance_pool = locked.resonance_pool
    return True


# =============================================================================
# Divine intervention (#2360)
# =============================================================================

_DIVINE_INTERVENTION_TRIGGER_NAME = "divine_intervention_on_incapacitated"
_DIVINE_INTERVENTION_COOLDOWN_NAME = "Divine Intervention Cooldown"


def _broadcast_miracle_narrative(character, text: str, scene=None) -> None:
    """Broadcast miracle narrative as an EMIT to the active scene.

    No-ops when no scene or no primary persona. Mirrors ``_broadcast_manifestation``
    in ``world/magic/audere_majora.py``.
    """
    from world.scenes.constants import InteractionMode  # noqa: PLC0415
    from world.scenes.interaction_services import (  # noqa: PLC0415
        create_interaction,
        push_interaction,
    )
    from world.scenes.models import Persona, Scene  # noqa: PLC0415

    if scene is None:
        scene = Scene.objects.active_for_room(character.location).first()
    if scene is None:
        return

    try:
        persona = character.sheet_data.primary_persona
    except (AttributeError, Persona.DoesNotExist):
        return

    interaction = create_interaction(
        persona=persona,
        content=text,
        mode=InteractionMode.EMIT,
        scene=scene,
    )
    push_interaction(
        interaction,
        receiver_persona_ids=[],
        target_persona_ids=[],
        receiver_characters=[],
    )


def perform_divine_intervention(
    character_sheet: "CharacterSheet",
    being: WorshippedBeing,
    miracle: "Miracle",
    *,
    scene=None,
) -> "MiraclePerformance":
    """Commit seam for a divine intervention: spend pool, apply conditions, audit.

    Called by ``maybe_fire_divine_intervention``. Assumes eligibility is already
    verified (favor threshold, pool sufficient, cooldown clear).
    """
    from django.db import transaction  # noqa: PLC0415

    from world.conditions.services import apply_condition  # noqa: PLC0415
    from world.worship.models import MiraclePerformance  # noqa: PLC0415

    character = character_sheet.character

    with transaction.atomic():
        spend_worship_pool(being, miracle.resonance_pool_cost, reason="divine_intervention")

        # Apply each MiracleAppliedCondition row directly via apply_condition.
        # Miracles have no technique context, so apply_technique_conditions is
        # not used — only base_severity and base_duration_rounds contribute.
        for row in miracle.condition_applications.select_related("condition"):
            apply_condition(
                target=character,
                condition=row.condition,
                severity=row.base_severity,
                duration_rounds=row.base_duration_rounds,
            )

        performance = MiraclePerformance.objects.create(
            miracle=miracle,
            being=being,
            target_character=character_sheet,
            scene=scene,
            resonance_spent=miracle.resonance_pool_cost,
            trigger_event="character_incapacitated",
        )

    # Broadcast narrative (outside transaction, mirrors _broadcast_manifestation)
    _broadcast_miracle_narrative(character, miracle.narrative_text, scene)

    return performance


def maybe_fire_divine_intervention(character, payload=None) -> None:  # noqa: ARG001
    """Trigger handler: fire a divine miracle when a high-devotion PC is incapacitated.

    Called by the ``divine_intervention_on_incapacitated`` TriggerDefinition's
    ``CALL_SERVICE_FUNCTION`` flow step. The ``payload`` is a
    ``CharacterIncapacitatedPayload`` (unused — the character is the trigger's ``obj``).
    """
    from world.character_sheets.models import CharacterSheet  # noqa: PLC0415
    from world.conditions.models import ConditionInstance  # noqa: PLC0415
    from world.worship.constants import MiracleTrigger  # noqa: PLC0415
    from world.worship.models import Miracle  # noqa: PLC0415

    sheet = CharacterSheet.objects.filter(character=character).first()
    if sheet is None:
        return

    cfg = get_divine_intervention_config()

    # Cooldown check
    if ConditionInstance.objects.filter(
        target=character,
        condition__name=_DIVINE_INTERVENTION_COOLDOWN_NAME,
    ).exists():
        return

    # Find qualifying (being, miracle) pairs.
    standings = DevotionStanding.objects.filter(
        character_sheet=sheet,
    ).select_related("being")

    candidates: list[tuple] = []
    for standing in standings:
        if standing.favor < cfg.favor_threshold:
            continue
        miracles = Miracle.objects.filter(
            being=standing.being,
            intervention_trigger=MiracleTrigger.INCAPACITATED,
            is_active=True,
            favor_threshold__lte=standing.favor,
        )
        candidates.extend(
            (standing, miracle)
            for miracle in miracles
            if standing.being.resonance_pool
            >= max(miracle.resonance_pool_cost, cfg.min_pool_for_intervention)
        )

    if not candidates:
        return

    # Pick highest-priority (lowest sort_order).
    candidates.sort(key=lambda pair: pair[1].sort_order)
    standing, miracle = candidates[0]

    # Resolve scene.
    from world.scenes.models import Scene  # noqa: PLC0415

    scene = Scene.objects.active_for_room(character.location).first()

    # Perform the miracle.
    perform_divine_intervention(sheet, standing.being, miracle, scene=scene)

    # Apply cooldown condition.
    from world.conditions.models import ConditionTemplate  # noqa: PLC0415
    from world.conditions.services import apply_condition as _apply  # noqa: PLC0415

    cooldown_template = ConditionTemplate.objects.filter(
        name=_DIVINE_INTERVENTION_COOLDOWN_NAME,
    ).first()
    if cooldown_template is not None:
        _apply(
            target=character,
            condition=cooldown_template,
            duration_rounds=cfg.cooldown_hours * 60,
        )


def install_divine_intervention_trigger(
    character_sheet: "CharacterSheet",
    being: WorshippedBeing,  # noqa: ARG001
) -> None:
    """Install the divine intervention Trigger on the character's ObjectDB.

    Idempotent — ``get_or_create`` on (obj, trigger_definition). Called from
    ``bump_devotion`` when favor crosses the config threshold. Mirrors the
    Soul Tether trigger installation pattern (soul_tether.py:316).
    """
    from flows.models import Trigger, TriggerDefinition  # noqa: PLC0415

    trigger_def = TriggerDefinition.objects.filter(
        name=_DIVINE_INTERVENTION_TRIGGER_NAME,
    ).first()
    if trigger_def is None:
        return  # Content not seeded; no-op.

    character = character_sheet.character
    trigger, created = Trigger.objects.get_or_create(
        obj=character,
        trigger_definition=trigger_def,
    )
    if created:
        handler = character.trigger_handler
        if handler is not None:
            handler.on_trigger_added(trigger)


def remove_divine_intervention_trigger(
    character_sheet: "CharacterSheet",
    being: WorshippedBeing,  # noqa: ARG001
) -> None:
    """Remove the divine intervention trigger when favor drops below threshold."""
    from flows.models import Trigger, TriggerDefinition  # noqa: PLC0415

    trigger_def = TriggerDefinition.objects.filter(
        name=_DIVINE_INTERVENTION_TRIGGER_NAME,
    ).first()
    if trigger_def is None:
        return

    character = character_sheet.character
    Trigger.objects.filter(
        obj=character,
        trigger_definition=trigger_def,
    ).delete()
