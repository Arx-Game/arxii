# One-way exits are a staff tool; owner and story links stay symmetric

**Status:** Accepted (2026-09, #3860)

**Context.** Every exit-minting surface made a symmetric pair: `create_exit_pair`
is what the owner's building link, a GM's story link and the staff link action
all called, and no dialog, action or admin page could leave the return exit out.
Staff wanted Limbo to lead down onto the grid without the grid leading back up
(Dan, 2026-09-14), and telnet `@open` was the only way. Limbo also belongs to no
Area, so the Atlas, whose grids are Area-scoped, showed it on no grid; only the
room search reached it.

**Decision.** A one-way exit is a deliberate staff choice, made in two places
and nowhere else: `StaffLinkRoomsAction` with `one_way` (through the public
`grid_services.create_exit`, one direction, no return) and the Atlas's exit
dialog, where "Both ways" stays pressed by default and "One way" hides the
return name and says nothing leads back. The owner's building `link_rooms` and a
GM's `story_link_rooms` keep calling `create_exit_pair`. The builder payloads
tell the truth about it: every exit row in the area manager and the room detail
carries `one_way`, computed in one query per payload, and the room document's
chip tags it. Rooms with no Area are listed in the Atlas's index rail under
"Unfiled rooms" (`GET /api/world-builder/areas/unfiled-rooms/`, staff only, since
no warrant covers an area-less room), so reaching Limbo never depends on knowing
to search.

**Rejected alternative: let every link surface go one way.** A building's
interior and a story area are kept self-contained by the two-way convention;
an owner or a GM stranding a room by omitting the return exit is a support case
waiting to happen, and neither surface asked for it. Exit-graph connectivity
(ADR-0120) is unchanged: a one-way exit is an ordinary exit, and `find_route`
walks it in the one direction it exists.

**Rejected alternative: an Area for area-less rooms.** Filing Limbo under a
synthetic "Unfiled" Area would make it appear on a grid it has no place on and
give it an ancestry it does not have. A listing in the rail reaches it without
pretending.
