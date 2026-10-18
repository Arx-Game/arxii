"""Every change to an organization's reputation is recorded with its cause (#4448, #4339)."""

from django.core.exceptions import ValidationError
from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.mechanics.constants import (
    REPUTATION_GAIN_CATEGORY_NAME,
    REPUTATION_GAIN_ORGANIZATION_TARGET_NAME,
)
from world.mechanics.test_helpers import grant_lever
from world.narrative.constants import NarrativeCategory
from world.narrative.models import NarrativeMessage
from world.roster.factories import RosterEntryFactory, RosterTenureFactory
from world.secrets.constants import DEFAULT_VICTIM_SEVERITY_BY_LEVEL, SecretLevel
from world.secrets.factories import SecretFactory, SecretVictimFactory
from world.secrets.services import expose_secret, reverse_secret_exposure
from world.societies.constants import (
    LIVE_REASON_LINE_CAUSES,
    REASON_LINE_PLACEHOLDER,
    OrganizationReputationCause,
)
from world.societies.factories import (
    OrganizationFactory,
    OrganizationReputationEventFactory,
    OrganizationReputationFactory,
    OrganizationReputationReasonLineFactory,
    SocietyFactory,
)
from world.societies.models import (
    REPUTATION_MAX,
    OrganizationReputation,
    OrganizationReputationEvent,
)
from world.societies.renown import bump_organization_reputation
from world.societies.reputation_reasons import reason_lines_by_reputation

CAUSE = OrganizationReputationCause


def _events(persona, organization):
    return list(
        OrganizationReputationEvent.objects.filter(
            reputation__persona=persona, reputation__organization=organization
        ).order_by("pk")
    )


class WriterRecordsEveryChangeTests(TestCase):
    def setUp(self) -> None:
        self.sheet = CharacterSheetFactory()
        self.persona = self.sheet.primary_persona
        self.org = OrganizationFactory()

    def test_a_change_writes_one_event_with_the_applied_amount_and_tiers(self) -> None:
        value = bump_organization_reputation(
            self.persona, self.org, -150, cause=CAUSE.STAFF_ADJUSTMENT
        )
        assert value == -150
        (event,) = _events(self.persona, self.org)
        assert event.cause == CAUSE.STAFF_ADJUSTMENT
        assert event.amount == -150
        assert (event.tier_before, event.tier_after) == ("unknown", "disfavored")

    def test_the_amount_is_the_clamped_amount(self) -> None:
        OrganizationReputationFactory(
            persona=self.persona, organization=self.org, value=REPUTATION_MAX - 10
        )
        bump_organization_reputation(self.persona, self.org, 500, cause=CAUSE.STAFF_ADJUSTMENT)
        (event,) = _events(self.persona, self.org)
        assert event.amount == 10

    def test_nothing_is_recorded_when_the_clamp_changes_nothing(self) -> None:
        OrganizationReputationFactory(
            persona=self.persona, organization=self.org, value=REPUTATION_MAX
        )
        bump_organization_reputation(self.persona, self.org, 50, cause=CAUSE.STAFF_ADJUSTMENT)
        assert _events(self.persona, self.org) == []

    def test_the_amount_is_after_the_reputation_gain_lever(self) -> None:
        grant_lever(
            self.sheet, REPUTATION_GAIN_CATEGORY_NAME, REPUTATION_GAIN_ORGANIZATION_TARGET_NAME, 50
        )
        bump_organization_reputation(self.persona, self.org, 100, cause=CAUSE.STAFF_ADJUSTMENT)
        (event,) = _events(self.persona, self.org)
        assert event.amount == 150

    def test_a_missing_citation_refuses_the_whole_change(self) -> None:
        with self.assertRaises(ValidationError):
            bump_organization_reputation(self.persona, self.org, -100, cause=CAUSE.SECRET_EXPOSED)
        assert not OrganizationReputation.objects.filter(
            persona=self.persona, organization=self.org, value__lt=0
        ).exists()
        assert _events(self.persona, self.org) == []


class CitationMatrixTests(TestCase):
    def _event(self, cause, **citations):
        reputation = OrganizationReputationFactory()
        return OrganizationReputationEvent(
            reputation=reputation,
            cause=cause,
            amount=-10,
            tier_before="unknown",
            tier_after="unknown",
            **citations,
        )

    def test_a_secret_cause_must_cite_a_secret(self) -> None:
        with self.assertRaises(ValidationError):
            self._event(CAUSE.SECRET_REVERSED).full_clean()
        self._event(CAUSE.SECRET_REVERSED, secret=SecretFactory()).full_clean()

    def test_a_cause_that_cites_nothing_refuses_a_citation(self) -> None:
        with self.assertRaises(ValidationError):
            self._event(CAUSE.GANG_TURF, secret=SecretFactory()).full_clean()
        self._event(CAUSE.GANG_TURF).full_clean()

    def test_a_cause_cannot_cite_another_causes_record(self) -> None:
        with self.assertRaises(ValidationError):
            self._event(CAUSE.STAKE_RESOLVED, secret=SecretFactory()).full_clean()


