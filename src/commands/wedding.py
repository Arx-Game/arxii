"""Telnet command for the wedding consent-offer inbox (#2358).

Account-scoped, not character-scoped — mirrors ``commands/seance.py`` exactly:
the officiant's ``ceremony/wedding`` start action creates one offer per spouse
honoree, and either spouse's account answers it here (or via the web).
"""

from commands.command import ArxCommand

_SUBVERB_OFFERS = "offers"
_SUBVERB_LIST = "list"
_SUBVERB_ACCEPT = "accept"
_SUBVERB_DECLINE = "decline"
_BARE_SUBVERBS = frozenset({"", _SUBVERB_OFFERS, _SUBVERB_LIST})
_RESPOND_SUBVERBS = frozenset({_SUBVERB_ACCEPT, _SUBVERB_DECLINE})


class CmdWedding(ArxCommand):
    """Answer a pending wedding's consent prompt.

    Usage:
        wedding                    - list your pending wedding consent offers
        wedding offers             - same as bare `wedding`
        wedding accept <id>        - consent to the marriage
        wedding decline <id>       - decline (aborts the whole ceremony)

    Both spouses must accept before the officiant can complete the rite;
    the union and marriage pact are not created until then.
    """

    key = "wedding"
    locks = "cmd:all()"
    help_category = "Social"
    action = None

    def func(self) -> None:
        from actions.definitions.ceremonies import RespondWeddingConsentOfferAction  # noqa: PLC0415

        raw = (self.args or "").strip()
        parts = raw.split(maxsplit=1)
        subverb = parts[0].lower() if parts else _SUBVERB_OFFERS
        rest = parts[1].strip() if len(parts) > 1 else ""

        if subverb in _BARE_SUBVERBS:
            self._show_offers()
            return
        if subverb not in _RESPOND_SUBVERBS:
            self.msg("Usage: wedding [offers|accept <id>|decline <id>]")
            return
        if not rest:
            self.msg(f"Usage: wedding {subverb} <id>")
            return
        try:
            offer_id = int(rest)
        except ValueError:
            self.msg("That's not a valid offer id.")
            return
        result = RespondWeddingConsentOfferAction().run(
            actor=None,
            account=self.account,
            offer_id=offer_id,
            accept=(subverb == _SUBVERB_ACCEPT),
        )
        if result.message:
            self.msg(result.message)

    def _show_offers(self) -> None:
        from world.ceremonies.services import (  # noqa: PLC0415
            pending_wedding_consent_offers_for_account,
        )

        offers = pending_wedding_consent_offers_for_account(self.account)
        if not offers:
            self.msg("No wedding awaits your consent.")
            return
        lines = ["Pending wedding consent offers:"]
        for offer in offers:
            honoree = offer.ceremony_honoree.honoree_sheet.character.db_key
            location = offer.ceremony_honoree.ceremony.location.objectdb.db_key
            lines.append(f"  [{offer.pk}] {honoree}, wedding at {location}")
        self.msg("\n".join(lines))
