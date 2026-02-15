"""
Character Creation service functions.

Handles the business logic for character creation, including
draft management and character finalization.
"""

from __future__ import annotations

from datetime import timedelta
import logging
from typing import TYPE_CHECKING

from django.db import transaction
from django.utils import timezone
from evennia.utils import create

from world.character_creation.constants import ApplicationStatus, CommentType
from world.character_creation.models import CharacterDraft
from world.character_creation.types import ProjectedResonance, ResonanceSource
from world.forms.services import calculate_weight
from world.roster.models import Roster, RosterEntry

if TYPE_CHECKING:
    from evennia.accounts.models import AccountDB

    from world.character_creation.models import (
        DraftApplication,
        DraftApplicationComment,
        DraftMotif,
        DraftMotifResonance,
    )
    from world.character_sheets.models import CharacterSheet

logger = logging.getLogger(__name__)


class CharacterCreationError(Exception):
    """Base exception for character creation errors.

    These contain user-safe validation messages intended for API responses,
    not stack traces or internal details. Access via .reason for clarity.
    """

    @property
    def reason(self) -> str:
        return str(self)


class DraftIncompleteError(CharacterCreationError):
    """Raised when attempting to finalize an incomplete draft."""


class DraftExpiredError(CharacterCreationError):
    """Raised when attempting to use an expired draft."""


@transaction.atomic
def finalize_character(  # noqa: C901, PLR0912, PLR0915
    draft: CharacterDraft, *, add_to_roster: bool = False
):
    """
    Create a Character from a completed CharacterDraft.

    Args:
        draft: The completed CharacterDraft to finalize
        add_to_roster: If True, skip application and add directly to roster (staff/GM only)

    Returns:
        The created Character object

    Raises:
        DraftIncompleteError: If required stages are not complete
        DraftExpiredError: If the draft has expired
    """
    from typeclasses.characters import Character  # noqa: F401, PLC0415

    # Validate draft state
    if draft.is_expired:
        msg = "This character draft has expired due to inactivity."
        raise DraftExpiredError(msg)

    if not draft.can_submit():
        incomplete = [
            CharacterDraft.Stage(stage).label
            for stage, complete in draft.get_stage_completion().items()
            if not complete and stage != CharacterDraft.Stage.REVIEW
        ]
        msg = f"Cannot finalize: incomplete stages: {', '.join(incomplete)}"
        raise DraftIncompleteError(msg)

    # Build character name
    first_name = draft.draft_data.get("first_name", "")
    family_name = ""
    if draft.family:
        family_name = draft.family.name
    elif draft.selected_beginnings and not draft.selected_beginnings.family_known:
        family_name = ""  # Special beginnings characters have no family name initially

    if family_name:
        full_name = f"{first_name} {family_name}"
    else:
        full_name = first_name

    # Resolve starting room
    starting_room = draft.get_starting_room()

    # Create the Character object using Evennia's create_object
    character = create.create_object(
        typeclass="typeclasses.characters.Character",
        key=full_name,
        location=starting_room,
        home=starting_room,  # Set home to starting room as well
        nohome=starting_room is None,  # Allow no home if no starting room
    )

    # Create or update CharacterSheet with canonical data
    from world.character_sheets.models import CharacterSheet, Heritage  # noqa: PLC0415

    sheet, _ = CharacterSheet.objects.get_or_create(character=character)

    # Set demographic data from draft's FK references
    if draft.selected_gender:
        sheet.gender = draft.selected_gender
        # Auto-derive pronouns from gender
        _set_pronouns_from_gender(sheet, draft.selected_gender)
    if draft.age:
        sheet.age = draft.age

    # Set species from draft's selected species
    if draft.selected_species:
        sheet.species = draft.selected_species

    # Set family from draft
    if draft.family:
        sheet.family = draft.family

    # Set heritage based on selected beginnings
    # Note: Heritage model in character_sheets is for lore/special types
    # For now, set a default "Normal" heritage; future work may link Beginnings to Heritage
    normal_heritage, _ = Heritage.objects.get_or_create(
        name="Normal",
        defaults={
            "description": "Standard upbringing with known family.",
            "is_special": False,
            "family_known": True,
        },
    )
    sheet.heritage = normal_heritage

    # Set origin realm from the selected starting area
    if draft.selected_area and draft.selected_area.realm:
        sheet.origin_realm = draft.selected_area.realm

    # Set descriptive text from draft_data
    draft_data = draft.draft_data
    if draft_data.get("description"):
        sheet.additional_desc = draft_data["description"]
    if draft_data.get("background"):
        sheet.background = draft_data["background"]
    if draft_data.get("personality"):
        sheet.personality = draft_data["personality"]
    if draft_data.get("concept"):
        sheet.concept = draft_data["concept"]

    # Set physical characteristics from draft
    if draft.height_inches:
        sheet.true_height_inches = draft.height_inches
    if draft.build:
        sheet.build = draft.build
        # Calculate weight if we have both height and build
        if draft.height_inches:
            sheet.weight_pounds = calculate_weight(draft.height_inches, draft.build)

    sheet.save()

    character.save()

    # Create stat values from draft (optimized with bulk operations)
    from world.traits.models import CharacterTraitValue, Trait, TraitType  # noqa: PLC0415

    stats = draft.draft_data.get("stats", {})
    if stats:
        # Fetch all stat traits in one query
        stat_names = list(stats.keys())
        traits_by_name = {
            trait.name: trait
            for trait in Trait.objects.filter(name__in=stat_names, trait_type=TraitType.STAT)
        }

        # Create trait values in bulk
        trait_values = [
            CharacterTraitValue(character=character, trait=traits_by_name[name], value=value)
            for name, value in stats.items()
            if name in traits_by_name
        ]
        CharacterTraitValue.objects.bulk_create(trait_values)

    # Create skill values from draft
    _create_skill_values(character, draft)

    # Create goal records from draft
    _build_and_create_goals(character, draft)

    # Create distinction records and their modifiers
    _create_distinctions(character, draft)

    # Create path history record
    if draft.selected_path:
        from world.progression.models import CharacterPathHistory  # noqa: PLC0415

        CharacterPathHistory.objects.create(
            character=character,
            path=draft.selected_path,
        )

    # Apply post-CG bonuses if any (from other stages exceeding 5)
    # NOTE: This is reserved for future functionality where other CG stages might
    # modify stats beyond the normal 1-5 range. Not currently used.
    # TODO: Implement when heritage/path bonuses are added
    post_cg_bonuses = draft.draft_data.get("stats_post_cg_bonuses", {})
    if post_cg_bonuses:
        for stat_name, bonus in post_cg_bonuses.items():
            trait_value = CharacterTraitValue.objects.filter(
                character=character, trait__name=stat_name
            ).first()
            if trait_value:
                trait_value.value += int(bonus * 10)
                trait_value.save()

    # Handle roster assignment
    if add_to_roster:
        # Staff/GM directly adding to roster - no application needed
        roster = _get_or_create_available_roster()
        RosterEntry.objects.create(
            character=character,
            roster=roster,
        )
    else:
        # Player submission - create application for review
        # TODO: Create RosterApplication when that workflow is implemented
        # For now, create entry in a "Pending" roster
        roster = _get_or_create_pending_roster()
        RosterEntry.objects.create(
            character=character,
            roster=roster,
        )

    # Family is already set on CharacterSheet above

    # Finalize magic data before deleting draft
    finalize_magic_data(draft, sheet)

    # Clean up the draft (CASCADE deletes all Draft* models)
    draft.delete()

    return character


