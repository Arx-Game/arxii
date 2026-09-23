# ADR-0311: A household member is Ward of the house, never of the family's name

**Status:** Accepted (2026-09-23, #3983).

`add_household_member` records a house's retainers — staff/service-placed, never appable — as
filled `Vacancy` rows at the org's own `Household` rank, defaulting an unlabeled entry's position
to "Ward." The rejected alternative was a **`WARD` basis on `FamilyMembership`** — folding a ward
into the kinship graph as a sixth membership basis alongside `BORN`/`MARRIED_IN`/`ADOPTED`/
`LEGITIMIZED`/`GRANTED`/`FOUNDING`, the same table a house's actual name-bearing kin sit in. That
was rejected because a household member is deliberately NOT of the family's blood or name:
`add_household_member` writes no `kin_node`/`kin_pool` link and no `FamilyMembership` at all, on
purpose — those links are what marks a slot appable on the family's own claim path, and a ward
taken in to serve the house is a fact about the ORGANIZATION, not the FAMILY. "Ward" is a
household position, read off `Vacancy.name`, never a `MembershipBasis` value; a sheeted ward who
also happens to hold a primary persona gets an ordinary `OrganizationMembership` at the Household
rank, the same channel any staff/retainer role would use — never a family tie.
