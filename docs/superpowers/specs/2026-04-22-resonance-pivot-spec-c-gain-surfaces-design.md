# Resonance Pivot — Spec C: Resonance Gain Surfaces

**Status:** Design
**Date:** 2026-04-22
**Depends on:** Resonance Pivot Spec A (DONE), Scope 6 Soulfray Recovery & Decay
(DONE — for scheduler pattern)
**Blocks:** None — can be developed standalone.
**Related:** Spec A §3.1 (earn interface), §8.2 (Spec C handoff), Scope 6 daily
tick infrastructure.

---

## 1. Context & Design Intent

### 1.1 What Spec A left us

Spec A built the full Thread currency economy: `CharacterResonance.balance`
(spendable) + `lifetime_earned` (monotonic audit), the `grant_resonance`
service function, and the Thread / Imbuing / Pull machinery that currency
flows into. But Spec A explicitly deferred the *gain surfaces* — the sites
that actually call `grant_resonance` — to this spec. Today there are zero
such callers in the codebase. The whole Thread economy is mechanically
inert: no character can earn spendable resonance from gameplay, so Imbuing
and pulls are unreachable by normal play.

`grant_resonance` already accepts `source: str` and `source_ref: int | None`
kwargs that it currently ignores. Spec A flagged them as "reserved for
Phase 12 audit hook" — that hook is this spec.

### 1.2 What this spec builds

**Four gain surfaces, all routing through `grant_resonance`:**

1. **Scene-entry endorsement** — immediate, flat-per-grant, once per
   `(endorser, endorsee, scene)` pair. Peers already present in the scene
   endorse a character's entry pose.
2. **Pose endorsement** — deferred, weekly "divide-by-use" settlement.
   Peers tag in-scene interactions throughout the week; at weekly tick
   each endorser's fixed pot divides across their endorsements
   (`ceil(pot / N)`).
3. **Room residence trickle** — daily passive, one grant per claimed
   resonance that matches the character's current residence's aura tags.
4. **Outfit trickle** — infrastructure only (empty loop) until the Items
   system ships.

**Mechanical auto-gains are cut from scope.** Earlier brainstorming
considered awarding resonance on technique use, ritual completion, or
relationship-track advances. All removed — the design intent is that
resonance gain is the mechanical reward for *RP that portrays and is
perceived as the character you've claimed to be*, not the reward for
pressing magic buttons.

### 1.3 Design philosophy: aura farming, made literal

> *"Making an impressive entrance should actually grant magical power.
> Wearing a costume that reinforces your identity should passively generate
> resonance. The evil sorceress who resides in a spider-lair and wears
> webs gains more resonance than Bob the Bland who blends in with the
> normies. The world's lore literally requires characters to walk the
> walk of their chosen role."*

Resonance is the reinforcement mechanic that justifies doubling down on
narrative tropes. The magic system rewards commitment to identity. Players
who refuse to commit to a vibe get no mechanical benefit from the magic
system — that's the design intent, not a balancing problem.

Peer endorsement of roleplay is the **main** source. Room residence is a
significant passive bump to reward *decorating thematically*. Outfit is a
deliberate forward hook for the Items system. All other surfaces are out
of scope.

### 1.4 Pre-alpha balance posture

We have no players. All tuning values in this spec are placeholders,
staff-editable via admin, intended to be adjusted during playtest. The
design does *not* lock in any specific magnitudes; it locks in the
*shape* of the economy and the *mechanisms* by which values are applied,
so that tuning is a config change, not a code change.

Target active-vs-passive ratio: an active RPer in 3+ scenes/week with
peer engagement and a themed lair should out-earn a fashion-maxed
passive-only hermit by roughly 2–3×. Values tuned to hit that target
during playtest.

---

## 2. Models

All new models live in `world/magic` unless otherwise noted. All use
`SharedMemoryModel`. All concrete models use the existing patterns for
timestamps (`auto_now_add`) and audit FKs.

### 2.1 `ResonanceGainConfig` (singleton tuning surface)

Staff-editable singleton. All gain magnitudes live here. Exposed via
Django admin; no code changes required to tune.

```python
class ResonanceGainConfig(SharedMemoryModel):
    """Singleton tuning surface for Resonance gain. One row per environment."""

    weekly_pot_per_character = PositiveIntegerField(default=20)
    scene_entry_grant = PositiveIntegerField(default=4)
    residence_daily_trickle_per_resonance = PositiveIntegerField(default=1)
    outfit_daily_trickle_per_item_resonance = PositiveIntegerField(default=1)
    same_pair_daily_cap = PositiveIntegerField(default=0)  # 0 = off
    settlement_day_of_week = IntegerField(default=0)  # Monday = 0 (ISO)

    updated_at = DateTimeField(auto_now=True)
    updated_by = ForeignKey(AccountDB, null=True, on_delete=SET_NULL)
```

**Singleton enforcement:** singleton-by-convention, enforced at the service
layer via `get_resonance_gain_config()` (get-or-create on a reserved pk=1).
No DB-level constraint — matches the lightweight singleton pattern used
elsewhere in the codebase. `get_resonance_gain_config()` lazily creates
the row on first read. This is the only resonance-gain config model in
the system.

