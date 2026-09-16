# Worship & Ceremonies

**Status:** Core slice SHIPPED (#2355 worship foundation + #2289 ceremonies/funerals, 2026-07-13);
Seance (#2393), Miracles/divine intervention (#2360), item legend value (#2359), Wedding (#2358/#2999
incl. wedding-consent/coronation/divorce, 2026-08-15), and post-CG public conversion (#2361) have
since shipped too — see below.
**Depends on:** Skills/Checks (Rites + aspects), Secrets, Consent, Clues, Renown/Legend,
Vitals (#2287 ghost containers), Events/Scenes (optional chassis)

## What's built

- **Worship foundation (#2355):** `WorshippedBeing` (gods as authorable data, vast
  `resonance_pool`, rare `avatar_sheet` — ADR-0132), `WorshipTradition` → Rites
  specialization bridge, `WorshipGrant` ledger, `DevotionStanding` (one-way PC→god
  favor), `WorshipDeclaration` (CG public + secret worship; secret mints a Secret;
  `public_is_sincere` heart-vs-lip-service flag, #2361).
  Rites skill + 4 tradition specializations (PLACEHOLDER names), Ceremony Rites
  CheckType with the Devotion aspect (Path of the Chosen's edge), God's Favorite
  Princess/Prince/Chosen achievements (top-devotion reach/tie per being).
- **Ceremonies (#2289):** framework (`CeremonyType` rows: Funeral full handler,
  Blessing/Sermon renown-only, Seance third ghost-window handler #2393, Wedding
  solemnizes an active Betrothal #2358/#2999, Conversion repoints public worship
  #2361) with open/offering/speech/finish/abandon actions,
  telnet `ceremony` family, read API + game-view room card. Funerals re-open the
  ghost's emit window (third ADR-0131 container), award posthumous prestige through
  the legend engine (officiant lesser cut), feed the being's pool from sacrificed
  items (with item legend value carried into the honoree deed, #2359), and invoke
  the `execute_will` NO-OP seam (#1985 fills it). Twisted rites
  (secretly serving the officiant's hidden god) leak consent-gated clues. Corpse
  gear routes through steal unless the dead player's friends list trusts the taker.
  Bounded abandonment via the hourly `ceremonies.auto_abandon` sweep.
- **Worship rites & rewards (#3777, 2026-09-16):** tiered rites over the pantheon
  foundations (#3776). `RiteKind` (1 Devotional / 2 Demanding / 3 Perilous) is the shared
  catalog; each being instantiates its own `WorshipRite` (flavor, check type, one of its
  own `BeingResonance` rows); `WorshipRiteTierAward` pays resonance and favor per (tier,
  outcome), three tiers tuned once for every god. A tier 1 or 2 rite is a scene act
  (`perform_worship_rite`, `PerformWorshipRiteAction`): 1 AP per tier plus a little social
  fatigue, the rite's check with the tradition specialization, then the award; a FAVORED
  resonance, the being's feast day and birth favor each double it. Devotion from a rite
  lands once per game week per character, resonance every time, so repeats stay fine for
  RP. Tier 3 is the existing Ceremony machinery: a RITE `CeremonyType` carries the rite
  and the officiant's Rites roll pays it at finish; participants earn through
  dramatic-moment tags. Offerings carrying a facet the being favors are credited at a
  config multiplier on the pool grant and the devotion bump. `Relic` names a specific
  sacred `ItemInstance` of a being (dashboard surface in #3780). Every magnitude is
  PLACEHOLDER; the event/contest mechanics a tier 3 rite might wrap stay out of scope
  (#3770).
- **Shrines & temples (#3778, 2026-09-16):** places of worship as sites a rite is
  performed at, over #3777. A **shrine** is room-level and personal: a new SHRINE
  `RoomFeatureInstance` kind reusing Sanctum's one-feature-per-room and soft-delete
  machinery, with a `ShrineDetails` sidecar (being, founder, `consecration_points`);
  founded by the room's holder (`found_shrine`, action `shrine_found`), never bought or
  built as a project. A **temple** is building-level and institutional: a
  `TempleDedication` on the `Building` itself, one active per building, covering every
  room under the building's area node with no per-room duplication; dedicated by whoever
  holds the building (credited owner, area holder, or that holder's org leader;
  `dedicate_temple`, action `temple_dedicate`). A rite of the site's own being is boosted
  by the site's tier bonus (`ConsecrationTier` ladders per scope, shrine and temple
  additive, so a cathedral's inner altar stacks) and consecrates the site by its tier in
  points; a site of another being does neither. Every magnitude is PLACEHOLDER and the
  ladders are authored rows, reconcilable with a general location-intensity system
  (#3771) later.
- **Prayers & visions (#3779, 2026-09-16):** Arx 1's freeform prayer revived, split from the
  mechanical rites. A `Prayer` is a plain log of a character's words to a being (`pray`,
  telnet `pray <being>=<words>`), one of the few freeform channels straight to staff, with
  no effect of its own. Three independent, stackable conditions make one count: dire straits
  (Soulfray active, or health in the knockout band) runs the divine-intervention check on the
  NEAR_DEATH trigger, the wire `MiracleTrigger.NEAR_DEATH` had waited for, narrowed to the god
  prayed to; the first prayer of the game week at a shrine or temple of the being pays a
  little devotion (the humblest engagement, below a tier 1 rite); and a GM may answer with a
  `Vision`. A vision is first-class prose from a being (`send_vision`, staff action
  `vision_send`, the sheet's Send-vision composer beside the character's recent prayers),
  with `reveal_source`, an optional Codex clue handed over on the spot, an optional episode of
  a story the recipient is in, delivered through the narrative system's VISIONS category with
  the one treatment reserved for visions: `|G[VISION]|n` on telnet, its own `vision` feed lane
  and the sheet's emerald `VisionCard` on the web. Rarity is the GM's restraint, not a rule.
  Every magnitude is PLACEHOLDER. The near-death read is a light touch on TehomCD's
  Soulfray/vitals domain, flagged on the PR.
- **Deity Editor (#3780, 2026-09-16):** the staff surface over the whole stack, at
  `/staff/pantheon`. A tile grid sorted by resonance pool (the number beside each name),
  searchable by name or nickname, filterable by Codex tier; "+ Add God" opens the edit
  page. The edit page is one long page, never a wizard: collapsible sections (Identity,
  Nicknames, Portfolio with resonances and favored facets, Feast Days, Tarot, Relationships,
  Visibility, GM Notes) with a highlight dot while an optional field is unfilled, no explainer
  copy anywhere (each "+ Add" carries its explanation as a hover tooltip), saved live with no
  draft gate pre-launch. Visibility is the linked Codex entry's tier: Public, Obscure (known to
  one organization's membership through the new `OrganizationCodexGrant`, the bridge #3776
  deferred to implementation), or Secret. The per-being tracking dashboard puts the pool and
  "Send Vision…" together in the header and tabs Overview, Worship (contributors, offerings
  and most devoted on one page), Temples & Shrines, Prayers (dire / act of devotion / answered
  badges), Visions, Relics, and Codex Entries (the being's page, its prerequisite chain and
  the entries its visions' clues open, with which clue unlocks each). Only Dan and TehomCD use
  it; density over hand-holding.
- **Miracles / divine intervention (#2360):** gods spend `resonance_pool` on authored
  `Miracle` effects that fire automatically for a high-devotion PC in danger, plus
  faith-colored Audere Majora crossing variants.
- **Post-CG public conversion (#2361):** a `CONVERSION` ceremony repoints
  `WorshipDeclaration.public_being`, via either a PC-officiated rite the convert
  must accept (`WorshipConversionOffer`, mirrors the Seance offer — player-reachable
  through REST `/api/ceremonies/conversion-offers/`, the telnet `conversion` command,
  and the web `ConversionOfferBanner`/`ConversionOfferDialog`, all mirroring the
  Seance offer's own delivery surfaces) or a self-officiated solo rite (no other PC
  needed). The heart-vs-lip-service choice (`public_is_sincere`) is private,
  owner/staff-only; the web dialog carries the choice as a Switch, telnet acceptance
  is always sincere. The deed rides the existing #1464 scandal fork — no bespoke
  social-consequence mechanism. Secret-faith retarget/shed (the draft spec's Decisions
  4/5) was scoped OUT of this pass: an old secret faith's `Secret` row is proven
  untouched (a no-op), not built into a retarget/shed service or a new secret-side
  Action — flag as a possible follow-on if play surfaces demand for changing a
  *secret* faith post-CG.

## Not built (filed)

- Coronation ceremony type + divorce/murder prestige hits for Wedding (#2358)
- **Wedding consent + Coronation + divorce prestige (#2358, 2026-08-15):** WEDDING
  solemnizes a pre-existing `Betrothal` at FINISH, gated on a `WeddingConsentOffer`
  per spouse honoree minted at ceremony START (both must ACCEPT; a DECLINE aborts the
  whole ceremony) — replaces the earlier idea of gating consent at `propose_betrothal`.
  CORONATION solemnizes an already-held `Title` (no title-passing mechanics; one-off
  per (honoree, title) via the `Coronation` record). `initiate_divorce` — either spouse
  ends a living `Union` unilaterally; both take a personal deed-prestige hit, the
  initiator steeper. Neither ceremony type mints extra flat prestige; event grandeur
  (#2357) is the intended payoff lever once it lands.

## Not built (filed)

- **Discovered spouse-murder prestige hit** — the mechanism
  (`apply_spouse_murder_penalty`-shaped service, larger than the divorce penalty) is
  deliberately not built: the justice app has no victim FK on any crime model, so
  "this conviction's victim was the convict's spouse" cannot be derived. Building that
  linkage is a justice-app design question with its own blast radius, not a #2358
  side effect.

## Not built (filed)
- Event grandeur / prestige-wealth investment for once-in-a-lifetime events (#2357 —
  the events roadmap's reserved EventModification slot)
- Generic RP turn-queue (#2356)
- Wills & estates (#1985 — the funeral seam's other half)
