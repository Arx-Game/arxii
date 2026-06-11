"""Audere threshold configuration and lifecycle management."""

from __future__ import annotations

from dataclasses import dataclass

from django.db import models, transaction
from evennia.objects.models import ObjectDB
from evennia.utils.idmapper.models import SharedMemoryModel

AUDERE_CONDITION_NAME = "Audere"
AUDERE_MAJORA_CONDITION_NAME = "Audere Majora"
SOULFRAY_CONDITION_NAME = "Soulfray"


class AudereThreshold(SharedMemoryModel):
    """Configuration for when Audere can be triggered and its effects.

    Expected to have a single row (global config). Modeled as a table
    for factory/test flexibility and admin editability.

    Audere requires a hard triple gate:
    1. Runtime intensity at or above minimum_intensity_tier
    2. Active Soulfray condition at or above minimum_warp_stage
    3. Active CharacterEngagement (character must be in stakes)
    """

    minimum_intensity_tier = models.ForeignKey(
        "magic.IntensityTier",
        on_delete=models.PROTECT,
        help_text="Runtime intensity must reach this tier for Audere to trigger.",
    )
    minimum_warp_stage = models.ForeignKey(
        "conditions.ConditionStage",
        on_delete=models.PROTECT,
        help_text="Soulfray must be at this stage or higher.",
    )
    intensity_bonus = models.IntegerField(
        help_text="Added to engagement.intensity_modifier when Audere activates.",
    )
    anima_pool_bonus = models.PositiveIntegerField(
        help_text="Temporary increase to CharacterAnima.maximum during Audere.",
    )
    # Deprecated: no longer used by Soulfray severity calculation (Scope #3).
    # Audere naturally drives high Soulfray via intensity boost. Can be removed.
    warp_multiplier = models.PositiveIntegerField(
        default=2,
        help_text="Soulfray severity increment multiplier during Audere (deprecated field name).",
    )

    class Meta:
        verbose_name = "Audere Threshold"
        verbose_name_plural = "Audere Thresholds"

    def __str__(self) -> str:
        return (
            f"Audere: tier≥{self.minimum_intensity_tier}, "
            f"warp≥{self.minimum_warp_stage}, "
            f"+{self.intensity_bonus} intensity"
        )


class PendingAudereOffer(SharedMemoryModel):
    """A poll-able Audere offer awaiting the player's accept/decline (#873).

    Created by ``maybe_create_audere_offer`` when the eligibility gate opens
    during a cast; deleted on respond, on staleness, or at encounter cleanup.
    Advisory text is never stored — it is computed at serialization time so the
    corruption warning is always current.
    """

    character_sheet = models.ForeignKey(
        "character_sheets.CharacterSheet",
        on_delete=models.CASCADE,
        related_name="audere_offers",
    )
    fired_intensity = models.PositiveIntegerField(
        help_text="Runtime intensity of the cast that opened the gate.",
    )
    soulfray_stage_order = models.PositiveSmallIntegerField(
        help_text="Soulfray stage order at fire time (display snapshot).",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["character_sheet"],
                name="one_pending_audere_per_character",
            ),
        ]

    def __str__(self) -> str:
        return (
            f"PendingAudereOffer(sheet={self.character_sheet_id}, intensity={self.fired_intensity})"
        )


@dataclass
class AudereOfferResult:
    """Result of an Audere offer decision."""

    accepted: bool
    intensity_bonus_applied: int = 0
    anima_pool_expanded_by: int = 0
    advisory_text: str = ""


def _check_intensity_gate(runtime_intensity: int, minimum_tier_threshold: int) -> bool:
    """Return True if runtime intensity resolves to a tier at or above minimum."""
    from world.magic.models import IntensityTier

    resolved_tier = (
        IntensityTier.objects.filter(threshold__lte=runtime_intensity)
        .order_by("-threshold")
        .first()
    )
    if resolved_tier is None:
        return False
    return resolved_tier.threshold >= minimum_tier_threshold


