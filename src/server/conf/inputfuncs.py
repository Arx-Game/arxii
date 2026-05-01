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


def execute_action(session, *args, **kwargs):  # noqa: ARG001 — Evennia inputfunc signature
    """Run a registered Action for the session's puppeted character.

    This is the unified web entry point for game mutations. Both telnet
    commands and the React frontend converge on ``Action.run()``; this
    inputfunc is how the frontend reaches it. REST stays read-only.

    Inbound payload (kwargs):
        action: str — the action key (e.g. "equip", "give")
        kwargs: dict — action kwargs. Keys whose stripped name (``foo_id`` →
                       ``foo``) appears in the action's ``objectdb_target_kwargs``
                       set are resolved from int → ObjectDB before dispatch.
                       All other kwargs (including non-ObjectDB id kwargs like
                       ``outfit_id``) are passed through unchanged.

    Outbound: ``session.msg`` with
        ``type=WebsocketMessageType.ACTION_RESULT.value`` and a kwargs
        payload of ``{"success": bool, "message": str | None,
        "data": dict | None}``.
    """
    from evennia.objects.models import ObjectDB  # noqa: PLC0415

    from actions.registry import get_action  # noqa: PLC0415
    from actions.types import ActionInterrupted  # noqa: PLC0415
    from web.webclient.message_types import WebsocketMessageType  # noqa: PLC0415

    def _send(success, message=None, data=None):
        session.msg(
            type=WebsocketMessageType.ACTION_RESULT.value,
            kwargs={"success": success, "message": message, "data": data},
        )

    actor = session.puppet
    if actor is None:
        _send(False, "You must be playing a character to do that.")
        return

    action_key = kwargs.get("action")
    if not action_key:
        _send(False, "No action specified.")
        return

    action = get_action(action_key)
    if action is None:
        _send(False, f"Unknown action: {action_key}.")
        return

    raw_action_kwargs = kwargs.get("kwargs") or {}
    resolved = {}
    objectdb_targets = action.objectdb_target_kwargs
    for key, value in raw_action_kwargs.items():
        if key.endswith("_id") and isinstance(value, int) and key[:-3] in objectdb_targets:
            try:
                resolved[key[:-3]] = ObjectDB.objects.get(pk=value)
            except ObjectDB.DoesNotExist:
                _send(False, f"Object not found: {key}={value}.")
                return
        else:
            resolved[key] = value

    try:
        result = action.run(actor, **resolved)
    except ActionInterrupted as exc:
        _send(False, str(exc) or "Action interrupted.")
        return

    _send(result.success, result.message, result.data)
