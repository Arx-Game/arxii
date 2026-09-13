from django.db import models


class ImportAction(models.TextChoices):
    SKIP = "skip", "Skip"
    REPLACE = "replace", "Replace"
    MERGE = "merge", "Merge"


class BacklogStatusFilter(models.TextChoices):
    """`?status=` values the Authoring Workbench queue panel filters on (#3019, #3828).

    Declaration order is dropdown order. An absent `?status=` resolves to
    `UNWRITTEN` (`DEFAULT_BACKLOG_STATUS`), so `ALL` is the explicit way to see
    everything. `UNREVIEWED` means *written and not yet reviewed* - the same
    partition the stock changelist's `CreditStatusListFilter` calls "written" -
    so a review pass never lists rows nobody has written yet (#3828).
    """

    UNWRITTEN = "unwritten", "To write"
    UNREVIEWED = "unreviewed", "To review"
    PLACEHOLDER = "placeholder", "Placeholder"
    ALL = "all", "All"


#: What the queue shows when the URL carries no `?status=` at all (#3828): a
#: writing session opens on the work, not on the whole backlog.
DEFAULT_BACKLOG_STATUS = BacklogStatusFilter.UNWRITTEN
