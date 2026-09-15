"""Django admin registrations for behaviors app models (#3831)."""

from django.contrib import admin

from behaviors.models import BehaviorPackageDefinition


@admin.register(BehaviorPackageDefinition)
class BehaviorPackageDefinitionAdmin(admin.ModelAdmin):
    """#3831 - the reusable behavior package template (name -> service function)."""

    list_display = ("name", "service_function_path")
    search_fields = ("name", "service_function_path", "description")
