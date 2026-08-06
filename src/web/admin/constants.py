from django.db import models


class ImportAction(models.TextChoices):
    SKIP = "skip", "Skip"
    REPLACE = "replace", "Replace"
    MERGE = "merge", "Merge"


class BacklogStatusFilter(models.TextChoices):
    """`?status=` values the Authoring Workbench queue panel filters on (#3019)."""

    PLACEHOLDER = "placeholder", "Placeholder"
    UNWRITTEN = "unwritten", "Unwritten"
    UNREVIEWED = "unreviewed", "Unreviewed"
