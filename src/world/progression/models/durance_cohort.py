"""Models for the Durance intake cohort (#2479)."""

from __future__ import annotations

from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel


class DuranceCohort(SharedMemoryModel):
    """An intake cohort for the Ritual of the Durance.

    A cohort is a batch of newly-registered Gifted who passed through the
    Academy together. It hangs off the Shroudwatch Academy Organization so
    membership is the persistent peer-group surface future systems can query.
    """

    organization = models.ForeignKey(
        "societies.Organization",
        on_delete=models.PROTECT,
        related_name="durance_cohorts",
        help_text="The Academy organization this cohort belongs to.",
    )
    name = models.CharField(max_length=255, blank=True)
    opened_at = models.DateTimeField(auto_now_add=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    enrollment_scene = models.ForeignKey(
        "scenes.Scene",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="durance_cohorts_opened_here",
    )

    class Meta:
        ordering = ["-opened_at"]

    def __str__(self) -> str:
        return self.name or f"Intake cohort {self.pk}"


class CohortEnrollment(SharedMemoryModel):
    """Bridge table linking a Persona to a DuranceCohort."""

    cohort = models.ForeignKey(
        DuranceCohort,
        on_delete=models.CASCADE,
        related_name="enrollments",
    )
    persona = models.ForeignKey(
        "scenes.Persona",
        on_delete=models.CASCADE,
        related_name="cohort_enrollments",
    )
    enrolled_at = models.DateTimeField(auto_now_add=True)
    enrollment_scene = models.ForeignKey(
        "scenes.Scene",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="cohort_enrollments_here",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["cohort", "persona"],
                name="cohort_enrollment_unique",
            ),
        ]
        ordering = ["-enrolled_at"]

    def __str__(self) -> str:
        return f"{self.persona} in {self.cohort}"
