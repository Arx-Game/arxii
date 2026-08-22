# ADR-0231: Org appeals are a distinct IC surface from the OOC staff-contact Petition

Date: 2026-08-22. Status: accepted (issue #3293 spec).

`Petition` (`world.player_submissions.models.Petition`) already exists in this codebase
as an OOC emergency staff-contact ticket, routed to the staff inbox - not a request a
character can address to an organization. Arx I's "petitions" (post a free-text ask, an
org's members see it, someone signs on to help) are an IC roleplay hook with no OOC or
staff dimension at all: any character asks a house/guild/temple for aid, members read and
sign onto it, and leadership resolves it with a written answer. Naming the new model
`Petition` would collide with the existing OOC surface in code search, admin, docs, and
player-facing copy, and conflating the two in shared vocabulary risks staff routing
logic accidentally picking up player-authored IC asks (or vice versa).

Decision: the new model is `OrgAppeal` (+ `OrgAppealSignon`), and "Appeal" is the
canonical term for this IC ask everywhere it is spoken of (player-facing copy, telnet
`appeal <org>=...`, the `AppealsPanel`/`LodgeAppealDialog` React components, the
`OrgAppealViewSet` API). "Petition" stays reserved exclusively for the OOC staff-contact
ticket; the `world/societies/AGENT_GLOSSARY.md` entry for Appeal explicitly warns
against using "petition" for it. Rejected alternative: extending `Petition` itself with
an org-directed mode - rejected because it is architecturally a staff-inbox ticket
(routing, staff visibility, no organization concept at all), and widening it would make
an OOC safety-contact surface do double duty as gameplay content, the opposite of the
IC/OOC separation this split protects.