def _set_pronouns_from_gender(sheet, gender) -> None:
    """
    Set pronoun fields on CharacterSheet based on selected gender.

    Maps gender key to default pronouns:
    - male → he/him/his
    - female → she/her/her
    - nonbinary, other → they/them/their (default)
    """
    pronoun_map = {
        "male": ("he", "him", "his"),
        "female": ("she", "her", "her"),
    }

    # Default to they/them/their for non-binary or unrecognized gender keys
    subject, obj, possessive = pronoun_map.get(gender.key, ("they", "them", "their"))

    sheet.pronoun_subject = subject
    sheet.pronoun_object = obj
    sheet.pronoun_possessive = possessive


def _get_or_create_available_roster() -> Roster:
    """Get or create the 'Available' roster for staff-added characters."""
    roster, _ = Roster.objects.get_or_create(
        name="Available",
        defaults={
            "description": "Characters available for players to apply for",
            "is_active": True,
            "is_public": True,
            "allow_applications": True,
        },
    )
    return roster


def _get_or_create_pending_roster() -> Roster:
    """Get or create the 'Pending' roster for characters awaiting approval."""
    roster, _ = Roster.objects.get_or_create(
        name="Pending",
        defaults={
            "description": "Characters awaiting staff approval",
            "is_active": False,
            "is_public": False,
            "allow_applications": False,
        },
    )
    return roster


