"""Designed persona/mask creation flow (#1127).

Replaces the removed raw ``PersonaViewSet`` create. Validates what may be created, caps
ESTABLISHED personas, and — the load-bearing guarantee — enforces the descriptor-never-auto-attach
privacy invariant (#1109): a freshly created persona starts with a blank descriptor set, never
copied from a sibling face.
"""

from types import SimpleNamespace

from django.test import TestCase, override_settings
from rest_framework.test import APIRequestFactory, force_authenticate

from world.character_sheets.factories import CharacterSheetFactory
from world.forms.factories import (
    CharacterFormFactory,
    CharacterFormValueFactory,
    FormTraitFactory,
    FormTraitOptionFactory,
    PersonaTraitDescriptorFactory,
)
from world.forms.models import CharacterFormState, FormType, PersonaTraitDescriptor
from world.scenes.constants import PersonaType
from world.scenes.models import Persona
from world.scenes.services import (
    GuiseProfileError,
    PersonaCreationError,
    create_mask,
    create_persona,
    set_persona_profile,
)
from world.scenes.views import PersonaViewSet


class CreatePersonaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.sheet = CharacterSheetFactory()

    def test_creates_established_persona(self):
        persona = create_persona(self.sheet, name="Robert D'Vile", persona_type="established")
        assert persona.pk is not None
        assert persona.persona_type == PersonaType.ESTABLISHED
        assert persona.character_sheet_id == self.sheet.pk

    def test_rejects_primary_creation(self):
        with self.assertRaises(PersonaCreationError):
            create_persona(self.sheet, name="Fake Primary", persona_type="primary")

    def test_rejects_blank_name(self):
        with self.assertRaises(PersonaCreationError):
            create_persona(self.sheet, name="   ", persona_type="established")

    @override_settings(MAX_ESTABLISHED_PERSONAS_PER_SHEET=2)
    def test_enforces_established_cap(self):
        create_persona(self.sheet, name="One", persona_type="established")
        create_persona(self.sheet, name="Two", persona_type="established")
        with self.assertRaises(PersonaCreationError):
            create_persona(self.sheet, name="Three", persona_type="established")

    @override_settings(MAX_ESTABLISHED_PERSONAS_PER_SHEET=0)
    def test_staff_bypasses_cap(self):
        persona = create_persona(
            self.sheet, name="Staff Made", persona_type="established", bypass_cap=True
        )
        assert persona.pk is not None

    @override_settings(MAX_ESTABLISHED_PERSONAS_PER_SHEET=0)
    def test_temporary_masks_are_not_capped(self):
        # cap is 0 yet TEMPORARY masks still create — they're throwaway.
        mask = create_persona(self.sheet, name="A Masked Figure", persona_type="temporary")
        assert mask.persona_type == PersonaType.TEMPORARY


class DescriptorPrivacyInvariantTests(TestCase):
    """The whole privacy guarantee, as one assertion: a new persona's descriptors are empty."""

    @classmethod
    def setUpTestData(cls):
        cls.sheet = CharacterSheetFactory()
        cls.primary = cls.sheet.primary_persona
        cls.hair = FormTraitFactory(name="hair_color", display_name="Hair Color")

    def test_new_persona_has_no_descriptors_even_when_a_sibling_does(self):
        # The primary face carries a distinctive descriptor.
        PersonaTraitDescriptorFactory(persona=self.primary, trait=self.hair, text="Crimson")
        # Creating a new face must NOT copy it.
        new_face = create_persona(self.sheet, name="Robert", persona_type="established")
        assert not PersonaTraitDescriptor.objects.filter(persona=new_face).exists()


class CreateMaskTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.sheet = CharacterSheetFactory()
        cls.character = cls.sheet.character
        cls.hair = FormTraitFactory(name="hair_color", display_name="Hair Color")
        cls.red = FormTraitOptionFactory(trait=cls.hair, name="red", display_name="Red")

    def test_mask_is_temporary_and_fake_and_active(self):
        mask = create_mask(self.sheet, name="The Stag Mask")
        assert mask.persona_type == PersonaType.TEMPORARY
        assert mask.is_fake_name is True
        self.sheet.refresh_from_db()
        assert self.sheet.active_persona_id == mask.pk

    def test_mask_with_disguise_form_applies_overlay(self):
        # Real form so apply_disguise has a body to overlay.
        true_form = CharacterFormFactory(character=self.character, form_type=FormType.TRUE)
        CharacterFormValueFactory(form=true_form, trait=self.hair, option=self.red)
        CharacterFormState.objects.create(character=self.character, active_form=true_form)
        disguise = CharacterFormFactory(
            character=self.character, form_type=FormType.DISGUISE, is_player_created=True
        )

        create_mask(self.sheet, name="The Stag Mask", disguise_form=disguise)

        state = CharacterFormState.objects.get(character=self.character)
        assert state.active_fake_overlay_id == disguise.id


