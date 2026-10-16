from __future__ import annotations

from django.contrib import admin
from django.db.models import Count
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.urls import reverse

from world.admin_utils import OneRowPerFormSet
from world.scenes.action_constants import DIFFICULTY_VALUES, MIN_DIFFICULTY_POINTS, DifficultyChoice
from world.worship.models import (
    BeingFacet,
    BeingNickname,
    BeingRelationship,
    BeingResonance,
    BeingTarotCard,
    ChosenFavorConfig,
    ConsecrationTier,
    DevotionConfig,
    DevotionStanding,
    DivineInterventionConfig,
    FavorInvocation,
    FavorOutcomeAward,
    Miracle,
    MiracleAppliedCondition,
    MiracleDamageProfile,
    MiraclePerformance,
    Pledge,
    PledgeCredit,
    PledgeDetails,
    Prayer,
    Relic,
    RiteKind,
    ShrineDetails,
    TempleDedication,
    Vision,
    WorshipDeclaration,
    WorshipFeastDay,
    WorshipGrant,
    WorshippedBeing,
    WorshipRite,
    WorshipRitePerformance,
    WorshipRiteTierAward,
    WorshipTradition,
)


@admin.register(WorshipTradition)
class WorshipTraditionAdmin(admin.ModelAdmin):
    list_display = ("name", "rites_specialization")
    search_fields = ("name",)


class BeingTarotCardInline(admin.TabularInline):
    model = BeingTarotCard
    formset = OneRowPerFormSet
    extra = 0
    autocomplete_fields = ("card",)


@admin.register(WorshippedBeing)
class WorshippedBeingAdmin(admin.ModelAdmin):
    list_display = ("name", "tradition", "resonance_pool", "lifetime_worship", "is_active")
    list_filter = ("tradition", "is_active")
    search_fields = ("name",)
    raw_id_fields = ("avatar_sheet",)
    # codex_entry points into the whole CodexEntry corpus — a plain select would
    # render every entry. Same widget MagicProgressionMilestoneAdmin uses against
    # the same CodexEntryAdmin (which declares the required search_fields).
    # invocation_check_type (#4333): the per-being override of the default
    # invocation check; blank uses Devotion config's.
    autocomplete_fields = ("codex_entry", "invocation_check_type")
    filter_horizontal = ("ultimate_techniques",)
    # The tarot link carries an orientation (#4198), so it is a row, not a multi-select.
    inlines = (BeingTarotCardInline,)


@admin.register(BeingFacet)
class BeingFacetAdmin(admin.ModelAdmin):
    list_display = ("being", "facet")
    list_filter = ("being",)
    search_fields = ("being__name", "facet__name")


@admin.register(BeingResonance)
class BeingResonanceAdmin(admin.ModelAdmin):
    list_display = ("being", "resonance", "tier")
    list_filter = ("being", "tier")
    search_fields = ("being__name", "resonance__name")


@admin.register(BeingNickname)
class BeingNicknameAdmin(admin.ModelAdmin):
    list_display = ("name", "being")
    list_filter = ("being",)
    search_fields = ("being__name", "name")


@admin.register(BeingRelationship)
class BeingRelationshipAdmin(admin.ModelAdmin):
    list_display = ("being_a", "being_b", "valence")
    list_filter = ("valence",)
    search_fields = ("being_a__name", "being_b__name")


@admin.register(WorshipFeastDay)
class WorshipFeastDayAdmin(admin.ModelAdmin):
    list_display = ("name", "being", "ic_month", "ic_day")
    list_filter = ("being",)
    search_fields = ("name", "being__name")


@admin.register(WorshipGrant)
class WorshipGrantAdmin(admin.ModelAdmin):
    list_display = ("being", "amount", "granted_by", "reason", "created_at")
    list_filter = ("being",)
    raw_id_fields = ("granted_by",)