def _build_and_create_goals(character, draft: CharacterDraft) -> list:
    """
    Build CharacterGoal instances from draft_data and create them.

    Serializer validated the domain PKs; this builds instances and bulk creates.
    """
    from world.goals.constants import GoalStatus  # noqa: PLC0415
    from world.goals.models import CharacterGoal  # noqa: PLC0415
    from world.mechanics.models import ModifierType  # noqa: PLC0415

    goals_data = draft.draft_data.get("goals", [])
    if not goals_data:
        return []

    # Fetch all needed domains in one query
    domain_ids = [g.get("domain_id") for g in goals_data if g.get("domain_id")]
    domains_by_id = {d.id: d for d in ModifierType.objects.filter(id__in=domain_ids)}

    # Build and create instances
    goals_to_create = [
        CharacterGoal(
            character=character,
            domain=domains_by_id[g["domain_id"]],
            points=g["points"],
            notes=g.get("notes", ""),
            status=GoalStatus.ACTIVE,
        )
        for g in goals_data
        if g.get("domain_id") in domains_by_id and g.get("points", 0) > 0
    ]

    if not goals_to_create:
        return []

    return CharacterGoal.objects.bulk_create(goals_to_create)


def _create_distinctions(character, draft: CharacterDraft) -> None:
    """
    Create CharacterDistinction records and their modifiers from draft data.

    Uses bulk operations to avoid per-distinction queries. The chain is:
    1. Bulk-create CharacterDistinction records
    2. Bulk-create ModifierSource + CharacterModifier records for all effects
    3. Aggregate and apply resonance total updates
    """
    from world.distinctions.models import CharacterDistinction, Distinction  # noqa: PLC0415
    from world.distinctions.types import DistinctionOrigin  # noqa: PLC0415

    distinctions_data = draft.draft_data.get("distinctions", [])
    if not distinctions_data:
        return

    # Dict keyed by distinction_id deduplicates entries (CharacterDistinction
    # has unique_together on character+distinction, so duplicates would fail)
    entries_by_id = {d["distinction_id"]: d for d in distinctions_data if d.get("distinction_id")}

    # Fetch all distinctions with effects prefetched in one query
    distinctions = Distinction.objects.filter(id__in=entries_by_id.keys()).prefetch_related(
        "effects__target__category"
    )
    distinctions_by_id = {d.id: d for d in distinctions}

    # Build CharacterDistinction instances
    char_distinctions = []
    for distinction_id, entry in entries_by_id.items():
        distinction = distinctions_by_id.get(distinction_id)
        if not distinction:
            logger.warning(
                "Invalid distinction ID %s in draft for character %s",
                distinction_id,
                character.key,
            )
            continue
        char_distinctions.append(
            CharacterDistinction(
                character=character,
                distinction=distinction,
                rank=entry.get("rank", 1),
                notes=entry.get("notes", ""),
                origin=DistinctionOrigin.CHARACTER_CREATION,
            )
        )

    if not char_distinctions:
        return

    created_distinctions = CharacterDistinction.objects.bulk_create(char_distinctions)
    _create_distinction_modifiers_bulk(character.sheet_data, created_distinctions)


def _create_distinction_modifiers_bulk(sheet, char_distinctions: list) -> None:
    """
    Bulk-create ModifierSource and CharacterModifier records for a list of CharacterDistinctions.

    Expects the distinction FK on each CharacterDistinction to have effects prefetched.
    """
    from world.magic.services import add_resonance_total  # noqa: PLC0415
    from world.mechanics.models import CharacterModifier, ModifierSource  # noqa: PLC0415

    # Build ModifierSource instances for all effects across all distinctions
    sources = []
    source_effect_ranks = []  # parallel list: (effect, rank) per source
    for char_dist in char_distinctions:
        for effect in char_dist.distinction.effects.all():  # prefetched, no query
            sources.append(
                ModifierSource(
                    distinction_effect=effect,
                    character_distinction=char_dist,
                )
            )
            source_effect_ranks.append((effect, char_dist.rank))

    if not sources:
        return

    created_sources = ModifierSource.objects.bulk_create(sources)

    # Build CharacterModifier instances and collect resonance updates
    modifiers = []
    resonance_totals: dict = {}

    for source, (effect, rank) in zip(created_sources, source_effect_ranks, strict=True):
        value = effect.get_value_at_rank(rank)
        modifiers.append(
            CharacterModifier(
                character=sheet,
                value=value,
                source=source,
            )
        )
        if effect.target.category.name == "resonance":
            resonance_totals[effect.target] = resonance_totals.get(effect.target, 0) + value

    CharacterModifier.objects.bulk_create(modifiers)

    # Apply aggregated resonance updates
    for resonance_type, total_value in resonance_totals.items():
        add_resonance_total(sheet, resonance_type, total_value)


