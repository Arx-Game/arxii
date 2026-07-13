# Worship & Ceremonies

**Status:** Core slice SHIPPED (#2355 worship foundation + #2289 ceremonies/funerals, 2026-07-13)
**Depends on:** Skills/Checks (Rites + aspects), Secrets, Consent, Clues, Renown/Legend,
Vitals (#2287 ghost containers), Events/Scenes (optional chassis)

## What's built

- **Worship foundation (#2355):** `WorshippedBeing` (gods as authorable data, vast
  `resonance_pool`, rare `avatar_sheet` — ADR-0132), `WorshipTradition` → Rites
  specialization bridge, `WorshipGrant` ledger, `DevotionStanding` (one-way PC→god
  favor), `WorshipDeclaration` (CG public + secret worship; secret mints a Secret).
  Rites skill + 4 tradition specializations (PLACEHOLDER names), Ceremony Rites
  CheckType with the Devotion aspect (Path of the Chosen's edge), God's Favorite
  Princess/Prince/Chosen achievements (top-devotion reach/tie per being).
- **Ceremonies (#2289):** framework (`CeremonyType` rows; Funeral full handler,
  Blessing/Sermon renown-only) with open/offering/speech/finish/abandon actions,
  telnet `ceremony` family, read API + game-view room card. Funerals re-open the
  ghost's emit window (third ADR-0131 container), award posthumous prestige through
  the legend engine (officiant lesser cut), feed the being's pool from sacrificed
  items, and invoke the `execute_will` NO-OP seam (#1985 fills it). Twisted rites
  (secretly serving the officiant's hidden god) leak consent-gated clues. Corpse
  gear routes through steal unless the dead player's friends list trusts the taker.
  Bounded abandonment via the hourly `ceremonies.auto_abandon` sweep.

## Not built (filed)

- Wedding + Coronation ceremony types over `Union`/`MarriagePact` + divorce/murder
  prestige hits (#2358)
- Event grandeur / prestige-wealth investment for once-in-a-lifetime events (#2357 —
  the events roadmap's reserved EventModification slot)
- Miracles / divine intervention spending worship pools + audere coupling (#2360)
- Item legend value + legend transfer at offerings (#2359)
- Post-CG worship conversion (#2361); generic RP turn-queue (#2356)
- Wills & estates (#1985 — the funeral seam's other half)
