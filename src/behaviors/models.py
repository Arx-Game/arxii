from __future__ import annotations

"""Models for reusable behavior packages."""

from functools import cached_property
from importlib import import_module
from typing import Callable

from django.db import models
from evennia.objects.models import ObjectDB
from evennia.utils.idmapper.models import SharedMemoryModel


class BehaviorPackageDefinition(SharedMemoryModel):
    """Template describing a reusable behavior package."""

    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True, null=True)
    service_function_path = models.CharField(
        max_length=255,
        help_text="Python path to the service function for this package.",
    )

    def __str__(self) -> str:
        return self.name

    @cached_property
    def service_function(self) -> Callable:
        """Import and cache the service function."""

        module_path, func_name = self.service_function_path.rsplit(".", 1)
        module = import_module(module_path)
        return getattr(module, func_name)

    def get_service_function(self) -> Callable:
        """Return the service function for this package."""

        return self.service_function


class BehaviorPackageInstance(SharedMemoryModel):
    """Active behavior package attached to an object."""

    definition = models.ForeignKey(
        BehaviorPackageDefinition,
        on_delete=models.CASCADE,
        related_name="instances",
    )
    obj = models.ForeignKey(
        ObjectDB,
        on_delete=models.CASCADE,
        related_name="behavior_packages",
    )
    hook = models.CharField(
        max_length=100,
        help_text="Name of the hook where this package applies.",
    )
    data = models.JSONField(blank=True, null=True)

    def __str__(self) -> str:
        return f"{self.definition.name} for {self.obj.key}"

    def get_hook(self, name: str) -> Callable | None:
        """Return the service function for ``name`` if this instance uses it."""

        if name != self.hook:
            return None

        return self.definition.get_service_function()

    def get_from_data(self, key: str):
        """Return ``key`` from ``data`` if present and ``data`` is a mapping."""

        if isinstance(self.data, dict):
            return self.data.get(key)
        return None
