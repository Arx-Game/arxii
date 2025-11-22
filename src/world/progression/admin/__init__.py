"""
Admin package for progression models.

This package organizes admin interfaces into logical modules:
- rewards_admin: Admin for XP and development points
- unlocks_admin: Admin for unlocks, requirements, and XP costs
"""

# Import all admin classes to register them with Django
from world.progression.admin.rewards_admin import *  # noqa: F403
from world.progression.admin.unlocks_admin import *  # noqa: F403
