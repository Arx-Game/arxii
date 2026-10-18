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
from world.narrative.constants import NarrativeCategory
from world.narrative.models import NarrativeMessageDelivery
from world.secrets.models import Secret
from world.secrets.services import grant_secret_knowledge
from world.seeds.checks import seed_check_resolution_tables
from world.seeds.social_checks import seed_social_check_content
from world.skills.factories import CharacterSpecializationValueFactory
from world.skills.models import Specialization
from world.societies.constants import OrganizationReputationCause
from world.societies.factories import (
    OrganizationFactory,
    OrganizationMembershipFactory,
    OrganizationReputationReasonLineFactory,
    SocietyFactory,
)
from world.societies.models import OrganizationReputation
from world.tasking.constants import TaskTargetKind
from world.tasking.factories import OrgTaskFactory, TaskOutcomeRouteFactory, TaskTemplateFactory
from world.tasking.services import assign_agent, resolve_task
from world.traits.factories import CheckOutcomeFactory


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
