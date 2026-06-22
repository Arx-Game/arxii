import factory
import factory.django as factory_django

from world.character_sheets.factories import CharacterSheetFactory
from world.roster.factories import RosterEntryFactory
from world.secrets.constants import SecretLevel, SecretProvenance
from world.secrets.models import Secret, SecretCategory, SecretKnowledge, SecretVictim


class SecretCategoryFactory(factory_django.DjangoModelFactory):
    class Meta:
        model = SecretCategory
        django_get_or_create = ("name",)

    name = factory.Sequence(lambda n: f"Category {n}")
    description = ""
    is_active = True


class SecretFactory(factory_django.DjangoModelFactory):
    class Meta:
        model = Secret

    subject_sheet = factory.SubFactory(CharacterSheetFactory)
    # Default GM-authored so a factory secret may sit at any level without tripping the
    # player-flavor anchor rule; override provenance/author_persona for player cases.
    provenance = SecretProvenance.GM_AUTHORED
    level = SecretLevel.UNCOMMON_KNOWLEDGE
    content = factory.Faker("sentence")


class SecretKnowledgeFactory(factory_django.DjangoModelFactory):
    class Meta:
        model = SecretKnowledge
        django_get_or_create = ("roster_entry", "secret")

    roster_entry = factory.SubFactory(RosterEntryFactory)
    secret = factory.SubFactory(SecretFactory)


class SecretVictimFactory(factory_django.DjangoModelFactory):
    """Victim of a secret's fact. Pass ``organization=`` or ``persona=`` (exactly one)."""

    class Meta:
        model = SecretVictim

    secret = factory.SubFactory(SecretFactory)
    organization = factory.SubFactory("world.societies.factories.OrganizationFactory")
    persona = None
