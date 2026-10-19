"""Journeys for an organization's reputation of a character (#4448, #4339 slice 1).

A spy job done badly leaves a residue secret that names the job's target as its victim.
When rumor makes the secret public the target organization thinks less of the handler, the
handler's sheet says why in staff-authored words, and nobody else's sheet says anything.
"""

from __future__ import annotations

from datetime import timedelta

from django.test import override_settings
from evennia.utils.ansi import strip_ansi

from evennia_extensions.factories import RoomProfileFactory
from integration_tests.harness import JourneyCase
from world.areas.constants import AreaLevel
from world.areas.factories import AreaFactory
from world.assets.factories import NPCAssetFactory
from world.character_creation.factories import RealmFactory
from world.checks.test_helpers import force_check_outcome
from world.missions.constants import OptionKind, OptionSource
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
from world.narrative.constants import NarrativeCategory
from world.narrative.models import NarrativeMessageDelivery
from world.predicates.describe import explain_leaf_for_staff
from world.secrets.models import Secret
from world.secrets.services import expose_secret, grant_secret_knowledge
from world.seeds.checks import seed_check_resolution_tables
from world.seeds.social_checks import seed_social_check_content
from world.skills.factories import CharacterSpecializationValueFactory
from world.skills.models import Specialization
from world.societies.constants import (
    NamedOrganizationRole,
    OrganizationRelationKind,
    OrganizationReputationCause,
    RenownMagnitude,
)
from world.societies.factories import (
    NamedOrganizationFactory,
    OrganizationFactory,
    OrganizationMembershipFactory,
    OrganizationRelationFactory,
    OrganizationReputationReasonLineFactory,
    SocietyFactory,
)
from world.societies.models import OrganizationReputation
from world.tasking.constants import TaskTargetKind
from world.tasking.factories import OrgTaskFactory, TaskOutcomeRouteFactory, TaskTemplateFactory
from world.tasking.services import assign_agent, resolve_task
from world.traits.factories import CheckOutcomeFactory

HARMED = NamedOrganizationRole.HARMED
HELPED = NamedOrganizationRole.HELPED


