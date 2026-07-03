"""Tests for CREATE_POSITION, MOVE_TO_POSITION, GRANT_FLIGHT, and REMOVE_FLIGHT effect handlers.

Built using setUp (not setUpTestData) — Evennia ObjectDB instances (DbHolder)
are not deepcopyable and would break setUpTestData.
"""

from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory
from world.areas.positioning.constants import PositionKind
from world.areas.positioning.models import Position
from world.areas.positioning.services import (
    connect_positions,
    edge_between,
    place_in_position,
    position_of,
)
from world.checks.constants import EffectTarget, EffectType, PositionDestination
from world.checks.factories import ConsequenceEffectFactory, ConsequenceFactory
from world.checks.types import ResolutionContext
from world.mechanics.constants import CapabilitySourceType, ResolutionType
from world.mechanics.effect_handlers import apply_all_effects, apply_effect
from world.mechanics.factories import (
    AerialPropertyFactory,
    ApplicationFactory,
    ChallengeApproachFactory,
    ChallengeInstanceFactory,
    ChallengeTemplateConsequenceFactory,
    ChallengeTemplateFactory,
    PropertyFactory,
)
from world.mechanics.models import ObjectProperty
from world.mechanics.types import CapabilitySource


class CreatePositionHandlerTests(TestCase):
    """Tests for the CREATE_POSITION effect handler."""

    def setUp(self) -> None:
        from evennia import create_object

        self.room = create_object("typeclasses.rooms.Room", key="CPHandlerRoom", nohome=True)
        self.char = CharacterFactory(location=self.room)
        self.start = Position.objects.create(room=self.room, name="start")
        place_in_position(self.char, self.start)
        self.consequence = ConsequenceFactory()

    def test_create_position_carves_and_connects(self) -> None:
        """CREATE_POSITION creates a new named position and connects it to the actor's position."""
        effect = ConsequenceEffectFactory(
            consequence=self.consequence,
            effect_type=EffectType.CREATE_POSITION,
            position_name="floating platform",
            position_connect_from_actor=True,
            position_place_occupant=False,
        )
        result = apply_effect(effect, ResolutionContext(character=self.char))
        self.assertTrue(result.applied)
        new = Position.objects.get(room=self.room, name="floating platform")
        self.assertIsNotNone(edge_between(position_of(self.char), new))

    def test_create_position_places_occupant(self) -> None:
        """CREATE_POSITION with position_place_occupant=True moves SELF into the new position."""
        effect = ConsequenceEffectFactory(
            consequence=self.consequence,
            effect_type=EffectType.CREATE_POSITION,
            position_name="cloud",
            position_place_occupant=True,
            position_connect_from_actor=False,
            target=EffectTarget.SELF,
        )
        apply_effect(effect, ResolutionContext(character=self.char))
        self.assertEqual(position_of(self.char).name, "cloud")

    def test_create_position_returns_created_instance(self) -> None:
        """CREATE_POSITION result carries the new Position as created_instance."""
        effect = ConsequenceEffectFactory(
            consequence=self.consequence,
            effect_type=EffectType.CREATE_POSITION,
            position_name="rampart",
            position_connect_from_actor=False,
            position_place_occupant=False,
        )
        result = apply_effect(effect, ResolutionContext(character=self.char))
        self.assertIsInstance(result.created_instance, Position)
        self.assertEqual(result.created_instance.name, "rampart")

    def test_create_position_no_connect_when_flag_false(self) -> None:
        """CREATE_POSITION with position_connect_from_actor=False does not create an edge."""
        effect = ConsequenceEffectFactory(
            consequence=self.consequence,
            effect_type=EffectType.CREATE_POSITION,
            position_name="island",
            position_connect_from_actor=False,
            position_place_occupant=False,
        )
        apply_effect(effect, ResolutionContext(character=self.char))
        new = Position.objects.get(room=self.room, name="island")
        self.assertIsNone(edge_between(self.start, new))


