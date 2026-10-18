"""Journeys for the actions tranche (#3657, tranche 2): organizations, the consent
lists and carrying a body. Each types what a player types or sends what the web
client sends, and asserts what the player was told."""

from __future__ import annotations

from datetime import timedelta

from django.test import override_settings
from django.utils import timezone

from integration_tests.harness import JourneyCase
from world.conditions.constants import UNCONSCIOUS_CONDITION_NAME
from world.conditions.models import ConditionTemplate
from world.conditions.services import apply_condition
from world.consent.factories import SocialConsentCategoryFactory
from world.consent.models import SocialConsentCategoryRule
from world.consent.services import body_handling_category
from world.relationships.constants import TypeValence
from world.relationships.factories import RelationshipTypeFactory
from world.roster.models import RosterTenure
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

    def carry_allowed(self) -> bool:
        """Whether Hobb may carry her right now; a carry is set down again so the next
        check starts from the floor."""
        result = self.web(self.hobb, "carry_body", target=self.ysmay)
        if result.detail.success:
            self.web(self.hobb, "set_down_body")
            return True
        self.assertIn("Ysmay's player has not consented to body handling.", result.detail.message)
        return False

    def test_each_mode_decides_who_may_handle_her(self) -> None:
        SocialConsentCategoryFactory(key="hugging", name="Hugging")
        self.knock_out(self.ysmay)
        self.assertFalse(self.carry_allowed())

        self.assertIn(
            "Body Handling set to everyone.",
            self.telnet(self.ysmay, "consent category body-handling=everyone"),
        )
        self.assertTrue(self.carry_allowed())

        # Under the blacklist mode everyone may, except the people on this category's list.
        self.assertIn(
            "Body Handling set to all-but-blacklist.",
            self.telnet(self.ysmay, "consent category body-handling=blacklist"),
        )
        self.assertTrue(self.carry_allowed())
        self.telnet(self.ysmay, "consent blacklist add Hobb to hugging")
        self.assertTrue(self.carry_allowed())
        self.telnet(self.ysmay, "consent blacklist add Hobb to body-handling")
        self.assertFalse(self.carry_allowed())
        self.telnet(self.ysmay, "consent blacklist remove Hobb from body-handling")
        self.assertTrue(self.carry_allowed())

        # Under the friends mode only the friends she has named, and her whitelist, may;
        # Hobb naming her does not count.
        self.assertIn(
            "Body Handling set to friends.",
            self.telnet(self.ysmay, "consent category body-handling=friends"),
        )
        self.assertFalse(self.carry_allowed())
        self.assertIn(
            "You added Ysmay as a friend (from this character).",
            self.telnet(self.hobb, "friend Ysmay"),
        )
        self.assertFalse(self.carry_allowed())
        self.assertIn(
            "You added Hobb as a friend (from this character).",
            self.telnet(self.ysmay, "friend Hobb"),
        )
        self.assertTrue(self.carry_allowed())
        self.assertIn(
            "You removed Hobb as a friend (from this character).",
            self.telnet(self.ysmay, "unfriend Hobb"),
        )
        self.assertFalse(self.carry_allowed())
        self.telnet(self.ysmay, "consent whitelist add Hobb to body-handling")
        self.assertTrue(self.carry_allowed())

        # The master switch overrides every list.
        self.assertIn("Social actions are now blocked.", self.telnet(self.ysmay, "consent off"))
        self.assertFalse(self.carry_allowed())
        self.assertIn("Social actions are now allowed.", self.telnet(self.ysmay, "consent on"))
        self.assertTrue(self.carry_allowed())
        self.telnet(self.ysmay, "consent whitelist remove Hobb from body-handling")

        # Under the rivals mode only a mutual, open hostility admits him.
        RelationshipTypeFactory(name="Rival", valence=TypeValence.HOSTILE)
        self.assertIn(
            "Body Handling set to rivals.",
            self.telnet(self.ysmay, "consent category body-handling=rivals"),
        )
        self.assertFalse(self.carry_allowed())
        self.assertIn(
            "Rival declared toward Hobb.",
            self.telnet(self.ysmay, "relationship declare Hobb=Rival,public"),
        )
        self.assertFalse(self.carry_allowed())
        self.assertIn(
            "Rival declared toward Ysmay.",
            self.telnet(self.hobb, "relationship declare Ysmay=Rival,public"),
        )
        self.assertTrue(self.carry_allowed())

        # Back to the category's own default, which for body handling is the whitelist.
        self.assertIn(
            "Body Handling reverted to default",
            self.telnet(self.ysmay, "consent category body-handling=default"),
        )
        self.assertFalse(
            SocialConsentCategoryRule.objects.filter(
                preference__tenure__roster_entry__character_sheet=self.ysmay.sheet_data
            ).exists()
        )
        self.assertFalse(self.carry_allowed())

    def test_the_lists_are_hers_alone_and_only_for_the_living(self) -> None:
        ysmay_tenure = RosterTenure.objects.get(
            roster_entry__character_sheet=self.ysmay.sheet_data, end_date=None
        )
        result = self.web(
            self.hobb,
            "set_social_consent_preference",
            tenure_id=ysmay_tenure.pk,
            allow_social_actions=False,
        )
        self.assertFalse(result.detail.success)
        self.assertEqual(
            result.detail.message, "You can only manage consent for your own characters."
        )
        result = self.web(
            self.ysmay,
            "set_social_consent_preference",
            tenure_id=ysmay_tenure.pk,
            allow_social_actions="maybe",
        )
        self.assertFalse(result.detail.success)
        self.assertEqual(result.detail.message, "allow_social_actions must be a boolean.")
        self.assertIn(
            "That character is not on the list.",
            self.telnet(self.ysmay, "consent whitelist remove Hobb from body-handling"),
        )

        # A character whose player has moved on cannot be listed, and a player who has
        # moved on cannot list anyone.
        hobb_tenure = RosterTenure.objects.get(
            roster_entry__character_sheet=self.hobb.sheet_data, end_date=None
        )
        hobb_tenure.end_date = timezone.now() - timedelta(days=1)
        hobb_tenure.save(update_fields=["end_date"])
        self.assertIn(
            "Hobb has no active character tenure.",
            self.telnet(self.ysmay, "consent whitelist add Hobb to body-handling"),
        )
        result = self.web(
            self.ysmay,
            "add_social_consent_whitelist",
            tenure_id=ysmay_tenure.pk,
            category_key="body-handling",
            allowed_tenure_id=hobb_tenure.pk,
        )
        self.assertFalse(result.detail.success)
        self.assertEqual(result.detail.message, "That character is not currently active.")
        # Her own tenure ended: the lists are closed to her (the master switch alone is
        # not, since it changes nothing anyone else can act on).
        hobb_tenure.end_date = None
        hobb_tenure.save(update_fields=["end_date"])
        ysmay_tenure.end_date = timezone.now() - timedelta(days=1)
        ysmay_tenure.save(update_fields=["end_date"])
        result = self.web(
            self.ysmay,
            "add_social_consent_whitelist",
            tenure_id=ysmay_tenure.pk,
            category_key="body-handling",
            allowed_tenure_id=hobb_tenure.pk,
        )
        self.assertFalse(result.detail.success)
        self.assertEqual(result.detail.message, "Your character is not currently active.")
