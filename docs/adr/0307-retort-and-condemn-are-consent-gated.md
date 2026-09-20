# ADR-0307: Retort and Condemn are consent-gated by rivalry or by choice; Praise and Nominate never are

**Status:** Accepted (2026-09-20, #3941).

#2160 shipped Retort as a button on every public journal entry — any reader could answer any
writer's entry with an unconsented public rebuttal, an antagonism surface with no opt-out.
#3941 adds `ResponseType.CONDEMN` (praise's antagonistic opposite, XP mirrors retort:
`CONDEMN_GIVEN_XP`/`CONDEMN_RECEIVED_XP` alias `RETORT_GIVEN_XP`/`RETORT_RECEIVED_XP`) and gates
both Retort and Condemn — never Praise or a Nomination, which stay open on every readable
entry — behind consent: `CharacterSheet.retort_consent` (`RetortConsent`: `RIVALS` default,
`ANYONE`) is the writer's own dial, checked by the one predicate
`journals.services.can_retort(viewer_sheet, author)`, which is true when the author set
`ANYONE`, or when an active, non-pending `CharacterRelationship` exists in either direction
between the two with progress on a negative-sign track (`RelationshipTrack.sign`) — "rival," for
now, defined structurally rather than by a dedicated relationship kind, so when the
relationships pass adds one it narrows inside this single function and no caller changes.
`create_journal_response` enforces the gate server-side (the UI only hides the buttons), and a
refusal raises the same neutral `JournalError.UNAVAILABLE` used elsewhere in the app (ADR
precedent: #2996's block rejection) — a rejection never confirms or denies a rivalry, matching
the block-probing threat model. Rejected alternatives: leaving Retort ungated (the shipped
#2160 behavior — a harassment surface with no writer recourse); and a per-entry consent toggle
instead of a sheet-level one (rejected because consent here is about who may address *the
writer*, not about any one piece of writing — a per-entry flag would need to be re-declared on
every future entry and would still leave already-posted entries exposed to a writer who changes
their mind).
