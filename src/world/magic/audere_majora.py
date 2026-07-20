"""Audere Majora — Crossing the Threshold (#543). Models + services."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from django.db import models, transaction
from evennia.objects.models import ObjectDB
from evennia.utils.idmapper.models import SharedMemoryModel

from world.areas.services import area_for_scene
from world.classes.models import PathStage
from world.magic.audere import (
    AUDERE_CONDITION_NAME,
    AUDERE_MAJORA_CONDITION_NAME,
    SOULFRAY_CONDITION_NAME,
    AbstractPendingOffer,
    _check_intensity_gate,
)
from world.magic.models.techniques import (
    AbstractAppliedCondition,
    AbstractCapabilityGrant,
)
from world.progression.models.advancement import AbstractClassLevelAdvancement
from world.progression.selectors import current_path_for_character
from world.societies.renown_config import RenownAwardConfig

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet


class AudereMajoraThreshold(RenownAwardConfig):
    """Configuration for a tier-crossing boundary level.

    One row per boundary level (5, 10, 15, 20). Authored by staff in the DB.
    Ceremony text is spoiler-private and never appears in code.
    """

    boundary_level = models.PositiveSmallIntegerField(
        unique=True,
        help_text="Character level the gate opens at (5, 10, 15, 20).",
    )
    target_stage = models.PositiveSmallIntegerField(
        choices=PathStage.choices,
        help_text="PathStage the character crosses into.",
    )
    minimum_intensity_tier = models.ForeignKey(
        "magic.IntensityTier",
        on_delete=models.PROTECT,
        related_name="+",
    )
    minimum_warp_stage = models.ForeignKey(
        "conditions.ConditionStage",
        on_delete=models.PROTECT,
        related_name="+",
    )
    requires_active_audere = models.BooleanField(
        default=True,
        help_text="When False, an active Audere condition is not required for the gate to open.",
    )
    vision_text = models.TextField(
        help_text="Shown ONLY to the crossing player. Authored in DB; spoiler-private.",
    )
    manifestation_text = models.TextField(
        help_text="Broadcast to the room when the offer fires. Authored in DB.",
    )
    deed_title = models.CharField(
        max_length=200,
        blank=True,
        default="",
        help_text=(
            "PUBLIC deed name used as the renown/echo title when a crossing mints a "
            "deed. Non-spoiler — distinct from vision_text/manifestation_text. Blank "
            "falls back to a generic composed title."
        ),
    )

    class Meta:
        ordering = ["boundary_level"]
        verbose_name = "Audere Majora Threshold"
        verbose_name_plural = "Audere Majora Thresholds"

    def __str__(self) -> str:
        return f"Crossing at level {self.boundary_level} → {self.get_target_stage_display()}"


class PendingAudereMajoraOffer(AbstractPendingOffer):
    """A poll-able Audere Majora offer awaiting the player's response (#543).

    Created when the crossing gate opens during a qualifying cast.
    One offer per character at a time (unique constraint).
    """

    character_sheet = models.ForeignKey(
        "character_sheets.CharacterSheet",
        on_delete=models.CASCADE,
        related_name="audere_majora_offers",
    )
    threshold = models.ForeignKey(
        AudereMajoraThreshold,
        on_delete=models.PROTECT,
        related_name="pending_offers",
    )
    faith_variant = models.ForeignKey(
        "AudereMajoraFaithVariant",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="pending_offers",
        help_text="Faith variant selected at offer creation; null = no faith coupling.",
    )

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Pending Audere Majora Offer"
        verbose_name_plural = "Pending Audere Majora Offers"
        constraints = [
            models.UniqueConstraint(
                fields=["character_sheet"],
                name="one_pending_audere_majora_per_character",
            ),
        ]

    def __str__(self) -> str:
        return (
            f"PendingAudereMajoraOffer(sheet={self.character_sheet_id}, "
            f"threshold={self.threshold_id})"
        )


class AudereMajoraCrossing(AbstractClassLevelAdvancement, SharedMemoryModel):
    """Irreversible receipt: this character crossed this threshold. Survives death."""

    character_sheet = models.ForeignKey(
        "character_sheets.CharacterSheet",
        on_delete=models.CASCADE,
        related_name="audere_majora_crossings",
    )
    threshold = models.ForeignKey(
        AudereMajoraThreshold,
        on_delete=models.PROTECT,
        related_name="crossings",
    )
    # NOT named "path": Evennia's idmapper metaclass shadows a `path` attribute.
    chosen_path = models.ForeignKey(
        "classes.Path",
        on_delete=models.PROTECT,
        related_name="audere_majora_crossings",
    )
    legend_entry = models.OneToOneField(
        "societies.LegendEntry",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audere_majora_crossing",
        help_text="The legend deed minted for this crossing. Receipt stays source of truth.",
    )

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["character_sheet", "threshold"],
                name="one_crossing_per_character_per_threshold",
            ),
        ]
        verbose_name = "Audere Majora Crossing"
        verbose_name_plural = "Audere Majora Crossings"

    def __str__(self) -> str:
        return (
            f"AudereMajoraCrossing(sheet={self.character_sheet_id}, "
            f"threshold={self.threshold_id}, "
            f"level {self.level_before}→{self.level_after})"
        )


# =============================================================================
# Services
# =============================================================================


def _has_crossed(sheet, threshold: AudereMajoraThreshold) -> bool:
    """Return True if the character already has a completed crossing for this threshold."""
    return AudereMajoraCrossing.objects.filter(character_sheet=sheet, threshold=threshold).exists()


def _has_active_condition(character: ObjectDB, condition_name: str) -> bool:
    """Return True if the character has an active ConditionInstance for the named condition."""
    from world.conditions.models import ConditionInstance  # noqa: PLC0415

    return ConditionInstance.objects.filter(
        target=character,
        condition__name=condition_name,
    ).exists()


def is_mid_audere_majora_crossing(character_sheet: CharacterSheet) -> bool:
    """True while a character's Audere Majora crossing is unresolved or ongoing.

    Covers both windows: the open-but-undecided offer (PendingAudereMajoraOffer
    exists — the gate has opened, the player hasn't accepted/declined yet) and
    the post-crossing power-spike aftermath (an active "Audere Majora"
    ConditionInstance — cleared only at full encounter completion). Single-
    character check — used by the disconnect-pause services (one lookup, one
    character). For the round-resolution hard block, use
    ``any_character_mid_audere_majora_crossing`` instead (batched).
    """
    if PendingAudereMajoraOffer.objects.filter(character_sheet=character_sheet).exists():
        return True
    from world.conditions.models import ConditionInstance  # noqa: PLC0415

    return ConditionInstance.objects.filter(
        target=character_sheet.character,
        condition__name=AUDERE_MAJORA_CONDITION_NAME,
    ).exists()


def any_character_mid_audere_majora_crossing(
    character_sheets: Iterable[CharacterSheet],
) -> bool:
    """Batched sibling of ``is_mid_audere_majora_crossing`` — one pair of
    ``__in=`` queries covering every given character, not one query pair per
    character. Required for the round-resolution hard block (#1899): a large
    battle can have 10+ active participants, and this spec's whole point for
    large battles is to keep resolution cheap — looping the single-character
    check per participant would reintroduce the N+1 this spec's scale
    exception exists to avoid.
    """
    sheets = list(character_sheets)
    if not sheets:
        return False
    if PendingAudereMajoraOffer.objects.filter(character_sheet__in=sheets).exists():
        return True
    from world.conditions.models import ConditionInstance  # noqa: PLC0415

    # CharacterSheet.character is a OneToOneField(primary_key=True), so
    # sheet.pk == sheet.character_id. Filter by id directly instead of
    # dereferencing `.character` on each sheet, which would issue an
    # uncached query per sheet (an N+1 identical in shape to the one this
    # batched function exists to prevent; #1899 spec review).
    return ConditionInstance.objects.filter(
        target_id__in=[s.pk for s in sheets],
        condition__name=AUDERE_MAJORA_CONDITION_NAME,
    ).exists()


def eligible_paths_for_threshold(character: ObjectDB, threshold: AudereMajoraThreshold) -> list:
    """Return active child paths at the threshold's target stage reachable from the current path.

    Returns an empty list when the character has no path history or no valid child paths.

    Paths with authored TraitRequirements the character does not meet are filtered
    out (#2538). Fail-open: a path with no requirements is always eligible.
    """
    from world.progression.services.spends import check_requirements_for_path  # noqa: PLC0415

    path = current_path_for_character(character)
    if path is None:
        return []
    candidates = path.child_paths.filter(stage=threshold.target_stage, is_active=True)
    return [p for p in candidates if check_requirements_for_path(character, p)[0]]


def _check_class_level_unlock_gate(character: ObjectDB) -> bool:
    """Gate 8: if a ClassLevelUnlock is authored for the character's next level,
    its requirements must be met. No authored unlock = no gate (fail-open)."""
    from world.progression.models import ClassLevelUnlock  # noqa: PLC0415
    from world.progression.services.advancement import primary_class_level  # noqa: PLC0415
    from world.progression.services.spends import check_requirements_for_unlock  # noqa: PLC0415

    cl = primary_class_level(character)
    if cl is None:
        return True
    unlock = ClassLevelUnlock.objects.filter(
        character_class=cl.character_class, target_level=cl.level + 1
    ).first()
    if unlock is None:
        return True
    requirements_met, _failed = check_requirements_for_unlock(character, unlock)
    return requirements_met


def _evaluate_majora_gates(  # noqa: PLR0911
    character: ObjectDB, runtime_intensity: int, sheet: CharacterSheet
) -> tuple[AudereMajoraThreshold | None, int]:
    """Run all Audere Majora eligibility gates, returning the threshold + stage.

    Returns ``(threshold, stage_order)`` when every gate passes, or
    ``(None, 0)`` as soon as any gate fails. The Soulfray query is inlined
    (mirroring ``_evaluate_audere_gates``) so the ``stage_order`` is captured
    for the caller to reuse instead of re-querying via
    ``soulfray_stage_order_snapshot``.

    Gates in order:
    1. A threshold exists at boundary_level == sheet.current_level.
    2. Character has NOT already crossed this threshold.
    3. Runtime intensity resolves to a tier at or above threshold.minimum_intensity_tier.
    4. Character has Soulfray at or above threshold.minimum_warp_stage.
    5. Character has an active CharacterEngagement.
    6. If threshold.requires_active_audere, character has the Audere condition.
    7. At least one eligible child path exists.
    8. If a ClassLevelUnlock is authored for (character's primary class, that
       class's next level), its requirements (ItemRequirement, TraitRequirement,
       etc., via check_requirements_for_unlock) must be met. No authored unlock =
       no gate (fail-open) -- #1859.
    """
    from world.conditions.models import ConditionInstance  # noqa: PLC0415
    from world.mechanics.engagement import CharacterEngagement  # noqa: PLC0415

    threshold = AudereMajoraThreshold.objects.filter(boundary_level=sheet.current_level).first()
    if threshold is None:
        return None, 0

    if _has_crossed(sheet, threshold):
        return None, 0

    if not _check_intensity_gate(runtime_intensity, threshold.minimum_intensity_tier.threshold):
        return None, 0

    soulfray_instance = (
        ConditionInstance.objects.filter(
            target=character,
            condition__name=SOULFRAY_CONDITION_NAME,
        )
        .select_related("current_stage")
        .first()
    )
    if soulfray_instance is None or soulfray_instance.current_stage is None:
        return None, 0
    stage_order = soulfray_instance.current_stage.stage_order
    if stage_order < threshold.minimum_warp_stage.stage_order:
        return None, 0

    if not CharacterEngagement.objects.filter(character=character).exists():
        return None, 0

    if threshold.requires_active_audere and not _has_active_condition(
        character, AUDERE_CONDITION_NAME
    ):
        return None, 0

    if not eligible_paths_for_threshold(character, threshold):
        return None, 0

    if not _check_class_level_unlock_gate(character):
        return None, 0

    return threshold, stage_order


def check_audere_majora_eligibility(
    character: ObjectDB, runtime_intensity: int
) -> AudereMajoraThreshold | None:
    """Check all gates for the Audere Majora offer.

    Returns the threshold on success, None if any gate fails.
    """
    from world.character_sheets.models import CharacterSheet  # noqa: PLC0415

    sheet = CharacterSheet.objects.filter(character=character).first()
    if sheet is None:
        return None
    threshold, _stage_order = _evaluate_majora_gates(character, runtime_intensity, sheet)
    return threshold


def _broadcast_manifestation(character: ObjectDB, text: str) -> None:
    """Broadcast the threshold manifestation text as an EMIT to the active scene.

    No-ops silently when: no active scene at location, or character has no primary persona.
    """
    from world.scenes.constants import InteractionMode  # noqa: PLC0415
    from world.scenes.interaction_services import (  # noqa: PLC0415
        create_interaction,
        push_interaction,
    )
    from world.scenes.models import Persona, Scene  # noqa: PLC0415

    scene = Scene.objects.active_for_room(character.location).first()
    if scene is None:
        return

    try:
        # sheet_data is CharacterSheet's OneToOne reverse accessor (models.py:98).
        persona = character.sheet_data.primary_persona
    except (AttributeError, Persona.DoesNotExist):
        # AttributeError covers a missing sheet (plain ObjectDB); DoesNotExist
        # a sheet with no PRIMARY persona (intentionally loud).
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


def maybe_create_audere_majora_offer(
    character: ObjectDB, runtime_intensity: int, *, sheet: CharacterSheet | None = None
) -> PendingAudereMajoraOffer | None:
    """Persist a poll-able Audere Majora offer when the crossing gate opens for this cast.

    Returns None for NPCs without a CharacterSheet or when any eligibility gate fails.
    Idempotent: repeated qualifying casts update the single row (update_or_create).
    Broadcast fires only on first creation; re-fires after decline broadcast again;
    refreshes from a still-open gate stay silent.

    Accepts an optional ``sheet`` kwarg to avoid re-fetching the CharacterSheet
    when the caller already has it (e.g. the Step 8c cast hook). When omitted,
    falls back to fetching it.
    """
    from world.character_sheets.models import CharacterSheet  # noqa: PLC0415

    if sheet is None:
        sheet = CharacterSheet.objects.filter(character=character).first()
    if sheet is None:
        return None

    threshold, stage_order = _evaluate_majora_gates(character, runtime_intensity, sheet)
    if threshold is None:
        return None

    offer, created = PendingAudereMajoraOffer.objects.update_or_create(
        character_sheet=sheet,
        defaults={
            "threshold": threshold,
            "fired_intensity": runtime_intensity,
            "soulfray_stage_order": stage_order,
        },
    )

    if created:
        _broadcast_manifestation(character, threshold.manifestation_text)

    return offer


# =============================================================================
# Deed helpers
# =============================================================================


def _crossing_deed_title(threshold: AudereMajoraThreshold, persona, chosen_path) -> str:
    """Public, non-spoiler deed name: authored override, else generic composed copy."""
    if threshold.deed_title:
        return threshold.deed_title
    return f"{persona.name}'s Crossing — {chosen_path.name}"


def _crossing_deed_description(persona, chosen_path) -> str:
    """Generic non-spoiler deed description from public facts only."""
    return f"{persona.name} crossed the threshold onto {chosen_path.name}."


def _mint_crossing_deed(crossing: AudereMajoraCrossing) -> None:
    """Mint the renown deed for a completed crossing; record present witnesses.

    No-ops when the crosser has no primary persona. When the threshold's risk
    yields no legend (misconfigured), fire_renown_award creates no LegendEntry
    and there is nothing to link or witness.
    """
    from world.scenes.models import Persona  # noqa: PLC0415
    from world.societies.constants import DeedKnowledgeSource  # noqa: PLC0415
    from world.societies.knowledge_services import (  # noqa: PLC0415
        grant_deed_knowledge,
        scene_witness_personas,
    )
    from world.societies.models import LegendEntry  # noqa: PLC0415
    from world.societies.renown import fire_renown_award  # noqa: PLC0415

    sheet = crossing.character_sheet
    try:
        persona = sheet.primary_persona
    except Persona.DoesNotExist:
        return

    scene = crossing.scene
    origin_area = area_for_scene(scene)
    threshold = crossing.threshold
    title = _crossing_deed_title(threshold, persona, crossing.chosen_path)

    result = fire_renown_award(
        persona=persona,
        origin_area=origin_area,
        title=title,
        **threshold.as_renown_award_kwargs(),
    )
    if result.legend_entry_id is None:
        return

    entry = LegendEntry.objects.get(pk=result.legend_entry_id)
    if not entry.description:
        entry.description = _crossing_deed_description(persona, crossing.chosen_path)
        entry.save(update_fields=["description"])

    crossing.legend_entry = entry
    crossing.save(update_fields=["legend_entry"])

    if scene is not None:
        grant_deed_knowledge(
            deed=entry,
            personas=scene_witness_personas(scene),
            source=DeedKnowledgeSource.WITNESSED,
        )


# =============================================================================
# Crossing services (Task 4)
# =============================================================================


@dataclass
class AudereMajoraCrossingResult:
    """Result of a Crossing decision."""

    accepted: bool
    level_before: int = 0
    level_after: int = 0
    chosen_path_name: str = ""
    advisory_text: str = ""
    declaration_interaction_id: int | None = None
    faith_coupling_applied: bool = False
    faith_being_name: str = ""


def _primary_class_level(character: ObjectDB):
    """Return the primary CharacterClassLevel, or the highest-level one if none is primary.

    Thin alias for ``progression.services.advancement.primary_class_level``; kept for
    backward compatibility with any callers in this module.
    Deferred import avoids a circular import through world.progression.services.__init__.
    """
    from world.progression.services.advancement import primary_class_level  # noqa: PLC0415

    return primary_class_level(character)


def _post_declaration(character: ObjectDB, text: str):
    """Create a POSE interaction for the crossing declaration.

    Returns (scene, interaction) on success.
    Returns (None, None) when there is no active scene at the character's location.
    Returns (scene, None) when the character has no primary persona.
    Returns (scene, None) when text is empty — callers must enforce non-empty text.
    """
    from world.scenes.constants import InteractionMode  # noqa: PLC0415
    from world.scenes.interaction_services import create_interaction  # noqa: PLC0415
    from world.scenes.models import Persona, Scene  # noqa: PLC0415

    scene = Scene.objects.active_for_room(character.location).first()

    if not text.strip():
        return scene, None

    if scene is None:
        return None, None

    try:
        persona = character.sheet_data.primary_persona
    except (AttributeError, Persona.DoesNotExist):
        return scene, None

    interaction = create_interaction(
        persona=persona,
        content=text,
        mode=InteractionMode.POSE,
        scene=scene,
    )
    return scene, interaction


def cross_threshold(
    sheet,
    threshold: AudereMajoraThreshold,
    chosen_path,
    *,
    declaration_text: str,
) -> AudereMajoraCrossingResult:
    """Execute the crossing inside the caller's transaction.

    Assumes the caller has validated eligibility and holds the offer lock.
    Does not delete the offer row — caller is responsible for that.
    """
    from world.conditions.models import ConditionTemplate  # noqa: PLC0415
    from world.conditions.services import apply_condition  # noqa: PLC0415
    from world.magic.audere import corruption_advisory_for_character  # noqa: PLC0415
    from world.progression.services.advancement import (  # noqa: PLC0415
        apply_class_level_advance,
        cross_into_path,
    )
    from world.scenes.interaction_services import push_interaction  # noqa: PLC0415

    character = sheet.character

    advisory = corruption_advisory_for_character(character)

    scene, interaction = _post_declaration(character, declaration_text)

    # Eligibility re-validation guarantees sheet.current_level == boundary_level
    # at this point, so the receipt records the character-level crossing even if
    # the primary class row lags behind a higher multiclass row.
    level_before = threshold.boundary_level
    level_after = threshold.boundary_level + 1

    apply_class_level_advance(sheet, level_after=level_after)

    # Switch onto the chosen path and grant its gift(s) + curated starter techniques
    # (#1579, ADR-0055) through the shared path-change seam — the same seam the
    # Durance level-3 semi-crossing uses. Idempotent; a no-op for paths with no
    # PathGiftGrant rows.
    cross_into_path(sheet, chosen_path)

    crossing = AudereMajoraCrossing.objects.create(
        character_sheet=sheet,
        threshold=threshold,
        chosen_path=chosen_path,
        scene=scene,
        declaration_interaction=interaction,
        level_before=level_before,
        level_after=level_after,
    )
    _mint_crossing_deed(crossing)

    majora_template = ConditionTemplate.get_by_name(AUDERE_MAJORA_CONDITION_NAME)
    # Result deliberately unchecked, mirroring offer_audere: no authored trigger
    # cancels this today. A future PRE_APPLY cancel would advance the level but
    # skip the power spike — revisit if such content is ever authored.
    apply_condition(target=character, condition=majora_template)

    if interaction is not None:
        declaration_id = interaction.pk

        def _push():
            push_interaction(
                interaction,
                receiver_persona_ids=[],
                target_persona_ids=[],
                receiver_characters=[],
            )

        transaction.on_commit(_push)
    else:
        declaration_id = None

    return AudereMajoraCrossingResult(
        accepted=True,
        level_before=level_before,
        level_after=level_after,
        chosen_path_name=chosen_path.name,
        advisory_text=advisory,
        declaration_interaction_id=declaration_id,
    )


def resolve_audere_majora_offer(
    offer_id: int,
    *,
    accept: bool,
    path_id: int | None = None,
    declaration_text: str = "",
) -> AudereMajoraCrossingResult:
    """Resolve a pending Audere Majora offer: accept (cross) or decline.

    Two-phase pattern mirroring resolve_audere_offer:
    - Plain lookup + staleness check OUTSIDE any transaction.
    - Actual work re-fetches with select_for_update inside transaction.atomic().
    """
    from world.magic.audere import corruption_advisory_for_character  # noqa: PLC0415
    from world.magic.exceptions import (  # noqa: PLC0415
        AudereMajoraOfferNotFoundError,
        AudereMajoraOfferStaleError,
        AudereMajoraPathError,
    )
    from world.magic.services.alterations import enforce_advancement_gate  # noqa: PLC0415

    offer = PendingAudereMajoraOffer.objects.filter(pk=offer_id).first()
    if offer is None:
        raise AudereMajoraOfferNotFoundError

    character = offer.character_sheet.character
    sheet = offer.character_sheet

    if not accept:
        advisory = corruption_advisory_for_character(character)
        offer.delete()
        return AudereMajoraCrossingResult(accepted=False, advisory_text=advisory)

    # Staleness check OUTSIDE transaction
    threshold = check_audere_majora_eligibility(character, offer.fired_intensity)
    if threshold is None or threshold.pk != offer.threshold_id:
        offer.delete()
        raise AudereMajoraOfferStaleError

    # Spend guards
    enforce_advancement_gate(sheet)

    # Path validation
    eligible_paths = eligible_paths_for_threshold(character, threshold)
    chosen_path = next((p for p in eligible_paths if p.pk == path_id), None)
    if chosen_path is None:
        raise AudereMajoraPathError

    with transaction.atomic():
        locked = PendingAudereMajoraOffer.objects.select_for_update().filter(pk=offer_id).first()
        if locked is None:
            raise AudereMajoraOfferNotFoundError

        result = cross_threshold(
            sheet,
            threshold,
            chosen_path,
            declaration_text=declaration_text,
        )
        locked.delete()

    return result


def end_audere_majora(character: ObjectDB) -> None:
    """Remove the Audere Majora condition from a character.

    Safe no-op when the condition is absent or the template doesn't exist.

    Note: unlike end_audere, no engagement/anima reverts are needed —
    Audere Majora's effects are condition-modifier driven and cleared by
    the condition removal itself.
    """
    from world.conditions.models import ConditionTemplate  # noqa: PLC0415
    from world.conditions.services import remove_condition  # noqa: PLC0415

    template = ConditionTemplate.objects.filter(name=AUDERE_MAJORA_CONDITION_NAME).first()
    if template is None:
        return
    remove_condition(character, template)


# =============================================================================
# Faith Variant (#2360)
# =============================================================================


class AudereMajoraFaithVariant(SharedMemoryModel):
    """Faith-specific ceremony override for a crossing threshold (#2360).

    When a crossing character has high devotion to a being whose pool is
    sufficient, this variant overrides the threshold's vision_text and
    manifestation_text and grants a mechanical bonus (condition payload).
    Pool is spent at crossing time (not offer creation), so a declined
    offer costs nothing.
    """

    threshold = models.ForeignKey(
        AudereMajoraThreshold,
        on_delete=models.CASCADE,
        related_name="faith_variants",
    )
    being = models.ForeignKey(
        "worship.WorshippedBeing",
        on_delete=models.PROTECT,
        related_name="audere_majora_faith_variants",
    )
    vision_text = models.TextField(
        help_text="Shown ONLY to the crossing player. Spoiler-private.",
    )
    manifestation_text = models.TextField(
        help_text="Broadcast to the room when the offer fires.",
    )
    resonance_pool_cost = models.PositiveIntegerField(
        help_text="Spent from being.resonance_pool when this variant fires (at crossing time).",
    )
    favor_threshold = models.PositiveIntegerField(default=50)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["threshold", "being"]
        constraints = [
            models.UniqueConstraint(
                fields=["threshold", "being"],
                name="unique_faith_variant_per_threshold_being",
            ),
        ]

    def __str__(self) -> str:
        return f"FaithVariant({self.threshold} / {self.being})"


class AudereMajoraFaithVariantCapabilityGrant(AbstractCapabilityGrant):
    """Capability grant payload for an AudereMajoraFaithVariant (#2360).

    INERT until a capability-read-path issue is built — mirrors
    SignatureMotifBonusCapabilityGrant inertness.
    """

    faith_variant = models.ForeignKey(
        AudereMajoraFaithVariant,
        on_delete=models.CASCADE,
        related_name="capability_grants",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["faith_variant", "capability"],
                name="faith_variant_cap_grant_unique",
            ),
        ]


class AudereMajoraFaithVariantAppliedCondition(AbstractAppliedCondition):
    """Applied condition payload for an AudereMajoraFaithVariant (#2360).

    The MVP mechanical bonus surface for faith-colored crossings.
    """

    faith_variant = models.ForeignKey(
        AudereMajoraFaithVariant,
        on_delete=models.CASCADE,
        related_name="condition_applications",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["faith_variant", "condition", "target_kind"],
                name="faith_variant_applied_condition_unique",
            ),
        ]
