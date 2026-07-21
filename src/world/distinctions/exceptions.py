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


class DistinctionRevokeError(Exception):
    """Raised when a distinction cannot be revoked through the change flow (#2607).

    Defensive guard: ``revoke_distinction`` refuses a distinction carrying
    resonance/asset/codex grants (no clean unwind) rather than silently orphaning
    monotonic resonance currency. ``change_supported`` gates this upstream at
    request submit; this exception is the last line.
    """

    user_message: str = "This distinction cannot be removed through this flow."
    SAFE_MESSAGES: ClassVar[frozenset[str]] = frozenset()

    def __init__(self, user_message: str | None = None) -> None:
        if user_message is not None:
            self.user_message = user_message
        super().__init__(self.user_message)
