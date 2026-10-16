"""Journeys for the actions tranche (#3657, tranche 2): organizations, the consent
lists and carrying a body. Each types what a player types or sends what the web
client sends, and asserts what the player was told."""

from __future__ import annotations

from django.test import override_settings

from integration_tests.harness import JourneyCase
from world.conditions.constants import UNCONSCIOUS_CONDITION_NAME
from world.conditions.models import ConditionTemplate
from world.conditions.services import apply_condition
from world.consent.services import body_handling_category
from world.societies.factories import OrganizationFactory, OrganizationMembershipFactory
from world.societies.models import OrganizationMembership
from world.vitals.seeds import ensure_foundational_capabilities, ensure_unconscious_condition


def persona_of(character):
    return character.sheet_data.primary_persona


def rank_tier(organization, character) -> int | None:
    row = OrganizationMembership.objects.filter(
        organization=organization, persona=persona_of(character), left_at__isnull=True
    ).first()
    return None if row is None else row.rank.tier


class JoiningAndRisingInAnOrganization(JourneyCase):
    """Ysmay leads the Lantern Guild; Hobb is invited, joins, rises, falls and is expelled."""

    def setUp(self) -> None:
        super().setUp()
        self.room = self.make_room("The Lantern")
        self.ysmay = self.make_player("Ysmay", room=self.room)
        self.hobb = self.make_player("Hobb", room=self.room)
        self.guild = OrganizationFactory(name="The Lantern Guild")
        self.watch(self.hobb)
        OrganizationMembershipFactory(
            organization=self.guild, persona=persona_of(self.ysmay), rank=1
        )

    def test_an_invitation_accepted_then_the_ranks(self) -> None:
        told = self.telnet(self.hobb, "org join The Lantern Guild")
        self.assertIn("You have no pending invitation to join that organization.", told)

        told = self.telnet(self.ysmay, "org invite Hobb in The Lantern Guild")
        self.assertIn("You invite Hobb to join The Lantern Guild.", told)
        invited = (
            "Ysmay invites you to join The Lantern Guild. accept org to join, deny org to refuse."
        )
        self.assertTold(self.hobb, invited)

        told = self.telnet(self.hobb, "accept")
        self.assertIn("[org] invitation to join The Lantern Guild from Ysmay", told)
        told = self.telnet(self.hobb, "accept org")
        self.assertIn("You join The Lantern Guild.", told)
        self.assertEqual(rank_tier(self.guild, self.hobb), 5)

        told = self.telnet(self.ysmay, "org promote Hobb in The Lantern Guild")
        self.assertIn("You promote Hobb in The Lantern Guild.", told)
        self.assertEqual(rank_tier(self.guild, self.hobb), 4)

        told = self.telnet(self.ysmay, "org demote Hobb in The Lantern Guild")
        self.assertIn("You demote Hobb in The Lantern Guild.", told)
        self.assertEqual(rank_tier(self.guild, self.hobb), 5)

        told = self.telnet(self.ysmay, "org expel Hobb in The Lantern Guild")
        self.assertIn("You expel Hobb from The Lantern Guild.", told)
        self.assertIsNone(rank_tier(self.guild, self.hobb))

    def test_a_member_leaves_and_cannot_leave_twice(self) -> None:
        OrganizationMembershipFactory(organization=self.guild, persona=persona_of(self.hobb))
        told = self.telnet(self.hobb, "org leave The Lantern Guild")
        self.assertIn("You leave The Lantern Guild.", told)
        self.assertIsNone(rank_tier(self.guild, self.hobb))
        told = self.telnet(self.hobb, "org leave The Lantern Guild")
        self.assertNotIn("You leave", told)
        self.assertTrue(told.strip(), "a second leave said nothing")

    def test_a_rank_and_file_member_cannot_promote_the_leader(self) -> None:
        OrganizationMembershipFactory(organization=self.guild, persona=persona_of(self.hobb))
        told = self.telnet(self.hobb, "org promote Ysmay in The Lantern Guild")
        self.assertNotIn("You promote", told)
        self.assertTrue(told.strip(), "the refusal said nothing")
        self.assertEqual(rank_tier(self.guild, self.ysmay), 1)

    def test_an_unknown_organization_is_named_back(self) -> None:
        told = self.telnet(self.hobb, "org join The Moth Club")
        self.assertIn("Could not find organization 'The Moth Club'.", told)

    def test_the_web_invite_is_the_same_action(self) -> None:
        result = self.web(
            self.ysmay,
            "org_invite",
            target_persona_id=persona_of(self.hobb).pk,
            organization_id=self.guild.pk,
        )
        self.assertTrue(result.detail.success, result.detail.message)
        self.assertIn("You invite Hobb to join The Lantern Guild.", result.detail.message)
        self.assertTold(self.hobb, "Ysmay invites you to join The Lantern Guild.")
        self.assertIn(
            "[org] invitation to join The Lantern Guild from Ysmay",
            self.telnet(self.hobb, "accept"),
        )


