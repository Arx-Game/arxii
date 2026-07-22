"""Typed exceptions for the covenants app."""

from typing import ClassVar


class CovenantError(Exception):
    """Base for covenant typed exceptions."""

    user_message: str = "An unexpected covenant error occurred."
    SAFE_MESSAGES: ClassVar[frozenset[str]] = frozenset(
        {
            "An unexpected covenant error occurred.",
        }
    )


class CovenantRoleNeverHeldError(CovenantError):
    """Raised when weaving a COVENANT_ROLE thread for a role never held."""

    user_message = "You must have held this role before you can weave a thread to it."
    SAFE_MESSAGES: ClassVar[frozenset[str]] = frozenset(
        {
            "You must have held this role before you can weave a thread to it.",
        }
    )


class CovenantMemberBlockError(CovenantError):
    """Raised when joining is blocked because a member has blocked the would-be member (#1278).

    Deliberately generic — the joiner is never told *which* member, preserving the anti-derivation
    symmetry (they don't learn the blocker's identity).
    """

    user_message = "This covenant has a member who has blocked you."
    SAFE_MESSAGES: ClassVar[frozenset[str]] = frozenset(
        {
            "This covenant has a member who has blocked you.",
        }
    )


class CovenantFormationError(CovenantError):
    """Base for covenant formation failures."""

    user_message = "Covenant formation failed."
    SAFE_MESSAGES: ClassVar[frozenset[str]] = frozenset(
        {
            "Covenant formation failed.",
        }
    )


class InsufficientFoundersError(CovenantFormationError):
    """Raised when covenant formation is attempted with fewer than two founders.

    Covenants are inherently group structures; collaborative play is the
    point. See `feedback_covenants_are_group_only.md`.
    """

    user_message = "A covenant must be founded by at least two characters."
    SAFE_MESSAGES: ClassVar[frozenset[str]] = frozenset(
        {
            "A covenant must be founded by at least two characters.",
        }
    )


class DuplicateFounderError(CovenantFormationError):
    """Raised when the founder list names the same character more than once."""

    user_message = "Each founder must be a distinct character."
    SAFE_MESSAGES: ClassVar[frozenset[str]] = frozenset(
        {
            "Each founder must be a distinct character.",
        }
    )


class BattleBindingRequiredError(CovenantFormationError):
    """Raised when a BATTLE covenant is created without specifying a battle_binding."""

    user_message = "A Battle covenant must specify a battle_binding (standing or campaign)."
    SAFE_MESSAGES: ClassVar[frozenset[str]] = frozenset(
        {
            "A Battle covenant must specify a battle_binding (standing or campaign).",
        }
    )


class BattleBindingNotAllowedError(CovenantFormationError):
    """Raised when a non-BATTLE covenant is created with a battle_binding set."""

    user_message = "Only Battle covenants may set a battle_binding."
    SAFE_MESSAGES: ClassVar[frozenset[str]] = frozenset(
        {
            "Only Battle covenants may set a battle_binding.",
        }
    )


class CampaignStoryNotAllowedError(CovenantFormationError):
    """Raised when a non-CAMPAIGN covenant is given a campaign_story link."""

    user_message = "Only CAMPAIGN battle covenants may set a campaign_story."
    SAFE_MESSAGES: ClassVar[frozenset[str]] = frozenset(
        {
            "Only CAMPAIGN battle covenants may set a campaign_story.",
        }
    )


class CourtLeaderRequiredError(CovenantFormationError):
    """Raised when a COURT covenant is created without specifying a leader."""

    user_message = "A Court covenant must specify a leader."
    SAFE_MESSAGES: ClassVar[frozenset[str]] = frozenset(
        {
            "A Court covenant must specify a leader.",
        }
    )


class CourtLeaderNotAllowedError(CovenantFormationError):
    """Raised when a non-COURT covenant is created with a leader set."""

    user_message = "Only Court covenants may set a leader."
    SAFE_MESSAGES: ClassVar[frozenset[str]] = frozenset(
        {
            "Only Court covenants may set a leader.",
        }
    )


class CovenantEngagementPrerequisiteNotMetError(CovenantError):
    """Raised when attempting scene engagement without members present."""

    user_message = "No covenant members present to engage with."
    SAFE_MESSAGES: ClassVar[frozenset[str]] = frozenset(
        {
            "No covenant members present to engage with.",
        }
    )


class CovenantNameConflictError(CovenantError):
    """Raised when covenant name already exists."""

    user_message = "A covenant with that name already exists."
    SAFE_MESSAGES: ClassVar[frozenset[str]] = frozenset(
        {
            "A covenant with that name already exists.",
        }
    )