class MoveToPositionHandlerTests(TestCase):
    """Tests for the MOVE_TO_POSITION effect handler."""

    def setUp(self) -> None:
        from evennia import create_object

        self.room = create_object("typeclasses.rooms.Room", key="MTHandlerRoom", nohome=True)
        self.char = CharacterFactory(location=self.room)
        self.other = CharacterFactory(location=self.room)
        self.actor_pos = Position.objects.create(room=self.room, name="actor_spot")
        self.other_pos = Position.objects.create(room=self.room, name="other_spot")
        self.balcony = Position.objects.create(room=self.room, name="balcony")
        place_in_position(self.char, self.actor_pos)
        place_in_position(self.other, self.other_pos)
        self.consequence = ConsequenceFactory()

    def test_move_actor_position_pull(self) -> None:
        """MOVE_TO_POSITION with ACTOR_POSITION pulls TARGET to the actor's position."""
        effect = ConsequenceEffectFactory(
            consequence=self.consequence,
            effect_type=EffectType.MOVE_TO_POSITION,
            position_destination=PositionDestination.ACTOR_POSITION,
            target=EffectTarget.TARGET,
        )
        apply_effect(effect, ResolutionContext(character=self.char, target=self.other))
        self.assertEqual(position_of(self.other).pk, position_of(self.char).pk)

    def test_move_named(self) -> None:
        """MOVE_TO_POSITION with NAMED moves SELF to the named position."""
        effect = ConsequenceEffectFactory(
            consequence=self.consequence,
            effect_type=EffectType.MOVE_TO_POSITION,
            position_destination=PositionDestination.NAMED,
            position_name="balcony",
            target=EffectTarget.SELF,
        )
        apply_effect(effect, ResolutionContext(character=self.char))
        self.assertEqual(position_of(self.char).name, "balcony")

    def test_move_unresolvable_destination_returns_unapplied(self) -> None:
        """MOVE_TO_POSITION with a NAMED position that does not exist returns applied=False."""
        effect = ConsequenceEffectFactory(
            consequence=self.consequence,
            effect_type=EffectType.MOVE_TO_POSITION,
            position_destination=PositionDestination.NAMED,
            position_name="nonexistent_position",
            target=EffectTarget.SELF,
        )
        result = apply_effect(effect, ResolutionContext(character=self.char))
        self.assertFalse(result.applied)
        self.assertIsNotNone(result.skip_reason)


