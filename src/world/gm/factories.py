"""GM system factories."""

from datetime import timedelta
import secrets

from django.utils import timezone
import factory
from factory import django as factory_django

from evennia_extensions.factories import AccountFactory
from world.gm.constants import GMApplicationStatus, GMLevel
from world.gm.models import (
    GMApplication,
    GMLevelCap,
    GMLevelChange,
    GMProfile,
    GMRosterInvite,
    GMTable,
    GMTableMembership,
)
from world.roster.factories import RosterEntryFactory
from world.scenes.factories import PersonaFactory
from world.societies.constants import RenownRisk


class GMProfileFactory(factory_django.DjangoModelFactory):
    class Meta:
        model = GMProfile

    account = factory.SubFactory(AccountFactory)
    level = GMLevel.STARTING
    approved_at = factory.LazyFunction(timezone.now)
    approved_by = factory.SubFactory(AccountFactory)


class GMApplicationFactory(factory_django.DjangoModelFactory):
    class Meta:
        model = GMApplication

    account = factory.SubFactory(AccountFactory)
    application_text = factory.Faker("paragraph", nb_sentences=5)
    status = GMApplicationStatus.PENDING


class GMTableFactory(factory_django.DjangoModelFactory):
    class Meta:
        model = GMTable

    gm = factory.SubFactory(GMProfileFactory)
    name = factory.Sequence(lambda n: f"Test Table {n}")


class GMTableMembershipFactory(factory_django.DjangoModelFactory):
    class Meta:
        model = GMTableMembership

    table = factory.SubFactory(GMTableFactory)
    persona = factory.SubFactory(PersonaFactory)  # defaults to ESTABLISHED


class GMRosterInviteFactory(factory_django.DjangoModelFactory):
    class Meta:
        model = GMRosterInvite

    roster_entry = factory.SubFactory(RosterEntryFactory)
    created_by = factory.SubFactory(GMProfileFactory)
    code = factory.LazyFunction(lambda: secrets.token_urlsafe(48))
    expires_at = factory.LazyFunction(lambda: timezone.now() + timedelta(days=30))
    is_public = False


class GMLevelCapFactory(factory_django.DjangoModelFactory):
    class Meta:
        model = GMLevelCap
        django_get_or_create = ("level",)

    level = GMLevel.STARTING
    max_beat_risk = RenownRisk.NONE
    allow_custom_stakes = False
    allow_global_scope_authoring = False


class GMLevelChangeFactory(factory_django.DjangoModelFactory):
    class Meta:
        model = GMLevelChange

    profile = factory.SubFactory(GMProfileFactory)
    old_level = GMLevel.STARTING
    new_level = GMLevel.JUNIOR
    changed_by = factory.SubFactory(AccountFactory)
    reason = factory.Faker("sentence")


# --- Seed GM level caps (#2000 task 1) ------------------------------------
#
# Mirrors world.boundaries.factories.make_default_content_themes(): plain
# get_or_create per row (not GMLevelCapFactory, to sidestep the FactoryBoy
# django_get_or_create gotcha where a pre-existing row silently drops
# non-lookup kwargs). Idempotent — safe to call multiple times. Values are
# the ratified defaults from the GM trust ladder plan (#2000): designer-tunable,
# staff can retune per-row in admin.


def seed_default_gm_level_caps() -> dict[str, GMLevelCap]:
    """Create (or retrieve) the 5 default ``GMLevelCap`` rows, keyed by level.

    Idempotent — safe to call multiple times (e.g. from multiple migrations
    or test setups) without creating duplicate rows or new pks.
    """
    defaults = {
        GMLevel.STARTING: {
            "max_beat_risk": RenownRisk.LOW,
            "allow_custom_stakes": False,
            "allow_global_scope_authoring": False,
        },
        GMLevel.JUNIOR: {
            "max_beat_risk": RenownRisk.MODERATE,
            "allow_custom_stakes": False,
            "allow_global_scope_authoring": False,
        },
        GMLevel.GM: {
            "max_beat_risk": RenownRisk.HIGH,
            "allow_custom_stakes": False,
            "allow_global_scope_authoring": False,
        },
        GMLevel.EXPERIENCED: {
            "max_beat_risk": RenownRisk.EXTREME,
            "allow_custom_stakes": False,
            "allow_global_scope_authoring": False,
        },
        GMLevel.SENIOR: {
            "max_beat_risk": RenownRisk.EXTREME,
            "allow_custom_stakes": True,
            "allow_global_scope_authoring": False,
        },
    }
    caps: dict[str, GMLevelCap] = {}
    for level, field_defaults in defaults.items():
        cap, _ = GMLevelCap.objects.get_or_create(level=level, defaults=field_defaults)
        caps[level] = cap
    return caps
