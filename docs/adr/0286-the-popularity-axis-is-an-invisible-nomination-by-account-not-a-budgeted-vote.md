# ADR-0286: The popularity axis is an invisible nomination by the account, not a budgeted vote

**Status:** Accepted (#3738, 2026-09-09). Amends ADR-0115 (applause is three axes): the
*popularity* axis keeps its place but changes mechanism. Related ADR-0033, ADR-0237.

**Context.** ADR-0115 kept applause split across votes (popularity), kudos (graciousness)
and reactions (expression). The votes axis was the Arx I shape: a weekly budget of seven
per character plus one per scene finished, spent on poses, scene participations and
journals, settled on a log curve capped at fifty with Memorable Poses at three, two, one.
The reviewer ruled it the wrong shape of the game (2026-09-09): uncapped, votes were
meaningless; capped, they made people RP early or late in the week to spend them, and the
scene bonus rewarded scene spam.

**Decision.** The popularity axis is a **nomination**: "I am voting this person for good
RP because of this." It hangs off a piece of prose the nominator read this week and could
see (a pose through `Interaction.objects.visible_to`, a public or revealed journal entry),
and it names the character who wrote it. One **account** nominating one **character** in
one week is one nomination however many pieces it cites; alts and personas collapse to the
account, and two characters of one player are two nominees because XP is per sheet. There
is **no budget**: nothing to spend early or lose at week's end; the scarcity is that you can
only nominate what you saw this week, which also makes "vote for a friend whether they RP'd
or not" impossible without policing. A nomination is **invisible** to the nominee: no
toast, no running count, no names, no public tally, only the settled XP at week's end,
because knowing who voted for you creates pressure to return it. Settlement pays four paths
on one stepped curve (the reviewer's tiers to 133, then widening by half): nominations in
general by distinct people from 3, the character's own most nominated prose a flat 1, best
in scene by scene wins from 1 with ties paying everyone, and the game's most nominated
journal a flat 1 with ties paying all. The highlight reel still ranks on the axis but its
payload carries no count of it.

**Rejected.** Keeping a budget with a gentler curve (the use-it-or-lose-it pressure is the
budget itself, not its size). Counting scenes or poses instead of distinct people (rewards
volume; distinct people cannot be farmed, which is why the very popular are paid more on
the curve, not less). Merging the nomination into kudos or reactions (kudos toasts in real
time and reactions are public by design; invisibility is the point). A game-wide "most
nominated prose" (per person, so anyone nominated at all has one). Dropping the diminishing
tail (once the tenth nominator changes nothing, nobody bothers, the original complaint
about uncapped votes from the other side).

> Source: #3738, the reviewer's rulings in conversation on 2026-09-09.
