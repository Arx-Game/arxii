"""Tests for issue_proclamation and edict services (#2842)."""

from django.test import TestCase, tag

from world.proclamations.factories import (
    EdictKindFactory,
    ProclamationFactory,
    StanceArchetypeFactory,
)
from world.proclamations.services import (
    enact_edict,
    issue_proclamation,
    revoke_edict,
)
from world.scenes.factories import PersonaFactory
from world.societies.factories import (
    OrganizationFactory,
    SocietyFactory,
    SocietyReputationFactory,
)
from world.societies.models import (
    SocietyReputation,
)


class IssueProclamationTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.persona = PersonaFactory()
        cls.stance = StanceArchetypeFactory(mercy_delta=3)
        cls.society_aligned = SocietyFactory(mercy=5)
        cls.society_opposed = SocietyFactory(mercy=-5)
        cls.society_neutral = SocietyFactory(mercy=0)
        # Give the persona standing with each society
        for society in (cls.society_aligned, cls.society_opposed, cls.society_neutral):
            SocietyReputationFactory(persona=cls.persona, society=society, value=0)

    def test_issue_creates_proclamation(self):
        result = issue_proclamation(self.persona, self.stance, prose="Test!")
        assert result.proclamation.issuer == self.persona
        assert result.proclamation.stance == self.stance
        assert result.proclamation.prose == "Test!"

    def test_aligned_society_gains_on_success(self):
        """Aligned society gets positive reputation when check succeeds."""
        from world.checks.test_helpers import force_check_outcome
        from world.traits.models import CheckOutcome

        success = CheckOutcome.objects.filter(success_level__gt=0).first()
        if success is None:
            self.skipTest("No seeded CheckOutcome with success_level > 0")
        with force_check_outcome(success):
            issue_proclamation(self.persona, self.stance)
        rep = SocietyReputation.objects.get(persona=self.persona, society=self.society_aligned)
        assert rep.value > 0, "Aligned society should gain reputation on success"

    def test_aligned_society_gains_nothing_on_failure(self):
        """Failed roll wins nobody — aligned society stays at 0."""
        from world.checks.test_helpers import force_check_outcome
        from world.traits.models import CheckOutcome

        failure = CheckOutcome.objects.filter(success_level__lte=0).first()
        if failure is None:
            self.skipTest("No seeded CheckOutcome with success_level <= 0")
        with force_check_outcome(failure):
            issue_proclamation(self.persona, self.stance)
        rep = SocietyReputation.objects.get(persona=self.persona, society=self.society_aligned)
        assert rep.value == 0, "Failed roll should win nothing for aligned societies"

    def test_opposed_society_loses_on_failure(self):
        """Opposed society takes full reputation loss on failure."""
        from world.checks.test_helpers import force_check_outcome
        from world.traits.models import CheckOutcome

        failure = CheckOutcome.objects.filter(success_level__lte=0).first()
        if failure is None:
            self.skipTest("No seeded CheckOutcome with success_level <= 0")
        with force_check_outcome(failure):
            issue_proclamation(self.persona, self.stance)
        rep = SocietyReputation.objects.get(persona=self.persona, society=self.society_opposed)
        assert rep.value < 0, "Opposed society should lose reputation on failure"

    def test_neutral_society_unaffected(self):
        """A society with zero dot product is never touched."""
        from world.checks.test_helpers import force_check_outcome
        from world.traits.models import CheckOutcome

        success = CheckOutcome.objects.filter(success_level__gt=0).first()
        if success is None:
            self.skipTest("No seeded CheckOutcome with success_level > 0")
        with force_check_outcome(success):
            result = issue_proclamation(self.persona, self.stance)
        assert self.society_neutral.pk not in result.society_deltas


class IssueProclamationWithOrgTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.persona = PersonaFactory()
        cls.stance = StanceArchetypeFactory(mercy_delta=3)
        cls.org = OrganizationFactory()
        # Give the persona standing with the org's society
        if cls.org.society is not None:
            SocietyReputationFactory(persona=cls.persona, society=cls.org.society, value=0)

    def test_issue_with_org_creates_proclamation_with_org(self):
        result = issue_proclamation(self.persona, self.stance, org=self.org)
        assert result.proclamation.org == self.org


@tag("postgres")  # Area.save() refreshes a materialized view (areas_areaclosure)
class EdictServiceTests(TestCase):
    def setUp(self) -> None:
        from world.areas.factories import AreaFactory
        from world.societies.houses.models import Domain

        org = OrganizationFactory()
        self.domain = Domain.objects.create(
            area=AreaFactory(), name="EdictTestDomain", owner_org=org, population=100
        )
        self.persona = PersonaFactory()
        self.stance = StanceArchetypeFactory()
        self.kind = EdictKindFactory(stance=self.stance)
        self.proc = ProclamationFactory(issuer=self.persona, stance=self.stance)

    def test_enact_creates_active_edict(self):
        edict = enact_edict(self.domain, self.kind, self.proc)
        assert edict.is_active
        assert edict.kind == self.kind

    def test_enact_replaces_existing_edict(self):
        first = enact_edict(self.domain, self.kind, self.proc)
        second_kind = EdictKindFactory(stance=self.stance)
        second = enact_edict(self.domain, second_kind, self.proc)
        first.refresh_from_db()
        assert not first.is_active, "First edict should be revoked"
        assert second.is_active

    def test_revoke_deactivates_edict(self):
        enact_edict(self.domain, self.kind, self.proc)
        revoked = revoke_edict(self.domain)
        assert revoked is not None
        assert not revoked.is_active

    def test_revoke_with_no_active_edict_returns_none(self):
        result = revoke_edict(self.domain)
        assert result is None
