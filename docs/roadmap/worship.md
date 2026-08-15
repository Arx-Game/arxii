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
