# Secrets glossary

**Secret**:
A hidden fact or relationship about one character (its `subject_sheet`, who is both the subject and sole owner), with a level, an optional category, and consequences. The missing fourth privacy primitive alongside Distinction (permanent trait), Condition (live state), and Resonance — a fact that must be earned and shared rather than a trait or state.
_Avoid_: private distinction, hidden flag, shared secret (a multi-party situation is two distinct single-owner Secrets).

**Secret links (#4528)**:
`Secret.about_persona` (who the secret is about when not the subject: the demon behind a voice, a familiar, a person) and `Secret.story` (the story the truth belongs to, the fourth act anchor beside deed, legend and scene; `Story.anchored_secrets`). Staff-set, on `AuthoredSecretSerializer` only, never on the knowledge-scoped shape. The held distinctions a secret holds (`secret.distinctions`, a plain FK since #4528) are ticked from the secret's side on the Secret admin (`set_secret_distinctions`); a ticked one is private, an unticked one public again.
_Avoid_: a story or persona link on the distinction kind or the held row; "NPC link" as a field name.

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

**Reach** (`SecretGossip.area`, #4085):
The highest area a rumor has climbed to; every social hub inside it hears the rumor. A plant starts a rumor at the hub room's own area, and `climb_gossip` moves it one parent up each time its heat meets that level's `GOSSIP_CLIMB_THRESHOLDS` entry, merging with a row already there. A reach never descends: decay fades heat, only suppression to 0 ends the rumor. There is no fixed boundary and no "region" rung; a faint rumor is a street's, a hot one a kingdom's.
_Avoid_: region, gossip region, regional heat, scope.

**Smear**:
The one-move Level-1 accusation through the rumor mill (`plant_smear`, #1825): a single Gossip roll gates hub + skill + the target's hostile consent, mints the ACCUSATION secret, seeds its gossip heat at the hub's area, and plants the counter-clue whose difficulty the same roll sets. A miss mints nothing.
_Avoid_: slander (no such verb), gossip attack.

**Rebuttal**:
An `AccusationRebuttal` row (#1825): one character's public case against an accusation's credibility — the consentless defense (anyone holding the knowledge may refute at a hub; the Tom/Bob/Fred rule). One attempt per refuter, success or failure; success applies a partial compensating reversal. The full clear is justice-side nullification.
_Avoid_: disproof (nullification is the proof), counter-accusation (that's denounce, justice-side).

**Compensating reversal**:
`reverse_secret_exposure` — re-deriving what `expose_secret` applied (diffuse archetype deltas + relational org-victim severities) and bumping the negation, fraction-scaled. Not idempotent; callers own the once-only guard. `societies_exposed` is never un-set: the secret *was* exposed, the world just stops believing it.
_Avoid_: un-expose, reputation rollback.

**GRANT_SECRET effect** (#3071):
The `checks.EffectType` value letting an authored `ConsequenceEffect` hand a character `SecretKnowledge` when an outcome lands — the same `apply_all_effects` chokepoint `GRANT_CODEX` fires from. Its handler (`world.mechanics.effect_handlers._grant_secret`) calls `grant_secret_knowledge` with `knows_category`/`knows_consequences` left at their `False` defaults — the fact is known, the deeper layers are not, mirroring `GRANT_CODEX`'s "a scene hands you a lead, not the answer" UNCOVERED semantics without needing a parallel bypass (`SecretKnowledge` has no UNCOVERED-equivalent status field to bypass in the first place).
_Avoid_: secret reward, secret drop (not a loot mechanic — see the mechanics app's structured-consequences invariant).

**Hook** (#4397):
A top-level `Secret` (no `hook` link) a character carries that a GM may build on: a creation pick's secret, a staff-written one, a line the player left. Read with the truths under it by the GM running a table the character is seated at (`hooks_for_subject`, `truths_by_hook`, the table route). A past life is a hook until a GM makes it a truth.
_Avoid_: plot thread, story seed (a hook is a Secret row, nothing new), quest.

**Truth** (#4397):
A GM-authored, subject-unaware `Secret` pointing at a hook through `Secret.hook` (`author_truth`); one level only, the same subject. The player reads the hook until the truth is revealed through a `SecretKnowledge` grant.
_Avoid_: answer, reveal (the reveal is the grant, not the row), sub-secret.
