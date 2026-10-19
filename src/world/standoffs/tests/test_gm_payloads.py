"""Who sees what of a standoff over the API (#4354).

The GM view (every group's cause, drives, faction rules and matches, force, morale) goes
to the scene's GMs and staff only. A player gets their own view; an onlooker in the scene
gets the public summary. The GM decides proposals through the prompt queue and moves
morale through the encounter.
"""

import json
from unittest.mock import patch

from django.test import TestCase
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory, CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import CheckTypeFactory
from world.combat.constants import CauseKind, OpponentTier, ParticipantStatus
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
    CreatureTemplateFactory,
    seed_scaling_defaults,
)
from world.gm.constants import GMPromptStatus
from world.gm.models import GMPrompt
from world.mechanics.factories import PropertyFactory
from world.roster.factories import RosterTenureFactory
from world.scenes.factories import SceneFactory, SceneParticipationFactory
from world.standoffs.constants import StandoffGroupState
from world.standoffs.factories import (
    CreatureDriveFactory,
    FactionRuleFactory,
    StandoffApproachFactory,
    restamp_from_templates,
)
from world.standoffs.models import StandoffConfig, StandoffMoraleRuling
from world.standoffs.services.state import open_standoff
from world.standoffs.services.verbs import standoff_press
from world.standoffs.tests.test_proposals import CHECK, forced

LEVEL = "world.standoffs.services.force.effective_combat_level"
DRIVE_NAME = "PLACEHOLDER drive property"
ANGLE = "PLACEHOLDER angle text"


def _player(name: str):
    account = AccountFactory(username=f"acct_{name}")
    character = CharacterFactory(db_key=name)
    sheet = CharacterSheetFactory(character=character)
    RosterTenureFactory(
        roster_entry__character_sheet=sheet,
        player_data__account=account,
    )
    return account, sheet


