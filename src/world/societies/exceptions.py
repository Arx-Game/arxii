"""Typed exceptions for the societies app."""

from typing import ClassVar


class LegendError(Exception):
    """Base for societies legend-related typed exceptions.

    Each subclass carries a ``user_message`` class attribute and a ``SAFE_MESSAGES``
    allowlist so callers can surface the message to end-users safely.
    """

    user_message: str = "An error occurred while awarding legend."
    SAFE_MESSAGES: ClassVar[frozenset[str]] = frozenset(
        {
            "An error occurred while awarding legend.",
        }
    )


class LegendAwardParticipantMissingError(LegendError):
    """Raised when a LEGEND_AWARD effect is applied with no participants in context."""

    user_message = "Cannot award legend without participants."
    SAFE_MESSAGES: ClassVar[frozenset[str]] = frozenset(
        {
            "Cannot award legend without participants.",
        }
    )


class LegendAwardScopeError(LegendError):
    """Raised when a LEGEND_AWARD effect is attached to a GLOBAL-scope beat.

    GLOBAL-scope beats do not map to a concrete set of participants, so legend
    cannot be awarded. Task 13 (beat resolution wiring) raises this during
    pool application when it detects a GLOBAL-scope beat with a LEGEND_AWARD
    effect.
    """

    user_message = "Legend awards from GLOBAL-scope beats are not supported."
    SAFE_MESSAGES: ClassVar[frozenset[str]] = frozenset(
        {
            "Legend awards from GLOBAL-scope beats are not supported.",
        }
    )


class OrganizationMembershipError(Exception):
    """Base for typed organization-membership exceptions.

    Carries a safe ``user_message`` and an allowlist so callers can surface
    errors to end-users without leaking internal details.
    """

    user_message: str = "An organization membership error occurred."
    SAFE_MESSAGES: ClassVar[frozenset[str]] = frozenset(
        {"An organization membership error occurred."}
    )


class AlreadyOrganizationMemberError(OrganizationMembershipError):
    user_message = "You are already a member of this organization."
    SAFE_MESSAGES = frozenset({"You are already a member of this organization."})


class NotOrganizationMemberError(OrganizationMembershipError):
    user_message = "You are not a member of this organization."
    SAFE_MESSAGES = frozenset({"You are not a member of this organization."})


class NotAuthorizedToInviteError(OrganizationMembershipError):
    user_message = "You are not authorized to invite members to this organization."
    SAFE_MESSAGES = frozenset({"You are not authorized to invite members to this organization."})


class NotAuthorizedToKickError(OrganizationMembershipError):
    user_message = "You are not authorized to remove members from this organization."
    SAFE_MESSAGES = frozenset({"You are not authorized to remove members from this organization."})


class NotAuthorizedToManageRanksError(OrganizationMembershipError):
    user_message = "You are not authorized to manage ranks in this organization."
    SAFE_MESSAGES = frozenset({"You are not authorized to manage ranks in this organization."})


class NotAuthorizedToManageOrganizationError(OrganizationMembershipError):
    user_message = "You do not outrank that member."
    SAFE_MESSAGES = frozenset({"You do not outrank that member."})


class OrganizationOfferResolvedError(OrganizationMembershipError):
    user_message = "That offer has already been resolved."
    SAFE_MESSAGES = frozenset({"That offer has already been resolved."})


class OrganizationOfferNotForYouError(OrganizationMembershipError):
    user_message = "That offer is not for you."
    SAFE_MESSAGES = frozenset({"That offer is not for you."})


class OrganizationOfferPendingError(OrganizationMembershipError):
    user_message = "You already have a pending offer for that organization."
    SAFE_MESSAGES = frozenset({"You already have a pending offer for that organization."})


class OrganizationMemberBlockError(OrganizationMembershipError):
    user_message = "You cannot join this organization due to an active block."
    SAFE_MESSAGES = frozenset({"You cannot join this organization due to an active block."})


class InvalidOrganizationPersonaError(OrganizationMembershipError):
    user_message = "Only primary or established personas can join organizations."
    SAFE_MESSAGES = frozenset({"Only primary or established personas can join organizations."})


class CannotPromoteError(OrganizationMembershipError):
    user_message = "This member cannot be promoted further."
    SAFE_MESSAGES = frozenset({"This member cannot be promoted further."})


class CannotDemoteError(OrganizationMembershipError):
    user_message = "This member cannot be demoted further."
    SAFE_MESSAGES = frozenset({"This member cannot be demoted further."})


class CrossOrganizationRankError(OrganizationMembershipError):
    user_message = "That member is not in the same organization."
    SAFE_MESSAGES = frozenset({"That member is not in the same organization."})


class NoPendingInvitationError(OrganizationMembershipError):
    user_message = "You have no pending invitation to that organization."
    SAFE_MESSAGES = frozenset({"You have no pending invitation to that organization."})


class NotAGenericOrganizationError(OrganizationMembershipError):
    user_message = "This organization uses a covenant membership lifecycle, not the generic one."
    SAFE_MESSAGES = frozenset(
        {"This organization uses a covenant membership lifecycle, not the generic one."}
    )
