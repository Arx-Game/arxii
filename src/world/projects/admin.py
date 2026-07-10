"""Django admin for the projects framework — authoring contribution methods (#1574)."""

from django.contrib import admin

from world.projects.models import ContributionMethod, ProjectKindResonanceAward


@admin.register(ContributionMethod)
class ContributionMethodAdmin(admin.ModelAdmin):
    """Staff author the per-ProjectKind, check-based contribution methods (#1574)."""

    list_display = ("name", "kind", "check_type", "ap_cost", "progress_on_success", "is_active")
    list_filter = ("kind", "is_active")
    search_fields = ("name",)
    raw_id_fields = ("check_type",)


@admin.register(ProjectKindResonanceAward)
class ProjectKindResonanceAwardAdmin(admin.ModelAdmin):
    """#2038 — per-ProjectKind PROJECT_CONTRIBUTION resonance payout (staff-tunable)."""

    list_display = ("kind", "resonance_award_amount")
    ordering = ("kind",)
