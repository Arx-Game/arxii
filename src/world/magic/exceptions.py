"""Spec A magic-app exceptions. Each carries a user_message allowlist
per the project's no-str(exc)-in-API rule (CLAUDE.md)."""

from typing import ClassVar


class MagicError(Exception):
    """Base for player-surfaceable magic failures.

    ``user_message`` is what reaches the player. Raise-sites that pass an
    explicit message are authoring player-facing text (e.g. "Unknown
    resonance.") and it becomes the user_message; raising with no args keeps
    the subclass's class-level message. Never surface ``str(exc)`` of other
    exception types (#2386 tranche 4).
    """

    user_message = "An error occurred."

    def __init__(self, *args: object) -> None:
        super().__init__(*args)
        # Only bare MagicError treats its message as player text (the pull
        # paths author these). Subclasses raise with INTERNAL detail ("Need
        # 100 XP … trait_258") and keep their curated class-level
        # user_message — never leak the internals.
        if type(self) is MagicError and args and isinstance(args[0], str) and args[0]:
            self.user_message = args[0]


class ResonanceInsufficient(MagicError):
    user_message = "You do not have enough resonance for this."


class AnchorCapExceeded(MagicError):
    user_message = "This thread cannot grow beyond its anchor's strength."


class PathCapExceeded(MagicError):
    user_message = "Your Path stage limits this thread's growth."


class XPInsufficient(MagicError):
    user_message = "You do not have enough XP for this."


class TechniqueStyleForbidden(MagicError):
    user_message = "Your path does not permit this technique's style."


class GiftUnlockMissing(MagicError):
    user_message = "You must unlock this gift before learning its techniques."


class TechniqueCapExceeded(MagicError):
    user_message = (
        "You have reached the maximum techniques for this gift at your current thread level."
    )


class GiftAlreadyOwnedError(MagicError):
    user_message = "You already have this gift."


class InvalidImbueAmount(MagicError):
    user_message = "Invalid imbue amount."


class CovenantRoleNotEngagedError(InvalidImbueAmount):
    """A COVENANT_ROLE Thread pull was attempted while no engaged membership matches."""

    user_message = "You're not currently fulfilling this covenant role."


class WeavingUnlockMissing(MagicError):
    user_message = "You have not learned to weave threads of this kind."


class MantleNotClearedError(MagicError):
    """Raised when weaving a MANTLE thread for a mantle whose level 1 isn't cleared."""

    user_message = "You must clear this mantle's first rank before you can weave a thread to it."


class NoMatchingWornFacetItemsError(MagicError):
    user_message = "You aren't wearing anything bearing this facet."


class RitualComponentError(MagicError):
    user_message = "You do not have the required components for this ritual."


class NoRitualConfigured(MagicError):
    user_message = "You don't have an anima ritual configured."


class RitualCheckConfigMissing(MagicError):
    user_message = "This ritual's check has not been configured."


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
# Audere offer exceptions (#873)
# =============================================================================


class AudereOfferError(Exception):
    """Base for Audere offer-surface errors. Carries user_message per
    the no-str(exc)-in-API rule (CLAUDE.md)."""

    user_message: str = "Audere offer operation failed."
    SAFE_MESSAGES: ClassVar[frozenset[str]] = frozenset()

    def __init__(self, user_message: str | None = None) -> None:
        if user_message is not None:
            self.user_message = user_message
        super().__init__(self.user_message)


class AudereOfferNotFoundError(AudereOfferError):
    user_message = "No pending Audere offer found."
    SAFE_MESSAGES = frozenset({user_message})


class AudereOfferStaleError(AudereOfferError):
    user_message = "The Audere gate has closed; this offer is no longer valid."
    SAFE_MESSAGES = frozenset({user_message})


# =============================================================================
# Audere Majora offer exceptions (#543)
# =============================================================================


class AudereMajoraOfferError(AudereOfferError):
    """Base for Audere Majora offer-surface errors.

    Subclasses AudereOfferError so callers can catch the whole offer-surface
    family in one clause; user_message semantics inherited.
    """

    user_message: str = "Audere Majora offer operation failed."


class AudereMajoraOfferNotFoundError(AudereMajoraOfferError):
    user_message = "No pending Crossing offer found."
    SAFE_MESSAGES = frozenset({user_message})


class AudereMajoraOfferStaleError(AudereMajoraOfferError):
    user_message = "The moment has passed — the threshold no longer answers."
    SAFE_MESSAGES = frozenset({user_message})


