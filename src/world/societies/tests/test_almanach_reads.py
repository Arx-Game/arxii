"""Tests for the Almanach de Catenys read payloads (#3983): the ladder, the
house document, and the realm charter (Plan B Task 3)."""

from django.test import TestCase

from world.areas.constants import AreaLevel
from world.areas.factories import AreaFactory
from world.character_creation.factories import RealmFactory
from world.roster.constants import NOBLE_KIND_NAME, MembershipBasis
from world.roster.factories import FamilyFactory, FamilyKindFactory, KinspersonFactory
from world.roster.services.kinship import add_membership
from world.societies.factories import OrganizationFactory, VacancyFactory
from world.societies.houses.almanach import (
    add_household_member,
    assign_holder,
    batch_unclaimed,
    name_rung,
    plant_rung,
    publish_house,
)
from world.societies.houses.almanach_reads import (
    charter_for_realm,
    document_for_house,
    ladder_for_realm,
)
from world.societies.houses.constants import SuccessionDerivation, TitleTier
from world.societies.houses.models import (
    HouseAspectDefinition,
    HouseTemplate,
    NobiliaryParticle,
    SuccessionLaw,
    Title,
)


class LadderReadTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.realm = RealmFactory(name="Inferna")
        cls.crown = OrganizationFactory(name="Piropa")
        cls.kingdom = plant_rung(
            realm=cls.realm, tier=TitleTier.KINGDOM, name="Inferna", held_by=cls.crown
        )
        cls.fervor = plant_rung(
            realm=cls.realm, tier=TitleTier.DUCHY, name="Fervor", parent_title=cls.kingdom
        )
        batch_unclaimed(
            parent_title=cls.fervor, tier=TitleTier.COUNTY, count=2, baronies_per_county=1
        )
        publish_house(cls.crown)
        # Fervor's own internal chain member (unnamed by plant_rung) — named
        # here so a chain-member row (not a chain top) can be asserted on.
        cls.arsura = Title.objects.get(tier=TitleTier.COUNTY, seat_domain=cls.fervor.seat_domain)
        name_rung(cls.arsura, "Arsura")

    def test_rows_carry_state_sworn_to_demesne_and_vassals(self) -> None:
        payload = ladder_for_realm(self.realm)
        by_name = {r.name: r for r in payload.rows if r.name}
        fervor = by_name["Fervor"]
        arsura = by_name["Arsura"]
        assert fervor.state == "Unclaimed"
        assert fervor.claimable
        assert fervor.sworn_to == "Piropa"
        assert fervor.demesne == 1, "the seat barony of its seat county"
        assert fervor.vassals == 2, "two unclaimed counties beneath"
        assert payload.unclaimed_by_tier[TitleTier.COUNTY] == 2
        expected_baronies = 2 + 1 + 1  # vassal baronies + seat baronies of unclaimed rungs
        assert payload.unclaimed_by_tier[TitleTier.BARONY] == expected_baronies
        seat = next(r for r in payload.rows if r.is_seat_of == "Piropa")
        assert seat.tier == TitleTier.BARONY
        # comes_with: a chain member reports its chain top's name; the top
        # itself reports "".
        assert arsura.comes_with == "Fervor"
        assert fervor.comes_with == ""
        # seat_domain_id: every title on one chain shares the same value.
        assert arsura.seat_domain_id == fervor.seat_domain_id
        chain_rows = [r for r in payload.rows if r.seat_domain_id == fervor.seat_domain_id]
        assert len(chain_rows) == 3, "Fervor's duchy, county (Arsura) and barony"
        # chain_top_id is what a client groups a chain by: every member
        # points at the top, and the top points at itself. Unlike
        # ``comes_with`` (a NAME) it survives an undefined top.
        assert fervor.chain_top_id == fervor.title_id
        assert all(r.chain_top_id == fervor.title_id for r in chain_rows)

    def test_an_undefined_chain_top_still_groups_its_own_chain(self) -> None:
        """#3983 review I5: ``comes_with`` is the top's name, so it is "" for
        an undefined duchy and name-matching silently lost the whole chain —
        exactly the rows a founder claiming an undefined slot must see."""
        undefined_duchy = plant_rung(
            realm=self.realm, tier=TitleTier.DUCHY, name="", parent_title=self.kingdom
        )
        payload = ladder_for_realm(self.realm)
        chain = [r for r in payload.rows if r.chain_top_id == undefined_duchy.pk]
        assert len(chain) == 3, "the undefined duchy, its county and its seat barony"
        assert {r.tier for r in chain} == {
            TitleTier.DUCHY,
            TitleTier.COUNTY,
            TitleTier.BARONY,
        }
        assert all(r.comes_with == "" for r in chain), "the name-keyed field cannot do this"

    def test_a_contested_title_reports_its_claimant(self) -> None:
        """Deferred item 2: the plate's "Brasa · Luxen · claimed · Piropa"
        row. The write path is the hidden-heir work; the read is here."""
        luxen = OrganizationFactory(name="Luxen")
        brasa = plant_rung(
            realm=self.realm,
            tier=TitleTier.DUCHY,
            name="Brasa",
            parent_title=self.kingdom,
            held_by=luxen,
        )
        brasa.claimant_org = self.crown
        brasa.save(update_fields=["claimant_org"])
        payload = ladder_for_realm(self.realm)
        row = next(r for r in payload.rows if r.title_id == brasa.pk)
        assert row.claimant_name == "Piropa"
        assert all(r.claimant_name == "" for r in payload.rows if r.title_id != brasa.pk)

    def test_founder_ladder_hides_unpublished_houses(self) -> None:
        other = OrganizationFactory(name="Solano")
        ardor = plant_rung(
            realm=self.realm,
            tier=TitleTier.COUNTY,
            name="Ardor",
            parent_title=self.kingdom,
            held_by=other,
        )
        founder = ladder_for_realm(self.realm, for_founder=True)
        assert all(r.house_name != "Solano" for r in founder.rows)
        assign_holder(ardor, other)
        publish_house(other)
        founder = ladder_for_realm(self.realm, for_founder=True)
        assert any(r.house_name == "Solano" for r in founder.rows)


