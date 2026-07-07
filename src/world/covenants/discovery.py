"""Backwards-compatible shim for the crossing ceremony (ADR-0094, #1987).

The ceremony logic has been generalized and moved to
``world.magic.crossing``. This module re-exports
``execute_crossing_ceremonies`` as ``fire_variant_discoveries`` for
backwards compatibility with existing imports (tests, docs, call sites).

New code should import from ``world.magic.crossing.ceremony`` directly.

See ADR-0094 for the cross-kind contract and ADR-0055 for the original
specialization engine.
"""

from __future__ import annotations

from world.magic.crossing.ceremony import execute_crossing_ceremonies

# Backwards-compatible alias — the old name referenced "variants" which only
# applies to 2 of 9 target kinds. New code should use ``execute_crossing_ceremonies``.
fire_variant_discoveries = execute_crossing_ceremonies

__all__ = ["execute_crossing_ceremonies", "fire_variant_discoveries"]
