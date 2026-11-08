"""Journeys for keeping magical rolls on Magic skills (#4547).

The skills a magical roll adds are bespoke Magic skills that staff make and point each
roll at (ADR-4450). They are never skills a character picks anywhere else, so a cast
never counts one skill twice.

- Staff set a magic skill in admin: each of the three pickers (a magical activity's
  skill, a casting style's skill, a technique's own skill) offers Magic skills only and
  refuses any other skill on save. The Path and Gift forms carry no skill since #5002.
- A caster on a Path whose style's skill is a Magic skill casts through
  ``cast_technique`` against the seeded "Technique Cast" fallback check: the roll is
  the check type's stat plus the technique skill once. The seed used to weight an
  "occult" trait into that check as well, so a staff Magic skill called occult
  counted twice.
- Staff open the Required content dashboard and see each check type that weights a
  Magic skill directly, with a link to those check types in admin.
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import patch

from django.contrib.admin.widgets import RelatedFieldWidgetWrapper
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.forms.widgets import MultiWidget, SelectMultiple
from django.urls import reverse

from integration_tests.harness import JourneyCase
from world.checks.factories import CheckTypeFactory, CheckTypeTraitFactory
from world.checks.models import CheckType
from world.checks.services import perform_check
from world.checks.test_helpers import force_check_outcome
from world.checks.types import CheckResult, ExtraTraitTerm
from world.classes.factories import PathFactory
from world.covenants.factories import CombatStyleFactory
from world.covenants.models import CombatStyle
from world.magic.constants import GiftKind, MagicActivity
from world.magic.factories import (
    BinaryEffectTypeFactory,
    CharacterAnimaFactory,
    GiftFactory,
    TechniqueFactory,
    TechniqueStyleFactory,
)
from world.magic.models import Technique, TechniqueStyle
from world.magic.models.magic_activity import MagicActivitySkill
from world.magic.seeds_cast import TECHNIQUE_CAST_CHECK_TYPE_NAME, ensure_technique_cast_content
from world.progression.factories import CharacterPathHistoryFactory
from world.scenes.factories import SceneFactory
from world.scenes.tests.cast_test_helpers import grant_technique
from world.skills.factories import SkillFactory
from world.traits.factories import CheckSystemSetupFactory
from world.traits.models import (
    CharacterTraitValue,
    CheckOutcome,
    PointConversionRange,
    Trait,
    TraitCategory,
    TraitType,
)
from world.vitals.models import CharacterVitals

SKILL_VALUE = 30


def _magic_skill(name: str) -> Trait:
    return SkillFactory(name=name, category=TraitCategory.MAGIC)


def _posted_value(bound) -> object | None:
    """What the browser posts for one bound field; None for an unchecked checkbox."""
    value = bound.value()
    if value is None:
        widget = bound.field.widget
        if isinstance(widget, RelatedFieldWidgetWrapper):
            widget = widget.widget
        return None if isinstance(widget, SelectMultiple) else ""
    if isinstance(value, bool):
        return "on" if value else None
    if isinstance(value, list):
        return [str(v) for v in value]
    return str(value)


def _page_as_post(response) -> dict[str, object]:
    """The change page's form and inline formsets, as a browser would post them unchanged.

    Extra inline forms post their initial values too, as the browser renders them, so
    an untouched extra row stays unchanged and is skipped.
    """
    bound_fields = list(response.context["adminform"].form)
    for inline in response.context["inline_admin_formsets"]:
        formset = inline.formset
        bound_fields.extend(formset.management_form)
        for form in formset.forms:
            bound_fields.extend(form)
    data: dict[str, object] = {}
    for bound in bound_fields:
        widget = bound.field.widget
        if isinstance(widget, MultiWidget):
            for i, part in enumerate(widget.decompress(bound.value())):
                data[f"{bound.html_name}_{i}"] = "" if part is None else str(part)
            continue
        value = _posted_value(bound)
        if value is not None:
            data[bound.html_name] = value
    return data


def _errors(response) -> list:
    """Every form and formset error on a re-rendered change page, for a failing assertion."""
    if response.status_code == 302:
        return []
    found = [response.context["adminform"].form.errors]
    for inline in response.context["inline_admin_formsets"]:
        found.extend(inline.formset.errors)
        found.extend(inline.formset.non_form_errors())
    return found


class StaffSetAMagicSkillInAdmin(JourneyCase):
    """Staff point each magic skill picker at a skill; only a Magic skill is taken."""

    def setUp(self) -> None:
        super().setUp()
        staff = get_user_model().objects.create_user(
            username="warden", password="pw", is_staff=True, is_superuser=True
        )
        self.client.force_login(staff)
        self.thaumaturgy = _magic_skill("Thaumaturgy")
        self.persuasion = SkillFactory(name="Persuasion", category=TraitCategory.SOCIAL)
        # A combat style's own skill is a Magic skill no picker offers (#4921), so every
        # "offered" set below holds Thaumaturgy alone.
        self.daring_dance = _magic_skill("The Daring Dance")
        CombatStyleFactory(name="The Daring Dance", skill=self.daring_dance)

    def offered(self, model_name: str, field_name: str) -> set[str]:
        """The skills the picker's search box offers, as the admin widget asks for them."""
        response = self.client.get(
            reverse("admin:autocomplete"),
            {"app_label": "arxii", "model_name": model_name, "field_name": field_name},
        )
        self.assertEqual(response.status_code, 200)
        return {row["text"] for row in response.json()["results"]}

    def save_change_form(self, url: str, field: str, skill: Trait):
        page = self.client.get(url)
        self.assertEqual(page.status_code, 200)
        data = _page_as_post(page)
        data[field] = str(skill.pk)
        return self.client.post(url, data)

    def assert_refused_then_taken(self, url: str, field: str, row) -> None:
        refused = self.save_change_form(url, field, self.persuasion)

        self.assertEqual(refused.status_code, 200)
        self.assertIn(field, refused.context["adminform"].form.errors)
        row.refresh_from_db()
        self.assertIsNone(getattr(row, f"{field}_id"))

        taken = self.save_change_form(url, field, self.thaumaturgy)

        self.assertEqual(taken.status_code, 302, _errors(taken))
        row.refresh_from_db()
        self.assertEqual(getattr(row, f"{field}_id"), self.thaumaturgy.pk)

    def test_a_magical_activity_takes_a_magic_skill_only(self) -> None:
        self.assertEqual(self.offered("magicactivityskill", "skill"), {"Thaumaturgy (Skill)"})
        url = reverse("admin:arxii_magicactivityskill_add")
        row = {"activity": MagicActivity.RITUAL_WORKING, "weight": "1.00"}

        refused = self.client.post(url, {**row, "skill": self.persuasion.pk})

        self.assertEqual(refused.status_code, 200)
        self.assertIn("skill", refused.context["adminform"].form.errors)
        self.assertFalse(MagicActivitySkill.objects.exists())

        taken = self.client.post(url, {**row, "skill": self.thaumaturgy.pk})

        self.assertEqual(taken.status_code, 302, taken.content[:500])
        self.assertEqual(
            MagicActivitySkill.objects.get(activity=MagicActivity.RITUAL_WORKING).skill,
            self.thaumaturgy,
        )

    def test_a_casting_style_takes_a_magic_skill_only(self) -> None:
        style = TechniqueStyleFactory(name="Incantation")
        self.assertEqual(self.offered("techniquestyle", "skill"), {"Thaumaturgy (Skill)"})

        self.assert_refused_then_taken(
            reverse("admin:arxii_techniquestyle_change", args=[style.pk]), "skill", style
        )

    def test_the_path_and_gift_forms_carry_no_skill(self) -> None:
        """The skill is set once, on the style; a Path or Gift only picks its style (#5002)."""
        for url in (
            reverse("admin:arxii_path_change", args=[PathFactory().pk]),
            reverse("admin:arxii_gift_change", args=[GiftFactory(kind=GiftKind.MINOR).pk]),
        ):
            with self.subTest(url=url):
                page = self.client.get(url)
                self.assertEqual(page.status_code, 200)
                fields = set(page.context["adminform"].form.fields)
                self.assertIn("style", fields)
                self.assertNotIn("technique_skill", fields)
                self.assertNotIn("skill", fields)

    def test_a_technique_takes_a_magic_skill_only(self) -> None:
        technique = TechniqueFactory()
        self.assertEqual(self.offered("technique", "skill"), {"Thaumaturgy (Skill)"})

        self.assert_refused_then_taken(
            reverse("admin:arxii_technique_change", args=[technique.pk]), "skill", technique
        )

    def test_a_row_saved_outside_admin_is_refused_by_model_validation(self) -> None:
        """``full_clean`` holds the same rule for any other writer, with the reason."""
        rows = (
            MagicActivitySkill(activity=MagicActivity.CEREMONY, skill=self.persuasion),
            TechniqueStyle(name="Glass", skill=self.persuasion),
            Technique(gift=GiftFactory(), name="Glass Edge", skill=self.persuasion),
        )
        for row in rows:
            with self.subTest(model=type(row).__name__):
                errors = self.validation_errors(row)
                self.assertIn("skill", errors)
                self.assertIn("Magic category", " ".join(errors["skill"]))

    def test_a_style_skill_is_refused_by_every_picker(self) -> None:
        """A combat style's skill is trained in creation; no magical roll adds it (#4921)."""
        rows = (
            MagicActivitySkill(activity=MagicActivity.CEREMONY, skill=self.daring_dance),
            TechniqueStyle(name="Steps", skill=self.daring_dance),
            Technique(gift=GiftFactory(), name="Step Edge", skill=self.daring_dance),
        )
        for row in rows:
            with self.subTest(model=type(row).__name__):
                errors = self.validation_errors(row)
                self.assertIn("skill", errors)
                self.assertIn("not a combat style's skill", " ".join(errors["skill"]))

    def test_a_style_refuses_a_skill_a_picker_already_adds(self) -> None:
        """The other way round: a style never takes a picker's skill (#4921)."""
        TechniqueStyleFactory(skill=self.thaumaturgy)
        style = CombatStyle(name="Veil and Needle", defense_style="barrier", skill=self.thaumaturgy)

        errors = self.validation_errors(style)

        self.assertIn("skill", errors)
        self.assertIn("already adds this skill", " ".join(errors["skill"]))
        style.skill = _magic_skill("Veil and Needle")
        self.assertEqual(self.validation_errors(style), {})

    def test_a_casting_style_refuses_a_combat_style_skill_in_admin(self) -> None:
        style = TechniqueStyleFactory(name="Prayer")

        refused = self.save_change_form(
            reverse("admin:arxii_techniquestyle_change", args=[style.pk]),
            "skill",
            self.daring_dance,
        )

        self.assertEqual(refused.status_code, 200)
        self.assertIn("skill", refused.context["adminform"].form.errors)
        style.refresh_from_db()
        self.assertIsNone(style.skill_id)

    @staticmethod
    def validation_errors(row) -> dict[str, list[str]]:
        try:
            row.full_clean()
        except ValidationError as exc:
            return exc.message_dict
        return {}


