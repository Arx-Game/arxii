"""Credit stamping for the Upbringing Builder (#3660): the Workbench's Save-and-credit rule."""

from __future__ import annotations

from django.utils import timezone

from world.character_creation.models import (
    OriginTemplate,
    OriginTemplateSlot,
    OriginTemplateSlotChoice,
)
from world.contributors.models import ContentContributor


def _rows(template: OriginTemplate) -> list:
    slots = list(OriginTemplateSlot.objects.filter(template=template))
    choices = list(OriginTemplateSlotChoice.objects.filter(slot__in=slots))
    return [template, *slots, *choices]


def stamp_written(template: OriginTemplate, contributor: ContentContributor) -> None:
    """Every row on the route is written by ``contributor`` today."""
    today = timezone.now().date()
    for row in _rows(template):
        row.written_by = contributor
        row.written_on = today
        row.save(update_fields=["written_by", "written_on"])


def stamp_reviewed(template: OriginTemplate, contributor: ContentContributor) -> None:
    """Every row on the route is reviewed by ``contributor`` today; authorship untouched."""
    today = timezone.now().date()
    for row in _rows(template):
        row.reviewed_by = contributor
        row.reviewed_on = today
        row.save(update_fields=["reviewed_by", "reviewed_on"])
