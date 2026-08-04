"""Admin customization views."""

from datetime import UTC, datetime
import logging

from django.apps import apps
from django.contrib.admin.views.decorators import staff_member_required
from django.core import serializers
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_POST

from core.app_domains import domain_of, resolve_model_by_name
from web.admin.models import AdminExcludedModel, AdminPinnedModel
from web.admin.services import HARDCODED_EXCLUDED_APPS, analyze_fixture, execute_import

logger = logging.getLogger(__name__)


def _resolve_domain(app_label, model_name):
    """Resolve a request's ``(app_label, model_name)`` to its authoring domain.

    The pin/exclude UI POSTs the model's *domain* (``export_preview``'s
    ``data-app-label``, itself ``core.app_domains.domain_of`` — #2906), not
    Django's real app_label (a single ``"arxii"`` for nearly every model
    post-collapse). ``apps.get_model(app_label, model_name)`` would 400 on
    every toggle since "magic"/"roster"/etc. are no longer installed app
    labels — resolve by model name instead, via the same model-name index
    ``resolve_model_by_name`` uses everywhere else, passing the domain along
    only to disambiguate the rare same-named-model case. Returns ``None`` if
    the model doesn't exist.
    """
    try:
        model = resolve_model_by_name(f"{app_label}.{model_name}" if app_label else model_name)
    except LookupError:
        return None
    return domain_of(model)


@require_POST
@staff_member_required
def toggle_pin_model(request):
    """Toggle whether a model is pinned to the Recent section."""
    app_label = request.POST.get("app_label")
    model_name = request.POST.get("model_name")

    if not app_label or not model_name:
        return JsonResponse({"error": "Missing app_label or model_name"}, status=400)

    domain = _resolve_domain(app_label, model_name)
    if domain is None:
        return JsonResponse({"error": "Unknown model"}, status=400)

    pin, created = AdminPinnedModel.objects.get_or_create(
        app_label=domain,
        model_name=model_name,
    )

    if not created:
        pin.delete()
        return JsonResponse({"pinned": False})

    return JsonResponse({"pinned": True})


@staff_member_required
def is_model_pinned(request):
    """Check if a model is currently pinned."""
    app_label = request.GET.get("app_label")
    model_name = request.GET.get("model_name")

    if not app_label or not model_name:
        return JsonResponse({"error": "Missing app_label or model_name"}, status=400)

    domain = _resolve_domain(app_label, model_name)
    if domain is None:
        return JsonResponse({"error": "Unknown model"}, status=400)

    pinned = AdminPinnedModel.objects.filter(
        app_label=domain,
        model_name=model_name,
    ).exists()

    return JsonResponse({"pinned": pinned})


@require_POST
@staff_member_required
def export_data(request):
    """Export selected models as Django fixture JSON."""
    selected = request.POST.getlist("models")
    if not selected:
        return JsonResponse({"error": "No models selected"}, status=400)

    all_objects = []
    for model_key in selected:
        try:
            app_label, model_name = model_key.split(".")
        except ValueError:
            continue

        # Skip hardcoded exclusions as safety check
        if app_label in HARDCODED_EXCLUDED_APPS:
            continue

        try:
            # model_key carries the domain (export_preview's data-model-key —
            # core.app_domains.domain_of, #2906), not Django's real app_label
            # (uniformly "arxii" post-collapse) — resolve by model name.
            model = resolve_model_by_name(model_key)
            objects = list(model.objects.all())
            all_objects.extend(objects)
        except Exception:
            logger.exception("admin export loop skipped a model (audit: was silent)")
            continue

    # Serialize with natural keys
    data = serializers.serialize(
        "json",
        all_objects,
        indent=2,
        use_natural_foreign_keys=True,
        use_natural_primary_keys=True,
    )

    # Create response with download
    timestamp = datetime.now(tz=UTC).strftime("%Y-%m-%d")
    filename = f"arx-config-{timestamp}.json"
    response = HttpResponse(data, content_type="application/json")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


@require_POST
@staff_member_required
def toggle_export_exclusion(request):
    """Toggle whether a model is excluded from export."""
    app_label = request.POST.get("app_label")
    model_name = request.POST.get("model_name")

    if not app_label or not model_name:
        return JsonResponse({"error": "Missing app_label or model_name"}, status=400)

    domain = _resolve_domain(app_label, model_name)
    if domain is None:
        return JsonResponse({"error": "Unknown model"}, status=400)

    exclusion, created = AdminExcludedModel.objects.get_or_create(
        app_label=domain,
        model_name=model_name,
    )

    if not created:
        exclusion.delete()
        return JsonResponse({"excluded": False})

    return JsonResponse({"excluded": True})


