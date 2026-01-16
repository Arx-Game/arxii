"""Admin customization views."""

from django.contrib.admin.views.decorators import staff_member_required
from django.http import JsonResponse
from django.views.decorators.http import require_POST

from web.admin.models import AdminPinnedModel


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