def _create_skill_values(character, draft: CharacterDraft) -> None:
    """Create CharacterSkillValue and CharacterSpecializationValue records from draft."""
    from world.skills.models import (  # noqa: PLC0415
        CharacterSkillValue,
        CharacterSpecializationValue,
        Skill,
        Specialization,
    )

    skills_data = draft.draft_data.get("skills", {})
    specializations_data = draft.draft_data.get("specializations", {})

    # Create skill values
    for skill_id, value in skills_data.items():
        if value > 0:
            try:
                skill = Skill.objects.get(pk=int(skill_id))
                CharacterSkillValue.objects.create(
                    character=character,
                    skill=skill,
                    value=value,
                    development_points=0,
                    rust_points=0,
                )
            except Skill.DoesNotExist:
                logger.warning(
                    "Invalid skill ID %s in draft for character %s",
                    skill_id,
                    character.key,
                )

    # Create specialization values
    for spec_id, value in specializations_data.items():
        if value > 0:
            try:
                spec = Specialization.objects.get(pk=int(spec_id))
                CharacterSpecializationValue.objects.create(
                    character=character,
                    specialization=spec,
                    value=value,
                    development_points=0,
                )
            except Specialization.DoesNotExist:
                logger.warning(
                    "Invalid specialization ID %s in draft for character %s",
                    spec_id,
                    character.key,
                )


def get_accessible_starting_areas(account):
    """
    Get all starting areas accessible to an account.

    Args:
        account: The AccountDB instance

    Returns:
        QuerySet of StartingArea objects the account can select
    """
    from world.character_creation.models import StartingArea  # noqa: PLC0415

    areas = StartingArea.objects.filter(is_active=True)

    if account.is_staff:
        return areas

    # Filter by access level
    accessible_ids = [area.id for area in areas if area.is_accessible_by(account)]

    return areas.filter(id__in=accessible_ids)


def can_create_character(account) -> tuple[bool, str]:
    """
    Check if an account can create a new character.

    Args:
        account: The AccountDB instance

    Returns:
        Tuple of (can_create: bool, reason: str)
    """
    # Staff bypass all restrictions
    if account.is_staff:
        return True, ""

    # Check email verification
    # TODO: Integrate with actual email verification system
    if hasattr(account, "email_verified") and not account.email_verified:
        return False, "Email verification required"

    # Check trust level
    # TODO: Implement trust system
    try:
        trust = account.trust
    except AttributeError:
        msg = "Trust system not yet implemented on Account model"
        raise NotImplementedError(msg) from None
    if trust < 0:
        return False, "Account trust level too low"

    # Check character limit
    # TODO: Make this configurable via django settings or model
    max_characters = 3
    current_count = account.character_drafts.count()
    # TODO: Also count actual characters owned by account
    if current_count >= max_characters:
        return False, f"Maximum of {max_characters} characters reached"

    return True, ""


@transaction.atomic
def finalize_magic_data(draft: CharacterDraft, sheet: CharacterSheet) -> None:
    """
    Convert Draft* magic models to real models.

    Called during finalize_character() after CharacterSheet is created.
    Each Draft* model has a convert_to_real_version() method that handles
    its own conversion logic.

    Also creates Reincarnation records for gifts granted by Old Soul,
    and applies bonus resonance values.
    """
    from world.character_creation.models import (  # noqa: PLC0415
        DraftAnimaRitual,
        DraftMotif,
    )
    from world.magic.models import Reincarnation  # noqa: PLC0415
    from world.magic.services import add_resonance_total  # noqa: PLC0415

    # 1. Finalize Gifts (each gift converts its own techniques)
    for draft_gift in draft.draft_gifts_new.select_related(
        "source_distinction",
    ).all():
        real_gift = draft_gift.convert_to_real_version(sheet)

        # Create Reincarnation record for gifts from Old Soul
        if draft_gift.source_distinction is not None:
            Reincarnation.objects.create(character=sheet, gift=real_gift)

        # Apply bonus resonance value
        if draft_gift.bonus_resonance_value:
            for resonance in real_gift.resonances.all():
                add_resonance_total(
                    sheet,
                    resonance,
                    draft_gift.bonus_resonance_value,
                )

    # 2. Finalize Motif (optional - only if player created one)
    draft_motif = DraftMotif.objects.filter(draft=draft).first()
    if draft_motif:
        draft_motif.convert_to_real_version(sheet)

    # 3. Finalize Anima Ritual (optional - only if player created one)
    draft_ritual = DraftAnimaRitual.objects.filter(draft=draft).first()
    if draft_ritual:
        draft_ritual.convert_to_real_version(sheet)


