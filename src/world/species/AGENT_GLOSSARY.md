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
- **Species lineage** — `Species.lineage`: the species followed by every
  ancestor via `parent`, nearest first. What `codex_entries` walks so a
  subspecies character is granted the umbrella entry too (#2880). Still
  taxonomy, not a character's ancestry. _Avoid:_ "ancestry", "family tree"
  (those are the roster kinship graph).
- **Required trait** — `SpeciesFormTrait.is_required=True`: a species
  identity marker (horns + tail for Infernals, wings for Daeva, fangs
  for vampires) that CG must fill. ("True Infernal" is a retired term and the
  species row was deleted in #2880 — the mainline is plain `Infernal`.) Species identity is protected by required
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
- **Language** — a catalog `Language` row backed 1:1 by a `TraitType.LANGUAGE`
  `Trait` (#2993/ADR-0214). The trait link, not a bespoke model, is what makes
  a tongue trainable/gradable — per-character fluency is an ordinary
  `CharacterTraitValue` on that trait. _Avoid:_ `CharacterLanguage` (rejected
  alternative, ADR-0214).
- **Fluency** — the 1-100 `CharacterTraitValue` on a `Language`'s trait,
  banded by `language_constants.fluency_band`: broken (1-29), conversational
  (30-69), fluent (70+). `FLUENT_GRANT_VALUE=70` is what CG/universal grants
  set. Trained like any other trait via `TrainLanguageAction`'s weekly
  teacher/self-study DP sessions; LANGUAGE-typed traits are rust-exempt.
- **Garble** — the per-observer comprehension rendering of speech in a
  language the listener doesn't fully know: `language_services.garble_text`
  keeps a fraction of words (`BAND_KEEP_RATIO` by `min(speaker_band,
  listener_band)`), deterministically seeded on `language_id:text`
  (`speech_seed`) so live delivery, WS push, and every later scene-log read
  agree — and a character who later learns the language can reread old logs
  in the clear (ADR-0214's deliberate divergence from ADR-0170 snapshotting).
  _Avoid:_ persisting a garbled render (comprehension is always recomputed,
  never stored).
- **Universal language** — a `Language` with `is_universal=True` (e.g. Arvani
  Common): granted to every character at CG finalize
  (`provision_starting_languages`) regardless of species or `Beginnings`, a
  content flag rather than a hardcoded name lookup.
- **Restricted language** — a `Language` with `restricted=True` (#3162):
  gameplay-gated, cannot be self-studied from zero fluency
  (`TrainLanguageAction` hard-blocks self-study below fluency 1), but a
  co-present FLUENT teacher can still teach it from zero — first entry always
  comes from a GM grant/`Distinction`/story hook, then spreads
  person-to-person via teacher training. Species/`Beginnings` attachment and
  `is_universal` grants bypass the flag entirely (CG-time grants are never
  gated). _Avoid:_ conflating with `is_universal` — the two flags are
  orthogonal (a language can be neither, either, or in principle both,
  though a universal+restricted combination has no current content use).
