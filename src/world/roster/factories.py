"""
Factories for roster models.
"""

from django.utils import timezone
import factory
import factory.django as factory_django

from evennia_extensions.factories import (  # noqa: F401  (CharacterFactory re-exported for tests)
    AccountFactory,
    CharacterFactory,
    MediaFactory,
)
from evennia_extensions.models import Artist, PlayerData
from world.character_sheets.factories import CharacterSheetFactory
from world.character_sheets.models import CharacterSheet
from world.roster.constants import COMMONER_KIND_NAME, NOBLE_KIND_NAME
from world.roster.models import (
    Family,
    FamilyKind,
    GameInvite,
    InviteStatus,
    PlayerMail,
    Roster,
    RosterApplication,
    RosterEntry,
    RosterTenure,
    RosterType,
    TenureDisplaySettings,
    TenureGallery,
    TenureMedia,
)


class FamilyKindFactory(factory_django.DjangoModelFactory):
    """Family kinds (#3617). get_or_create on name so tests share the migration rows.

    ``styles_as_house`` tracks the canonical ``NOBLE_KIND_NAME`` row (test tiers build
    schema straight from model state and never replay migration 0219's backfill, so
    a factory call is often what actually creates the canonical row in a test DB;
    see ``server/conf/sqlite_test_settings.py``'s data-seeding caveat).
    """

    class Meta:
        model = FamilyKind
        django_get_or_create = ("name",)

    name = COMMONER_KIND_NAME
    styles_as_house = factory.LazyAttribute(lambda o: o.name == NOBLE_KIND_NAME)


class FamilyFactory(factory_django.DjangoModelFactory):
    """Factory for Family instances."""

    class Meta:
        model = Family
        django_get_or_create = ("name",)

    name = factory.Sequence(lambda n: f"House TestFamily{n}")
    kind = factory.SubFactory(FamilyKindFactory)
    description = factory.LazyAttribute(lambda obj: f"Description for {obj.name}")
    is_playable = True


class KinspersonFactory(factory_django.DjangoModelFactory):
    """Factory for kinship graph nodes (#2062)."""

    class Meta:
        model = "arxii.Kinsperson"

    name = factory.Sequence(lambda n: f"Kin {n}")


class ParentageEdgeFactory(factory_django.DjangoModelFactory):
    """Factory for typed parentage edges (#2062)."""

    class Meta:
        model = "arxii.ParentageEdge"

    child = factory.SubFactory(KinspersonFactory)
    parent = factory.SubFactory(KinspersonFactory)


class KinspersonTraitValueFactory(factory_django.DjangoModelFactory):
    """Factory for pinned kinsperson appearance values (#2815)."""

    class Meta:
        model = "arxii.KinspersonTraitValue"

    kinsperson = factory.SubFactory(KinspersonFactory)


class UnionKindFactory(factory_django.DjangoModelFactory):
    """Factory for authorable union vocabulary rows (#2062)."""

    class Meta:
        model = "arxii.UnionKind"
        django_get_or_create = ("name",)

    name = "Marriage"
    confers_wedlock = True


class UnionFactory(factory_django.DjangoModelFactory):
    """Factory for unions (#2062). Pass members=[...] post-generation."""

    class Meta:
        model = "arxii.Union"

    kind = factory.SubFactory(UnionKindFactory)

    @factory.post_generation
    def members(self, create, extracted, **kwargs):
        if create and extracted:
            self.members.set(extracted)


class SoulFactory(factory_django.DjangoModelFactory):
    """Factory for souls (#2062)."""

    class Meta:
        model = "arxii.Soul"


class KinSlotPoolFactory(factory_django.DjangoModelFactory):
    """Factory for kin slot pools (#2062). Pass parents=[...] post-generation."""

    class Meta:
        model = "arxii.KinSlotPool"

    family = factory.SubFactory(FamilyFactory)
    count_remaining = 3

    @factory.post_generation
    def parents(self, create, extracted, **kwargs):
        if create and extracted:
            self.parents.set(extracted)


class PlayerDataFactory(factory_django.DjangoModelFactory):
    """Factory for PlayerData instances."""

    class Meta:
        model = PlayerData

    account = factory.SubFactory(AccountFactory)


class RosterFactory(factory_django.DjangoModelFactory):
    """Factory for Roster instances."""

    class Meta:
        model = Roster
        # roster_type (#2728) is unique + required — at most 7 rows can ever exist, one
        # per RosterType. get_or_create on it means a RosterFactory() call reuses the
        # canonical row when ensure_rosters() already seeded it (e.g. via
        # finalize_character in the same test) instead of colliding on insert. Note the
        # standard django_get_or_create caveat: on reuse, every other field below is
        # NOT applied to the pre-existing row — pass roster_type= explicitly when a test
        # needs a guaranteed-fresh row with specific field values.
        django_get_or_create = ("roster_type",)

    name = factory.Sequence(lambda n: f"Roster_{n}")
    # Pinned, NOT an Iterator. factory.Iterator advances off a process-global counter,
    # so a bare RosterFactory() would land on a different shelf depending on how many
    # other tests ran first — nondeterminism on a *unique* column, which is a latent
    # flake generator (#2728). A character with no stated shelf belongs on Active, and
    # any test that cares which shelf it gets passes roster_type= explicitly.
    roster_type = RosterType.ACTIVE
    description = factory.LazyAttribute(lambda obj: f"Description for {obj.name}")
    is_active = True
    allow_applications = True
    sort_order = factory.Sequence(lambda n: n)


