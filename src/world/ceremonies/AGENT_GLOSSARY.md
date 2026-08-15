# Ceremonies glossary

- **Ceremony** — a player-run rite bookending freeform RP (`Ceremony`): open →
  offerings/speeches → finish/abandon. Does not require a Scene or Event.
  _Avoid_: conflating with the magic `Ritual` CEREMONY execution kind (caster-scoped
  thread rites — a different system).
- **Officiant** — the persona who opened the ceremony and may direct it; anyone can
  officiate, skill shapes the outcome.
- **Honoree** — a character the rite recognizes (`CeremonyHonoree`); at a funeral,
  the deceased.
- **Offering** — an item sacrificed (destroyed) to the rite; its value feeds the
  being's worship pool and the honoree tally.
- **Presented being** — what attendees see the rite performed for; the TRUE `being`
  differs only in a twisted rite and never leaves player-facing surfaces.
- **Twisted rite** — a ceremony secretly serving the officiant's hidden god behind
  their public front; consent-gated witnesses may sense it (clue on the worship
  Secret).
- **Ghost window** — the death scene, the IC day of death, an OPEN funeral honoring the
  character at their location, or an OPEN seance with an ACCEPTED offer at its location
  (#2393) — any of these re-opens a dead character's emit/pose voice (ADR-0131).
- **Seance** — a `CeremonyType` (`SEANCE`) that, once its `SeanceManifestationOffer` is
  ACCEPTED by the honoree's own controlling account, widens their ghost window and — for a
  RETIRED honoree only — grants a narrow, ceremony-scoped puppet-back-in via
  `Account.can_puppet_for_seance`. Never a resurrection: the grant is torn down the instant
  the ceremony closes (`revoke_seance_manifestations`).
- **Will seam** — `execute_will(sheet)`, invoked per honoree at a funeral's finish;
  since #1985 it delegates to `estates.execute_settlement` (the funeral door —
  first of funeral / will-reading / sweeper wins; safe no-op for long-dead honorees).
- **Trusted handler** — someone the dead player's tenure friended; may take from the
  corpse without `steal`.
- **Conversion** — a `CeremonyType` (`CONVERSION`, #2361) that repoints the convert's
  public `WorshipDeclaration.public_being` on finish. Two routes: a PC-officiated rite
  the convert must accept (`WorshipConversionOffer`, mirrors the Seance offer), or a
  self-officiated solo rite (officiant IS the honoree — no offer, no other PC needed).
  Mints a deed through the same #1464 scandal fork any public deed uses; carries no
  bespoke social-consequence mechanism.
- **Conversion offer** — `WorshipConversionOffer`, the consent gate for a PC-officiated
  conversion. Created at open only when the officiant differs from the convert. PENDING
  until the convert's own account answers (`respond_to_conversion_offer`); accepting
  records the heart-vs-lip-service choice right there. A declined or never-answered
  offer means the rite concludes but honors nothing for that honoree — no deed, no
  worship repoint (mirrors a declined Seance offer's shape, not its puppet mechanics).
- **Wedding consent offer** — a `CeremonyType` (`WEDDING`) consent gate
  (`WeddingConsentOffer`, #2358): one row per spouse honoree, minted by the
  officiant's `open_ceremony` call at ceremony START. Both must reach ACCEPTED
  before `finish_ceremony`'s WEDDING branch may solemnize; a DECLINE aborts the
  whole ceremony (`abandon_ceremony`). The union + marriage pact mint at
  ceremony FINISH, never before — this replaced the earlier idea of gating
  consent on `propose_betrothal` (betrothal stays a house-leader proposal
  artifact; the binding moment is the rite itself). Shares `SeanceOfferStatus`
  (PENDING/ACCEPTED/DECLINED) with the Seance offer — same three-state shape.
- **Coronation** — a `CeremonyType` (`CORONATION`) that solemnizes an
  ALREADY-HELD `Title` — no title-passing mechanics live here (the honoree
  must already hold the title via the house/realm systems, or the officiant's
  caller is staff/GM fiat). One-off per (honoree, title): `Coronation` (#2358)
  is the permanent record, minted at FINISH, unique on `(honoree_sheet,
  title)` — a later coronation for a DIFFERENT title (a ducal coronation
  followed by an imperial one) still stands. `open_ceremony`'s precondition is
  the friendly pre-check; the `UniqueConstraint` is the real enforcement.
- **Divorce** — `world.societies.houses.pact_services.initiate_divorce`
  (#2358): either spouse ends a living `Union` unilaterally (`end_union`, the
  field's first writer), dissolving the bound `MarriagePact` under
  `PactDissolutionReason.DIVORCE` (fires the existing house-level
  `apply_pact_shift` alliance reprice) and applying a personal deed-prestige
  hit (`award_deed_prestige`) to BOTH spouses — the initiator's steeper.
  Distinct from `ANNULMENT` (the zero-penalty staff/GM void path).