def _check_soulfray_gate(character: ObjectDB, minimum_stage_order: int) -> bool:
    """Return True if character has Soulfray at the required stage or higher."""
    from world.conditions.models import ConditionInstance

    soulfray_instance = (
        ConditionInstance.objects.filter(
            target=character,
            condition__name=SOULFRAY_CONDITION_NAME,
        )
        .select_related("current_stage")
        .first()
    )
    if soulfray_instance is None or soulfray_instance.current_stage is None:
        return False
    return soulfray_instance.current_stage.stage_order >= minimum_stage_order


def check_audere_eligibility(character: ObjectDB, runtime_intensity: int) -> bool:
    """Check whether a character meets all gates for Audere activation.

    Five gates -- all must be true:
    1. AudereThreshold config exists
    2. Runtime intensity resolves to a tier at or above the threshold's minimum
    3. Character has an active Soulfray at the required stage or higher
    4. Character has a CharacterEngagement
    5. Character is NOT already in Audere
    """
    from world.conditions.models import ConditionInstance
    from world.mechanics.engagement import CharacterEngagement

    threshold = AudereThreshold.objects.first()
    if threshold is None:
        return False

    has_engagement = CharacterEngagement.objects.filter(character=character).exists()
    already_in_audere = ConditionInstance.objects.filter(
        target=character,
        condition__name=AUDERE_CONDITION_NAME,
    ).exists()

    return (
        _check_intensity_gate(runtime_intensity, threshold.minimum_intensity_tier.threshold)
        and _check_soulfray_gate(character, threshold.minimum_warp_stage.stage_order)
        and has_engagement
        and not already_in_audere
    )


def corruption_advisory_for_character(character: ObjectDB) -> str:
    """Return a character-loss advisory string if the character has corruption at stage 3+.

    Returns an empty string when no advisory is warranted (no corruption at warning stages).
    Per spec §3.5: at stage 3+ the advisory must contain the explicit phrase "character loss".
    """
    from world.conditions.models import ConditionInstance

    instances = ConditionInstance.objects.filter(
        target=character,
        condition__corruption_resonance__isnull=False,
        current_stage__stage_order__gte=3,
    ).select_related("condition__corruption_resonance", "current_stage")
    resonance_names = [
        i.condition.corruption_resonance.name
        for i in instances
        if i.condition.corruption_resonance is not None
    ]
    if not resonance_names:
        return ""
    names = ", ".join(resonance_names)
    return (
        f"Entering Audere will accelerate corruption on {names} — "
        "character loss is possible if accumulated corruption advances to terminal stage."
    )


def offer_audere(character: ObjectDB, *, accept: bool) -> AudereOfferResult:
    """Process a player's Audere offer decision.

    If declined, returns immediately. If accepted, applies the Audere condition
    and grants intensity/anima bonuses within a transaction.
    """
    from world.conditions.models import ConditionTemplate
    from world.conditions.services import apply_condition
    from world.magic.models import CharacterAnima
    from world.mechanics.engagement import CharacterEngagement

    advisory = corruption_advisory_for_character(character)

    if not accept:
        return AudereOfferResult(accepted=False, advisory_text=advisory)

    threshold = AudereThreshold.objects.first()
    if threshold is None:
        return AudereOfferResult(accepted=False, advisory_text=advisory)

    audere_template = ConditionTemplate.get_by_name(AUDERE_CONDITION_NAME)

    with transaction.atomic():
        # Apply Audere condition
        apply_condition(target=character, condition=audere_template)

        # Boost engagement intensity modifier
        engagement = CharacterEngagement.objects.select_for_update().get(
            character=character,
        )
        engagement.intensity_modifier += threshold.intensity_bonus
        engagement.save(update_fields=["intensity_modifier"])

        # Expand anima pool
        anima = CharacterAnima.objects.select_for_update().get(character=character)
        anima.pre_audere_maximum = anima.maximum
        anima.maximum += threshold.anima_pool_bonus
        anima.save(update_fields=["pre_audere_maximum", "maximum"])

    return AudereOfferResult(
        accepted=True,
        intensity_bonus_applied=threshold.intensity_bonus,
        anima_pool_expanded_by=threshold.anima_pool_bonus,
        advisory_text=advisory,
    )


