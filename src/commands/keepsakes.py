"""Telnet face of keepsakes (#4530): parsing only, every rule lives in the actions."""

from __future__ import annotations

from typing import TYPE_CHECKING

from commands.command import ArxCommand

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet

_SWITCH_RELEASE = "release"
_SWITCH_SHOW = "show"
_SWITCH_TREASURED = "treasured"
_KINDS = ("tie", "deed", "being", "organization", "person", "place")


class CmdKeepsake(ArxCommand):
    """Keep an item you hold as a keepsake: it stands for something in your life.

    Usage:
        keepsake                                        - your keepsakes
        keepsake[/show][/treasured] <item> = <kind> <subject> ; <your words>
        keepsake/release <item>                         - stop keeping it

    <kind> is one of: tie, deed, being, organization, person, place. <subject> is the
    other character a tie is with, the deed's title, the being, organization or person, or
    the place's name. Your words are one to three sentences, in your own voice; the game
    never scores them, only what the keepsake stands for. /show lets examine show your
    words; /treasured also marks the item treasured, so staff ask you before it is put at
    stake. A keepsake counts after a short wait from the day you keep it, and you can keep
    only a few at a time.
    """

    key = "keepsake"
    takes_switches = True
    locks = "cmd:all()"
    help_category = "Items"
    action = None

    def func(self) -> None:
        from actions.definitions.keepsakes import (  # noqa: PLC0415
            DeclareKeepsakeAction,
            ReleaseKeepsakeAction,
        )

        sheet = self.caller.character_sheet
        if sheet is None:
            self.msg("You have no character sheet.")
            return
        switches = {switch.lower() for switch in self.switches}
        raw = (self.args or "").strip()
        if _SWITCH_RELEASE in switches:
            result = ReleaseKeepsakeAction().run(actor=self.caller, item_name=raw)
            self.msg(result.message)
            return
        if not raw:
            self.msg(_render_keepsakes(sheet))
            return
        item_name, _, rest = raw.partition("=")
        kind, _, remainder = rest.strip().partition(" ")
        subject, _, words = remainder.partition(";")
        if not item_name.strip() or kind.lower() not in _KINDS or not words.strip():
            self.msg(
                "Usage: keepsake <item> = <kind> <subject> ; <your words> "
                f"(kind: {', '.join(_KINDS)})"
            )
            return
        result = DeclareKeepsakeAction().run(
            actor=self.caller,
            item_name=item_name.strip(),
            subject_kind=kind.lower(),
            subject_name=subject.strip(),
            text=words.strip(),
            shown_on_examine=_SWITCH_SHOW in switches,
            treasured=_SWITCH_TREASURED in switches,
        )
        self.msg(result.message)


def _render_keepsakes(sheet: CharacterSheet) -> str:
    """The character's keepsakes: what each stands for, whether it counts yet, and the slots
    in use. Never what the words are worth: nothing scores them."""
    from django.utils import timezone  # noqa: PLC0415

    from world.items.services.keepsakes import keepsake_status, live_keepsakes  # noqa: PLC0415

    status = keepsake_status(sheet)
    rows = list(live_keepsakes(sheet))
    if not rows:
        return (
            f"You keep no keepsakes ({status.used} of {status.limit} kept). "
            "'keepsake <item> = <kind> <subject> ; <your words>' keeps one."
        )
    lines = [f"|wKeepsakes|n ({status.used} of {status.limit} kept)"]
    for row in rows:
        waited = (timezone.now() - row.created_at).days
        counts = (
            "counts now"
            if waited >= status.wait_days
            else f"counts in {status.wait_days - waited} days"
        )
        shown = ", shown on examine" if row.shown_on_examine else ""
        lines.append(f"  {row.item_instance}: stands for {row.subject_name} ({counts}{shown})")
    return "\n".join(lines)
