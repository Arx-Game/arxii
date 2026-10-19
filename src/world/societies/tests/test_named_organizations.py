"""Deeds name the organizations they helped or harmed, and rivals and allies react (#4473)."""

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from evennia_extensions.factories import RoomProfileFactory
from world.areas.constants import AreaLevel
from world.areas.factories import AreaFactory
from world.character_creation.factories import RealmFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.constants import EffectType
from world.checks.factories import ConsequenceEffectFactory, ConsequenceFactory
from world.checks.types import ResolutionContext
from world.mechanics.effect_handlers import apply_effect
from world.missions.constants import OptionKind, OptionSource, RewardGroupRule
from world.missions.factories import (
    MissionDeedRecordFactory,
    MissionInstanceFactory,
    MissionNodeFactory,
    MissionOptionFactory,
    MissionOptionRouteFactory,
    MissionParticipantFactory,
    MissionTemplateFactory,
)
from world.missions.models import MissionRenownAward
from world.missions.services.renown_emission import emit_terminal_renown_awards
from world.scenes.factories import SceneFactory
from world.secrets.models import Secret
from world.secrets.services import expose_secret
from world.societies.constants import (
    MAGNITUDE_NAMED_ORGANIZATION_AWARDS,
    NamedActReach,
    NamedOrganizationRole,
    OrganizationRelationKind,
    OrganizationReputationCause,
    RenownMagnitude,
)
from world.societies.factories import (
    LegendEntryFactory,
    LegendSourceTypeFactory,
    NamedOrganizationFactory,
    OrganizationFactory,
    OrganizationRelationFactory,
    OrganizationReputationFactory,
    OrganizationReputationReasonLineFactory,
    PhilosophicalArchetypeFactory,
    SocietyFactory,
)
from world.societies.models import (
    DeedOrganization,
    OrganizationReputation,
    OrganizationReputationEvent,
    RenownMagnitudeAward,
)
from world.societies.named_organizations import (
    NamedReaction,
    react_to_named_organizations,
    reaction_total,
)
from world.societies.renown import bump_organization_reputation
from world.societies.reputation_reasons import reason_lines_by_reputation
from world.societies.services import create_legend_event
from world.traits.factories import CheckOutcomeFactory

CAUSE = OrganizationReputationCause
HARMED = NamedOrganizationRole.HARMED
HELPED = NamedOrganizationRole.HELPED


def _value(persona, organization) -> int:
    row = OrganizationReputation.objects.filter(persona=persona, organization=organization).first()
    return row.value if row is not None else 0


class ReactionMathTests(TestCase):
    """The base, the principle adjustment and the rule that a reaction never crosses zero."""

    def setUp(self) -> None:
        self.cunning = PhilosophicalArchetypeFactory(name="Sly Work", method_delta=-3)

    def test_a_helped_organization_that_prizes_the_methods_is_more_pleased(self) -> None:
        org = OrganizationFactory(method_override=-4)
        total = reaction_total(NamedReaction(org, HELPED, False, 120), [self.cunning])
        assert total == 156  # base 120 + (-3 x -4 = 12, x 3 = 36)

    def test_a_harmed_organization_that_dislikes_the_methods_is_more_hurt(self) -> None:
        org = OrganizationFactory(society=SocietyFactory(method=4))
        total = reaction_total(NamedReaction(org, HARMED, False, 120), [self.cunning])
        assert total == -156  # -120 + (-3 x 4 = -12, x 3 = -36)

    def test_the_adjustment_is_capped_at_half_the_base(self) -> None:
        org = OrganizationFactory(method_override=-5)
        extreme = PhilosophicalArchetypeFactory(name="Extreme Sly", method_delta=-5)
        assert reaction_total(NamedReaction(org, HELPED, False, 120), [extreme]) == 180
        org_hates = OrganizationFactory(method_override=5)
        assert reaction_total(NamedReaction(org_hates, HARMED, False, 120), [extreme]) == -180

    def test_approval_never_flips_a_harmed_organization_across_zero(self) -> None:
        org = OrganizationFactory(method_override=5)
        approving = PhilosophicalArchetypeFactory(name="Approved Sly", method_delta=5)
        total = reaction_total(NamedReaction(org, HARMED, False, 100), [approving])
        assert total == -50  # the cap holds the adjustment at +50, so it stays a harm

    def test_a_standalone_organization_with_no_override_holds_no_stance(self) -> None:
        standalone = OrganizationFactory(society=None)
        assert standalone.get_effective_principle("method") == 0
        assert reaction_total(NamedReaction(standalone, HELPED, False, 80), [self.cunning]) == 80


