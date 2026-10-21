"""Distinction → Secret relocation services (#1334).

A sensitive distinction is *relocated* into a Secret: ``CharacterDistinction.secret`` is the
privacy primitive (its presence is the secret-state). These cover mint/clear and prove the
relocated secret is learned through the existing held-knowledge loop (``SecretKnowledge``).
"""

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.distinctions.factories import CharacterDistinctionFactory, DistinctionFactory
from world.distinctions.services import (
    clear_distinction_secret,
    mint_distinction_secret,
    set_secret_distinctions,
)
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

    def test_clear_keeps_a_secret_that_still_holds_another_distinction(self) -> None:
        """#4528: one secret may hold several distinctions; unlinking one leaves the rest."""
        cd, sheet = self._character_distinction(name="Evil Advice")
        other = CharacterDistinctionFactory(
            character=sheet, distinction=DistinctionFactory(name="Maladaptive Coping Mechanism")
        )
        secret = mint_distinction_secret(cd)
        other.secret = secret
        other.save(update_fields=["secret"])

        clear_distinction_secret(cd)

        cd.refresh_from_db()
        other.refresh_from_db()
        assert cd.secret_id is None
        assert other.secret_id == secret.pk
        assert Secret.objects.filter(pk=secret.pk).exists()

    def test_clear_keeps_a_hook_that_has_truths_under_it(self) -> None:
        cd, sheet = self._character_distinction(name="Evil Advice")
        hook = mint_distinction_secret(cd)
        Secret.objects.create(
            subject_sheet=sheet,
            level=SecretLevel.UNCOMMON_KNOWLEDGE,
            provenance=SecretProvenance.GM_AUTHORED,
            content="The voice is her past life's husband.",
            subject_aware=False,
            hook=hook,
        )

        clear_distinction_secret(cd)

        assert Secret.objects.filter(pk=hook.pk).exists()

    def test_set_secret_distinctions_links_the_ticked_and_frees_the_rest(self) -> None:
        cd, sheet = self._character_distinction(name="Evil Advice")
        second = CharacterDistinctionFactory(
            character=sheet, distinction=DistinctionFactory(name="Maladaptive Coping Mechanism")
        )
        third = CharacterDistinctionFactory(
            character=sheet, distinction=DistinctionFactory(name="Charming")
        )
        stranger = CharacterDistinctionFactory(distinction=DistinctionFactory(name="Wrathful"))
        secret = mint_distinction_secret(cd)

        linked, unlinked = set_secret_distinctions(secret, [second, third, stranger])

        assert (linked, unlinked) == (2, 1)
        for row in (cd, second, third, stranger):
            row.refresh_from_db()
        assert cd.secret_id is None
        assert second.secret_id == secret.pk
        assert third.secret_id == secret.pk
        assert stranger.secret_id is None
        assert Secret.objects.filter(pk=secret.pk).exists()

        linked, unlinked = set_secret_distinctions(secret, [])
        assert (linked, unlinked) == (0, 2)
        assert Secret.objects.filter(pk=secret.pk).exists()

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
