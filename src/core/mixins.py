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

    Subclasses that need MULTIPLE discriminators (e.g., parent type AND
    holder type) should override ``clean()`` to call
    ``_validate_discriminator`` for each pair, merge the resulting error
    dicts, and raise a single ``ValidationError`` so all field errors
    surface at once.
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
        # Most discriminator targets expose .name (Persona, Area, Organization);
        # fall back to str(target) for targets like RoomProfile that don't.
        try:
            return str(target.name)
        except AttributeError:
            return str(target)

    @staticmethod
    def _is_unset(value: Any) -> bool:
        """Treat both ``None`` and the empty string as unset.

        FK fields are ``None`` when unset; CharField fields default to ``""``.
        Discriminators target either kind, so both forms count as "no value here."
        """
        return value is None or value == ""

    def _validate_discriminator(
        self, discriminator_field: str, discriminator_map: dict[str, str]
    ) -> dict[str, str]:
        """Return field-keyed errors for a discriminator/FK group.

        Verifies that the discriminator value is in ``discriminator_map``
        AND that exactly one matching target is set. Returns an empty dict on
        success. Does NOT raise — caller merges/raises.
        """
        discriminator_value = getattr(self, discriminator_field)
        expected_field = discriminator_map.get(discriminator_value)
        if expected_field is None:
            if discriminator_value:
                return {
                    discriminator_field: (
                        f"Unknown value {discriminator_value!r}; "
                        f"must be one of {list(discriminator_map)}."
                    )
                }
            return {discriminator_field: "This field is required."}

        errors: dict[str, str] = {}
        if self._is_unset(getattr(self, expected_field)):
            errors[expected_field] = (
                f"Required when {discriminator_field} is {discriminator_value}."
            )
        for value, field_name in discriminator_map.items():
            if value != discriminator_value and not self._is_unset(getattr(self, field_name)):
                errors[field_name] = (
                    f"Must be null when {discriminator_field} is {discriminator_value}."
                )
        return errors

    def clean(self) -> None:
        super().clean()  # type: ignore[misc]
        errors = self._validate_discriminator(self.DISCRIMINATOR_FIELD, self.DISCRIMINATOR_MAP)
        if errors:
            raise ValidationError(errors)

    def save(self, *args: object, **kwargs: object) -> None:
        self.clean()
        super().save(*args, **kwargs)  # type: ignore[misc]
