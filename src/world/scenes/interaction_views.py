from __future__ import annotations

from collections.abc import Sequence
from http import HTTPMethod
from typing import Any

from django.db.models import Prefetch, Q, QuerySet
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.pagination import BasePagination, CursorPagination, PageNumberPagination
from rest_framework.permissions import AllowAny, BasePermission, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.serializers import BaseSerializer

from flows.scene_data_manager import SceneDataManager
from flows.service_functions.communication import message_location
from world.magic.models import CharacterResonance, PoseEndorsement, SceneEntryEndorsement
from world.scenes.block_services import flag_blocked_contact_attempt, hidden_persona_ids_for_viewer
from world.scenes.constants import (
    InteractionMode,
    PersonaType,
    PoseKind,
    ReactionWindowKind,
)
from world.scenes.interaction_filters import (
    InteractionFavoriteFilter,
    InteractionFilter,
    InteractionReactionFilter,
)
from world.scenes.interaction_link_services import auto_link_pose_to_actions
from world.scenes.interaction_permissions import (
    CanViewInteraction,
    IsInteractionWriter,
    get_account_personas,
    get_account_roster_entries,
)
from world.scenes.interaction_serializers import (
    InteractionDetailSerializer,
    InteractionFavoriteSerializer,
    InteractionListSerializer,
    InteractionReactionSerializer,
    PoseSubmitSerializer,
    ReactionEmojiSerializer,
)
from world.scenes.interaction_services import (
    delete_interaction,
    idempotent_record_interaction,
    mark_very_private,
    personas_for_characters,
    resolve_characters_by_name,
)
from world.scenes.models import (
    Interaction,
    InteractionAction,
    InteractionFavorite,
    InteractionReaction,
    Persona,
    ReactionEmoji,
    Scene,
    SceneParticipation,
)
from world.scenes.place_models import InteractionReceiver
from world.scenes.reachability import UnreachableError
from world.scenes.reaction_models import ReactionWindow, WindowReaction
from world.scenes.reaction_services import open_reaction_window
from world.scenes.reaction_toggle_services import (
    toggle_interaction_favorite,
    toggle_interaction_reaction,
)
from world.scenes.reply_link_handler import InteractionReplyHandler
from world.scenes.services import active_persona_for_sheet
from world.scenes.thread_services import InteractionThreadError, ReplyTarget


def _refusal_response(*, code: str, field: str, detail: str, hint: str | None) -> Response:
    """Shared 400 body shape for a typed submit-pose refusal.

    Both ``InteractionThreadError`` (reply refusal) and ``UnreachableError``
    (#3787 Task 4 tagging refusal) translate through this one shape --
    ``hint`` is omitted rather than sent as ``null`` when the refusal carries
    none (``InteractionThreadError`` only sets it for the Place-to-Scene reply
    mismatch; every ``UnreachableError`` carries one).
    """
    body: dict[str, str] = {"code": code, "field": field, "detail": detail}
    if hint is not None:
        body["hint"] = hint
    return Response(body, status=status.HTTP_400_BAD_REQUEST)


class InteractionCursorPagination(CursorPagination):
    page_size = 50
    ordering = "-timestamp"
    cursor_query_param = "cursor"
    cursor_query_description = "The pagination cursor value."


class InteractionViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    """ViewSet for browsing interactions with destroy and mark_private actions."""

    filter_backends = [DjangoFilterBackend]
    filterset_class = InteractionFilter
    pagination_class = InteractionCursorPagination
    permission_classes = [IsAuthenticated]

    def get_serializer_context(self) -> dict[str, Any]:
        context = super().get_serializer_context()
        entries = get_account_roster_entries(self.request)
        context["roster_entry_ids"] = {e.pk for e in entries} if entries else set()
        # The viewer's own character sheets — who their PersonaDiscovery rows belong to,
        # for per-viewer persona-name resolution (#1109).
        context["viewer_sheet_ids"] = {e.character_sheet_id for e in entries} if entries else set()
        # #1279 — staff are universal discoverers: they see real identities behind masks
        # everywhere, not just in the report detail serializer.
        context["is_staff"] = self.request.user.is_staff
        # Per-viewer my_reaction on reaction windows (#904) — context, never
        # Prefetch(to_attr) on the shared instances.
        context["persona_ids"] = set(get_account_personas(self.request))
        # Viewer's character sheet PKs — used for my_pose_endorsement and
        # entry_endorsed_by_me (#1138).
        context["character_sheet_ids"] = (
            {e.character_sheet_id for e in entries} if entries else set()
        )
        # Scene-entry endorsements indexed by endorsee_sheet_id — loaded once
        # per list request, keyed by the scene query param (#1138).
        scene_id = self.request.query_params.get("scene")  # noqa: USE_FILTERSET
        entry_map: dict[int, list] = {}
        if scene_id:
            rows = (
                SceneEntryEndorsement.objects.filter(scene_id=scene_id)
                .select_related("endorser_sheet", "resonance")
                .prefetch_related(
                    Prefetch(
                        "endorser_sheet__personas",
                        queryset=Persona.objects.filter(persona_type=PersonaType.PRIMARY),
                        to_attr="cached_primary_persona",
                    )
                )
            )
            for r in rows:
                entry_map.setdefault(r.endorsee_sheet_id, []).append(r)
        context["scene_entry_endorsements"] = entry_map
        # Viewer's GM/owner status for the ?scene= filter, computed once per
        # request (not once per interaction row, and not via Scene.is_gm()/
        # is_owner()'s participations_cached — a fresh query per distinct
        # in-memory Scene instance since select_related builds a new one per
        # row). Pre-seeds InteractionListSerializer._viewer_can_gm_scene's
        # per-scene cache directly so the dramatic_moment_suggestions field
        # never re-derives it (#2183).
        viewer_can_gm_cache: dict[int, bool] = {}
        if scene_id:
            user = self.request.user
            if user.is_authenticated:
                viewer_can_gm_cache[int(scene_id)] = bool(
                    user.is_staff
                    or SceneParticipation.objects.filter(
                        Q(is_gm=True) | Q(is_owner=True),
                        scene_id=scene_id,
                        account_id=user.pk,
                    ).exists()
                )
        context["_viewer_can_gm_cache"] = viewer_can_gm_cache
        return context

    def get_queryset(self) -> QuerySet[Interaction]:
        # Deferred: world.combat imports world.scenes at module scope elsewhere;
        # importing CombatRoundAction lazily keeps this view free of an import cycle.
        from world.combat.models import CombatRoundAction  # noqa: PLC0415
        from world.magic.constants import SuggestionStatus  # noqa: PLC0415
        from world.magic.models.dramatic_moment import (  # noqa: PLC0415
            DramaticMomentSuggestion,
            DramaticMomentTag,
        )

        base_qs = Interaction.objects.select_related(
            "persona__character_sheet",
            "persona__character_sheet__roster_entry",
            "persona__character_sheet__gender",  # #1109: apparent gender for anonymous sdesc
            "persona",
            "scene",
            "place",
            "language",  # #2993: read-time comprehension needs is_universal/trait_id inline
            "attributed_companion",  # #3294: N+1-safe companion-attribution rendering
        ).prefetch_related(
            Prefetch(
                "persona__character_sheet__resonances",
                queryset=CharacterResonance.objects.select_related("resonance"),
                to_attr="cached_resonances",
            ),
            Prefetch(
                "endorsements",
                queryset=PoseEndorsement.objects.select_related(
                    "endorser_sheet", "resonance"
                ).prefetch_related(
                    Prefetch(
                        "endorser_sheet__personas",
                        queryset=Persona.objects.filter(persona_type=PersonaType.PRIMARY),
                        to_attr="cached_primary_persona",
                    )
                ),
                to_attr="cached_endorsements",
            ),
            Prefetch(
                "target_personas",
                queryset=Persona.objects.all(),
                to_attr="cached_target_personas",
            ),
            Prefetch(
                "favorites",
                queryset=InteractionFavorite.objects.all(),
                to_attr="cached_favorites",
            ),
            Prefetch(
                "receivers",
                queryset=InteractionReceiver.objects.select_related("persona"),
                to_attr="cached_receivers",
            ),
            Prefetch(
                "reactions",
                queryset=InteractionReaction.objects.all(),
                to_attr="cached_reactions",
            ),
            Prefetch(
                "action_links",
                queryset=InteractionAction.objects.select_related("action_interaction"),
                to_attr="cached_action_links",
            ),
            # has_critical_effect (#996): attach each linked ACTION's
            # CombatRoundAction(s) + focused opponent to the action_interaction
            # instances as `cached_round_actions`. A separate top-level path
            # prefetch (not nested inside the to_attr queryset above, where a
            # two-hop prefetch through the select_related forward FK fails to
            # attach). SharedMemoryModel shares instances by pk, so this lands on
            # the very same action_interaction objects cached_action_links exposes.
            Prefetch(
                "action_links__action_interaction__combat_round_actions",
                queryset=CombatRoundAction.objects.select_related("focused_opponent_target"),
                to_attr="cached_round_actions",
            ),
            Prefetch(
                "reaction_windows",
                queryset=ReactionWindow.objects.prefetch_related(
                    Prefetch(
                        "reactions",
                        queryset=WindowReaction.objects.select_related("reactor_persona"),
                        to_attr="cached_reaction_rows",
                    )
                ),
                to_attr="cached_reaction_windows",
            ),
            Prefetch(
                "dramatic_moment_tags",
                queryset=DramaticMomentTag.objects.select_related("moment_type"),
                to_attr="cached_dramatic_moment_tags",
            ),
            Prefetch(
                "dramatic_moment_suggestions",
                queryset=DramaticMomentSuggestion.objects.filter(
                    status=SuggestionStatus.PENDING
                ).select_related("moment_type"),
                to_attr="cached_dramatic_moment_suggestions",
            ),
        )

        # Read-visibility lives on the Interaction queryset so the scene highlight reel
        # (#1241) shares the exact same gate — no parallel privacy implementation.
        user = self.request.user
        persona_ids = get_account_personas(self.request) if user.is_authenticated else []
        since = self.request.query_params.get("since") or self.request.query_params.get("from")  # noqa: USE_FILTERSET
        qs = base_qs.visible_to(user, persona_ids=persona_ids, since=since)
        # #1278 — hide personas the viewer can't see (Block, enforced, staff bypass).
        # Muted personas (#2087) are NOT excluded here — their interactions stay in the
        # feed with content blanked by the serializer ("actions still show without text").
        exclude_persona_ids: set[int] = set()
        if not user.is_staff:
            exclude_persona_ids = hidden_persona_ids_for_viewer(viewer_account=user)
        if exclude_persona_ids:
            qs = qs.exclude(persona_id__in=exclude_persona_ids)
        return qs

    def get_serializer_class(
        self,
    ) -> type[BaseSerializer[Interaction]]:
        if self.action == "retrieve":
            return InteractionDetailSerializer
        return InteractionListSerializer

    def get_permissions(self) -> Sequence[BasePermission]:
        # Sequence, not list: this class also defines a `list()` action method
        # (below), and a bare `list[...]` annotation elsewhere in the same class
        # body resolves against that method rather than the builtin.
        if self.action == "list":
            # Public shop-window read (#3305): landing-page scene excerpt.
            # Scoping lives in InteractionQuerySet.visible_to's anonymous
            # branch (public-room-heard only, 90-day bound).
            return [AllowAny()]
        if self.action == "destroy":
            return [IsAuthenticated(), IsInteractionWriter()]
        if self.action == "retrieve":
            return [IsAuthenticated(), CanViewInteraction()]
        return [permission() for permission in self.permission_classes]

    @property
    def paginator(self) -> BasePagination | None:
        pager = super().paginator
        if pager is not None and not self.request.user.is_authenticated:
            pager.page_size = 5  # landing page needs ~2; no throttling exists (#3305)
        return pager

    def destroy(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        interaction = self.get_object()
        persona_ids = get_account_personas(request)
        if not persona_ids or interaction.persona_id not in persona_ids:
            return Response(
                {"detail": "You are not the writer of this interaction."},
                status=status.HTTP_403_FORBIDDEN,
            )
        writer_persona = Persona.objects.get(pk=interaction.persona_id)
        deleted = delete_interaction(interaction, writer_persona)
        if not deleted:
            return Response(
                {"detail": "Cannot delete this interaction (too old or not yours)."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=[HTTPMethod.POST], url_path="mark-private")
    def mark_private(self, request: Request, pk: int | None = None) -> Response:
        interaction = self.get_object()
        persona_ids = get_account_personas(request)
        if not persona_ids:
            return Response(
                {"detail": "No personas found for your account."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        # Try each persona -- mark_very_private checks receiver/writer internally
        personas = Persona.objects.filter(pk__in=persona_ids)
        for persona in personas:
            mark_very_private(interaction, persona)
        serializer = self.get_serializer(interaction)
        return Response(serializer.data)

    @action(detail=False, methods=[HTTPMethod.POST], url_path="submit-pose")
    def submit_pose(self, request: Request) -> Response:
        """Create a POSE Interaction with full WS-pose-path parity (#2156).

        Accepts ``action_link_ids`` for an explicit override:
        - Absent (key missing): auto-link is run.
        - Present as a list (even empty): exact links are created; auto-link skipped.

        Mirrors ``actions.definitions.communication.PoseAction.execute``: broadcasts
        the raw text via ``message_location`` (telnet visibility), records through the
        shared ``record_interaction`` seam (ephemeral-scene gate, SceneParticipation +
        covenant engagement), and flags blocked-contact attempts for any resolved
        directed-pose targets. ``target_names`` (composer-mode ``@Name`` targets) are
        resolved with the same semantics as the WS ``@Name``-prefix parser.
        """
        serializer = PoseSubmitSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        # The submitted persona_id (ownership-validated) only SELECTS the acting
        # character; authorship is always the character's currently-worn face
        # (#981 active persona), derived server-side so a client passing the
        # primary persona can never unmask a worn ESTABLISHED alt or mask.
        selected = Persona.objects.get(pk=data["persona_id"])
        persona = active_persona_for_sheet(selected.character_sheet)
        scene: Scene | None = (
            Scene.objects.get(pk=data["scene_id"]) if data.get("scene_id") else None
        )
        character = persona.character_sheet.character
        pose_kind = data.get("pose_kind", PoseKind.STANDARD)
        content = data["content"]

        target_names: list[str] = data.get("target_names") or []
        target_characters = (
            resolve_characters_by_name(target_names, character.location)
            if target_names and character.location is not None
            else []
        )
        target_personas = personas_for_characters(target_characters) if target_characters else None

        # #1278/#2088 — flag circumvention: a blocked player directing a pose at the
        # blocker via another identity. Mirrors PoseAction.execute's directed-pose gate.
        for target_persona in target_personas or []:
            flag_blocked_contact_attempt(
                initiator_persona=persona,
                target_persona=target_persona,
                scene=scene,
            )

        action_link_ids: list[int] | None = data.get("action_link_ids")

        def _on_created(created: Interaction) -> None:
            if pose_kind == PoseKind.ENTRY and created.scene_id is not None:
                # #904 — an entrance is a reactable moment; the window stays
                # open (and reactable) until the scene closes.
                open_reaction_window(interaction=created, kind=ReactionWindowKind.ENTRANCE)

            if action_link_ids is not None:
                # Explicit override: create exactly the supplied links in order,
                # skipping auto-link entirely (empty list = caller opted out).
                InteractionAction.objects.bulk_create(
                    [
                        InteractionAction(
                            pose=created,
                            action_interaction_id=aid,
                            ordering=i,
                        )
                        for i, aid in enumerate(action_link_ids)
                    ]
                )
            else:
                auto_link_pose_to_actions(created)

        client_request_id = data["client_request_id"]
        reply_data = data.get("reply_to")
        reply_target = (
            ReplyTarget(
                interaction_id=reply_data["id"],
                timestamp=reply_data["timestamp"],
            )
            if reply_data is not None
            else None
        )
        # Target/scene identity (#3760 final review Finding 3): a content-only
        # comparison silently misclassified "same text, different target or
        # scene" as a legitimate replay -- nothing (re-)delivered to the new
        # audience, caller told it succeeded. Mirrors the fix already applied
        # to PoseAction/WhisperAction (commit 64d7ce3e1,
        # actions/definitions/communication.py) for this REST sibling.
        # target_personas is M2M (via InteractionTargetPersona), so it can't
        # be a plain getattr(stored, field) == value comparison like
        # scene_id can; see idempotent_record_interaction's
        # _comparison_fields_match for the callable contract.
        target_persona_pks = (
            frozenset(p.pk for p in target_personas) if target_personas else frozenset()
        )
        try:
            result = idempotent_record_interaction(
                persona=persona,
                client_request_id=client_request_id,
                comparison_fields={
                    "content": content,
                    "pose_kind": pose_kind,
                    "scene_id": scene.pk if scene is not None else None,
                    "target": lambda stored: (
                        frozenset(p.pk for p in stored.target_personas.all()) == target_persona_pks
                    ),
                },
                character=character,
                content=content,
                mode=InteractionMode.POSE,
                scene=scene,
                pose_kind=pose_kind,
                target_personas=target_personas,
                reply_to=reply_target,
                on_created=_on_created,
            )
        except InteractionThreadError as exc:
            return _refusal_response(
                code=exc.code, field="reply_to", detail=str(exc), hint=exc.venue_hint
            )
        except UnreachableError as exc:
            # #3787 Task 4 - refuse tagging a persona who cannot receive the row.
            # Nothing was written: create_interaction raises before any bulk_create.
            return _refusal_response(
                code=exc.code, field="target_names", detail=str(exc), hint=exc.venue_hint
            )

        if result.conflict:
            return Response(
                {"detail": "This request id was already used for different content."},
                status=status.HTTP_409_CONFLICT,
            )

        # Broadcast raw text for telnet clients (WS parity — mirrors
        # PoseAction.execute's message_location call). Gated on `not result.replayed`
        # rather than a separate pre-check query (#3760 review fix): a bare
        # PoseSubmission.exists() pre-check race-loses to two genuinely concurrent
        # retries (both can observe "not found" before either commits), whereas
        # `result.replayed` is already race-safe — idempotent_record_interaction's
        # IntegrityError-catch-and-reread path also reports replayed=True for the
        # loser of a true race, so deriving the gate from it closes that hole too.
        # A submission that never reaches the ledger (e.g. the InteractionThreadError
        # 400 above) is, by design, re-validated fresh on every attempt (spec
        # Decision 3) and so broadcasts again on retry.
        if not result.replayed:
            sdm = SceneDataManager()
            caller_state = sdm.initialize_state_for_object(character)
            message_location(caller_state, content)

        interaction = result.interaction
        response_status = status.HTTP_200_OK if result.replayed else status.HTTP_201_CREATED

        if interaction is None:
            # Ephemeral scene: record_interaction already pushed the real-time
            # payload (push_ephemeral_interaction) and deliberately never persists
            # an Interaction row — there is nothing to serialize as a resource.
            # Reachable both on first acceptance and on a clean replay of one
            # (idempotent_record_interaction never treats an ephemeral acceptance
            # as a conflict — there is nothing stored to compare against).
            return Response(
                {"ephemeral": True, "replayed": result.replayed}, status=response_status
            )

        # The interaction has not been through get_queryset()'s Prefetch pipeline —
        # freshly created, or (on replay) fetched via idempotent_record_interaction's
        # bare select_related lookup — so the cached_* to_attr attributes used by
        # InteractionListSerializer do not exist yet. Set them to empty lists to
        # avoid AttributeError on serialization; a new pose has no receivers,
        # favorites, or reactions (target personas are whatever we just resolved).
        interaction.cached_receivers = []
        interaction.cached_target_personas = target_personas or []
        interaction.cached_favorites = []
        interaction.cached_reactions = []
        interaction.cached_action_links = []
        interaction.cached_dramatic_moment_tags = []
        interaction.cached_dramatic_moment_suggestions = []
        interaction.cached_endorsements = []
        # ENTRY poses opened a window above; let the serializer query it (no
        # cached attr) so the fresh response includes the reactable strip.
        interaction.cached_reaction_windows = None
        out_serializer = InteractionListSerializer(
            interaction, context=self.get_serializer_context()
        )
        return Response(
            {**out_serializer.data, "replayed": result.replayed}, status=response_status
        )

    def list(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """Paginate as usual, then prime the reply-link handler for the whole page.

        Read through InteractionReplyHandler (Interaction.reply_link_handler) rather
        than a bare Prefetch with a `to_attr` kwarg in get_queryset above: that
        spelling silently stops running the second time an instance is warm under the
        identity map (ADR-0263, #3673) - the trap the other cached_* fields there
        still carry, predating that ADR. Otherwise identical to
        ListModelMixin.list(). Defined last in the class body so an earlier
        `list[...]` annotation above (get_permissions) resolves to the builtin, not
        this method.
        """
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            InteractionReplyHandler.prime(list(page))
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)


class InteractionFavoritePagination(PageNumberPagination):
    page_size = 50


class InteractionFavoriteViewSet(viewsets.ModelViewSet):
    """ViewSet for toggling interaction favorites."""

    serializer_class = InteractionFavoriteSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = InteractionFavoritePagination
    filter_backends = [DjangoFilterBackend]
    filterset_class = InteractionFavoriteFilter
    http_method_names = ["post", "delete", "get"]

    def get_queryset(self) -> QuerySet[InteractionFavorite]:
        roster_entries = get_account_roster_entries(self.request)
        if not roster_entries:
            return InteractionFavorite.objects.none()
        return InteractionFavorite.objects.filter(roster_entry__in=roster_entries).order_by(
            "-timestamp"
        )

    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """Toggle a favorite on or off for the authenticated user."""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        interaction = serializer.validated_data["interaction"]
        roster_entries = get_account_roster_entries(request)
        if not roster_entries:
            return Response(
                {"detail": "No roster entries found for your account."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        # Use the first roster entry for favorites
        roster_entry = roster_entries[0]
        created, favorite = toggle_interaction_favorite(
            interaction=interaction,
            roster_entry=roster_entry,
        )
        if not created:
            return Response(
                {"detail": "Favorite removed."},
                status=status.HTTP_200_OK,
            )
        return Response(
            InteractionFavoriteSerializer(favorite).data,
            status=status.HTTP_201_CREATED,
        )


class InteractionReactionViewSet(viewsets.ModelViewSet):
    """Toggle emoji reactions on interactions.

    A cataloged emoji with nonzero valence additionally fires an ambient
    relationship bump at the pose's author (#1699). The chip toggle is the
    primary behavior — a failed/deduped bump never blocks the reaction, and
    un-reacting never reverts a bump (the per-interaction unique constraint
    prevents re-farming).
    """

    serializer_class = InteractionReactionSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = InteractionFavoritePagination
    filter_backends = [DjangoFilterBackend]
    filterset_class = InteractionReactionFilter
    http_method_names = ["post", "delete"]

    def get_queryset(self) -> QuerySet[InteractionReaction]:
        return InteractionReaction.objects.filter(account=self.request.user).order_by("-pk")

    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """Toggle: delete if exists, create if not."""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        interaction = serializer.validated_data["interaction"]
        emoji = serializer.validated_data["emoji"]
        created, reaction = toggle_interaction_reaction(
            interaction=interaction,
            account=request.user,  # type: ignore[invalid-argument-type]
            emoji=emoji,
        )
        if not created:
            return Response(status=status.HTTP_204_NO_CONTENT)
        bump_applied, bump_message = self._maybe_apply_bump(request, interaction, emoji)
        return Response(
            {
                **InteractionReactionSerializer(reaction).data,
                "bump_applied": bump_applied,
                "bump_message": bump_message,
            },
            status=status.HTTP_201_CREATED,
        )

    def _maybe_apply_bump(
        self, request: Request, interaction: Any, emoji: str
    ) -> tuple[bool, str | None]:
        """Fire the relationship bump for a valenced catalog emoji; never raise."""
        from actions.definitions.relationships import RelationshipBumpAction  # noqa: PLC0415

        catalog_entry = ReactionEmoji.objects.filter(emoji=emoji, is_active=True).first()
        if catalog_entry is None or catalog_entry.valence == 0:
            return False, None
        actor = request.user.puppet
        if actor is None:
            return False, None
        author_persona = interaction.persona
        if author_persona is None or author_persona.character_sheet is None:
            return False, None
        result = RelationshipBumpAction().run(
            actor=actor,
            target_sheet=author_persona.character_sheet,
            valence=catalog_entry.valence,
            interaction=interaction,
            source_emoji=catalog_entry,
        )
        return result.success, (result.message if result.success else None)


class ReactionEmojiViewSet(viewsets.ReadOnlyModelViewSet):
    """The active reaction-emoji catalog the scene footer renders (#1699)."""

    serializer_class = ReactionEmojiSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = InteractionFavoritePagination
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["valence"]
    http_method_names = ["get"]

    def get_queryset(self) -> QuerySet[ReactionEmoji]:
        return ReactionEmoji.objects.filter(is_active=True)
