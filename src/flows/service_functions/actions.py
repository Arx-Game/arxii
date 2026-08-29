"""Action-layer service functions (#3418)."""

from evennia.objects.models import ObjectDB


def redirect_action_target(*, payload: object, object_id: object, **kwargs: object) -> bool:
    """Redirect an in-flight action's target to a real ``ObjectDB`` (#3418).

    The action-layer counterpart to ``redirect_move``
    (``flows.service_functions.movement``, ADR-0242): ``MODIFY_PAYLOAD``'s
    ``value`` is a JSON step parameter, so it can only ever write a pk int or
    other scalar into ``payload.target`` — an authored interception that
    wants the real object (e.g. so a real action's ``execute()`` can call
    ``target.location``) must resolve the pk itself first. Mirrors
    ``redirect_move``'s no-op-on-failure convention: never raises, just
    leaves the payload's target untouched when ``object_id`` doesn't resolve.

    Args:
        payload: The ``ActionIntentPayload``; needs a ``target`` attribute.
        object_id: The pk (int, or int-like) of the object to redirect to.

    Returns:
        True if the target was redirected, False if ``object_id`` didn't
        resolve to a real object (no-op).
    """
    try:
        pk = int(object_id)  # type: ignore[call-overload]
    except (TypeError, ValueError):
        return False
    obj = ObjectDB.objects.filter(pk=pk).first()
    if obj is None:
        return False
    payload.target = obj
    return True


hooks = {
    "redirect_action_target": redirect_action_target,
}
