"""Character Secrets — model invariant + authoring services (#1334, slice 1).

Bio/story stay public; sensitive facts live here. The load-bearing rule is
anchor-scales-with-level: only Level-1 player-flavor may be free-authored, so player flavor can
never masquerade as canon.
"""

from django.core.exceptions import ValidationError
from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.roster.factories import RosterEntryFactory
from world.secrets.constants import SecretLevel, SecretProvenance
from world.secrets.factories import SecretCategoryFactory, SecretFactory
from world.secrets.models import Secret, SecretKnowledge
from world.secrets.services import (
    SecretError,
    author_player_flavor_secret,
    author_secret,
    grant_secret_knowledge,
    secret_known_to,
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

    def test_a_secret_is_owned_by_exactly_one_subject(self) -> None:
        # Single-owner policy: a secret belongs to exactly one character (no shared/group rows).
        secret = SecretFactory(subject_sheet=self.subject)
        assert secret in self.subject.secrets.all()


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


class SecretKnowledgeServiceTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.secret = SecretFactory()
        cls.knower = RosterEntryFactory()

    def test_grant_records_the_fact_layer(self) -> None:
        held = grant_secret_knowledge(roster_entry=self.knower, secret=self.secret)
        assert isinstance(held, SecretKnowledge)
        assert held.knows_category is False  # extra layers stay locked until unlocked
        assert held.knows_consequences is False
        assert secret_known_to(self.secret, self.knower) is True

    def test_grant_is_idempotent_and_layers_are_monotonic(self) -> None:
        grant_secret_knowledge(roster_entry=self.knower, secret=self.secret)
        # Unlock a layer; re-granting without it does NOT re-hide it.
        grant_secret_knowledge(roster_entry=self.knower, secret=self.secret, knows_category=True)
        grant_secret_knowledge(roster_entry=self.knower, secret=self.secret)
        rows = SecretKnowledge.objects.filter(roster_entry=self.knower, secret=self.secret)
        assert rows.count() == 1
        held = rows.get()
        assert held.knows_category is True  # stayed unlocked

    def test_unknown_to_a_stranger(self) -> None:
        assert secret_known_to(self.secret, RosterEntryFactory()) is False


class SecretClueTargetTests(TestCase):
    """A secret is discovered through the clue loop: a SECRET clue grants its fact (#1334)."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.secret = SecretFactory()
        cls.knower = RosterEntryFactory()

    def _secret_clue(self):
        from world.clues.constants import ClueTargetKind
        from world.clues.models import Clue

        return Clue.objects.create(
            target_kind=ClueTargetKind.SECRET,
            target_secret=self.secret,
            name="A torn love letter",
            description="Ink smudged, but the meaning is plain.",
        )

    def test_granting_a_secret_clue_target_teaches_the_secret(self) -> None:
        from world.clues.services import grant_clue_target, target_already_known

        clue = self._secret_clue()
        assert target_already_known(clue, self.knower) is False
        grant_clue_target(clue, self.knower)
        assert secret_known_to(self.secret, self.knower) is True
        assert target_already_known(clue, self.knower) is True
