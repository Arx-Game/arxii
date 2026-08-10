# Predator Ecology (#3093, ADR-0211)

Named NPC antagonists that make the deterrence spine (#3091) bite, on a
deliberately slow escalation ladder, plus deterrence-blind Afflictions.

## Models (`world/predators/`)

- **`PredatorKind`** — authored vocabulary (bandit company, pirate fleet,
  raider warband): base strength + optional per-stage pacing override.
- **`PredatorBand`** — the antagonist: kind, `home_region` (Area; reach +
  regional-peace scope), `strength` (burned by counterplay; dormancy below
  `DORMANCY_FLOOR`, disband at zero), `loot_stash`, `prey` (Organization),
  `stage` (`MenaceStage`), `weeks_unanswered`, `dormant_until`, `disbanded_at`.
  Deliberately NOT an Organization (ADR-0211).
- **`MenaceEvent`** — one step of the band's story; the tidings source.
- **`AfflictionSign`** — the week of dread before an outbreak converts.

## The menace ladder (`world/predators/services.py`)

`MenaceStage`: RUMORS → LAWLESSNESS → ROBBERY → RAIDS → TERROR, with
`STAGE_WEEKS` pacing (~10 weekly crons rumor→raid, Apostate's ruling).
`weekly_menace_tick` (game_clock processor, after stature, before crisis
generation): spawn rolls per unmenaced realm, prey selection
(`select_prey` — weakest PERCEIVED landed org in reach, honoring
consort-derived regional peace via `has_regional_peace`), stage effects
(LAWLESSNESS: weekly unrest tick; ROBBERY: `ROBBERY_SKIM_PCT` off
uncollected income pools into the stash; RAIDS/TERROR: one open attributed
`DomainCrisis` — origin `PREDATOR`, `aggressor_band` set, no covert window,
severity by stage), and advancement only when `weeks_unanswered` clears the
stage's bar. `strike_band` is the counterplay seam: burns strength, knocks
the ladder down, resets the clock; called by `resolve_crisis` when an
attributed raid is answered (mission/task/pay), and by the
`sabotage_predator` spy payout. `sabotage_band` is the smaller-knife variant.

## Afflictions

`DomainCrisisType.ignores_stature` marks Affliction-class types: their spawn
path (`weekly_affliction_tick`) never reads stature bands. Every outbreak is
announced by an `AfflictionSign` a week ahead; unresolved outbreaks with
`affliction_spreads` roll a weekly one-hop spread to a same-realm domain,
capped at `AFFLICTION_SPREAD_MAX` per root (`DomainCrisis.spread_count`).

## Espionage

`TaskTargetKind.PREDATOR` + `OrgTask.target_band`; route payouts
`scout_predator` (stage/strength/lair/prey report) and `sabotage_predator`
(`world/tasking/spy_payouts.py`).

## Tidings

`FeedItemKind.MENACE`: every `MenaceEvent` (ladder steps both directions)
and every looming `AfflictionSign` is public news — the slow build-up is the
point, so the whole region watches it happen.

## Grand displays

`apply_grand_display(org, quality)` (stature side): an event whose PROVISION
quality clears the bar pushes the host org's perceived stature toward/above
true, bounded by `STATURE_BLUFF_MAX_ELEVATION` — the upward half of the
bluffing game (whispers are the downward half). Seam: `complete_event`'s
catering-prestige hook.

## Seeds

Cluster `predators` (`world/seeds/predators.py`): kinds + Affliction crisis
types. Bands themselves spawn organically from the weekly tick.
