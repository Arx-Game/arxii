# A masked actor is never remembered by a consent list

**Status:** Accepted (2026-10-10) · **Issue:** #4189 · **Related:** [ADR-4187](adr-4187-ask-is-a-consent-mode-only-for-categories-that-act-on-you.md)

Two one-motion shortcuts write a consent list row from a request addressed by persona: the
makeover ask's "Always let" / "Never from" (#4187) and the scene consent prompt's "Deny & block"
(#1698). The whitelist and blacklist are keyed by the actor's real `RosterTenure`, and the
Privacy page shows each row under the real character's name, so a row written for someone
acting under a mask would tell the target who wore it. The maintainer ruled that a masked
person is never remembered: the lists must not become a way of inferring who a masked person
is. Both shortcuts therefore write nothing when the actor's persona is not PRIMARY, and say
nothing about it, because any notice ("this face can't be remembered") would itself reveal
that the face is a mask. The refusal or the deny still happens; only the remembered row is
skipped, so the target is asked again by that face next time and "Deny & block" does not block
it. **Rejected:** a persona-keyed list row ("remember this face"), a new shape for lists that
are tenure-scoped everywhere else, and one that would interact with unmasking
(`PersonaDiscovery`); and telling the target the shortcut was skipped. Adding a person by hand
on the Privacy page is unaffected: the player names a tenure they already know.
