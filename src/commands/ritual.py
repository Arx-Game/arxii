"""Telnet command for performing magical rituals.

Thin telnet face of ``actions.definitions.ritual.PerformRitualAction`` (single-actor
path) and the session services in ``world.magic.services.sessions`` (multi-participant
session path).

Single-actor path (SERVICE/CEREMONY kind):
    ``ritual <name>``                       — perform a ritual by name
    ``ritual <name> key=value [key=value]``  — with ritual parameters

Multi-participant session path:
    ``ritual sessions``                              — list pending sessions
    ``ritual draft <name> invite=<char>[,<char>]``  — draft a session
        (add ``role=sinner|sineater resonance=<name> [writeup=...]`` for rituals
        that carry setup info, e.g. the soul-tether BILATERAL)
    ``ritual join <id> [role=sinner|sineater]``      — accept your invitation
    ``ritual decline <id>``                          — decline your invitation
    ``ritual fire <id>``                             — fire the session (initiator only)

The web path uses ``RitualSessionViewSet`` for sessions and ``RitualPerformView``
for single-actor rituals — both converge on the same service functions.
"""

from __future__ import annotations

from typing import Any

from django.db.models import Q

from actions.definitions.ritual import PerformRitualAction
from commands.command import ArxCommand
from commands.exceptions import CommandError

_THREAD_KWARG = "thread"
_THREAD_ID_KEY = "thread_id"
_SESSION_SUBCMDS = frozenset({"sessions", "draft", "join", "decline", "fire"})
# Kwargs carried into session/participant dicts for rituals that need setup
# info (e.g. the soul-tether BILATERAL). Keys match what the ritual's
# service_function_path reads off RitualSession.session_kwargs /
# RitualSessionParticipant.participant_kwargs.
_ROLE_KWARG = "role"
_RESONANCE_KWARG = "resonance"
_WRITEUP_KWARG = "writeup"
_SESSION_RESONANCE_ID_KEY = "resonance_id"
_SESSION_WRITEUP_KEY = "writeup"
_PARTICIPANT_ROLE_KEY = "soul_tether_role"


def _resolve_soul_tether_role(token: str) -> str:
    """Map a telnet ``role=`` token to a SoulTetherRole value.

    Returns the canonical uppercase enum value (``"SINNER"`` / ``"SINEATER"``)
    that the fire handler ``accept_soul_tether_via_session`` compares against.
    Raises ``CommandError`` for unknown roles.
    """
    from world.magic.types.soul_tether import SoulTetherRole  # noqa: PLC0415

    normalized = token.strip().upper()
    for role in SoulTetherRole:
        if normalized == role.value:
            return role.value
    msg = f"Unknown role '{token}'. Use role=sinner or role=sineater."
    raise CommandError(msg)


def _parse_trailing_kwarg(rest: str, key: str) -> str | None:
    """Return the value of a ``key=value`` token in *rest*, or None if absent.

    Scans whitespace-delimited tokens for one starting with ``key=`` and
    returns its value. Used by session subcommands that take a single optional
    kwarg (e.g. ``join <id> role=sinner``) alongside a positional session id.
    """
    prefix = f"{key}="
    for token in rest.split():
        if token.startswith(prefix):
            return token[len(prefix) :]
    return None


