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

Every stock Django admin page over shared rows has the same hazard on every refused save,
for its own form, every inline formset and a changelist's list edit. ``ArxAdminSite.register``
mixes ``RefusedSaveRestoreMixin`` into each such admin (#4626, ADR-4626): it keeps every row
the page binds a form to (``CacheGuard``) before validating, and puts the rows back in place
on a refusal or on a save that raises part way. The builder pages above flush instead; a
page of its own may take a ``CacheGuard`` too (the Soulfray Stage Builder does).
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

from django.contrib.admin import ModelAdmin
from django.db import router, transaction
from django.db.models import Model
from django.forms import BaseModelForm, BaseModelFormSet
from django.template.response import TemplateResponse
from evennia.utils.idmapper.models import SharedMemoryModel

from core.identity_map import CacheGuard


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


#: The guard of the admin POST this context is serving. Django calls the hooks that
#: bind (``_create_formsets``, the changelist formset's validation) and the one that
#: renders a refusal (``render_change_form``) from inside its own view, with no way to
#: pass an argument through, so the view that owns the POST sets this for its length.
_ADMIN_POST_GUARD: ContextVar[CacheGuard | None] = ContextVar("admin_post_guard", default=None)


@contextmanager
def _guarding_admin_post() -> Iterator[CacheGuard]:
    """A fresh ``CacheGuard`` for one admin POST; restores it if the POST raises.

    Django's admin save runs inside ``transaction.atomic``, so a raise rolls the
    database back. The rows' Python objects keep what validation and the save wrote,
    and this puts them back to match.
    """
    guard = CacheGuard()
    token = _ADMIN_POST_GUARD.set(guard)
    try:
        yield guard
    except BaseException:
        guard.restore()
        raise
    finally:
        _ADMIN_POST_GUARD.reset(token)


class _KeepsRowsBeforeValidating:
    """A changelist formset that keeps every row it edits before validating it."""

    def full_clean(self) -> None:
        guard = _ADMIN_POST_GUARD.get()
        if guard is not None:
            guard.keep(*(form.instance for form in self.forms))
        super().full_clean()


class RefusedSaveRestoreMixin:
    """A ``ModelAdmin`` mixin: a refused or failed save leaves every row as stored.

    Django's ``_changeform_view`` validates the change form and every inline formset on
    a POST, which writes the posted values onto the cached rows behind them, and the
    changelist's list edit does the same to each listed row. This keeps those rows (a
    ``CacheGuard``) before validation and puts them back in place, on the same objects,
    so the page on reload, the API, the game and any row already holding one read the
    stored values:

    - on a refusal, after the errors page renders (it shows the posted values);
      ``render_change_form`` is reached on a POST only when the change form was refused,
      and a refused list edit is the changelist page itself rather than a redirect;
    - on a save that raises part way, after Django's transaction rolls back.

    ``ArxAdminSite.register`` mixes this into every admin over shared rows; an admin
    never lists it itself. The guard test in ``web/admin/tests/test_refused_save_restore``
    fails for a registered admin without it.
    """

    def changeform_view(self, request, object_id=None, form_url="", extra_context=None):
        if request.method != "POST":
            return super().changeform_view(request, object_id, form_url, extra_context)
        with _guarding_admin_post():
            return super().changeform_view(request, object_id, form_url, extra_context)

    def _create_formsets(self, request, obj, change):
        """Keep the form's row and every inline row once bound, before any validates.

        ``_changeform_view`` calls this after binding the change form and before
        ``form.is_valid()``, so it is the one point where every row is bound and none
        is written yet.
        """
        formsets, inline_instances = super()._create_formsets(request, obj, change)
        guard = _ADMIN_POST_GUARD.get()
        if guard is not None:
            guard.keep(obj, *(form.instance for formset in formsets for form in formset.forms))
        return formsets, inline_instances

    def render_change_form(  # noqa: PLR0913 - ModelAdmin.render_change_form's own signature
        self, request, context, add=False, change=False, form_url="", obj=None
    ) -> TemplateResponse:
        response = super().render_change_form(
            request, context, add=add, change=change, form_url=form_url, obj=obj
        )
        guard = _ADMIN_POST_GUARD.get()
        if request.method != "POST" or guard is None:
            return response
        try:
            response.render()
        finally:
            guard.restore()
        return response

    def changelist_view(self, request, extra_context=None):
        if request.method != "POST" or "_save" not in request.POST:
            return super().changelist_view(request, extra_context)
        # One transaction for the whole POST, as Django gives the change form: its own
        # covers only the save loop, so a raise after it (the message, the redirect)
        # would otherwise leave the rows written and the guard putting them back.
        with (
            _guarding_admin_post() as guard,
            transaction.atomic(using=router.db_for_write(self.model)),
        ):
            response = super().changelist_view(request, extra_context)
            if isinstance(response, TemplateResponse):
                try:
                    response.render()
                finally:
                    guard.restore()
            return response

    def get_changelist_formset(self, request, **kwargs):
        formset_class = super().get_changelist_formset(request, **kwargs)
        return type(formset_class.__name__, (_KeepsRowsBeforeValidating, formset_class), {})


def edits_shared_rows(model: type[Model], admin_class: type[ModelAdmin]) -> bool:
    """Whether an admin for ``model`` binds forms to identity-mapped rows: its own model
    or a model one of its declared inlines edits is a ``SharedMemoryModel``."""
    inline_models = [inline.model for inline in admin_class.inlines]
    return any(issubclass(m, SharedMemoryModel) for m in (model, *inline_models))


def with_refused_save_restore(
    model: type[Model], admin_class: type[ModelAdmin]
) -> type[ModelAdmin]:
    """``admin_class`` with ``RefusedSaveRestoreMixin`` first in its MRO, when it edits
    shared rows and does not already have it; otherwise ``admin_class`` unchanged.

    First in the MRO so an admin's own ``changeform_view``, ``render_change_form`` or
    ``changelist_view`` runs inside the guard and cannot skip it.
    """
    if issubclass(admin_class, RefusedSaveRestoreMixin) or not edits_shared_rows(
        model, admin_class
    ):
        return admin_class
    return type(
        admin_class.__name__,
        (RefusedSaveRestoreMixin, admin_class),
        {
            "__module__": admin_class.__module__,
            "__qualname__": admin_class.__qualname__,
            "__doc__": admin_class.__doc__,
        },
    )
