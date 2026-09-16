"""Player-facing worship failures (#3777). ``user_message`` is safe to display."""


class WorshipRiteError(Exception):
    """Base: a rite could not be performed. ``user_message`` is player-safe."""

    user_message = "That rite cannot be performed now."

    def __init__(self, user_message: str | None = None) -> None:
        if user_message is not None:
            self.user_message = user_message
        super().__init__(self.user_message)


class RiteNotAvailable(WorshipRiteError):
    """The rite or its being is inactive, or the rite is a ceremony-only tier."""

    user_message = "That rite is not open to you here."


class RiteIsCeremony(RiteNotAvailable):
    """A tier 3 rite is performed as a Ceremony, never as a solo act."""

    user_message = "That rite is a ceremony: open one in the being's name."


class RiteScenePrerequisiteFailed(WorshipRiteError):
    """A rite is a scene act: it needs an active scene the performer is in."""

    user_message = "A rite is performed in a live scene you have entered."


class RiteActionPointsInsufficient(WorshipRiteError):
    """The tier's AP cost could not be paid."""

    user_message = "You don't have enough action points for that rite."


class RiteAwardMissing(WorshipRiteError):
    """No WorshipRiteTierAward row for this tier and outcome: a content gap,
    raised rather than paying 0 (the AnimaRitualBudgetAward convention)."""

    user_message = "That rite's rewards are not configured yet; tell staff."


class ConsecrationError(Exception):
    """A shrine or temple could not be founded, grown or dissolved; player-safe."""

    user_message = "That cannot be consecrated."

    def __init__(self, user_message: str | None = None) -> None:
        if user_message is not None:
            self.user_message = user_message
        super().__init__(self.user_message)


class SiteNotHeld(ConsecrationError):
    user_message = "You do not hold this place."


class SiteAlreadyTaken(ConsecrationError):
    user_message = "This place already carries a feature or dedication."


class SiteNotFound(ConsecrationError):
    user_message = "There is no such holy site here."
