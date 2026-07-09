"""Telnet command for thread crossing choices (generalized, #1990)."""

from __future__ import annotations

from commands.command import ArxCommand


class CmdCrossing(ArxCommand):
    """Choose how your thread's resonance manifests at a crossing.

    Usage:
      crossing list          - show pending offers + available options
      crossing choose <id>  - resolve a pending offer by picking an option
    """

    key = "crossing"
    aliases = ["traitcross", "crossingchoice"]
    locks = "cmd:all()"
    help_category = "Magic"

    def func(self) -> None:
        sheet = self.caller.sheet_data
        if sheet is None:
            self.msg("You don't have a character sheet.")
            return

        args = self.args.strip().split()
        if not args or args[0] == "list":  # noqa: STRING_LITERAL
            self._list_offers(sheet)
        elif args[0] == "choose":  # noqa: STRING_LITERAL
            if len(args) < 2:  # noqa: PLR2004
                self.msg("Usage: crossing choose <option_id>")
                return
            self._choose(sheet, args[1])
        else:
            self.msg("Usage: crossing list | crossing choose <option_id>")

    def _list_offers(self, sheet: object) -> None:
        from world.magic.models.crossing import (  # noqa: PLC0415
            CrossingOption,
            PendingCrossingOffer,
        )

        offers = PendingCrossingOffer.objects.filter(thread__owner=sheet).select_related(
            "thread__resonance",
            "thread__target_trait",
            "thread__target_facet",
            "thread__target_mantle",
            "thread__target_relationship_track__track",
            "thread__target_relationship_track__relationship__target__character",
            "thread__target_capstone__relationship__target__character",
        )
        if not offers:
            self.msg("You have no pending crossing offers.")
            return
        for offer in offers:
            from world.magic.crossing.handlers import _anchor_label_for  # noqa: PLC0415

            anchor_label = _anchor_label_for(offer.thread)
            res_name = offer.thread.resonance.name if offer.thread.resonance else "???"
            self.msg(f"|wCrossing level {offer.crossing_level}|n - {res_name} {anchor_label}")
            options = CrossingOption.objects.filter(
                target_kind=offer.thread.target_kind,
                resonance=offer.thread.resonance,
                crossing_level=offer.crossing_level,
            )
            for opt in options:
                self.msg(f"  [{opt.id}] {opt.name}: {opt.description}")

    def _choose(self, sheet: object, option_id_str: str) -> None:
        from actions.definitions.crossing import (  # noqa: PLC0415
            ResolveCrossingOfferAction,
        )
        from world.magic.models.crossing import (  # noqa: PLC0415
            CrossingOption,
            PendingCrossingOffer,
        )

        try:
            option_id = int(option_id_str)
        except ValueError:
            self.msg("Option ID must be a number.")
            return

        offer = PendingCrossingOffer.objects.filter(thread__owner=sheet).first()
        if offer is None:
            self.msg("You have no pending crossing offer.")
            return

        option = CrossingOption.objects.filter(pk=option_id).first()
        if option is None:
            self.msg(f"No option with ID {option_id}.")
            return

        actor = self.caller
        action = ResolveCrossingOfferAction()
        result = action.run(actor=actor, offer=offer, option=option)
        self.msg(result.message)
