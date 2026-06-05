"""Phase C tests for the Renown system (#676).

Covers org-accumulated inflow + persona outflow:

* ``apply_org_inflow_for_persona_deed`` — flat 10% from a member's deed
  into each of that persona's org memberships' accumulated values, with
  covenant orgs also receiving legend inflow.
* ``recompute_persona_prestige_from_orgs`` — rank-weighted readout of
  every membership's org standing into the persona's prestige_from_orgs
  (and total_prestige denorm).
* ``apply_body_covenant_legend_inflow`` — body-flow covenant legend for
  TEMPORARY personas, walking to the body's PRIMARY persona's covenant
  memberships and applying rank-weighted legend.
* Loop-safety — outflow never feeds back into the org.
* Cron decay integration — after org accumulated values drop, every
  member's prestige_from_orgs is recomputed.
"""

from __future__ import annotations

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.covenants.factories import CovenantFactory
from world.scenes.constants import PersonaType
from world.scenes.factories import PersonaFactory
from world.societies.constants import (
    MAGNITUDE_FAME_AWARDS,
    MAGNITUDE_PRESTIGE_AWARDS,
    ORG_INFLOW_FRACTION,
    RANK_OUTFLOW_MULTIPLIERS,
    RISK_LEGEND_AWARDS,
    RenownMagnitude,
    RenownRisk,
)
from world.societies.factories import OrganizationFactory, OrganizationMembershipFactory
from world.societies.renown import (
    apply_body_covenant_legend_inflow,
    apply_org_inflow_for_persona_deed,
    decay_all_org_accumulated,
    fire_renown_award,
    recompute_persona_prestige_from_orgs,
)


def _make_primary_persona():
    character = CharacterFactory()
    sheet = CharacterSheetFactory(character=character)
    return sheet.primary_persona


def _make_temporary_persona(character_sheet):
    return PersonaFactory(
        character_sheet=character_sheet,
        persona_type=PersonaType.TEMPORARY,
    )


