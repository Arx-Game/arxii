# Story-Asset Custody & Cross-GM Clearance

A GM-authorable protection that guards a story's load-bearing assets — NPCs, items,
factions, locations, or custom subjects — from being appeared-with, harmed, captured, or
removed by actors at *other* tables, while giving GMs a real permission path to borrow
each other's assets for crossovers. Kills the "nemesis unceremoniously bumped off as a
miniboss at another table" anticlimax.

**Axis note (ADR-0098):** this is GM/story-declared *narrative-structure* protection —
distinct from `world.boundaries` (`PlayerBoundary`/`TreasuredSubject`), which is
player-declared OOC *emotional safety*. Neither replaces the other; see
[boundaries.md](boundaries.md) for the sibling system and ADR-0098 for why they stay
separate despite sharing the same typed-subject-FK shape and `_subject_identity`
matching helper.

**Source:** `src/world/stories/` (models, services, DRF surfaces, telnet — one app, no
cross-app split like boundaries needs). **API prefix:** `/api/protected-subjects/`,
`/api/custody-clearances/`. **Telnet:** `story protect`, `story clearance` (see
`src/commands/CLAUDE.md`'s `story.py` entry for the full grammar). **Frontend:**
`ProtectedSubjectsPanel` (StoryAuthorPage tab) + `ClearanceInbox` (GMQueuePage section),
`frontend/src/stories/components/`. **[BUILT & WIRED]** — every surface below is verified
against the committed code.

---

## Models (`src/world/stories/models.py`)

### `StoryProtectedSubject`

Replaces the old NPC-only `StoryNPCDependency`. Generalizes to the full
`StakeSubjectKind` vocabulary, reusing `Stake`'s typed-subject-FK shape field-for-field.

| Field | Purpose |
|---|---|
| `story` | FK, `CASCADE` — the protecting story |
| `subject_kind` | `StakeSubjectKind` choice |
| `subject_sheet` | `CharacterSheet` FK, `SET_NULL` — NPC_FATE / PERSONAL_JEOPARDY |
| `subject_item` | `ItemInstance` FK, `SET_NULL` — ITEM |
| `subject_society` | `Society` FK, `SET_NULL` — FACTION (society-level) |
| `subject_organization` | `Organization` FK, `SET_NULL` — FACTION (organization-level) |
| `subject_label` | Freeform `CharField` — CUSTOM / CAMPAIGN_TRACK, or a LOCATION fallback |
| `beat` | Optional `Beat` FK, `SET_NULL` — beat-scoped window (protection applies only while the beat is UNSATISFIED); `None` = story-level (whole arc, gated on `story.status == ACTIVE`) |
| `is_active` | Soft on/off switch |
| `notes` | GM-only free text — **never serialized to outsiders** |
| `created_at` | Timestamp; also the tiebreak field when several stories protect the same identity (oldest wins — see [Custody verdict](#custody-verdict-check_subject_custody)) |

Exactly one of `subject_sheet`/`subject_item`/`subject_society`/`subject_organization`/
`subject_label` must be set (model `clean()` + `StoryProtectedSubjectSerializer.validate`
both enforce it — DRF never calls `clean()` on save).

### `CustodyClearance`

| Field | Purpose |
|---|---|
| `protected_subject` | FK, `CASCADE` — the protection this clearance is against |
| `requested_by` | `GMProfile` FK — the requesting GM |
| `requesting_story` / `requesting_beat` | Optional FKs — the requester's own story/beat this clearance is needed for |
| `scope` | `CustodyScope` (`appear` < `harm` < `remove`) |
| `status` | `CustodyClearanceStatus` (`pending`/`granted`/`denied`/`escalated`), default `pending` |
| `granted_by` | `GMProfile` FK — the custodian GM who directly decided (GRANTED/DENIED); null while PENDING/ESCALATED and null for a staff-resolved escalation |
| `staff_resolver` | Staff account FK — set only when a staff tiebreak resolved an ESCALATED row |
| `message` / `response_note` | Requester's ask / custodian's or staff's reply |
| `revoked_at` | Soft-revoke timestamp on a GRANTED row — never hard-deleted |
| `created_at` / `resolved_at` | Timestamps (`resolved_at` set when status leaves PENDING/ESCALATED) |

A partial-unique constraint prevents a duplicate live (PENDING/ESCALATED) request from
the same requester against the same protection at the same scope.

---

## Custody verdict (`check_subject_custody`, `world.stories.services.custody`)

**THE single seam every enforcement point calls** — never a bespoke check per call
site, so the participation/staff/clearance rule can never drift:

```python
check_subject_custody(
    subject_identity: SubjectIdentity,
    actor_account: AccountDB | None,
    scope: str,               # CustodyScope
    acting_story: Story | None = None,
) -> CustodyVerdict
```

Allowed when: no active `StoryProtectedSubject` matches the identity; OR `actor_account`
is staff (no exceptions — staff is unrestricted everywhere in this design); OR, for
*every* matching protection, the actor either acts from within the very story that
declared it (`acting_story == protection.story`, never treated as "a different story"),
participates in the protecting story (`StoryParticipation`), or holds an active,
sufficient-scope `CustodyClearance`.

Subject identity is matched via `_subject_identity` (`world.stories.services.boundaries`
— the same comparison `Stake`/`TreasuredSubject` boundary screening uses; `Stake` and
`StoryProtectedSubject` share the identical typed-FK shape). When several stories
independently protect the same identity, the verdict reports the **oldest-declared**
blocking protection (`created_at` ascending) as the custodian to route a request to —
not whichever story most recently added an overlapping protection.

### `CustodyVerdict` (`world.stories.types`)

`allowed`, `requires_scope` (the scope the actor lacks), `custodian_gm_username` (for
the disclosure message — the *only* identifying detail ever surfaced),
`protecting_subject_id` (internal/audit only, **never** player-serialized). A blocked
verdict discloses exactly: *"under another story's custody — request clearance from GM
`<name>`"* — never the protecting story, beat, or reason (mirrors `world.boundaries`'
privacy posture, ADR-0033/ADR-0086).

### Enforcement points

| Point | Location | Scope checked |
|---|---|---|
| Death guard (NPC flee at 1 HP) | `is_death_prevented_by_story` (`world.stories.services.custody`, thin re-export shim at `npc_protection.py`) | character-based, not account-based — `StoryParticipation.character` may be an NPC ally with no `AccountDB` |
| Stake authoring | `StakeSerializer._check_custody` (`world.stories.serializers`) | APPEAR (the weakest guarantee — merely wagering the subject) |
| Stake resolution writer fire-time recheck | `_custody_allows_fire_time_write` (`world.stories.services.stake_resolution`) | HARM/REMOVE per the specific writer about to fire; acting account is the completing beat's own story's Lead GM (staff bypass applies identically at fire time) |
| Opponent spawning | `_enforce_opponent_custody_gate` (`world.combat.services`, `add_opponent`) | APPEAR; gated only for an *existing* `CharacterSheet` resolution (`existing_objectdb`/`persona`), never a freshly-created ephemeral `CombatNPC`; `acting_account=None` (system-initiated spawns — duels, cast-seed, magic-summon, companion-materialize) skips the gate entirely rather than calling with a null actor (which would mean "no clearance possible") |

`NPCUnderCustodyError` (`world.combat.scaling`) is the typed exception the opponent-spawn
gate raises; stake authoring raises a `serializers.ValidationError` with the same
disclosure-safe message.

---

## Custody clearance lifecycle (`world.stories.services.custody_clearance`)

| Service | Effect |
|---|---|
| `request_clearance` | Creates a PENDING `CustodyClearance`; notifies the protection's custodian |
| `grant_clearance` | Custodian GM only, PENDING → GRANTED |
| `deny_clearance` | Custodian GM only, PENDING → DENIED |
| `escalate_clearance` | Requester only; DENIED, or PENDING older than `CUSTODY_ESCALATION_STALE_DAYS` (7, `world.stories.constants`) → ESCALATED |
| `resolve_escalation` | Staff only; ESCALATED → GRANTED or DENIED, records `staff_resolver` |
| `revoke_clearance` | Custodian GM **or staff** (the one action where staff stands in for the custodian directly — routine cleanup, not a contested decision); soft `revoked_at`, never reversible, never in-flight scenes |
| `matching_active_protected_subjects` | Identity-based lookup (ADR-0099) — every active protection sharing a `subject_kind` + typed-ref/label identity, across every story independently protecting it |
| `active_clearance_exists` | Read helper `check_subject_custody` calls via `_active_clearance_allows` |
| `clearance_is_stale` | Public — shared by the escalate service and its input-serializer pre-validation |

**Binding authority split (Task 3 review, held through the whole feature):** the
protecting story's Lead GM decides grant/deny directly, with **no staff bypass** —
staff act only through escalate→resolve, never by posing as the custodian. Revoke is
the sole exception: custodian **or** staff, both directly.

---

## API (DRF)

### `StoryProtectedSubjectViewSet` — `/api/protected-subjects/`

Full CRUD. `IsProtectedSubjectStoryOwnerOrStaff` + a matching `get_queryset` scope
(owner/lead-GM of the story, staff sees all) — **404-not-filtered**, mirroring
`world.boundaries`'s privacy posture: a non-owner's GET/PATCH/DELETE against another
story's row 404s rather than 403ing or leaking the GM-only `notes` field.

`DELETE` is overridden to **soft-deactivate** (`is_active=False`), never a hard delete —
a `StoryProtectedSubject` is story-significant data whose `CustodyClearance` decision
trail CASCADEs from it; a hard delete would destroy the record of every past
grant/deny/escalate/resolve/revoke. `is_active` stays directly writable via
`PATCH`/`PUT` too, so a client may equally reactivate a protection. Filters:
`story`, `subject_kind`, `is_active`.

### `CustodyClearanceViewSet` — `/api/custody-clearances/`

List/retrieve/create only — every state transition is a dedicated `@action`
(grant/deny/escalate/resolve/revoke), each 1:1 with the service table above and gated
by its own permission class (never a shared permission across actions):

| Action | Method | Permission |
|---|---|---|
| `create` (`request_clearance`) | `POST /api/custody-clearances/` | `IsAuthenticated` + `IsGMProfile` |
| `grant` | `POST .../{id}/grant/` | `IsGMProfile` + `IsClearanceCustodianGM` (exact custodian match, no staff bypass) |
| `deny` | `POST .../{id}/deny/` | same as `grant` |
| `escalate` | `POST .../{id}/escalate/` | `IsGMProfile` + `IsClearanceRequesterGM` |
| `resolve` | `POST .../{id}/resolve/` (`{grant: bool, response_note}`) | `IsStaffForCustodyResolution` |
| `revoke` | `POST .../{id}/revoke/` | `IsClearanceCustodianOrStaff` |

`get_queryset`: requester's own requests (`requested_by=gm_profile`) + requests
targeting stories the caller owns/leads, unioned; staff sees all (this is also the
staff escalation-queue read, paired with the `status=escalated` filter). Filters:
`protected_subject`, `scope`, `status`.

**Create accepts two mutually exclusive paths** (ADR-0099 — closes a pk-discoverability
gap the Task 6 review found):

- **pk path** — `protected_subject` directly (unscoped-by-story queryset — a clearance
  request is inherently cross-story).
- **identity path** — `subject_kind` + exactly one of
  `subject_sheet`/`subject_item`/`subject_society`/`subject_organization`/
  `subject_label`, mirroring `StoryProtectedSubjectSerializer`'s exactly-one-subject
  rule. Resolves to *every* active protection sharing that identity (a subject can be
  independently protected by more than one story) and fans out one `CustodyClearance`
  per match in a single atomic call, skipping (not re-raising on) any row where the
  requester already has a live PENDING/ESCALATED request. **The only self-serviceable
  door** for a requester who was only ever told the custodian's username, never the
  internal `protected_subject` pk (`CustodyVerdict` never serializes it).

Response is always a bare array (`CustodyClearance[]`, never paginated) since a single
identity-path submission can create/report several rows.

---

## Telnet (`src/commands/story.py`)

`story protect`/`story clearance` — thin ORM + service calls over
`world.stories.services.custody_clearance` (no dedicated `Action`; authorization is
replicated inline to match the API's permission classes exactly). Full grammar and
disambiguation rules (`org=`/`society=` aliases for `faction=` when a name matches both
an Organization and a Society) documented in `src/commands/CLAUDE.md`'s `story.py`
entry — kept in tandem there rather than duplicated here.

---

## Frontend (`frontend/src/stories/`)

- **`ProtectedSubjectsPanel`** — new tab on `StoryAuthorPage` (owner/lead-GM/staff-only,
  inherits the page's existing gating). List (active + deactivated badge) + add dialog
  (`ProtectedSubjectFormDialog`, kind + typed-ref picker via the shared
  `SubjectRefFields` component) + deactivate/reactivate.
- **`ClearanceInbox`** — new section on `GMQueuePage`, mounted as a sibling of the
  existing GM-queue content (not nested inside its 403 gate — staff resolving
  escalations may have no `GMProfile`). Incoming (client-side bucketed by
  "`protected_subject` id appears in my own `/api/protected-subjects/` list") vs.
  Outgoing (everything else); staff see a dedicated Escalation Queue instead, since the
  Incoming/Outgoing split would otherwise misleadingly bucket every clearance in the
  system as "incoming" for a staff account. `RequestClearanceDialog` (identity path)
  reachable from the inbox header.

---

## Tests

- `src/world/stories/tests/test_protected_subjects.py` — model + `StoryProtectedSubject`
  API CRUD (soft-deactivate, ownership scoping)
- `src/world/stories/tests/test_custody_service.py` — `check_subject_custody` matrix
  (protected vs. unprotected × participant vs. outsider × clearance scope ladder ×
  staff bypass), oldest-custodian tiebreak
- `src/world/stories/tests/test_custody_clearance.py` — lifecycle services incl.
  escalation staleness + revocation
- `src/world/stories/tests/test_custody_api.py` — `CustodyClearanceViewSet` permission
  split (custodian-only grant/deny, no staff bypass; requester-only escalate;
  staff-only resolve; custodian-or-staff revoke), identity-path fan-out + duplicate skip
- `src/commands/tests/test_story_custody_command.py` — telnet `story protect`/
  `story clearance` grammar, disambiguation, disclosure
- `frontend/src/stories/__tests__/*` — `ProtectedSubjectsPanel`, `ClearanceInbox`
  (incoming/outgoing split, staff-only escalation queue), the clearance action dialogs

## Integrates With

- **Stakes** — `StakeSerializer`/`StakeResolution` writer custody gates; see
  [stakes.md's Custody seam](stakes.md#custody-seam-worldstoriesservicescustody-2001)
- **Boundaries** — sibling player-declared system, shares `_subject_identity`; see
  [boundaries.md](boundaries.md) and ADR-0098
- **Combat** — `add_opponent`'s APPEAR gate (`world.combat.services`,
  `world.combat.scaling.NPCUnderCustodyError`)
- **GM** — `GMProfile` custodian/requester identity; `GMTable.gm` is the exact
  custodian match `IsClearanceCustodianGM` requires (not `Story.owners` — an owner who
  isn't the table's Lead GM can view a clearance via the queryset but cannot grant/deny it)

## Source

`src/world/stories/`
- `models.py` — `StoryProtectedSubject`, `CustodyClearance`
- `constants.py` — `CustodyScope`, `CustodyClearanceStatus`, `CUSTODY_ESCALATION_STALE_DAYS`
- `types.py` — `CustodyVerdict`
- `services/custody.py` — `check_subject_custody`, `is_death_prevented_by_story`,
  `subject_identity_for_sheet`, matching-protection helpers
- `services/custody_clearance.py` — the full lifecycle service table above
- `exceptions.py` — `CustodyClearanceError`, `CustodyClearanceStateError`,
  `CustodyClearanceAuthorityError`
- `serializers.py` — `StoryProtectedSubjectSerializer`, `CustodyClearanceSerializer`,
  `CustodyClearanceRequestSerializer` (pk/identity dual path), per-action input
  serializers (decision/escalate/resolve/revoke)
- `views.py` — `StoryProtectedSubjectViewSet`, `CustodyClearanceViewSet`
- `permissions.py` — `IsProtectedSubjectStoryOwnerOrStaff`, `IsClearanceCustodianGM`,
  `IsClearanceRequesterGM`, `IsStaffForCustodyResolution`, `IsClearanceCustodianOrStaff`,
  `user_owns_or_leads_story`

Cross-app: `world/combat/services.py` (`add_opponent` gate),
`world/combat/scaling.py` (`NPCUnderCustodyError`), `src/commands/story.py` (telnet),
`frontend/src/stories/components/{ProtectedSubjectsPanel,ClearanceInbox,
SubjectRefFields,ProtectedSubjectFormDialog,RequestClearanceDialog,
GrantClearanceDialog,DenyClearanceDialog,EscalateClearanceButton,
RevokeClearanceButton,ResolveClearanceDialog,ClearanceStatusBadge}.tsx`.
