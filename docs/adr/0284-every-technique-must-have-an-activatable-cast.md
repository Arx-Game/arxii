# Every technique must have an activatable cast; capability grants are not passive techniques

**Status:** Accepted (#3713, 2026-09-08). Related ADR-0248.

Every technique must be activatable. A `TechniqueCapabilityGrant` is the latent,
standing possession tier of a technique, not a separate passive technique category.
It may be weaker than an activated effect, but the technique must still have an
action template and a cast payload that can spend anima and be strengthened by
thread pulls.

A technique without an `action_template` is therefore **unfinished**. It is not a
valid character-creation pick and never appears in the player cast list. The
character-creation catalog and validator enforce the same rule as the runtime cast
gate. Staff wire authored catalog rows to the shared standalone cast template
through the `TechniqueAdmin` bulk action after reviewing the payload.

This rejects a standing-only exception: a binary capability with no activatable
magnitude is not a complete technique. Capability grants remain possession-side,
as settled by ADR-0248; activated capability changes ride an applied condition.
