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
- **Domains** — `WorshippedBeing.domains`, plain prose naming the spheres a being holds
  ("Carnage, wanton bloodshed, feral battle"). Deliberately NOT a lookup table (#3776):
  overlap between gods is expected and nothing matches on it mechanically, so a
  vocabulary would only add an authoring gate. _Avoid_: portfolio, sphere table.
- **Being facet** — a favored aesthetic facet of a being (`BeingFacet`, #3776), drawn from
  the SAME flat `magic.Facet` pool characters bind through `Motif` — there is no separate
  divine vocabulary (ADR-0289). Double-dipping is the point: a character's own bound facet
  and their patron's favored facet being the same row is what the Chosen overlap bonus
  reads. No cap, no policing. _Avoid_: divine facet, god motif.
- **Being resonance** — a resonance a being favors or is merely associated with
  (`BeingResonance`, #3776): `resonance` + `tier` (`BeingResonanceTier`
  FAVORED/ASSOCIATED). FAVORED acts pay double, ASSOCIATED the ordinary rate — the model
  for "different kinds of worshipper" serving one god. No cap. _Avoid_: `CharacterResonance`
  for beings (that's the per-character currency).
- **Tarot cards** — `WorshippedBeing.tarot_cards`, the cards people BELIEVE represent a
  being (#3776). Pure association, no cap, no claim of canon. Read by birth favor (below);
  distinct from a character's own single `tarot_card`. _Avoid_: the being's card (there may
  be several, and belief is not fact).
- **Being codex entry** — `WorshippedBeing.codex_entry`, the being's own Codex page,
  following the `Gift`/`Technique`/`HouseAspectOption` precedent (#3776). Visibility
  (public / known-to-some / researchable) is read ENTIRELY through the linked entry's
  `is_public` tier — `WorshippedBeing` deliberately carries no visibility field of its own.
  PROTECT, so deleting a page that a god points at is refused rather than silent.
- **Being nickname** — an alternate name a being's worshippers use (`BeingNickname`,
  #3776); a being may carry several. No reverent/irreverent field — tone is prose, not
  data. `societies.Organization.patron_nickname` points at one of these, never
  directly at the `WorshippedBeing`, so different organizations can name the same god
  differently in their own records.
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
- **Being relationship** — a public relationship fact between two gods
  (`BeingRelationship`, #3776): `being_a`/`being_b` + `valence`
  (`BeingRelationshipValence`: ALLY/RIVAL/FEUD/UNKNOWN) + `public_story`. Deliberately
  NO hidden-truth field — a real hidden truth (why two beings actually feud) is a
  separately-authored, separately-gated `CodexEntry` reached through a `Clue`, never a
  maybe-secret field here, because even a hidden/blank field on a public row would leak
  presence/absence of a mystery. `being_a`/`being_b` are undirected (ALLY of X reads the
  same as ALLY of Y) and get sorted into canonical pk order automatically, so the same
  pair can never be recorded twice with the sides swapped.
- **Rite kind** — a pantheon-wide kind of rite (`RiteKind`, #3777): a name and a
  **rite tier** (`RiteTier` 1 Devotional / 2 Demanding / 3 Perilous). The tier is the
  only mechanical fact: 1 AP per tier, the award row, and at tier 3 that the rite is
  a Ceremony. _Avoid_: "ritual" (that is `magic.Ritual`, an unrelated mechanic).
- **Worship rite** — a being's own instantiation of a rite kind (`WorshipRite`): its
  flavor text, the check it rolls, and which of the being's own resonances it
  channels. Performed as a scene act at tiers 1 and 2 (`perform_worship_rite`), as
  a RITE ceremony at tier 3. _Avoid_: "rite" for the ceremony Rites skill roll.
- **Tier award** — the authored payout per (rite tier, check outcome)
  (`WorshipRiteTierAward`): resonance and favor. Every pair is seeded; a missing
  row raises rather than paying 0.
- **Rite performance** — one performance of a rite by one character
  (`WorshipRitePerformance`): the audit row, the resonance ledger's WORSHIP_RITE
  source, and the weekly favor cap (favor from a given rite lands once per game
  week per character; resonance is never capped).
- **Relic** — a specific sacred item of a being (`Relic`, #3777): one named
  `ItemInstance`, never an archetype. Distinct from a **favored offering**, any
  sacrificed item whose facet the being favors (credited at the config multiplier).
  _Avoid_: "artifact".
- **Shrine** — a room-level place of worship (`ShrineDetails`, #3778): a SHRINE
  `RoomFeatureInstance` plus its sidecar (being, founder, consecration points). Founded
  by the room's holder, dissolved by them; the small, personal case (a house shrine).
  _Avoid_: "altar" as a model term, "temple" for a single room.
- **Temple** — a building-level place of worship (`TempleDedication`, #3778): one active
  dedication per `Building`, every room under it sanctified, one shared consecration
  total. Dedicated by whoever holds the building. Not a room feature. _Avoid_: "church",
  "cathedral" as model terms (a cathedral is a temple with a shrine at its altar).
- **Consecration** — a site's accumulated worship (`consecration_points`, #3778): grows
  by the tier of each rite of the site's own being performed there, and reads through the
  authored `ConsecrationTier` ladder as a bonus percent on that being's rite awards.
  Shrine and temple bonuses add. A plain counter, not resonance. _Avoid_: "sanctity",
  "holiness" as field names.
- **Holding a place** — the founding gate for a site (`SiteNotHeld`, #3778): a room's
  `effective_owner` persona for a shrine; a building's credited `owner_persona`, the holder
  of its area, or that holder's org leader for a temple. Never a payment.
- **Prayer** — a character's freeform words to a being (`Prayer`, #3779): a plain log
  with no effect of its own, read by staff. Mechanically meaningful only through the
  conditions recorded on it: the **holy-site prayer** (the first per game week at a shrine
  or temple of the being pays a little devotion) and **dire straits** (Soulfray active or
  near death; the NEAR_DEATH intervention check runs for the god prayed to). _Avoid_:
  "prayer" for the Rites skill or the Prayer TechniqueStyle (both older uses); "petition".
- **Vision** — a GM-sent vision (`Vision`, #3779): prose a being sends one character,
  first-class and standalone, delivered as a VISIONS narrative message in the one
  treatment reserved for visions. `reveal_source` decides whether the recipient learns
  the being. May answer a prayer, hand over a Codex clue, or belong to an episode; usually
  none of these. Never automatic, never player-triggered. _Avoid_: "dream" (the dreams app
  is the sleep realm), "omen", "vision_text" (an Audere Majora threshold's own field).
- **Dire straits** — the danger a god might answer (`DireStraitsKind`, #3779): Soulfray
  active (read through the safety checkpoint's `get_soulfray_warning`) or health at or
  below the knockout band while alive. Near death outranks Soulfray on the record.
- **Feast day** — a being's annually-recurring worship holiday (`WorshipFeastDay`,
  #3776): `ic_month`/`ic_day`, no year, unique per being+date. Its own model rather
  than reusing `weather.FeastDay` — a religious concept shouldn't be owned by the
  weather app. Feeds a future universal worship-rite reward multiplier (#3777) for
  anyone worshipping the being that day — distinct from birth favor below, which is
  per-character, not per-date.
- **Birth favor** — `is_birth_favored_by(sheet, being, *, today)` (#3776): True only
  when the character's own `tarot_card` matches one of the being's `tarot_cards` AND
  `today` is the character's `birthday_month`/`birthday_day`. Doubles a worship-rite
  payout for that being (#3777); it does not itself grant anything. `today` defaults
  to the current IC date (`game_clock.get_ic_now()`), matching how the Town Crier
  birthday feed already reads the same two fields — never the real wall clock.
- **God's Favorite** — the achievement for reaching (or tying) a being's top devotion;
  three gendered rows (Princess/Prince/Chosen); never names the being.
- **Miracle** — an authored effect a WorshippedBeing can perform by spending its
  `resonance_pool` (#2360). Miracles fire automatically when a high-devotion PC is
  incapacitated. Authored as payload rows (conditions, capabilities, damage profiles)
  reusing the `Abstract*` bases. _Avoid_: "prayer" (the mundane skill is Rites; a
  TechniqueStyle named Prayer exists).
- **Divine Intervention** — the automatic firing of a Miracle when a PC with
  `DevotionStanding.favor` above the config threshold is incapacitated (#2360), or
  prays in dire straits (#3779, the NEAR_DEATH trigger, narrowed to the god prayed to).
  The god decides — no player prompt. Per-character cooldown via a timed condition.
  Trigger installed on the character's ObjectDB when `bump_devotion` pushes favor past
  the threshold; removed when it drops below.
- **Faith Variant** — an `AudereMajoraFaithVariant` — per-being ceremony override for
  Audere Majora crossings (#2360). When a crossing character has high devotion, the
  variant overrides vision/manifestation text and grants a mechanical bonus
  (condition payload). Pool spent at crossing time, not offer creation — a declined
  offer costs nothing.
