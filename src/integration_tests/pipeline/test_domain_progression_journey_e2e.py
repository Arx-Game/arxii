"""Building to neighborhood to domain progression (#696), one journey per gap.

Each journey drives the real services end to end (checks forced through
``world.checks.test_helpers.force_check_outcome``, the official seam; nothing
else mocked): eligibility then declare (gap 3), the fallback owner (gap 4), a
raid picking the weakest-defended domain (gap 5), a steward's grant landing in
a member's bucket and the house-set price paying out (gap 6), an instance
entrance admitting the run and hiding from everyone else (gap 7), and a
steward-set difficulty consumed by the PC run that picks the task up (gap 8).
"""

from __future__ import annotations

import random

from django.test import TestCase
from evennia.objects.models import ObjectDB

from evennia_extensions.factories import CharacterFactory, ObjectDBFactory
from evennia_extensions.models import RoomProfile
from flows.factories import SceneDataManagerFactory
from flows.service_functions.serializers.room_state import RoomStatePayloadSerializer
from world.areas.constants import AreaLevel
from world.areas.elevation_services import declare_elevation, elevation_eligibility
from world.areas.factories import AreaFactory
from world.areas.models import AreaElevationRequirement
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import CheckTypeFactory
from world.checks.test_helpers import force_check_outcome
from world.currency.constants import MATERIAL_AUTO_SELL_THRESHOLD
from world.currency.services import (
    auto_sell_excess_materials,
    get_or_create_purse,
    get_or_create_treasury,
)
from world.instances.services import complete_instanced_room, spawn_instanced_room
from world.items.constants import OrgMaterialLedgerKind
from world.items.factories import MaterialCategoryFactory
from world.items.gems.buckets import material_value
from world.items.materials_models import OrgMaterialLedgerEntry, OrgMaterialStock
from world.items.services.org_materials import grant_material_stock, set_asking_price
from world.locations.constants import HolderType, LocationParentType, StatKey
from world.locations.factories import LocationOwnershipFactory, LocationValueModifierFactory
from world.locations.models import LocationOwnership
from world.locations.services import effective_owner_for_area
from world.military.factories import MilitaryUnitFactory
from world.missions.constants import OptionKind, OptionSource
from world.missions.factories import (
    MissionInstanceFactory,
    MissionNodeFactory,
    MissionOptionFactory,
    MissionOptionRouteFactory,
    MissionParticipantFactory,
    MissionTemplateFactory,
)
from world.missions.models import MissionParticipant
from world.missions.services.resolution import resolve_option
from world.predators.constants import MenaceStage
from world.predators.factories import PredatorBandFactory
from world.predators.services import weekly_menace_tick
from world.roster.constants import NOBLE_KIND_NAME
from world.roster.factories import FamilyFactory, FamilyKindFactory
from world.scenes.factories import PersonaFactory
from world.societies.factories import OrganizationFactory, OrganizationMembershipFactory
from world.societies.houses.models import DomainCrisis, HouseStature
from world.societies.houses.services import assign_garrison, create_domain, effective_defenses
from world.tasking.factories import TaskTemplateFactory
from world.tasking.services import accept_task, create_task
from world.traits.factories import CheckOutcomeFactory

_EXIT_TYPECLASS = "typeclasses.exits.Exit"


class _NoSpawnRandom(random.Random):
    """rng whose random() is 1.0 (no spawns, no spreads): a deterministic tick."""

    def random(self) -> float:
        return 1.0


def _room(name: str) -> ObjectDB:
    return ObjectDBFactory(db_key=name, db_typeclass_path="typeclasses.rooms.Room")


def _pc(room: ObjectDB) -> ObjectDB:
    character = CharacterFactory()
    CharacterSheetFactory(character=character)
    character.db_location = room
    character.save(update_fields=["db_location"])
    return character


class ElevationJourneyTests(TestCase):
    """Gap 3: a holder is told why the neighborhood cannot rise, fixes it, declares."""

    def test_eligibility_then_declare(self) -> None:
        neighborhood = AreaFactory(level=AreaLevel.NEIGHBORHOOD)
        sheet = CharacterSheetFactory()
        declarer = sheet.primary_persona
        for _ in range(2):
            building = AreaFactory(level=AreaLevel.BUILDING, parent=neighborhood)
            LocationOwnershipFactory(area=building, holder_persona=declarer)
        AreaElevationRequirement.objects.create(
            to_level=AreaLevel.WARD, min_held_buildings=2, min_order_stat=10, cost_coppers=500
        )
        purse = get_or_create_purse(sheet)
        purse.balance = 1000
        purse.save(update_fields=["balance"])

        LocationValueModifierFactory(area=neighborhood, stat_key=StatKey.ORDER, value=3)
        first = elevation_eligibility(neighborhood, declarer=declarer)
        self.assertFalse(first.eligible)
        self.assertTrue(any("order" in reason for reason in first.reasons))

        LocationValueModifierFactory(area=neighborhood, stat_key=StatKey.ORDER, value=7)
        second = elevation_eligibility(neighborhood, declarer=declarer)
        self.assertTrue(second.eligible, second.reasons)

        declare_elevation(neighborhood, declarer=declarer, treasury_or_purse=purse)

        neighborhood.refresh_from_db()
        purse.refresh_from_db()
        self.assertEqual(neighborhood.level, AreaLevel.WARD)
        self.assertEqual(purse.balance, 500)


