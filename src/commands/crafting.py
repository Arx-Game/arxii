"""Craft telnet command — the ``craft <subverb>`` namespace (#1866).

Routes ``facet``/``removefacet``/``style``/``quote`` through the crafting
Actions (``actions/definitions/crafting.py``) — the same seam the web
ItemFacetViewSet/ItemStyleCraftViewSet now use (#1866 refactor, Task 3).
No business logic here — only telnet parsing + item/facet/style resolution.
"""

from __future__ import annotations

from typing import Any

from actions.definitions.crafting import (
    AttachFacetAction,
    AttachStyleAction,
    DetachFacetAction,
)
from commands.command import ArxCommand
from commands.exceptions import CommandError

_USAGE = (
    "Usage: craft facet <name> item=<id> | craft removefacet <item_facet_id> | "
    "craft style <name> item=<id> | craft quote facet=<name>|style=<name> item=<id>"
)


def _parse_kwargs(args: str) -> dict[str, str]:
    """Parse trailing ``key=value`` tokens off ``args``; return them as a dict."""
    out: dict[str, str] = {}
    tokens = args.split()
    for token in tokens:
        if "=" in token:
            key, _, value = token.partition("=")
            out[key] = value
    return out


def _leading_text(args: str) -> str:
    """Return the tokens before the first ``key=value`` token, joined by spaces."""
    words = []
    for token in args.split():
        if "=" in token:
            break
        words.append(token)
    return " ".join(words)


class CmdCraft(ArxCommand):
    """Attach a facet or style to an item you're holding, or detach a facet.

    Usage:
        craft facet <facet name> item=<item id>
        craft removefacet <item_facet id>
        craft style <style name> item=<item id>
        craft quote facet=<name>|style=<name> item=<item id>
    """

    key = "craft"
    locks = "cmd:all()"

    def func(self) -> None:
        raw = (self.args or "").strip()
        if not raw:
            self.msg(_USAGE)
            return
        parts = raw.split(maxsplit=1)
        subverb = parts[0].lower()
        rest = parts[1].strip() if len(parts) > 1 else ""
        handler = {
            "facet": self._do_facet,
            "removefacet": self._do_removefacet,
            "style": self._do_style,
            "quote": self._do_quote,
        }.get(subverb)
        if handler is None:
            self.msg(f"Unknown craft action '{subverb}'. {_USAGE}")
            return
        try:
            handler(rest)
        except CommandError as err:
            self.msg(str(err))

    def _resolve_item_instance(self, item_id_raw: str) -> Any:
        from actions.definitions.item_helpers import resolve_item_instance  # noqa: PLC0415

        if not item_id_raw or not item_id_raw.isdigit():
            raise CommandError(_USAGE)
        obj = self.caller.search(f"#{item_id_raw}", location=self.caller)
        if not obj:
            msg = "You aren't holding that item."
            raise CommandError(msg)
        instance = resolve_item_instance(obj)
        if instance is None:
            msg = "That isn't an item."
            raise CommandError(msg)
        return instance

    def _do_facet(self, rest: str) -> None:
        from world.magic.models import Facet  # noqa: PLC0415

        kwargs = _parse_kwargs(rest)
        name = _leading_text(rest)
        item_instance = self._resolve_item_instance(kwargs.get("item", ""))
        facet = Facet.objects.filter(name__iexact=name).first()
        if facet is None:
            msg = f"No facet called '{name}'."
            raise CommandError(msg)
        result = AttachFacetAction().run(
            actor=self.caller, item_instance=item_instance, facet=facet
        )
        if result.message:
            self.msg(result.message)

    def _do_removefacet(self, rest: str) -> None:
        from world.items.models import ItemFacet  # noqa: PLC0415

        rest = rest.strip()
        if not rest.isdigit():
            msg = "Usage: craft removefacet <item_facet id>."
            raise CommandError(msg)
        item_facet = ItemFacet.objects.filter(pk=int(rest)).select_related("item_instance").first()
        if item_facet is None:
            msg = "No such attached facet."
            raise CommandError(msg)
        result = DetachFacetAction().run(actor=self.caller, item_facet=item_facet)
        if result.message:
            self.msg(result.message)

    def _do_style(self, rest: str) -> None:
        from world.items.models import Style  # noqa: PLC0415

        kwargs = _parse_kwargs(rest)
        name = _leading_text(rest)
        item_instance = self._resolve_item_instance(kwargs.get("item", ""))
        style = Style.objects.filter(name__iexact=name).first()
        if style is None:
            msg = f"No style called '{name}'."
            raise CommandError(msg)
        result = AttachStyleAction().run(
            actor=self.caller, item_instance=item_instance, style=style
        )
        if result.message:
            self.msg(result.message)

    def _do_quote(self, rest: str) -> None:
        from world.items.crafting.constants import CraftingRecipeKind  # noqa: PLC0415
        from world.items.crafting.services import build_crafting_quote  # noqa: PLC0415
        from world.items.models import Style  # noqa: PLC0415
        from world.magic.models import Facet  # noqa: PLC0415

        kwargs = _parse_kwargs(rest)
        self._resolve_item_instance(kwargs.get("item", ""))
        sheet = self.caller.sheet_data
        if "facet" in kwargs:  # noqa: STRING_LITERAL
            facet = Facet.objects.filter(name__iexact=kwargs["facet"]).first()
            if facet is None:
                msg = f"No facet called '{kwargs['facet']}'."
                raise CommandError(msg)
            quote = build_crafting_quote(
                kind=CraftingRecipeKind.FACET_ATTACH,
                crafter_character=self.caller,
                crafter_character_sheet=sheet,
                target=facet,
            )
        elif "style" in kwargs:  # noqa: STRING_LITERAL
            style = Style.objects.filter(name__iexact=kwargs["style"]).first()
            if style is None:
                msg = f"No style called '{kwargs['style']}'."
                raise CommandError(msg)
            quote = build_crafting_quote(
                kind=CraftingRecipeKind.STYLE_ATTACH,
                crafter_character=self.caller,
                crafter_character_sheet=sheet,
                target=style,
            )
        else:
            raise CommandError(_USAGE)
        self.msg(
            f"Cost: {quote.costs}. Affordable: {quote.affordable}. "
            f"Max quality tier: {quote.max_quality_tier}."
        )
