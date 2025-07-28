from __future__ import annotations

"""Models for reusable behavior packages."""

from importlib import import_module
from typing import Any, Callable, Dict

from django.db import models
from evennia.objects.models import ObjectDB
from evennia.utils.idmapper.models import SharedMemoryModel


class BehaviorPackageDefinition(SharedMemoryModel):
    """Template describing a reusable behavior package."""

    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True, null=True)
    service_function_path = models.CharField(
        max_length=255,
        help_text="Python path to the service module implementing hooks.",
    )

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._hooks: Dict[str, Callable] | None = None

    def __str__(self) -> str:
        return self.name

    @property
    def hooks(self) -> Dict[str, Callable]:
        """Return hook functions provided by the service module."""
        if self._hooks is None:
            module = import_module(self.service_function_path)
            self._hooks = module.hooks
        return self._hooks

    def get_hook(self, name: str) -> Callable | None:
        """Return a hook function if available."""
        return self.hooks.get(name)


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
    data = models.JSONField(blank=True, null=True)

    def __str__(self) -> str:
        return f"{self.definition.name} for {self.obj.key}"

    def get_hook(self, name: str) -> Callable | None:
        """Return the hook function for ``name`` if available."""
        return self.definition.get_hook(name)
