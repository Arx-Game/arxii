# Declared risk is a wager, not a payout: Legend is settled, not asserted

Legend was minted at the moment of an act, at a flat authored value, from twelve
sites. Ten of them never asked whether anything was at stake or whether anything
was accomplished: a feeding kill minted a deed for draining a helpless victim, a
lockpick minted one, a feast minted one, and a beat completed without ever
locking its stakes contract paid its full authored tier ungated. On the renown
side, `_resolve_award_inputs` computed `legend_awarded = RISK_LEGEND_AWARDS[risk]`
straight off an authored `RenownAwardConfig.risk`, so an author setting
`risk=EXTREME` on any config paid 1500 to anyone, at any level, with nothing
actually at stake.

**Legend now settles at the end of a story unit, and every number that decides
its value is priced rather than asserted.** `world.societies.legend_settlement`
is the single seam. It applies, in order: a **per-person peril floor** (each
earner's risk priced against their own level, not the party average — below
`LEGEND_RISK_FLOOR` they mint zero, not a reduced award); the **held-objective
share** (the shared deed pays the severity-weighted fraction of stakes actually
held, so beating the monsters while the town burns pays for the monsters); a
**station** stamp of `min(earner level, threat level)`; and a **standout pass**
that pays a crucial contribution resolved brilliantly even when the unit was
lost, generalizing ADR-0122 past `Battle`.

`RenownAwardConfig.risk` keeps its meaning and its consumer — it is now the
author's *ceiling* on how legendary an event type may be, and Legend pays on the
weaker of that declaration and the level-priced settled reality. #676's
three-independent-scales model (Magnitude → fame + prestige, Risk → legend,
Archetypes → reputation) is **preserved**: a royal wedding is still high
Magnitude and NONE Risk, still enormously famous, still worth no Legend.

Station is stamped on the entry but **not folded into `base_value`**. A deed's
worth as a story does not depend on who did it — the level 1 and the level 5 who
survived the same threat did the equally impressive thing — so the stored value
is untuned and `station_multiplier()` is applied on read by
`LegendRequirement.is_met_by_character`. Retuning the multiplier therefore never
requires recomputing a historical row, and the `CharacterLegendSummary` matview
stays the tale-worth total that fame, murmur, common knowledge and item legend
correctly read.

The advancement gate additionally **bands** on station: only deeds won at or near
the step being taken qualify, so a bank accumulated at level 1 while development
points accrued stops qualifying once you advance past it. Legend itself remains
permanent and monotonic (ADR-0066, ADR-0054); advancement is the only read that
narrows.

**Rejected: splitting Legend out of the renown bundle.** An earlier draft of the
spec proposed removing `_create_legend_entry` from `fire_renown_award` on the
grounds that Legend and Renown were conflated, and additionally read
`RenownAwardConfig.risk` as vestigial once that split removed its only consumer.
Both were wrong and are recorded here so they are not re-proposed. Tracing the
field's intent found the orthogonality was designed in from the start
(`societies/constants.py`, #676 Phase B: "Each Renown event carries up to three
independent scales"), and the "no remaining consumer" reading was **circular** —
the refactor itself was what removed the consumer. The defect was never the
shared descriptor; it was that Legend's axis alone was taken at face value while
`Beat.risk` (ADR-0067) already gets priced.

**Rejected: authoring the station multiplier.** Every other number here moved to
a staff-editable row (`RiskCalibration.legend_award`, `RenownMagnitudeAward`,
`LegendSettlementConfig`), with the Python constants demoted to fallbacks. The
station multiplier deliberately stayed a code constant: it is not a tuning knob
but the rule that you cannot bank above your station or by slumming, and
authoring it would let that rule be edited away. Tuning it costs a deploy and
nothing else, since base values are stored untuned.

**Audere Majora is a structural exception, not a waiver.** A crossing is always a
legendary reward and cannot happen without great personal risk, so it mints
unconditionally at the character's new level via `structurally_perilous`. It does
not bypass the gates; it satisfies them by the shape of the act — jeopardy is
intrinsic, a completed crossing *is* the objective held, and a tier crossing sits
at the ceiling of the old station by definition. Nothing authored can set the
flag. This also closes a bug the ruling exposed: the crossing deed was previously
*contingent* on `threshold.risk`, guarded only by a test asserting the seeded
default, so an authored `risk=NONE` produced a crossing with no deed at all.

> Status: accepted · Source: #3463 · Extends ADR-0066 (Legend earned only from
> difficult victories) and ADR-0076 (removal reached through the fuse walk);
> generalizes ADR-0122 (battle legend win-gated with standout exceptions) past
> Battle; preserves ADR-0077 (effective risk priced to target level) and
> reconciles with ADR-0080 (battle stakes price at declared risk) — that ADR
> governs what the objective is worth, this one governs what an individual
> earned, and a demigod on a battlefield still risked nothing personally.
