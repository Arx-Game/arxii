from typing import Any

from evennia.accounts.models import AccountDB
from evennia.objects.models import ObjectDB
import factory

from typeclasses.characters import Character

class ObjectDBFactory(factory.django.DjangoModelFactory):
    def __new__(cls, *args: Any, **kwargs: Any) -> ObjectDB: ...

    class Meta:
        model: type[ObjectDB]
        django_get_or_create: tuple[str, ...]

    db_key: str
    db_typeclass_path: str

class AccountFactory(factory.django.DjangoModelFactory):
    def __new__(cls, *args: Any, **kwargs: Any) -> AccountDB: ...

    class Meta:
        model: type[AccountDB]
        django_get_or_create: tuple[str, ...]

    username: str
    email: str

class CharacterFactory(ObjectDBFactory):
    def __new__(cls, *args: Any, **kwargs: Any) -> Character: ...

    db_key: str
    db_typeclass_path: str

class GMCharacterFactory(ObjectDBFactory):
    def __new__(cls, *args: Any, **kwargs: Any) -> Character: ...

    db_key: str
    db_typeclass_path: str
