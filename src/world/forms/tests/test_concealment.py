"""Per-disguise concealment levels (#1272).

A disguise overlay's ``concealment_level`` controls what an unpierced viewer sees:
- NONE: full trait + descriptor (the existing overlay behavior).
- DESCRIPTOR: normalized value visible, player-authored descriptor hidden.
- FULL: traits hidden entirely — nothing shows.
"""

from django.test import TestCase
from rest_framework.test import APITestCase

from evennia_extensions.factories import AccountFactory, CharacterFactory
from evennia_extensions.models import PlayerData
from world.character_sheets.factories import CharacterSheetFactory
from world.forms.factories import (
    CharacterFormFactory,
    CharacterFormValueFactory,
    FormTraitFactory,
    FormTraitOptionFactory,
    PersonaTraitDescriptorFactory,
)
from world.forms.models import CharacterFormState, ConcealmentLevel, FormType
from world.forms.services import apply_disguise, get_presented_appearance
from world.roster.factories import RosterEntryFactory, RosterTenureFactory


class ConcealmentTelnetTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.character = CharacterFactory()
        cls.sheet = CharacterSheetFactory(character=cls.character)
        cls.hair = FormTraitFactory(name="hair_color", display_name="Hair Color")
        cls.red = FormTraitOptionFactory(trait=cls.hair, name="red", display_name="Red")
        cls.blonde = FormTraitOptionFactory(trait=cls.hair, name="blonde", display_name="Blonde")

    def setUp(self):
        self.true_form = CharacterFormFactory(character=self.character, form_type=FormType.TRUE)
        CharacterFormValueFactory(form=self.true_form, trait=self.hair, option=self.red)
        CharacterFormState.objects.create(character=self.character, active_form=self.true_form)
        self.disguise = CharacterFormFactory(
            character=self.character, form_type=FormType.DISGUISE, is_player_created=True
        )
        CharacterFormValueFactory(form=self.disguise, trait=self.hair, option=self.blonde)
        self.persona = self.sheet.primary_persona
        PersonaTraitDescriptorFactory(persona=self.persona, trait=self.hair, text="Flowing Crimson")

    def _hair(self, *, pierced=False):
        presented = {
            p.trait_name: p for p in get_presented_appearance(self.character, pierced=pierced)
        }
        return presented.get("hair_color")

    def test_none_concealment_shows_descriptor(self):
        apply_disguise(self.character, self.disguise, concealment_level=ConcealmentLevel.NONE)
        trait = self._hair()
        assert trait.display == "Flowing Crimson"
        assert trait.descriptor == "Flowing Crimson"
        assert trait.normalized == "Blonde"

    def test_descriptor_concealment_hides_descriptor_shows_value(self):
        apply_disguise(self.character, self.disguise, concealment_level=ConcealmentLevel.DESCRIPTOR)
        trait = self._hair()
        assert trait.display == "Blonde"
        assert trait.descriptor == ""
        assert trait.normalized == "Blonde"

    def test_full_concealment_hides_traits(self):
        apply_disguise(self.character, self.disguise, concealment_level=ConcealmentLevel.FULL)
        assert self._hair() is None

    def test_pierced_read_ignores_concealment(self):
        apply_disguise(self.character, self.disguise, concealment_level=ConcealmentLevel.FULL)
        trait = self._hair(pierced=True)
        assert trait.display == "Flowing Crimson"

    def test_no_overlay_shows_real_form(self):
        trait = self._hair()
        assert trait.display == "Flowing Crimson"
        assert trait.normalized == "Red"


class ConcealmentWebTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = AccountFactory()
        cls.roster_entry = RosterEntryFactory()
        cls.player_data, _ = PlayerData.objects.get_or_create(account=cls.owner)
        RosterTenureFactory(player_data=cls.player_data, roster_entry=cls.roster_entry)
        cls.sheet = cls.roster_entry.character_sheet
        cls.character = cls.sheet.character
        cls.hair = FormTraitFactory(name="hair_color", display_name="Hair Color")
        cls.red = FormTraitOptionFactory(trait=cls.hair, name="red", display_name="Red")
        cls.blonde = FormTraitOptionFactory(trait=cls.hair, name="blonde", display_name="Blonde")

    def setUp(self):
        self.true_form = CharacterFormFactory(character=self.character, form_type=FormType.TRUE)
        CharacterFormValueFactory(form=self.true_form, trait=self.hair, option=self.red)
        CharacterFormState.objects.create(character=self.character, active_form=self.true_form)
        self.disguise = CharacterFormFactory(
            character=self.character, form_type=FormType.DISGUISE, is_player_created=True
        )
        CharacterFormValueFactory(form=self.disguise, trait=self.hair, option=self.blonde)

    def _appearance(self, viewer):
        self.client.force_authenticate(user=viewer)
        resp = self.client.get(f"/api/character-sheets/{self.sheet.pk}/")
        return resp.data["appearance"]

    def _stranger(self):
        stranger = AccountFactory()
        pd, _ = PlayerData.objects.get_or_create(account=stranger)
        RosterTenureFactory(player_data=pd, roster_entry=RosterEntryFactory())
        return stranger

    def test_web_descriptor_concealment_hides_descriptor(self):
        apply_disguise(self.character, self.disguise, concealment_level=ConcealmentLevel.DESCRIPTOR)
        appearance = self._appearance(self._stranger())
        traits = {t["trait"]: t for t in appearance["form_traits"]}
        assert traits["Hair Color"]["value"] == "Blonde"

    def test_web_full_concealment_hides_traits(self):
        apply_disguise(self.character, self.disguise, concealment_level=ConcealmentLevel.FULL)
        appearance = self._appearance(self._stranger())
        assert appearance["form_traits"] == []

    def test_web_owner_sees_through_concealment(self):
        apply_disguise(self.character, self.disguise, concealment_level=ConcealmentLevel.FULL)
        appearance = self._appearance(self.owner)
        traits = {t["trait"]: t for t in appearance["form_traits"]}
        assert traits["Hair Color"]["value"] == "Red"
