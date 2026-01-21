from django.contrib import admin

from world.magic.models import (
    Affinity,
    AnimaRitualType,
    CharacterAnima,
    CharacterAnimaRitual,
    CharacterAura,
    CharacterGift,
    CharacterPower,
    CharacterResonance,
    Gift,
    IntensityTier,
    Power,
    Resonance,
    Thread,
    ThreadJournal,
    ThreadResonance,
    ThreadType,
)


@admin.register(Affinity)
class AffinityAdmin(admin.ModelAdmin):
    list_display = ["name", "affinity_type"]
    search_fields = ["name", "description"]
    readonly_fields = ["affinity_type"]  # Type shouldn't change after creation


@admin.register(Resonance)
class ResonanceAdmin(admin.ModelAdmin):
    list_display = ["name", "slug", "default_affinity"]
    list_filter = ["default_affinity"]
    search_fields = ["name", "slug", "description"]
    prepopulated_fields = {"slug": ("name",)}


@admin.register(CharacterAura)
class CharacterAuraAdmin(admin.ModelAdmin):
    list_display = ["character", "celestial", "primal", "abyssal", "get_dominant"]
    list_filter = ["updated_at"]
    search_fields = ["character__db_key"]
    readonly_fields = ["updated_at"]

    @admin.display(description="Dominant")
    def get_dominant(self, obj):
        return obj.dominant_affinity.label


@admin.register(CharacterResonance)
class CharacterResonanceAdmin(admin.ModelAdmin):
    list_display = ["character", "resonance", "scope", "strength", "is_active"]
    list_filter = ["resonance", "scope", "strength", "is_active"]
    search_fields = ["character__db_key", "resonance__name"]
    autocomplete_fields = ["resonance"]


@admin.register(IntensityTier)
class IntensityTierAdmin(admin.ModelAdmin):
    list_display = ["name", "threshold", "control_modifier"]
    ordering = ["threshold"]


@admin.register(Gift)
class GiftAdmin(admin.ModelAdmin):
    list_display = ["name", "slug", "affinity", "level_requirement"]
    list_filter = ["affinity", "level_requirement"]
    search_fields = ["name", "slug", "description"]
    prepopulated_fields = {"slug": ("name",)}
    filter_horizontal = ["resonances"]


@admin.register(Power)
class PowerAdmin(admin.ModelAdmin):
    list_display = [
        "name",
        "gift",
        "affinity",
        "base_intensity",
        "base_control",
        "anima_cost",
        "level_requirement",
    ]
    list_filter = ["gift", "affinity", "level_requirement"]
    search_fields = ["name", "slug", "description"]
    prepopulated_fields = {"slug": ("name",)}
    filter_horizontal = ["resonances"]
    autocomplete_fields = ["gift"]


@admin.register(CharacterGift)
class CharacterGiftAdmin(admin.ModelAdmin):
    list_display = ["character", "gift", "acquired_at"]
    list_filter = ["gift", "acquired_at"]
    search_fields = ["character__db_key", "gift__name"]
    autocomplete_fields = ["gift"]


@admin.register(CharacterPower)
class CharacterPowerAdmin(admin.ModelAdmin):
    list_display = ["character", "power", "times_used", "unlocked_at"]
    list_filter = ["power__gift", "unlocked_at"]
    search_fields = ["character__db_key", "power__name"]
    autocomplete_fields = ["power"]


@admin.register(CharacterAnima)
class CharacterAnimaAdmin(admin.ModelAdmin):
    list_display = ["character", "current", "maximum", "last_recovery"]
    list_filter = ["last_recovery"]
    search_fields = ["character__db_key"]
    readonly_fields = ["last_recovery"]


@admin.register(AnimaRitualType)
class AnimaRitualTypeAdmin(admin.ModelAdmin):
    list_display = ["name", "slug", "category", "base_recovery"]
    list_filter = ["category"]
    search_fields = ["name", "slug", "description"]
    prepopulated_fields = {"slug": ("name",)}


@admin.register(CharacterAnimaRitual)
class CharacterAnimaRitualAdmin(admin.ModelAdmin):
    list_display = ["character", "ritual_type", "is_primary", "times_performed"]
    list_filter = ["ritual_type", "is_primary"]
    search_fields = ["character__db_key", "ritual_type__name"]
    autocomplete_fields = ["ritual_type"]


@admin.register(ThreadType)
class ThreadTypeAdmin(admin.ModelAdmin):
    list_display = [
        "name",
        "slug",
        "romantic_threshold",
        "trust_threshold",
        "rivalry_threshold",
        "protective_threshold",
        "enmity_threshold",
    ]
    search_fields = ["name", "slug", "description"]
    prepopulated_fields = {"slug": ("name",)}
    autocomplete_fields = ["grants_resonance"]


class ThreadResonanceInline(admin.TabularInline):
    model = ThreadResonance
    extra = 0
    autocomplete_fields = ["resonance"]


class ThreadJournalInline(admin.TabularInline):
    model = ThreadJournal
    extra = 0
    readonly_fields = ["created_at"]
    fields = ["author", "content", "created_at"]


@admin.register(Thread)
class ThreadAdmin(admin.ModelAdmin):
    list_display = [
        "initiator",
        "receiver",
        "romantic",
        "trust",
        "rivalry",
        "protective",
        "enmity",
        "is_soul_tether",
    ]
    list_filter = ["is_soul_tether", "created_at"]
    search_fields = ["initiator__db_key", "receiver__db_key"]
    inlines = [ThreadResonanceInline, ThreadJournalInline]


@admin.register(ThreadJournal)
class ThreadJournalAdmin(admin.ModelAdmin):
    list_display = ["thread", "author", "created_at"]
    list_filter = ["created_at"]
    search_fields = ["thread__initiator__db_key", "thread__receiver__db_key"]
    readonly_fields = ["created_at"]


@admin.register(ThreadResonance)
class ThreadResonanceAdmin(admin.ModelAdmin):
    list_display = ["thread", "resonance", "strength"]
    list_filter = ["resonance", "strength"]
    search_fields = ["thread__initiator__db_key", "thread__receiver__db_key"]
    autocomplete_fields = ["resonance"]
