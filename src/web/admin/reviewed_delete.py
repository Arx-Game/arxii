"""A reviewed delete for a `ModelAdmin` whose rows other rows depend on (#4064).

Django's delete view stops at a ``PROTECT`` link: it names the blocking rows and offers
nothing. For a row staff deliberately want gone (a placeholder organization that owns a
domain, is liege to a house and is named by a template) that is a dead end, and two of
the kinds that block most often had no admin page to go to at all.

``ReviewedDeleteMixin`` replaces the dead end with a plan the deleter reads and decides
row by row. Nothing here relaxes ``PROTECT``: every other delete path (the shell,
services, the inline tickbox, the bulk action) is still refused. The mixin is a way
*through* the guard for a superuser, one row at a time, with the organization's name
typed back:

- **Deleted with it**: the cascade, as Django lists it.
- **Blocking rows**: every protected row, each with a choice. *Detach* clears the link
  and keeps the row, offered only when the link is nullable and the row still validates
  without it. *Delete* removes the row and everything that cascades from it; a row chosen
  for delete is collected in the next round, so its own protectors join the list.
- **Nothing is written** until every blocking row has a choice and the typed name
  matches; then it all happens in one transaction or not at all.

The plan is never stored: it is rebuilt from the posted choices on every request, so a
row added between review and confirm shows up undecided and refuses the confirm.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from django.contrib import messages
from django.contrib.admin.utils import NestedObjects, quote, unquote
from django.core.exceptions import FieldDoesNotExist, ValidationError
from django.db import IntegrityError, router, transaction
from django.db.models import ProtectedError
from django.db.models.deletion import PROTECT
from django.template.response import TemplateResponse
from django.urls import NoReverseMatch, reverse
from django.utils.html import format_html
from django.utils.text import capfirst

if TYPE_CHECKING:
    from django.db.models import Model
    from django.http import HttpRequest, HttpResponse

DETACH = "detach"
DELETE = "delete"
CHOICE_PREFIX = "choice-"
REVIEW_FIELD = "review"
REVIEW_UPDATE = "update"
REVIEW_CONFIRM = "confirm"
TYPED_NAME_FIELD = "typed_name"
REVIEW_TEMPLATE = "admin/reviewed_delete_confirmation.html"
_UNDECIDED = "Decide what happens to every blocking row first."
_NAME_MISMATCH = "The name you typed does not match; nothing was deleted."
_STALE = "Something changed while you were reviewing; look again before deleting."
_REQUIRED = "This link is required; the row cannot stand without it."


def row_key(obj: Model) -> str:
    """The posted-form identity of a blocking row: ``app_label.model:pk``."""
    return f"{obj._meta.label_lower}:{obj.pk}"


@dataclass(frozen=True)
class BlockingRow:
    """One protected row in the plan and what the deleter decided for it."""

    key: str
    obj: Any
    kind: str
    label: str
    admin_url: str | None
    written_by: str
    links: tuple[str, ...]
    can_detach: bool
    detach_note: str
    choice: str | None
    forced: bool
    round: int

    @property
    def decided(self) -> bool:
        return self.forced or self.choice in (DETACH, DELETE)

    @property
    def offers(self) -> tuple[str, ...]:
        if self.forced:
            return ()
        return (DETACH, DELETE) if self.can_detach else (DELETE,)


@dataclass
class DeletePlan:
    """Everything a confirm would write, built from the root and the posted choices."""

    root: Any
    collector: NestedObjects
    blocking: list[BlockingRow] = field(default_factory=list)

    @property
    def detached(self) -> list[BlockingRow]:
        return [row for row in self.blocking if row.choice == DETACH and not row.forced]

    @property
    def deleted_rows(self) -> list[BlockingRow]:
        """Blocking rows to remove before the root, deepest round first."""
        chosen = [row for row in self.blocking if row.forced or row.choice == DELETE]
        return sorted(chosen, key=lambda row: -row.round)

    @property
    def undecided(self) -> list[BlockingRow]:
        return [row for row in self.blocking if not row.decided]

    @property
    def complete(self) -> bool:
        return not self.undecided

    def nested(self, format_callback) -> list:
        return self.collector.nested(format_callback)

    def model_count(self) -> list[tuple[str, int]]:
        return [
            (str(model._meta.verbose_name_plural), len(objs))
            for model, objs in self.collector.model_objs.items()
        ]


def _protect_links(obj: Model, removed: dict[type, set]) -> tuple[str, ...]:
    """The FK/O2O fields on ``obj`` that PROTECT a row being removed."""
    links = []
    for f in obj._meta.concrete_fields:
        if not (f.many_to_one or f.one_to_one) or f.remote_field is None:
            continue
        if f.remote_field.on_delete is not PROTECT:
            continue
        target_pks = removed.get(f.related_model, set())
        if getattr(obj, f.attname) in target_pks:
            links.append(f.name)
    return tuple(links)


def _detach_verdict(obj: Model, links: tuple[str, ...]) -> tuple[bool, str]:
    """Whether the row survives with its links cleared, and why not when it does not.

    Works on a copy: the instance is identity-mapped and must not be mutated for a
    check. A nullable link whose row then fails ``clean()`` or a constraint (a row
    that must point at exactly one of two holders) is delete-only, with the message.
    """
    for name in links:
        if not obj._meta.get_field(name).null:
            return False, _REQUIRED
    probe = copy.copy(obj)
    for name in links:
        setattr(probe, obj._meta.get_field(name).attname, None)
        setattr(probe, name, None)
    try:
        probe.clean()
        probe.validate_constraints()
    except ValidationError as exc:
        return False, "; ".join(exc.messages)
    return True, ""


def _written_by(obj: Model) -> str:
    """The credited author's name, for a CreditedContent row; empty for any other."""
    from world.contributors.models import CreditedContent  # noqa: PLC0415

    if not isinstance(obj, CreditedContent) or obj.written_by_id is None:
        return ""
    return str(obj.written_by)


