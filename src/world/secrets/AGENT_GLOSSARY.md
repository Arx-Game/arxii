# Secrets glossary

**Secret**:
A hidden fact or relationship about one character (its `subject_sheet`, who is both the subject and sole owner), with a level, an optional category, and consequences. The missing fourth privacy primitive alongside Distinction (permanent trait), Condition (live state), and Resonance — a fact that must be earned and shared rather than a trait or state.
_Avoid_: private distinction, hidden flag, shared secret (a multi-party situation is two distinct single-owner Secrets).

**Secret Level (1–4)**:
An ordinal (`SecretLevel`: Uncommon Knowledge, Whispers, Carefully Kept, Dangerous) giving a secret its narrative weight and default share-scope. The 1–4 value is structural and load-bearing — only Level-1 player-flavor may be free-authored, and the value defaults a victim's reputation hit — while the display names are placeholder.
_Avoid_: tier, severity, depth.

**Secret Provenance**:
Where a secret came from (`SecretProvenance`: GM-authored, action-anchored, or player-flavor), read as a canonicity spectrum from canon down to unverified flavor. It drives the anchor-scales-with-level rule and OOC attribution; it is attribution, not a trust-warning.
_Avoid_: source, origin, trust level.

**SecretKnowledge**:
A roster-scoped record that one character holds a given secret, so knowledge follows the character across players. Holding the row is the fact layer; `knows_category` and `knows_consequences` are partial-knowledge layers that unlock independently and monotonically, so a secret's Unknown layers can persist per-knower even after the fact is out.
_Avoid_: known secret, CharacterSecret, secret grant.

**Act anchor**:
The recorded act a secret is the hidden truth behind (#1573) — held as optional FKs on the `Secret` itself (`legend_deed` → `LegendEntry`, `mission_deed` → `MissionDeedRecord`, `scene` → `Scene`). One act = one secret: the act may surface through several of these records at once, but they are co-facets of a single truth, never separate secrets. The distinct *consequences* (legend / criminal / society) are not the anchor — they ride the #1429 reputation payload. The FK lives on the secret (not a back-reference on the record) per ADR-0062.
_Avoid_: deed link, deed discriminator, one-secret-per-deed, evidence record (the raw-`Interaction` blackmail link is a later slice).