@staff_member_required
def is_model_excluded(request):
    """Check if a model is currently excluded from export."""
    app_label = request.GET.get("app_label")
    model_name = request.GET.get("model_name")

    if not app_label or not model_name:
        return JsonResponse({"error": "Missing app_label or model_name"}, status=400)

    domain = _resolve_domain(app_label, model_name)
    if domain is None:
        return JsonResponse({"error": "Unknown model"}, status=400)

    excluded = AdminExcludedModel.objects.filter(
        app_label=domain,
        model_name=model_name,
    ).exists()

    return JsonResponse({"excluded": excluded})


@staff_member_required
def export_preview(request):
    """Show export preview with model inventory."""
    from core.natural_keys import NaturalKeyMixin  # noqa: PLC0415

    excluded = set(AdminExcludedModel.objects.values_list("app_label", "model_name"))

    included_models = []
    excluded_models = []
    warnings = []
    total_records = 0

    for model in apps.get_models():
        real_app_label = model._meta.app_label  # noqa: SLF001

        # Skip hardcoded exclusions entirely. HARDCODED_EXCLUDED_APPS lists
        # Django/Evennia app labels (which stay separate apps, #2906), so this
        # check stays keyed on the real app_label, not the authoring domain.
        if real_app_label in HARDCODED_EXCLUDED_APPS:
            continue

        # Authoring domain (core.app_domains.domain_of — #2906), identical to
        # real_app_label today; the AdminExcludedModel rows above key on it.
        app_label = domain_of(model)
        model_name = model._meta.model_name  # noqa: SLF001

        # Get record count
        try:
            count = model.objects.count()
        except Exception:
            logger.exception("admin export loop skipped a model (audit: was silent)")
            continue

        has_natural_key = issubclass(model, NaturalKeyMixin) or hasattr(model, "natural_key")

        model_info = {
            "app_label": app_label,
            "model_name": model_name,
            "verbose_name": model._meta.verbose_name_plural.title(),  # noqa: SLF001
            "count": count,
            "has_natural_key": has_natural_key,
        }

        if (app_label, model_name) in excluded:
            excluded_models.append(model_info)
        else:
            included_models.append(model_info)
            total_records += count
            if not has_natural_key and count > 0:
                warnings.append(f"{app_label}.{model_name} has {count} records but no natural keys")

    context = {
        "title": "Export Preview",
        "included_models": sorted(included_models, key=lambda m: (m["app_label"], m["model_name"])),
        "excluded_models": sorted(excluded_models, key=lambda m: (m["app_label"], m["model_name"])),
        "total_records": total_records,
        "total_models": len(included_models),
        "warnings": warnings,
    }
    return render(request, "admin/export_preview.html", context)


@staff_member_required
def import_upload(request):
    """Show file upload form for import, or parse uploaded file and show preview."""
    if request.method == "POST":
        uploaded_file = request.FILES.get("file")
        if not uploaded_file:
            return render(
                request,
                "admin/import_upload.html",
                {"title": "Import Data", "error": "No file selected."},
            )
        try:
            content = uploaded_file.read().decode("utf-8")
            analysis = analyze_fixture(content)
        except Exception as exc:
            logger.exception("Fixture upload parse failed")
            return render(
                request,
                "admin/import_upload.html",
                {"title": "Import Data", "error": f"Failed to parse file: {exc}"},
            )
        # Store fixture content in session for the execute step
        request.session["import_fixture_data"] = content
        return render(
            request,
            "admin/import_preview.html",
            {"title": "Import Preview", "analysis": analysis},
        )
    return render(request, "admin/import_upload.html", {"title": "Import Data"})


@require_POST
@staff_member_required
def import_execute(request):
    """Execute import with selected per-model actions."""
    fixture_data = request.session.get("import_fixture_data")
    if not fixture_data:
        return render(
            request,
            "admin/import_upload.html",
            {
                "title": "Import Data",
                "error": "No fixture data found. Please upload a file first.",
            },
        )

    # Collect per-model actions from form POST data
    action_prefix = "action_"
    model_actions = {}
    for key, value in request.POST.items():
        if key.startswith(action_prefix):
            model_key = key[len(action_prefix) :]
            model_actions[model_key] = value

    result = execute_import(fixture_data, model_actions)

    # Clean up session
    request.session.pop("import_fixture_data", None)

    return render(
        request,
        "admin/import_results.html",
        {"title": "Import Results", "result": result},
    )
