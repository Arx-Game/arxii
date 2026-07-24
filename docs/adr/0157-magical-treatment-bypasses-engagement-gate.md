# Magical treatment bypasses the engagement gate

## Decision

`perform_treatment` gains a `skip_engagement_gate: bool = False` parameter. The
technique-cast path (`apply_technique_treatments`) passes `True`; the mundane
`treat_condition` scene action leaves it `False` (default — unchanged behavior).

Magical treatment works in combat — the engagement gate that blocks mundane
treatment is lifted for the technique-cast path. All other bounds are preserved:
the per-healer-once-per-wound bound, the never-to-full fraction (ADR-0156), the
treatment's own check roll, resonance/anima costs, `TreatmentAttempt` record, and
failure backlash.

## Rationale

Healers are a core fantasy. Magical healing can be ultra-fast via magic — it
takes the caster's combat round (the technique cast already consumes the round).
The engagement gate exists for mundane treatment because physical first-aid
cannot reasonably be performed mid-fight; magic has no such constraint.

## Rejected alternatives

- **Remove the engagement gate from perform_treatment entirely** — would also
  lift the restriction for mundane treatment, removing a design constraint the
  mundane path relies on.
- **Build a separate magical-treatment service** — would risk diverging from the
  bounded-mend invariant; the whole point of #2668 is to route through the
  existing `perform_treatment` seam.

> Status: accepted · Source: issue #2668 · Related: ADR-0156 (double-bounded wound mend)
