# ADR-0221: Codex containers hide when their subtree is empty; knowledge is an account-wide union

Date: 2026-08-19. Status: accepted (Tehom ruling).

Codex categories and subjects are pure taxonomy, but they carry prose descriptions.
When a subject has no visible entries, that description becomes the canonical public
text for its topic - readers treat navigation prose as lore - and an all-secret branch
leaks its existence through its name. So the API hides any category or subject whose
subtree contains no entry visible to the requester, uniformly across tree, list,
retrieve, and children endpoints (a hidden subject 404s on direct retrieve, so its
description cannot be read by probing ids). Rejected alternatives: per-subject
visibility flags (a second visibility system to keep in sync with entries - entries
are the one unit of secrecy) and frontend-only hiding (leaves descriptions readable
via the API). Accepted cost: a corpus with nothing public renders an empty codex page.

In the same change, reader knowledge became the union across all the account's
playable characters (with `?character=<roster_entry_id>` to narrow, and per-character
`known_by` in entry payloads), replacing the old implicit first-roster-entry
selection - which both violated the no-implicit-first-item API rule and hid
multi-character players' knowledge. Rejected alternative: a mandatory single active
character (session-selected), which would have made the codex unreadable as a
whole-account reference and required session plumbing the web codex does not need.
