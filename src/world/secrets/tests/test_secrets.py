"""Character Secrets — model invariant + authoring services (#1334, slice 1).

Bio/story stay public; sensitive facts live here. The load-bearing rule is
anchor-scales-with-level: only Level-1 player-flavor may be free-authored, so player flavor can
never masquerade as canon.
"""

from django.core.exceptions import ValidationError
from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.secrets.constants import SecretLevel, SecretProvenance
from world.secrets.factories import SecretCategoryFactory, SecretFactory
from world.secrets.models import Secret
from world.secrets.services import (
    SecretError,
    author_player_flavor_secret,
    author_secret,
)


class SecretModelTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.subject = CharacterSheetFactory()

    def test_gm_secret_may_sit_at_any_level(self) -> None:
        secret = SecretFactory(
            subject_sheet=self.subject,
            provenance=SecretProvenance.GM_AUTHORED,
            level=SecretLevel.DANGEROUS,
        )
        secret.full_clean()  # no raise
        assert secret.level == SecretLevel.DANGEROUS

    def test_action_anchored_secret_may_sit_at_any_level(self) -> None:
        secret = SecretFactory(
            subject_sheet=self.subject,
            provenance=SecretProvenance.ACTION_ANCHORED,
            level=SecretLevel.CAREFULLY_KEPT,
        )
        secret.full_clean()  # no raise

    def test_player_flavor_is_allowed_at_level_one(self) -> None:
        secret = SecretFactory(
            subject_sheet=self.subject,
            provenance=SecretProvenance.PLAYER_FLAVOR,
            level=SecretLevel.UNCOMMON_KNOWLEDGE,
        )
        secret.full_clean()  # no raise

    def test_player_flavor_above_level_one_is_rejected(self) -> None:
        secret = SecretFactory.build(
            subject_sheet=self.subject,
            provenance=SecretProvenance.PLAYER_FLAVOR,
            level=SecretLevel.DANGEROUS,
        )
        with self.assertRaises(ValidationError):
            secret.full_clean()

    def test_category_null_means_unknown(self) -> None:
        secret = SecretFactory(subject_sheet=self.subject, category=None)
        assert secret.category is None  # Unknown is a first-class state

    def test_two_party_secret_names_the_other(self) -> None:
        other = CharacterSheetFactory()
        secret = SecretFactory(subject_sheet=self.subject, second_party_sheet=other)
        assert secret.second_party_sheet_id == other.pk
        # Reverse accessor reaches the implicated party's secrets.
        assert secret in other.implicating_secrets.all()


class AuthorSecretServiceTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.subject = CharacterSheetFactory()
        cls.category = SecretCategoryFactory(name="Scandal")

    def test_author_secret_persists_a_valid_secret(self) -> None:
        secret = author_secret(
            subject_sheet=self.subject,
            provenance=SecretProvenance.GM_AUTHORED,
            level=SecretLevel.DANGEROUS,
            content="She poisoned the duke.",
            category=self.category,
            consequences="Execution if proven.",
        )
        assert Secret.objects.filter(pk=secret.pk).exists()
        assert secret.category_id == self.category.pk

    def test_author_secret_rejects_player_flavor_above_level_one(self) -> None:
        with self.assertRaises(SecretError):
            author_secret(
                subject_sheet=self.subject,
                provenance=SecretProvenance.PLAYER_FLAVOR,
                level=SecretLevel.DANGEROUS,
                content="totally real, trust me",
            )

    def test_author_player_flavor_secret_caps_at_level_one(self) -> None:
        persona = self.subject.primary_persona
        secret = author_player_flavor_secret(
            subject_sheet=self.subject,
            author_persona=persona,
            content="Terrified of the color blue.",
        )
        assert secret.level == SecretLevel.UNCOMMON_KNOWLEDGE
        assert secret.provenance == SecretProvenance.PLAYER_FLAVOR
        assert secret.author_persona_id == persona.pk
