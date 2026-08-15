# Worship glossary

- **Worshipped Being** — a god, spirit, totem, or dark power authorable as data
  (`WorshippedBeing`); holds a vast worship pool; almost never played (ADR-0132).
  _Avoid_: deity model, god NPC.
- **Tradition** — a style of worship (`WorshipTradition`) binding beings to the Rites
  specialization their ceremonies roll with. PLACEHOLDER names: Church Liturgy,
  Spiritcalling, Druidry, Occultism.
- **Rites** — the mundane ceremonial skill (open to every path; Path of the Chosen's
  edge is aspect-based). _Avoid_: "Prayer" for the skill — Prayer is the magic
  TechniqueStyle gated to Path of the Chosen.
- **Worship pool** — `WorshippedBeing.resonance_pool`, the spendable accumulated
  worship miracles (#2360) draw on via `spend_worship_pool`. _Avoid_:
  CharacterResonance for beings.
- **Devotion standing** — the one-way PC→god favor record (`DevotionStanding`).
  _Avoid_: CharacterRelationship for sheetless gods.
- **Worship declaration** — a character's public being + optional secret being
  (`WorshipDeclaration`); the secret side mints a Secret at CG finalization.
- **Heart vs lip service** — `WorshipDeclaration.public_is_sincere` (#2361): whether a
  character genuinely believes their PUBLIC declaration (True) or it is performative
  only (False). A player choice made explicitly at conversion; PRIVATE — never leaves
  owner/staff surfaces (same leak-table pattern as `current_mood`). Defaults True for
  CG declarations, where public and inward faith are the same thing by construction.
  _Avoid_: confusing this with `secret_being` — that's a wholly separate, second faith
  kept hidden; sincerity is about whether the PUBLIC faith is real.
- **Public conversion** — repointing `WorshipDeclaration.public_being` post-CG, via a
  Conversion ceremony (`world.ceremonies` glossary). Old `DevotionStanding` favor and
  the old secret faith's `Secret` row are left standing as history — conversion never
  deletes or mutates either.
- **God's Favorite** — the achievement for reaching (or tying) a being's top devotion;
  three gendered rows (Princess/Prince/Chosen); never names the being.
- **Miracle** — an authored effect a WorshippedBeing can perform by spending its
  `resonance_pool` (#2360). Miracles fire automatically when a high-devotion PC is
  incapacitated. Authored as payload rows (conditions, capabilities, damage profiles)
  reusing the `Abstract*` bases. _Avoid_: "prayer" (the mundane skill is Rites; a
  TechniqueStyle named Prayer exists).
- **Divine Intervention** — the automatic firing of a Miracle when a PC with
  `DevotionStanding.favor` above the config threshold is incapacitated (#2360). The
  god decides — no player prompt. Per-character cooldown via a timed condition.
  Trigger installed on the character's ObjectDB when `bump_devotion` pushes favor past
  the threshold; removed when it drops below.
- **Faith Variant** — an `AudereMajoraFaithVariant` — per-being ceremony override for
  Audere Majora crossings (#2360). When a crossing character has high devotion, the
  variant overrides vision/manifestation text and grants a mechanical bonus
  (condition payload). Pool spent at crossing time, not offer creation — a declined
  offer costs nothing.