class MissionAwardNamesOrganizationsTests(TestCase):
    """A mission award's named organizations react through the one writer."""

    def setUp(self) -> None:
        template = MissionTemplateFactory(name="Night at the Mill", risk_tier=1)
        template.reward_group_rule = RewardGroupRule.ALL_EQUAL
        node = MissionNodeFactory(template=template, key="entry", is_entry=True)
        option = MissionOptionFactory(
            node=node, order=0, option_kind=OptionKind.BRANCH, source_kind=OptionSource.AUTHORED
        )
        self.route = MissionOptionRouteFactory(option=option, outcome_tier=None, target_node=None)
        self.instance = MissionInstanceFactory(template=template)
        self.sheet = CharacterSheetFactory()
        MissionParticipantFactory(
            instance=self.instance, character=self.sheet, is_contract_holder=True
        )
        self.deed = MissionDeedRecordFactory(
            instance=self.instance, actor=self.sheet, node=node, option=option
        )
        self.persona = self.sheet.primary_persona
        self.patron = OrganizationFactory(name="Order of the Lantern")
        self.rival = OrganizationFactory(name="Millwrights")
        self.award = MissionRenownAward.objects.create(
            route=self.route, magnitude=RenownMagnitude.MODERATE, contract_holder_only=True
        )

    def _fire(self) -> None:
        emit_terminal_renown_awards(self.instance, self.route, self.deed)

    def test_a_helped_organization_rises_at_once_and_the_change_cites_the_deed(self) -> None:
        NamedOrganizationFactory(mission_award=self.award, organization=self.patron, role=HELPED)
        self._fire()
        assert _value(self.persona, self.patron) == MAGNITUDE_NAMED_ORGANIZATION_AWARDS["moderate"]
        (event,) = OrganizationReputationEvent.objects.filter(reputation__organization=self.patron)
        assert event.cause == CAUSE.DEED_NAMED
        assert event.mission_deed == self.deed
        assert DeedOrganization.objects.get(mission_deed=self.deed).role == HELPED

    def test_the_staff_tuned_magnitude_amount_sizes_the_base(self) -> None:
        RenownMagnitudeAward.objects.create(
            magnitude=RenownMagnitude.MODERATE,
            fame_award=1,
            prestige_award=1,
            named_organization_award=300,
        )
        NamedOrganizationFactory(mission_award=self.award, organization=self.rival, role=HARMED)
        self._fire()
        assert _value(self.persona, self.rival) == -300

    def test_a_covert_harm_waits_for_exposure(self) -> None:
        NamedOrganizationFactory(
            mission_award=self.award, organization=self.rival, role=HARMED, only_if_exposed=True
        )
        self._fire()
        assert _value(self.persona, self.rival) == 0
        secret = Secret.objects.get(subject_sheet=self.sheet)
        assert secret.mission_deed == self.deed
        (victim,) = secret.victims.all()
        assert victim.organization == self.rival
        assert victim.severity == 120

        expose_secret(secret, societies=[SocietyFactory()])
        assert _value(self.persona, self.rival) == -120
        (event,) = OrganizationReputationEvent.objects.filter(reputation__organization=self.rival)
        assert event.cause == CAUSE.SECRET_EXPOSED

    def test_an_award_naming_no_organization_changes_nothing(self) -> None:
        self._fire()
        assert not OrganizationReputation.objects.exists()
        assert not DeedOrganization.objects.exists()

    def test_the_reaction_does_not_depend_on_the_organizations_current_opinion(self) -> None:
        OrganizationReputationFactory(persona=self.persona, organization=self.rival, value=-600)
        NamedOrganizationFactory(mission_award=self.award, organization=self.rival, role=HARMED)
        self._fire()
        assert _value(self.persona, self.rival) == -720


