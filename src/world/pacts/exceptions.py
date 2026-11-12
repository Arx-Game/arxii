"""Player-facing pact failures (#4341). ``user_message`` is safe to display."""


class PactError(Exception):
    """Base: a pact could not be signed or ended. ``user_message`` is player-safe."""

    user_message = "That cannot be done with a pact now."

    def __init__(self, user_message: str | None = None) -> None:
        if user_message is not None:
            self.user_message = user_message
        super().__init__(self.user_message)


class PactAlreadyHeld(PactError):
    """She already holds an active pact with the offer's being."""

    user_message = "You already hold a pact with that being."


class PactOfferUnavailable(PactError):
    """The offer, or its being, is not active."""

    user_message = "That pact is not offered."


class NoActivePact(PactError):
    """She holds no active pact with that being."""

    user_message = "You hold no pact with that being."
