"""
Django admin configuration for roster models.
"""

from django.contrib import admin
from django.forms import BaseInlineFormSet, ModelForm
from django.http import HttpRequest
from django.utils.html import format_html

from world.roster.models import (
    Family,
    FamilyKind,
    FamilyMembership,
    HiddenCharacterArt,
    KinSlotPool,
    Kinsperson,
    KinspersonTraitValue,
    NPCPresetSkillLine,
    NPCPresetTraitLine,
    NPCStatlinePreset,
    ParentageEdge,
    PlayerMail,
    Roster,
    RosterApplication,
    RosterEntry,
    RosterTenure,
    Soul,
    SoulIncarnation,
    TenureDisplaySettings,
    TenureMedia,
    UnionKind,
)
from world.roster.services.kinship import create_person


class KinInline(admin.TabularInline):
    """The family's people (#4213). An appable row with no sheet is an open slot.

    A row added here becomes a person through ``create_person`` in
    ``FamilyAdmin.save_formset``, so its ``FamilyMembership`` exists:
    ``Kinsperson.family`` is only the denorm of that claim, and the tree
    builders read the claim. Leaving a family is a membership end on the
    person's own page, never a row delete here.
    """

    model = Kinsperson
    fk_name = "family"
    extra = 0
    show_change_link = True
    can_delete = False
    fields = ["name", "definition_tier", "sheet", "gender", "age", "is_deceased", "is_appable"]
    raw_id_fields = ["sheet"]
    ordering = ["name"]


class KinSlotPoolInline(admin.TabularInline):
    """The family's fuzzy-capacity openings (#4213); ``parents`` stays on the pool's page."""

    model = KinSlotPool
    extra = 0
    show_change_link = True
    fields = ["description", "count_remaining", "allowed_genders", "age_min", "age_max"]
    autocomplete_fields = ["allowed_genders"]


@admin.register(Family)
class FamilyAdmin(admin.ModelAdmin):
    autocomplete_fields = ["created_by"]
    list_display = ["name", "kind", "influence", "is_playable", "created_by_cg"]
    list_filter = ["kind", "is_playable", "created_by_cg"]
    search_fields = ["name", "description"]
    ordering = ["kind", "name"]
    readonly_fields = ["almanach"]
    inlines = [KinInline, KinSlotPoolInline]

    @admin.display(description="Almanach")
    def almanach(self, obj: Family) -> str:
        """The house document for a housed family; a commoner family has none."""
        if obj.pk is None:
            return "Save the family first."
        org = obj.organizations.first()
        if org is None:
            return "No organization; no Almanach page."
        return format_html('<a href="/staff/almanach/houses/{}">{}</a>', org.pk, org.name)

    def save_formset(
        self, request: HttpRequest, form: ModelForm, formset: BaseInlineFormSet, change: bool
    ) -> None:
        """A new kin row is created through ``create_person`` (membership included);
        an existing row saves as itself. Pools save the ordinary way."""
        if formset.model is not Kinsperson:
            super().save_formset(request, form, formset, change)
            return
        for person in formset.save(commit=False):
            if person.pk is not None:
                person.save()
                continue
            node = create_person(
                name=person.name,
                tier=person.definition_tier,
                sheet=person.sheet,
                family=form.instance,
                age=person.age,
                gender=person.gender,
                is_deceased=person.is_deceased,
                created_by=request.user,
            )
            if person.is_appable:
                node.is_appable = True
                node.save(update_fields=["is_appable"])
        formset.save_m2m()


@admin.register(FamilyKind)
class FamilyKindAdmin(admin.ModelAdmin):
    list_display = ["name", "styles_as_house", "is_active", "sort_order"]
    list_editable = ["styles_as_house", "is_active", "sort_order"]
    search_fields = ["name"]


class ParentageUpInline(admin.TabularInline):
    model = ParentageEdge
    fk_name = "child"
    extra = 0
    raw_id_fields = ["parent", "born_within_union", "secret"]
    verbose_name = "Parent"
    verbose_name_plural = "Parents"


