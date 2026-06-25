# Multi-target casts validate a target list with per-target consent

A cast carries a list of target Personas through a validation seam (`validate_cast_target`), where
cardinality is enforced from the technique's authored `target_type` (SELF/SINGLE/multi) and each
target is evaluated independently so an AFK or non-consenting target blocks no one else; we rejected a
single-target-only model and an all-or-nothing consent gate. (Source #572 governs the Interaction
storage scale, not this seam — confirm the cast-target persistence shape against code before relying
on a specific field layout.)

> Status: accepted · Source: #572, magic/services/targeting.py · Confidence: derived-from-roadmap, verify against code
