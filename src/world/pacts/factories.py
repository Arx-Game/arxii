"""FactoryBoy factories for being pacts (#4341). Text fields are labelled placeholders:
offer prose is staff-authored."""

from __future__ import annotations

import factory

from world.checks.factories import CheckTypeFactory
from world.conditions.constants import DurationType
from world.conditions.factories import ConditionStageFactory, ConditionTemplateFactory
from world.conditions.models import ConditionTemplate
from world.conditions.types import AdvancementResistFailureKind
from world.pacts.constants import CharacterPactCommitmentKind
from world.pacts.models import (
    CharacterPact,
    PactCredit,
    PactOffer,
    PactOfferCommitment,
    PactPeriodDetails,
)
from world.projects.constants import CompletionMode, ProjectKind
from world.projects.factories import ProjectFactory
from world.worship.constants import PledgeCreditSource
from world.worship.factories import DevotionStandingFactory, WorshippedBeingFactory

#: (name, severity threshold) of a pact condition's stages, best to worst.
PACT_STAGES = (("Sworn", 1), ("Strained", 11), ("Soured", 21), ("Breached", 31))


def make_pact_condition(
    *, name: str | None = None, resist_difficulty: int = 10
) -> ConditionTemplate:
    """A staged pact condition: permanent, no passive decay, four severity stages.

    Every stage advances at its threshold (the pact handler rolls the resist itself);
    stages 2 to 4 carry a resist check at ``resist_difficulty``.
    """
    kwargs = {"name": name} if name else {}
    condition = ConditionTemplateFactory(
        has_progression=True,
        default_duration_type=DurationType.PERMANENT,
        default_duration_value=0,
        passive_decay_per_day=0,
        **kwargs,
    )
    check_type = CheckTypeFactory()
    for order, (stage_name, threshold) in enumerate(PACT_STAGES, start=1):
        ConditionStageFactory(
            condition=condition,
            stage_order=order,
            name=stage_name,
            rounds_to_next=None,
            severity_threshold=threshold,
            advancement_resist_failure_kind=AdvancementResistFailureKind.ADVANCE_AT_THRESHOLD,
            resist_check_type=check_type if order > 1 else None,
            resist_difficulty=resist_difficulty,
        )
    return condition


class PactOfferFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = PactOffer

    being = factory.SubFactory(WorshippedBeingFactory)
    name = factory.Sequence(lambda n: f"Pact Offer {n}")
    offer_text = "[staff-authored offer text]"
    closing_text = "[staff-authored closing text]"
    onlooker_line = ""
    period_weeks = 2
    condition = factory.LazyFunction(make_pact_condition)
    severity_per_miss = 10
    is_active = True


class PactOfferCommitmentFactory(factory.django.DjangoModelFactory):
    """A FAVOR_EARNED commitment by default; pass ``kind=CUSTOM, notes=...`` for a promise."""

    class Meta:
        model = PactOfferCommitment

    offer = factory.SubFactory(PactOfferFactory)
    kind = CharacterPactCommitmentKind.FAVOR_EARNED
    owed_by_holder = True
    amount = 10
    notes = ""


class CharacterPactFactory(factory.django.DjangoModelFactory):
    """An active pact. The standing defaults to the holder's, with the offer's being."""

    class Meta:
        model = CharacterPact

    character_sheet = factory.SubFactory("world.character_sheets.factories.CharacterSheetFactory")
    offer = factory.SubFactory(PactOfferFactory)
    devotion_standing = factory.LazyAttribute(
        lambda o: DevotionStandingFactory(character_sheet=o.character_sheet, being=o.offer.being)
    )
    condition_instance = None


class PactPeriodDetailsFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = PactPeriodDetails

    project = factory.SubFactory(
        ProjectFactory,
        kind=ProjectKind.PACT_PERIOD,
        completion_mode=CompletionMode.TIERED_PERIOD,
    )
    pact = factory.SubFactory(CharacterPactFactory)
    commitment = factory.LazyAttribute(lambda o: PactOfferCommitmentFactory(offer=o.pact.offer))


class PactCreditFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = PactCredit

    period = factory.SubFactory(PactPeriodDetailsFactory)
    source = PledgeCreditSource.DEED
    credited = 2
    game_week = None