class FamilyMembershipInline(admin.TabularInline):
    model = FamilyMembership
    extra = 0


class KinspersonTraitValueInline(admin.TabularInline):
    """Pinned appearance values (#2815) — authored or back-inferred."""

    model = KinspersonTraitValue
    extra = 0
    raw_id_fields = ["trait", "option"]


@admin.register(Kinsperson)
class KinspersonAdmin(admin.ModelAdmin):
    """Staff authoring surface for the kinship graph (#2062)."""

    autocomplete_fields = ["created_by"]

    list_display = [
        "display_name",
        "definition_tier",
        "species",
        "power_band",
        "family",
        "is_deceased",
        "is_appable",
        "deferred_definer",
    ]
    list_filter = [
        "definition_tier",
        "power_band",
        "species",
        "is_deceased",
        "is_appable",
        "family__kind",
    ]
    search_fields = ["name", "description", "family__name"]
    raw_id_fields = ["sheet", "functionary", "deferred_definer"]
    inlines = [ParentageUpInline, FamilyMembershipInline, KinspersonTraitValueInline]


@admin.register(ParentageEdge)
class ParentageEdgeAdmin(admin.ModelAdmin):
    list_display = ["child", "kind", "parent", "is_ritual_invoker", "is_public_record", "is_true"]
    list_filter = ["kind", "is_ritual_invoker", "is_public_record", "is_true"]
    search_fields = ["child__name", "parent__name"]
    raw_id_fields = ["child", "parent", "born_within_union", "secret"]


@admin.register(KinSlotPool)
class KinSlotPoolAdmin(admin.ModelAdmin):
    list_display = ["family", "description", "count_remaining"]
    list_filter = ["family__kind"]
    search_fields = ["family__name", "description"]
    filter_horizontal = ["parents", "allowed_genders"]


@admin.register(Roster)
class RosterAdmin(admin.ModelAdmin):
    list_display = [
        "name",
        "roster_type",
        "description",
        "is_active",
        "allow_applications",
        "sort_order",
    ]
    list_filter = ["roster_type", "is_active", "allow_applications"]
    search_fields = ["name", "roster_type", "description"]
    ordering = ["sort_order", "name"]


@admin.register(RosterEntry)
class RosterEntryAdmin(admin.ModelAdmin):
    list_display = [
        "character_sheet",
        "roster",
        "activity_requirement",
        "joined_roster",
        "profile_picture",
    ]
    list_filter = ["roster", "activity_requirement", "joined_roster"]
    search_fields = ["character_sheet__character__db_key"]
    readonly_fields = ["joined_roster", "created_date", "updated_date"]

    # Use autocomplete for CharacterSheet (could be many) and profile_picture
    autocomplete_fields = ["character_sheet", "created_by_account", "profile_picture"]
    # Roster is a lookup table with few entries, keep default widget

    fieldsets = (
        (
            "Character Info",
            {"fields": ("character_sheet", "roster", "activity_requirement", "profile_picture")},
        ),
        (
            "History",
            {"fields": ("joined_roster", "previous_roster"), "classes": ("collapse",)},
        ),
        ("Staff Notes", {"fields": ("gm_notes",), "classes": ("collapse",)}),
        (
            "Timestamps",
            {
                "fields": ("created_date", "updated_date", "last_puppeted"),
                "classes": ("collapse",),
            },
        ),
    )


@admin.register(RosterTenure)
class RosterTenureAdmin(admin.ModelAdmin):
    list_display = [
        "roster_entry",
        "display_name",
        "start_date",
        "end_date",
        "is_current",
    ]
    list_filter = ["start_date", "end_date", "player_number"]
    search_fields = [
        "roster_entry__character_sheet__character__db_key",
        "player_data__account__username",
    ]
    readonly_fields = ["display_name"]
    date_hierarchy = "start_date"

    # Use autocomplete for user-populated tables that could be large
    autocomplete_fields = ["roster_entry", "player_data", "approved_by"]

    fieldsets = (
        (
            "Tenure Info",
            {
                "fields": (
                    "player_data",
                    "roster_entry",
                    "player_number",
                    "display_name",
                ),
            },
        ),
        (
            "Timeline",
            {
                "fields": (
                    "start_date",
                    "end_date",
                    "applied_date",
                    "approved_date",
                    "approved_by",
                ),
            },
        ),
        ("Media", {"fields": ("photo_folder",), "classes": ("collapse",)}),
        ("Staff Notes", {"fields": ("tenure_notes",), "classes": ("collapse",)}),
    )

    def is_current(self, obj):
        return obj.is_current

    is_current.boolean = True
    is_current.short_description = "Current"


