# ADR-4726-A: The stat lane applies wherever a stat is read

A buff to a stat used to be a flat number summed in `TraitHandler._get_stat_modifier`; with
#4551's lanes, a stat buff is now valued by its level and size from the `stat` lane's
`ModifierValue` table and piles of one kind taper by the lane's `ModifierTaper` rows, and we put
that valuation in `_get_stat_modifier` itself, so checks, fatigue capacity, stamina's health term,
carrying capacity and scandal all read one buffed number (the web sheet shows the stored,
unbuffed stats, `_build_stats`). The rejected
alternative was valuing and tapering stat buffs only on checks (inside the check seam), which
would leave a character's strength a different number on a roll than in their
carrying capacity; the owner ruled against it on 2026-10-26, and the price is that the stat read
is on the combat hot path (#552), so the table and taper rows load only when a source is sized or
a kind has a pile.

> Status: accepted · Source: owner ruling 2026-10-26 on #4551 · issue #4726 (slice 8 of #4551)
