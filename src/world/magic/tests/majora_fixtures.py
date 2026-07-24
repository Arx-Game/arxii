"""Shared fixture builder for Audere Majora test modules (#543).

All three Majora test suites (offer, crossing, API) need the same 15-step world:
intensity tier → soulfray condition + stages → threshold → prospect/puissant paths →
character + sheet → class level + cache invalidation → path history → soulfray condition
instance → audere condition instance → engagement.

The crossing and API tests additionally need a PendingAudereMajoraOffer row.
The API tests additionally wire the sheet to an account via a RosterTenure.
"""

from __future__ import annotations

from django.contrib.contenttypes.models import ContentType
from evennia.objects.models import ObjectDB

from evennia_extensions.factories import CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.classes.factories import CharacterClassFactory, PathFactory
from world.classes.models import CharacterClassLevel, PathStage
from world.conditions.factories import (
    ConditionInstanceFactory,
    ConditionStageFactory,
    ConditionTemplateFactory,
)
from world.magic.audere import AUDERE_CONDITION_NAME, SOULFRAY_CONDITION_NAME
from world.magic.audere_majora import AudereMajoraThreshold, PendingAudereMajoraOffer
from world.magic.factories import IntensityTierFactory
from world.mechanics.constants import EngagementType
from world.mechanics.engagement import CharacterEngagement
from world.progression.models import CharacterPathHistory
from world.societies.constants import RenownMagnitude, RenownReach, RenownRisk


def build_majora_world(  # noqa: PLR0913 — fixture knobs are keyword-only by design
    boundary_level: int,
    suffix: str,
    *,
    intensity_tier=None,
    soulfray_template=None,
    soulfray_stage=None,
    vision_text: str = "[PLACEHOLDER VISION]",
    manifestation_text: str = "[PLACEHOLDER MANIFESTATION]",
    intensity_tier_threshold: int | None = None,
):
    """Build the shared 15-step Audere Majora world fixture.

    Creates (or reuses) the authored rows (intensity tier, soulfray template + stages,
    AudereMajoraThreshold, prospect/puissant paths) and per-character rows (ObjectDB,
    CharacterSheet, CharacterClassLevel, CharacterPathHistory, ConditionInstance × 2,
    CharacterEngagement).

    Parameters
    ----------
    boundary_level:
        The threshold boundary level; also the character's primary class level.
    suffix:
        Appended to all unique names to avoid UNIQUE constraint collisions across
        concurrent test classes.
    intensity_tier:
        Pass a pre-created IntensityTier to share it across fixture calls.
        Created fresh (threshold = ``intensity_tier_threshold`` or 10) when None.
    soulfray_template:
        Pass a pre-created ConditionTemplate for Soulfray reuse.
        Created fresh when None.
    soulfray_stage:
        Pass a pre-created ConditionStage (stage_order=3) when sharing the template.
        Created fresh (alongside stage_order 1 + 2) when None.
    vision_text / manifestation_text:
        Stored on the AudereMajoraThreshold row; tests use placeholders.
    intensity_tier_threshold:
        The ``threshold`` value for a newly created IntensityTier; ignored when
        ``intensity_tier`` is supplied.  Defaults to 10 when None.

    Returns
    -------
    tuple:
        (character, sheet, threshold, prospect_path, puissant_path, soulfray_stage)
    """
    if intensity_tier_threshold is None:
        intensity_tier_threshold = 10

    # Intensity tier: reuse or create
    if intensity_tier is None:
        intensity_tier = IntensityTierFactory(
            name=f"Major_{boundary_level}{suffix}",
            threshold=intensity_tier_threshold,
            control_modifier=0,
        )

    # Soulfray condition template + stages
    if soulfray_template is None:
        soulfray_template = ConditionTemplateFactory(
            name=SOULFRAY_CONDITION_NAME, has_progression=True
        )
    if soulfray_stage is None:
        ConditionStageFactory(
            condition=soulfray_template,
            stage_order=1,
            name=f"Fraying_{boundary_level}{suffix}",
        )
        ConditionStageFactory(
            condition=soulfray_template,
            stage_order=2,
            name=f"Tearing_{boundary_level}{suffix}",
        )
        soulfray_stage = ConditionStageFactory(
            condition=soulfray_template,
            stage_order=3,
            name=f"Ripping_{boundary_level}{suffix}",
        )

    threshold = AudereMajoraThreshold.objects.create(
        boundary_level=boundary_level,
        target_stage=PathStage.PUISSANT,
        minimum_intensity_tier=intensity_tier,
        minimum_warp_stage=soulfray_stage,
        requires_active_audere=True,
        vision_text=vision_text,
        manifestation_text=manifestation_text,
        # Renown-bearing default so a crossing mints a deed, converging with
        # ``ensure_audere_majora_threshold`` (#1205). ``fire_renown_award`` only
        # mints a LegendEntry when risk != NONE.
        magnitude=RenownMagnitude.HIGH,
        risk=RenownRisk.HIGH,
        reach=RenownReach.REGIONAL,
    )

    prospect_path = PathFactory(name=f"Prospect_{boundary_level}{suffix}", stage=PathStage.PROSPECT)
    puissant_path = PathFactory(name=f"Puissant_{boundary_level}{suffix}", stage=PathStage.PUISSANT)
    puissant_path.parent_paths.add(prospect_path)

    # Real Character typeclass (not a bare ObjectDB) so the ``threads`` handler
    # exists — cross_threshold now provisions a latent GIFT thread via the
    # path-magic grant (#1579), and production crossings always run on real
    # Characters.
    character = CharacterFactory(db_key=f"majora_char_{boundary_level}{suffix}")
    sheet = CharacterSheetFactory(character=character)

    char_class = CharacterClassFactory(name=f"Mage_{boundary_level}{suffix}")
    CharacterClassLevel.objects.create(
        character=sheet,
        character_class=char_class,
        level=boundary_level,
        is_primary=True,
    )
    sheet.invalidate_class_level_cache()

    CharacterPathHistory.objects.create(character=sheet, path=prospect_path)

    ConditionInstanceFactory(
        target=character,
        condition=soulfray_template,
        current_stage=soulfray_stage,
    )

    audere_template = ConditionTemplateFactory(name=AUDERE_CONDITION_NAME, has_progression=False)
    ConditionInstanceFactory(target=character, condition=audere_template, current_stage=None)

    obj_ct = ContentType.objects.get_for_model(ObjectDB)
    CharacterEngagement.objects.create(
        character=character,
        engagement_type=EngagementType.CHALLENGE,
        source_content_type=obj_ct,
        source_id=character.pk,
    )

    return character, sheet, threshold, prospect_path, puissant_path, soulfray_stage


