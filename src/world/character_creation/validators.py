"""Stage validation functions for character creation.

Each function takes a CharacterDraft instance and returns a list of
human-readable error messages. An empty list means the stage is complete.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from rest_framework import serializers

from world.character_creation.constants import (
    REQUIRED_STATS,
    STAT_MAX_VALUE,
    STAT_MIN_VALUE,
    Stage,
)
from world.character_creation.types import StageValidationErrors

if TYPE_CHECKING:
    from world.character_creation.models import CharacterDraft


def get_all_stage_errors(draft: CharacterDraft) -> StageValidationErrors:
    """Compute validation errors for every stage.

    Returns a dict mapping stage number to a list of error messages.
    Empty list means the stage is complete.
    """
    return {
        Stage.ORIGIN: get_origin_errors(draft),
        Stage.HERITAGE: get_heritage_errors(draft),
        Stage.LINEAGE: get_lineage_errors(draft),
        Stage.DISTINCTIONS: get_distinctions_errors(draft),
        Stage.PATH: get_path_errors(draft),
        Stage.GIFT: compute_magic_errors(draft),
        Stage.ATTRIBUTES: get_attributes_errors(draft),
        Stage.APPEARANCE: get_appearance_errors(draft),
        Stage.IDENTITY: get_identity_errors(draft),
        Stage.FINAL_TOUCHES: [],
    }


# ---------------------------------------------------------------------------
# Individual stage validators
# ---------------------------------------------------------------------------


def get_origin_errors(draft: CharacterDraft) -> list[str]:
    """Return validation errors for the Origin stage."""
    if not draft.selected_area:
        return ["Select a starting area"]
    return []


def get_heritage_errors(draft: CharacterDraft) -> list[str]:
    """Return validation errors for the Heritage stage."""
    errors: list[str] = []
    if not draft.selected_beginnings:
        errors.append("Select a beginnings path")
    if not draft.selected_species:
        errors.append("Select a species")
    if not draft.selected_gender:
        errors.append("Select a gender")

    # Species must be allowed by beginnings
    if draft.selected_beginnings and draft.selected_species:
        available_species = draft.selected_beginnings.get_available_species()
        if draft.selected_species not in available_species:
            errors.append("Selected species is not allowed for this beginnings path")

    # Lineage must be complete (family or tarot card)
    errors.extend(get_lineage_errors(draft))

    # CG points must not be over budget
    remaining = draft.calculate_cg_points_remaining()
    if remaining < 0:
        errors.append(f"CG points over budget by {abs(remaining)}")

    return errors


def get_lineage_errors(draft: CharacterDraft) -> list[str]:
    """Return validation errors for the Lineage stage."""
    # Family chosen completes lineage (family provides surname)
    if draft.family is not None:
        return []
    # Familyless characters (orphan or unknown origins) need a tarot card
    is_familyless = (
        draft.selected_beginnings and not draft.selected_beginnings.family_known
    ) or draft.draft_data.get("lineage_is_orphan", False)
    if is_familyless:
        if not draft.draft_data.get("tarot_card_name"):
            return ["Select a tarot card for your surname"]
        return []
    return ["Select a family"]


def get_distinctions_errors(draft: CharacterDraft) -> list[str]:
    """Return validation errors for the Distinctions stage."""
    errors: list[str] = []
    if not draft.draft_data.get("traits_complete", False):
        errors.append("Confirm your distinction selections")
    remaining = draft.calculate_cg_points_remaining()
    if remaining < 0:
        errors.append(f"CG points over budget by {abs(remaining)}")
    return errors


def get_path_errors(draft: CharacterDraft) -> list[str]:
    """Return validation errors for the Path stage.

    Skill point allocation used to be validated here too (Stage was "Path &
    Skills"); it now lives under the Attributes & Skills stage — see
    ``get_skill_allocation_errors`` (#2426).
    """
    if not draft.selected_path:
        return ["Select a path"]
    return []


def get_skill_allocation_errors(draft: CharacterDraft) -> list[str]:
    """Return validation errors for skill point allocation.

    Moved from the Path stage into the Attributes & Skills stage (#2426) —
    skills are now allocated alongside primary attributes, not path selection.
    """
    errors: list[str] = []
    try:
        draft.validate_path_skills()
    except serializers.ValidationError as exc:
        # Extract message(s) from DRF ValidationError
        if isinstance(exc.detail, list):
            errors.extend(str(d) for d in exc.detail)
        elif isinstance(exc.detail, str):
            errors.append(exc.detail)
        else:
            errors.append(str(exc.detail))
    return errors


def get_attributes_errors(draft: CharacterDraft) -> list[str]:
    """Return validation errors for the Attributes & Skills stage."""
    errors: list[str] = [*get_skill_allocation_errors(draft)]
    stats = draft.draft_data.get("stats", {})

    # All 12 stats must exist
    missing = [s for s in REQUIRED_STATS if s not in stats]
    if missing:
        errors.append(f"Missing stats: {', '.join(missing)}")
        return errors  # Can't validate values if stats are missing

    # Validate each stat value
    for stat_name, value in stats.items():
        if stat_name not in REQUIRED_STATS:
            continue
        if not isinstance(value, int):
            errors.append(f"{stat_name} has invalid value")
        elif not (STAT_MIN_VALUE <= value <= STAT_MAX_VALUE):
            errors.append(f"{stat_name} must be between {STAT_MIN_VALUE} and {STAT_MAX_VALUE}")

    remaining = draft.calculate_points_remaining()
    if remaining > 0:
        errors.append(f"{remaining} point(s) remaining to allocate")
    elif remaining < 0:
        errors.append(f"{abs(remaining)} point(s) over budget")

    return errors


def get_appearance_errors(draft: CharacterDraft) -> list[str]:
    """Return validation errors for the Appearance stage."""
    errors: list[str] = []
    if draft.age is None:
        errors.append("Set your character's age")
    if draft.height_band is None:
        errors.append("Select a height band")
    if draft.height_inches is None:
        errors.append("Set exact height")
    if draft.build is None:
        errors.append("Select a build")
    return errors


def get_identity_errors(draft: CharacterDraft) -> list[str]:
    """Return validation errors for the Identity stage."""
    if not draft.draft_data.get("first_name"):
        return ["Enter a first name"]
    return []


# ---------------------------------------------------------------------------
# Magic stage validators
# ---------------------------------------------------------------------------


def compute_magic_errors(draft: CharacterDraft) -> list[str]:  # noqa: PLR0911
    """Compute validation errors for the Magic stage (Gift/technique picks, #2426).

    Gift-stage validation, in order (return-first style):
    1. Must have selected_tradition.
    2. Must have selected_gift_id, and it must be one of the gifts available for
       the draft's (tradition, path) per ``cg_catalog.get_gift_options``.
    3. Must have >=1 selected_technique_ids, each drawn from the chosen gift's
       pool ∪ signature availability set, and no more than
       ``draft.starting_technique_picks``.
    4. Must have selected_gift_resonance_id (anchors the latent GIFT thread, #1620).
    5. Must have a valid anima_check_stat_id (a Trait with trait_type=STAT) and a
       valid anima_check_skill_id (an active Skill) — the character's Anima Check.
    """
    from world.magic.services.cg_catalog import (  # noqa: PLC0415
        get_gift_options,
        get_technique_options,
    )
    from world.skills.models import Skill  # noqa: PLC0415
    from world.traits.models import Trait, TraitType  # noqa: PLC0415

    if not draft.selected_tradition:
        return ["Select a tradition"]

    gift_id = draft.draft_data.get("selected_gift_id")
    if not gift_id:
        return ["Select a gift"]

    gift_options = get_gift_options(draft.selected_tradition, draft.selected_path)
    gift = next((g for g in gift_options if g.id == gift_id), None)
    if gift is None:
        return ["Select a valid gift for your tradition"]

    technique_ids = draft.draft_data.get("selected_technique_ids") or []
    if not technique_ids:
        return ["Select at least one technique"]

    technique_options = get_technique_options(draft.selected_path, gift, draft.selected_tradition)
    available_ids = {t.id for t in technique_options.pool} | {
        t.id for t in technique_options.signature
    }
    if any(technique_id not in available_ids for technique_id in technique_ids):
        return ["Selected technique is not available"]

    picks = draft.starting_technique_picks
    if len(technique_ids) > picks:
        return [f"You may select at most {picks} techniques"]

    # Resonance is required — anchors the latent GIFT thread (#1620)
    resonance_id = draft.draft_data.get("selected_gift_resonance_id")
    if not resonance_id:
        return ["Select a gift resonance"]

    stat_id = draft.draft_data.get("anima_check_stat_id")
    skill_id = draft.draft_data.get("anima_check_skill_id")
    stat_valid = (
        bool(stat_id) and Trait.objects.filter(pk=stat_id, trait_type=TraitType.STAT).exists()
    )
    skill_valid = bool(skill_id) and Skill.objects.filter(pk=skill_id, is_active=True).exists()
    if not (stat_valid and skill_valid):
        return ["Choose the stat and skill your magic rolls (your Anima Check)"]

    return []