class OrgInflowTests(TestCase):
    """A persona's deed flows flat 10% into each membership's org accumulated."""

    def test_no_memberships_no_inflow(self) -> None:
        persona = _make_primary_persona()
        touched = apply_org_inflow_for_persona_deed(
            persona, prestige_delta=100, fame_delta=1000, legend_delta=50
        )
        self.assertEqual(touched, ())

    def test_single_membership_flat_inflow(self) -> None:
        persona = _make_primary_persona()
        org = OrganizationFactory()
        OrganizationMembershipFactory(persona=persona, organization=org, rank=3)
        touched = apply_org_inflow_for_persona_deed(
            persona, prestige_delta=300, fame_delta=1500, legend_delta=200
        )
        self.assertEqual(touched, (org.pk,))
        org.refresh_from_db()
        # 10% flat: 30 prestige, 150 fame. No legend — non-covenant org.
        self.assertEqual(org.accumulated_prestige, int(300 * ORG_INFLOW_FRACTION))
        self.assertEqual(org.accumulated_fame, int(1500 * ORG_INFLOW_FRACTION))
        self.assertEqual(org.accumulated_legend, 0)

    def test_inflow_is_rank_independent(self) -> None:
        """Flat 10% — rank does not affect inflow size."""
        persona_high = _make_primary_persona()
        persona_low = _make_primary_persona()
        org_high = OrganizationFactory()
        org_low = OrganizationFactory()
        OrganizationMembershipFactory(persona=persona_high, organization=org_high, rank=1)
        OrganizationMembershipFactory(persona=persona_low, organization=org_low, rank=5)
        apply_org_inflow_for_persona_deed(
            persona_high, prestige_delta=1000, fame_delta=0, legend_delta=0
        )
        apply_org_inflow_for_persona_deed(
            persona_low, prestige_delta=1000, fame_delta=0, legend_delta=0
        )
        org_high.refresh_from_db()
        org_low.refresh_from_db()
        self.assertEqual(org_high.accumulated_prestige, org_low.accumulated_prestige)

    def test_multiple_memberships_each_receive_inflow(self) -> None:
        persona = _make_primary_persona()
        org_a = OrganizationFactory(name="Org A")
        org_b = OrganizationFactory(name="Org B")
        OrganizationMembershipFactory(persona=persona, organization=org_a, rank=2)
        OrganizationMembershipFactory(persona=persona, organization=org_b, rank=4)
        touched = apply_org_inflow_for_persona_deed(
            persona, prestige_delta=500, fame_delta=0, legend_delta=0
        )
        self.assertEqual(set(touched), {org_a.pk, org_b.pk})
        org_a.refresh_from_db()
        org_b.refresh_from_db()
        self.assertEqual(org_a.accumulated_prestige, 50)
        self.assertEqual(org_b.accumulated_prestige, 50)

    def test_covenant_membership_receives_legend(self) -> None:
        persona = _make_primary_persona()
        covenant = CovenantFactory()
        OrganizationMembershipFactory(persona=persona, organization=covenant.organization, rank=2)
        apply_org_inflow_for_persona_deed(
            persona, prestige_delta=100, fame_delta=200, legend_delta=1000
        )
        covenant.organization.refresh_from_db()
        # Covenant gets all three: 10 prestige, 20 fame, 100 legend.
        self.assertEqual(covenant.organization.accumulated_prestige, 10)
        self.assertEqual(covenant.organization.accumulated_fame, 20)
        self.assertEqual(covenant.organization.accumulated_legend, 100)

    def test_non_covenant_org_ignores_legend_delta(self) -> None:
        persona = _make_primary_persona()
        org = OrganizationFactory()
        OrganizationMembershipFactory(persona=persona, organization=org, rank=3)
        apply_org_inflow_for_persona_deed(
            persona, prestige_delta=0, fame_delta=0, legend_delta=10000
        )
        org.refresh_from_db()
        self.assertEqual(org.accumulated_legend, 0)

    def test_temporary_persona_no_direct_inflow(self) -> None:
        primary = _make_primary_persona()
        temp = _make_temporary_persona(primary.character_sheet)
        org = OrganizationFactory()
        OrganizationMembershipFactory(persona=primary, organization=org, rank=2)
        touched = apply_org_inflow_for_persona_deed(
            temp, prestige_delta=1000, fame_delta=1000, legend_delta=0
        )
        self.assertEqual(touched, ())
        org.refresh_from_db()
        self.assertEqual(org.accumulated_prestige, 0)
        self.assertEqual(org.accumulated_fame, 0)


