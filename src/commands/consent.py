"""Telnet consent flow — thin shells over the consent service (#1337).

Targeted social actions are an inherently two-party protocol: the initiator
opens a PENDING ``SceneActionRequest`` (this base); the target accepts/denies
via ``CmdAccept``/``CmdDeny`` (Task 6). Telnet calls the SAME service functions
the web viewset calls (``create_action_request`` / ``respond_to_action_request``)
— convergence at the service seam, not ``action.run()``.

Convergence is at the **service seam**, not the resolution. The web viewset
resolves ``scene`` / ``initiator_persona`` / ``target_persona`` from explicit
ids in the POST payload (the web client already picked which face it is acting
as). Telnet has no payload, so it *derives* the same three objects from the
caller's location and a typed target name — scene via the location's active
scene, personas via ``active_persona_for_sheet`` (the caller's currently
presented face). The two paths therefore differ in how they obtain the
arguments, but hand the identical
``create_action_request(scene, initiator_persona, target_persona, action_key)``
call to the shared service — which owns all consent logic.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from commands.command import ArxCommand
from commands.exceptions import CommandError
from world.scenes.action_constants import ActionRequestStatus, ConsentDecision
from world.scenes.action_models import SceneActionRequest

if TYPE_CHECKING:
    from world.scenes.models import Persona, Scene


class ConsentRequestCommand(ArxCommand):
    """Base for telnet commands that open a consent request.

    Subclasses set ``action_key`` (the registry action key, e.g. "intimidate").
    Resolves the caller's active scene + persona and the named target's persona,
    then calls ``create_action_request`` — the same service the consent viewset
    calls. All consent logic stays in the service; this is a thin shell.

    Usage:
        <key> <character>
    """

    action_key: ClassVar[str] = ""
    locks = "cmd:all()"
    action = None

    def func(self) -> None:
        from world.scenes.action_services import create_action_request  # noqa: PLC0415

        try:
            scene, initiator_persona = self._resolve_scene_and_initiator()
            target_persona = self._resolve_target_persona()
        except CommandError as err:
            self.msg(str(err))
            return

        request = create_action_request(
            scene=scene,
            initiator_persona=initiator_persona,
            target_persona=target_persona,
            action_key=self.action_key,
        )
        self.msg(
            f"You move to {self.action_key} {target_persona.name}. "
            f"Awaiting their response (request #{request.pk})."
        )

    def _resolve_scene_and_initiator(self) -> tuple[Scene, Persona]:
        """Resolve (active Scene, initiator Persona) for the caller.

        The scene is the active scene at the caller's location; the persona is
        the face the caller is currently presenting (``active_persona_for_sheet``).
        The web viewset instead takes these from explicit payload ids; telnet
        derives them. Raises ``CommandError`` on either miss so the command
        surfaces a clean message.
        """
        from world.scenes.interaction_services import _get_active_scene  # noqa: PLC0415

        scene = _get_active_scene(getattr(self.caller, "location", None))  # noqa: GETATTR_LITERAL
        if scene is None:
            msg = "You are not in an active scene."
            raise CommandError(msg)

        initiator_persona = self._persona_for(self.caller, "You have no character identity.")
        return scene, initiator_persona

    def _resolve_target_persona(self) -> Persona:
        """Resolve the target persona from ``self.args`` (a character name).

        Searches near the caller for the named character, then takes their
        active persona. Raises ``CommandError`` on a missing name or sheet.
        """
        name = self.require_args(f"Whom do you want to {self.action_key or 'target'}?")
        target = self.search_or_raise(name)
        return self._persona_for(target, f"{target} has no character identity.")

    def _persona_for(self, character: object, missing_msg: str) -> Persona:
        """Active persona for ``character``; ``CommandError(missing_msg)`` on miss."""
        from django.core.exceptions import ObjectDoesNotExist  # noqa: PLC0415

        from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415

        sheet = getattr(character, "sheet_data", None)  # noqa: GETATTR_LITERAL
        if sheet is None:
            raise CommandError(missing_msg)
        try:
            return active_persona_for_sheet(sheet)
        except ObjectDoesNotExist as exc:
            raise CommandError(missing_msg) from exc


class CmdIntimidate(ConsentRequestCommand):
    """Attempt to intimidate another character (they must accept or deny).

    Usage:
        intimidate <character>
    """

    key = "intimidate"
    action_key = "intimidate"


_NO_PENDING_MSG = "You have no pending action to respond to."


class _RespondCommand(ArxCommand):
    """Base for telnet commands that answer a pending consent request.

    Subclasses set ``decision`` (a ``ConsentDecision`` value). Resolves the
    caller's pending ``SceneActionRequest`` — by id when ``self.args`` is a
    digit, else the most-recent PENDING request targeting the caller's active
    persona — then forwards the decision to ``respond_to_action_request``, the
    SAME service the consent viewset calls. All consent + resolution logic stays
    in the service; this is a thin shell.

    Usage:
        <key> [request_id]
    """

    decision: ClassVar[str] = ""
    locks = "cmd:all()"
    action = None

    def func(self) -> None:
        from world.scenes.action_services import respond_to_action_request  # noqa: PLC0415

        request = self._resolve_pending_request()
        if request is None:
            self.msg(_NO_PENDING_MSG)
            return
        respond_to_action_request(action_request=request, decision=self.decision)
        verb = "accept" if self.decision == ConsentDecision.ACCEPT else "deny"
        self.msg(f"You {verb} the action against you.")

    def _resolve_pending_request(self) -> SceneActionRequest | None:
        """Most-recent PENDING request targeting the caller (or by id arg).

        Resolves the caller's active persona, then the latest PENDING
        ``SceneActionRequest`` whose ``target_persona`` is that persona. When
        ``self.args`` is a digit, looks up by pk (still constrained to the
        caller as target). Returns None when nothing matches.
        """
        from django.core.exceptions import ObjectDoesNotExist  # noqa: PLC0415

        from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415

        sheet = getattr(self.caller, "sheet_data", None)  # noqa: GETATTR_LITERAL
        if sheet is None:
            return None
        try:
            persona = active_persona_for_sheet(sheet)
        except ObjectDoesNotExist:
            return None
        qs = SceneActionRequest.objects.filter(
            target_persona=persona, status=ActionRequestStatus.PENDING
        )
        args = self.args.strip() if self.args else ""
        if args.isdigit():
            return qs.filter(pk=int(args)).first()
        return qs.order_by("-id").first()


class CmdAccept(_RespondCommand):
    """Accept a pending action targeting you.

    Usage:
        accept [request_id]
    """

    key = "accept"
    decision = ConsentDecision.ACCEPT


class CmdDeny(_RespondCommand):
    """Deny a pending action targeting you.

    Usage:
        deny [request_id]
    """

    key = "deny"
    decision = ConsentDecision.DENY
