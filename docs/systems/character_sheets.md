# Character Sheets — Source of Truth

CharacterSheet is the single anchor for all character-related data.

**Source:** `src/world/character_sheets/`

---

## The Model

`CharacterSheet` is OneToOne to ObjectDB (`primary_key=True` — shares pk), holding demographics/appearance fields. Every playable character has one.

The **narrative bio** (concept, real_concept, quote, the three Actor's Sheet answers `never_do`/`protect`/`fear` (#3621), background, obituary) *and* the **lineage FKs** (family, heritage, tarot_card, tarot_reversed, origin_realm) were sliced out into a separate **`Profile`** model (#1270, slices 1 + 3) so a cover identity can present its own fabricated bio *and* lineage. The sheet owns one `true_profile` (its real bio + lineage), and the PRIMARY persona points at it. `CharacterSheet` keeps read/write forwarding properties (`sheet.concept` → `true_profile.concept`, `sheet.family` → `true_profile.family`, with a `save()` cascade), so existing reads/writes — and all *mechanical* lineage reads — are unchanged; they always resolve to the real `true_profile`. **Cover display is wired** (slices 2 + 3): the profile serializer reads concept/quote/story **and lineage** from the *presented* persona's profile (`_presented_bio_profile`) — the real `true_profile` when revealed, a cover persona's own authored profile when presenting one, else blank/none (never the real bio or lineage for a non-revealed face). The real `fullname` and progression `path` stay reveal-gated (not part of the guise). The cover *authoring* form (letting a player fill in a cover persona's fabricated profile) is the remaining player-facing follow-up. `Profile.beginnings` is a further M2M, to `character_creation.Beginnings` through **`ProfileBeginnings`** (`source`, `note`, `gained_at`, #3775, ADR-0303): every origin the character holds, not just the one from character creation, so a Sleeper's recovered homeland or a reincarnation's remembered life adds a row instead of overwriting the first. `CharacterSheet.beginnings` forwards to `true_profile.beginnings.all()` and is read-only; rows are only ever added through `ProfileBeginnings` so each carries its own `source`.

## Privacy Tiers (#1271)

Each mechanical sheet section carries a player-controlled visibility tier
(`SheetVisibility`: `SELF` / `FRIENDS` / `PUBLIC`) — `stats_visibility`, `skills_visibility`,
`magic_visibility`, `goals_visibility` on `CharacterSheet`, defaulting to `SELF` (the #1109
"private by default" behaviour). **`standing_visibility` (#3906) is the one that does not**:
it defaults to `FRIENDS`, because which houses someone belongs to and what each thinks of
them is the kind of thing a friend would know and a stranger would have to ask about, and
`PUBLIC` is the opt-in for a character who wants their allegiances read off the page. The profile serializer resolves the viewer's openness once
(`_viewer_access_level`: staff/owner = SELF, on the owner's `PlayerAllowList` = FRIENDS, else
PUBLIC) and shows each section when access meets its tier (`SHEET_VISIBILITY_RANK`). The FRIENDS
allow-list lookup runs only when a section is actually FRIENDS-gated, so the all-default case adds
no query. Bio/story tiers (entangled with the presented-identity gating) and the player-facing
tier-setting UI are follow-ups.

## The Reference Sheet (#3898)

The web character sheet (`frontend/src/roster/pages/CharacterSheetPage.tsx`) is the
reference sheet an artist makes for a character, on the Arx Folio system the Gatefold
and character creation already speak. Its styles live in
`frontend/src/character_sheets/sheet.css`, scoped under `.refsheet`; the display
primitives are `character_sheets/components/sheet/`. That file deliberately does not
reuse `character-creation/cg.css`: CG's `.entry` is a *selection* control with a chosen
state and doors, and the sheet only ever describes.

**The plate** is the head: the art, the name with any `PersonaTitle`s composed into the
same `h1`, the concept, the quote, two short glance lines, and the looks strip. It is
painted in night literals in both themes — it is the cover, and a cover does not change
with the reader's lights. Nothing mechanical appears on it: no health, no fatigue, no
attributes.

**Eight sections** replace the old sixteen tabs. Five are public — Sheet, Physical,
Ties, Distinctions, Magic — then a visible break labelled "Yours only" and three the
character's own player reads: Knowledge (secrets, clues, gossip), Estate (purse,
carried, property, the land their organizations hold, agreements, the law) and Growth
(advancement, sheet-change requests, languages, origin story). Estate is named for what
it holds rather than "Holdings", which reads as fiefs in this genre and is not what the
section is; it is also the word the will copy inside it already uses (#3901). Friends left the sheet for `/profile/friends`: an OOC
trusted-partner list belongs to the account, not to a character.

**Gating is render-or-vanish.** A block a viewer may not read is absent, and the page
keeps its shape for a stranger, a friend and the owner alike — no empty-state cards. The
goals band and the abilities band are gated by the existing `goals_visibility` /
`stats_visibility` / `skills_visibility` tiers, which the serializer already enforces by
emptying those sections; the frontend renders what it is handed and never re-implements a
tier. A viewer who gets neither band is offered a rumor about the character in their
place. Condition on Physical reads as sentences for the owner and staff, and as one
observational line for everyone else.

**`looks` and `plate_ink`** are the payload's contribution. `_build_looks` returns the
character's tenure media with the `MoodOption` each is tagged with (`TenureMedia.look`),
the worn one first, so the plate can wear one and offer the rest beside it; the owner
clicking a look calls `POST /api/roster/entries/{pk}/set_profile_picture/`. A
non-privileged viewer receives only public-gallery images plus the worn one — a private
gallery's `allowed_viewers` sharing is honoured on the gallery pages and deliberately not
here, so the strip under-shows rather than risking a private image on a page anyone can
open. `plate_ink` (`PlateInk`: ember / verdigris / rose / night) is OOC chrome, ungated,
and picked in settings rather than on the sheet.

**`worn` and `mentors`** are the payload's other two contributions. `_build_worn` lists
what the character has on, and what separates viewers is the #2985 layer walk rather than
a visibility tier: `compute_worn_visibility` is the same predicate the look command and
the show/conceal verbs use, so a shift under a coat is hidden here for the same reason it
is hidden there. A covered piece is dropped for everyone but the owner and staff, who get
it with `is_hidden` set so the sheet can say it is there and unseen. This lives on the
sheet rather than on `EquippedItemViewSet` because that endpoint answers only for a
character its caller plays, which emptied the Wearing block for every visitor — and worn
things are the most visible things a character has. `_build_mentors` returns the active
`MentorBond` rows (#1165) in both directions, each saying what the OTHER party is; it is
owner and staff only, matching the covenant roles it sits beside, because a Mentor's Vow
is sworn inside a covenant.

Threads under Magic reuse the existing thread list endpoint, narrowed to one character by
`ThreadFilter.owner` (#3898) — the list is account-scoped, so without it an account with
alts read every character's threads on whichever sheet it opened.

**The composed panels were re-skinned, not merely reparented.** `RelationshipsSection`,
`KinshipPanel`, `ReputationTab`, `TitlesPanel`, `DistinctionsTab` and `SpellbookTab` now
draw in the sheet's own primitives, and each lost something that only made sense when it
was a tab of its own: the duplicate "Relationships" header a panel drew inside the
heading the sheet already draws, the soul-tether card whose entire body was the words
"No active soul tethers.", and the spellbook's four workbench links, which under the
section row read as a second navigation bar. A panel composed into a section draws no
heading at that weight — `Subheading` is the one it uses for a group inside a section.

**Estate's Domains block** (#3901) names the land the character's organizations hold:
the domain, whose it is, and the area it decorates. The gate is ACTIVE membership and
nothing more — `_build_domains` reads the character's personas' memberships where
`left_at` and `exiled_at` are both null. That a house holds a stretch of land is not a
secret anyone keeps; whether this character may walk into it is a different question,
answered by `LocationTenancy` against the land rather than by anything on the sheet.

The block exists because deleting it would have been worse. A `Domain` is org-owned
(`owner_org`, the #1884/#930 ruling) and a `Building` is individual-owned
(`owner_persona` is its only ownership field), so org land on a personal page muddies
what the section is — but a player coming onto a roster character may have no idea their
house holds a keep, and nothing else on the sheet could tell them. Render-or-vanish
matters more here than anywhere: most organizations hold no land at all, so the block is
absent far more often than it is present.

**Estate has no "Owed and Owing" block**, which the spec asks for. Half of it has
nothing to read: `currency.DebtInstrument` and both obligation models are
organization-to-organization, and no character-level debt exists anywhere in `world`. The
other half, contracts, DOES have a model — `currency.Contract` is persona to persona,
with collateral, garnishment and formality — and it has no frontend surface anywhere in
the app; Agreements covers wills, claims and settlements, not contracts. So the block is
absent because building it means building a contracts surface from nothing, which is its
own issue. It is not absent because the data was already shown elsewhere.

**Ties visibility was settled by #3906.** Covenant is PUBLIC — a covenant role is a thing
a character IS in the world, the way a title is, and the Titles block beside it has always
been public. Standing is FRIENDS by default with `standing_visibility` as the opt-in to
`PUBLIC`.

Both blocks now read the **sheet payload** (`standing`, `covenants`) rather than calling
the society and covenant-role endpoints. That is not a refactor for tidiness: all three of
those endpoints answer only for the characters the REQUESTER plays, so as a visitor they
returned nothing whatever the visibility field said, and as the owner they returned every
character on the account and had to be filtered client-side to the viewed persona.
`_build_standing` queries `OrganizationMembership` / `OrganizationReputation` directly off
the presented persona and `_build_covenants` reads `covenant_role_assignments` off the
sheet; `_section_visible(access, sheet.standing_visibility)` empties `standing` for a
viewer below the tier, so what the client renders is already the answer.

Both blocks then **vanish when empty**, and here render-or-vanish is a correctness rule
rather than a style one: a withheld section and an unaffiliated character arrive at the
client identically, so a line reading "They belong to nobody" would be a flat lie on
every stranger's view of a character who belongs to three houses. Vanishing also leaks
nothing — a hidden rail and an empty one look the same, which is what a privacy tier is
supposed to buy. Titles beside it keeps its empty-state line and is right to: it is
never withheld, so its empty state is always true. Note the prefetch
shape: `standing` deliberately does NOT ride a `personas__organization_memberships`
prefetch — a top-level prefetch through `personas` cannot reuse the `cached_personas`
Prefetch and re-fetches every persona to redescend, which cost four extra queries for
three rows of output.

**Three gaps were open questions rather than unfinished work, and each now has its own
issue.** A stranger's rumor band renders but is passed nothing, because which guideline a
rumor may draw from, and in whose words, needs a mechanically determined rumor system
first (**#3903**). The plate's portrait needs rights on public-facing art and flags so
viewers can filter by preference, with friends seeing whatever image someone is showing
(**#3904**); a look still does NOT follow the character's declared mood, since
`CharacterSheet.current_mood` is inward and owner-only (#2994) and driving a public
portrait from it would publish exactly what that ruling keeps private. And the Gift
sentence names no tradition, because `GiftEntry` carries no tradition field and tradition
membership lives on the character rather than the gift — provenance at acquisition is
**#3905**.

**The aura is a proportional strip**, three segments sized by their shares with the split
said in words beneath ("A fifth celestial, a third primal, the rest abyssal."). The strip
carries the proportions so the figures themselves never reach the page, which is how it
satisfies both the spec and the magic app's standing rule that player-facing data is
narrative rather than numerical. `.refsheet-aura` and its three segment rules had been
written and left unconnected; #3898's second review caught that, the same shape as
`plate_ink`.

**Two blocks appear that the demo does not draw**, both carried forward from the old
sixteen-tab page rather than added here, and both now in the sheet's own vocabulary
rather than the old page's utility classes. Worship (the public faith line, the owner's
Pray door, visions, and staff-only prayers) sits at the foot of the Sheet section; and
At a glance carries a Tarot row. Removing a live feature to match a drawing is not this
branch's call, so they are re-skinned and recorded.

Two things deliberately keep their old chrome. `OwnedDwellingsCard` and
`TenantedRoomsCard` under Estate are shared with the Renown page, so re-skinning them
would change a surface outside this issue; and the cards under Estate and Growth are
forms rather than reference reading. Both are recorded in the roadmap as remaining.

## Web Sheet Mechanics Display (#3042)

The `stats`/`skills` sections of `CharacterSheetSerializer` were always built (`_build_stats`/
`_build_skills`) and gated by the tiers above, but had no frontend consumer — a player's own
12 stats and skill ratings were invisible on the web sheet. `_build_stats` returns
**display-scale** values (`tv.value // STAT_DISPLAY_DIVISOR`, ADR-0193 — stats store internal
×10) so the client never has to know about the storage scale; `_build_skills` values are already
true-scale (skills store and display the same number). `frontend/src/character_sheets/components/
MechanicsSection.tsx` renders both on the character sheet's Sheet tab
(`roster/pages/CharacterSheetPage.tsx`), reading `useCharacterSheetQuery` and rendering whatever
`stats`/`skills` the API returns — it does not re-implement visibility client-side. The magic
section's `resonances` (claimed-resonance balances, already serialized by `_build_magic_resonances`,
#2032) similarly had no frontend consumer; `SpellbookTab.tsx` now renders a "Resonances" card
alongside Gifts/Motif/Aura. Per-trait development-point progress is NOT part of this payload
(deferred to #3039's landing) — the skill entry's `at_boundary` flag is the only progress signal
shown today.

## Related Models

All character-related models FK back to CharacterSheet:

- **`Profile`** (#1270) — the narrative bio surface a persona presents. `CharacterSheet.true_profile` (OneToOne) is the real bio; `Persona.profile` (FK) is the bio that face presents (PRIMARY → the sheet's `true_profile`; a cover persona may own its own). Null `Persona.profile` falls back to the sheet's `true_profile`.
- **`Persona`** (scenes) — IC identity of a character. FK via `character_sheet`. A character can have multiple personas (PRIMARY, ESTABLISHED, TEMPORARY). The unique PRIMARY persona per sheet is accessed via `sheet.primary_persona`.
- **`RosterEntry`** (roster) — tracks which character is being played and by whom. OneToOne to CharacterSheet.
- **`CharacterVitals`** (vitals) — health/status tracking. OneToOne to CharacterSheet.
- Mechanical systems (combat, magic, achievements, etc.) — FK to CharacterSheet.

## Primary Persona Invariant

Every CharacterSheet should have exactly one Persona with `persona_type=PRIMARY`. This is enforced by a partial unique constraint. The `primary_persona` cached property on CharacterSheet fetches it. If no PRIMARY exists, it raises `Persona.DoesNotExist` — intentionally loud, not a silent None.

## Character Creation

Use `world.character_sheets.services.create_character_with_sheet()` to create a playable character. It atomically creates the Character typeclass, CharacterSheet, and PRIMARY Persona in a single transaction. This is the blessed creation path — factories and the character_creation app both use it.

## Display Helpers

Three display tiers for character identity, primary implementations on Persona:

- **`display_ic()`** — Just the persona name. What IC observers see.
- **`display_with_history()`** — Adds tenure disambiguation (e.g., "Bob (Thomas #2)") when there's ambiguity; collapses redundancy when persona name matches character name.
- **`display_to_staff()`** — Full staff context including account: "Bob (Thomas #2, played by Fred)".

CharacterSheet has thin delegates that call `primary_persona.display_*()`:

```python
sheet.display_to_staff()                # uses primary persona
persona.display_to_staff()              # uses that specific persona
membership.persona.display_to_staff()   # context-pinned persona (e.g., GM table)
```

When a caller has a specific persona (membership, event enrollment, etc.), call display helpers directly on the persona. When you have only a sheet, use the delegates.

## Why Not CharacterIdentity?

`CharacterIdentity` existed historically as a separate model and was deleted in the 2026-04 refactor. Its only unique contribution was `active_persona` — which is now derived from `persona_type=PRIMARY`. Having two OneToOne peers (CharacterSheet + CharacterIdentity) hanging off the same ObjectDB was confusing to agents reading the code.

---

## Mood (#2994)

`CharacterSheet.current_mood` (nullable FK → `MoodOption`, `SET_NULL`, `related_name="+"`) is a
sticky declared internal state — mirrors `current_language`'s shape, but lives on the sheet (not
`Persona`) because a mask doesn't change how the person underneath feels. **INTERNAL and SILENT
by design**: `SetMoodAction` (telnet `feel <state>` / bare `feel` to clear, `actions/definitions/
mood.py`) writes only `current_mood`, never calls `message_location` or `record_interaction` — no
room echo, no scene Interaction row, no look/appearance rendering. It carries no mechanical effect.

Detection is earned, not ambient: `SenseMoodAction` (`sense_mood`) is the sole way another
character learns a mood, gated on the actor holding a `skills.Specialization` named "Empathy"
(value ≥ 1 — no thematically-right parent Skill exists in the catalog yet; flagged as a content
gap rather than force-fit) and resolved via `perform_check` against a `checks.CheckType` named
"Sense Mood" (also a content gap, same reason). Both gates fail cleanly with a vague in-fiction
message when the underlying content row doesn't exist yet, rather than crashing — they are seams
for the lore repo to fill, not code that needs re-touching once content lands. Success privately
reveals the target's current mood (or "their feelings are settled" when null) to the senser only;
the target is never notified, in either outcome (SILENT).

`current_mood` is exposed on `CharacterSheetSerializer`'s `identity.current_mood` — owner/staff
only, `None` for every other viewer (mirrors the age-axes leak-table pattern). `MoodOption` is a
curated, content-authored lookup (`character_sheets.moodoption` in `core_management
.content_export.CONTENT_MODELS`) — it ships EMPTY in code; states (angry, upset, happy, sad, calm,
flirty, PLACEHOLDER-extendable) arrive via the lore repo's content round trip.

## Enums (types.py)

```python
from world.character_sheets.types import MaritalStatus
# Values: SINGLE, MARRIED, WIDOWED, DIVORCED

from world.character_sheets.types import Gender as GenderChoices
# Values: MALE, FEMALE, NON_BINARY, OTHER
# Note: This TextChoices enum is separate from the Gender model below.
```

---

## Lookup Tables (SharedMemoryModel - cached, rarely change)

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `CharacterEnemy` | Who wants the character to fail, priced (#3621, ADR-0279) | `character`, `kind` (`EnemyKind`), `organization` / `family` / `figure_name`, `power_tier` (`EnemyPowerTier`), `reach` (`societies.EnemyReach`), `degree` (`EnemyDegree`), `price`, `why`, `public_line`, `secret`, `reason` (FK `EnemyReason`, #3709) (nullable), `status` (`EnemyStatus`: placed / pending). Written at CG finalize; `CharacterEnemyAdmin` recomputes the price when staff place a free-written one |
| `Heritage` | Origin story types (Sleeper, Misbegotten, Normal) | `name`, `description`, `is_special`, `family_known`, `family_display`, `first_appeared_ic` (#3663 — nullable IC date the first of the heritage were born; CG caps age at the whole IC years since, floor 18, via `character_creation.services.age_bounds`; Misbegotten = 980-01-01; set on production through `HeritageAdmin`), `chronological_age_unknown` (#2756 — Sleepers: CG leaves `ic_birth_year` null; everyone, the player included, sees "Unknown") |
| `Gender` | Canonical gender identities | `key`, `display_name`, `is_default` |
| `Pronouns` | Canonical pronoun sets (decoupled from gender) | `key`, `display_name`, `subject`, `object`, `possessive`, `is_default` |
| `MoodOption` | Curated declared-mood states (#2994) | `name`, `description`, `sort_order`, `is_active` |

Appearance traits are NOT here: the legacy `Characteristic`/`CharacteristicValue`/
`CharacterSheetValue` models were retired (#1119) in favour of the forms app
(`FormTrait`/`FormTraitOption`/`SpeciesFormTrait`/`CharacterForm`) — see
`docs/systems/forms.md`.

## Character Data

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `CharacterSheet` | Primary character demographics, identity, and source-of-truth anchor | `character` (OneToOne to ObjectDB, primary_key), **age axes (#2756, ADR-0172)**: `matured_years` (the maturation meter), `withered_years` (curse overlay), `aging_paused`, `ic_birth_year` (nullable; chronological derives vs `get_ic_now()`), `birthday_month`/`birthday_day` (celebrated date; Sleeper waking day) + derived `biological_age`/`apparent_age`/`chronological_age` properties (the old `age`/`real_age`/`birthday` columns are retired), `gender`, `pronouns`, pronoun fields, `species`, `social_rank`, `marital_status`, `additional_desc`, `true_profile` (OneToOne → Profile). Narrative bio (`concept`/`quote`/`background`/…) **and lineage** (`family`/`heritage`/`tarot_card`/`tarot_reversed`/`origin_realm`) are read/written through forwarding properties → `true_profile` (#1270). |
| `Profile` | The narrative bio + lineage a persona presents (#1270) | `concept`, `real_concept`, `quote`, `never_do`, `protect`, `fear` (the Actor's Sheet, #3621), `background`, `obituary`, `family` (FK roster.Family), `heritage` (FK), `tarot_card` (FK), `tarot_reversed`, `origin_realm` (FK realms.Realm), `beginnings` (M2M to `character_creation.Beginnings` through `ProfileBeginnings`, #3775). Referenced by `CharacterSheet.true_profile` and `Persona.profile`. `owning_sheet_or_none` is the reverse of `CharacterSheet.true_profile`, None for a cover profile no sheet owns as its real bio. |
| `ProfileBeginnings` | One origin a Profile holds, and why (#3775, ADR-0303) | `profile` (FK), `beginnings` (FK `character_creation.Beginnings`), `source` (`ProfileBeginningsSource`: `character_creation` / `recovered_memory` / `past_life`), `note`, `gained_at` (auto). Unique per `(profile, beginnings)`; a partial unique constraint allows only one `character_creation` row per profile. The set only grows - deleting a row revokes nothing. |

---

## Integration Points

- **Societies**: Personas are the identity layer for organization memberships, reputation, and legend
- **Character Creation**: `CharacterSheet` fields are populated during `finalize_character()`; use `create_character_with_sheet()` as the blessed creation path
- **Roster**: `RosterEntry` is OneToOne to CharacterSheet; `sheet.family` links to `roster.Family` (the FK lives on `Profile`; read via the forwarding property, #1270 slice 3)
- **Species**: `CharacterSheet.species`; per-species appearance palettes live in `forms.SpeciesFormTrait`
- **Tarot**: `sheet.tarot_card` for familyless character surnames (FK on `Profile`, forwarded)
- **Forms**: `CharacterSheet.build` links to `forms.Build` for body type
- **Realms**: `sheet.origin_realm` links to `realms.Realm` (FK on `Profile`, forwarded)
- **Scenes**: `Persona.character_sheet` FK links sheets to their personas; `sheet.primary_persona` accesses the PRIMARY
- **Vitals**: `CharacterVitals` is OneToOne to CharacterSheet
