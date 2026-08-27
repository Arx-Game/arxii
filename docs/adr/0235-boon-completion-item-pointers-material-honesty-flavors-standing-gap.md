# ADR-0235: Boon completion — knowledge-side item pointers, honest material refusal, sibling ask flavors, NPC-only standing-gap shift

**Status:** accepted (2026-08-27, #2540 slice 3)

Five related decisions from the slice-3 Boon-completion build (structured social asks riding
`SceneActionRequest`, see `scenes/CLAUDE.md`):

**1. Exact item pointers ride the knowledge side's own discriminated-target/subject-FK idioms,
not a new join table.** A held/vault-item Boon must name something the asker actually *knows
about* — so "does the asker have a pointer to this item" needed a real predicate
(`character_has_item_pointer`, `boon_services.py`). Rather than invent a standalone
`ItemPointer` model to join askers to items, the pointer rides the knowledge-object idioms that
already exist per surface: `Clue.target_kind=ITEM` (a new discriminated-target value, paired
`target_item_template` required + `target_item_instance` optional narrowing — mirroring the
existing `PERSONA_LINK` multi-discriminator exception) and `subject_item_template`/
`subject_item_instance` FK pairs on `CodexEntry` and `Secret` (mirroring their existing
subject-FK pattern). **Rejected:** a standalone pointer join table (`ItemPointer(sheet, item)`)
— it would duplicate what "the asker knows about this item" already means on three different
knowledge surfaces, and desynchronize the moment any one of them evolves its own notion of
"discovered." One migration (0175) adds all the fields; 0176 is choices-only (below).

**2. Pointer-gated named-item asks — no inventory browsing, ever.** The boon-options endpoint's
`pointer_items` field surfaces only the asker's OWN pointer-known items relevant to a target
(`pointer_known_items_for_target`), computed entirely from the asker's pointers. It is never a
query against the target's actual holdings. The asker's ask window is bounded by their own
knowledge, full stop — a design constraint that also closed a probing oracle: the first cut let a
pointer-less asker distinguish "item doesn't exist" from "item exists but I have no pointer" from
"item exists, I have a pointer, but they don't hold it" by iterating item ids and reading which
message came back. The fix round (`d10fcb37f`) reordered both `_validate_held_item_ask` and
`_validate_vault_item_ask` to check the pointer FIRST and fail every pointer-less case with the
identical `BOON_NO_POINTER_TEXT`, regardless of whether the id is real, held by the target, or
held by someone else — only once a pointer is confirmed does "they don't currently hold it"
become a safe, distinct message, because a pointer-holder legitimately knows the item exists.

**Reusable rule (oracle closure for knowledge-gated surfaces):** any surface gated on "does the
caller have prior knowledge of X" must make every non-knowing path return a byte-identical
response — same status code, same body shape, same message — across every dimension an attacker
could vary (item doesn't exist / exists but unpointed / exists, pointed, but ineligible for an
unrelated reason). Ordering the checks so the knowledge gate runs first, before any
downstream check that could leak a distinguishing signal, is the mechanism; identical output on
every non-knowing branch is the invariant. Generalize this to the next knowledge-gated ask
surface rather than re-deriving it from scratch.

**3. MATERIAL boon kind: honest unavailability, not never-ask-the-impossible.** The roadmap's
visibility-=-eligibility tenet (`design-tenets.md` §"Visibility = eligibility") says a gated
surface shouldn't present an option the caller can't actually take. A holdings-filtered material
category picker would satisfy that tenet directly — but it would also leak the target's private
wealth OOC (which categories they stock, in what depth) to every asker who opens the ask form,
independent of whether they ever submit. We ruled the category list STATIC and public (every
`MaterialCategory`, unfiltered by any target's bucket) and instead let a well-formed ask that
turns out to be impossible fail with an honest, in-fiction refusal at submit time
(`BoonUnavailable`, mapped to a 200 `{boon_refused: true, detail}` by
`SceneActionRequestViewSet.create` — see decision 3a below) rather than a 400: no row is created,
no roll fires, no consent burn, no affection drain, and a piloted target's queue never sees it.
This is "shopping, not rejection" — the asker browses a real menu and is honestly told the shelf
is bare, the same way an NPC merchant would say so, rather than the UI silently hiding the empty
shelf. **This refines, not violates, the visibility-=-eligibility tenet**: the predicate that
decides what's *offered* (the category list) is deliberately coarser than the predicate that
decides what's *grantable* (the live bucket check), and the gap between them is closed by an
honest runtime refusal instead of client-side filtering — the accepted trade being a boolean
"they don't have it" reveal (privacy-cheap) traded against a wealth-depth reveal (privacy-
expensive) that the naive filtered-picker approach would have made instead. Tier labels only
(MINOR/FAIR/GREAT, reusing money's vocabulary) are shown, never a computed amount — the granted
quantity is computed fresh AT FULFILLMENT (tier pct of the target's *current* bucket), the
deliberate money asymmetry (money freezes `amount` at ask time; material does not, because the
target's bucket can move between ask and grant in a way a purse mid-scene generally doesn't).

**4. Ask flavors are sibling templates with real action keys, not a payload variant.** Con a
Boon / Charm a Boon / Menace a Boon (Con / Seduction / Intimidation checks respectively, Menace at
+1 tier mirroring Seduce-harder-than-Flirt) are three additional `ActionTemplate` singletons
(`boon_con`/`boon_charm`/`boon_menace`, joining plain `boon` in `BOON_ACTION_KEYS`) rather than a
single `boon` template carrying a `flavor` field that selects the check type at resolution time.
**Rejected:** flavor-as-payload — per-flavor check type is exactly the kind of thing
`ActionTemplate` already exists to carry (the check type lives on the template, not a runtime
branch inside the Boon resolver), and a payload flavor field would need its own validation,
serialization, and a runtime dispatch the template system gives for free. All four templates
share one consent category (`boon`) and one resolver registration loop over
`BOON_ACTION_KEYS` — one opt-in, one fulfillment path, only the template (check type + name)
differs per flavor.

**5. The standing-gap audacity shift is NPC-only; a piloted target's own difficulty choice
always rules.** `npc_boon_tier_shift` (dial 2, the NPC-side relative-cost band) now sums the
existing relative-cost band with a new rank-gap term (`RANK_GAP_TIER_BANDS`, PLACEHOLDER
magnitudes): asking a higher-standing NPC for a boon gets additively harder per rank-gap
threshold crossed, and punching down or asking an equal never adds a tier. This shift is folded
into dial 2's NPC band and nowhere else — `action_services.py`'s piloted call site deliberately
omits `extra_tier_modifier`, so a live human defender's own chosen difficulty is never
overridden by the asker's standing gap. This follows the July piloted-consent ruling that a
piloted defender's own difficulty choice is always authoritative over any asker-side or NPC-only
mechanical dial.

**3a. The two migrations, both schema-only.** 0175 (`AddField` × 3: `Boon.material_category`,
`Clue.target_item_instance`, `Clue.target_item_template`) plus the codex/secret subject-item
FKs bundled in the same migration; 0176 is `AlterField` on `Boon.kind`'s choices to add
`MATERIAL`. Both are schema-only (ADR-0013 — no data migrations pre-production); splitting the
choices alter into its own migration was incidental to the build order (the MATERIAL kind
constant landed after the FK fields), not a deliberate two-step rollout.

**Schema-gap fix carried from Task 2's review:** the create endpoint's alternate 200
`{boon_refused, detail}` shape was undocumented in OpenAPI. Fixed in this slice by documenting it
as a `responses={201: ..., 200: inline_serializer(...)}` status-keyed dict on `create`'s
`@extend_schema` — the same pattern already used throughout `magic/views.py` and
`missions/views.py` for a status-varying response, rather than introducing a new polymorphic-
response convention for one endpoint.

**Rejected globally:** a standalone `ItemPointer` join table (see decision 1) and a
holdings-filtered material category list (see decision 3) were the two live temptations this
slice had to resist — both would have been the more "obviously correct" first instinct and both
would have cost more than they bought (schema duplication in the first case, a privacy leak in
the second).
