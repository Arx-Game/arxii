# 0194 — Accents multiply per slot; prestige is per-piece; legend pierces concealment

**Status:** Accepted (2026-08-04, Apostate's ruling on #2965)

The ballgown problem: a piece spanning three body-region slots competed with
three separates, and the pre-#2965 walks accidentally counted every
per-slot `EquippedItem` row — multiplying ALL crafted modifiers AND full
prestige by coverage, making both "wear many pieces" and "wear one huge
piece" exploitable depending on the walk. The ruling splits three ways:
**accents extend and multiply per slot covered** (a 3-slot gown's menace ×3 —
the statement scales with the canvas it commands; this also balances against
separates, whose three per-piece accent caps total the same weighted rungs at
much higher crafting cost), **prestige counts once per piece** (a masterwork
is one masterwork however large — never slot-multiplied), and **legend counts
even when concealed** (it is magical; ownership carries it — fabric doesn't
block an aura). Social-facing effects (accents, prestige) read only VISIBLE
pieces — topmost uncovered layer per region, from the `TemplateSlot`
coverage data that already existed — while wearer-facing effects (comfort,
armor, mitigation) read everything worn; the alternative of counting
concealed pieces socially was rejected as breaking intuitive perception. The
deliberate escape hatch is the **Reveal** action: a revealed piece counts
every slot it occupies until unequipped, making hidden finery a timing play
rather than a passive stat.