class RosterEntryFactory(factory_django.DjangoModelFactory):
    """Factory for RosterEntry instances."""

    class Meta:
        model = RosterEntry

    character_sheet = factory.SubFactory(CharacterSheetFactory)
    roster = factory.SubFactory(RosterFactory)


class RosterTenureFactory(factory_django.DjangoModelFactory):
    """Factory for RosterTenure instances."""

    class Meta:
        model = RosterTenure

    player_data = factory.SubFactory(PlayerDataFactory)
    roster_entry = factory.SubFactory(RosterEntryFactory)
    player_number = factory.Sequence(lambda n: n)
    start_date = factory.LazyFunction(timezone.now)
    applied_date = factory.LazyFunction(timezone.now)


class RosterApplicationFactory(factory_django.DjangoModelFactory):
    """Factory for RosterApplication instances."""

    class Meta:
        model = RosterApplication

    player_data = factory.SubFactory(PlayerDataFactory)
    character = factory.SubFactory("world.character_sheets.factories.CharacterSheetFactory")
    application_text = "I would like to play this character because they seem interesting."
    status = "pending"


class TenureDisplaySettingsFactory(factory_django.DjangoModelFactory):
    """Factory for TenureDisplaySettings instances."""

    class Meta:
        model = TenureDisplaySettings

    tenure = factory.SubFactory(RosterTenureFactory)
    public_character_info = True
    show_online_status = True
    allow_pages = True
    allow_tells = True
    plot_involvement = "medium"


class TenureMediaFactory(factory_django.DjangoModelFactory):
    """Factory for TenureMedia instances."""

    class Meta:
        model = TenureMedia

    tenure = factory.SubFactory(RosterTenureFactory)
    media = factory.SubFactory(
        MediaFactory,
        player_data=factory.LazyAttribute(
            lambda obj: obj.factory_parent.tenure.player_data,
        ),
    )
    sort_order = 0


class PlayerMailFactory(factory_django.DjangoModelFactory):
    """Factory for PlayerMail instances."""

    class Meta:
        model = PlayerMail

    sender_tenure = factory.SubFactory(RosterTenureFactory)
    recipient_tenure = factory.SubFactory(RosterTenureFactory)
    subject = factory.Sequence(lambda n: f"Subject {n}")
    message = factory.Sequence(lambda n: f"Message body {n}")


class TenureGalleryFactory(factory_django.DjangoModelFactory):
    """Factory for TenureGallery instances."""

    class Meta:
        model = TenureGallery

    tenure = factory.SubFactory(RosterTenureFactory)
    name = factory.Sequence(lambda n: f"Gallery {n}")
    is_public = True


class ArtistFactory(factory_django.DjangoModelFactory):
    """Factory for Artist instances."""

    class Meta:
        model = Artist

    player_data = factory.SubFactory(PlayerDataFactory)
    name = factory.Sequence(lambda n: f"Artist {n}")
    description = ""
    commission_notes = ""
    accepting_commissions = True


class GameInviteFactory(factory_django.DjangoModelFactory):
    """Factory for GameInvite instances (#2483)."""

    class Meta:
        model = GameInvite

    inviter = factory.SubFactory(PlayerDataFactory)
    token = factory.Sequence(lambda n: f"test-token-{n:048d}")
    message = factory.Faker("sentence")
    status = InviteStatus.PENDING


class NPCStatlinePresetFactory(factory_django.DjangoModelFactory):
    """Factory for curated Story-NPC statline presets (#3427)."""

    class Meta:
        model = "arxii.NPCStatlinePreset"
        django_get_or_create = ("name",)

    name = factory.Sequence(lambda n: f"Test Preset {n}")
    description = factory.Faker("sentence")


class NPCPresetTraitLineFactory(factory_django.DjangoModelFactory):
    """Factory for one STAT line on a preset (#3427)."""

    class Meta:
        model = "arxii.NPCPresetTraitLine"

    preset = factory.SubFactory(NPCStatlinePresetFactory)
    trait = factory.SubFactory("world.traits.factories.StatTraitFactory")
    display_value = 3


class NPCPresetSkillLineFactory(factory_django.DjangoModelFactory):
    """Factory for one SKILL line on a preset (#3427)."""

    class Meta:
        model = "arxii.NPCPresetSkillLine"

    preset = factory.SubFactory(NPCStatlinePresetFactory)
    skill = factory.SubFactory("world.skills.factories.SkillFactory")
    value = 25


def grant_test_tenure(character_sheet: CharacterSheet) -> RosterTenure:
    """Give ``character_sheet`` a live, non-staff tenure (achievement-eligible, #3024).

    Reuses the sheet's existing RosterEntry when one exists (a second would
    violate the OneToOne); otherwise creates one.
    """
    entry = character_sheet.roster_entry_or_none
    if entry is None:
        entry = RosterEntryFactory(character_sheet=character_sheet)
    return RosterTenureFactory(roster_entry=entry, end_date=None)
