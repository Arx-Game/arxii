"""Service functions related to perceiving objects."""

from typing import Any

from flows.object_states.base_state import BaseState


def get_formatted_description(
    obj: BaseState,
    mode: str = "look",
    **kwargs: Any,
) -> str:
    """Return a formatted description for ``obj``.

    Args:
        obj: State of the target object.
        mode: Display mode passed to :meth:`BaseState.return_appearance`.
        **kwargs: Extra keyword arguments for appearance helpers.

    Returns:
        The formatted description.
    """
    return obj.return_appearance(mode=mode, **kwargs)


def object_has_tag(
    obj: BaseState,
    tag: str,
    **kwargs: object,
) -> bool:
    """Return True if ``obj`` has ``tag``.

    Args:
        obj: State of the target object.
        tag: Tag name to check for.

    Returns:
        bool: True if the tag exists.
    """
    try:
        return bool(obj.obj.tags.get(tag))
    except AttributeError:
        return False


def append_to_attribute(
    obj: BaseState,
    attribute: str,
    append_text: str,
    **kwargs: Any,
) -> None:
    """Append text to an attribute on the state for ``obj``.

    Args:
        obj: State of the target object.
        attribute: Name of the attribute.
        append_text: Text to append.
        **kwargs: Additional keyword arguments.
    """
    current = getattr(obj, attribute, "")
    setattr(obj, attribute, f"{current}{append_text}")


def show_inventory(
    caller: BaseState,
    **kwargs: object,
) -> None:
    """Send the caller a list of carried items.

    Args:
        caller: State of the character.
        **kwargs: Additional keyword arguments.
    """
    items = caller.contents
    if not items:
        caller.msg("You are not carrying anything.")
        return

    names = [it.get_display_name(looker=caller) for it in items]
    text = "You are carrying: " + ", ".join(names)
    caller.msg(text)


hooks = {
    "get_formatted_description": get_formatted_description,
    "object_has_tag": object_has_tag,
    "append_to_attribute": append_to_attribute,
    "show_inventory": show_inventory,
}