@override_settings(SEED_SAMPLE_CONTENT=True)  # the social check content gates on it
class ASpyJobGoneWrong(JourneyCase):
    """Ysmay's job against the Guild of Locks went badly; Hobb hears of it and spreads it."""

    def setUp(self) -> None:
        super().setUp()
        seed_check_resolution_tables()
        seed_social_check_content()
        realm = RealmFactory()
        SocietyFactory(realm=realm)
        hub_area = AreaFactory(name="The Bazaar", level=AreaLevel.NEIGHBORHOOD, realm=realm)
        self.hub = RoomProfileFactory(area=hub_area, is_social_hub=True).objectdb

        self.ysmay = self.make_player("Ysmay", room=self.make_room("Ysmay's Lodging"))
        self.hobb = self.make_player("Hobb", room=self.hub)
        self.wat = self.make_player("Wat", room=self.hub)
        gossip = Specialization.objects.get(name="Gossip", parent_skill__trait__name="Persuasion")
        CharacterSpecializationValueFactory(
            character=self.hobb.sheet_data, specialization=gossip, value=10
        )

        self.locks = OrganizationFactory(name="Guild of Locks")
        self.own_org = OrganizationFactory(name="Lantern Circle")
        self.ysmay_persona = self.ysmay.sheet_data.primary_persona
        OrganizationMembershipFactory(organization=self.own_org, persona=self.ysmay_persona)
        self.outcome = CheckOutcomeFactory(name="job outcome", success_level=2)
        self.special = CheckOutcomeFactory(name="gossip_special", success_level=2)

    def _run_the_job(self) -> Secret:
        template = TaskTemplateFactory(duration=timedelta(days=1), target_kind=TaskTargetKind.ORG)
        TaskOutcomeRouteFactory(template=template, outcome_tier=self.outcome, incriminate_level=1)
        asset = NPCAssetFactory(promoter_persona=self.ysmay_persona)
        task = OrgTaskFactory(
            template=template,
            org=self.own_org,
            issued_by=self.ysmay_persona,
            target_kind=TaskTargetKind.ORG,
            target_org=self.locks,
        )
        with force_check_outcome(self.outcome):
            assign_agent(task, asset, self.ysmay_persona)
        with force_check_outcome(self.outcome):
            resolve_task(task)
        return Secret.objects.get(subject_sheet=self.ysmay.sheet_data)

    def _spread_until_public(self, secret: Secret) -> None:
        grant_secret_knowledge(roster_entry=self.hobb.sheet_data.roster_entry, secret=secret)
        for _ in range(40):
            with force_check_outcome(self.special):
                told = strip_ansi(self.telnet(self.hobb, "gossip plant 1"))
            if "public" in told.lower() or "everyone" in told.lower():
                return

    def _sheet_reputations(self, viewer) -> list[dict]:
        response = self.api(self.account_of(viewer)).get(f"/api/character-sheets/{self.ysmay.pk}/")
        self.assertEqual(response.status_code, 200, response.content)
        return response.data["standing"]["reputations"]

    def test_nothing_changes_until_the_secret_is_exposed(self) -> None:
        secret = self._run_the_job()
        self.assertEqual(secret.victims.get().organization, self.locks)
        self.assertFalse(OrganizationReputation.objects.filter(organization=self.locks).exists())

    def test_exposure_lowers_the_tier_and_the_sheet_says_why_to_its_owner_only(self) -> None:
        secret = self._run_the_job()
        self._spread_until_public(secret)

        reputation = OrganizationReputation.objects.get(
            persona=self.ysmay_persona, organization=self.locks
        )
        self.assertEqual(reputation.get_tier().value, "disfavored")
        (event,) = reputation.events.all()
        self.assertEqual(event.cause, OrganizationReputationCause.SECRET_EXPOSED)
        self.assertEqual(event.secret, secret)

        (row,) = self._sheet_reputations(self.ysmay)
        self.assertEqual(row["organization"], "Guild of Locks")
        self.assertEqual(row["tier"], "disfavored")
        self.assertEqual(row["reasons"], ["Disfavored [staff-authored reason text]"])
        self.assertNotIn("value", row)

        OrganizationReputationReasonLineFactory(
            cause=OrganizationReputationCause.SECRET_EXPOSED,
            text="{tier}: something you did was exposed",
        )
        (row,) = self._sheet_reputations(self.ysmay)
        self.assertEqual(row["reasons"], ["Disfavored: something you did was exposed"])
        # The reason names neither the secret nor Hobb, who spread it.
        self.assertNotIn(secret.content, str(row))
        self.assertNotIn("Hobb", str(row))

    def test_ysmay_is_told_the_tier_changed(self) -> None:
        secret = self._run_the_job()
        self._spread_until_public(secret)
        bodies = list(
            NarrativeMessageDelivery.objects.filter(
                recipient_character_sheet=self.ysmay.sheet_data,
                message__category=NarrativeCategory.RENOWN,
            ).values_list("message__body", flat=True)
        )
        self.assertEqual(bodies, ["Guild of Locks: Disfavored [staff-authored reason text]"])


