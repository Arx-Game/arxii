# Covenants Slice B — Lifecycle (Formation + Induction) & Engagement UI

**Date:** 2026-05-10
**Status:** Draft (post-brainstorm; awaiting spec review)
**Branch:** TBD (e.g. `covenants-slice-b-lifecycle`)
**Related:**
- `docs/roadmap/covenants.md` — domain roadmap; Slice B owns "Lifecycle + UI" per the slice decomposition
- `docs/architecture/covenants-slice-a.md` — Slice A; this spec composes with it
- `docs/architecture/ritual-ui-pattern.md` — UI precedent for "formation IS the ritual"
- `src/world/magic/models/rituals.py` — existing `Ritual` + `RitualComponentRequirement` shape this spec extends
- `src/world/magic/actions.py` — `PerformRitualAction` dispatch path (single-actor; Slice B introduces a session-based path alongside it)
- `src/world/covenants/services.py` — Slice A services this spec wraps (`create_covenant`, `add_member`, engagement services)
- `src/world/covenants/handlers.py` — `CharacterCovenantRoleHandler` this spec extends

---

## Goal

Land the lifecycle that turns Covenants from "data exists" into "players can actually form and grow them in play." Slice A shipped the entity, membership FK, engagement context, anchor cap formula, and pull gating — but a covenant can only be created today via factories or admin, and engagement is set only by direct service calls. Slice B introduces:

- A multi-participant ritual coordination primitive (`RitualSession`) in `world/magic`, reusable for any ritual that requires consent across N characters.
- Two new `Ritual` factories driving covenant formation and post-founding induction through that primitive.
- A Soul Tether retrofit that converts the existing single-actor ritual to a `BILATERAL` (sineater + sinner) multi-participant flow, validating the primitive against a second use case.
- Manual engage/disengage UI surfaces, plus Durance scene-co-presence auto-engagement.
- Frontend pages for the inbox, draft, response, and detail flows — placeholder UI mirroring the existing `RitualPerformDialog` shape.

Slice B is intentionally lifecycle-only on the entry side: **no exit lifecycle ships in this slice.** Voluntary leave, kicking, dissolution, and dissolution-kind ceremonies are deferred to allow a careful design (see §3.1).

---

## Background

### What Slice A landed

- `Covenant` model (name, type, level, sworn_objective, formed_at, dissolved_at)
- `CharacterCovenantRole` membership row with `covenant` FK + `engaged` boolean
- Service functions: `create_covenant`, `add_member`, `change_role`, `dissolve_covenant`, `assign_covenant_role`, `end_covenant_role`, `set_engaged_membership`, `clear_engaged_membership`, `clear_engaged_for_type`
- `CharacterCovenantRoleHandler` cached handler (`character.covenant_roles`)
- Read-only REST API at `/api/covenants/`
- Modifier pipeline reads `currently_engaged_roles`; Thread anchor cap reads `max_covenant_level_for_role`; pull eligibility checks engagement; weave gate checks `has_ever_held`.

### What's missing

The lifecycle that surfaces all of the above to players. Today:

- Covenants exist only via admin or factories.
- Membership is added only via direct `add_member` service calls.
- Engagement is set only by explicit `set_engaged_membership` calls (typically in `setUpTestData`).
- The Slice A spec explicitly defers permission model, invite/accept ceremony, dissolution kinds, and auto-engagement triggers to Slice B.

### Slice B's place in the multi-slice buildout

| Slice | Scope | Status |
|---|---|---|
| A | Covenant entity + membership FK + engagement context + anchor cap + COVENANT_ROLE pull gating | **Shipped** |
| **B** | **RitualSession primitive + covenant formation + induction + Soul Tether BILATERAL retrofit + manual engage/disengage + Durance scene auto-engage + UI** | **This spec** |
| C | Sworn Objective model + Stories/Missions integration | Future |
| D | Covenant-level XP/progression, group-ability unlocks, sub-role unlocks | Future |
| E | Battle Covenants + Durance × Battle stacking + war-scope combat auto-engage | Future |
| F | Group abilities (techniques/rituals gated by ≥N members present) | Future |
| G | Use-based weave gate & anchor cap for COVENANT_ROLE Threads | Future |
| H | Thread situational gating for non-COVENANT_ROLE kinds | Future |