class FallbackOwnerJourneyTests(TestCase):
    """Gap 4: an unowned ward answers to the nearest owned ancestor, until it is owned."""

    def test_fallback_owner_then_own_row(self) -> None:
        region = AreaFactory(level=AreaLevel.REGION)
        city = AreaFactory(level=AreaLevel.CITY, parent=region)
        ward = AreaFactory(level=AreaLevel.WARD, parent=city)
        crown = OrganizationFactory(name="The Crown")
        region_row = LocationOwnership.objects.create(
            parent_type=LocationParentType.AREA,
            area=region,
            holder_type=HolderType.ORGANIZATION,
            holder_organization=crown,
        )

        self.assertEqual(effective_owner_for_area(ward), region_row)

        ward_row = LocationOwnership.objects.create(
            parent_type=LocationParentType.AREA,
            area=ward,
            holder_type=HolderType.PERSONA,
            holder_persona=PersonaFactory(),
        )

        self.assertEqual(effective_owner_for_area(ward), ward_row)
        self.assertEqual(effective_owner_for_area(city), region_row)


class DefensesJourneyTests(TestCase):
    """Gap 5: a garrison posts, effective defenses read through the seam, and a
    band at the RAIDS stage strikes the domain with the lowest effective defenses."""

    def test_raid_targets_lowest_defenses(self) -> None:
        family = FamilyFactory(name="Prey", kind=FamilyKindFactory(name=NOBLE_KIND_NAME))
        prey = OrganizationFactory(name="House Prey", family=family)
        HouseStature.objects.create(organization=prey, perceived_total=100, true_total=100)
        fortified = create_domain(area=AreaFactory(), name="Fortified Vale", owner_org=prey)
        fortified.prosperity = 10
        fortified.defenses = 90
        fortified.save(update_fields=["prosperity", "defenses"])
        exposed = create_domain(area=AreaFactory(), name="Exposed Marches", owner_org=prey)
        exposed.prosperity = 90
        exposed.defenses = 0
        exposed.save(update_fields=["prosperity", "defenses"])

        post = assign_garrison(domain=fortified, unit=MilitaryUnitFactory(owner_org=prey))
        self.assertEqual(post.domain, fortified)
        # The garrison seam reads through effective_defenses; its combat term is
        # TehomCD's to fill, so today it adds nothing on top of the stat.
        self.assertGreaterEqual(effective_defenses(fortified), fortified.defenses)
        self.assertGreater(effective_defenses(fortified), effective_defenses(exposed))

        band = PredatorBandFactory(prey=prey, stage=MenaceStage.RAIDS)
        weekly_menace_tick(rng=_NoSpawnRandom())

        crisis = DomainCrisis.objects.get(aggressor_band=band)
        self.assertEqual(crisis.domain, exposed)


