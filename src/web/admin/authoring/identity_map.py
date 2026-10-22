"""Putting the identity map back after a refused builder save.

Validating a ``ModelForm`` writes the posted values onto ``form.instance`` (Django's
``_post_clean``), and for a saved row that instance is the one SharedMemoryModel's
identity map hands to every later reader in the process. A refused save would leave the
refused values there: the next page load shows them as if saved, and the corrected
save compares against them, finds no change for that row and skips the write while
reporting success. Render the errors first (they need the posted values), then call
``flush_refused_instances`` so the next reader loads what the database holds.

A page that assigns posted values onto a row itself, outside any form, and then calls
``full_clean()`` (the authoring workbench's row editor, #4543) has the same hazard and
passes the row directly.
"""

from __future__ import annotations

from django.forms import BaseModelForm, BaseModelFormSet
from evennia.utils.idmapper.models import SharedMemoryModel


def flush_refused_instances(*bound: BaseModelForm | BaseModelFormSet | SharedMemoryModel) -> None:
    """Drop every saved row behind these bound forms, formsets or rows from the identity map.

    A row passed directly is one the caller assigned posted values onto before a refused
    ``full_clean()``. An unsaved row (no pk) was never cached, so it is skipped.
    """
    for item in bound:
        if isinstance(item, SharedMemoryModel):
            instances = [item]
        elif isinstance(item, BaseModelFormSet):
            instances = [form.instance for form in item.forms]
        else:
            instances = [item.instance]
        for instance in instances:
            if instance.pk is not None:
                instance.flush_from_cache(force=True)
