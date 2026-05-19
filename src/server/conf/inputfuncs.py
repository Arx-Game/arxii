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
            )
        except ValueError:
            return unknown_err

    if action_key:
        return ActionRef(backend=ActionBackend.REGISTRY, registry_key=action_key)

    return "No action specified."


def _resolve_registry_kwargs(ref: object, raw_kwargs: dict) -> "dict | str":
    """Resolve ObjectDB ``*_id`` kwargs for a REGISTRY ref.

    For REGISTRY refs the ``Action`` object is interrogated for its
    ``objectdb_target_kwargs`` set; matching ``<name>_id`` integer kwargs are
    resolved to ``ObjectDB`` instances.  Non-REGISTRY refs pass kwargs through
    unchanged (no contract).

    Returns the resolved kwargs dict on success, or an error string on failure
    (action not found or ObjectDB lookup failed).

    ``ref`` is typed as ``object`` because all ``actions.*`` imports are deferred
    in this Evennia conf module; the concrete type is ``ActionRef``.
    """
    from evennia.objects.models import ObjectDB  # noqa: PLC0415

    from actions.constants import ActionBackend  # noqa: PLC0415
    from actions.registry import get_action  # noqa: PLC0415
    from actions.types import ActionRef  # noqa: PLC0415

    typed_ref: ActionRef = ref  # type: ignore[assignment]
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
            try:
                resolved[key[:-3]] = ObjectDB.objects.get(pk=value)
            except ObjectDB.DoesNotExist:
                return f"Object not found: {key}={value}."
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

    typed_result: DispatchResult = dispatch_result  # type: ignore[assignment]
    return extract_dispatch_message_data(typed_result.detail)


def execute_action(session, *args, **kwargs):  # noqa: ARG001 — Evennia inputfunc signature
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
        "data": dict | None}``.
    """
    from actions.errors import ActionDispatchError  # noqa: PLC0415
    from actions.player_interface import dispatch_player_action  # noqa: PLC0415
    from actions.types import ActionInterrupted  # noqa: PLC0415
    from web.webclient.message_types import WebsocketMessageType  # noqa: PLC0415

    def _send(success: bool, message: str | None = None, data: object = None) -> None:
        session.msg(
            type=WebsocketMessageType.ACTION_RESULT.value,
            kwargs={"success": success, "message": message, "data": data},
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

    raw_kwargs: dict = kwargs.get("kwargs") or {}
    resolved_or_err = _resolve_registry_kwargs(ref, raw_kwargs)
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