class MaterialEconomyJourneyTests(TestCase):
    """Gap 6: a steward's grant lands in one member's bucket, and the excess the
    house does not hand out liquidates at the price the house set."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.org = OrganizationFactory(name="House Westrock")
        cls.category = MaterialCategoryFactory(name="Cordwood")
        cls.leader = PersonaFactory()
        cls.member = PersonaFactory()
        OrganizationMembershipFactory(organization=cls.org, persona=cls.leader, rank=1)
        OrganizationMembershipFactory(organization=cls.org, persona=cls.member)

    def test_grant_lands_in_a_bucket_and_the_rest_sells_at_the_asking_price(self) -> None:
        stock = OrgMaterialStock.objects.create(
            organization=self.org,
            material_category=self.category,
            value=MATERIAL_AUTO_SELL_THRESHOLD + 1400,
        )
        recipient = self.member.character_sheet

        entry = grant_material_stock(
            organization=self.org,
            material_category=self.category,
            value=400,
            to_sheet=recipient,
            granted_by=self.leader,
        )
        stock.refresh_from_db()
        self.assertEqual(entry.kind, OrgMaterialLedgerKind.GRANT)
        self.assertEqual(material_value(recipient, self.category), 400)
        self.assertEqual(stock.value, MATERIAL_AUTO_SELL_THRESHOLD + 1000)

        set_asking_price(
            organization=self.org, material_category=self.category, pct=80, by=self.leader
        )
        coins = auto_sell_excess_materials(organization=self.org)

        self.assertEqual(coins, 800)
        treasury = get_or_create_treasury(self.org)
        treasury.refresh_from_db()
        self.assertEqual(treasury.balance, 800)
        stock.refresh_from_db()
        self.assertEqual(stock.value, MATERIAL_AUTO_SELL_THRESHOLD)
        kinds = list(
            OrgMaterialLedgerEntry.objects.filter(organization=self.org)
            .order_by("pk")
            .values_list("kind", flat=True)
        )
        self.assertEqual(kinds[0], OrgMaterialLedgerKind.GRANT)
        self.assertEqual(len(kinds), 2)


class EntranceJourneyTests(TestCase):
    """Gap 7: the run's people pass the doorway and see it; a bystander does neither."""

    def test_entrance_traversal_and_hiding(self) -> None:
        anchor = _room("Inn Hallway")
        hallway_area = AreaFactory(name="Inn District")
        anchor_profile, _ = RoomProfile.objects.get_or_create(objectdb=anchor)
        anchor_profile.area = hallway_area
        anchor_profile.save(update_fields=["area"])
        owner = _pc(anchor)
        participant = _pc(anchor)
        bystander = _pc(anchor)
        spawned = spawn_instanced_room(
            name="Darkened Interior",
            description="",
            owner=owner.sheet_data,
            return_location=anchor,
            source_key="journey:entrance",
            anchor_room=anchor,
        )
        mission = MissionInstanceFactory(spawned_room_id=spawned.pk)
        MissionParticipantFactory(instance=mission, character=participant.sheet_data)
        entrance = ObjectDB.objects.get(db_typeclass_path=_EXIT_TYPECLASS, db_location=anchor)

        context = SceneDataManagerFactory()
        for obj in (anchor, spawned, entrance, owner, participant, bystander):
            context.initialize_state_for_object(obj)
        exit_state = context.get_state_by_pk(entrance.pk)
        room_state = context.get_state_by_pk(anchor.pk)

        def visible_to(character: ObjectDB) -> bool:
            caller_state = context.get_state_by_pk(character.pk)
            serializer = RoomStatePayloadSerializer(
                None, context={"caller": caller_state, "room": room_state}
            )
            _chars, _objs, exits, _place = serializer._serialize_contents(room_state, caller_state)
            return entrance.dbref in {row["dbref"] for row in exits}

        for admitted in (owner, participant):
            self.assertTrue(exit_state.can_traverse(context.get_state_by_pk(admitted.pk)))
            self.assertTrue(visible_to(admitted))
        self.assertFalse(exit_state.can_traverse(context.get_state_by_pk(bystander.pk)))
        self.assertFalse(visible_to(bystander))

        # The interior inherits the doorway's area, and teardown takes the doorway with it.
        self.assertEqual(spawned.room_profile.area_id, hallway_area.pk)
        complete_instanced_room(spawned)
        self.assertFalse(ObjectDB.objects.filter(pk=entrance.pk).exists())


class IssueDifficultyJourneyTests(TestCase):
    """Gap 8: the steward's roll at issue sets the number the runner rolls against."""

    def test_steward_set_difficulty_is_consumed_by_the_pickup(self) -> None:
        org = OrganizationFactory(name="House Ledger")
        steward = PersonaFactory()
        runner = PersonaFactory()
        OrganizationMembershipFactory(organization=org, persona=steward, rank=1)
        OrganizationMembershipFactory(organization=org, persona=runner)

        mission_template = MissionTemplateFactory(name="Collect the levies", risk_tier=2)
        node = MissionNodeFactory(template=mission_template, key="collect", is_entry=True)
        success = CheckOutcomeFactory(name="levies success", success_level=1)
        option = MissionOptionFactory(
            node=node,
            order=0,
            option_kind=OptionKind.CHECK,
            source_kind=OptionSource.AUTHORED,
            authored_check_type=CheckTypeFactory(name="Tax Collection"),
        )
        MissionOptionRouteFactory(option=option, outcome_tier=success, target_node=None)
        task_template = TaskTemplateFactory(mission_template=mission_template)

        good_briefing = CheckOutcomeFactory(name="briefing good", success_level=2)
        with force_check_outcome(good_briefing):
            task = create_task(task_template, org, steward)
        self.assertIsNotNone(task.derived_difficulty)
        self.assertNotEqual(task.derived_difficulty, mission_template.risk_tier)

        fulfillment = accept_task(task, runner)
        instance = fulfillment.mission_instance
        actor = MissionParticipant.objects.get(instance=instance)

        with force_check_outcome(success) as capture:
            resolve_option(instance, node, option, actor)

        self.assertEqual(capture.target_difficulty, task.derived_difficulty)
