"""Standoff telnet command: the ``standoff <subverb>`` namespace (#4145).

Reaches the standoff registry actions through the shared ``dispatch_player_action`` seam,
the same path the web uses. Names typed by the player (group, approach, terms, drive, angle)
are looked up by ``iexact`` against rows scoped to the caller's standoff; nothing is
designated by name in code.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from actions.constants import ActionBackend
from actions.types import ActionResult
from commands.command import DispatchCommand
from commands.exceptions import CommandError

if TYPE_CHECKING:
    from collections.abc import Callable

    from actions.types import ActionRef, DispatchResult
    from world.combat.models import CombatEncounter, CombatParticipant
    from world.standoffs.models import StandoffGroup
    from world.standoffs.services.gm_view import GMGroupView, GMStandoffView
    from world.standoffs.services.view import GroupView, LeverView, StandoffView

_SUBVERBS: dict[str, str] = {
    "read": "standoff_read",
    "press": "standoff_press",
    "display": "standoff_press",
    "terms": "standoff_terms",
    "fight": "standoff_fight",
    "share": "standoff_share_angle",
}
_NOT_IN_STANDOFF = "You are not in a standoff."
_CAUSE_WORD = "cause"
# Trailing consent keyword on `standoff display`: accept the Soulfray risk, as on `cast`.
_SOULFRAY_KEYWORD = "soulfray"


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
        standoff                         - the groups here, your angles and what you can do
        standoff read <group> [cause|<drive>|<angle>] - read a group for what moves it
        standoff press <approach> <group> - press a group with an approach
        standoff display <technique> <group> [soulfray] - cast a technique as a display
                                           of power; 'soulfray' accepts the Soulfray risk
        standoff terms <terms> <group>   - name terms to a group
        standoff share <group> <angle>   - share what you feel about a group
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
                "creature_template", "persona"
            )
        )

    def _group(self, name: str) -> StandoffGroup:
        """The group a typed name picks: the whole name, else a unique prefix or whole word."""
        typed = name.lower()
        groups = self._groups()
        matches = [g for g in groups if g.name.lower() == typed]
        if not matches:
            matches = [
                g
                for g in groups
                if g.name.lower().startswith(typed) or typed in g.name.lower().split()
            ]
        if not matches:
            msg = f"No group named '{name}' in this standoff."
            raise CommandError(msg)
        if len(matches) > 1:
            listed = ", ".join(sorted({g.name for g in matches}))
            msg = f"'{name}' could mean more than one group: {listed}. Be more specific."
            raise AmbiguousNameError(msg)
        return matches[0]

    def _own_matches(self, group: StandoffGroup) -> list[Any]:
        from world.standoffs.services.faction_rules import faction_rule_matches  # noqa: PLC0415

        return faction_rule_matches(group, self.caller.sheet_data)

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
            if match.rule.angle_text.lower() == focus.lower():
                return {
                    "focus_kind": RevealKind.FACTION_RULE,
                    "focus_faction_rule_id": match.rule.pk,
                }
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

        words = text.split()
        confirm = len(words) > 1 and words[-1].lower() == _SOULFRAY_KEYWORD
        if confirm:
            text = " ".join(words[:-1])
        technique, group = self._split(text, self._technique, self._group)
        approach = StandoffApproach.objects.filter(casts_technique=True).order_by("pk").first()
        if approach is None:
            msg = "There is no display of power available here."
            raise CommandError(msg)
        kwargs: dict[str, Any] = {
            "group_id": group.pk,
            "approach_id": approach.pk,
            "technique_id": technique.pk,
        }
        if confirm:
            kwargs["confirm_soulfray_risk"] = True
        return kwargs

    def _report_dispatch_result(self, result: DispatchResult) -> None:
        """The action's message; a display stopped at Soulfray also says how to accept."""
        super()._report_dispatch_result(result)
        detail = result.detail
        if isinstance(detail, ActionResult) and detail.data.get("soulfray_warning"):
            self.msg(
                f"Type |wstandoff display {self._rest} {_SOULFRAY_KEYWORD}|n to accept the risk."
            )

    def _terms_args(self, text: str) -> dict[str, Any]:
        terms, group = self._split(text, self._terms, self._group)
        return {"group_id": group.pk, "terms_id": terms.pk}

    def _share_args(self, text: str) -> dict[str, Any]:
        def angle_for(group: StandoffGroup) -> Callable[[str], Any]:
            def find(name: str) -> Any:
                for match in self._own_matches(group):
                    if match.rule.angle_text.lower() == name.lower():
                        return match.rule
                msg = f"You have no angle '{name}'."
                raise CommandError(msg)

            return find

        for lead, tail in _name_splits(text):
            try:
                group = self._group(lead)
                return {"group_id": group.pk, "faction_rule_id": angle_for(group)(tail).pk}
            except AmbiguousNameError:
                raise
            except CommandError:
                continue
        msg = "Usage: standoff share <group> <angle>."
        raise CommandError(msg)

    # -- summary ---------------------------------------------------------------

    def _show_summary(self) -> None:
        """Print the standoff as the caller may see it: as a participant, a GM or an onlooker.

        A participant gets their own view. Anyone else in a room whose encounter is in its
        standoff gets the GM view when they GM that scene (or are staff), else the public
        summary (#4354).
        """
        from actions.definitions.standoff import _standoff_participant  # noqa: PLC0415
        from world.standoffs.services.view import build_standoff_view  # noqa: PLC0415

        participant = _standoff_participant(self.caller)
        if participant is not None:
            view = build_standoff_view(participant.encounter, participant.character_sheet)
            if view is not None:
                self.msg("\n".join(_render_view(view)))
                return
        encounter = _room_standoff_encounter(self.caller)
        if encounter is None:
            self.msg(_NOT_IN_STANDOFF)
            return
        self.msg("\n".join(_render_outside_view(self.caller, encounter)))


