# ADR-0235: Humiliation is a permanent brand under a fading reputational layer; its verdict notice stays narrow; public records never expire

**Status:** accepted (2026-08-27, #2378 follow-up design call)

Three ratified decisions closing out the #2378 sentence-enforcement slice's open
humiliation/notification/records questions. **(1) Default HUMILIATION is
two-layered.** A PERMANENT physical brand (`sentences.mint_humiliation_brand`)
outlives the sentence entirely — provenance-free, its story discoverable in play
but never spelled out on the record itself, mirroring `apply_humiliation`'s
existing neutral-copy rule. Atop it sits a TEMPORARY reputational layer: the
existing deed-prestige hit (now persisted verbatim onto
`JusticeCase.humiliation_prestige_hit` rather than re-derived) plus a persona-scoped
examine/profile explanation (`sentences.active_humiliation_mark`, surfaced via
`PersonaSerializer.humiliation_mark`). Both fade together at
`HUMILIATION_TERM_DAYS` — `sentence_sweep_tick`'s new restore leg
(`_sweep_humiliation_restores`) awards the exact stored hit back and zeroes the
field, idempotently. The brand itself is SCAR SUBSTRATE — TehomCD's domain — so
`mint_humiliation_brand` is a documented no-op seam wired in at the correct call
site now, not a new call site added later. **Rejected:** modeling the whole
consequence as one expiring row — collapses two genuinely different lifetimes (a
permanent mark vs. a fading one) into one, and the permanent half belongs to a
substrate this slice doesn't own.

**ADR-0081 nuance:** "automatic loss is fine; automatic gain is not" reads, at a
glance, like it forbids the sweep's restore leg — a cron handing out positive
prestige with nobody acting. It doesn't apply here: the restore is a reversal of
a loss `apply_humiliation` itself inflicted automatically, closing a debt this
system created against itself for the EXACT amount debited, not new value
creation. Same shape as any other term simply expiring.

**(2) Verdict-notification audience is ratified as-is: area-feed only.**
`notify_verdict`'s existing reachable audience (the accused + exculpatory
submitters via direct narrative message) already excludes accusers/victims by
design (see the accuser-routing-gap note in `notifications.py`) — anything
broader than the case's own participants belongs to the area-scoped public
record (`active_public_marks`, the wanted board, `tidings` VERDICT feed items),
not a direct push. This design call closes the open question without a code
change: the split between direct-notice audience and area-feed audience was
already correct.

**(3) Public records are permanent IC history — confirmed, not new.** A served
sentence's trace in the public record removes only via pardon/exoneration
(`lifecycle.pardon_persona`, `AccusationNullification`); nothing else prunes it.
Already true in code (`ExileDecree.lifted_at`, the nullification path) — this
call records the principle so a future change doesn't casually add a decay/prune
path without recognizing it as a reversal of an explicit ruling.

> Status: accepted · Source: #2378 follow-up spec (2026-08-27 design call),
> world/justice/sentences.py, world/justice/models.py, world/scenes/serializers.py