@admin.register(DevotionStanding)
class DevotionStandingAdmin(admin.ModelAdmin):
    list_display = (
        "character_sheet",
        "being",
        "favor",
        "lifetime_favor",
        "valence",
        "established_at",
        "released_at",
    )
    list_filter = ("being", "valence")
    raw_id_fields = ("character_sheet",)


@admin.register(WorshipDeclaration)
class WorshipDeclarationAdmin(admin.ModelAdmin):
    list_display = ("character_sheet", "public_being", "secret_being")
    raw_id_fields = ("character_sheet", "secret")


class MiracleAppliedConditionInline(admin.TabularInline):
    model = MiracleAppliedCondition
    formset = OneRowPerFormSet
    extra = 0


class MiracleDamageProfileInline(admin.TabularInline):
    model = MiracleDamageProfile
    extra = 0


@admin.register(Miracle)
class MiracleAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "being",
        "resonance_pool_cost",
        "intervention_trigger",
        "favor_threshold",
        "is_active",
    )
    list_filter = ("being", "intervention_trigger", "is_active")
    search_fields = ("name",)
    inlines = [
        MiracleAppliedConditionInline,
        MiracleDamageProfileInline,
    ]


@admin.register(MiraclePerformance)
class MiraclePerformanceAdmin(admin.ModelAdmin):
    list_display = (
        "miracle",
        "being",
        "target_character",
        "resonance_spent",
        "trigger_event",
        "created_at",
    )
    list_filter = ("being", "trigger_event")
    raw_id_fields = ("target_character", "scene")
    readonly_fields = (
        "miracle",
        "being",
        "target_character",
        "scene",
        "resonance_spent",
        "trigger_event",
        "created_at",
    )


@admin.register(DivineInterventionConfig)
class DivineInterventionConfigAdmin(admin.ModelAdmin):
    list_display = ("favor_threshold", "cooldown_hours", "min_pool_for_intervention")


@admin.register(ChosenFavorConfig)
class ChosenFavorConfigAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "anima_recovery_threshold",
        "anima_recovery_bonus",
        "earn_bonus_percent",
        "invocation_ease_points",
    )
    readonly_fields = ("chosen_per_being",)
    fieldsets = (
        (
            "Anima recovery and ceremony edge",
            {
                "fields": (
                    "anima_recovery_threshold",
                    "anima_recovery_bonus",
                    "ceremony_edge_threshold",
                    "ceremony_edge_bonus",
                )
            },
        ),
        (
            "Favor: earning and invocation",
            {"fields": ("earn_bonus_percent", "invocation_ease_points", "chosen_per_being")},
        ),
    )

    @admin.display(description="Chosen per being")
    def chosen_per_being(self, obj: ChosenFavorConfig) -> str:
        """How many characters each being has as its Chosen (an active patronage)."""
        del obj  # The counts are game-wide; the singleton row is not read.
        rows = (
            DevotionStanding.objects.filter(valence__isnull=False, released_at__isnull=True)
            .values("being__name")
            .annotate(count=Count("id"))
            .order_by("being__name")
        )
        if not rows:
            return "No being has a Chosen yet."
        return " · ".join(f"{row['being__name']} {row['count']}" for row in rows)


class FavorOutcomeAwardInline(admin.TabularInline):
    """The outcome-keyed favor terms (#4333): invocation bonuses, closing awards."""

    model = FavorOutcomeAward
    formset = OneRowPerFormSet
    extra = 0
    fields = ("kind", "outcome_tier", "amount")
    ordering = ("kind", "-outcome_tier__success_level")
    verbose_name = "favor outcome award"
    verbose_name_plural = "Favor outcome awards: one table, two kinds"


#: DevotionConfig's difficulty choice field, relabelled with its points.
_BASE_DIFFICULTY_FIELD = "base_difficulty"
#: The example favor invocation modifier the read-only difficulty table shows.
_EXAMPLE_INVOCATION_MODIFIER = 15


