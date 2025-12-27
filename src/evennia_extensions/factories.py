"""
Factories for Evennia models.
"""

import factory
from allauth.account.models import EmailAddress, EmailConfirmation
from django.utils import timezone
from evennia.accounts.models import AccountDB
from evennia.objects.models import ObjectDB
from evennia.utils import create


class ObjectDBFactory(factory.django.DjangoModelFactory):
    """
    Factory for creating ObjectDB instances for testing.
    """

    class Meta:
        model = ObjectDB
        django_get_or_create = ("db_key",)

    db_key = factory.Sequence(lambda n: f"test_object_{n}")
    db_typeclass_path = "typeclasses.objects.Object"

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        """
        Use Evennia's create_object to properly set up the object.
        """
        # Remove any fields that aren't valid for create_object
        kwargs.pop("_using", None)
        kwargs.pop("_quantity", None)

        key = kwargs.pop("db_key")
        typeclass = kwargs.pop("db_typeclass_path")
        home = kwargs.pop("db_home", None) or kwargs.pop("home", None)
        if not home:
            kwargs["nohome"] = True

        return create.create_object(typeclass=typeclass, key=key, home=home, **kwargs)

    @classmethod
    def _setup_next_sequence(cls):
        """
        Start sequence at 1 for better test readability.
        """
        return 1


class AccountFactory(factory.django.DjangoModelFactory):
    """
    Factory for creating AccountDB instances for testing.
    """

    class Meta:
        model = AccountDB
        django_get_or_create = ("username",)

    username = factory.Sequence(lambda n: f"test_user_{n}")
    email = factory.LazyAttribute(lambda obj: f"{obj.username}@example.com")

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        """
        Use Evennia's create_account to properly set up the account.
        """
        # Remove any fields that aren't valid for create_account
        kwargs.pop("_using", None)
        kwargs.pop("_quantity", None)

        # Handle is_staff separately as it's not a create_account parameter
        is_staff = kwargs.pop("is_staff", False)

        username = kwargs.pop("username")
        email = kwargs.pop("email", f"{username}@example.com")
        password = kwargs.pop("password", "testpassword123")

        account = create.create_account(username, email, password, **kwargs)

        # Set is_staff after account creation
        if is_staff:
            account.is_staff = True
            account.save()

        return account

    @classmethod
    def _setup_next_sequence(cls):
        """
        Start sequence at 1 for better test readability.
        """
        return 1


class CharacterFactory(ObjectDBFactory):
    """
    Factory for creating Character objects for testing.
    """

    db_key = factory.Sequence(lambda n: f"TestChar_{n}")
    db_typeclass_path = "typeclasses.characters.Character"

    @classmethod
    def _setup_next_sequence(cls):
        """
        Start sequence at 1 for better test readability.
        """
        return 1


class GMCharacterFactory(ObjectDBFactory):
    """
    Factory for creating GM Character objects for testing.
    """

    db_key = factory.Sequence(lambda n: f"GM_{n}")
    db_typeclass_path = "typeclasses.characters.Character"

    @classmethod
    def _setup_next_sequence(cls):
        """
        Start sequence at 1 for better test readability.
        """
        return 1


class EmailAddressFactory(factory.django.DjangoModelFactory):
    """
    Factory for creating EmailAddress instances for testing.
    """

    class Meta:
        model = EmailAddress

    user = factory.SubFactory(AccountFactory)
    email = factory.LazyAttribute(lambda obj: obj.user.email)
    verified = False
    primary = True


class EmailConfirmationFactory(factory.django.DjangoModelFactory):
    """
    Factory for creating EmailConfirmation instances for testing.
    """

    class Meta:
        model = EmailConfirmation

    email_address = factory.SubFactory(EmailAddressFactory)
    sent = factory.LazyFunction(timezone.now)

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        """
        Use EmailConfirmation.create() to generate proper key.
        """
        email_address = kwargs.pop("email_address")
        sent = kwargs.pop("sent", timezone.now())

        confirmation = EmailConfirmation.create(email_address)
        confirmation.sent = sent
        confirmation.save()

        return confirmation
