"""
Admin package for progression models.

This package organizes admin interfaces into logical modules:
- rewards_admin: Admin for XP and development points
- kudos_admin: Admin for kudos points and categories
- unlocks_admin: Admin for unlocks, requirements, and XP costs
- paths_admin: Admin for character path history
"""

# Import all admin classes to register them with Django
from world.progression.admin.kudos_admin import *  # noqa: F403
from world.progression.admin.paths_admin import *  # noqa: F403
from world.progression.admin.rewards_admin import *  # noqa: F403
from world.progression.admin.unlocks_admin import *  # noqa: F403