@admin.register(RosterApplication)
class RosterApplicationAdmin(admin.ModelAdmin):
    list_display = ["player_data", "character", "status", "applied_date", "reviewed_by"]
    list_filter = ["status", "applied_date", "reviewed_date"]
    search_fields = ["player_data__account__username", "character__name"]
    readonly_fields = ["applied_date", "reviewed_date"]
    date_hierarchy = "applied_date"

    # Use autocomplete for user-populated tables that could be large
    autocomplete_fields = ["character", "player_data", "reviewed_by"]

    fieldsets = (
        ("Application Info", {"fields": ("player_data", "character", "status")}),
        ("Timeline", {"fields": ("applied_date", "reviewed_date", "reviewed_by")}),
        ("Content", {"fields": ("application_text",)}),
        ("Review", {"fields": ("review_notes",), "classes": ("collapse",)}),
    )

    actions = ["approve_applications", "deny_applications"]

    def approve_applications(self, request, queryset):
        count = 0
        try:
            staff_player_data = request.user.player_data
        except AttributeError:
            staff_player_data = None
        if not staff_player_data:
            self.message_user(
                request,
                "You must have PlayerData to approve applications.",
                level="ERROR",
            )
            return

        from world.roster.services.slots import SlotsFullError  # noqa: PLC0415

        for application in queryset.filter(status="pending"):
            try:
                approved = application.approve(staff_player_data)
            except SlotsFullError as exc:
                self.message_user(
                    request,
                    f"Application {application.pk} not approved: {exc.user_message}",
                    level="ERROR",
                )
                continue
            if approved:
                count += 1

        self.message_user(request, f"Approved {count} applications.")

    approve_applications.short_description = "Approve selected applications"

    def deny_applications(self, request, queryset):
        count = 0
        try:
            staff_player_data = request.user.player_data
        except AttributeError:
            staff_player_data = None
        if not staff_player_data:
            self.message_user(
                request,
                "You must have PlayerData to deny applications.",
                level="ERROR",
            )
            return

        for application in queryset.filter(status="pending"):
            if application.deny(staff_player_data, "Denied via admin action"):
                count += 1

        self.message_user(request, f"Denied {count} applications.")

    deny_applications.short_description = "Deny selected applications"


@admin.register(TenureDisplaySettings)
class TenureDisplaySettingsAdmin(admin.ModelAdmin):
    list_display = [
        "tenure",
        "public_character_info",
        "show_online_status",
        "plot_involvement",
    ]
    list_filter = [
        "public_character_info",
        "show_online_status",
        "allow_pages",
        "plot_involvement",
    ]
    search_fields = ["tenure__roster_entry__character_sheet__character__db_key"]
    readonly_fields = ["created_date", "updated_date"]

    # Use autocomplete for tenure (there could be many)
    autocomplete_fields = ["tenure"]

    fieldsets = (
        (
            "Display Preferences",
            {"fields": ("tenure", "public_character_info", "show_online_status")},
        ),
        ("Communication", {"fields": ("allow_pages", "allow_tells")}),
        ("Roleplay", {"fields": ("rp_preferences", "plot_involvement")}),
        (
            "Timestamps",
            {"fields": ("created_date", "updated_date"), "classes": ("collapse",)},
        ),
    )