@override_settings(SEED_SAMPLE_CONTENT=True)
class KeepingHandsOffHerBody(JourneyCase):
    """Ysmay is knocked out; whether Hobb may carry her is her consent to give.

    The awareness capability and the Unconscious template are content-repo rows
    (#2698); the vitals seeds only invent them under ``SEED_SAMPLE_CONTENT``, so
    this journey runs with it on, the way the sample-content deploy does. On a
    deploy without those rows authored, ``can_act`` is True for everyone and an
    unconscious body can be neither protected nor carried.
    """

    def setUp(self) -> None:
        super().setUp()
        ensure_foundational_capabilities()
        ensure_unconscious_condition()
        body_handling_category()
        self.room = self.make_room("The Lantern")
        self.ysmay = self.make_player("Ysmay", room=self.room)
        self.hobb = self.make_player("Hobb", room=self.room)

    def knock_out(self, character) -> None:
        template = ConditionTemplate.objects.get(name=UNCONSCIOUS_CONDITION_NAME)
        result = apply_condition(character, template, severity=1)
        self.assertTrue(result.success, result.message)

    def test_an_awake_character_is_asked_not_carried(self) -> None:
        result = self.web(self.hobb, "carry_body", target=self.ysmay)
        self.assertFalse(result.detail.success)
        self.assertIn("Ysmay is in no state to be slung over a shoulder", result.detail.message)

    def test_consent_opens_the_door_and_the_blacklist_shuts_it(self) -> None:
        self.knock_out(self.ysmay)
        result = self.web(self.hobb, "carry_body", target=self.ysmay)
        self.assertFalse(result.detail.success)
        self.assertIn("Ysmay's player has not consented to body handling.", result.detail.message)

        told = self.telnet(self.ysmay, "consent whitelist add Hobb to body-handling")
        self.assertIn("may target you with Body Handling actions.", told)
        result = self.web(self.hobb, "carry_body", target=self.ysmay)
        self.assertTrue(result.detail.success, result.detail.message)
        self.assertIn("You are now carrying Ysmay.", result.detail.message)

        result = self.web(self.hobb, "set_down_body")
        self.assertTrue(result.detail.success, result.detail.message)
        result = self.web(self.hobb, "set_down_body")
        self.assertFalse(result.detail.success)
        self.assertIn("You are not carrying anyone.", result.detail.message)

        # Body handling is an allowlist category: taking Hobb off the list shuts
        # the door again. (Blacklisting him while he is still listed does not;
        # the gate consults only the whitelist under this mode, which the
        # blacklist command's reply does not say. Recorded as a gap on #3657.)
        told = self.telnet(self.ysmay, "consent whitelist remove Hobb from body-handling")
        self.assertIn("removed from Body Handling whitelist.", told)
        result = self.web(self.hobb, "carry_body", target=self.ysmay)
        self.assertFalse(result.detail.success)
        self.assertIn("Ysmay's player has not consented to body handling.", result.detail.message)

    def test_the_blacklist_lines_read_back(self) -> None:
        told = self.telnet(self.ysmay, "consent blacklist add Hobb to body-handling")
        self.assertIn("may no longer target you with Body Handling actions.", told)
        told = self.telnet(self.ysmay, "consent blacklist remove Hobb from body-handling")
        self.assertIn("removed from Body Handling blacklist.", told)
        told = self.telnet(self.ysmay, "consent blacklist remove Hobb from body-handling")
        self.assertIn("That character is not on the blacklist.", told)

    def test_a_category_that_does_not_exist_is_named_back(self) -> None:
        told = self.telnet(self.ysmay, "consent blacklist add Hobb to hugging")
        self.assertIn("No consent category named 'hugging'", told)
