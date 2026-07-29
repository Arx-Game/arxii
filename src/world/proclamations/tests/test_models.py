"""Tests for the proclamations models (#2842)."""

from django.core.exceptions import ValidationError
from django.test import TestCase, tag
import pytest

from world.proclamations.factories import (
    EdictKindFactory,
    ProclamationFactory,
    StanceArchetypeFactory,
)
from world.proclamations.models import (
    DomainEdict,
    EdictKind,
    Proclamation,
    StanceArchetype,
)
from world.scenes.factories import PersonaFactory


class StanceArchetypeTests(TestCase):
    def test_stance_has_six_principle_deltas(self):
        stance = StanceArchetype.objects.create(
            name="Defense of the Old Ways",
            description="A call to preserve what was.",
            mercy_delta=0,
            method_delta=1,
            status_delta=0,
            change_delta=-3,
            allegiance_delta=-1,
            power_delta=0,
        )
        assert stance.mercy_delta == 0
        assert stance.method_delta == 1
        assert stance.change_delta == -3
        assert str(stance) == "Defense of the Old Ways"

    def test_stance_delta_validators_reject_out_of_range(self):
        stance = StanceArchetype(name="X", mercy_delta=10)
        with pytest.raises(ValidationError):
            stance.full_clean()

    def test_stance_natural_key_is_name(self):
        assert StanceArchetype.NaturalKeyConfig.fields == ["name"]


class ProclamationTests(TestCase):
    def test_proclamation_requires_issuer_and_stance(self):
        persona = PersonaFactory()
        stance = StanceArchetypeFactory()
        proc = Proclamation.objects.create(
            issuer=persona,
            stance=stance,
            prose="Hear me, people of the city.",
        )
        assert proc.issuer == persona
        assert proc.stance == stance
        assert proc.org is None
        assert proc.prose == "Hear me, people of the city."
        assert proc.check_outcome == ""
        assert proc.issued_at is not None

    def test_proclamation_with_org(self):
        from world.societies.factories import OrganizationFactory

        persona = PersonaFactory()
        org = OrganizationFactory()
        stance = StanceArchetypeFactory()
        proc = Proclamation.objects.create(
            issuer=persona,
            org=org,
            stance=stance,
            prose="For the guild.",
        )
        assert proc.org == org


class EdictKindTests(TestCase):
    def test_edict_kind_has_stance_and_payload(self):
        stance = StanceArchetypeFactory()
        kind = EdictKind.objects.create(
            name="Squeeze the Taxes",
            description="Tax everything that moves.",
            stance=stance,
            income_gross_pct=20,
            weekly_unrest_delta=5,
            weekly_upkeep_coppers=0,
        )
        assert kind.stance == stance
        assert kind.income_gross_pct == 20
        assert str(kind) == "Squeeze the Taxes"


@tag("postgres")  # Area.save() refreshes a materialized view (areas_areaclosure)
class DomainEdictTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        from world.areas.factories import AreaFactory
        from world.societies.factories import OrganizationFactory
        from world.societies.houses.models import Domain

        org = OrganizationFactory()
        cls.domain = Domain.objects.create(
            area=AreaFactory(), name="TestDomain", owner_org=org, population=100
        )
        cls.persona = PersonaFactory()
        cls.stance = StanceArchetypeFactory()
        cls.kind = EdictKindFactory(stance=cls.stance)
        cls.proc = ProclamationFactory(issuer=cls.persona, stance=cls.stance)

    def test_active_edict_is_active(self):
        edict = DomainEdict.objects.create(
            domain=self.domain,
            kind=self.kind,
            proclamation=self.proc,
        )
        assert edict.revoked_at is None
        assert edict.is_active is True

    def test_revoked_edict_is_inactive(self):
        from django.utils import timezone

        edict = DomainEdict.objects.create(
            domain=self.domain,
            kind=self.kind,
            proclamation=self.proc,
        )
        edict.revoked_at = timezone.now()
        edict.save()
        assert edict.is_active is False
