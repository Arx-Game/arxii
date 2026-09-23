"""Django relation fields for partitioned scene metadata."""

from typing import Any

from django.db import models
from django.db.models.fields.related import ForeignObject
from django.db.models.fields.related_descriptors import ForwardManyToOneDescriptor


class CompositeForwardManyToOneDescriptor(ForwardManyToOneDescriptor):
    """Forward descriptor that rejects scalar-id cache misresolution."""

    def __get__(self, instance: Any, cls: type[Any] | None = None) -> Any:
        related = super().__get__(instance, cls)
        if instance is None or related is None:
            return related
        for local_field, remote_field in self.field.related_fields:
            if getattr(instance, local_field.attname) != getattr(related, remote_field.attname):
                self.field.delete_cached_value(instance)
                raise self.RelatedObjectDoesNotExist
        return related


class CompositeForeignKey(ForeignObject):
    """ORM-only multi-column relation; PostgreSQL owns physical integrity.

    Django does not emit a database constraint for ``ForeignObject``. The
    corresponding PostgreSQL composite FK is maintained by the scene SQL
    migration. ``DO_NOTHING`` leaves delete/cascade behavior to that exact
    database constraint instead of Django's scalar-id collector.
    """

    forward_related_accessor_class = CompositeForwardManyToOneDescriptor

    def __init__(
        self,
        to: Any,
        *,
        from_fields: list[str] | tuple[str, ...],
        to_fields: list[str] | tuple[str, ...],
        related_name: str | None = None,
        **kwargs: Any,
    ) -> None:
        kwargs.pop("on_delete", None)
        super().__init__(
            to,
            on_delete=models.DO_NOTHING,
            from_fields=from_fields,
            to_fields=to_fields,
            related_name=related_name,
            **kwargs,
        )
