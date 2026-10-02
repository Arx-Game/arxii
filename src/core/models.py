"""Project model base classes."""

from django.db import router
from evennia.utils.idmapper.models import SharedMemoryModel, SharedMemoryModelBase

from core.deletion import IdentityMapCollector
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
    methods when a direct database write is intentional. A delete's own
    ``SET_NULL`` updates are carried into the cache (``core.deletion``).
    """

    objects = ArxSharedMemoryManager()

    class Meta:
        abstract = True

    def delete(self, using=None, keep_parents=False):
        """Evennia's and Django's ``delete()``, with an ``IdentityMapCollector``.

        Mirrors ``SharedMemoryModel.delete`` (flush, mark deleted) and then
        ``Model.delete`` (Django 5.2) line for line; only the collector differs.
        """
        self.flush_from_cache()
        self._is_deleted = True
        if not self._is_pk_set():
            msg = (
                f"{self._meta.object_name} object can't be deleted because its "
                f"{self._meta.pk.attname} attribute is set to None."
            )
            raise ValueError(msg)
        using = using or router.db_for_write(self.__class__, instance=self)
        collector = IdentityMapCollector(using=using, origin=self)
        collector.collect([self], keep_parents=keep_parents)
        return collector.delete()