class AMissionForOneOrganizationAgainstAnother(JourneyCase):
    """Ysmay's mission for the Lantern Order sabotages the Millwrights' mill (#4473, slice 2).

    The award names the Order as helped and the Millwrights as harmed only if exposed. The
    Carters were authored ahead of play as the Millwrights' rivals; the Order's tier rises at
    once, the Millwrights' waits for the exposure, and the Carters follow the Millwrights.
    """

    def setUp(self) -> None:
        super().setUp()
        self.ysmay = self.make_player("Ysmay", room=self.make_room("Ysmay's Lodging"))
        self.sheet = self.ysmay.sheet_data
        self.persona = self.sheet.primary_persona
        self.order = OrganizationFactory(name="Lantern Order")
        self.millwrights = OrganizationFactory(name="Millwrights")
        self.carters = OrganizationFactory(name="Carters")
        OrganizationRelationFactory(
            organization=self.carters,
            toward=self.millwrights,
            kind=OrganizationRelationKind.RIVAL,
            share_percent=50,
        )
        template = MissionTemplateFactory(name="Night at the Mill", risk_tier=1)
        node = MissionNodeFactory(template=template, key="entry", is_entry=True)
        option = MissionOptionFactory(
            node=node, order=0, option_kind=OptionKind.BRANCH, source_kind=OptionSource.AUTHORED
        )
        self.route = MissionOptionRouteFactory(option=option, outcome_tier=None, target_node=None)
        self.instance = MissionInstanceFactory(template=template)
        MissionParticipantFactory(
            instance=self.instance, character=self.sheet, is_contract_holder=True
        )
        self.deed = MissionDeedRecordFactory(
            instance=self.instance, actor=self.sheet, node=node, option=option
        )
        award = MissionRenownAward.objects.create(
            route=self.route, magnitude=RenownMagnitude.HIGH, contract_holder_only=True
        )
        NamedOrganizationFactory(mission_award=award, organization=self.order, role=HELPED)
        NamedOrganizationFactory(
            mission_award=award, organization=self.millwrights, role=HARMED, only_if_exposed=True
        )
        OrganizationReputationReasonLineFactory(
            cause=OrganizationReputationCause.DEED_NAMED, text="{tier}, because of {title}"
        )
        OrganizationReputationReasonLineFactory(
            cause=OrganizationReputationCause.RELATED_ORGANIZATION,
            text="{tier}, because {organization} is now {other_tier} toward you",
        )

    def _sheet_reputations(self) -> dict[str, dict]:
        response = self.api(self.account_of(self.ysmay)).get(
            f"/api/character-sheets/{self.ysmay.pk}/"
        )
        self.assertEqual(response.status_code, 200, response.content)
        return {row["organization"]: row for row in response.data["standing"]["reputations"]}

    def test_the_helped_organization_rises_now_and_the_harmed_one_waits(self) -> None:
        emit_terminal_renown_awards(self.instance, self.route, self.deed)

        rows = self._sheet_reputations()
        self.assertEqual(list(rows), ["Lantern Order"])
        self.assertEqual(rows["Lantern Order"]["tier"], "liked")
        self.assertEqual(rows["Lantern Order"]["reasons"], ["Liked, because of Night at the Mill"])
        bodies = list(
            NarrativeMessageDelivery.objects.filter(
                recipient_character_sheet=self.sheet, message__category=NarrativeCategory.RENOWN
            ).values_list("message__body", flat=True)
        )
        self.assertIn("Lantern Order: Liked, because of Night at the Mill", bodies)
        self.assertFalse([body for body in bodies if "Millwrights" in body])

    def test_exposure_drops_the_millwrights_and_their_rivals_warm_to_her(self) -> None:
        emit_terminal_renown_awards(self.instance, self.route, self.deed)
        secret = Secret.objects.get(subject_sheet=self.sheet)

        expose_secret(secret, societies=[SocietyFactory()])

        rows = self._sheet_reputations()
        self.assertEqual(rows["Millwrights"]["tier"], "disliked")
        self.assertEqual(rows["Carters"]["tier"], "favored")
        self.assertEqual(
            rows["Carters"]["reasons"],
            ["Favored, because Millwrights is now Disliked toward you"],
        )
        # A rival's rule sees both causes, one per line, for the GM.
        reason = explain_leaf_for_staff(
            {"leaf": "min_org_reputation", "params": {"org": "Carters", "tier": "favored"}},
            self.persona,
        )
        self.assertIn("related organization", reason)
        self.assertIn("Millwrights moved -250 by secret exposed", reason)
