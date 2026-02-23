from __future__ import annotations

from functools import cached_property
from typing import TYPE_CHECKING

from django.db import models

from flows.consts import PRE_FLIGHT_FLOW_NAME

if TYPE_CHECKING:
    from flows.models.flows import FlowDefinition


class FlowDefinitionManager(models.Manager):
    """
    Manager for FlowDefinition so we can fetch well-known flows by name.
    """

    @cached_property
    def preflight_flow(self) -> FlowDefinition:
        """
        The single PreflightFlow definition.
        Cached on first access for the lifetime of this manager.
        """
        return self.get(name=PRE_FLIGHT_FLOW_NAME)
