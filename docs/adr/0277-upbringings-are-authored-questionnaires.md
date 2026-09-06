# ADR-0277: Upbringings are authored questionnaires, not a generalised anchor/mentor model

**Status:** Accepted (#3660, 2026-09-05, TehomCD ruling against the demo). Related ADR-0268, ADR-0269, ADR-0273.

**Context.** Upbringing prompts (`OriginTemplateSlot`) were either a free write-in or a
priced pick list. Nothing linked an answer to a real `societies.Organization`, tagged
when the tie was formed or what kind of tie it was, or attached any stake to it, so a
"raised by a household" or "sailed with a crew" Upbringing produced prose only, never a
row a later scene, GM, or renown check could reach. The first design pass generalised
this into a single anchor field plus a single mentor field on the Upbringing itself,
which a reviewer rejected as a demo shaped around one example rather than the general
authoring need.

**Decision.** An Upbringing is an authored questionnaire: `OriginTemplateSlot.kind`
(`QuestionKind`) is one of TEXT, PICK (the two existing shapes), GROUP, or PERSON. A
GROUP question's anchor comes from an authored source rule (`AnchorSource`): a pool of
every matching org, a named list, the same group an earlier GROUP question resolved to,
the served house, or the character's own family; the last two need no stored pick at
all, since `questionnaire.anchor_for` derives them fresh from the draft. Any question
may show only after an earlier one is answered, and a GROUP or PERSON question tags
what the tie was (`connection_kind`) and when it formed (`life_stage`). An answer on a
PICK or GROUP question may grant a Distinction, bundled at no extra cost, and a GROUP
answer may seed the anchor's opinion of the character through
`societies.renown.bump_organization_reputation` at finalize. The route into a
Beginning stays the Upbringing card itself, not a separate pick; staff author a whole
route (the Upbringing, its questions, and their answers) on one admin page, the
Upbringing Builder, credited to the operator on save. Membership in a staff family
continues to run through a Vacancy (ADR-0273); a questionnaire connection is a tie, not
a rank.

**Rejected.** A separate Connection model alongside `OriginTemplateSlot` (two authored
rows for one prompt). Letting a GROUP question anchor to a notable NPC rather than only
a real Organization. A person field bolted onto another question's kind, rather than
its own PERSON kind. Capping an Upbringing at one connection. A pick list standing in
for the route into a Beginning. A rulings form embedded in the demo page itself; the
reviewer's stated preference was worked examples plus feedback in chat, not another
authoring surface to maintain.
