"""Reputation "at most" and association leaves (#4361).

Every row is seeded here; names are placeholders.
"""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from evennia_extensions.factories import CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.missions.constants import MissionStatus
from world.missions.factories import MissionInstanceFactory
from world.npc_services.factories import NPCRoleFactory, NPCServiceOfferFactory
from world.predicates.catalog import leaf_catalog
from world.predicates.describe import describe_leaf, explain_leaf_for_staff
from world.predicates.predicates import CharacterPredicateContext, evaluate
from world.predicates.validation import validate_predicate_tree
from world.roster.factories import FamilyFactory
from world.scenes.factories import PersonaFactory
from world.societies.factories import (
    OrganizationFactory,
    OrganizationMembershipFactory,
    OrganizationReputationFactory,
    OrganizationTypeFactory,
    SocietyFactory,
    SocietyReputationFactory,
)
from world.societies.models import AssociationConfig

HONORED = 600
DESPISED = -600


def _leaf(name: str, **params: object) -> dict:
    return {"leaf": name, "params": params}


class _Base(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.society = SocietyFactory(name="PLACEHOLDER Quay Folk")
        cls.org = OrganizationFactory(name="PLACEHOLDER Company", society=cls.society)
        cls.sheet = CharacterSheetFactory(character=CharacterFactory())
        cls.persona = cls.sheet.primary_persona

    def _ctx(self, persona: object = None) -> CharacterPredicateContext:
        return CharacterPredicateContext(
            self.sheet.character, presented_persona=persona or self.persona
        )

    def _true(self, rule: dict, persona: object = None) -> bool:
        return evaluate(rule, self._ctx(persona))


class MaxReputationTests(_Base):
    def test_at_most_matches_low_tiers_only(self) -> None:
        OrganizationReputationFactory(persona=self.persona, organization=self.org, value=DESPISED)
        self.assertTrue(self._true(_leaf("max_org_reputation", org=self.org.name, tier="disliked")))
        self.assertFalse(self._true(_leaf("max_org_reputation", org=self.org.name, tier="reviled")))

    def test_no_row_never_matches(self) -> None:
        self.assertFalse(self._true(_leaf("max_org_reputation", org=self.org.name, tier="revered")))
        self.assertFalse(
            self._true(_leaf("max_society_standing", society=self.society.name, tier="revered"))
        )

    def test_society_at_most(self) -> None:
        SocietyReputationFactory(persona=self.persona, society=self.society, value=HONORED)
        rule = _leaf("max_society_standing", society=self.society.name, tier="honored")
        self.assertTrue(self._true(rule))
        rule = _leaf("max_society_standing", society=self.society.name, tier="liked")
        self.assertFalse(self._true(rule))

    def test_an_unknown_tier_is_an_authoring_error(self) -> None:
        errors = validate_predicate_tree(_leaf("max_org_reputation", org="x", tier="beloved"))
        self.assertTrue(errors)

    def test_catalog_offers_the_tiers_as_choices(self) -> None:
        params = {leaf["name"]: leaf["params"] for leaf in leaf_catalog()}
        tier = next(p for p in params["max_org_reputation"] if p["name"] == "tier")
        self.assertIn("despised", tier["choices"])


class AssociationTests(_Base):
    def _associated(self, persona: object = None) -> bool:
        return self._true(_leaf("associated_with_org", org=self.org.name), persona)

    def test_a_current_member_is_associated(self) -> None:
        OrganizationMembershipFactory(persona=self.persona, organization=self.org)
        self.assertTrue(self._associated())
        self.assertTrue(self._true(_leaf("associated_with_society", society=self.society.name)))

    def test_a_stranger_is_not(self) -> None:
        self.assertFalse(self._associated())

    def test_a_former_member_counts_for_the_configured_years(self) -> None:
        membership = OrganizationMembershipFactory(persona=self.persona, organization=self.org)
        membership.left_at = timezone.now() - timedelta(days=200)
        membership.save(update_fields=["left_at"])
        self.assertTrue(self._associated())
        membership.left_at = timezone.now() - timedelta(days=365 * 3)
        membership.save(update_fields=["left_at"])
        self.assertFalse(self._associated())

    def test_an_exile_always_counts(self) -> None:
        membership = OrganizationMembershipFactory(persona=self.persona, organization=self.org)
        long_ago = timezone.now() - timedelta(days=365 * 10)
        membership.left_at = long_ago
        membership.exiled_at = long_ago
        membership.save(update_fields=["left_at", "exiled_at"])
        self.assertTrue(self._associated())

    def test_membership_of_an_organization_below_counts_for_the_one_above(self) -> None:
        child = OrganizationFactory(parent_org=self.org, society=self.society)
        OrganizationMembershipFactory(persona=self.persona, organization=child)
        self.assertTrue(self._associated())

    def test_a_covert_organization_never_counts(self) -> None:
        covert = OrganizationFactory(org_type=OrganizationTypeFactory(is_covert=True))
        OrganizationMembershipFactory(persona=self.persona, organization=covert)
        self.assertFalse(self._true(_leaf("associated_with_org", org=covert.name)))

    def test_an_alternate_persona_does_not_carry_the_main_persona_ties(self) -> None:
        OrganizationMembershipFactory(persona=self.persona, organization=self.org)
        alt = PersonaFactory(character_sheet=self.sheet)
        self.assertFalse(self._associated(alt))

    def test_kin_count_only_under_the_primary_persona(self) -> None:
        family = FamilyFactory()
        house = OrganizationFactory(family=family, society=self.society)
        self.sheet.family = family
        self.sheet.true_profile.save()
        self.assertTrue(self._true(_leaf("associated_with_org", org=house.name)))
        alt = PersonaFactory(character_sheet=self.sheet)
        self.assertFalse(self._true(_leaf("associated_with_org", org=house.name), alt))

    def test_steady_work_for_the_organizations_people(self) -> None:
        config = AssociationConfig.load()
        role = NPCRoleFactory(faction_affiliation=self.org)
        offer = NPCServiceOfferFactory(role=role)
        for _ in range(config.work_missions - 1):
            MissionInstanceFactory(
                source_offer=offer,
                accepted_as_persona=self.persona,
                status=MissionStatus.COMPLETE,
                completed_at=timezone.now() - timedelta(days=5),
            )
        self.assertFalse(self._associated())
        MissionInstanceFactory(
            source_offer=offer,
            accepted_as_persona=self.persona,
            status=MissionStatus.COMPLETE,
            completed_at=timezone.now() - timedelta(days=5),
        )
        self.assertTrue(self._associated())


class StaffReasonTests(_Base):
    def test_the_reason_names_the_hidden_tier_for_staff(self) -> None:
        OrganizationReputationFactory(persona=self.persona, organization=self.org, value=HONORED)
        leaf = _leaf("min_org_reputation", org=self.org.name, tier="liked")
        reason = explain_leaf_for_staff(leaf, self.persona)
        self.assertIn("high regard", reason)
        self.assertIn("Honored", reason)

    def test_the_reason_names_the_recent_causes_for_staff(self) -> None:
        from world.secrets.factories import SecretFactory
        from world.societies.constants import OrganizationReputationCause
        from world.societies.renown import bump_organization_reputation

        secret = SecretFactory()
        bump_organization_reputation(
            self.persona,
            self.org,
            -150,
            cause=OrganizationReputationCause.SECRET_EXPOSED,
            secret=secret,
        )
        bump_organization_reputation(
            self.persona, self.org, 50, cause=OrganizationReputationCause.GANG_TURF
        )
        leaf = _leaf("max_org_reputation", org=self.org.name, tier="disliked")
        tier_line, newest, earlier = explain_leaf_for_staff(leaf, self.persona).split("\n")
        self.assertIn("Disfavored", tier_line)
        self.assertEqual(newest, "Moved by: gang turf, Disfavored to Disfavored")
        self.assertEqual(
            earlier,
            f"Earlier: secret exposed (secret #{secret.pk}, level 1: "
            f"{' '.join(secret.content.split())[:60]}), Unknown to Disfavored",
        )

    def test_the_reason_names_the_association(self) -> None:
        membership = OrganizationMembershipFactory(persona=self.persona, organization=self.org)
        membership.left_at = timezone.now() - timedelta(days=30)
        membership.save(update_fields=["left_at"])
        reason = explain_leaf_for_staff(
            _leaf("associated_with_org", org=self.org.name), self.persona
        )
        self.assertEqual(reason, f"association: formerly a member of {self.org.name}")

    def test_players_get_no_reason_for_the_new_leaves(self) -> None:
        for leaf in (
            _leaf("associated_with_org", org=self.org.name),
            _leaf("max_org_reputation", org=self.org.name, tier="disliked"),
        ):
            self.assertIsNone(describe_leaf(leaf))
