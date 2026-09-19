"""Project model base classes."""

from evennia.utils.idmapper.models import SharedMemoryModel, SharedMemoryModelBase

from core.managers import ArxSharedMemoryManager


class ArxSharedMemoryModelBase(SharedMemoryModelBase):
    """Keep each concrete model's identity cache separate from the base class."""

    def _prepare(self) -> None:
        dbmodel = self._meta.concrete_model if self._meta.proxy else self
        self.__dbclass__ = dbmodel
        if "__instance_cache__" not in dbmodel.__dict__:
            dbmodel.__instance_cache__ = {}
        super()._prepare()


class ArxSharedMemoryModel(SharedMemoryModel, metaclass=ArxSharedMemoryModelBase):
    """Shared-memory model with guarded queryset writes.

    Queryset ``update()`` and ``bulk_update()`` bypass Evennia's identity map,
    leaving resident instances stale. Use the explicit ``*_with_reason``
    methods when a direct database write is intentional.
    """

    objects = ArxSharedMemoryManager()

    class Meta:
        abstract = True
