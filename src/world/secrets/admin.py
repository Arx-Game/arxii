from django import forms
from django.contrib import admin, messages

from world.admin_utils import OneRowPerFormSet
from world.distinctions.models import CharacterDistinction
from world.distinctions.services import set_secret_distinctions
from world.secrets.constants import DEFAULT_VICTIM_SEVERITY_BY_LEVEL
from world.secrets.models import Secret, SecretCategory, SecretKnowledge, SecretVictim


@admin.register(SecretCategory)
class SecretCategoryAdmin(admin.ModelAdmin):
    list_display = ["name", "is_active"]
    list_filter = ["is_active"]
    search_fields = ["name", "description"]


class SecretKnowledgeInline(admin.TabularInline):
    """Read-only: who knows this secret (#3679) — audit-only, edited via SecretKnowledgeAdmin."""

    model = SecretKnowledge
    formset = OneRowPerFormSet
    fields = ["roster_entry", "knows_category", "knows_consequences", "found_at"]
    readonly_fields = ["roster_entry", "knows_category", "knows_consequences", "found_at"]
    extra = 0
    can_delete = False

    def has_add_permission(self, request, obj=None):  # noqa: ARG002
        return False

    def has_change_permission(self, request, obj=None):  # noqa: ARG002
        return False


class SecretVictimInline(admin.TabularInline):
    """Who the secret's underlying fact wronged (#4448): an organization or a persona.

    ``severity`` is left out on purpose: the size of an organization victim's reaction on
    exposure is always the secret's level default, never chosen per case.
    """

    model = SecretVictim
    verbose_name_plural = "Victims"
    template = "admin/secrets/victims_inline.html"
    fields = ["organization", "persona"]
    raw_id_fields = ["organization", "persona"]
    extra = 0


#: The picker field's name on ``SecretAdminForm`` (#4528).
_PICKER = "distinctions"


class SecretAdminForm(forms.ModelForm):
    """The secret's form plus the picker (#4528): the subject's held distinctions as
    checkboxes, the ticked ones held in this secret and so private. Absent on the add
    view, where the subject is not yet known."""

    distinctions = forms.ModelMultipleChoiceField(
        queryset=CharacterDistinction.objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label="Distinctions held in this secret",
        help_text="Ticked: relocated into this secret, off the public sheet. "
        "Unticked: public again.",
    )

    class Meta:
        model = Secret
        # The admin decides the field set, as it does for its default form; this form
        # only adds the picker on top of every model field.
        fields = "__all__"  # noqa: DJ007

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        instance = self.instance
        if instance.pk is None:
            # The add view: no subject yet, so nothing to pick; the admin leaves the
            # field off the page (``SecretAdmin.get_fields``).
            return
        held = CharacterDistinction.objects.filter(
            character_id=instance.subject_sheet_id
        ).select_related("distinction")
        self.fields[_PICKER].queryset = held
        self.fields[_PICKER].initial = held.filter(secret_id=instance.pk)


@admin.register(Secret)
class SecretAdmin(admin.ModelAdmin):
    form = SecretAdminForm
    autocomplete_fields = ["scene", "subject_item_instance"]
    list_display = ["__str__", "level", "category", "provenance", "created_date"]
    list_filter = ["level", "provenance", "category"]
    search_fields = ["content", "consequences"]
    raw_id_fields = ["subject_sheet", "author_persona", "hook", "about_persona", "story"]
    readonly_fields = [
        "created_date",
        "updated_date",
        "get_default_victim_severity",
    ]
    inlines = [SecretVictimInline, SecretKnowledgeInline]

    def get_fields(self, request, obj=None):
        """The picker shows only once the secret, and so its subject, exists (#4528)."""
        fields = list(super().get_fields(request, obj))
        if obj is None:
            fields.remove(_PICKER)
        return fields

    def save_related(self, request, form, formsets, change: bool) -> None:
        """Apply the picker after the secret itself is saved (#4528)."""
        super().save_related(request, form, formsets, change)
        if not change or _PICKER not in form.cleaned_data:
            return
        linked, unlinked = set_secret_distinctions(form.instance, form.cleaned_data[_PICKER])
        if linked or unlinked:
            messages.info(
                request,
                f"{linked} distinction(s) now private in this secret; {unlinked} public again.",
            )

    @admin.display(description="Default victim severity")
    def get_default_victim_severity(self, obj: Secret) -> str:
        """What a victim organization's reputation drops by on this secret's first exposure."""
        if obj.pk is None:
            return "-"
        exposed = obj.societies_exposed.exists()
        return (
            f"{DEFAULT_VICTIM_SEVERITY_BY_LEVEL.get(obj.level, 0)} at level {obj.level}. "
            f"{'Already exposed.' if exposed else 'Not yet exposed.'}"
        )


@admin.register(SecretKnowledge)
class SecretKnowledgeAdmin(admin.ModelAdmin):
    list_display = ["__str__", "knows_category", "knows_consequences", "found_at"]
    list_filter = ["knows_category", "knows_consequences"]
    raw_id_fields = ["roster_entry", "secret"]
    readonly_fields = ["found_at"]
