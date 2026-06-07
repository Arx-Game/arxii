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


class SubrolePromotionError(CovenantError):
    """Base for sub-role promotion failures."""

    user_message = "Sub-role promotion failed."
    SAFE_MESSAGES: ClassVar[frozenset[str]] = frozenset(
        {
            "Sub-role promotion failed.",
        }
    )


class SubroleParentMismatchError(SubrolePromotionError):
    """Raised when the target sub-role's parent does not match the membership's role."""

    user_message = "Target sub-role's parent does not match your current role in this covenant."
    SAFE_MESSAGES: ClassVar[frozenset[str]] = frozenset(
        {
            "Target sub-role's parent does not match your current role in this covenant.",
        }
    )


class SubroleThreadLevelInsufficientError(SubrolePromotionError):
    """Raised when the character's Thread level on the parent role is too low."""

    user_message = (
        "Your Thread level on the parent role is not yet high enough to unlock this sub-role."
    )
    SAFE_MESSAGES: ClassVar[frozenset[str]] = frozenset(
        {
            "Your Thread level on the parent role is not yet high enough to unlock this sub-role.",
        }
    )


class SubroleResonanceMismatchError(SubrolePromotionError):
    """Raised when the character has no Thread on the parent role with the matching resonance."""

    user_message = "You do not have a Thread on the parent role with the matching resonance."
    SAFE_MESSAGES: ClassVar[frozenset[str]] = frozenset(
        {
            "You do not have a Thread on the parent role with the matching resonance.",
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
