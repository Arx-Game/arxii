# Societies System

Social structures, organizations, reputation, and legend tracking for character identities (personas).

**Source:** `src/world/societies/`

---

## Enums (types.py)

```python
from world.societies.types import ReputationTier
# Values: REVILED, DESPISED, DISLIKED, DISFAVORED, UNKNOWN, FAVORED, LIKED, HONORED, REVERED

# Convert numeric reputation to tier
tier = ReputationTier.from_value(350)       # ReputationTier.LIKED
tier.display_name                            # "Liked"
tier.range_description                       # "+250 to +499"
```

**Reputation Tier Thresholds:**

| Tier | Range |
|------|-------|
| Reviled | -1000 to -750 |
| Despised | -749 to -500 |
| Disliked | -499 to -250 |
| Disfavored | -249 to -100 |
| Unknown | -99 to +99 |
| Favored | +100 to +249 |
| Liked | +250 to +499 |
| Honored | +500 to +749 |
| Revered | +750 to +1000 |

---

## Models

### Core Structures (SharedMemoryModel - cached)

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `Society` | Socio-political stratum within a Realm | `name`, `realm` (FK to `realms.Realm`), `description`, 6 principle fields (`mercy`, `method`, `status`, `change`, `allegiance`, `power`) |
| `OrganizationType` | Template with default rank titles for org categories | `name`, `rank_1_title` through `rank_5_title` |
| `Organization` | Specific group within a Society | `name`, `society`, `org_type`, 6 `*_override` principle fields, 5 `rank_*_title_override` fields |

