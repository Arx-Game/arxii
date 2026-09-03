"""GM system factories."""

from datetime import timedelta
import secrets

from django.utils import timezone
import factory
from factory import django as factory_django

from actions.factories import ConsequencePoolFactory
from evennia_extensions.factories import AccountFactory
from world.areas.constants import AreaLevel, GridOrigin
from world.gm.constants import CatalogSuggestionProposalKind, GMApplicationStatus, GMLevel
from world.gm.models import (
    AreaBuildGrant,
    CatalogSuggestion,
    CheckTypeSituationFit,
    ConsequencePoolGuide,
    GMApplication,
    GMLevelCap,
    GMLevelChange,
    GMProfile,
    GMRosterInvite,
    GMTable,
    GMTableMembership,
    SituationDifficultyGuide,
    SituationKind,
    StoryArea,
    StoryRoomGrant,
)
from world.player_submissions.constants import SubmissionStatus
from world.roster.factories import RosterEntryFactory
from world.scenes.action_constants import DifficultyChoice
from world.scenes.factories import PersonaFactory
from world.societies.constants import RenownRisk


class GMProfileFactory(factory_django.DjangoModelFactory):
    class Meta:
        model = GMProfile

    account = factory.SubFactory(AccountFactory)
    level = GMLevel.STARTING
    approved_at = factory.LazyFunction(timezone.now)
    approved_by = factory.SubFactory(AccountFactory)


class AreaBuildGrantFactory(factory_django.DjangoModelFactory):
    class Meta:
        model = AreaBuildGrant

    account = factory.SubFactory(AccountFactory)
    area = factory.SubFactory("world.areas.factories.AreaFactory")
    max_level = AreaLevel.BUILDING
    granted_by = factory.SubFactory(AccountFactory)


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
    auto_clear_regional = False
    allow_item_rewards = False


class GMLevelChangeFactory(factory_django.DjangoModelFactory):
    class Meta:
        model = GMLevelChange

    profile = factory.SubFactory(GMProfileFactory)
    old_level = GMLevel.STARTING
    new_level = GMLevel.JUNIOR
    changed_by = factory.SubFactory(AccountFactory)
    reason = factory.Faker("sentence")


class StoryAreaFactory(factory_django.DjangoModelFactory):
    class Meta:
        model = StoryArea

    gm = factory.SubFactory(GMProfileFactory)
    area = factory.SubFactory(
        "world.areas.factories.AreaFactory",
        level=AreaLevel.BUILDING,
        origin=GridOrigin.STORY,
    )


class StoryRoomGrantFactory(factory_django.DjangoModelFactory):
    class Meta:
        model = StoryRoomGrant

    room = factory.SubFactory("evennia_extensions.factories.RoomProfileFactory")
    character = factory.SubFactory("world.character_sheets.factories.CharacterSheetFactory")
    granted_by = factory.SubFactory(GMProfileFactory)


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
            "auto_clear_regional": False,
            "max_story_areas": 1,
            "max_story_rooms_per_area": 8,
            "max_story_npcs": 0,
            "allow_item_rewards": False,
        },
        GMLevel.JUNIOR: {
            "max_beat_risk": RenownRisk.MODERATE,
            "allow_custom_stakes": False,
            "allow_global_scope_authoring": False,
            "auto_clear_regional": False,
            "max_story_areas": 2,
            "max_story_rooms_per_area": 12,
            "max_story_npcs": 2,
            "allow_item_rewards": False,
        },
        GMLevel.GM: {
            "max_beat_risk": RenownRisk.HIGH,
            "allow_custom_stakes": False,
            "allow_global_scope_authoring": False,
            "auto_clear_regional": False,
            "max_story_areas": 3,
            "max_story_rooms_per_area": 20,
            "max_story_npcs": 4,
            "allow_item_rewards": False,
        },
        GMLevel.EXPERIENCED: {
            "max_beat_risk": RenownRisk.EXTREME,
            "allow_custom_stakes": False,
            "allow_global_scope_authoring": False,
            "auto_clear_regional": True,
            "max_story_areas": 4,
            "max_story_rooms_per_area": 30,
            "max_story_npcs": 8,
            "allow_item_rewards": True,
        },
        GMLevel.SENIOR: {
            "max_beat_risk": RenownRisk.EXTREME,
            "allow_custom_stakes": True,
            "allow_global_scope_authoring": False,
            "auto_clear_regional": True,
            "max_story_areas": 6,
            "max_story_rooms_per_area": 50,
            "max_story_npcs": 12,
            "allow_item_rewards": True,
        },
    }
    caps: dict[str, GMLevelCap] = {}
    for level, field_defaults in defaults.items():
        cap, _ = GMLevelCap.objects.get_or_create(level=level, defaults=field_defaults)
        caps[level] = cap
    return caps


# --- GM scenario catalog factories (#2127) ---------------------------------


class SituationKindFactory(factory_django.DjangoModelFactory):
    class Meta:
        model = SituationKind
        django_get_or_create = ("name",)

    name = factory.Sequence(lambda n: f"Test Kind {n}")
    description = factory.Faker("sentence")
    minimum_gm_level = GMLevel.STARTING


class CheckTypeSituationFitFactory(factory_django.DjangoModelFactory):
    class Meta:
        model = CheckTypeSituationFit

    situation_kind = factory.SubFactory(SituationKindFactory)
    fit_notes = factory.Faker("sentence")


