"""Service layer for the agriculture system.

Re-exports the public API so callers import from ``world.agriculture.services``
rather than individual submodules.
"""

from world.agriculture.services.production import (
    field_production_tick,
    get_food_config,
)

__all__ = [
    "field_production_tick",
    "get_food_config",
]
