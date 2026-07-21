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
    ``ritual cancel <id>``                           — cancel a pending session (initiator only)

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
_SESSION_SUBCMDS = frozenset({"sessions", "draft", "join", "decline", "fire", "cancel"})


def _advancement_error_message(exc: Exception) -> str:
    """Return a caller-safe error string from a ``ClassLevelAdvancementError``.

    Only ``AdvancementRequirementsNotMet`` carries the per-requirement
    ``failed`` list — explicit dispatch, not a getattr default (#2386).
    """
    from world.progression.exceptions import AdvancementRequirementsNotMet  # noqa: PLC0415

    if isinstance(exc, AdvancementRequirementsNotMet) and exc.failed:
        return "; ".join(exc.failed)
    return exc.user_message


def _tokenize_draft_args(rest: str) -> tuple[str, list[str], dict[str, str]]:
    """Parse ``<name> invite=<a>[,<b>] key=value …`` into ``(name, invitee_names, kwargs)``.

    Processes tokens left-to-right:
    - ``invite=<csv>`` is parsed as the invitee list.
    - ``key=value`` tokens go into *kwargs*; if the next tokens contain no
      ``=`` they are consumed as the value's remainder — matching
      ``writeup=``/``declaration=``-style trailing-text behaviour.
    - All other tokens are accumulated as the ritual name.
    """
    tokens = rest.split()
    name_parts: list[str] = []
    invite_names: list[str] = []
    kwargs: dict[str, str] = {}
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token.startswith("invite="):
            invite_names = [n.strip() for n in token[7:].split(",") if n.strip()]
            index += 1
        elif "=" in token and not token.startswith("="):
            key, _, val = token.partition("=")
            # Consume any following tokens that are not themselves key=value pairs
            # (trailing-value semantics: writeup=<narrative> spans remaining tokens).
            j = index + 1
            trailing: list[str] = []
            while j < len(tokens) and "=" not in tokens[j]:
                trailing.append(tokens[j])
                j += 1
            if trailing:
                val = " ".join([val, *trailing]).strip()
                index = j
            else:
                index += 1
            kwargs[key] = val
        else:
            name_parts.append(token)
            index += 1
    return " ".join(name_parts).strip(), invite_names, kwargs


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
        ``ritual cancel <id>``                           — cancel a pending session (initiator only)
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
                elif first == "cancel":  # noqa: STRING_LITERAL
                    self._handle_cancel(rest)
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

    def _handle_draft(self, rest: str) -> None:
        """Draft a multi-participant session: ``draft <name> invite=<char>[,<char>]``."""
        from datetime import timedelta  # noqa: PLC0415

        from django.utils import timezone  # noqa: PLC0415

        from commands.ritual_adapters import get_adapter  # noqa: PLC0415
        from world.magic.constants import (  # noqa: PLC0415
            ParticipationRule,
            RitualExecutionKind,
        )
        from world.magic.exceptions import (  # noqa: PLC0415
            ParticipantCountError,
            RitualSessionError,
        )
        from world.magic.models import Ritual  # noqa: PLC0415
        from world.magic.services.sessions import draft_session  # noqa: PLC0415

        name, invite_names, kwargs = _tokenize_draft_args(rest)

        usage = (
            "Usage: ritual draft <ritual_name> invite=<character>[,<character>]\n"
            "       [role=sinner|sineater resonance=<name> [writeup=<narrative>]]"
        )
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
            invitee_sheet = target.character_sheet
            if invitee_sheet is None:
                msg = f"'{invite_name}' has no character sheet."
                raise CommandError(msg)
            invitees.append(invitee_sheet)

        initiator_sheet = self.caller.sheet_data
        parse = get_adapter(ritual).parse_draft(kwargs=kwargs, caller=self.caller)

        try:
            session = draft_session(
                ritual=ritual,
                initiator=initiator_sheet,
                proposed_terms="",
                session_kwargs=parse.session_kwargs,
                invitee_sheets=invitees,
                session_references=parse.session_references,
                initiator_participant_kwargs=parse.initiator_participant_kwargs,
                initiator_references=parse.initiator_references,
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
        from commands.ritual_adapters import get_adapter  # noqa: PLC0415
        from world.magic.exceptions import SessionNotInPendingError  # noqa: PLC0415
        from world.magic.models.sessions import RitualSessionParticipant  # noqa: PLC0415
        from world.magic.services.sessions import accept_session  # noqa: PLC0415

        session_id = self._parse_session_id(
            rest, "Usage: ritual join <session_id> [role=sinner|sineater]"
        )
        # Consume trailing non-key=value tokens into a key's value so that
        # multi-word names (e.g. ``role=Iron Warden``) are captured in full.
        # Mirrors ``_tokenize_draft_args`` trailing-value semantics.
        kwargs: dict[str, str] = {}
        tokens = rest.split()[1:]
        index = 0
        while index < len(tokens):
            token = tokens[index]
            if "=" in token and not token.startswith("="):
                key, _, val = token.partition("=")
                j = index + 1
                trailing: list[str] = []
                while j < len(tokens) and "=" not in tokens[j]:
                    trailing.append(tokens[j])
                    j += 1
                if trailing:
                    val = " ".join([val, *trailing]).strip()
                    index = j
                else:
                    index += 1
                kwargs[key] = val
            else:
                index += 1

        sheet = self.caller.sheet_data
        participant = (
            RitualSessionParticipant.objects.filter(
                session_id=session_id,
                character_sheet=sheet,
            )
            .select_related("session__ritual")
            .first()
        )
        if participant is None:
            msg = f"You are not an invited participant of session #{session_id}."
            raise CommandError(msg)
        parse = get_adapter(participant.session.ritual).parse_join(
            kwargs=kwargs, caller=self.caller
        )
        try:
            accept_session(
                participant=participant,
                participant_kwargs=parse.participant_kwargs,
                references=parse.references,
            )
        except SessionNotInPendingError:
            msg = f"You have already responded to session #{session_id}."
            raise CommandError(msg) from None
        if self._maybe_auto_fire(participant, session_id):
            return
        self.caller.msg(f"You have joined ritual session #{session_id}.")

    def _maybe_auto_fire(self, participant: Any, session_id: int) -> bool:
        """Auto-fire *participant*'s session if the adapter says to; return True if handled.

        Sends a completion or error message and returns True so ``_handle_join`` can
        return early.  Returns False when the adapter says not to auto-fire, leaving
        the normal "You have joined" message path intact.
        """
        from commands.ritual_adapters import get_adapter  # noqa: PLC0415

        adapter = get_adapter(participant.session.ritual)
        if not adapter.should_auto_fire(session=participant.session):
            return False
        from world.magic.exceptions import ThresholdNotMetError  # noqa: PLC0415
        from world.magic.services.sessions import fire_session  # noqa: PLC0415
        from world.progression.exceptions import ClassLevelAdvancementError  # noqa: PLC0415

        try:
            fire_session(session=participant.session)
        except ThresholdNotMetError:
            self.caller.msg(f"You have spoken; the rite awaits the others (session #{session_id}).")
            return True
        except ClassLevelAdvancementError as exc:
            raise CommandError(_advancement_error_message(exc)) from exc
        self.caller.msg(f"The rite is complete — session #{session_id}.")
        return True

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
        from world.progression.exceptions import ClassLevelAdvancementError  # noqa: PLC0415

        try:
            fire_session(session=session)
        except ThresholdNotMetError:
            msg = f"Session #{session_id} cannot fire yet — not all participants have responded."
            raise CommandError(msg) from None
        except ClassLevelAdvancementError as exc:
            raise CommandError(_advancement_error_message(exc)) from exc
        self.caller.msg(f"Ritual session #{session_id} has been fired. The ritual is complete.")

    def _handle_cancel(self, rest: str) -> None:
        """Cancel a pending session (initiator only): ``cancel <id>``."""
        from world.magic.models.sessions import RitualSession  # noqa: PLC0415
        from world.magic.services.sessions import cancel_session  # noqa: PLC0415

        session_id = self._parse_session_id(rest, "Usage: ritual cancel <session_id>")
        sheet = self.caller.sheet_data
        session = RitualSession.objects.filter(pk=session_id, initiator=sheet).first()
        if session is None:
            msg = f"Session #{session_id} not found or you are not its initiator."
            raise CommandError(msg)
        cancel_session(session=session)
        self.caller.msg(f"Ritual session #{session_id} has been cancelled.")

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

        tradition_id = raw_kwargs.pop("tradition_id", None)
        if tradition_id is not None:
            from world.magic.models import Tradition  # noqa: PLC0415

            tradition = Tradition.objects.filter(pk=tradition_id, is_active=True).first()
            if tradition is None:
                msg = f"No active tradition with id {tradition_id}."
                raise CommandError(msg)
            service_kwargs["tradition"] = tradition

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
            instance = obj.item_instance_or_none
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