class AudereMajoraPathError(AudereMajoraOfferError):
    user_message = "That path is not open to you at this crossing."
    SAFE_MESSAGES = frozenset({user_message})


# =============================================================================
# Entry flourish offer exceptions (#1140)
# =============================================================================


class EntryFlourishOfferError(Exception):
    """Base for entry-flourish offer resolution failures."""

    user_message: str = "Could not resolve the entry flourish."
    SAFE_MESSAGES: ClassVar[frozenset[str]] = frozenset()


class EntryFlourishOfferNotFoundError(EntryFlourishOfferError):
    user_message = "No pending entry flourish offer found."
    SAFE_MESSAGES = frozenset({user_message})


class EntryFlourishOfferStaleError(EntryFlourishOfferError):
    user_message = "That resonance is no longer available for your flourish."
    SAFE_MESSAGES = frozenset({user_message})


# =============================================================================
# Trait crossing exceptions (#1989)
# =============================================================================


class CrossingOfferError(Exception):
    """Base error for crossing offer resolution."""

    user_message: str = "An error occurred with your crossing offer."
    SAFE_MESSAGES: ClassVar[frozenset[str]] = frozenset()


class CrossingOfferNotFoundError(CrossingOfferError):
    user_message = "You have no pending crossing offer."
    SAFE_MESSAGES = frozenset({user_message})


class CrossingOfferStaleError(CrossingOfferError):
    user_message = "That option is no longer available for this crossing."
    SAFE_MESSAGES = frozenset({user_message})


# =============================================================================
# Dramatic moment exceptions (#544)
# =============================================================================


class DramaticMomentCapExceeded(Exception):
    """Raised when a dramatic moment tag would exceed the per_scene_cap for the type."""

    user_message = "This dramatic moment has already been awarded its maximum times this scene."
    SAFE_MESSAGES: ClassVar[frozenset[str]] = frozenset({user_message})


class DramaticMomentSuggestionAlreadyResolved(MagicError):
    """Raised when resolving a DramaticMomentSuggestion that is no longer PENDING (#2183)."""

    user_message = "That suggestion has already been resolved."


# =============================================================================
# Technique Builder exceptions (#537)
# =============================================================================


class UnsupportedGiftResonanceError(MagicError):
    user_message = "That resonance is not supported by this gift."


class TechniqueAuthoringNotPermitted(MagicError):
    user_message = "You are not permitted to author a technique at that tier."


class TechniqueBudgetExceeded(MagicError):
    user_message = "This design exceeds the power budget for its tier."

    def __init__(self, breakdown=None):
        super().__init__(self.user_message)
        self.breakdown = breakdown


class DuplicateTechniqueName(MagicError):
    """Raised when authoring a Technique whose (gift, name) collides with an existing
    row — pre-checked ahead of the INSERT so a name collision fails clean instead of
    an unhandled IntegrityError against the ``unique_technique_name_per_gift`` DB
    constraint (#2486)."""

    user_message = "A technique with that name already exists for this gift."


# =============================================================================
# Technique Draft exceptions (#1496)
# =============================================================================


class NoActiveTechniqueDraft(MagicError):
    user_message = "You have no technique draft. Start one with `technique draft <name>`."


class TechniqueDraftIncomplete(MagicError):
    """Raised when a required draft field is unset at draft_to_design time."""

    user_message = "Draft is incomplete; some required fields are unset."

    def __init__(self, missing_fields: list[str]) -> None:
        self.missing_fields = list(missing_fields)
        msg = f"Draft is incomplete. Missing: {', '.join(self.missing_fields)}."
        self.user_message = msg
        super().__init__(msg)


class UnknownTechniqueVocab(MagicError):
    user_message = "Unknown technique vocabulary term (gift, style, effect type, or restriction)."


class UnknownGift(UnknownTechniqueVocab):
    """Raised when a gift_id does not resolve to a known Gift."""

    user_message = "Unknown gift."


class InvalidConsequencePoolChoice(MagicError):
    user_message = "That outcome flavor isn't available. Choose one from the catalog."


class GiftNotOwned(MagicError):
    user_message = "You do not know that gift."


class TechniqueNotOwned(MagicError):
    """Raised when weaving a signature (TECHNIQUE) thread on a technique the
    character does not know (no CharacterTechnique row)."""

    user_message = "You do not know this technique."


class RelationshipBondNotOwned(MagicError):
    """Raised when weaving a RELATIONSHIP_TRACK/RELATIONSHIP_CAPSTONE thread on a
    relationship-track or capstone row the weaving character does not itself hold
    (i.e. the row's ``relationship.source`` is a different CharacterSheet, #2033).
    Protects both the telnet and web (``ThreadSerializer``) weave paths — the two
    relationship-kind anchors are the only ones whose owning row can belong to
    someone else's relationship."""

    user_message = "That isn't your own relationship bond to weave a thread on."


