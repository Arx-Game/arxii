# Pacts with beings (`world/pacts`, #4341)

A **being pact** is a standing bargain a character strikes with a god, demon, spirit or the
dead of a line, who becomes her patron. A being offers it on one of its pledges; she accepts it
at that pledge's closing rite. From then on she owes the being favor every period. Meeting it
keeps the pact's everyday benefit; falling short worsens a staged condition she carries, and
the condition's last stage ends the pact in breach. She can also renounce it. Either way the
condition's cost eases out over the following periods.

Pacts are a family: the **Court Pact** (a servant's fealty to a Court, `covenants`), the
**Marriage Pact** (two houses through a union, `societies/houses`) and the **Org Pact** (two
organizations) already exist. The being pact is a sibling of the Marriage Pact's commitments,
not a generalization of them (spec section 7): a marriage commitment fires at signing and a
breach costs a house prestige, while a being pact commitment is graded every period and moves
a staged condition.

`world/pacts` is its own sub-package because it points into worship, conditions, checks and
projects, and none of them import it (FK direction, ADR-0010). The one FK the other way,
`Pledge.pact_offer`, is a string reference.

Spec and rulings: GitHub issue #4341 (sections 6 and 7). Decision record: ADR-4341
(patron-scoped modifiers), which ships with this issue so a pact patronage never receives the
Chosen bonuses.

## Models (`world/pacts/models.py`)

- `PactOffer` (`CreditedContent`) - a being's authored offer. `being` FK `WorshippedBeing`
  (nullable column, but a check constraint `pact_offer_has_one_party` requires it today; the
  follower pacts issue adds a second party column and widens the check), `name` (unique per
  being), `offer_text` (shown on the pledge), `closing_text` (shown to the holder on breach),
  `onlooker_line` (shown to the room when the pact ends, by breach or renouncing; blank shows
  nothing), `period_weeks` (game weeks per period, default 2), `condition` FK `ConditionTemplate` (PROTECT; `clean()` requires
  a progressing condition with at least `MIN_PACT_CONDITION_STAGES` = 2 severity-threshold
  stages), `severity_per_miss` (severity a wholly missed period adds, default 10), `is_active`.
- `PactOfferCommitment` - one thing every holder of the offer owes. `offer` FK, `kind`
  (`CharacterPactCommitmentKind`), `owed_by_holder` (must be True for now; `clean()` refuses
  False), `amount` (favor per period for FAVOR_EARNED, must be above 0), `notes` (the promise
  for CUSTOM, required). Commitments live on the offer because every holder owes the same
  thing.
- `CharacterPact` - a character's signed pact. `character_sheet` FK (the holder),
  `offer` FK (PROTECT), `devotion_standing` FK `DevotionStanding` (her standing with the being;
  check `character_pact_has_one_party` requires it today), `condition_instance` FK
  `ConditionInstance` (SET_NULL; empty once the condition has eased away), `signed_at`,
  `dissolved_at` (empty = active), `dissolution_reason` (`CharacterPactEnding`). Constraints:
  `unique_active_pact_per_standing` (one active pact per standing) and
  `character_pact_reason_iff_dissolved`. `is_active` property. A dissolved pact keeps its row as
  the record.
- `PactPeriodDetails` - the sidecar of one `PACT_PERIOD` project: `project` O2O, `pact` FK,
  `commitment` FK (null = an **ease-out period** opened after the pact ended), and the grading,
  written once: `resist_outcome` FK `CheckOutcome` (when a resist roll was needed),
  `severity_change` (signed; null = not graded yet), `stage_after` FK `ConditionStage`. The
  project and this row are the receipt that makes each period's check run once.
- `PactCredit` - one favor credit toward a period, by source (the "Deeds +4, rite +2" lines on
  the pact card). `period` FK, `source` (`PledgeCreditSource`), `credited`, `base` (what the write
  takes from the weekly deed cap, counted once: 0 when its `PledgeCredit` already counts it, and
  0 on every period's row but the first when one write credits several periods), `game_week`.
  Mirrors `PledgeCredit`; the counter itself is the period project's `current_progress`.

Also added outside the sub-package:

- `Pledge.pact_offer` FK `PactOffer` (null, SET_NULL; `Pledge.clean()` requires the offer to be
  the pledge's own being's).
- `ProjectKind.PACT_PERIOD` (`world/projects/constants.py`), run as `CompletionMode.TIERED_PERIOD`.
  `world/pacts/apps.py ready()` registers its kind handler (`grade_pact_period`) and tiered
  resolver (`resolve_pact_period`); `world/apps.py` calls it after worship's.

**Constants** (`world/pacts/constants.py`): `CharacterPactCommitmentKind` (FAVOR_EARNED: graded
every period against the favor earned with the being; CUSTOM: a recorded promise, shown and never
checked) and `CharacterPactEnding` (BREACH, RENOUNCED, PARTY_ENDED; nothing writes PARTY_ENDED
yet).

**Exceptions** (`world/pacts/exceptions.py`): `PactError` (base, carries a player-safe
`user_message`), `PactAlreadyHeld`, `PactOfferUnavailable`, `NoActivePact`.

**Types** (`world/pacts/types.py`): `PactStageLine`, `PactSourceLine`, `PeriodGrade`,
`PactCommitmentLine`, `PactOfferSummary`, `PactCard`.

## Services (`world/pacts/services.py`)

### Reading

- `active_pact_with(sheet, being) -> CharacterPact | None`.
- `pact_offer_summary(offer) -> PactOfferSummary` - the offer as the pledge card shows it: the
  being, text, commitments, favor per period, promises, the condition's effects and its stages
  (the last stage flagged).
- `offered_pact_summary(pledge) -> PactOfferSummary | None` - the pact a pledge offers while the
  offer stands. Read by `PledgeSerializer.pact_offer`.
- `carded_pacts() -> QuerySet[CharacterPact]` - every pact a card shows, newest first: active
  pacts and ended pacts still easing out.
- `pact_card(pact) -> PactCard` and `pact_cards_for(sheet) -> list[PactCard]` - the open period's
  favor against its requirement and time limit, its favor by source, the condition's stage,
  severity and next threshold, the promises, and whether the being is her secret faith.
- `pact_beings_for(sheet)` - beings whose active pact with her has an open commitment period
  (deeds credit them). A pact with no FAVOR_EARNED commitment earns no deed favor: there is no
  `PactCredit` for the weekly cap to count.
- `pact_deed_favor_this_week(sheet)` - base deed favor her pact credits took from this week's
  deed cap; `pledge_services` adds it to the pledge credits' base, so the cap counts each deed
  once.

### Signing

`sign_being_pact(sheet, offer) -> CharacterPact`. Refuses with `PactOfferUnavailable` when the
offer or its being is inactive, and with `PactAlreadyHeld` when she already holds an active pact
with the being. In one transaction it:

1. gets or creates her `DevotionStanding` with the being. A standing with no valence becomes a
   `PACT` patronage (`established_at` set); a released one has `released_at` cleared; a Chosen's
   own standing keeps its valence (it stays Chosen);
2. puts the offer's condition on her at its first stage (`apply_condition`). A resolved instance
   left by an earlier pact is removed first; one still easing out from an ended pact with the
   same condition is kept at its severity and its ease-out chain is cancelled;
3. creates the `CharacterPact` and opens one period per FAVOR_EARNED commitment
   (`open_pact_period(pact, commitment)`: a `PACT_PERIOD` project of `period_weeks` game weeks
   with the commitment's amount as `threshold_target`).

The only caller is `close_pledge(..., accept_pact=True)` (see "Accepting at a pledge's close").

### Serving

`record_pact_credit(sheet, being, credited, source, *, base=0) -> list[PactCredit]`, called by
`bump_devotion` after `record_pledge_credit` for every positive favor write. It adds the credited
favor to every open commitment period of her active pact with the being and writes one
`PactCredit` each. A pledge's closing and lapse awards (`PledgeCreditSource.CLOSING` / `LAPSE`)
never count. Deeds reach a pact's being through `credit_pledge_deed`, which now credits the open
pledge's being and then each pact being, under the one weekly deed cap.

### The period check

At its time limit the lifecycle tick resolves a `PACT_PERIOD` project.
`resolve_pact_period(project)` picks the tier (met, or an ease-out period: Success; short:
Failure) and `resolve_project` runs `grade_pact_period(project, outcome_tier)` once. For a
commitment period of an active pact (`_grade_commitment_period`):

- **Met** (earned at least required): severity eases by `severity_per_miss * earned // required`,
  at most twice `severity_per_miss`, never below the first stage's threshold. No roll.
- **Short**: the rise is `ceil(severity_per_miss * shortfall / required)`. When the rise would
  reach the next worse stage and that stage has a resist check, the check rolls first
  (`perform_check_with_modifiers`) at the stage's `resist_difficulty` minus the favor band's ease
  (`invocation_services.favor_ease_for`: the `DevotionConfig` low and high bands). A Botch is
  lifted to Failure (`sacrifice_services.lift_botch`), so a niche cannot backfire. The tier sets
  the move:

  | Resist tier | Severity added |
  |---|---|
  | Critical Success | nothing |
  | Success | up to one below the worse stage's threshold; the stage holds |
  | Partial Success | half the rise, rounded up |
  | Failure (or Botch) | the full rise |

  A short period that stays inside the current stage needs no roll, and a worse stage with no
  resist check authored takes the full rise unrolled. Only the next worse stage rolls.
- The handler calls `advance_condition_severity` (or `decay_condition_severity`) with that
  amount, records it on the `PactPeriodDetails`, sends the holder one system narrative message
  (nobody else), and opens the next period. Pact conditions should use ADVANCE_AT_THRESHOLD
  stages so the condition system does not roll a second time; the builder warns on
  HOLD_OVERFLOW.

A commitment period left open on an ended pact is recorded with no change.

### Breach

When grading moves the condition onto its last stage, the pact ends in breach (`_breach`):
dissolved with BREACH and its other open commitment periods cancelled; a `PACT` patronage is
released (`release_patronage`, its first caller); the stage's settle pool, if authored, fires
against the holder only, at the failed resist roll's tier (a breach reached with no roll fires
no pool); the holder sees the offer's `closing_text` and the ending lines; the room sees the
`onlooker_line` if one is written; an ease-out period opens. Codex entries and clues she gained
are kept; nothing is deleted. Every holder line and room line from grading (met, short, breach,
ease-out) is sent with `transaction.on_commit`: grading runs inside the project tick's atomic
block, and a rollback there must not leave her holding a roll result the next tick rolls again.

### Renouncing

`renounce_pact(sheet, being) -> RenouncedPact` ends her active pact with RENOUNCED, cancels its
open commitment periods, releases a `PACT` patronage the same way, sends the room the offer's
`onlooker_line` on commit and opens an ease-out period. It returns the pact and the one message
she is told (the action delivers it; the service sends her nothing, so she reads it once).
Raises `NoActivePact` when she holds none.

### Release rule (D5)

Only a `PACT`-valence standing is released when a pact ends (`_release_if_pact`). A Chosen whose
own patron added a pact keeps her Chosen patronage when the pact ends: the pact row ends, and the
Chosen bond follows its own character-creation lifecycle.

### Ease-out

After any ending the condition eases by `severity_per_miss` each period until it is gone (owner
ruling 2026-10-18). An ease-out period is a `PACT_PERIOD` project whose `PactPeriodDetails` has
no commitment; `_grade_ease_out_period` decays the condition and opens the next one, or at zero
removes the condition and opens nothing more.

## Accepting at a pledge's close

`close_pledge(sheet, *, scene, offered_items=(), accept_pact=False)`
(`worship/pledge_services.py`). When she chose to accept, the pledge resolved, it carries a
`pact_offer` and the rite resolved it at Success or better, `sign_being_pact` runs in its own
transaction after the pledge's resolution commits, so a refused signing never undoes the close.
`ClosingOutcome.pact` is the new pact, or `ClosingOutcome.pact_refusal` carries the reason
(`MSG_NO_PACT_OFFERED`, `MSG_PACT_NEEDS_SUCCESS`, or the `PactError` message). Any other result,
or closing without accepting, leaves no pact and nothing pending; the pledge can be taken again.
The pledge pays its award and its answer either way.

## Interfaces

- **API**: `GET /api/pacts/cards/` (`PactCardViewSet`, read-only, paginated, filter
  `character_sheet`): the owner's own characters' pact cards, staff anyone's. The pledge list
  (`/api/worship/pledges/`) and pledge cards carry `pact_offer` (`PactOfferSummarySerializer`,
  null when none).
- **Actions**: `pact_renounce` (`RenouncePactAction`, `actions/definitions/pacts.py`; kwargs
  `being_id` or `being_name`, resolved only among her own carded pacts; every refusal reads "You
  hold no pact with that being." and names nothing); `pledge_close` (`ClosePledgeAction`) takes `accept_pact` (True or
  `"true"`) and returns `pact_signed` in its data.
- **Telnet**: `pact` (no args or `pact list`) shows the caller's being pact cards first, then the
  existing organization pacts; `pact/renounce <being>` (any other switch refuses with the usage
  line); `pledge/close/accept[=<item>,...]`
  closes the pledge and accepts its pact (`commands/pacts.py`, `commands/worship.py`).
- **Web**: `PactCard` (`frontend/src/worship/components/PactCard.tsx`) in the sheet's
  `WorshipSection`; the pledge card shows the offer and the close dialog offers "close and
  accept the pact".
- **Admin**: `PactOfferAdmin` (commitments inline), `CharacterPactAdmin`,
  `PactPeriodDetailsAdmin` (credits inline). The **Being Service builder**
  (`web/admin/being_service/`, `/admin/_being_service/<being>/`) has a Pacts section: the offer
  form with its commitments, and beside each saved offer (`live.pact_offer_context`) the
  commitment's share of a period's deed cap (`pact_demand`, warnings below a quarter and above
  two thirds), the condition's stages with their resist checks, a warning when
  `severity_per_miss` differs from the stage spacing or a stage uses HOLD_OVERFLOW, holders by
  stage, holders short last period, and the pledges that offer it. The pledge form gains
  "Pact offered at the close" with a read-only brief of the chosen offer
  (`live.pact_offer_brief`). The condition itself is authored in the condition admin.

Journeys: `integration_tests/test_pacts_with_beings_journeys.py`,
`test_pact_card_journeys.py`, `test_manifest_picker_journeys.py`.

## Reach of a pact

- A pact patronage is an active patronage: `active_patronage_for` / `active_patronage_of`
  include it, so the being's bond ultimates are listed at Audere while the pact holds (ADR-4098,
  unchanged) and the technique picker accepts the being as an option.
- It is not a Chosen patronage: `chosen_patronage_of` excludes `PACT`, so a pact holder gets no
  Chosen earning bonus, invocation ease or anima recovery (ADR-4341; see `worship.md`).
- Its condition, effects and settle pool touch only the holder. A secret faith's pact card is
  hers alone.

## The technique picker (#4341)

Built in this issue so a pact's being can be brought into a fight. A player chooses which bound
being or companion each manifesting technique brings: `world/magic/services/manifestation.py`
(`manifest_choices_for`, `set_character_manifestation`), action `manifest_set`, telnet
`manifest` / `manifest <technique>=<option>`, `GET /api/magic/manifest-choices/?character_sheet=`
and the Spellbook's `ManifestPickerPanel`. See `magic.md` "Manifesting a bound entity".

## Extension points (not built)

- **Commitments that trigger on their own** (#4440): `ConditionTemplate.reactive_triggers`
  installs flow triggers on the bearer, and `Trigger.source_stage` keeps one active at one stage
  only. A "never do X" commitment would move the condition through the same grading.
- **Options in certain situations**: `VowSituationalPerk` fires today only from a
  `covenant_role`; a second nullable source (`ConditionStage`) would let a pact stage carry
  perks.
- **More commitment kinds**: new `CharacterPactCommitmentKind` values, each with its grading
  handler. A kind owed by the other party arrives with follower pacts.
- **Per-holder commitments**: if later pacts are negotiated per holder, per-pact rows copy from
  the offer at signing, the way `BetrothalTerm` rows become `PactCommitment` rows at a wedding.
- **Another route to an offer**: a mission or answer could sign one through an `EffectType`
  calling `sign_being_pact`. None exists.

Not built, each its own issue: follower pacts with NPCs who serve her (#4437), spirit companions
for a character aided by the spirits of the dead (#4438), a being leading a Court (#4439; the
guard against a being leader stays), and commitments that trigger on their own (#4440).
