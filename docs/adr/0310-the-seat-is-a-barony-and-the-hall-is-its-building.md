# ADR-0310: A title's seat is always a barony; the hall is a separate building on it

**Status:** Accepted (2026-09-23, #3983).

Every rung `plant_rung` plants — barony up through empire — carries a seat chain that bottoms out
at exactly one `BARONY`-tier `Domain`, never higher (`_CHAIN_BELOW`'s every entry ends
`(BARONY,)`; a march shares its county's own one-barony seat rather than minting a second). The
rejected alternative was **seating a duchy or kingdom directly on its own county-level `Area`** —
skipping the barony rung as an unnecessary extra hop. It was rejected because "seat" needs to mean
one concrete, walkable parcel a house actually rules in person — population, holdings, land
shapes, a hall — and a county-sized "seat" is too coarse to carry that; it would blur "the
demesne this house lives on" with "the whole territory it holds sway over," the exact distinction
the ladder's demesne/vassal counts depend on. The seat's own building — its literal keep — is a
further, separate `BUILDING`-level `Area` (`Domain.hall`), deliberately never the same name as the
demesne itself: `describe_demesne` refuses a hall name that repeats the domain's own name, because
the land and the building sitting on it are two distinct nouns a player needs to be able to tell
apart ("the Duchy of Veyrane" versus "Veyrane Hall").
