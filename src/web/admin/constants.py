from django.db import models


class ImportAction(models.TextChoices):
    SKIP = "skip", "Skip"
    REPLACE = "replace", "Replace"
    MERGE = "merge", "Merge"
