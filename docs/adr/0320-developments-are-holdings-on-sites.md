# 0320 — Developments are holdings on sites; one farm, not two; unsited yields nothing

**Status:** accepted (2026-09-29, #4060 slice 2)

The maintainer wants a family's businesses to be physical: a farm, an inn, a ship, a
quarry, something the family possesses and the player has a piece of, each with its own
income. Two shapes already existed: `DomainHolding`, an abstract income stream on a
domain (the seeded "Farmland PLACEHOLDER" among them), and agriculture's FIELD room
feature, a site-bound, leveled farm that grows food into the domain's stockpile. Two
farms. **Decision:** no new development model. `DomainHolding` *is* the development and
gains a site (`room_profile`, `building`, `field`), `level` and `standing`; `HoldingKind`
says what a kind sits on (`site_kind`), how many land units it occupies and whether it
is a farm (`requires_field`). A farm is one holding standing on one FIELD feature: food
through agriculture's tick, coin through the holding's stream, one collection. The seeded
Farmland kind becomes that farm by data migration; its existing holdings keep their
streams and are placed in play. Sited LAND holdings use up the domain's land units, so
developing land is an investment rather than pure profit on top of the base yield
(ADR-0319). **A holding of a sited kind that stands nowhere yields nothing until it is
placed**, which is what gives anyone a reason to place it; that this drops the seeded
Farmland holdings' income to zero on production until staff attach a field is a
deliberate change, stated on the PR.

**Rejected:** (a) a new `Development` model beside holdings and fields (a third farm);
(b) folding fields into holdings and retiring agriculture (the food economy has real
consumers: population, armies, ship crews); (c) grandfathering unsited holdings at full
yield (nothing would ever be placed). Buildings and ships are sites, never units
(#4060 hub: player-built rooms must not manufacture territory).
