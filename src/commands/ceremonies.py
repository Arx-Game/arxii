"""Telnet command family for ceremonies (#2289).

Thin dispatch onto the ceremony Actions — no business logic here (ADR-0001).
"""

from commands.command import ArxCommand

_OPEN_SUBVERBS = frozenset({"funeral", "blessing", "sermon"})
_SUBVERB_OFFERING = "offering"
_SUBVERB_SPEECH = "speech"
_SUBVERB_FINISH = "finish"
_SUBVERB_ABANDON = "abandon"
_SUBVERB_SHOW = "show"


class CmdCeremony(ArxCommand):
    """Conduct a ceremony — a rite bookending freeform RP.

    Usage:
        ceremony/funeral <name>[,<name2>…][=<being>]   — open a funeral for the dead
        ceremony/blessing [<name>,…][=<being>]         — open a blessing
        ceremony/sermon [<name>,…][=<being>]           — open a sermon
        ceremony/offering <item>[,<item2>…]            — sacrifice items (officiant)
        ceremony/speech <name>[=<honoree>]             — recognize a speaker (officiant)
        ceremony/finish                                — conclude and tally (officiant)
        ceremony/abandon                               — abandon unfinished (officiant/staff)
        ceremony                                       — show the rite underway here

    The rite is performed in the name of your public worship unless ``=<being>``
    names another. Space form (``ceremony funeral …``) works too.
    """

    key = "ceremony"
    aliases = ["ceremonies"]
    locks = "cmd:all()"
    help_category = "Social"
    action = None  # routed per-subverb in func()

    def func(self) -> None:
        raw = (self.args or "").strip()
        subverb = self.switches[0].lower() if self.switches else ""
        if not subverb and raw:
            parts = raw.split(maxsplit=1)
            subverb = parts[0].lower()
            raw = parts[1].strip() if len(parts) > 1 else ""
        if not subverb:
            self._show_current()
            return
        if subverb in _OPEN_SUBVERBS:
            self._dispatch_open(subverb, raw)
        elif subverb == _SUBVERB_OFFERING:
            self._dispatch_offering(raw)
        elif subverb == _SUBVERB_SPEECH:
            self._dispatch_speech(raw)
        elif subverb == _SUBVERB_FINISH:
            self._dispatch_simple(_SUBVERB_FINISH)
        elif subverb == _SUBVERB_ABANDON:
            self._dispatch_simple(_SUBVERB_ABANDON)
        elif subverb == _SUBVERB_SHOW:
            self._show_current()
        else:
            self.msg("Usage: ceremony/<funeral|blessing|sermon|offering|speech|finish|abandon>")

    @staticmethod
    def _split_names(text: str) -> list[str]:
        return [part.strip() for part in text.split(",") if part.strip()]

    def _dispatch_open(self, type_key: str, rest: str) -> None:
        from actions.definitions.ceremonies import OpenCeremonyAction  # noqa: PLC0415

        names_part, _, being_part = rest.partition("=")
        result = OpenCeremonyAction().run(
            actor=self.caller,
            type_key=type_key,
            honoree_names=self._split_names(names_part),
            being_name=being_part.strip() or None,
        )
        if result.message:
            self.msg(result.message)

    def _dispatch_offering(self, rest: str) -> None:
        from actions.definitions.ceremonies import CeremonyOfferingAction  # noqa: PLC0415

        result = CeremonyOfferingAction().run(actor=self.caller, item_names=self._split_names(rest))
        if result.message:
            self.msg(result.message)

    def _dispatch_speech(self, rest: str) -> None:
        from actions.definitions.ceremonies import CeremonySpeechAction  # noqa: PLC0415

        speaker_part, _, honoree_part = rest.partition("=")
        result = CeremonySpeechAction().run(
            actor=self.caller,
            speaker_name=speaker_part.strip(),
            honoree_name=honoree_part.strip() or None,
        )
        if result.message:
            self.msg(result.message)

    def _dispatch_simple(self, verb: str) -> None:
        from actions.definitions.ceremonies import (  # noqa: PLC0415
            AbandonCeremonyAction,
            FinishCeremonyAction,
        )

        action_cls = FinishCeremonyAction if verb == _SUBVERB_FINISH else AbandonCeremonyAction
        result = action_cls().run(actor=self.caller)
        if result.message:
            self.msg(result.message)

    def _show_current(self) -> None:
        from actions.definitions.ceremonies import _open_ceremony_here  # noqa: PLC0415

        ceremony = _open_ceremony_here(self.caller)
        if ceremony is None:
            self.msg("No ceremony is underway here.")
            return
        honorees = ", ".join(
            str(h.honoree_sheet) for h in ceremony.honorees.select_related("honoree_sheet")
        )
        lines = [
            f"{ceremony.ceremony_type.name} — in the name of {ceremony.presented_being.name}",
            f"Officiant: {ceremony.officiant}",
        ]
        if honorees:
            lines.append(f"Honoring: {honorees}")
        lines.append(f"Offerings: {ceremony.offerings.count()}")
        lines.append(f"Speeches: {ceremony.speeches.count()}")
        self.msg("\n".join(lines))