class StandoffPayloadTests(TestCase):
    def setUp(self) -> None:
        # setUp, not setUpTestData: tests move groups into proposals and fights.
        seed_scaling_defaults()
        self.gm = AccountFactory(username="acct_gm")
        self.player, self.player_sheet = _player("standoffplayer")
        self.onlooker, _ = _player("standoffonlooker")
        self.scene = SceneFactory()
        SceneParticipationFactory(scene=self.scene, account=self.gm, is_gm=True)
        self.encounter = CombatEncounterFactory(scene=self.scene)
        self.participant = CombatParticipantFactory(
            encounter=self.encounter,
            character_sheet=self.player_sheet,
            status=ParticipantStatus.ACTIVE,
        )
        self.template = CreatureTemplateFactory(tier=OpponentTier.MOOK, cause=CauseKind.ORDERS)
        for _ in range(3):
            CombatOpponentFactory(encounter=self.encounter, creature_template=self.template)
        CreatureDriveFactory(
            creature_template=self.template, property=PropertyFactory(name=DRIVE_NAME)
        )
        restamp_from_templates(self.encounter)
        FactionRuleFactory(creature_template=self.template, rule={}, angle_text=ANGLE)
        config = StandoffConfig.load()
        config.read_check_type = CheckTypeFactory()
        config.save()
        level = patch(LEVEL, return_value=100)
        level.start()
        self.addCleanup(level.stop)
        self.group = open_standoff(self.encounter)[0]

    def detail(self, account) -> dict:
        client = APIClient()
        client.force_authenticate(user=account)
        response = client.get(f"/api/combat/{self.encounter.pk}/")
        self.assertEqual(response.status_code, 200)
        return response.data

    def test_the_gm_sees_the_whole_profile(self) -> None:
        data = self.detail(self.gm)
        self.assertIsNone(data["standoff"])
        (group,) = data["gm_standoff"]["groups"]
        self.assertEqual(group["cause"], "Orders")
        self.assertFalse(group["cause_fires"])
        self.assertEqual([d["label"] for d in group["drives"]], [DRIVE_NAME])
        (rule,) = group["faction_rules"]
        self.assertEqual(rule["angle_text"], ANGLE)
        self.assertEqual(rule["matched_by"], [self.player_sheet.primary_persona.name])
        self.assertEqual(len(group["members"]), 3)

    def test_the_gm_reads_why_a_reputation_rule_matches_and_which_acts_moved_it(self) -> None:
        from world.secrets.factories import SecretFactory
        from world.societies.constants import OrganizationReputationCause
        from world.societies.factories import OrganizationFactory
        from world.societies.renown import bump_organization_reputation

        org = OrganizationFactory(name="Guild of Locks")
        FactionRuleFactory(
            creature_template=self.template,
            rule={"leaf": "max_org_reputation", "params": {"org": org.name, "tier": "disfavored"}},
            angle_text="reads the guild's grudge",
        )
        bump_organization_reputation(
            self.player_sheet.primary_persona,
            org,
            -150,
            cause=OrganizationReputationCause.SECRET_EXPOSED,
            secret=SecretFactory(),
        )
        (group,) = self.detail(self.gm)["gm_standoff"]["groups"]
        (rule,) = [
            r for r in group["faction_rules"] if r["angle_text"] == "reads the guild's grudge"
        ]
        (reason,) = rule["why"]
        tier_line, moved = reason.split("\n")
        self.assertIn("Disfavored", tier_line)
        self.assertTrue(moved.startswith("Moved by: secret exposed (secret #"), moved)

    def test_the_gm_reads_a_rivals_reaction_and_the_change_it_followed(self) -> None:
        from world.societies.constants import (
            OrganizationRelationKind,
            OrganizationReputationCause,
        )
        from world.societies.factories import OrganizationFactory, OrganizationRelationFactory
        from world.societies.renown import bump_organization_reputation

        court = OrganizationFactory(name="Hallowed Court")
        wardens = OrganizationFactory(name="Wardens of the March")
        OrganizationRelationFactory(
            organization=wardens,
            toward=court,
            kind=OrganizationRelationKind.RIVAL,
            share_percent=50,
        )
        FactionRuleFactory(
            creature_template=self.template,
            rule={"leaf": "min_org_reputation", "params": {"org": wardens.name, "tier": "favored"}},
            angle_text="the wardens favor her",
        )
        bump_organization_reputation(
            self.player_sheet.primary_persona,
            court,
            -240,
            cause=OrganizationReputationCause.GANG_TURF,
        )
        (group,) = self.detail(self.gm)["gm_standoff"]["groups"]
        (rule,) = [r for r in group["faction_rules"] if r["angle_text"] == "the wardens favor her"]
        (reason,) = rule["why"]
        tier_line, moved, source = reason.split("\n")
        self.assertIn("Favored", tier_line)
        self.assertEqual(
            moved,
            "Moved by: related organization, +120 (50% of Hallowed Court's -240, rival), "
            "Unknown to Favored",
        )
        self.assertEqual(
            source, "Source: gang turf moved Hallowed Court by -240, Unknown to Disfavored"
        )

    def test_no_player_or_onlooker_payload_carries_the_gm_view(self) -> None:
        for account in (self.player, self.onlooker):
            data = self.detail(account)
            self.assertIsNone(data["gm_standoff"])
            self.assertNotIn(DRIVE_NAME, json.dumps(data["standoff_summary"]))
            self.assertNotIn("Orders", json.dumps(data["standoff_summary"]))

    def test_the_onlooker_gets_the_public_summary_and_no_player_view(self) -> None:
        data = self.detail(self.onlooker)
        self.assertIsNone(data["standoff"])
        summary = data["standoff_summary"]
        (group,) = summary["groups"]
        self.assertEqual((group["name"], group["member_count"]), (self.template.name, 3))
        self.assertEqual(summary["participants"], [self.player_sheet.primary_persona.name])

    def test_a_proposal_shows_as_deciding_to_players_and_open_to_onlookers(self) -> None:
        with patch(CHECK, return_value=forced(-2)):
            standoff_press(self.participant, self.group, StandoffApproachFactory())
        self.group.refresh_from_db()
        self.assertEqual(self.group.state, StandoffGroupState.PROPOSED)
        self.assertEqual(self.detail(self.player)["standoff"]["groups"][0]["state"], "proposed")
        summary_group = self.detail(self.onlooker)["standoff_summary"]["groups"][0]
        self.assertEqual(summary_group["state"], "open")
        self.assertTrue(summary_group["emboldened"])
        gm_group = self.detail(self.gm)["gm_standoff"]["groups"][0]
        self.assertIsNotNone(gm_group["pending_prompt_id"])
        self.assertTrue(gm_group["proposal_reason"])

    def test_the_gm_decides_through_the_prompt_queue(self) -> None:
        with patch(CHECK, return_value=forced(-2)):
            standoff_press(self.participant, self.group, StandoffApproachFactory())
        prompt = GMPrompt.objects.get(standoff_group=self.group)
        client = APIClient()
        client.force_authenticate(user=self.gm)
        queue = client.get("/api/gm/prompts/", {"scene": self.scene.pk}).data["results"]
        self.assertEqual(queue[0]["standoff_group_name"], self.template.name)
        self.assertEqual(queue[0]["standoff_cause_label"], "Orders")
        # The patched level-100 player against the group, one band emboldened by the botch.
        self.assertRegex(
            queue[0]["standoff_force"], r"^Force: party 100, them [\d.]+, emboldened 1 band\.$"
        )
        refused = client.post(f"/api/gm/prompts/{prompt.pk}/override/", {}, format="json")
        self.assertEqual(refused.status_code, 400)
        response = client.post(
            f"/api/gm/prompts/{prompt.pk}/override/",
            {"reason": "PLACEHOLDER reason"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        prompt.refresh_from_db()
        self.assertEqual(prompt.status, GMPromptStatus.DISMISSED)
        self.group.refresh_from_db()
        self.assertEqual(self.group.state, StandoffGroupState.OPEN)
        gm_group = self.detail(self.gm)["gm_standoff"]["groups"][0]
        self.assertEqual(gm_group["last_decision"], "Overridden: PLACEHOLDER reason")

    def test_a_player_cannot_reach_another_gms_prompt(self) -> None:
        with patch(CHECK, return_value=forced(-2)):
            standoff_press(self.participant, self.group, StandoffApproachFactory())
        prompt = GMPrompt.objects.get(standoff_group=self.group)
        client = APIClient()
        client.force_authenticate(user=self.player)
        response = client.post(f"/api/gm/prompts/{prompt.pk}/confirm/")
        self.assertIn(response.status_code, (403, 404))
        self.group.refresh_from_db()
        self.assertEqual(self.group.state, StandoffGroupState.PROPOSED)

    def test_the_gm_moves_morale_through_the_encounter(self) -> None:
        client = APIClient()
        client.force_authenticate(user=self.gm)
        url = f"/api/combat/{self.encounter.pk}/standoff-morale/"
        body = {"group_id": self.group.pk, "direction": "shake", "reason": "PLACEHOLDER"}
        with patch("actions.definitions.gm_standoff._announce"):
            response = client.post(url, body, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["gm_standoff"]["groups"][0]["morale_state"], "falter")
        self.assertTrue(StandoffMoraleRuling.objects.filter(group=self.group).exists())
        player = APIClient()
        player.force_authenticate(user=self.player)
        self.assertEqual(player.post(url, body, format="json").status_code, 403)
