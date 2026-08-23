"""Tests for leader favor/disfavor standing declarations (#3290)."""

from __future__ import annotations

from django.test import TestCase
import pytest

from actions.definitions.standing_declarations import declare_standing_action
from world.consent.constants import ConsentMode
from world.consent.factories import (
    SocialConsentCategoryFactory,
    SocialConsentCategoryRuleFactory,
    SocialConsentPreferenceFactory,
)
from world.roster.factories import RosterEntryFactory, RosterTenureFactory
from world.scenes.constants import PersonaType
from world.scenes.factories import PersonaFactory
from world.societies.constants import (
    STANDING_DECLARATION_DISFAVOR_DELTA,
    STANDING_DECLARATION_FAVOR_DELTA,
    StandingDirection,
)
from world.societies.exceptions import (
    NotAuthorizedToDeclareStandingError,
    StandingConsentBlockedError,
    StandingRateLimitedError,
)
from world.societies.factories import OrganizationFactory, OrganizationMembershipFactory
from world.societies.models import OrganizationReputation, StandingDeclaration
from world.societies.standing_services import declare_standing


class DeclareStandingServiceTests(TestCase):
    """Service-level gates: rank, target validity, consent, rate limit."""

    def setUp(self):
        self.org = OrganizationFactory()
        self.leader = PersonaFactory(persona_type=PersonaType.ESTABLISHED)
        self.member = PersonaFactory(persona_type=PersonaType.ESTABLISHED)
        self.target = PersonaFactory(persona_type=PersonaType.ESTABLISHED)

        OrganizationMembershipFactory(organization=self.org, persona=self.leader, rank=1)
        OrganizationMembershipFactory(organization=self.org, persona=self.member, rank=5)

    def test_favor_declaration_moves_reputation_and_mints_audit_row(self):
        declaration = declare_standing(
            organization=self.org,
            target_persona=self.target,
            declared_by_persona=self.leader,
            direction=StandingDirection.FAVOR,
            citation="For tireless service to the guild.",
        )

        assert declaration.direction == StandingDirection.FAVOR
        assert declaration.delta_applied == STANDING_DECLARATION_FAVOR_DELTA
        assert declaration.citation == "For tireless service to the guild."

        # Existing readers (OrganizationReputation) see the real, clamped move —
        # never a parallel writer, always the shared bump_organization_reputation path.
        reputation = OrganizationReputation.objects.get(persona=self.target, organization=self.org)
        assert reputation.value == STANDING_DECLARATION_FAVOR_DELTA

    def test_disfavor_moves_reputation_negative(self):
        declaration = declare_standing(
            organization=self.org,
            target_persona=self.target,
            declared_by_persona=self.leader,
            direction=StandingDirection.DISFAVOR,
            citation="Marked as an enemy of the guild.",
        )

        assert declaration.delta_applied == STANDING_DECLARATION_DISFAVOR_DELTA
        reputation = OrganizationReputation.objects.get(persona=self.target, organization=self.org)
        assert reputation.value == STANDING_DECLARATION_DISFAVOR_DELTA

    def test_non_privileged_rank_is_refused(self):
        with pytest.raises(NotAuthorizedToDeclareStandingError):
            declare_standing(
                organization=self.org,
                target_persona=self.target,
                declared_by_persona=self.member,
                direction=StandingDirection.FAVOR,
                citation="I declare this myself.",
            )
        assert not OrganizationReputation.objects.filter(
            persona=self.target, organization=self.org
        ).exists()

    def test_non_member_is_refused(self):
        stranger = PersonaFactory(persona_type=PersonaType.ESTABLISHED)
        with pytest.raises(NotAuthorizedToDeclareStandingError):
            declare_standing(
                organization=self.org,
                target_persona=self.target,
                declared_by_persona=stranger,
                direction=StandingDirection.FAVOR,
                citation="Not even a member.",
            )

    def test_second_declaration_same_org_target_same_week_is_rate_limited(self):
        declare_standing(
            organization=self.org,
            target_persona=self.target,
            declared_by_persona=self.leader,
            direction=StandingDirection.FAVOR,
            citation="First declaration.",
        )
        with pytest.raises(StandingRateLimitedError):
            declare_standing(
                organization=self.org,
                target_persona=self.target,
                declared_by_persona=self.leader,
                direction=StandingDirection.FAVOR,
                citation="Second declaration, same week.",
            )
        assert (
            StandingDeclaration.objects.filter(
                organization=self.org, target_persona=self.target
            ).count()
            == 1
        )


