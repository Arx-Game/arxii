# ADR-0287: One CG point makes a physical feature distinctive, and a distinction can be held per feature

**Status:** Accepted (#3739, 2026-09-10). Extends ADR-0010 (FK direction) and the
#2632 normalized-appearance decision; relates to #2886 (item accent axes) and #2985
(markings).

**Context.** "Flaming crimson hair the colour of the dawn" and "red hair" are both
things players want to write, and the game needs both: the prose is what other
characters read, and the normalized `FormTrait`/`FormTraitOption` value is what
descriptor concealment, dye items, heredity and species palettes all read. #2632
settled that by keeping the normalized layer and adding a free per-trait descriptor
line, labelled "In your own words", on every trait row in character creation. Two
problems followed. The free line asked every player to write flavour for every trait
whether they had anything to say or not, and the reviewer found the label itself
condescending. And nothing let a player have a feature that is *actually* unusual:
an off-species colour, a scar people react to, horns that read as a crown. Meanwhile
`ModifierTarget.is_styleable` already carried three presence axes for item accents
(allure, menace, regal), of which regal had never been wired to anything, because no
courtly check existed to bind it to.

**Decision.** A **feature** is any trait row or any marking, species-required markers
included. Spending **one CG point** on it makes it **distinctive**, and that one point
buys three things at once: the description field opens (only then), the palette widens
to every option the trait carries including a new off-species "Unnatural" umbrella
(a strange colour is assumed to have a magical explanation), and the three presence
axes go up for sale on that feature. Each axis costs **2 a tier** and adds **+2** to
its axis a tier, in any combination on one feature; they reach 5 in play and stop at
**3** in character creation. A marking's own name and description stay free, so the
point buys only its axes. Mechanically this makes `Distinction` a thing a character
can hold **once per feature** (`taken_per_feature`), so `CharacterDistinction` carries
the feature it names and every draft-entry reader keys by `(distinction, feature)`
instead of by distinction. Regal is bound at last, to a newly seeded **Command**
CheckType (presence + Leadership): rallying troops to make a stand, appealing to the
people on your right to rule. A bonus travels with visibility — a marking-bound
modifier drops out while the worn layers cover that marking's region.

**Rejected.** *A free description line on every trait* (the #2632 shape): it asks
everyone for prose and singles out no one, and pricing the field is what makes a
distinctive feature mean something. *Graded adjective lists per tier* — the player
picking a lead phrase from an authored list per tier, which was the first design:
withdrawn as clutter, and it takes the words out of the player's hands. *1 to 5 ranks
on the description itself*: the description is not a magnitude. *A separate
"warped by magic" door for off-species colours*: a second gate for the same thing the
point already opens. *Making the axes cost what an item accent costs*: a physical
feature is meant to matter more than a garment, so a feature tier is +2 where an
accent rung is +1. *Naming the umbrella "Otherworldly"*: it carries connotations that
are inaccurate here; "Unnatural" is the word.

> Source: #3739, the reviewer's rulings in conversation on 2026-09-09 and 2026-09-10,
> and the demo the spec was approved off.