### 2.2 `PoseEndorsement` (weekly deferred)

```python
class PoseEndorsement(SharedMemoryModel):
    endorser_sheet = ForeignKey(CharacterSheet, on_delete=CASCADE,
                                related_name="pose_endorsements_given")
    endorsee_sheet = ForeignKey(CharacterSheet, on_delete=CASCADE,
                                related_name="pose_endorsements_received")
    interaction = ForeignKey(Interaction, on_delete=CASCADE,
                             related_name="endorsements")
    resonance = ForeignKey(Resonance, on_delete=PROTECT)
    persona_snapshot = ForeignKey(Persona, on_delete=SET_NULL, null=True,
                                  help_text="Endorsee's persona at endorsement time — "
                                            "captures masquerade for audit.")
    created_at = DateTimeField(auto_now_add=True, db_index=True)
    settled_at = DateTimeField(null=True, blank=True, db_index=True)
    granted_amount = PositiveIntegerField(null=True, blank=True,
                                           help_text="Set at weekly settlement.")

    class Meta:
        constraints = [
            UniqueConstraint(fields=["endorser_sheet", "interaction"],
                             name="unique_pose_endorsement_per_endorser_per_interaction"),
        ]
        indexes = [
            Index(fields=["endorser_sheet", "settled_at"],
                  name="pose_endorsement_unsettled_idx"),
        ]
```

Validation at creation (in `create_pose_endorsement` service):
- `endorser_sheet != endorsee_sheet` derived from `interaction.persona.character_sheet`.
- `account_for_sheet(endorser_sheet) != account_for_sheet(endorsee_sheet)` — alt guard.
- `interaction.mode != WHISPER` — whispers don't count (private, not witnessed).
- `interaction.visibility != VERY_PRIVATE` — private visibility also excluded.
- Endorser was a scene participant of `interaction.scene` (historical
  `SceneParticipation` row) OR is in `interaction.cached_receivers` for
  organic grid RP.
- `resonance` exists in `endorsee_sheet.character_resonances` (row exists,
  balance can be 0 — claim semantics per Spec A §2.2).

### 2.3 `SceneEntryEndorsement` (immediate, flat)

```python
class SceneEntryEndorsement(SharedMemoryModel):
    endorser_sheet = ForeignKey(CharacterSheet, on_delete=CASCADE,
                                related_name="scene_entry_endorsements_given")
    endorsee_sheet = ForeignKey(CharacterSheet, on_delete=CASCADE,
                                related_name="scene_entry_endorsements_received")
    scene = ForeignKey(Scene, on_delete=CASCADE,
                       related_name="entry_endorsements")
    entry_interaction = ForeignKey(Interaction, on_delete=SET_NULL,
                                    null=True, blank=True,
                                    help_text="The ENTRY pose being endorsed; nullable "
                                              "for resilience to interaction cleanup.")
    resonance = ForeignKey(Resonance, on_delete=PROTECT)
    persona_snapshot = ForeignKey(Persona, on_delete=SET_NULL, null=True)
    granted_amount = PositiveIntegerField(help_text="Captured from config at creation.")
    created_at = DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            UniqueConstraint(fields=["endorser_sheet", "endorsee_sheet", "scene"],
                             name="unique_scene_entry_endorsement_per_pair_per_scene"),
        ]
```

