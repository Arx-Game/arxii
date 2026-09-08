# ADR-0285: Realm pages read a realm API because the realm now owns content; the realm boards are #676's per-realm addition, diegetic in shape

**Status:** Accepted (#3725, 2026-09-08). Amends ADR-0227 (no realms API) and the #676
diegetic-discovery invariant. Related ADR-0201, ADR-0238, ADR-0224.

**Context.** ADR-0227 rejected a `world/realms` read API because a realm was only an FK
off rows other apps already served, so a second read surface for the same pitch content
would have been a duplicate. #3725 gives the realm content of its own: the testament
(the reviewer's pitch prose, `RealmTestamentSection` rows with motto lines) and a formal
name, which no starting area, society or sheet carries. The realm page also needs a
public view onto rows that today are served only to members (`OrganizationViewSet`
lists the viewer's own memberships) and rankings that #676 ruled live on in-world
objects, discovered not browsed, with "per-realm rankings" named as a possible later
addition.

**Decision.** `/api/realms/` is a read-only, anonymous realm API (ADR-0224's
shop-window shape): the hub list, a realm by slug, and two realm-scoped actions. The
organizations action serves a dedicated shop-window serializer (name, words, colours,
sigil, description, kind, society) with covert kinds shown only to their own members,
so nothing a member-only read protects can reach a visitor. The notables action serves
the realm's two boards (renown, legend) over the realm's Active-roster PRIMARY personas
through the same row serializer the diegetic boards use (a name and a band label, never
the value), which is the per-realm addition #676 reserved; the ruling that message
boards, where people post, never show to guests stands unchanged. The landing page keeps
reading its pitch content off the starting-area read; ADR-0227's rejection is amended,
not reversed. The testament is authored only in admin (ADR-0238), credited (ADR-0201).

**Rejected.**
- Serving the testament through `StartingArea` again: the testament is the realm's, not
  the capital's, and a realm may have more than one area.
- A public branch inside `OrganizationViewSet`: mixing a member gate and an anonymous
  shop window in one queryset invites the wrong serializer on the wrong branch; a
  separate serializer with no path to members, ranks, treasury or boards is the
  containment.
- Login-only boards, or none: the reviewer ruled the top tens public and message boards
  members-only; the shape (names and phrases, active characters, no numbers) keeps the
  hidden-mechanics rule (#761) on a public page.
- A stored slug column: the slug is derived from the name over a handful of rows;
  `realm_by_slug` resolves it, and renaming a realm in admin moves its page.
