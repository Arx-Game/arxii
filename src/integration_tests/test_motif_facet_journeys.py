"""Journeys: tying imagery (facets) to your magic (#5021).

Ysmay holds the Wildfire resonance. She ties Wolf to it with ``motif bindfacet``, and
the game starts counting it: a flourish staff gated on Wolf shows in ``signature list``
and can be signed, and a carried item bearing Wolf becomes an offering for Wildfire. She
cannot untie Wolf while that signed flourish needs it; once she clears the flourish she
can. The web does the same through ``/api/magic/motif-styles/bind-facet/``, and staff set
or fix the same rows on the Motif Resonance admin page.

Every expected line comes from the issue's spec and the owner's rulings: up to five
facets on one resonance, a facet may sit on several resonances, the resonance must be
claimed, an alias reaches its facet, and removing a facet a signed flourish needs is
refused until the flourish is cleared.
"""

from __future__ import annotations

from evennia.accounts.models import AccountDB

from integration_tests.harness import JourneyCase
from world.items.factories import ItemFacetFactory, ItemInstanceFactory
from world.magic.constants import ComponentMode, TargetKind
from world.magic.factories import (
    CharacterResonanceFactory,
    CharacterTechniqueFactory,
    FacetFactory,
    ResonanceFactory,
    TechniqueFactory,
)
from world.magic.models import (
    FacetAlias,
    MotifResonance,
    MotifResonanceAssociation,
    SignatureMotifBonus,
    Thread,
)
from world.magic.services.drift import qualifying_components

BIND_FACET_URL = "/api/magic/motif-styles/bind-facet/"
UNBIND_FACET_URL = "/api/magic/motif-styles/unbind-facet/"
LIST_URL = "/api/magic/motif-styles/"


class _FacetCase(JourneyCase):
    """Ysmay, who holds Wildfire and knows Frost Lash on a level-3 thread."""

    def setUp(self) -> None:
        super().setUp()
        self.room = self.make_room("The Loom Room")
        self.ysmay = self.make_player("Ysmay", room=self.room)
        self.sheet = self.ysmay.sheet_data
        self.wildfire = ResonanceFactory(name="Wildfire")
        self.tidewater = ResonanceFactory(name="Tidewater")
        CharacterResonanceFactory(character_sheet=self.sheet, resonance=self.wildfire)
        self.wolf = FacetFactory(name="Wolf")
        FacetAlias.objects.create(facet=self.wolf, name="Wolves")

    def facets_on(self, resonance) -> list[str]:
        return sorted(
            MotifResonanceAssociation.objects.filter(
                motif_resonance__motif__character=self.sheet,
                motif_resonance__resonance=resonance,
            ).values_list("facet__name", flat=True)
        )


