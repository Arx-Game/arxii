"""Staff edit mode, piece B: the rows CG writes, on a sheet that never went through CG (#4221)."""

from __future__ import annotations

from django.test import TestCase
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory
from world.character_creation.factories import BeginningsFactory
from world.character_creation.sheet_writers import (
    SheetWriteError,
    creation_beginnings,
    set_beginnings,
    set_enemy,
    set_skill_values,
    set_stat_values,
    set_true_form_values,
    set_worship_declaration,
)
from world.character_sheets.factories import GenderFactory
from world.character_sheets.types import EnemyDegree, EnemyKind, EnemyPowerTier
from world.distinctions.factories import DistinctionFactory
from world.distinctions.models import CharacterDistinction, SheetUpdateRequest
from world.distinctions.staff import (
    staff_add_distinction,
    staff_remove_distinction,
    staff_set_distinction_rank,
)
from world.distinctions.types import DistinctionOrigin
from world.forms.factories import FormTraitFactory, FormTraitOptionFactory
from world.forms.models import CharacterForm, CharacterFormValue, FormType
from world.roster.factories import PlayerDataFactory, RosterEntryFactory, RosterTenureFactory
from world.skills.factories import SkillFactory, SpecializationFactory
from world.skills.models import CharacterSkillValue, CharacterSpecializationValue
from world.traits.factories import StatTraitFactory
from world.traits.models import CharacterTraitChange, CharacterTraitValue, TraitChangeSource
from world.vitals.models import CharacterVitals
from world.worship.factories import WorshippedBeingFactory
from world.worship.models import WorshipDeclaration


class BareSheetServiceTests(TestCase):
    """Each writer creates what a bare sheet lacks and updates what it holds."""

    def setUp(self) -> None:
        self.sheet = RosterEntryFactory().character_sheet

    def test_stats_create_then_update_with_staff_provenance(self) -> None:
        strength = StatTraitFactory(name="strength_b")
        set_stat_values(self.sheet, {strength: 3}, source=TraitChangeSource.STAFF_EDIT)
        set_stat_values(self.sheet, {strength: 4}, source=TraitChangeSource.STAFF_EDIT)
        row = CharacterTraitValue.objects.get(character=self.sheet, trait=strength)
        assert row.value == 40
        sources = set(
            CharacterTraitChange.objects.filter(
                character_sheet=self.sheet, trait=strength
            ).values_list("source", flat=True)
        )
        assert sources == {TraitChangeSource.STAFF_EDIT}

    def test_stats_keep_their_range(self) -> None:
        with self.assertRaises(SheetWriteError):
            set_stat_values(
                self.sheet,
                {StatTraitFactory(name="wits_b"): 9},
                source=TraitChangeSource.STAFF_EDIT,
            )

    def test_skills_write_the_trait_row_checks_read_and_keep_the_cap(self) -> None:
        skill = SkillFactory()
        spec = SpecializationFactory(parent_skill=skill)
        set_skill_values(self.sheet, {skill: 20}, {spec: 10}, source=TraitChangeSource.STAFF_EDIT)
        assert CharacterSkillValue.objects.get(character=self.sheet, skill=skill).value == 20
        assert (
            CharacterSpecializationValue.objects.get(
                character=self.sheet, specialization=spec
            ).value
            == 10
        )
        assert CharacterTraitValue.objects.get(character=self.sheet, trait=skill.trait).value == 20
        with self.assertRaises(SheetWriteError):
            set_skill_values(self.sheet, {skill: 999}, {}, source=TraitChangeSource.STAFF_EDIT)

    def test_true_form_is_created_then_updated(self) -> None:
        hair = FormTraitFactory(name="hair_b")
        red = FormTraitOptionFactory(trait=hair, name="red_b")
        black = FormTraitOptionFactory(trait=hair, name="black_b")
        set_true_form_values(self.sheet, {hair: red})
        set_true_form_values(self.sheet, {hair: black})
        form = CharacterForm.objects.get(character=self.sheet, form_type=FormType.TRUE)
        value = CharacterFormValue.objects.get(form=form, trait=hair)
        assert (value.option, value.natural_option) == (black, black)
        with self.assertRaises(SheetWriteError):
            set_true_form_values(self.sheet, {FormTraitFactory(name="eyes_b"): red})

    def test_one_creation_beginnings_at_a_time(self) -> None:
        first, second = BeginningsFactory(), BeginningsFactory()
        set_beginnings(self.sheet, first)
        set_beginnings(self.sheet, second)
        assert creation_beginnings(self.sheet) == second

    def test_worship_creates_then_updates(self) -> None:
        public, secret = WorshippedBeingFactory(), WorshippedBeingFactory()
        set_worship_declaration(self.sheet, public, None)
        set_worship_declaration(self.sheet, public, secret)
        declaration = WorshipDeclaration.objects.get(character_sheet=self.sheet)
        assert (declaration.public_being, declaration.secret_being) == (public, secret)

    def test_enemy_row_is_validated_for_staff(self) -> None:
        enemy = set_enemy(
            self.sheet,
            kind=EnemyKind.PERSON,
            figure_name="The Pale Duke",
            power_tier=EnemyPowerTier.values[0],
            degree=EnemyDegree.values[0],
            price=0,
        )
        assert enemy.figure_name == "The Pale Duke"
        with self.assertRaises(SheetWriteError):
            set_enemy(self.sheet, enemy=enemy, degree="not-a-degree")


