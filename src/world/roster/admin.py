"""
Django admin configuration for roster models.
"""

import contextlib

from django import forms
from django.contrib import admin
from django.contrib.admin.widgets import AutocompleteSelect, ForeignKeyRawIdWidget
from django.core.exceptions import ValidationError
from django.forms import BaseInlineFormSet, ModelForm
from django.http import HttpRequest
from django.utils.html import format_html

from world.admin_utils import OneRowPerFormSet
from world.roster.models import (
    Family,
    FamilyKind,
    FamilyMembership,
    HiddenCharacterArt,
    KinSlotPool,
    Kinsperson,
    KinspersonTraitValue,
    NPCLoan,
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
    StoryNPCSettings,
    TenureDisplaySettings,
    TenureMedia,
    Union,
    UnionKind,
)
from world.roster.services.kinship import (
    KinshipServiceError,
    already_married_message,
    binding_marriage_of,
    create_person,
    end_union,
    open_wedlock_union_among,
    record_union,
    separate_union,
    wedlock_union_kind,
)
from world.secrets.models import Secret


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
    formset = OneRowPerFormSet
    fk_name = "child"
    extra = 0
    raw_id_fields = ["parent", "born_within_union", "secret"]
    verbose_name = "Parent"
    verbose_name_plural = "Parents"


class FamilyMembershipInline(admin.TabularInline):
    model = FamilyMembership
    extra = 0


#: The through row between a person and a union; the Spouses section's model (#4232).
SpouseRow = Union.members.through


def _spouse_row_label(row: SpouseRow) -> str:
    """The row heading the admin prints for an existing row: the union, not
    "Union_members object (1)". The through model is Django's own, so its label
    is set here rather than on a model class of ours."""
    return str(row.union)


SpouseRow.__str__ = _spouse_row_label


class SpouseForm(ModelForm):
    """One row of the Spouses section: the union's own fields, carried on its through row.

    A new row names a partner (an existing node, picked through the Kinsperson
    autocomplete) and the union to record between them; an existing row edits the
    union it already stands for, and its other members are shown read-only, since a
    union may hold more than two. ``KinspersonAdmin.save_formset`` writes every row
    through the kinship services, never ``save()``.
    """

    partner = forms.ModelChoiceField(
        queryset=Kinsperson.objects.all(),
        required=False,
        widget=AutocompleteSelect(Union.members.field, admin.site),
        help_text="Who the person marries. Set on a new row only.",
    )
    kind = forms.ModelChoiceField(queryset=UnionKind.objects.all())
    started_at = forms.DateTimeField(required=False)
    separated_at = forms.DateTimeField(
        required=False, help_text="Set when they live apart; the marriage stands (#4870)."
    )
    ended_at = forms.DateTimeField(required=False, help_text="Set to end the marriage.")
    is_public_record = forms.BooleanField(required=False, initial=True)
    is_true = forms.BooleanField(required=False, initial=True)
    secret = forms.ModelChoiceField(
        queryset=Secret.objects.all(),
        required=False,
        widget=ForeignKeyRawIdWidget(Union.secret.field.remote_field, admin.site),
    )

    class Meta:
        model = SpouseRow
        fields: list[str] = []

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        union = self.instance.union if self.instance.pk else None
        if union is not None:
            self.initial.update(
                kind=union.kind_id,
                started_at=union.started_at,
                separated_at=union.separated_at,
                ended_at=union.ended_at,
                is_public_record=union.is_public_record,
                is_true=union.is_true,
                secret=union.secret_id,
            )
            return
        with contextlib.suppress(KinshipServiceError):
            self.initial.setdefault("kind", wedlock_union_kind().pk)

    def clean(self) -> dict:
        cleaned = super().clean()
        if self.instance.pk:
            return cleaned
        partner = cleaned.get("partner")
        if partner is None:
            self.add_error("partner", "Name who the person marries.")
            return cleaned
        # On the add page the parent is unsaved: the formset sets only the id, and it
        # is None, so the relation itself cannot be read. The two checks against the
        # person need a saved person; a new one has no marriages to clash with.
        person_pk = self.instance.kinsperson_id
        if person_pk is None:
            return cleaned
        if partner.pk == person_pk:
            self.add_error("partner", "A person cannot marry themselves.")
            return cleaned
        person = Kinsperson.objects.get(pk=person_pk)
        if open_wedlock_union_among([person, partner]) is not None:
            self.add_error("partner", "They already share an open marriage.")
            return cleaned
        kind = cleaned.get("kind")
        if kind is not None and kind.confers_wedlock:
            # A marriage must end, by death or dissolution, before either party
            # marries again (ruling on #4232); a consort or paramour kind is no marriage.
            for party in (person, partner):
                if binding_marriage_of(party) is not None:
                    self.add_error("partner", already_married_message(party))
                    return cleaned
        return cleaned


class SpouseFormSet(OneRowPerFormSet):
    """Refuses to delete a union a marriage pact or a recorded birth still points at."""

    def clean(self) -> None:
        super().clean()
        from world.societies.houses.models import MarriagePact  # noqa: PLC0415

        for form in self.deleted_forms:
            union = form.instance.union
            dependents = []
            if MarriagePact.objects.filter(union=union).exists():
                dependents.append("a marriage pact")
            if union.births.exists():
                dependents.append("a recorded birth")
            if dependents:
                what = " and ".join(dependents)
                msg = (
                    f"{union} cannot be removed: {what} depends on it. "
                    "Set an end date to end the marriage instead."
                )
                raise ValidationError(msg)