@transaction.atomic
def ensure_draft_motif(draft: CharacterDraft) -> DraftMotif:
    """
    Ensure a DraftMotif exists for the given draft and sync its resonances.

    Creates the DraftMotif if it doesn't exist, then syncs DraftMotifResonance
    records from gift resonances (is_from_gift=True) and projected resonances
    from distinctions (is_from_gift=False).

    Idempotent — safe to call multiple times.

    Args:
        draft: The CharacterDraft to ensure a motif for.

    Returns:
        The DraftMotif instance.
    """
    from world.character_creation.models import DraftMotif  # noqa: PLC0415

    motif, _ = DraftMotif.objects.get_or_create(draft=draft)

    gift_resonance_ids = _collect_gift_resonance_ids(draft)
    projected_resonance_ids = {p.resonance_id for p in get_projected_resonances(draft)}
    existing = {(mr.resonance_id, mr.is_from_gift): mr for mr in motif.resonances.all()}

    _add_missing_resonances(motif, gift_resonance_ids, projected_resonance_ids, existing)
    _remove_stale_resonances(existing, gift_resonance_ids, projected_resonance_ids)

    motif.refresh_from_db()
    return motif


def _collect_gift_resonance_ids(draft: CharacterDraft) -> set[int]:
    """Collect resonance IDs from all draft gifts."""
    ids: set[int] = set()
    for gift in draft.draft_gifts_new.prefetch_related("resonances").all():
        for res in gift.resonances.all():
            ids.add(res.id)
    return ids


def _add_missing_resonances(
    motif: DraftMotif,
    gift_ids: set[int],
    projected_ids: set[int],
    existing: dict[tuple[int, bool], DraftMotifResonance],
) -> None:
    """Add DraftMotifResonance records that are expected but missing."""
    from world.character_creation.models import DraftMotifResonance  # noqa: PLC0415

    for res_id in gift_ids:
        if (res_id, True) not in existing:
            DraftMotifResonance.objects.get_or_create(
                motif=motif, resonance_id=res_id, defaults={"is_from_gift": True}
            )

    for res_id in projected_ids:
        if (res_id, False) not in existing:
            if not DraftMotifResonance.objects.filter(motif=motif, resonance_id=res_id).exists():
                DraftMotifResonance.objects.create(
                    motif=motif, resonance_id=res_id, is_from_gift=False
                )


def _remove_stale_resonances(
    existing: dict[tuple[int, bool], DraftMotifResonance],
    gift_ids: set[int],
    projected_ids: set[int],
) -> None:
    """Remove DraftMotifResonance records that are no longer expected."""
    for (res_id, is_from_gift), mr in existing.items():
        is_stale = (is_from_gift and res_id not in gift_ids) or (
            not is_from_gift and res_id not in projected_ids
        )
        if is_stale:
            mr.delete()


def get_projected_resonances(draft: CharacterDraft) -> list[ProjectedResonance]:
    """
    Calculate projected resonance totals from a draft's distinction selections.

    Reads the draft's distinction data, looks up each distinction's effects,
    filters to resonance-category effects, and sums values by resonance type.

    Args:
        draft: The CharacterDraft to project resonances for.

    Returns:
        List of ProjectedResonance dataclasses with resonance totals and source breakdowns.
    """
    from world.distinctions.models import Distinction  # noqa: PLC0415
    from world.mechanics.constants import RESONANCE_CATEGORY_NAME  # noqa: PLC0415

    distinctions_data = draft.draft_data.get("distinctions", [])
    if not distinctions_data:
        return []

    # Build lookup of distinction_id -> rank from draft data
    entries_by_id = {d["distinction_id"]: d for d in distinctions_data if d.get("distinction_id")}
    if not entries_by_id:
        return []

    # Fetch all distinctions with effects and their targets prefetched
    distinctions = Distinction.objects.filter(id__in=entries_by_id.keys()).prefetch_related(
        "effects__target__category"
    )
    distinctions_by_id = {d.id: d for d in distinctions}

    # Aggregate resonance values: keyed by resonance ModifierType id
    resonance_totals: dict[int, ProjectedResonance] = {}

    for distinction_id, entry in entries_by_id.items():
        distinction = distinctions_by_id.get(distinction_id)
        if not distinction:
            continue

        rank = entry.get("rank", 1)
        for effect in distinction.effects.all():
            if effect.target.category.name != RESONANCE_CATEGORY_NAME:
                continue
            value = effect.get_value_at_rank(rank)
            resonance_id = effect.target.id
            if resonance_id not in resonance_totals:
                resonance_totals[resonance_id] = ProjectedResonance(
                    resonance_id=resonance_id,
                    resonance_name=effect.target.name,
                    total=0,
                    sources=[],
                )
            resonance_totals[resonance_id].total += value
            resonance_totals[resonance_id].sources.append(
                ResonanceSource(
                    distinction_name=distinction.name,
                    value=value,
                )
            )

    return list(resonance_totals.values())