def _room_standoff_encounter(caller: Any) -> CombatEncounter | None:
    """The newest encounter in the caller's room that is in its standoff, if any."""
    from world.combat.models import CombatEncounter  # noqa: PLC0415
    from world.standoffs.services.state import is_in_standoff  # noqa: PLC0415

    room = caller.location
    if room is None:
        return None
    candidates = CombatEncounter.objects.filter(room=room, round_number=0).order_by("-created_at")
    return next((e for e in candidates if is_in_standoff(e)), None)


def _render_outside_view(caller: Any, encounter: CombatEncounter) -> list[str]:
    """The GM view for a scene GM or staff; the public summary for anyone else."""
    from commands.utils.gm_resolution import resolve_account_or_none  # noqa: PLC0415
    from world.standoffs.services.gm_view import (  # noqa: PLC0415
        build_gm_standoff_view,
        build_standoff_summary,
    )

    # A puppeting session sets ``account``; a character played off a tenure resolves
    # through ``active_account``.
    account = caller.account or resolve_account_or_none(caller)
    is_gm = account is not None and (
        account.is_staff or (encounter.scene is not None and encounter.scene.is_gm(account))
    )
    if is_gm:
        gm_view = build_gm_standoff_view(encounter)
        if gm_view is not None:
            return _render_gm_view(gm_view)
    summary = build_standoff_summary(encounter)
    if summary is None:
        return [_NOT_IN_STANDOFF]
    lines = [f"Standoff at {summary.place}:" if summary.place else "Standoff:"]
    lines.extend(
        f"  {group.name} ({group.member_count}) - "
        + _state_words(group.state, group.morale_state, emboldened=group.emboldened)
        for group in summary.groups
    )
    if summary.participants:
        lines.append(f"In the standoff: {', '.join(summary.participants)}.")
    return lines


def _gm_profile_lines(group: GMGroupView) -> list[str]:
    """A group's cause, affiliation and drives for the GM, with what the placement edited."""
    status = f"fires: {group.cause_reason}" if group.cause_fires else "holds"
    edited = " - edited here" if group.cause_edited else ""
    lines = [f"    Cause: {group.cause} ({status}){edited}"]
    if group.cause_clock:
        lines.append(f"    {group.cause_clock}")
    if group.affiliation:
        set_here = " - set on this line" if group.affiliation_edited else ""
        lines.append(f"    Affiliation: {group.affiliation}{set_here}")
    if group.pending_prompt_id is not None:
        lines.append(
            f"    Proposal [{group.pending_prompt_id}]: {group.proposal_reason} "
            f"(gm prompt confirm, hold or override {group.pending_prompt_id})"
        )
    lines.extend(
        f"    Drive: {drive.label} ({drive.strength})"
        f"{' - edited here' if drive.edited else ''}{' - read' if drive.revealed else ''}"
        for drive in group.drives
    )
    lines.append(f"    Speaks: {', '.join(group.speaks) or 'no language'}")
    lines.extend(
        f"    Their regard: {regard.participant} {regard.label} ({regard.regard})"
        for regard in group.regards
    )
    return lines


