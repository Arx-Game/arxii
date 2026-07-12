"""DisguiseKitEffect model and use-item dispatch (#2249)."""

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.forms.factories import (
    CharacterFormFactory,
    CharacterFormStateFactory,
    CharacterFormValueFactory,
    FormTraitFactory,
    FormTraitOptionFactory,
)
from world.forms.models import CharacterFormState, ConcealmentLevel, DisguiseKind, FormType
from world.forms.services import apply_disguise, remove_disguise
from world.items.factories import ItemInstanceFactory, ItemTemplateFactory
from world.items.models import DisguiseKitEffect, ItemTemplate, QualityTier
from world.items.services.usage import use_item


class DisguiseKitEffectModelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.template = ItemTemplate.objects.create(name="Basic Disguise Kit")

    def test_can_create_effect_with_kind_and_level(self):
        effect = DisguiseKitEffect.objects.create(
            item_template=self.template,
            disguise_kind=DisguiseKind.MUNDANE,
            concealment_level=ConcealmentLevel.DESCRIPTOR,
        )
        self.assertEqual(effect.disguise_kind, DisguiseKind.MUNDANE)
        self.assertEqual(effect.concealment_level, ConcealmentLevel.DESCRIPTOR)

    def test_defaults_to_mundane_none(self):
        effect = DisguiseKitEffect.objects.create(item_template=self.template)
        self.assertEqual(effect.disguise_kind, DisguiseKind.MUNDANE)
        self.assertEqual(effect.concealment_level, ConcealmentLevel.NONE)

    def test_related_name_on_template(self):
        DisguiseKitEffect.objects.create(item_template=self.template)
        self.assertEqual(self.template.disguise_kit_effects.count(), 1)

    def test_str_includes_template_name(self):
        effect = DisguiseKitEffect.objects.create(item_template=self.template)
        self.assertIn("Basic Disguise Kit", str(effect))


class UseItemDisguiseKitDispatchTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.hair = FormTraitFactory(name="hair_color_dk", display_name="Hair Color")
        cls.red = FormTraitOptionFactory(trait=cls.hair, name="red_dk", display_name="Red")
        cls.blonde = FormTraitOptionFactory(trait=cls.hair, name="blonde_dk", display_name="Blonde")

        cls.character = CharacterFactory()
        cls.sheet = CharacterSheetFactory(character=cls.character)
        cls.true_form = CharacterFormFactory(character=cls.character, form_type=FormType.TRUE)
        CharacterFormValueFactory(form=cls.true_form, trait=cls.hair, option=cls.red)
        CharacterFormStateFactory(character=cls.character, active_form=cls.true_form)

        cls.disguise = CharacterFormFactory(
            character=cls.character, form_type=FormType.DISGUISE, is_player_created=True
        )
        CharacterFormValueFactory(form=cls.disguise, trait=cls.hair, option=cls.blonde)

        cls.tier = QualityTier.objects.create(
            name="Fine DK",
            color_hex="#00FF00",
            numeric_min=40,
            numeric_max=59,
            stat_multiplier=1.5,
            sort_order=2,
        )
        cls.template = ItemTemplateFactory(
            name="Disguise Kit Item",
            is_consumable=True,
            max_charges=1,
        )
        cls.template.disguise_kit_effects.create(
            disguise_kind=DisguiseKind.MUNDANE,
            concealment_level=ConcealmentLevel.DESCRIPTOR,
        )
        cls.kit_instance = ItemInstanceFactory(
            template=cls.template,
            charges=1,
            quality_tier=cls.tier,
            holder_character_sheet=cls.sheet,
        )

    def test_use_item_applies_disguise_overlay(self):
        use_item(item_instance=self.kit_instance, user=self.character)
        state = CharacterFormState.objects.get(character=self.character)
        assert state.active_fake_overlay_id is not None
        assert state.overlay_kind == DisguiseKind.MUNDANE
        assert state.applied_kit_instance_id == self.kit_instance.id

    def test_remove_disguise_clears_kit_instance(self):
        # Create a fresh character+state to avoid setUpTestData's cached
        # reverse-accessor returning a stale CharacterFormState to remove_disguise.
        from evennia_extensions.factories import CharacterFactory
        from world.character_sheets.factories import CharacterSheetFactory
        from world.forms.factories import (
            CharacterFormFactory,
            CharacterFormStateFactory,
            CharacterFormValueFactory,
        )

        character = CharacterFactory()
        CharacterSheetFactory(character=character)
        true_form = CharacterFormFactory(character=character, form_type=FormType.TRUE)
        CharacterFormValueFactory(form=true_form, trait=self.hair, option=self.red)
        CharacterFormStateFactory(character=character, active_form=true_form)
        disguise = CharacterFormFactory(
            character=character, form_type=FormType.DISGUISE, is_player_created=True
        )
        CharacterFormValueFactory(form=disguise, trait=self.hair, option=self.blonde)
        apply_disguise(
            character,
            disguise,
            kind=DisguiseKind.MUNDANE,
            kit_instance=self.kit_instance,
        )
        state = CharacterFormState.objects.get(character=character)
        assert state.applied_kit_instance_id == self.kit_instance.id
        remove_disguise(character)
        state.refresh_from_db()
        assert state.applied_kit_instance_id is None