def _admin_url(admin_site, obj: Model) -> str | None:
    if not admin_site.is_registered(obj._meta.model):
        return None
    try:
        return reverse(
            f"{admin_site.name}:{obj._meta.app_label}_{obj._meta.model_name}_change",
            args=(quote(obj.pk),),
        )
    except NoReverseMatch:
        return None


def choices_from(post) -> dict[str, str]:
    """The ``choice-<key>`` fields of a posted review, unknown values dropped."""
    return {
        name[len(CHOICE_PREFIX) :]: value
        for name, value in post.items()
        if name.startswith(CHOICE_PREFIX) and value in (DETACH, DELETE)
    }


def build_delete_plan(root: Model, choices: dict[str, str], admin_site) -> DeletePlan:
    """Collect the root, then each row chosen for delete, round by round, to a fixpoint."""
    collector = NestedObjects(using=router.db_for_write(root._meta.model))
    collector.collect([root])
    plan = DeletePlan(root=root, collector=collector)
    seen_rounds: dict[str, int] = {}
    collected: set[str] = {row_key(root)}
    round_no = 1
    while True:
        removed = {model: {obj.pk for obj in objs} for model, objs in collector.model_objs.items()}
        for obj in sorted(collector.protected, key=lambda o: (o._meta.label, o.pk)):
            seen_rounds.setdefault(row_key(obj), round_no)
        new_deletes = [
            obj
            for obj in collector.protected
            if choices.get(row_key(obj)) == DELETE
            and row_key(obj) not in collected
            and obj.pk not in removed.get(obj._meta.model, set())
        ]
        if not new_deletes:
            break
        for obj in sorted(new_deletes, key=lambda o: (o._meta.label, o.pk)):
            collector.collect([obj])
            collected.add(row_key(obj))
        round_no += 1

    removed = {model: {obj.pk for obj in objs} for model, objs in collector.model_objs.items()}
    rows = []
    for obj in collector.protected:
        key = row_key(obj)
        forced = obj.pk in removed.get(obj._meta.model, set()) and key not in collected
        links = _protect_links(obj, removed)
        can_detach, note = (False, "") if forced else _detach_verdict(obj, links)
        choice = choices.get(key)
        if key in collected:
            choice = DELETE
        elif choice == DETACH and not can_detach:
            choice = None
        rows.append(
            BlockingRow(
                key=key,
                obj=obj,
                kind=capfirst(str(obj._meta.verbose_name)),
                label=str(obj),
                admin_url=_admin_url(admin_site, obj),
                written_by=_written_by(obj),
                links=links,
                can_detach=can_detach,
                detach_note=note,
                choice=choice,
                forced=forced,
                round=seen_rounds.get(key, round_no),
            )
        )
    plan.blocking = sorted(rows, key=lambda row: (row.round, row.kind, row.label))
    return plan