def _band_label(points: int) -> str:
    from world.worship.invocation_services import band_for_points  # noqa: PLC0415

    return DifficultyChoice(band_for_points(points)).label


def invocation_difficulty_rows(config: DevotionConfig, chosen_ease: int) -> list[list[str]]:
    """The read-only "Resulting invocation difficulty" table (#4333, design 10).

    One row per favor band, one column per kind of character: a stranger, a
    holder of an example +15 favor invocation modifier, a Chosen, and a Chosen
    holding the modifier. Each cell is the difficulty band the eases add up to.
    """
    base = DIFFICULTY_VALUES[config.base_difficulty]
    low, high = config.favor_ease_low_threshold, config.favor_ease_high_threshold
    bands = (
        (f"1 to {low - 1}", 0),
        (f"{low} to {high - 1}", config.favor_ease_low_points),
        (f"{high} or more", config.favor_ease_high_points),
    )
    columns = (
        (0, 0),
        (0, _EXAMPLE_INVOCATION_MODIFIER),
        (chosen_ease, 0),
        (chosen_ease, _EXAMPLE_INVOCATION_MODIFIER),
    )
    return [
        [label]
        + [
            _band_label(max(base - favor_ease - chosen - modifier, MIN_DIFFICULTY_POINTS))
            for chosen, modifier in columns
        ]
        for label, favor_ease in bands
    ]


def invocations_last_week() -> str:
    """Invocations in the last finished game week, by surface and by outcome."""
    from world.game_clock.models import GameWeek  # noqa: PLC0415

    week = GameWeek.objects.filter(is_current=False).order_by("-started_at").first()
    if week is None:
        return "No finished game week yet."
    rows = FavorInvocation.objects.filter(game_week=week)
    total = rows.count()
    if not total:
        return "None."
    missions = rows.filter(mission_instance__isnull=False).count()
    outcomes = (
        rows.values("outcome_tier__name", "outcome_tier__success_level")
        .annotate(count=Count("id"))
        .order_by("-outcome_tier__success_level")
    )
    by_outcome = ", ".join(f"{row['outcome_tier__name']} {row['count']}" for row in outcomes)
    return (
        f"{total} (missions {missions}, scene checks and actions {total - missions}). "
        f"Outcomes: {by_outcome}."
    )


