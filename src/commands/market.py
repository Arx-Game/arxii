"""Telnet ``market`` command family (#2066).

Browse is a thin read over the market services; every mutation dispatches the
matching REGISTRY action — the same seam the web market center uses. No
business logic in the command.

Grammar:
  market                       — stalls + listings in your current square
  market/buy <listing-id>      — buy NPC stock
  market/buyware <listing-id>  — buy an unfinished PC ware
  market/list <stall-id>=<item-id>,<price>   — list your unfinished craftwork
  market/finish <pass-id>=<name>;<description> — finish a purchased ware
  market/offer <recipe kind>=<fee>            — set your service offer here
  market/commission <offer-id>=<item-id>,<target-id> — craft via a service
"""

from __future__ import annotations

from typing import Any

from commands.command import ArxCommand
from commands.exceptions import CommandError

_USAGE = (
    "Usage:\n"
    "  market  ·  market/buy <listing-id>  ·  market/buyware <listing-id>\n"
    "  market/list <stall-id>=<item-id>,<price>\n"
    "  market/finish <pass-id>=<name>;<description>\n"
    "  market/offer <recipe kind>=<fee>\n"
    "  market/commission <offer-id>=<item-id>,<target-id>"
)


class CmdMarket(ArxCommand):
    """Trade in the market square — stock, unfinished wares, crafting services."""

    key = "market"
    locks = "cmd:all()"
    help_category = "Economy"
    action = None  # routes to multiple actions

    def func(self) -> None:
        try:
            self._dispatch()
        except CommandError as err:
            self.msg(str(err))

    def _dispatch(self) -> None:
        switches = {s.lower() for s in (self.switches or [])}
        args = (self.args or "").strip()
        if not switches:
            self._browse()
            return
        handlers = {
            "buy": self._buy_stock,
            "buyware": self._buy_ware,
            "list": self._list_ware,
            "finish": self._finish,
            "offer": self._offer,
            "commission": self._commission,
        }
        for switch in switches:
            handler = handlers.get(switch)
            if handler is not None:
                handler(args)
                return
        raise CommandError(_USAGE)

    def _run(self, action_key: str, **kwargs: Any) -> None:
        from actions.registry import get_action  # noqa: PLC0415

        action = get_action(action_key)
        result = action.run(actor=self.caller, **kwargs)
        self.msg(result.message)

    def _browse(self) -> None:
        from evennia_extensions.models import RoomProfile  # noqa: PLC0415
        from world.items.market.models import MarketSquare  # noqa: PLC0415

        location = self.caller.location
        profile = (
            RoomProfile.objects.filter(objectdb=location).select_related("area").first()
            if location
            else None
        )
        square = None
        if profile is not None and profile.area_id is not None:
            square = MarketSquare.objects.filter(area=profile.area).first()
        if square is None:
            self.msg("There is no market square here.")
            return
        lines = [f"|w{square.name}|n"]
        for stall in square.stalls.all():
            lines.append(f"  |c{stall.name}|n (stall #{stall.pk})")
            stock_rows = stall.stock_listings.filter(is_active=True).select_related("template")
            lines.extend(
                f"    [{stock.pk}] {stock.template.name} — {stock.price}c" for stock in stock_rows
            )
            ware_rows = stall.ware_listings.filter(sold_at__isnull=True).select_related(
                "item_instance"
            )
            lines.extend(
                f"    [{ware.pk}] {ware.item_instance.display_name} — {ware.price}c "
                "(unfinished — you name and describe it)"
                for ware in ware_rows
            )
        self.msg("\n".join(lines))

    def _buy_stock(self, args: str) -> None:
        if not args.isdigit():
            msg = "Usage: market/buy <listing-id>"
            raise CommandError(msg)
        self._run("market_buy_stock", listing_id=int(args))

    def _buy_ware(self, args: str) -> None:
        if not args.isdigit():
            msg = "Usage: market/buyware <listing-id>"
            raise CommandError(msg)
        self._run("market_buy_ware", listing_id=int(args))

    def _list_ware(self, args: str) -> None:
        try:
            stall_part, rest = args.split("=", 1)
            item_part, price_part = rest.split(",", 1)
            stall_id, item_id, price = int(stall_part), int(item_part), int(price_part)
        except ValueError as exc:
            msg = "Usage: market/list <stall-id>=<item-id>,<price>"
            raise CommandError(msg) from exc
        self._run("market_list_ware", stall_id=stall_id, item_instance_id=item_id, price=price)

    def _finish(self, args: str) -> None:
        try:
            pass_part, rest = args.split("=", 1)
            name, _, description = rest.partition(";")
        except ValueError as exc:
            msg = "Usage: market/finish <pass-id>=<name>;<description>"
            raise CommandError(msg) from exc
        self._run(
            "market_finish_ware",
            finishing_pass_id=int(pass_part),
            item_name=name.strip(),
            description=description.strip(),
        )

    def _offer(self, args: str) -> None:
        try:
            kind, fee = args.split("=", 1)
        except ValueError as exc:
            msg = "Usage: market/offer <recipe kind>=<fee>"
            raise CommandError(msg) from exc
        self._run("market_set_service_offer", recipe_kind=kind.strip(), fee=int(fee.strip()))

    def _commission(self, args: str) -> None:
        try:
            offer_part, rest = args.split("=", 1)
            item_part, target_part = rest.split(",", 1)
        except ValueError as exc:
            msg = "Usage: market/commission <offer-id>=<item-id>,<target-id>"
            raise CommandError(msg) from exc
        self._run(
            "market_service_craft",
            offer_id=int(offer_part),
            item_instance_id=int(item_part),
            target_id=int(target_part),
        )