class CmdRitual(ArxCommand):
    """Perform a magical ritual or manage a multi-participant ritual session.

    **Single-actor rituals:**
        ``ritual <name>``
        ``ritual <name> key=value [key=value]``
        Example: ``ritual Rite of Imbuing thread=5``

    **Multi-participant session lifecycle:**
        ``ritual sessions``                              — list pending sessions
        ``ritual draft <name> invite=<char>[,<char>]``   — draft a session
            (add ``role=sinner|sineater resonance=<name> [writeup=...]`` for
            rituals that carry setup info, e.g. the soul-tether BILATERAL)
        ``ritual join <id> [role=sinner|sineater]``       — accept your invitation
        ``ritual decline <id>``                           — decline your invitation
        ``ritual fire <id>``                              — fire the session (initiator only)
    """

    key = "ritual"
    locks = "cmd:all()"
    action = PerformRitualAction()

    def func(self) -> None:
        """Route session subcommands; fall through to single-actor action otherwise."""
        first = (self.args or "").strip().split()[0].lower() if (self.args or "").strip() else ""
        if first in _SESSION_SUBCMDS:
            rest = (self.args or "").strip()[len(first) :].strip()
            try:
                if first == "sessions":  # noqa: STRING_LITERAL
                    self._handle_sessions()
                elif first == "draft":  # noqa: STRING_LITERAL
                    self._handle_draft(rest)
                elif first == "join":  # noqa: STRING_LITERAL
                    self._handle_join(rest)
                elif first == "decline":  # noqa: STRING_LITERAL
                    self._handle_decline(rest)
                elif first == "fire":  # noqa: STRING_LITERAL
                    self._handle_fire(rest)
            except CommandError as err:
                self.caller.msg(str(err))
        else:
            super().func()

    # ------------------------------------------------------------------
    # Session handlers
    # ------------------------------------------------------------------

    def _handle_sessions(self) -> None:
        """List pending sessions where caller is initiator or participant."""
        from world.magic.models.sessions import RitualSession  # noqa: PLC0415

        sheet = self.caller.sheet_data
        qs = (
            RitualSession.objects.filter(
                Q(initiator=sheet) | Q(participants__character_sheet=sheet)
            )
            .distinct()
            .select_related("ritual", "initiator__character")
            .prefetch_related("participants__character_sheet__character")  # noqa: PREFETCH_STRING
        )
        sessions = list(qs)
        if not sessions:
            self.caller.msg("You have no pending ritual sessions.")
            return
        lines = ["|wPending ritual sessions:|n"]
        for s in sessions:
            participant_summary = ", ".join(
                f"{p.character_sheet.character.db_key}:{p.state}" for p in s.participants.all()
            )
            lines.append(
                f"  [#{s.pk}] {s.ritual.name}"
                f" (by {s.initiator.character.db_key}) — {participant_summary}"
            )
        self.caller.msg("\n".join(lines))

    def _handle_draft(  # noqa: C901, PLR0912, PLR0915
        self, rest: str
    ) -> None:
        """Draft a multi-participant session: ``draft <name> invite=<char>[,<char>]``."""
        from datetime import timedelta  # noqa: PLC0415

        from django.utils import timezone  # noqa: PLC0415

        from world.magic.constants import (  # noqa: PLC0415
            ParticipationRule,
            RitualExecutionKind,
        )
        from world.magic.exceptions import (  # noqa: PLC0415
            ParticipantCountError,
            RitualSessionError,
        )
        from world.magic.models import Ritual  # noqa: PLC0415
        from world.magic.models.affinity import Resonance  # noqa: PLC0415
        from world.magic.services.sessions import draft_session  # noqa: PLC0415

        # Parse: ``Ritual Name invite=char1[,char2] role=sinner|sineater
        #         resonance=<name> [writeup=<narrative>]``
        tokens = rest.split()
        name_parts: list[str] = []
        invite_names: list[str] = []
        role_token = ""
        resonance_token = ""
        writeup = ""
        index = 0
        while index < len(tokens):
            token = tokens[index]
            if token.startswith("invite="):
                invite_names = [n.strip() for n in token[7:].split(",") if n.strip()]
            elif token.startswith(f"{_ROLE_KWARG}="):
                role_token = token[len(_ROLE_KWARG) + 1 :]
            elif token.startswith(f"{_RESONANCE_KWARG}="):
                resonance_token = token[len(_RESONANCE_KWARG) + 1 :]
            elif token.startswith(f"{_WRITEUP_KWARG}="):
                writeup = " ".join([token[len(_WRITEUP_KWARG) + 1 :], *tokens[index + 1 :]]).strip()
                break
            else:
                name_parts.append(token)
            index += 1

        usage = (
            "Usage: ritual draft <ritual_name> invite=<character>[,<character>]\n"
            "       [role=sinner|sineater resonance=<name> [writeup=<narrative>]]"
        )
        name = " ".join(name_parts).strip()
        if not name:
            raise CommandError(usage)
        if not invite_names:
            raise CommandError(usage)

        ritual = Ritual.objects.filter(
            name__iexact=name,
            execution_kind__in=[RitualExecutionKind.SERVICE, RitualExecutionKind.FLOW],
            participation_rule__in=[
                ParticipationRule.FORMATION,
                ParticipationRule.INDUCTION,
                ParticipationRule.BILATERAL,
            ],
        ).first()
        if ritual is None:
            msg = (
                f"No multi-participant ritual named '{name}' found. "
                "(Single-actor rituals use 'ritual <name>' without 'draft'.)"
            )
            raise CommandError(msg)

        invitees = []
        for invite_name in invite_names:
            target = self.caller.search(invite_name)
            if target is None:
                msg = f"Cannot find '{invite_name}'."
                raise CommandError(msg)
            invitee_sheet = getattr(target, "sheet_data", None)  # noqa: GETATTR_LITERAL
            if invitee_sheet is None:
                msg = f"'{invite_name}' has no character sheet."
                raise CommandError(msg)
            invitees.append(invitee_sheet)

        initiator_sheet = self.caller.sheet_data

        # Build session-level + initiator-participant kwargs from the parsed tokens.
        session_kwargs: dict[str, Any] = {}
        initiator_participant_kwargs: dict[str, Any] = {}
        if role_token:
            initiator_participant_kwargs[_PARTICIPANT_ROLE_KEY] = _resolve_soul_tether_role(
                role_token
            )
        if resonance_token:
            resonance_name = resonance_token.strip()
            resonance = Resonance.objects.filter(name__iexact=resonance_name).first()
            if resonance is None:
                msg = f"No resonance named '{resonance_name}'."
                raise CommandError(msg)
            session_kwargs[_SESSION_RESONANCE_ID_KEY] = resonance.pk
        if writeup:
            session_kwargs[_SESSION_WRITEUP_KEY] = writeup

        try:
            session = draft_session(
                ritual=ritual,
                initiator=initiator_sheet,
                proposed_terms="",
                session_kwargs=session_kwargs,
                invitee_sheets=invitees,
                session_references=[],
                initiator_participant_kwargs=initiator_participant_kwargs,
                initiator_references=[],
                expires_at=timezone.now() + timedelta(hours=24),
            )
        except (ParticipantCountError, RitualSessionError) as exc:
            raise CommandError(exc.user_message) from exc

        invite_list = ", ".join(inv.character.db_key for inv in invitees)
        self.caller.msg(
            f"Ritual session #{session.pk} drafted: {ritual.name}. "
            f"Invited: {invite_list}. "
            f"Use 'ritual fire {session.pk}' once all have joined."
        )

    def _handle_join(self, rest: str) -> None:
        """Accept a session invitation: ``join <id> [role=sinner|sineater]``."""
        from world.magic.exceptions import SessionNotInPendingError  # noqa: PLC0415
        from world.magic.models.sessions import RitualSessionParticipant  # noqa: PLC0415
        from world.magic.services.sessions import accept_session  # noqa: PLC0415

        session_id = self._parse_session_id(
            rest, "Usage: ritual join <session_id> [role=sinner|sineater]"
        )
        participant_kwargs: dict[str, Any] = {}
        role_token = _parse_trailing_kwarg(rest, _ROLE_KWARG)
        if role_token is not None:
            participant_kwargs[_PARTICIPANT_ROLE_KEY] = _resolve_soul_tether_role(role_token)

        sheet = self.caller.sheet_data
        participant = RitualSessionParticipant.objects.filter(
            session_id=session_id,
            character_sheet=sheet,
        ).first()
        if participant is None:
            msg = f"You are not an invited participant of session #{session_id}."
            raise CommandError(msg)
        try:
            accept_session(
                participant=participant,
                participant_kwargs=participant_kwargs,
                references=[],
            )
        except SessionNotInPendingError:
            msg = f"You have already responded to session #{session_id}."
            raise CommandError(msg) from None
        self.caller.msg(f"You have joined ritual session #{session_id}.")

    def _handle_decline(self, rest: str) -> None:
        """Decline a session invitation: ``decline <id>``."""
        from world.magic.exceptions import SessionNotInPendingError  # noqa: PLC0415
        from world.magic.models.sessions import (  # noqa: PLC0415
            RitualSession,
            RitualSessionParticipant,
        )
        from world.magic.services.sessions import decline_session  # noqa: PLC0415

        session_id = self._parse_session_id(rest, "Usage: ritual decline <session_id>")
        sheet = self.caller.sheet_data
        participant = RitualSessionParticipant.objects.filter(
            session_id=session_id,
            character_sheet=sheet,
        ).first()
        if participant is None:
            msg = f"You are not an invited participant of session #{session_id}."
            raise CommandError(msg)
        try:
            decline_session(participant=participant)
        except SessionNotInPendingError:
            msg = f"You have already responded to session #{session_id}."
            raise CommandError(msg) from None
        if not RitualSession.objects.filter(pk=session_id).exists():
            self.caller.msg(
                f"You declined session #{session_id}. The session was dissolved "
                "— the threshold can no longer be met."
            )
        else:
            self.caller.msg(f"You declined ritual session #{session_id}.")

    def _handle_fire(self, rest: str) -> None:
        """Fire a session (initiator only): ``fire <id>``."""
        from world.magic.exceptions import ThresholdNotMetError  # noqa: PLC0415
        from world.magic.models.sessions import RitualSession  # noqa: PLC0415
        from world.magic.services.sessions import fire_session  # noqa: PLC0415

        session_id = self._parse_session_id(rest, "Usage: ritual fire <session_id>")
        sheet = self.caller.sheet_data
        session = RitualSession.objects.filter(pk=session_id, initiator=sheet).first()
        if session is None:
            msg = f"Session #{session_id} not found or you are not its initiator."
            raise CommandError(msg)
        try:
            fire_session(session=session)
        except ThresholdNotMetError:
            msg = f"Session #{session_id} cannot fire yet — not all participants have responded."
            raise CommandError(msg) from None
        self.caller.msg(f"Ritual session #{session_id} has been fired. The ritual is complete.")

    # ------------------------------------------------------------------
    # Single-actor helpers (unchanged)
    # ------------------------------------------------------------------

    def resolve_action_args(self) -> dict[str, Any]:
        """Parse ``ritual <name> [k=v ...]`` into action kwargs."""
        from world.magic.constants import RitualExecutionKind  # noqa: PLC0415
        from world.magic.models import Ritual, Thread  # noqa: PLC0415

        args = self.require_args("Perform which ritual?")
        name, raw_kwargs = self._split_name_and_kwargs(args)

        ritual = Ritual.objects.filter(
            name__iexact=name,
            execution_kind__in=[
                RitualExecutionKind.SERVICE,
                RitualExecutionKind.CEREMONY,
            ],
        ).first()
        if ritual is None:
            msg = f"You don't know how to perform '{name}'."
            raise CommandError(msg)

        service_kwargs: dict[str, Any] = {}
        thread_id = raw_kwargs.pop(_THREAD_ID_KEY, None)
        if thread_id is not None:
            thread = Thread.objects.filter(
                pk=thread_id,
                owner=self.caller.sheet_data,
                retired_at__isnull=True,
            ).first()
            if thread is None:
                msg = "You have no active thread with that id."
                raise CommandError(msg)
            service_kwargs["thread"] = thread

        service_kwargs.update(raw_kwargs)

        components = self._gather_components()
        return {"ritual": ritual, "components_provided": components, **service_kwargs}

    def _split_name_and_kwargs(self, args: str) -> tuple[str, dict[str, int]]:
        """Split into ritual name + trailing ``key=value`` int tokens."""
        tokens = args.split()
        kwargs: dict[str, int] = {}
        name_parts: list[str] = []
        in_kwargs = False
        for token in tokens:
            if "=" in token and not token.startswith("="):
                in_kwargs = True
                key, _, value = token.partition("=")
                try:
                    parsed = int(value)
                except ValueError as exc:
                    msg = f"Ritual parameter '{key}' must be a number."
                    raise CommandError(msg) from exc
                kwargs[_THREAD_ID_KEY if key == _THREAD_KWARG else key] = parsed
            elif in_kwargs:
                msg = "Ritual parameters must come after the ritual name."
                raise CommandError(msg)
            else:
                name_parts.append(token)
        name = " ".join(name_parts).strip()
        if not name:
            msg = "Perform which ritual?"
            raise CommandError(msg)
        return name, kwargs

    def _gather_components(self) -> list[Any]:
        """Collect ItemInstance rows for the caller's carried items."""
        components = []
        for obj in self.caller.contents:
            instance = getattr(obj, "item_instance", None)  # noqa: GETATTR_LITERAL
            if instance is not None:
                components.append(instance)
        return components

    def _parse_session_id(self, rest: str, usage_msg: str) -> int:
        """Parse the first token of ``rest`` as an integer session pk."""
        rest = rest.strip()
        if not rest:
            raise CommandError(usage_msg)
        try:
            return int(rest.split()[0])
        except ValueError as exc:
            msg = f"Session ID must be a number. {usage_msg}"
            raise CommandError(msg) from exc
