"""
Character Creation service functions.

Handles the business logic for character creation, including
draft management and character finalization.
"""

from __future__ import annotations

from datetime import timedelta
import logging
from typing import TYPE_CHECKING

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Prefetch, QuerySet
from django.utils import timezone
from evennia.objects.models import ObjectDB

from evennia_extensions.models import PlayerData
from world.character_creation.constants import (
    PATH_OF_THE_CHOSEN_NAME,
    ApplicationStatus,
    CommentType,
    OriginStoryState,
)
from world.character_creation.models import (
    CharacterDraft,
    CharacterOriginSlot,
    OriginTemplate,
    OriginTemplateSlot,
)
from world.character_sheets.services import create_character_with_sheet
from world.forms.services import calculate_weight
from world.roster.models import Roster, RosterEntry, RosterTenure
from world.roster.models.choices import CreationProvenance, RosterType

# "Pending" is CG-specific and not a general roster type in RosterType choices
PENDING_ROSTER_NAME = "Pending"

if TYPE_CHECKING:
    from django.contrib.auth.base_user import AbstractBaseUser
    from django.contrib.auth.models import AnonymousUser
    from evennia.accounts.models import AccountDB

    from world.character_creation.models import (
        DraftApplication,
        DraftApplicationComment,
    )
    from world.character_sheets.models import CharacterSheet, Profile
    from world.scenes.models import Persona
    from world.stories.models import Story

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
def finalize_character(
    draft: CharacterDraft,
    *,
    add_to_roster: bool = False,
    created_by_account: AccountDB | None = None,
) -> ObjectDB:
    """
    Create a Character from a completed CharacterDraft.

    Args:
        draft: The completed CharacterDraft to finalize
        add_to_roster: If True, skip application and add directly to roster (staff/GM only)
        created_by_account: The account authoring this character, stamped on the
            RosterEntry for provenance (#1506). Defaults to the draft's own account.
            ``add_to_roster`` is the staff direct-add path, so it records STAFF
            provenance; the normal player path records PLAYER (an original character).

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
    full_name = _build_character_full_name(draft)

    # Resolve starting room
    starting_room = draft.get_starting_room()

    # Create Character + CharacterSheet + PRIMARY Persona atomically.
    # The service ensures every sheet has a PRIMARY persona, preserving the
    # invariant used everywhere else (tests, factories, etc.).
    character, sheet, primary_persona = create_character_with_sheet(
        character_key=full_name,
        primary_persona_name=full_name,
    )

    # Apply Evennia room/home wiring (not handled by the service).
    if starting_room is not None:
        character.location = starting_room
        character.home = starting_room
        _grant_cg_residence_tenancy(draft, starting_room, primary_persona)
        _grant_prelude_mission(draft, character, primary_persona)
        _grant_orientation_mission(draft, character, primary_persona)

    # Populate sheet fields (demographics, descriptive text, physical traits) and save.
    _apply_sheet_demographics(sheet, draft)

    character.save()

    # Create true form from appearance form traits
    _create_true_form(character, draft.draft_data)

    # Create stat trait values, skills, goals, distinctions, path history, post-CG bonuses
    _apply_character_mechanics(character, draft)

    # Initialize CharacterVitals and set to full health now that class levels / stats exist
    # so derive_base_max_health has meaningful inputs. recompute alone never heals from 0,
    # so we explicitly set health = max_health to give fresh characters a full pool.
    from world.magic.services.threads import recompute_max_health_with_threads  # noqa: PLC0415
    from world.vitals.models import CharacterVitals  # noqa: PLC0415

    vitals, _ = CharacterVitals.objects.get_or_create(character_sheet=sheet)
    recompute_max_health_with_threads(sheet)
    vitals.refresh_from_db()
    vitals.health = vitals.max_health
    vitals.save(update_fields=["health"])

    # Handle roster assignment
    # Provenance signal (#1506): the staff direct-add path is STAFF; the normal
    # self-creation path is PLAYER (an original character). The authoring account
    # defaults to the draft's owner.
    provenance = CreationProvenance.STAFF if add_to_roster else CreationProvenance.PLAYER
    author = created_by_account if created_by_account is not None else draft.account
    if add_to_roster:
        # Staff/GM directly adding to roster - no application needed
        roster = _get_or_create_available_roster()
        RosterEntry.objects.create(
            character_sheet=character.sheet_data,
            roster=roster,
            creation_provenance=provenance,
            created_by_account=author,
        )
    else:
        # Character awaiting approval — placed in Pending roster.
        # approve_application() moves to Active and creates RosterTenure.
        roster = _get_or_create_pending_roster()
        RosterEntry.objects.create(
            character_sheet=character.sheet_data,
            roster=roster,
            creation_provenance=provenance,
            created_by_account=author,
        )

    # Family is already set on CharacterSheet above

    # Property grant: a Beginnings-configured grant profile (if any) hands
    # the new PC an owned building before other CG side-effects run.
    _grant_property_house_if_eligible(draft, primary_persona)

    # House claim materialization (#1884 Phase D): an approved CG-defined
    # house builds its full package now, BEFORE the kinship bind (the founder
    # node must land in the new family). Runs before draft deletion (the
    # claim rides the draft).
    _bind_house_claim(draft, sheet)

    # Kinship graph binding (#2062): claim the chosen slot / mint from the
    # chosen pool, or self-serve a node for the new PC. Runs before draft
    # deletion (the claim FKs live on the draft).
    _bind_kinship_node(draft, sheet)

    # Finalize magic data before deleting draft
    finalize_magic_data(draft, sheet)

    # Reconcile ritual knowledge from grant tables (path, tradition, distinction, codex).
    # Must run AFTER _apply_character_mechanics (path history / distinctions exist)
    # and AFTER finalize_magic_data (codex grants from tradition may have been created).
    # Beginnings ritual grants are NOT walked by reconcile_ritual_knowledge because
    # Beginnings is not stored post-finalization; we handle them here directly (Option A).
    roster_entry = character.sheet_data.roster_entry
    _grant_beginnings_ritual_knowledge(draft, roster_entry)
    from world.magic.services.ritual_knowledge import reconcile_ritual_knowledge  # noqa: PLC0415

    reconcile_ritual_knowledge(roster_entry)

    # Convert unspent CG points to locked XP (best-effort: don't block finalization)
    _convert_remaining_cg_points_to_xp(draft, character)

    # Clean up the draft (CASCADE deletes all Draft* models)
    draft.delete()

    return character


def _bind_house_claim(draft: CharacterDraft, sheet: CharacterSheet) -> None:
    """Materialize an approved CG house claim (#1884 Phase D).

    Pending or rejected claims materialize nothing — the character enters
    play houseless (the claim dies with the draft). Best-effort like the
    kinship bind: a refusal must not strand finalization.
    """
    from world.societies.houses.constants import HouseClaimStatus  # noqa: PLC0415
    from world.societies.houses.creator import materialize_house_claim  # noqa: PLC0415
    from world.societies.houses.models import HouseClaim  # noqa: PLC0415
    from world.societies.houses.services import HousesServiceError  # noqa: PLC0415

    claim = HouseClaim.objects.filter(draft=draft).first()
    if claim is None:
        return
    if claim.status != HouseClaimStatus.APPROVED:
        logger.warning(
            "Draft %s finalized with un-approved house claim %s (%s); skipping.",
            draft.pk,
            claim.pk,
            claim.status,
        )
        return
    try:
        materialize_house_claim(claim, sheet=sheet)
    except HousesServiceError:
        logger.exception(
            "House claim %s materialization failed for draft %s; continuing houseless.",
            claim.pk,
            draft.pk,
        )


def _grant_property_house_if_eligible(draft: CharacterDraft, persona: Persona) -> None:
    """Grant the selected Beginnings' PropertyGrantProfile, if one is configured.

    Generic hook — no specific beginning or grant profile is named here.
    Content (lore repo) wires Beginnings.property_grant_profile per path.
    """
    beginnings = draft.selected_beginnings
    profile = beginnings.property_grant_profile if beginnings is not None else None
    if profile is None:
        return
    from world.buildings.property_grant_services import grant_property_house  # noqa: PLC0415

    grant_property_house(persona, profile)


def _bind_kinship_node(draft: CharacterDraft, sheet: CharacterSheet) -> None:
    """Bind the new PC into the kinship graph (#2062).

    Priority: an explicitly claimed appable node → a mint from a claimed
    pool → a self-serve node in the draft's family (or familyless). CG
    deferral (``defer_parents``) simply records no parent edges — the
    deferred positions get created when defined later. Best-effort: a
    kinship refusal (e.g. a slot claimed moments earlier by someone else)
    must not strand finalization, so it logs and falls back to self-serve.
    """
    from world.roster.services.kinship import (  # noqa: PLC0415
        KinshipServiceError,
        claim_appable_node,
        ensure_node_for_sheet,
        mint_from_pool,
    )

    try:
        if draft.claimed_kin_slot is not None:
            claim_appable_node(node=draft.claimed_kin_slot, sheet=sheet)
            return
        if draft.claimed_kin_pool is not None:
            node = mint_from_pool(draft.claimed_kin_pool, created_by=draft.account)
            claim_appable_node(node=node, sheet=sheet)
            return
    except KinshipServiceError:
        logger.exception(
            "Kinship slot claim failed for draft %s; falling back to self-serve node.",
            draft.pk,
        )
    ensure_node_for_sheet(sheet, family=draft.family)


def _build_character_full_name(draft: CharacterDraft) -> str:
    """
    Build the character's full name from draft data.

    Uses the family name if a family is set, otherwise tries to derive a
    surname from the selected tarot card (for familyless characters).
    """
    first_name = draft.draft_data.get("first_name", "")
    family_name = ""
    if draft.family:
        family_name = draft.family.name
    else:
        # Try tarot surname for familyless characters (best-effort)
        tarot_card_name = draft.draft_data.get("tarot_card_name")
        if tarot_card_name:
            from world.tarot.models import TarotCard  # noqa: PLC0415

            try:
                tarot_card = TarotCard.objects.get(name=tarot_card_name)
                is_reversed = draft.draft_data.get("tarot_reversed", False)
                family_name = tarot_card.get_surname(is_reversed)
            except (TarotCard.DoesNotExist, KeyError, TypeError):
                logger.exception(
                    "Failed to resolve tarot surname for card_name=%s",
                    tarot_card_name,
                )

    if family_name:
        return f"{first_name} {family_name}"
    return first_name


def _grant_cg_residence_tenancy(
    draft: CharacterDraft,
    starting_room: ObjectDB,
    primary_persona: Persona,
) -> None:
    """Grant a residence tenancy at CG finalization when the area authors it (#2036).

    Design item 4: closes the "Academy auto-residence" story with zero manual player
    step. Guarded on ``StartingArea.grants_residence_tenancy`` (an authored per-area
    toggle — not every starting area need be residence-backed) and on the starting
    room actually resolving a ``RoomProfile`` (rooms may lack one during early
    testing, per ``StartingArea``'s own docstring — a graceful no-op, matching
    today's behavior for those rooms).

    ``grant_tenancy`` auto-defaults both Evennia ``home`` (redundant with the direct
    assignment the caller already made, but idempotent/harmless) and
    ``CharacterSheet.current_residence`` via ``maybe_default_residence`` — the one
    call that makes the daily residence-trickle gate reachable.
    """
    starting_area = draft.selected_area
    if starting_area is None or not starting_area.grants_residence_tenancy:
        return
    from evennia_extensions.models import RoomProfile  # noqa: PLC0415
    from world.locations.services import grant_tenancy  # noqa: PLC0415

    try:
        room_profile = starting_room.room_profile
    except RoomProfile.DoesNotExist:
        return
    grant_tenancy(
        room_profile=room_profile,
        tenant_persona=primary_persona,
        notes="Academy enrollment",
    )


def _grant_prelude_mission(draft: CharacterDraft, character: ObjectDB, persona: Persona) -> None:
    """Auto-grant the Beginning's prelude Mission at CG finalization (#2470).

    No-op when the draft has no Beginning, or the Beginning has no authored
    ``prelude_mission`` (e.g. content not written yet for that Beginning).

    Deliberately NOT best-effort, unlike the kinship/house-claim grants below:
    a misconfigured template (e.g. no entry node) is a content-authoring bug,
    not contention, and must fail finalization loudly rather than silently
    mint a character missing its designed, non-replayable first-hour content.
    """
    beginnings = draft.selected_beginnings
    if beginnings is None or beginnings.prelude_mission is None:
        return
    from world.missions.services.run import staff_assign_mission  # noqa: PLC0415

    staff_assign_mission(beginnings.prelude_mission, character, persona=persona)


def _grant_orientation_mission(
    _draft: CharacterDraft, character: ObjectDB, persona: Persona
) -> None:
    """Auto-grant the Academy orientation Mission at CG finalization (#2479).

    The orientation mission funnels the new Gifted toward the intake Ritual of
    the Durance. It is best-effort: if the MissionTemplate row has not been
    seeded yet, the character is created without it and can be granted later.
    """
    from world.missions.services.run import staff_assign_mission  # noqa: PLC0415
    from world.seeds.character_creation import ensure_orientation_mission  # noqa: PLC0415

    template = ensure_orientation_mission()
    if template is None:
        return
    staff_assign_mission(template, character, persona=persona)


def _finalize_origin_slots(sheet: CharacterSheet, origin_slots: dict[str, str]) -> str:
    """Upsert CharacterOriginSlot rows from draft_data and assemble prose (#2478).

    Called from ``_apply_sheet_demographics`` when the draft carries
    ``origin_slots``. Returns the assembled prose for ``Profile.background``.
    State refresh is deferred to the caller (after ``profile.save()``) so
    ``refresh_origin_story_state`` sees the final prose value.
    """
    for slot_id_str, value in origin_slots.items():
        try:
            slot = OriginTemplateSlot.objects.get(pk=int(slot_id_str))
        except (OriginTemplateSlot.DoesNotExist, ValueError, TypeError):
            logger.warning(
                "Origin slot id %s not found during finalize; skipping.",
                slot_id_str,
            )
            continue
        set_origin_slot(sheet, slot, value)
    return assemble_origin_prose(sheet)


def _set_demographics(sheet: CharacterSheet, draft: CharacterDraft) -> None:
    """Apply gender, pronouns, age, species, and family from the draft."""
    if draft.selected_gender:
        sheet.gender = draft.selected_gender
        # Auto-derive pronouns from gender
        _set_pronouns_from_gender(sheet, draft.selected_gender)
    if draft.age:
        sheet.age = draft.age
    if draft.selected_species:
        sheet.species = draft.selected_species
    if draft.family:
        sheet.family = draft.family


def _set_tarot_card(sheet: CharacterSheet, draft: CharacterDraft) -> None:
    """Best-effort set the tarot card and reversed flag from draft_data."""
    tarot_card_name = draft.draft_data.get("tarot_card_name")
    if not tarot_card_name:
        return
    from world.tarot.models import TarotCard  # noqa: PLC0415

    try:
        sheet.tarot_card = TarotCard.objects.get(name=tarot_card_name)
        sheet.tarot_reversed = draft.draft_data.get("tarot_reversed", False)
    except (TarotCard.DoesNotExist, KeyError, TypeError):
        logger.exception(
            "Failed to set tarot card on CharacterSheet for card_name=%s",
            tarot_card_name,
        )


def _set_heritage(sheet: CharacterSheet, draft: CharacterDraft) -> None:
    """Set heritage from Beginnings if available, otherwise default to Normal."""
    from world.character_sheets.models import Heritage  # noqa: PLC0415

    if draft.selected_beginnings and draft.selected_beginnings.heritage:
        sheet.heritage = draft.selected_beginnings.heritage
        return
    normal_heritage, _ = Heritage.objects.get_or_create(
        name="Normal",
        defaults={
            "description": "Standard upbringing with known family.",
            "is_special": False,
            "family_known": True,
        },
    )
    sheet.heritage = normal_heritage


def _set_origin_realm(sheet: CharacterSheet, draft: CharacterDraft) -> None:
    """Set origin realm from the selected starting area if present."""
    if draft.selected_area and draft.selected_area.realm:
        sheet.origin_realm = draft.selected_area.realm


def _ensure_profile(sheet: CharacterSheet) -> Profile:
    """Return the sheet's true_profile, creating one if missing."""
    profile = sheet.true_profile
    if profile is not None:
        return profile
    from world.character_sheets.models import Profile  # noqa: PLC0415

    profile = Profile.objects.create()
    sheet.true_profile = profile
    return profile


def _set_descriptive_text(sheet: CharacterSheet, draft_data: dict) -> str | None:
    """Apply descriptive/profile text fields from draft_data.

    additional_desc is appearance text (stays on the sheet); the narrative bio
    lives on true_profile now (#1270). Origin story: assemble prose from
    structured slots if present (#2478), otherwise fall back to legacy
    free-text background for backward compat. Returns the origin_slots dict
    if prose was assembled (so the caller can refresh state), else None.
    """
    if draft_data.get("description"):
        sheet.additional_desc = draft_data["description"]

    profile = _ensure_profile(sheet)
    origin_slots = draft_data.get("origin_slots")
    if origin_slots:
        profile.background = _finalize_origin_slots(sheet, origin_slots)
    elif draft_data.get("background"):
        profile.background = draft_data["background"]
    if draft_data.get("personality"):
        profile.personality = draft_data["personality"]
    if draft_data.get("concept"):
        profile.concept = draft_data["concept"]
    if draft_data.get("quote"):
        profile.quote = draft_data["quote"]
    profile.save()
    return origin_slots


def _set_physical_characteristics(sheet: CharacterSheet, draft: CharacterDraft) -> None:
    """Apply height and build (plus derived weight) from the draft."""
    if draft.height_inches:
        sheet.true_height_inches = draft.height_inches
    if draft.build:
        sheet.build = draft.build
        # Calculate weight if we have both height and build
        if draft.height_inches:
            sheet.weight_pounds = calculate_weight(draft.height_inches, draft.build)


def _apply_sheet_demographics(sheet: CharacterSheet, draft: CharacterDraft) -> None:
    """
    Populate demographic, heritage, descriptive, and physical fields on a CharacterSheet
    from a CharacterDraft and save it.

    Covers: gender/pronouns, age, species, family, tarot, heritage, origin realm,
    descriptive text (description/background/personality/concept/quote), and
    physical characteristics (height/build/weight).
    """
    _set_demographics(sheet, draft)
    _set_tarot_card(sheet, draft)
    _set_heritage(sheet, draft)
    _set_origin_realm(sheet, draft)

    origin_slots = _set_descriptive_text(sheet, draft.draft_data)
    # Refresh origin-story state now that the assembled prose is persisted (#2478).
    if origin_slots:
        refresh_origin_story_state(sheet)

    _set_physical_characteristics(sheet, draft)
    sheet.save()


def _apply_character_mechanics(character: ObjectDB, draft: CharacterDraft) -> None:
    """
    Create stat trait values, skills, goals, distinctions, path history, and post-CG
    bonuses for the character from draft data.

    Centralized so both player and GM finalize flows share the same mechanics setup.
    """
    from world.traits.models import CharacterTraitValue, Trait, TraitType  # noqa: PLC0415

    # Create stat values from draft (optimized with bulk operations)
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

    # Create the worship declaration (+ secret-worship Secret) (#2355)
    _create_worship_declaration(character, draft)

    # Create path history record
    if draft.selected_path:
        from world.progression.models import CharacterPathHistory  # noqa: PLC0415

        CharacterPathHistory.objects.create(
            character=character,
            path=draft.selected_path,
        )

    # Establish patronage for Path of the Chosen (#2550)
    if draft.selected_path and draft.selected_path.name == PATH_OF_THE_CHOSEN_NAME:
        from world.worship.models import PatronageValence, WorshipDeclaration  # noqa: PLC0415
        from world.worship.services import establish_patronage  # noqa: PLC0415

        declaration = WorshipDeclaration.objects.filter(
            character_sheet=character.sheet_data
        ).first()
        if declaration:
            being = declaration.secret_being or declaration.public_being
            if being:
                establish_patronage(
                    character.sheet_data, being, valence=PatronageValence.DEVOTIONAL
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
                trait_value.value += int(bonus)
                trait_value.save()


def _create_worship_declaration(character: ObjectDB, draft: CharacterDraft) -> None:
    """Create the WorshipDeclaration from the draft's picks; mint the Secret (#2355).

    Both picks are optional (an unaffiliated character has no declaration row).
    A secret pick equal to the public pick is stored public-only — there is
    nothing to hide.
    """
    if draft.public_worship_id is None and draft.secret_worship_id is None:
        return
    from world.worship.models import WorshipDeclaration  # noqa: PLC0415
    from world.worship.secrets import mint_worship_secret  # noqa: PLC0415

    secret_being = draft.secret_worship
    if secret_being is not None and secret_being.pk == draft.public_worship_id:
        secret_being = None
    declaration, _ = WorshipDeclaration.objects.get_or_create(
        character_sheet=character.sheet_data,
        defaults={"public_being": draft.public_worship, "secret_being": secret_being},
    )
    if declaration.secret_being is not None:
        mint_worship_secret(declaration)


def _convert_remaining_cg_points_to_xp(draft: CharacterDraft, character: ObjectDB) -> None:
    """
    Convert any unspent CG points on the draft to locked XP on the character.

    Best-effort: failures are logged but do not block finalization.
    """
    remaining_cg_points = draft.calculate_cg_points_remaining()
    if remaining_cg_points <= 0:
        return

    try:
        from world.character_creation.models import CGPointBudget  # noqa: PLC0415
        from world.progression.services import award_cg_conversion_xp  # noqa: PLC0415

        conversion_rate = CGPointBudget.get_active_conversion_rate()
        award_cg_conversion_xp(
            character,
            remaining_cg_points=remaining_cg_points,
            conversion_rate=conversion_rate,
        )
    except Exception:
        logger.exception(
            "Failed to convert %d CG points to XP for character %s",
            remaining_cg_points,
            character.key,
        )


def _set_pronouns_from_gender(sheet: CharacterSheet, gender: str) -> None:
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
        name=RosterType.AVAILABLE,
        defaults={
            "description": "Characters available for players to apply for",
            "is_active": True,
            "is_public": True,
            "allow_applications": True,
        },
    )
    return roster


def _get_or_create_active_roster() -> Roster:
    """Get or create the 'Active' roster for approved player characters."""
    roster, _ = Roster.objects.get_or_create(
        name=RosterType.ACTIVE,
        defaults={
            "description": "Currently active player characters",
            "is_active": True,
            "is_public": True,
            "allow_applications": False,
        },
    )
    return roster


def _get_or_create_pending_roster() -> Roster:
    """Get or create the 'Pending' roster for characters awaiting approval."""
    roster, _ = Roster.objects.get_or_create(
        name=PENDING_ROSTER_NAME,
        defaults={
            "description": "Characters awaiting staff approval",
            "is_active": False,
            "is_public": False,
            "allow_applications": False,
        },
    )
    return roster


def _build_and_create_goals(character: ObjectDB, draft: CharacterDraft) -> list:
    """
    Build CharacterGoal instances from draft_data and create them.

    Serializer validated the domain PKs; this builds instances and bulk creates.
    """
    from world.goals.constants import GoalStatus  # noqa: PLC0415
    from world.goals.models import CharacterGoal  # noqa: PLC0415
    from world.mechanics.models import ModifierTarget  # noqa: PLC0415

    goals_data = draft.draft_data.get("goals", [])
    if not goals_data:
        return []

    # Fetch all needed domains in one query
    domain_ids = [g.get("domain_id") for g in goals_data if g.get("domain_id")]
    domains_by_id = {d.id: d for d in ModifierTarget.objects.filter(id__in=domain_ids)}

    # Build and create instances
    goals_to_create = [
        CharacterGoal(
            character=character.sheet_data,
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


def _create_distinctions(character: ObjectDB, draft: CharacterDraft) -> None:
    """
    Create CharacterDistinction records and their modifiers from draft data.

    Uses bulk operations to avoid per-distinction queries. The chain is:
    1. Bulk-create CharacterDistinction records
    2. Bulk-create ModifierSource + CharacterModifier records for all non-resonance-category
       effects, then reconcile each distinction's resonance grants (standing/currency axis —
       ``reconcile_distinction_resonance_grants``, the ``DistinctionResonanceGrant`` sidecar;
       see ``_create_distinction_modifiers_bulk``, #1834)
    3. Mint a Secret for any ``secret_by_default`` distinction
    """
    from world.distinctions.models import CharacterDistinction, Distinction  # noqa: PLC0415
    from world.distinctions.types import DistinctionOrigin  # noqa: PLC0415

    distinctions_data = draft.draft_data.get("distinctions", [])
    if not distinctions_data:
        return

    # Dict keyed by distinction_id deduplicates entries (CharacterDistinction
    # has unique_together on character+distinction, so duplicates would fail)
    entries_by_id = {d["distinction_id"]: d for d in distinctions_data if d.get("distinction_id")}

    from world.distinctions.models import DistinctionEffect  # noqa: PLC0415

    # Fetch all distinctions with effects prefetched in one query
    distinctions = Distinction.objects.filter(id__in=entries_by_id.keys()).prefetch_related(
        Prefetch(
            "effects",
            queryset=DistinctionEffect.objects.select_related("target__category"),
            to_attr="cached_effects",
        ),
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
                character=character.sheet_data,
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

    # #1334 — a ``secret_by_default`` kind (criminal / scandalous) relocates into a Secret on
    # grant, so it never shows on the public distinctions list. One-time finalize over a handful
    # of distinctions, so the per-mint query is fine; reuses the single minting authority.
    from world.distinctions.services import mint_distinction_secret  # noqa: PLC0415

    for cd in created_distinctions:
        if cd.distinction.secret_by_default:
            mint_distinction_secret(cd)


def _create_distinction_modifiers_bulk(sheet: CharacterSheet, char_distinctions: list) -> None:
    """
    Bulk-create ModifierSource and CharacterModifier records for a list of CharacterDistinctions,
    then reconcile each distinction's resonance grants.

    Expects the distinction FK on each CharacterDistinction to have effects prefetched.

    Resonance-CATEGORY effects are skipped here — distinction resonance flows through
    ``reconcile_distinction_resonance_grants`` (the ``DistinctionResonanceGrant`` sidecar),
    not a resonance-targeted ``CharacterModifier`` row (#1834). Every other effect still
    materializes a modifier as before. Reconcile runs for every CharacterDistinction
    regardless of whether it has any effects at all — a distinction can carry a
    ``DistinctionResonanceGrant`` with no ``DistinctionEffect`` rows.
    """
    from world.assets.services import (  # noqa: PLC0415
        reconcile_distinction_asset_grants,
    )
    from world.magic.services.distinction_resonance import (  # noqa: PLC0415
        reconcile_distinction_resonance_grants,
    )
    from world.mechanics.constants import RESONANCE_CATEGORY_NAME  # noqa: PLC0415
    from world.mechanics.models import CharacterModifier, ModifierSource  # noqa: PLC0415
    from world.npc_services.regard import reconcile_distinction_regard_seeds  # noqa: PLC0415

    # Build ModifierSource instances for all effects across all distinctions
    sources = []
    source_effect_ranks = []  # parallel list: (effect, rank) per source
    for char_dist in char_distinctions:
        for effect in char_dist.distinction.cached_effects:  # prefetched via to_attr
            if effect.target.category.name == RESONANCE_CATEGORY_NAME:
                continue
            sources.append(
                ModifierSource(
                    distinction_effect=effect,
                    character_distinction=char_dist,
                )
            )
            source_effect_ranks.append((effect, char_dist.rank))

    if sources:
        created_sources = ModifierSource.objects.bulk_create(sources)

        modifiers = [
            CharacterModifier(
                character=sheet,
                target=effect.target,
                value=effect.get_value_at_rank(rank),
                source=source,
            )
            for source, (effect, rank) in zip(created_sources, source_effect_ranks, strict=True)
        ]

        CharacterModifier.objects.bulk_create(modifiers)

    for char_dist in char_distinctions:
        reconcile_distinction_resonance_grants(char_dist)
        reconcile_distinction_asset_grants(char_dist)
        reconcile_distinction_regard_seeds(char_dist)


def _create_true_form(character: ObjectDB, draft_data: dict) -> None:
    """
    Create a true form for the character from draft form_traits data.

    Args:
        character: The newly created Character object
        draft_data: The draft's JSON data blob
    """
    from world.forms.models import FormTrait, FormTraitOption  # noqa: PLC0415
    from world.forms.services import create_true_form  # noqa: PLC0415

    form_traits = draft_data.get("form_traits", {})
    if not form_traits:
        return

    # Resolve trait names to FormTrait instances
    trait_names = list(form_traits.keys())
    traits_by_name = {t.name: t for t in FormTrait.objects.filter(name__in=trait_names)}

    # Resolve option IDs to FormTraitOption instances
    option_ids = [v for v in form_traits.values() if isinstance(v, int)]
    options_by_id = {o.id: o for o in FormTraitOption.objects.filter(id__in=option_ids)}

    # Build selections dict, skipping invalid entries
    selections = {}
    for trait_name, option_id in form_traits.items():
        trait = traits_by_name.get(trait_name)
        option = options_by_id.get(option_id)
        if trait and option and option.trait_id == trait.id:
            selections[trait] = option

    if selections:
        create_true_form(character, selections)

    # #2632 — CG-authored per-trait descriptors ("red" + "flowing crimson"):
    # free-text presentation flavor written onto the PRIMARY persona. Only
    # traits actually selected get a descriptor; player-authored here, so the
    # descriptor-never-auto-attach privacy invariant (#1109) is untouched —
    # nothing is copied, the player typed it for this face.
    descriptors = draft_data.get("form_trait_descriptors", {})
    if selections and isinstance(descriptors, dict):
        from world.forms.models import PersonaTraitDescriptor  # noqa: PLC0415

        sheet = character.character_sheet
        persona = sheet.primary_persona if sheet else None
        if persona is not None:
            for trait in selections:
                text = descriptors.get(trait.name)
                if isinstance(text, str) and text.strip():
                    PersonaTraitDescriptor.objects.update_or_create(
                        persona=persona,
                        trait=trait,
                        defaults={"text": text.strip()},
                    )


def _create_skill_values(character: ObjectDB, draft: CharacterDraft) -> None:
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


def get_accessible_starting_areas(account: AbstractBaseUser | AnonymousUser) -> QuerySet:
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


def can_create_character(account: AbstractBaseUser | AnonymousUser) -> tuple[bool, str]:
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
    # TODO: Implement trust system - default to 0 (trusted) until then
    trust: int = account.trust if hasattr(account, "trust") else 0  # type: ignore[assignment]
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


def _finalize_gift_and_techniques(draft: CharacterDraft, sheet: CharacterSheet) -> None:
    """Step 1: link the CG-chosen catalog Gift + Techniques to the character.

    Replaces the old CG-creates-a-new-technique path (#2426): the Gift and
    Techniques are staff-authored catalog rows the player picked via the CG
    option endpoints (``get_gift_options``/``get_technique_options``) —
    finalize only links them, it never mints new ``Gift``/``Technique`` rows.
    Outcome-flavor consequence-pool selection is dropped entirely (spec
    correction on #2426): every catalog technique already carries its own
    authored ``action_template``.

    No-op when the draft has no selected gift (legacy/test-only draft_data —
    ``compute_magic_errors`` requires ``selected_gift_id`` on any draft that
    reaches submission).
    """
    gift_id = draft.draft_data.get("selected_gift_id")
    if not gift_id:
        return

    from world.magic.models import (  # noqa: PLC0415
        CharacterTechnique,
        Gift,
        Resonance,
        Technique,
    )
    from world.magic.specialization.services import grant_gift_to_character  # noqa: PLC0415

    gift = Gift.objects.get(pk=gift_id)

    # Provision the CharacterGift link + the latent level-0 GIFT thread at the
    # player's CG-chosen resonance (#1578, ADR-0055). Acquiring a gift IS
    # weaving a (latent) thread.
    resonance_id = draft.draft_data.get("selected_gift_resonance_id")
    resonance = Resonance.objects.filter(pk=resonance_id).first() if resonance_id else None
    grant_gift_to_character(sheet, gift, resonance=resonance)

    technique_ids = draft.draft_data.get("selected_technique_ids") or []
    techniques = list(Technique.objects.filter(pk__in=technique_ids))
    for technique in techniques:
        CharacterTechnique.objects.get_or_create(character=sheet, technique=technique)

    from world.achievements.constants import AccessChangeSource  # noqa: PLC0415
    from world.achievements.discovery import announce_access_change  # noqa: PLC0415

    announce_access_change(
        sheet, gained=techniques, lost=[], source=AccessChangeSource.CHARACTER_CREATION
    )


def _finalize_tradition_codex_grants(draft: CharacterDraft, sheet: CharacterSheet) -> None:
    """Step 3: apply tradition codex grants. No-op without a selected tradition."""
    if not draft.selected_tradition:
        return

    from world.codex.constants import CodexKnowledgeStatus  # noqa: PLC0415
    from world.codex.models import (  # noqa: PLC0415
        CharacterCodexKnowledge,
        TraditionCodexGrant,
    )

    grant_entry_ids = list(
        TraditionCodexGrant.objects.filter(tradition=draft.selected_tradition).values_list(
            "entry_id", flat=True
        )
    )
    if not grant_entry_ids:
        return

    roster_entry = sheet.roster_entry
    for entry_id in grant_entry_ids:
        CharacterCodexKnowledge.objects.get_or_create(
            roster_entry=roster_entry,
            entry_id=entry_id,
            defaults={"status": CodexKnowledgeStatus.KNOWN},
        )


def _finalize_path_codex_grants(draft: CharacterDraft, sheet: CharacterSheet) -> None:
    """Apply Path codex grants. No-op without a selected path.

    Mirrors _finalize_tradition_codex_grants: the chosen Path teaches the
    character which magic milestones exist (drives the dashboard discovery
    tiers). Idempotent via get_or_create.
    """
    if not draft.selected_path:
        return

    from world.codex.constants import CodexKnowledgeStatus  # noqa: PLC0415
    from world.codex.models import CharacterCodexKnowledge, PathCodexGrant  # noqa: PLC0415

    grant_entry_ids = list(
        PathCodexGrant.objects.filter(path=draft.selected_path).values_list("entry_id", flat=True)
    )
    if not grant_entry_ids:
        return

    roster_entry = sheet.roster_entry
    for entry_id in grant_entry_ids:
        CharacterCodexKnowledge.objects.get_or_create(
            roster_entry=roster_entry,
            entry_id=entry_id,
            defaults={"status": CodexKnowledgeStatus.KNOWN},
        )


def _finalize_beginnings_codex_grants(draft: CharacterDraft, sheet: CharacterSheet) -> None:
    """Apply Beginnings codex grants. No-op without a selected beginnings.

    Mirrors _finalize_tradition_codex_grants: the chosen Beginnings teaches the
    character lore about their origin. Idempotent via get_or_create.
    """
    if not draft.selected_beginnings:
        return

    from world.codex.constants import CodexKnowledgeStatus  # noqa: PLC0415
    from world.codex.models import (  # noqa: PLC0415
        BeginningsCodexGrant,
        CharacterCodexKnowledge,
    )

    grant_entry_ids = list(
        BeginningsCodexGrant.objects.filter(beginnings=draft.selected_beginnings).values_list(
            "entry_id", flat=True
        )
    )
    if not grant_entry_ids:
        return

    roster_entry = sheet.roster_entry
    for entry_id in grant_entry_ids:
        CharacterCodexKnowledge.objects.get_or_create(
            roster_entry=roster_entry,
            entry_id=entry_id,
            defaults={"status": CodexKnowledgeStatus.KNOWN},
        )


def _finalize_distinction_codex_grants(draft: CharacterDraft, sheet: CharacterSheet) -> None:
    """Apply Distinction codex grants for all selected distinctions.

    Mirrors _finalize_tradition_codex_grants. Idempotent via get_or_create.
    """
    distinctions_data = draft.draft_data.get("distinctions", [])
    if not distinctions_data:
        return

    from world.codex.constants import CodexKnowledgeStatus  # noqa: PLC0415
    from world.codex.models import (  # noqa: PLC0415
        CharacterCodexKnowledge,
        DistinctionCodexGrant,
    )

    distinction_ids = {
        d["distinction_id"]  # noqa: STRING_LITERAL
        for d in distinctions_data
        if "distinction_id" in d  # noqa: STRING_LITERAL
    }
    if not distinction_ids:
        return

    grant_entry_ids = list(
        DistinctionCodexGrant.objects.filter(distinction_id__in=distinction_ids).values_list(
            "entry_id", flat=True
        )
    )
    if not grant_entry_ids:
        return

    roster_entry = sheet.roster_entry
    for entry_id in grant_entry_ids:
        CharacterCodexKnowledge.objects.get_or_create(
            roster_entry=roster_entry,
            entry_id=entry_id,
            defaults={"status": CodexKnowledgeStatus.KNOWN},
        )


def _finalize_species_codex(sheet: CharacterSheet) -> None:
    """Grant the species's codex entry, if any. Idempotent via get_or_create."""
    try:
        species = sheet.species
    except AttributeError:
        return
    if species is None or species.codex_entry_id is None:
        return

    from world.codex.constants import CodexKnowledgeStatus  # noqa: PLC0415
    from world.codex.models import CharacterCodexKnowledge  # noqa: PLC0415

    CharacterCodexKnowledge.objects.get_or_create(
        roster_entry=sheet.roster_entry,
        entry_id=species.codex_entry_id,
        defaults={"status": CodexKnowledgeStatus.KNOWN},
    )


def _finalize_resonance_codex(draft: CharacterDraft, sheet: CharacterSheet) -> None:
    """Grant the selected gift resonance's codex entry, if any.

    The resonance is stored in draft_data['selected_gift_resonance_id'].
    Idempotent via get_or_create.
    """
    resonance_id = draft.draft_data.get("selected_gift_resonance_id")
    if not resonance_id:
        return

    from world.codex.constants import CodexKnowledgeStatus  # noqa: PLC0415
    from world.codex.models import CharacterCodexKnowledge  # noqa: PLC0415
    from world.magic.models import Resonance  # noqa: PLC0415

    try:
        resonance = Resonance.objects.get(pk=resonance_id)
    except Resonance.DoesNotExist:
        return
    if resonance.codex_entry_id is None:
        return

    CharacterCodexKnowledge.objects.get_or_create(
        roster_entry=sheet.roster_entry,
        entry_id=resonance.codex_entry_id,
        defaults={"status": CodexKnowledgeStatus.KNOWN},
    )


def _finalize_anima_ritual(draft: CharacterDraft, sheet: CharacterSheet) -> None:
    """Step 5: create player anima Ritual + sidecar + CharacterRitualKnowledge.

    The Ritual is authored by the player's account. Its stat + skill are the
    player's explicit CG Anima Check pick (``anima_check_stat_id`` /
    ``anima_check_skill_id`` — required by ``compute_magic_errors``, #2426);
    when a draft has neither set (legacy/test-only draft_data),
    ``provision_player_anima_ritual`` falls back to its Willpower +
    highest-CG-skill defaults. Both are customisable post-CG.
    CharacterRitualKnowledge is created so the ritual gate in the scene action
    menu is satisfied.
    Guard: if the sheet has no RosterEntry yet (e.g. in isolated unit tests that
    call finalize_magic_data directly), skip — the CharacterRitualKnowledge cannot
    be created without a roster_entry FK. finalize_character always creates the
    RosterEntry before calling this, so this guard only fires in test-only paths.
    """
    from world.roster.models import RosterEntry  # noqa: PLC0415

    try:
        roster_entry = sheet.roster_entry
    except RosterEntry.DoesNotExist:
        return

    from world.magic.services.anima import provision_player_anima_ritual  # noqa: PLC0415

    character_name = draft.draft_data.get("first_name", "Character")
    ritual_name = draft.draft_data.get("anima_ritual_name") or f"{character_name}'s Anima Ritual"

    stat = None
    stat_id = draft.draft_data.get("anima_check_stat_id")
    if stat_id:
        from world.traits.models import Trait  # noqa: PLC0415

        stat = Trait.objects.filter(pk=stat_id).first()

    skill = None
    skill_id = draft.draft_data.get("anima_check_skill_id")
    if skill_id:
        from world.skills.models import Skill  # noqa: PLC0415

        skill = Skill.objects.filter(pk=skill_id).first()

    provision_player_anima_ritual(
        account=draft.account,
        character_sheet=sheet,
        roster_entry=roster_entry,
        ritual_name=ritual_name,
        stat=stat,
        skill=skill,
    )


@transaction.atomic
def finalize_magic_data(draft: CharacterDraft, sheet: CharacterSheet) -> None:
    """Create magic models from the CG-chosen catalog Gift/Techniques during finalization.

    Called during finalize_character() after CharacterSheet is created.
    Links CharacterGift + CharacterTechnique to the CG-chosen catalog Gift and
    Techniques, creates CharacterTradition, applies tradition codex grants, and
    creates CharacterAura — then recomputes it once so any resonance already
    seeded earlier in finalize (e.g. distinction resonance grants, #1834) is
    reflected in the starting aura.
    """
    from world.fatigue.services import get_or_create_fatigue_pool  # noqa: PLC0415
    from world.magic.models import (  # noqa: PLC0415
        CharacterAnima,
        CharacterAura,
        CharacterTradition,
    )

    # 1. Link the CG-chosen catalog Gift + Techniques
    _finalize_gift_and_techniques(draft, sheet)

    # 1b. Provision species Minor Gift(s) + latent GIFT thread + any drawback (#1580).
    #     Re-uses the player's CG-chosen resonance (same key as the Major-gift block)
    #     so the species gift thread anchors to the same resonance the player picked.
    #     Falls back to each gift's first supported resonance when unset.
    from world.species.services import provision_species_gifts  # noqa: PLC0415

    _cg_resonance = None
    _cg_resonance_id = draft.draft_data.get("selected_gift_resonance_id")
    if _cg_resonance_id:
        from world.magic.models import Resonance  # noqa: PLC0415

        _cg_resonance = Resonance.objects.filter(pk=_cg_resonance_id).first()
    provision_species_gifts(sheet, resonance=_cg_resonance)

    # 2. Create CharacterTradition — unconditional: compute_magic_errors requires
    #    selected_tradition on any draft that reaches submission (#2426).
    CharacterTradition.objects.create(
        character=sheet,
        tradition=draft.selected_tradition,
    )

    # 2b. Golden Hare CG entrance obligation (#2428) — Unbound Prospects start
    #     owing Shroudwatch Academy a Hare; sponsored Prospects start
    #     SETTLED_BY_SPONSOR (the sponsor spent a Hare on their behalf).
    _finalize_academy_entrance_obligation(draft, sheet)

    # 3. Apply tradition codex grants
    _finalize_tradition_codex_grants(draft, sheet)

    # 3b. Apply path codex grants (teaches which magic milestones exist)
    _finalize_path_codex_grants(draft, sheet)

    # 3c. Apply beginnings/distinction/species codex grants
    _finalize_beginnings_codex_grants(draft, sheet)
    _finalize_distinction_codex_grants(draft, sheet)
    _finalize_species_codex(sheet)

    # 4. Create CharacterAura, then persist the guided Glimpse picks (#2427)
    #    through the glimpse services so glimpse_state stays consistent.
    from world.magic.services.glimpse import (  # noqa: PLC0415
        link_distinction_to_glimpse,
        set_glimpse_prose,
        set_glimpse_tags,
    )

    aura = CharacterAura(character=sheet.character)
    aura.full_clean()
    aura.save()

    tag_ids = draft.draft_data.get("glimpse_tag_ids", [])
    if tag_ids:
        from world.magic.constants import GlimpseTagAxis  # noqa: PLC0415
        from world.magic.models import GlimpseTag  # noqa: PLC0415

        tags = list(GlimpseTag.objects.filter(pk__in=tag_ids, is_active=True))
        for axis in GlimpseTagAxis:
            axis_tags = [tag for tag in tags if tag.axis == axis]
            if axis_tags:
                set_glimpse_tags(aura, axis_tags, axis=axis)

    set_glimpse_prose(aura, draft.draft_data.get("glimpse_story", ""))

    linked_ids = draft.draft_data.get("glimpse_linked_distinction_ids", [])
    if linked_ids:
        from world.distinctions.models import CharacterDistinction  # noqa: PLC0415

        linked = CharacterDistinction.objects.filter(character=sheet, distinction_id__in=linked_ids)
        for character_distinction in linked:
            link_distinction_to_glimpse(character_distinction, aura)

    # 4b. Recompute aura now that CharacterAura exists. _apply_character_mechanics
    # (distinctions, via reconcile_distinction_resonance_grants) runs earlier in
    # finalize_character, before this row existed, so any resonance it seeded couldn't
    # write through recompute_aura's no-CharacterAura no-op (#1834). This call catches
    # the starting aura up to whatever resonance CG has granted so far.
    from world.magic.services.aura import recompute_aura  # noqa: PLC0415

    recompute_aura(sheet)

    # 5. Seed CharacterAnima + FatiguePool (idempotent — skip if already present).
    #    These must exist for Soul Tether sineating/rescue deductions to apply.
    CharacterAnima.objects.get_or_create(
        character=sheet.character,
        defaults={"current": 10, "maximum": 10},
    )
    get_or_create_fatigue_pool(sheet)

    # 6. Create player anima Ritual + sidecar + CharacterRitualKnowledge.
    _finalize_anima_ritual(draft, sheet)

    # 7. Grant the selected gift resonance's codex entry.
    _finalize_resonance_codex(draft, sheet)


def _finalize_academy_entrance_obligation(draft: CharacterDraft, sheet: CharacterSheet) -> None:
    """Create the CG-finalize Golden Hare Academy obligation row (#2428).

    Unbound Prospects (no Tradition sponsor) start CG owing Shroudwatch
    Academy one Golden Hare (``OWED``); every other tradition is sponsored —
    the sponsor literally spent a Hare on the Prospect's behalf at CG time,
    so that row starts ``SETTLED_BY_SPONSOR`` with ``settled_at`` stamped and
    ``settled_by_token`` left ``NULL`` (lore-recorded, not a minted item at CG
    time — spec ruling on #2428).

    The Academy is resolved by name (``SHROUDWATCH_ACADEMY_NAME``) rather than
    a FK on the draft/sheet — a defensive, logged skip when it isn't seeded
    mirrors ``seed_beginning_traditions``'s Unbound-tradition skip (#2444);
    cluster ordering guarantees this can't happen via the Big Button.

    Idempotent via ``get_or_create`` keyed on (debtor, creditor, origin) so
    re-finalize test paths don't create a duplicate obligation row.
    """
    from world.character_creation.constants import (  # noqa: PLC0415
        SHROUDWATCH_ACADEMY_NAME,
        UNBOUND_TRADITION_NAME,
    )
    from world.societies.constants import ObligationOrigin, ObligationState  # noqa: PLC0415
    from world.societies.models import Organization, OrganizationObligation  # noqa: PLC0415

    academy = Organization.objects.filter(name=SHROUDWATCH_ACADEMY_NAME).first()
    if academy is None:
        logger.warning(
            "Skipping Academy entrance obligation: %r org is not seeded.",
            SHROUDWATCH_ACADEMY_NAME,
        )
        return

    tradition = draft.selected_tradition
    is_unbound = tradition is not None and tradition.name == UNBOUND_TRADITION_NAME
    if is_unbound:
        defaults = {"state": ObligationState.OWED}
    else:
        defaults = {"state": ObligationState.SETTLED_BY_SPONSOR, "settled_at": timezone.now()}

    OrganizationObligation.objects.get_or_create(
        debtor=sheet,
        creditor=academy,
        origin=ObligationOrigin.ACADEMY_ENTRANCE,
        defaults=defaults,
    )


def _grant_beginnings_ritual_knowledge(draft: CharacterDraft, roster_entry: RosterEntry) -> None:
    """Grant CharacterRitualKnowledge for BeginningsRitualGrant rows.

    Beginnings is not stored on CharacterSheet post-finalization, so
    reconcile_ritual_knowledge() cannot walk it. This function handles the
    Beginnings grant source directly at finalization time (Option A from Phase 8
    design notes), before the general reconciliation pass.

    Idempotent via get_or_create — safe to call multiple times.
    """
    beginnings = draft.selected_beginnings
    if beginnings is None:
        return

    from world.magic.models import CharacterRitualKnowledge  # noqa: PLC0415
    from world.magic.models.grants import BeginningsRitualGrant  # noqa: PLC0415

    ritual_ids = list(
        BeginningsRitualGrant.objects.filter(beginnings=beginnings).values_list(
            "ritual_id", flat=True
        )
    )
    for ritual_id in ritual_ids:
        CharacterRitualKnowledge.objects.get_or_create(
            roster_entry=roster_entry,
            ritual_id=ritual_id,
            defaults={"learned_from": None},
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
        player_account=draft.account,
        status=ApplicationStatus.SUBMITTED,
        submission_notes=submission_notes,
    )
    DraftApplicationComment.objects.create(
        application=application,
        author=None,
        text="Application submitted for review.",
        comment_type=CommentType.STATUS_CHANGE,
    )

    # Attach invite context if the submitting account arrived via an invite (#2483)
    try:
        from world.roster.services.invite_notifications import (  # noqa: PLC0415
            notify_inviter_of_submission,
        )
        from world.roster.services.invite_services import annotate_application  # noqa: PLC0415

        invite = annotate_application(application, application.player_account)
        if invite is not None:
            notify_inviter_of_submission(invite, application)
    except Exception:
        logger.exception(
            "Failed to annotate/notify invite for application %s",
            application.pk,
        )

    from world.character_creation.email_service import CGEmailService  # noqa: PLC0415

    try:
        CGEmailService.handle_submission(application)
    except Exception:
        logger.exception("Failed to send CG submission emails for application %s", application.pk)

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


def claim_application(
    application: DraftApplication, *, reviewer: AbstractBaseUser | AnonymousUser
) -> None:
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
    application: DraftApplication, *, reviewer: AbstractBaseUser | AnonymousUser, comment: str = ""
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

    # Preserve audit data before finalize_character deletes the draft
    draft = application.draft
    application.player_account = draft.account
    application.character_name = draft.draft_data.get("first_name", "")
    application.save(
        update_fields=["status", "reviewer", "reviewed_at", "player_account", "character_name"]
    )
    DraftApplicationComment.objects.create(
        application=application,
        author=None,
        text=f"Application approved by {reviewer.username}.",
        comment_type=CommentType.STATUS_CHANGE,
    )

    player_account = draft.account
    character = finalize_character(draft, add_to_roster=False)

    # Move character from Pending → Active roster
    active_roster = _get_or_create_active_roster()
    roster_entry = character.sheet_data.roster_entry
    roster_entry.move_to_roster(active_roster)

    # Create RosterTenure linking player to character
    player_data, _ = PlayerData.objects.get_or_create(account=player_account)
    reviewer_data, _ = PlayerData.objects.get_or_create(account=reviewer)

    player_number = roster_entry.tenures.count() + 1
    RosterTenure.objects.create(
        player_data=player_data,
        roster_entry=roster_entry,
        player_number=player_number,
        start_date=timezone.now(),
        approved_date=timezone.now(),
        approved_by=reviewer_data,
    )

    from world.character_creation.email_service import CGEmailService  # noqa: PLC0415

    try:
        CGEmailService.send_application_approved(application)
    except Exception:
        logger.exception("Failed to send CG approval email for application %s", application.pk)


def request_revisions(
    application: DraftApplication, *, reviewer: AbstractBaseUser | AnonymousUser, comment: str
) -> None:
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

    from world.character_creation.email_service import CGEmailService  # noqa: PLC0415

    try:
        CGEmailService.send_revisions_requested(application)
    except Exception:
        logger.exception(
            "Failed to send CG revisions-requested email for application %s", application.pk
        )


def deny_application(
    application: DraftApplication, *, reviewer: AbstractBaseUser | AnonymousUser, comment: str
) -> None:
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

    from world.character_creation.email_service import CGEmailService  # noqa: PLC0415

    try:
        CGEmailService.send_application_denied(application)
    except Exception:
        logger.exception("Failed to send CG denial email for application %s", application.pk)


def add_application_comment(
    application: DraftApplication, *, author: AbstractBaseUser | AnonymousUser, text: str
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


@transaction.atomic
def finalize_gm_character(draft: CharacterDraft) -> tuple[RosterEntry, Story]:
    """Finalize a GM-initiated draft into a roster character + story.

    Creates Character + CharacterSheet + PRIMARY Persona, a RosterEntry on
    the Available roster (no tenure), a Story linked to the GM's target
    table, and a StoryParticipation linking the character to the story.

    Args:
        draft: CharacterDraft with is_gm_creation=True, target_table set,
            story_title set.

    Returns:
        (roster_entry, story)

    Raises:
        ValidationError: if draft is not a GM draft, or missing target_table,
            or missing story_title.
    """
    from world.stories.constants import StoryScope  # noqa: PLC0415
    from world.stories.models import Story, StoryParticipation  # noqa: PLC0415
    from world.stories.services.progress import create_character_progress  # noqa: PLC0415

    if not draft.is_gm_creation:
        msg = "Draft is not a GM creation draft."
        raise ValidationError(msg)
    if draft.target_table is None:
        msg = "GM drafts require a target_table at finalize."
        raise ValidationError(msg)
    if draft.target_table.gm.account_id != draft.account_id:
        msg = "You do not own the target table."
        raise ValidationError(msg)
    if not draft.story_title:
        msg = "GM drafts require a story_title at finalize."
        raise ValidationError(msg)

    # Build name — reuse helper (handles tarot surname for orphans, plain
    # first_name otherwise).
    full_name = _build_character_full_name(draft)

    # Create Character + Sheet + Primary Persona atomically.
    character, sheet, _primary = create_character_with_sheet(
        character_key=full_name,
        primary_persona_name=full_name,
    )

    # Populate sheet demographics and mechanics (shared helpers).
    _apply_sheet_demographics(sheet, draft)
    _apply_character_mechanics(character, draft)

    # Finalize magic data (same as player finalize flow — GM-created
    # characters may have gift/technique/tradition/aura selections in the draft).
    finalize_magic_data(draft, sheet)

    # NOTE: home and location are intentionally unset. A GM-created character
    # sits on the Available roster with no location. Once a player claims the
    # character (via RosterApplication → tenure), downstream code sets the
    # starting location at activation time.
    # Create RosterEntry on Available roster (no tenure). Stamp GM_TABLE provenance
    # (#1506): the player-GM authored this for their table, recorded as a viewable
    # quality/trust signal alongside the GM's account and the table itself.
    entry = RosterEntry.objects.create(
        character_sheet=sheet,
        roster=_get_or_create_available_roster(),
        creation_provenance=CreationProvenance.GM_TABLE,
        created_by_account=draft.account,
        created_for_table=draft.target_table,
    )

    # Create the Story tied to the GM's target table.
    story = Story.objects.create(
        title=draft.story_title,
        description=draft.story_description,
        primary_table=draft.target_table,
        scope=StoryScope.CHARACTER,
        character_sheet=sheet,
    )
    story.owners.add(draft.account)
    story.invalidate_owner_cache()

    # Link character to the story.
    StoryParticipation.objects.create(
        story=story,
        character=character,
        is_active=True,
    )

    # Create a progress pointer so the Phase 2 dashboard has something to show.
    # current_episode starts null (pre-story / frontier); GM sets the first episode later.
    # Uses create_character_progress to evaluate auto-beats at snapshot time —
    # catches retroactive matches if the character already satisfies a beat.
    create_character_progress(
        story=story,
        character_sheet=sheet,
        current_episode=None,
    )

    # Convert unspent CG points → XP (best-effort) and delete draft.
    _convert_remaining_cg_points_to_xp(draft, character)
    draft.delete()

    return entry, story


# =============================================================================
# Origin-story guided-flow write services (#2478)
#
# Single write path for a character's origin story: slot answers and prose
# assembly. Every mutation recomputes ``CharacterSheet.origin_story_state`` so
# the cached state never drifts from the slot rows (the field is a cache of
# truth, mirroring the ``glimpse_state`` precedent, #2427).
# =============================================================================


def refresh_origin_story_state(sheet: CharacterSheet) -> OriginStoryState:
    """Recompute and persist ``origin_story_state`` from slot rows + prose.

    Mirrors ``refresh_glimpse_state`` (``glimpse.py:28-39``).
    """
    has_slots = sheet.origin_slots.exists()
    has_prose = bool(sheet.background and sheet.background.strip())
    if has_prose and has_slots:
        state = OriginStoryState.COMPLETE
    elif has_slots:
        state = OriginStoryState.SLOTS_ONLY
    else:
        state = OriginStoryState.NOT_STARTED
    if sheet.origin_story_state != state:
        sheet.origin_story_state = state
        sheet.save(update_fields=["origin_story_state"])
    return state


@transaction.atomic
def set_origin_slot(sheet: CharacterSheet, slot: OriginTemplateSlot, value: str) -> None:
    """Upsert a character's slot answer, then refresh state.

    Mirrors ``set_glimpse_tags`` (``glimpse.py:42-62``).
    """
    CharacterOriginSlot.objects.update_or_create(sheet=sheet, slot=slot, defaults={"value": value})
    refresh_origin_story_state(sheet)


def clear_origin_slot(sheet: CharacterSheet, slot: OriginTemplateSlot) -> None:
    """Delete a slot answer and recompute state."""
    CharacterOriginSlot.objects.filter(sheet=sheet, slot=slot).delete()
    refresh_origin_story_state(sheet)


def assemble_origin_prose(sheet: CharacterSheet) -> str:
    """Compose the frame narrative + slot answers into prose.

    Pure template concatenation — no LLM. Called at finalize and on
    sheet-editor save. Returns empty string when the sheet has no slots
    filled.
    """
    slots = list(sheet.origin_slots.select_related("slot__template").order_by("slot__sort_order"))
    if not slots:
        return ""

    template: OriginTemplate | None = slots[0].slot.template
    if template is None:
        return ""

    lines = [template.frame_narrative, ""]
    for row in slots:
        lines.append(row.slot.prompt)
        lines.append(row.value)
        lines.append("")
    return "\n".join(lines).strip()