class DocumentReadTests(TestCase):
    def test_document_folds_lands_and_lists_vassals(self) -> None:
        realm = RealmFactory(name="Inferna", default_tithe_pct=10, theme="luxen")
        crown = OrganizationFactory(name="Piropa")
        # The document's realm block reads the house's OWN realm (through its
        # society, ``realm_for_house`` — the same seam the particle and the
        # tithe already use), so the fixture seats the crown in the realm its
        # titles lie in rather than the factory's incidental one.
        crown.society.realm = realm
        crown.society.save(update_fields=["realm"])
        plant_rung(realm=realm, tier=TitleTier.KINGDOM, name="Inferna", held_by=crown)
        doc = document_for_house(crown, viewer=None, staff=True)
        assert doc.house["name"] == "Piropa"
        assert doc.lands["count"] == 1
        assert doc.lands["baronies"][0]["is_seat"] is True
        assert doc.realm["holds"] == "Inferna"
        # The realm itself, so the document can prefill a tithe, link the
        # ladder, and know whether Gentry is a standing this realm offers.
        assert doc.realm["realm_id"] == realm.pk
        assert doc.realm["default_tithe_pct"] == realm.default_tithe_pct
        assert doc.realm["realm_theme"] == realm.theme

    def test_a_societyless_house_still_reports_the_realm_keys(self) -> None:
        """An org outside any society (a covenant) has no realm standing at
        all; the block keeps its shape so no reader tests for the key."""
        wanderers = OrganizationFactory(name="Wanderers", society=None)
        doc = document_for_house(wanderers, viewer=None, staff=True)
        assert doc.realm["realm_id"] is None
        assert doc.realm["default_tithe_pct"] == 0
        assert doc.realm["realm_theme"] == ""

    def test_household_lists_retainers_and_excludes_kin_vacancies(self) -> None:
        realm = RealmFactory(name="Inferna")
        family = FamilyFactory(name="House Piropa")
        crown = OrganizationFactory(name="Piropa", family=family)
        plant_rung(realm=realm, tier=TitleTier.KINGDOM, name="Inferna", held_by=crown)
        ward = KinspersonFactory(name="Marisol")
        ward_vacancy = add_household_member(house=crown, kinsperson=ward)
        kin = KinspersonFactory(name="Cousin", family=family)
        VacancyFactory(
            organization=crown, name="Cousin's Claim", rank=ward_vacancy.rank, kin_node=kin
        )
        doc = document_for_house(crown, viewer=None, staff=True)
        holder_names = {row["holder_name"] for row in doc.household}
        positions = {row["position"] for row in doc.household}
        assert "Marisol" in holder_names
        assert "Cousin's Claim" not in positions

    def test_the_staff_document_carries_truth_and_public_belief(self) -> None:
        """#3983 spec Testing (3), the staff side: the document is staff-only
        and reads the family with the omniscient viewer, so a believed death
        shows as a living person the world thinks is dead."""
        realm = RealmFactory(name="Inferna")
        family = FamilyFactory(name="House Brasa")
        crown = OrganizationFactory(name="Brasa", family=family)
        plant_rung(realm=realm, tier=TitleTier.KINGDOM, name="Inferna", held_by=crown)
        heir = KinspersonFactory(name="Living Heir", believed_deceased=True)
        add_membership(kinsperson=heir, family=family, basis=MembershipBasis.BORN)

        doc = document_for_house(crown, viewer=None, staff=True)
        node = next(n for n in doc.family["nodes"] if n["id"] == heir.pk)
        assert node["is_deceased"] is False
        assert node["believed_deceased"] is True

    def test_realm_demesne_and_vassals_reach_beyond_the_top_chain(self) -> None:
        realm = RealmFactory(name="Inferna")
        crown = OrganizationFactory(name="Piropa")
        other = OrganizationFactory(name="Solano")
        kingdom = plant_rung(realm=realm, tier=TitleTier.KINGDOM, name="Inferna", held_by=crown)
        # Plant the county unclaimed and Seawatch under it (so Seawatch's own
        # liege walk resolves straight past the unclaimed county to the
        # crown, matching held_by=crown with no swear_fealty call at all),
        # then seat "other" on the county directly on the Title rows. Going
        # through assign_holder here would call swear_fealty(vassal=crown,
        # liege=other) - a genuine cycle (other's own liege is already crown
        # from the county's own creation), correctly refused by the write
        # side's cycle guard (#3983 Task 1-3) - and orthogonal to what this
        # read-layer test exercises.
        county = plant_rung(
            realm=realm, tier=TitleTier.COUNTY, name="Ardor", parent_title=kingdom, held_by=None
        )
        plant_rung(
            realm=realm,
            tier=TitleTier.BARONY,
            name="Seawatch",
            parent_title=county,
            held_by=crown,
        )
        for member in Title.objects.filter(seat_domain_id=county.seat_domain_id):
            member.house = other
            member.is_claimable = False
            member.save(update_fields=["house", "is_claimable"])

        doc = document_for_house(crown, viewer=None, staff=True)
        demesne_names = {row["name"] for row in doc.realm["demesne"]}
        assert "Seawatch" in demesne_names, "a barony held directly inside a vassal's county"
        assert len(doc.realm["vassals"]) == 1, "the vassal house, once"
        assert doc.realm["vassals"][0]["held_by"] == "Solano"


