Expectations for the round-2 evidence run, written from the #5125 spec (rulings 4, 7, 8, 14, 16-19, 22-26, 28, 29)
and the staff-authored numbers I seeded (steps Trace 2 / Some 4 / Rich 7 / Massive 10 points; curve 2->2, 4->4, 7->6,
10->8, 15->10, 20->11; cap 12; related share 50%; call-up cost 3 anima; harvest thread bonus 5, AP cost 2). Nothing
here comes from running the code.

Item 4 (taper). Mira (fire, thread level 100) casts in Cinder Hall (fire 10 = Some = 4 points) wearing a coat that
carries fire at Some (4) and holding a brand that carries fire at Some (4). Expect three source lines of +4 points
each (12 points) and ONE total power that is less than 12 (the sum of each source alone, 4 + 4 + 4), read off the
curve as 8. The cast ledger has one line per source and the lines add up to the total. Each extra source adds no
more than the one before: power for 1, 2, 3 sources is 4, 6, 8.

Item 5 (related share, no chain). Substances authored: fire~light related, light~ice related, fire and ice have no
relation. Mira in Sunlit Hall (light Massive, 10 points): before she perceives light the card says only
"Something here strengthens your fire" with a positive amount; after a Magesight success names the light the card
names light, says it is related to fire, and the amount is half of Massive (5). Mira in Frost Cave (ice Massive):
no line from ice at all, before or after she perceives the ice (relations never chain), and the cast ledger has no ice line.

Item 7 (good success). Ilsa (ice) in The Vault (fire Rich 30, light Some 10, stone Massive 100). Plain Success:
her look ends with the stone only. Critical Success (a good success): her look names stone, fire and light.
Leaving the room clears it.

Item 9 (thread bonus). In The Ash Lair, Mira (thread on Pyrecraft) is offered the harvest with "+5 from your thread on
Pyrecraft"; Maren (holds Pyrecraft, no thread, same everything else) is offered it with no thread line. The same
dice give Mira a check total exactly 5 points above Maren's.

Item 10 (no Primum in ordinary places). In The Forge (hot, no authored Primum) Mira `extract` says there is nothing
to extract and `extract fire` is refused; no Primum item appears; no action points or fatigue are spent. In The Ash Lair
Ilsa (has not perceived fire) `extract fire` is refused with the same plain words and costs nothing; after she casts
Magesight (plain success names the strongest substance, fire) `extract` offers it and `extract fire` mints Primum and
lowers the lair.

Item 12 (label). In the web client Tomas (a mage of an unrelated Gift) clicks Mira in the room, then her worn Ember
Coat, and the item panel shows "Carries fire".

Item 13 (held gear). The Ash Brand sitting in Mira's bag adds nothing to her Kindle card. Once she wields it (a hand
slot) the card gains a fire line for the brand of +4 and the power goes up; removing it takes the line away.

Item 14 (call-up). `callup fire` in The Forge raises the place by one step (Trace to Some), costs the one shared amount
(3 anima, or free where her control covers it), writes one call-up row and sends one system line. Every Resonance
balance she has is the same before and after.

Item 15 (property). Every technique of the major Gift Pyrecraft carries the property "fiery" read at call time. Clearing
the technique's stored marks, or saving the technique admin page with the property unticked, leaves it carried
(has_property true, in effect_property_ids_by_technique). A technique of the minor Gift Second Sight carries nothing.
The Power Builder page for an application that needs "fiery" still lists Kindle as a technique that does it, with the
property ticked, and saving that page with it unticked keeps it carried.
