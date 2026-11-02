"""Telnet ``vow`` command (#4929): a vow holder's focus picks.

``vow picks`` lists every pick each primary vow offers, by level, from the same
``vow_pick_catalogs`` the character sheet reads. ``vow pick <name>`` chooses one
through ``ChooseVowFocusPickAction``, the action the web dispatches. ``vow reswear
<old>=<new>`` performs the Rite of Re-swearing (#4940) through ``PerformRitualAction``,
as the sheet's Change picks dialog does. No rules live here: parse, resolve the names
the player typed to ids, call the action.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from commands.command import ArxCommand
from commands.exceptions import CommandError

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.covenants.types import VowPickCatalog, VowPickEntry, VowPickLevel

#: The word that names the covenant: ``vow pick Riposte in The Quicksilver Hall``.
_IN = "in"
_USAGE = (
    "Usage: vow picks [in <covenant>] | vow pick <name> [in <covenant>] | "
    "vow reswear <chosen pick>=<new pick> [in <covenant>]"
)
_RESWEAR_USAGE = "Usage: vow reswear <chosen pick>=<new pick> [in <covenant>]"


class CmdVow(ArxCommand):
    """See and choose your vow's focus picks.

    Usage:
        vow picks [in <covenant>]       - every pick your vow offers, by level
        vow pick <name> [in <covenant>] - choose a pick within its level's budget
        vow reswear <chosen>=<new> [in <covenant>]
                                        - the Rite of Re-swearing: give up a chosen
                                          pick for another of the same level

    A pick opens when your vow reaches its level. Budget you do not spend waits
    for a later pick. Chosen picks change only through the Rite of Re-swearing,
    which costs action points from your week and is never performed in a fight.
    """

    key = "vow"
    locks = "cmd:all()"
    help_category = "Covenants"
    action = None  # routes to the list, ChooseVowFocusPickAction and PerformRitualAction

    def func(self) -> None:
        try:
            self._dispatch()
        except CommandError as err:
            self.msg(str(err))

    def _dispatch(self) -> None:
        tokens = (self.args or "").split()
        if not tokens:
            raise CommandError(_USAGE)
        verb, words = tokens[0].lower(), tokens[1:]
        rest, covenant_name = self._parse_in_covenant(words)
        if verb == "picks":  # noqa: STRING_LITERAL
            self._list(covenant_name)
        elif verb == "pick" and words:  # noqa: STRING_LITERAL
            # "Cut in Two" is a pick's name, not "Cut" in a covenant called "Two": a trailing
            # "in <name>" names a covenant only when the caller is in one by that name.
            if covenant_name is not None and self._own_covenant_id(covenant_name) is None:
                rest, covenant_name = words, None
            if not rest:
                raise CommandError(_USAGE)
            self._choose(" ".join(rest), covenant_name)
        elif verb == "reswear":  # noqa: STRING_LITERAL
            self._reswear(words)
        else:
            raise CommandError(_USAGE)

    @staticmethod
    def _parse_in_covenant(tokens: list[str]) -> tuple[list[str], str | None]:
        """Pop a trailing ``in <covenant>`` phrase from *tokens*."""
        lower = [token.lower() for token in tokens]
        if _IN not in lower:
            return tokens, None
        index = len(lower) - 1 - lower[::-1].index(_IN)
        return tokens[:index], " ".join(tokens[index + 1 :]).strip() or None

    def _sheet(self) -> CharacterSheet:
        sheet = self.caller.character_sheet
        if sheet is None:
            msg = "You have no character sheet."
            raise CommandError(msg)
        return sheet

    def _own_covenant_id(self, covenant_name: str) -> int | None:
        """The id of the caller's active covenant named *covenant_name*, or None."""
        from world.covenants.selectors import get_active_memberships  # noqa: PLC0415

        for membership in get_active_memberships(character_sheet=self._sheet()):
            if membership.covenant.name.lower() == covenant_name.lower():
                return membership.covenant_id
        return None

    def _covenant_id(self, covenant_name: str | None) -> int | None:
        """The id of the caller's covenant named *covenant_name*, or None when not named."""
        if covenant_name is None:
            return None
        covenant_id = self._own_covenant_id(covenant_name)
        if covenant_id is None:
            msg = f"You are not a member of a covenant named '{covenant_name}'."
            raise CommandError(msg)
        return covenant_id

    def _list(self, covenant_name: str | None) -> None:
        from world.covenants.focus_picks import vow_pick_catalogs  # noqa: PLC0415

        covenant_id = self._covenant_id(covenant_name)
        catalogs = [
            catalog
            for catalog in vow_pick_catalogs(self._sheet())
            if covenant_id is None or catalog.covenant_id == covenant_id
        ]
        if not catalogs:
            self.msg("You hold no vow with focus picks.")
            return
        self.msg("\n\n".join(_render_catalog(catalog) for catalog in catalogs))

    def _choose(self, pick_name: str, covenant_name: str | None) -> None:
        from actions.definitions.covenants import ChooseVowFocusPickAction  # noqa: PLC0415

        result = ChooseVowFocusPickAction().run(
            actor=self.caller,
            pick_name=pick_name,
            covenant_id=self._covenant_id(covenant_name),
        )
        self.msg(result.message)

    def _reswear(self, words: list[str]) -> None:
        old_name, sep, new_text = " ".join(words).partition("=")
        new_words = new_text.split()
        rest, covenant_name = self._parse_in_covenant(new_words)
        # As with "vow pick": a trailing "in <name>" names a covenant only when it is one.
        if covenant_name is not None and self._own_covenant_id(covenant_name) is None:
            rest, covenant_name = new_words, None
        old_name, new_name = old_name.strip(), " ".join(rest).strip()
        if not sep or not old_name or not new_name:
            raise CommandError(_RESWEAR_USAGE)
        old_id, new_id, covenant_id = self._reswear_ids(
            old_name, new_name, self._covenant_id(covenant_name)
        )
        from actions.definitions.ritual import PerformRitualAction  # noqa: PLC0415
        from world.covenants.focus_picks import (  # noqa: PLC0415
            NO_RESWEAR_RITE_MESSAGE,
            reswear_ritual,
        )

        ritual = reswear_ritual()
        if ritual is None:
            raise CommandError(NO_RESWEAR_RITE_MESSAGE)
        carried = [
            obj.item_instance_or_none
            for obj in self.caller.contents
            if obj.item_instance_or_none is not None
        ]
        result = PerformRitualAction().run(
            actor=self.caller,
            ritual=ritual,
            components_provided=carried,
            old_pick_id=old_id,
            new_pick_id=new_id,
            covenant_id=covenant_id,
        )
        self.msg(result.message)

    def _reswear_ids(
        self, old_name: str, new_name: str, covenant_id: int | None
    ) -> tuple[int, int, int]:
        """The old pick, new pick and covenant ids, from the names typed, among own vows."""
        from world.covenants.focus_picks import vow_pick_catalogs  # noqa: PLC0415

        catalogs = [
            catalog
            for catalog in vow_pick_catalogs(self._sheet())
            if covenant_id is None or catalog.covenant_id == covenant_id
        ]
        holding = [
            (catalog, entry)
            for catalog in catalogs
            for level in catalog.levels
            for entry in level.picks
            if entry.chosen and entry.name.lower() == old_name.lower()
        ]
        if not holding:
            msg = f"You have not chosen a pick named {old_name}."
            raise CommandError(msg)
        if len({catalog.covenant_id for catalog, _ in holding}) > 1:
            names = sorted({catalog.covenant for catalog, _ in holding})
            msg = f"Which covenant? You chose {old_name} in: {', '.join(names)}."
            raise CommandError(msg)
        catalog, old = holding[0]
        taking = [
            entry
            for level in catalog.levels
            for entry in level.picks
            if entry.name.lower() == new_name.lower()
        ]
        if not taking:
            msg = f"Your vow offers no pick named {new_name}."
            raise CommandError(msg)
        if len(taking) > 1:
            msg = f"Your vow offers two picks named {new_name}; change it on your sheet."
            raise CommandError(msg)
        return old.id, taking[0].id, catalog.covenant_id