class StoryConsequenceNamesOrganizationsTests(TestCase):
    """A LEGEND_AWARD consequence's base is scaled by the roll."""

    def setUp(self) -> None:
        self.persona = CharacterSheetFactory().primary_persona
        self.source = LegendSourceTypeFactory()
        self.ruled_against = OrganizationFactory(name="Hallowed Court")
        effect = ConsequenceEffectFactory(
            consequence=ConsequenceFactory(),
            effect_type=EffectType.LEGEND_AWARD,
            legend_base_value=10,
            legend_source_type=self.source,
            legend_description_template="The land dispute is ruled.",
        )
        NamedOrganizationFactory(
            consequence_effect=effect,
            organization=self.ruled_against,
            role=HARMED,
            base_amount=200,
        )
        self.effect = effect

    def _apply(self, success_level: int):
        context = ResolutionContext(
            character=self.persona.character_sheet.character,
            participants=[self.persona],
            outcome_tier=CheckOutcomeFactory(
                name=f"tier {success_level}", success_level=success_level
            ),
        )
        return apply_effect(self.effect, context)

    def test_a_success_scales_the_base_by_the_tier_multiplier(self) -> None:
        self._apply(success_level=1)
        assert _value(self.persona, self.ruled_against) == -240  # 200 x 1.2
        (event,) = OrganizationReputationEvent.objects.all()
        assert event.cause == CAUSE.DEED_NAMED
        assert event.legend_entry.persona == self.persona

    def test_the_deed_records_the_named_organization(self) -> None:
        self._apply(success_level=0)
        (named,) = DeedOrganization.objects.all()
        assert named.organization == self.ruled_against
        assert named.legend_entry.persona == self.persona


