from django.db import models


class NarrativeCategory(models.TextChoices):
    STORY = "story", "Story update"
    ATMOSPHERE = "atmosphere", "Atmosphere"
    VISIONS = "visions", "Visions"
    HAPPENSTANCE = "happenstance", "Happenstance"
    SYSTEM = "system", "System"