def _render_gm_group(group: GMGroupView) -> list[str]:
    """One group of the GM's view, as plain text."""
    named = " - named NPC" if group.is_named_npc else ""
    lines = [
        f"  [{group.group_id}] {group.name} ({group.member_count}){named} - "
        + _state_words(group.state, group.morale_state, emboldened=group.emboldened_bands > 0),
        *_gm_profile_lines(group),
    ]
    lines.extend(
        f"    Faction rule: {rule.label} (from {rule.source}){_effect_words(rule.cause_effect)}"
        f" - matches {', '.join(rule.matched_by) or 'nobody'}{' - read' if rule.revealed else ''}"
        for rule in group.faction_rules
    )
    lines.append(
        f"    Force: party {group.effective_party_force}, them {group.group_force} "
        f"(margin {group.cause_margin_percent}%)"
    )
    lines.append(
        "    Morale: " + ", ".join(f"{m.name} {m.morale} ({m.morale_state})" for m in group.members)
    )
    return lines


def _effect_words(cause_effect: str) -> str:
    """The words beside a faction rule that provokes the group or keeps it back."""
    from world.standoffs.constants import CauseEffect  # noqa: PLC0415

    if cause_effect == CauseEffect.PROVOKE:
        return " - provokes them"
    if cause_effect == CauseEffect.SUPPRESS:
        return " - keeps them back"
    return ""


def _render_gm_view(view: GMStandoffView) -> list[str]:
    """The GM's whole view of a standoff, as plain text."""
    lines = [f"Standoff at {view.place} (GM):" if view.place else "Standoff (GM):"]
    for group in view.groups:
        lines.extend(_render_gm_group(group))
    # No pipe characters: on telnet "|" starts a colour code.
    lines.append("GM: gm standoff shake <group id> <reason> (or steady)")
    return lines


def _state_words(state: str, morale_state: str, *, emboldened: bool) -> str:
    """A group's state for a reader: PROPOSED reads as open plus deciding."""
    from world.combat.morale import OpponentMoraleState  # noqa: PLC0415
    from world.standoffs.constants import StandoffGroupState  # noqa: PLC0415

    deciding = state == StandoffGroupState.PROPOSED
    words = [StandoffGroupState.OPEN.label if deciding else StandoffGroupState(state).label]
    if emboldened:
        words.append("emboldened")
    if morale_state == OpponentMoraleState.FALTER:
        words.append("faltering")
    elif morale_state == OpponentMoraleState.BREAK:
        words.append("broken")
    if deciding:
        words.append("deciding")
    return ", ".join(words)


def _render_view(view: StandoffView) -> list[str]:
    """Text lines for a ``StandoffView``: the web payload's content, as plain text."""
    lines = [f"Standoff at {view.place}:" if view.place else "Standoff:"]
    for group in view.groups:
        lines.extend(_render_group(view, group))
    lines.append(f"You can: {', '.join(_SUBVERBS)}.")
    return lines


def _render_group(view: StandoffView, group: GroupView) -> list[str]:
    """Render one group's visible lines in the summary."""
    lines = [
        f"  {group.name} ({group.member_count}) - "
        + _state_words(group.state, group.morale_state, emboldened=group.emboldened)
    ]
    if group.read_grade_label:
        lines.append(f"    read ({group.read_check}): {group.read_grade_label}")
    if group.hidden_count:
        lines.append(f"    There is more to read here ({group.hidden_count} unread).")
    if group.cause is not None:
        gloss = f" {group.cause_gloss}" if group.cause_gloss else ""
        lines.append(f"    Cause: {group.cause}.{gloss}")
    lines.extend(f"    Drive: {drive.label} ({drive.strength})." for drive in group.drives)
    lines.extend(f"    {line}" for line in group.revealed_faction_rules)
    lines.extend(
        f"    You feel: {angle.text}{' (shared)' if angle.shared else ''}"
        for angle in view.angles
        if angle.group_id == group.group_id and angle.text
    )
    lines.extend(
        f"    Shared: {angle.text}"
        for angle in view.shared_angles
        if angle.group_id == group.group_id and angle.text
    )
    lines.extend(
        f"    press {approach.name}: {approach.grade_label}"
        + _lever_suffix(approach.levers)
        + _refusal_suffix(approach.refusal)
        for approach in view.approaches
        if approach.group_id == group.group_id
    )
    lines.extend(
        f"    terms {terms.name}: {terms.grade_label}"
        + (f" (on a critical: {terms.critical_label})" if terms.critical_label else "")
        + _lever_suffix(terms.levers)
        + _refusal_suffix(terms.refusal)
        for terms in view.terms
        if terms.group_id == group.group_id
    )
    return lines


def _refusal_suffix(refusal: str) -> str:
    """A language-gated entry is listed with why it is closed (#4373)."""
    return f" - refused: {refusal}" if refusal else ""
