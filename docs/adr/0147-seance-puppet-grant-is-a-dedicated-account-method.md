# Seance's retired-honoree puppet grant is a dedicated Account method, never merged into the general login gate

`Account.can_puppet_character` (and the `PlayerData.get_available_characters` list it partly
relies on) is the single, general-purpose gate every puppet-switch in the game passes through
— including `CmdIC`, the only place `puppet_character_in_session` is called from. A retired
character is excluded from both of those unconditionally, by design (#2287): once `retire`
fires, that character can never be puppeted again, full stop.

Seance (#2393) needs one narrow exception to that: a retired honoree, with an ACCEPTED
`SeanceManifestationOffer` on a currently-OPEN Seance ceremony, may be puppeted again for as
long as that ceremony stays open. Rather than threading a bypass flag or an extra parameter
into `can_puppet_character` itself, this is a wholly separate method,
`Account.can_puppet_for_seance`, consulted only as a fallback inside
`puppet_character_in_session` when the general gate has already said no. `CmdIC`'s own
character-name search pool is separately widened (`get_seance_manifestable_characters`) so a
retired honoree can even be found by `@ic <name>` in the first place.

We rejected folding this into `can_puppet_character` directly: that method is read by every
puppet-switch path in the codebase, several of which (roster application review, future
"list who could conceivably ever puppet this" tooling) have no reason to ever learn about
seances. A dedicated method keeps the general gate's contract exactly what it has always been
— "is this character alive-or-unretired and available to you right now" — and makes the
seance exception a single, greppable, narrowly-scoped surface instead of a conditional buried
inside the one gate every other system trusts to be simple.

> Status: accepted · Source: #2393