Validation at creation (in `create_scene_entry_endorsement` service):
- Endorser has a historical `SceneParticipation` row on the scene (no
  `joined_at` comparison — "hearing about a banger entrance secondhand"
  is legitimate, and we don't want to incentivize arriving late).
- `endorsee_sheet` has an `Interaction` with `pose_kind=ENTRY`,
  `scene=scene`, persona FK resolving to `endorsee_sheet`.
- Alt guard (account level).
- Resonance is in endorsee's claimed list.
- Pair+scene unique.

On success, the row is created AND `grant_resonance` fires synchronously
in the same transaction.

### 2.4 `ResonanceGrant` (universal audit ledger)

Every `grant_resonance` call writes one row here. This is the source of
truth for "how did this character earn this resonance" — the audit feed
that populates the player-facing ledger and any future leaderboard.

```python
class GainSource(TextChoices):
    POSE_ENDORSEMENT = "POSE_ENDORSEMENT", "Pose endorsement"
    SCENE_ENTRY = "SCENE_ENTRY", "Scene entry endorsement"
    ROOM_RESIDENCE = "ROOM_RESIDENCE", "Room residence trickle"
    OUTFIT_ITEM = "OUTFIT_ITEM", "Outfit item trickle"
    STAFF_GRANT = "STAFF_GRANT", "Staff grant"


class ResonanceGrant(SharedMemoryModel):
    character_sheet = ForeignKey(CharacterSheet, on_delete=CASCADE,
                                  related_name="resonance_grants")
    resonance = ForeignKey(Resonance, on_delete=PROTECT)
    amount = PositiveIntegerField()
    source = CharField(max_length=24, choices=GainSource.choices)
    source_ref_id = BigIntegerField(null=True, blank=True,
                                     help_text="PK of the row in the source-specific "
                                               "table (PoseEndorsement, SceneEntryEndorsement, "
                                               "etc.). Not a typed FK — the grant_resonance "
                                               "service already accepts this as a raw int "
                                               "per Spec A §3.1.")
    granted_at = DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        indexes = [
            Index(fields=["character_sheet", "granted_at"],
                  name="resonance_grant_sheet_time_idx"),
            Index(fields=["character_sheet", "source", "granted_at"],
                  name="resonance_grant_sheet_source_idx"),
        ]
```

**Why not typed FKs?** `grant_resonance` already accepts `source_ref: int`
per Spec A's locked interface. Typed FKs would require either changing
the service signature (out of scope — Spec A shipped) or building a
router inside the ledger (complexity). Raw `source_ref_id` matches the
service contract directly. Looking up the originating row requires
source-type-to-model mapping, which is a reasonable ledger burden; the
audit model can be extended with typed FKs later if query ergonomics
require it.

**Invariant (modulo reversals — see §8.4 / §11.4):**

At launch, with no retraction model yet resolved, the invariant is
`sum(ResonanceGrant.amount WHERE character_sheet=X AND resonance=Y) ==
CharacterResonance.lifetime_earned WHERE character_sheet=X AND resonance=Y`.
`grant_resonance` writes both transactionally.

Once retraction lands (§11.4 chooses between option (a) separate
`ResonanceGrantReversal` model vs. option (b) signed `IntegerField`),
the invariant restates to either `sum(grants) - sum(reversals) ==
lifetime_earned` (option a) or `sum(amount)` with signed ints (option b).
Implementers: do NOT codify the current simple-sum invariant into a test
that will break when reversals are added. Reference this section's
variable form.

No drift-detection infrastructure — a staff reconciliation query handles
the rare case of drift.

### 2.5 `RoomAuraProfile` (room's magical character)

Represents the room's own magical nature — resonance tags, future ambient
effects, future place-of-power amplification, future decoration-as-
magical-furniture. **Independent of residence.** Holy sites, abyssal
grottos, battle venues, and personal lairs all host a `RoomAuraProfile`
if they have magical character. Non-magical rooms simply have no aura
profile (the OneToOne reverse lookup returns None).

```python
class RoomAuraProfile(SharedMemoryModel):
    room_profile = OneToOneField(RoomProfile, primary_key=True,
                                  on_delete=CASCADE,
                                  related_name="room_aura_profile")
    # Future: place_of_power flag, ambient_effect fields,
    # decoration summary, combat bonus data.
```

### 2.6 `RoomResonance` (aura-profile ↔ resonance M2M through)

```python
class RoomResonance(SharedMemoryModel):
    room_aura_profile = ForeignKey(RoomAuraProfile, on_delete=CASCADE,
                                    related_name="room_resonances")
    resonance = ForeignKey(Resonance, on_delete=PROTECT)
    set_by = ForeignKey(AccountDB, on_delete=SET_NULL, null=True,
                        help_text="Staff/player who tagged this resonance.")
    set_at = DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            UniqueConstraint(fields=["room_aura_profile", "resonance"],
                             name="unique_room_resonance_per_profile"),
        ]
```

### 2.7 Changes to existing models

**`CharacterSheet.current_residence`** — new FK:

```python
current_residence = ForeignKey(
    "evennia_extensions.RoomProfile",
    null=True, blank=True,
    on_delete=PROTECT,
    related_name="residents",
    help_text="The RoomProfile the character has declared as their residence. "
              "Residence is a neutral narrative declaration; mechanical trickle "
              "only fires if the residence also has a RoomAuraProfile with "
              "resonance tags matching the character's claimed resonances.",
)
```

**Why on CharacterSheet directly and not a dedicated `CharacterResidence`
extension model?** `current_residence` is a single nullable FK — no
per-row data hangs off it today (set_at / set_by audit lives on a future
change-log if needed, not on the residence itself). A OneToOne extension
model would be one-row-per-sheet with a single FK column, effectively a
table with no payload. The residence is also a property of "this
character" — natural to store alongside other character state. If future
residence-specific fields appear (move cooldowns, historical residence
tracking, multi-residence ownership), extraction to a
`CharacterResidence` model is a mechanical refactor. YAGNI applies.

**`Interaction.pose_kind`** — new TextChoices field:

```python
class PoseKind(TextChoices):
    STANDARD = "standard", "Standard"
    ENTRY = "entry", "Entry"
    DEPARTURE = "departure", "Departure"  # reserved for future

pose_kind = CharField(max_length=16, choices=PoseKind.choices,
                      default=PoseKind.STANDARD, db_index=True)
```

Spec C only reads `ENTRY`. `DEPARTURE` is reserved for a future departure-
pose mechanic. Setting `pose_kind=ENTRY` is the job of a future `+enter`
command (or API surface); Spec C does not implement that command.

**Partitioned-table note:** `Interaction` is partitioned. Adding
`pose_kind` is an additive column change — `mode`, `vote_count`, and
`visibility` already coexist on it. The partition SQL needs updating to
match the migration. Flagged for the implementation plan.

---

## 3. Services

All services in `world/magic/services/` (new submodule
`world/magic/services/gain.py` to keep the file focused).

### 3.1 Endorsement creation

```python
def create_pose_endorsement(
    endorser_sheet: CharacterSheet,
    interaction: Interaction,
    resonance: Resonance,
) -> PoseEndorsement:
    """Validate and persist a pose endorsement.

    Does NOT fire grant_resonance — settlement happens weekly.

    Raises:
        ValidationError: precondition failure (alt guard, whisper, unclaimed
            resonance, duplicate, non-participant).
    """


def create_scene_entry_endorsement(
    endorser_sheet: CharacterSheet,
    endorsee_sheet: CharacterSheet,
    scene: Scene,
    resonance: Resonance,
) -> SceneEntryEndorsement:
    """Validate, persist, and grant the flat scene-entry reward.

    Atomic: writes the SceneEntryEndorsement row and fires grant_resonance
    (which writes the ResonanceGrant ledger row) in one transaction.

    Raises:
        ValidationError: precondition failure.
    """
```

### 3.2 Weekly settlement

```python
def settle_weekly_pot(endorser_sheet: CharacterSheet) -> SettlementResult:
    """Settle all unsettled PoseEndorsement rows for one endorser.

    For each endorser with unsettled endorsements:
      1. Sum N = count of unsettled endorsements for that endorser.
      2. share = ceil(config.weekly_pot_per_character / N)
      3. For each unsettled endorsement:
         - Call grant_resonance(endorsee_sheet, resonance, share,
                                source=POSE_ENDORSEMENT,
                                source_ref=<PoseEndorsement.pk>)
         - Set granted_amount = share, settled_at = now()
      4. All under one atomic transaction — partial settlement is impossible.

    Idempotent: re-running with no unsettled rows is a no-op.

    Returns:
        SettlementResult(endorser_sheet, endorsements_settled, total_granted).
    """
```

### 3.3 Residence management

```python
def set_residence(
    sheet: CharacterSheet,
    room_profile: RoomProfile | None,
) -> None:
    """Set or clear a character's current residence.

    Passing None clears the residence (character has no current lair).
    O(1) — updates the FK and invalidates any cached handler state.
    """


def tag_room_resonance(
    room_profile: RoomProfile,
    resonance: Resonance,
    set_by: AccountDB | None = None,
) -> RoomResonance:
    """Tag a room with a resonance. Lazy-creates RoomAuraProfile if missing.

    Idempotent: if the tag already exists, returns the existing row unchanged.
    """


def untag_room_resonance(
    room_profile: RoomProfile,
    resonance: Resonance,
) -> None:
    """Remove a resonance tag from a room. No-op if the tag doesn't exist."""


def get_residence_resonances(sheet: CharacterSheet) -> set[Resonance]:
    """Return the set of resonances granting trickle for this character.

    Computes: (sheet.current_residence → RoomAuraProfile → resonance tags)
              ∩ (sheet.character_resonances — claimed set).
    Returns empty set if sheet has no residence, residence has no aura
    profile, or no tags match claimed resonances.
    """
```

### 3.4 Daily + weekly ticks

```python
def resonance_daily_tick() -> ResonanceDailyTickSummary:
    """Master daily tick. Runs residence + outfit trickle.

    Registered in ``src/world/game_clock/tasks.py`` alongside
    ``anima_regen_tick`` and ``decay_all_conditions_tick`` (Scope 6
    pattern — see `CronDefinition(task_key="magic.anima_regen_daily", ...)`
    at approximately line 316 of that file).

    Each per-character step is atomic (one transaction per character);
    a failure on one character does not poison the tick.
    """


def resonance_weekly_settlement_tick() -> ResonanceWeeklySettlementSummary:
    """Master weekly tick. Runs pose-endorsement settlement.

    Registered in ``src/world/game_clock/tasks.py``. Fires on
    config.settlement_day_of_week (default Monday). Actual gate is 'sheet
    has unsettled endorsements' (not date comparison) so server downtime
    on settlement day doesn't skip a week; the tick fires on the next
    daily pass and finds the overdue work.
    """
```

### 3.5 Account resolution helper

```python
def account_for_sheet(sheet: CharacterSheet) -> AccountDB | None:
    """Resolve a CharacterSheet to the Account currently playing it.

    Walks CharacterSheet → RosterEntry → current RosterTenure → Account.
    Returns None if the sheet has no current tenure (between players,
    retired, NPC).

    Alt-guard helper: two sheets with the same non-None account are alts.
    Alt-guard comparison: if either returns None, treat as "no alt
    relationship proven" — endorsement is permitted (fail-open at the
    sheet layer; account-less sheets should be rare and staff-visible).
    """
```

---

## 4. API

All endpoints follow existing patterns: FilterSets, proper pagination,
permission classes, DRF serializers.

### 4.1 New endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| POST | `/api/scene-entry-endorsements/` | Create an entry endorsement. Body: `{scene_id, endorsee_sheet_id, resonance_id}`. Returns 201 + the created row (including `granted_amount`). |
| POST | `/api/pose-endorsements/` | Create a pose endorsement. Body: `{interaction_id, resonance_id}`. Returns 201. No amount yet (unsettled). |
| DELETE | `/api/pose-endorsements/<id>/` | Retract an unsettled endorsement. 404 if already settled. Permission: requester owns the endorser_sheet. |
| DELETE | `/api/scene-entry-endorsements/<id>/` | Retract an entry endorsement. Also claws back the ResonanceGrant + updates balance/lifetime_earned. Permission: requester owns the endorser_sheet. Time-window optional (config-tunable). |
| GET | `/api/resonance-grants/?character_sheet=<id>` | Paginated ledger viewer. Filterable by source, resonance, date range. Endorsee-private by default. |
| PATCH | `/api/character-sheets/<sheet_id>/` | Update `current_residence_id` as a partial field update. Body: `{current_residence_id: <int>}` or `{current_residence_id: null}`. Uses the existing CharacterSheet viewset — no new endpoint. |

### 4.2 Permissions

- Endorsement creation: requester's persona must match the endorser_sheet
  (standard "act as your character" permission).
- Resonance-grants GET: requester must own the character_sheet OR be staff.
  Future leaderboard flag `ResonanceGrant.is_public` (unused at launch)
  leaves room for opt-in public visibility.
- Residence PATCH (on CharacterSheet): requester must own the sheet — handled by the existing CharacterSheet viewset permissions, no new permission class needed. The serializer needs `current_residence` added to its `fields` with appropriate write access.

### 4.3 Serializers

Standard DRF ModelSerializers. `PoseEndorsement` serializer exposes
`granted_amount` and `settled_at` as read-only — clients display "pending"
until settled. `SceneEntryEndorsement` serializer exposes
`granted_amount` as read-only (captured at creation).

---

## 5. Gain Surface Rules Summary

### 5.1 Scene-entry endorsement

| Property | Value |
|---|---|
| Trigger | Peer calls `create_scene_entry_endorsement` |
| Cadence | Immediate; `grant_resonance` fires synchronously |
| Value | `config.scene_entry_grant` (default 4) |
| Source enum | `SCENE_ENTRY` |
| Who can endorse | Any character with a historical `SceneParticipation` row on the scene |
| Who can be endorsed | Character with an `Interaction` in the scene where `pose_kind=ENTRY` |
| Once per | `(endorser_sheet, endorsee_sheet, scene)` — unique constraint |
| Resonance constraint | Must be in endorsee's claimed resonances |
| Alt guard | `account_for_sheet(endorser) != account_for_sheet(endorsee)` |
| Masquerade behavior | Gain goes to real sheet; `persona_snapshot` captured |

### 5.2 Pose endorsement

| Property | Value |
|---|---|
| Trigger | Peer calls `create_pose_endorsement` |
| Cadence | Deferred — settled weekly |
| Value | `ceil(weekly_pot_per_character / N_endorser_unsettled_count)` at settlement |
| Source enum | `POSE_ENDORSEMENT` |
| Who can endorse | Scene participant of `interaction.scene` OR interaction receiver |
| Who can be endorsed | Target of any non-whisper, non-very-private interaction |
| Once per | `(endorser_sheet, interaction)` — unique constraint |
| Resonance constraint | Must be in endorsee's claimed resonances |
| Alt guard | Same as above |
| Masquerade behavior | Same as above |
| Whispers | Excluded (`mode == WHISPER` blocked at service layer) |
| Very-private | Excluded (`visibility == VERY_PRIVATE` blocked at service layer) |
| Settlement cadence | Weekly (`settlement_day_of_week`), fallback: "unsettled rows exist" gate |

### 5.3 Room residence trickle

| Property | Value |
|---|---|
| Trigger | Daily tick processes all sheets with `current_residence` set |
| Cadence | Daily |
| Value | `config.residence_daily_trickle_per_resonance` per matching resonance |
| Source enum | `ROOM_RESIDENCE` |
| Source ref | `RoomAuraProfile.pk` |
| Eligibility | Sheet has `current_residence`; residence's `RoomProfile` has an associated `RoomAuraProfile`; at least one tagged resonance matches the sheet's claimed resonances |
| Matching rule | Union of (aura profile resonance tags) ∩ (sheet's claimed resonances) — one trickle per matching resonance |

### 5.4 Outfit trickle (stubbed)

| Property | Value |
|---|---|
| Trigger | Daily tick calls `get_outfit_resonance_contributions(sheet)` |
| Value | Today: empty iterable. When Items ships: per-(item, resonance) contribution |
| Source enum | `OUTFIT_ITEM` |
| Source ref | When implemented: `ItemInstance.pk` |
| Spec C scope | Hook only — no item authoring, helper returns empty |

### 5.5 Staff grant

| Property | Value |
|---|---|
| Trigger | Staff admin action via Django admin |
| Cadence | On-demand |
| Source enum | `STAFF_GRANT` |
| Source ref | Nullable (staff grants need no source row) |

Staff can grant arbitrary amounts via admin. This is intentionally low-
ceremony — the ResonanceGrant ledger captures it, that's the audit.

---

## 6. Tuning & Sizing (Placeholders)

Default `ResonanceGainConfig` values at first migration:

| Knob | Default | Reasoning |
|---|---|---|
| `weekly_pot_per_character` | 20 | Active player endorsing 4–6 poses/week → each endorsement worth 3–5 |
| `scene_entry_grant` | 4 | Memorable scene with 4 endorsers on your entry → +16 for that entry |
| `residence_daily_trickle_per_resonance` | 1 | One matching resonance → 7/week per claimed resonance |
| `outfit_daily_trickle_per_item_resonance` | 1 | (Unused until Items ships) |
| `same_pair_daily_cap` | 0 (off) | YAGNI until observed abuse |
| `settlement_day_of_week` | 0 (Monday) | Server UTC |

### 6.1 Projected weekly income

An active-RPer-with-fashion baseline per week:
- 3 scenes × ~4 entry endorsements = **~12** (scene entry)
- 3 × ~3 pose endorsements (ceil-weighted) = **~9** (pose endorsement)
- 7 × ~3 residence trickles (3 claimed resonances matched) = **~21**
- 7 × ~3 outfit trickles (post-Items) = **~21**

**≈ 63/week active+engaged.** Bob the Bland: 0. That's the intended gap.

These numbers exist to be tuned during playtest — not to be defended. The
shape of the economy (endorsement > residence > outfit, weekly pot
divides, no receive cap) is the locked-in part.

---

## 7. Anti-Farm Rules

### 7.1 Account-level alt guard

`account_for_sheet(endorser) != account_for_sheet(endorsee)` is enforced
at both endorsement service functions. Players with multiple characters
logged in simultaneously (a supported feature) cannot self-endorse across
characters. If either returns `None`, endorsement is permitted (fail-open
at the sheet layer) — account-less sheets are edge cases that staff should
investigate separately.

### 7.2 Resonance fit constraint

Endorser can only tag resonances the endorsee has already claimed
(`CharacterResonance` row exists, balance ≥ 0). You cannot be
reinforced for identities you haven't claimed. Character creation
claims initial resonances; subsequent claims happen via progression or
staff action (out of scope for Spec C).

### 7.3 Whisper / private-pose exclusion

Interactions with `mode == WHISPER` or `visibility == VERY_PRIVATE` are
not endorsable. Aura farming requires witnesses — whispers don't have
them, private visibility means the interaction isn't publicly
attributable.

### 7.4 Presence requirement

Pose endorsement requires the endorser was a scene participant or
interaction receiver. Prevents drive-by endorsement from outside the
scene. Scene-entry endorsement requires a historical `SceneParticipation`
row (no `joined_at` comparison — that would perversely incentivize
late arrival).

### 7.5 Self-endorsement block

`endorser_sheet != endorsee_sheet` enforced at service layer. (Alt guard
handles the cross-character case; this handles the trivial case.)

### 7.6 Tunable pair throttle

`same_pair_daily_cap` defaults to 0 (off). Can be raised to N to throttle
how many times one endorser can tag the same endorsee within a rolling
24h window. YAGNI until observed abuse patterns warrant it.

### 7.7 Uniqueness constraints

- Pose endorsement: unique `(endorser_sheet, interaction)` — one endorsement per pose per endorser.
- Scene entry: unique `(endorser_sheet, endorsee_sheet, scene)` — one entry endorsement per pair per scene.

### 7.8 No receive cap — popularity is power

There is no cap on how many endorsements a character can *receive* per
week. If 12 people think your entrance was sick, you get 12 endorsements.
This is the intended design: popularity-to-power conversion is the point
of aura farming.

---

## 8. Audit & Visibility

### 8.1 The ResonanceGrant ledger

Every gain writes one `ResonanceGrant` row. The ledger is the canonical
record of "how did I earn this resonance." Ordered by `granted_at`,
filterable by `source`, `resonance`, date range, character_sheet.

### 8.2 Endorsee-private visibility

By default, a character's ResonanceGrant ledger is visible only to:
- The account owning the character.
- Staff.

Public leaderboards are **out of scope** for this spec but explicitly
designed-for: add `ResonanceGrant.is_public = BooleanField(default=False)`
in a future spec to support opt-in "weekly aura farmer" public displays.
The endorsee's consent is the gate — we don't reveal private RP grants
without permission.

### 8.3 Masquerade handling

When an endorsement targets an Established or Temporary persona
(masquerade), the grant flows to the real `CharacterSheet` but the audit
row captures `persona_snapshot`. Audit reads like: `"+4 Abyssal from Alice
for [The Veiled Stranger]'s pose"`. Currency is real; identity surface is
whatever the endorsee chose to present.

This is explicitly required — the user design calls for masquerades to
work. Omitting persona snapshot would make disguise anti-incentivized
(can't farm aura while hiding your identity).

### 8.4 Retraction semantics

- Pose endorsement: retractable via DELETE while `settled_at IS NULL`. No
  grant has fired yet, so nothing to claw back.
- Scene-entry endorsement: retractable via DELETE; in an atomic
  transaction, remove the endorsement row, decrement `CharacterResonance.balance`
  and `lifetime_earned` by `granted_amount`, and create a compensating
  `ResonanceGrant` row with `amount = -granted_amount`. Balance must go
  ≥ 0 (refuse retraction that would underflow — audit + error). Time-window
  for retraction is optional, tunable via config (default: unrestricted,
  since this is pre-alpha). Post-launch tuning may restrict to N-hour
  window.

Note: a negative-amount `ResonanceGrant` violates the `PositiveIntegerField`
constraint. The compensating-row design needs reconsidering — likely use
a separate `ResonanceGrantReversal` model, or allow `amount = IntegerField`
with a service-layer-enforced "grants are positive, reversals are negative"
rule. Flagged for implementation-phase resolution.

---

## 9. Testing Strategy

### 9.1 Unit tests

Per-model and per-service tests in `world/magic/tests/`:

- Model constraint tests: uniqueness violations raise IntegrityError; fit
  filters at query time; Interaction pose_kind default STANDARD.
- `create_pose_endorsement` precondition failures: alt guard, whisper,
  very-private, unclaimed resonance, duplicate, non-participant, self-
  endorsement.
- `create_scene_entry_endorsement` precondition failures: no entry pose,
  endorser never a participant, alt guard, duplicate pair, unclaimed
  resonance.
- `settle_weekly_pot` math: ceil division with 1/3/7/20 unsettled rows;
  idempotency (re-run is a no-op); atomic transaction (all-or-nothing).
- `residence_trickle_tick`: sheet with no residence skipped; residence
  with no aura profile skipped; matching resonances trickle; non-matching
  resonances don't trickle; multi-claimed-resonance character gets one
  trickle per match.
- `set_residence`: set, clear, change.
- `tag_room_resonance`: idempotent, lazy-creates aura profile.
- `account_for_sheet`: walks the chain, returns None on no-tenure.

### 9.2 Integration tests

In `src/world/magic/tests/integration/test_resonance_gain_flow.py`,
mirroring Scope 6's `test_soulfray_recovery_flow.py` pattern:

1. **Full week simulation.** Alice creates 5 pose endorsements on Bob's
   poses across the week. Weekly settlement tick fires. Bob's
   `CharacterResonance.balance` reflects `ceil(20/5) × 5 = 20`. 5 new
   `ResonanceGrant` rows exist with source=POSE_ENDORSEMENT.
   `lifetime_earned` matches.
2. **Scene-entry immediate grant.** Alice calls
   `create_scene_entry_endorsement` on Bob's entry pose. Bob's balance
   increments by 4 in the same transaction. 1 new `ResonanceGrant` row
   with source=SCENE_ENTRY.
3. **Alt guard blocks cross-endorsement.** Alice has two characters,
   A1 and A2. A1 attempts to endorse A2 → service raises ValidationError,
   no row written.
4. **Masquerade flows correctly.** Bob poses as "The Veiled Stranger"
   (Established persona). Alice endorses. Audit row captures
   persona_snapshot = Veiled Stranger's persona. Currency lands on Bob's
   real CharacterSheet.
5. **Residence trickle end-to-end.** Staff creates a RoomAuraProfile and
   tags two resonances. Bob declares residence there (but has claimed
   only one of the two resonances). Daily tick fires. Bob's balance for
   his claimed resonance increments by 1. His other resonance (not
   tagged on the lair) doesn't trickle. Non-claimed tagged resonance
   also doesn't trickle.
6. **Outfit stub runs cleanly.** Daily tick iterates all sheets, calls
   `get_outfit_resonance_contributions` (empty), completes without
   errors.
7. **Tuning update.** Staff updates `weekly_pot_per_character = 40`.
   Next settlement uses 40. Prior settled rows are unaffected.
8. **Whisper exclusion.** Alice attempts to endorse Bob's whisper
   interaction. Service raises ValidationError.
9. **Retraction.** Alice creates a scene-entry endorsement, then DELETEs
   it. Bob's balance and lifetime_earned decrement by the granted amount.
   Compensating audit row exists (per final shape from impl phase §8.4).

### 9.3 Factories

In `world/magic/factories.py` extensions:
- `ResonanceGainConfigFactory` (singleton helper).
- `PoseEndorsementFactory`, `SceneEntryEndorsementFactory`.
- `RoomAuraProfileFactory`, `RoomResonanceFactory`.

`CharacterResidenceFactory` is *not* needed — `current_residence` is just
a FK on CharacterSheet, set directly.

### 9.4 Regression coverage

Changes to `CharacterSheet` (new FK) and `Interaction` (new field) require
full-regression runs against character_sheets and scenes test suites. Run
with and without `--keepdb` before PR (per project `CLAUDE.md`).

---

## 10. Out of Scope

Explicitly **not** in Spec C:

- **The `+enter` command.** Including technique-coupled flashy entrances
  (flight, teleport, combat entry). Spec C only reads `pose_kind=ENTRY`;
  setting it is a future command layer.
- **Departure pose mechanics.** `pose_kind=DEPARTURE` is reserved in the
  enum but not acted on.
- **Item authoring for outfit trickle.** Items system hasn't shipped. The
  tick loop + helper stub ship empty; real item content lands with the
  Items spec.
- **Environment/outfit **claiming** by players.** Staff admin-authors
  `RoomResonance` at launch. Player-tagged lairs (tag-your-own-home-if-
  you-own-it) wait for the room-ownership system.
- **Public leaderboards.** Schema supports future public mode via opt-in
  flag; no public endpoint ships now.
- **Mechanical auto-grants.** Technique use, ritual completion,
  relationship-track advances, capstone unlocks — all deliberately cut.
  The economy is RP, not buttons.
- **Place-of-power combat bonuses.** A character "literally stronger" in
  their abyssal grotto is a future combat-spec concern. `RoomAuraProfile`
  is the natural data home for it and Spec C leaves the extensibility
  hooks clean, but the mechanic itself is out of scope.
- **Decorations-as-magical-furniture.** Same story as places-of-power:
  RoomAuraProfile is the future home; Spec C doesn't author.
- **Room ownership, keys, access control.** These are security/permission
  concerns distinct from magical aura. Per RoomProfile's docstring, they
  get their own sibling extension model(s) when needed.

---

## 11. Risks & Unknowns

### 11.1 Account resolution chain

The alt guard depends on `CharacterSheet → RosterEntry → current
RosterTenure → Account`. Implementation phase needs to verify the exact
FK shape and handle the null-tenure case (sheets between players,
retired, NPCs). Design decision: fail-open at the sheet layer for
None-account cases (endorsement permitted); account-less sheets are edge
cases staff investigate separately.

### 11.2 Partitioned-table column addition

`Interaction` is partitioned. Adding `pose_kind` is an additive column
change (follows the existing pattern of `mode`, `vote_count`,
`visibility`) but the partition SQL needs to be updated to match the
migration. Flagged for implementation-phase attention.

### 11.3 Settlement day boot timing

If the server is down on the configured settlement day, the weekly tick
misses its window. Implementation must use "sheet has unsettled
endorsements" as the actual gate (not date comparison). The
`settlement_day_of_week` is a *cue*, not a *constraint*. Same pattern as
Scope 6's daily ticks.

### 11.4 Negative-amount audit rows

Scene-entry retraction needs a compensating ledger row. `amount =
PositiveIntegerField` forbids negatives. Impl phase resolves by either:
- (a) Adding `ResonanceGrantReversal` sibling model (explicit reversal
  records, preserves grant positivity invariant), or
- (b) Changing `amount` to `IntegerField` with service-layer invariant.

Design leans (a) for cleaner audit semantics, flagged for impl-phase
confirmation.

### 11.5 Pose endorsement weight asymmetry

The weekly-pot-divides model means an endorsee doesn't know their grant
value until settlement. Intentional — encourages liberal tagging and
rewards picky endorsers naturally. But it is a design choice worth
confirming during playtest; if it feels unsatisfying in practice, a
migration path to a fixed-per-tag model is trivial (no schema change,
just service-function refactor).

### 11.6 Residence swapping exploitation

A character could theoretically change their current_residence right
before the daily tick to maximize trickle. Not a real concern pre-alpha
with no players. Config has no swap cooldown at launch. If abuse patterns
emerge post-alpha, `last_residence_change_at` + config cooldown knob is
a small follow-up.

---

## 12. Handoff to Future Specs

### 12.1 For the Items system

When the Items system ships:
- Add `ItemTemplate.resonances` M2M (or on wearable subtype).
- Implement `get_outfit_resonance_contributions(character_sheet) -> Iterable[tuple[ItemInstance, Resonance, int]]`.
- Worn-item scoping (which inventory slots count as "worn") is the Items
  spec's call.

Tick loop, config knob, and `ResonanceGrant.source=OUTFIT_ITEM` are
ready. No Spec C revisit.

### 12.2 For a place-of-power system

When a future combat/environment spec wants room-aura-to-power coupling:
- Read resonance tags via `RoomAuraProfile.room_resonances` (clean API
  already in place).
- Extend `RoomAuraProfile` with `place_of_power` flags or
  amplification fields — additive schema change.
- Combat bonuses read from the aura profile; they don't touch residence
  or trickle code.

### 12.3 For the `+enter` command

The entry-pose command is a command-layer feature. When it ships:
- Create an `Interaction` with `pose_kind=ENTRY`.
- Optionally call `use_technique` alongside for flashy entrances.
- Spec C's scene-entry endorsement surface is downstream and requires
  no changes.

### 12.4 For the departure-pose mechanic

`pose_kind=DEPARTURE` is reserved. When you design the mechanic:
- Define the equivalent of scene-entry endorsement (scene-exit
  endorsement?) or a different gain shape (witness memory?).
- Either a new `SceneExitEndorsement` model or extend the existing
  scene-entry endorsement with a generic "scene pose endorsement" that
  covers both kinds.

### 12.5 For a public leaderboard

When public visibility is wanted:
- Add `ResonanceGrant.is_public = BooleanField(default=False)`.
- Opt-in flag on the endorsee's account/settings.
- New `/api/public-resonance-grants/` endpoint filters by `is_public=True`.
- Aggregation queries for weekly top-earners, top-aura-farmers-by-
  resonance, etc. — classic leaderboard pattern, reads from
  ResonanceGrant.