class SecretExposureIsRecordedTests(TestCase):
    def setUp(self) -> None:
        self.secret = SecretFactory(level=SecretLevel.CAREFULLY_KEPT)
        self.persona = self.secret.subject_sheet.primary_persona
        self.org = OrganizationFactory()
        SecretVictimFactory(secret=self.secret, organization=self.org, severity=None)

    def test_exposure_records_the_secret_as_the_cause(self) -> None:
        expose_secret(self.secret, societies=[SocietyFactory()])
        (event,) = _events(self.persona, self.org)
        assert event.cause == CAUSE.SECRET_EXPOSED
        assert event.secret == self.secret
        assert event.amount == -DEFAULT_VICTIM_SEVERITY_BY_LEVEL[SecretLevel.CAREFULLY_KEPT]

    def test_reversal_records_its_own_event(self) -> None:
        expose_secret(self.secret, societies=[SocietyFactory()])
        reverse_secret_exposure(self.secret)
        causes = [event.cause for event in _events(self.persona, self.org)]
        assert causes == [CAUSE.SECRET_EXPOSED, CAUSE.SECRET_REVERSED]


class ReasonLineTests(TestCase):
    def setUp(self) -> None:
        self.secret = SecretFactory(level=SecretLevel.CAREFULLY_KEPT)
        self.persona = self.secret.subject_sheet.primary_persona
        self.org = OrganizationFactory()
        SecretVictimFactory(secret=self.secret, organization=self.org, severity=None)
        expose_secret(self.secret, societies=[SocietyFactory()])
        self.reputation = OrganizationReputation.objects.get(
            persona=self.persona, organization=self.org
        )

    def _lines(self) -> list[str]:
        return reason_lines_by_reputation([self.reputation.pk])[self.reputation.pk]

    def test_until_staff_author_the_line_the_player_reads_a_placeholder(self) -> None:
        (line,) = self._lines()
        assert line == f"Despised {REASON_LINE_PLACEHOLDER}"

    def test_the_authored_line_replaces_the_placeholder(self) -> None:
        OrganizationReputationReasonLineFactory(
            cause=CAUSE.SECRET_EXPOSED, text="{tier}: [authored exposure line]"
        )
        assert self._lines() == ["Despised: [authored exposure line]"]

    def test_a_secret_cause_never_names_the_secret(self) -> None:
        OrganizationReputationReasonLineFactory(cause=CAUSE.SECRET_EXPOSED, text="{tier} {title}")
        (line,) = self._lines()
        assert self.secret.content not in line
        assert str(self.secret.pk) not in line

    def test_only_the_newest_three_lines_are_shown(self) -> None:
        for _ in range(4):
            OrganizationReputationEventFactory(reputation=self.reputation)
        assert len(self._lines()) == 3

    def test_a_cause_with_no_copy_shows_the_tier_only(self) -> None:
        OrganizationReputationEvent.objects.all().delete()
        OrganizationReputationEventFactory(
            reputation=self.reputation, cause=CAUSE.GANG_TURF, tier_after="favored"
        )
        assert self._lines() == ["Favored"]


class TierChangeMessageTests(TestCase):
    def setUp(self) -> None:
        self.sheet = CharacterSheetFactory()
        self.persona = self.sheet.primary_persona
        self.org = OrganizationFactory(name="Guild of Locks")

    def _make_player_run(self) -> None:
        RosterTenureFactory(
            roster_entry=RosterEntryFactory(character_sheet=self.sheet), end_date=None
        )

    def _messages(self):
        return NarrativeMessage.objects.filter(category=NarrativeCategory.RENOWN)

    def test_a_tier_change_tells_a_player_run_character(self) -> None:
        self._make_player_run()
        bump_organization_reputation(self.persona, self.org, -300, cause=CAUSE.GANG_TURF)
        (message,) = self._messages()
        assert message.body == "Guild of Locks: Disliked"

    def test_a_change_inside_a_tier_sends_nothing(self) -> None:
        self._make_player_run()
        bump_organization_reputation(self.persona, self.org, 10, cause=CAUSE.GANG_TURF)
        assert not self._messages().exists()

    def test_an_npc_hears_nothing(self) -> None:
        bump_organization_reputation(self.persona, self.org, -300, cause=CAUSE.GANG_TURF)
        assert not self._messages().exists()

    def test_a_character_creation_seed_is_not_news(self) -> None:
        self._make_player_run()
        bump_organization_reputation(
            self.persona, self.org, 300, cause=CAUSE.CHARACTER_CREATION, scale_gain=False
        )
        assert not self._messages().exists()


class RequiredContentProbeTests(TestCase):
    def test_the_probe_names_each_live_cause_until_it_is_authored(self) -> None:
        from web.admin.tuning.required_content import _probe_reputation_reason_lines

        result = _probe_reputation_reason_lines()
        assert not result.present
        assert len(result.missing) == len(LIVE_REASON_LINE_CAUSES)
        for cause in LIVE_REASON_LINE_CAUSES:
            OrganizationReputationReasonLineFactory(cause=cause, text="{tier}: authored")
        assert _probe_reputation_reason_lines().present
