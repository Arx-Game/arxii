"""Telnet faces of prayer and the GM-sent vision (#3779).

Thin: parsing only, every rule lives in the actions.
"""

from commands.command import ArxCommand

_SWITCH_REVEAL = "reveal"
_SWITCH_PRAYER = "prayer"


class CmdPray(ArxCommand):
    """Pray to a being in your own words.

    Usage:
        pray <being>=<your words>

    A prayer is a message, not a mechanic: staff read them, and a god may
    answer one with a vision. Praying at a shrine or temple of the being once a
    week counts as an act of devotion; praying in dire straits may be answered
    at once.
    """

    key = "pray"
    locks = "cmd:all()"
    help_category = "Social"
    action = None

    def func(self) -> None:
        from actions.definitions.worship import PrayAction  # noqa: PLC0415

        raw = (self.args or "").strip()
        if "=" not in raw:
            self.msg("Usage: pray <being>=<your words>")
            return
        being_name, text = (part.strip() for part in raw.split("=", 1))
        if not being_name or not text:
            self.msg("Usage: pray <being>=<your words>")
            return
        result = PrayAction().run(actor=self.caller, being_name=being_name, text=text)
        if result.message:
            self.msg(result.message)


class CmdVision(ArxCommand):
    """Send a character a vision from a being (staff).

    Usage:
        vision[/reveal] <character>/<being>=<prose>
        vision/prayer <id> <character>/<being>=<prose>

    /reveal tells the recipient which being sent it. /prayer <id> marks the
    prayer this answers. A Codex clue or an episode is attached from the web
    dialog; the telnet face carries only the prose.
    """

    key = "vision"
    locks = "cmd:perm(Admin)"
    help_category = "GM"
    action = None

    def func(self) -> None:
        from actions.definitions.worship import SendVisionAction  # noqa: PLC0415

        raw = (self.args or "").strip()
        switches = {switch.lower() for switch in self.switches}
        prayer_id: int | None = None
        if _SWITCH_PRAYER in switches:
            head, _, raw = raw.partition(" ")
            try:
                prayer_id = int(head)
            except ValueError:
                self.msg("Usage: vision/prayer <id> <character>/<being>=<prose>")
                return
            raw = raw.strip()
        if "=" not in raw or "/" not in raw.split("=", 1)[0]:
            self.msg("Usage: vision[/reveal] <character>/<being>=<prose>")
            return
        target, body = (part.strip() for part in raw.split("=", 1))
        recipient_name, being_name = (part.strip() for part in target.split("/", 1))
        result = SendVisionAction().run(
            actor=self.caller,
            account=self.account,
            recipient_name=recipient_name,
            being_name=being_name,
            body=body,
            reveal_source=_SWITCH_REVEAL in switches,
            prayer=prayer_id,
        )
        if result.message:
            self.msg(result.message)
