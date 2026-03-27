from django.db import models


class EventStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    SCHEDULED = "scheduled", "Scheduled"
    ACTIVE = "active", "Active"
    COMPLETED = "completed", "Completed"
    CANCELLED = "cancelled", "Cancelled"


class InvitationTargetType(models.TextChoices):
    PERSONA = "persona", "Persona"
    ORGANIZATION = "organization", "Organization"
    SOCIETY = "society", "Society"
