"""
Input functions

Input functions are always called from the client (they handle server
input, hence the name).

This module is loaded by being included in the
`settings.INPUT_FUNC_MODULES` tuple.

All *global functions* included in this module are considered
input-handler functions and can be called by the client to handle
input.

An input function must have the following call signature:

    cmdname(session, *args, **kwargs)

Where session will be the active session and *args, **kwargs are extra
incoming arguments and keyword properties.

A special command is the "default" command, which is will be called
when no other cmdname matches. It also receives the non-found cmdname
as argument.

    default(session, cmdname, *args, **kwargs)

"""

import time
from typing import cast
import uuid

from django.core.exceptions import ObjectDoesNotExist
from evennia.server.inputfuncs import text as _evennia_text

from server.conf.mush_markup import normalize_mush_markup
from web.webclient.message_types import TextFrameOption, WebsocketMessageType

# def oob_echo(session, *args, **kwargs):
#     """
#     Example echo function. Echoes args, kwargs sent to it.
#
#     Args:
#         session (Session): The Session to receive the echo.
#         args (list of str): Echo text.
#         kwargs (dict of str, optional): Keyed echo text
#
#     """
#     session.msg(oob=("echo", args, kwargs))
#
#
# def default(session, cmdname, *args, **kwargs):
#     """
#     Handles commands without a matching inputhandler func.
#
#     Args:
#         session (Session): The active Session.
#         cmdname (str): The (unmatched) command name
#         args, kwargs (any): Arguments to function.
#
#     """
#     pass


def text(session, *args, **kwargs):
    """Telnet input adapter, and the staff console's tag (#3857).

    Telnet is line-oriented, so ``%r`` is how MU* players embed a newline into a
    single line of input. Only telnet-family sessions are rewritten; websocket /
    ajax sessions (the React frontend, which sends real newlines and dispatches
    via ``execute_action``) pass through untouched. We then delegate to Evennia's
    default ``text`` handler rather than re-implementing command handling.

    A line the web client sends from its staff Commands mode carries
    ``console=True`` (#3857). While Evennia runs that line, the session's
    ``ndb.text_frame_options`` is set to ``{"console": True}`` so
    ``ServerSession.data_out`` merges that option into every ``text`` frame
    it sends; the client routes those to its console sheet and never to the
    column. Command execution is synchronous for the commands this exists
    for; output a command schedules for later is not tagged and lands where
    it always did.
    """
    console = bool(kwargs.pop(TextFrameOption.CONSOLE.value, False))
    if args and str(session.protocol_key or "").startswith("telnet"):
        args = (normalize_mush_markup(args[0]), *args[1:])
    if not console:
        _evennia_text(session, *args, **kwargs)
        return
    # The slot has more than one writer (``Character.at_post_puppet`` is the
    # other), so the previous value is restored rather than cleared.
    previous = session.ndb.text_frame_options
    session.ndb.text_frame_options = {TextFrameOption.CONSOLE.value: True}
    try:
        _evennia_text(session, *args, **kwargs)
    finally:
        session.ndb.text_frame_options = previous


PUPPET_COMMAND = WebsocketMessageType.PUPPET.value


def _puppet_error(session, error: str) -> None:
    session.msg(command_error={"error": error, "command": PUPPET_COMMAND})


def puppet(session, *args, **kwargs):  # noqa: ARG001 - Evennia's inputfunc signature
    """The web client's puppet handshake (#3933).

    ``["puppet", [], {"character": name}]`` replaces the ``@ic <name>`` line the
    client used to send on every socket open. It reaches the same idempotent
    ``Account.puppet_character_in_session`` and sends no text: success is the
    ``puppet_changed`` broadcast that puppeting already emits, a refusal is a
    ``command_error`` frame. Telnet keeps ``@ic``.
    """
    character = kwargs.get("character")
    account = session.account
    if account is None:
        _puppet_error(session, "Not logged in.")
        return
    if not isinstance(character, str) or not character.strip():
        _puppet_error(session, "Which character?")
        return
    wanted = character.strip().lower()
    matches = [char for char in account.get_available_characters() if char.key.lower() == wanted]
    if len(matches) != 1:
        _puppet_error(session, f"Character '{character.strip()}' is not one of yours.")
        return
    ok, message = account.puppet_character_in_session(matches[0], session)
    if not ok:
        _puppet_error(session, message)


