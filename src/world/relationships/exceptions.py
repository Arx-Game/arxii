"""Exceptions for relationship writeup feedback operations.

Each carries a ``user_message`` attribute for safe 400 API responses, mirroring
the style in ``world.progression.exceptions``.
"""

from __future__ import annotations


class WriteupFeedbackError(Exception):
    """Base for all writeup feedback failures."""

    user_message = "Could not record that feedback."

    def __init__(self, message: str | None = None) -> None:
        super().__init__(message or self.user_message)
        self.user_message = message or self.user_message


class WriteupNotSharedError(WriteupFeedbackError):
    """The writeup is private; commendation requires a shared (non-private) writeup."""

    user_message = "You can only commend a writeup that has been shared."


class NotWriteupSubjectError(WriteupFeedbackError):
    """The giver is not the subject of the writeup."""

    user_message = "Only the subject of the writeup can commend it."


class CannotCommendOwnWriteupError(WriteupFeedbackError):
    """The giver is the author of the writeup and cannot self-commend."""

    user_message = "You cannot commend your own writeup."


class AlreadyCommendedError(WriteupFeedbackError):
    """The giver has already commended this writeup (non-revocable, one per account)."""

    user_message = "You have already commended this writeup."


class WriteupNotVisibleError(WriteupFeedbackError):
    """The account cannot view this writeup (e.g. PRIVATE writeup, non-party viewer)."""

    user_message = "You cannot view this writeup."


class RelationshipBumpError(Exception):
    """Base for ambient relationship-bump failures (#1699)."""

    user_message = "Could not record that bump."

    def __init__(self, message: str | None = None) -> None:
        super().__init__(message or self.user_message)
        self.user_message = message or self.user_message


class AlreadyAcknowledgedError(RelationshipBumpError):
    """A bump for this (relationship, interaction) pair already exists."""

    user_message = "You've already acknowledged that."


class SystemTracksNotSeededError(RelationshipBumpError):
    """The generic Regard/Friction system tracks are missing from the database."""

    user_message = "Relationship bumps aren't available right now."
