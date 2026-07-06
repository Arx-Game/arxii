"""Crossing ceremony registry and handlers (ADR-0094, #1987).

Generalizes the discovery ceremony (formerly ``fire_variant_discoveries``) so
every ``TargetKind`` dispatches to a handler at PathStage crossing levels
(3, 6, 11, 16, 21).

The ceremony *beat* (achievement + codex unlock + narrative message) is shared;
the *effect shape* (variant-discovery, additive, or unlock) is per-kind.

See:
    - ADR-0094 — the cross-kind contract.
    - ADR-0055 — the original "one specialization engine" for Gift/Path/Role.
    - ``world.covenants.discovery`` — backwards-compatible shim re-exporting
      ``fire_variant_discoveries``.
"""
