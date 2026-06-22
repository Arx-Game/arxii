# Character Secrets (#1334)

Hidden facts about a character — cover identities, crimes, private distinctions, secret
relationships (affairs, blackmail, an unclocked soultether). The privacy layer of the mystery
loop.

**Source:** `src/world/secrets/`
**Umbrella issue / design:** #1334

> **Build status:** Slices 1–3 built — content model + authoring (slice 1), **discovery**
> (slice 2: the held/partial-knowledge record + the SECRET clue-target), and the **secret-tab
> display** (slice 3: the known-secrets API + the React tab, locked layers shown as "Unknown").
> Action-anchored minting (blackmail/murder/affair/crime → Secret + Evidence), the Deed↔Secret
> cross-link, the #1269 distinction migration, and the CG nudge are **later slices** of #1334.

---

## The core idea

Bio and story stay **fully public**. Sensitive information is *relocated* into Secrets that
must be earned, shared, and that carry consequences. The only privacy primitive is "this is a
secret, and here's who knows it." A `Secret` is the missing **fourth primitive** alongside
Distinction (permanent trait) / Condition (live state) / Resonance — a hidden FACT or
RELATIONSHIP, which is neither a trait nor a state.

## Models

### `Secret`
A hidden fact, anchored to a subject.

| Field | Purpose |
|---|---|
| `subject_sheet` | FK `CharacterSheet` — who the secret is about, **and its sole owner** |
| `level` | 1–4 (`SecretLevel`) — narrative weight + default share-scope. **Names are PLACEHOLDER** (spec §10 fork; values are load-bearing, labels are provisional) |
| `category` | FK `SecretCategory`, null — what it's about. **Null = Unknown** (first-class) |
| `consequences` | Text, blank = Unknown |
| `content` | The secret as narrated (player- or GM-authored prose) |
| `provenance` | `SecretProvenance` ∈ GM / action / player-flavor |
| `author_persona` | FK `Persona`, null — the narrating persona (OOC attribution); null for GM |

### `SecretCategory`
Staff-editable lookup (`SharedMemoryModel`) so the taxonomy grows without a migration. A
secret with no category reads as **Unknown**.

### `SecretKnowledge`
A character's held knowledge of a secret — roster-scoped (like `CharacterClue`, so knowledge
follows the character across players). Holding the row is the **fact** layer; `knows_category`
and `knows_consequences` are the **partial-knowledge layers** that unlock independently (and
monotonically — never re-hidden), so a secret's Unknown layers can persist per-knower even after
the fact is out.

## The load-bearing invariant — anchor scales with level

`Secret.clean` enforces it: **only Level-1 player-flavor secrets may be free-authored.** A
Level-1 flavor secret ("terrified of the color blue") has *no mechanical effect*, so whether
it's "true" is moot — there's nothing to be disappointed by. Anything heavier must be
**GM-authored** (canon) or **action-anchored** (minted by a mechanical action — true because it
happened). This is what structurally stops a player from free-writing a Dangerous-tier "I
killed a god" and having it read as canon. Provenance is *attribution*, not a trust-warning;
canonicity is read off author + anchor + level (a spectrum: GM-canon → action-anchored →
player-flavor).

## Services (`services.py`)

- `author_secret(...)` — author a secret, enforcing the invariant (raises `SecretError`).
- `author_player_flavor_secret(...)` — the only path a player may free-write: Level-1 flavor,
  attributed to their persona.
- `grant_secret_knowledge(*, roster_entry, secret, knows_category=False, knows_consequences=False)`
  — record that a character knows a secret, unlocking layers (idempotent, monotonic). The single
  entry point discovery surfaces call.
- `secret_known_to(secret, roster_entry)` — whether a character holds the fact of a secret.

## Discovery (the clue loop)

