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


class AssistantClaimError(StoryError):
    _SAFE_MESSAGE = "An assistant GM claim operation failed."


class BeatNotAGMEligibleError(AssistantClaimError):
    _SAFE_MESSAGE = "This beat is not flagged as available for Assistant GM claims."


class ClaimNotApprovableError(AssistantClaimError):
    _SAFE_MESSAGE = "This claim is not in a state where it can be approved or rejected."


class ClaimApprovalPermissionError(AssistantClaimError):
    _SAFE_MESSAGE = "Only the Lead GM or Staff can approve or reject this claim."


class ClaimStateTransitionError(AssistantClaimError):
    _SAFE_MESSAGE = "This claim cannot transition to the requested state."


class SessionRequestNotOpenError(StoryError):
    _SAFE_MESSAGE = "This session request cannot be scheduled in its current state."