# =============================================================================
# Signature-bonus selection exceptions (#1582)
# =============================================================================


class NotATechniqueThread(MagicError):
    """Raised when set_signature_bonus is called on a non-TECHNIQUE-kind Thread."""

    user_message = "A signature bonus can only be set on a technique thread."


class SignatureBonusNotAvailable(MagicError):
    """Raised when the requested SignatureMotifBonus does not qualify for the owner's Motif."""

    user_message = "This bonus is not available for your motif."


class SignatureBelowCrossing(MagicError):
    """Raised when set_signature_bonus is called on a thread below the first crossing (level 3)."""

    user_message = "A signature can only be set on a technique thread that has crossed level 3."


class SignatureBonusLocked(MagicError):
    """Raised when the bonus requires a higher crossing level than the thread has reached."""

    user_message = "That signature bonus requires a deeper thread. Keep imbuing."


# =============================================================================
# Player-facing Motif style-binding exceptions (#2030)
# =============================================================================


class StyleResonanceUnclaimed(MagicError):
    user_message = "You have not claimed that resonance."


class StyleBindingCapExceeded(MagicError):
    user_message = "You cannot bind any more styles to that resonance."


class StyleNotBound(MagicError):
    user_message = "That style is not bound to any of your resonances."


# =============================================================================
# Portal travel — anchor install/dissolve exceptions (#2222)
# =============================================================================


class PortalAnchorStandingRequired(MagicError):
    """Raised when installing an anchor without owner or tenant standing."""

    user_message = "You don't have standing to install a portal anchor here."


class PortalAnchorKindAlreadyInstalled(MagicError):
    """Raised when the room already has an active anchor of the requested kind."""

    user_message = "An anchor of that kind is already installed here."


class PortalAnchorFundsInsufficient(MagicError):
    """Raised when the installer's purse can't cover ``PORTAL_ANCHOR_INSTALL_COST``."""

    user_message = "You cannot afford to install a portal anchor here."


class PortalAnchorDissolveNotAllowed(MagicError):
    """Raised when dissolving an anchor without owner standing (owner-gated, #2222)."""

    user_message = "You don't have standing to dissolve this anchor."


# ---------------------------------------------------------------------------
# #1583 — Fall / Redemption
# ---------------------------------------------------------------------------


class FallRedemptionError(MagicError):
    """Base for all Fall/Redemption conversion refusals.

    Carries a ``user_message`` safe for display; callers surface this to the
    player rather than the raw exception string.
    """

    user_message: str

    def __init__(self, user_message: str) -> None:
        super().__init__(user_message)
        self.user_message = user_message


class FallEligibilityError(FallRedemptionError):
    """Raised when a character's aura has not drifted enough for a Fall/Redemption,
    or when they have already undergone an irreversible conversion."""


class ConversionMappingError(FallRedemptionError):
    """Raised when no ResonanceConversion row exists for a
    (source_resonance, target_affinity) pair."""


class PenanceError(FallRedemptionError):
    """Raised when there is no non-native resonance to convert during Atonement."""


class AlreadyInTraditionError(MagicError):
    """Raised when ``join_tradition`` is called with the character's own currently
    active tradition (#2441) — a no-op re-join is refused rather than silently
    swapping the row for itself."""

    user_message = "You are already a member of this tradition."


class NoActiveTraditionError(MagicError):
    """Raised when ``leave_tradition`` is called on a character with no active
    ``CharacterTradition`` row (#2441) — already traditionless, nothing to leave."""

    user_message = "You have no tradition to leave."


class GhostTutorError(MagicError):
    """Base for ghost-tutor summoning failures (#2460)."""

    user_message = "The summoning fails."


class NotTraditionMemberError(GhostTutorError):
    """Raised when the summoner is not an active member of the target tradition.

    You can only summon a tutor for *your* tradition — the tutelage substitutes
    for the dead-trainer side, it doesn't bypass membership.
    """

    user_message = "You are not a member of that tradition."


class GhostTutelageAlreadyExistsError(GhostTutorError):
    """Raised when a GhostTutelage already exists for (character, tradition).

    Raised (not silently succeeded) so the transaction rolls back and the
    consumed ritual components are refunded — the player loses nothing and
    gets a clear 'already summoned' message.
    """

    user_message = "You have already summoned a tutor for that tradition."