def build_crossing_world(  # noqa: PLR0913 — fixture knobs are keyword-only by design
    boundary_level: int,
    suffix: str,
    *,
    intensity_tier=None,
    soulfray_template=None,
    soulfray_stage=None,
    fired_intensity: int | None = None,
    vision_text: str = "[PLACEHOLDER VISION]",
    manifestation_text: str = "[PLACEHOLDER MANIFESTATION]",
    intensity_tier_threshold: int | None = None,
):
    """Build a crossing world + PendingAudereMajoraOffer row.

    Delegates to ``build_majora_world`` for the shared rows, then creates the
    PendingAudereMajoraOffer needed by crossing and API tests.

    Returns
    -------
    tuple:
        (character, sheet, threshold, prospect_path, puissant_path, offer)
    """
    character, sheet, threshold, prospect_path, puissant_path, soulfray_stage = build_majora_world(
        boundary_level,
        suffix,
        intensity_tier=intensity_tier,
        soulfray_template=soulfray_template,
        soulfray_stage=soulfray_stage,
        vision_text=vision_text,
        manifestation_text=manifestation_text,
        intensity_tier_threshold=intensity_tier_threshold,
    )

    if fired_intensity is None:
        fired_intensity = 20

    offer = PendingAudereMajoraOffer.objects.create(
        character_sheet=sheet,
        threshold=threshold,
        fired_intensity=fired_intensity,
        soulfray_stage_order=soulfray_stage.stage_order,
    )

    return character, sheet, threshold, prospect_path, puissant_path, offer
