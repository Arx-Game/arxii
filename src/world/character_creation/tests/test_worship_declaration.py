"""CG worship declaration tests (#2355): finalization + secret mint + leak."""

from django.test import TestCase

from world.character_creation.services import _create_worship_declaration
from world.character_sheets.factories import CharacterSheetFactory
from world.secrets.models import Secret
from world.worship.factories import WorshippedBeingFactory
from world.worship.models import PatronageValence, WorshipDeclaration
from world.worship.services import establish_patronage


class _DraftStub:
    """The narrow draft surface _create_worship_declaration reads."""

    def __init__(self, public=None, secret=None) -> None:
        self.public_worship = public
        self.public_worship_id = public.pk if public else None
        self.secret_worship = secret
        self.secret_worship_id = secret.pk if secret else None


class WorshipDeclarationFinalizationTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.public = WorshippedBeingFactory()
        cls.dark = WorshippedBeingFactory()

    def _character(self):
        sheet = CharacterSheetFactory()
        return sheet.character, sheet

    def test_no_picks_creates_nothing(self) -> None:
        character, sheet = self._character()
        _create_worship_declaration(character, _DraftStub())
        self.assertFalse(WorshipDeclaration.objects.filter(character_sheet=sheet).exists())

    def test_public_only_creates_declaration_without_secret(self) -> None:
        character, sheet = self._character()
        _create_worship_declaration(character, _DraftStub(public=self.public))
        declaration = WorshipDeclaration.objects.get(character_sheet=sheet)
        self.assertEqual(declaration.public_being, self.public)
        self.assertIsNone(declaration.secret_being)
        self.assertIsNone(declaration.secret)
        self.assertFalse(Secret.objects.filter(subject_sheet=sheet).exists())

    def test_secret_pick_mints_secret(self) -> None:
        character, sheet = self._character()
        _create_worship_declaration(character, _DraftStub(public=self.public, secret=self.dark))
        declaration = WorshipDeclaration.objects.get(character_sheet=sheet)
        self.assertEqual(declaration.secret_being, self.dark)
        self.assertIsNotNone(declaration.secret)
        self.assertIn(self.dark.name, declaration.secret.content)
        self.assertEqual(declaration.secret.subject_sheet, sheet)

    def test_secret_equal_to_public_collapses_to_public_only(self) -> None:
        character, sheet = self._character()
        _create_worship_declaration(character, _DraftStub(public=self.public, secret=self.public))
        declaration = WorshipDeclaration.objects.get(character_sheet=sheet)
        self.assertIsNone(declaration.secret_being)
        self.assertIsNone(declaration.secret)

    def test_identity_section_exposes_public_name_only(self) -> None:
        from world.character_sheets.serializers import _build_identity

        character, sheet = self._character()
        _create_worship_declaration(character, _DraftStub(public=self.public, secret=self.dark))
        character.cached_path_history = []  # the viewset prefetch normally sets this
        identity = _build_identity(sheet)
        self.assertEqual(identity["worship"]["name"], self.public.name)
        self.assertNotIn(self.dark.name, str(identity))


class PatronageEstablishmentTests(TestCase):
    """Patronage establishment from a worship declaration (#2550).

    The CG finalization hook calls ``establish_patronage`` when the character's
    path is Path of the Chosen. These tests verify the service-level behavior
    that the hook relies on.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        cls.being = WorshippedBeingFactory()
        cls.sheet = CharacterSheetFactory()

    def test_establish_patronage_creates_devotion_standing_with_valence(self) -> None:
        standing = establish_patronage(self.sheet, self.being, valence=PatronageValence.DEVOTIONAL)
        self.assertEqual(standing.valence, PatronageValence.DEVOTIONAL)
        self.assertIsNotNone(standing.established_at)
        self.assertIsNone(standing.released_at)
        self.assertEqual(standing.favor, 0)  # favor starts at 0 at CG

    def test_non_chosen_devotion_standing_has_null_valence(self) -> None:
        """Ordinary worship (bump_devotion) does not set valence."""
        from world.worship.services import bump_devotion

        standing = bump_devotion(self.sheet, self.being, 10)
        self.assertIsNone(standing.valence)
        self.assertIsNone(standing.established_at)
        self.assertEqual(standing.favor, 10)
