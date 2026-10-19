"""Reading action kwargs that arrive in more than one shape.

Telnet passes strings and the web dispatcher may pass JSON booleans, so a yes/no
kwarg is read the same way by every action that takes one.
"""

from __future__ import annotations

from typing import Any

# The spellings of "yes" a typed or web caller may send.
TRUTHY_KWARG_VALUES = frozenset({"yes", "y", "true", "1"})


def truthy_kwarg(value: Any) -> bool:
    """Whether a yes/no kwarg says yes: a bool as it is, else one of the yes spellings."""
    if isinstance(value, bool):
        return value
    return value is not None and str(value).strip().lower() in TRUTHY_KWARG_VALUES