class SceneReachDecidesWhetherTheyReactTests(TestCase):
    """A scene deed the reach check contains or keeps private does not react at once."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.realm = RealmFactory()
        cls.society = SocietyFactory(realm=cls.realm, mercy=5)
        cls.kingdom = AreaFactory(level=AreaLevel.KINGDOM, realm=cls.realm)
        cls.vile = PhilosophicalArchetypeFactory(name="Vile Conduct", mercy_delta=-2)
        cls.noble = PhilosophicalArchetypeFactory(name="Noble Conduct", mercy_delta=2)
        cls.harmed = OrganizationFactory(name="Harmed Guild")
        cls.helped = OrganizationFactory(name="Helped Guild")

    def _deed(self, *, public: bool, archetypes):
        persona = CharacterSheetFactory().primary_persona
        scene = SceneFactory(location=RoomProfileFactory(area=self.kingdom, is_public=public))
        reactions = [
            NamedReaction(self.harmed, HARMED, False, 100),
            NamedReaction(self.helped, HELPED, False, 100),
        ]
        _, (entry,) = create_legend_event(
            "A deed",
            LegendSourceTypeFactory(),
            10,
            [persona],
            scene=scene,
            archetypes=archetypes,
            named_reactions=reactions,
        )
        return persona, entry

    def test_a_contained_deed_holds_the_harmed_organization_as_a_victim(self) -> None:
        persona, entry = self._deed(public=False, archetypes=[self.vile])
        assert _value(persona, self.harmed) == 0
        assert _value(persona, self.helped) == 0
        secret = Secret.objects.get(legend_deed=entry)
        assert [v.organization for v in secret.victims.all()] == [self.harmed]
        assert secret.victims.get().severity is None

    def test_a_deed_kept_private_with_no_secret_gets_a_new_one_for_the_harmed(self) -> None:
        persona, entry = self._deed(public=False, archetypes=[self.noble])
        assert _value(persona, self.harmed) == 0
        assert _value(persona, self.helped) == 0
        secret = Secret.objects.get(legend_deed=entry)
        (victim,) = secret.victims.all()
        assert victim.organization == self.harmed
        assert victim.severity == 100

    def test_a_public_deed_reacts_at_once_both_ways(self) -> None:
        persona, _ = self._deed(public=True, archetypes=[self.noble])
        assert _value(persona, self.harmed) == -100
        assert _value(persona, self.helped) == 100


class ReactToNamedOrganizationsRoutingTests(TestCase):
    def setUp(self) -> None:
        self.persona = CharacterSheetFactory().primary_persona
        self.org = OrganizationFactory()

    def test_a_contained_act_does_nothing_here(self) -> None:
        applied = react_to_named_organizations(
            persona=self.persona,
            reactions=[NamedReaction(self.org, HARMED, False, 100)],
            archetypes=[],
            reach=NamedActReach.CONTAINED,
        )
        assert applied == {}
        assert _value(self.persona, self.org) == 0

    def test_a_persona_that_cannot_hold_reputation_reacts_to_nothing(self) -> None:
        from world.scenes.constants import PersonaType
        from world.scenes.factories import PersonaFactory

        mask = PersonaFactory(persona_type=PersonaType.TEMPORARY)
        applied = react_to_named_organizations(
            persona=mask, reactions=[NamedReaction(self.org, HELPED, False, 100)], archetypes=[]
        )
        assert applied == {}


class RivalsAndAlliesReactTests(TestCase):
    def setUp(self) -> None:
        self.persona = CharacterSheetFactory().primary_persona
        self.court = OrganizationFactory(name="Hallowed Court")
        self.wardens = OrganizationFactory(name="Wardens of the March")
        self.friends = OrganizationFactory(name="Court Friends")
        self.wardens_of_wardens = OrganizationFactory(name="Wardens' Rivals")
        OrganizationRelationFactory(
            organization=self.wardens,
            toward=self.court,
            kind=OrganizationRelationKind.RIVAL,
            share_percent=50,
        )
        OrganizationRelationFactory(
            organization=self.friends,
            toward=self.court,
            kind=OrganizationRelationKind.ALLY,
            share_percent=25,
        )
        OrganizationRelationFactory(
            organization=self.wardens_of_wardens,
            toward=self.wardens,
            kind=OrganizationRelationKind.RIVAL,
            share_percent=50,
        )

    def test_a_rival_moves_the_other_way_by_its_share_and_the_ripple_stops(self) -> None:
        bump_organization_reputation(self.persona, self.court, -240, cause=CAUSE.GANG_TURF)
        assert _value(self.persona, self.court) == -240
        assert _value(self.persona, self.wardens) == 120
        assert _value(self.persona, self.friends) == -60
        # One step only: the rival's own change moved nobody.
        assert _value(self.persona, self.wardens_of_wardens) == 0

    def test_the_ripple_is_recorded_citing_the_source_change(self) -> None:
        bump_organization_reputation(self.persona, self.court, -240, cause=CAUSE.GANG_TURF)
        source = OrganizationReputationEvent.objects.get(reputation__organization=self.court)
        ripple = OrganizationReputationEvent.objects.get(reputation__organization=self.wardens)
        assert ripple.cause == CAUSE.RELATED_ORGANIZATION
        assert ripple.source_event == source
        assert ripple.amount == 120

    def test_a_character_creation_seed_does_not_ripple(self) -> None:
        bump_organization_reputation(self.persona, self.court, -240, cause=CAUSE.CHARACTER_CREATION)
        assert _value(self.persona, self.wardens) == 0

    def test_a_staff_adjustment_does_not_ripple(self) -> None:
        bump_organization_reputation(
            self.persona, self.court, 300, cause=CAUSE.STAFF_ADJUSTMENT, scale_gain=False
        )
        assert _value(self.persona, self.friends) == 0

    def test_the_share_applies_to_the_change_actually_applied(self) -> None:
        OrganizationReputationFactory(persona=self.persona, organization=self.court, value=-980)
        bump_organization_reputation(self.persona, self.court, -240, cause=CAUSE.GANG_TURF)
        assert _value(self.persona, self.wardens) == 10  # half of the 20 that applied

    def test_the_reason_line_names_the_organization_that_caused_it(self) -> None:
        OrganizationReputationReasonLineFactory(
            cause=CAUSE.RELATED_ORGANIZATION,
            text="{tier}, because {organization} now holds you as {other_tier}",
        )
        bump_organization_reputation(self.persona, self.court, -240, cause=CAUSE.GANG_TURF)
        reputation = OrganizationReputation.objects.get(
            persona=self.persona, organization=self.wardens
        )
        (line,) = reason_lines_by_reputation([reputation.pk])[reputation.pk]
        assert line == "Favored, because Hallowed Court now holds you as Disfavored"

    def test_a_ripple_follows_a_deed_named_reaction(self) -> None:
        sheet = CharacterSheetFactory()
        react_to_named_organizations(
            persona=sheet.primary_persona,
            reactions=[NamedReaction(self.court, HARMED, False, 200)],
            archetypes=[],
            legend_entry=LegendEntryFactory(persona=sheet.primary_persona),
        )
        assert _value(sheet.primary_persona, self.wardens) == 100


class AuthoringRulesTests(TestCase):
    def test_only_if_exposed_is_refused_on_a_helped_row(self) -> None:
        award = MissionRenownAward.objects.create(
            route=MissionOptionRouteFactory(), magnitude=RenownMagnitude.SMALL
        )
        org = OrganizationFactory()
        row = NamedOrganizationFactory.build(
            mission_award=award, organization=org, role=HELPED, only_if_exposed=True
        )
        with self.assertRaises(ValidationError):
            row.full_clean()
        with self.assertRaises(IntegrityError), transaction.atomic():
            NamedOrganizationFactory(
                mission_award=award, organization=org, role=HELPED, only_if_exposed=True
            )

    def test_a_consequence_row_needs_a_base_and_a_mission_row_must_not_have_one(self) -> None:
        effect = ConsequenceEffectFactory(
            effect_type=EffectType.LEGEND_AWARD,
            legend_base_value=5,
            legend_source_type=LegendSourceTypeFactory(),
        )
        no_base = NamedOrganizationFactory.build(consequence_effect=effect, base_amount=None)
        with self.assertRaises(ValidationError):
            no_base.full_clean()
        award = MissionRenownAward.objects.create(
            route=MissionOptionRouteFactory(), magnitude=RenownMagnitude.SMALL
        )
        with_base = NamedOrganizationFactory.build(mission_award=award, base_amount=10)
        with self.assertRaises(ValidationError):
            with_base.full_clean()

    def test_a_row_needs_exactly_one_owner(self) -> None:
        with self.assertRaises(IntegrityError), transaction.atomic():
            NamedOrganizationFactory(mission_award=None, consequence_effect=None)

    def test_only_a_legend_award_effect_can_name_organizations(self) -> None:
        effect = ConsequenceEffectFactory(effect_type=EffectType.APPLY_CONDITION)
        row = NamedOrganizationFactory.build(consequence_effect=effect, base_amount=10)
        with self.assertRaises(ValidationError):
            row.full_clean()

    def test_a_relation_share_is_one_to_fifty_between_two_organizations(self) -> None:
        a, b = OrganizationFactory(), OrganizationFactory()
        for share in (0, 51):
            row = OrganizationRelationFactory.build(organization=a, toward=b, share_percent=share)
            with self.assertRaises(ValidationError):
                row.full_clean()
        with self.assertRaises(ValidationError):
            OrganizationRelationFactory.build(organization=a, toward=a).full_clean()
        with self.assertRaises(IntegrityError), transaction.atomic():
            OrganizationRelationFactory(organization=a, toward=a)
        OrganizationRelationFactory(organization=a, toward=b)
        with self.assertRaises(IntegrityError), transaction.atomic():
            OrganizationRelationFactory(organization=a, toward=b)