class AwayFromActorHandlerTests(TestCase):
    """Tests for MOVE_TO_POSITION / AWAY_FROM_ACTOR (knockback, #1317)."""

    def setUp(self) -> None:
        from evennia import create_object

        self.room = create_object("typeclasses.rooms.Room", key="KnockbackRoom", nohome=True)
        self.attacker = CharacterFactory(location=self.room)
        self.defender = CharacterFactory(location=self.room)
        self.attacker_pos = Position.objects.create(room=self.room, name="attacker_spot")
        self.defender_pos = Position.objects.create(room=self.room, name="defender_spot")
        self.far_pos = Position.objects.create(room=self.room, name="far_spot")
        place_in_position(self.attacker, self.attacker_pos)
        place_in_position(self.defender, self.defender_pos)
        # attacker_spot <-> defender_spot <-> far_spot (a line); far_spot is NOT
        # adjacent to attacker_spot, so it's the correct "away" destination.
        connect_positions(self.attacker_pos, self.defender_pos)
        connect_positions(self.defender_pos, self.far_pos)
        self.consequence = ConsequenceFactory()

    def test_knockback_moves_defender_away_from_attacker(self) -> None:
        """AWAY_FROM_ACTOR shoves the TARGET to the neighbor farthest from the actor."""
        effect = ConsequenceEffectFactory(
            consequence=self.consequence,
            effect_type=EffectType.MOVE_TO_POSITION,
            position_destination=PositionDestination.AWAY_FROM_ACTOR,
            target=EffectTarget.TARGET,
        )
        apply_effect(effect, ResolutionContext(character=self.attacker, target=self.defender))
        self.assertEqual(position_of(self.defender).pk, self.far_pos.pk)

    def test_knockback_noop_when_defender_has_no_neighbor(self) -> None:
        """No valid destination -> applied=False, defender stays put."""
        isolated = Position.objects.create(room=self.room, name="isolated_spot")
        place_in_position(self.defender, isolated)
        effect = ConsequenceEffectFactory(
            consequence=self.consequence,
            effect_type=EffectType.MOVE_TO_POSITION,
            position_destination=PositionDestination.AWAY_FROM_ACTOR,
            target=EffectTarget.TARGET,
        )
        result = apply_effect(
            effect, ResolutionContext(character=self.attacker, target=self.defender)
        )
        self.assertFalse(result.applied)
        self.assertEqual(position_of(self.defender).pk, isolated.pk)

    def test_knockback_noop_when_attacker_has_no_position(self) -> None:
        """Attacker not placed in any Position -> can't compute 'away', no-op."""
        no_pos_attacker = CharacterFactory(location=self.room)
        effect = ConsequenceEffectFactory(
            consequence=self.consequence,
            effect_type=EffectType.MOVE_TO_POSITION,
            position_destination=PositionDestination.AWAY_FROM_ACTOR,
            target=EffectTarget.TARGET,
        )
        result = apply_effect(
            effect, ResolutionContext(character=no_pos_attacker, target=self.defender)
        )
        self.assertFalse(result.applied)

    def test_knockback_noop_when_defender_resists(self) -> None:
        """A defender with the sure_footed Capability (#1793) is not moved."""
        with patch.object(self.defender, "has_capability", return_value=True):
            effect = ConsequenceEffectFactory(
                consequence=self.consequence,
                effect_type=EffectType.MOVE_TO_POSITION,
                position_destination=PositionDestination.AWAY_FROM_ACTOR,
                target=EffectTarget.TARGET,
            )
            result = apply_effect(
                effect, ResolutionContext(character=self.attacker, target=self.defender)
            )
        self.assertFalse(result.applied)
        self.assertEqual(position_of(self.defender).pk, self.defender_pos.pk)

    def test_knockback_noop_when_only_neighbor_is_attacker_position(self) -> None:
        """Defender's only open neighbor is the attacker's own position.

        ``away`` (which already excludes actor_pos) is empty here, so the
        handler falls back to ``neighbors`` -- which must ALSO exclude the
        attacker's position, otherwise a knockback could shove the defender
        onto the attacker (#1317 finding 3). With no other neighbor, there's
        no valid destination: applied=False, defender stays put.
        """
        # Replace the room's positions with a dead-end pocket: defender_pos is
        # connected ONLY to attacker_pos (no far_pos edge).
        dead_end_defender = Position.objects.create(room=self.room, name="dead_end_defender")
        place_in_position(self.defender, dead_end_defender)
        connect_positions(self.attacker_pos, dead_end_defender)

        effect = ConsequenceEffectFactory(
            consequence=self.consequence,
            effect_type=EffectType.MOVE_TO_POSITION,
            position_destination=PositionDestination.AWAY_FROM_ACTOR,
            target=EffectTarget.TARGET,
        )
        result = apply_effect(
            effect, ResolutionContext(character=self.attacker, target=self.defender)
        )
        self.assertFalse(result.applied)
        self.assertEqual(position_of(self.defender).pk, dead_end_defender.pk)

    def test_knockback_two_effects_chain_two_hops(self) -> None:
        """Two AWAY_FROM_ACTOR rows on one Consequence chain into a 2-hop shove.

        Each row resolves fresh, so the second row computes 'away from actor'
        using the defender's position AFTER the first row already moved them.
        """
        beyond_pos = Position.objects.create(room=self.room, name="beyond_spot")
        connect_positions(self.far_pos, beyond_pos)
        ConsequenceEffectFactory(
            consequence=self.consequence,
            effect_type=EffectType.MOVE_TO_POSITION,
            position_destination=PositionDestination.AWAY_FROM_ACTOR,
            target=EffectTarget.TARGET,
            execution_order=0,
        )
        ConsequenceEffectFactory(
            consequence=self.consequence,
            effect_type=EffectType.MOVE_TO_POSITION,
            position_destination=PositionDestination.AWAY_FROM_ACTOR,
            target=EffectTarget.TARGET,
            execution_order=1,
        )
        apply_all_effects(
            self.consequence, ResolutionContext(character=self.attacker, target=self.defender)
        )
        self.assertEqual(position_of(self.defender).pk, beyond_pos.pk)


