# ADR-4979: A card the route closes is absent; a card another pick blocks says "Unavailable because <reason>"

**Status:** Accepted (built #4979; amends ADR-0280; related #4978, #4124)

**Decision.** Whether a pick a player cannot take right now shows at all is decided by one
question: could the player change what blocks it. A Beginning is the frame they chose, so a
distinction its route closes (`OriginTemplate.closed_distinctions`) is absent from every
chapter's offers and named nowhere, with nothing printed in its place. A pick blocked by
something the player can swap, a held card that excludes it, a cap, a prerequisite still open
to them, stays visible, disabled, and reads "Unavailable because <reason>", with the reason a
plain clause: "Unavailable because mutually exclusive with Toughened Up". Every lock reason
starts with those two words. **Rejected:** the #3675 shape, a "Closed by your route: <card>:
<reason>" hint under the last pick of each chapter with a staff-written `closed_reason` per
route. The maintainer's ruling (2026-11-03): a player who took a Beginning is customizing a
character inside it and is not weighing the cards that frame never offers, so naming them only
clutters; a card that is available on this beginning but exclusive with another pick is a live
trade-off, and the player wants to know when it is open and when it is not. "Closed on this
road" and "Closed by your route" were also judged bad wording on their own. The cost is one
authored column dropped (`closed_reason`, a deliberate discard: it only ever fed the hint) and
one fewer place a route can speak to the player, which is the point.
