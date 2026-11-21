from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

from django.db import models
from django.utils import timezone

from core.managers import ArxSharedMemoryQuerySet, GuardedSharedMemoryManager
from world.scenes.constants import InteractionMode, InteractionVisibility, ScenePrivacyMode

if TYPE_CHECKING:
    from evennia.accounts.models import AccountDB
    from evennia.objects.models import ObjectDB


class SceneQuerySet(ArxSharedMemoryQuerySet):
    """Queryset helpers for Scene visibility."""

    def active_for_room(self, location: ObjectDB | None) -> SceneQuerySet:
        """Active, room-scoped RP scenes at *location* — excludes battle-backed scenes.

        *location* is the Evennia room object; ``Scene.location`` is its
        ``RoomProfile``, which shares the room's pk, so the filter is on the id.

        A staged ``Battle``'s backing Scene (``Battle`` is a 1:1 Scene extension, #2010)
        is active + located + PUBLIC and typically the newest scene at the room too, so
        an unfiltered ``Scene.objects.filter(location=room, is_active=True)`` lookup
        would let it hijack every room-scoped active-scene resolver — the battle map is
        not the room's RP scene. Every such resolver (``get_active_scene``,
        ``ensure_scene_for_location``, the create-scene collision check, ``scene status``)
        must go through this method rather than hand-rolling the filter (#2010 review).
        """
        location_id = location.pk if location is not None else None
        return self.filter(location_id=location_id, is_active=True, battle__isnull=True)

    def viewable_by(self, account: AccountDB | None) -> SceneQuerySet:
        """Scenes ``account`` may view.

        staff -> all; authenticated non-staff -> public OR participant;
        anonymous/None -> public only. This is the single source of truth
        for scene read-visibility (was inlined in SceneViewSet.get_queryset).
        """
        if account is not None and account.is_authenticated:
            if account.is_staff:
                return self
            return self.filter(
                models.Q(privacy_mode=ScenePrivacyMode.PUBLIC) | models.Q(participants=account)
            ).distinct()
        return self.filter(privacy_mode=ScenePrivacyMode.PUBLIC)


# Preserve the idmapper-cached .get() by subclassing SharedMemoryManager.
SceneManager = GuardedSharedMemoryManager.from_queryset(SceneQuerySet)


def room_heard_q() -> models.Q:
    """Broadcast content everyone present perceived.

    Default visibility, not place-scoped, not directed (no receiver rows, not a
    whisper). Whispers, table-talk and receiver-scoped mutters are DIRECTED: they
    reach only their parties, so they are never room-heard.

    Shared by `InteractionQuerySet.visible_to` (read visibility),
    `world.scenes.attention_services` (#3774), which counts ambient unread
    inside a scene, and the live WebSocket push's reply-parent gate
    (`interaction_services._reply_parent_payload`, #3787). All three must agree
    on this definition: an attention count built on a looser predicate would
    disclose that a private aside took place, as an increment the viewer is not
    a party to, and a looser reply-parent gate would do the same for a reply.
    Returns a fresh Q each call, since combining a Q with `&`/`|` is not safe to
    do to a shared instance.
    """
    return models.Q(
        visibility=InteractionVisibility.DEFAULT,
        place__isnull=True,
        receivers__isnull=True,
    ) & ~models.Q(mode=InteractionMode.WHISPER)


class InteractionQuerySet(ArxSharedMemoryQuerySet):
    """Queryset helpers for Interaction read-visibility."""

    def room_heard(self) -> InteractionQuerySet:
        """Narrow to broadcast rows: see ``room_heard_q``."""
        return self.filter(room_heard_q())

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
        were present in during this account's own tenure on the character, or they personally
        participated in, plus everything (bar
        very-private) in scenes they GM'd.
        """
        # Local imports avoid the managers <-> models import cycle (models imports this module).
        from world.roster.models import RosterTenure  # noqa: PLC0415
        from world.scenes.models import Interaction, SceneParticipation  # noqa: PLC0415
        from world.scenes.place_models import InteractionReceiver  # noqa: PLC0415

        is_authenticated = account is not None and account.is_authenticated
        if is_authenticated and account.is_staff:
            # Staff sees everything except very-private (#1219: that tier admits no exception).
            return self.exclude(visibility=InteractionVisibility.VERY_PRIVATE)

        # Time bound for partition pruning; the 'since' param overrides the 90-day default.
        time_bound = {"timestamp__gte": since or (timezone.now() - timedelta(days=90))}

        room_heard = room_heard_q()

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

        # Scenes whose room-heard content this account may read because one of their CURRENT
        # characters was present. The grant counts only what happened during the account's
        # OWN tenure on that character: a persona's history from before this account played
        # it is the previous player's, so a new player of a roster character does not read
        # the old private-scene poses (#3751). A tenure's start may be unrecorded (null),
        # which reaches back indefinitely; its end may be open (null).
        def _in_own_tenure(*, sheet_field: str, time_field: str) -> models.Exists:
            return models.Exists(
                RosterTenure.objects.filter(
                    models.Q(start_date__isnull=True)
                    | models.Q(start_date__lte=models.OuterRef(time_field)),
                    models.Q(end_date__isnull=True)
                    | models.Q(end_date__gte=models.OuterRef(time_field)),
                    player_data__account_id=account_id,
                    roster_entry__character_sheet_id=models.OuterRef(sheet_field),
                )
            )

        written_scene_ids = Interaction.objects.filter(
            _in_own_tenure(sheet_field="persona__character_sheet_id", time_field="timestamp"),
            persona_id__in=current_persona_ids,
            scene__isnull=False,
        ).values("scene_id")
        received_scene_ids = InteractionReceiver.objects.filter(
            _in_own_tenure(sheet_field="persona__character_sheet_id", time_field="timestamp"),
            persona_id__in=current_persona_ids,
            interaction__scene__isnull=False,
        ).values("interaction__scene_id")
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
            models.Q(scene_id__in=written_scene_ids) | models.Q(scene_id__in=received_scene_ids),
            room_heard,
            **time_bound,
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

    def readable_by(
        self,
        account: AccountDB | None,
        *,
        persona_ids: list[int] | None = None,
        since: str | None = None,
    ) -> InteractionQuerySet:
        """``visible_to`` minus the faces the viewer's blocks hide (#1278): what ``account``
        may actually read.

        The one gate every read of an interaction goes through (the interaction list and
        detail, play search, context and summaries, a reply's parent chip, the highlight
        reel), so a blocked face is absent from all of them alike. Muted faces are NOT
        dropped here: their poses stay in the feed with the text blanked by the serializer
        (#2087). Staff bypass blocks, as everywhere.
        """
        # Local import: block_services imports the scenes models, which import this module.
        from world.scenes.block_services import hidden_persona_ids_for_viewer  # noqa: PLC0415

        queryset = self.visible_to(account, persona_ids=persona_ids, since=since)
        if account is None or not account.is_authenticated or account.is_staff:
            return queryset
        hidden_persona_ids = hidden_persona_ids_for_viewer(viewer_account=account)
        if hidden_persona_ids:
            queryset = queryset.exclude(persona_id__in=hidden_persona_ids)
        return queryset


# Preserve the idmapper-cached .get() by subclassing SharedMemoryManager.
InteractionManager = GuardedSharedMemoryManager.from_queryset(InteractionQuerySet)
