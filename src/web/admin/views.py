"""Admin customization views."""

from datetime import UTC, datetime
import logging

from django.apps import apps
from django.contrib.admin.views.decorators import staff_member_required
from django.core import serializers
from django.db import transaction
from django.http import HttpResponse, JsonResponse
from django.views.decorators.http import require_POST

from web.admin.models import AdminExcludedModel, AdminPinnedModel

logger = logging.getLogger(__name__)


@require_POST
@staff_member_required
def toggle_pin_model(request):
    """Toggle whether a model is pinned to the Recent section."""
    app_label = request.POST.get("app_label")
    model_name = request.POST.get("model_name")

    if not app_label or not model_name:
        return JsonResponse({"error": "Missing app_label or model_name"}, status=400)

    pin, created = AdminPinnedModel.objects.get_or_create(
        app_label=app_label,
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

    pinned = AdminPinnedModel.objects.filter(
        app_label=app_label,
        model_name=model_name,
    ).exists()

    return JsonResponse({"pinned": pinned})


@staff_member_required
def export_data(request):  # noqa: ARG001
    """Export all non-excluded models as Django fixture JSON."""
    # Get excluded models as set of (app_label, model_name) tuples
    excluded = set(AdminExcludedModel.objects.values_list("app_label", "model_name"))

    # Collect all objects to serialize
    all_objects = []
    for model in apps.get_models():
        app_label = model._meta.app_label  # noqa: SLF001
        model_name = model._meta.model_name  # noqa: SLF001

        # Skip if excluded
        if (app_label, model_name) in excluded:
            continue

        # Skip Django's built-in session, contenttypes, migrations, etc.
        if app_label in ("sessions", "contenttypes", "django_migrations", "admin"):
            continue

        # Skip Evennia's internal models that shouldn't be exported
        if app_label in ("server", "scripts", "comms", "help", "typeclasses"):
            continue

        # Get all objects for this model
        try:
            objects = list(model.objects.all())
            all_objects.extend(objects)
        except Exception:  # noqa: BLE001, S112
            # Skip models that can't be queried (abstract, proxy issues, etc.)
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
def import_data(request):
    """Import Django fixture JSON, replacing all data for included models."""
    uploaded_file = request.FILES.get("file")
    if not uploaded_file:
        return JsonResponse({"error": "No file uploaded"}, status=400)

    try:
        content = uploaded_file.read().decode("utf-8")
        objects = list(serializers.deserialize("json", content))
    except Exception:
        logger.exception("Failed to parse fixture file")
        return JsonResponse({"error": "Invalid fixture file format"}, status=400)

    # Group objects by model
    objects_by_model = {}
    for obj in objects:
        model = obj.object.__class__
        if model not in objects_by_model:
            objects_by_model[model] = []
        objects_by_model[model].append(obj)

    try:
        with transaction.atomic():
            # Delete existing data for each model in the fixture
            for model in objects_by_model:
                model.objects.all().delete()

            # Save all objects
            for obj in objects:
                obj.save()

        return JsonResponse({"success": True, "count": len(objects)})
    except Exception:
        logger.exception("Failed to import fixture data")
        return JsonResponse({"error": "Import failed"}, status=500)


@require_POST
@staff_member_required
def toggle_export_exclusion(request):
    """Toggle whether a model is excluded from export."""
    app_label = request.POST.get("app_label")
    model_name = request.POST.get("model_name")

    if not app_label or not model_name:
        return JsonResponse({"error": "Missing app_label or model_name"}, status=400)

    exclusion, created = AdminExcludedModel.objects.get_or_create(
        app_label=app_label,
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

    excluded = AdminExcludedModel.objects.filter(
        app_label=app_label,
        model_name=model_name,
    ).exists()

    return JsonResponse({"excluded": excluded})