@transaction.atomic
def apply_tradition_template(draft: CharacterDraft) -> None:
    """
    Apply a tradition template to a draft, pre-filling magic stage data.

    Looks up the TraditionTemplate for the draft's selected_tradition + selected_path.
    Clears existing magic draft data and creates new DraftGift, DraftTechniques,
    DraftMotif, DraftMotifResonances, DraftMotifResonanceAssociations, and
    DraftAnimaRitual from the template.

    No-op if no template exists for the tradition+path combo, or if tradition/path not set.
    """
    from world.character_creation.models import (  # noqa: PLC0415
        DraftAnimaRitual,
        DraftGift,
        DraftMotif,
        DraftMotifResonance,
        DraftMotifResonanceAssociation,
        DraftTechnique,
        TraditionTemplate,
    )

    if not draft.selected_tradition or not draft.selected_path:
        return

    template = (
        TraditionTemplate.objects.filter(
            tradition=draft.selected_tradition,
            path=draft.selected_path,
        )
        .prefetch_related("techniques", "facets", "resonances")
        .first()
    )

    if not template:
        return

    # Clear existing magic data
    draft.draft_gifts_new.all().delete()
    DraftMotif.objects.filter(draft=draft).delete()
    DraftAnimaRitual.objects.filter(draft=draft).delete()

    # Create DraftGift
    gift = DraftGift.objects.create(
        draft=draft,
        name=template.gift_name,
        description=template.gift_description,
    )
    gift.resonances.set(template.resonances.all())

    # Create DraftTechniques
    for tech in template.techniques.all():
        DraftTechnique.objects.create(
            gift=gift,
            name=tech.name,
            description=tech.description,
            style=tech.style,
            effect_type=tech.effect_type,
        )

    # Create DraftMotif
    motif = DraftMotif.objects.create(
        draft=draft,
        description=template.motif_description,
    )

    # Create DraftMotifResonances from template resonances
    resonance_map = {}
    for resonance in template.resonances.all():
        mr = DraftMotifResonance.objects.create(
            motif=motif,
            resonance=resonance,
            is_from_gift=True,
        )
        resonance_map[resonance.pk] = mr

    # Create DraftMotifResonanceAssociations from template facets
    for facet_entry in template.facets.all():
        motif_resonance = resonance_map.get(facet_entry.resonance_id)
        if motif_resonance:
            DraftMotifResonanceAssociation.objects.create(
                motif_resonance=motif_resonance,
                facet=facet_entry.facet,
            )

    # Create DraftAnimaRitual
    if template.anima_ritual_stat and template.anima_ritual_skill:
        DraftAnimaRitual.objects.create(
            draft=draft,
            stat=template.anima_ritual_stat,
            skill=template.anima_ritual_skill,
            resonance=template.anima_ritual_resonance,
            description=template.anima_ritual_description,
        )


def submit_draft_for_review(
    draft: CharacterDraft, *, submission_notes: str = ""
) -> DraftApplication:
    """
    Submit a character draft for staff review.

    Creates a DraftApplication in SUBMITTED status and logs a status change comment.

    Args:
        draft: The CharacterDraft to submit.
        submission_notes: Optional notes from the player about the submission.

    Returns:
        The created DraftApplication instance.

    Raises:
        ValueError: If the draft already has an application or is not ready to submit.
    """
    from world.character_creation.models import (  # noqa: PLC0415
        DraftApplication,
        DraftApplicationComment,
    )

    if hasattr(draft, "application"):
        try:
            draft.application  # noqa: B018
            msg = "This draft already has an application."
            raise CharacterCreationError(msg)
        except DraftApplication.DoesNotExist:
            pass

    if not draft.can_submit():
        msg = "Draft is not complete enough to submit."
        raise CharacterCreationError(msg)

    application = DraftApplication.objects.create(
        draft=draft,
        status=ApplicationStatus.SUBMITTED,
        submission_notes=submission_notes,
    )
    DraftApplicationComment.objects.create(
        application=application,
        author=None,
        text="Application submitted for review.",
        comment_type=CommentType.STATUS_CHANGE,
    )
    return application


