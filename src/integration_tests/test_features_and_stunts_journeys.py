"""Journeys for place features and stunts (#4675, slice 3 of #4651).

Staff attach a feature (a chandelier) to a blueprint place; staging the blueprint gives the
live place the same feature on the same square. A feature square must lie inside its place.

A character in a place with a feature whose challenge pairs with her capabilities sees a
stunt in her move list ("Chandelier to Stage"), rolls it, and lands (or misses and stays).
See the Hall fixture below for the rows.
"""

from __future__ import annotations

from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse

from actions.player_interface import dispatch_player_action, get_player_actions
from evennia_extensions.factories import MediaFactory, RoomProfileFactory
from integration_tests.harness import JourneyCase
from world.areas.positioning.constants import FeatureReach
from world.areas.positioning.factories import (
    BlueprintFeatureFactory,
    FeatureTypeFactory,
    PositionFactory,
)
from world.areas.positioning.models import PositionFeature
from world.areas.positioning.services import (
    add_blueprint_position,
    attach_feature,
    connect_positions,
    create_blueprint,
    detach_feature,
    instantiate_blueprint,
    place_in_position,
    position_of,
)
from world.areas.positioning.stunts import perform_stunt
from world.checks.constants import EffectType
from world.checks.factories import ConsequenceEffectFactory, ConsequenceFactory
from world.checks.types import CheckResult
from world.combat.constants import (
    OpponentTier,
    ParticipantStatus,
    StrikeDelivery,
    TargetingMode,
    TargetSelection,
)
from world.combat.factories import (
    CombatEncounterFactory,
    CombatParticipantFactory,
    CreatureTemplateFactory,
    OpponentTierTemplateFactory,
    ThreatPoolEntryFactory,
    ThreatPoolFactory,
)
from world.combat.models import CombatOpponent, CombatParticipant
from world.combat.services.boss.creature_spawn import spawn_from_creature_template
from world.combat.services.movement_budget import hops_left
from world.conditions.constants import FoundationalCapability
from world.conditions.factories import (
    CapabilityTypeFactory,
    ConditionCapabilityEffectFactory,
    ConditionTemplateFactory,
    DamageTypeFactory,
)
from world.conditions.models import CapabilityType
from world.conditions.services import apply_condition
from world.gm.factories import GMProfileFactory
from world.magic.factories import CharacterAnimaFactory
from world.mechanics.factories import (
    ApplicationFactory,
    ChallengeApproachFactory,
    ChallengeTemplateConsequenceFactory,
    ChallengeTemplateFactory,
    CharacterEngagementFactory,
    ModifierCategoryFactory,
)
from world.mechanics.models import (
    ChallengeInstance,
    CharacterModifier,
    ModifierSource,
    ModifierTarget,
)
from world.scenes.constants import RoundStatus
from world.seeds.checks import seed_check_resolution_tables
from world.traits.factories import CheckOutcomeFactory
from world.vitals.models import CharacterVitals
from world.vitals.seeds import ensure_foundational_capabilities


def _blueprint_with_floor(feature_type=None, square=(6, 4)):
    blueprint = create_blueprint("Hall")
    floor = add_blueprint_position(blueprint, "Floor")
    floor.area_x, floor.area_y, floor.area_w, floor.area_h = 2, 2, 10, 8
    floor.save()
    if feature_type is not None:
        BlueprintFeatureFactory(
            blueprint_position=floor,
            feature_type=feature_type,
            square_x=square[0],
            square_y=square[1],
        )
    return blueprint, floor


