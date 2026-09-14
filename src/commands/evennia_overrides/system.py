"""System commands the cmdhandler invokes on its own (#3856).

Evennia's cmdhandler resolves an unmatched command name by looking up the
``CMD_NOMATCH`` system command in the current cmdset; with none, it sends its
own "Command '...' is not available." line as a plain ``text`` frame that the web
client cannot tell apart from a look result or a builder's output. This command
reproduces Evennia's wording (the near-miss suggestions included) and sends it
typed ``error``, so the client renders it as the red note the player needs
instead of silence. Telnet output is byte-identical to Evennia's default.
"""

from evennia.commands.cmdhandler import CMD_NOMATCH
from evennia.utils.utils import list_to_string, string_suggestions

from commands.command import ArxCommand

_SUGGESTION_CUTOFF = 0.7
_SUGGESTION_MAX = 3


class CmdNoMatch(ArxCommand):
    """Answer an unmatched command name with Evennia's own text, typed ``error``."""

    key = CMD_NOMATCH
    locks = "cmd:all()"

    def resolve_action_args(self) -> dict[str, object]:
        return {}

    def _execute(self) -> None:
        raw = self.args or ""
        text = f"Command '{raw}' is not available."
        suggestions: list[str] = []
        cmdset = self.cmdset
        if cmdset is not None:
            suggestions = string_suggestions(
                raw,
                cmdset.get_all_cmd_keys_and_aliases(self.caller),
                cutoff=_SUGGESTION_CUTOFF,
                maxnum=_SUGGESTION_MAX,
            )
        if suggestions:
            text += f" Maybe you meant {list_to_string(suggestions, endsep='or', addquote=True)}?"
        else:
            text += ' Type "help" for help.'
        self.msg(text, type="error")
