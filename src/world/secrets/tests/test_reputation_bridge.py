"""Secret reveal → reputation bridge (#1429).

When a secret becomes known to a society, it feeds the existing renown engine via two channels:
the **diffuse** archetype reading (read through each society's principles, so the same fact nets
opposite signs for opposed societies) and the **relational** victim hit (a direct organization
reputation delta, independent of that org's philosophy). Persona victims are recorded only.
"""

from django.test import TestCase

from world.scenes.factories import PersonaFactory
from world.secrets.constants import DEFAULT_VICTIM_SEVERITY_BY_LEVEL, SecretLevel
from world.secrets.factories import SecretFactory, SecretVictimFactory
from world.secrets.services import expose_secret
from world.societies.factories import (
    OrganizationFactory,
    PhilosophicalArchetypeFactory,
    SocietyFactory,
)
from world.societies.models import OrganizationReputation, SocietyReputation


class SecretReputationBridgeTests(TestCase):
    def test_diffuse_reading_nets_opposite_signs_per_society(self) -> None:
        secret = SecretFactory(level=SecretLevel.DANGEROUS)
        persona = secret.subject_sheet.primary_persona
        secret.archetypes.add(PhilosophicalArchetypeFactory(power_delta=2))
        pro = SocietyFactory(name="Pro-power", power=5)
        anti = SocietyFactory(name="Anti-power", power=-5)

        result = expose_secret(secret, societies=[pro, anti])

        assert result.society_reputation_deltas[pro.pk] > 0
        assert result.society_reputation_deltas[anti.pk] < 0
        assert SocietyReputation.objects.get(persona=persona, society=pro).value > 0
        assert SocietyReputation.objects.get(persona=persona, society=anti).value < 0

    def test_org_victim_is_hit_independent_of_its_philosophy(self) -> None:
        secret = SecretFactory(level=SecretLevel.CAREFULLY_KEPT)
        persona = secret.subject_sheet.primary_persona
        victim_org = OrganizationFactory()
        SecretVictimFactory(secret=secret, organization=victim_org, severity=None)

        result = expose_secret(secret, societies=[SocietyFactory()])

        expected = -DEFAULT_VICTIM_SEVERITY_BY_LEVEL[SecretLevel.CAREFULLY_KEPT]
        assert result.organization_victim_deltas[victim_org.pk] == expected
        assert (
            OrganizationReputation.objects.get(persona=persona, organization=victim_org).value
            == expected
        )

    def test_explicit_severity_overrides_the_level_default(self) -> None:
        secret = SecretFactory(level=SecretLevel.DANGEROUS)
        persona = secret.subject_sheet.primary_persona
        org = OrganizationFactory()
        SecretVictimFactory(secret=secret, organization=org, severity=42)

        expose_secret(secret, societies=[SocietyFactory()])

        assert OrganizationReputation.objects.get(persona=persona, organization=org).value == -42

    def test_persona_victim_is_recorded_but_not_effected(self) -> None:
        secret = SecretFactory()
        victim_persona = PersonaFactory()
        SecretVictimFactory(secret=secret, organization=None, persona=victim_persona)

        result = expose_secret(secret, societies=[SocietyFactory()])

        assert victim_persona.pk in result.persona_victim_ids
        assert result.organization_victim_deltas == {}

    def test_diffuse_fires_one_shot_per_society(self) -> None:
        secret = SecretFactory()
        persona = secret.subject_sheet.primary_persona
        secret.archetypes.add(PhilosophicalArchetypeFactory(power_delta=1))
        society = SocietyFactory(power=5)

        first = expose_secret(secret, societies=[society])
        second = expose_secret(secret, societies=[society])

        assert first.society_reputation_deltas != {}
        assert second.society_reputation_deltas == {}
        # Applied exactly once — not doubled by the re-exposure.
        assert (
            SocietyReputation.objects.get(persona=persona, society=society).value
            == first.society_reputation_deltas[society.pk]
        )

    def test_victims_fire_once_even_as_more_societies_learn(self) -> None:
        secret = SecretFactory(level=SecretLevel.WHISPERS)
        persona = secret.subject_sheet.primary_persona
        org = OrganizationFactory()
        SecretVictimFactory(secret=secret, organization=org)
        s1 = SocietyFactory(name="S1")
        s2 = SocietyFactory(name="S2")

        first = expose_secret(secret, societies=[s1])
        second = expose_secret(secret, societies=[s2])

        assert org.pk in first.organization_victim_deltas
        assert second.organization_victim_deltas == {}
        expected = -DEFAULT_VICTIM_SEVERITY_BY_LEVEL[SecretLevel.WHISPERS]
        rep = OrganizationReputation.objects.get(persona=persona, organization=org)
        assert rep.value == expected
