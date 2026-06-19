from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import models
from evennia.utils.idmapper.manager import SharedMemoryManager

from world.scenes.constants import ScenePrivacyMode

if TYPE_CHECKING:
    from evennia.accounts.models import AccountDB


class SceneQuerySet(models.QuerySet):
    """Queryset helpers for Scene visibility."""

    def viewable_by(self, account: AccountDB | None) -> SceneQuerySet:
        """Scenes ``account`` may view.

        staff -> all; authenticated non-staff -> public OR participant;
        anonymous/None -> public only. This is the single source of truth
        for scene read-visibility (was inlined in SceneViewSet.get_queryset).
        """
        if account is not None and getattr(account, "is_authenticated", False):  # noqa: GETATTR_LITERAL
            if account.is_staff:
                return self
            return self.filter(
                models.Q(privacy_mode=ScenePrivacyMode.PUBLIC) | models.Q(participants=account)
            ).distinct()
        return self.filter(privacy_mode=ScenePrivacyMode.PUBLIC)


# Preserve the idmapper-cached .get() by subclassing SharedMemoryManager.
SceneManager = SharedMemoryManager.from_queryset(SceneQuerySet)
