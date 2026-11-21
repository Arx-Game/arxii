"""A colour option's swatch value (#5241): the field's rule, the first-pass table, the API."""

import re

from django.core.exceptions import ValidationError
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory
from world.forms.factories import FormTraitFactory, FormTraitOptionFactory
from world.forms.models import SpeciesFormTrait, TraitType
from world.forms.serializers import FormTraitOptionSerializer
from world.forms.swatches import DEFAULT_SWATCHES, default_swatch
from world.species.models import Species

HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


class SwatchFieldTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.trait = FormTraitFactory(
            name="hair_color", display_name="Hair Color", trait_type=TraitType.COLOR
        )

    def test_a_colour_is_six_hex_digits_after_a_hash(self):
        option = FormTraitOptionFactory(trait=self.trait, name="auburn", color_hex="#7a3220")
        option.full_clean()

    def test_blank_is_allowed_for_an_option_with_no_single_colour(self):
        option = FormTraitOptionFactory(trait=self.trait, name="prismatic")
        assert option.color_hex == ""
        option.full_clean()

    def test_anything_else_is_refused(self):
        for bad in ("red", "#abc", "7a3220", "#7a322g", "#7a3220;"):
            option = FormTraitOptionFactory.build(trait=self.trait, name="bad", color_hex=bad)
            with self.assertRaises(ValidationError, msg=bad):
                option.full_clean()

    def test_the_option_serializer_carries_it(self):
        option = FormTraitOptionFactory(trait=self.trait, name="auburn", color_hex="#7a3220")
        assert FormTraitOptionSerializer(option).data["color_hex"] == "#7a3220"


class DefaultSwatchTests(TestCase):
    def test_every_value_in_the_table_is_a_colour_the_field_accepts(self):
        for trait_name, colours in DEFAULT_SWATCHES.items():
            for option_name, colour in colours.items():
                assert HEX.match(colour), f"{trait_name}.{option_name}: {colour!r}"

    def test_an_option_the_table_does_not_name_is_blank(self):
        assert default_swatch("hair_color", "auburn") == DEFAULT_SWATCHES["hair_color"]["auburn"]
        # No single colour, so it is left out on purpose and drawn striped.
        assert default_swatch("hair_color", "prismatic") == ""
        assert default_swatch("horn_type", "spiral") == ""


class FormOptionsSwatchTests(TestCase):
    """The Appearance stage reads the colour off the form-options answer."""

    @classmethod
    def setUpTestData(cls):
        cls.account = AccountFactory()
        cls.species = Species.objects.create(name="Swatch Test Species")
        trait = FormTraitFactory(
            name="hair_color", display_name="Hair Color", trait_type=TraitType.COLOR
        )
        cls.auburn = FormTraitOptionFactory(trait=trait, name="auburn", color_hex="#7a3220")
        cls.prismatic = FormTraitOptionFactory(trait=trait, name="prismatic")
        link = SpeciesFormTrait.objects.create(
            species=cls.species, trait=trait, is_available_in_cg=True
        )
        link.allowed_options.set([cls.auburn, cls.prismatic])

    def test_each_option_carries_its_colour_or_a_blank(self):
        client = APIClient()
        client.force_authenticate(user=self.account)
        resp = client.get(f"/api/character-creation/form-options/{self.species.id}/")
        assert resp.status_code == status.HTTP_200_OK
        (row,) = resp.data["traits"]
        assert row["trait"]["trait_type"] == "color"
        by_name = {o["name"]: o["color_hex"] for o in row["options"]}
        assert by_name == {"auburn": "#7a3220", "prismatic": ""}
        assert {o["name"]: o["color_hex"] for o in row["all_options"]} == by_name