_RESYNC_REQUEST_ID_LENGTH = 36
_RESYNC_RATE_LIMIT_SECONDS = 5.0
_RESYNC_REPLAY_TTL_SECONDS = 300.0
_RESYNC_REPLAY_MAX_ENTRIES = 32
_RESYNC_RATE_LIMITED_CODE = "rate_limited"


def _canonical_resync_request_id(value: object) -> str | None:
    """Return only the canonical UUID wire form used for resync correlation."""
    if not isinstance(value, str) or len(value) != _RESYNC_REQUEST_ID_LENGTH:
        return None
    try:
        parsed = uuid.UUID(value)
    except ValueError:
        return None
    canonical = str(parsed)
    return canonical if value == canonical else None


def _send_resync_error(
    session,
    request_id: str | None,
    code: str,
    retry_after_ms: int | None = None,
) -> None:
    """Send a bounded requester-only resync error frame."""
    payload = {"client_request_id": request_id, "code": code}
    if code == _RESYNC_RATE_LIMITED_CODE:
        payload["retry_after_ms"] = retry_after_ms
    session.msg(state_resync_error=((), payload))


def request_room_state(session, *args, **kwargs):  # noqa: C901, PLR0912
    """Request a full viewer-bound room-state snapshot on this websocket.

    The Evennia portal passes the third frame element as direct keyword
    arguments. Only the canonical ``client_request_id`` field is accepted.
    """
    if args or set(kwargs) != {"client_request_id"}:
        _send_resync_error(session, None, "invalid_request")
        return
    request_id = _canonical_resync_request_id(kwargs.get("client_request_id"))
    if request_id is None:
        _send_resync_error(session, None, "invalid_request")
        return

    actor = session.puppet
    if actor is None:
        _send_resync_error(session, request_id, "not_puppeted")
        return
    if not actor.has_account:
        _send_resync_error(session, request_id, "not_authenticated")
        return
    if actor.location is None:
        _send_resync_error(session, request_id, "no_location")
        return

    now = time.monotonic()
    try:
        replay_cache = session.ndb.room_state_resync_replay
    except AttributeError:
        replay_cache = {}
        session.ndb.room_state_resync_replay = replay_cache
    expired = [
        key for key, seen_at in replay_cache.items() if now - seen_at >= _RESYNC_REPLAY_TTL_SECONDS
    ]
    for key in expired:
        del replay_cache[key]
    if request_id in replay_cache:
        _send_resync_error(session, request_id, "duplicate_request")
        return
    try:
        last_accepted = session.ndb.room_state_resync_last_accepted
    except AttributeError:
        last_accepted = None
    if last_accepted is not None and now - last_accepted < _RESYNC_RATE_LIMIT_SECONDS:
        retry_after_ms = int((_RESYNC_RATE_LIMIT_SECONDS - (now - last_accepted)) * 1000)
        _send_resync_error(session, request_id, "rate_limited", retry_after_ms)
        return

    # Reserve atomically before expensive serialization. Even a failed send
    # consumes this reservation, preventing concurrent bypasses.
    replay_cache[request_id] = now
    while len(replay_cache) > _RESYNC_REPLAY_MAX_ENTRIES:
        oldest = min(replay_cache, key=replay_cache.get)
        del replay_cache[oldest]
    session.ndb.room_state_resync_last_accepted = now

    try:
        result = actor.send_room_state(session=session, resync_request_id=request_id)
    except (AttributeError, TypeError, ValueError, ObjectDoesNotExist):
        _send_resync_error(session, request_id, "serialization_failed")
        return
    if not result.sent:
        _send_resync_error(session, request_id, result.code or "send_failed")
        return
    if session.puppet is not actor or session not in actor.sessions.all():
        _send_resync_error(session, request_id, "session_rebound")
        return
    session.msg(
        state_resync=(
            (),
            {
                "client_request_id": request_id,
                "state_epoch": result.state_epoch,
                "state_sequence": result.state_sequence,
                "room_dbref": result.room_dbref,
                "room_id": result.room_id,
                "scene_id": result.scene_id,
            },
        )
    )


