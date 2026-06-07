"""Spec A magic-app exceptions. Each carries a user_message allowlist
per the project's no-str(exc)-in-API rule (CLAUDE.md)."""

from typing import ClassVar


class MagicError(Exception):
    user_message = "An error occurred."


class ResonanceInsufficient(MagicError):
    user_message = "You do not have enough resonance for this."


class AnchorCapExceeded(MagicError):
    user_message = "This thread cannot grow beyond its anchor's strength."


class AnchorCapNotImplemented(MagicError):
    user_message = "This anchor's growth ceiling is not yet implemented."


class PathCapExceeded(MagicError):
    user_message = "Your Path stage limits this thread's growth."


class XPInsufficient(MagicError):
    user_message = "You do not have enough XP for this."


class InvalidImbueAmount(MagicError):
    user_message = "Invalid imbue amount."


class CovenantRoleNotEngagedError(InvalidImbueAmount):
    """A COVENANT_ROLE Thread pull was attempted while no engaged membership matches."""

    user_message = "You're not currently fulfilling this covenant role."


class WeavingUnlockMissing(MagicError):
    user_message = "You have not learned to weave threads of this kind."


class NoMatchingWornFacetItemsError(MagicError):
    user_message = "You aren't wearing anything bearing this facet."


class RitualComponentError(MagicError):
    user_message = "You do not have the required components for this ritual."


class NoRitualConfigured(MagicError):
    user_message = "You don't have an anima ritual configured."


class RitualAlreadyPerformedThisScene(MagicError):
    user_message = "You've already performed your ritual in this scene."


class CharacterEngagedForRitual(MagicError):
    user_message = "You cannot perform a ritual during combat."


class AnimaPoolAtMaximum(MagicError):
    user_message = "Your anima pool is already full."


class RitualScenePrerequisiteFailed(MagicError):
    user_message = "You cannot perform a ritual right now."


