"""Threads namespace command — thread management hub (#1993).

Replaces the standalone ``crossing`` command. Provides:
  threads              / threads list          — show all active threads
  threads crossing list                        — show pending crossing offers + options
  threads crossing choose <id>                 — resolve a pending offer
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from commands.command import ArxCommand

if TYPE_CHECKING:
    from world.magic.models import Thread, ThreadResonance


def _resonance_mix(thread: Thread, rows: list[ThreadResonance]) -> str:
    """The resonances a thread holds, the leading one first, each with its share in words.

    One resonance reads as its name alone. Several read as ``Fury (most), Domination (a
    fifth)``: each row's part of what went into the thread, in words and never as a number
    (#5123). A resonance with nothing imbued is left out while another has something; a thread
    with nothing imbued yet lists its resonances by name.
    """
    from world.magic.services.drift import share_in_words  # noqa: PLC0415

    if not rows:
        return thread.resonance.name if thread.resonance else "???"
    imbued = [row for row in rows if row.amount > 0]
    if not imbued:
        return ", ".join(row.resonance.name for row in rows)
    if len(imbued) == 1:
        return imbued[0].resonance.name
    total = sum(row.amount for row in imbued)
    return ", ".join(
        f"{row.resonance.name} ({share_in_words(Decimal(row.amount) * 100 / total)})"
        for row in imbued
    )


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
        from world.magic.crossing.handlers import (  # noqa: PLC0415
            _open_labels_by_relationship_id,
            anchor_label_for,
        )
        from world.magic.models import Thread, ThreadResonance  # noqa: PLC0415

        threads = list(
            Thread.objects.filter(
                owner=sheet,
                retired_at__isnull=True,
            ).select_related(
                "resonance",
                "target_trait",
                "target_facet",
                "target_technique",
                "target_mantle",
                "target_relationship__target__character",
                "target_relationship__target_companion",
                "target_capstone__relationship__target__character",
                "target_capstone__relationship__target_companion",
                "target_sanctum_details__feature_instance__room_profile__objectdb",
            )
        )
        if not threads:
            self.msg("You have no active threads.")
            return

        open_labels = _open_labels_by_relationship_id(threads)
        # One query, read fresh: a prefetch would stay on the shared Thread instances.
        rows_by_thread: dict[int, list[ThreadResonance]] = {}
        for row in ThreadResonance.objects.filter(thread__in=threads).select_related("resonance"):
            rows_by_thread.setdefault(row.thread_id, []).append(row)
        lines = ["|wYour threads:|n"]
        for thread in threads:
            anchor = anchor_label_for(thread, open_labels)
            mix = _resonance_mix(thread, rows_by_thread.get(thread.pk, []))
            lines.append(f"  {mix} {anchor} (level {thread.level})")
        self.msg("\n".join(lines))

    def _list_crossing_offers(self, sheet: object) -> None:
        from world.magic.crossing.handlers import (  # noqa: PLC0415
            _open_labels_by_relationship_id,
            anchor_label_for,
        )
        from world.magic.models.crossing import (  # noqa: PLC0415
            CrossingOption,
            PendingCrossingOffer,
        )

        offers = list(
            PendingCrossingOffer.objects.filter(thread__owner=sheet).select_related(
                "thread__resonance",
                "thread__target_trait",
                "thread__target_facet",
                "thread__target_mantle",
                "thread__target_relationship__target__character",
                "thread__target_relationship__target_companion",
                "thread__target_capstone__relationship__target__character",
                "thread__target_capstone__relationship__target_companion",
                "thread__target_sanctum_details__feature_instance__room_profile__objectdb",
            )
        )
        if not offers:
            self.msg("You have no pending crossing offers.")
            return
        open_labels = _open_labels_by_relationship_id(offer.thread for offer in offers)
        for offer in offers:
            anchor_label = anchor_label_for(offer.thread, open_labels)
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
