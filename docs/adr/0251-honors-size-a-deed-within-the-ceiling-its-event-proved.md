# Honors size a deed within the ceiling its event already proved

The Rite of Honors (#3466) lets a character spend Golden Hares and write a public journal
to raise another character's deed (`LegendEntry.base_value`), or to establish a brand-new
solo deed for an act the automatic settlement never credited. Every honor is clamped to
`anchor_event.base_value - existing_base_value` (`honors.py`'s `headroom`): a deed can never
be honored past what its anchoring `LegendEvent` itself already proved, and establishing a
deed prices it the same way against that same ceiling. **Peer judgment redistributes
recognition inside an envelope a settled event already earned; it never invents peril that
did not happen.** This is why the feature does not reopen the hole ADR-0249 closed — that
ADR made Legend price from a settled stakes contract instead of an authored flat value
exactly so nothing could mint danger that was never risked, and honoring only ever moves
value that the event's own settlement already proved was at stake, never above it.

Two refinements surfaced during implementation, both load-bearing:

- **Establishing is refused when the honoree already has an active deed anchored to that
  event** (`HonoreeAlreadyAnchoredError`). Without this, several honorers could each
  establish a separate full-ceiling deed for the same act, uncapping the aggregate the
  ceiling exists to bound — many voices are meant to grow *one* deed, never mint their own.
- **A struck deed (`LegendEntry.is_active=False`) neither proves peril, counts toward the
  station max used when establishing, nor blocks a fresh deed from being established.** It
  is worth nothing everywhere else a deed's value is read, so directing someone to "honor
  the existing deed instead" would send them to spend Hares on a record that can never be
  worth anything again; the act may still deserve a genuine one.

**Rejected: let honors mint freely, with the Hare cost as the only brake.** An earlier shape
of the spec taxed honoring in Golden Hares alone and let `honor_value_added` land
unclamped. Rejected because a cost is a friction, not a ceiling — a well-funded character
could still inflate a deed past anything its event proved, which is precisely the unpriced
danger ADR-0249 spent #3463 removing. The ceiling clamp is not a tuning knob to loosen later;
it is the property that keeps this feature safe to have shipped at all.

> Status: accepted · Source: #3466 · Extends ADR-0249 (Legend is settled, not asserted)