class StaffDistinctionTests(TestCase):
    def setUp(self) -> None:
        self.sheet = RosterEntryFactory().character_sheet

    def test_add_rank_and_remove_with_no_request(self) -> None:
        distinction = DistinctionFactory(max_rank=3)
        held = staff_add_distinction(self.sheet, distinction, rank=2)
        assert (held.rank, held.origin) == (2, DistinctionOrigin.STAFF)
        staff_set_distinction_rank(held, 1)
        held.refresh_from_db()
        assert held.rank == 1
        staff_remove_distinction(held)
        assert not CharacterDistinction.objects.filter(character=self.sheet).exists()
        assert not SheetUpdateRequest.objects.filter(character_sheet=self.sheet).exists()

    def test_rank_out_of_range_is_refused(self) -> None:
        held = staff_add_distinction(self.sheet, DistinctionFactory(max_rank=2))
        with self.assertRaises(SheetWriteError):
            staff_set_distinction_rank(held, 3)


class StaffRowEndpointTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.staff = AccountFactory(is_staff=True)
        cls.player = PlayerDataFactory()
        cls.entry = RosterEntryFactory()
        RosterTenureFactory(player_data=cls.player, roster_entry=cls.entry, player_number=1)
        cls.sheet = cls.entry.character_sheet
        cls.base = f"/api/character-sheets/{cls.sheet.pk}"

    def setUp(self) -> None:
        self.client = APIClient()

    def test_stats_endpoint_writes_fills_vitals_and_answers_with_the_sheet(self) -> None:
        strength = StatTraitFactory(name="strength_e")
        self.client.force_authenticate(user=self.staff)
        response = self.client.patch(
            f"{self.base}/staff-stats/", {"stats": {str(strength.pk): 2}}, format="json"
        )
        assert response.status_code == 200, response.content[:800]
        assert response.data["id"] == self.sheet.pk
        assert CharacterTraitValue.objects.get(character=self.sheet, trait=strength).value == 20
        assert CharacterVitals.objects.filter(character_sheet=self.sheet).exists()

    def test_the_owner_gets_a_404(self) -> None:
        self.client.force_authenticate(user=self.player.account)
        for method, path in (
            ("patch", "staff-stats"),
            ("patch", "staff-skills"),
            ("post", "staff-distinctions"),
            ("put", "staff-beginnings"),
            ("post", "staff-vitals"),
        ):
            response = getattr(self.client, method)(f"{self.base}/{path}/", {}, format="json")
            assert response.status_code == 404, path

    def test_distinction_add_then_remove_through_the_api(self) -> None:
        distinction = DistinctionFactory()
        self.client.force_authenticate(user=self.staff)
        response = self.client.post(
            f"{self.base}/staff-distinctions/", {"distinction": distinction.pk}, format="json"
        )
        assert response.status_code == 200, response.content[:800]
        held = CharacterDistinction.objects.get(character=self.sheet, distinction=distinction)
        response = self.client.patch(
            f"{self.base}/staff-distinction/", {"character_distinction": held.pk}, format="json"
        )
        assert response.status_code == 200, response.content[:800]
        assert not CharacterDistinction.objects.filter(pk=held.pk).exists()

    def test_a_gender_edit_sets_the_pronoun_forms(self) -> None:
        female = GenderFactory(key="female")
        self.client.force_authenticate(user=self.staff)
        response = self.client.patch(
            f"{self.base}/staff-edit/", {"gender": female.pk}, format="json"
        )
        assert response.status_code == 200, response.content[:800]
        self.sheet.refresh_from_db()
        assert self.sheet.pronoun_subject == "she"


class StaffRowsPayloadTests(TestCase):
    def test_the_payload_lists_held_rows_by_id_and_options_serve_the_pickers(self) -> None:
        staff = AccountFactory(is_staff=True)
        sheet = RosterEntryFactory().character_sheet
        strength = StatTraitFactory(name="strength_p")
        set_stat_values(sheet, {strength: 3}, source=TraitChangeSource.STAFF_EDIT)
        held = staff_add_distinction(sheet, DistinctionFactory())
        client = APIClient()
        client.force_authenticate(user=staff)

        rows = client.get(f"/api/character-sheets/{sheet.pk}/").data["staff_edit"]["rows"]
        assert rows["stats"] == {strength.pk: 3}
        assert [row["id"] for row in rows["distinctions"]] == [held.pk]
        assert rows["has_vitals"] is False

        options = client.get(f"/api/character-sheets/{sheet.pk}/staff-options/")
        assert options.status_code == 200, options.content[:400]
        assert {"id": strength.pk, "name": strength.name} in options.data["stats"]
        assert options.data["form_traits"] == []