@admin.register(TenureMedia)
class TenureMediaAdmin(admin.ModelAdmin):
    list_display = ["media", "tenure", "roster_entry", "crop_width", "sort_order"]
    search_fields = [
        "tenure__roster_entry__character_sheet__character__db_key",
        "roster_entry__character_sheet__character__db_key",
        "media__title",
    ]

    autocomplete_fields = ["tenure", "roster_entry", "media", "look"]

    fieldsets = (
        # Exactly one of tenure (a player's upload) or roster entry (character art, #4151).
        ("Link", {"fields": ("tenure", "roster_entry", "media")}),
        ("Look", {"fields": ("crop_x", "crop_y", "crop_width", "look")}),
        ("Settings", {"fields": ("sort_order",)}),
    )


@admin.register(HiddenCharacterArt)
class HiddenCharacterArtAdmin(admin.ModelAdmin):
    list_display = ["tenure", "picture"]
    autocomplete_fields = ["tenure", "picture"]


@admin.register(PlayerMail)
class PlayerMailAdmin(admin.ModelAdmin):
    list_display = [
        "sender_tenure",
        "recipient_tenure",
        "subject",
        "sent_date",
        "is_read",
        "archived",
    ]
    list_filter = ["sent_date", "read_date", "archived"]
    search_fields = [
        "sender_tenure__player_data__account__username",
        "sender_tenure__roster_entry__character_sheet__character__db_key",
        "recipient_tenure__roster_entry__character_sheet__character__db_key",
        "subject",
    ]
    readonly_fields = ["sent_date", "read_date"]
    date_hierarchy = "sent_date"

    # Use autocomplete for user-populated tables
    autocomplete_fields = [
        "sender_tenure",
        "recipient_tenure",
        "in_reply_to",
    ]

    fieldsets = (
        (
            "Message Info",
            {
                "fields": (
                    "sender_tenure",
                    "recipient_tenure",
                    "subject",
                ),
            },
        ),
        ("Content", {"fields": ("message",)}),
        ("Threading", {"fields": ("in_reply_to",), "classes": ("collapse",)}),
        ("Status", {"fields": ("sent_date", "read_date", "archived")}),
    )

    def is_read(self, obj):
        return obj.is_read

    is_read.boolean = True
    is_read.short_description = "Read"


class NPCPresetTraitLineInline(admin.TabularInline):
    model = NPCPresetTraitLine
    extra = 1
    autocomplete_fields = ["trait"]


class NPCPresetSkillLineInline(admin.TabularInline):
    model = NPCPresetSkillLine
    extra = 1
    autocomplete_fields = ["skill"]


@admin.register(NPCStatlinePreset)
class NPCStatlinePresetAdmin(admin.ModelAdmin):
    """Staff authoring surface for the Story-NPC statline catalog (#3427)."""

    list_display = ["name", "description"]
    search_fields = ["name", "description"]
    inlines = [NPCPresetTraitLineInline, NPCPresetSkillLineInline]


@admin.register(UnionKind)
class UnionKindAdmin(admin.ModelAdmin):
    """#3831 - authorable union vocabulary (marriage, consortium, concubinage...)."""

    list_display = ["name", "realm", "confers_wedlock", "stature_share_pct", "max_concurrent"]
    list_filter = ["confers_wedlock", "contributes_to_origin_house", "requires_landed_title"]
    search_fields = ["name"]
    list_select_related = ["realm"]
    autocomplete_fields = ["realm"]


@admin.register(Soul)
class SoulAdmin(admin.ModelAdmin):
    """#3831 - a soul with an ordered chain of incarnations."""

    list_display = ["__str__"]
    search_fields = ["notes"]


@admin.register(SoulIncarnation)
class SoulIncarnationAdmin(admin.ModelAdmin):
    """#3831 - one life of a soul."""

    list_display = ["soul", "sequence", "kinsperson", "is_public_record", "is_true"]
    list_filter = ["is_public_record", "is_true"]
    search_fields = ["kinsperson__name"]
    list_select_related = ["soul", "kinsperson"]
    autocomplete_fields = ["kinsperson"]
    raw_id_fields = ["soul", "secret"]
