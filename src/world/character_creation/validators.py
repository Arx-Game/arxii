"""Stage validation functions for character creation.

Each function takes a CharacterDraft instance and returns a list of
human-readable error messages. An empty list means the stage is complete.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from rest_framework import serializers

from world.character_creation.constants import (
    REQUIRED_STATS,
    STAT_DISPLAY_DIVISOR,
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
        Stage.PATH_SKILLS: get_path_skills_errors(draft),
        Stage.ATTRIBUTES: get_attributes_errors(draft),
        Stage.MAGIC: compute_magic_errors(draft),
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


def get_path_skills_errors(draft: CharacterDraft) -> list[str]:
    """Return validation errors for the Path & Skills stage."""
    errors: list[str] = []
    if not draft.selected_path:
        errors.append("Select a path")
    if not draft.selected_tradition:
        errors.append("Select a tradition")
    if errors:
        return errors  # Can't validate skills without path/tradition

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
    """Return validation errors for the Attributes stage."""
    errors: list[str] = []
    stats = draft.draft_data.get("stats", {})

    # All 9 stats must exist
    missing = [s for s in REQUIRED_STATS if s not in stats]
    if missing:
        errors.append(f"Missing stats: {', '.join(missing)}")
        return errors  # Can't validate values if stats are missing

    # Validate each stat value
    for stat_name, value in stats.items():
        if not isinstance(value, int):
            errors.append(f"{stat_name} has invalid value (not an integer)")
        elif value % STAT_DISPLAY_DIVISOR != 0:
            errors.append(
                f"{stat_name} has invalid value (not a multiple of {STAT_DISPLAY_DIVISOR})"
            )
        elif not (STAT_MIN_VALUE <= value <= STAT_MAX_VALUE):
            errors.append(
                f"{stat_name} is out of range (must be {STAT_MIN_VALUE}-{STAT_MAX_VALUE})"
            )

    # Free points must be exactly 0
    free_points = draft.calculate_stats_free_points()
    if free_points > 0:
        errors.append(f"{free_points} free point(s) remaining")
    elif free_points < 0:
        errors.append(f"{abs(free_points)} point(s) over budget")

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


def compute_magic_errors(draft: CharacterDraft) -> list[str]:
    """Compute validation errors for the Magic stage.

    Cantrip-based validation:
    - Must have selected_cantrip_id in draft_data
    - If cantrip requires_facet, must have selected_facet_id that is in allowed_facets
    """
    from world.magic.models import Cantrip  # noqa: PLC0415

    cantrip_id = draft.draft_data.get("selected_cantrip_id")
    if not cantrip_id:
        return ["Select a cantrip"]

    try:
        cantrip = Cantrip.objects.get(pk=cantrip_id, is_active=True)
    except Cantrip.DoesNotExist:
        return ["Select a valid cantrip"]

    if cantrip.requires_facet:
        facet_id = draft.draft_data.get("selected_facet_id")
        if not facet_id:
            prompt = cantrip.facet_prompt or "Choose your element"
            return [prompt]
        if not cantrip.allowed_facets.filter(pk=facet_id).exists():
            return ["Selected option is not valid for this cantrip"]

    return []
