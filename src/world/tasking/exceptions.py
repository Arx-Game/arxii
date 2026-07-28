"""Typed exceptions for the tasking app. Views surface user_message, never str(exc)."""


class TaskingError(Exception):
    """Base for tasking service failures."""

    user_message = "That task operation could not be completed."

    def __init__(self) -> None:
        super().__init__(self.user_message)


class TaskAssignmentError(TaskingError):
    """Base for assignment failures."""

    user_message = "That agent cannot take this task."


class TaskNotOpenError(TaskAssignmentError):
    user_message = "This task already has an assignment or is closed."


class AgentUnavailableError(TaskAssignmentError):
    user_message = "That agent is not available for tasking."


class ForeignAgentError(TaskAssignmentError):
    user_message = "You can only dispatch your own agents."


class HandlerNotMemberError(TaskAssignmentError):
    user_message = "Only members of the issuing organization can handle its tasks."


class TargetConsentError(TaskingError):
    """Raised when an offensive job's PC target hasn't opted into espionage."""

    user_message = "They are not open to that kind of play."


class TaskResolutionError(TaskingError):
    """Raised when a task is not in a resolvable state."""

    user_message = "That task is not ready to resolve."


class NoActiveFulfillmentError(TaskResolutionError):
    user_message = "This task has no active agent on it."