class SeverEdgeHandlerTests(TestCase):
    """Tests for the SEVER_EDGE effect handler."""

    def setUp(self) -> None:
        from evennia import create_object

        from world.areas.positioning.services import connect_positions

        self.room = create_object("typeclasses.rooms.Room", key="SEHandlerRoom", nohome=True)
        self.char = CharacterFactory(location=self.room)
        self.pos_a = Position.objects.create(room=self.room, name="courtyard")
        self.pos_b = Position.objects.create(room=self.room, name="gate")
        connect_positions(self.pos_a, self.pos_b)
        place_in_position(self.char, self.pos_a)
        self.consequence = ConsequenceFactory()

    def test_sever_removes_existing_edge(self) -> None:
        """SEVER_EDGE removes the edge between two named positions."""
        effect = ConsequenceEffectFactory(
            consequence=self.consequence,
            effect_type=EffectType.SEVER_EDGE,
            position_name="courtyard",
            position_name_b="gate",
        )
        result = apply_effect(effect, ResolutionContext(character=self.char))
        self.assertTrue(result.applied)
        self.assertIsNone(edge_between(self.pos_a, self.pos_b))

    def test_sever_skips_when_no_edge(self) -> None:
        """SEVER_EDGE returns applied=False when there is no edge to sever."""
        from world.areas.positioning.services import disconnect_positions

        disconnect_positions(self.pos_a, self.pos_b)
        effect = ConsequenceEffectFactory(
            consequence=self.consequence,
            effect_type=EffectType.SEVER_EDGE,
            position_name="courtyard",
            position_name_b="gate",
        )
        result = apply_effect(effect, ResolutionContext(character=self.char))
        self.assertFalse(result.applied)
        self.assertIsNotNone(result.skip_reason)

    def test_sever_skips_when_endpoint_missing(self) -> None:
        """SEVER_EDGE returns applied=False when a named position does not exist."""
        effect = ConsequenceEffectFactory(
            consequence=self.consequence,
            effect_type=EffectType.SEVER_EDGE,
            position_name="courtyard",
            position_name_b="nonexistent_position",
        )
        result = apply_effect(effect, ResolutionContext(character=self.char))
        self.assertFalse(result.applied)
        self.assertIsNotNone(result.skip_reason)