@admin.register(DevotionConfig)
class DevotionConfigAdmin(admin.ModelAdmin):
    """The favor terms every character shares (#4333): a singleton change form.

    Read-only context below the awards: the difficulty the eases add up to for a
    stranger, a favor invocation modifier holder and a Chosen at each favor band,
    and last week's invocations by outcome.
    """

    change_form_template = "admin/worship/devotionconfig/change_form.html"
    autocomplete_fields = ("invocation_check_type",)
    readonly_fields = ("eases_rule", "earning_rate_rule")
    inlines = (FavorOutcomeAwardInline,)
    fieldsets = (
        (
            "Invocation check",
            {
                "fields": (
                    "invocation_check_type",
                    "base_difficulty",
                    "eases_rule",
                    ("favor_ease_low_threshold", "favor_ease_low_points"),
                    ("favor_ease_high_threshold", "favor_ease_high_points"),
                    "invocations_per_week",
                )
            },
        ),
        (
            "Earning",
            {
                "fields": (
                    "earning_rate_rule",
                    ("favored_deed_percent", "associated_deed_percent"),
                    "weekly_deed_favor_cap",
                    "sacrifice_value_per_favor",
                )
            },
        ),
    )

    @admin.display(description="Eases")
    def eases_rule(self, obj: DevotionConfig) -> str:
        del obj
        return (
            "All eases add, in points; 15 points is one band; never below Trivial (15). "
            "The Chosen ease is on Chosen favor config; favor invocation modifiers come "
            "from the modifier system."
        )

    @admin.display(description="Earning rate")
    def earning_rate_rule(self, obj: DevotionConfig) -> str:
        del obj
        return (
            "100% plus additive bonuses: the Chosen bonus (Chosen favor config) and favor "
            "earning modifiers (modifier system). Every favor a character earns with a "
            "being is scaled by it."
        )

    def formfield_for_choice_field(self, db_field, request, **kwargs):
        """Show each difficulty band with its points ("Daunting (75 points)")."""
        if db_field.name == _BASE_DIFFICULTY_FIELD:
            kwargs["choices"] = [
                (value, f"{label} ({DIFFICULTY_VALUES[value]} points)")
                for value, label in DifficultyChoice.choices
            ]
        return super().formfield_for_choice_field(db_field, request, **kwargs)

    def has_add_permission(self, request: HttpRequest) -> bool:
        del request
        return not DevotionConfig.objects.exists()

    def has_delete_permission(
        self, request: HttpRequest, obj: DevotionConfig | None = None
    ) -> bool:
        del request, obj  # The singleton is never deleted.
        return False

    def changelist_view(
        self, request: HttpRequest, extra_context: dict | None = None
    ) -> HttpResponse:
        """The singleton has no list: open its one row (creating it if needed)."""
        from world.worship.invocation_services import get_devotion_config  # noqa: PLC0415

        del request, extra_context
        config = get_devotion_config()
        return HttpResponseRedirect(reverse("admin:arxii_devotionconfig_change", args=(config.pk,)))

    def render_change_form(  # noqa: PLR0913 - Django's own signature
        self, request, context, add=False, change=False, form_url="", obj=None
    ):
        """Adds the read-only difficulty table and last week's counts."""
        from world.worship.services import get_chosen_favor_config  # noqa: PLC0415

        if obj is not None:
            context["difficulty_headers"] = (
                "Favor",
                "Stranger",
                f"+{_EXAMPLE_INVOCATION_MODIFIER} invocation modifier",
                "Chosen",
                f"Chosen and +{_EXAMPLE_INVOCATION_MODIFIER} modifier",
            )
            context["difficulty_rows"] = invocation_difficulty_rows(
                obj, get_chosen_favor_config().invocation_ease_points
            )
            context["invocations_last_week"] = invocations_last_week()
        return super().render_change_form(
            request, context, add=add, change=change, form_url=form_url, obj=obj
        )


@admin.register(RiteKind)
class RiteKindAdmin(admin.ModelAdmin):
    list_display = ("name", "tier")
    list_filter = ("tier",)
    search_fields = ("name",)


@admin.register(WorshipRite)
class WorshipRiteAdmin(admin.ModelAdmin):
    list_display = ("name", "being", "kind", "check_type", "resonance", "is_active")
    list_filter = ("kind__tier", "is_active")
    search_fields = ("name", "being__name")
    autocomplete_fields = ("being", "check_type")
    raw_id_fields = ("resonance",)


@admin.register(WorshipRiteTierAward)
class WorshipRiteTierAwardAdmin(admin.ModelAdmin):
    list_display = ("tier", "outcome_tier", "resonance_amount", "favor_amount")
    list_filter = ("tier",)


@admin.register(WorshipRitePerformance)
class WorshipRitePerformanceAdmin(admin.ModelAdmin):
    list_display = (
        "character_sheet",
        "rite",
        "outcome_tier",
        "resonance_granted",
        "favor_granted",
        "performed_at",
    )
    list_filter = ("rite__kind__tier",)
    raw_id_fields = ("character_sheet", "rite", "game_week", "scene", "ceremony")


@admin.register(Relic)
class RelicAdmin(admin.ModelAdmin):
    list_display = ("item_instance", "being", "created_at")
    search_fields = ("being__name", "item_instance__custom_name", "item_instance__template__name")
    autocomplete_fields = ("being",)
    raw_id_fields = ("item_instance",)


@admin.register(ShrineDetails)
class ShrineDetailsAdmin(admin.ModelAdmin):
    list_display = ("feature_instance", "being", "consecration_points", "created_at")
    search_fields = ("being__name",)
    autocomplete_fields = ("being",)
    raw_id_fields = ("feature_instance", "founder_character_sheet")


