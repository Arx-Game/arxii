"""Exceptions for the relationships app. Each carries ``user_message`` for safe 400s."""

from __future__ import annotations


class TieError(Exception):
    """Base for label / depth / tier write failures (#3957)."""

    user_message = "That change to the relationship is not possible."

    def __init__(self, message: str | None = None) -> None:
        super().__init__(message or self.user_message)
        self.user_message = message or self.user_message


class LabelAlreadyDeclaredError(TieError):
    user_message = "That label is already declared."


class LabelEndedError(TieError):
    user_message = "That label has ended."


class AwarenessBackwardError(TieError):
    user_message = "A label can be made known, never hidden again."


class SameTypeShiftError(TieError):
    user_message = "Choose a different label to change to."


class TierNotReachedError(TieError):
    user_message = "The relationship is not deep enough for the next tier."


class CapstoneEntryInvalidError(TieError):
    user_message = "Pick one of your own journal entries about them."


class AllocationTooLargeError(TieError):
    user_message = "You do not have that much AP this week."


class NotYourTieError(TieError):
    user_message = "That is not your relationship."


class RelationshipBumpError(Exception):
    """Base for ambient relationship-bump failures (#1699)."""

    user_message = "Could not record that bump."

    def __init__(self, message: str | None = None) -> None:
        super().__init__(message or self.user_message)
        self.user_message = message or self.user_message


class AlreadyAcknowledgedError(RelationshipBumpError):
    """A bump for this (relationship, interaction) pair already exists."""

    user_message = "You've already acknowledged that."