Secrets are discovered through the existing investigation loop, not a parallel system. `Clue`
gained a `SECRET` `target_kind` + `target_secret` FK (#1334); `grant_clue_target` teaches the
secret's fact via `grant_secret_knowledge`, and `target_already_known` reflects held knowledge.
So a planted/searched SECRET clue grants the secret on acquisition exactly like a CODEX or RESCUE
clue.

## Display — the secret tab

`GET /api/secrets/known/?subject=<CharacterSheet pk>&viewer=<RosterEntry pk>` returns the secrets
the **active viewing character** holds about that subject (newest first), paginated. The
serializer renders each held secret with locked layers as **"Unknown"**: the fact (`content`)
always shows, but `category` / `consequences` read "Unknown" when the viewer hasn't unlocked that
layer *or* the secret leaves it unplaced. The frontend `SecretsTab` (a tab on
`CharacterSheetPage`) renders the list; Radix unmounts inactive tab content, so the query only
fires when the tab is opened.

> **IC scope invariant:** IC knowledge scopes to the **active character**, never the account.
> `KnownSecretViewSet` scopes to the single `viewer` RosterEntry the caller passes, validated
> via `RosterEntry.objects.for_account` (so the param can't reach another account's knowledge);
> no/unowned `viewer` → no secrets. The frontend resolves the active character from
> `state.game.active`. An alt knowing a secret never surfaces it while you play a different face.

## Reputation consequences — the reveal bridge (#1429)

A secret is an **unrevealed fact**; revealing it feeds the existing renown/reputation engine
(`world/societies/`). `expose_secret(secret, *, societies)` (the reveal→reputation bridge) fires
two channels, one-shot:

- **Diffuse / philosophical.** The secret's `archetypes` (M2M → `societies.PhilosophicalArchetype`)
  are dot-producted against each newly-exposed society's principles — so the *same* fact reads
  positive to an ambition-prizing society and negative to a pious one. Tracked per society via
  `Secret.societies_exposed` so re-exposure never double-fires. Reuses
  `societies.renown.apply_archetype_society_reputation`.
- **Relational / targeted.** A `SecretVictim` names an entity directly harmed; on first exposure
  it takes a hit **independent of its philosophy** (an org that prizes cunning still turns on you
  for killing its head). **Organization** victims get an `OrganizationReputation` delta
  (`severity`, or the level default from `DEFAULT_VICTIM_SEVERITY_BY_LEVEL`) via
  `societies.renown.bump_organization_reputation` — the first gameplay writer of org reputation.

**Persona victims — the victim decides.** A persona victim's effect is **never auto-applied**
(the relationship system is consent-gated and player-driven). Instead, when the victim *learns
the secret* — through personal discovery / sharing / a confession, or because it went **public**
(public knowledge reaches the victim too) — they are **prompted** to decide a relationship effect
of their own toward the perpetrator via the normal relationship flow. The hook lives in
`grant_secret_knowledge` (the single point a character learns a secret): on first learn, if the
learner is a registered `SecretVictim.persona` **and** the character is run by an account
(`roster.selectors.get_account_for_character`), a `NarrativeMessage` prompts them. NPC victims
have no one to decide, so nothing fires. `expose_secret` grants PC victims the knowledge so the
same hook prompts them when the secret goes public.

Reputation attaches to the subject's **primary persona** (only established/primary identities
accrue reputation). A *guided* one-click grievance prompt, the `magnitude`/fame axis, org-level
diffuse interpretation, the *exposure trigger* (how individual `SecretKnowledge` propagates to
society-level exposure — the gossip slice), enforcement (wanted/blood-feud conditions,
hostile-territory consequences), and propaganda (granular re-framing of the diffuse reading) are
**later slices** of the #1429 sub-epic.

## Boundary with Codex

Cut on **authorship**, not topic. **Codex** = canon lore (subjects, history, world) authored
under lore authority — scarce, reviewed. **Secret** = a hidden, earned, consequential fact
about a concrete entity — self-serve. They share one substrate: the knowledge ledger + the
clue/discovery loop (`world/clues/`). The same entity can have both (an artifact's lore in
Codex, its hidden command-word as a Secret), cross-linked. Decision rule: *"Is this
canon-true-about-the-world (Codex), or a hidden fact about a specific entity with a keeper and
consequences (Secret)?"*

## Planned integration points (later slices)

- **Deeds:** cross-link a Secret to its sibling `MissionDeedRecord` — one act, two tellings
  (public embellished deed vs. private true secret); earning the secret recontextualizes the legend.
- **Distinctions (#1269):** replace the PUBLIC/PRIVATE visibility flag with a `secret` flag + level.
- **Scenes:** `PersonaDiscovery` becomes the PERSONA_LINK kind of secret.
- **Tehom boundary:** soul/tether/sineater marker known-ness surfaces *via* Secrets (reference,
  not replacement).
