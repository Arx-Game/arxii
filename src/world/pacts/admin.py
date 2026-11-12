"""Django admin for being pacts (#4341).

Offers are authored here with their commitments inline. Characters' pacts and
their periods are written only by play, so those pages are read-mostly.
"""

from __future__ import annotations

from django.contrib import admin
from django.http import HttpRequest

from world.pacts.models import (
    CharacterPact,
    PactCredit,
    PactOffer,
    PactOfferCommitment,
    PactPeriodDetails,
)


class PactOfferCommitmentInline(admin.TabularInline):
    model = PactOfferCommitment
    extra = 0
    fields = ("kind", "amount", "notes", "owed_by_holder")


@admin.register(PactOffer)
class PactOfferAdmin(admin.ModelAdmin):
    """A being's pact offers and what every holder commits to."""

    list_display = ("name", "being", "period_weeks", "severity_per_miss", "is_active")
    list_filter = ("is_active", "being")
    search_fields = ("name", "being__name")
    raw_id_fields = ("being", "condition")
    inlines = (PactOfferCommitmentInline,)


@admin.register(CharacterPact)
class CharacterPactAdmin(admin.ModelAdmin):
    """Characters' pacts. Signed, graded and ended through play; staff correct here."""

    list_display = (
        "character_sheet",
        "offer",
        "signed_at",
        "dissolved_at",
        "dissolution_reason",
    )
    list_filter = ("dissolution_reason", "offer__being")
    raw_id_fields = ("character_sheet", "offer", "devotion_standing", "condition_instance")
    readonly_fields = ("signed_at",)


class PactCreditInline(admin.TabularInline):
    model = PactCredit
    extra = 0
    can_delete = False
    fields = ("source", "credited", "game_week", "created_at")
    readonly_fields = fields

    def has_add_permission(self, request: HttpRequest, obj=None) -> bool:
        del request, obj
        return False


@admin.register(PactPeriodDetails)
class PactPeriodDetailsAdmin(admin.ModelAdmin):
    """Pact periods, read-only: each one's commitment, grading and credits."""

    list_display = ("pact", "commitment", "project", "severity_change", "created_at")
    list_filter = ("pact__offer__being",)
    readonly_fields = (
        "project",
        "pact",
        "commitment",
        "resist_outcome",
        "severity_change",
        "stage_after",
        "created_at",
    )
    inlines = (PactCreditInline,)

    def has_add_permission(self, request: HttpRequest) -> bool:
        del request
        return False
