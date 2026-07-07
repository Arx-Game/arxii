# ADR-0099: Custody clearance requests are identity-based, not protected_subject-pk-based

## Context

`CustodyVerdict` (ADR-0098's enforcement seam) deliberately never serializes the blocking
`StoryProtectedSubject`'s pk to the blocked actor — only `custodian_gm_username` and a generic
"under another story's custody" message (mirrors ADR-0086's privacy posture: never the story,
beat, or reason). That is correct for the block itself, but the Task 6 first pass built
`POST /api/custody-clearances/` to accept only a `protected_subject` pk — which the blocked GM
never legitimately learns. A blocked outsider GM who only knows the custodian's username had no
self-serviceable way to request clearance at all; the only path left was an OOC ask to staff or
the custodian to hand over a pk, defeating the point of a GM-to-GM request flow.

## Decision

**`CustodyClearanceRequestSerializer` accepts either of two mutually exclusive paths:**

- **pk path** — `protected_subject` directly (unchanged, still useful once a GM already knows
  the row, e.g. from their own story's authoring UI).
- **identity path** — `subject_kind` + exactly one typed pointer (`subject_sheet`/
  `subject_item`/`subject_society`/`subject_organization`/`subject_label`), the same
  `_subject_identity` tuple `check_subject_custody` matches against. The identity path resolves
  to *every* active `StoryProtectedSubject` row sharing that identity — a subject can be
  independently protected by more than one story — and fans out one `CustodyClearance` per
  match in a single atomic call.

This makes the identity path the only door a blocked GM needs: they already know what they
tried to appear-with/harm/remove (their own action's target), so `subject_kind` + the typed
ref/label is information they already have, unlike the internal pk.

**Residual disclosure, accepted:** submitting an identity that matches an active protection
always creates a PENDING clearance and notifies that protection's custodian — the identity
probe is self-announcing (the custodian learns a clearance was requested, same as any
legitimate ask) and duplicate-guarded (a live PENDING/ESCALATED request from the same requester
at the same scope is skipped, not re-created, avoiding the partial-unique-constraint error a
retry would otherwise hit). This mirrors `check_subject_custody`'s own accepted disclosure
shape (learning "this identity is protected" by trying and being told "request clearance from
GM X") rather than adding new leakage: an identity that resolves to zero protections is
rejected with the identical `does_not_exist`-shaped error the pk path already raises for an
inactive/missing pk, so a non-oracle guarantee holds on both paths — no extra generic-message
logic was needed to make them indistinguishable.

## Rejected

- **Keep pk-only, and expose `protecting_subject_id` to the blocked actor** so they have a pk
  to submit. Rejected outright: this directly reverses `CustodyVerdict`'s privacy contract
  (ADR-0086's posture, "never the story, beat, or reason") for the sake of request-flow
  convenience — the whole point of `protecting_subject_id` staying internal/audit-only.
- **A staff-mediated lookup endpoint** ("ask staff which pk this is") instead of a
  self-serviceable identity path. Rejected: it reintroduces the exact staff-bottleneck the
  GM-to-GM clearance flow exists to avoid, for a request pattern (I want to act on the thing I
  can already see/name) that doesn't need staff in the loop at all.

> Status: accepted · Source: #2001 Task 6 review (PK-discoverability gap); extends ADR-0098
> (custody vs. boundaries axis), ADR-0086 (disclosure posture).
