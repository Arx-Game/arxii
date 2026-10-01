# 0327 — A house's verdict on a member is a standing on the membership, and a secret goal is a mark on the goal

**Status:** accepted (2026-10-01, #4106)

Two things the first roster character could not be said to be. A member could be *struck
off* a house (`OrganizationMembership.exiled_at`) and a whole house could be in exile
(`Organization.house_state`), but a person could not be in disgrace or in exile while her
house stood and kept her name, rank and claim, which in some realms is a soft sentence and
cover for other business. And a character's goals had one visibility for the whole section,
so she could not carry two public aims and one nobody else may see. **The rulings:** favor
is a standing on the membership (`MembershipFavor`: in favour, in disgrace, exiled, plus a
note), because it is the house's verdict and can be lifted, and the row stays a membership
so nothing that reads membership breaks on a verdict; a secret goal is a mark on the goal
(`CharacterGoal.is_secret`), dropped in the sheet's goal builder for every reader but the
owner or staff before the section's tier is consulted, so opening the section is not all or
nothing, and it still costs what any goal costs. **Rejected:** (a) an "Exiled" distinction
with a reason line, since a distinction is a trait of the person and a verdict belongs to the
house that gave it; (b) nothing mechanical, since the roster is where the politics should be
readable; (c) making secret goals the journal's job, since an entry is about a goal and is not
the goal; (d) a second visibility tier for secret goals, since the mark is per goal and a tier
is per section. The membership standing is set in the admin only for now; an in-play verb (a
pardon, a banishment) is later work and a `needs-design` question for the houses system. In
building this the goals read was moved off a `Prefetch(to_attr=)` onto the identity-mapped
sheet, which Django never re-fetches once set, onto a cached handler a goal's save clears
(ADR-0278): the mark would otherwise have been a leak, an unmarked goal shown until restart.
Related: ADR-0278, ADR-0313 (members exiled vs houses in exile), ADR-0033 (leak prevention).
