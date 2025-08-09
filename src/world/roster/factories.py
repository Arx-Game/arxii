"""
Factories for roster models.
"""

from django.utils import timezone
from evennia.accounts.models import AccountDB
import factory

from evennia_extensions.factories import ObjectDBFactory
from evennia_extensions.models import Artist, PlayerData, PlayerMedia
from world.roster.models import (
    Roster,
    RosterApplication,
    RosterEntry,
    RosterTenure,
    TenureDisplaySettings,
    TenureMedia,
)


class AccountDBFactory(factory.django.DjangoModelFactory):
    """Factory for AccountDB instances."""

    class Meta:
        model = AccountDB
        django_get_or_create = ("username",)

    username = factory.Sequence(lambda n: f"testuser_{n}")
    email = factory.LazyAttribute(lambda obj: f"{obj.username}@test.com")


class PlayerDataFactory(factory.django.DjangoModelFactory):
    """Factory for PlayerData instances."""

    class Meta:
        model = PlayerData

    account = factory.SubFactory(AccountDBFactory)


class RosterFactory(factory.django.DjangoModelFactory):
    """Factory for Roster instances."""

    class Meta:
        model = Roster

    name = factory.Sequence(lambda n: f"Roster_{n}")
    description = factory.LazyAttribute(lambda obj: f"Description for {obj.name}")
    is_active = True
    sort_order = factory.Sequence(lambda n: n)


class CharacterFactory(ObjectDBFactory):
    """Factory for Character objects."""

    db_key = factory.Sequence(lambda n: f"Character_{n}")
    db_typeclass_path = "typeclasses.characters.Character"


class RosterEntryFactory(factory.django.DjangoModelFactory):
    """Factory for RosterEntry instances."""

    class Meta:
        model = RosterEntry

    character = factory.SubFactory(CharacterFactory)
    roster = factory.SubFactory(RosterFactory)


class RosterTenureFactory(factory.django.DjangoModelFactory):
    """Factory for RosterTenure instances."""

    class Meta:
        model = RosterTenure

    player_data = factory.SubFactory(PlayerDataFactory)
    roster_entry = factory.SubFactory(RosterEntryFactory)
    player_number = factory.Sequence(lambda n: n)
    start_date = factory.LazyFunction(timezone.now)
    applied_date = factory.LazyFunction(timezone.now)


class RosterApplicationFactory(factory.django.DjangoModelFactory):
    """Factory for RosterApplication instances."""

    class Meta:
        model = RosterApplication

    player_data = factory.SubFactory(PlayerDataFactory)
    character = factory.SubFactory(CharacterFactory)
    application_text = (
        "I would like to play this character because they seem interesting."
    )
    status = "pending"


class TenureDisplaySettingsFactory(factory.django.DjangoModelFactory):
    """Factory for TenureDisplaySettings instances."""

    class Meta:
        model = TenureDisplaySettings

    tenure = factory.SubFactory(RosterTenureFactory)
    public_character_info = True
    show_online_status = True
    allow_pages = True
    allow_tells = True
    plot_involvement = "medium"


class PlayerMediaFactory(factory.django.DjangoModelFactory):
    """Factory for PlayerMedia instances."""

    class Meta:
        model = PlayerMedia

    player_data = factory.SubFactory(PlayerDataFactory)
    cloudinary_public_id = factory.Sequence(lambda n: f"test_media_{n}")
    cloudinary_url = factory.LazyAttribute(
        lambda obj: f"https://res.cloudinary.com/test/image/upload/{obj.cloudinary_public_id}"
    )
    media_type = "photo"
    title = factory.Sequence(lambda n: f"Test Media {n}")


class TenureMediaFactory(factory.django.DjangoModelFactory):
    """Factory for TenureMedia instances."""

    class Meta:
        model = TenureMedia

    tenure = factory.SubFactory(RosterTenureFactory)
    media = factory.SubFactory(
        PlayerMediaFactory,
        player_data=factory.LazyAttribute(
            lambda obj: obj.factory_parent.tenure.player_data
        ),
    )
    sort_order = 0
    is_public = True


class ArtistFactory(factory.django.DjangoModelFactory):
    """Factory for Artist instances."""

    class Meta:
        model = Artist

    player_data = factory.SubFactory(PlayerDataFactory)
    name = factory.Sequence(lambda n: f"Artist {n}")
    description = ""
    commission_notes = ""
    accepting_commissions = True