class ReviewedDeleteMixin:
    """Give a ``ModelAdmin``'s delete view a plan when protected rows block it.

    Applied to an admin whose rows get blocked (``OrganizationAdmin``). The stock
    view runs unchanged for a row nothing blocks, and for a user who is not a
    superuser; the review is a superuser act (#4064, Decision 5).
    """

    reviewed_delete_template = REVIEW_TEMPLATE

    def delete_blocking_row(self, request: HttpRequest, obj: Model) -> None:  # noqa: ARG002
        """Remove one blocking row. Override for a kind with its own ending seam."""
        obj.delete()

    def confirm_name(self, obj: Model) -> str:
        """What the deleter must type back: the row's ``name`` field when the model has
        one (the admin this serves does), else its string."""
        try:
            field = obj._meta.get_field("name")
        except FieldDoesNotExist:
            return str(obj)
        return str(field.value_from_object(obj) or obj)

    def delete_view(self, request: HttpRequest, object_id: str, extra_context=None):
        obj = self.get_object(request, unquote(object_id))  # type: ignore[attr-defined]
        if obj is None or not request.user.is_superuser:
            return super().delete_view(request, object_id, extra_context)  # type: ignore[misc]
        if not self.has_delete_permission(request, obj):  # type: ignore[attr-defined]
            return super().delete_view(request, object_id, extra_context)  # type: ignore[misc]
        choices = choices_from(request.POST) if request.method == "POST" else {}
        plan = build_delete_plan(obj, choices, self.admin_site)  # type: ignore[attr-defined]
        if not plan.blocking:
            return super().delete_view(request, object_id, extra_context)  # type: ignore[misc]
        if request.method == "POST" and request.POST.get(REVIEW_FIELD) == REVIEW_CONFIRM:
            response = self._confirm(request, obj, plan)
            if response is not None:
                return response
            plan = build_delete_plan(obj, choices, self.admin_site)  # type: ignore[attr-defined]
        return self._render_review(request, obj, plan)

    def _confirm(self, request: HttpRequest, obj: Model, plan: DeletePlan) -> HttpResponse | None:
        """Write the plan, or say why not and return None so the review re-renders."""
        if not plan.complete:
            messages.error(request, _UNDECIDED)
            return None
        typed = request.POST.get(TYPED_NAME_FIELD, "").strip()
        if typed != self.confirm_name(obj):
            messages.error(request, _NAME_MISMATCH)
            return None
        obj_display = str(obj)
        obj_id = obj.serializable_value(obj._meta.pk.attname)
        try:
            with transaction.atomic():
                for row in plan.detached:
                    for name in row.links:
                        setattr(row.obj, row.obj._meta.get_field(name).attname, None)
                    row.obj.save(update_fields=list(row.links))
                    self.log_change(  # type: ignore[attr-defined]
                        request, row.obj, f"Detached from {obj_display}: {', '.join(row.links)}"
                    )
                for row in plan.deleted_rows:
                    self.log_deletions(  # type: ignore[attr-defined]
                        request, row.obj._meta.model.objects.filter(pk=row.obj.pk)
                    )
                    self.delete_blocking_row(request, row.obj)
                self.log_deletions(request, obj._meta.model.objects.filter(pk=obj.pk))  # type: ignore[attr-defined]
                self.delete_model(request, obj)  # type: ignore[attr-defined]
        except (ProtectedError, IntegrityError):
            messages.error(request, _STALE)
            return None
        return self.response_delete(request, obj_display, obj_id)  # type: ignore[attr-defined]

    def _render_review(self, request: HttpRequest, obj: Model, plan: DeletePlan):
        opts = obj._meta
        admin_site = self.admin_site  # type: ignore[attr-defined]

        def format_callback(item: Model) -> str:
            url = _admin_url(admin_site, item)
            name = capfirst(str(item._meta.verbose_name))
            if url is None:
                return f"{name}: {item}"
            return format_html('{}: <a href="{}">{}</a>', name, url, item)

        context = {
            **admin_site.each_context(request),
            "title": f"Delete {opts.verbose_name}",
            "subtitle": None,
            "object_name": str(opts.verbose_name),
            "object": obj,
            "deleted_objects": plan.nested(format_callback),
            "model_count": plan.model_count(),
            "perms_lacking": set(),
            "protected": plan.blocking,
            "detached": plan.detached,
            "undecided": plan.undecided,
            "confirm_name": self.confirm_name(obj),
            "detach": DETACH,
            "delete": DELETE,
            "choice_prefix": CHOICE_PREFIX,
            "review_field": REVIEW_FIELD,
            "review_update": REVIEW_UPDATE,
            "review_confirm": REVIEW_CONFIRM,
            "typed_name_field": TYPED_NAME_FIELD,
            "opts": opts,
            "app_label": opts.app_label,
            "preserved_filters": self.get_preserved_filters(request),  # type: ignore[attr-defined]
            "is_popup": False,
            "to_field": None,
            "media": self.media,  # type: ignore[attr-defined]
        }
        request.current_app = admin_site.name
        return TemplateResponse(request, self.reviewed_delete_template, context)