class FeatureJourneys(TestCase):
    def test_staging_a_blueprint_gives_the_live_place_its_feature(self):
        chandelier = FeatureTypeFactory(name="Chandelier")
        blueprint, _ = _blueprint_with_floor(chandelier)
        room = RoomProfileFactory().objectdb

        positions = instantiate_blueprint(blueprint, room)

        feature = PositionFeature.objects.get(position=positions[0])
        self.assertEqual(feature.feature_type, chandelier)
        self.assertEqual((feature.square_x, feature.square_y), (6, 4))

    def test_restaging_with_a_featureless_blueprint_leaves_no_features(self):
        chandelier = FeatureTypeFactory(name="Chandelier")
        with_feature, _ = _blueprint_with_floor(chandelier)
        bare = create_blueprint("Bare")
        add_blueprint_position(bare, "Floor")
        room = RoomProfileFactory().objectdb
        instantiate_blueprint(with_feature, room)

        instantiate_blueprint(bare, room, replace=True)

        self.assertFalse(PositionFeature.objects.filter(position__room=room).exists())

    def test_a_feature_square_outside_its_place_is_refused(self):
        chandelier = FeatureTypeFactory(name="Chandelier")
        _, floor = _blueprint_with_floor()
        feature = BlueprintFeatureFactory.build(
            blueprint_position=floor, feature_type=chandelier, square_x=40, square_y=4
        )
        with self.assertRaisesMessage(ValidationError, "That square is outside Floor."):
            feature.full_clean()

    def test_a_square_on_a_place_with_no_area_is_refused(self):
        chandelier = FeatureTypeFactory(name="Chandelier")
        blueprint = create_blueprint("Plain")
        bare = add_blueprint_position(blueprint, "Yard")
        feature = BlueprintFeatureFactory.build(
            blueprint_position=bare, feature_type=chandelier, square_x=1, square_y=1
        )
        with self.assertRaises(ValidationError):
            feature.full_clean()

    def test_attach_then_detach_round_trips(self):
        chandelier = FeatureTypeFactory(name="Chandelier")
        blueprint, _ = _blueprint_with_floor()
        room = RoomProfileFactory().objectdb
        place = instantiate_blueprint(blueprint, room)[0]

        feature = attach_feature(place, chandelier, square=(6, 4))
        self.assertEqual(list(place.features.all()), [feature])
        self.assertEqual((feature.square_x, feature.square_y), (6, 4))

        detach_feature(feature)
        self.assertFalse(place.features.exists())

    def test_attach_with_a_square_outside_the_place_is_refused_and_saves_nothing(self):
        chandelier = FeatureTypeFactory(name="Chandelier")
        blueprint, _ = _blueprint_with_floor()
        room = RoomProfileFactory().objectdb
        place = instantiate_blueprint(blueprint, room)[0]

        with self.assertRaisesMessage(ValidationError, "That square is outside Floor."):
            attach_feature(place, chandelier, square=(40, 4))

        self.assertFalse(PositionFeature.objects.filter(position=place).exists())

    def test_a_feature_with_only_one_square_number_is_refused(self):
        chandelier = FeatureTypeFactory(name="Chandelier")
        blueprint, _ = _blueprint_with_floor()
        room = RoomProfileFactory().objectdb
        place = instantiate_blueprint(blueprint, room)[0]
        feature = PositionFeature(position=place, feature_type=chandelier, square_x=6)

        with self.assertRaisesMessage(ValidationError, "Fill in both square numbers"):
            feature.full_clean()


# -- Stunts (task 2) -------------------------------------------------------------------------
#
# The Hall: Floor - Stage (an open edge) and Floor - Gallery (a wall nobody walks through),
# with a fight in DECLARING round 1. A Chandelier (reach: adjacent) hangs over the Floor; its
# challenge "Swing" has one approach by acrobatics, "Swing across". Its missed outcome carries
# a 7-point fall (DEAL_DAMAGE on the roller). Kit tumbles by a Tumbler's Poise condition
# (acrobatics 10) and has three hops a round (movement 5 + 10 = 15, five a hop). Pell has no
# acrobatics. Expected values are the rows built here and the spec's copy.

FULL_HEALTH = 100
FALL = 7
EXTRA_MOVEMENT = 10
CHALLENGE_PERFORM_CHECK = "world.mechanics.challenge_resolution.perform_check"
STUNT_ENTRY = "Chandelier to {place}"
USED_IT = "You use the Chandelier to reach {place}."
REACHED_ROUGHLY = "You reach {place}, but not cleanly."
MISSED = "You don't make it."
ROOM_USED_IT = "{name} uses the Chandelier to reach {place}."
ROOM_MISSED = "{name} tries the Chandelier and doesn't make it."
CANT_FROM_HERE = "You can't do that from here."
STOPPED_BY = "You are stopped by {name}."
NO_GM = "Only staff or the scene's GM can do that."
DIFFICULTY_LABELS = {"Impossible", "Easy", "Moderate", "Hard", "Very Hard"}