class TyingAFacetOverTelnet(_FacetCase):
    def test_she_ties_wolf_by_its_alias_and_sees_it_listed(self) -> None:
        told = self.telnet(self.ysmay, "motif bindfacet Wolves=Wildfire")

        self.assertIn("Wolf is now tied to your Wildfire resonance.", told)
        self.assertEqual(self.facets_on(self.wildfire), ["Wolf"])
        listing = self.telnet(self.ysmay, "motif")
        self.assertIn("Your facets:", listing)
        self.assertIn("Wildfire: Wolf", listing)

    def test_tying_it_twice_changes_nothing(self) -> None:
        self.telnet(self.ysmay, "motif bindfacet Wolf=Wildfire")
        told = self.telnet(self.ysmay, "motif bindfacet Wolf=Wildfire")

        self.assertIn("Wolf is now tied to your Wildfire resonance.", told)
        self.assertEqual(self.facets_on(self.wildfire), ["Wolf"])

    def test_one_facet_sits_on_two_resonances(self) -> None:
        CharacterResonanceFactory(character_sheet=self.sheet, resonance=self.tidewater)
        self.telnet(self.ysmay, "motif bindfacet Wolf=Wildfire")
        self.telnet(self.ysmay, "motif bindfacet Wolf=Tidewater")

        self.assertEqual(self.facets_on(self.wildfire), ["Wolf"])
        self.assertEqual(self.facets_on(self.tidewater), ["Wolf"])

    def test_a_sixth_facet_is_refused(self) -> None:
        for name in ("Silk", "Scythe", "Red", "Moon", "Ash"):
            FacetFactory(name=name)
            self.telnet(self.ysmay, f"motif bindfacet {name}=Wildfire")

        told = self.telnet(self.ysmay, "motif bindfacet Wolf=Wildfire")

        self.assertIn("You cannot tie any more facets to that resonance.", told)
        self.assertEqual(len(self.facets_on(self.wildfire)), 5)
        self.assertNotIn("Wolf", self.facets_on(self.wildfire))

    def test_an_unclaimed_resonance_is_refused(self) -> None:
        told = self.telnet(self.ysmay, "motif bindfacet Wolf=Tidewater")

        self.assertIn("You have not claimed that resonance.", told)
        self.assertFalse(MotifResonanceAssociation.objects.exists())

    def test_an_unknown_facet_is_refused(self) -> None:
        told = self.telnet(self.ysmay, "motif bindfacet Griffon=Wildfire")

        self.assertIn("There is no facet called 'Griffon'.", told)
        self.assertFalse(MotifResonanceAssociation.objects.exists())

    def test_untying_a_facet_she_never_tied_is_refused(self) -> None:
        told = self.telnet(self.ysmay, "motif unbindfacet Wolf=Wildfire")

        self.assertIn("That facet is not tied to that resonance.", told)

    def test_she_unties_it_again(self) -> None:
        self.telnet(self.ysmay, "motif bindfacet Wolf=Wildfire")

        told = self.telnet(self.ysmay, "motif unbindfacet Wolf=Wildfire")

        self.assertIn("Wolf is no longer tied to your Wildfire resonance.", told)
        self.assertEqual(self.facets_on(self.wildfire), [])


class AFacetGatedFlourishBecomesReachable(_FacetCase):
    """A flourish gated on Wolf appears once Wolf is tied, and holds Wolf while signed."""

    def setUp(self) -> None:
        super().setUp()
        technique = TechniqueFactory(name="Frost Lash", level=1, damage_profile=False)
        CharacterTechniqueFactory(character=self.sheet, technique=technique)
        self.howl = SignatureMotifBonus.objects.create(
            name="Howl of the Pack", required_facet=self.wolf
        )
        self.thread = Thread.objects.create(
            owner=self.sheet,
            resonance=self.wildfire,
            target_kind=TargetKind.TECHNIQUE,
            target_technique=technique,
            name=technique.name,
            level=30,  # stored; shows 3, the flourish's default minimum (#4585)
        )
        self.ysmay.threads.invalidate()

    def test_the_flourish_shows_only_once_wolf_is_tied(self) -> None:
        self.assertNotIn("Howl of the Pack", self.telnet(self.ysmay, "signature list"))

        self.telnet(self.ysmay, "motif bindfacet Wolf=Wildfire")

        self.assertIn("Howl of the Pack", self.telnet(self.ysmay, "signature list"))
        told = self.telnet(self.ysmay, "signature set technique=Frost Lash bonus=Howl of the Pack")
        self.assertIn("Signature bonus 'Howl of the Pack' set on Frost Lash.", told)

    def test_wolf_cannot_be_untied_while_the_signed_flourish_needs_it(self) -> None:
        self.telnet(self.ysmay, "motif bindfacet Wolf=Wildfire")
        self.telnet(self.ysmay, "signature set technique=Frost Lash bonus=Howl of the Pack")

        told = self.telnet(self.ysmay, "motif unbindfacet Wolf=Wildfire")

        self.assertIn(
            "Your Howl of the Pack flourish needs that facet. "
            "Clear the flourish first with 'signature clear'.",
            told,
        )
        self.assertEqual(self.facets_on(self.wildfire), ["Wolf"])

        self.telnet(self.ysmay, "signature clear technique=Frost Lash")
        told = self.telnet(self.ysmay, "motif unbindfacet Wolf=Wildfire")
        self.assertIn("Wolf is no longer tied to your Wildfire resonance.", told)
        self.assertEqual(self.facets_on(self.wildfire), [])

    def test_wolf_can_leave_one_resonance_while_another_still_carries_it(self) -> None:
        CharacterResonanceFactory(character_sheet=self.sheet, resonance=self.tidewater)
        self.telnet(self.ysmay, "motif bindfacet Wolf=Wildfire")
        self.telnet(self.ysmay, "motif bindfacet Wolf=Tidewater")
        self.telnet(self.ysmay, "signature set technique=Frost Lash bonus=Howl of the Pack")

        told = self.telnet(self.ysmay, "motif unbindfacet Wolf=Tidewater")

        self.assertIn("Wolf is no longer tied to your Tidewater resonance.", told)
        self.assertIn("Howl of the Pack", self.telnet(self.ysmay, "signature list"))


