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
    from world.standoffs.services.view import LeverView, StandoffView

_SUBVERBS: dict[str, str] = {
    "read": "standoff_read",
    "press": "standoff_press",
    "display": "standoff_press",
    "terms": "standoff_terms",
    "fight": "standoff_fight",
    "share": "standoff_share_spark",
}
_NOT_IN_STANDOFF = "You are not in a standoff."
_CAUSE_WORD = "cause"


def _lever_suffix(levers: list[LeverView]) -> str:
    return f" ({'; '.join(lever.text for lever in levers)})" if levers else ""


class AmbiguousNameError(CommandError):
    """A typed name matched several rows; the message lists them."""


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
        standoff display <technique> <group> - cast a technique as a display of power
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
        if self._subverb == "display":  # noqa: STRING_LITERAL
            return self._display_args(text)
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
        """The group a typed name picks: the whole name, else a unique prefix or whole word."""
        typed = name.lower()
        groups = self._groups()
        matches = [g for g in groups if g.creature_template.name.lower() == typed]
        if not matches:
            matches = [
                g
                for g in groups
                if g.creature_template.name.lower().startswith(typed)
                or typed in g.creature_template.name.lower().split()
            ]
        if not matches:
            msg = f"No group named '{name}' in this standoff."
            raise CommandError(msg)
        if len(matches) > 1:
            listed = ", ".join(sorted({g.creature_template.name for g in matches}))
            msg = f"'{name}' could mean more than one group: {listed}. Be more specific."
            raise AmbiguousNameError(msg)
        return matches[0]

    def _own_matches(self, group: StandoffGroup) -> list[Any]:
        from world.standoffs.services.regard import regard_matches  # noqa: PLC0415

        return regard_matches(group, self.caller.sheet_data)

    def _split(self, text: str, first: Callable[[str], Any], second: Callable[[str], Any]) -> Any:
        """Resolve ``<first> <second>`` where either may be several words."""
        for lead, tail in _name_splits(text):
            try:
                return first(lead), second(tail)
            except AmbiguousNameError:
                raise
            except CommandError:
                continue
        msg = f"Could not tell what '{text}' names. Usage: standoff {self._subverb} ..."
        raise CommandError(msg)

    # -- argument parsing ------------------------------------------------------

    def _read_args(self, text: str) -> dict[str, Any]:
        try:
            return {"group_id": self._group(text).pk}
        except AmbiguousNameError:
            raise
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

    def _technique(self, name: str) -> Any:
        from world.magic.services.ultimates import castable_technique_named  # noqa: PLC0415

        technique = castable_technique_named(self._participant().character_sheet, name)
        if technique is None:
            msg = f"You do not know a technique named '{name}'."
            raise CommandError(msg)
        return technique

    def _display_args(self, text: str) -> dict[str, Any]:
        from world.standoffs.models import StandoffApproach  # noqa: PLC0415

        technique, group = self._split(text, self._technique, self._group)
        approach = StandoffApproach.objects.filter(casts_technique=True).order_by("pk").first()
        if approach is None:
            msg = "There is no display of power available here."
            raise CommandError(msg)
        return {"group_id": group.pk, "approach_id": approach.pk, "technique_id": technique.pk}

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
            except AmbiguousNameError:
                raise
            except CommandError:
                continue
        msg = "Usage: standoff share <group> <spark>."
        raise CommandError(msg)

    # -- summary ---------------------------------------------------------------

    def _show_summary(self) -> None:
        """Print the standoff as the caller may see it, from the shared view builder."""
        from actions.definitions.standoff import _standoff_participant  # noqa: PLC0415
        from world.standoffs.services.view import build_standoff_view  # noqa: PLC0415

        participant = _standoff_participant(self.caller)
        view = (
            None
            if participant is None
            else build_standoff_view(participant.encounter, participant.character_sheet)
        )
        if view is None:
            self.msg(_NOT_IN_STANDOFF)
            return
        self.msg("\n".join(_render_view(view)))


def _render_view(view: StandoffView) -> list[str]:
    """Text lines for a ``StandoffView``: the web payload's content, as plain text."""
    from world.standoffs.constants import StandoffGroupState  # noqa: PLC0415

    lines = [f"Standoff at {view.place}:" if view.place else "Standoff:"]
    for group in view.groups:
        lines.append(
            f"  {group.name} ({group.member_count}) - {StandoffGroupState(group.state).label}"
        )
        if group.read_grade_label:
            lines.append(f"    read ({group.read_check}): {group.read_grade_label}")
        if group.hidden_count:
            lines.append(f"    There is more to read here ({group.hidden_count} unread).")
        if group.cause is not None:
            gloss = f" {group.cause_gloss}" if group.cause_gloss else ""
            lines.append(f"    Cause: {group.cause}.{gloss}")
        lines.extend(f"    Drive: {drive.label} ({drive.strength})." for drive in group.drives)
        lines.extend(f"    {line}" for line in group.revealed_regard)
        lines.extend(
            f"    You feel: {spark.text}{' (shared)' if spark.shared else ''}"
            for spark in view.sparks
            if spark.group_id == group.group_id and spark.text
        )
        lines.extend(
            f"    Shared: {spark.text}"
            for spark in view.shared_sparks
            if spark.group_id == group.group_id and spark.text
        )
        lines.extend(
            f"    press {approach.name}: {approach.grade_label}" + _lever_suffix(approach.levers)
            for approach in view.approaches
            if approach.group_id == group.group_id
        )
        lines.extend(
            f"    terms {terms.name}: {terms.grade_label}"
            + (f" (on a critical: {terms.critical_label})" if terms.critical_label else "")
            for terms in view.terms
            if terms.group_id == group.group_id
        )
    lines.append(f"You can: {', '.join(_SUBVERBS)}.")
    return lines