class ACastCountsItsMagicSkillOnce(JourneyCase):
    """Ysmay and Hobb walk the same Path; only Ysmay has trained its Occult skill.

    The technique rolls the seeded "Technique Cast" fallback check. Staff named their
    Magic skill Occult, the name the seed used to weight into that check itself.
    """

    def setUp(self) -> None:
        super().setUp()
        CheckSystemSetupFactory.create()
        PointConversionRange.objects.get_or_create(
            trait_type=TraitType.SKILL,
            min_value=1,
            defaults={"max_value": 100, "points_per_level": 1},
        )
        self.template = ensure_technique_cast_content()
        self.occult = _magic_skill("occult")
        self.path = PathFactory(style=TechniqueStyleFactory(skill=self.occult))
        self.lantern = self.make_room("The Lantern")
        SceneFactory(room=self.lantern)
        self.technique = TechniqueFactory(
            gift=GiftFactory(),
            anima_cost=1,
            effect_type=BinaryEffectTypeFactory(),
            damage_profile=False,
            action_template=self.template,
        )
        self.ysmay = self.caster_on_the_path("Ysmay", skill_value=SKILL_VALUE)
        self.hobb = self.caster_on_the_path("Hobb", skill_value=0)

    def caster_on_the_path(self, name: str, *, skill_value: int):
        character = self.make_player(name, room=self.lantern)
        sheet = character.sheet_data
        CharacterPathHistoryFactory(character=sheet, path=self.path)
        grant_technique(sheet.primary_persona, self.technique)
        CharacterAnimaFactory(character=sheet, current=20, maximum=30)
        CharacterVitals.objects.create(
            character_sheet=sheet, health=50, max_health=50, base_max_health=50
        )
        if skill_value:
            CharacterTraitValue.objects.create(
                character=sheet, trait=self.occult, value=skill_value
            )
        return character

    def cast(self, character) -> tuple[CheckType, tuple[ExtraTraitTerm, ...], CheckResult]:
        """Cast on the web seam; return the check type, the added terms and the result."""
        rolled: list[tuple[CheckType, CheckResult]] = []

        def spy(*args, **kwargs) -> CheckResult:
            result = perform_check(*args, **kwargs)
            check_type = kwargs.get("check_type") or args[1]
            rolled.append((check_type, result))
            return result

        success = CheckOutcome.objects.get(name="Success")
        with (
            force_check_outcome(success) as capture,
            patch("actions.services.perform_check", side_effect=spy),
        ):
            outcome = self.web(character, "cast_technique", technique_id=self.technique.pk)
        self.assertTrue(outcome.detail.success, outcome.detail.message)
        self.assertEqual(len(rolled), 1)
        check_type, result = rolled[0]
        return check_type, capture.extra_traits, result

    def test_the_technique_skill_counts_once(self) -> None:
        check_type, terms, trained = self.cast(self.ysmay)

        self.assertEqual(check_type.name, TECHNIQUE_CAST_CHECK_TYPE_NAME)
        weighted = set(check_type.traits.values_list("trait__name", flat=True))
        self.assertEqual(weighted, {"willpower"})
        self.assertEqual(terms, (ExtraTraitTerm(trait=self.occult, weight=Decimal("1.00")),))
        _, _, untrained = self.cast(self.hobb)
        self.assertEqual(trained.trait_points - untrained.trait_points, SKILL_VALUE)


