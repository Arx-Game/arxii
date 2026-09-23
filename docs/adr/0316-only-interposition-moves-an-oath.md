# ADR-0316: Only interposition moves an oath

**Status:** Accepted (2026-09-23, #3983).

When a rung is granted to a house, `rehome_vassals` re-swears the chains beneath it — but only
where the new holder has been *interposed* between a vassal and the liege it already answered to
(a county sworn to the crown, with a duke now seated in between, owes the duke). Two other
candidates look identical from the Atlas and must not move: a house the new holder itself answers
to (the crown's own loose barony lying inside one of its vassals' counties), and a house whose
real fealty is elsewhere entirely and which merely owns one barony down here. The rejected
alternative was the **blanket containment test** `plant_rung`/`assign_holder` apply to a holder's
own oath (`_may_swear_to_containment_liege`: refuse whenever the candidate already has any
`FealtyEdge`). That reads correctly for a house being seated — it has no oath yet — but applied to
re-homing it refuses the one case re-homing exists for, since a vassal being re-homed *always*
already has an edge. Worse, doing nothing at all was not neutral: `swear_fealty`'s cycle guard
raises on the crown case, and because `assign_holder` is atomic the whole seating rolls back —
which at CG finalize is a founder losing their house at the last step. So the test is the
relationship between the candidate's current liege and the new holder's own liege chain, not the
mere existence of an oath: no oath at all, or an oath to somebody the new holder now answers to,
moves; anything else stays HELD, not sworn.
