"""Telnet command for the public-conversion offer inbox (#2361).

Account-scoped, not character-scoped — mirrors commands/seance.py exactly.
Only the PC-officiated conversion route (Ratified amendment #1a) mints an
offer; the self-officiated solo route needs no consent surface at all.
"""

from commands.command import ArxCommand

_SUBVERB_OFFERS = "offers"
_SUBVERB_LIST = "list"
_SUBVERB_ACCEPT = "accept"
_SUBVERB_DECLINE = "decline"
_BARE_SUBVERBS = frozenset({"", _SUBVERB_OFFERS, _SUBVERB_LIST})
_RESPOND_SUBVERBS = frozenset({_SUBVERB_ACCEPT, _SUBVERB_DECLINE})


class CmdConversion(ArxCommand):
    """Answer a pending public-conversion offer.

    Usage:
        conversion                    - list your pending conversion offers
        conversion offers             - same as bare `conversion`
        conversion accept <id>        - accept the offer (converts you inwardly too)
        conversion decline <id>       - decline the offer

    Accepting via telnet always converts you sincerely (heart and public act
    together) — the lip-service option is web-only for now, since there's no
    telnet syntax slot for it yet. Use the web client's dialog to convert
    publicly without converting inwardly.
    """

    key = "conversion"
    locks = "cmd:all()"
    help_category = "Social"
    action = None

    def func(self) -> None:
        from actions.definitions.ceremonies import RespondConversionOfferAction  # noqa: PLC0415

        raw = (self.args or "").strip()
        parts = raw.split(maxsplit=1)
        subverb = parts[0].lower() if parts else _SUBVERB_OFFERS
        rest = parts[1].strip() if len(parts) > 1 else ""

        if subverb in _BARE_SUBVERBS:
            self._show_offers()
            return
        if subverb not in _RESPOND_SUBVERBS:
            self.msg("Usage: conversion [offers|accept <id>|decline <id>]")
            return
        if not rest:
            self.msg(f"Usage: conversion {subverb} <id>")
            return
        try:
            offer_id = int(rest)
        except ValueError:
            self.msg("That's not a valid offer id.")
            return
        result = RespondConversionOfferAction().run(
            actor=None,
            account=self.account,
            offer_id=offer_id,
            accept=(subverb == _SUBVERB_ACCEPT),
            sincere=True,
        )
        if result.message:
            self.msg(result.message)

    def _show_offers(self) -> None:
        from world.ceremonies.services import pending_conversion_offers_for_account  # noqa: PLC0415

        offers = pending_conversion_offers_for_account(self.account)
        if not offers:
            self.msg("No conversion rite is waiting on your answer.")
            return
        lines = ["Pending conversion offers:"]
        for offer in offers:
            honoree = offer.ceremony_honoree.honoree_sheet.character.db_key
            location = offer.ceremony_honoree.ceremony.location.objectdb.db_key
            being = offer.ceremony_honoree.ceremony.presented_being.name
            lines.append(f"  [{offer.pk}] {honoree}, called to {being} at {location}")
        self.msg("\n".join(lines))
