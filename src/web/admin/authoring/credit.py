"""Row-level credit stamping shared by every authoring page (#3675).

Promoted from ``upbringing_builder.credit``'s per-row loop body: any single
``CreditedContent`` row can be stamped this same way, whether it belongs to a
whole route (the Upbringing Builder, which loops its own rows and calls this
per row) or a handful of standard-lines rows edited straight off a formset
(the tradition slate page).
"""

from __future__ import annotations

from django.utils import timezone

from world.contributors.models import ContentContributor, CreditedContent


def stamp_written(row: CreditedContent, contributor: ContentContributor) -> None:
    """``row`` is written by ``contributor`` today."""
    row.written_by = contributor
    row.written_on = timezone.now().date()
    row.save(update_fields=["written_by", "written_on"])


def stamp_reviewed(row: CreditedContent, contributor: ContentContributor) -> None:
    """``row`` is reviewed by ``contributor`` today; authorship untouched."""
    row.reviewed_by = contributor
    row.reviewed_on = timezone.now().date()
    row.save(update_fields=["reviewed_by", "reviewed_on"])
