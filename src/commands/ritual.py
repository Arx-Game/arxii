"""Telnet command for performing magical rituals.

Thin telnet face of ``actions.definitions.ritual.PerformRitualAction``. Parses
``ritual <name> [key=value ...]`` into the action's kwargs. Scope: SERVICE-kind
rituals (Imbuing, Atonement) — the only kind a telnet player drives directly.
The web path uses the same action via ``RitualPerformView``.
"""

from __future__ import annotations

from typing import Any

from actions.definitions.ritual import PerformRitualAction
from commands.command import ArxCommand
from commands.exceptions import CommandError

# Telnet-friendly kwarg alias: players type ``thread=<id>`` (the pk); the action
# / service expect the resolved ``thread`` model, and the view path uses
# ``thread_id`` as the primitive key. Map the input token to ``thread_id`` here.
_THREAD_KWARG = "thread"
_THREAD_ID_KEY = "thread_id"


class CmdRitual(ArxCommand):
    """Perform a magical ritual you know.

    Telnet grammar:
        ``ritual <name>``                       — perform a ritual by name
        ``ritual <name> key=value [key=value]``  — with ritual parameters

    Example:
        ``ritual Rite of Imbuing thread=5``

    Trailing ``key=value`` tokens are ritual parameters; everything before the
    first such token is the ritual name. Carried items are offered as components
    and pruned to what the ritual requires.
    """

    key = "ritual"
    locks = "cmd:all()"
    action = PerformRitualAction()

    def resolve_action_args(self) -> dict[str, Any]:
        """Parse ``ritual <name> [k=v ...]`` into action kwargs."""
        from world.magic.constants import RitualExecutionKind  # noqa: PLC0415
        from world.magic.models import Ritual, Thread  # noqa: PLC0415

        args = self.require_args("Perform which ritual?")
        name, raw_kwargs = self._split_name_and_kwargs(args)

        ritual = Ritual.objects.filter(
            name__iexact=name,
            execution_kind=RitualExecutionKind.SERVICE,
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

        # Pass through any remaining parsed kwargs (e.g. amount) verbatim.
        service_kwargs.update(raw_kwargs)

        components = self._gather_components()
        return {"ritual": ritual, "components_provided": components, **service_kwargs}

    def _split_name_and_kwargs(self, args: str) -> tuple[str, dict[str, int]]:
        """Split into ritual name + trailing ``key=value`` int tokens.

        Tokens are whitespace-separated. The name is everything before the first
        ``key=value`` token; values that parse as ints are coerced (so ``thread=5``
        yields ``thread_id``→5 via the caller). Non-int values raise CommandError.
        """
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
                # ``thread`` is the telnet-friendly alias for the ``thread_id`` pk.
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