def end_audere(character: ObjectDB) -> None:
    """End Audere for a character, reverting all bonuses.

    Safe to call even if Audere is not active (no-op).
    """
    from world.conditions.models import ConditionTemplate
    from world.conditions.services import remove_condition
    from world.magic.models import CharacterAnima
    from world.mechanics.engagement import CharacterEngagement

    audere_template = ConditionTemplate.objects.filter(
        name=AUDERE_CONDITION_NAME,
    ).first()
    if audere_template is None:
        return

    threshold = AudereThreshold.objects.first()

    with transaction.atomic():
        # Remove condition
        remove_condition(character, audere_template)

        # Revert engagement intensity modifier
        if threshold is not None:
            engagement = (
                CharacterEngagement.objects.select_for_update().filter(character=character).first()
            )
            if engagement is not None:
                engagement.intensity_modifier -= threshold.intensity_bonus
                engagement.save(update_fields=["intensity_modifier"])

        # Revert anima pool
        anima = CharacterAnima.objects.select_for_update().filter(character=character).first()
        if anima is not None and anima.pre_audere_maximum is not None:
            anima.maximum = anima.pre_audere_maximum
            anima.current = min(anima.current, anima.maximum)
            anima.pre_audere_maximum = None
            anima.save(update_fields=["maximum", "current", "pre_audere_maximum"])


def maybe_create_audere_offer(
    character: ObjectDB, runtime_intensity: int
) -> PendingAudereOffer | None:
    """Persist a poll-able offer when the Audere gate opens for this cast.

    Returns None (no row) for NPCs without a CharacterSheet or when any
    eligibility gate fails. Idempotent: repeated qualifying casts update the
    single row per character (update_or_create).
    """
    from world.character_sheets.models import CharacterSheet
    from world.conditions.models import ConditionInstance

    sheet = CharacterSheet.objects.filter(character=character).first()
    if sheet is None:
        return None
    if not check_audere_eligibility(character, runtime_intensity):
        return None

    soulfray_instance = (
        ConditionInstance.objects.filter(
            target=character,
            condition__name=SOULFRAY_CONDITION_NAME,
        )
        .select_related("current_stage")
        .first()
    )
    stage_order = 0
    if soulfray_instance is not None and soulfray_instance.current_stage is not None:
        stage_order = soulfray_instance.current_stage.stage_order

    offer, _created = PendingAudereOffer.objects.update_or_create(
        character_sheet=sheet,
        defaults={
            "fired_intensity": runtime_intensity,
            "soulfray_stage_order": stage_order,
        },
    )
    return offer


def resolve_audere_offer(offer_id: int, *, accept: bool) -> AudereOfferResult:
    """Resolve a pending Audere offer: accept or decline, then delete the row.

    Two-phase (mirrors resolve_sineating_from_db in services/soul_tether.py):
    a plain lookup + staleness re-validation run OUTSIDE any transaction so a
    stale row can be deleted without leaving ghosts; the actual resolution
    re-fetches with select_for_update inside transaction.atomic(). A re-fetch
    miss (a concurrent respond won the race) raises AudereOfferNotFoundError.
    """
    from world.magic.exceptions import AudereOfferNotFoundError, AudereOfferStaleError

    offer = PendingAudereOffer.objects.filter(pk=offer_id).first()
    if offer is None:
        raise AudereOfferNotFoundError

    character = offer.character_sheet.character
    if not check_audere_eligibility(character, offer.fired_intensity):
        offer.delete()
        raise AudereOfferStaleError

    with transaction.atomic():
        locked = PendingAudereOffer.objects.select_for_update().filter(pk=offer_id).first()
        if locked is None:
            raise AudereOfferNotFoundError
        result = offer_audere(character, accept=accept)
        locked.delete()
    return result