class PersonaOutflowTests(TestCase):
    """``prestige_from_orgs`` = rank-weighted sum of each org's standing."""

    def test_no_memberships_outflow_zero(self) -> None:
        persona = _make_primary_persona()
        result = recompute_persona_prestige_from_orgs(persona)
        self.assertEqual(result, 0)
        persona.refresh_from_db()
        self.assertEqual(persona.prestige_from_orgs, 0)

    def test_outflow_rank_weighted(self) -> None:
        """Same org, higher rank = larger outflow share."""
        leader = _make_primary_persona()
        aspirant = _make_primary_persona()
        org = OrganizationFactory(base_prestige=1000)
        OrganizationMembershipFactory(persona=leader, organization=org, rank=1)
        OrganizationMembershipFactory(persona=aspirant, organization=org, rank=5)

        recompute_persona_prestige_from_orgs(leader)
        recompute_persona_prestige_from_orgs(aspirant)
        leader.refresh_from_db()
        aspirant.refresh_from_db()

        self.assertEqual(leader.prestige_from_orgs, int(1000 * RANK_OUTFLOW_MULTIPLIERS[1]))
        self.assertEqual(aspirant.prestige_from_orgs, int(1000 * RANK_OUTFLOW_MULTIPLIERS[5]))
        self.assertGreater(leader.prestige_from_orgs, aspirant.prestige_from_orgs)

    def test_outflow_sums_base_and_accumulated(self) -> None:
        persona = _make_primary_persona()
        org = OrganizationFactory(base_prestige=100, accumulated_prestige=50, accumulated_fame=200)
        OrganizationMembershipFactory(persona=persona, organization=org, rank=2)
        recompute_persona_prestige_from_orgs(persona)
        persona.refresh_from_db()
        # rank 2 multiplier × (100 + 50 + 200)
        self.assertEqual(persona.prestige_from_orgs, int(350 * RANK_OUTFLOW_MULTIPLIERS[2]))

    def test_outflow_sums_across_memberships(self) -> None:
        persona = _make_primary_persona()
        org_a = OrganizationFactory(name="A", base_prestige=200)
        org_b = OrganizationFactory(name="B", base_prestige=500)
        OrganizationMembershipFactory(persona=persona, organization=org_a, rank=1)
        OrganizationMembershipFactory(persona=persona, organization=org_b, rank=3)
        recompute_persona_prestige_from_orgs(persona)
        persona.refresh_from_db()
        expected = int(200 * RANK_OUTFLOW_MULTIPLIERS[1]) + int(500 * RANK_OUTFLOW_MULTIPLIERS[3])
        self.assertEqual(persona.prestige_from_orgs, expected)

    def test_outflow_updates_total_prestige(self) -> None:
        persona = _make_primary_persona()
        persona.prestige_from_deeds = 50
        persona.prestige_from_dwellings = 25
        persona.save(update_fields=["prestige_from_deeds", "prestige_from_dwellings"])
        org = OrganizationFactory(base_prestige=1000)
        OrganizationMembershipFactory(persona=persona, organization=org, rank=2)
        recompute_persona_prestige_from_orgs(persona)
        persona.refresh_from_db()
        self.assertEqual(
            persona.total_prestige,
            persona.prestige_from_dwellings
            + persona.prestige_from_items
            + persona.prestige_from_orgs
            + persona.prestige_from_deeds,
        )

    def test_temporary_persona_outflow_zero(self) -> None:
        """TEMPORARY personas can't hold memberships, so their outflow stays 0."""
        primary = _make_primary_persona()
        temp = _make_temporary_persona(primary.character_sheet)
        result = recompute_persona_prestige_from_orgs(temp)
        self.assertEqual(result, 0)


class BodyCovenantLegendInflowTests(TestCase):
    """TEMPORARY persona's deed routes legend into the body's primary's covenant memberships."""

    def test_no_primary_no_inflow(self) -> None:
        """Sheet with only a TEMPORARY persona (no PRIMARY) — body-flow no-ops."""
        character = CharacterFactory()
        sheet = CharacterSheetFactory(character=character)
        # Delete the auto-created primary so only a temporary exists.
        sheet.primary_persona.delete()
        temp = _make_temporary_persona(sheet)
        touched = apply_body_covenant_legend_inflow(temp, legend_delta=500)
        self.assertEqual(touched, ())

    def test_no_covenant_memberships_no_inflow(self) -> None:
        primary = _make_primary_persona()
        org = OrganizationFactory()  # not a covenant
        OrganizationMembershipFactory(persona=primary, organization=org, rank=2)
        temp = _make_temporary_persona(primary.character_sheet)
        touched = apply_body_covenant_legend_inflow(temp, legend_delta=500)
        self.assertEqual(touched, ())
        org.refresh_from_db()
        self.assertEqual(org.accumulated_legend, 0)

    def test_covenant_membership_receives_rank_weighted_legend(self) -> None:
        primary = _make_primary_persona()
        covenant = CovenantFactory()
        OrganizationMembershipFactory(persona=primary, organization=covenant.organization, rank=1)
        temp = _make_temporary_persona(primary.character_sheet)

        touched = apply_body_covenant_legend_inflow(temp, legend_delta=1000)
        self.assertEqual(touched, (covenant.organization.pk,))
        covenant.organization.refresh_from_db()
        # 10% × rank_1 multiplier (1.0) × 1000 = 100
        expected = int(1000 * ORG_INFLOW_FRACTION * RANK_OUTFLOW_MULTIPLIERS[1])
        self.assertEqual(covenant.organization.accumulated_legend, expected)

    def test_low_rank_primary_yields_smaller_inflow(self) -> None:
        primary = _make_primary_persona()
        covenant = CovenantFactory()
        OrganizationMembershipFactory(persona=primary, organization=covenant.organization, rank=5)
        temp = _make_temporary_persona(primary.character_sheet)
        apply_body_covenant_legend_inflow(temp, legend_delta=10000)
        covenant.organization.refresh_from_db()
        expected = int(10000 * ORG_INFLOW_FRACTION * RANK_OUTFLOW_MULTIPLIERS[5])
        self.assertEqual(covenant.organization.accumulated_legend, expected)


