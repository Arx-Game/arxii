"""Exception hierarchy for the guarded beta-reset wipe (#3055 PR 2)."""

from __future__ import annotations


class BetaResetError(Exception):
    """Base for every beta-reset refusal.

    Attributes:
        user_message: Operator-facing explanation, safe to print to stdout.
    """

    def __init__(self, user_message: str = "") -> None:
        super().__init__(user_message)
        self.user_message = user_message


class BetaResetDisabledError(BetaResetError):
    """Raised when the hardcoded ``BETA_RESET_ENABLED`` constant is False."""

    def __init__(
        self,
        user_message: str = (
            "The beta-reset command is disabled (BETA_RESET_ENABLED = False in "
            "world/beta_reset/services.py). This is a deliberate post-cutover code "
            "change; re-enabling it requires a reviewed PR."
        ),
    ) -> None:
        super().__init__(user_message)


class ReleaseLatchedError(BetaResetError):
    """Raised when a ``ReleaseLatch`` row already exists.

    Independent of ``BETA_RESET_ENABLED`` — this is the belt-and-suspenders
    DB-side guard that survives even a stale deploy.
    """

    def __init__(
        self,
        user_message: str = (
            "A ReleaseLatch row already exists — early access has been marked "
            "released. The beta reset can never run again, by design."
        ),
    ) -> None:
        super().__init__(user_message)


class ConfirmationPhraseMismatchError(BetaResetError):
    """Raised when the typed confirmation phrase doesn't match exactly."""

    def __init__(
        self,
        user_message: str = "The typed confirmation phrase did not match. Nothing was touched.",
    ) -> None:
        super().__init__(user_message)


class BackupNotVerifiedError(BetaResetError):
    """Raised when ``--backup-verified-at`` is missing, malformed, or stale."""

    def __init__(
        self,
        user_message: str = (
            "--backup-verified-at is required, must be an ISO-8601 timestamp, and must be "
            "within the freshness window. Run a backup restore-verify (see infra/scripts/"
            "restore-rehearsal.sh) immediately before this command."
        ),
    ) -> None:
        super().__init__(user_message)


class AlreadyReleasedError(BetaResetError):
    """Raised by ``mark_released()`` when a ``ReleaseLatch`` row already exists.

    Distinct from ``ReleaseLatchedError`` (raised by the wipe path) — this one
    is raised by the write side, since the latch is refuse-if-exists, not
    upsert.
    """

    def __init__(
        self,
        user_message: str = (
            "A ReleaseLatch row already exists. mark_released() refuses to write a second "
            "one — the latch is one-way by design."
        ),
    ) -> None:
        super().__init__(user_message)


class CarryOverError(BetaResetError):
    """Raised when a character named for carry-over cannot be carried over.

    The operator named it with ``--carry-over``; the message says which character and why,
    and nothing was touched.
    """


class IncompleteLedgerError(BetaResetError):
    """Raised when the provenance ledger of a kept character is not whole.

    Subtracting the play-time deltas from an incomplete ledger would restore a wrong number,
    so execution refuses by default and names every character and trait. Nothing was touched.
    ``--allow-incomplete-ledger`` proceeds past them.
    """

    def __init__(self, findings: dict[str, list[str]]) -> None:
        self.findings = findings
        lines = [f"  {name}: {'; '.join(problems)}" for name, problems in findings.items()]
        super().__init__(
            "The provenance ledger is incomplete for these characters, so their progress "
            "cannot be reversed reliably:\n"
            + "\n".join(lines)
            + "\nRe-run with --allow-incomplete-ledger to proceed past them. Nothing was touched."
        )


class WipeBlockedError(BetaResetError):
    """Raised when a ``ProtectedError`` stops the cutover; the whole cutover rolled back."""

    def __init__(self, blocking_models: list[str], detail: str) -> None:
        self.blocking_models = blocking_models
        super().__init__(
            f"The cutover was blocked by {', '.join(blocking_models)} rows that point at rows "
            f"the wipe deletes ({detail}). Everything was rolled back and nothing changed."
        )


class CutoverFailedError(BetaResetError):
    """Raised when any other failure stops the cutover; the whole cutover rolled back."""

    def __init__(self, cause: Exception) -> None:
        super().__init__(
            f"The cutover failed with {type(cause).__name__}: {cause}. Everything was rolled "
            "back and nothing changed."
        )