class StaffSeeWhichCheckTypesWeightAMagicSkill(JourneyCase):
    """The dashboard names each check type that builds a Magic skill into itself."""

    def setUp(self) -> None:
        super().setUp()
        staff = get_user_model().objects.create_user(
            username="warden", password="pw", is_staff=True, is_superuser=True
        )
        self.client.force_login(staff)

    def test_the_row_lists_the_check_types_and_links_to_them(self) -> None:
        occult = _magic_skill("Occult Theory")
        tiding = CheckTypeFactory(name="Reading the Tides")
        CheckTypeTraitFactory(check_type=tiding, trait=occult)
        plain = CheckTypeFactory(name="Climbing")
        CheckTypeTraitFactory(check_type=plain, trait=SkillFactory())

        page = self.client.get(reverse("admin_ops_required_content"))

        self.assertEqual(page.status_code, 200)
        body = page.content.decode()
        self.assertIn("Check types weight no Magic skill", body)
        self.assertIn("Reading the Tides: Occult Theory", body)
        self.assertNotIn("Climbing:", body)
        link = f"{reverse('admin:arxii_checktype_changelist')}?id__in={tiding.pk}"
        self.assertIn(f'href="{link}"', body)

        listed = self.client.get(link)

        self.assertEqual(listed.status_code, 200)
        self.assertEqual(list(listed.context["cl"].result_list), [tiding])

    def test_a_fresh_seed_leaves_the_row_clear(self) -> None:
        ensure_technique_cast_content()

        page = self.client.get(reverse("admin_ops_required_content"))

        self.assertEqual(page.status_code, 200)
        self.assertNotIn("Technique Cast: ", page.content.decode())