class SetPersonaProfileTests(TestCase):
    """Authoring a cover identity's own (fabricated) bio — the Guise Sheet (#1270)."""

    @classmethod
    def setUpTestData(cls):
        cls.sheet = CharacterSheetFactory()
        cls.cover = create_persona(cls.sheet, name="Robert D'Vile", persona_type="established")

    def test_attaches_a_profile_the_first_time(self):
        assert self.cover.profile is None
        profile = set_persona_profile(
            self.cover, concept="A jovial wine merchant", quote="In vino veritas."
        )
        self.cover.refresh_from_db()
        assert self.cover.profile_id == profile.pk
        assert profile.concept == "A jovial wine merchant"
        assert profile.quote == "In vino veritas."

    def test_partial_update_leaves_other_fields_untouched(self):
        set_persona_profile(self.cover, concept="Merchant", background="Born in the river-ward.")
        # A later edit of one field must not blank the others.
        set_persona_profile(self.cover, concept="Spice merchant")
        self.cover.refresh_from_db()
        assert self.cover.profile.concept == "Spice merchant"
        assert self.cover.profile.background == "Born in the river-ward."

    def test_reuses_the_same_profile_on_re_edit(self):
        first = set_persona_profile(self.cover, concept="One")
        second = set_persona_profile(self.cover, quote="Two")
        assert first.pk == second.pk  # one guise profile per persona, not a new row each edit

    def test_rejects_primary_persona(self):
        with self.assertRaises(GuiseProfileError):
            set_persona_profile(self.sheet.primary_persona, concept="not allowed")


class CreatePersonaEndpointTests(TestCase):
    """The designed web create endpoints (#1127) replacing the removed raw ModelViewSet create."""

    def setUp(self):
        self.sheet = CharacterSheetFactory()
        self.character = self.sheet.character
        self.factory = APIRequestFactory()

    def _post(self, action_name, url, body, *, puppet, is_staff=False):
        request = self.factory.post(url, body, format="json")
        user = SimpleNamespace(is_authenticated=True, is_staff=is_staff, puppet=puppet)
        force_authenticate(request, user=user)
        return PersonaViewSet.as_view({"post": action_name})(request)

    def test_create_established_endpoint(self):
        resp = self._post(
            "create_established",
            "/api/scenes/personas/create-established/",
            {"name": "Robert D'Vile"},
            puppet=self.character,
        )
        assert resp.status_code == 201
        assert Persona.objects.filter(
            character_sheet=self.sheet,
            name="Robert D'Vile",
            persona_type=PersonaType.ESTABLISHED,
        ).exists()

    def test_create_mask_endpoint(self):
        resp = self._post(
            "create_mask",
            "/api/scenes/personas/create-mask/",
            {"name": "A Masked Figure"},
            puppet=self.character,
        )
        assert resp.status_code == 201
        mask = Persona.objects.get(character_sheet=self.sheet, name="A Masked Figure")
        assert mask.persona_type == PersonaType.TEMPORARY
        assert mask.is_fake_name is True

    @override_settings(MAX_ESTABLISHED_PERSONAS_PER_SHEET=0)
    def test_cap_returns_400_for_non_staff(self):
        resp = self._post(
            "create_established",
            "/api/scenes/personas/create-established/",
            {"name": "Too Many"},
            puppet=self.character,
        )
        assert resp.status_code == 400

    @override_settings(MAX_ESTABLISHED_PERSONAS_PER_SHEET=0)
    def test_staff_bypasses_cap_over_the_endpoint(self):
        resp = self._post(
            "create_established",
            "/api/scenes/personas/create-established/",
            {"name": "Staff Identity"},
            puppet=self.character,
            is_staff=True,
        )
        assert resp.status_code == 201

    def test_no_played_character_400(self):
        resp = self._post(
            "create_established",
            "/api/scenes/personas/create-established/",
            {"name": "Nobody"},
            puppet=None,
        )
        assert resp.status_code == 400