class _TheHall(JourneyCase):
    def setUp(self) -> None:
        super().setUp()
        seed_check_resolution_tables()
        with override_settings(SEED_SAMPLE_CONTENT=True):  # movement
            ensure_foundational_capabilities()
        OpponentTierTemplateFactory(tier=OpponentTier.MOOK, base_health=30, base_soak=0)
        self.room = self.make_room("The Hall")
        self.floor = PositionFactory(room=self.room, name="Floor")
        self.stage = PositionFactory(room=self.room, name="Stage")
        self.gallery = PositionFactory(room=self.room, name="Gallery")
        connect_positions(self.floor, self.stage)
        connect_positions(self.floor, self.gallery, is_passable=False)
        self.encounter = CombatEncounterFactory(
            status=RoundStatus.DECLARING, round_number=1, room=self.room
        )
        self.acrobatics = CapabilityTypeFactory(name="acrobatics", innate_baseline=0)
        self.swing = ChallengeTemplateFactory(name="Swing")
        ChallengeApproachFactory(
            challenge_template=self.swing,
            application=ApplicationFactory(name="Swing", capability=self.acrobatics),
            display_name="Swing across",
        )
        self.clean = CheckOutcomeFactory(name="Swing-Clean", success_level=1)
        self.partly = CheckOutcomeFactory(name="Swing-Partial", success_level=0)
        self.missed = CheckOutcomeFactory(name="Swing-Missed", success_level=-1)
        fall = ConsequenceFactory(outcome_tier=self.missed, label="Fall")
        ConsequenceEffectFactory(
            consequence=fall,
            effect_type=EffectType.DEAL_DAMAGE,
            damage_amount=FALL,
            damage_type=DamageTypeFactory(name="blunt"),
            target="self",
        )
        ChallengeTemplateConsequenceFactory(challenge_template=self.swing, consequence=fall)
        self.chandelier_type = FeatureTypeFactory(
            name="Chandelier", reach=FeatureReach.ADJACENT, challenge_template=self.swing
        )
        self.chandelier = attach_feature(self.floor, self.chandelier_type)
        self.poise = ConditionTemplateFactory(name="Tumbler's Poise")
        ConditionCapabilityEffectFactory(condition=self.poise, capability=self.acrobatics, value=10)

    def raise_movement(self, character) -> None:
        movement = CapabilityType.objects.get(name=FoundationalCapability.MOVEMENT)
        target, _ = ModifierTarget.objects.get_or_create(
            name=f"capability_{movement.pk}",
            category=ModifierCategoryFactory(name="capability"),
            defaults={
                "description": "",
                "display_order": 0,
                "is_active": True,
                "target_capability": movement,
            },
        )
        CharacterModifier.objects.create(
            character=character.sheet_data,
            target=target,
            value=EXTRA_MOVEMENT,
            source=ModifierSource.objects.create(),
        )

    def person(self, name: str, *, at=None, fighting: bool = True, acrobat: bool = True):
        character = self.make_player(name, room=self.room)
        sheet = character.sheet_data
        CharacterVitals.objects.create(
            character_sheet=sheet, health=FULL_HEALTH, max_health=FULL_HEALTH, base_max_health=100
        )
        CharacterAnimaFactory(character=sheet, current=20, maximum=20)
        CharacterEngagementFactory(character=sheet)
        if fighting:
            CombatParticipantFactory(
                encounter=self.encounter, character_sheet=sheet, status=ParticipantStatus.ACTIVE
            )
        self.raise_movement(character)
        if acrobat:
            apply_condition(character, self.poise)
        place_in_position(character, at or self.floor)
        return character

    def bandit(self, *, at) -> CombatOpponent:
        pool = ThreatPoolFactory(name="Bandit attacks")
        ThreatPoolEntryFactory(
            pool=pool,
            name="Bandit strike",
            base_damage=10,
            delivery=StrikeDelivery.MELEE,
            targeting_mode=TargetingMode.SINGLE,
            target_selection=TargetSelection.HIGHEST_THREAT,
        )
        template = CreatureTemplateFactory(
            name="Bandit", tier=OpponentTier.MOOK, threat_pool=pool, speed_hops=1
        )
        return spawn_from_creature_template(self.encounter, template, position=at)

    def participant(self, character) -> CombatParticipant:
        return CombatParticipant.objects.get(
            encounter=self.encounter, character_sheet=character.sheet_data
        )

    def health(self, character) -> int:
        return CharacterVitals.objects.get(character_sheet=character.sheet_data).health

    def roll(self, outcome):
        def forced(_character, check_type, *_args: object, **_kwargs: object) -> CheckResult:
            return CheckResult(
                check_type=check_type,
                outcome=outcome,
                chart=None,
                roller_rank=None,
                target_rank=None,
                rank_difference=0,
                trait_points=0,
                aspect_bonus=0,
                total_points=0,
            )

        return patch(CHALLENGE_PERFORM_CHECK, side_effect=forced)

    def stunts(self, character) -> list:
        return [
            action
            for action in get_player_actions(character)
            if action.ref.registry_key == "perform_stunt"
        ]

    def stunt(self, character, place, **extra):
        return self.web(
            character,
            "perform_stunt",
            feature_id=self.chandelier.pk,
            position_id=place.pk,
            **extra,
        )


