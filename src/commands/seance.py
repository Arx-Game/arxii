"""Telnet command for the seance manifestation-offer inbox (#2393).

Account-scoped, not character-scoped — the caller may have no puppeted
character at all (a retired honoree answering their own offer).
"""

from commands.command import ArxCommand

_SUBVERB_OFFERS = "offers"
_SUBVERB_LIST = "list"
_SUBVERB_ACCEPT = "accept"
_SUBVERB_DECLINE = "decline"
_BARE_SUBVERBS = frozenset({"", _SUBVERB_OFFERS, _SUBVERB_LIST})
_RESPOND_SUBVERBS = frozenset({_SUBVERB_ACCEPT, _SUBVERB_DECLINE})


class CmdSeance(ArxCommand):
    """Answer a pending seance's call to speak again.

    Usage:
        seance                    — list your pending seance offers
        seance offers             — same as bare `seance`
        seance accept <id>        — answer the seance's call
        seance decline <id>       — decline the seance's call

    A retired character's account still receives these — you don't need to
    be playing anyone to answer.
    """

    key = "seance"
    locks = "cmd:all()"
    help_category = "Social"
    action = None

    def func(self) -> None:
        from actions.definitions.ceremonies import RespondSeanceOfferAction  # noqa: PLC0415

        raw = (self.args or "").strip()
        parts = raw.split(maxsplit=1)
        subverb = parts[0].lower() if parts else _SUBVERB_OFFERS
        rest = parts[1].strip() if len(parts) > 1 else ""

        if subverb in _BARE_SUBVERBS:
            self._show_offers()
            return
        if subverb not in _RESPOND_SUBVERBS:
            self.msg("Usage: seance [offers|accept <id>|decline <id>]")
            return
        if not rest:
            self.msg(f"Usage: seance {subverb} <id>")
            return
        try:
            offer_id = int(rest)
        except ValueError:
            self.msg("That's not a valid offer id.")
            return
        result = RespondSeanceOfferAction().run(
            actor=None,
            account=self.account,
            offer_id=offer_id,
            accept=(subverb == _SUBVERB_ACCEPT),
        )
        if result.message:
            self.msg(result.message)

    def _show_offers(self) -> None:
        from world.ceremonies.services import pending_seance_offers_for_account  # noqa: PLC0415

        offers = pending_seance_offers_for_account(self.account)
        if not offers:
            self.msg("No seance is calling for you.")
            return
        lines = ["Pending seance offers:"]
        for offer in offers:
            honoree = offer.ceremony_honoree.honoree_sheet.character.db_key
            location = offer.ceremony_honoree.ceremony.location.objectdb.db_key
            lines.append(f"  [{offer.pk}] {honoree}, called at {location}")
        self.msg("\n".join(lines))