@admin.register(TempleDedication)
class TempleDedicationAdmin(admin.ModelAdmin):
    list_display = ("building", "being", "consecration_points", "dedicated_at", "dissolved_at")
    list_filter = ("being",)
    search_fields = ("being__name", "building__area__name")
    autocomplete_fields = ("being",)
    raw_id_fields = ("building", "founder_character_sheet")


@admin.register(ConsecrationTier)
class ConsecrationTierAdmin(admin.ModelAdmin):
    list_display = ("scope", "name", "min_points", "bonus_percent")
    list_filter = ("scope",)


@admin.register(Prayer)
class PrayerAdmin(admin.ModelAdmin):
    """The freeform channel staff read (#3779): newest first, answerable from the vision admin."""

    list_display = (
        "prayed_at",
        "character_sheet",
        "being",
        "devotion_granted",
        "dire_straits",
        "intervention",
    )
    list_filter = ("being", "dire_straits")
    search_fields = ("text", "character_sheet__character__db_key", "being__name")
    autocomplete_fields = ("being",)
    raw_id_fields = ("character_sheet", "room_profile", "game_week", "intervention")
    readonly_fields = ("prayed_at",)


@admin.register(Vision)
class VisionAdmin(admin.ModelAdmin):
    list_display = ("sent_at", "recipient", "being", "reveal_source", "sent_by", "prayer")
    list_filter = ("being", "reveal_source")
    search_fields = ("body", "recipient__character__db_key", "being__name")
    autocomplete_fields = ("being",)
    raw_id_fields = ("recipient", "sent_by", "prayer", "clue", "episode", "message")
    readonly_fields = ("sent_at", "resonance_spent")


@admin.register(Pledge)
class PledgeAdmin(admin.ModelAdmin):
    """Pledge types (#4333 slice 2), listed here and written on the Being Service
    builder: the one place a staff-owned being's pledge types are authored (Ruling 8).
    The change form's object tool opens the being's builder."""

    list_display = ("name", "being", "favor_target", "span_weeks", "closing_rite", "is_active")
    list_filter = ("being", "is_active")
    search_fields = ("name", "being__name")
    readonly_fields = (
        "being",
        "name",
        "description",
        "favor_target",
        "span_weeks",
        "closing_rite",
        "is_active",
        "service_builder",
    )
    fields = readonly_fields

    @admin.display(description="Edit")
    def service_builder(self, obj: Pledge) -> str:
        from django.utils.html import format_html  # noqa: PLC0415

        url = reverse("admin_being_service", args=[obj.being_id])
        return format_html('<a href="{}">Open the Being Service builder</a>', url)

    def has_add_permission(self, request: HttpRequest) -> bool:
        del request
        return False


class PledgeCreditInline(admin.TabularInline):
    model = PledgeCredit
    extra = 0
    can_delete = False
    fields = ("source", "base", "earning_rate_percent", "credited", "game_week", "created_at")
    readonly_fields = fields

    def has_add_permission(self, request: HttpRequest, obj=None) -> bool:
        del request, obj
        return False


@admin.register(PledgeDetails)
class PledgeDetailsAdmin(admin.ModelAdmin):
    """Characters' pledges (#4333 slice 2), read-only: each one's credits, attempts
    and closing rite. Pledges are opened, credited and closed only through play."""

    list_display = ("character_sheet", "pledge", "project", "close_attempts", "created_at")
    list_filter = ("pledge__being",)
    raw_id_fields = ("character_sheet", "project", "prayer", "closing_performance")
    readonly_fields = (
        "project",
        "character_sheet",
        "pledge",
        "prayer",
        "closing_performance",
        "close_attempts",
        "created_at",
    )
    inlines = (PledgeCreditInline,)

    def has_add_permission(self, request: HttpRequest) -> bool:
        del request
        return False
