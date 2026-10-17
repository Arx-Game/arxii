"""FactoryBoy factories for standoffs. Strings are placeholders, never player prose."""

import factory
from factory import django as factory_django

from world.checks.factories import CheckTypeFactory
from world.combat.constants import CauseKind
from world.combat.factories import CombatEncounterFactory, CreatureTemplateFactory
from world.conditions.factories import CapabilityTypeFactory
from world.mechanics.factories import PropertyFactory
from world.standoffs.constants import DriveStrength, RevealKind, TermsEffect
from world.standoffs.models import (
    CreatureDrive,
    FactionRule,
    StandoffApproach,
    StandoffCauseGloss,
    StandoffGroup,
    StandoffReactionLine,
    StandoffReveal,
    StandoffTerms,
)


class CreatureDriveFactory(factory_django.DjangoModelFactory):
    class Meta:
        model = CreatureDrive

    creature_template = factory.SubFactory(CreatureTemplateFactory)
    property = factory.SubFactory(PropertyFactory)
    strength = DriveStrength.MINOR


class FactionRuleFactory(factory_django.DjangoModelFactory):
    class Meta:
        model = FactionRule

    creature_template = factory.SubFactory(CreatureTemplateFactory)
    angle_text = "PLACEHOLDER angle"
    revealed_text = "PLACEHOLDER revealed"


class StandoffApproachFactory(factory_django.DjangoModelFactory):
    class Meta:
        model = StandoffApproach
        django_get_or_create = ("name",)

    name = factory.Sequence(lambda n: f"Approach {n}")
    check_type = factory.SubFactory(CheckTypeFactory)
    capability = factory.SubFactory(CapabilityTypeFactory)


class StandoffTermsFactory(factory_django.DjangoModelFactory):
    class Meta:
        model = StandoffTerms
        django_get_or_create = ("name",)

    name = factory.Sequence(lambda n: f"Terms {n}")
    effect = TermsEffect.PASS


class StandoffCauseGlossFactory(factory_django.DjangoModelFactory):
    class Meta:
        model = StandoffCauseGloss
        django_get_or_create = ("cause",)

    cause = CauseKind.PREDATION
    text = "PLACEHOLDER cause gloss"


class StandoffGroupFactory(factory_django.DjangoModelFactory):
    class Meta:
        model = StandoffGroup

    encounter = factory.SubFactory(CombatEncounterFactory)
    creature_template = factory.SubFactory(CreatureTemplateFactory)


class StandoffRevealFactory(factory_django.DjangoModelFactory):
    """A CAUSE reveal by default; pass ``kind`` with the matching FK for the others."""

    class Meta:
        model = StandoffReveal

    group = factory.SubFactory(StandoffGroupFactory)
    kind = RevealKind.CAUSE


class StandoffReactionLineFactory(factory_django.DjangoModelFactory):
    """A line on an approach by default; pass ``approach=None, terms=...`` for terms."""

    class Meta:
        model = StandoffReactionLine

    approach = factory.SubFactory(StandoffApproachFactory)
    min_success_level = 1
    text = "PLACEHOLDER <actor> and <group>"


def restamp_from_templates(encounter: object) -> None:
    """Re-stamp every templated opponent in ``encounter`` from its template as it is now.

    A spawn stamps the template's standoff profile on the opponent (#4361); a test that
    edits the template (cause, drives, affiliation) after its opponents exist calls this,
    the way a real encounter would have been spawned from the edited template.
    """
    from world.mechanics.models import ObjectProperty
    from world.standoffs.services.placement import (
        placement_profile,
        stamp_opponent,
    )

    for opponent in encounter.opponents.exclude(creature_template=None):
        # A named NPC's object is its own character: nothing standoff-specific lives there.
        if opponent.objectdb_id is not None and opponent.persona_id is None:
            ObjectProperty.objects.filter(
                object_id=opponent.objectdb_id,
                source_condition__isnull=True,
                source_challenge__isnull=True,
            ).delete()
        stamp_opponent(opponent, placement_profile(opponent.creature_template))
