"""Skill admin pieces shared by the Skill and Trait admin pages (#5006).

A skill is authored on the Trait page's Skill section and edited on the Skill page, and both
saves make its modifier target. These live here, not in either app's admin module, so neither
admin imports the other's (the ``world/societies/admin_inlines.py`` precedent). Nothing here
registers an admin.
"""

from django.contrib import admin, messages
from django.core.exceptions import ValidationError
from django.forms.models import BaseInlineFormSet
from django.http import HttpRequest
from django.urls import reverse
from django.utils.html import format_html, format_html_join

from world.contributors.admin import CREDIT_FIELDSET
from world.mechanics.services import ensure_skill_target
from world.skills.models import Skill
from world.traits.models import TraitType

SKILL_ON_NON_SKILL_TRAIT_MESSAGE = (
    "Only a trait of type Skill can be a skill. Set Trait type to Skill, or clear the "
    "Skill section."
)


def ensure_skill_target_or_warn(request: HttpRequest, skill: Skill) -> None:
    """Make sure a modifier target points at ``skill``'s trait, warning staff if not (#4820).

    A skill rolls a distinction's bonus only through a stat-category ``ModifierTarget``
    whose ``target_trait`` is the skill's trait; without one a pasted ``+10 <skill>`` is
    refused. Both admin paths that save a skill call this: the Skill page and the Skill
    section on the Trait page (#5006). An explicit call, not a signal (ADR-0009).
    """
    if ensure_skill_target(skill.trait) is None:
        messages.warning(
            request,
            f"No modifier target was made for {skill.name}: another category already "
            "has a target of that name. Retarget that row to this skill's trait on "
            "the Modifier targets admin.",
        )


class SkillOnTraitFormSet(BaseInlineFormSet):
    """Refuses a Skill section filled in on a trait that is not of type Skill (#5006).

    ``Skill.trait``'s ``limit_choices_to`` guards the Skill page's picker, but an inline
    sets the parent itself and never runs that check, so this formset does.
    """

    def clean(self) -> None:
        super().clean()
        if self.instance.trait_type == TraitType.SKILL:
            return
        for form in self.forms:
            if form.has_changed() and not self._should_delete_form(form):
                raise ValidationError(SKILL_ON_NON_SKILL_TRAIT_MESSAGE)


class SkillOnTraitInline(admin.StackedInline):
    """The Skill section of the Trait page: author a skill on one page (#5006).

    A skill is a Trait of type Skill plus this row (tooltip, sheet order, active flag).
    Leaving the section untouched makes no skill, since some skill-type traits are rolled
    by checks without being a skill a character trains. Specializations stay on the
    Skill page (stock admin cannot nest an inline in an inline); the section links there.
    The trait's own save runs ``ensure_skill_target_or_warn`` for a skill saved here.
    """

    model = Skill
    formset = SkillOnTraitFormSet
    extra = 1
    max_num = 1
    can_delete = False
    # Django titles a max_num=1 inline with verbose_name, so it carries the instruction.
    verbose_name = "Skill (fill in to make this trait a skill)"
    readonly_fields = ["specializations_link"]
    fieldsets = (
        (None, {"fields": ("tooltip", "display_order", "is_active", "specializations_link")}),
        CREDIT_FIELDSET,
    )

    @admin.display(description="Specializations")
    def specializations_link(self, obj: Skill | None) -> str:
        if obj is None or obj.pk is None:
            return "Save the skill first, then add specializations on its Skill page."
        url = reverse("admin:arxii_skill_change", args=[obj.pk])
        names = format_html_join(", ", "{}", ((spec.name,) for spec in obj.specializations.all()))
        return format_html(
            '{} <a href="{}">Edit specializations on the Skill page</a>',
            names or "None yet.",
            url,
        )
