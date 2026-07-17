# Gifts are Major or Minor; species abilities are a species-granted Minor Gift

Every character's character-creation Gift is their **Major Gift**; **Minor Gifts** are smaller,
shared, more-easily-acquired gifts (e.g. *Sight* → Soulsight/Magesight, *Travel* → teleportation),
and a species' innate powers (vampire, lycan, khati lineage) are delivered as a **species-granted
Minor Gift** rather than a bespoke per-species ability system. We add the Major/Minor split by
extending the one `Gift`/`CharacterGift` model with a `kind` column (ADR-0007) and reusing the
existing grant/ritual acquisition paths; we rejected both a parallel `MinorGift` model (ADR-0016)
and a separate species-ability subsystem, because routing species powers through the gift pipeline
gives them techniques, threads, resonance, and progression for free.

> Status: accepted · Source: design discussion 2026-06-27 · Confidence: verify against code — extends `world/magic` `Gift` (no Major/Minor field today)

> Update (#2472): `SpeciesGiftGrant` now expresses species balance in four
> independent, freely-combinable shapes — condition drawback, benefit condition,
> drawback distinction (a social/reputation price), and a CG point cost (summed
> into the CG-points breakdown) — plus the all-null/0 default, a free weak gift.
> Per-species assignment of these shapes is lore-repo content, not authored here.
