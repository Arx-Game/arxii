"""Threads namespace command — thread management hub (#1993).

Replaces the standalone ``crossing`` command. Provides:
  threads              / threads list          — show all active threads
  threads crossing list                        — show pending crossing offers + options
  threads crossing choose <id>                 — resolve a pending offer
"""

from __future__ import annotations

from commands.command import ArxCommand


class CmdThreads(ArxCommand):
    """Manage your threads and resolve crossing offers.

    Usage:
      threads                      - show all your active threads
      threads list                 - same as above
      threads crossing list        - show pending crossing offers + options
      threads crossing choose <id> - resolve a pending offer by picking an option
    """

    key = "threads"
    aliases = ["thread"]
    locks = "cmd:all()"
    help_category = "Magic"

    def func(self) -> None:
        sheet = self.caller.sheet_data
        if sheet is None:
            self.msg("You don't have a character sheet.")
            return

        args = self.args.strip().split()
        if not args or args[0] == "list":  # noqa: STRING_LITERAL
            self._list_threads(sheet)
        elif args[0] == "crossing":  # noqa: STRING_LITERAL
            if len(args) < 2:  # noqa: PLR2004
                self.msg("Usage: threads crossing list | threads crossing choose <id>")
                return
            if args[1] == "list":  # noqa: STRING_LITERAL
                self._list_crossing_offers(sheet)
            elif args[1] == "choose":  # noqa: STRING_LITERAL
                if len(args) < 3:  # noqa: PLR2004
                    self.msg("Usage: threads crossing choose <option_id>")
                    return
                self._choose_crossing(sheet, args[2])
            else:
                self.msg("Usage: threads crossing list | threads crossing choose <id>")
        else:
            self.msg("Usage: threads list | threads crossing list | threads crossing choose <id>")

    def _list_threads(self, sheet: object) -> None:
        from world.magic.crossing.handlers import _anchor_label_for  # noqa: PLC0415
        from world.magic.models import Thread  # noqa: PLC0415

        threads = Thread.objects.filter(
            owner=sheet,
            retired_at__isnull=True,
        ).select_related(
            "resonance",
            "target_trait",
            "target_facet",
            "target_technique",
            "target_mantle",
            "target_relationship_track__track",
            "target_relationship_track__relationship__target__character",
            "target_capstone__relationship__target__character",
            "target_sanctum_details__feature_instance__room_profile__objectdb",
        )
        if not threads:
            self.msg("You have no active threads.")
            return

        lines = ["|wYour threads:|n"]
        for thread in threads:
            anchor = _anchor_label_for(thread)
            res_name = thread.resonance.name if thread.resonance else "???"
            display_level = thread.level // 10
            lines.append(f"  {res_name} {anchor} (level {display_level})")
        self.msg("\n".join(lines))

    def _list_crossing_offers(self, sheet: object) -> None:
        from world.magic.crossing.handlers import _anchor_label_for  # noqa: PLC0415
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
            "thread__target_sanctum_details__feature_instance__room_profile__objectdb",
        )
        if not offers:
            self.msg("You have no pending crossing offers.")
            return
        for offer in offers:
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

    def _choose_crossing(self, sheet: object, option_id_str: str) -> None:
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
