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
    FamilyPath,
    Stage,
)
from world.character_creation.types import StageValidationErrors

if TYPE_CHECKING:
    from world.character_creation.models import CharacterDraft, OriginTemplate


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


def get_draft_parent_lines(draft: CharacterDraft) -> list:
    """Heredity ParentLines for a draft's parents (#2815).

    Claimed kin slot: derive from the slot node's authored true edges.
    Invented parents: the dominant line is implicit (the child's species, per
    back-inference) and only a declared cross-species other parent
    contributes; player-invented parents are always band-null.
    """
    from world.roster.services.heredity import ParentLine, derive_lines_for_child  # noqa: PLC0415

    if draft.claimed_kin_slot is not None:
        return derive_lines_for_child(draft.claimed_kin_slot)
    if draft.second_parent_species is not None:
        return [
            ParentLine(
                kinsperson=None,
                species=draft.selected_species,
                band=None,
                is_dominant_role=True,
            ),
            ParentLine(
                kinsperson=None,
                species=draft.second_parent_species,
                band=None,
                is_dominant_role=False,
            ),
        ]
    return []


def _get_heredity_species_errors(draft: CharacterDraft) -> list[str]:
    """Parent Dominance legality for the chosen species (#2815).

    One-directional and creation-time only: a claimed slot's authored parents
    must support the chosen species *now*. When chimeric is possible (both
    parents Grand+), any species is accepted — chimeric offspring are unique
    authored species that no enumeration can predict, and a staff-authored
    slot at that power implies staff intent.
    """
    from world.roster.services.heredity import derivable_species  # noqa: PLC0415

    if draft.selected_species is None or draft.claimed_kin_slot is None:
        return []
    lines = get_draft_parent_lines(draft)
    if not lines:
        return []
    derivation = derivable_species(lines, fallback_maternal=draft.selected_species)
    if draft.selected_species in derivation.allowed or derivation.chimeric_possible:
        return []
    allowed_names = ", ".join(species.name for species in derivation.allowed)
    return [
        f"{draft.selected_species.name} is not derivable from this slot's parents "
        f"(allowed: {allowed_names})"
    ]


def get_lineage_errors(draft: CharacterDraft) -> list[str]:
    """Return validation errors for the Lineage stage (#3617).

    Upbringing chosen and accessible -> family path resolved -> path-specific
    completion -> every required prompt on that path answered.
    """
    errors: list[str] = []
    if (
        draft.second_parent_species is not None
        and not str(draft.draft_data.get("other_parent_name", "")).strip()
    ):
        errors.append("Name the parent whose species you selected")
    errors.extend(_get_heredity_species_errors(draft))

    template = draft.selected_origin_template
    if template is None:
        errors.append("Choose your upbringing")
        return errors
    wrong_beginning = (
        draft.selected_beginnings_id is not None
        and template.beginning_id != draft.selected_beginnings_id
    )
    if wrong_beginning:
        errors.append("Your upbringing does not belong to your beginning")
        return errors
    if not template.is_accessible_by(draft.account):
        errors.append("That upbringing is not available to you")
    path = draft.resolve_family_path()
    if not path:
        errors.append("Choose how your family fits your upbringing")
        return errors
    errors.extend(_get_family_path_errors(draft, path))
    errors.extend(_get_prompt_errors(draft, template, path))
    return errors


def _get_family_path_errors(draft: CharacterDraft, path: str) -> list[str]:
    from world.character_creation.services import family_name_is_taken  # noqa: PLC0415

    template = draft.selected_origin_template
    if path == FamilyPath.NONE:
        if draft.draft_data.get("tarot_card_name"):
            return []
        return ["Select a tarot card for your surname"]
    if path == FamilyPath.NAMED:
        name = str(draft.draft_data.get("new_family_name", "")).strip()
        if not name:
            return ["Name your family"]
        if family_name_is_taken(name):
            return ["A family by that name already exists"]
        return []
    family = draft.family
    if family is None:
        return ["Select a family"]
    if not family.is_playable:
        return ["That family is not open to this upbringing"]
    kinds = list(template.claimable_kinds.all())
    if kinds and family.kind not in kinds:
        return ["That family is not open to this upbringing"]
    area_realm = draft.selected_area.realm if draft.selected_area else None
    realm_mismatch = (
        family.origin_realm is not None
        and area_realm is not None
        and family.origin_realm != area_realm
    )
    if realm_mismatch:
        return ["That family is not from your starting area"]
    return []


