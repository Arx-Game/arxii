# ADR-0199: Minor gifts may override caster-path casting style

**Status:** Accepted · **Source:** #2905, Tehom design ruling 2026-08-03

## Context

ADR-0167 established that `TechniqueStyle` — and so `cast_concealment`, the attribution-hiding
knob `_concealment_for` resolves in `world/magic/services/cast_observation.py` — is a property
of the caster's Path, not of the Technique: the authored content contradicted a per-technique
style gate 71% of the time (236 of 330 `PathGiftGrant.starter_techniques` rows carried a style
whose `allowed_paths` excluded the very path granting them).

But a species-granted (MINOR) `Gift` is magic the character never chose — nobody picks their
own Khati senses the way they pick a Path. Tying its casting manner to whatever Path the
character happens to walk makes a Khati's species magic exactly as loud as their Path, with
the gift itself getting no say in how it manifests.

## Decision

`Gift` gains a nullable `style` FK to `TechniqueStyle` (`on_delete=PROTECT`, mirroring
`Path.style`'s shape). `_concealment_for` in `cast_observation.py` now checks
`technique.gift.style` first, falling back to the caster's Path style exactly as before when
the gift sets none. Every `Technique` has a required `gift` FK, so the check is always safe —
there is no technique without a gift to consult.

ADR-0167 still stands as the default: a Path-chosen technique still gets its casting manner
from the caster's Path. This narrows it for the one case where the character didn't choose the
gift they're casting from.

## Alternatives considered

**A style FK on `Technique` instead of `Gift`.** Rejected — that is exactly the shape ADR-0167
deleted, and for the same reason (per-technique style caused the 71% authoring contradiction
above). `Gift` is the technique-sharing unit that already carries the MAJOR/MINOR discriminator
this decision depends on; anchoring the override there keeps one style decision per gift instead
of one per technique.

## Confidence

Built and wired — `Gift.style` (`src/world/magic/models/gifts.py`) and the
`technique.gift.style` precedence check in `_concealment_for`
(`src/world/magic/services/cast_observation.py`). Nullable, so no backfill for existing rows
(ADR-0013); every Minor Gift authored so far stays styleless (defers to Path) until content
sets `Gift.style` on a real gift — that content authoring is out of scope for #2905.
