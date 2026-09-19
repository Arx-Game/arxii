# Locations glossary

Domain-local vocabulary for `world.locations` (the ambient value cascade, the deed,
and the access ladder #3902). Root terms live in `AGENT_GLOSSARY_MAP.md`; the cascade
itself is documented in `src/world/locations/CLAUDE.md`.

- **Grant** — a `LocationTenancy` row: a time-bound, revocable right to use a
  specific piece of land, held by a persona **or** an organization. It hangs off the
  **land** (an area or a room), never off the person, which is the ruling on where
  access permissions live. A grant on an area covers every room inside it.
  _Avoid:_ lease (implies rent, which lives in the economy), permission, key (a key
  is one *rung* of a grant, not the grant itself).
- **Rung** — which of `LocationRole`'s three values a grant carries
  (`LocationTenancy.kind`). Cumulative: each includes everything below it.
  _Avoid:_ level, tier, permission level.
- **Guest** — the lowest rung. Visitation and nothing else: locked exits open,
  guards do not challenge, wards stay quiet. A guest is NOT a tenant and must never
  be counted as one — they do not live there, get no stables capacity, appear on no
  Tenanted Rooms card, and are not notified when the alarm fires.
  _Avoid:_ visitor, keyholder (both read as informal; "guest" is the ruled term).
- **Tenant** — "temporary ownership" in Apostate's words. Lives there, uses the
  servants, furnishes the place (room features), sets a primary home, locks doors,
  and may hand out GUEST keys. May NOT grant a tenancy or do structural work.
  _Avoid:_ resident (that is the other axis — see **Residence**), renter, occupant.
- **Trustee** — trusted to act for the owner. Everything a tenant has, plus
  structural building work ("control any home state") and granting TENANT. May not
  appoint another trustee: the owner's trust in one person does not pass on.
  A trustee is authority, not residence: a seneschal may administer a keep they have
  never slept in. _Avoid:_ steward, manager, deputy owner.
- **Owner** — the deed-holder, a `LocationOwnership` row. Deliberately **not** a
  `LocationRole` member: one active owner per location, resolved most-specific-wins
  up the area tree, with a lifecycle the ladder does not share. Clears every rung,
  and alone may transfer the deed, appoint a trustee, or revoke a trustee. _Avoid:_ landlord, holder
  (ambiguous — `holder_type` is the persona-vs-organization discriminator).
- **Standing** — whether a persona clears a given rung at a given room, answered by
  `has_standing(persona, room, at_least=...)`. The one gate; it composes the deed,
  direct grants, and grants reaching the persona through organization membership.
  _Avoid:_ access, permission, `is_tenant` (removed in #3902 — it meant "holds any
  grant", which silently became "guest included" once rungs existed).
- **Residence** — whether a character keeps a household somewhere, a **separate axis**
  from the ladder. `is_primary_home` on a grant is the declared one (one per persona);
  it drives prestige-from-dwellings and the sheet's Tenanted Rooms card. Authority and
  residence are independent, and conflating them is the mistake the ladder exists to
  prevent. _Avoid:_ home (ambiguous with Evennia's `home` recall location), tenancy.
- **Granted by** — the persona recorded on a grant as having handed it over
  (`granted_by`; NULL when the world did). Revocation follows it: apart from the
  holder departing and the owner ending anything, only the granter may take a grant
  back, and only while they still hold the standing to have given it. _Avoid:_
  issuer, sponsor.
- **Keyring** — the sheet's Estate read of every active grant a character holds,
  directly or through an organization, naming the place, where it is, the rung and who
  granted it. Its job is **discovery**: without it a new player of a roster character
  cannot learn that a friend's house is open to them or that their family holds a keep.
  _Avoid:_ access list, permissions list.
