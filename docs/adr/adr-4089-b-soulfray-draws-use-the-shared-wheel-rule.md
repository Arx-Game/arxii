# ADR-4089-B: Soulfray draws spin the shared outcome wheel by the shared rule

**Status:** accepted (owner rulings 2026-10-02 and 2026-10-03, #4089). **Related:** #924 (the
outcome wheel), ADR-4089-A (the Crossing climax ruling from the same issue).

Soulfray draws spin the same #924 outcome wheel by the same per-result rule used everywhere - a
roll result spins when any of its options is ticked (`Consequence.theater`) or can kill
(`character_loss`); the Soulfray Stage Builder's own "Spin the wheel" checkbox states this shared
rule rather than a Soulfray-specific one, so the checkbox keeps one meaning across the game. The
wheel always shows every authored option for the drawn tier, including one a character's modifiers
removed from the actual draw (a Can-kill row a non-lethal cast filters out) - the animation spins
past it and nothing on screen or in the payload reveals that it was filtered; the draw itself,
which face is selected, stays filtered, so a non-lethal cast still can never land on or be charged
with a death consequence. On the scene action path the Soulfray reveal plays after the action's own
wheels, and only to the caster - a Soulfray stage draw is the caster's own backlash, not something
the rest of the scene's audience watches. Telnet receives no wheel: it has no `roulette_result`
output, and the outcome itself was already applied identically for both clients, so there is
nothing telnet needs to show. **Rejected:** a landed-option trigger (spin only when the SELECTED
face is ticked or lethal) - that would make the wheel itself leak which rows a modifier filtered
out, since a drawn-but-filtered Can-kill row would spin on some casts and not others depending on
whether it happened to be the one picked; spinning on the tier's authored content instead keeps the
wheel's behavior constant regardless of what a modifier removed.
