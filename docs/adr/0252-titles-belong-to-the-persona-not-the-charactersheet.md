# Titles belong to the Persona, not the CharacterSheet

`CharacterTitle` (#1522) hung its earned-title record on `CharacterSheet`. The Rite of
Honors (#3466) can mint a title for a deed done behind a mask — a disguise, an
established/temporary Persona distinct from the character's own face — and a
sheet-scoped title would surface that deed on the character sheet, outing the player
wearing the mask to anyone who could see it. #3466 retargets the model onto `Persona`
(renamed `PersonaTitle`): a title is how the world names a *face*, and Legend, the system
titles are drawn from, is persona-scoped throughout (`LegendEntry.persona`,
`PersonaLegendSummary`, spread, knowledge). The sheet-scoped title was the anomaly, not
the rule. `maybe_grant_deed_title` lands the title on `deed.persona` — the face that did
the deed — so an honor mints a title only where the deed itself already lives, and it can
never surface on the sheet of whoever was wearing the mask.

Achievement-sourced titles (the pre-existing `RewardDefinition` TITLE path, `_grant_title`)
resolve to the character's **PRIMARY** persona, never their active one. An achievement is a
sheet-level fact about who a character *is* — a stat crossing a threshold — so the title
belongs to their real identity; using the active persona would stamp the achievement onto
whatever disguise happened to be worn at the moment the stat ticked over, which has nothing
to do with the disguise itself.

**Rejected: gate the mint and withhold the title from a masked earner.** An earlier shape
of the fix left the title on `CharacterSheet` and simply refused to grant a title when the
earning persona was not the primary one, rather than retargeting the model. Rejected on two
grounds: it punished the masked player by denying them a title they had legitimately earned
merely for wearing a mask when they earned it, and it left a conditional (`if persona is not
primary: skip`) that someone could later regress, quietly reintroducing the exact outing
hazard this ADR closes — the retarget removes the hazard structurally, the gate would only
have policed it.

> Status: accepted · Source: #3466 · Extends #1522 (achievement titles); companion to
> ADR-0251 (the honor ceiling)