class ConnectEdgeHandlerTests(TestCase):
    """Tests for the CONNECT_EDGE effect handler."""

    def setUp(self) -> None:
        from evennia import create_object

        self.room = create_object("typeclasses.rooms.Room", key="CEHandlerRoom", nohome=True)
        self.char = CharacterFactory(location=self.room)
        self.pos_a = Position.objects.create(room=self.room, name="tower")
        self.pos_b = Position.objects.create(room=self.room, name="bridge")
        place_in_position(self.char, self.pos_a)
        self.consequence = ConsequenceFactory()

    def test_connect_creates_missing_edge(self) -> None:
        """CONNECT_EDGE creates an edge between two unconnected named positions."""
        effect = ConsequenceEffectFactory(
            consequence=self.consequence,
            effect_type=EffectType.CONNECT_EDGE,
            position_name="tower",
            position_name_b="bridge",
        )
        result = apply_effect(effect, ResolutionContext(character=self.char))
        self.assertTrue(result.applied)
        self.assertIsNotNone(edge_between(self.pos_a, self.pos_b))

    def test_connect_idempotent_already_connected(self) -> None:
        """CONNECT_EDGE returns applied=True even when the edge already exists."""
        from world.areas.positioning.services import connect_positions

        connect_positions(self.pos_a, self.pos_b)
        effect = ConsequenceEffectFactory(
            consequence=self.consequence,
            effect_type=EffectType.CONNECT_EDGE,
            position_name="tower",
            position_name_b="bridge",
        )
        result = apply_effect(effect, ResolutionContext(character=self.char))
        self.assertTrue(result.applied)
        self.assertIsNotNone(edge_between(self.pos_a, self.pos_b))

    def test_connect_skips_when_endpoint_missing(self) -> None:
        """CONNECT_EDGE returns applied=False when a named position does not exist."""
        effect = ConsequenceEffectFactory(
            consequence=self.consequence,
            effect_type=EffectType.CONNECT_EDGE,
            position_name="tower",
            position_name_b="nonexistent_position",
        )
        result = apply_effect(effect, ResolutionContext(character=self.char))
        self.assertFalse(result.applied)
        self.assertIsNotNone(result.skip_reason)


class GrantFlightHandlerTests(TestCase):
    """Tests for the GRANT_FLIGHT effect handler."""

    def setUp(self) -> None:
        from evennia import create_object

        AerialPropertyFactory()
        self.room = create_object("typeclasses.rooms.Room", key="GFHandlerRoom", nohome=True)
        self.char = CharacterFactory(location=self.room)
        self.ground = Position.objects.create(
            room=self.room, name="ground", kind=PositionKind.PRIMARY
        )
        place_in_position(self.char, self.ground)
        self.consequence = ConsequenceFactory()

    def test_grant_flight_moves_to_aerial_position(self) -> None:
        """GRANT_FLIGHT places the character in an AERIAL position."""
        effect = ConsequenceEffectFactory(
            consequence=self.consequence,
            effect_type=EffectType.GRANT_FLIGHT,
            target=EffectTarget.SELF,
        )
        result = apply_effect(effect, ResolutionContext(character=self.char))
        self.assertTrue(result.applied)
        self.assertEqual(position_of(self.char).kind, PositionKind.AERIAL)

    def test_grant_flight_sets_aerial_property(self) -> None:
        """GRANT_FLIGHT sets the 'aerial' ObjectProperty on the character."""
        effect = ConsequenceEffectFactory(
            consequence=self.consequence,
            effect_type=EffectType.GRANT_FLIGHT,
            target=EffectTarget.SELF,
        )
        apply_effect(effect, ResolutionContext(character=self.char))
        self.assertTrue(
            ObjectProperty.objects.filter(object=self.char, property__name="aerial").exists()
        )


class RemoveFlightHandlerTests(TestCase):
    """Tests for the REMOVE_FLIGHT effect handler."""

    def setUp(self) -> None:
        from evennia import create_object

        from world.areas.positioning.services import enter_aerial

        AerialPropertyFactory()
        self.room = create_object("typeclasses.rooms.Room", key="RFHandlerRoom", nohome=True)
        self.char = CharacterFactory(location=self.room)
        self.ground = Position.objects.create(
            room=self.room, name="ground", kind=PositionKind.PRIMARY
        )
        place_in_position(self.char, self.ground)
        enter_aerial(self.char)
        self.consequence = ConsequenceFactory()

    def test_remove_flight_returns_to_ground_position(self) -> None:
        """REMOVE_FLIGHT returns the character to a ground (non-AERIAL) position."""
        effect = ConsequenceEffectFactory(
            consequence=self.consequence,
            effect_type=EffectType.REMOVE_FLIGHT,
            target=EffectTarget.SELF,
        )
        result = apply_effect(effect, ResolutionContext(character=self.char))
        self.assertTrue(result.applied)
        self.assertNotEqual(position_of(self.char).kind, PositionKind.AERIAL)

    def test_remove_flight_clears_aerial_property(self) -> None:
        """REMOVE_FLIGHT removes the 'aerial' ObjectProperty from the character."""
        effect = ConsequenceEffectFactory(
            consequence=self.consequence,
            effect_type=EffectType.REMOVE_FLIGHT,
            target=EffectTarget.SELF,
        )
        apply_effect(effect, ResolutionContext(character=self.char))
        self.assertFalse(
            ObjectProperty.objects.filter(object=self.char, property__name="aerial").exists()
        )