def unsubmit_draft(application: DraftApplication) -> None:
    """
    Un-submit a draft application, returning it to editable state.

    Sets the application status back to REVISIONS_REQUESTED so the player
    can resume editing.

    Args:
        application: The DraftApplication to un-submit.

    Raises:
        ValueError: If the application is not in SUBMITTED status.
    """
    from world.character_creation.models import DraftApplicationComment  # noqa: PLC0415

    if application.status != ApplicationStatus.SUBMITTED:
        msg = "Can only un-submit applications that are in Submitted status."
        raise CharacterCreationError(msg)

    application.status = ApplicationStatus.REVISIONS_REQUESTED
    application.save(update_fields=["status"])
    DraftApplicationComment.objects.create(
        application=application,
        author=None,
        text="Player resumed editing.",
        comment_type=CommentType.STATUS_CHANGE,
    )


def resubmit_draft(application: DraftApplication, *, comment: str = "") -> None:
    """
    Resubmit a draft application after revisions.

    Optionally creates a player message comment before changing status back
    to SUBMITTED.

    Args:
        application: The DraftApplication to resubmit.
        comment: Optional message from the player about changes made.

    Raises:
        ValueError: If the application is not in REVISIONS_REQUESTED status.
    """
    from world.character_creation.models import DraftApplicationComment  # noqa: PLC0415

    if application.status != ApplicationStatus.REVISIONS_REQUESTED:
        msg = "Can only resubmit applications that are in Revisions Requested status."
        raise CharacterCreationError(msg)

    if comment:
        DraftApplicationComment.objects.create(
            application=application,
            author=application.draft.account,
            text=comment,
            comment_type=CommentType.MESSAGE,
        )

    application.status = ApplicationStatus.SUBMITTED
    application.save(update_fields=["status"])
    DraftApplicationComment.objects.create(
        application=application,
        author=None,
        text="Application resubmitted for review.",
        comment_type=CommentType.STATUS_CHANGE,
    )


def withdraw_draft(application: DraftApplication) -> None:
    """
    Withdraw a draft application.

    Sets the application to WITHDRAWN status and schedules soft-delete
    expiry after SOFT_DELETE_DAYS.

    Args:
        application: The DraftApplication to withdraw.

    Raises:
        ValueError: If the application is already in a terminal state.
    """
    from world.character_creation.models import (  # noqa: PLC0415
        SOFT_DELETE_DAYS,
        DraftApplicationComment,
    )

    if application.is_terminal:
        msg = "Cannot withdraw an application that is already in a terminal state."
        raise CharacterCreationError(msg)

    application.status = ApplicationStatus.WITHDRAWN
    application.expires_at = timezone.now() + timedelta(days=SOFT_DELETE_DAYS)
    application.save(update_fields=["status", "expires_at"])
    DraftApplicationComment.objects.create(
        application=application,
        author=None,
        text="Application withdrawn by player.",
        comment_type=CommentType.STATUS_CHANGE,
    )


# ── Staff Review Services ───────────────────────────────────────────────────


def claim_application(application: DraftApplication, *, reviewer: AccountDB) -> None:
    """
    Claim a submitted application for staff review.

    Sets the application to IN_REVIEW, assigns the reviewer, and records the timestamp.

    Args:
        application: The DraftApplication to claim.
        reviewer: The staff AccountDB claiming the application.

    Raises:
        ValueError: If the application is not in SUBMITTED status.
    """
    from world.character_creation.models import DraftApplicationComment  # noqa: PLC0415

    if application.status != ApplicationStatus.SUBMITTED:
        msg = "Can only claim applications that are in Submitted status."
        raise CharacterCreationError(msg)

    application.status = ApplicationStatus.IN_REVIEW
    application.reviewer = reviewer
    application.reviewed_at = timezone.now()
    application.save(update_fields=["status", "reviewer", "reviewed_at"])
    DraftApplicationComment.objects.create(
        application=application,
        author=None,
        text=f"Claimed for review by {reviewer.username}.",
        comment_type=CommentType.STATUS_CHANGE,
    )


