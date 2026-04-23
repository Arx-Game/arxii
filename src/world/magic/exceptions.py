"""Spec A magic-app exceptions. Each carries a user_message allowlist
per the project's no-str(exc)-in-API rule (CLAUDE.md)."""


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


class WeavingUnlockMissing(MagicError):
    user_message = "You have not learned to weave threads of this kind."


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
