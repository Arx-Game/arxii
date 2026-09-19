# ADR-0305: Location access is a four-rung ladder carried on the grant

**Status:** Accepted (2026-09-19, #3902)

## Context

`LocationTenancy` meant one thing: this persona or organization may use this place.
Apostate's ruling separated four things a person can be to a place — an **owner** who
controls all forms of access, a **trustee** trusted to act for them, a **tenant** with
temporary ownership who may change the house and hand out access, and a **guest** who
may visit and nothing more.

The tempting shape was a sibling `LocationKey` model. It was rejected: the grant
already hangs off the **land** (an area/room discriminator, which is itself the ruling
on where access permissions belong), cascades down the area tree, accepts a persona or
an organization as holder, is time-bound and revocable with history kept, and bridges
organization membership. A sibling model would duplicate every one of those to express
one distinction.

## Decision

**One field, three values, on the existing grant.** `LocationTenancy.kind` is a
`LocationRole` — `GUEST` / `TENANT` / `TRUSTEE` — and the rungs are cumulative.
**OWNER is deliberately not a member of that enum:** the deed is a `LocationOwnership`
row with a different lifecycle (one active holder per location, cascade
most-specific-wins), and folding it in would create a second source of truth for who
owns a place. `OWNER_RANK` tops `LOCATION_ROLE_RANK` so the comparison stays total
across both models.

Three further decisions follow from it:

**`is_tenant` was removed, not redefined.** It meant "holds any grant", and the moment
grants gained a rung that became "holds something, we are not saying what" — so the
eleven call sites reading `is_owner(p, r) or is_tenant(p, r)` would all have silently
started meaning "guest included". Each now names its rung through
`has_standing(persona, room, at_least=...)`. This is the #3923 lesson applied before
the fact rather than after it: an enumerated set that a later feature grows, read
through a predicate that cannot express the growth, fails open and raises nothing.

**The model default is the LOWEST rung.** A writer who forgets the kwarg mints a Guest,
which surfaces as "my key does not work" and gets reported. The opposite default mints
a Tenant, which is a silent over-grant nobody sees. Rows written before the field
existed all meant TENANT, so migration 0147 fills them with that via
`preserve_default=False` and the model default reverts to GUEST afterwards.

**Authority and residence are separate axes.** The ladder answers "may they act here".
`is_primary_home` answers "do they live here". A trustee may hold real authority over a
keep they have never slept in, so the sheet's Tenanted Rooms card and prestige read
residence, not a rung. (Stables capacity is the exception recorded under Consequences.)

**Granting is authorized in the service, not deferred to callers.** `grant_tenancy`'s
previous docstring said "Caller is responsible for permission gating (only owners
should grant tenancy)" and callers overwhelmingly did not. It now requires `kind`,
takes `granted_by`, and enforces the ladder: a GUEST grant needs Tenant-or-above, a
TENANT grant needs Trustee-or-above, and a TRUSTEE grant is the owner's alone. A trustee
is "someone trusted by the owner", and trust a trustee could pass to a friend, who could
pass it on again, is not the owner's trust any more; revoking a trustee was already
owner-only, and the two halves have to agree or the owner ends up removing appointments
they never made. `granted_by=None` remains the system path (character generation,
admin, seeds) and is now explicit rather than what happens when nobody thought about it.

**Revocation follows the chain of grants, not rank.** The first cut let anyone who
*could have granted* a rung revoke it, which meant a tenant could pull a key the owner
gave and a trustee could evict a tenant the owner installed, each unpicking the owner's
arrangements from inside. `end_room_tenancy` now lets the holder depart, lets the owner
end anything, and otherwise requires that the caller is the row's `granted_by` and
still clears `can_grant` for that rung. This is the reason `granted_by` exists.

## Consequences

A key becomes a real thing a player can give and a new player can discover: the keyring
on the sheet's Estate section lists every active grant, so the next player of a
character learns both that a friend's house is open to them and that their family holds
a keep. Both were previously unlearnable from the sheet.

Every call site now states an intention it previously only implied, which is more text
but is the thing a reader checks against. The cost is that adding a rung means deciding
what it clears at each site rather than getting a default — which is the point.

One thing stays imperfect and is recorded rather than papered over: residence has no
multi-place fact in the model (`is_primary_home` and `CharacterSheet.current_residence`
are both one-per-persona), so `stables_capacity_bonus_for_sheet` uses TENANT-or-above as
a proxy and a non-resident trustee clears it. Fixing that needs a residence design, not
a rung.

## Alternatives rejected

- **A sibling `LocationKey` model** — duplicates the closure walk, both discriminators,
  the active window and the membership bridge to express one enum value.
- **A two-value field (resident/guest)** — the original spec. It cannot express a
  trustee, and the ruling needs one.
- **Per-capability booleans on the grant** (`may_use_servants`, `may_renovate`, …) —
  maximally expressive and the natural next step if the rungs prove too coarse, but it
  multiplies structure and UI against a ruling that describes four *roles*, not a
  permission matrix. The ladder can grow into this later; starting here would be
  inventing a system the ruling did not ask for.
- **Folding OWNER into `LocationRole`** — would need the deed's one-active-holder
  constraint and its most-specific-wins cascade replicated on a model that deliberately
  has neither.
