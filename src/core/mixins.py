"""
Shared model mixins for Arx II.
"""

from __future__ import annotations

from typing import Any

from django.core.exceptions import ValidationError


class DiscriminatorMixin:
    """Mixin for models with a type field that selects which FK is active.

    Subclasses define:
        DISCRIMINATOR_FIELD: str — the name of the type/choice field
        DISCRIMINATOR_MAP: dict[str, str] — enum value -> FK field name
    """

    DISCRIMINATOR_FIELD: str
    DISCRIMINATOR_MAP: dict[str, str]

    def get_active_target(self) -> Any | None:
        """Return the object referenced by the currently-active FK."""
        field_name = self.DISCRIMINATOR_MAP.get(getattr(self, self.DISCRIMINATOR_FIELD))
        if field_name is None:
            return None
        return getattr(self, field_name)

    def get_active_target_name(self) -> str:
        """Return the name of the active target, or '(deleted)' if null."""
        target = self.get_active_target()
        if target is None:
            return "(deleted)"
        return str(target.name)

    def clean(self) -> None:
        super().clean()  # type: ignore[misc]
        discriminator_value = getattr(self, self.DISCRIMINATOR_FIELD)
        expected_field = self.DISCRIMINATOR_MAP.get(discriminator_value)
        if not expected_field:
            return

        errors: dict[str, str] = {}

        # Expected FK must be set
        if getattr(self, expected_field) is None:
            errors[expected_field] = (
                f"Required when {self.DISCRIMINATOR_FIELD} is {discriminator_value}."
            )

        # Other FKs must be null
        for disc_value, field_name in self.DISCRIMINATOR_MAP.items():
            if disc_value != discriminator_value and getattr(self, field_name) is not None:
                errors[field_name] = (
                    f"Must be null when {self.DISCRIMINATOR_FIELD} is {discriminator_value}."
                )

        if errors:
            raise ValidationError(errors)

    def save(self, *args: object, **kwargs: object) -> None:
        self.clean()
        super().save(*args, **kwargs)  # type: ignore[misc]