class AStuntInTheMoveList(_TheHall):
    def test_an_acrobat_sees_the_chandelier_to_each_place_it_reaches(self) -> None:
        kit = self.person("Kit")

        stunts = {action.display_name: action for action in self.stunts(kit)}

        # The Gallery is behind a wall a walk cannot cross; the swing goes over it.
        self.assertEqual(
            set(stunts), {STUNT_ENTRY.format(place="Stage"), STUNT_ENTRY.format(place="Gallery")}
        )
        entry = stunts[STUNT_ENTRY.format(place="Stage")]
        approach, _, difficulty = entry.description.partition(" · ")
        self.assertEqual(approach, "Swing across")
        self.assertIn(difficulty, DIFFICULTY_LABELS)
        self.assertTrue(entry.prerequisite_met)
        self.assertEqual(entry.ref.feature_id, self.chandelier.pk)
        self.assertEqual(entry.ref.position_id, self.stage.pk)
        # The plain walk to the Stage is still listed on its own.
        names = [action.display_name for action in get_player_actions(kit)]
        self.assertIn("Move to Stage", names)

    def test_the_entry_dispatches_as_listed(self) -> None:
        kit = self.person("Kit")
        entry = next(
            action
            for action in self.stunts(kit)
            if action.display_name == STUNT_ENTRY.format(place="Stage")
        )

        with self.roll(self.clean):
            result = dispatch_player_action(kit, entry.ref, {})

        self.assertTrue(result.detail.success, result.detail.message)
        self.assertEqual(position_of(kit), self.stage)

    def test_a_walker_without_the_capability_sees_no_stunt(self) -> None:
        pell = self.person("Pell", acrobat=False)

        self.assertEqual(self.stunts(pell), [])

        result = self.stunt(pell, self.stage)

        self.assertFalse(result.detail.success)
        self.assertEqual(result.detail.message, CANT_FROM_HERE)
        self.assertEqual(position_of(pell), self.floor)

    def test_a_feature_whose_challenge_has_no_approach_offers_nothing(self) -> None:
        rope = FeatureTypeFactory(name="Rope", reach=FeatureReach.ADJACENT)
        self.chandelier.delete()
        attach_feature(self.floor, rope)
        kit = self.person("Kit")

        self.assertEqual(self.stunts(kit), [])

    def test_a_feature_in_another_place_is_not_hers_to_use(self) -> None:
        kit = self.person("Kit", at=self.stage)

        self.assertEqual(self.stunts(kit), [])
        result = self.stunt(kit, self.gallery)

        self.assertFalse(result.detail.success)
        self.assertEqual(result.detail.message, CANT_FROM_HERE)


