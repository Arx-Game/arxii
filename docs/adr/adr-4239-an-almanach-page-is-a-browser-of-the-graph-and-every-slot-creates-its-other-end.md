# ADR-4239: An Almanach page is a browser of the graph, and every slot creates its other end

**Status:** Accepted (2026-10-11, ApostateCD)
**Issue:** #4239 (folds #4081)
**Related:** ADR-0097 (kinship is a person-node graph with truth vs public record), ADR-0098
(houses are organizations), ADR-0268 (family standing uses existing organization mechanisms;
kinds are rows), ADR-0273 (family entry is a staff-authored Vacancy), ADR-4209 (no tier words on
player kin surfaces), ADR-0309 to ADR-0316 (the Almanach's ladder and house document)

## Context

Authoring one connected piece of the world (a roster character's family, which means her kin,
her house, its holding, where it lies, its vassals) meant a tour of the Django admin one model
at a time. Character creation had solved the same chain for a founder, and the Almanach (#3983)
authored a house's record, but only for a noble house that already existed, relative to a
realm's ladder. Staff had no equivalent for a crime family, a commoner family, or a person who
did not yet belong anywhere.

## Decision

**Four page types over the rows that exist, every link a slot, every slot able to create the
thing at its other end.** A person, a house or family, a realm (the ladder) and a domain (a
rung) each have a page with an address. A picker that finds nothing offers Create in place.
The admin stays as an escape hatch; nothing is removed from it.

**A family needs no organization until it has standing.** Create Family makes a `Family` row
alone when the type does not style as a house and no holding is chosen; an orphan's dozen NPC
relatives are a family and kin rows and nothing else. A template, a holding, or a type that
styles as a house builds the organization through `build_family_org` (ADR-0268). A family with
people takes standing later through `found_organization`.

**Create Family for a noble house carries its holding by default**, with None yet as the
opt-out: Create plants a domain and title under a rung and the new house and the chosen person
hold it; Vacant title takes an unclaimed rung. Add vassal house on a title row always makes the
new house its holder. A family with no title or turf may be given a home (the domain its
holdings stand on), never automatically: the common original character has a background family
that never stands on grid.

**Kin are created with only a family and linked to anyone in any family.** Parentage is
corrected by replacing the edge; unions are ended; nobody is deleted from this surface. A
person's status is Alive, RIP or Missing, with the record's accuracy and its obituary kept apart
from the truth (ADR-0097). A player character's name, tier and death are never edited here.

**Words follow the code.** A Title is the rung, a Domain is its land, a Holding is one work on
a domain, Vassals are the rungs beneath; the person who holds a title is its holder; "seat"
means only a domain's seat barony. Create, never Found. Family type, never kind. Staff pages
show a kinsperson's tier as 0/1/2/3 and spelled long after the name; players never see it
(ADR-4209). The dead and the missing carry (RIP) and (Missing) after the name in the muted
color, never a strikethrough. Staff copy is fragments, with no explanation beside a control.

## Alternatives rejected

- **A wizard with a fixed order.** Staff never start from the same end; the work is a graph,
  not a sequence.
- **Admin inlines.** One model per page is the problem being solved.
- **A `life_status` column replacing the death booleans.** Eighteen modules read
  `is_deceased`; a restructure for one more state was the larger shape. `is_missing` rides
  beside the two booleans; if a fourth state ever appears, that is the moment to collapse them.
- **Creating realms from the Almanach.** Realms are the six imperial regions, seeded. What
  staff create is a domain, a rung on a realm's ladder.
- **The map and the ledger in this round.** Footprints and placement are the Atlas's and need
  a schema pass of their own (#4242); income by barony, vassal and trade taxes, goods, overhead
  and debts are the organizational ledger (#4243). Books reads what exists until it.
