# Character Secrets (#1334)

Hidden facts about a character — cover identities, crimes, private distinctions, secret
relationships (affairs, blackmail, an unclocked soultether). The privacy layer of the mystery
loop.

**Source:** `src/world/secrets/`
**Umbrella issue / design:** #1334

> **Build status:** Slice 1 (the content model + authoring) is built. Discovery (clue-target
> wiring), the per-knower held/partial-knowledge record, the profile secret-tab display,
> action-anchored minting (blackmail/murder/affair/crime → Secret + Evidence), the Deed↔Secret
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
| `subject_sheet` | FK `CharacterSheet` — who the secret is about |
| `second_party_sheet` | FK `CharacterSheet`, null — the named other for a two-party secret (affair, blackmail). Ownership follows consequence; a mutually-damning secret names both |
| `level` | 1–4 (`SecretLevel`) — narrative weight + default share-scope. **Names are PLACEHOLDER** (spec §10 fork; values are load-bearing, labels are provisional) |
| `category` | FK `SecretCategory`, null — what it's about. **Null = Unknown** (first-class) |
| `consequences` | Text, blank = Unknown |
| `content` | The secret as narrated (player- or GM-authored prose) |
| `provenance` | `SecretProvenance` ∈ GM / action / player-flavor |
| `author_persona` | FK `Persona`, null — the narrating persona (OOC attribution); null for GM |

### `SecretCategory`
Staff-editable lookup (`SharedMemoryModel`) so the taxonomy grows without a migration. A
secret with no category reads as **Unknown**.

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

## Boundary with Codex

Cut on **authorship**, not topic. **Codex** = canon lore (subjects, history, world) authored
under lore authority — scarce, reviewed. **Secret** = a hidden, earned, consequential fact
about a concrete entity — self-serve. They share one substrate: the knowledge ledger + the
clue/discovery loop (`world/clues/`). The same entity can have both (an artifact's lore in
Codex, its hidden command-word as a Secret), cross-linked. Decision rule: *"Is this
canon-true-about-the-world (Codex), or a hidden fact about a specific entity with a keeper and
consequences (Secret)?"*

## Planned integration points (later slices)

- **Clues:** add a `SECRET` value to `ClueTargetKind` + FK on `Clue` (already anticipated, #1143)
  so secrets are discovered through the same Search / `acquire_clue` loop.
- **Deeds:** cross-link a Secret to its sibling `MissionDeedRecord` — one act, two tellings
  (public embellished deed vs. private true secret); earning the secret recontextualizes the legend.
- **Distinctions (#1269):** replace the PUBLIC/PRIVATE visibility flag with a `secret` flag + level.
- **Scenes:** `PersonaDiscovery` becomes the PERSONA_LINK kind of secret.
- **Tehom boundary:** soul/tether/sineater marker known-ness surfaces *via* Secrets (reference,
  not replacement).
