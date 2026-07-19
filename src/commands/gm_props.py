"""GM stage-prop improv telnet namespace (#2503) — the ``stage`` command.

Thin subverb router over ``dispatch_player_action``, mirroring ``CmdDefense``'s
shape (``commands/defenses.py``). No business logic lives here — the GM gate,
the curated ItemTemplate/Property name lookups, and the actual staging all live
in ``StagePropAction``/``StagePropertyAction``
(``actions/definitions/gm_props.py``), the same seam a future web "stage a
prop" button would dispatch through.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from actions.constants import ActionBackend
from commands.command import DispatchCommand
from commands.exceptions import CommandError

if TYPE_CHECKING:
    from actions.types import ActionRef

_SUBVERB_PROP = "prop"
_SUBVERB_PROPERTY = "property"

# subverb -> registry action key.
_SUBVERBS: dict[str, str] = {
    _SUBVERB_PROP: "stage_prop",
    _SUBVERB_PROPERTY: "stage_property",
}

_USAGE = "Usage: stage prop <item template name> | stage property <property name> [=<target>]."


class CmdStage(DispatchCommand):
    """GM improv: conjure a prop, or tag an object with a property, mid-scene.

    Usage:
        stage prop <item template name>
        stage property <property name> [=<target name>]
    """

    key = "stage"
    locks = "cmd:all()"

    _subverb: str = ""
    _rest: str = ""

    def func(self) -> None:
        """Route the leading subverb; bare ``stage`` shows usage."""
        raw = (self.args or "").strip()
        if not raw:
            self.msg(_USAGE)
            return
        parts = raw.split(maxsplit=1)
        self._subverb = parts[0].lower()
        self._rest = parts[1].strip() if len(parts) > 1 else ""
        if self._subverb not in _SUBVERBS:
            options = ", ".join(sorted(_SUBVERBS))
            self.msg(f"Unknown stage action '{self._subverb}'. Try: {options}.")
            return
        super().func()  # resolve_action_ref + resolve_action_args + dispatch

    def resolve_action_ref(self) -> ActionRef:
        """Build a REGISTRY ``ActionRef`` for the parsed subverb."""
        from actions.types import ActionRef  # noqa: PLC0415

        return ActionRef(backend=ActionBackend.REGISTRY, registry_key=_SUBVERBS[self._subverb])

    def resolve_action_args(self) -> dict[str, Any]:
        """Resolve the subverb's arguments into dispatch kwargs."""
        if self._subverb == _SUBVERB_PROP:
            if not self._rest:
                msg = "Usage: stage prop <item template name>."
                raise CommandError(msg)
            return {"item_template": self._rest}

        # property [=<target>]
        name_part, _, target_part = self._rest.partition("=")
        property_name = name_part.strip()
        if not property_name:
            msg = "Usage: stage property <property name> [=<target>]."
            raise CommandError(msg)
        kwargs: dict[str, Any] = {"property": property_name}
        target_name = target_part.strip()
        if target_name:
            kwargs["target"] = self.search_or_raise(target_name)
        return kwargs