class CharterReadTests(TestCase):
    """#3983 Plan B Task 3: the founder ladder's realm-level defaults."""

    def test_charter_reads_the_tierless_templates_law_and_blank_floor_particle(self) -> None:
        realm = RealmFactory(name="Inferna")
        crown = OrganizationFactory(name="Piropa")
        kind = FamilyKindFactory(name=NOBLE_KIND_NAME)
        tiered_law = SuccessionLaw.objects.create(
            name="Tiered Law", derivation=SuccessionDerivation.PRIMOGENITURE_WEDLOCK
        )
        tierless_law = SuccessionLaw.objects.create(
            name="Tierless Law", derivation=SuccessionDerivation.PRIMOGENITURE_WEDLOCK
        )
        HouseTemplate.objects.create(
            name="Tiered Charter",
            realm=realm,
            tier=TitleTier.DUCHY,
            kind=kind,
            society=crown.society,
            org_type=crown.org_type,
            liege=crown,
            default_succession_law=tiered_law,
        )
        tierless_template = HouseTemplate.objects.create(
            name="Tierless Charter",
            realm=realm,
            kind=kind,
            society=crown.society,
            org_type=crown.org_type,
            liege=crown,
            default_succession_law=tierless_law,
        )
        quiddity = HouseAspectDefinition.objects.create(
            name="Charter Quiddity", prompt="Which virtue rules the house?"
        )
        tierless_template.aspect_definitions.add(quiddity)
        # A banded particle that must NOT win over the blank-floor default.
        NobiliaryParticle.objects.create(
            realm=realm, kind=kind, tier_floor=TitleTier.DUCHY, particle="du"
        )
        NobiliaryParticle.objects.create(
            realm=realm, kind=kind, particle="de", taken_in_particle="d'"
        )
        AreaFactory(level=AreaLevel.CITY, realm=realm, is_capital=True, name="Piropa City")

        charter = charter_for_realm(realm)
        assert charter.succession_law == {"name": "Tierless Law", "codex_entry_id": None}
        assert charter.particle == {"born": "de", "taken_in": "d'"}
        assert charter.quiddity_prompt == "Which virtue rules the house?"
        assert charter.capital_name == "Piropa City"

    def test_charter_falls_back_to_the_first_template_when_none_is_tierless(self) -> None:
        realm = RealmFactory(name="Umbros")
        crown = OrganizationFactory(name="Solano")
        kind = FamilyKindFactory(name=NOBLE_KIND_NAME)
        only_law = SuccessionLaw.objects.create(
            name="Only Law", derivation=SuccessionDerivation.PRIMOGENITURE_WEDLOCK
        )
        HouseTemplate.objects.create(
            name="Only Charter",
            realm=realm,
            tier=TitleTier.BARONY,
            kind=kind,
            society=crown.society,
            org_type=crown.org_type,
            liege=crown,
            default_succession_law=only_law,
        )
        charter = charter_for_realm(realm)
        assert charter.succession_law == {"name": "Only Law", "codex_entry_id": None}
        assert charter.particle == {"born": "", "taken_in": ""}
        assert charter.quiddity_prompt == ""
        assert charter.capital_name == ""

    def test_charter_with_no_authored_rows_is_all_blank(self) -> None:
        realm = RealmFactory(name="Charterless Realm")
        charter = charter_for_realm(realm)
        assert charter.succession_law is None
        assert charter.particle == {"born": "", "taken_in": ""}
        assert charter.quiddity_prompt == ""
        assert charter.capital_name == ""