class CovenantRiteError(CovenantError):
    """Base for covenant rite activation failures."""

    user_message = "The rite cannot be performed right now."
    SAFE_MESSAGES: ClassVar[frozenset[str]] = frozenset(
        {
            "The rite cannot be performed right now.",
        }
    )


class CovenantLevelTooLowError(CovenantRiteError):
    """Raised when the covenant's level is below the rite's requirement."""

    user_message = "Your covenant is not yet powerful enough to perform this rite."
    SAFE_MESSAGES: ClassVar[frozenset[str]] = frozenset(
        {
            "Your covenant is not yet powerful enough to perform this rite.",
        }
    )


class NotEnoughMembersPresentError(CovenantRiteError):
    """Raised when too few active covenant members are present to perform the rite."""

    user_message = "Not enough covenant members are present."
    SAFE_MESSAGES: ClassVar[frozenset[str]] = frozenset(
        {
            "Not enough covenant members are present.",
        }
    )


class NoActiveBattleError(CovenantRiteError):
    """Raised when a rite that requires a battle is attempted outside an active encounter."""

    user_message = "This rite can only be performed in battle."
    SAFE_MESSAGES: ClassVar[frozenset[str]] = frozenset(
        {
            "This rite can only be performed in battle.",
        }
    )


class NotAStandingBattleCovenantError(CovenantError):
    """Raised when a rise/stand-down targets a non-STANDING-battle covenant."""

    user_message = "This action requires a standing battle covenant."
    SAFE_MESSAGES: ClassVar[frozenset[str]] = frozenset(
        {
            "This action requires a standing battle covenant.",
        }
    )


class CovenantNotDormantError(CovenantError):
    """Raised when a rise ritual targets a covenant that is not dormant."""

    user_message = "This covenant is already risen — it cannot be called to banners again."
    SAFE_MESSAGES: ClassVar[frozenset[str]] = frozenset(
        {
            "This covenant is already risen — it cannot be called to banners again.",
        }
    )


class CovenantExitError(CovenantError):
    """Base for covenant exit (leave/kick) failures."""

    user_message = "This covenant action is not allowed."
    SAFE_MESSAGES: ClassVar[frozenset[str]] = frozenset(
        {
            "This covenant action is not allowed.",
        }
    )


class NotAuthorizedToKickError(CovenantExitError):
    """Raised when a member without kick permission attempts to remove another member."""

    user_message = "You do not have permission to remove members."
    SAFE_MESSAGES: ClassVar[frozenset[str]] = frozenset(
        {
            "You do not have permission to remove members.",
        }
    )


class CannotKickEqualOrHigherRankError(CovenantExitError):
    """Raised when attempting to remove a member of equal or higher rank."""

    user_message = "You can only remove members ranked below you."
    SAFE_MESSAGES: ClassVar[frozenset[str]] = frozenset(
        {
            "You can only remove members ranked below you.",
        }
    )


class CannotKickSelfError(CovenantExitError):
    """Raised when a leader attempts to kick themselves."""

    user_message = "To leave the covenant yourself, use Leave rather than Kick."
    SAFE_MESSAGES: ClassVar[frozenset[str]] = frozenset(
        {
            "To leave the covenant yourself, use Leave rather than Kick.",
        }
    )


class NotAuthorizedToInviteError(CovenantExitError):
    """Raised when a member without invite permission attempts to invite another member."""

    user_message = "You do not have permission to invite members."
    SAFE_MESSAGES: ClassVar[frozenset[str]] = frozenset(
        {
            "You do not have permission to invite members.",
        }
    )


class NotAuthorizedToManageRanksError(CovenantExitError):
    """Raised when a member without rank management permission attempts to modify ranks."""

    user_message = "You do not have permission to manage covenant ranks."
    SAFE_MESSAGES: ClassVar[frozenset[str]] = frozenset(
        {
            "You do not have permission to manage covenant ranks.",
        }
    )


class LastManagerRankError(CovenantExitError):
    """Raised when attempting to remove rank management capability from the last manager."""

    user_message = "The covenant must keep at least one member who can manage ranks."
    SAFE_MESSAGES: ClassVar[frozenset[str]] = frozenset(
        {
            "The covenant must keep at least one member who can manage ranks.",
        }
    )


class CrossCovenantRankError(CovenantError):
    """Raised when attempting to use a rank from a different covenant."""

    user_message = "That rank does not belong to this covenant."
    SAFE_MESSAGES: ClassVar[frozenset[str]] = frozenset(
        {
            "That rank does not belong to this covenant.",
        }
    )


