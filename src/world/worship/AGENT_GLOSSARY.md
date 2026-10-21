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
- **Favor** — a character's standing with one being, `DevotionStanding.favor` (running total
  `lifetime_favor`). Read as standing (divine intervention, miracle thresholds, God's
  Favorite, Chosen anima recovery) and as the gate and ease of an invocation; never spent
  (ADR-4333-A). _Avoid_: confusing it with an organization's favor token
  (`FavorTokenDetails`, currency) or an organization membership's `favor`.
- **Invocation** — calling on a being's favor before a check (#4333): the system rolls an
  invocation check (`invoke_favor`) and its outcome tier sets the bonus
  (`FavorOutcomeAward` kind INVOCATION) on the check it was declared on. Needs favor above
  zero and a use left this game week (`DevotionConfig.invocations_per_week`; a failure
  counts). Recorded as a `FavorInvocation`, whose `player_line` is the player's one line of
  how it shows. _Avoid_: "boon" (the scenes social ask), "blessing" (reads as a condition),
  "prayer" (a message, not a mechanic).
- **Worn piece** — a piece a character has on that carries a facet a being favors
  (`BeingFacet`) and has meaning points (#4520): it eases that being's invocation check and
  raises the earning rate with it by its points times the facet's two rates, at most
  `worn_items_counted` of them, all ease within `invocation_meaning_ease_max`. A piece with no
  meaning counts for nothing, however it was paid for. _Avoid_: "equipment bonus" (the
  modifier walk is a separate mechanism).
- **Resonance fed** — a meaning signal: the resonance an item's facets fed its current holder,
  in a resonance the being lists, counted only alongside another signal (#4520).
- **Earning rate** — the percentage applied to all favor a character earns with one being
  (#4333): 100 + `ChosenFavorConfig.earn_bonus_percent` for an active patronage of it + the
  character's favor earning modifiers + what the worn pieces carrying a favored facet add
  (#4520). `bump_devotion` applies it to every positive amount.
- **Favor modifier** — a modifier against a target in the `favor_invocation` (difficulty
  points eased) or `favor_earning` (earning-rate points) category, scoped to one being by
  `ModifierTarget.target_being` or to every being (null). Any modifier source can grant one
  except facet, mantle and motif bonuses (#4333 slice 8). Read only by
  `favor_modifier_total`. _Avoid_: a being-to-distinction link table.
- **Pledge** — two things (#4333 slice 2). A *pledge type* is an authored `Pledge` row: a
  being's offer of service with a favor target, a span in game weeks and a closing rite (one of
  the being's own tier 1 or 2 rites). An *open pledge* is one character's: a `Project` of kind
  PLEDGE with a `PledgeDetails` sidecar; at most one per character. Authored for staff-owned
  beings on the Being Service builder. _Avoid_: vigil, vow (a covenant vow), quest.
- **Favor target** — the favor a character must earn with the being after opening a pledge,
  before it can be closed (`Pledge.favor_target`, the project's `threshold_target`). Progress
  is the favor itself, on `Project.current_progress`: every favor write for the being while
  the pledge is open adds to it. _Avoid_: marks, points (no second currency).
- **Deed** — an act in ordinary play that grants the character a resonance the pledged being
  holds as FAVORED or ASSOCIATED (`credit_pledge_deed`, called by `grant_resonance`); it earns
  favor only while a pledge to that being is open, under `DevotionConfig.weekly_deed_favor_cap`
  (base favor). A worship rite's own grant is not a deed, and neither is a passive grant (a
  residence or outfit trickle, a distinction grant, a staff grant): favor comes only from a
  character's actions.
- **Sacrifice** — an item given up to a being at its shrine or temple outside a ceremony
  (`sacrifice_items`): a check eased by the item's **meaning points** (what it means to the
  one giving it up), whose outcome tier selects the SACRIFICE `FavorOutcomeAward` that is the
  base favor; the item is soft-destroyed and keeps its design. An item with no meaning is
  given up for nothing, whatever it cost: no favor, pool grant or prestige reads a price.
  Recorded as a `CeremonyOffering` with `being` set and no ceremony, its roll, and one
  `OfferingSignal` per signal. _Avoid_: "offering" for this (an offering is made during a
  ceremony); "value" or "price" for what it earns by.
- **Meaning signal / meaning points** — one fact that makes an item matter to the character
  holding it, worth points; an item's points are the sum, read by `item_meaning`
  (`world/items/services/meaning.py`) from records, never from a price. 6a signals: carried,
  gift, heirloom, own work, made by a tie. See the items system doc.
- **Pledge credit** — one favor write credited to a pledge, with its calculation
  (`PledgeCredit`: base, earning rate, credited, and the deed, sacrifice or rite it was for).
  The audit trail behind the pledge card, not a counter (ADR-4362).
- **Closing rite / closing award** — performing the pledge's closing rite once its target is
  met closes it, paying the CLOSING `FavorOutcomeAward` for the rite's outcome in place of the
  rite's own award. A first Failure or Critical Failure leaves one retry (Ruling 17).
- **Lapse** — a pledge whose span ends unclosed. At half its target or more it pays the
  Partial Success closing award, otherwise nothing; never an answer, and earned favor is kept
  (Ruling 18).
- **Answer** — text staff wrote ahead for a being at one outcome tier (`Answer`, #4333 slice
  3), optionally for one pledge type, delivered as a vision. Its parts, in the vision's order:
  delay text, answer text with the sacrifice lines, fact text with its fact clue (a Codex
  entry or a secret), cost text with its cost pool, follow-up text with its follow-up clue;
  plus an onlooker line (the one room line others see) and `conceals_source`. Fact text and
  clue only on Success and Critical Success; the follow-up clue only on Partial Success and
  above (`answer_part_errors`, enforced on save and again at delivery). A closing rite that
  resolves a pledge draws one (`draw_answer`: the pledge type's rows, then the being's
  general rows, at the tier and then each lower tier). Authored for staff-owned beings on the
  Answer builder. _Avoid_: omen, sign, response.
- **Sacrifice line** — one authored line of an answer for one facet (`AnswerSacrificeLine`).
  The vision adds it once per distinct facet recorded on the pledge's sacrifices; any other
  sacrificed item is listed by name after the lines.
- **Held answer** — an answer drawn at a close that the being's worship pool cannot yet pay
  for (`PendingAnswer`): kept, never dropped, and sent as a vision by the daily tick
  (`deliver_held_answers`) once the pool can pay. Staff see held answers on the being's
  dashboard.
- **Steward** — a GM table assigned to a being by staff (`BeingSteward`, #4333 slice 4). The
  table's GM writes the being's pledge types and answers on the table page, and a closing rite
  of a pledge to it reaches that GM as a `BEING_ANSWER` prompt: one of the being's answers at or
  below the tier, or on Success and above the GM's own text (ADR-4333-C). Dismissed or
  unanswered within `DevotionConfig.steward_answer_days`, an authored answer is drawn. Only a
  Senior GM's table, never for a being that shows a **god sign** (a public codex entry, a public
  worship declaration, a Chosen outside the table, a temple; a secret faith is not one). Only
  the table's members serve a stewarded being. _Avoid_: owner, patron (a patron is the being of
  a Chosen), custodian (stories' custody).
- **Live route / live answer** — a GM running a scene answers a rite performed there (#4333
  slice 5, `live_services`): one of the being's general answers at or below the rolled tier, or
  one of its miracles, sent from a `BEING_ANSWER` prompt tied to the rite performance. Limit:
  once per being and character per game week, answers and miracles together. A pledge's closing
  rite never raises it (that is the **pledge route**). Dismissing sends nothing. Only a GM level
  with `GMLevelCap.may_adapt_answers` edits an answer's text, and never its clue, cost or
  follow-up. _Avoid_: prayer answer (a prayer is player-written text), ad-hoc boon.
- **Catalogue clue** — a clue one of a being's answers already links (fact or follow-up,
  `catalogue_clues`): the only clues a steward attaches to their own text or to answers they
  write. Staff create clues.
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
  distinct from a character's own single `tarot_card`. Since #4198 the link row is
  `BeingTarotCard` and carries `is_reversed`: a card represents a being upright or
  reversed, one row per (being, card), read as "The Tower reversed". _Avoid_: the being's
  card (there may be several, and belief is not fact); a reversed card as a second card.
- **Companion** — what a being's Codex entry shows beside the prose (#4198): the deity's
  provider `worship/companion.py`, registered at `ready()` into the Codex's companion
  registry; see the codex glossary. _Avoid_: sidebar, infobox.
- **Deity Editor** — the staff tool that authors the pantheon (#3780): one long edit
  page per being, saved live, and a per-being tracking dashboard. Lives in
  `worship/editor_services.py` and `frontend/src/pantheon/`. _Avoid_: "god admin",
  "pantheon builder".
- **Visibility tier** — a being's Codex tier as the editor reads it (`BeingVisibility`,
  #3780): **Public** (`is_public`), **Obscure** (not public, one organization's membership
  knows it through an `OrganizationCodexGrant`), **Secret** (a Clue must be found; also a
  being with no page yet). Never a field on the being.
- **GM notes** — `WorshippedBeing.gm_notes` (#3780): staff-only prose, never shown to
  players; prose, never a link, since no Arx 1 object exists here to link to.
- **Being codex entry** — `WorshippedBeing.codex_entry`, the being's own Codex page,
  following the `Gift`/`Technique`/`HouseCharterOption` precedent (#3776). Visibility
  (public / known-to-some / researchable) is read ENTIRELY through the linked entry's
  `is_public` tier — `WorshippedBeing` deliberately carries no visibility field of its own.
  PROTECT, so deleting a page that a god points at is refused rather than silent.
- **Being nickname** — an alternate name a being's worshippers use (`BeingNickname`,
  #3776); a being may carry several. No reverent/irreverent field — tone is prose, not
  data. `societies.Organization.patron_nickname` points at one of these, never
  directly at the `WorshippedBeing`, so different organizations can name the same god
  differently in their own records. A house's patron is set once, at founding, from the
  charter's patron question (#4205: `HouseCharterOption.being_nickname`), and the god's
  Codex companion lists its **sworn houses** (the published orgs whose
  `patron_nickname.being` is that god), each linked to its house page.
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
  (`BeingRelationshipValence`: ALLY/RIVAL/FEUD/UNKNOWN) + `story_from_a`/`story_from_b`
  (#4198: one telling per side, each god's page writes and shows its own). Deliberately
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
- **Vision** — a vision (`Vision`, #3779): prose a being sends one character,
  first-class and standalone, delivered as a VISIONS narrative message in the one
  treatment reserved for visions. `reveal_source` decides whether the recipient learns
  the being. May answer a prayer, hand over a Codex or secret clue, or belong to an episode;
  usually none of these. Always written by a person: sent live by staff or a GM, or written
  ahead as an Answer and released by a closing rite (`Vision.answer`, ADR-4333-B). A player
  never causes one on demand; below Success it carries no fact text and no fact clue.
  _Avoid_: "dream" (the dreams app is the sleep realm), "omen", "vision_text" (an Audere
  Majora threshold's own field).
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