def _render_catalog(catalog: VowPickCatalog) -> str:
    lines = [f"|w{catalog.vow}|n, vow level {catalog.vow_level}."]
    grouped = len(catalog.vows) > 1
    for level in catalog.levels:
        lines.extend(_render_level(level, grouped=grouped))
    return "\n".join(lines)


def _render_level(level: VowPickLevel, *, grouped: bool) -> list[str]:
    """One budget line for the level, then its picks, under each vow's name for a sub-role."""
    if level.is_open:
        head = f"Level {level.level}: {level.spent} of {level.budget}."
    else:
        head = f"Level {level.level}: opens at vow level {level.level}."
    lines = [head]
    vow = None
    for pick in level.picks:
        if grouped and pick.vow != vow:
            vow = pick.vow
            lines.append(f" {vow}:")
        lines.append(_render_pick(pick))
    return lines


def _render_pick(pick: VowPickEntry) -> str:
    unit = "pt" if pick.price == 1 else "pts"
    mark = "|g*|n" if pick.chosen else "-"
    line = f"  {mark} {pick.name}, {pick.price} {unit}."
    if pick.chosen:
        line += " Chosen."
    elif pick.locked_reason:
        line += f" |x({pick.locked_reason})|n"
    if pick.description:
        line += f" {pick.description}"
    mechanics = " · ".join([*pick.effects, pick.limits])
    return f"{line}\n      {mechanics}"
