"""Service layer for the agriculture system.

Re-exports the public API so callers import from ``world.agriculture.services``
rather than individual submodules.
"""

from world.agriculture.services.collection import collect_field_food
from world.agriculture.services.consumption import domain_consumption_tick
from world.agriculture.services.domain import (
    max_food_capacity,
    resolve_domain_for_feature,
)
from world.agriculture.services.handlers import (
    handle_field_progression,
    handle_granary_progression,
)
from world.agriculture.services.production import (
    field_production_tick,
    get_food_config,
)
from world.agriculture.services.provisioning import provision_army, provision_ship_leg
from world.agriculture.services.transfer import transfer_food

__all__ = [
    "collect_field_food",
    "domain_consumption_tick",
    "field_production_tick",
    "get_food_config",
    "handle_field_progression",
    "handle_granary_progression",
    "max_food_capacity",
    "provision_army",
    "provision_ship_leg",
    "resolve_domain_for_feature",
    "transfer_food",
]