def _make_capability_source(capability_id: int) -> CapabilitySource:
    """Build a minimal CapabilitySource for resolve_challenge calls."""
    return CapabilitySource(
        capability_name="fly",
        capability_id=capability_id,
        value=10,
        source_type=CapabilitySourceType.TECHNIQUE,
        source_name="Test Technique",
        source_id=1,
    )


class GatingFarSideEffectTests(TestCase):
    """Unit test: GATING_FAR_SIDE resolves to the far endpoint of the gating edge.

    Exercises _gating_far_side via apply_effect with PositionDestination.GATING_FAR_SIDE.
    """

    def setUp(self) -> None:
        from evennia import create_object

        self.room = create_object("typeclasses.rooms.Room", key="GFSRoom", nohome=True)
        self.char = CharacterFactory(location=self.room)
        self.courtyard = Position.objects.create(room=self.room, name="courtyard")
        self.balcony = Position.objects.create(room=self.room, name="balcony")
        place_in_position(self.char, self.courtyard)

        # Wire a gating challenge (minimal setup — just need a live ChallengeInstance).
        prop = PropertyFactory(name="gfs_prop")
        ApplicationFactory(target_property=prop)
        template = ChallengeTemplateFactory(name="GFS Gate")
        self.gate = ChallengeInstanceFactory(
            template=template,
            location=self.room,
            target_object=self.room,
        )
        connect_positions(self.courtyard, self.balcony, gating_challenge=self.gate)
        self.consequence = ConsequenceFactory()

    def test_gating_far_side_resolves_opposite_endpoint(self) -> None:
        """MOVE_TO_POSITION/GATING_FAR_SIDE moves the actor to the far side of the gate edge."""
        effect = ConsequenceEffectFactory(
            consequence=self.consequence,
            effect_type=EffectType.MOVE_TO_POSITION,
            position_destination=PositionDestination.GATING_FAR_SIDE,
            target=EffectTarget.SELF,
        )
        ctx = ResolutionContext(character=self.char, challenge_instance=self.gate)
        result = apply_effect(effect, ctx)
        self.assertTrue(result.applied)
        self.assertEqual(position_of(self.char).pk, self.balcony.pk)

    def test_gating_far_side_no_challenge_instance_skips(self) -> None:
        """GATING_FAR_SIDE with no challenge_instance on context returns applied=False."""
        effect = ConsequenceEffectFactory(
            consequence=self.consequence,
            effect_type=EffectType.MOVE_TO_POSITION,
            position_destination=PositionDestination.GATING_FAR_SIDE,
            target=EffectTarget.SELF,
        )
        ctx = ResolutionContext(character=self.char)  # no challenge_instance
        result = apply_effect(effect, ctx)
        self.assertFalse(result.applied)

    def test_gating_far_side_from_balcony_returns_courtyard(self) -> None:
        """GATING_FAR_SIDE resolves symmetrically — from balcony, the far side is courtyard."""
        place_in_position(self.char, self.balcony)
        effect = ConsequenceEffectFactory(
            consequence=self.consequence,
            effect_type=EffectType.MOVE_TO_POSITION,
            position_destination=PositionDestination.GATING_FAR_SIDE,
            target=EffectTarget.SELF,
        )
        ctx = ResolutionContext(character=self.char, challenge_instance=self.gate)
        apply_effect(effect, ctx)
        self.assertEqual(position_of(self.char).pk, self.courtyard.pk)


