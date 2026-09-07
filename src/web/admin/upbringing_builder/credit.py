"""Credit stamping for the Upbringing Builder (#3660): the Workbench's Save-and-credit rule.

The per-row stamp itself lives in ``web.admin.authoring.credit`` (#3675), shared
with the tradition slate page - this module only knows which rows make up one
route.
"""

from __future__ import annotations

from web.admin.authoring.credit import (
    stamp_reviewed as _stamp_reviewed_row,
    stamp_written as _stamp_written_row,
)
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
    for row in _rows(template):
        _stamp_written_row(row, contributor)


def stamp_reviewed(template: OriginTemplate, contributor: ContentContributor) -> None:
    """Every row on the route is reviewed by ``contributor`` today; authorship untouched."""
    for row in _rows(template):
        _stamp_reviewed_row(row, contributor)
