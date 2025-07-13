"""
Factories for Evennia models.
"""

from evennia.objects.models import ObjectDB
import factory


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
        from evennia.utils import create

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
