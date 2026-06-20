from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

from django.db import models
from django.utils import timezone
from evennia.utils.idmapper.manager import SharedMemoryManager

from world.scenes.constants import InteractionMode, InteractionVisibility, ScenePrivacyMode

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


class InteractionQuerySet(models.QuerySet):
    """Queryset helpers for Interaction read-visibility."""

    def visible_to(
        self,
        account: AccountDB | None,
        *,
        persona_ids: list[int] | None = None,
        since: str | None = None,
    ) -> InteractionQuerySet:
        """Interactions ``account`` may read, preserving any prefetches on ``self``.

        Single source of truth for interaction read-visibility (was inlined in
        ``InteractionViewSet.get_queryset``). Reused by the scene highlight reel so the
        reel can never surface a pose the viewer cannot already see — even as a sealed
        slot. Callers pass the account's CURRENT persona ids (empty for anonymous) and the
        optional ``since`` time bound (the request's ``since`` param); both are request
        concerns kept out of this DB-pure method.

        staff -> everything except very-private (#1219); anonymous -> public room-heard
        only; authenticated non-staff -> public room-heard, plus content reaching them as
        a pinned party (writer/receiver), plus room-heard in scenes their current personas
        were present in or they personally participated in, plus everything (bar
        very-private) in scenes they GM'd.
        """
        # Local imports avoid the managers <-> models import cycle (models imports this module).
        from world.scenes.models import Interaction, SceneParticipation  # noqa: PLC0415

        is_authenticated = account is not None and getattr(account, "is_authenticated", False)  # noqa: GETATTR_LITERAL
        if is_authenticated and account.is_staff:
            # Staff sees everything except very-private (#1219: that tier admits no exception).
            return self.exclude(visibility=InteractionVisibility.VERY_PRIVATE)

        # Time bound for partition pruning; the 'since' param overrides the 90-day default.
        time_bound = {"timestamp__gte": since or (timezone.now() - timedelta(days=90))}

        # "Room-heard" = broadcast content everyone present perceived: default visibility,
        # not place-scoped, and not directed (no receiver rows, not a whisper). Whispers /
        # table-talk / receiver-scoped mutters are DIRECTED -- they reach only their parties.
        room_heard = models.Q(
            visibility=InteractionVisibility.DEFAULT,
            place__isnull=True,
            receivers__isnull=True,
        ) & ~models.Q(mode=InteractionMode.WHISPER)

        # Public room-heard -> anyone, including unauthenticated viewers.
        public_visible = Interaction.objects.filter(
            room_heard,
            models.Q(scene__privacy_mode=ScenePrivacyMode.PUBLIC) | models.Q(scene__isnull=True),
            **time_bound,
        ).values("pk")

        if not is_authenticated:
            return self.filter(pk__in=public_visible)

        account_id = account.pk
        current_persona_ids = persona_ids or []

        # Scenes whose room-heard content this account may read: where one of their CURRENT
        # characters was present (so a new player inherits the character's full history), or
        # which they PERSONALLY participated in (so a former player keeps the scenes they did).
        present_scene_ids = Interaction.objects.filter(
            models.Q(persona_id__in=current_persona_ids)
            | models.Q(receivers__persona_id__in=current_persona_ids),
            scene__isnull=False,
        ).values("scene_id")
        participated_scene_ids = SceneParticipation.objects.filter(account_id=account_id).values(
            "scene_id"
        )
        gm_scene_ids = SceneParticipation.objects.filter(account_id=account_id, is_gm=True).values(
            "scene_id"
        )

        # Private content reaches this account ONLY as an actual party -- writer or receiver,
        # pinned BY ACCOUNT at creation. Persona inheritance and mere scene presence never
        # grant it; a former party keeps it. This is the whole privacy guarantee.
        party = Interaction.objects.filter(
            models.Q(writer_account_id=account_id) | models.Q(receivers__account_id=account_id),
            **time_bound,
        ).values("pk")
        present_visible = Interaction.objects.filter(
            room_heard, scene_id__in=present_scene_ids, **time_bound
        ).values("pk")
        participated_visible = Interaction.objects.filter(
            room_heard, scene_id__in=participated_scene_ids, **time_bound
        ).values("pk")
        # The GM who ran a scene sees everything in it except very-private.
        gm_visible = (
            Interaction.objects.filter(scene_id__in=gm_scene_ids, **time_bound)
            .exclude(visibility=InteractionVisibility.VERY_PRIVATE)
            .values("pk")
        )

        visible_ids = public_visible.union(party, present_visible, participated_visible, gm_visible)
        return self.filter(pk__in=visible_ids)


# Preserve the idmapper-cached .get() by subclassing SharedMemoryManager.
InteractionManager = SharedMemoryManager.from_queryset(InteractionQuerySet)
