"""Event lifecycle + invitation RSVP telnet command — the ``event <subverb>`` namespace (#1499).

A single ``ArxCommand`` routes the host event verbs and the invitee RSVP through
``action.run()`` — the same seam the web ``EventViewSet`` / ``EventInvitationViewSet``
use — plus the telnet-only ``list`` / ``show`` read surfaces.

Host verbs (reach the Actions in ``actions/definitions/events.py``):

- ``event create name=<text> room=<name|id> when=<datetime> ...`` → ``CreateEventAction``
- ``event schedule <id>`` / ``start <id>`` / ``complete <id>`` / ``cancel <id>`` → lifecycle Actions
- ``event invite <id> <persona|org|society>=<name|id> [by=<persona>]`` → ``InviteToEventAction``

Invitee verb:

- ``event rsvp <id> accept|decline`` → ``RespondInvitationAction`` (the invitee acts as
  their own active persona)

The verbs live under the ``event`` namespace rather than as bare top-level keys (e.g.
``accept`` / ``decline``) to avoid exit/channel/alias collisions — mirrors
``CmdRelationship`` / ``CmdDuel`` / ``CmdRitual`` subverb routing. Bare ``event`` /
``event list`` shows the caller's visible events hub; ``event show <id>`` shows one in
detail (telnet-only — the web gets list/detail implicitly from ``EventViewSet``).

The host lifecycle + invite Actions are **account-authorized** (a staffer or scene GM
can manage an event with no character), so they take an ``account`` kwarg and pass
``actor=None`` through ``action.run()``; ``create`` and ``rsvp`` act *as* a persona and
take a resolved character actor. No consent gate (ADR-0024 — events are calendaring; an
invitation does not compel behavior).
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from commands.command import ArxCommand
from commands.exceptions import CommandError

if TYPE_CHECKING:
    from evennia.accounts.models import AccountDB

    from actions.base import Action
    from world.events.models import Event, EventInvitation

# Subverbs.
_SUBVERB_LIST = "list"
_SUBVERB_SHOW = "show"
_SUBVERB_CREATE = "create"
_SUBVERB_SCHEDULE = "schedule"
_SUBVERB_START = "start"
_SUBVERB_COMPLETE = "complete"
_SUBVERB_CANCEL = "cancel"
_SUBVERB_INVITE = "invite"
_SUBVERB_RSVP = "rsvp"
_LIFECYCLE_SUBVERBS = frozenset(
    {_SUBVERB_SCHEDULE, _SUBVERB_START, _SUBVERB_COMPLETE, _SUBVERB_CANCEL}
)

# Telnet key=value argument keys.
_KEY_NAME = "name"
_KEY_ROOM = "room"
_KEY_WHEN = "when"
_KEY_DESC = "desc"
_KEY_PUBLIC = "public"
_KEY_PHASE = "phase"
_KEY_BY = "by"

# Multi-word value keys — their value runs until the next ``key=`` token.
# ``name`` / ``desc`` are free text; ``room`` (room names often have spaces) and
# ``when`` (``YYYY-MM-DD HH:MM`` contains a space) extend to the next ``key=``
# rather than taking a single token. Invite target keys (persona=/org=/society=)
# stay single-token so the "exactly one target" check stays unambiguous.
_MULTIWORD_KEYS = frozenset({_KEY_NAME, _KEY_DESC, _KEY_ROOM, _KEY_WHEN})

# Invite target-type tokens → InvitationTargetType values.
_INVITE_TARGET_TOKENS: dict[str, str] = {
    "persona": "persona",
    "org": "organization",
    "organization": "organization",
    "society": "society",
}


def _parse_kwargs(rest: str) -> dict[str, str]:
    """Split ``key=value ...`` (with optional leading positional) into a kwargs dict.

    A free-text key (``name`` / ``desc``) extends to the next ``key=`` token; other
    keys take exactly one value token, and a bare token following a completed
    single-word value is an error. Mirrors ``relationships._parse_name_and_kwargs``.
    """
    tokens = rest.split()
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
                "Multi-word values are only allowed for name and desc."
            )
            raise CommandError(msg)
        else:
            msg = f"Unexpected argument '{token}'."
            raise CommandError(msg)
    if key:
        kwargs[key] = " ".join(value_parts).strip()
    return kwargs


def _parse_when(value: str | None) -> datetime:
    """Parse a ``when=`` value into a timezone-aware datetime.

    Accepts ISO 8601 (``Z``, numeric offset, microseconds) or
    ``YYYY-MM-DD [HH:MM[:SS]]``. A naive datetime (the ``YYYY-MM-DD …`` forms,
    or ISO with no offset) is interpreted in the server's current timezone
    (``.replace(tzinfo=…)``), so it compares correctly against the aware
    ``timezone.now()`` the Action uses (``USE_TZ=True``). Raises
    ``CommandError`` with usage guidance on a malformed value; the Action
    rejects past times.
    """
    from django.utils import timezone  # noqa: PLC0415

    if not value:
        msg = "when= is required (e.g. when=2026-07-04 19:00)."
        raise CommandError(msg)
    candidate = value.strip()
    tz = timezone.get_current_timezone()
    # ISO 8601 first (Python 3.11+ fromisoformat handles 'Z', offset, microseconds).
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        parsed = None
    if parsed is None:
        for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                parsed = datetime.strptime(candidate, fmt).replace(tzinfo=tz)
            except ValueError:
                parsed = None
                continue
            break
    if parsed is None:
        msg = f"Could not parse when='{value}'. Use ISO (2026-07-04T19:00:00) or YYYY-MM-DD HH:MM."
        raise CommandError(msg)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=tz)
    return parsed


class CmdEvent(ArxCommand):
    """Schedule and manage RP gatherings, and RSVP to invitations.

    Usage:
        event                               — list events visible to you
        event list                          — same as bare ``event``
        event show <id>                     — detail one event (hosts, invitations, RSVPs)
        event create name=<text> room=<name|id> when=<datetime>
            [desc=<text>] [public=<yes|no>] [phase=day|dusk|night|dawn]
        event schedule <id>                 — DRAFT → SCHEDULED
        event start <id>                    — SCHEDULED → ACTIVE (spawns the scene)
        event complete <id>                 — ACTIVE → COMPLETED (host / scene GM / staff)
        event cancel <id>                   — DRAFT/SCHEDULED → CANCELLED (host / staff)
        event invite <id> persona=<name|id> [by=<persona>]
        event invite <id> org=<name|id>      — or organization= / society=
        event rsvp <id> accept|decline      — respond to your own persona invitation

    ``when=`` accepts ISO 8601 or ``YYYY-MM-DD HH:MM``. Room resolves by name
    (caller.search) or numeric id; persona/org/society targets resolve by name
    (iexact) or id. Lifecycle verbs are account-authorized — staff and scene
    GMs can manage an event with no character. ``rsvp`` acts as your active
    persona and only works on a persona-targeted invitation addressed to you.
    """

    key = "event"
    aliases = ["events"]
    locks = "cmd:all()"
    action = None  # routed per-subverb in func()

    def func(self) -> None:
        """Route the leading subverb; bare ``event`` lists visible events."""
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
            elif subverb == _SUBVERB_CREATE:
                self._dispatch_create(rest)
            elif subverb in _LIFECYCLE_SUBVERBS:
                self._dispatch_lifecycle(subverb, rest)
            elif subverb == _SUBVERB_INVITE:
                self._dispatch_invite(rest)
            elif subverb == _SUBVERB_RSVP:
                self._dispatch_rsvp(rest)
            else:
                self.msg(self._usage())
        except CommandError as err:
            self.msg(str(err))
            self.msg(command_error={"error": str(err), "command": self.raw_string or ""})

    # -- host write verbs ----------------------------------------------------

    def _dispatch_create(self, rest: str) -> None:
        """``event create name=… room=… when=… [desc=…] [public=…] [phase=…]``."""
        from actions.definitions.events import CreateEventAction  # noqa: PLC0415
        from world.game_clock.constants import TimePhase  # noqa: PLC0415

        kwargs = _parse_kwargs(rest)
        name = kwargs.get(_KEY_NAME)
        if not name:
            msg = "Usage: event create name=<text> room=<name|id> when=<datetime> [...]"
            raise CommandError(msg)
        location_id = self._resolve_location_id(kwargs.get(_KEY_ROOM))
        scheduled_real_time = _parse_when(kwargs.get(_KEY_WHEN))
        public_token = kwargs.get(_KEY_PUBLIC)
        is_public = self._parse_bool(public_token, default=True) if public_token else True
        phase_token = kwargs.get(_KEY_PHASE)
        time_phase = self._parse_phase(phase_token) if phase_token else TimePhase.DAY

        result = CreateEventAction().run(
            actor=self.caller,
            name=name,
            description=kwargs.get(_KEY_DESC, "") or "",
            location_id=location_id,
            scheduled_real_time=scheduled_real_time,
            is_public=is_public,
            time_phase=time_phase,
        )
        if result.message:
            self.msg(result.message)

    def _dispatch_lifecycle(self, subverb: str, rest: str) -> None:
        """``event <schedule|start|complete|cancel> <id>``."""
        from actions.definitions.events import (  # noqa: PLC0415
            CancelEventAction,
            CompleteEventAction,
            ScheduleEventAction,
            StartEventAction,
        )

        event_id = self._require_event_id(rest, subverb)
        action_cls: type[Action] = {
            _SUBVERB_SCHEDULE: ScheduleEventAction,
            _SUBVERB_START: StartEventAction,
            _SUBVERB_COMPLETE: CompleteEventAction,
            _SUBVERB_CANCEL: CancelEventAction,
        }[subverb]
        result = action_cls().run(actor=None, account=self._account(), event_id=event_id)
        if result.message:
            self.msg(result.message)

    def _dispatch_invite(self, rest: str) -> None:
        """``event invite <id> <persona|org|society>=<name|id> [by=<persona>]``."""
        from actions.definitions.events import InviteToEventAction  # noqa: PLC0415

        parts = rest.split(None, 1)
        if len(parts) < 2 or "=" not in parts[1]:  # noqa: PLR2004
            msg = "Usage: event invite <id> persona=<name|id> [by=<persona>]  (or org= / society=)"
            raise CommandError(msg)
        event_id = self._parse_id(parts[0], "event id")
        kwargs = _parse_kwargs(parts[1])
        target_type, target_id = self._resolve_invite_target(kwargs)
        invited_by_id: int | None = None
        if _KEY_BY in kwargs:
            invited_by_id = self._resolve_persona_id(kwargs[_KEY_BY], label="by persona")
        result = InviteToEventAction().run(
            actor=None,
            account=self._account(),
            event_id=event_id,
            target_type=target_type,
            target_id=target_id,
            invited_by_persona_id=invited_by_id,
        )
        if result.message:
            self.msg(result.message)

    def _dispatch_rsvp(self, rest: str) -> None:
        """``event rsvp <id> accept|decline`` (the invitee acts as their persona)."""
        from actions.definitions.events import RespondInvitationAction  # noqa: PLC0415
        from world.events.constants import RSVP_VERB_TO_RESPONSE  # noqa: PLC0415

        parts = rest.split()
        if len(parts) != 2:  # noqa: PLR2004
            msg = "Usage: event rsvp <id> accept|decline"
            raise CommandError(msg)
        invitation_id = self._parse_id(parts[0], "invitation id")
        choice = parts[1].lower()
        if choice not in RSVP_VERB_TO_RESPONSE:
            msg = "RSVP must be 'accept' or 'decline'."
            raise CommandError(msg)
        response = RSVP_VERB_TO_RESPONSE[choice]
        result = RespondInvitationAction().run(
            actor=self.caller,
            invitation_id=invitation_id,
            response=response,
        )
        if result.message:
            self.msg(result.message)

    # -- read verbs ----------------------------------------------------------

    def _show_list(self) -> None:
        """Render events visible to the caller's active persona (or public events)."""
        from world.events.services import get_visible_events  # noqa: PLC0415

        persona = self._actor_persona_or_none()
        events = list(get_visible_events(persona).order_by("scheduled_real_time"))
        if not events:
            self.msg("No events to show.")
            return
        lines = ["|wUpcoming events:|n"]
        lines.extend(self._render_list_row(event) for event in events)
        lines.append("Use 'event show <id>' for detail.")
        self.msg("\n".join(lines))

    def _show_detail(self, rest: str) -> None:
        """Render one event by id (must be visible to the caller)."""
        from world.events.models import Event  # noqa: PLC0415
        from world.events.services import get_visible_events  # noqa: PLC0415

        event_id = self._parse_id(rest, "event id")
        persona = self._actor_persona_or_none()
        event = get_visible_events(persona).filter(pk=event_id).first()
        if event is None:
            event = Event.objects.filter(pk=event_id).first()
            if event is None:
                msg = f"No event #{event_id} found."
                raise CommandError(msg)
            # Visible-events scoping hides private/cancelled events the caller
            # cannot see; fall through to the not-found message rather than leak.
            msg = f"No event #{event_id} visible to you."
            raise CommandError(msg)
        self.msg(self._render_detail(event))

    # -- resolution helpers --------------------------------------------------

    def _account(self) -> AccountDB:
        """The caller's account (host lifecycle/invite verbs are account-authorized)."""
        account = self.caller.account
        if account is None:
            msg = "You must be logged in to manage events."
            raise CommandError(msg)
        return account

    def _actor_persona_or_none(self) -> Any:
        """The caller's active persona, or None (reads fall back to public events)."""
        from django.core.exceptions import ObjectDoesNotExist  # noqa: PLC0415

        from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415

        try:
            sheet = self.caller.sheet_data
        except (AttributeError, ObjectDoesNotExist):
            return None
        try:
            return active_persona_for_sheet(sheet)
        except ObjectDoesNotExist:
            return None

    def _resolve_location_id(self, value: str | None) -> int:
        """Resolve a ``room=`` token (caller.search or numeric id) to a RoomProfile id."""
        from evennia_extensions.models import RoomProfile  # noqa: PLC0415

        if not value:
            msg = "room= is required (a room name or id)."
            raise CommandError(msg)
        if value.isdigit():
            location_id = int(value)
        else:
            room = self.caller.search(value)
            if not room:
                msg = f"Could not find a room '{value}'."
                raise CommandError(msg)
            location_id = self._room_profile_id(room)
        if not RoomProfile.objects.filter(pk=location_id).exists():
            # The numeric id resolved but no RoomProfile backs it — events anchor
            # on the RoomProfile, so a profile-less room cannot host one.
            msg = f"Room '{value}' is not set up to host events."
            raise CommandError(msg)
        return location_id

    def _resolve_invite_target(self, kwargs: dict[str, str]) -> tuple[str, int]:
        """Resolve the single ``persona=`` / ``org=`` / ``society=`` invite target.

        Returns ``(target_type, target_id)``. Exactly one target token must be set.
        """
        from world.scenes.models import Persona  # noqa: PLC0415
        from world.societies.models import Organization, Society  # noqa: PLC0415

        present = [k for k in kwargs if k in _INVITE_TARGET_TOKENS]
        if len(present) != 1:
            msg = "Provide exactly one invite target: persona=, org=, or society= (by name or id)."
            raise CommandError(msg)
        token = present[0]
        value = kwargs[token]
        target_type = _INVITE_TARGET_TOKENS[token]
        model = {"persona": Persona, "organization": Organization, "society": Society}[target_type]
        target_id = self._resolve_target_id(model, value, label=token)
        return target_type, target_id

    def _resolve_target_id(self, model: type[Any], value: str, *, label: str) -> int:
        """Resolve a model instance by name (iexact) or pk; return its id."""
        if value.isdigit():
            instance = model.objects.filter(pk=int(value)).first()
        else:
            instance = model.objects.filter(name__iexact=value).first()
        if instance is None:
            msg = f"No {label} '{value}' found."
            raise CommandError(msg)
        return instance.pk

    def _resolve_persona_id(self, value: str, *, label: str) -> int:
        """Resolve a persona by name (iexact) or pk to its id (for ``by=``)."""
        from world.scenes.models import Persona  # noqa: PLC0415

        return self._resolve_target_id(Persona, value, label=label)

    # -- parsing helpers -----------------------------------------------------

    def _require_event_id(self, rest: str, subverb: str) -> int:
        if not rest:
            msg = f"Usage: event {subverb} <id>"
            raise CommandError(msg)
        return self._parse_id(rest, "event id")

    def _parse_id(self, value: str, label: str) -> int:
        value = value.strip().removeprefix("#")
        if not value.isdigit():
            msg = f"{label.capitalize()} must be a number."
            raise CommandError(msg)
        return int(value)

    def _parse_bool(self, value: str | None, *, default: bool) -> bool:
        token = (value or "").strip().lower()
        if token in ("yes", "y", "true", "1", "public"):
            return True
        if token in ("no", "n", "false", "0", "private"):
            return False
        return default

    def _parse_phase(self, value: str | None) -> str:
        from world.game_clock.constants import TimePhase  # noqa: PLC0415

        token = (value or "").strip().lower()
        if token in TimePhase.values:
            return token
        msg = "phase must be one of: day, dusk, night, dawn."
        raise CommandError(msg)

    # -- rendering -----------------------------------------------------------

    def _render_list_row(self, event: Event) -> str:
        location_name = self._location_name(event)
        return (
            f"[#{event.pk}] |w{event.name}|n ({event.get_status_display()}) — "
            f"{location_name} @ {self._fmt_time(event.scheduled_real_time)}"
        )

    def _render_detail(self, event: Event) -> str:
        lines = [
            f"|wEvent #{event.pk}: {event.name}|n — {event.get_status_display()}",
            f"Location: {self._location_name(event)}",
            f"When: {self._fmt_time(event.scheduled_real_time)} ({event.time_phase})",
            f"Visibility: {'public' if event.is_public else 'private'}",
        ]
        if event.description:
            lines.append(f"{event.description}")
        hosts = list(event.hosts.select_related("persona"))
        if hosts:
            lines.append("|wHosts:|n " + ", ".join(self._host_label(h) for h in hosts))
        invitations = list(
            event.invitations.select_related(
                "target_persona", "target_organization", "target_society"
            )
        )
        if invitations:
            lines.append("|wInvitations:|n")
            lines.extend(f"  {self._invitation_label(inv)}" for inv in invitations)
        else:
            lines.append("No invitations yet.")
        return "\n".join(lines)

    def _host_label(self, host: Any) -> str:
        name = host.persona.name if host.persona else "(deleted)"
        return f"{name}{' (primary)' if host.is_primary else ''}"

    def _invitation_label(self, invitation: EventInvitation) -> str:
        target = invitation.get_active_target()
        target_name = target.name if target else "(removed)"
        target_type = invitation.get_target_type_display()
        rsvp = self._rsvp_label(invitation.response)
        return f"[#{invitation.pk}] {target_type} {target_name} — {rsvp}"

    def _rsvp_label(self, response: str) -> str:
        from world.events.constants import InvitationResponse  # noqa: PLC0415

        labels = {
            InvitationResponse.ACCEPTED: "|gaccepted|n",
            InvitationResponse.DECLINED: "|rdeclined|n",
            InvitationResponse.PENDING: "pending",
        }
        return labels.get(response, response)

    # -- low-level render helpers -------------------------------------------

    @staticmethod
    def _fmt_time(when: datetime) -> str:
        return when.strftime("%Y-%m-%d %H:%M")

    @staticmethod
    def _location_name(event: Event) -> str:
        try:
            return event.location.objectdb.db_key
        except AttributeError:
            return "(unknown room)"

    @staticmethod
    def _room_profile_id(room: Any) -> int:
        """Look up the RoomProfile for a room ObjectDB; raise if none exists."""
        from evennia_extensions.models import RoomProfile  # noqa: PLC0415

        try:
            profile = RoomProfile.objects.get(objectdb=room)
        except RoomProfile.DoesNotExist as exc:
            msg = f"Room '{room.db_key}' is not set up to host events."
            raise CommandError(msg) from exc
        return profile.pk

    def _usage(self) -> str:
        return (
            "Usage: event [list|show <id>|create name=… room=… when=…|"
            "schedule <id>|start <id>|complete <id>|cancel <id>|"
            "invite <id> persona=…|rsvp <id> accept|decline]"
        )
