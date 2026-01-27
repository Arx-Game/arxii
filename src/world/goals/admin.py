"""Django admin configuration for the goals system."""

from django.contrib import admin

from world.goals.models import CharacterGoal, GoalJournal, GoalRevision

# Note: GoalDomain was replaced with ModifierType(category='goal').
# Goal domains are managed through the mechanics ModifierTypeAdmin.


@admin.register(CharacterGoal)
class CharacterGoalAdmin(admin.ModelAdmin):
    """Admin for CharacterGoal instances."""

    list_display = ["character", "domain", "points", "updated_at"]
    list_filter = ["domain"]
    search_fields = ["character__db_key", "notes"]
    list_select_related = ["character", "domain"]
    raw_id_fields = ["character"]


@admin.register(GoalJournal)
class GoalJournalAdmin(admin.ModelAdmin):
    """Admin for GoalJournal entries."""

    list_display = ["character", "title", "domain", "is_public", "xp_awarded", "created_at"]
    list_filter = ["is_public", "domain", "created_at"]
    search_fields = ["character__db_key", "title", "content"]
    list_select_related = ["character", "domain"]
    raw_id_fields = ["character"]
    date_hierarchy = "created_at"


@admin.register(GoalRevision)
class GoalRevisionAdmin(admin.ModelAdmin):
    """Admin for GoalRevision tracking."""

    list_display = ["character", "last_revised_at", "can_revise_display"]
    search_fields = ["character__db_key"]
    list_select_related = ["character"]
    raw_id_fields = ["character"]

    @admin.display(boolean=True, description="Can Revise")
    def can_revise_display(self, obj: GoalRevision) -> bool:
        """Display whether character can revise goals."""
        return obj.can_revise()