class MakingAStunt(_TheHall):
    def test_a_clean_swing_moves_her_and_spends_one_hop(self) -> None:
        kit = self.person("Kit")
        wren = self.person("Wren", at=self.stage, acrobat=False)
        self.watch(wren)

        with self.roll(self.clean):
            result = self.stunt(kit, self.gallery)

        self.assertTrue(result.detail.success, result.detail.message)
        self.assertEqual(result.detail.message, USED_IT.format(place="Gallery"))
        self.assertEqual(position_of(kit), self.gallery)
        self.assertEqual(self.participant(kit).hops_used, 1)
        self.assertEqual(self.health(kit), FULL_HEALTH)
        self.assertTold(wren, ROOM_USED_IT.format(name="Kit", place="Gallery"))
        minted = ChallengeInstance.objects.get(template=self.swing)
        self.assertFalse(minted.is_active)

    def test_a_partial_swing_still_lands_her(self) -> None:
        kit = self.person("Kit")

        with self.roll(self.partly):
            result = self.stunt(kit, self.stage)

        self.assertEqual(result.detail.message, REACHED_ROUGHLY.format(place="Stage"))
        self.assertEqual(position_of(kit), self.stage)

    def test_a_miss_keeps_her_spends_the_hop_and_the_fall_lands(self) -> None:
        kit = self.person("Kit")
        wren = self.person("Wren", at=self.stage, acrobat=False)
        self.watch(wren)

        with self.roll(self.missed):
            result = self.stunt(kit, self.stage)

        self.assertTrue(result.detail.success, result.detail.message)
        self.assertEqual(result.detail.message, MISSED)
        self.assertEqual(position_of(kit), self.floor)
        self.assertEqual(self.participant(kit).hops_used, 1)
        self.assertEqual(self.health(kit), FULL_HEALTH - FALL)
        self.assertTold(wren, ROOM_MISSED.format(name="Kit"))
        self.assertFalse(ChallengeInstance.objects.get(template=self.swing).is_active)

    def test_a_swing_into_held_ground_stops_her_there(self) -> None:
        self.bandit(at=self.stage)
        kit = self.person("Kit")

        with self.roll(self.clean):
            result = self.stunt(kit, self.stage)

        self.assertTrue(result.detail.success, result.detail.message)
        self.assertEqual(
            result.detail.message,
            f"{USED_IT.format(place='Stage')} {STOPPED_BY.format(name='Bandit')}",
        )
        self.assertEqual(position_of(kit), self.stage)
        self.assertEqual(hops_left(self.participant(kit)), 0)

    def test_the_instance_is_spent_even_when_resolution_raises(self) -> None:
        kit = self.person("Kit")

        with (
            patch(CHALLENGE_PERFORM_CHECK, side_effect=RuntimeError("dice fell off the table")),
            self.assertRaises(RuntimeError),
        ):
            perform_stunt(kit, self.chandelier, self.stage)

        self.assertFalse(
            ChallengeInstance.objects.filter(template=self.swing, is_active=True).exists()
        )
        self.assertEqual(position_of(kit), self.floor)

    def test_outside_a_fight_it_moves_her_with_no_hop(self) -> None:
        kit = self.person("Kit", fighting=False)

        with self.roll(self.clean):
            result = self.stunt(kit, self.stage)

        self.assertTrue(result.detail.success, result.detail.message)
        self.assertEqual(position_of(kit), self.stage)
        self.assertFalse(CombatParticipant.objects.filter(character_sheet=kit.sheet_data).exists())

    def test_by_telnet(self) -> None:
        kit = self.person("Kit")

        listing = self.telnet(kit, "position")
        self.assertIn("features: Chandelier", listing)

        with self.roll(self.clean):
            said = self.telnet(kit, "position/stunt Chandelier to Stage")

        self.assertIn(USED_IT.format(place="Stage"), said)
        self.assertEqual(position_of(kit), self.stage)
        self.assertEqual(self.participant(kit).hops_used, 1)