class EndorsementValidationError(Exception):
    """Raised when endorsement preconditions fail."""

    def __init__(self, reason: str, user_message: str | None = None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.user_message = user_message or reason


# =============================================================================
# Corruption exceptions (Scope #7)
# =============================================================================


class CorruptionError(Exception):
    """Base for corruption-related typed exceptions."""

    user_message: str = "Corruption operation failed."
    SAFE_MESSAGES: ClassVar[frozenset[str]] = frozenset(
        {"Corruption operation failed."},
    )

    def __init__(self, user_message: str | None = None) -> None:
        if user_message is not None:
            self.user_message = user_message
        super().__init__(self.user_message)


class ProtagonismLockedError(CorruptionError):
    """Raised when a service is invoked on a sheet that is mechanically locked from protagonism."""

    user_message = "Character is currently locked from protagonism and cannot perform this action."
    SAFE_MESSAGES: ClassVar[frozenset[str]] = frozenset(
        {"Character is currently locked from protagonism and cannot perform this action."},
    )


# =============================================================================
# Soul Tether exceptions (Spec B)
# =============================================================================


class SoulTetherError(Exception):
    """Base exception for Soul Tether errors.

    Carries user_message + SAFE_MESSAGES allowlist per project rule
    (CLAUDE.md: never use str(exc) in API responses).
    """

    user_message: str = "Soul Tether operation failed."
    SAFE_MESSAGES: ClassVar[frozenset[str]] = frozenset()

    def __init__(self, user_message: str | None = None) -> None:
        if user_message is not None:
            self.user_message = user_message
        super().__init__(self.user_message)


class AffinityGateError(SoulTetherError):
    """Raised when the proposed pairing fails the §3 affinity gates."""

    user_message: str = "Affinity gate failed for Soul Tether formation."
    SAFE_MESSAGES: ClassVar[frozenset[str]] = frozenset(
        {
            "Affinity gate failed for Soul Tether formation.",
            "Sineater must be Celestial- or Primal-affinity primary.",
            "Sinner cannot be Celestial-affinity primary.",
        },
    )


class NoSoulTetherUnlockError(SoulTetherError):
    """Raised when the Sinner has not purchased the RELATIONSHIP_CAPSTONE ThreadWeavingUnlock."""

    user_message: str = "Sinner has not unlocked Relationship Capstone thread weaving yet."
    SAFE_MESSAGES: ClassVar[frozenset[str]] = frozenset(
        {"Sinner has not unlocked Relationship Capstone thread weaving yet."},
    )


class SoulTetherFormationError(SoulTetherError):
    """Raised when formation prerequisites fail (consent, role, etc.)."""

    user_message: str = "Soul Tether formation failed."
    SAFE_MESSAGES: ClassVar[frozenset[str]] = frozenset(
        {
            "Soul Tether formation failed.",
            "Both characters must consent to forming a Soul Tether.",
            "An active Soul Tether already exists between these characters.",
        },
    )


class SineatingValidationError(SoulTetherError):
    """Raised when a Sineating request fails validation."""

    user_message: str = "Sineating request failed validation."
    SAFE_MESSAGES: ClassVar[frozenset[str]] = frozenset(
        {
            "Sineating request failed validation.",
            "No active Soul Tether exists between these characters.",
            "Both characters must be in the same scene to perform Sineating.",
            "Resonance specified is not one the Sinner accrues.",
            "Per-scene Sineating cap reached for this bond.",
            "No pending Sineating offer found.",
            "This offer expired because you are no longer in the same scene.",
        },
    )


class RescueValidationError(SoulTetherError):
    """Raised when rescue ritual gates fail."""

    user_message: str = "Soul Tether rescue ritual failed validation."
    SAFE_MESSAGES: ClassVar[frozenset[str]] = frozenset(
        {
            "Soul Tether rescue ritual failed validation.",
            "Sinner must be at corruption stage 3 or higher to be rescued.",
            "Both characters must be in the same scene for the rescue ritual.",
            "Rescue ritual already performed for this Sinner this scene.",
            "Sineater has insufficient resonance for the ritual cost.",
        },
    )


class StageAdvanceBonusError(SoulTetherError):
    """Raised when a stage-advance bonus offer resolution fails (Spec B §8.1)."""

    user_message: str = "Stage-advance bonus resolution failed."
    SAFE_MESSAGES: ClassVar[frozenset[str]] = frozenset(
        {
            "Stage-advance bonus resolution failed.",
            "No pending stage-advance offer found with that ID.",
            "Units committed exceeds the maximum available Hollow.",
            "No pending stage-advance offer found.",
            "This stage-advance prompt expired before you could respond.",
            "This stage-advance prompt expired; you are no longer in the same scene.",
        },
    )


# =============================================================================
# Ritual Session exceptions (Covenants Slice B)
# =============================================================================


class RitualSessionError(Exception):
    """Base for ritual session lifecycle errors."""

    user_message: str = "Ritual session operation failed."
    SAFE_MESSAGES: ClassVar[frozenset[str]] = frozenset()

    def __init__(self, user_message: str | None = None) -> None:
        if user_message is not None:
            self.user_message = user_message
        super().__init__(self.user_message)


class SessionNotInPendingError(RitualSessionError):
    user_message = "This ritual session is no longer accepting responses."
    SAFE_MESSAGES = frozenset({user_message})


class ThresholdNotMetError(RitualSessionError):
    user_message = "Not enough participants have accepted yet."
    SAFE_MESSAGES = frozenset({user_message})


class RequiredReferenceMissingError(RitualSessionError):
    user_message = "A required choice was not provided."
    SAFE_MESSAGES = frozenset({user_message})


class SessionTargetMissingError(RitualSessionError):
    user_message = "The target of this ritual is no longer available."
    SAFE_MESSAGES = frozenset({user_message})


class NotInvitedError(RitualSessionError):
    user_message = "You are not invited to this ritual session."
    SAFE_MESSAGES = frozenset({user_message})


class NotInitiatorError(RitualSessionError):
    user_message = "Only the ritual's initiator can perform this action."
    SAFE_MESSAGES = frozenset({user_message})


class BilateralRoleConflictError(RitualSessionError):
    user_message = "Both participants chose the same role; the ritual requires distinct roles."
    SAFE_MESSAGES = frozenset({user_message})


class ParticipantCountError(RitualSessionError):
    user_message = "The number of participants does not satisfy this ritual's requirements."
    SAFE_MESSAGES = frozenset({user_message})


# =============================================================================
# Technique Builder exceptions (#537)
# =============================================================================


class TechniqueAuthoringNotPermitted(MagicError):
    user_message = "You are not permitted to author a technique at that tier."


class TechniqueBudgetExceeded(MagicError):
    user_message = "This design exceeds the power budget for its tier."

    def __init__(self, breakdown=None):
        super().__init__(self.user_message)
        self.breakdown = breakdown
