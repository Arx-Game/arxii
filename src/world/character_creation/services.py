"""
Character Creation service functions.

Handles the business logic for character creation, including
draft management and character finalization.
"""

from django.db import transaction
from evennia.utils import create

from world.character_creation.models import CharacterDraft
from world.roster.models import Roster, RosterEntry


class CharacterCreationError(Exception):
    """Base exception for character creation errors."""


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
    elif draft.selected_heritage:
        family_name = ""  # Special heritage characters have no family name initially

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
    if draft.age:
        sheet.age = draft.age

    # Set species from draft's FK
    if draft.selected_species:
        sheet.species = draft.selected_species

    # Set family from draft
    if draft.family:
        sheet.family = draft.family

    # Set heritage - use SpecialHeritage's linked Heritage FK
    if draft.selected_heritage:
        sheet.heritage = draft.selected_heritage.heritage
    else:
        # Normal heritage - ensure it exists
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

    sheet.save()

    character.save()

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

    # Clean up the draft
    draft.delete()

    return character


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
