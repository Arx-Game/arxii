# Thread crossing ceremonies: every kind gets a resonance-matched personalization beat

ADR-0055 formalized "one specialization engine: resonance × entity → customized techniques" for
Gift, Path, and Covenant Role. The imbuing loop (`spend_resonance_for_imbuing`) already calls
`fire_variant_discoveries()` after every thread advance — but it only handles 2 of 9 `TargetKind`
values (GIFT, COVENANT_ROLE); the other 7 silently no-op.

We generalize the crossing ceremony so **every** `TargetKind` dispatches to a handler. The
handler produces a **resonance-matched personalization** at each PathStage crossing level (3, 6,
11, 16, 21) plus a **ceremony beat** (achievement + codex unlock + narrative message) consistent
with the existing GIFT/COVENANT_ROLE pattern. The ceremony entry point is named
`execute_crossing_ceremonies` (not "fire" — the word "fire" is confusing in a game with fire
magic); the shared beat helper is `execute_ceremony_beat`.

Critically, **not every kind uses the variant-discovery specialization shape.**
`AbstractSpecializedVariant` (the shared base for derived-on-read technique/covenant variants)
is *one* specialization shape — appropriate when the anchor entity has multiple resonance-flavored
forms selected by thread level (a technique manifests differently per resonance; a covenant role
has resonance-flavored sub-roles). But some kinds have different specialization shapes:

- **TECHNIQUE** uses an **additive** model (`SignatureMotifBonus`, ADR-0072) — a bonus layered on
  top of the technique, not a discovered variant. It must NOT inherit
  `AbstractSpecializedVariant`.
- **TRAIT / SANCTUM / MANTLE** may use an **unlock** model — a capability or passive unlocked at
  the crossing, authored as data (potentially via existing `ThreadPullEffect` rows with
  `min_thread_level` gates, plus a ceremony beat).
- **FACET** may tie into the Motif coherence system (deepening aesthetic bindings).
- **RELATIONSHIP_TRACK / RELATIONSHIP_CAPSTONE** may produce bond expressions (coordinating with
  Soul Tether / Spec B).

The contract is: **at a crossing level, the thread's resonance combines with the anchor to
produce a personalized manifestation + a ceremony beat.** The *shape* of that manifestation
(variant, additive, unlock) is per-kind. The ceremony beat is shared.

We rejected forcing all kinds into the variant-discovery shape because:
- ADR-0072 explicitly established that TECHNIQUE signatures are additive, not variants — forcing
  them into `AbstractSpecializedVariant` would violate that decision.
- Not every anchor has multiple resonance-flavored "forms" — a stat doesn't have variants, it has
  expressions. An unlock/capability model fits better.
- The variant-discovery shape requires a parent entity with authored child variants per
  resonance. Not all anchors have that structure (a trait, a sanctum, a relationship track).

We rejected a fully per-kind bespoke ceremony (no shared base) per ADR-0016: the ceremony beat
(achievement + codex + narrative) and the trigger (imbuing loop → crossing level) are shared; only
the effect shape varies. A registry of handlers keyed on `TargetKind` keeps the dispatch in one
place while allowing each kind to declare its own effect shape.

The handler registry follows the existing `OfferHandler` pattern
(`commands/offer_registry.py`): handlers register in `MagicConfig.ready()`, and
`execute_crossing_ceremonies` (the renamed `fire_variant_discoveries`) dispatches via the
registry. Kinds that have no handler yet (a gap being closed by follow-up subissues) log a
debug-level no-op rather than silently returning `None`.

> Status: accepted · Source: epic #1986, subissue #1987 · Confidence: derived-from-design, builds
> on the proven `fire_variant_discoveries` + `AbstractSpecializedVariant` pattern from #1578
