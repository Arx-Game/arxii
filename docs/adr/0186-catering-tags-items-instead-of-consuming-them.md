# ADR-0186: Catering tags items instead of consuming them

**Status:** Accepted (built #2869; supersedes the catering half of ADR-0184)

**Decision.** Catering is a property of *containers*, not an act performed on
individual dishes. Any container item — a banquet table, an amphora, a food
cabinet, a tray — can be flagged for a scheduled or active event
(`designate_catering_container`); thereafter every **consumable** placed into
it through the ordinary `put_in` path is tagged for that event
(`tag_catered_provision`), and the tagged provisions' quality sum mints the
primary host's Hospitality deed at `complete_event`, exactly as before.
**Nothing is consumed.** The food stays a real item that can be taken back
out, eaten, or stolen; removing it does not untag it, because setting it out
was the contribution. Tags are deduped per `(event, item_instance)`, so
shuffling a dish in and out cannot farm prestige, and re-flagging a vessel is
idempotent. Crucially the tag is **permanent and public**: both vessels and
provisions render their full catering history on examine — *"This amphora was
used for catering at Big Bob's Nameday."* — through the established
`return_appearance` sections pattern, so a vessel that has served ten banquets
carries ten lines and memorable events leave physical souvenirs scattered
through the world.

**Rejected alternatives.** (a) The shipped ADR-0184 design — consume the dish
into a snapshot row: simpler, but it destroyed the item, gave the world no
memory of the occasion, and required a bespoke per-item `cater` verb.
(b) A boolean `is_catering` field on the container: cannot express "this
vessel served at these four events over its life," which is the whole point.
(c) Awarding prestige at add-time rather than completion: makes the deed fire
repeatedly and invites add/remove churn; the tag set read at completion gives
one deed and natural dedupe. (d) Splitting prestige across all hosts: one
deed to the primary host matches the ceremony precedent and avoids
multiplying prestige by co-host count.
