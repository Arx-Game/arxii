"""Tie telnet command — the ``relationship <subverb>`` namespace (#3957 / #1485 / #1537).

A single command routes the tie-building verbs through ``action.run()`` — the same
seam the web tie panel uses — plus the telnet-only ``list`` / ``show`` read surfaces
and the ambient ``plus`` / ``neg`` bumps (#1699).

Write verbs (reach the Actions in ``actions/definitions/relationships.py``):

- ``relationship declare <name>=<type>[,private|clandestine|public]`` → ``DeclareLabelAction``
- ``relationship shift <name>=<from>,<to>[,note]`` → ``ShiftLabelAction``
- ``relationship end <name>=<type>`` → ``EndLabelAction``
- ``relationship reveal <name>=<type>,<clandestine|public>`` → ``AdvanceLabelAwarenessAction``
- ``relationship ap <name>=<n>`` → ``SetTieAllocationAction``
- ``relationship advance <name>=<journal entry id>`` → ``AdvanceRelationshipTierAction``
- ``relationship summary <name>=<text>`` → ``SetTieSummaryAction``
- ``relationship plus|neg <name>`` → ``RelationshipBumpAction``

The verbs live under the ``relationship`` namespace rather than as bare top-level
keys to avoid exit/channel/alias collisions — mirrors ``CmdRitual`` / ``CmdDuel``
subverb routing.

No consent gate: these describe the caller's own side of a tie, they do not compel
or provoke the target's behavior (ADR-0024).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from commands.command import ArxCommand
from commands.exceptions import CommandError

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.companions.models import Companion
    from world.relationships.models import (
        CharacterRelationship,
        RelationshipLabel,
        RelationshipType,
    )

# Subverbs.
_SUBVERB_LIST = "list"
_SUBVERB_SHOW = "show"
_SUBVERB_PLUS = "plus"
_SUBVERB_NEG = "neg"
_SUBVERB_DECLARE = "declare"
_SUBVERB_SHIFT = "shift"
_SUBVERB_END = "end"
_SUBVERB_REVEAL = "reveal"
_SUBVERB_AP = "ap"
_SUBVERB_ADVANCE = "advance"
_SUBVERB_SUMMARY = "summary"
_BUMP_SUBVERBS = frozenset({_SUBVERB_PLUS, _SUBVERB_NEG})

#: A label-row reference (``shift``'s ``<from>,<to>``, ``reveal``'s ``<type>,<awareness>``)
#: is at least a type token and a second token — the split-comma count checked below.
_MIN_LABEL_REF_PARTS = 2


def _active_companion_of(obj: Any) -> Companion | None:
    """The unreleased Companion whose live object is ``obj``, else None (#3575)."""
    return obj.companion_rows.filter(released_at__isnull=True).first()


def _require_int(value: str | None, name: str) -> int:
    """Return *value* as an int, or raise CommandError."""
    if value is None or value == "":
        msg = f"{name} is required."
        raise CommandError(msg)
    try:
        return int(value)
    except ValueError as exc:
        msg = f"{name} must be a number."
        raise CommandError(msg) from exc


class CmdRelationship(ArxCommand):
    """Record and review your side of a tie with other characters.

    Usage:
        relationship                                     - list your ties
        relationship list                                - same as bare ``relationship``
        relationship show <name|#>                       - detail one tie
        relationship plus <name>                         - ambient +1 bump
        relationship neg <name>                          - ambient -1 bump
        relationship declare <name>=<type>[,private|clandestine|public]
        relationship shift <name>=<from>,<to>[,note]
        relationship end <name>=<type>
        relationship reveal <name>=<type>,<clandestine|public>
        relationship ap <name>=<n>
        relationship advance <name>=<journal entry id>
        relationship summary <name>=<text>
    """

    key = "relationship"
    aliases = ["relation", "rel"]
    locks = "cmd:all()"
    action = None  # routed per-subverb in func()
    # Base Command has no switches attr; a class default keeps direct func() calls safe.
    switches: list[str] = []

    def _handlers(self) -> dict[str, Callable[[str], None]]:
        """The subverb -> handler table (a dict keeps ``func()`` under the branch limit)."""
        return {
            _SUBVERB_LIST: lambda _rest: self._show_list(),
            _SUBVERB_SHOW: self._show_detail,
            _SUBVERB_DECLARE: self._dispatch_declare,
            _SUBVERB_SHIFT: self._dispatch_shift,
            _SUBVERB_END: self._dispatch_end,
            _SUBVERB_REVEAL: self._dispatch_reveal,
            _SUBVERB_AP: self._dispatch_ap,
            _SUBVERB_ADVANCE: self._dispatch_advance,
            _SUBVERB_SUMMARY: self._dispatch_summary,
        }

    def func(self) -> None:
        """Route the leading subverb; bare ``relationship`` lists ties."""
        try:
            raw = (self.args or "").strip()
            # Switch form: ``rel/plus <name>`` / ``rel/neg <name>`` (#1699).
            switches = {s.lower() for s in (self.switches or [])}
            bump_switch = switches & _BUMP_SUBVERBS
            if bump_switch:
                self._dispatch_bump(bump_switch.pop(), raw)
                return
            if not raw:
                self._show_list()
                return
            parts = raw.split(maxsplit=1)
            # Accept the slash-form embedded in args too (``/plus <name>``).
            subverb = parts[0].lower().lstrip("/")
            rest = parts[1].strip() if len(parts) > 1 else ""
            if subverb in _BUMP_SUBVERBS:
                self._dispatch_bump(subverb, rest)
                return
            handler = self._handlers().get(subverb)
            if handler is None:
                self.msg(self._usage())
                return
            handler(rest)
        except CommandError as err:
            self.msg(str(err))
            self.msg(command_error={"error": str(err), "command": self.raw_string or ""})

    # -- ambient bumps (#1699) --------------------------------------------------

    def _dispatch_bump(self, subverb: str, rest: str) -> None:
        """Run RelationshipBumpAction at the named co-located character."""
        from actions.definitions.relationships import RelationshipBumpAction  # noqa: PLC0415

        name = rest.strip()
        if not name:
            msg = f"Usage: relationship {subverb} <name>"
            raise CommandError(msg)
        target_sheet, _companion = self._resolve_target(self.caller, name)
        valence = 1 if subverb == _SUBVERB_PLUS else -1
        result = RelationshipBumpAction().run(
            actor=self.caller, target_sheet=target_sheet, valence=valence
        )
        if result.message:
            self.msg(result.message)

    # -- label write verbs -------------------------------------------------------

    def _dispatch_declare(self, rest: str) -> None:
        """Syntax: ``declare <name>=<type>[,private|clandestine|public]``."""
        from actions.definitions.relationships import DeclareLabelAction  # noqa: PLC0415

        name, sep, rhs = rest.partition("=")
        if not name.strip() or not sep or not rhs.strip():
            msg = "Usage: relationship declare <name>=<type>[,private|clandestine|public]"
            raise CommandError(msg)
        parts = rhs.split(",", 1)
        type_name = parts[0].strip()
        awareness = parts[1].strip().lower() if len(parts) > 1 and parts[1].strip() else None
        target_sheet, target_companion = self._resolve_target(self.caller, name.strip())
        rel_type = self._resolve_type(type_name)
        run_kwargs: dict[str, Any] = {
            "target_sheet": target_sheet,
            "target_companion": target_companion,
            "type": rel_type,
        }
        if awareness:
            run_kwargs["awareness"] = awareness
        result = DeclareLabelAction().run(actor=self.caller, **run_kwargs)
        if result.message:
            self.msg(result.message)

    def _dispatch_shift(self, rest: str) -> None:
        """Syntax: ``shift <name>=<from>,<to>[,note]``."""
        from actions.definitions.relationships import ShiftLabelAction  # noqa: PLC0415

        name, sep, rhs = rest.partition("=")
        parts = rhs.split(",", 2) if sep else []
        if (
            not name.strip()
            or len(parts) < _MIN_LABEL_REF_PARTS
            or not parts[0].strip()
            or not parts[1].strip()
        ):
            msg = "Usage: relationship shift <name>=<from>,<to>[,note]"
            raise CommandError(msg)
        sheet = self._actor_sheet(self.caller)
        target_sheet, target_companion = self._resolve_target(self.caller, name.strip())
        label = self._own_open_label(sheet, target_sheet, target_companion, parts[0].strip())
        new_type = self._resolve_type(parts[1].strip())
        note = parts[2].strip() if len(parts) > _MIN_LABEL_REF_PARTS else ""
        result = ShiftLabelAction().run(
            actor=self.caller, label=label, new_type=new_type, note=note
        )
        if result.message:
            self.msg(result.message)

    def _dispatch_end(self, rest: str) -> None:
        """Syntax: ``end <name>=<type>``."""
        from actions.definitions.relationships import EndLabelAction  # noqa: PLC0415

        name, sep, type_name = rest.partition("=")
        if not name.strip() or not sep or not type_name.strip():
            msg = "Usage: relationship end <name>=<type>"
            raise CommandError(msg)
        sheet = self._actor_sheet(self.caller)
        target_sheet, target_companion = self._resolve_target(self.caller, name.strip())
        label = self._own_open_label(sheet, target_sheet, target_companion, type_name.strip())
        result = EndLabelAction().run(actor=self.caller, label=label)
        if result.message:
            self.msg(result.message)

    def _dispatch_reveal(self, rest: str) -> None:
        """Syntax: ``reveal <name>=<type>,<clandestine|public>``."""
        from actions.definitions.relationships import AdvanceLabelAwarenessAction  # noqa: PLC0415

        name, sep, rhs = rest.partition("=")
        parts = rhs.split(",", 1) if sep else []
        if (
            not name.strip()
            or len(parts) < _MIN_LABEL_REF_PARTS
            or not parts[0].strip()
            or not parts[1].strip()
        ):
            msg = "Usage: relationship reveal <name>=<type>,<clandestine|public>"
            raise CommandError(msg)
        sheet = self._actor_sheet(self.caller)
        target_sheet, target_companion = self._resolve_target(self.caller, name.strip())
        label = self._own_open_label(sheet, target_sheet, target_companion, parts[0].strip())
        awareness = parts[1].strip().lower()
        result = AdvanceLabelAwarenessAction().run(
            actor=self.caller, label=label, awareness=awareness
        )
        if result.message:
            self.msg(result.message)

    def _dispatch_ap(self, rest: str) -> None:
        """Syntax: ``ap <name>=<n>``."""
        from actions.definitions.relationships import SetTieAllocationAction  # noqa: PLC0415

        name, sep, value = rest.partition("=")
        if not name.strip() or not sep:
            msg = "Usage: relationship ap <name>=<n>"
            raise CommandError(msg)
        ap_amount = _require_int(value.strip(), "AP")
        target_sheet, target_companion = self._resolve_target(self.caller, name.strip())
        result = SetTieAllocationAction().run(
            actor=self.caller,
            target_sheet=target_sheet,
            target_companion=target_companion,
            ap_amount=ap_amount,
        )
        if result.message:
            self.msg(result.message)

    def _dispatch_advance(self, rest: str) -> None:
        """Syntax: ``advance <name>=<journal entry id>``."""
        from actions.definitions.relationships import AdvanceRelationshipTierAction  # noqa: PLC0415
        from world.journals.models import JournalEntry  # noqa: PLC0415

        name, sep, value = rest.partition("=")
        if not name.strip() or not sep:
            msg = "Usage: relationship advance <name>=<journal entry id>"
            raise CommandError(msg)
        entry_id = _require_int(value.strip(), "journal entry id")
        target_sheet, target_companion = self._resolve_target(self.caller, name.strip())
        if target_companion is not None:
            msg = "A relationship tier can only be advanced with a character."
            raise CommandError(msg)
        sheet = self._actor_sheet(self.caller)
        entry = JournalEntry.objects.filter(pk=entry_id, author=sheet).first()
        if entry is None:
            msg = f"No journal entry #{entry_id} of yours found."
            raise CommandError(msg)
        result = AdvanceRelationshipTierAction().run(
            actor=self.caller, target_sheet=target_sheet, journal_entry=entry
        )
        if result.message:
            self.msg(result.message)

    def _dispatch_summary(self, rest: str) -> None:
        """Syntax: ``summary <name>=<text>``."""
        from actions.definitions.relationships import SetTieSummaryAction  # noqa: PLC0415

        name, sep, text = rest.partition("=")
        if not name.strip() or not sep:
            msg = "Usage: relationship summary <name>=<text>"
            raise CommandError(msg)
        target_sheet, target_companion = self._resolve_target(self.caller, name.strip())
        result = SetTieSummaryAction().run(
            actor=self.caller,
            target_sheet=target_sheet,
            target_companion=target_companion,
            summary=text,
        )
        if result.message:
            self.msg(result.message)

    # -- read verbs ------------------------------------------------------------

    def _show_list(self) -> None:
        """Render one line per side of a tie the caller has touched (source side)."""
        from world.relationships.models import CharacterRelationship  # noqa: PLC0415

        sheet = self._actor_sheet(self.caller)
        qs = (
            CharacterRelationship.objects.filter(source=sheet)
            .select_related("target", "target__character", "target_companion")
            .prefetch_related("labels__type")  # noqa: PREFETCH_STRING — no to_attr on SharedMemoryModel
            .order_by("-updated_at")
        )
        relationships = list(qs)
        if not relationships:
            self.msg("You have recorded no relationships.")
            return
        self.msg("\n".join(self._render_list_row(rel) for rel in relationships))

    def _show_detail(self, rest: str) -> None:
        """Render a single side by target name or relationship id."""
        if not rest:
            msg = "Usage: relationship show <name|#>."
            raise CommandError(msg)
        sheet = self._actor_sheet(self.caller)
        relationship = self._resolve_relationship(sheet, rest)
        self.msg(self._render_detail(relationship))

    # -- resolution helpers ----------------------------------------------------

    def _actor_sheet(self, caller: Any) -> CharacterSheet:
        from django.core.exceptions import ObjectDoesNotExist  # noqa: PLC0415

        try:
            sheet = caller.sheet_data
        except (AttributeError, ObjectDoesNotExist) as exc:
            msg = "No active character."
            raise CommandError(msg) from exc
        if sheet is None:
            msg = "No active character."
            raise CommandError(msg)
        return sheet

    def _resolve_target(
        self, caller: Any, name: str
    ) -> tuple[CharacterSheet | None, Companion | None]:
        """Resolve a target name (caller.search) to a sheet or a bonded companion (#3575)."""
        from django.core.exceptions import ObjectDoesNotExist  # noqa: PLC0415

        target = caller.search(name)
        if not target:
            msg = f"Could not find '{name}'."
            raise CommandError(msg)
        companion = _active_companion_of(target)
        if companion is not None:
            return None, companion
        try:
            target_sheet = target.sheet_data
        except (AttributeError, ObjectDoesNotExist) as exc:
            msg = f"'{name}' has no character sheet."
            raise CommandError(msg) from exc
        if target_sheet is None:
            msg = f"'{name}' has no character sheet."
            raise CommandError(msg)
        return target_sheet, None

    def _resolve_type(self, value: str | None) -> RelationshipType:
        from world.relationships.models import RelationshipType  # noqa: PLC0415

        if not value:
            msg = "A relationship type is required."
            raise CommandError(msg)
        rel_type = RelationshipType.objects.filter(name__iexact=value.strip()).first()
        if rel_type is None:
            msg = f"No relationship type '{value}'."
            raise CommandError(msg)
        return rel_type

    def _own_open_label(
        self,
        sheet: CharacterSheet,
        target_sheet: CharacterSheet | None,
        target_companion: Companion | None,
        type_name: str,
    ) -> RelationshipLabel:
        from world.relationships.models import RelationshipLabel  # noqa: PLC0415

        rel_type = self._resolve_type(type_name)
        label = RelationshipLabel.objects.filter(
            relationship__source=sheet,
            relationship__target=target_sheet,
            relationship__target_companion=target_companion,
            type=rel_type,
            ended_at__isnull=True,
        ).first()
        if label is None:
            msg = f"You have not declared {rel_type.name} toward them."
            raise CommandError(msg)
        return label

    def _resolve_relationship(self, sheet: CharacterSheet, ref: str) -> CharacterRelationship:
        """Resolve one of the caller's (source-side) relationships by id or target name."""
        from django.core.exceptions import ObjectDoesNotExist  # noqa: PLC0415

        from world.relationships.models import CharacterRelationship  # noqa: PLC0415

        ref = ref.strip().removeprefix("#")
        qs = (
            CharacterRelationship.objects.filter(source=sheet)
            .select_related("target", "target__character", "target_companion")
            .prefetch_related("labels__type")  # noqa: PREFETCH_STRING — no to_attr on SharedMemoryModel
        )
        if ref.isdigit():
            relationship = qs.filter(pk=int(ref)).first()
        else:
            target = self.caller.search(ref)
            if not target:
                msg = f"Could not find '{ref}'."
                raise CommandError(msg)
            companion = _active_companion_of(target)
            if companion is not None:
                relationship = qs.filter(target_companion=companion).first()
            else:
                try:
                    target_sheet = target.sheet_data
                except (AttributeError, ObjectDoesNotExist):
                    target_sheet = None
                relationship = qs.filter(target=target_sheet).first() if target_sheet else None
        if relationship is None:
            msg = f"No relationship with '{ref}' found."
            raise CommandError(msg)
        return relationship

    # -- rendering -------------------------------------------------------------

    @staticmethod
    def _label_text(label: RelationshipLabel) -> str:
        """``Lover`` (public), ``Lover (clandestine)``, ``Enemy (private)``, ``Friend (former)``."""
        from world.relationships.constants import LabelAwareness  # noqa: PLC0415

        if label.is_former:
            return f"{label.type.name} (former)"
        if label.awareness == LabelAwareness.PUBLIC:
            return label.type.name
        return f"{label.type.name} ({label.awareness})"

    def _render_labels(self, side: CharacterRelationship) -> str:
        texts = [self._label_text(label) for label in side.labels.all()]
        return ", ".join(texts) if texts else "no labels"

    def _render_list_row(self, side: CharacterRelationship) -> str:
        """One summary line for a side of a tie: labels, depth, tier."""
        labels = self._render_labels(side)
        return f"{side.target_name}: {labels} | depth {side.pair_depth()} | tier {side.tier}"

    def _render_detail(self, side: CharacterRelationship) -> str:
        """A two-line detail view: the list row, then gauges + AP + summary."""
        from world.relationships.models import RelationshipAllocation  # noqa: PLC0415

        try:
            ap_this_week = side.allocation.ap_amount
        except RelationshipAllocation.DoesNotExist:
            ap_this_week = 0
        lines = [
            self._render_list_row(side),
            f"scenes {side.scene_depth} | invested {side.invested_depth} | "
            f"affection {side.affection} | conflict {side.conflict} | "
            f"ap this week {ap_this_week}",
        ]
        if side.summary:
            lines.append(side.summary)
        return "\n".join(lines)

    def _usage(self) -> str:
        return (
            "Usage: relationship [list|show <name|#>|plus <name>|neg <name>|"
            "declare <name>=<type>[,private|clandestine|public]|"
            "shift <name>=<from>,<to>[,note]|end <name>=<type>|"
            "reveal <name>=<type>,<clandestine|public>|ap <name>=<n>|"
            "advance <name>=<journal entry id>|summary <name>=<text>]"
        )
