"""Distinctions-app exceptions. Each carries a ``user_message`` allowlist
per the project's no-``str(exc)``-in-API rule (CLAUDE.md)."""

from typing import ClassVar


class DistinctionExclusionError(Exception):
    """Raised when granting/ranking a distinction would violate a mutual or
    variant exclusion rule (service-layer port of ``DraftDistinctionViewSet``'s
    ``_check_mutual_exclusions``/``_check_variant_exclusions``, #2037 Decision 2).
    """

    user_message: str = "This distinction conflicts with one you already hold."
    SAFE_MESSAGES: ClassVar[frozenset[str]] = frozenset()

    def __init__(self, user_message: str | None = None) -> None:
        if user_message is not None:
            self.user_message = user_message
        super().__init__(self.user_message)


class DistinctionPrerequisiteError(Exception):
    """Raised when removing a distinction that another held distinction depends on."""

    user_message: str = "Cannot remove this distinction — another distinction depends on it."

    def __init__(self, user_message: str | None = None) -> None:
        if user_message is not None:
            self.user_message = user_message
        super().__init__(self.user_message)


class DistinctionAuthorizationError(Exception):
    """Raised when a DistinctionChangeAuthorization is invalid or already consumed."""

    user_message: str = "This distinction change authorization is not valid."

    def __init__(self, user_message: str | None = None) -> None:
        if user_message is not None:
            self.user_message = user_message
        super().__init__(self.user_message)
