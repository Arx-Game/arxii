"""Django admin for missives (#3289).

Only ``TransmissionMethod`` is registered: it is staff-tuned vocabulary.
``Missive`` and ``MissiveAttachment`` are private letters between players and
deliberately have no admin.
"""

from __future__ import annotations

from django.contrib import admin

from world.messengers.models import TransmissionMethod


@admin.register(TransmissionMethod)
class TransmissionMethodAdmin(admin.ModelAdmin):
    list_display = ["name", "ic_delay_minutes", "is_universal"]
    search_fields = ["name"]
    list_filter = ["is_universal"]
