# ADR-4088: XP, Development, and Legend are three separate progression currencies

**Issue:** #4088 · **Related:** ADR-0053 (XP buys unlocks, never grants), ADR-0288
(XP is account-scoped, character-attributed), ADR-0249 (Legend settles at the end of a
story unit, priced against the earner's own level), ADR-0167 (Technique style belongs
to the Path, not the Technique), ADR-0199 (a Minor Gift's style may override the Path).

## Context

Character advancement in Arx II already runs on three separate currencies, but no
single doc or glossary entry said so plainly, and the model map's summary line read
XP and Development Points as one undifferentiated bucket. The progression system doc
(`docs/systems/progression.md`) framed development points as skill growth only, with
no mention of Legend or of the fact that a thread spends both XP and Development on
the same row. That gap produces a predictable misreading: an agent sees `XPTransaction`
and `DevelopmentTransaction` sitting side by side and assumes they are interchangeable,
or sees `LegendRequirement` and assumes Legend is just another XP-flavored gate. It is
not. Each currency answers a different question about a character, and the rules that
let a character actually level are the ones separating them.

## Decision

**State three currencies, not one advancement pool.** XP, Development, and Legend each
measure something distinct, and the gates in code already enforce the separation:

- **XP** unlocks a mechanical benefit at an authored cutoff (`ClassLevelUnlock`,
  `TraitRatingUnlock`, a `ThreadXPLockedLevel` boundary). It stands for the roleplay
  and content creation that justify the unlock, and is largely player-driven:
  nominations, kudos claims, and GM story rewards are the production sources
  (`world.progression.services.awards.award_xp`), not an automatic tick for playing.
- **Development** is progress toward a skill, stat, or thread cutoff. It stands for
  the time, effort, and resources the character invests, and mostly accrues
  automatically from ordinary play: `DevelopmentPoints` on skills and stats, resonance
  invested into a `magic.Thread.developed_points`, and Action Points spent through
  weekly training. Threads already carry this exactly: every tenth internal level is
  an authored, separately-priced `ThreadXPLockedLevel` boundary, so Development alone
  gets a thread to the boundary and a distinct XP spend is what lets it cross.
- **Legend** is progress toward a character level (a Durance step, an Audere Majora
  crossing), gated by `LegendRequirement`. It comes only from legendary achievement at
  great personal risk, settled at the end of a story unit and priced against the
  earner's own level and station rather than asserted at a flat authored value (#3463,
  ADR-0249). It is deliberately kept as its own currency, separate from both XP and
  Development, so that neither time nor effort, however much of either a character has
  banked, can level a character on its own.

Most unlocks cost both XP and Development together; Legend gates level advancement on
its own axis and is never a substitute for either, nor is either a substitute for it.

## Rejected

**Leveling a character purely from accumulated XP.** XP already buys unlocks that gate
acquisition (ADR-0053); folding level advancement into that same currency would let a
character who is simply prolific (many nominations, many kudos claims) level up with
no fictional risk at all, which is exactly what `LegendRequirement`'s banded, station-
priced gate exists to prevent.

**Leveling a character purely from accumulated Development or time played.** Development
measures invested effort, not danger. A character who trains every week but never
risks anything would level under this model purely by showing up, which contradicts
the explicit ruling behind ADR-0249: neither time nor effort levels a character.

**Collapsing all three into one undifferentiated "advancement points" pool.** The three
already have different production rules (player-authored content, ordinary play
investment, and story-risk settlement, respectively) and different consumption rules
(gating unlocks, gating thresholds, and gating levels, respectively); a single pool
would need a fourth layer of bookkeeping just to reconstruct which currency a given
balance was supposed to be, with no corresponding gain in clarity.

> Status: accepted · Source: issue #4088
