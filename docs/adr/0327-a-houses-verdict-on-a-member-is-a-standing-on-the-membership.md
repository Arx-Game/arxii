# 0327 — A house's verdict on a member is a standing on the membership, and goals are the owner's

**Status:** accepted (2026-10-02, #4106)

Two things the first roster character could not be said to be. A member could be *struck
off* a house (`OrganizationMembership.exiled_at`) and a whole house could be in exile
(`Organization.house_state`), but a person could not be in disgrace or in exile while her
house stood and kept her name, rank and claim, which in some realms is a soft sentence and
cover for other business. And a character's goals carried a section visibility tier
(`goals_visibility`, #1271) that read as if a player could open her aims to friends or to
everyone, so a character with a public purpose and a private one looked like she needed a
per-goal secret flag. **The rulings:** favor is a standing on the membership
(`MembershipFavor`: in favour, in disgrace, exiled, plus a note), because it is the house's
verdict and can be lifted, and the row stays a membership so nothing that reads membership
breaks on a verdict. Goals are the owner's and staff's, full stop: the tier is removed, no
goal carries a secret flag, and the sheet's goal builder runs only for a privileged reader.
Nothing had ever written `goals_visibility` (no endpoint, no control), so no player loses an
opening they had made. The thing a player actually wants, showing a private part of her sheet
to one chosen reader (the GM at her table, a character hers is bound to), is a per-viewer,
per-section OOC grant, not a tier opened to everyone at once and not a flag on one row; it is
its own design question (#4113). **Rejected:** (a) an "Exiled" distinction with a reason line, since a
distinction is a trait of the person and a verdict belongs to the house that gave it;
(b) nothing mechanical, since the roster is where the politics should be readable;
(c) `CharacterGoal.is_secret`, built and then withdrawn in the same PR once the tier it sat
on turned out to be unopenable and the wrong shape; (d) making the sharing the journal's job,
since an entry is about a goal and is not the sheet. The membership standing is set in the
admin only for now; an in-play verb (a pardon, a banishment) is later work and a
`needs-design` question for the houses system. In building this the goals read was moved off
a `Prefetch(to_attr=)` onto the identity-mapped sheet, which Django never re-fetches once
set, onto a cached handler a goal's save clears (ADR-0278): an edited goal would otherwise
have shown its old state until restart. Related: ADR-0278, ADR-0313 (members exiled vs houses
in exile), ADR-0033 (leak prevention).