class SpouseInline(admin.TabularInline):
    """The person's unions, added and ended through the kinship services (#4232)."""

    model = SpouseRow
    fk_name = "kinsperson"
    form = SpouseForm
    formset = SpouseFormSet
    extra = 0
    verbose_name = "Spouse"
    verbose_name_plural = "Spouses"
    readonly_fields = ["spouses"]
    fields = [
        "spouses",
        "partner",
        "kind",
        "started_at",
        "separated_at",
        "ended_at",
        "is_public_record",
        "is_true",
        "secret",
    ]

    @admin.display(description="Married to")
    def spouses(self, row: SpouseRow) -> str:
        if row.pk is None:
            return "-"
        others = row.union.members.exclude(pk=row.kinsperson_id)
        return ", ".join(member.display_name for member in others) or "-"


class KinspersonTraitValueInline(admin.TabularInline):
    """Pinned appearance values (#2815) — authored or back-inferred."""

    model = KinspersonTraitValue
    formset = OneRowPerFormSet
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
    # A sheet-bound person's ``name`` column is empty (the sheet names them), so the
    # autocomplete the Spouses section's partner picker uses has to search the
    # character's key too, or no player character can ever be picked (#4232).
    search_fields = ["name", "description", "family__name", "sheet__character__db_key"]
    raw_id_fields = ["sheet", "functionary", "deferred_definer"]
    inlines = [ParentageUpInline, FamilyMembershipInline, SpouseInline, KinspersonTraitValueInline]

    def save_formset(
        self, request: HttpRequest, form: ModelForm, formset: BaseInlineFormSet, change: bool
    ) -> None:
        """Spouses rows go through the kinship services (#4232); the rest save as usual.

        A new row records a union between the person and the named partner, ended at
        once when the row carries an end date. An existing row writes its union's own
        fields, and an end date set on an open union goes through ``end_union``. A
        deleted row deletes the union; ``SpouseFormSet.clean`` has already refused
        one a pact or a birth depends on.
        """
        if formset.model is not SpouseRow:
            super().save_formset(request, form, formset, change)
            return
        # The admin's change message reads these off a saved formset; this one never
        # calls ``formset.save()``, so they are filled by hand with the unions written.
        formset.new_objects = []
        formset.changed_objects = []
        formset.deleted_objects = []
        person = form.instance
        for row_form in formset.deleted_forms:
            union = row_form.instance.union
            formset.deleted_objects.append(union)
            union.delete()
        for row_form in formset.forms:
            if row_form in formset.deleted_forms or not row_form.has_changed():
                continue
            data = row_form.cleaned_data
            if row_form.instance.pk:
                union = row_form.instance.union
                _write_union(union, data)
                formset.changed_objects.append((union, row_form.changed_data))
                continue
            union = record_union(
                kind=data["kind"],
                members=[person, data["partner"]],
                started_at=data.get("started_at"),
                is_public_record=data.get("is_public_record", False),
                is_true=data.get("is_true", False),
                secret=data.get("secret"),
            )
            if data.get("separated_at"):
                separate_union(union, separated_at=data["separated_at"])
            if data.get("ended_at"):
                end_union(union, ended_at=data["ended_at"])
            formset.new_objects.append(union)


def _write_union(union: Union, data: dict) -> None:
    """An existing Spouses row's edits onto its union, ending it through ``end_union``."""
    union.kind = data["kind"]
    union.started_at = data.get("started_at")
    union.is_public_record = data.get("is_public_record", False)
    union.is_true = data.get("is_true", False)
    union.secret = data.get("secret")
    # A separation newly dated goes through ``separate_union``; a cleared one is lifted.
    separated_at = data.get("separated_at")
    if union.separated_at is None and separated_at:
        separate_union(union, separated_at=separated_at)
    else:
        union.separated_at = separated_at
    ended_at = data.get("ended_at")
    if union.ended_at is None and ended_at:
        union.save(
            update_fields=[
                "kind",
                "started_at",
                "separated_at",
                "is_public_record",
                "is_true",
                "secret",
            ]
        )
        end_union(union, ended_at=ended_at)
        return
    union.ended_at = ended_at
    union.save()


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
    formset = OneRowPerFormSet
    extra = 1
    autocomplete_fields = ["trait"]


class NPCPresetSkillLineInline(admin.TabularInline):
    model = NPCPresetSkillLine
    formset = OneRowPerFormSet
    extra = 1
    autocomplete_fields = ["skill"]


@admin.register(NPCStatlinePreset)
class NPCStatlinePresetAdmin(admin.ModelAdmin):
    """Staff authoring surface for the Story-NPC statline catalog (#3427)."""

    list_display = ["name", "description"]
    search_fields = ["name", "description"]
    inlines = [NPCPresetTraitLineInline, NPCPresetSkillLineInline]


@admin.register(StoryNPCSettings)
class StoryNPCSettingsAdmin(admin.ModelAdmin):
    list_display = ["roster_entry", "lend_policy", "borrow_audience", "listed_on_npc_roster"]
    list_filter = ["lend_policy", "borrow_audience", "listed_on_npc_roster", "is_template"]
    raw_id_fields = ["roster_entry"]


@admin.register(NPCLoan)
class NPCLoanAdmin(admin.ModelAdmin):
    list_display = ["roster_entry", "borrower", "status", "created_at", "started_at", "ended_at"]
    list_filter = ["status"]
    raw_id_fields = ["roster_entry", "borrower", "offered_by", "scene"]


@admin.register(UnionKind)
class UnionKindAdmin(admin.ModelAdmin):
    """#3831 - authorable union vocabulary (marriage, consortium, concubinage...)."""

    list_display = [
        "name",
        "realm",
        "confers_wedlock",
        "is_betrothal",
        "stature_share_pct",
        "max_concurrent",
    ]
    list_filter = [
        "confers_wedlock",
        "is_betrothal",
        "contributes_to_origin_house",
        "requires_landed_title",
    ]
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
