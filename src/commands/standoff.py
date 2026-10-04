"""Standoff telnet command: the ``standoff <subverb>`` namespace (#4145).

Reaches the standoff registry actions through the shared ``dispatch_player_action`` seam,
the same path the web uses. Names typed by the player (group, approach, terms, drive, spark)
are looked up by ``iexact`` against rows scoped to the caller's standoff; nothing is
designated by name in code.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from actions.constants import ActionBackend
from commands.command import DispatchCommand
from commands.exceptions import CommandError

if TYPE_CHECKING:
    from collections.abc import Callable

    from actions.types import ActionRef
    from world.combat.models import CombatParticipant
    from world.standoffs.models import StandoffGroup

_SUBVERBS: dict[str, str] = {
    "read": "standoff_read",
    "press": "standoff_press",
    "terms": "standoff_terms",
    "fight": "standoff_fight",
    "share": "standoff_share_spark",
}
_NOT_IN_STANDOFF = "You are not in a standoff."
_CAUSE_WORD = "cause"


def _name_splits(text: str) -> list[tuple[str, str]]:
    """Every way to cut ``text`` into a leading and trailing name, longest lead first."""
    words = text.split()
    return [(" ".join(words[:i]), " ".join(words[i:])) for i in range(len(words) - 1, 0, -1)]


class CmdStandoff(DispatchCommand):
    """Act in a standoff before a fight begins.

    Usage:
        standoff                         - the groups here, your sparks and what you can do
        standoff read <group> [cause|<drive>|<spark>] - read a group for what moves it
        standoff press <approach> <group> - press a group with an approach
        standoff terms <terms> <group>   - name terms to a group
        standoff share <group> <spark>   - share what you feel about a group
        standoff fight                   - break the standoff and begin the fight
    """

    key = "standoff"
    locks = "cmd:all()"

    _subverb: str = ""
    _rest: str = ""

    def func(self) -> None:
        """Route the leading subverb; bare ``standoff`` prints the summary."""
        raw = (self.args or "").strip()
        if not raw:
            self._show_summary()
            return
        parts = raw.split(maxsplit=1)
        self._subverb = parts[0].lower()
        self._rest = parts[1].strip() if len(parts) > 1 else ""
        if self._subverb not in _SUBVERBS:
            self.msg(f"Unknown standoff action '{self._subverb}'. Try: {', '.join(_SUBVERBS)}.")
            return
        super().func()

    def resolve_action_ref(self) -> ActionRef:
        """Build a REGISTRY ActionRef for the parsed subverb."""
        from actions.types import ActionRef  # noqa: PLC0415

        return ActionRef(backend=ActionBackend.REGISTRY, registry_key=_SUBVERBS[self._subverb])

    def resolve_action_args(self) -> dict[str, Any]:
        """Resolve the typed names into dispatch kwargs."""
        if self._subverb == "fight":  # noqa: STRING_LITERAL
            return {}
        text = self._require_rest()
        if self._subverb == "read":  # noqa: STRING_LITERAL
            return self._read_args(text)
        if self._subverb == "press":  # noqa: STRING_LITERAL
            return self._press_args(text)
        if self._subverb == "terms":  # noqa: STRING_LITERAL
            return self._terms_args(text)
        return self._share_args(text)

    # -- lookups ---------------------------------------------------------------

    def _require_rest(self) -> str:
        if not self._rest:
            msg = f"Usage: standoff {self._subverb} ... (see 'help standoff')."
            raise CommandError(msg)
        return self._rest

    def _participant(self) -> CombatParticipant:
        from actions.definitions.standoff import _standoff_participant  # noqa: PLC0415

        participant = _standoff_participant(self.caller)
        if participant is None:
            raise CommandError(_NOT_IN_STANDOFF)
        return participant

    def _groups(self) -> list[StandoffGroup]:
        from world.standoffs.models import StandoffGroup  # noqa: PLC0415

        return list(
            StandoffGroup.objects.filter(encounter=self._participant().encounter).select_related(
                "creature_template"
            )
        )

    def _group(self, name: str) -> StandoffGroup:
        matches = [g for g in self._groups() if g.creature_template.name.lower() == name.lower()]
        if not matches:
            msg = f"No group named '{name}' in this standoff."
            raise CommandError(msg)
        if len(matches) > 1:
            msg = f"More than one group named '{name}' - be more specific."
            raise CommandError(msg)
        return matches[0]

    def _own_matches(self, group: StandoffGroup) -> list[Any]:
        from world.standoffs.services.regard import regard_matches  # noqa: PLC0415

        return regard_matches(group, self.caller.sheet_data)

    def _split(self, text: str, first: Callable[[str], Any], second: Callable[[str], Any]) -> Any:
        """Resolve ``<first> <second>`` where either may be several words."""
        for lead, tail in _name_splits(text):
            try:
                return first(lead), second(tail)
            except CommandError:
                continue
        msg = f"Could not tell what '{text}' names. Usage: standoff {self._subverb} ..."
        raise CommandError(msg)

    # -- argument parsing ------------------------------------------------------

    def _read_args(self, text: str) -> dict[str, Any]:
        try:
            return {"group_id": self._group(text).pk}
        except CommandError:
            pass
        group, focus = self._split(text, self._group, lambda focus: focus)
        kwargs: dict[str, Any] = {"group_id": group.pk}
        kwargs.update(self._focus(group, focus))
        return kwargs

    def _focus(self, group: StandoffGroup, focus: str) -> dict[str, Any]:
        """The focus a typed word names; a word that names nothing is an unfocused read.

        Drive words resolve against the whole Property catalog, never this group's drives,
        so a guess cannot show whether the group has that drive.
        """
        from world.mechanics.models import Property  # noqa: PLC0415
        from world.standoffs.constants import RevealKind  # noqa: PLC0415

        if focus.lower() == _CAUSE_WORD:
            return {"focus_kind": RevealKind.CAUSE}
        for match in self._own_matches(group):
            if match.rule.spark_text.lower() == focus.lower():
                return {"focus_kind": RevealKind.REGARD, "focus_regard_rule_id": match.rule.pk}
        prop = Property.objects.filter(name__iexact=focus).first()
        if prop is not None:
            return {"focus_kind": RevealKind.DRIVE, "focus_property_id": prop.pk}
        return {}

    def _approach(self, name: str) -> Any:
        from world.standoffs.models import StandoffApproach  # noqa: PLC0415

        approach = StandoffApproach.objects.filter(name__iexact=name).first()
        if approach is None:
            msg = f"No approach named '{name}'."
            raise CommandError(msg)
        return approach

    def _terms(self, name: str) -> Any:
        from world.standoffs.models import StandoffTerms  # noqa: PLC0415

        terms = StandoffTerms.objects.filter(name__iexact=name).first()
        if terms is None:
            msg = f"No terms named '{name}'."
            raise CommandError(msg)
        return terms

    def _press_args(self, text: str) -> dict[str, Any]:
        approach, group = self._split(text, self._approach, self._group)
        return {"group_id": group.pk, "approach_id": approach.pk}

    def _terms_args(self, text: str) -> dict[str, Any]:
        terms, group = self._split(text, self._terms, self._group)
        return {"group_id": group.pk, "terms_id": terms.pk}

    def _share_args(self, text: str) -> dict[str, Any]:
        def spark_for(group: StandoffGroup) -> Callable[[str], Any]:
            def find(name: str) -> Any:
                for match in self._own_matches(group):
                    if match.rule.spark_text.lower() == name.lower():
                        return match.rule
                msg = f"You have no spark '{name}'."
                raise CommandError(msg)

            return find

        for lead, tail in _name_splits(text):
            try:
                group = self._group(lead)
                return {"group_id": group.pk, "regard_rule_id": spark_for(group)(tail).pk}
            except CommandError:
                continue
        msg = "Usage: standoff share <group> <spark>."
        raise CommandError(msg)

    # -- summary ---------------------------------------------------------------

    def _show_summary(self) -> None:
        """Print the groups, the viewer's own sparks and the verbs. Nothing unrevealed."""
        from actions.definitions.standoff import _standoff_participant  # noqa: PLC0415
        from world.standoffs.services.describe import describe_reveals  # noqa: PLC0415
        from world.standoffs.services.state import active_members  # noqa: PLC0415

        participant = _standoff_participant(self.caller)
        if participant is None:
            self.msg(_NOT_IN_STANDOFF)
            return
        lines = ["Standoff:"]
        for group in self._groups():
            count = len(active_members(group))
            lines.append(
                f"  {group.creature_template.name} ({count}) - {group.get_state_display()}"
            )
            lines.extend(
                f"    You feel: {match.rule.spark_text}"
                for match in self._own_matches(group)
                if match.rule.spark_text
            )
            lines.extend(
                f"    {line}"
                for line in describe_reveals(
                    group,
                    group.reveals.select_related("drive__property", "regard_rule"),
                    self.caller.sheet_data,
                )
            )
        lines.append(f"You can: {', '.join(_SUBVERBS)}.")
        self.msg("\n".join(lines))
