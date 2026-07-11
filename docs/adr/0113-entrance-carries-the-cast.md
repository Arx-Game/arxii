# A technique-driven entrance carries the cast — one check, not two

A "make an entrance" backed by a technique (`enter <technique>[=<target>]` / the web
`EntranceTechniqueAttachment`) resolves through exactly **one roll**: the technique's own
cast check (`request_technique_cast`) substitutes for the entrance's social check entirely.
The success level of that single cast drives every downstream consequence — the entry
flourish offer, the peer scene-entry endorsement, social disposition, and (above an authored
threshold) a GM-facing `DramaticMomentSuggestion` — via `run_entrance_success_hooks` at
whichever point the real success level becomes known (inline, at combat round resolution, or
at consent-accept, per the #2183 deferral matrix). Recognition is never automatic: a qualifying
cast only creates a **suggestion** a GM later confirms (minting a real `DramaticMomentTag`,
which fires the resonance grant + renown award) or dismisses — the existing
`DramaticMomentType` catalog and its per-scene cap are the sole gate on this reward, exactly as
they are for any other GM-tagged moment (mirrors ADR-0110: catalog and adaptation, never
invention). We rejected three alternatives: **a double roll** (a technique cast followed by a
separate social check) — this double-charges resources for one dramatic beat and produces two
success levels with no principled way to reconcile them into one narrative outcome; **a
mechanical auto-grant** of the dramatic-moment reward on a high success level — this bypasses
the human GM judgment call every other dramatic-moment tag requires, breaking the "GM checks:
curated, never invented" invariant from the other direction (an invented *reward* instead of an
invented *check*); and **a live-surge reward** (folding the recognition into Audere/intensity
surge machinery) — Audere answers "how does this cast feel mechanically right now," a different
question from "should this moment mint a renown deed," and conflating the two would tangle an
unrelated system's gate into this one.

> Status: accepted · Source: #2183 · Related: ADR-0110 (GM content is catalog and adaptation,
> never invention); ADR-0024 (consent gates behavior, not benefit — the entrance's own
> consent/risk gates are unaffected by this ADR)
