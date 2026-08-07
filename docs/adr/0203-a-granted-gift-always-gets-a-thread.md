# ADR-0203: A granted gift always gets a thread — resonance resolves inside the grant primitive

Context: #2967/#2968 gave `Gift.resonances` a legitimate empty-set meaning ("unrestricted" at
the weave gate), but the four call sites that granted a gift (`grant_path_magic`,
`provision_species_gifts`, CG's `_finalize_gift_and_techniques`, `charge_and_learn`'s implicit
gift acquisition) each read that same empty set as "no resonance available" and silently skipped
provisioning the gift's latent GIFT thread — #2971 named this "an empty gift resonance set means
unrest": a character could hold a `CharacterGift` and its techniques with no GIFT thread for any
downstream reader (cast resolution, dramatic-moment grants, crossing ceremonies) to find a
resonance on. Decision: move resonance resolution *inside* the shared primitive,
`grant_gift_to_character` — `_resolve_grant_resonance` (`world/magic/specialization/services.py`)
tries, in order, the caller's explicit pick (when the supported set is empty or contains it), an
existing GIFT thread already covering the gift (lineage-aware, via `gift_threads_for` — makes a
re-grant a true no-op), the supported set's claimed-or-first member, the character's own earliest
GIFT thread's resonance, their highest-`lifetime_earned` claimed resonance, and finally their
anima-ritual resonance; if none of those resolves, it raises `GiftResonanceUnresolvable` loudly
*before* the `CharacterGift` row is minted, so a partially-granted gift (link with no thread) —
the exact corrupted state this ADR eliminates — can never be created. Every grant call site now
goes through this one resolver, so a new caller inherits the "always a thread" contract for free
instead of needing to remember its own resonance-availability check. CG additionally writes the
same resolved pick onto the character's anima ritual (`RitualCheckConfig.resonance`) at finalize,
since the anima ritual is the character's magical identity and previously never recorded one from
CG at all. Rejected: keep "`None` skips thread provisioning" and patch each of the four call sites
individually to pick a fallback resonance — this is exactly the shape that produced the bug (a
policy duplicated per caller drifts, and a fifth future call site would silently reintroduce it).

> Status: accepted · Source: #2971 (spec references #2968) · Related: ADR-0052 (`Gift.resonances`
> is the weave-time supported set, not the cast-time value), ADR-0055 (specialization engine)
