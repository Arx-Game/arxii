"""Relationship-building telnet command — the ``relationship <subverb>`` namespace (#1485 / #1537).

A single command routes the positive relationship-building verbs through
``action.run()`` — the same seam the web ``RelationshipUpdateViewSet`` uses —
plus the telnet-only ``list`` / ``show`` read surfaces, and the feedback verbs
``kudos`` / ``complain``.

Write verbs (reach the Actions in ``actions/definitions/relationships.py``):

- ``relationship impression <name> ...``  → ``CreateFirstImpressionAction``
- ``relationship develop <name> ...``       → ``CreateDevelopmentAction``
- ``relationship capstone <name> ...``      → ``CreateCapstoneAction``
- ``relationship redistribute <name> ...``  → ``RedistributePointsAction``

Feedback verbs (#1537):

- ``relationship kudos <ref>``           → ``GiveWriteupKudosAction``
- ``relationship complain <ref>=<reason>`` → ``FileWriteupComplaintAction``

Writeup references use a type-prefix + pk notation — ``u<pk>`` for
RelationshipUpdate, ``d<pk>`` for RelationshipDevelopment, ``c<pk>`` for
RelationshipCapstone — matching the labels shown by ``relationship show``.
``_parse_writeup_ref`` encodes the shared scheme used in both display and parse.

The verbs live under the ``relationship`` namespace rather than as bare
top-level keys (e.g. ``impression`` / ``develop``) to avoid exit/channel/alias
collisions — mirrors ``CmdRitual`` / ``CmdDuel`` subverb routing.

No consent gate: these describe the caller's *regard* for another character,
they do not compel or provoke the target's behavior (ADR-0024). The Golden Rule
covers bad-faith writeups; the ``kudos`` / ``complaint`` feedback layer lets the
writeup subject commend or flag a writeup (#1537).

``linked_scene`` defaults to the caller's active scene in the current room
when the target is co-located in an active scene — so players can note a moment
in the moment, right after it warrants a relationship beat.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from commands.command import ArxCommand
from commands.exceptions import CommandError

if TYPE_CHECKING:
    from actions.base import Action
    from world.character_sheets.models import CharacterSheet
    from world.relationships.constants import FirstImpressionColoring, UpdateVisibility
    from world.relationships.models import CharacterRelationship, RelationshipTrack

# Subverbs.
_SUBVERB_IMPRESSION = "impression"
_SUBVERB_DEVELOP = "develop"
_SUBVERB_CAPSTONE = "capstone"
_SUBVERB_REDISTRIBUTE = "redistribute"
_SUBVERB_LIST = "list"
_SUBVERB_SHOW = "show"
_SUBVERB_KUDOS = "kudos"
_SUBVERB_COMPLAIN = "complain"
_WRITE_SUBVERBS = frozenset(
    {_SUBVERB_IMPRESSION, _SUBVERB_DEVELOP, _SUBVERB_CAPSTONE, _SUBVERB_REDISTRIBUTE}
)
_READ_SUBVERBS = frozenset({_SUBVERB_LIST, _SUBVERB_SHOW})
_FEEDBACK_SUBVERBS = frozenset({_SUBVERB_KUDOS, _SUBVERB_COMPLAIN})

# Writeup reference prefix → writeup_type string (matches what the Action + service expect).
# Labels are displayed in ``relationship show`` and parsed back here — one scheme, shared.
_WRITEUP_PREFIX_MAP: dict[str, str] = {
    "u": "update",
    "d": "development",
    "c": "capstone",
}

# Telnet key=value argument keys.
_KEY_TRACK = "track"
_KEY_SOURCE = "source"
_KEY_TARGET_TRACK = "target"
_KEY_POINTS = "points"
_KEY_TITLE = "title"
_KEY_WRITEUP = "writeup"
_KEY_COLORING = "coloring"
_KEY_VISIBILITY = "visibility"
_KEY_XP = "xp"

# Multi-word value keys — their value runs until the next ``key=`` token.
_MULTIWORD_KEYS = frozenset({_KEY_TITLE, _KEY_WRITEUP})


def _parse_kwargs_tokens(tokens: list[str]) -> dict[str, str]:
    """Parse ``key=value ...`` tokens into a kwargs dict.

    A free-text key (``title`` / ``writeup``) extends to the next ``key=`` token;
    other keys take exactly one value token, and a bare token following a
    completed single-word value is an error.
    """
    kwargs: dict[str, str] = {}
    key = ""
    value_parts: list[str] = []
    for token in tokens:
        if "=" in token and not token.startswith("="):
            if key:
                kwargs[key] = " ".join(value_parts).strip()
            key, _, value = token.partition("=")
            value_parts = [value] if value else []
        elif key and key in _MULTIWORD_KEYS:
            value_parts.append(token)
        elif key:
            msg = (
                f"Unexpected argument '{token}' after '{key}='. "
                "Multi-word values are only allowed for title and writeup."
            )
            raise CommandError(msg)
        else:
            msg = f"Unexpected argument '{token}'."
            raise CommandError(msg)
    if key:
        kwargs[key] = " ".join(value_parts).strip()
    return kwargs


def _parse_name_and_kwargs(rest: str) -> tuple[str, dict[str, str]]:
    """Split ``<name> key=value ...`` into the leading target name + a kwargs dict.

    The target name is positional (may be multi-word until the first ``key=``).
    Remaining ``key=value`` tokens are parsed by ``_parse_kwargs_tokens``.
    """
    tokens = rest.split()
    name_parts: list[str] = []
    idx = 0
    while idx < len(tokens) and "=" not in tokens[idx]:
        name_parts.append(tokens[idx])
        idx += 1
    name = " ".join(name_parts).strip()
    if idx == len(tokens):
        return name, {}
    return name, _parse_kwargs_tokens(tokens[idx:])


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
    """Record and review your regard for other characters.

    Usage:
        relationship                         — list your relationships
        relationship list                    — same as bare ``relationship``
        relationship show <name|#>           — detail one relationship (includes writeup refs)
        relationship impression <name> track=<id|name> points=<n>
            title=<text> writeup=<text> [coloring=positive|neutral|negative]
            [visibility=private|shared|gossip|public]
        relationship develop <name> track=<id|name> points=<n>
            title=<text> writeup=<text> [xp=<n>] [visibility=...]
        relationship capstone <name> track=<id|name> points=<n>
            title=<text> writeup=<text> [visibility=...]
        relationship redistribute <name> source=<track> target=<track>
            points=<n> title=<text> writeup=<text> [visibility=...]
        relationship kudos <ref>             — commend a shared writeup
        relationship complain <ref>=<reason> — file a staff complaint about a writeup

    Writeup refs are shown by ``relationship show``: ``u<id>`` = update,
    ``d<id>`` = development, ``c<id>`` = capstone (e.g. ``kudos u42``).
    Tracks resolve by name (iexact) or id. ``title`` / ``writeup`` are free
    text — their values run to the next ``key=`` token. An active scene in your
    current room is linked automatically when the target is co-located.
    """

    key = "relationship"
    aliases = ["relation"]
    locks = "cmd:all()"
    action = None  # routed per-subverb in func()

    def func(self) -> None:
        """Route the leading subverb; bare ``relationship`` lists relationships."""
        try:
            raw = (self.args or "").strip()
            if not raw:
                self._show_list()
                return
            parts = raw.split(maxsplit=1)
            subverb = parts[0].lower()
            rest = parts[1].strip() if len(parts) > 1 else ""
            if subverb == _SUBVERB_LIST:
                self._show_list()
            elif subverb == _SUBVERB_SHOW:
                self._show_detail(rest)
            elif subverb in _WRITE_SUBVERBS:
                self._dispatch_write(subverb, rest)
            elif subverb == _SUBVERB_KUDOS:
                self._dispatch_kudos(rest)
            elif subverb == _SUBVERB_COMPLAIN:
                self._dispatch_complain(rest)
            else:
                self.msg(self._usage())
        except CommandError as err:
            self.msg(str(err))
            self.msg(command_error={"error": str(err), "command": self.raw_string or ""})

    # -- write verbs -----------------------------------------------------------

    def _dispatch_write(self, subverb: str, rest: str) -> None:
        """Resolve the target + kwargs and run the matching relationship Action."""
        name, kwargs = _parse_name_and_kwargs(rest)
        if not name:
            msg = f"Usage: relationship {subverb} <name> ..."
            raise CommandError(msg)
        actor = self.caller
        sheet = self._actor_sheet(actor)
        target_sheet = self._resolve_target_sheet(actor, name)
        action, run_kwargs = self._build_write_kwargs(subverb, sheet, target_sheet, kwargs)
        result = action.run(actor=actor, **run_kwargs)
        if result.message:
            self.msg(result.message)

    def _build_write_kwargs(
        self,
        subverb: str,
        sheet: CharacterSheet,
        target_sheet: CharacterSheet,
        kwargs: dict[str, str],
    ) -> tuple[Action, dict[str, Any]]:
        """Translate parsed telnet kwargs into the Action's run() kwargs."""
        from actions.definitions.relationships import (  # noqa: PLC0415
            CreateCapstoneAction,
            CreateDevelopmentAction,
            CreateFirstImpressionAction,
            RedistributePointsAction,
        )

        common: dict[str, Any] = {
            "target_sheet": target_sheet,
            "points": _require_int(kwargs.get(_KEY_POINTS), _KEY_POINTS),
            "title": kwargs.get(_KEY_TITLE, ""),
            "writeup": kwargs.get(_KEY_WRITEUP, ""),
        }
        # Only pass visibility when the player set it, so each Action's own
        # default applies (capstone defaults to SHARED; the others to PRIVATE).
        if _KEY_VISIBILITY in kwargs:
            common["visibility"] = self._parse_visibility(kwargs.get(_KEY_VISIBILITY))

        if subverb == _SUBVERB_IMPRESSION:
            coloring = self._parse_coloring(kwargs.get(_KEY_COLORING))
            track = self._resolve_track(kwargs.get(_KEY_TRACK))
            return CreateFirstImpressionAction(), {**common, "track": track, "coloring": coloring}
        if subverb == _SUBVERB_DEVELOP:
            track = self._resolve_track(kwargs.get(_KEY_TRACK))
            xp = _require_int(kwargs.get(_KEY_XP, "0"), _KEY_XP) if _KEY_XP in kwargs else 0
            return CreateDevelopmentAction(), {**common, "track": track, "xp_awarded": xp}
        if subverb == _SUBVERB_CAPSTONE:
            track = self._resolve_track(kwargs.get(_KEY_TRACK))
            return CreateCapstoneAction(), {**common, "track": track}
        # redistribute
        source_track = self._resolve_track(kwargs.get(_KEY_SOURCE), label="source track")
        target_track = self._resolve_track(kwargs.get(_KEY_TARGET_TRACK), label="target track")
        run_kwargs = {**common, "source_track": source_track, "target_track": target_track}
        return RedistributePointsAction(), run_kwargs

    # -- feedback verbs (kudos / complain) ------------------------------------

    def _dispatch_kudos(self, rest: str) -> None:
        """Commend a shared writeup.  Syntax: ``relationship kudos <ref>``."""
        from actions.definitions.relationships import GiveWriteupKudosAction  # noqa: PLC0415

        ref = rest.strip()
        if not ref:
            msg = (
                "Usage: relationship kudos <ref>  "
                "(e.g. 'kudos u42'; see 'relationship show <name|#>' for refs)."
            )
            raise CommandError(msg)
        writeup_type, writeup_id = self._parse_writeup_ref(ref)
        result = GiveWriteupKudosAction().run(
            actor=self.caller, writeup_type=writeup_type, writeup_id=writeup_id
        )
        if result.message:
            self.msg(result.message)

    def _dispatch_complain(self, rest: str) -> None:
        """File a writeup complaint.  Syntax: ``relationship complain <ref>=<reason>``."""
        from actions.definitions.relationships import FileWriteupComplaintAction  # noqa: PLC0415

        if "=" not in rest:
            msg = (
                "Usage: relationship complain <ref>=<reason>  "
                "(e.g. 'complain u42=This writeup is in bad faith.')."
            )
            raise CommandError(msg)
        ref, _, reason = rest.partition("=")
        reason = reason.strip()
        if not reason:
            msg = "A reason is required. Usage: relationship complain <ref>=<reason>"
            raise CommandError(msg)
        writeup_type, writeup_id = self._parse_writeup_ref(ref.strip())
        result = FileWriteupComplaintAction().run(
            actor=self.caller,
            writeup_type=writeup_type,
            writeup_id=writeup_id,
            reason=reason,
        )
        if result.message:
            self.msg(result.message)

    def _parse_writeup_ref(self, ref: str) -> tuple[str, int]:
        """Parse a writeup reference like ``u42``, ``d15``, or ``c7`` into (writeup_type, pk).

        Prefix letters match the labels shown in ``relationship show``:
        ``u`` = RelationshipUpdate, ``d`` = RelationshipDevelopment, ``c`` = RelationshipCapstone.
        This is the single shared scheme — the same notation used in both display and parse.
        """
        ref = ref.strip().lower()
        for prefix, writeup_type in _WRITEUP_PREFIX_MAP.items():
            if ref.startswith(prefix) and len(ref) > len(prefix):
                pk_str = ref[len(prefix) :]
                if pk_str.isdigit():
                    return writeup_type, int(pk_str)
        msg = (
            f"Invalid writeup reference '{ref}'. "
            "Use u<id> (update), d<id> (development), or c<id> (capstone) — "
            "labels shown by 'relationship show <name|#>'."
        )
        raise CommandError(msg)

    # -- read verbs ------------------------------------------------------------

    def _show_list(self) -> None:
        """Render the caller's relationships (source side), newest first."""
        from world.relationships.models import CharacterRelationship  # noqa: PLC0415

        sheet = self._actor_sheet(self.caller)
        qs = (
            CharacterRelationship.objects.filter(source=sheet)
            .select_related("target", "target__character")
            .order_by("-updated_at")
        )
        relationships = list(qs)
        if not relationships:
            self.msg("You have recorded no relationships.")
            return
        lines = ["|wYour relationships:|n"]
        lines.extend(self._render_list_row(rel) for rel in relationships)
        lines.append("Use 'relationship show <name|#>' for detail.")
        self.msg("\n".join(lines))

    def _show_detail(self, rest: str) -> None:
        """Render a single relationship by target name or relationship id."""
        if not rest:
            msg = "Usage: relationship show <name or #id>."
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

    def _resolve_target_sheet(self, caller: Any, name: str) -> CharacterSheet:
        """Resolve a target character name (caller.search) to its CharacterSheet."""
        from django.core.exceptions import ObjectDoesNotExist  # noqa: PLC0415

        target = caller.search(name)
        if not target:
            msg = f"Could not find '{name}'."
            raise CommandError(msg)
        try:
            target_sheet = target.sheet_data
        except (AttributeError, ObjectDoesNotExist) as exc:
            msg = f"'{name}' has no character sheet."
            raise CommandError(msg) from exc
        if target_sheet is None:
            msg = f"'{name}' has no character sheet."
            raise CommandError(msg)
        return target_sheet

    def _resolve_track(self, value: str | None, *, label: str = "track") -> RelationshipTrack:
        """Resolve a RelationshipTrack by name (iexact) or numeric id."""
        from world.relationships.models import RelationshipTrack  # noqa: PLC0415

        if value is None or value == "":
            msg = f"{label} is required (name or id)."
            raise CommandError(msg)
        if value.isdigit():
            track = RelationshipTrack.objects.filter(pk=int(value)).first()
        else:
            track = RelationshipTrack.objects.filter(name__iexact=value).first()
        if track is None:
            msg = f"No relationship track '{value}' found."
            raise CommandError(msg)
        return track

    def _resolve_relationship(self, sheet: CharacterSheet, ref: str) -> CharacterRelationship:
        """Resolve one of the caller's (source-side) relationships by id or target name."""
        from django.db.models import Prefetch  # noqa: PLC0415

        from world.relationships.models import (  # noqa: PLC0415
            CharacterRelationship,
            RelationshipTrackProgress,
        )

        ref = ref.strip().removeprefix("#")
        qs = (
            CharacterRelationship.objects.filter(source=sheet)
            .select_related("target", "target__character")
            .prefetch_related(
                Prefetch(
                    "track_progress",
                    queryset=RelationshipTrackProgress.objects.select_related("track"),
                    to_attr="cached_track_progress",
                ),
            )
        )
        if ref.isdigit():
            relationship = qs.filter(pk=int(ref)).first()
        else:
            target = self.caller.search(ref)
            if not target:
                msg = f"Could not find '{ref}'."
                raise CommandError(msg)
            relationship = qs.filter(target=target.sheet_data).first()
        if relationship is None:
            msg = f"No relationship #{ref} found."
            raise CommandError(msg)
        return relationship

    def _parse_visibility(self, value: str | None) -> UpdateVisibility:
        """Coerce a visibility token to UpdateVisibility (default PRIVATE)."""
        from world.relationships.constants import UpdateVisibility  # noqa: PLC0415

        if value is None or value == "":
            return UpdateVisibility.PRIVATE
        try:
            return UpdateVisibility(value.lower())
        except ValueError as exc:
            msg = "visibility must be one of: private, shared, gossip, public."
            raise CommandError(msg) from exc

    def _parse_coloring(self, value: str | None) -> FirstImpressionColoring:
        """Coerce a coloring token to FirstImpressionColoring (default NEUTRAL)."""
        from world.relationships.constants import FirstImpressionColoring  # noqa: PLC0415

        if value is None or value == "":
            return FirstImpressionColoring.NEUTRAL
        try:
            return FirstImpressionColoring(value.lower())
        except ValueError as exc:
            msg = "coloring must be one of: positive, neutral, negative."
            raise CommandError(msg) from exc

    # -- rendering -------------------------------------------------------------

    def _render_list_row(self, rel: CharacterRelationship) -> str:
        """One summary line for a relationship in the list view."""
        target_name = rel.target.character.db_key
        status = "pending" if rel.is_pending else "active"
        flags: list[str] = []
        if rel.is_deceitful:
            flags.append("deceitful")
        if rel.is_soul_tether:
            flags.append("soul-tether")
        flag_text = f" ({', '.join(flags)})" if flags else ""
        affection = rel.affection
        return (
            f"[#{rel.pk}] {target_name} — |{self._affection_color(affection)}{affection:+d}|n "
            f"({status}){flag_text}"
        )

    def _render_detail(self, rel: CharacterRelationship) -> str:
        """A multi-line detail view for one relationship."""
        from world.relationships.models import (  # noqa: PLC0415
            RelationshipCapstone,
            RelationshipDevelopment,
            RelationshipUpdate,
        )

        target_name = rel.target.character.db_key
        status = "pending" if rel.is_pending else "active"
        lines = [
            f"|wRelationship #{rel.pk} with {target_name}|n — {status}",
            f"Affection: {rel.affection:+d}  Absolute value: {rel.absolute_value}  "
            f"Developed: {rel.developed_absolute_value}",
        ]
        progress = sorted(rel.cached_track_progress, key=lambda p: p.track.display_order)
        if progress:
            lines.append("|wTracks:|n")
            for prog in progress:
                tier = prog.current_tier
                tier_name = tier.name if tier else "—"
                lines.append(
                    f"  {prog.track.name}: {prog.developed_points} permanent / "
                    f"{prog.temporary_points} temporary (cap {prog.capacity}, tier {tier_name})"
                )
        else:
            lines.append("No track progress recorded yet.")

        # Writeups — listed with type-prefix refs so players know what to pass to kudos/complain.
        updates = list(
            RelationshipUpdate.objects.filter(relationship=rel)
            .select_related("track")
            .order_by("created_at")
        )
        developments = list(
            RelationshipDevelopment.objects.filter(relationship=rel)
            .select_related("track")
            .order_by("created_at")
        )
        capstones = list(
            RelationshipCapstone.objects.filter(relationship=rel)
            .select_related("track")
            .order_by("created_at")
        )
        if updates or developments or capstones:
            lines.append("|wWriteups:|n  (use ref with 'kudos <ref>' or 'complain <ref>=<reason>')")
            lines.extend(f"  [u{u.pk}] ({u.visibility}) {u.track.name}: {u.title}" for u in updates)
            lines.extend(
                f"  [d{d.pk}] ({d.visibility}) {d.track.name}: {d.title}" for d in developments
            )
            lines.extend(
                f"  [c{c.pk}] ({c.visibility}) {c.track.name}: {c.title}" for c in capstones
            )

        return "\n".join(lines)

    @staticmethod
    def _affection_color(affection: int) -> str:
        """Evennia color code for an affection value (green/red/grey)."""
        if affection > 0:
            return "g"
        if affection < 0:
            return "r"
        return "n"

    def _usage(self) -> str:
        return (
            "Usage: relationship [list|show <name|#>|impression <name> ...|"
            "develop <name> ...|capstone <name> ...|redistribute <name> ...|"
            "kudos <ref>|complain <ref>=<reason>]"
        )
