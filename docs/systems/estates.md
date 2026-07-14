# Wills & Estate Settlement (#1985)

A character's death opens a **settlement window**; the estate executes through the
first of three doors — a funeral's finish, an executor's will-reading, or the
deadline sweeper — never by staff hand and never blockable by an idle player
(ADR-0133). Wills are the unilateral member of the **agreements family**
(`Contract`, #928, is the bilateral member); the family is a UI hub (the sheet's
Agreements tab), deliberately not a shared model.

**Source:** `src/world/estates/`. **API prefix:** `/api/estates/`. **Frontend:**
`AgreementsPanel` (+ `BequestEditor`/`ExecutorEditor`), a `CharacterSheetPage` tab.
**Action:** `will_reading` (REGISTRY, `actions/definitions/estates.py`). **[BUILT &
WIRED]** as of #1985.

## Models (`src/world/estates/models.py`)

| Model | Purpose |
|---|---|
| `Will` | OneToOne → CharacterSheet; `testament_text` (read aloud at the reading); freely edited while alive, service-frozen once a settlement exists |
| `WillExecutor` | will FK + `scenes.Persona` FK; any one tagged executor can perform the reading |
| `Bequest` | will FK, `kind` (`BequestKind`: SPECIFIC_ITEM / COIN_AMOUNT / ALL_COIN / BUILDING / BUSINESS / RESIDUARY), matching target FK, typed `recipient_persona` XOR `recipient_organization`; one RESIDUARY per will (partial unique); items/businesses require persona recipients (orgs cannot hold either surface) |
| `EstateSettlement` | OneToOne → CharacterSheet; `deadline`, `status` (PENDING/SETTLED/PARKED), `settled_via` (FUNERAL/READING/AUTO) |
| `EstateClaim` | settlement FK + ItemInstance FK + typed claimant pair — an inherited grievance over an unrecovered theft; claimant-visible only, the holder is never notified |
| `EstateConfig` | pk=1 singleton: `settlement_window_days` (default 14 real days, PLACEHOLDER) |

## Services (`src/world/estates/services.py`)

- **`open_settlement(sheet)`** — called from the single death writer
  (`vitals.services._mark_dead`, which also stamps `Kinsperson.is_deceased` and fires
  the previously-unwired `handle_death_for_pacts`). Sets the sweeper deadline and
  notifies executors best-effort.
- **`execute_settlement(sheet, via=…)`** — THE one idempotent execution path, atomic
  + `select_for_update`, PENDING-only (first door wins). Order: resolve the **estate
  heir** → debts → bequests (kind-major, `order` within kind) → residuary sweep →
  contract party substitution → end tenancies/employment → mint claims. PARKED
  (escheat unresolvable while assets need a home) rolls back to ZERO estate
  mutations — a staff queue, never a half-estate.
- **Estate-heir chain** (every fall-through lands on the next link): valid RESIDUARY
  recipient → `resolve_intestate_heir` → `resolve_escheat_org`. Invalid recipients
  (dead/retired persona) fall through; no chained inheritance — a dead heir's own
  estate never receives on their behalf.
- **`resolve_intestate_heir(sheet)`** — (a) family-org head: lowest-tier active
  member persona of an org anchoring a `Family` the deceased held a live
  `FamilyMembership` in, who is themselves living family (vassals never qualify);
  (b) public-record next of kin (`viewer=None` kinship reads — hidden kin never
  auto-inherit): wedlock spouse → eldest child → elder living parent → eldest
  sibling (constants PLACEHOLDER); sheeted, living kin only.
- **`resolve_escheat_org(sheet)`** — nearest ancestor Area (self first, plain
  `parent` walk — no AreaClosure dependency) carrying a `Domain` with an
  `owner_org`; primary-home region first, death location's region as fallback.
- **Debts before bequests** (anti-loophole): unfulfilled one-shot NOTARIZED
  `ContractTerm`s the deceased owed + building `upkeep_arrears` pay from the purse
  first, partial when it runs dry (no item clawback). Debts owed TO the deceased
  survive via party substitution — the estate heir takes the contract seat
  (killing your creditor cancels nothing); with no heir at all the contract cancels.
- **Ademption**: a bequeathed item the estate no longer owns is skipped — except a
  hot item stolen from the deceased mints its `EstateClaim` to the *named* recipient
  instead of the estate heir.
- **Org heirs / escheat**: coin → treasury; buildings → `LocationOwnership` (org)
  with `Building.owner_persona` nulled; items → ownership CLEARED (free loot — the
  org "distributes as they want" through play); businesses wind down
  (`active=False`). Item and business records are persona/sheet-scoped surfaces.

## Ownership, theft, and the hot-goods gate

Theft moves the live owner pointer (`steal`, ADR-0091) — history lives in the
permanent `OwnershipEvent` ledger (new event type `INHERITED`, in
`PROVENANCE_EVENT_TYPES`). `world.items.services.provenance` answers
`has_unresolved_stolen_provenance(item)` / `stolen_victim(item)`: hot = the latest
theft's victim never got it back. The `receiving-stolen-goods` consent category
(data-seeded under `antagonism`, default-deny, accessor
`receiving_stolen_goods_category()`) gates hot-item transfer at `give()` and at
estate delivery; the refusal (`RecipientConsentDenied`) is category-generic so the
provenance never leaks. Blocked bequests fall through the estate-heir chain.

## The three doors

| Door | Seam | Notes |
|---|---|---|
| Funeral | `ceremonies.services.execute_will` (kept signature; body delegates) | per honoree at `ceremony_finish`; safe no-op for long-dead honorees |
| Will-reading | `will_reading` REGISTRY action | executor-persona gated; emits the testament to the room |
| Sweeper | `estates.auto_settle` (`game_clock/tasks.py`, hourly) | fires past `deadline`; **retire is deliberately NOT a door** (ADR-0133 — instant retire must not yank the estate from under a planned funeral) |

## API (DRF, `/api/estates/`)

`wills/`, `bequests/`, `executors/` — own-character CRUD (404-not-filtered; staff
see all); serializer-enforced freeze + kind/target coherence (mirrors `clean()`).
`settlements/` — read-only, executors + staff. `claims/` — read-only, claimant only.

## Tests

`src/world/estates/tests/` — `test_models`, `test_settlement_open` (death-writer
wiring), `test_intestate`, `test_settlement` (execution journeys), `test_doors`,
`test_api`. Also `world/items/tests/test_provenance.py`,
`test_hot_goods_consent.py`.

## Integrates With

- **Vitals** — `_mark_dead` opens the window; `is_dead`/`is_retired` validate recipients
- **Ceremonies** — the funeral door (#2289's seam, now live)
- **Items** — holder flips + `INHERITED` ledger rows; provenance reads
- **Currency** — `transfer` (coin), `Contract`/`ContractTerm` (debts + substitution), `Business`
- **Locations/Buildings** — `transfer_ownership`, `end_tenancy`, `Building.owner_persona`, arrears
- **Roster (kinship)** — public-record readers for next of kin; `Kinsperson.is_deceased`
- **Societies** — org recipients, treasuries, `Domain.owner_org` escheat; title
  succession (`SuccessionLaw`/`pass_title`) stays deliberately untouched
- **Consent** — the `receiving-stolen-goods` category (ADR-0113 tree)
