from django.db import models


class ResponseType(models.TextChoices):
    """Type of journal response."""

    PRAISE = "praise", "Praise"
    RETORT = "retort", "Retort"


# Weekly XP awards for journal actions
JOURNAL_POST_XP = [5, 2, 1]  # 1st, 2nd, 3rd post per week
PRAISE_GIVEN_XP = 2
PRAISE_RECEIVED_XP = 1
RETORT_GIVEN_XP = 1
RETORT_RECEIVED_XP = 3
