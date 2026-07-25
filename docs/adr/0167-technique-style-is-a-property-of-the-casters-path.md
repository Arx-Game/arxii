# Technique style is a property of the caster's Path, not of the Technique

#2700 asked whether `Technique.style` should stay a single FK or become multi-valued,
so that the same technique could be taught in different styles by different paths. The
answer is neither: `style` does not belong on `Technique` at all. It is a property of
the **practitioner**, and it now lives on `classes.Path.style`.

## Decision

**Style hangs off the caster's Path.** The same catalog `Technique` is an Incantation
when a Path of Tomes character casts it and a Manifestation when a Path of Steel one
does. `Technique.style`, `TechniqueDraft.style`, and `TechniqueStyle.allowed_paths` are
deleted; `allowed_paths` becomes the reverse accessor of `Path.style`. Many paths may
share one style — higher-stage paths inherit their line's style — so the cardinality is
many-paths-to-one-style, which is why the FK sits on `Path` (also the ADR-0010
direction: the specific model points at the reusable primitive).

**Style is mechanical, not decorative.** A `StyleCapabilityRequirement` row gates casting
on the caster's capabilities — an Incantation caster who cannot speak cannot incant.
These are evaluated by `technique_performable` against the same
`get_effective_capability_value` oracle as `TechniqueCapabilityRequirement`, so one gate
reads two requirement sources. They cannot be collapsed into the per-technique set: a
per-technique requirement is caster-independent by construction and so structurally
cannot express "this applies only when a Tomes character casts it."

This does not contradict ADR-0136's ruling that the system never specifies how magic
*appears* when cast. "Can observers detect that a cast happened" and "can you cast while
silenced" are a different axis from "what does it look like"; players still narrate the
latter.

**The path-style learn gate is deleted outright, not re-derived.** `can_learn_technique`
and `TechniqueStyleForbidden` are gone. Gift ownership (`learn_technique`'s existing
`GiftNotOwned` check) plus `PathGiftGrant`/`TraditionGiftGrant` curation is the real
gate, and it operates at technique granularity — finer than style ever did.

## Why

The authored content contradicted the style gate 71% of the time: 236 of 330
`PathGiftGrant.starter_techniques` rows carried a style whose `allowed_paths` excluded
the very path granting them (61 distinct path × gift × style collisions; 11 of 25 gifts
already spanned multiple styles). Those grants landed anyway only because
`grant_path_magic` writes `CharacterTechnique` rows directly and never called the gate —
the same fast-path-skips-slow-path-validation shape as #2687. The learn and teaching
paths *did* call it, so a character could own a technique they could not be taught, and
`sphinx.audit_vow_coverage` under-reported their real coverage.

Style-on-Technique also defeated the requirement that motivated having styles at all.
Path of Whispers — whose whole point is casting with no visible indication — has 58
authored starter grants, of which only 14 are Subtle; 32 are Manifestation ("raw
elemental force given shape and weight"). Anchored to the technique, three-quarters of a
Whispers character's starting kit is *visible* magic. Anchored to the Path, all 58 casts
are subtle because the caster is a Whispers practitioner.

In the content as authored, style was already a synonym for Path: five styles each had
`allowed_paths` of exactly one path, 1:1, covering 252 of 278 techniques. The remaining
seven styles ("Warding Stance", "Conjuration", …) had no gate at all and were mostly
machine-minted by `effect_palette_content.py` with templated descriptions, purely to
satisfy a non-null FK — the field manufactured content that meant nothing. Nothing
outside the learn gate, serializer, and admin read `Technique.style`; the CG
Tradition→Gift→Technique funnel never referenced it.

The field made sense when it was introduced (PR #252), in the build-your-own-technique
era: a player authored a technique and chose its style. #2426 turned `Technique` into a
shared staff-authored catalog row, and the same field silently became a global
constraint on a row everyone shares. It survived that rework because it carried the path
gate, not because the concept was re-examined.

## Rejected alternatives

**Keep the single FK.** Leaves the 71% content conflict, the grant/learn inconsistency,
and the Whispers-kit-is-visible problem in place.

**Make `style` an M2M on `Technique`.** Answers the literal question but treats a
caster-derived property as catalog data: it would require every technique to enumerate
every path-style that may ever cast it, and re-enumerate on every new path. It also
still cannot express "Subtle applies to everything *this caster* does."

**Re-derive a path restriction from `Path.style`.** Honest to the old intent, but
reproduces the same 71% conflict — the content authors have already voted against that
restriction.

**Delete `TechniqueStyle` entirely** as pure flavor. Rejected because style carries real
mechanical weight (subtle casting, capability-gated casting circumstances); deleting it
would discard a live requirement, not just vocabulary.

> Status: accepted · Source: #2700, Tehom design ruling 2026-07-25 · Confidence: built
> and wired — `Path.style` + `StyleCapabilityRequirement` folded into
> `technique_performable`; `Technique.style`/`TechniqueDraft.style`/`allowed_paths`/
> `can_learn_technique`/`TechniqueStyleForbidden` removed.
