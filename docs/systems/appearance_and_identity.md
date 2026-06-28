# Appearance & Identity Architecture

> Cross-cutting architecture that unifies **who a character is known as** (Persona),
> **what their body actually is** (Form), **what they're projecting over it**
> (disguise/illusion), and **what their canonical body is** (true form + natural
> baseline). Per-system mechanics live in [`forms.md`](forms.md) (form trait
> machinery), [`scenes.md`](scenes.md) (Persona, scene recording), and
> [`character_sheets.md`](character_sheets.md) (the source-of-truth anchor). This doc
> is the layer that says how those compose.

> **Status:** design — captured 2026-06-15 from a long design conversation. The
> implementation lands in slices (see *Decomposition*); slice 1 is the only one fully
> scoped here. Builds on **#1044** (active-persona resolution — merged), which made
> `active_persona_for_sheet` the canonical "which face right now."

## Tenets it inherits (already canon — do not duplicate, reference)

From [`docs/roadmap/design-tenets.md`](../roadmap/design-tenets.md):

- **Players are always aware when another player can see their RP** (tenet). The
  concealment floor here is **OOC presence disclosure** — you can hide *who* you are
  and *what you look like* (an invisibility effect may hide your traits), never *that
  you are present*: a concealed/invisible presence still surfaces an OOC tell ("an
  invisible presence is here"). "Watch a scene without participating" = enter as a
  separate persona.
- **IC-meaningful state FKs to Persona, not AccountDB** — descriptors, reputation,
  and identity all hang off Persona (the IC layer), never the account (the OOC
  player).
- **Per-PC visibility; UI displays are by persona, never by account** — rendering is
  scoped to what the *viewer's* persona would know.

One **new** cross-cutting tenet this work proposes adding to that corpus:

- **Named faces are public; concealment is opt-in.** A persona with a public name is
  shown by name to *everyone*, familiar or not (accessibility of RP). Obfuscation is
  something a player *does* (a mask, a disguise, an anonymous throwaway persona) — it
  is never the default state of being unknown. (Classic MUD name-scrambling
  conflates "I don't know you" with "you're hidden"; we reject that.)

## The core model: four independent questions

The system must always be able to answer these **separately** — the bugs all come
from collapsing two of them together:

| # | Question | Layer | Real? | Changed by | Reverts / reveals to |
|---|----------|-------|-------|-----------|----------------------|
| 1 | Who are they **known as**? | **Persona** | — (identity) | switching persona | — |
| 2 | What is their body **actually, now**? | **Current real form** | **REAL** | shapeshift | the return point (true form) |
| 3 | What are they **projecting** over it? | **Fake overlay** | **FAKE** | disguise / illusion | the current real form, when pierced |
| 4 | What's their **canonical / natural** body? | **True form + natural baseline** | **REAL** | nothing (it's the anchor) | — |

Form and Persona are **orthogonal axes** — proven by the worked examples: a con
artist changes persona with an *identical* body; a curse changes the body and
*suppresses* the persona. Neither can be derived from the other.

## Layer 1 — Persona (identity, social)

