"""Officially dead at creation (#4396): the world meets an established face from day one."""

from django.test import TestCase
from evennia.accounts.models import AccountDB

from world.character_creation.models import CharacterDraft
from world.character_creation.serializers import CharacterDraftSerializer
from world.character_creation.services import finalize_character
from world.character_creation.tests.finalization_fixtures import FinalizationTestMixin
from world.scenes.constants import PersonaType
from world.scenes.models import Persona
from world.scenes.services import active_persona_for_sheet

FACE = {
    "face_name": "Cambria",
    "concept": "A marquessa's widow, lately arrived",
    "quote": "Grief keeps its own hours.",
    "never_do": "Answer to the old name.",
    "protect": "The house that buried me.",
    "fear": "A face from before.",
    "background": "Cambria came to the city with the spring tide.",
}


class OfficiallyDeadFinalizeTests(FinalizationTestMixin, TestCase):
    def setUp(self) -> None:
        self._flush_common_caches()
        self.account = AccountDB.objects.create(username="officially_dead")
        self._setup_finalization_base(
            self, prefix="Officially Dead", height_min=700, height_max=800
        )

    def test_the_face_is_worn_and_the_true_face_is_believed_dead(self) -> None:
        draft = self._create_base_draft(first_name="Kima", officially_dead=FACE)

        character = finalize_character(draft, add_to_roster=True)
        sheet = character.sheet_data

        primary = sheet.primary_persona
        assert primary.believed_deceased is True
        worn = active_persona_for_sheet(sheet)
        assert worn.pk != primary.pk
        assert worn.name == "Cambria"
        assert worn.persona_type == PersonaType.ESTABLISHED
        assert worn.is_fake_name is False
        guise = worn.profile
        assert guise is not None
        assert guise.pk != sheet.true_profile_id
        assert guise.concept == FACE["concept"]
        assert guise.quote == FACE["quote"]
        assert guise.never_do == FACE["never_do"]
        assert guise.protect == FACE["protect"]
        assert guise.fear == FACE["fear"]
        assert guise.background == FACE["background"]
        # The true bio is untouched by the face's texts.
        assert sheet.true_profile.concept != FACE["concept"]
        # The kin node the bind made carries the same belief, so the almanach agrees.
        assert sheet.kinsperson.believed_deceased is True

    def test_a_face_with_a_name_only_wears_an_empty_guise(self) -> None:
        draft = self._create_base_draft(first_name="Kima", officially_dead={"face_name": "Cambria"})
        character = finalize_character(draft, add_to_roster=True)
        worn = active_persona_for_sheet(character.sheet_data)
        assert worn.name == "Cambria"
        assert worn.profile is None

    def test_a_blank_face_name_takes_nothing(self) -> None:
        draft = self._create_base_draft(first_name="Kima", officially_dead={"face_name": "  "})
        character = finalize_character(draft, add_to_roster=True)
        sheet = character.sheet_data
        assert sheet.primary_persona.believed_deceased is False
        assert active_persona_for_sheet(sheet).pk == sheet.primary_persona.pk
        assert Persona.objects.filter(character_sheet=sheet).count() == 1


class OfficiallyDeadDraftValidationTests(TestCase):
    def setUp(self) -> None:
        from world.character_creation.models import StartingArea
        from world.realms.models import Realm

        self.account = AccountDB.objects.create(username="officially_dead_draft")
        realm = Realm.objects.create(name="Test Realm", description="Test realm")
        area = StartingArea.objects.create(
            name="Test Area",
            description="Test area",
            realm=realm,
            access_level=StartingArea.AccessLevel.ALL,
        )
        self.draft = CharacterDraft.objects.create(account=self.account, selected_area=area)

    def _patch(self, value):
        return CharacterDraftSerializer(
            instance=self.draft, data={"draft_data": {"officially_dead": value}}, partial=True
        )

    def test_a_face_and_its_texts_are_accepted_and_null_clears(self) -> None:
        serializer = self._patch(FACE)
        assert serializer.is_valid(), serializer.errors
        assert serializer.save().draft_data["officially_dead"] == FACE
        serializer = self._patch(None)
        assert serializer.is_valid(), serializer.errors
        assert serializer.save().draft_data["officially_dead"] is None

    def test_the_shape_is_checked(self) -> None:
        for bad in ("Cambria", {"face_name": 3}, {"face_name": "Cambria", "rank": "high"}):
            serializer = self._patch(bad)
            assert not serializer.is_valid(), bad
            assert "officially_dead" in str(serializer.errors)