class AFacetedItemBecomesAnOffering(_FacetCase):
    def test_a_wolf_pelt_counts_for_wildfire_once_wolf_is_tied(self) -> None:
        pelt = ItemInstanceFactory()
        ItemFacetFactory(item_instance=pelt, facet=self.wolf)
        self.assertEqual(qualifying_components(self.sheet, self.wildfire, [pelt]), [])

        self.telnet(self.ysmay, "motif bindfacet Wolf=Wildfire")

        offered = qualifying_components(self.sheet, self.wildfire, [pelt])
        self.assertEqual([(c.item, c.mode) for c in offered], [(pelt, ComponentMode.FACET)])


class TyingAFacetFromTheBrowser(_FacetCase):
    def client_for_ysmay(self):
        client = self.api(self.account_of(self.ysmay))
        client.credentials(HTTP_X_CHARACTER_ID=str(self.ysmay.pk))
        return client

    def test_bind_list_and_unbind_over_rest(self) -> None:
        client = self.client_for_ysmay()
        body = {"facet_id": self.wolf.pk, "resonance_id": self.wildfire.pk}

        bound = client.post(BIND_FACET_URL, body, format="json")
        self.assertEqual(bound.status_code, 200, bound.content)
        listed = client.get(LIST_URL).json()
        self.assertEqual(
            listed["facet_bindings"],
            [
                {
                    "facet_id": self.wolf.pk,
                    "facet_name": "Wolf",
                    "resonance_id": self.wildfire.pk,
                    "resonance_name": "Wildfire",
                }
            ],
        )
        sheet_motif = client.get(f"/api/character-sheets/{self.sheet.pk}/").json()["magic"]
        self.assertIn("Wolf", str(sheet_motif))

        unbound = client.post(UNBIND_FACET_URL, body, format="json")
        self.assertEqual(unbound.status_code, 200, unbound.content)
        self.assertEqual(client.get(LIST_URL).json()["facet_bindings"], [])

    def test_refusals_are_clean_400s(self) -> None:
        client = self.client_for_ysmay()

        unclaimed = client.post(
            BIND_FACET_URL,
            {"facet_id": self.wolf.pk, "resonance_id": self.tidewater.pk},
            format="json",
        )
        self.assertEqual(unclaimed.status_code, 400)
        self.assertEqual(unclaimed.json()["detail"], "You have not claimed that resonance.")
        no_facet = client.post(
            BIND_FACET_URL, {"facet_id": 999999, "resonance_id": self.wildfire.pk}, format="json"
        )
        self.assertEqual(no_facet.status_code, 400)
        self.assertEqual(no_facet.json()["detail"], "No such facet.")
        self.assertFalse(MotifResonanceAssociation.objects.exists())

    def test_another_players_character_is_out_of_reach(self) -> None:
        hobb = self.make_player("Hobb", room=self.room)
        client = self.api(self.account_of(hobb))
        client.credentials(HTTP_X_CHARACTER_ID=str(self.ysmay.pk))

        response = client.post(
            BIND_FACET_URL,
            {"facet_id": self.wolf.pk, "resonance_id": self.wildfire.pk},
            format="json",
        )

        self.assertEqual(response.status_code, 404)
        self.assertFalse(MotifResonanceAssociation.objects.exists())


