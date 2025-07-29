from commands.command import ArxCommand
from commands.dispatchers import TargetDispatcher
from commands.exceptions import CommandError
from commands.handlers.base import BaseHandler


class LockDispatcher(TargetDispatcher):
    """Resolve an exit target and a key object."""

    def get_additional_kwargs(self):
        match = self.pattern.match(self._input_string())
        if not match:
            raise CommandError("Invalid syntax.")
        exit_obj = self._get_target(match)
        key_name = match.group("key")
        key_obj = self.command.caller.search(key_name)
        if not key_obj:
            raise CommandError(f"Could not find target '{key_name}'.")
        return {"target": exit_obj, "key": key_obj}


class CmdLock(ArxCommand):
    """Lock an exit with a key."""

    key = "lock"
    locks = "cmd:all()"
    dispatchers = [
        LockDispatcher(
            r"^(?P<target>.+?)\s+with\s+(?P<key>.+)$",
            BaseHandler(flow_name="lock_exit"),
        )
    ]


class CmdUnlock(ArxCommand):
    """Unlock an exit with a key."""

    key = "unlock"
    locks = "cmd:all()"
    dispatchers = [
        LockDispatcher(
            r"^(?P<target>.+?)\s+with\s+(?P<key>.+)$",
            BaseHandler(flow_name="unlock_exit"),
        )
    ]