- Existing `Persona` (`world/scenes`): `PRIMARY` / `ESTABLISHED` / `TEMPORARY`,
  `is_fake_name`, plus prestige/fame fields (reputation is **per-persona** — a
  criminal alt's infamy never touches the primary).
- **Creation flow (#1127).** PRIMARY is minted once at character creation; everything else goes
  through the designed, validated services `scenes.services.create_persona` (durable ESTABLISHED,
  capped by `settings.MAX_ESTABLISHED_PERSONAS_PER_SHEET`, staff bypass) and `create_mask` (a
  TEMPORARY anonymous mask, optionally applying a #1110 disguise overlay and switching the worn
  face). Faces: telnet `persona create <name>` / `persona mask <name>` and the web
  `PersonaViewSet` `create-established` / `create-mask` actions. The raw `ModelViewSet` create was
  removed — these are the only creation surfaces. They create the persona and **nothing else**, so
  the *Privacy invariant* below holds structurally (no descriptor is ever copied from a sibling).
- **Named/public personas** (PRIMARY, ESTABLISHED) render **by name to everyone** —
  the accessibility guarantee.
- **Anonymous personas** (`is_fake_name`, typically TEMPORARY — the mask) render as a
  composed **sdesc** ("a man in a stag mask") until discovered.
- **Two kinds of secret**, both driving mystery loops:
  - **Hidden link** between two *public* faces (Bob *is* Robert) — the protected
    unit; discovered via `PersonaDiscovery` / investigation. Showing each public
    face freely never leaks the link.
  - **Hidden face** — a deliberately anonymous presentation; the name beneath is
    discovered through play.
- **Descriptor overlay** — the per-trait flavor string, scoped **`(Persona × FormTrait)`**
  (e.g. red hair rendered "Rusty Auburn" as Bob, "Crimson" as Robert). This is the
  **privacy-bearing layer**: distinctive, identifying, and therefore **never
  auto-attached across personas** (see *Privacy invariant*). It is *not* on the form
  value — one shared form must be able to carry different descriptors per persona.
- Active face resolves via `active_persona_for_sheet` (**#1044**).
- **Switching the active face** flows through `SetActivePersonaAction` (key
  `"set_active_persona"`, `actions/definitions/personas.py`, **#1347**) — a REGISTRY
  action with `target_type=SELF` and kwarg `persona_id`. Both the web
  (`PersonaViewSet.set_active`) and telnet (`CmdPersona` / `wear-face` alias,
  `commands/persona.py`) route through `dispatch_player_action` → `action.run()`;
  `world.scenes.services.set_active_persona` remains the sole mutator underneath.
  Bare `persona`/`persona list` on telnet renders the caller's own personas and marks
  the active one; `persona <name>` or `wear-face <name>` triggers the switch.
  **Scope boundary:** the pose/sdesc read-path (`record_interaction` /
  `_characters_to_active_personas`) is **not** changed here — making poses reflect the
  presented persona (with privacy/discovery/freeze) is **#1109**'s scope.
- **Web surface** (`world/forms/views.py:AlternateSelfViewSet`,
  `frontend/src/game/components/FormSwitcher.tsx`, #1111 slice 4) —
  `GET /api/forms/alternate-selves/` lists caller-owned alternate selves with an
  `is_active` flag; `POST /api/forms/alternate-selves/shift/` and `revert/` dispatch
  `ShiftFormAction` / `RevertFormAction` through `dispatch_player_action`. The
  top-bar `FormSwitcher` mirrors `PersonaSwitcher` and surfaces revert errors
  returned by the action.
- **Telnet `form` namespace** (`commands/form.py`, #1111 slice 4) — `form list` shows
  the active alternate self, the available alternate selves, and whether revert is
  blocked; `form shift <name|id>` triggers `ShiftFormAction`; `form revert` triggers
  `RevertFormAction`. All dispatch through `dispatch_player_action`, converging with
  the web form dispatcher on the same action seam.

## Layer 2 — Form (physical body, REAL)

- Normalized traits via `FormTrait` / `FormTraitOption` / `CharacterForm` /
  `CharacterFormValue` (`world/forms`). `TraitType` is `COLOR` / `STYLE`.
- **Three real anchors, not one:**
  - `current_real_form` — what the body is right now (= true form unless shapeshifted).
  - `true_form` — the **shapeshift return point**: the current real *human* body
    *including* accumulated cosmetics (blue-dyed hair, etc.).
  - `natural baseline` — the **origin/genetic** values per mutable trait (the brown
    hair under the dye). The "wash it out / reset to natural" target. *Distinct from
    the return point.*
- **Cosmetic change** (the common case — hair dye, makeup, restyling) = a **real,
  in-place edit** of `current_real_form`'s *mutable* traits. There is no concealment
  and nothing to "see through" — her hair simply *is* blue now. It updates the
  baseline a later disguise overlays on / a shapeshift returns to.
  - Requires a **mutability tag** on traits: cosmetically self-editable (hair
    color/style, makeup) vs fixed (height, base build, species markers — magic only).
  - Requires a **change log** (when, which persona/player, from→to, optional note) +
    the persisted **natural value** — so a *roster handoff* doesn't lose "what was it
    originally," and "let's wash it out" has an answer.
- **Shapeshift** = swap `current_real_form` to a different **real** form (`FormType.ALTERNATE`),
  with a **return point** (true form). Dimensions:
  - **Voluntary vs involuntary** — Lily's controlled wolf-out (self-toggled,
    self-revertible, persona intact) vs a rage/curse (triggered, self-revert blocked,
    reverts only when an external `revert_gate` clears).
  - **Duration** — reuse `DurationType` (`SCENE` / `GAME_TIME` "until the full moon" /
    `REAL_TIME` / `UNTIL_REMOVED`) + `expires_at`. Permanent = no expiry.
  - **Persona-suppression** is a property of the *instance*, not of shapeshifting —
    a flag/state ("in control" vs "not herself"), identity unchanged.
  - **Combat profile** — a battle form / dragon carries mechanical stats. The form
    record is the shared anchor; the combat profile is the **senior dev's** side
    hanging off it.
- **Available-forms repertoire** — which forms a character *can* take (innate
  werewolf, learned dragon shape), gated by species/magic. `SpeciesFormTrait` is a
  start; the "forms I can become" set is its own thing.

## Layer 3 — Fake overlay (disguise / illusion, FAKE)

- A layer painted **over** `current_real_form`; the real form is unchanged beneath,
  and the overlay carries **reveal metadata**:
  - **Mundane disguise** (wig, dye-to-deceive, fake horns) → defeated by
    perception/inspection.
  - **Magical illusion** → defeated by dispel / see-magic.
  - Pierce it → the viewer sees `current_real_form`.
- **Cosmetic vs disguise is structural, not physical** — same hair dye in-fiction.
  The distinguisher is **whether a different real form is being preserved underneath
  to hide.** Cosmetic edits reality (no hidden truth); disguise overlays over a
  preserved, hidden reality. Two player actions: "change my appearance" vs "apply a
  disguise."
- **Stacking** (open decision) — disguise over a shapeshift, illusion over a disguise.
  Decide single-slot vs an ordered stack pierced layer-by-layer.
- Descriptors can attach to overlays too (a disguise has its own flavor).

## Layer 4 — True form & natural baseline (the anchors)

Covered in Layer 2's "three real anchors." The key non-collapse: **natural baseline
(origin) ≠ true form (return point)** — washing out dye returns to *natural*;
reverting a shapeshift returns to the *current real* (cosmetics included).

## Alternate-self lifecycle (slice 4)

The alternate-self (shapeshift / cover-identity) seam is intentionally decoupled:
**control is independent of the shift**.

- **Assumption** — `world.forms.services.assume_alternate_self(sheet, alt)` swaps the
  form and/or persona facets, creates the stat-suite (`ModifierSource` +
  `CharacterModifier`) and ability-suite (`CharacterTechnique` rows tagged to that
  source), and records return anchors on `ActiveAlternateSelf`. Assumption is **not**
  gated by `in_control`; forced/inadvertent shifts (moon madness, rage) are the point.
- **`CharacterSheet.in_control`** — a `@cached_property` derived from active conditions
  whose `ConditionCategory.alters_behavior` is True (rage / possession / charm /
  mind-control). It is **not** a stored flag and not a per-status name lookup.
- **Revert** — `world.forms.services.revert_alternate_self(sheet)` restores the captured
  form/persona anchors and deletes the granted modifier + technique rows. Revert is
  **blocked** while `not sheet.in_control` and raises `RevertBlockedError`. Only
  revert is blocked; assumption stays allowed.
- **Removing an `alters_behavior` condition does NOT auto-revert the form.** It
  re-derives `in_control=True`, which unblocks a later self-revert. The form persists
  after the condition clears. The canonical instance is the fury `Berserk` condition,
  seeded with a `Control` category carrying `alters_behavior=True`; it is cleared by
  the existing `RestoreSenseAction` (`restore_sense`) calm-down action.

## Player-facing action seam

The two alternate-self verbs are real `actions.base.Action`s on the shared
`action.run()` seam (ADR-0001):

- **`ShiftFormAction`** (`actions/definitions/forms.py`, key `"shift_form"`) —
  assumes an `AlternateSelf` owned by the actor's sheet. `target_type=SELF`, kwarg
  `alternate_self_id`. **Not gated by `in_control`**; forced/inadvertent shifts
  (moon madness, rage) use the same path. A foreign or unknown id returns a
  uniform failure message to avoid leaking repertoire information.
- **`RevertFormAction`** (`actions/definitions/forms.py`, key `"revert_form"`) —
  reverts the active alternate self. `target_type=SELF`, no kwargs. Catches
  `RevertBlockedError` while `not sheet.in_control` and surfaces it as a failure
  `ActionResult`. No active alt-self also returns a failure result.

Both wrap `world.forms.services.assume_alternate_self` / `revert_alternate_self`;
  telnet and the web dispatcher converge on the same action path.

Service details and the stacking guard (permanently-known techniques are not
overwritten) live in [`forms.md`](forms.md).

## The single render composition

There is **one** resolution, used by telnet **and** web (today they diverge — telnet
reads legacy `Characteristic`, web reads the TRUE form; both ignore disguises). For a
viewer **V**:

1. Start from `current_real_form`'s normalized traits.
2. If a `fake_overlay` exists **and V has not pierced it**, swap in the overlay's traits.
3. Apply the **active persona's descriptors** where the trait is present.
4. Resolve the **name**: public-named persona → the name; anonymous persona → composed
   **sdesc**; if V holds a `PersonaDiscovery` for it → the real identity (per-viewer).
5. V is **always told a presence is there** — never nothing; a concealed/invisible
   presence surfaces an OOC marker ("an invisible presence is here") rather than silence.

**Truth query** (the owner, staff, and game mechanics) ignores overlays and reads
`current_real_form` + `true_form` + all personas — **ground truth**. So there are
exactly **two views**: the owner/staff ground-truth view, and everyone else's
composed-and-gated view.

## Visibility, accessibility & attribution rules

- **Named public faces are shown to all** (PC *and* named NPC) — accessibility. The
  divide is **named/public vs unnamed/faceless**, not PC vs NPC. ("If it has a name,
  you can talk to it" is the new-player signal.)
- **sdesc is triggered by concealment, never by unfamiliarity.** The composing
  machinery exists; only its trigger changes.
- **NPC/world deed attribution is probabilistic** — whether a faceless NPC / the
  world pins a deed on your persona is a *chance*, not automatic (deniability, and the
  humour of a deed misattributed). This is the existing **room-traffic / deed-spreading**
  system; the appearance layer only supplies *which persona acted*.
- **Presence is always disclosed to the player** (hard tenet). An invisibility effect
  may hide traits but never bare presence (an OOC "invisible presence is here" tell).
  Undisclosed lurking / scry-from-a-distance → redesign to surface presence, or use a
  separate persona.
- **Recorded scenes freeze the presented persona.** A logged scene where Robert acted
  stores *Robert* forever — never re-resolved to Bob later, or it retroactively outs
  people. (Scene/interaction records already carry `persona_ids`.)

## Real vs fake — the truth ledger

- `current_real_form` is **REAL** — a shapeshift genuinely *is* the toad; there is
  nothing "underneath" to see through; it has a return point.
- `fake_overlay` is **FAKE** — pierceable, real form beneath.
- **True-seeing ≠ pierce-a-fake.** Revealing "this dragon is actually Lily" reads the
  shapeshift's `return_form`/persona link — a different reveal verb than dispelling an
  illusion. Both exist; don't conflate them.

## Privacy invariant (the whole guarantee, in one rule)

> A descriptor is authored **independently per persona** and **never auto-attaches**
> from another persona of the same character — blank by default, no "copy from my
> real face" pre-fill, no template that carries it over. Deliberate reuse (a chosen
> tell) is allowed; accidental/default reuse is structurally impossible.

Outing-by-descriptor happens *only* when one distinctive string appears on two
personas of the same character. Search is fine (a search for "crimson" surfacing many
crimson-haired people is the feature working). The single failure mode is accidental
cross-persona sameness — and the invariant above makes it impossible. It is **testable
as one assertion**: creating a persona/disguise leaves its descriptors empty; no code
path copies a descriptor from a sibling persona.

## Anti-reinvention ledger

| Surface | Verdict | Evidence |
|---|---|---|
| `Persona` + `active_persona` resolution | **BUILT & WIRED** | `world/scenes/models.py`; `active_persona_for_sheet` (#1044); set-active wired via `SetActivePersonaAction` (web + telnet, #1347) |
| `PersonaDiscovery` | **BUILT** | `world/scenes` (per scenes guide) |
| `CharacterForm` / `FormType` (TRUE/ALTERNATE/DISGUISE) / `CharacterFormState` / `switch_form` / `get_apparent_form` | **BUILT, partly wired** | `world/forms/models.py:202-302`, `services.py:18-64`; wired to a forms API endpoint, **not** to character-appearance rendering (`_build_appearance` reads the TRUE form) |
| `DurationType` + `TemporaryFormChange` | **BUILT** | `world/forms/models.py:215-318` — covers shapeshift/overlay durations |
| Legacy `Characteristic` skin/eye/hair | **BUILT & WIRED (to retire)** | `character_sheets/factories.py:280-393`; read by telnet `item_data` — **duplicates** the FormTrait definitions |
| Persona ↔ Form link | **ABSENT** | grep → 0; the two systems are disconnected |
| `(Persona × FormTrait)` descriptor | **ABSENT** | genuinely new — the core net-new surface |
| Trait **mutability** tag | **ABSENT** | small new flag on `FormTrait` |
| Natural baseline + change log | **ABSENT** | new |
| Two-slot active state (`current_real_form` + `active_fake_overlay`) | **BUILT (#1110)** | `forms.CharacterFormState.active_form` (real) + `active_fake_overlay` + `overlay_kind` (`DisguiseKind`); `apply_disguise`/`remove_disguise`; `get_presented_appearance(pierced=)` swaps the overlay in unless pierced (the pierce *contest* stays the senior dev's) |
| Single render composition (gated by viewer) | **PARTLY WIRED (#1325)** | scalar fields ARE viewer-gated: `_build_appearance` exposes exact `height_inches` only to owner/staff (others get the coarse `height_band` label via `get_height_band`) and shows the free-text `description` only when `reveal_identity`; form-trait *overlay* selection still reads the TRUE form (ignores `active_fake_overlay`) — that part remains not wired |

**Consolidation to ratify:** retire the legacy `Characteristic` path for skin/eye/hair
so `FormTrait` is the single home (kills the telnet-vs-web duplication).

## Ownership boundaries

- **This substrate (ours):** persona-scoped descriptors, form trait values, cosmetic
  editing, natural baseline + change log, the render composition, and the *slots*
  other systems write into (`current_real_form`, `return_form`, `active_fake_overlay`,
  `revert_gate`, in-control flag).
- **Magic / combat / conditions / scars (senior dev's domain):** illusion casting &
  dispel, shapeshift spells & triggers, the **berserker-rage condition + calm-down
  contest**, perception-vs-disguise contests, scars/aging, and the **combat profiles**
  of forms. The substrate exposes slots; those systems fill them.

## Decomposition (slices)

1. **Slice 1 — everyday appearance (ours, no magic).** Retire legacy → FormTrait;
   `(Persona × FormTrait)` descriptors; cosmetic in-place editing of mutable traits;
   natural baseline + change log; mutability tags; per-persona scoping that **degrades
   gracefully** to the single-persona case; the single render composition. Serves the
   noblewoman *and* roster continuity. **Shippable; the spec target.**
2. **Slice 2 — multiple identities (ours).** Multi-persona descriptors → the privacy
   invariant (Bob/Robert); anonymous personas → sdesc; `PersonaDiscovery` wiring;
   recorded-scene persona freezing.
3. **Slice 3 — concealment (ours + perception).** Fake overlays (disguise/illusion),
   reveal metadata, stacking. **Substrate shipped (#1110):** `active_fake_overlay` + `overlay_kind`
   (`DisguiseKind` MUNDANE/MAGICAL) on `CharacterFormState`; `apply_disguise`/`remove_disguise`;
   `get_presented_appearance(character, *, pierced=False)` presents the overlay unless pierced, with
   the owner/staff ground-truth read passing `pierced=True`. **Single-slot** for now (the ordered-stack
   open decision is deferred). The **pierce contest** (perception-vs-disguise / dispel) is the senior
   dev's domain and writes into these slots — a separate issue.
4. **Slice 4 — shapeshift (mostly senior dev).** Voluntary alternate forms first (Lily
   controlled, near-free from `ALTERNATE`); then involuntary/rage as a
   conditions-driven state; durations; combat profiles.

## Open decisions (resolve at spec time)

- Overlay **stacking**: single slot vs ordered stack.
- **Eye colour**: default to *not* freely cosmetic (contacts = a mundane disguise)?
- **Cosmetic friction**: free, or gated by a consumable/salon? (Lean low-friction —
  it's a common action.)
- **Persona-suppression** representation (flag on the form-state vs on the persona).
- **Natural baseline** granularity: per-trait snapshot vs full-form snapshot.

## Worked examples (every case maps cleanly)

| Case | Form | Persona | Descriptor | Notes |
|------|------|---------|-----------|-------|
| **Bob the Great** | true form (red hair, human ♂) | PRIMARY: Bob | "Rusty Auburn" | the public primary |
| **Robert D'Vile** | **same** true form | ESTABLISHED: Robert | **"Crimson"** | shared body, hidden *link* |
| **Stag Mask** | same form | TEMPORARY (anonymous) | — | sdesc until discovered; concealment = the temp persona |
| **Slimy Toad** | toad form (swap, involuntary) | suppressed & **locked** | — | curse; reverts on `revert_gate` |
| **Noblewoman dyeing hair** | edits her *real* form's mutable traits | her one persona | "Robin's-egg" | cosmetic; natural baseline = brown |
| **Roster handoff** | current real (blue) | inherited | — | change log + natural baseline answer "what was it originally" |
| **Lily — controlled wolf-out** | ALTERNATE real form (voluntary) | persona intact (still Lily) | — | self-revertible; combat profile |
| **Lily — rage** | same wolf form (involuntary) | in-control flag = false | — | reverts when allies *calm her down* (a condition) |
| **Dragon duel** | high-power ALTERNATE form | (could be suppressed or kept) | — | combat profile mandatory; true-seeing reveals it's her |