class DeclareStandingConsentTests(TestCase):
    """DISFAVOR routes through the #2170 antagonism-consent seam (the ``hostile`` category)."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.hostile = SocialConsentCategoryFactory(key="hostile", default_mode=ConsentMode.EVERYONE)

    def setUp(self):
        self.org = OrganizationFactory()
        self.leader_tenure = RosterTenureFactory()
        self.leader = PersonaFactory(
            character_sheet=self.leader_tenure.roster_entry.character_sheet,
            persona_type=PersonaType.ESTABLISHED,
        )
        self.target_tenure = RosterTenureFactory()
        self.target = PersonaFactory(
            character_sheet=self.target_tenure.roster_entry.character_sheet,
            persona_type=PersonaType.ESTABLISHED,
        )
        OrganizationMembershipFactory(organization=self.org, persona=self.leader, rank=1)

    def test_disfavor_open_hostile_category_permits(self):
        # hostile defaults EVERYONE here -> a leader with no relationship may disfavor.
        declaration = declare_standing(
            organization=self.org,
            target_persona=self.target,
            declared_by_persona=self.leader,
            direction=StandingDirection.DISFAVOR,
            citation="Open season.",
        )
        assert declaration.direction == StandingDirection.DISFAVOR

    def test_disfavor_without_consent_is_refused(self):
        pref = SocialConsentPreferenceFactory(tenure=self.target_tenure)
        SocialConsentCategoryRuleFactory(
            preference=pref, category=self.hostile, mode=ConsentMode.ALLOWLIST
        )
        with pytest.raises(StandingConsentBlockedError):
            declare_standing(
                organization=self.org,
                target_persona=self.target,
                declared_by_persona=self.leader,
                direction=StandingDirection.DISFAVOR,
                citation="They never agreed to this.",
            )
        assert not OrganizationReputation.objects.filter(
            persona=self.target, organization=self.org
        ).exists()

    def test_favor_bypasses_the_consent_gate_entirely(self):
        # Favor is pure benefit (#3290 decision 1) — the same lockdown that blocks
        # disfavor never touches favor.
        pref = SocialConsentPreferenceFactory(tenure=self.target_tenure)
        SocialConsentCategoryRuleFactory(
            preference=pref, category=self.hostile, mode=ConsentMode.ALLOWLIST
        )
        declaration = declare_standing(
            organization=self.org,
            target_persona=self.target,
            declared_by_persona=self.leader,
            direction=StandingDirection.FAVOR,
            citation="Honored regardless.",
        )
        assert declaration.direction == StandingDirection.FAVOR


class DeclareStandingActionTests(TestCase):
    """``action.run()`` — the web + telnet convergence seam."""

    def setUp(self):
        self.org = OrganizationFactory()
        self.leader_roster = RosterEntryFactory()
        self.leader_actor = self.leader_roster.character_sheet.character
        self.leader_persona = self.leader_roster.character_sheet.primary_persona

        self.target_roster = RosterEntryFactory()
        self.target_persona = self.target_roster.character_sheet.primary_persona

        OrganizationMembershipFactory(organization=self.org, persona=self.leader_persona, rank=1)

    def test_execute_declares_favor(self):
        result = declare_standing_action.execute(
            self.leader_actor,
            target=self.target_persona,
            organization_id=self.org.pk,
            direction=StandingDirection.FAVOR,
            citation="Recognized before the whole guild.",
        )
        assert result.success is True
        reputation = OrganizationReputation.objects.get(
            persona=self.target_persona, organization=self.org
        )
        assert reputation.value == STANDING_DECLARATION_FAVOR_DELTA

    def test_execute_requires_a_citation(self):
        result = declare_standing_action.execute(
            self.leader_actor,
            target=self.target_persona,
            organization_id=self.org.pk,
            direction=StandingDirection.FAVOR,
            citation="   ",
        )
        assert result.success is False

    def test_execute_surfaces_rank_refusal_message(self):
        member_roster = RosterEntryFactory()
        member_actor = member_roster.character_sheet.character
        member_persona = member_roster.character_sheet.primary_persona
        OrganizationMembershipFactory(organization=self.org, persona=member_persona, rank=5)

        result = declare_standing_action.execute(
            member_actor,
            target=self.target_persona,
            organization_id=self.org.pk,
            direction=StandingDirection.FAVOR,
            citation="I'll declare it myself.",
        )
        assert result.success is False
        assert "not authorized" in result.message.lower()
