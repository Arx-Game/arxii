from decimal import Decimal

import factory

from evennia_extensions.factories import CharacterFactory
from world.forms.models import (
    AppearanceChangeLog,
    Build,
    CharacterForm,
    CharacterFormState,
    CharacterFormValue,
    DurationType,
    FormTrait,
    FormTraitOption,
    FormType,
    HeightBand,
    PersonaTraitDescriptor,
    SourceType,
    SpeciesFormTrait,
    TemporaryFormChange,
    TraitType,
)
from world.species.factories import SpeciesFactory


class HeightBandFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = HeightBand
        django_get_or_create = ("name",)

    name = factory.Sequence(lambda n: f"height_band_{n}")
    display_name = factory.LazyAttribute(lambda o: o.name.replace("_", " ").title())
    min_inches = 60
    max_inches = 72
    weight_min = None
    weight_max = None
    is_cg_selectable = True
    hide_build = False
    sort_order = factory.Sequence(lambda n: n)


class BuildFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Build
        django_get_or_create = ("name",)

    name = factory.Sequence(lambda n: f"build_{n}")
    display_name = factory.LazyAttribute(lambda o: o.name.replace("_", " ").title())
    weight_factor = Decimal("2.5")
    is_cg_selectable = True
    sort_order = factory.Sequence(lambda n: n)


class FormTraitFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = FormTrait
        django_get_or_create = ("name",)

    name = factory.Sequence(lambda n: f"trait_{n}")
    display_name = factory.LazyAttribute(lambda o: o.name.replace("_", " ").title())
    trait_type = TraitType.STYLE
    sort_order = factory.Sequence(lambda n: n)


class FormTraitOptionFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = FormTraitOption
        django_get_or_create = ("trait", "name")

    trait = factory.SubFactory(FormTraitFactory)
    name = factory.Sequence(lambda n: f"option_{n}")
    display_name = factory.LazyAttribute(lambda o: o.name.replace("_", " ").title())
    sort_order = factory.Sequence(lambda n: n)
    height_modifier_inches = None


class SpeciesFormTraitFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = SpeciesFormTrait
        django_get_or_create = ("species", "trait")

    species = factory.SubFactory(SpeciesFactory)
    trait = factory.SubFactory(FormTraitFactory)
    is_available_in_cg = True


class CharacterFormFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = CharacterForm

    character = factory.SubFactory(CharacterFactory)
    name = ""
    form_type = FormType.TRUE
    is_player_created = False


class CharacterFormValueFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = CharacterFormValue
        django_get_or_create = ("form", "trait")

    form = factory.SubFactory(CharacterFormFactory)
    trait = factory.SubFactory(FormTraitFactory)
    option = factory.SubFactory(FormTraitOptionFactory, trait=factory.SelfAttribute("..trait"))
    natural_option = factory.SelfAttribute("option")


class CharacterFormStateFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = CharacterFormState
        django_get_or_create = ("character",)

    character = factory.LazyAttribute(lambda o: o.active_form.character)
    active_form = factory.SubFactory(CharacterFormFactory)


class TemporaryFormChangeFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = TemporaryFormChange

    character = factory.SubFactory(CharacterFactory)
    trait = factory.SubFactory(FormTraitFactory)
    option = factory.SubFactory(FormTraitOptionFactory, trait=factory.SelfAttribute("..trait"))
    source_type = SourceType.SYSTEM
    source_id = None
    duration_type = DurationType.UNTIL_REMOVED
    expires_at = None
    expires_after_scenes = None


class PersonaTraitDescriptorFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = PersonaTraitDescriptor
        django_get_or_create = ("persona", "trait")

    persona = factory.SubFactory("world.scenes.factories.PersonaFactory")
    trait = factory.SubFactory(FormTraitFactory)
    text = "Crimson"


class AppearanceChangeLogFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = AppearanceChangeLog

    form = factory.SubFactory(CharacterFormFactory)
    persona = factory.SubFactory("world.scenes.factories.PersonaFactory")
    trait = factory.SubFactory(FormTraitFactory)
    from_option = factory.SubFactory(FormTraitOptionFactory, trait=factory.SelfAttribute("..trait"))
    to_option = factory.SubFactory(FormTraitOptionFactory, trait=factory.SelfAttribute("..trait"))
    from_text = ""
    to_text = "Crimson"
    actor_persona = factory.SelfAttribute("persona")
    note = ""
