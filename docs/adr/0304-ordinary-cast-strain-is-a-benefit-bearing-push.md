# ADR-0304: Ordinary-cast strain is a benefit-bearing push

## Status

Accepted for issue #3912.

## Decision

A non-zero ordinary-cast strain commitment spends extra anima and immediately
increases technique power through the shared `use_technique` seam. The conversion
uses the authored `StrainConfig` diminishing-return curve and is applied exactly
once. It does not change the check modifier or turn a failed check into a success.
Clash contributions enter the same seam and no longer convert strain in the caller.

The server keeps the declared commitment for audit. Non-lethal encounters clamp the
actual cost to available anima and report the effective commitment used for power and
fatigue. Lethal casts preserve intentional focused-clash overburn semantics. Soulfray
comes only from the resulting anima deficit; strain has no second Soulfray charge.

## Player contract

The combat action payload exposes the base effective cost, anima cap, and curve knobs.
The combat surface shows `+N anima`, `+B(N) power`, projected cost, and a warning when
the push can empty anima. Zero strain is shown as **No push: baseline power**. Results
and action outcome details expose declared strain, effective strain, and
`strain_power_bonus`. Scene-action enhancement strain remains cost/Soulfray-only until
a separate power-propagation design is approved.
