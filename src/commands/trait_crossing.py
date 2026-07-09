"""Telnet command for TRAIT thread crossing choices (#1989)."""

from __future__ import annotations

from commands.command import ArxCommand


class CmdTraitCrossing(ArxCommand):
    """Choose how your TRAIT thread's resonance manifests at a crossing.

    Usage:
      traitcross list          - show pending offers + available options
      traitcross choose <id>  - resolve a pending offer by picking an option
    """

    key = "traitcross"
    aliases = ["traitcrossing"]
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
                self.msg("Usage: traitcross choose <option_id>")
                return
            self._choose(sheet, args[1])
        else:
            self.msg("Usage: traitcross list | traitcross choose <option_id>")

    def _list_offers(self, sheet: object) -> None:
        from world.magic.models.trait_crossing import (  # noqa: PLC0415
            PendingTraitCrossingOffer,
            TraitCrossingOption,
        )

        offers = PendingTraitCrossingOffer.objects.filter(thread__owner=sheet).select_related(
            "thread__resonance", "thread__target_trait"
        )
        if not offers:
            self.msg("You have no pending trait crossing offers.")
            return
        for offer in offers:
            trait_name = offer.thread.target_trait.name if offer.thread.target_trait else "???"
            res_name = offer.thread.resonance.name if offer.thread.resonance else "???"
            self.msg(f"|wCrossing level {offer.crossing_level}|n - {res_name} {trait_name}")
            options = TraitCrossingOption.objects.filter(
                resonance=offer.thread.resonance,
                crossing_level=offer.crossing_level,
            )
            for opt in options:
                self.msg(f"  [{opt.id}] {opt.name}: {opt.description or opt.narrative_snippet}")

    def _choose(self, sheet: object, option_id_str: str) -> None:
        from actions.definitions.trait_crossing import (  # noqa: PLC0415
            ResolveTraitCrossingOfferAction,
        )
        from world.magic.models.trait_crossing import (  # noqa: PLC0415
            PendingTraitCrossingOffer,
            TraitCrossingOption,
        )

        try:
            option_id = int(option_id_str)
        except ValueError:
            self.msg("Option ID must be a number.")
            return

        offer = PendingTraitCrossingOffer.objects.filter(thread__owner=sheet).first()
        if offer is None:
            self.msg("You have no pending trait crossing offer.")
            return

        option = TraitCrossingOption.objects.filter(pk=option_id).first()
        if option is None:
            self.msg(f"No option with ID {option_id}.")
            return

        actor = self.caller
        action = ResolveTraitCrossingOfferAction()
        result = action.run(actor=actor, offer=offer, option=option)
        self.msg(result.message)
