"""Distinction → Secret relocation services (#1334).

A sensitive distinction is *relocated* into a Secret: ``CharacterDistinction.secret`` is the
privacy primitive (its presence is the secret-state). These cover mint/clear and prove the
relocated secret is learned through the existing held-knowledge loop (``SecretKnowledge``).
"""

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.distinctions.factories import CharacterDistinctionFactory, DistinctionFactory
from world.distinctions.services import clear_distinction_secret, mint_distinction_secret
from world.roster.factories import RosterEntryFactory
from world.secrets.constants import SecretLevel, SecretProvenance
from world.secrets.models import Secret
from world.secrets.services import grant_secret_knowledge, secret_known_to


class DistinctionSecretServiceTests(TestCase):
    def _character_distinction(self, **distinction_kwargs):
        sheet = CharacterSheetFactory()
        distinction = DistinctionFactory(**distinction_kwargs)
        cd = CharacterDistinctionFactory(character=sheet, distinction=distinction)
        return cd, sheet

    def test_mint_creates_a_secret_about_the_subject_and_links_it(self) -> None:
        cd, sheet = self._character_distinction(
            name="Wanted Criminal", default_secret_level=SecretLevel.DANGEROUS
        )
        secret = mint_distinction_secret(cd)

        cd.refresh_from_db()
        assert cd.secret_id == secret.pk
        assert cd.is_secret is True
        assert secret.subject_sheet_id == sheet.pk
        assert secret.level == SecretLevel.DANGEROUS
        # Content seeds from the distinction name (terse, player-editable per legend-deed trust).
        assert secret.content == "Wanted Criminal"
        assert secret.provenance == SecretProvenance.GM_AUTHORED

    def test_mint_is_idempotent(self) -> None:
        cd, _ = self._character_distinction()
        first = mint_distinction_secret(cd)
        second = mint_distinction_secret(cd)
        assert first.pk == second.pk
        assert Secret.objects.count() == 1

    def test_mint_respects_explicit_level_provenance_and_content(self) -> None:
        cd, _ = self._character_distinction()
        secret = mint_distinction_secret(
            cd,
            level=SecretLevel.UNCOMMON_KNOWLEDGE,
            provenance=SecretProvenance.PLAYER_FLAVOR,
            content="I once cheated at cards.",
        )
        assert secret.level == SecretLevel.UNCOMMON_KNOWLEDGE
        assert secret.provenance == SecretProvenance.PLAYER_FLAVOR
        assert secret.content == "I once cheated at cards."

    def test_clear_deletes_the_secret_and_makes_the_distinction_public(self) -> None:
        cd, _ = self._character_distinction()
        secret = mint_distinction_secret(cd)
        clear_distinction_secret(cd)

        cd.refresh_from_db()
        assert cd.secret_id is None
        assert cd.is_secret is False
        assert not Secret.objects.filter(pk=secret.pk).exists()

    def test_clear_is_a_noop_without_a_secret(self) -> None:
        cd, _ = self._character_distinction()
        clear_distinction_secret(cd)  # must not raise
        assert cd.is_secret is False

    def test_relocated_distinction_is_learnable_through_the_clue_loop(self) -> None:
        # The whole point of relocation: a secret distinction is held + learned through the same
        # SecretKnowledge loop as any other secret — no parallel mechanism. Once learned it
        # surfaces on the secret tab (the known-secrets query), not the public distinctions list.
        cd, _ = self._character_distinction(name="Wanted Criminal")
        secret = mint_distinction_secret(cd)
        learner = RosterEntryFactory()
        assert secret_known_to(secret, learner) is False
        grant_secret_knowledge(roster_entry=learner, secret=secret)
        assert secret_known_to(secret, learner) is True
