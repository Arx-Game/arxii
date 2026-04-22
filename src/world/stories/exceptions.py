class StoryError(Exception):
    """Base class for stories-app user-facing errors."""

    _SAFE_MESSAGE = "A story system error occurred."

    @property
    def user_message(self) -> str:
        return self._SAFE_MESSAGE


class BeatNotResolvableError(StoryError):
    _SAFE_MESSAGE = "This beat cannot be resolved in its current state."


class NoEligibleTransitionError(StoryError):
    _SAFE_MESSAGE = "There is no transition available to advance this episode."


class AmbiguousTransitionError(StoryError):
    _SAFE_MESSAGE = "Multiple transitions are eligible — please pick one."


class ProgressionRequirementNotMetError(StoryError):
    _SAFE_MESSAGE = "Progression requirements for this episode are not yet met."
