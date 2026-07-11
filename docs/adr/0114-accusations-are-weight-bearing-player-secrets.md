# Player-authored accusations are weight-bearing secrets, gated by consent not by the model

A frame-job (#1825) is a player-authored **false scandal about another character** that must
mint heat and reputation exactly like a true one until disproven. It is stored as a `Secret`
under a new `SecretProvenance.ACCUSATION` that is **deliberately exempt** from the two
`Secret.clean()` caps on player content (the player-flavor-above-Level-1 ban and the
anchored-implies-evidenced ban): an ACCUSATION may sit at any level and anchor to an *alleged*
deed. Its abuse guard is not the model but the **consent gate at the mint action** — a played
target must have opened their `hostile` antagonism-consent category (#2170) to the framer;
NPCs are always frameable. Falsity stays **emergent** (a divergence between the alleged deed
and the truth), never a stored flag, so a leaked accusation flows through the same
`expose_secret` → reputation and `accrue_heat(deed=alleged)` paths as any real scandal.

We rejected the two alternatives. Routing frame-jobs through the **heat path only** (a
`HeatSource` with no `Secret`) was lighter but left nothing to disprove, leverage, or reveal —
the scandal has to be a real, knowable object for the "until disproven" gameplay to exist.
Keeping accusations at **Level-1 player-flavor** (the existing free-authoring tier) preserved
the caps but made frame-jobs too weak to matter. Exempting a *distinct* provenance keeps the
canon-protection rules intact for `PLAYER_FLAVOR` while letting antagonism-by-consent carry
weight; the consent gate, not a content cap, is what stops abuse.

> Status: accepted · Source: #1825, Apostate ratification 2026-07-11