### Membership and Reputation (SharedMemoryModel - per-persona instances)

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `OrganizationRank` | One rung on an org's five-tier authority ladder | `organization`, `name`, `tier` (1 highest, 5 lowest), `can_invite`, `can_kick`, `can_manage_ranks`, `can_lead_rituals`, `can_declare_standing` (#3290), `can_resolve_appeals` (#3293) |
| `OrganizationMembership` | Links a Persona to an Organization at a rank | `organization`, `persona` (FK to `scenes.Persona`), `rank` (FK to `OrganizationRank`), `joined_date`, `left_at`, `exiled_at` |
| `OrganizationMembershipOffer` | Pending or resolved invitation/application | `organization`, `from_persona`, `to_persona`, `kind` (`INVITE`/`APPLICATION`), `status` (`PENDING`/`ACCEPTED`/`DECLINED`/`CANCELLED`), `created_at`, `resolved_at` |
| `SocietyReputation` | Persona's reputation with a Society | `persona`, `society`, `value` (-1000 to +1000) |
| `OrganizationReputation` | Persona's reputation with an Organization | `persona`, `organization`, `value` (-1000 to +1000) |
| `StandingDeclaration` (#3290) | A leader's audited favor/disfavor declaration | `organization`, `target_persona`, `declared_by_persona`, `direction` (`StandingDirection` FAVOR/DISFAVOR), `delta_applied`, `citation`, `game_week` (FK, rate-limit key), `created_at`; unique per (organization, target_persona, game_week) |

### Legend System (models.Model)

**Settled, not asserted (#3463, ADR-0249).** Legend is priced at the END of a story
unit by `world.societies.legend_settlement.settle_legend_for`, the single mint seam.
Four rules, in order:

1. **Per-person peril floor** — each earner's risk priced against their own level,
   not the party average. Below `LegendSettlementConfig.risk_floor`: **zero**, not a
   reduced award. Safe play cannot advance anyone.
2. **Held-objective share** — the shared deed pays the severity-weighted fraction of
   stakes actually held.
3. **Station** — `min(earner level, threat level)`, stamped as
   `LegendEntry.earned_at_level`, never folded into `base_value`.
4. **Standout pass** — brilliance on a crucial contribution pays even when the unit
   was lost (ADR-0122, generalized past `Battle`).

`RenownAwardConfig.risk` is a **declared wager, not a payout**: Legend pays on the
weaker of the author's declaration and the level-priced settled reality, and mints
nothing without a settled context. #676's three independent scales are preserved —
a royal wedding stays high Magnitude, NONE Risk: famous, not legendary.

Authored tuning: `RiskCalibration.legend_award`, `RenownMagnitudeAward`,
`LegendSettlementConfig`. Python constants are fallbacks only.

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `LegendEntry` | A deed that earns legend for a persona | `persona`, `title`, `description`, `base_value`, `source_note`, `location_note`, `societies_aware` (M2M) |
| `LegendSpread` | An instance of spreading/embellishing a deed | `legend_entry`, `spreader_persona`, `value_added`, `description`, `method`, `societies_reached` (M2M) |
| `LegendLevelCalibration` (#3466) | Per-level dials for honoring and deed-granted titles | `level` (unique), `honor_hares_required`, `honor_value_added`, `deed_title_threshold`. Authored content; unguarded lookups (a missing row raises, surfacing on the admin required-content panel rather than silently mispricing an honor) |
| `LegendHonor` (#3466) | One paid, written testimony to a deed | `deed`, `honorer` (PROTECT — story-significant), `journal_entry`, `deed_story`, `hares` (M2M to Golden Hares spent), `hares_spent`, `value_added`, `established_deed`; unique per (deed, honorer) |

**Spreading a deed grows fame *and* prestige.** On a successful `spread_a_tale`
retelling (`_resolve_spread_tale`), besides adding traffic-scaled legend, the deed
subject's **fame** (`apply_spread_fame_bump` — fast, larger, and it decays) and
**prestige** (`apply_spread_prestige_bump` — slow, smaller, permanent
`prestige_from_deeds`; #2168) both grow, each scaled by the room's
`room_activity_band` multiplier. A Social Hub (#1694) boosts that multiplier via
room traffic, so it amplifies both. Fame tier separately acts as a display
multiplier on prestige.

#### The Rite of Honors (#3466, ADR-0251, ADR-0252)

A character spends Golden Hares and writes a public journal to honor another
character's deed — raising a witnessed deed's `base_value`, or *establishing* a
fresh solo deed for an extraordinary act the automatic settlement never
credited. `world.societies.honors.honor_deed` is the single seam, dispatched by
the "Rite of Honors" `magic.Ritual` row (`SERVICE` execution kind,
`hedge_accessible=False` — a Gifted rite by ruling). It works posthumously by
design: nothing in `honors.py` checks life-state, and nothing should.

**The ceiling rule (ADR-0251).** Honoring may raise a deed's `base_value` only up
to the anchoring `LegendEvent.base_value` — `headroom = event.base_value -
deed.base_value`, and a headroom of zero refuses (`DeedAtCeilingError`). Peer
judgment *redistributes* recognition inside an envelope the event's own
settlement already proved; it can never invent peril that never happened. That
is why the rite does not reopen the hole ADR-0249 closed: nothing here mints
danger, it only moves already-proved value between the event and its deeds.
Several refinements close gaps that clamp alone doesn't:
- **Establishing refuses when the honoree already has an active deed anchored to
  that event** (`HonoreeAlreadyAnchoredError`) — otherwise several honorers could
  each establish a separate full-ceiling deed for the same act, uncapping the
  aggregate the ceiling exists to bound. Many voices are meant to grow ONE deed.
  The anchoring `LegendEvent` row is locked (`select_for_update()`) before this
  check runs, so two concurrent establishes against the same event serialize
  behind one commit rather than both reading "no anchored deed yet" (the
  amplify branch gets the equivalent guarantee for free via the deed's own row
  lock).
- **Establishing also requires the HONOREE to have witnessed the anchoring
  event**, not just the honorer — checked against the same
  `scene_witness_personas` list the honorer is checked against
  (`HonoreeNotPresentToEstablishError`). Gating only the honorer would let a
  witness mint a full-ceiling deed for someone who was never at the event,
  inventing peril they never faced. This is deliberately a presence check, not
  a widened `HonoreeAlreadyAnchoredError` scoped across a sheet's personas —
  that would become a mask-identity oracle (telling a prober that some other
  persona on the same sheet already has a deed there).
- **A struck deed (`LegendEntry.is_active=False`) proves nothing.** It doesn't
  count toward the station used when establishing a sibling deed, doesn't block
  a fresh deed from being established under the same event, and amplifying one
  is refused outright (`DeedNotActiveError`) — it is worth nothing everywhere
  else a deed's value is read, so a paid rite could never raise a number any
  read path will ever surface.

**Titles retarget to Persona (ADR-0252).** `achievements.PersonaTitle`
(`maybe_grant_deed_title`, called from `honor_deed`'s last step) mints a title
when a deed crosses its station's `LegendLevelCalibration.deed_title_threshold`,
landing on `deed.persona` — the face that did it, never the character sheet.
Titles hang on **Persona** throughout precisely because Legend is persona-scoped
throughout; a deed earned behind a mask titles the mask and can never surface on
the character sheet to out the player. Achievement-sourced titles (the
unrelated `RewardDefinition` TITLE path) resolve to the sheet's **PRIMARY**
persona, never the active one — an achievement is a fact about who the
character *is*, not whatever disguise happened to be worn when a stat ticked
over.

**The honorer is always the PRIMARY persona, never whatever face is active.**
`honor_deed` resolves `honorer_persona = character_sheet.primary_persona`
unconditionally — the same argument `_grant_title` makes for achievement
titles. An honor is a named public act: the journal is authored by
`character_sheet` (the real character) and the mirrored scene pose
(`_post_declaration`) always posts under the primary persona regardless of
what's active, so recording a mask as `LegendHonor.honorer` would be a
deterministic mask-to-real link sitting right beside that public journal. The
rite is always performed as yourself.

**Eligibility, in order** (`honor_deed`'s Step 2, all before any write):
amplifying requires already knowing the deed (`knows_deed`), not having
already honored it (`unique_honor_per_honorer`), and the deed being active
(struck deeds refuse amplification outright); establishing requires having
witnessed the anchoring event's scene (both the honorer AND the honoree,
above) and not being the honoree's own face. Both refuse honoring your own
deed. Pricing (`LegendLevelCalibration`, keyed by the honorer's own level) and
affordability (Golden Hares via `resolve_unredeemed_favor_tokens`) run only
after eligibility clears.

### Obligations (#2428)

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `OrganizationObligation` | A personal debt of one Golden Hare owed by a character to an org (e.g. an Unbound Prospect's unpaid Academy entrance) | `debtor` (FK to `character_sheets.CharacterSheet`, CASCADE, `related_name="org_obligations"`), `creditor` (FK to `Organization`, PROTECT, `related_name="personal_obligations_owed"` — **not** `obligations_owed`, which `currency.OrgObligation.from_organization` already claims for its unrelated org-to-org tithe/tax concept), `origin` (`ObligationOrigin`: `ACADEMY_ENTRANCE`/`OTHER`), `state` (`ObligationState`: `OWED`/`SETTLED`/`SETTLED_BY_SPONSOR`), `created_at`, `settled_at`, `settled_by_token` (FK to `currency.FavorTokenDetails`, SET_NULL, string ref) |

Rows are never deleted — a settled obligation is permanent history, not a
cleared flag. `obligation_services.py`:

- `settle_obligation(obligation, token)` — redeems `token` via
  `currency.redeem_favor_token(token, redeemer_org=obligation.creditor)` (Task
  1's typed surface: raises `ValidationError` if the token is already redeemed
  or not issued by the creditor), then flips `OWED` → `SETTLED` and stamps
  `settled_at`/`settled_by_token`. Raises `ObligationNotOwedError` if the
  obligation isn't `OWED`. Live caller: `world.npc_services.effects.
  run_settle_obligation_offer` (the `OfferKind.SETTLE_OBLIGATION` effect handler),
  reached via the Academy Registrar's ungated offer
  (`world.npc_services.seeds.ensure_academy_registrar_role`) — the whole-branch-fix
  front door that lets a debtor actually pay this off in play.
- `has_open_obligation(sheet, org)` — read-only gate: `True` iff `sheet` has
  an `OWED` row against `org`. Consumed by the Academy training gate (#2440).

**CG-finalize hook (#2428 Task 3):** `world.character_creation.services.finalize_magic_data`
resolves the "Shroudwatch Academy" `Organization` by name (seeded by
`world.seeds.character_creation.ensure_shroudwatch_academy`, `tradition=None` —
deliberate NULL, #2426 ruling) and creates one `ACADEMY_ENTRANCE` obligation row
per character: `OWED` when `draft.selected_tradition.name == "Unbound"`, else
`SETTLED_BY_SPONSOR` with `settled_at` stamped and `settled_by_token` left `NULL`
(the sponsor's Hare is lore-recorded, not a minted item at CG time). Defensive
logged skip (no row created) if the Academy isn't seeded yet, mirroring
`seed_beginning_traditions`'s Unbound-tradition skip. `get_or_create`-idempotent.

FK direction (ADR-0010): societies is the dependent side of this edge (an
obligation is a societies concept that happens to be settled with a currency
instrument), so `settled_by_token` uses the string ref
`"currency.FavorTokenDetails"` and `obligation_services.py` deferred-imports
`world.currency.services` at call time rather than at module load.

**Audere Majora crossing → deed.** When a character completes an Audere Majora
threshold crossing (`world/magic/audere_majora.py`), `_mint_crossing_deed` calls
`fire_renown_award` using the threshold's authored `RenownAwardConfig` fields
(magnitude/risk/reach/archetypes). This creates a `LegendEntry` attributed to the
crosser's primary persona (and fires fame/prestige/society-reputation awards). The
resulting entry is linked back via `AudereMajoraCrossing.legend_entry` (OneToOneField,
related_name `audere_majora_crossing`). Personas present in the scene are recorded as
`WITNESSED` via `grant_deed_knowledge`. No `LegendEntry` is created when
`threshold.risk == NONE`.

---

## Appeals to organizations (#3293)

An appeal is a free-text IC ask lodged with an organization: any character may
lodge one (no membership required), members read and sign onto it to show
support, and leadership resolves it with a written answer. "Appeal" is the
canonical term — "petition" stays reserved for the unrelated OOC staff-contact
ticket (`world.player_submissions.models.Petition`); see ADR-0231.

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `OrgAppeal` | A free-text ask lodged with an org | `organization`, `petitioner_persona`, `title`, `body`, `state` (`OrgAppealState`: `OPEN`/`GRANTED`/`DECLINED`/`WITHDRAWN`), `resolution_text`, `resolved_by_persona` (nullable), `created_at`, `resolved_at` |
| `OrgAppealSignon` | A member's public show of support for an open appeal | `appeal`, `member_persona`, `note`, `created_at` — unique per (appeal, member) |

**Lifecycle** mirrors `GroupStoryRequest` (`stories/models.py` #2119) — a
sibling shape for a different target (org vs. GM pool), not a generalization
of it: `OPEN` → `GRANTED`/`DECLINED` (leadership, written answer) or
`WITHDRAWN` (petitioner). A DB-level partial unique constraint enforces one
`OPEN` appeal per (organization, petitioner) — the constraint is the contract;
`appeal_services.py` does not pre-check it, but `LodgeAppealAction` catches the
resulting `IntegrityError` and surfaces a friendly refusal (mirrors
`InviteToEventAction`'s `EventError.INVITE_DUPLICATE` pattern).

FK direction (ADR-0010): `OrgAppeal`/`OrgAppealSignon` are the
specific/dependent request models; they point at the general primitives
(`Organization`, `scenes.Persona`) with no back-reference from either.

**`appeal_services.py`:**

- `lodge_appeal(*, organization, petitioner_persona, title, body)` — creates
  an `OPEN` row. No `is_established_or_primary` gate (unlike
  `apply_to_organization`) — lodging is not membership.
- `signon_appeal(*, appeal, member_persona, note="")` — idempotent
  get-or-create; requires an active membership (`NotOrganizationMemberError`)
  and an `OPEN` appeal (`AppealNotOpenError`).
- `resolve_appeal(*, appeal, verdict, resolution_text, resolver_persona, is_staff=False)`
  — requires a `can_resolve_appeals` rank (`can_resolve_org_appeals`) or
  `is_staff=True`; raises `NotAuthorizedToResolveAppealError`,
  `InvalidAppealVerdictError`, or `AppealNotOpenError`.
- `withdraw_appeal(*, appeal, petitioner_persona)` — petitioner-only
  (`NotAppealPetitionerError`) while `OPEN`.
- `can_resolve_org_appeals(persona, organization)` — active-membership +
  `rank__can_resolve_appeals` check, mirrors `houses.services.is_org_leader`.

**No mechanical rewards** — the written answer is RP; an org acts on a
granted appeal through existing levers (`OrgTask`, standing, coin). Composed,
not wired, in this PR.

**Actions** (`actions/definitions/org_appeals.py`, all `target_type=SELF`,
`category="social"`): `org_appeal_lodge` (`LodgeAppealAction`),
`org_appeal_signon` (`SignonAppealAction`), `org_appeal_resolve`
(`ResolveAppealAction` — `verdict` kwarg is `"grant"`/`"decline"`, `answer`
becomes `resolution_text`), `org_appeal_withdraw` (`WithdrawAppealAction`).

**Telnet** (`commands/organizations.py`, `CmdAppeal`, key `appeal`, a sibling
namespace to `CmdOrg` — not a subverb of it, since its default grammar lodges
rather than listing subverbs): `appeal <org>=<title>/<body>` (lodge),
`appeal list <org>` (read, member + own-appeal gated), `appeal signon
<id>[=<note>]`, `appeal resolve <id>=grant|decline/<answer>`, `appeal
withdraw <id>`.

**DRF** (`OrgAppealViewSet`, `/api/societies/appeals/`): list/retrieve
(queryset = active members of the org + the petitioner's own appeals,
mirrors `tasking/views.py`'s `OrgTaskViewSet` member-gated board read),
`create` (lodge), and detail actions `signon`/`resolve`/`withdraw` — all
dispatch through the matching Action (ADR-0001), the same seam telnet uses.

**Frontend** (`frontend/src/orgs/`): `AppealsPanel` on the members-only
`OrgPage` (list + sign-on dialog + leadership resolve dialog — every member
sees the Resolve button, the backend enforces the rank/staff gate and a
non-privileged attempt surfaces as a toast error); `LodgeAppealDialog` on the
public `DossierPage` (readable by any authenticated player — the "Appeal to
`<org>`" surface for an outsider who isn't a member).

---

## Principles System

Six value axes on a -5 to +5 scale. Organizations can override society values.

| Principle | Negative (-5) | Positive (+5) |
|-----------|---------------|---------------|
| `mercy` | Ruthlessness | Compassion |
| `method` | Cunning | Honor |
| `status` | Ambition | Humility |
| `change` | Tradition | Progress |
| `allegiance` | Loyalty | Independence |
| `power` | Hierarchy | Equality |

---

## Key Methods

### Organization

```python
from world.societies.models import Organization

# Get effective principle (override or inherit from society)
org.get_effective_principle("mercy")  # Returns int (-5 to +5)

# Get effective rank title (override or inherit from org_type)
org.get_rank_title(1)  # Returns str, e.g., "Patriarch"
```

### OrganizationMembership

```python
from world.societies.models import OrganizationMembership

# Get the title for this member's rank
membership.get_title()  # Delegates to org.get_rank_title(self.rank)

# Validation: only primary or established personas can join
membership.clean()  # Raises ValidationError for temporary disguises
```

### SocietyReputation / OrganizationReputation

```python
from world.societies.models import SocietyReputation

# Get named tier from hidden numeric value
reputation.get_tier()  # Returns ReputationTier enum member
reputation.get_tier().display_name  # "Favored"
```

### LegendEntry

```python
from world.societies.models import LegendEntry

# Total legend = base + all spreads
entry.get_total_value()  # base_value + sum(spreads.value_added)
```

---

## Membership Lifecycle

Generic (non-covenant) organizations use a rank-based lifecycle defined in
`world.societies.membership_services`. Covenants have their own lifecycle and are
rejected by these services/actions.

### Service functions

```python
from world.societies.membership_services import (
    ensure_default_rank_ladder,
    base_rank_for_organization,
    active_membership_for_persona,
    join_organization,
    leave_organization,
    invite_to_organization,
    apply_to_organization,
    accept_invitation,
    decline_invitation,
    accept_application,
    decline_application,
    promote_member,
    demote_member,
    expel_member,
)
```

- `ensure_default_rank_ladder(organization)` creates tiers 1–5 if absent; top tier gets all capability flags.
- `join_organization(organization, persona)` admits at the lowest tier (5) after checking blocks and persona validity.
- `invite_to_organization(...)` / `apply_to_organization(...)` create pending offers.
- `accept_invitation(offer, persona)` / `accept_application(offer, actor_persona)` promote the offer to a membership.
- `leave_organization(membership)` records a voluntary departure (`left_at`).
- `expel_member(target, actor)` records an expulsion (`left_at` and `exiled_at`).
- `promote_member(target, actor)` / `demote_member(target, actor)` move a member one tier, gated by `can_manage_ranks`.

### Player actions and telnet command

All major transitions are actions on the shared `action.run()` / `dispatch_player_action()` seam:

| Action key | Telnet usage | Purpose |
|------------|--------------|---------|
| `org_invite` | `org invite <name> in <organization>` | Invite a persona to join |
| `org_apply` | `org apply <organization>` | Apply to join an organization |
| `org_join` | `org join <organization>` | Accept a pending invitation |
| `org_leave` | `org leave <organization>` | Voluntarily leave the organization |
| `org_promote` | `org promote <name> in <organization>` | Move a member up one tier |
| `org_demote` | `org demote <name> in <organization>` | Move a member down one tier |
| `org_expel` | `org expel <name> from <organization>` | Remove a member from the organization |

`CmdOrg` routes `org <subverb>` through the same dispatcher the web UI uses.
Invitation accept/decline also flows through the existing `accept org` / `decline org`
offer registry (`commands/offer_registry`) with `OrgInviteHandler` registered under
keyword `org`.

### Ritual-dispatched induction (#1868)

Alongside the plain `org_invite`/`org_join` path above, a member holding a rank with
`can_lead_rituals=True` may lead a ceremonial "Organization Induction" `Ritual`,
dispatched through the generic `world.magic` `RitualSession` machinery (the same
substrate Covenant Induction uses). This is an **additional**, optional path — the
plain invite/join path above is untouched and keeps working for every organization.

- `world.societies.membership_services.assert_initiator_can_lead_org_ritual` —
  draft-time validator; the first real consumer of `OrganizationRank.can_lead_rituals`.
- `world.societies.membership_services.induct_organization_member_via_session` —
  fire-time service; reuses `join_organization` unchanged.
- Telnet: `ritual draft "Organization Induction" invite=<candidate> organization=<name>`,
  then the candidate `ritual join <id>`, then the officiant `ritual fire <id>`. See
  `commands/ritual_adapters.py`'s `OrganizationInductionAdapter`.
- Covenant-kind organizations are rejected (they keep their own bespoke induction
  ritual via `world.covenants.services`).
- **Telnet-only for v1** — no web entry point exists yet, since no generic-Organization
  frontend exists at all (tracked under "Organization UI" in
  `docs/roadmap/societies.md`'s MVP list). Nothing here blocks adding one later.

### Standing Declarations (#3290)

An org leader (a rank with `can_declare_standing=True`) can officially declare a
persona favored or disfavored, a deliberate act distinct from the automated
consequences (secret reveals, gang turf, stake resolution) that are the only other
gameplay writers of `OrganizationReputation`.

```python
from world.societies.standing_services import declare_standing

declaration = declare_standing(
    organization=guild,
    target_persona=member,
    declared_by_persona=leader,
    direction=StandingDirection.FAVOR,  # or DISFAVOR
    citation="For tireless service to the guild.",
)
```

Gates, in order:

1. **Rank** — the declaring persona's active membership rank must carry
   `can_declare_standing`; else `NotAuthorizedToDeclareStandingError`.
2. **Target validity** — the target must be able to hold organization reputation at
   all (`is_established_or_primary`); else `InvalidStandingTargetError`.
3. **Consent (DISFAVOR only)** — DISFAVOR is antagonism and routes through the
   #2170 antagonism-consent seam: the target's `hostile` `SocialConsentCategory`
   rule must admit the declaring persona (`world.consent.services
   .consent_blocks_targeting`) — the same category
   `world.secrets.services.accusation_permitted` consults for the frame-job
   denounce gate, reused rather than minting a new category. FAVOR is pure
   benefit and skips this gate entirely. Refusal: `StandingConsentBlockedError`.
4. **Rate limit** — at most one declaration per (organization, target_persona) per
   IC `GameWeek` (`world.game_clock.week_services.get_current_game_week`); else
   `StandingRateLimitedError`.

The delta itself is a PLACEHOLDER magnitude (`STANDING_DECLARATION_FAVOR_DELTA` /
`STANDING_DECLARATION_DISFAVOR_DELTA`, `constants.py`) applied through the existing
`bump_organization_reputation` — `declare_standing` never writes
`OrganizationReputation` directly. `StandingDeclaration.delta_applied` records the
actual clamped move (old value → new value), which can be less than the nominal
delta near the ±1000 ceiling/floor.

**Action + telnet:** `declare_standing_action` (key `declare_standing`) takes
`target`, `organization_id`, `direction`, `citation` kwargs; `CmdOrg` gains
`org favor <person> in <organization>=<citation>` / `org disfavor <person> in
<organization>=<citation>` subverbs routing through the same dispatcher every
other `org` subverb uses.

**Web:** the OrgPage Standing Declarations panel (`frontend/src/orgs/pages
/OrgPage.tsx`) lists the org's public declaration history and, for a viewer whose
own membership in that org carries `can_declare_standing`, offers a
`DeclareStandingDialog` (`frontend/src/orgs/components/DeclareStandingDialog.tsx`)
that dispatches through the generic `POST /api/actions/characters/{id}/dispatch/`
seam (registry key `declare_standing`) — the same path `PersonaContextMenu`'s
Challenge/Identify menu items use for a registry action with no `ActionTemplate`.

### DRF endpoints

Read-only endpoints under `/api/societies/`:

| Endpoint | Viewset | Purpose |
|----------|---------|---------|
| `/organizations/` | `OrganizationViewSet` | Organizations the requester belongs to (staff see all); `?name=` filters iexact (family-org resolve) |
| `/memberships/` | `OrganizationMembershipViewSet` | Current memberships, excluding covenants |
| `/ranks/` | `OrganizationRankViewSet` | Rank ladders for visible organizations |
| `/offers/` | `OrganizationMembershipOfferViewSet` | Offers owned/received/org-visible to the requester; `respond` detail action (#3412) — `POST /offers/{id}/respond/` with `{"response": "accept"\|"decline"}` dispatches the `membership_services` accept/decline functions (INVITE → requester owns `to_persona`; APPLICATION → requester holds an invite-authorized membership; no staff bypass, matching telnet) and returns the updated offer |
| `/reputations/` | `OrganizationReputationViewSet` | The requester's active persona's org reputations (standing) — `{id, persona, organization, organization_name, tier}`, tier only, self-scoped (#1446) |
| `/standing-declarations/` | `StandingDeclarationViewSet` | Public favor/disfavor declaration history (#3290) — `{id, organization, organization_name, target_persona, target_persona_name, declared_by_persona, declared_by_persona_name, direction, citation, created_at}`; **public** (unlike `/reputations/`), no `delta_applied` (mirrors the reputation viewset's "tier only, never the raw value" convention); writes go through `declare_standing_action`, never a POST here |
| `/appeals/` | `OrgAppealViewSet` | Appeals to organizations (#3293) — list/retrieve is members + own appeals; `create` lodges, `signon`/`resolve`/`withdraw` detail actions dispatch through the matching Action |
| `/deeds/` | `DeedViewSet` (#3466) | Public read of every active `LegendEntry` — any authenticated player, including deeds belonging to a persona they don't play (legend is public, like proclamations); `honor` detail action — `POST /deeds/{id}/honor/` `{journal_title, journal_body}` amplifies this deed. Payload includes `ceiling`/`headroom` (against the anchoring event) and `can_honor` (eligibility preview scoped to the requester's own active persona) |
| `/events/` | `LegendEventViewSet` (#3466) | Public read of `LegendEvent` rows; `establish` detail action — `POST /events/{id}/establish/` `{honoree_persona, deed_title, journal_title, journal_body}` mints a fresh deed under that event. Both actions dispatch through `PerformRitualAction` against the seeded "Rite of Honors" ritual, never `honor_deed` directly — mirroring `world.magic.views.RitualPerformView`, so telnet and web converge on one action |

All covenant-backed organizations are excluded from the membership/rank/offer endpoints.

---

## Key Constraints

- Only personas with `persona.is_established_or_primary` (PRIMARY or ESTABLISHED) can:
  - Hold organization memberships
  - Have reputation with societies or organizations
- Temporary disguises are rejected via `clean()` validation on save
- `OrganizationMembership` has a unique constraint on `(organization, persona)`
- `SocietyReputation` has a unique constraint on `(persona, society)`
- `OrganizationReputation` has a unique constraint on `(persona, organization)`
- `StandingDeclaration` has a unique constraint on `(organization, target_persona, game_week)` (#3290 rate limit)

---

## Admin

All models registered with Django admin:

- `SocietyAdmin` - Principle fields grouped in fieldsets, `OrganizationInline` for child orgs
- `OrganizationTypeAdmin` - Rank title management
- `OrganizationAdmin` - Collapsible principle/rank overrides, `OrganizationMembershipInline`
- `OrganizationMembershipAdmin` - With effective title display
- `SocietyReputationAdmin` / `OrganizationReputationAdmin` - With tier display
- `StandingDeclarationAdmin` (#3290) - `delta_applied` visible for staff dispute resolution (the player-facing API omits it)
- `LegendEntryAdmin` - With total value, spread count, `LegendSpreadInline`
- `LegendSpreadAdmin` - With society reach tracking

## Neighborhood Turf (#2862, ADR-0185)

Who holds a crime neighborhood, and how firmly. `NeighborhoodTurf` is one row per
NEIGHBORHOOD-level `Area`: `controlling_org` + `grip` (0-100). `turf_services
.apply_turf_push(org, area, amount)` owns the arithmetic — uncontested ground is
claimed outright, the holder's own pushes deepen grip, a rival's erode it, and grip
breaking flips control to the pusher at a deliberately shallow `FLIP_START_GRIP`
(freshly taken ground is loose).

Control is consequential, which is what makes turf worth fighting for:

- **Guard pressure** — grip writes an area-wide `StatKey.CRIME` cascade modifier
  (`_sync_crime_modifier`), and `justice.pipeline.maybe_guard_encounter` scales its
  trigger chance by it (via `locations.services.area_stat_total`). A tightly-held
  patch is a *busier* patch for everyone.
- **Revenue** — `CRIME_KICKUP` income streams on the area re-target to the
  controller (per-row saves; never a bulk `.update()`, which the identity map
  would not see).
- **Retaliation** — a push against held ground opens a `Gang Retaliation` THREAT
  crisis (CRIMINAL_ORG audience) against the *pusher*: pay tribute, run the
  "Hold the Corner" mission, or wait and bleed grip.

Gangs are ordinary `Organization` rows of the `gang` `OrganizationType`; an "NPC
gang" is simply one with no player members, not a separate model. Pushes are fed
by the GANG_TURF project machinery (`complete_gang_turf` tier completions ×
`TURF_PUSH_FACTOR`) and by turf missions' PROJECT reward lines. Surfaces:
`start_gang_turf` action, telnet `turf` / `turf push <crew>`. Seeded demo stage in
`world/seeds/underworld.py`.
