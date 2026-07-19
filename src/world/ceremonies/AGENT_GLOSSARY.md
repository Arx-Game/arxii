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