Note that some Slice B-adjacent work intentionally lives outside Slice B: covenant exit lifecycle (see §3.1), Battle covenant auto-engage (depends on a Battle entity that doesn't yet exist). Soul Tether is **in scope** as a BILATERAL retrofit (§3.12, §4.15) that validates the `RitualSession` primitive against a second use case.

---

## Architecture decisions

These are the design points fixed during the Slice B brainstorm. Several constrain future slices.

### 3.1 Covenants languish; no exit lifecycle in MVP

Voluntary leave, kicking, and dissolution are **not in Slice B and not in MVP.** Inactive members stay in the membership table; covenants are allowed to drift into dormancy as players come and go. Engagement is the natural "I'm not playing this covenant right now" signal — disengaged is not the same as left.

Reasoning: most exit events happen for OOC reasons (real life, lost interest, broken keyboard). Forcing an in-character ritual ceremony to handle OOC absence makes the system feel bad — punishing OOC reality with IC theatrics. Letting covenants languish keeps the door open if/when the player returns.

Implications for Slice B:
- No UI for voluntary leave.
- No UI for kicking members.
- No UI for dissolving a covenant. Slice A's `dissolve_covenant` service exists but stays unsurfaced (staff-only emergency tool).
- Quorum calculations (§3.4) must NOT require unanimity of all active members — many founders may be 6+ months inactive. Quorum is computed on respondents.

This rule applies to all future covenant slices: when designing exit flows later, design them as IC-narrative events (vow-breaking, betrayal, sworn-objective fulfilled), not as OOC-housekeeping ergonomics.

### 3.2 Lifecycle is fully ritual-driven, with each participant choosing their own role

Covenant formation and post-founding induction both happen via ritual ceremonies, not CRUD endpoints. Multiple characters participate in each ritual, and **each participant chooses their own role** (Sword / Shield / Crown for Durance founding; whichever role they want for induction). Player agency over the role they take is an explicit design requirement — the initiator does not assign roles on others' behalf.

This is consistent with Arx II's overarching design framing ("an MMO for dramatic theater-kid roleplayers") and rules out the MMO-style "auto-add everyone in the room" model.

Practically:
- Founding requires ≥2 participants (per Slice A's `MINIMUM_FOUNDERS = 2`).
- Each founder's acceptance of the ritual invitation includes their own role choice.
- Induction adds one new member; the candidate's acceptance includes their role choice. Existing members participate to vouch but don't choose new roles.

### 3.3 Multi-participant coordination via a new `RitualSession` primitive in `world/magic`

The existing `PerformRitualAction` (single-actor: one performer, optional target, fire-and-forget) does not support "wait for N characters to consent." A new primitive is required.

`RitualSession` lives in `world/magic` because it is a magic-system concern, not a covenant concern. It is reusable for any future ritual that requires multi-character consent.

Rejected alternatives:
- A separate `MultiParticipantRitual` model alongside `Ritual` — parallel infrastructure for admin/dispatch/frontend, two systems to maintain.
- A covenant-specific `CovenantFormationSession` in `world/covenants` — locks in not-DRY; future multi-participant rituals get nothing from it.

### 3.4 Threshold rules per `Ritual.participation_rule`

`Ritual` gains a `participation_rule` field (`TextChoices`: `SINGLE_ACTOR`, `FORMATION`, `INDUCTION`, `BILATERAL`). All `Ritual` rows live in factories today (used by integration tests and, eventually, by an authoring UI that surfaces sane defaults). The project does not use Django data migrations to seed game content — factories are the single source. Slice B adds factories for the new ritual kinds and updates the Soul Tether factory to use the new participation_rule (see §3.12 and §4.15).

- **`SINGLE_ACTOR`**: dispatched via `PerformRitualAction` directly, no `RitualSession` involved. The simplest rule, used by rituals where one performer acts (with optional target). Default for the field. Existing single-actor factories (Imbuing, anima ritual, soul_tether_rescue) take the default; their dispatch path is unchanged.
- **`FORMATION`**: all `INVITED` participants must respond `ACCEPTED`, with ≥2 accepts required to fire. Any `DECLINE` immediately kills the session (see lifecycle below). Initiator must explicitly fire when threshold is met.
- **`INDUCTION`**: simple majority of respondents — `accepts > declines AND accepts ≥ 2` (initiator + at least one other). Non-respondents do not block; the initiator can fire when threshold is met. This is deliberately **respondent-based**, not membership-based, because many founders may be inactive (per §3.1) and unanimity-of-all-members is unworkable.
- **`BILATERAL`**: exactly 2 participants, both must accept. Used by Soul Tether (sineater + sinner). Smaller-scope variant of FORMATION with a fixed participant count of 2 — distinct from FORMATION because the participant count is constrained at the model layer, and the per-participant choice is a binary role (one end of the relationship vs the other).

A future "core / guest" tier or per-member admin/invite-privilege flags will likely refine the INDUCTION rule. Out of scope for B.

### 3.5 Engagement is a contextual state with a shared prerequisite

Engagement (the per-row `CharacterCovenantRole.engaged` boolean from Slice A) represents "I am currently fulfilling this role for this covenant." It is not a self-declaration toggle — it requires IC presence with other covenant members.

The same prerequisite check (`can_engage_durance_membership`) is used by:
- The manual engage endpoint (request rejected with typed error if prerequisite fails).
- The auto-engage trigger (silently no-ops if prerequisite fails).
- The serializer's `can_engage` computed read-only field (frontend uses to disable/enable the Engage button with a tooltip).

Disengagement has no prerequisite — players can always step out of role.

For Battle covenants, the Slice B placeholder is "no IC prerequisite." When the Battle entity ships (Slice E or earlier), the Battle branch of the helper becomes `is_in_active_battle(...)`-style.

### 3.6 Manual engagement sticks; auto-engage never overrides manual

The auto-engage trigger only fires when the character has **no engaged membership of that type**. Once engaged (auto or manual), the engagement persists until the player explicitly disengages or manually engages a different covenant of the same type.

Reasoning: prevents flip-flopping engagement when a character moves between scenes containing different covenants' members. Engagement is a deliberate state, not a hover effect.

There is no auto-disengage — leaving a scene does not clear engagement. Players manage their own engagement state from then on.

### 3.7 Persistence is transient: session deleted on terminal state

`RitualSession` rows persist only during PENDING coordination. On `fire`, `cancel`, expiry, or threshold-killing decline, the session and its dependent rows (participants, references) are deleted in the same transaction.

Audit trail lives entirely on the resulting domain rows (`Covenant.formed_at`, `CharacterCovenantRole.joined_at`). There are **no reverse FKs** from `Covenant` or `CharacterCovenantRole` back to `RitualSession`. This is a YAGNI choice: no current or near-future use case requires "show the founding ceremony record after the fact." If future analytics need it, a separate `RitualExecutionLog` model can be layered on without disrupting the primitive.

### 3.8 Discriminator-pattern M2M for typed FK references

Per-session and per-participant **model FK references** (target covenant, chosen role, future kinds) live in a separate `RitualSessionReference` table that follows the project's established discriminator convention (`Thread`, `ResonanceGrant`, `EventInvitation`):

- A `kind` `TextChoices` column.
- N nullable typed FK columns (`ref_covenant`, `ref_covenant_role`, …).
- A `CheckConstraint` enforcing exactly one `ref_*` matches `kind`.
- An optional `participant` FK that distinguishes session-level (`participant=null`) from participant-scoped references.

Scalar inputs (text, ints) live in `session_kwargs` and `participant_kwargs` JSON. The project's "no JSONField for referencing other models" rule is honored: every model FK goes through `RitualSessionReference`.

A `role` semantic-label field on `RitualSessionReference` was considered and **dropped as YAGNI** — for Slice B's two ritual kinds, `kind` + `participant` scope is sufficient to identify each reference's meaning unambiguously. Add `role` later if a future ritual needs same-kind references with different meanings (e.g., a "merge two covenants" ritual with `source_covenant` + `target_covenant` both `kind=COVENANT`).

### 3.9 No raw `.filter()` on related managers; cached handlers only

This is Slice A discipline restated: Slice B code does **not** call `.filter()` on `CharacterSheet.memberships`, `Covenant.memberships`, or any other related manager — that pattern defeats the SharedMemoryModel identity-map cache.

Slice B extends `CharacterCovenantRoleHandler` with new methods (`active_memberships`, `active_memberships_for_type`, `currently_engaged_for_type`) and introduces a new `CovenantMembershipHandler` attached to `Covenant.member_roster`. All membership lookups in Slice B services and helpers route through these handlers.

Reviewer responsibility: grep for `.filter(left_at__isnull=...)` and `covenant.memberships.` access patterns in **new Slice B code**; flag any violations. Note that existing Slice A `dissolve_covenant` already iterates `covenant.memberships.filter(left_at__isnull=True)` inside its mutation transaction — this is intentional (mutators need fresh DB state, not cached handler reads) and must NOT be flagged. The handler-routing rule applies to *read* paths, not to in-transaction mutator iteration.

### 3.10 Validation in serializers, permissions in permission classes, services do atomic operations

Per project rule. Slice B's services (`draft_session`, `accept_session`, `decline_session`, `fire_session`, `cancel_session`, the engagement helpers) do not validate user input. Validation lives in DRF serializers (`RitualSessionDraftSerializer`, `RitualSessionAcceptSerializer`, etc.). Permissions live in permission classes (`IsRitualSessionInitiator`, `IsInvitedParticipant`, `IsOwnMembership`).

Services raise typed exceptions only for state-transition violations discovered atomically (e.g., session no longer `PENDING` after the lock acquire) and for defensive assertions against programmer errors.

### 3.11 Ritual-system overlap with the Flow system

The flow system uses untyped `FlowStepDefinition.parameters: JSONField` for all inputs and has no concept of multi-actor coordination. `RitualSession` is genuinely new infrastructure (not a reinvention) and applies a higher modeling rigor than the flow system currently does.

Spec-level callout: when the flow system's untyped parameters start fighting back, a similar discriminator-references treatment is a candidate refactor. Not blocking, just leaving the path lit.

### 3.12 Soul Tether retrofit through `RitualSession` (BILATERAL)

The existing Soul Tether ritual (factory-only today, dispatched as single-actor performer-targets-target) is retrofitted through the new primitive in this slice. The retrofit:

- Validates the `RitualSession` design against a second, structurally different use case (covenant founding has N participants choosing from M roles; Soul Tether has exactly 2 participants choosing from 2 roles). If the primitive can't accommodate Soul Tether cleanly, that's an early signal to revise it.
- Removes Slice B's only "remember to do this later" debt.
- Reverses the May 2026 Soul Tether UI design's "no consent" decision. That decision was made when there was no infrastructure for asynchronous consent; with `RitualSession` available, requiring the sineater's explicit consent is the natural choice and reflects what the ritual *means* IC.

Soul Tether shape:
- **Two participants exactly:** the **sineater** and the **sinner**. Both are `CharacterSheet` rows. NPCs are GM-controlled characters (with character sheets) — no special NPC handling needed.
- **Each participant chooses which end of the relationship they are.** A new `SoulTetherRole` `TextChoices` (`SINEATER`, `SINNER`) lives in `world/magic/constants` and is referenced via a new `ReferenceKind.SOUL_TETHER_ROLE` (added to the discriminator-M2M alongside `COVENANT` and `COVENANT_ROLE`).
- **`participation_rule = BILATERAL`:** exactly 2 participants, both must accept. Validation enforces participant count = 2 at draft time AND that the two participants choose distinct roles (one sineater, one sinner) at fire time.
- **Initiator is one of the two participants.** They draft the session naming the other character as the second participant.

`soul_tether_rescue` (a separate ritual) stays `SINGLE_ACTOR` — rescue inherently doesn't allow consent (the rescuee may be incapacitated, possessed, etc.), so it remains a performer-targets-target action.

The wrapper service `accept_soul_tether_via_session(session)` unpacks the two participants and their `SOUL_TETHER_ROLE` references, identifies which is sineater and which is sinner, and dispatches to the existing `world.magic.services.soul_tether.accept_soul_tether` service with arguments shaped to match its current signature. The existing service's logic is unchanged; only the call site shape changes.

The existing Soul Tether frontend page is updated to route through `RitualSessionDraftDialog` (initiator picks the second character + their own role) and `RitualSessionResponseDialog` (the second participant accepts and picks the remaining role).

---

## In scope

### 4.1 `Ritual.participation_rule` field

Add a `TextChoices` field to the existing `Ritual` model:

```python
class ParticipationRule(models.TextChoices):
    SINGLE_ACTOR = "SINGLE_ACTOR", "Single Actor"
    FORMATION    = "FORMATION",    "Formation (all must accept, ≥2)"
    INDUCTION    = "INDUCTION",    "Induction (majority of respondents)"

participation_rule = models.CharField(
    max_length=32,
    choices=ParticipationRule.choices,
    default=ParticipationRule.SINGLE_ACTOR,
)
```

Field default = `SINGLE_ACTOR`. The covenant formation/induction factories (§4.7) take `FORMATION` and `INDUCTION` respectively; the Soul Tether factory (§4.15) is updated to take `BILATERAL`. Existing single-actor factories (Imbuing, anima ritual, soul_tether_rescue) take the default — their dispatch path through `PerformRitualAction` is unchanged. Only non-`SINGLE_ACTOR` rituals route through the new `RitualSession` flow.

### 4.2 `RitualSession` model

```python
class RitualSession(SharedMemoryModel):
    ritual         = FK → Ritual (PROTECT)
    initiator      = FK → CharacterSheet (PROTECT)
    proposed_terms = TextField(blank=True)         # blurb shown to invitees
    session_kwargs = JSONField(default=dict)        # SCALAR initiator inputs only
    expires_at     = DateTimeField()
    created_at     = DateTimeField(auto_now_add=True)
```

No `state` field — the session's life is implicit. Any DECLINE that drops accepts below the ritual's threshold causes the session to be deleted in the same transaction. After fire/cancel/expiry, the row is deleted. All existing rows in the table are by definition either `PENDING` (some participants still INVITED) or `READY` (all ACCEPTED, threshold met, awaiting initiator fire) — derivable from participant states.

`session_kwargs` carries only scalar initiator inputs (covenant name string, sworn objective text). Model FKs go through `RitualSessionReference`.

### 4.3 `RitualSessionParticipant` model

```python
class ParticipantState(models.TextChoices):
    INVITED  = "INVITED",  "Invited"
    ACCEPTED = "ACCEPTED", "Accepted"
    DECLINED = "DECLINED", "Declined"

class RitualSessionParticipant(SharedMemoryModel):
    session            = FK → RitualSession (CASCADE, related_name="participants")
    character_sheet    = FK → CharacterSheet (PROTECT)
    state              = CharField(choices=ParticipantState.choices, default=INVITED)
    participant_kwargs = JSONField(default=dict)    # SCALAR per-participant inputs
    responded_at       = DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [UniqueConstraint(fields=["session", "character_sheet"])]
```

Initiator is a participant (auto-created with `state=ACCEPTED` and any session-level participant_kwargs/references they declared at draft time).

### 4.4 `RitualSessionReference` model (discriminator M2M)

```python
class ReferenceKind(models.TextChoices):
    COVENANT      = "COVENANT",      "Covenant"
    COVENANT_ROLE = "COVENANT_ROLE", "Covenant Role"
    # add new kinds as new ritual types need them

class RitualSessionReference(SharedMemoryModel):
    session            = FK → RitualSession (CASCADE, related_name="references")
    participant        = FK → RitualSessionParticipant (CASCADE, null=True,
                                                       blank=True,
                                                       related_name="references")
                         # null = session-level; non-null = participant-scoped
    kind               = CharField(choices=ReferenceKind.choices)
    ref_covenant       = FK → Covenant (PROTECT, null=True, blank=True)
    ref_covenant_role  = FK → CovenantRole (PROTECT, null=True, blank=True)

    class Meta:
        constraints = [
            CheckConstraint(
                check=(
                    (Q(kind="COVENANT")      & Q(ref_covenant__isnull=False) & Q(ref_covenant_role__isnull=True))
                  | (Q(kind="COVENANT_ROLE") & Q(ref_covenant__isnull=True)  & Q(ref_covenant_role__isnull=False))
                ),
                name="ritual_session_reference_exactly_one_ref",
            ),
        ]
```

Add new `ReferenceKind` values + new typed FK columns + extended `CheckConstraint` whenever a future ritual needs a new reference type.

### 4.5 Session lifecycle services

In `src/world/magic/services/sessions.py` (new file):

```python
def draft_session(
    *,
    ritual: Ritual,
    initiator: CharacterSheet,
    proposed_terms: str,
    session_kwargs: dict,
    invitee_sheets: Sequence[CharacterSheet],
    session_references: Sequence[RitualSessionReferenceSpec],
    initiator_participant_kwargs: dict | None = None,
    initiator_references: Sequence[RitualSessionReferenceSpec] | None = None,
    expires_at: datetime | None = None,
) -> RitualSession: ...

def accept_session(
    *,
    participant: RitualSessionParticipant,
    participant_kwargs: dict,
    references: Sequence[RitualSessionReferenceSpec],
) -> None: ...

def decline_session(*, participant: RitualSessionParticipant) -> None: ...

def fire_session(*, session: RitualSession) -> object: ...

def cancel_session(*, session: RitualSession) -> None: ...
```

`RitualSessionReferenceSpec` is a typed dataclass in `world/magic/types.py` carrying `kind` + the populated typed FK target (instance, not pk — per project preference). Services translate specs → DB rows.

All state-changing services wrap in `transaction.atomic()` + `select_for_update()` on the session (or participant for `accept`/`decline`) to serialize concurrent writers. Each `select_for_update().get()` is followed by `refresh_from_db()` to ensure the SharedMemoryModel-cached instance reflects the just-locked row's values. Inline comments in each service explain the specific race the lock prevents.

`fire_session` validates: state-derived threshold met, all `ACCEPTED` participants have all required references (per the ritual's `participant_fields` schema), session-level required references present. On success: dispatches the ritual's `service_function_path`, deletes the session in the same transaction, returns the dispatched service's return value (`Covenant` for formation, `CharacterCovenantRole` for induction). On failure: typed exception, transaction rolls back, session stays alive for the initiator to retry or cancel.

The HTTP `POST /api/rituals/sessions/{id}/fire/` view returns `200 OK` with a small JSON envelope so the frontend can navigate to the result:

```json
{"result_kind": "covenant" | "membership", "result_id": <pk>}
```

The `result_kind` discriminator lets the frontend route appropriately (formation → covenant detail page; induction → covenant detail with the new member highlighted). The view derives `result_kind` from the ritual's `participation_rule` (FORMATION → "covenant"; INDUCTION → "membership"). No nested serialization in this response — the frontend invalidates the relevant react-query caches after fire and re-fetches the full object via existing endpoints.

### 4.6 Covenant ritual service wrappers

In `src/world/covenants/services.py` (alongside Slice A services):

```python
def create_covenant_via_session(*, session: RitualSession) -> Covenant: ...
def induct_member_via_session(*, session: RitualSession) -> CharacterCovenantRole: ...
```

Both are thin wrappers around Slice A's existing `create_covenant` / `add_member`. They unpack `session.session_kwargs` + iterate `session.participants` + read each participant's references, then call the Slice A service. All actual creation logic and invariant enforcement stays in Slice A. If Slice A's service raises a typed `CovenantError`, it propagates up through `fire_session` and the transaction rolls back.

**Implementation note on `Covenant.name` uniqueness.** Slice A did not add a uniqueness constraint on `Covenant.name`. If two formation rituals fire concurrently with the same proposed name, both succeed today. Implementation should decide whether to:
(a) leave it unconstrained (matches current Slice A behavior; duplicate names in the wild are tolerable)
(b) add `unique=True` on `Covenant.name` in the Slice B model migration (catches the conflict at the DB layer; raises `IntegrityError` which `fire_session` translates to a typed `CovenantNameConflictError`)
Recommend (b) for predictability, but the call is left for the implementation plan.

### 4.7 Two new `Ritual` factories

The project never uses Django data migrations to seed game content. All `Ritual` rows are constructed by FactoryBoy factories used by integration tests today and surfaced through an authoring UI eventually. Slice B adds two factories in `src/world/magic/tests/factories.py` (or co-located in `src/world/covenants/tests/factories.py` if they're tied to covenant scenarios):

- **`CovenantFormationRitualFactory`**: `participation_rule=FORMATION`, `execution_kind=SERVICE`, `service_function_path="world.covenants.services.create_covenant_via_session"`, `input_schema` with session-level fields (`name`, `covenant_type`, `sworn_objective`, `invitees`) + `participant_fields` (`chosen_covenant_role`).
- **`CovenantInductionRitualFactory`**: `participation_rule=INDUCTION`, `execution_kind=SERVICE`, `service_function_path="world.covenants.services.induct_member_via_session"`, `input_schema` with session-level fields (`target_covenant`, `candidate`) + `participant_fields` (`chosen_covenant_role`, `applies_to: "candidate_only"`).

Both use `django_get_or_create=("name",)` so the factory is idempotent across `setUpTestData` calls.

Authoring UI for staff to create / edit Ritual rows is a future concern; for now, these factories also serve as the canonical "sane defaults" reference for that future tooling.

### 4.8 `Ritual.input_schema` extension: `participant_fields`

The existing `input_schema` JSON shape gains an optional `participant_fields` array:

```json
{
  "fields": [...],                    // session-level (initiator-set at draft)
  "participant_fields": [...]         // per-participant (set at acceptance)
}
```

Each participant_field declaration may include:
- `name`, `type`, `label`, `required` (existing convention)
- `applies_to`: `"all_participants"` (default) or `"candidate_only"` (induction-style — only the new candidate fills these in)
- `depends_on`: optional reference to a session-level field (e.g., role picker filtered by chosen `covenant_type`)

Slice B-only field types: `covenant_picker`, `covenant_role_picker` (frontend implementations in §4.13).

### 4.9 Engagement endpoints + shared prerequisite helper

New action endpoints on the existing covenant API:

```
POST /api/covenants/character-roles/{id}/engage/      # IsOwnMembership
POST /api/covenants/character-roles/{id}/disengage/   # IsOwnMembership
```

Permission class `IsOwnMembership` checks the membership's `character_sheet` is one the requesting user currently plays via the active RosterTenure chain (mirrors Slice A's read view scoping).

Engage endpoint validation calls the shared helper `can_engage_durance_membership(membership)`. Failure raises new `CovenantEngagementPrerequisiteNotMetError(CovenantError)` with `user_message="No covenant members present to engage with."` Returns 422.

The helper:

```python
def can_engage_durance_membership(membership: CharacterCovenantRole) -> bool:
    if membership.covenant.covenant_type != CovenantType.DURANCE:
        return True  # Battle: no IC prereq for Slice B (TODO when Battles ship)
    char = membership.character_sheet.character
    location = char.location
    if location is None:
        return False
    if get_active_scene(location) is None:
        return False
    self_sheet = membership.character_sheet
    target_covenant = membership.covenant
    for obj in location.contents:
        sheet = getattr(obj, "character_sheet", None)
        if sheet is None or sheet == self_sheet:
            continue
        if sheet.covenant_roles.currently_held_role_in(target_covenant) is not None:
            return True
    return False
```

The exact Character ↔ CharacterSheet accessor on `obj` (`obj.character_sheet`) must match the existing relationship on the typeclass; verify and adjust during implementation.

### 4.10 Scene auto-engage trigger

New service `evaluate_scene_engagement(character_sheet, room)` in `src/world/covenants/services.py`:

```python
def evaluate_scene_engagement(
    *,
    character_sheet: CharacterSheet,
    room: ObjectDB,
) -> None:
    if character_sheet.covenant_roles.currently_engaged_for_type(
        CovenantType.DURANCE
    ) is not None:
        return  # manual sticks; auto never overrides
    candidates: list[tuple[CharacterCovenantRole, int]] = []
    for membership in character_sheet.covenant_roles.active_memberships_for_type(
        CovenantType.DURANCE
    ):
        if not can_engage_durance_membership(membership):
            continue
        co_present = _co_present_member_count(membership, room)
        candidates.append((membership, co_present))
    if not candidates:
        return
    candidates.sort(key=lambda c: (-c[1], c[0].covenant_id))
    set_engaged_membership(membership=candidates[0][0])
```

Subscription points (call `evaluate_scene_engagement` from):
- The character-movement service in `flows/services` whenever a character's `location` settles in a new room (post-arrival).
- `start_scene` service in `world/scenes/services.py` (so existing-room characters are evaluated when a scene fires up at their location).
- `_join_scene_as_participant` (or equivalent) when a player joins an existing scene as a participant.

Each subscription point is a single new function call inside the existing service's transaction. No Django signals (per project rule).

**Implementation discovery step.** The exact callsite names in `world/scenes/services.py` and `flows/services/` are not pinned down by this spec. The implementation plan must include a discovery task that locates the canonical "character arrived in room" and "joined active scene" service-function callsites and wires `evaluate_scene_engagement` calls into them. If a single canonical callsite doesn't exist, the implementation plan must propose where to add one (and whether to refactor existing scattered callsites to converge through it).

### 4.11 Handler additions

`CharacterCovenantRoleHandler` (extend Slice A, in `src/world/covenants/handlers.py`):

```python
@cached_property  # from django.utils.functional
def active_memberships(self) -> list[CharacterCovenantRole]: ...

def active_memberships_for_type(
    self, covenant_type: str,
) -> list[CharacterCovenantRole]: ...

def currently_engaged_for_type(
    self, covenant_type: str,
) -> CharacterCovenantRole | None: ...
```

New handler `CovenantMembershipHandler` (in same file):

```python
class CovenantMembershipHandler:
    def __init__(self, covenant: Covenant): ...

    @cached_property
    def active_memberships(self) -> list[CharacterCovenantRole]: ...

    @cached_property
    def active_character_sheets(self) -> list[CharacterSheet]: ...

    def invalidate(self) -> None: ...
```

**Attachment.** Slice A's `CharacterCovenantRoleHandler` is attached via `@cached_property` on the `Character` typeclass (`src/typeclasses/characters.py:158-163`). `Covenant` is a Django model, not a typeclass, so the equivalent attachment goes on the `Covenant` model itself:

```python
# src/world/covenants/models.py
class Covenant(SharedMemoryModel):
    ...
    @cached_property                                # from django.utils.functional
    def member_roster(self) -> "CovenantMembershipHandler":
        from world.covenants.handlers import CovenantMembershipHandler
        return CovenantMembershipHandler(self)
```

Lazy import inside the property avoids the circular-import that would otherwise surface (handlers import models). The cached_property is per-instance; SharedMemoryModel's identity map ensures the same Covenant instance is reused, so the handler also persists across accesses.

`invalidate()` is called from existing Slice A mutators (`assign_covenant_role`, `end_covenant_role`, `add_member`, `change_role`, `dissolve_covenant`) — extend each to invalidate both `character.covenant_roles` (already done in Slice A) AND the affected `covenant.member_roster`.

### 4.12 Full API surface (additions)

**RitualSession endpoints (new), at `/api/rituals/sessions/`:**

```
GET    /api/rituals/sessions/?as_invitee=me     # inbox; FilterSet
GET    /api/rituals/sessions/?as_initiator=me   # outbox
GET    /api/rituals/sessions/{id}/              # detail
POST   /api/rituals/sessions/                   # draft
POST   /api/rituals/sessions/{id}/accept/       # body: {participant_kwargs, references}
POST   /api/rituals/sessions/{id}/decline/
POST   /api/rituals/sessions/{id}/fire/
DELETE /api/rituals/sessions/{id}/              # cancel (custom action)
```

Permission classes:
- `IsRitualSessionParticipantOrInitiator` for `GET detail`
- `IsInvitedParticipant` for `accept`, `decline` (rejects if not invited; rejects if state is not `INVITED`)
- `IsRitualSessionInitiator` for `fire`, cancel (`DELETE`)
- `IsAuthenticated` + per-action validation for `POST` (draft)

`DELETE` is wired via DRF's standard `destroy` mixin (which calls `cancel_session`); this preserves the standard router URL shape while routing through the typed cancel service. Alternative — a custom action `POST /api/rituals/sessions/{id}/cancel/` — is acceptable but less conventional. Implementation should pick one and stay consistent.

Serializers do all user-input validation. Services raise typed exceptions only for state-transition violations.

**Engagement endpoints (new), at `/api/covenants/character-roles/`:**

```
POST   /api/covenants/character-roles/{id}/engage/
POST   /api/covenants/character-roles/{id}/disengage/
```

Permission class: `IsOwnMembership` (active RosterTenure chain).

**Serializer extension:**

`CharacterCovenantRoleSerializer` (Slice A, read-only) gains:
- `can_engage` — boolean from `can_engage_durance_membership(membership)`
- `engage_blocked_reason` — short string when `can_engage` is False, else null

**Unchanged in Slice B:**
- No `POST /api/covenants/covenants/` (creation is via formation ritual)
- No `DELETE` on covenants or character-roles (no exit lifecycle in MVP)
- Slice A read endpoints unchanged in shape

### 4.13 Frontend

**New pages** (mirroring existing patterns):

- `RitualSessionInboxPage` — lists pending invitations (polling via react-query, ~5s staleTime)
- `RitualSessionDetailPage` — shows participants + states + their submitted choices; initiator-only Fire / Cancel buttons
- `CovenantsListPage` — lists the player's covenant memberships (verify whether a placeholder already exists; extend or create)
- `CovenantDetailPage` — name, sworn objective, member roster, per-row Engage/Disengage button (disabled with tooltip when serializer's `can_engage=false`), "Induct New Member" CTA opening the induction `RitualSessionDraftDialog`

**New components** (under `frontend/src/rituals/components/`):

- `RitualSessionDraftDialog` — renders a ritual's session-level `fields` schema; submits to `POST /api/rituals/sessions/`
- `RitualSessionResponseDialog` — Accept renders `participant_fields` schema as a form (reuses existing `RitualForm`); Decline is one click

**New ritual-form field types** (under `frontend/src/rituals/components/fields/`):

- `CovenantPickerField` — dropdown of covenants the initiator has active memberships in
- `CovenantRolePickerField` — dropdown of `CovenantRole` rows filtered by covenant_type (depends_on resolution)

Registered via `registerFieldComponent(type, Component)` in the existing field registry index.

**Notification surface**: numeric badge on a top-nav "Inbox" link counting pending invitations. Polled. If a project-wide notification system exists, integrate; otherwise placeholder badge is fine.

**Generated API types**: regenerate via `just gen-api-types` after backend serializers land.

### 4.14 Typed exceptions

In `src/world/magic/exceptions.py`:

```
RitualSessionError(Exception)   # base; user_message + SAFE_MESSAGES allowlist
├── SessionNotInPendingError
├── ThresholdNotMetError
├── RequiredReferenceMissingError
├── SessionTargetMissingError
├── NotInvitedError
└── NotInitiatorError
```

In `src/world/covenants/exceptions.py`:

```
CovenantEngagementPrerequisiteNotMetError(CovenantError)
```

All carry `user_message` + `SAFE_MESSAGES` allowlist per project rule. Views use `exc.user_message`, never `str(exc)`.

### 4.15 Soul Tether retrofit

Per §3.12. Concrete deliverables:

**Backend additions:**
- `SoulTetherRole` `TextChoices` in `src/world/magic/constants.py` (`SINEATER`, `SINNER`)
- New `ReferenceKind.SOUL_TETHER_ROLE` value + new typed FK column on `RitualSessionReference`: `ref_soul_tether_role` is NOT a model FK (it's an enum), so this case is the exception to the discriminator-FK pattern. Two options:
  - (a) Store the SoulTetherRole enum value in `participant_kwargs` JSON (it IS a scalar enum, not a model FK — fits the JSON convention)
  - (b) Add a `ref_soul_tether_role` `CharField(choices=SoulTetherRole.choices, null=True)` column on `RitualSessionReference` to keep all participant choices in one table
  - **Recommend (a)** — it's a scalar enum, JSON is the right home per §3.8's split. Implementation plan picks.
- New optional `min_participants` / `max_participants` `PositiveSmallIntegerField` columns on `Ritual`. `BILATERAL` rituals set both to 2. `FORMATION` and `INDUCTION` leave them null. `SINGLE_ACTOR` leaves them null. Validation in the draft service enforces the bounds when set.
- Wrapper service `accept_soul_tether_via_session(session)` in `src/world/magic/services/soul_tether.py` — unpacks the two participants, identifies sineater + sinner from their respective `SoulTetherRole` choices, calls the existing `accept_soul_tether` with the existing argument shape.
- New typed exception `BilateralRoleConflictError(RitualSessionError)` raised at fire if both participants chose the same role.

**Factory update:**
- `SoulTetherRitualFactory` (in `src/world/magic/tests/factories.py`) updated: `participation_rule=BILATERAL`, `min_participants=2`, `max_participants=2`, `service_function_path` switched to `accept_soul_tether_via_session`, `input_schema` updated to declare `participant_fields` for the SoulTetherRole choice. The existing factory's name and any other consumed attributes stay stable so other test suites aren't broken.
- `SoulTetherRescueRitualFactory` is unchanged — stays `SINGLE_ACTOR` per §3.12.

**Frontend update:**
- The existing Soul Tether page (per the May 2026 UI spec) is updated to invoke `RitualSessionDraftDialog` with the BILATERAL Soul Tether ritual instead of the single-actor `RitualPerformDialog`.
- New ritual-form field type: `SoulTetherRolePickerField` — small radio/dropdown for SINEATER vs SINNER. Registered via the existing field registry.
- The existing Soul Tether dialog component is either deprecated/removed or kept as a thin shim that opens the new flow — implementation plan picks based on how widely it's referenced.

**Tests:**
- All existing Soul Tether integration tests are updated to drive the session flow (draft → both accept with role choices → fire → existing soul tether service called with correct args).
- New tests: `BilateralRoleConflictError` raised when both participants pick the same role; `BILATERAL` participant count enforcement at draft.
- `soul_tether_rescue` tests are unchanged.

---

## Out of scope (durably documented)

- **Covenant exit lifecycle** (voluntary leave, kicking, dissolution) — see §3.1. Not in Slice B, not in MVP.
- **Battle covenant auto-engage** — depends on a Battle entity that doesn't yet exist. When Battles ship (Slice E or earlier), the Battle branch of `can_engage_durance_membership` becomes a real prerequisite; the auto-trigger goes in the "character joins Battle's roster" code path.
- **Soul Tether `BILATERAL` retrofit IS in scope** (§3.12, §4.15) — moved from out-of-scope. `soul_tether_rescue` stays `SINGLE_ACTOR` (rescue inherently doesn't allow consent).
- **Other multi-character rituals** beyond Soul Tether are still out of scope. Future rituals (group magical workings, group sworn oaths, etc.) get their own design when authored. The `RitualSession` primitive supports them.
- **Sworn-objective structuring** — stays free-text `TextField` in Slice B; Slice C structures it.
- **Per-member admin / invite-privilege flags ("core / guest" tier)** — future enhancement when activity churn becomes a real problem.
- **Use-based weave gates and use-based anchor cap** — Slice G.
- **Ritual cost / components** for formation + induction — both rituals ship with no `RitualComponentRequirement` rows; cost tuning is content authoring, not Slice B infrastructure.
- **Real-time updates via websockets** for ritual session state — defer pending a broader architectural conversation about extending the existing game-connection websocket to more pages. Slice B uses polling; this is acknowledged tech debt.
- **Per-participant intent persistence at acceptance time as a grief-protection layer** — the current model captures choices via the `accept` endpoint at acceptance time, which is sufficient. If grief becomes a problem, a richer signed-intent model can layer on without disruption.
- **Multi-typed-FK reference rows / `role` field on `RitualSessionReference`** — not needed for Slice B's two ritual kinds. Add when a future ritual has same-kind references with different meanings.
- **Cron cleanup of expired sessions** — query-time filter (`expires_at__gte=now()`) is sufficient; cron later if needed.
- **Mobile-first layouts, animation, ritual-cinematic visuals** — desktop-only placeholder UI for Slice B.

---

## Implementation discipline

All Slice B code complies with the project's standing rules; calling out the ones most relevant to this slice:

- New models inherit `SharedMemoryModel` (`SHARED_MEMORY` linter)
- Field choices via `TextChoices` / `IntegerChoices`, no string literals (`STRING_LITERAL`)
- All `prefetch_related` uses `Prefetch(... to_attr=...)` paired with `cached_property` accessors (`PREFETCH_STRING`)
- All `cached_property` imported from `django.utils.functional` (`CACHED_PROPERTY_IMPORT`)
- All view query params via FilterSet, never `request.query_params` (`USE_FILTERSET`)
- No `getattr(obj, "literal_string")` for known attrs (`GETATTR_LITERAL`)
- No `Meta.ordering` on the new models — list views add `.order_by(...)` explicitly
- All new exceptions typed with `user_message` + `SAFE_MESSAGES` allowlist; no `str(exc)` in API responses
- **No `.filter()` on related managers** — handler-cached lookups only (the rule from §3.9). Reviewer subagent should grep for violations.
- No relative imports — absolute only
- No Django signals — explicit service calls only
- 100-char line limit
- Type annotations on all functions in the typed apps (`world.covenants` and `world.magic` are typed)

`select_for_update` callsites carry inline comments explaining the specific race they prevent. `refresh_from_db()` follows each `select_for_update().get()` to ensure SharedMemoryModel-cached instances reflect the just-locked row.

---

## Testing

### Backend

- `test_ritual_session_models.py` — invariants, `CheckConstraint`, `clean()`
- `test_ritual_session_services.py` — draft/accept/decline/fire/cancel for both ritual kinds; race-condition fire (two concurrent calls); session deletion on terminal states
- `test_ritual_session_views.py` — permissions, scoping, FilterSet, payload validation
- `test_covenant_handler.py` (extend Slice A) — new `CharacterCovenantRoleHandler` methods + cache invalidation
- `test_covenant_member_roster_handler.py` — new `Covenant.member_roster` handler + cache invalidation
- `test_engagement_prerequisite.py` — `can_engage_durance_membership` all branches (Battle short-circuit, no location, no active scene, no co-presence, with co-presence, multiple covenants)
- `test_engagement_views.py` — engage/disengage endpoints + serializer `can_engage` field
- `test_evaluate_scene_engagement.py` — auto-engage trigger correctness (manual sticks, ties broken deterministically, multiple candidates)
- Integration: `test_formation_flow.py` — end-to-end (draft → all accept with role choices → fire → covenant exists with correct memberships)
- Integration: `test_induction_flow.py` — end-to-end (draft → majority accept → fire → membership added)
- Integration: `test_scene_auto_engage.py` — character moves into scene with covenant member → auto-engages; manual engagement sticks across moves; scene end leaves engagement intact

### Factories

- `RitualSessionFactory`, `RitualSessionParticipantFactory`, `RitualSessionReferenceFactory` (with covenant + covenant_role variants) in `src/world/magic/tests/factories.py`
- Extend Slice A's covenant factories as needed

`setUpTestData` per project pattern.

### Frontend

- Component tests for inbox, draft dialog, response dialog (Testing Library)
- Field-type tests for `CovenantPickerField`, `CovenantRolePickerField`
- Integration: the formation flow end-to-end through the frontend stack

### Regression before push

Per CLAUDE.md:
- `arx test world.magic world.covenants flows world.scenes world.combat` (affected suites)
- `echo "yes" | uv run arx test` (full suite, no `--keepdb`) once before pushing — catches fresh-DB issues from new `create_object` callsites or initial-setup dependencies

---

## Migrations

Per project rule "avoid multiple migrations during development for a new feature" AND the project rule "no data migrations for game content":

- **One model migration** in `src/world/magic/migrations/` adding `Ritual.participation_rule`, optional `Ritual.min_participants` / `Ritual.max_participants` (if §3.12 BILATERAL needs them — see that section), `RitualSession`, `RitualSessionParticipant`, `RitualSessionReference` (with the discriminator `CheckConstraint`s).
- Optional **one model migration** in `src/world/covenants/migrations/` adding `Covenant.name` `unique=True` if the implementation plan picks option (b) from §4.6.
- **No data migrations.** All `Ritual` rows are created by FactoryBoy factories (§4.7, §4.15). Game content seeding is via factories + future authoring UI — never via Django migrations.

Run `arx manage makemigrations world.magic world.covenants` once at the end of feature work, not after each model tweak.

---

## Notes

- The Slice A spec is `docs/architecture/covenants-slice-a.md`; the Slice A implementation plan is `docs/superpowers/plans/2026-05-10-covenants-slice-a-implementation.md`.
- The roadmap update accompanying this spec must mark Slice B as in-progress and note the deliberate omission of exit lifecycle (covenants languish — durable design intent for all future slices).
- The "Arxitecture audit" skill / checklist suggested during brainstorm — a checklist agent that runs over specs/plans for the project's standing architectural rules — is tracked as a follow-up after Slice B ships. Out of scope for this spec.
