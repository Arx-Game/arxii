"""Naming a crew into an authored slot at character creation (#4061 slice 3)."""

from django.test import TestCase
from evennia.accounts.models import AccountDB

from evennia_extensions.factories import RoomProfileFactory
from world.areas.constants import AreaLevel
from world.areas.factories import AreaFactory
from world.character_creation.factories import OriginTemplateFactory
from world.character_creation.serializers import FamilyTemplateSerializer
from world.character_creation.services import finalize_character
from world.character_creation.tests.finalization_fixtures import FinalizationTestMixin
from world.character_creation.validators import _get_named_path_errors as get_family_name_errors
from world.roster.factories import FamilyKindFactory
from world.roster.models import Family
from world.societies.factories import OrganizationFactory, OrganizationTypeFactory
from world.societies.houses.factories import HouseTemplateFactory
from world.societies.houses.models import FealtyEdge
from world.societies.houses.services import house_for_family
from world.societies.membership_services import ensure_default_rank_ladder
from world.societies.models import CrewSlot, Turf
from world.societies.turf_services import apply_turf_push


class CrewSlotFinalizeTests(FinalizationTestMixin, TestCase):
    def setUp(self):
        self._flush_common_caches()
        self.account = AccountDB.objects.create(username="crew_founder")
        self._setup_finalization_base(self, prefix="Crew", height_min=700, height_max=800)
        city = AreaFactory(level=AreaLevel.BARONY, realm=self.area.realm)
        neighborhood = AreaFactory(level=AreaLevel.NEIGHBORHOOD, parent=city)
        self.gang = OrganizationFactory(name="Ashfingers")
        ensure_default_rank_ladder(self.gang)
        apply_turf_push(self.gang, neighborhood, 60)
        self.corner = RoomProfileFactory(area=neighborhood, is_outdoor=True)
        self.slot = CrewSlot.objects.create(gang=self.gang, name="The Saltside corner")
        self.slot.rooms.add(self.corner)
        self.template = HouseTemplateFactory(
            name="A Crew",
            realm=self.area.realm,
            kind=FamilyKindFactory(name="Crime"),
            org_type=OrganizationTypeFactory(name="crew"),
            founds_a_crew=True,
        )
        self.upbringing = OriginTemplateFactory(
            beginning=self.beginnings, family_templates=[self.template]
        )

    def _draft(self, *, slot=None):
        draft = self._create_base_draft(new_family_name="Saltsiders")
        draft.selected_origin_template = self.upbringing
        draft.draft_data.pop("tarot_card_name", None)
        if slot is not None:
            draft.draft_data["crew_slot_id"] = slot.pk
        draft.save()
        return draft

    def test_the_template_offers_the_open_slots(self):
        data = FamilyTemplateSerializer(self.template).data
        self.assertTrue(data["founds_a_crew"])
        self.assertEqual(
            data["crew_slots"],
            [
                {
                    "id": self.slot.pk,
                    "name": "The Saltside corner",
                    "gang": "Ashfingers",
                    "rooms": [self.corner.objectdb.key],
                }
            ],
        )

    def test_a_crew_template_needs_a_slot(self):
        self.assertIn("Choose the corner your crew holds", get_family_name_errors(self._draft()))
        self.assertEqual(get_family_name_errors(self._draft(slot=self.slot)), [])

    def test_finalize_claims_the_slot_for_the_new_crew(self):
        finalize_character(self._draft(slot=self.slot), add_to_roster=True)

        crew = house_for_family(Family.objects.get(name="Saltsiders"))
        self.slot.refresh_from_db()
        self.assertEqual(self.slot.claimed_by, crew)
        self.assertEqual(Turf.objects.get(room_profile=self.corner).controlling_org, crew)
        self.assertEqual(FealtyEdge.objects.get(vassal=crew).liege, self.gang)
