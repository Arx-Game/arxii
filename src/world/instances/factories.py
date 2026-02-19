from evennia.objects.models import ObjectDB
import factory
import factory.django as factory_django

from world.instances.constants import InstanceStatus
from world.instances.models import InstancedRoom


class InstancedRoomFactory(factory_django.DjangoModelFactory):
    class Meta:
        model = InstancedRoom

    room = factory.LazyFunction(
        lambda: ObjectDB.objects.create(
            db_key="Instance Room",
            db_typeclass_path="typeclasses.rooms.Room",
        )
    )
    status = InstanceStatus.ACTIVE
    source_key = ""
