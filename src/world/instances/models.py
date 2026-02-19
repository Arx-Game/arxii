from django.core.exceptions import ValidationError
from django.db import models

from world.instances.constants import InstanceStatus


class InstancedRoom(models.Model):
    """Tracks the lifecycle of a temporary instanced room."""

    room = models.OneToOneField(
        "objects.ObjectDB",
        on_delete=models.CASCADE,
        related_name="instance_data",
    )
    owner = models.ForeignKey(
        "character_sheets.CharacterSheet",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="owned_instances",
    )
    # TODO: Add GM owner FK when GM/storyteller system is designed.
    # GM-created instances (story scenes, event rooms) will need a
    # separate FK to the GM model. Query pattern: "all active instances
    # owned by this GM" for their management dashboard.
    return_location = models.ForeignKey(
        "objects.ObjectDB",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    # TODO: Replace with FK to mission/template model when missions
    # system is designed. Missions will query instances by source to
    # manage active mission rooms for a player.
    source_key = models.CharField(max_length=200, blank=True)
    status = models.CharField(
        max_length=20,
        choices=InstanceStatus.choices,
        default=InstanceStatus.ACTIVE,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Instanced Room"
        verbose_name_plural = "Instanced Rooms"

    def __str__(self):
        return f"Instance: {self.room.db_key} ({self.get_status_display()})"

    def clean(self):
        if self.return_location_id is not None:
            loc = self.return_location
            typeclass_path = loc.db_typeclass_path if loc else ""
            if not typeclass_path.startswith("typeclasses.rooms."):
                msg = "return_location must be a Room typeclass."
                raise ValidationError({"return_location": msg})