class AGMAddsAFeature(_TheHall):
    def test_staff_attach_a_feature_to_a_live_place_and_remove_it(self) -> None:
        rope = FeatureTypeFactory(name="Rope", reach=FeatureReach.ANY_PLACE)
        gm = self.person("Ash", fighting=False, acrobat=False)
        account = self.account_of(gm)
        account.is_staff = True
        account.save(update_fields=["is_staff"])

        result = self.web(
            gm, "gm_attach_feature", position_id=self.stage.pk, feature_type_id=rope.pk
        )

        self.assertTrue(result.detail.success, result.detail.message)
        self.assertEqual(result.detail.message, "You add the Rope to Stage.")
        added = PositionFeature.objects.get(position=self.stage, feature_type=rope)

        removed = self.web(gm, "gm_detach_feature", feature_id=added.pk)

        self.assertEqual(removed.detail.message, "You remove the Rope from Stage.")
        self.assertFalse(PositionFeature.objects.filter(pk=added.pk).exists())

    def test_a_gm_in_a_large_room_keeps_every_gm_tool_on_the_first_page(self) -> None:
        """Ten places: one "Add feature" entry, not ten, so staging stays on page one."""
        for number in range(7):
            PositionFactory(room=self.room, name=f"Alcove {number + 1}")
        gm = self.person("Ash", fighting=False, acrobat=False)
        account = self.account_of(gm)
        account.is_staff = True
        account.save(update_fields=["is_staff"])

        response = self.api(account).get(
            reverse("actions:available-actions", kwargs={"character_id": gm.pk})
        )

        self.assertEqual(response.status_code, 200)
        keys = [row["ref"]["registry_key"] for row in response.data["results"]]
        self.assertEqual(keys.count("gm_attach_feature"), 1)
        self.assertEqual(keys.count("gm_place_in_position"), 10)
        for staging in (
            "create_battle",
            "stage_battle_map",
            "spawn_battle_units",
            "enlist_battle_participant",
        ):
            self.assertIn(staging, keys)
        self.assertGreater(keys.index("gm_attach_feature"), keys.index("create_battle"))

    def test_a_player_who_is_not_a_gm_is_refused(self) -> None:
        rope = FeatureTypeFactory(name="Rope")
        pell = self.person("Pell", fighting=False, acrobat=False)

        self.assertFalse(
            [a for a in get_player_actions(pell) if a.ref.registry_key == "gm_attach_feature"]
        )
        result = self.web(
            pell, "gm_attach_feature", position_id=self.stage.pk, feature_type_id=rope.pk
        )
        removed = self.web(pell, "gm_detach_feature", feature_id=self.chandelier.pk)

        self.assertFalse(result.detail.success)
        self.assertEqual(result.detail.message, NO_GM)
        self.assertEqual(removed.detail.message, NO_GM)
        self.assertFalse(PositionFeature.objects.filter(feature_type=rope).exists())
        self.assertTrue(PositionFeature.objects.filter(pk=self.chandelier.pk).exists())


class TheFeatureTypeList(JourneyCase):
    """GET /api/areas/feature-types/: what the GM attach control offers (#4675)."""

    def setUp(self) -> None:
        super().setUp()
        self.room = self.make_room("The Hall")
        self.art = MediaFactory()
        self.chandelier = FeatureTypeFactory(
            name="Chandelier", reach=FeatureReach.ADJACENT, art=self.art
        )
        self.rope = FeatureTypeFactory(name="Rope", reach=FeatureReach.ANY_PLACE)

    def test_a_gm_sees_every_feature_type_with_its_reach_and_art(self) -> None:
        gm = self.make_player("Ash", room=self.room)
        GMProfileFactory(account=self.account_of(gm))

        response = self.api(self.account_of(gm)).get("/api/areas/feature-types/")

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(
            response.json()["results"],
            [
                {
                    "id": self.chandelier.pk,
                    "name": "Chandelier",
                    "reach": "adjacent",
                    "art_url": self.art.cloudinary_url,
                },
                {"id": self.rope.pk, "name": "Rope", "reach": "any_place", "art_url": None},
            ],
        )
        narrowed = self.api(self.account_of(gm)).get(
            "/api/areas/feature-types/", {"reach": "any_place"}
        )
        self.assertEqual([row["name"] for row in narrowed.json()["results"]], ["Rope"])

    def test_staff_see_the_list(self) -> None:
        ash = self.make_player("Ash", room=self.room)
        account = self.account_of(ash)
        account.is_staff = True
        account.save(update_fields=["is_staff"])

        response = self.api(account).get("/api/areas/feature-types/")

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(len(response.json()["results"]), 2)

    def test_a_player_who_is_not_a_gm_is_refused(self) -> None:
        pell = self.make_player("Pell", room=self.room)

        response = self.api(self.account_of(pell)).get("/api/areas/feature-types/")

        self.assertEqual(response.status_code, 403)
        self.assertIn(self.api().get("/api/areas/feature-types/").status_code, (401, 403))
