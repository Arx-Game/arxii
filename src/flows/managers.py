from django.db import models
from django.utils.functional import cached_property

from flows.consts import PRE_FLIGHT_FLOW_NAME


class FlowDefinitionManager(models.Manager):
    """
    Manager for FlowDefinition so we can fetch well-known flows by name.
    """

    @cached_property
    def preflight_flow(self):
        """
        The single PreflightFlow definition.
        Cached on first access for the lifetime of this manager.
        """
        return self.get(name=PRE_FLIGHT_FLOW_NAME)
