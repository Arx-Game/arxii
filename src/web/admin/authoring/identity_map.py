"""Putting the identity map back after a refused builder save.

Validating a ``ModelForm`` writes the posted values onto ``form.instance`` (Django's
``_post_clean``), and for a saved row that instance is the one SharedMemoryModel's
identity map hands to every later reader in the process. A refused save would leave the
refused values there: the next page load shows them as if saved, and the corrected
save compares against them, finds no change for that row and skips the write while
reporting success. Render the errors first (they need the posted values), then call
``flush_refused_instances`` so the next reader loads what the database holds.
"""

from __future__ import annotations

from django.forms import BaseModelForm, BaseModelFormSet


def flush_refused_instances(*bound: BaseModelForm | BaseModelFormSet) -> None:
    """Drop every saved row behind these bound forms or formsets from the identity map.

    An unsaved row (no pk) was never cached, so it is skipped.
    """
    for item in bound:
        forms = item.forms if isinstance(item, BaseModelFormSet) else [item]
        for form in forms:
            if form.instance.pk is not None:
                form.instance.flush_from_cache(force=True)