class GatedEdgeCrossingIntegrationTests(TestCase):
    """Integration: resolving an approach with GATING_FAR_SIDE crosses the gated edge.

    Author a challenge whose SUCCESS-tier approach consequence carries
    MOVE_TO_POSITION / GATING_FAR_SIDE / SELF with ResolutionType.PERSONAL
    (gate stays up for others). Patching perform_check to force a success outcome.
    """

    def setUp(self) -> None:
        from evennia import create_object

        from world.checks.factories import CheckTypeFactory
        from world.conditions.factories import CapabilityTypeFactory
        from world.traits.factories import CheckOutcomeFactory

        self.room = create_object("typeclasses.rooms.Room", key="GECRoom", nohome=True)
        self.char = CharacterFactory(location=self.room)
        self.courtyard = Position.objects.create(room=self.room, name="courtyard_gec")
        self.balcony = Position.objects.create(room=self.room, name="balcony_gec")
        place_in_position(self.char, self.courtyard)

        # Build the challenge authoring chain.
        self.outcome_success = CheckOutcomeFactory(name="Success_gec", success_level=1)
        self.check_type = CheckTypeFactory()
        capability = CapabilityTypeFactory(name="fly_gec")
        self.capability_source = _make_capability_source(capability.pk)

        prop = PropertyFactory(name="gec_prop")
        app = ApplicationFactory(capability=capability, target_property=prop)
        template = ChallengeTemplateFactory(name="Gated Crossing")
        template.properties.add(prop)
        self.approach = ChallengeApproachFactory(
            challenge_template=template,
            application=app,
            check_type=self.check_type,
            display_name="Fly across",
        )

        # SUCCESS-tier consequence: MOVE_TO_POSITION / GATING_FAR_SIDE / PERSONAL
        success_consequence = ConsequenceFactory(
            outcome_tier=self.outcome_success,
            label="Crossed the gap",
            weight=1,
        )
        ConsequenceEffectFactory(
            consequence=success_consequence,
            effect_type=EffectType.MOVE_TO_POSITION,
            position_destination=PositionDestination.GATING_FAR_SIDE,
            target=EffectTarget.SELF,
        )
        # Link consequence to template with PERSONAL resolution (gate stays active).
        ChallengeTemplateConsequenceFactory(
            challenge_template=template,
            consequence=success_consequence,
            resolution_type=ResolutionType.PERSONAL,
        )

        # Wire the gating challenge instance onto the edge.
        self.gate = ChallengeInstanceFactory(
            template=template,
            location=self.room,
            target_object=self.room,
        )
        connect_positions(self.courtyard, self.balcony, gating_challenge=self.gate)

    def test_cross_gated_edge_via_approach(self) -> None:
        """Resolving the approach moves the actor to the far side; gate stays up (PERSONAL)."""
        from world.checks.types import CheckResult
        from world.mechanics.challenge_resolution import resolve_challenge

        mock_result = CheckResult(
            check_type=self.check_type,
            outcome=self.outcome_success,
            chart=None,
            roller_rank=None,
            target_rank=None,
            rank_difference=0,
            trait_points=0,
            aspect_bonus=0,
            total_points=0,
        )

        with patch(
            "world.mechanics.challenge_resolution.perform_check",
            return_value=mock_result,
        ):
            resolve_challenge(self.char, self.gate, self.approach, self.capability_source)

        # Actor crossed to balcony.
        self.assertEqual(position_of(self.char).pk, self.balcony.pk)

        # PERSONAL resolution — gate stays active for others.
        self.gate.refresh_from_db()
        self.assertTrue(self.gate.is_active)