def _build_action_ref(kwargs: dict) -> object:
    """Build an ``ActionRef`` from the inbound payload, or return an error string.

    Accepts both shapes and normalises to a single ``ActionRef``:
    - Unified: ``{ref: {backend, ...}, kwargs: {...}}``
    - Legacy: ``{action: key, kwargs: {...}}``

    Returns an ``ActionRef`` on success, or a plain ``str`` error message.
    """
    from actions.constants import ActionBackend  # noqa: PLC0415
    from actions.errors import ActionDispatchError  # noqa: PLC0415
    from actions.types import ActionRef  # noqa: PLC0415

    unknown_err = ActionDispatchError(ActionDispatchError.UNKNOWN_ACTION_REF).user_message

    ref_dict: dict | None = kwargs.get("ref")
    action_key: str | None = kwargs.get("action")

    if ref_dict is not None:
        try:
            backend = ActionBackend(ref_dict.get("backend", ""))
        except ValueError:
            return unknown_err
        try:
            return ActionRef(
                backend=backend,
                challenge_instance_id=ref_dict.get("challenge_instance_id"),
                approach_id=ref_dict.get("approach_id"),
                technique_id=ref_dict.get("technique_id"),
                registry_key=ref_dict.get("registry_key"),
                position_id=ref_dict.get("position_id"),
                application_id=ref_dict.get("application_id"),
                target_object_id=ref_dict.get("target_object_id"),
            )
        except ValueError:
            return unknown_err

    if action_key:
        return ActionRef(backend=ActionBackend.REGISTRY, registry_key=action_key)

    return "No action specified."


def _resolve_registry_kwargs(ref: object, raw_kwargs: dict, actor: object) -> "dict | str":
    """Resolve ObjectDB ``*_id`` kwargs for a REGISTRY ref.

    For REGISTRY refs the ``Action`` object is interrogated for its
    ``objectdb_target_kwargs`` set; matching ``<name>_id`` integer kwargs are
    resolved to ``ObjectDB`` instances.  Non-REGISTRY refs pass kwargs through
    unchanged (no contract).

    Resolution is **scoped to objects the actor can perceive** — the same
    perception/concealment gate the actions' prerequisites enforce
    (``_is_visible_to``, which delegates to ``can_perceive``, #1225). A pk the
    actor can't perceive returns the *same* "Object not found" error as a
    non-existent pk, so a client cannot probe arbitrary object existence by pk
    (#1226). Every registry objectdb-target is a co-located-and-perceivable or
    held object, so this rejects nothing a prerequisite would have let through.

    Returns the resolved kwargs dict on success, or an error string on failure
    (action not found, or a target pk that doesn't exist / isn't perceivable).

    ``ref`` is typed as ``object`` because all ``actions.*`` imports are deferred
    in this Evennia conf module; the concrete type is ``ActionRef``.
    """
    from evennia.objects.models import ObjectDB  # noqa: PLC0415

    from actions.constants import ActionBackend  # noqa: PLC0415
    from actions.prerequisites import _is_visible_to  # noqa: PLC0415
    from actions.registry import get_action  # noqa: PLC0415
    from actions.types import ActionRef  # noqa: PLC0415

    typed_ref = cast("ActionRef", ref)
    if typed_ref.backend != ActionBackend.REGISTRY:
        return dict(raw_kwargs)

    registry_key: str = typed_ref.registry_key or ""
    action_obj = get_action(registry_key)
    if action_obj is None:
        return f"Unknown action: {registry_key}."

    objectdb_targets = action_obj.objectdb_target_kwargs
    resolved: dict = {}
    for key, value in raw_kwargs.items():
        if key.endswith("_id") and isinstance(value, int) and key[:-3] in objectdb_targets:
            obj = ObjectDB.objects.filter(pk=value).first()
            # Out-of-scope and non-existent collapse to one error — no existence probe.
            if obj is None or not _is_visible_to(actor, obj):
                return f"Object not found: {key}={value}."
            resolved[key[:-3]] = obj
        else:
            resolved[key] = value
    return resolved


