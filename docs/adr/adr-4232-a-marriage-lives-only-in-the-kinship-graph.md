# ADR-4232: A marriage lives only in the kinship graph; a wedding needs no betrothal

**Status:** Accepted (#4232, 2026-10-14). Amends ADR-0212 (org pacts and marriage in play:
the wedding still lands a betrothal's pact, but no longer requires one).

**Context.** A marriage was recorded in two places that never met. The kinship graph's
`Union` row, written only by `record_union`, is what the family tree, the Spouse and in-law
labels, intestate succession and house stature read. `CharacterSheet.marital_status`, a
Single/Married/Widowed/Divorced dropdown set only by staff edit mode and Django admin, is
what telnet `sheet` printed, and no wedding, divorce or death ever wrote it, so a character
married at a wedding still read `Marital Status: Single`. Two more gaps sat beside that: the
wedding rite recorded a marriage only when the pair held an active `Betrothal`, and a
betrothal must name two houses, so two commoners, or a noble and a commoner, could hold the
rite and nothing legal happened; and staff could not add a spouse in admin at all, since
only `UnionKind` was registered.

**Decision.** The `Union` is the only record of a marriage. A betrothal is optional for
everyone: a consented wedding with no betrothal between the honorees records the union
through `kinship.record_marriage` and nothing else (no pact, no prestige, no change of
family or name), while a betrothal, when one stands, adds exactly what it adds today (the
pact with its negotiated terms, the tier prestige, `wed_at`). Both paths take the wedlock
`UnionKind` from one lookup, `wedlock_union_kind()`. Staff add and end a marriage from a
Spouses section on the Kinsperson admin page, through the same services, and a row cannot
be deleted while a `MarriagePact` or a recorded birth points at its union. Marital status
is derived (`kinship.marital_status_of`) from the wedlock-conferring unions the viewer can
see, Married over Widowed over Divorced over Single, with the viewer's own dead fold, and
the sheet column is dropped; telnet `sheet` reads it with the character's own roster entry
as viewer, so a secret marriage the character has not learned of stays off the sheet.

*Rejected:* requiring a betrothal only for house-to-house marriages, or only for two
commoners. Either keeps a class of wedding that records nothing, and the owner's ruling was
that any consenting wedding is a marriage; rules for eloping may come later. *Rejected:*
keeping the sheet field and having the wedding, the divorce and a spouse's death write it.
A second copy of a fact the graph already holds drifts the moment any writer is missed, and
the column could never express a secret marriage or a believed death. *Rejected:* a
separate `Union` admin page instead of the inline. Staff record a marriage where they are
already editing the person, and a page per union would have put the partner picker a
navigation away.

Marriages are one to one and one at a time (ApostateCD, 2026-10-14). Polycules exist in
play as relationships and as non-wedlock unions, but a coded polygamy is neither thematic
nor safe out of character: it invites uneven power structures, harems of people taken
advantage of, so a wedlock union holds exactly two people and a marriage ends by death or
by dissolution before either party marries again. The ended union stays on the record as
the history of prior marriages. Death here is the truth, not the belief: a spouse the
world believes dead still binds while they live, and a plot that wants the widow free to
remarry has staff end the marriage on the record. A real death ends nothing on the record:
the status reads Widowed off the open union. *Rejected:* letting a believed death free the
survivor so that a refusal could never betray a hidden survival; it would have let the
record hold two open marriages the moment the first spouse returned.

**Consequences.** Any consenting pair can marry, one marriage at a time. `CharacterSheet.marital_status` is gone
(play state; every row on the production copy held the default). Staff edit mode loses its
Marital status row and the admin Kinsperson page gains Spouses. `MaritalStatus` moves to
`world.roster.constants`, since it now describes the kinship record. The wedding handler
gives an honoree with no node one first, and refuses, as a `CeremonyError` the officiant
sees, when no kind confers wedlock. `UnionKind.max_concurrent` is still not enforced by a
wedding; whether it should be is a design question not yet asked.