class FireRenownAwardOrgWiringTests(TestCase):
    """``fire_renown_award`` triggers inflow + outflow recompute end-to-end."""

    def test_primary_deed_inflows_and_recomputes_outflow(self) -> None:
        persona = _make_primary_persona()
        org = OrganizationFactory(base_prestige=0)
        OrganizationMembershipFactory(persona=persona, organization=org, rank=2)
        result = fire_renown_award(
            persona=persona,
            magnitude=RenownMagnitude.HIGH,
            risk=RenownRisk.MODERATE,
        )
        self.assertIn(org.pk, result.org_inflow_org_ids)
        org.refresh_from_db()
        persona.refresh_from_db()
        # Inflow landed.
        self.assertEqual(
            org.accumulated_prestige,
            int(MAGNITUDE_PRESTIGE_AWARDS["high"] * ORG_INFLOW_FRACTION),
        )
        self.assertEqual(
            org.accumulated_fame,
            int(MAGNITUDE_FAME_AWARDS["high"] * ORG_INFLOW_FRACTION),
        )
        # Outflow recomputed: standing × rank_2.
        expected_outflow = int(
            (org.accumulated_prestige + org.accumulated_fame) * RANK_OUTFLOW_MULTIPLIERS[2]
        )
        self.assertEqual(persona.prestige_from_orgs, expected_outflow)

    def test_covenant_membership_gets_legend_inflow(self) -> None:
        persona = _make_primary_persona()
        covenant = CovenantFactory()
        OrganizationMembershipFactory(persona=persona, organization=covenant.organization, rank=1)
        fire_renown_award(
            persona=persona,
            magnitude=RenownMagnitude.HIGH,
            risk=RenownRisk.HIGH,
        )
        covenant.organization.refresh_from_db()
        self.assertEqual(
            covenant.organization.accumulated_legend,
            int(RISK_LEGEND_AWARDS["high"] * ORG_INFLOW_FRACTION),
        )

    def test_temporary_persona_routes_legend_to_body_covenant(self) -> None:
        primary = _make_primary_persona()
        covenant = CovenantFactory()
        OrganizationMembershipFactory(persona=primary, organization=covenant.organization, rank=1)
        temp = _make_temporary_persona(primary.character_sheet)
        result = fire_renown_award(
            persona=temp,
            magnitude=RenownMagnitude.MODERATE,
            risk=RenownRisk.HIGH,
        )
        # TEMPORARY persona earns fame + legend on itself, no normal inflow.
        self.assertEqual(result.org_inflow_org_ids, ())
        self.assertIn(covenant.organization.pk, result.covenant_legend_inflow_org_ids)
        covenant.organization.refresh_from_db()
        expected = int(
            RISK_LEGEND_AWARDS["high"] * ORG_INFLOW_FRACTION * RANK_OUTFLOW_MULTIPLIERS[1]
        )
        self.assertEqual(covenant.organization.accumulated_legend, expected)

    def test_temporary_persona_no_org_inflow_for_prestige_or_fame(self) -> None:
        """Body-flow is legend-only — temp's prestige/fame stays on the temp persona."""
        primary = _make_primary_persona()
        covenant = CovenantFactory()
        OrganizationMembershipFactory(persona=primary, organization=covenant.organization, rank=1)
        temp = _make_temporary_persona(primary.character_sheet)
        fire_renown_award(
            persona=temp,
            magnitude=RenownMagnitude.HIGH,
            risk=RenownRisk.NONE,
        )
        covenant.organization.refresh_from_db()
        # No legend (risk none); no prestige/fame body-flow.
        self.assertEqual(covenant.organization.accumulated_prestige, 0)
        self.assertEqual(covenant.organization.accumulated_fame, 0)
        self.assertEqual(covenant.organization.accumulated_legend, 0)

    def test_multiple_members_all_get_outflow_recompute_after_inflow(self) -> None:
        """When a deed adds to an org, every member's outflow updates."""
        actor = _make_primary_persona()
        bystander = _make_primary_persona()
        org = OrganizationFactory(base_prestige=0)
        OrganizationMembershipFactory(persona=actor, organization=org, rank=2)
        OrganizationMembershipFactory(persona=bystander, organization=org, rank=4)

        fire_renown_award(persona=actor, magnitude=RenownMagnitude.HIGH)

        actor.refresh_from_db()
        bystander.refresh_from_db()
        org.refresh_from_db()
        standing = org.accumulated_prestige + org.accumulated_fame
        self.assertEqual(actor.prestige_from_orgs, int(standing * RANK_OUTFLOW_MULTIPLIERS[2]))
        self.assertEqual(bystander.prestige_from_orgs, int(standing * RANK_OUTFLOW_MULTIPLIERS[4]))


