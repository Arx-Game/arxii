# ADR-4209: A family page prints no tier words; full names on the roll, short names in the tree

**Status:** Accepted (2026-10-09, ApostateCD)
**Issue:** #4209
**Related:** ADR-0097 (kinship is a person-node graph with truth vs public record), ADR-0098
(houses are organizations), ADR-0218 (derived display names and née grammar), ADR-0311 (a
ward is household, never of the name)

## Context

A family had no page of its own: its tree was reachable only through a played member's
sheet, its description was drawn nowhere a player reads, and every link that named a house
landed on the members-only org page. #4209 gives each `Family` one page keyed by its pk. Two
questions about what that page prints were real forks, and both were ruled on the demo
canvas.

## Decision

**No definition-tier words on any player kin surface.** The roll, the tree, the selected
entry and the sheet's Kin block never print `Kinsperson.definition_tier` ("standing",
"name only", "pc"). A played person's name is a link to their sheet, and that is the only
distinction a player needs: whether someone has a sheet is implicit in whether they can be
clicked. The tier stays on the payload and in staff surfaces (admin, the Almanach), where
it is a staff concern.

**Full-formal names on the roll and the selected entry; a page-relative short form in the
tree.** The roll prints `full_display_name` (ADR-0218: style, first, née segment,
particle, family). The tree prints a tree form composed by the same grammar over the same
facts: a person of the page's family prints the first name alone, plus `ne <BirthFamily>`
when taken in and born elsewhere, because the page head already says which family this
is and a taken-in member's birth family is the one fact that adds context; anyone else
prints the common degree (first + particle + their own family) so a relative who is not of
the name keeps their name. No "married in" or "connected" tag: the name already carries
that. The dagger for the deceased stays, as the viewer is entitled to see it (#3983).

**The roll reaches one hop past the name.** `family_tree_for` adds a member's visible
parents and children, each hop through the same per-viewer `fact_visible` gate, so a
secret relative appears only for a knower and for staff.

## Alternatives rejected

- *Keep the tier words as a reader's aid.* They distinguish standing NPC from NPC from
  name-only, which only staff care about; for a player the link already says what matters,
  and the words were chrome on every node of a large tree.
- *A new `NameDegree` for the tree form.* The familiar degree is bare first with no née
  segment, and the tree form depends on which page is being read, not on the person, so it
  is a per-tree composition (`tree_names_for(people, within=family)`), not a stored
  preference.
- *Tags for taken-in and non-member people.* "Married in" repeats what `ne <Birth>` says;
  "connected" repeats what a non-member's own family name says. Dropped.
- *An org-keyed public face instead of a family page.* A commoner family has no org, and
  every member has a family, so the page is family-keyed and shows the house's gate when
  an org exists (ADR-0098).
