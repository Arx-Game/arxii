"""Typed exceptions for the vitals survivability pipeline.

Mirrors world.conditions.exceptions' shape: exceptions carry a user_message
attribute so callers can surface a safe, human-readable message without
str(exc) pitfalls.
"""


class NotAWoundError(Exception):
    """Raised by mend_wound() when the ConditionInstance has no WoundDetails.

    mend_wound() is a bounded-healing seam over an authored wound, not a
    general condition-severity API — calling it on a plain (non-wound)
    condition instance is a caller bug, not a recoverable game state.
    """

    user_message = "That condition isn't a mendable wound."