class StaffFixFacetsInAdmin(_FacetCase):
    def setUp(self) -> None:
        super().setUp()
        self.telnet(self.ysmay, "motif bindfacet Wolf=Wildfire")
        self.motif_resonance = MotifResonance.objects.get(
            motif__character=self.sheet, resonance=self.wildfire
        )
        staff = AccountDB.objects.create_superuser("facet_staff", "fs@example.com", "pw-123456")
        self.client.force_login(staff)
        self.url = f"/admin/arxii/motifresonance/{self.motif_resonance.pk}/change/"

    def _post(self, facet_rows: list[tuple[int | None, int, bool]]) -> object:
        """Post the change form with the facet inline holding ``(pk, facet_id, delete)``."""
        page = self.client.get(self.url)
        self.assertEqual(page.status_code, 200)
        data = {
            "motif": self.motif_resonance.motif_id,
            "resonance": self.wildfire.pk,
            "is_from_gift": "",
        }
        for inline in page.context["inline_admin_formsets"]:
            formset = inline.formset
            prefix = formset.prefix
            rows = facet_rows if formset.model is MotifResonanceAssociation else []
            data[f"{prefix}-TOTAL_FORMS"] = str(len(rows))
            data[f"{prefix}-INITIAL_FORMS"] = str(sum(1 for pk, _, _ in rows if pk))
            data[f"{prefix}-MIN_NUM_FORMS"] = "0"
            data[f"{prefix}-MAX_NUM_FORMS"] = "1000"
            for index, (pk, facet_id, delete) in enumerate(rows):
                data[f"{prefix}-{index}-id"] = str(pk or "")
                data[f"{prefix}-{index}-motif_resonance"] = str(self.motif_resonance.pk)
                data[f"{prefix}-{index}-facet"] = str(facet_id)
                if delete:
                    data[f"{prefix}-{index}-DELETE"] = "on"
        return self.client.post(self.url, data)

    def test_staff_add_red_and_remove_wolf(self) -> None:
        red = FacetFactory(name="Red")
        wolf_row = MotifResonanceAssociation.objects.get(facet=self.wolf)

        response = self._post([(wolf_row.pk, self.wolf.pk, True), (None, red.pk, False)])

        self.assertEqual(response.status_code, 302, response.content[:2000])
        self.assertEqual(self.facets_on(self.wildfire), ["Red"])

    def test_a_sixth_row_is_refused_with_the_cap(self) -> None:
        wolf_row = MotifResonanceAssociation.objects.get(facet=self.wolf)
        others = [FacetFactory(name=n) for n in ("Silk", "Scythe", "Red", "Moon", "Ash")]

        response = self._post(
            [(wolf_row.pk, self.wolf.pk, False)] + [(None, f.pk, False) for f in others]
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Maximum 5 facets per resonance.")
        self.assertEqual(self.facets_on(self.wildfire), ["Wolf"])


class PickingFacetsInCreation(JourneyCase):
    """A new player picks Wolf for her gift resonance in the Gift stage (#5021, slice 2).

    Over the REST seam the browser uses (the draft PATCH and ``personalization-options``),
    then the finalize step that writes the new character's magic.
    """

    DRAFTS = "/api/character-creation/drafts/"

    def setUp(self) -> None:
        super().setUp()
        from evennia_extensions.factories import AccountFactory
        from world.character_creation.factories import CharacterDraftFactory
        from world.magic.factories import (
            GiftFactory,
            SignatureMotifBonusFactory,
            ensure_canonical_affinities,
        )

        ensure_canonical_affinities()
        self.frost = ResonanceFactory(name="Frost")
        self.wolf = FacetFactory(name="Wolf")
        self.silk = FacetFactory(name="Silk")
        gift = GiftFactory(name="Ember")
        self.technique = TechniqueFactory(gift=gift, name="Scorch Lash", level=1)
        self.howl = SignatureMotifBonusFactory(
            name="Howl of the Pack",
            required_facet=self.wolf,
            required_resonance=None,
            min_crossing_level=10,
            creation_point_cost=3,
        )
        self.account = AccountFactory()
        self.client_api = self.api(self.account)
        self.draft = CharacterDraftFactory(
            account=self.account,
            draft_data={
                "selected_gift_id": gift.pk,
                "selected_technique_ids": [self.technique.pk],
                "selected_gift_resonance_id": self.frost.pk,
            },
        )

    def offered_flourishes(self) -> list[str]:
        response = self.client_api.get(f"{self.DRAFTS}{self.draft.pk}/personalization-options/")
        self.assertEqual(response.status_code, 200, response.content)
        return [f["name"] for f in response.json()[0]["flourishes"]]

    def pick_errors(self) -> list[str]:
        """What the Gift stage's validation says of the draft's flourish pick now."""
        from world.character_creation.constants import (
            GIFT_FACETS_KEY,
            TECHNIQUE_PERSONALIZATIONS_KEY,
        )
        from world.magic.services.creation_personalization import (
            parse_personalization_picks,
            personalization_pick_errors,
        )

        self.draft.refresh_from_db()
        data = self.draft.draft_data
        picks = parse_personalization_picks(
            data.get(TECHNIQUE_PERSONALIZATIONS_KEY), technique_ids=[self.technique.pk]
        )
        return personalization_pick_errors(
            picks,
            techniques=[self.technique],
            resonance_id=self.frost.pk,
            facet_ids=data.get(GIFT_FACETS_KEY) or [],
        )

    def patch_draft(self, draft_data: dict):
        return self.client_api.patch(
            f"{self.DRAFTS}{self.draft.pk}/", {"draft_data": draft_data}, format="json"
        )

    def test_picking_wolf_offers_the_wolf_flourish_and_finalize_ties_and_signs_it(self) -> None:
        from world.character_creation.constants import TECHNIQUE_PERSONALIZATIONS_KEY
        from world.character_creation.services import finalize_magic_data
        from world.character_sheets.factories import CharacterSheetFactory
        from world.magic.factories import TraditionFactory

        self.assertNotIn("Howl of the Pack", self.offered_flourishes())

        response = self.patch_draft({"selected_gift_facet_ids": [self.wolf.pk]})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertIn("Howl of the Pack", self.offered_flourishes())

        pick = {str(self.technique.pk): {"signature_bonus_id": self.howl.pk}}
        response = self.patch_draft({TECHNIQUE_PERSONALIZATIONS_KEY: pick})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(self.pick_errors(), [])
        self.draft.refresh_from_db()

        self.draft.selected_tradition = TraditionFactory()
        self.draft.save()
        sheet = CharacterSheetFactory()
        finalize_magic_data(self.draft, sheet)

        self.assertEqual(
            list(
                MotifResonanceAssociation.objects.filter(
                    motif_resonance__motif__character=sheet
                ).values_list("motif_resonance__resonance__name", "facet__name")
            ),
            [("Frost", "Wolf")],
        )
        thread = Thread.objects.get(owner=sheet, target_technique=self.technique)
        self.assertEqual(thread.signature_bonus, self.howl)

    def test_dropping_wolf_makes_the_flourish_pick_stale(self) -> None:
        from world.character_creation.constants import TECHNIQUE_PERSONALIZATIONS_KEY

        pick = {str(self.technique.pk): {"signature_bonus_id": self.howl.pk}}
        self.patch_draft(
            {"selected_gift_facet_ids": [self.wolf.pk], TECHNIQUE_PERSONALIZATIONS_KEY: pick}
        )
        self.patch_draft({"selected_gift_facet_ids": [self.silk.pk]})

        self.assertNotIn("Howl of the Pack", self.offered_flourishes())
        self.assertEqual(
            self.pick_errors(), ["A chosen signature flourish is no longer available."]
        )

    def test_six_facets_or_an_unknown_one_are_refused(self) -> None:
        many = [FacetFactory(name=n).pk for n in ("A", "B", "C", "D", "E", "F")]
        response = self.patch_draft({"selected_gift_facet_ids": many})
        self.assertEqual(response.status_code, 400)
        self.assertIn("Choose at most 5 facets.", str(response.json()))

        response = self.patch_draft({"selected_gift_facet_ids": [999999]})
        self.assertEqual(response.status_code, 400)
        self.assertIn("A chosen facet no longer exists.", str(response.json()))
