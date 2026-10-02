"""Audere Majora — Crossing the Threshold (#543). Models + services."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
import logging
from typing import TYPE_CHECKING

from django.db import models, transaction
from evennia.objects.models import ObjectDB

from core.models import ArxSharedMemoryModel as SharedMemoryModel
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
)
from world.progression.models.advancement import AbstractClassLevelAdvancement
from world.progression.selectors import current_path_for_character
from world.societies.renown_config import RenownAwardConfig

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet


logger = logging.getLogger(__name__)


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
        "arxii.IntensityTier",
        on_delete=models.PROTECT,
        related_name="+",
    )
    minimum_warp_stage = models.ForeignKey(
        "arxii.ConditionStage",
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
        help_text=(
            "Room line for the crossing. Broadcast when the offer fires, or held "
            "for the Crossing prompt when a GM is running the scene (#4101)."
        ),
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
    offer_title = models.CharField(
        max_length=120,
        default="PLACEHOLDER crossing offer title",
        help_text="#4101: heading of this threshold's crossing offer dialog.",
    )
    offer_strip_label = models.CharField(
        max_length=120,
        default="PLACEHOLDER crossing gate strip label",
        help_text="#4101 fold-in: the pulsing strip that reopens the crossing offer.",
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
        "arxii.CharacterSheet",
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
    manifestation_withheld = models.BooleanField(
        default=False,
        help_text=(
            "#4101: a prompted GM was present when the gate opened, so the room "
            "line was held for the Crossing prompt instead of broadcast."
        ),
    )
    scene = models.ForeignKey(
        "arxii.Scene",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="pending_audere_majora_offers",
        help_text=(
            "#4101 fix round 1: the scene active at gate-open, captured so a "
            "decline/staleness/encounter-end cleanup that never reaches a crossing "
            "can still deliver a withheld manifestation to the right room, even if "
            "the character has since moved or the scene has since ended."
        ),
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
        "arxii.CharacterSheet",
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
        "arxii.Path",
        on_delete=models.PROTECT,
        related_name="audere_majora_crossings",
    )
    legend_entry = models.OneToOneField(
        "arxii.LegendEntry",
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
    """True while any given character has an UNDECIDED crossing offer (#1899, #4098).

    The round-resolution hard block: one ``__in=`` query over every given character.
    Only the undecided-offer window blocks. After the crossing resolves, the Audere
    Majora condition lasts until encounter completion; blocking on it froze every
    later round, so the crosser could never act on their new Path (#4098 decision 9).
    The single-character ``is_mid_audere_majora_crossing`` (disconnect pause) still
    covers both windows.
    """
    sheets = list(character_sheets)
    if not sheets:
        return False
    return PendingAudereMajoraOffer.objects.filter(character_sheet__in=sheets).exists()


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


def _evaluate_majora_gates(
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

    if not CharacterEngagement.objects.filter(character_id=character.pk).exists():
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


def _broadcast_manifestation(
    character: ObjectDB, text: str, *, scene=None, scene_scoped_push: bool = False
) -> None:
    """Broadcast the threshold manifestation text as an EMIT.

    Pass ``scene`` explicitly (#4101 fix round 1, controller ruling M1) to attach the
    EMIT to a specific scene regardless of the character's CURRENT location — the
    scene the gate opened in, or the scene captured on a withheld offer, must stay
    the destination even if the character has since moved. Omitted, falls back to
    the scene active at the character's current location (pre-#4101 behavior).

    ``scene_scoped_push`` (#4101 fix round 2, must-fix 2): pass True for a
    RELEASE of a withheld/uncovered manifestation -- the live push then targets
    ``scene``'s own location (never the character's current one) and is skipped
    entirely once that scene has gone inactive. Leave False for the ordinary
    gate-open broadcast, which is synchronous with the cast and has no
    moved-since-then risk.

    No-ops silently when: no scene resolves, or character has no primary persona.
    """
    from world.scenes.interaction_services import broadcast_scene_emit  # noqa: PLC0415

    broadcast_scene_emit(character, text, scene=scene, scene_scoped_push=scene_scoped_push)


def _crossing_prompt_candidates(sheet: CharacterSheet, scene) -> list:
    """GMs of ``scene``, minus the crossing character's own account (#4101 fix round 1, M5).

    A player who also GMs their own scene must never be prompted about their OWN
    Crossing -- they already receive the vision privately, and a self-addressed GM
    prompt would hand them their own spoiler-private vision through a second,
    GM-facing surface.
    """
    from world.gm.prompt_services import scene_gm_accounts  # noqa: PLC0415
    from world.magic.services.gain import account_for_sheet  # noqa: PLC0415

    crosser_account = account_for_sheet(sheet)
    pool = scene_gm_accounts(scene)
    if crosser_account is None:
        return pool
    return [a for a in pool if a.pk != crosser_account.pk]


def release_withheld_crossing_manifestation(offer: PendingAudereMajoraOffer) -> None:
    """Send a withheld Crossing manifestation that will never get a crossing.

    #4101 fix round 1, controller ruling I1.

    A no-op unless ``offer.manifestation_withheld`` -- the gate opened with a GM
    present, so the room line was held for a Crossing prompt that will now never
    exist (the offer is about to be deleted: declined, gone stale, or the
    encounter ended). It must not be silently lost.

    Re-resolves the text fresh via ``resolve_crossing_text`` rather than reading a
    stored copy -- prepared text can change between gate-open and this call, and
    this mirrors how the offer poll (``get_vision_text``) already recomputes on
    every read. Delivered against ``offer.scene`` -- the scene captured at
    gate-open (#4101 fix round 1) -- explicitly, via ``transaction.on_commit`` so
    the broadcast survives whatever transaction the caller deletes the offer in,
    and lands even when that scene has since finished: ``broadcast_scene_emit``
    only uses an explicit ``scene`` to attach the Interaction, with no check that
    the scene is still active (verified against its own implementation).
    """
    if not offer.manifestation_withheld:
        return

    from world.magic.services.prepared_text import resolve_crossing_text  # noqa: PLC0415

    sheet = offer.character_sheet
    scene = offer.scene
    texts = resolve_crossing_text(sheet, offer.threshold, offer.faith_variant)
    if not texts.manifestation.strip():
        return
    character = sheet.character
    transaction.on_commit(
        lambda: _broadcast_manifestation(
            character, texts.manifestation, scene=scene, scene_scoped_push=True
        )
    )


def release_and_delete_withheld_offer(offer_id: int) -> None:
    """Lock, release any withheld manifestation, and delete one offer row.

    #4101 fix round 2, should-fix 4: wraps the release + delete pair in
    ``transaction.atomic()`` under ``select_for_update()`` on the offer, and
    only acts if the locked row still exists. Declining, going stale, and
    encounter-end cleanup all funnel through this one function -- a concurrent
    accept (which deletes the offer inside its own locked
    ``select_for_update`` block, see ``resolve_audere_majora_offer``) or a
    second decline/stale-check racing this one must never cause the
    manifestation to be released twice; whichever side's lock wins first, the
    other finds the row already gone and no-ops cleanly.

    ``release_withheld_crossing_manifestation`` already no-ops when the offer
    isn't withheld, so this is safe to call unconditionally on every offer a
    decline/staleness/encounter-end path is about to delete, not just the
    withheld ones.
    """
    with transaction.atomic():
        locked = (
            PendingAudereMajoraOffer.objects.select_for_update()
            .select_related("character_sheet__character", "threshold", "faith_variant", "scene")
            .filter(pk=offer_id)
            .first()
        )
        if locked is None:
            return
        release_withheld_crossing_manifestation(locked)
        locked.delete()


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
        from world.gm.constants import GMPromptKind  # noqa: PLC0415
        from world.gm.prompt_services import prompt_recipients  # noqa: PLC0415
        from world.magic.services.prepared_text import resolve_crossing_text  # noqa: PLC0415
        from world.scenes.models import Scene  # noqa: PLC0415

        variant = maybe_apply_audere_faith_coupling(sheet, threshold, offer)
        texts = resolve_crossing_text(sheet, threshold, variant)
        scene = Scene.objects.active_for_room(character.location).first()
        candidates = _crossing_prompt_candidates(sheet, scene)
        if prompt_recipients(scene, GMPromptKind.CROSSING, candidates=candidates):
            offer.manifestation_withheld = True
            offer.scene = scene
            offer.save(update_fields=["manifestation_withheld", "scene"])
        else:
            _broadcast_manifestation(character, texts.manifestation, scene=scene)

    return offer


def maybe_apply_audere_faith_coupling(
    sheet: CharacterSheet,
    threshold: AudereMajoraThreshold,
    offer: PendingAudereMajoraOffer,
) -> AudereMajoraFaithVariant | None:
    """Select and persist a faith variant on the offer if the character qualifies.

    Does NOT spend the pool — pool spend is deferred to ``cross_threshold``.
    Returns the selected variant, or None. If a variant is selected, its
    ``manifestation_text`` replaces the generic threshold broadcast.
    """
    from world.worship.models import DevotionStanding  # noqa: PLC0415

    variants = AudereMajoraFaithVariant.objects.filter(
        threshold=threshold,
        is_active=True,
    ).select_related("being")

    best_variant = None
    best_favor = 0
    for variant in variants:
        standing = DevotionStanding.objects.filter(
            character_sheet=sheet,
            being=variant.being,
        ).first()
        if standing is None or standing.favor < variant.favor_threshold:
            continue
        if variant.being.resonance_pool < variant.resonance_pool_cost:
            continue
        if standing.favor > best_favor:
            best_variant = variant
            best_favor = standing.favor

    if best_variant is None:
        return None

    offer.faith_variant = best_variant
    offer.save(update_fields=["faith_variant"])
    return best_variant


# =============================================================================
# Deed helpers
# =============================================================================


def _crossing_deed_title(persona, chosen_path, *, resolved_title: str = "") -> str:
    """Public deed name: the resolved title (character, else authored tier), else generic.

    #4101 fix round 1 (M4): the caller already passes ``resolve_crossing_text``'s
    fully layered ``deed_title`` (own prepared title, falling back to
    ``threshold.deed_title``), so ``resolved_title`` is never merely "the
    character's own pick" -- it is the final answer except in the one case
    neither layer authored anything, which falls through to the generic
    composed name below. No longer takes ``threshold`` directly -- the tier
    fallback it used to re-check is already folded into ``resolved_title``.
    """
    if resolved_title:
        return resolved_title
    return f"{persona.name}'s Crossing - {chosen_path.name}"


def _crossing_deed_description(persona, chosen_path) -> str:
    """Generic non-spoiler deed description from public facts only."""
    return f"{persona.name} crossed the threshold onto {chosen_path.name}."


def _mint_crossing_deed(crossing: AudereMajoraCrossing, *, deed_title: str = "") -> None:
    """Mint the renown deed for a completed crossing; record present witnesses.

    ``deed_title`` is the character's own prepared title (#4101), layered ahead of
    the authored tier title and the generic composed fallback by
    ``_crossing_deed_title``.

    No-ops when the crosser has no primary persona.

    **A crossing is always a legendary reward** (Tehom, 2026-08-29): it is
    impossible to have an Audere Majora without great personal risk, and it is
    likely the culmination of years of real-time play. So the deed is minted
    unconditionally, at the character's NEW level as its station, and no
    authored ``risk`` value can produce a crossing worth nothing.

    This is not an exception to #3463's gates — the crossing satisfies them
    structurally. Jeopardy is intrinsic to the act; a completed crossing *is*
    the objective held (there is no partial crossing); and a tier crossing sits
    at the ceiling of the old station by definition. ``structurally_perilous``
    exists so this one source need not fake a stakes contract to say so, and
    nothing authored can set it.

    Previously the deed was *contingent*: this function bailed on
    ``result.legend_entry_id is None``, and a threshold authored at
    ``risk=NONE`` produced a crossing with no deed at all — guarded only by a
    test asserting the seeded default. That state is now unreachable.
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
    title = _crossing_deed_title(persona, crossing.chosen_path, resolved_title=deed_title)

    result = fire_renown_award(
        persona=persona,
        origin_area=origin_area,
        title=title,
        station=crossing.level_after,
        structurally_perilous=True,
        **threshold.as_renown_award_kwargs(),
    )
    if result.legend_entry_id is None:
        logger.error(
            "Audere Majora crossing %s minted no legend entry — a crossing is "
            "always legendary, so this indicates a bug in the pricing path, "
            "not a misconfigured threshold.",
            crossing.pk,
        )
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

    # #3807: returned to cross_threshold, which pushes this row via push_interaction
    # once the rest of the crossing (level write, path history, receipt) has landed.
    interaction = create_interaction(  # noqa: UNDELIVERED - caller delivers it, see above
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
    offer: PendingAudereMajoraOffer | None = None,
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

    # The crossing is an Audere for the next tier (decision 12): reopen the reveal so it
    # draws on the new Path's ultimates.
    from world.magic.services.ultimates import clear_readied_ultimate  # noqa: PLC0415

    clear_readied_ultimate(sheet)

    from world.magic.services.prepared_text import (  # noqa: PLC0415
        consume_prepared_crossing_text,
        resolve_crossing_text,
    )

    variant = offer.faith_variant if offer is not None else None
    texts = resolve_crossing_text(sheet, threshold, variant)

    crossing = AudereMajoraCrossing.objects.create(
        character_sheet=sheet,
        threshold=threshold,
        chosen_path=chosen_path,
        scene=scene,
        declaration_interaction=interaction,
        level_before=level_before,
        level_after=level_after,
    )
    _mint_crossing_deed(crossing, deed_title=texts.deed_title)
    consume_prepared_crossing_text(sheet, crossing)
    withheld = offer is not None and offer.manifestation_withheld
    # Captured before the caller deletes the offer -- the scene is the crossing's
    # own fallback (#4101 fix round 2, should-fix 5) for when there is no active
    # scene AT crossing time (``scene`` above came back None), so the withheld
    # line is not silently dropped.
    offer_scene = offer.scene if offer is not None else None
    transaction.on_commit(
        lambda: _route_crossing(
            character, sheet, scene, texts, withheld=withheld, fallback_scene=offer_scene
        )
    )

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

    # Faith coupling bonus (#2360): apply variant conditions + spend pool at crossing.
    faith_coupling_applied = False
    faith_being_name = ""
    if offer is not None and offer.faith_variant_id is not None:
        variant = offer.faith_variant
        being = variant.being
        # Re-check pool (staleness guard — offer was created at cast time).
        if being.resonance_pool >= variant.resonance_pool_cost:
            from world.worship.services import spend_worship_pool  # noqa: PLC0415

            for row in variant.condition_applications.select_related("condition"):
                apply_condition(
                    target=character,
                    condition=row.condition,
                    severity=row.base_severity,
                    duration_rounds=row.base_duration_rounds,
                )
            spend_worship_pool(being, variant.resonance_pool_cost, reason="audere_faith_coupling")
            faith_coupling_applied = True
            faith_being_name = being.name

    return AudereMajoraCrossingResult(
        accepted=True,
        level_before=level_before,
        level_after=level_after,
        chosen_path_name=chosen_path.name,
        advisory_text=advisory,
        declaration_interaction_id=declaration_id,
        faith_coupling_applied=faith_coupling_applied,
        faith_being_name=faith_being_name,
    )


def _route_crossing(  # noqa: PLR0913 — one on_commit callback needs every piece of crossing context
    character, sheet, scene, texts, *, withheld: bool, fallback_scene=None
) -> None:
    """Prompt the scene's GMs with the Crossing, or deliver it as today (#4101).

    ``withheld`` is read from the offer BEFORE ``cross_threshold``'s caller deletes
    it, so this always has a plain bool to work with regardless of the offer row's
    lifetime. When withheld, the room line is the Crossing prompt's room-text
    default (spec decision 7); otherwise the room line already went out at
    gate-open and this only carries the private vision.

    ``fallback_scene`` (#4101 fix round 2, should-fix 5) is the offer's OWN
    captured scene, used whenever there is no active scene AT CROSSING time
    (``scene`` is None -- the scene ended, or the character moved to a
    scene-less room, between gate-open and the crossing resolving). Without
    this, a withheld manifestation would silently vanish:
    ``_broadcast_manifestation(..., scene=None)`` re-resolves by the
    character's CURRENT location internally and no-ops when that is also
    scene-less. The vision still logs even with no scene at all
    (``narrate_privately`` tolerates ``scene=None``) -- only the room
    broadcast needs this fallback.

    Candidates exclude the crossing character's own account (#4101 fix round 1,
    M5) -- a player who also GMs their own scene is never addressed about their
    own Crossing.

    Runs inside ``transaction.on_commit`` (the caller's lambda), so a
    ``DatabaseError`` here can no longer corrupt any state -- but it CAN still
    leave the vision and manifestation undelivered if left uncaught. Falls back
    to ``_deliver`` (the unprompted path) on that failure instead (#4101 fix
    round 1, M2), logging the error, so the crossing player's vision is never
    silently lost to a GM-prompt-creation bug. ``_crossing_prompt_candidates``
    is computed INSIDE the same ``try`` (#4101 fix round 2, must-fix 3) -- a
    failure resolving candidates must also fall back to unprompted delivery,
    not propagate past this on_commit callback uncaught.
    """
    from django.db import DatabaseError  # noqa: PLC0415

    from world.gm.constants import GMPromptKind  # noqa: PLC0415
    from world.gm.prompt_services import route_narratable_event  # noqa: PLC0415
    from world.gm.types import NarratableEvent  # noqa: PLC0415
    from world.scenes.interaction_services import narrate_privately  # noqa: PLC0415

    effective_scene = scene if scene is not None else fallback_scene
    room_text = texts.manifestation if withheld else ""

    def _deliver() -> None:
        if room_text.strip():
            _broadcast_manifestation(
                character, room_text, scene=effective_scene, scene_scoped_push=True
            )
        if texts.vision.strip():
            narrate_privately(character, texts.vision, scene=effective_scene)

    try:
        candidates = _crossing_prompt_candidates(sheet, effective_scene)
        route_narratable_event(
            NarratableEvent(
                kind=GMPromptKind.CROSSING,
                scene=effective_scene,
                character_sheet=sheet,
                room_text=room_text,
                private_text=texts.vision,
                prepared_for_character=texts.prepared,
            ),
            deliver_unprompted=_deliver,
            candidates=candidates,
        )
    except DatabaseError:
        logger.exception(
            "Crossing routing failed to create GM prompts for sheet %s; "
            "delivering unprompted instead (#4101).",
            sheet.pk,
        )
        _deliver()


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
        release_and_delete_withheld_offer(offer_id)
        return AudereMajoraCrossingResult(accepted=False, advisory_text=advisory)

    # Staleness check OUTSIDE transaction
    threshold = check_audere_majora_eligibility(character, offer.fired_intensity)
    if threshold is None or threshold.pk != offer.threshold_id:
        release_and_delete_withheld_offer(offer_id)
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
            offer=locked,
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
    from world.magic.services.ultimates import clear_readied_ultimate  # noqa: PLC0415

    template = ConditionTemplate.objects.filter(name=AUDERE_MAJORA_CONDITION_NAME).first()
    if template is None:
        return
    remove_condition(character, template)

    # A sheet-less character (NPC) never has a readied pick to clear.
    sheet = character.character_sheet
    if sheet is not None:
        clear_readied_ultimate(sheet)


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
        "arxii.WorshippedBeing",
        on_delete=models.PROTECT,
        related_name="audere_majora_faith_variants",
    )
    vision_text = models.TextField(
        help_text="Shown ONLY to the crossing player. Spoiler-private.",
    )
    manifestation_text = models.TextField(
        help_text=(
            "Room line for the crossing. Broadcast when the offer fires, or held "
            "for the Crossing prompt when a GM is running the scene (#4101)."
        ),
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