class SituationDifficultyGuideFactory(factory_django.DjangoModelFactory):
    class Meta:
        model = SituationDifficultyGuide

    situation_kind = factory.SubFactory(SituationKindFactory)
    risk = RenownRisk.MODERATE
    recommended_difficulty = DifficultyChoice.NORMAL
    guidance_text = factory.Faker("sentence")


class ConsequencePoolGuideFactory(factory_django.DjangoModelFactory):
    class Meta:
        model = ConsequencePoolGuide

    situation_kind = factory.SubFactory(SituationKindFactory)
    pool = factory.SubFactory(ConsequencePoolFactory)
    selection_criteria = factory.Faker("sentence")
    is_default = False


class CatalogSuggestionFactory(factory_django.DjangoModelFactory):
    class Meta:
        model = CatalogSuggestion

    submitted_by = factory.SubFactory(AccountFactory)
    proposal_kind = CatalogSuggestionProposalKind.OTHER
    proposal_text = factory.Faker("paragraph", nb_sentences=3)
    status = SubmissionStatus.OPEN


# --- Sample starter catalog taxonomy (#2127; content-repo-owned since #2865) --
#
# ``gm.situationkind`` and ``gm.situationdifficultyguide`` joined
# ``CONTENT_MODELS`` in #2865, so the content repo owns them and this seeder may
# no longer invent rows (ADR-0168): every write below goes through
# ``authored_or_sample``, which finds the authored row when the lore repo has one
# and creates a sample only under ``SEED_SAMPLE_CONTENT``. A starter set of three
# common GM scene archetypes with a difficulty guide at every RenownRisk tier --
# CheckTypeSituationFit/ConsequencePoolGuide rows are left for authoring against
# real CheckType/ConsequencePool catalogs (both are advisory content, ADR-0022).

_STARTER_SITUATION_KINDS: dict[str, dict[str, str]] = {
    "Chase": {
        "description": "A pursuit -- foot, mounted, or vehicular -- across a contested space.",
        "minimum_gm_level": GMLevel.STARTING,
    },
    "Negotiation": {
        "description": "A back-and-forth bargaining scene with something concrete at stake.",
        "minimum_gm_level": GMLevel.STARTING,
    },
    "Infiltration": {
        "description": "Getting somewhere (or something) without being caught.",
        "minimum_gm_level": GMLevel.JUNIOR,
    },
}

# (risk, recommended_difficulty, guidance_text) rows, authored per kind.
_STARTER_DIFFICULTY_GUIDES: dict[str, list[tuple[str, str, str]]] = {
    "Chase": [
        (RenownRisk.LOW, DifficultyChoice.EASY, "A low-stakes chase, mostly narrative color."),
        (
            RenownRisk.MODERATE,
            DifficultyChoice.NORMAL,
            "A real chase with a chance of losing them.",
        ),
        (
            RenownRisk.HIGH,
            DifficultyChoice.HARD,
            "The quarry is desperate and the terrain unkind.",
        ),
        (
            RenownRisk.EXTREME,
            DifficultyChoice.DAUNTING,
            "Life-or-death -- losing this chase has lasting consequences.",
        ),
    ],
    "Negotiation": [
        (RenownRisk.LOW, DifficultyChoice.EASY, "Both sides mostly want the same outcome."),
        (
            RenownRisk.MODERATE,
            DifficultyChoice.NORMAL,
            "Genuine friction; a bad roll costs something.",
        ),
        (
            RenownRisk.HIGH,
            DifficultyChoice.HARD,
            "The other side has real leverage and isn't afraid to use it.",
        ),
        (
            RenownRisk.EXTREME,
            DifficultyChoice.DAUNTING,
            "A failed negotiation here ends the relationship, or worse.",
        ),
    ],
    "Infiltration": [
        (
            RenownRisk.LOW,
            DifficultyChoice.NORMAL,
            "Lightly watched; a slip is embarrassing, not fatal.",
        ),
        (
            RenownRisk.MODERATE,
            DifficultyChoice.HARD,
            "Real guards, real locks, real consequences.",
        ),
        (
            RenownRisk.HIGH,
            DifficultyChoice.DAUNTING,
            "A hardened target -- getting caught means a fight or worse.",
        ),
        (
            RenownRisk.EXTREME,
            DifficultyChoice.HARROWING,
            "The single hardest target of its kind -- failure is catastrophic.",
        ),
    ],
}


def seed_catalog_starter_content() -> dict[str, SituationKind]:
    """Retrieve the starter ``SituationKind`` set + difficulty guides, or sample them.

    Idempotent -- safe to call multiple times (e.g. from ``arx seed dev`` or test
    setup) without creating duplicate rows or new pks. Returns the kinds keyed by
    name so callers/tests can chain further authoring off them; a kind the content
    repo does not author is simply absent from the returned mapping (and its
    difficulty guides are skipped) unless ``SEED_SAMPLE_CONTENT`` is on.
    """
    from world.seeds.sample_content import authored_or_sample

    kinds: dict[str, SituationKind] = {}
    for name, field_defaults in _STARTER_SITUATION_KINDS.items():
        kind = authored_or_sample(SituationKind, field_defaults, name=name)
        if kind is not None:
            kinds[name] = kind

    for name, rows in _STARTER_DIFFICULTY_GUIDES.items():
        kind = kinds.get(name)
        if kind is None:
            continue
        for risk, recommended_difficulty, guidance_text in rows:
            authored_or_sample(
                SituationDifficultyGuide,
                {
                    "recommended_difficulty": recommended_difficulty,
                    "guidance_text": guidance_text,
                },
                situation_kind=kind,
                risk=risk,
            )

    return kinds