class IncompleteRankReorderError(CovenantError):
    """Raised when ordered_rank_ids does not include all of a covenant's ranks."""

    user_message = "You must reorder all of the covenant's ranks at once."
    SAFE_MESSAGES: ClassVar[frozenset[str]] = frozenset(
        {
            "You must reorder all of the covenant's ranks at once.",
        }
    )


class CannotTransferToDepartedMemberError(CovenantError):
    """Raised when attempting to transfer leadership to a member who has left."""

    user_message = "You cannot transfer leadership to a member who has left."
    SAFE_MESSAGES: ClassVar[frozenset[str]] = frozenset(
        {
            "You cannot transfer leadership to a member who has left.",
        }
    )


class VowGateError(CovenantError):
    """Raised when a character's level places them outside the covenant band.

    A character out of the covenant's level band cannot join unless they hold
    an active Mentor's Vow bond (as mentor or sidekick) in the same covenant.
    """

    user_message = (
        "Your level is outside this covenant's range. A Mentor's Vow bond is required to join."
    )
    SAFE_MESSAGES: ClassVar[frozenset[str]] = frozenset(
        {
            "Your level is outside this covenant's range. A Mentor's Vow bond is required to join.",
        }
    )


class MentorBondError(CovenantError):
    """Raised when a Mentor's Vow bond cannot be established.

    Covers: neither/both parties out of band; partner not in band;
    max_sidekicks_per_mentor cap exceeded.
    """

    user_message = "The Mentor's Vow bond cannot be established."
    SAFE_MESSAGES: ClassVar[frozenset[str]] = frozenset(
        {
            "The Mentor's Vow bond cannot be established.",
        }
    )


class SecondaryVowRequiresEngagedPrimaryError(CovenantError):
    """Raised when engaging a secondary vow with no engaged primary of the same
    covenant type (#2641) — a secondary is never available without an active
    primary of that type to sit alongside."""

    user_message = "You must have an engaged primary vow of this type before a secondary vow."
    SAFE_MESSAGES: ClassVar[frozenset[str]] = frozenset(
        {
            "You must have an engaged primary vow of this type before a secondary vow.",
        }
    )


class SecondaryVowSameAnchorError(CovenantError):
    """Raised when a secondary vow shares its anchor role with the engaged primary
    vow of the same covenant type (#2641) — "no same-vow secondary": doubling down
    on one vow is allocation (thread investment), not a second vow."""

    user_message = "Your secondary vow cannot be the same vow as your primary."
    SAFE_MESSAGES: ClassVar[frozenset[str]] = frozenset(
        {
            "Your secondary vow cannot be the same vow as your primary.",
        }
    )


class SecondaryVowThreadExceedsPrimaryError(CovenantError):
    """Raised when a secondary vow's COVENANT_ROLE thread level exceeds the
    engaged primary's (#2641) — a secondary is never the deeper of the two."""

    user_message = "Your secondary vow cannot be deeper than your primary vow."
    SAFE_MESSAGES: ClassVar[frozenset[str]] = frozenset(
        {
            "Your secondary vow cannot be deeper than your primary vow.",
        }
    )


class CourtPactExistsError(CovenantError):
    """Raised when swearing a Court pact that already exists (active pact for the same pair)."""

    user_message = "An active Court pact already exists for this servant in this covenant."
    SAFE_MESSAGES: ClassVar[frozenset[str]] = frozenset(
        {
            "An active Court pact already exists for this servant in this covenant.",
        }
    )


class CourtGulfViolationError(CovenantError):
    """Raised when a servant joining a Court is not at least one power tier below the leader.

    Courts require a clear power gulf: the servant's tier must be strictly less than
    the leader's tier. Equal or higher tiers are rejected to preserve narrative hierarchy.
    """

    user_message = (
        "You must be at least one power tier below the Court's leader to swear fealty here."
    )
    SAFE_MESSAGES: ClassVar[frozenset[str]] = frozenset(
        {
            "You must be at least one power tier below the Court's leader to swear fealty here.",
        }
    )


class CourtGrantNotMonotonicError(CovenantError):
    """Raised when a grant raise would lower an existing CourtPact.granted_pull_cap.

    A master's promised power can never be revoked (#1718) — raise_court_pact_grant
    rejects any new_cap below the pact's current granted_pull_cap.
    """

    user_message = "A Court master's word cannot be taken back — the grant can only rise."
    SAFE_MESSAGES: ClassVar[frozenset[str]] = frozenset(
        {
            "A Court master's word cannot be taken back — the grant can only rise.",
        }
    )