def _result_from_dispatch(dispatch_result: object) -> "tuple[str | None, dict | None]":
    """Extract ``(message, data)`` from a ``DispatchResult`` detail object.

    Delegates to ``extract_dispatch_message_data`` so REST and WebSocket
    responses are guaranteed to be byte-identical.

    ``dispatch_result`` is typed as ``object`` because all ``actions.*`` imports
    are deferred in this Evennia conf module; the concrete type is ``DispatchResult``.
    """
    from actions.result_extraction import extract_dispatch_message_data  # noqa: PLC0415
    from actions.types import DispatchResult  # noqa: PLC0415

    typed_result = cast("DispatchResult", dispatch_result)
    return extract_dispatch_message_data(typed_result.detail)


def execute_action(session, *args, **kwargs):  # noqa: ARG001
    """Run a registered Action for the session's puppeted character.

    This is the unified web entry point for game mutations. Both telnet
    commands and the React frontend converge on ``dispatch_player_action``
    (the single write path); this inputfunc is how the frontend reaches it.
    REST stays read-only.

    Inbound payload accepts two shapes, both normalised to one dispatch path:

    Unified shape (preferred):
        ref: dict — ``{backend, registry_key?, challenge_instance_id?, approach_id?,
                       technique_id?}`` — fields required per-backend (see ActionRef).
        kwargs: dict — backend-specific action parameters.

    Legacy shape (still accepted; frontend migrates in T16):
        action: str — the registry action key (e.g. "equip", "give").
        kwargs: dict — action kwargs.

    For REGISTRY refs (both shapes), keys whose stripped name (``foo_id`` → ``foo``)
    appears in the action's ``objectdb_target_kwargs`` set are resolved from
    int → ObjectDB before dispatch.  All other kwargs pass through unchanged.

    Outbound: ``session.msg`` with
        ``type=WebsocketMessageType.ACTION_RESULT.value`` and a kwargs
        payload of ``{"success": bool, "message": str | None,
        "data": dict | None, "client_request_id": str | None}``. The
        ``client_request_id`` is echoed back unchanged from the inbound
        ``kwargs.client_request_id`` (when the caller supplied one) so a
        dispatching client can correlate this event with its own send
        instead of assuming "the next ``action_result`` on the bus is
        mine" (#3781).
    """
    from actions.errors import ActionDispatchError  # noqa: PLC0415
    from actions.player_interface import dispatch_player_action  # noqa: PLC0415
    from actions.types import ActionInterrupted  # noqa: PLC0415
    from web.webclient.message_types import WebsocketMessageType  # noqa: PLC0415

    raw_kwargs: dict = kwargs.get("kwargs") or {}
    client_request_id = raw_kwargs.get("client_request_id")
    if not isinstance(client_request_id, str):
        client_request_id = None

    def _send(success: bool, message: str | None = None, data: object = None) -> None:
        session.msg(
            type=WebsocketMessageType.ACTION_RESULT.value,
            kwargs={
                "success": success,
                "message": message,
                "data": data,
                "client_request_id": client_request_id,
            },
        )

    actor = session.puppet
    if actor is None:
        _send(False, "You must be playing a character to do that.")
        return

    ref_or_err = _build_action_ref(kwargs)
    if isinstance(ref_or_err, str):
        _send(False, ref_or_err)
        return
    ref = ref_or_err

    resolved_or_err = _resolve_registry_kwargs(ref, raw_kwargs, actor)
    if isinstance(resolved_or_err, str):
        _send(False, resolved_or_err)
        return
    resolved: dict = resolved_or_err

    try:
        dispatch_result = dispatch_player_action(actor, ref, resolved)
    except ActionDispatchError as exc:
        _send(False, exc.user_message)
        return
    except ActionInterrupted as exc:
        _send(False, str(exc) or "Action interrupted.")
        return

    if dispatch_result.deferred:
        _send(True, "Action declared for round resolution.")
        return

    message, data = _result_from_dispatch(dispatch_result)
    _send(True, message, data)