@transaction.atomic
def approve_application(
    application: DraftApplication, *, reviewer: AccountDB, comment: str = ""
) -> None:
    """
    Approve an application and finalize the character.

    Optionally creates a staff message comment, then sets status to APPROVED,
    records the reviewer/timestamp, creates a status change comment, and
    calls finalize_character on the draft.

    Args:
        application: The DraftApplication to approve.
        reviewer: The staff AccountDB approving the application.
        comment: Optional message from the reviewer.

    Raises:
        ValueError: If the application is not in IN_REVIEW status.
    """
    from world.character_creation.models import DraftApplicationComment  # noqa: PLC0415

    if application.status != ApplicationStatus.IN_REVIEW:
        msg = "Can only approve applications that are in In Review status."
        raise CharacterCreationError(msg)

    if comment:
        DraftApplicationComment.objects.create(
            application=application,
            author=reviewer,
            text=comment,
            comment_type=CommentType.MESSAGE,
        )

    application.status = ApplicationStatus.APPROVED
    application.reviewer = reviewer
    application.reviewed_at = timezone.now()
    application.save(update_fields=["status", "reviewer", "reviewed_at"])
    DraftApplicationComment.objects.create(
        application=application,
        author=None,
        text=f"Application approved by {reviewer.username}.",
        comment_type=CommentType.STATUS_CHANGE,
    )
    finalize_character(application.draft, add_to_roster=False)


def request_revisions(application: DraftApplication, *, reviewer: AccountDB, comment: str) -> None:
    """
    Request revisions on an application.

    Creates a staff message comment with feedback, then sets status to
    REVISIONS_REQUESTED with a status change comment.

    Args:
        application: The DraftApplication to request revisions on.
        reviewer: The staff AccountDB requesting revisions.
        comment: Required feedback message for the player.

    Raises:
        ValueError: If the application is not in IN_REVIEW status.
        ValueError: If comment is empty.
    """
    from world.character_creation.models import DraftApplicationComment  # noqa: PLC0415

    if application.status != ApplicationStatus.IN_REVIEW:
        msg = "Can only request revisions on applications that are in In Review status."
        raise CharacterCreationError(msg)

    if not comment.strip():
        msg = "A comment is required when requesting revisions."
        raise CharacterCreationError(msg)

    DraftApplicationComment.objects.create(
        application=application,
        author=reviewer,
        text=comment,
        comment_type=CommentType.MESSAGE,
    )

    application.status = ApplicationStatus.REVISIONS_REQUESTED
    application.reviewed_at = timezone.now()
    application.save(update_fields=["status", "reviewed_at"])
    DraftApplicationComment.objects.create(
        application=application,
        author=None,
        text=f"Revisions requested by {reviewer.username}.",
        comment_type=CommentType.STATUS_CHANGE,
    )


def deny_application(application: DraftApplication, *, reviewer: AccountDB, comment: str) -> None:
    """
    Deny an application.

    Creates a staff message comment with the denial reason, then sets status
    to DENIED with reviewer, timestamp, and a 14-day soft-delete expiry.

    Args:
        application: The DraftApplication to deny.
        reviewer: The staff AccountDB denying the application.
        comment: Required denial reason for the player.

    Raises:
        ValueError: If the application is not in IN_REVIEW status.
        ValueError: If comment is empty.
    """
    from world.character_creation.models import (  # noqa: PLC0415
        SOFT_DELETE_DAYS,
        DraftApplicationComment,
    )

    if application.status != ApplicationStatus.IN_REVIEW:
        msg = "Can only deny applications that are in In Review status."
        raise CharacterCreationError(msg)

    if not comment.strip():
        msg = "A comment is required when denying an application."
        raise CharacterCreationError(msg)

    DraftApplicationComment.objects.create(
        application=application,
        author=reviewer,
        text=comment,
        comment_type=CommentType.MESSAGE,
    )

    application.status = ApplicationStatus.DENIED
    application.reviewer = reviewer
    application.reviewed_at = timezone.now()
    application.expires_at = timezone.now() + timedelta(days=SOFT_DELETE_DAYS)
    application.save(update_fields=["status", "reviewer", "reviewed_at", "expires_at"])
    DraftApplicationComment.objects.create(
        application=application,
        author=None,
        text=f"Application denied by {reviewer.username}.",
        comment_type=CommentType.STATUS_CHANGE,
    )


def add_application_comment(
    application: DraftApplication, *, author: AccountDB, text: str
) -> DraftApplicationComment:
    """
    Add a message comment to an application.

    Args:
        application: The DraftApplication to comment on.
        author: The AccountDB authoring the comment.
        text: The comment text.

    Returns:
        The created DraftApplicationComment instance.

    Raises:
        ValueError: If text is empty.
    """
    from world.character_creation.models import DraftApplicationComment  # noqa: PLC0415

    if not text.strip():
        msg = "Comment text cannot be empty."
        raise CharacterCreationError(msg)

    return DraftApplicationComment.objects.create(
        application=application,
        author=author,
        text=text,
        comment_type=CommentType.MESSAGE,
    )
