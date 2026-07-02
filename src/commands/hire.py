"""Telnet face of the NPC-service hire/commission loop (#1493).

Thin command: parses subverbs, manages the ephemeral ``InteractionSession`` in
``caller.session.ndb.npc_interaction``, and delegates each operation to the
matching registry Action so telnet players reach the same seam as the web.
"""

from __future__ import annotations

from typing import Any, ClassVar

from actions.definitions.npc_services import (
    end_npc_interaction,
    resolve_npc_offer,
    start_npc_interaction,
)
from commands.command import ArxCommand
from commands.exceptions import CommandError
from world.npc_services.models import NPCRole
from world.npc_services.services import serialize_npc_session_state
from world.scenes.models import Persona


class CmdHire(ArxCommand):
    """Hire or commission services from an NPC.

    Usage:
        hire                              — show current interaction and offers
        hire <role name or id>           — start an interaction with that NPC role
        hire <role name or id> as <npc>  — start an interaction with a specific named NPC
        hire offer <id>                  — resolve an available offer
        hire end                         — end the current interaction

    The optional ``as <npc>`` clause selects a named Persona for class-2+ NPCs.
    It resolves the name the same way other targeted commands do (``self.caller.search``).

    ``hire`` is intentionally a single-word, domain-specific key — the verb only
    makes sense for NPC-service transactions and mirrors other economy/action verbs
    such as ``cast`` / ``clash`` / ``flee``. Namespacing it behind ``npc`` would add
    friction without reducing collision risk.
    """

    key = "hire"
    aliases: ClassVar[list[str]] = []
    locks = "cmd:all()"
    help_category = "General"

    _SESSION_KEY = "npc_interaction"

    _SUBVERB_END = "end"
    _SUBVERB_OFFER = "offer"

    def func(self) -> None:
        """Route subverbs; bare ``hire`` shows the status hub."""
        try:
            raw = (self.args or "").strip()
            if not raw:
                self._show_status_hub()
                return

            parts = raw.split(maxsplit=1)
            first = parts[0].lower()
            rest = parts[1].strip() if len(parts) > 1 else ""

            if first == self._SUBVERB_END:
                self._do_end()
            elif first == self._SUBVERB_OFFER:
                self._do_offer(rest)
            else:
                self._do_start(raw)
        except CommandError as err:
            self.msg(str(err))

    def _session(self) -> Any | None:
        """Return the in-flight InteractionSession, if any."""
        return getattr(self.caller.session.ndb, self._SESSION_KEY, None)

    def _set_session(self, session: Any) -> None:
        setattr(self.caller.session.ndb, self._SESSION_KEY, session)

    def _clear_session(self) -> None:
        setattr(self.caller.session.ndb, self._SESSION_KEY, None)

    def _parse_start_args(self, args: str) -> tuple[str, str | None]:
        """Split ``hire <role> [as <persona>]`` into role query and persona name."""
        clause = " as "
        idx = args.lower().find(clause)
        if idx != -1:
            role = args[:idx].strip()
            persona = args[idx + len(clause) :].strip()
            return role, persona or None
        return args, None

    def _resolve_persona_id(self, name: str | None) -> int | None:
        """Use ``self.caller.search`` to turn a Persona name into a primary-key id."""
        if not name:
            return None
        target = self.caller.search(name)
        if not target or not isinstance(target, Persona):
            msg = f"Could not find persona '{name}'."
            raise CommandError(msg)
        return target.pk

    def _do_start(self, args: str) -> None:
        if self._session() is not None:
            self.msg("You already have an interaction in progress. Use 'hire end' first.")
            return
        role_query, persona_name = self._parse_start_args(args)
        # Prefer a Functionary standing in this room (#1766) — that's the "walk up to the
        # NPC who's here" path. Fall back to a global role lookup so staff/tests can still
        # reach a role by name from anywhere.
        functionary = self._functionary_here(role_query)
        if functionary is not None:
            role: NPCRole = functionary.role
            display = functionary.display_name
        else:
            role = self.resolve_by_name_or_id(
                self._role_model(),
                role_query,
                not_found_msg="No one like that is here, and no NPC role by that name or id.",
            )
            display = role.name
        try:
            npc_persona_id = self._resolve_persona_id(persona_name)
        except CommandError as err:
            self.msg(str(err))
            return
        result = start_npc_interaction.run(
            actor=self.caller,
            role_id=role.pk,
            npc_persona_id=npc_persona_id,
        )
        if not result.success:
            # The action swallows MissingPrimaryPersonaError and flags it via
            # invariant_breach; in all failure cases, surface the message and stop cleanly.
            self.msg(result.message)
            return
        self._set_session(result.data["session"])
        self.msg(f"You begin speaking with {display}.")
        self._show_offers(result.data["session"])

    def _functionary_here(self, role_query: str) -> Any | None:
        """Resolve a Functionary matching *role_query* standing in the caller's room (#1766)."""
        from world.npc_services.functionaries import functionary_in_location  # noqa: PLC0415

        return functionary_in_location(self.caller.location, role_query)

    def _functionaries_here(self) -> list[str]:
        """Display names of active functionaries standing in the caller's room (#1766)."""
        from world.npc_services.functionaries import functionaries_in_location  # noqa: PLC0415

        return [f.display_name for f in functionaries_in_location(self.caller.location)]

    def _do_offer(self, args: str) -> None:
        session = self._session()
        if session is None:
            self.msg("No interaction is in progress.")
            return
        # #1770 PR4: `hire offer <id> acknowledge_risk=yes` is phase two of
        # the risky-mission opt-in (the gate's prompt names the token).
        first, _, rest = args.partition(" ")
        acknowledge_risk = rest.strip().lower() in {"acknowledge_risk=yes", "acknowledge_risk=y"}
        if acknowledge_risk:
            args = first
        if not args.isdigit():
            self.msg("Usage: hire offer <offer id> [acknowledge_risk=yes]")
            return
        offer_id = int(args)
        result = resolve_npc_offer.run(
            actor=self.caller,
            session=session,
            offer_id=offer_id,
            acknowledge_risk=acknowledge_risk,
        )
        if not result.success:
            self.msg(result.message)
            return
        if result.data["session"].closed:
            self._clear_session()
        else:
            self._set_session(result.data["session"])
        self.msg(result.message)
        if not result.data["session"].closed:
            self._show_offers(result.data["session"])

    def _do_end(self) -> None:
        session = self._session()
        if session is None:
            self.msg("No interaction is in progress.")
            return
        result = end_npc_interaction.run(actor=self.caller, session=session)
        if not result.success:
            self.msg(result.message)
            return
        self._clear_session()
        self.msg("You conclude the conversation.")

    def _show_status_hub(self) -> None:
        session = self._session()
        if session is None:
            lines = ["No interaction in progress. Use 'hire <name>' to start one."]
            here = self._functionaries_here()
            if here:
                lines.append("|wHere:|n " + ", ".join(here))
            self.msg("\n".join(lines))
            return
        self.msg(f"Speaking with {session.role.name} — rapport {session.current_rapport}.")
        self._show_offers(session)

    def _show_offers(self, session: Any) -> None:
        state = serialize_npc_session_state(session)
        lines = ["|wAvailable offers:|n"]
        for offer in state["available_offers"]:
            marker = " (final)" if offer["is_final"] else ""
            lines.append(f"  [#{offer['id']}] {offer['label']}{marker} [{offer['kind']}]")
        self.msg("\n".join(lines))

    def _role_model(self) -> type[NPCRole]:
        return NPCRole
