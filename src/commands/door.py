"""Door-related commands.

Lock and unlock actions are not yet implemented in the action layer.
These commands are stubs that will be wired up when LockAction and
UnlockAction are created.
"""

from __future__ import annotations

from commands.command import ArxCommand


class CmdLock(ArxCommand):
    """Lock an exit with a key."""

    key = "lock"
    locks = "cmd:all()"
    # TODO: wire to LockAction when created


class CmdUnlock(ArxCommand):
    """Unlock an exit with a key."""

    key = "unlock"
    locks = "cmd:all()"
    # TODO: wire to UnlockAction when created