class LoopSafetyTests(TestCase):
    """Outflow is a readout — never feeds back into the org."""

    def test_outflow_recompute_does_not_change_org(self) -> None:
        persona = _make_primary_persona()
        org = OrganizationFactory(base_prestige=500, accumulated_prestige=100, accumulated_fame=200)
        OrganizationMembershipFactory(persona=persona, organization=org, rank=1)
        before_prestige = org.accumulated_prestige
        before_fame = org.accumulated_fame
        before_legend = org.accumulated_legend
        recompute_persona_prestige_from_orgs(persona)
        org.refresh_from_db()
        self.assertEqual(org.accumulated_prestige, before_prestige)
        self.assertEqual(org.accumulated_fame, before_fame)
        self.assertEqual(org.accumulated_legend, before_legend)


class CronDecayRecomputesOutflowTests(TestCase):
    """``decay_all_org_accumulated`` recomputes prestige_from_orgs for affected members."""

    def test_decay_drops_outflow(self) -> None:
        persona = _make_primary_persona()
        org = OrganizationFactory(base_prestige=0, accumulated_prestige=10_000, accumulated_fame=0)
        OrganizationMembershipFactory(persona=persona, organization=org, rank=1)
        # Seed the outflow before decay.
        recompute_persona_prestige_from_orgs(persona)
        persona.refresh_from_db()
        before_outflow = persona.prestige_from_orgs
        self.assertGreater(before_outflow, 0)

        decay_all_org_accumulated()

        org.refresh_from_db()
        persona.refresh_from_db()
        # Org accumulated dropped, so persona outflow dropped to match.
        expected = int(
            (org.base_prestige + org.accumulated_prestige + org.accumulated_fame)
            * RANK_OUTFLOW_MULTIPLIERS[1]
        )
        self.assertEqual(persona.prestige_from_orgs, expected)
        self.assertLess(persona.prestige_from_orgs, before_outflow)
