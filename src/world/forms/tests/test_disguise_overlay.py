"""Disguise/illusion overlay substrate (#1110).

A fake overlay is painted over the real form: viewers who haven't pierced it see the overlay's
traits; the owner/staff ground-truth read (``pierced=True``) always sees the real form beneath.
The pierce *contest* itself (perception vs disguise / dispel) is the senior dev's domain — these
tests pin the substrate the contest writes into.
"""

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.forms.factories import (
    CharacterFormFactory,
    CharacterFormValueFactory,
    FormTraitFactory,
    FormTraitOptionFactory,
)
from world.forms.models import CharacterFormState, DisguiseKind, FormType
from world.forms.services import (
    NotADisguiseError,
    apply_disguise,
    get_presented_appearance,
    remove_disguise,
)


class DisguiseOverlayTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.character = CharacterFactory()
        cls.sheet = CharacterSheetFactory(character=cls.character)
        cls.hair = FormTraitFactory(name="hair_color", display_name="Hair Color")
        cls.red = FormTraitOptionFactory(trait=cls.hair, name="red", display_name="Red")
        cls.blonde = FormTraitOptionFactory(trait=cls.hair, name="blonde", display_name="Blonde")

    def setUp(self):
        # Real (true) form: red hair, and it is the active real form.
        self.true_form = CharacterFormFactory(character=self.character, form_type=FormType.TRUE)
        CharacterFormValueFactory(form=self.true_form, trait=self.hair, option=self.red)
        CharacterFormState.objects.create(character=self.character, active_form=self.true_form)
        # A disguise form: blonde hair.
        self.disguise = CharacterFormFactory(
            character=self.character, form_type=FormType.DISGUISE, is_player_created=True
        )
        CharacterFormValueFactory(form=self.disguise, trait=self.hair, option=self.blonde)

    def _hair(self, *, pierced: bool = False) -> str:
        presented = {
            p.trait_name: p for p in get_presented_appearance(self.character, pierced=pierced)
        }
        return presented["hair_color"].display

    def test_no_overlay_presents_real_form(self):
        assert self._hair() == "Red"

    def test_overlay_presents_disguise_traits(self):
        apply_disguise(self.character, self.disguise, kind=DisguiseKind.MUNDANE)
        assert self._hair() == "Blonde"

    def test_pierced_read_ignores_overlay_and_shows_real_form(self):
        apply_disguise(self.character, self.disguise, kind=DisguiseKind.MAGICAL)
        # Owner/staff ground-truth read sees through the overlay.
        assert self._hair(pierced=True) == "Red"
        # Unpierced viewer still sees the disguise.
        assert self._hair(pierced=False) == "Blonde"

    def test_apply_records_kind(self):
        apply_disguise(self.character, self.disguise, kind=DisguiseKind.MAGICAL)
        state = CharacterFormState.objects.get(character=self.character)
        assert state.active_fake_overlay_id == self.disguise.id
        assert state.overlay_kind == DisguiseKind.MAGICAL

    def test_remove_disguise_restores_real_form(self):
        apply_disguise(self.character, self.disguise)
        remove_disguise(self.character)
        state = CharacterFormState.objects.get(character=self.character)
        assert state.active_fake_overlay_id is None
        assert state.overlay_kind == ""
        assert self._hair() == "Red"

    def test_remove_disguise_is_idempotent(self):
        remove_disguise(self.character)  # no overlay set — must not raise
        assert self._hair() == "Red"

    def test_apply_rejects_foreign_form(self):
        other = CharacterFactory()
        foreign = CharacterFormFactory(character=other, form_type=FormType.DISGUISE)
        with self.assertRaises(ValueError):
            apply_disguise(self.character, foreign)

    def test_apply_rejects_non_disguise_form(self):
        with self.assertRaises(NotADisguiseError):
            apply_disguise(self.character, self.true_form)

    def test_current_real_form_property_is_the_active_form(self):
        state = CharacterFormState.objects.get(character=self.character)
        assert state.current_real_form == self.true_form
