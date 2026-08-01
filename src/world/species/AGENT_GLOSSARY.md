# Species glossary

Domain-local vocabulary for `world.species`. Root terms live in
`AGENT_GLOSSARY_MAP.md`.

- **Species** — a playable kind (Human, Khati, Infernal, …) or a subspecies
  under a `parent` (Khati → Vulpi/Cani). The parent link is taxonomy for
  grants/palette inheritance, NOT ancestry of an individual character —
  ancestry is the roster kinship graph. _Avoid:_ race (legacy term).
- **Species palette** — the `forms.SpeciesFormTrait.allowed_options` set for
  a (species, trait) pair: which colors/variants that species can normally
  take in CG. Empty = all options. Palettes are broad with pointed
  per-species *exclusions* (an Infernal cannot natively have fair skin or
  light-blue eyes); wearing an excluded color is the visible tell of
  cross-line blood. _Avoid:_ "human-exclusive colors" (retired first-pass
  framing).
- **Required trait** — `SpeciesFormTrait.is_required=True`: a species
  identity marker (horns + tail for True Infernals, wings for Daeva, fangs
  for vampires) that CG must fill. Species identity is protected by required
  structural traits, never by rationing colors.
- **Chimeric species** — a unique authored `Species` row (with its own codex
  entry) for a true halfbreed, possible only when both parents are Grand+
  (level 16+). Authored per pairing by staff; never computed. _Avoid:_
  halfbreed flags or generic "Chimera" rows.
- **Parent Dominance / power band / heredity** — live in the roster glossary
  (`world/roster/AGENT_GLOSSARY.md`); the rules engine is
  `world.roster.services.heredity`. _Avoid:_ "crossing" for species mixing —
  crossings are the magic-progression thresholds (3/6/11/16/21).
- **Felt sun exposure** — the graded per-character/per-room sun number
  (`sun_exposure.felt_sun_exposure`, #2846/ADR-0179): base(phase × sky) −
  shade − clothing coverage − authored/resonance garment SUN − modifier
  magic, floored at 0. Only the sun ever feeds it. _Avoid:_ "sunlight
  exposure" for the number (that's the condition's name); boolean framings
  like "sheltered/exposed".
- **Sun sensitivity (bane / allergy)** — the tier mapping felt exposure onto
  condition severity, anchored on held `Bane: Sunlight` / `Allergy: Sunlight`
  Distinctions identified by the `sun-bane`/`sun-allergy` DistinctionTags
  (worst held tier wins; innate species stamp and voluntary CG pick resolve
  identically). Bane keeps a severity floor only real shadow clears. _Avoid:_
  species-probed sensitivity, name-string template probes.
- **Sun refuge** — the nearest room where *shade alone* zeroes exposure
  (`sun_refuge.find_sun_refuge`; non-public rooms win ties). The AFK guard
  auto-flees there after the second unanswered damage instance. _Avoid:_
  "safe room" (unscoped).
- **Appetite (blood / essence)** — the hunger anchor Distinctions
  (`appetite-blood`/`appetite-essence` tags, #2853/ADR-0182): holders never
  regen anima naturally; blood feeds by the bite, essence by touch/glamour.
  `Undeath: Shade` is the separate drain anchor (daily upkeep) so the
  half-living never pay it. _Avoid:_ species-probed hunger, "vampirism" as a
  mechanic name.
- **Glut** — decaying overfill from feeding past maximum (`CharacterAnima.glut`):
  spends first, grants sun mitigation to appetite holders, never satisfies
  upkeep floors or quiets Ravenous. _Avoid:_ treating glut as a bigger tank.
- **Ravenous** — the visible hunger condition; severity tracks depletion depth
  and drives feeding restraint checks. In the desc footer it folds into the
  single worst-wins depletion clause. _Avoid:_ separate per-condition hunger
  lines (spam).
- **Moon pull** — the felt instinct pressure on a moon-bound character
  (`moon_pull.felt_moon_pull`: illumination × sky exposure − radiant shade;
  NIGHT only). Only occlusion dampens it — clothing and modifier magic never
  enter an instinct read. _Avoid:_ "moon exposure" (it is not a damage ladder).
- **Moon-Bound** — the control-pressure anchor Distinction (`moon-bound` tag,
  #2845/ADR-0183): holders roll `moon_control` (willpower + composure) under a
  strong pull; failure forces the battle-form shift + shared Berserk. Lycans
  innately via "The Wolf's Fury" grant. _Avoid:_ species-probed lycanthropy.
- **Battle form** — a lycan's ALTERNATE `CharacterForm` + `FormCombatProfile`
  stat suite (`moon_provisioning.ensure_lycan_battle_form`, lazily provisioned);
  moon clarity scales the whole suite at shift time via `instance_value`, and
  Wolf's-Fury thread level feeds `tuning_value`. _Avoid:_ a bespoke
  transformation mechanic (it IS the forms alternate-self machinery).
- **Moonlit Unease** — the Cani umbrella's flavor-only alertness condition under
  the open night moon (`reconcile_cani_unease`). _Avoid:_ wolf-specific khati
  subspecies (umbrella families only, ruled 2026-07-31).
