"""Secret-tab API (#1334) — a viewer's known secrets, with locked layers shown as "Unknown".

The load-bearing display rule (Apostate): a known secret shows its fact, but any partial-knowledge
layer the viewer hasn't unlocked — and any layer the secret leaves unplaced — reads "Unknown".
"""

from rest_framework.test import APITestCase

from evennia_extensions.factories import AccountFactory
from evennia_extensions.models import PlayerData
from world.roster.factories import RosterEntryFactory, RosterTenureFactory
from world.secrets.constants import SecretLevel, SecretProvenance
from world.secrets.factories import SecretCategoryFactory, SecretFactory
from world.secrets.services import grant_secret_knowledge

URL = "/api/secrets/known/"


class SecretTabAPITests(APITestCase):
    def _add_character(self, account):
        player_data, _ = PlayerData.objects.get_or_create(account=account)
        entry = RosterEntryFactory()
        RosterTenureFactory(player_data=player_data, roster_entry=entry)
        return entry

    def _viewer_with_character(self):
        account = AccountFactory()
        return account, self._add_character(account)

    def setUp(self) -> None:
        self.account, self.knower = self._viewer_with_character()
        self.subject = RosterEntryFactory().character_sheet
        self.category = SecretCategoryFactory(name="Scandal")
        self.client.force_authenticate(user=self.account)

    def _results(self, **params):
        # IC knowledge scopes to the active character; default the viewer to the test's knower.
        params.setdefault("viewer", self.knower.pk)
        return self.client.get(URL, params).data["results"]

    def test_known_secret_appears_on_the_subject_tab(self) -> None:
        secret = SecretFactory(
            subject_sheet=self.subject, content="She poisoned the duke.", category=self.category
        )
        grant_secret_knowledge(roster_entry=self.knower, secret=secret)
        results = self._results(subject=self.subject.pk)
        assert len(results) == 1
        assert results[0]["content"] == "She poisoned the duke."

    def test_locked_layers_render_unknown(self) -> None:
        secret = SecretFactory(
            subject_sheet=self.subject,
            category=self.category,
            consequences="Execution if proven.",
        )
        # Knows the fact only — not the category or consequences.
        grant_secret_knowledge(roster_entry=self.knower, secret=secret)
        row = self._results(subject=self.subject.pk)[0]
        assert row["category"] == "Unknown"
        assert row["consequences"] == "Unknown"
        assert row["content"]  # the fact itself is shown

    def test_unlocked_layers_render_the_real_values(self) -> None:
        secret = SecretFactory(
            subject_sheet=self.subject,
            category=self.category,
            consequences="Execution if proven.",
        )
        grant_secret_knowledge(
            roster_entry=self.knower, secret=secret, knows_category=True, knows_consequences=True
        )
        row = self._results(subject=self.subject.pk)[0]
        assert row["category"] == "Scandal"
        assert row["consequences"] == "Execution if proven."

    def test_unplaced_category_is_unknown_even_when_the_layer_is_unlocked(self) -> None:
        # The secret itself has no category → Unknown even to a knower who has the category layer.
        secret = SecretFactory(subject_sheet=self.subject, category=None)
        grant_secret_knowledge(roster_entry=self.knower, secret=secret, knows_category=True)
        row = self._results(subject=self.subject.pk)[0]
        assert row["category"] == "Unknown"

    def test_a_secret_you_do_not_know_is_not_listed(self) -> None:
        SecretFactory(subject_sheet=self.subject, content="Unknown to the viewer.")
        assert self._results(subject=self.subject.pk) == []

    def test_subject_filter_scopes_to_one_person(self) -> None:
        other_subject = RosterEntryFactory().character_sheet
        mine = SecretFactory(subject_sheet=self.subject)
        theirs = SecretFactory(subject_sheet=other_subject)
        grant_secret_knowledge(roster_entry=self.knower, secret=mine)
        grant_secret_knowledge(roster_entry=self.knower, secret=theirs)
        ids = {r["id"] for r in self._results(subject=self.subject.pk)}
        assert ids == {mine.pk}

    def test_author_attribution_player_vs_gm(self) -> None:
        player_secret = SecretFactory(
            subject_sheet=self.subject,
            provenance=SecretProvenance.PLAYER_FLAVOR,
            level=SecretLevel.UNCOMMON_KNOWLEDGE,
            author_persona=self.subject.primary_persona,
        )
        gm_secret = SecretFactory(
            subject_sheet=self.subject, provenance=SecretProvenance.GM_AUTHORED, author_persona=None
        )
        grant_secret_knowledge(roster_entry=self.knower, secret=player_secret)
        grant_secret_knowledge(roster_entry=self.knower, secret=gm_secret)
        authors = {r["id"]: r["author"] for r in self._results(subject=self.subject.pk)}
        assert authors[player_secret.pk] == self.subject.primary_persona.name
        assert authors[gm_secret.pk] == "GM/Staff"

    def test_scoped_to_the_active_character_not_the_account(self) -> None:
        # A second character on the SAME account knows a secret. Viewing as the first character
        # must NOT surface it — IC knowledge is per active character, never account-aggregate.
        alt = self._add_character(self.account)
        secret = SecretFactory(subject_sheet=self.subject)
        grant_secret_knowledge(roster_entry=alt, secret=secret)
        assert self._results(subject=self.subject.pk, viewer=self.knower.pk) == []
        # Viewing as the alt, it shows.
        ids = {r["id"] for r in self._results(subject=self.subject.pk, viewer=alt.pk)}
        assert ids == {secret.pk}

    def test_no_active_character_returns_empty(self) -> None:
        secret = SecretFactory(subject_sheet=self.subject)
        grant_secret_knowledge(roster_entry=self.knower, secret=secret)
        # No viewer → no secrets (never an account-wide aggregate).
        assert self.client.get(URL, {"subject": self.subject.pk}).data["results"] == []

    def test_cannot_view_as_another_accounts_character(self) -> None:
        _, other_entry = self._viewer_with_character()
        secret = SecretFactory(subject_sheet=self.subject)
        grant_secret_knowledge(roster_entry=other_entry, secret=secret)
        # Passing a roster entry the requester doesn't own → empty (for_account confines it).
        assert self._results(subject=self.subject.pk, viewer=other_entry.pk) == []

    def test_requires_authentication(self) -> None:
        self.client.force_authenticate(user=None)
        assert self.client.get(URL).status_code in (401, 403)