def _get_prompt_errors(draft: CharacterDraft, template: OriginTemplate, path: str) -> list[str]:
    from collections import defaultdict  # noqa: PLC0415

    from world.character_creation.models import OriginTemplateSlotChoice  # noqa: PLC0415

    errors: list[str] = []
    texts = draft.draft_data.get("origin_slots") or {}
    picks = draft.draft_data.get("origin_choices") or {}
    slots = list(template.slots.order_by("sort_order"))
    choices_by_slot: dict[int, list] = defaultdict(list)
    for choice in OriginTemplateSlotChoice.objects.filter(slot__template=template, is_active=True):
        choices_by_slot[choice.slot_id].append(choice)
    for slot in slots:
        if slot.applies_to not in (FamilyPath.ANY, path):
            continue
        active_choices = choices_by_slot.get(slot.id, [])
        choice_id = picks.get(str(slot.id))
        text = str(texts.get(str(slot.id), "")).strip()
        picked = None
        if choice_id is not None:
            picked = next((c for c in active_choices if c.id == int(choice_id)), None)
            if picked is None:
                errors.append(f"Invalid choice for {slot.name}")
                continue
        answered = picked is not None or (slot.allows_text and bool(text))
        if slot.is_required and not answered:
            errors.append(f"{slot.name} is required")
    return errors


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


def _get_form_trait_errors(draft: CharacterDraft) -> list[str]:
    """Required traits + palette legality for form-trait picks (#2815).

    Every ``is_required`` trait for the species needs a selection, and every
    selected option must sit in the species' own palette or among the
    inherited options a cross-species parent makes legal (pinned-aware).
    """
    from world.forms.models import SpeciesFormTrait  # noqa: PLC0415
    from world.roster.services.heredity import (  # noqa: PLC0415
        base_trait_options,
        inherited_options,
    )

    species = draft.selected_species
    if species is None:
        return []
    errors: list[str] = []
    selections = draft.draft_data.get("form_traits") or {}

    required_links = SpeciesFormTrait.objects.filter(
        species=species, is_available_in_cg=True, is_required=True
    ).select_related("trait")
    errors.extend(
        f"Select a {link.trait.display_name}"
        for link in required_links
        if not selections.get(link.trait.name)
    )

    if not selections:
        return errors

    # Legality is scoped per offered trait: a trait the species has no
    # SpeciesFormTrait link for was never offered — finalize silently skips
    # it (pre-#2815 behavior), so validation ignores it too. Children of
    # fully-defined parents work from the family look (base_trait_options
    # narrows a trait to the parents' pins when every line carries one).
    lines = get_draft_parent_lines(draft)
    base_palette = base_trait_options(species, lines)
    legal_by_trait: dict[str, set[int]] = {
        trait.name: {opt.pk for opt in options} for trait, options in base_palette.items()
    }
    if lines:
        for entry in inherited_options(species, lines):
            legal_by_trait.setdefault(entry.trait.name, set()).update(
                opt.pk for opt in entry.options
            )
    trait_names = {trait.name: trait.display_name for trait in base_palette}
    for trait_name, option_id in selections.items():
        legal = legal_by_trait.get(trait_name)
        if legal is None:
            continue
        if isinstance(option_id, int) and option_id not in legal:
            display = trait_names.get(trait_name, trait_name)
            errors.append(f"{display} selection is not available to your species or lineage")
    return errors


def get_appearance_errors(draft: CharacterDraft) -> list[str]:
    """Return validation errors for the Appearance stage."""
    errors: list[str] = []
    if draft.age is None:
        errors.append("Set your character's age")
    if draft.birthday_month is None or draft.birthday_day is None:
        errors.append("Pick your character's birthday")
    if draft.height_band is None:
        errors.append("Select a height band")
    if draft.height_inches is None:
        errors.append("Set exact height")
    if draft.build is None:
        errors.append("Select a build")
    errors.extend(_get_form_trait_errors(draft))
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
    from world.magic.models import Resonance  # noqa: PLC0415
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
        t.id for t in technique_options.tradition
    }
    if any(technique_id not in available_ids for technique_id in technique_ids):
        return ["Selected technique is not available"]

    picks = draft.starting_technique_picks
    if len(technique_ids) > picks:
        return [f"You may select at most {picks} techniques"]

    # Resonance is required — anchors the latent GIFT thread (#1620). The pick
    # must also still RESOLVE: a stale id (pointing at a since-deleted Resonance)
    # is worthless to the grant-time resolver at finalize (#2971), so it fails
    # validation here rather than raising GiftResonanceUnresolvable at submit.
    resonance_id = draft.draft_data.get("selected_gift_resonance_id")
    if not resonance_id or not Resonance.objects.filter(pk=resonance_id).exists():
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
