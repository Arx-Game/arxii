"""
API views for progression endpoints.

Note: This module uses a custom APIView rather than ViewSet because it aggregates
data from multiple models (XP, Kudos, transactions) into a single dashboard response.
Converting to ViewSet pattern would require going through Account with complex
nested serializers, which would be more complex without clear benefit for this
read-only dashboard endpoint.
"""

from http import HTTPMethod
from typing import Any, cast

from drf_spectacular.utils import extend_schema
from evennia.accounts.models import AccountDB
from evennia.objects.models import ObjectDB
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.filters import BaseFilterBackend
from rest_framework.pagination import LimitOffsetPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from actions.constants import ActionBackend
from actions.definitions.progression_rewards import (
    CastVoteAction,
    ClaimKudosAction,
    ClaimRandomSceneAction,
    ClearPathIntentAction,
    RemoveVoteAction,
    RerollRandomSceneAction,
    SetPathIntentAction,
)
from actions.player_interface import dispatch_player_action
from actions.types import ActionRef
from web.api.mixins import CharacterContextMixin
from world.character_sheets.models import CharacterSheet
from world.game_clock.week_services import get_current_game_week
from world.magic.services.threads import near_xp_lock_threads
from world.progression.models import (
    ExperiencePointsData,
    KudosClaimCategory,
    KudosPointsData,
    KudosTransaction,
    PathIntent,
    RandomSceneTarget,
    WeeklyVote,
    WeeklyVoteBudget,
    XPTransaction,
)
from world.progression.selectors import current_path_for_character, next_path_options
from world.progression.serializers import (
    AccountProgressionSerializer,
    CastVoteResponseSerializer,
    CastVoteSerializer,
    PathIntentDeclareSerializer,
    PathIntentSerializer,
    PathOptionsSerializer,
    RandomSceneTargetSerializer,
    VoteBudgetSerializer,
    WeeklyVoteSerializer,
)
from world.progression.serializers.unlocks import (
    ProgressionUnlockItemSerializer,
    PurchaseUnlockResponseSerializer,
    PurchaseUnlockSerializer,
)
from world.progression.services.spends import get_available_unlocks_for_character
from world.progression.services.voting import (
    get_or_create_vote_budget,
    get_votes_by_voter,
)
from world.roster.models import RosterEntry
from world.stories.pagination import StandardResultsSetPagination

# Default and maximum transaction limit for pagination
DEFAULT_TRANSACTION_LIMIT = 50
MAX_TRANSACTION_LIMIT = 200

# Repeated 404 detail message, extracted to satisfy S1192.
NO_CHARACTER_FOUND_MESSAGE = "No character found."


class TransactionPagination(LimitOffsetPagination):
    """Pagination for progression transaction lists."""

    default_limit = DEFAULT_TRANSACTION_LIMIT
    max_limit = MAX_TRANSACTION_LIMIT


def _build_progression_response(request: Request) -> Response:
    """Build the standard account progression response."""
    account = request.user

    paginator = TransactionPagination()
    limit = paginator.get_limit(request) or DEFAULT_TRANSACTION_LIMIT
    offset = paginator.get_offset(request)

    xp_data = ExperiencePointsData.objects.filter(account=account).first()
    kudos_data = KudosPointsData.objects.filter(account=account).first()

    xp_transactions = (
        XPTransaction.objects.filter(account=account)
        .select_related("character")
        .order_by("-transaction_date")[offset : offset + limit]
    )

    kudos_transactions = (
        KudosTransaction.objects.filter(account=account)
        .select_related("source_category", "claim_category", "awarded_by")
        .order_by("-transaction_date")[offset : offset + limit]
    )

    claim_categories = KudosClaimCategory.objects.filter(is_active=True)

    data = {
        "xp": xp_data,
        "kudos": kudos_data,
        "xp_transactions": xp_transactions,
        "kudos_transactions": kudos_transactions,
        "claim_categories": claim_categories,
    }

    serializer = AccountProgressionSerializer(data)
    return Response(serializer.data)


def _actor_for_account(account: AccountDB) -> ObjectDB | None:
    """Resolve a representative actor character for an account-level reward action.

    The action resolves the account straight back via get_account_for_character,
    so any of the account's active characters yields the same account. Returns
    None when the account has no active character.
    """
    entry = RosterEntry.objects.for_account(account).first()
    return entry.character_sheet.character if entry else None


class AccountProgressionView(APIView):
    """
    Get the current user's progression data (XP and Kudos).

    Returns XP balance, Kudos balance, recent transactions, and claim options.

    Query Parameters:
        limit (int): Maximum number of transactions to return per type.
                     Default: 50, Max: 200
        offset (int): Number of transactions to skip (for pagination).
                      Default: 0
    """

    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        """Return current user's XP and Kudos data (read-only)."""
        return _build_progression_response(request)


class ClaimKudosView(APIView):
    """
    Claim kudos and convert to XP.

    POST body: { "claim_category_id": int, "amount": int }
    Returns: Updated account progression data.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        """Claim kudos for XP conversion."""
        claim_category_id = request.data.get("claim_category_id")
        amount = request.data.get("amount")

        if claim_category_id is None or amount is None:
            return Response(
                {"detail": "claim_category_id and amount are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            amount = int(amount)
        except (TypeError, ValueError):
            return Response(
                {"detail": "amount must be an integer."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            claim_category = KudosClaimCategory.objects.get(
                id=claim_category_id,
                is_active=True,
            )
        except KudosClaimCategory.DoesNotExist:
            return Response(
                {"detail": "Invalid or inactive claim category."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        account = cast(AccountDB, request.user)
        actor = _actor_for_account(account)
        if actor is None:
            return Response(
                {"detail": "No active character to act as."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        result = ClaimKudosAction().run(
            actor=actor, claim_category_id=claim_category.pk, amount=amount
        )
        if not result.success:
            return Response({"detail": result.message}, status=status.HTTP_400_BAD_REQUEST)
        return _build_progression_response(request)


# --- Voting views ---


class VoteViewSet(
    mixins.ListModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    """ViewSet for casting, removing, and listing weekly votes.

    POST /votes/ — Cast a vote
    DELETE /votes/<id>/ — Unvote
    GET /votes/ — List current week's votes for the requesting user
    GET /votes/budget/ — Return current vote budget
    """

    serializer_class = WeeklyVoteSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self) -> Any:
        """Return current week's unprocessed votes for the requesting user."""
        return get_votes_by_voter(cast(AccountDB, self.request.user))

    def create(self, request: Request) -> Response:
        """Cast a vote on a piece of content."""
        serializer = CastVoteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        target_type = serializer.validated_data["target_type"]
        target_id = serializer.validated_data["target_id"]
        voter = cast(AccountDB, request.user)

        actor = _actor_for_account(voter)
        if actor is None:
            return Response(
                {"detail": "No active character to act as."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        result = CastVoteAction().run(actor=actor, target_type=target_type, target_id=target_id)
        if not result.success:
            return Response({"detail": result.message}, status=status.HTTP_400_BAD_REQUEST)

        WeeklyVote.flush_instance_cache()
        vote = WeeklyVote.objects.get(
            voter=voter,
            game_week=get_current_game_week(),
            target_type=target_type,
            target_id=target_id,
        )
        WeeklyVoteBudget.flush_instance_cache()
        budget = get_or_create_vote_budget(voter)
        response_serializer = CastVoteResponseSerializer(
            {"vote": vote, "budget": budget},
        )
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)

    def destroy(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """Remove (unvote) an existing vote by ID."""
        voter = cast(AccountDB, request.user)
        actor = _actor_for_account(voter)
        if actor is None:
            return Response(
                {"detail": "No active character to act as."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        instance = self.get_object()
        result = RemoveVoteAction().run(
            actor=actor,
            target_type=instance.target_type,
            target_id=instance.target_id,
        )
        if not result.success:
            return Response({"detail": result.message}, status=status.HTTP_400_BAD_REQUEST)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=False, methods=[HTTPMethod.GET])
    def budget(self, request: Request) -> Response:
        """Return the current vote budget for the requesting user."""
        account = cast(AccountDB, request.user)
        WeeklyVoteBudget.flush_instance_cache()
        budget = get_or_create_vote_budget(account)
        serializer = VoteBudgetSerializer(budget)
        return Response(serializer.data)


# --- Random Scene views ---


class RandomSceneViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """ViewSet for listing, claiming, and rerolling weekly random scene targets.

    GET /random-scenes/ — List current week's targets for the requesting user
    POST /random-scenes/<id>/claim/ — Claim a target
    POST /random-scenes/<id>/reroll/ — Reroll a target
    """

    serializer_class = RandomSceneTargetSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self) -> Any:
        """Return current week's random scene targets for the requesting user."""
        account = cast(AccountDB, self.request.user)
        game_week = get_current_game_week()
        return (
            RandomSceneTarget.objects.filter(
                account=account,
                game_week=game_week,
            )
            .select_related("target_persona")
            .order_by("slot_number")
        )

    @action(detail=True, methods=[HTTPMethod.POST])
    def claim(self, request: Request, pk: Any = None) -> Response:
        """Claim a random scene target, awarding XP."""
        account = cast(AccountDB, request.user)
        actor = _actor_for_account(account)
        if actor is None:
            return Response(
                {"detail": "No active character to act as."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        result = ClaimRandomSceneAction().run(actor=actor, target_id=pk)
        if not result.success:
            return Response({"detail": result.message}, status=status.HTTP_400_BAD_REQUEST)
        RandomSceneTarget.flush_instance_cache()
        target = RandomSceneTarget.objects.select_related("target_persona").get(pk=pk)
        serializer = RandomSceneTargetSerializer(target)
        return Response(serializer.data)

    @action(detail=True, methods=[HTTPMethod.POST])
    def reroll(self, request: Request, pk: Any = None) -> Response:
        """Reroll a random scene target slot."""
        account = cast(AccountDB, request.user)
        game_week = get_current_game_week()

        # Pre-check for 404: the target must belong to this account/week.
        target = RandomSceneTarget.objects.filter(
            pk=pk,
            account=account,
            game_week=game_week,
        ).first()
        if target is None:
            return Response(
                {"detail": "Random scene target not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        actor = _actor_for_account(account)
        if actor is None:
            return Response(
                {"detail": "No active character to act as."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        result = RerollRandomSceneAction().run(actor=actor, target_id=pk)
        if not result.success:
            return Response({"detail": result.message}, status=status.HTTP_400_BAD_REQUEST)
        RandomSceneTarget.flush_instance_cache()
        updated_target = RandomSceneTarget.objects.select_related("target_persona").get(pk=pk)
        serializer = RandomSceneTargetSerializer(updated_target)
        return Response(serializer.data)


# --- PathOptions view ---


class PathOptionsView(CharacterContextMixin, APIView):
    """GET /path-options/ — the calling character's current path + selectable next paths.

    Transition-generic (not Audere-specific): the same options drive the level-3
    pick and future path switches. Character resolved via the X-Character-ID header.
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(responses=PathOptionsSerializer)
    def get(self, request: Request) -> Response:
        character = self._get_character(request)
        if character is None:
            return Response(
                {"detail": NO_CHARACTER_FOUND_MESSAGE}, status=status.HTTP_404_NOT_FOUND
            )
        payload = {
            "current_path": current_path_for_character(character),
            "options": next_path_options(character),
        }
        return Response(PathOptionsSerializer(payload).data)


# --- PathIntent view ---


class PathIntentViewSet(CharacterContextMixin, viewsets.ViewSet):
    """Single-resource endpoint for a character's declared path intent.

    GET  path-intent/ — current intent or {"intent": null}
    PUT  path-intent/ — declare/replace intent; body: {"path_id": <int>}
    DELETE path-intent/ — clear intent (idempotent, 204)

    Ownership enforced via CharacterContextMixin: the X-Character-ID header
    must refer to a character in the requesting account's available roster.
    """

    permission_classes = [IsAuthenticated]

    def _get_sheet(self, request: Request) -> CharacterSheet | None:
        """Resolve the CharacterSheet for the requesting character, or None."""
        character = self._get_character(request)
        if character is None:
            return None
        # Reverse OneToOne may be absent for sheet-less characters.
        return getattr(character, "sheet_data", None)  # noqa: GETATTR_LITERAL

    def list(self, request: Request) -> Response:
        """GET — return current intent or {"intent": null}."""
        sheet = self._get_sheet(request)
        if sheet is None:
            return Response(
                {"detail": NO_CHARACTER_FOUND_MESSAGE}, status=status.HTTP_404_NOT_FOUND
            )

        try:
            intent = PathIntent.objects.select_related("intended_path").get(character_sheet=sheet)
        except PathIntent.DoesNotExist:
            return Response({"intent": None})

        return Response({"intent": PathIntentSerializer(intent).data})

    def update(self, request: Request, pk: Any = None) -> Response:
        """PUT — declare or replace the intent for this character."""
        character = self._get_character(request)
        if character is None:
            return Response(
                {"detail": NO_CHARACTER_FOUND_MESSAGE}, status=status.HTTP_404_NOT_FOUND
            )

        serializer = PathIntentDeclareSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        path = serializer.validated_path

        result = SetPathIntentAction().run(actor=character, path_id=path.pk)
        if not result.success:
            return Response({"detail": result.message}, status=status.HTTP_400_BAD_REQUEST)
        PathIntent.flush_instance_cache()
        sheet = character.sheet_data
        intent = PathIntent.objects.select_related("intended_path").get(character_sheet=sheet)
        return Response({"intent": PathIntentSerializer(intent).data})

    def destroy(self, request: Request, pk: Any = None) -> Response:
        """DELETE — clear the intent (idempotent)."""
        character = self._get_character(request)
        if character is None:
            return Response(
                {"detail": NO_CHARACTER_FOUND_MESSAGE}, status=status.HTTP_404_NOT_FOUND
            )

        result = ClearPathIntentAction().run(actor=character)
        if not result.success:
            return Response({"detail": result.message}, status=status.HTTP_400_BAD_REQUEST)
        PathIntent.flush_instance_cache()
        return Response(status=status.HTTP_204_NO_CONTENT)


# --- Unlock shop views ---


def _resolve_puppet_sheet(request: Request) -> tuple[Any, CharacterSheet]:
    """Return the played character and its sheet, or raise ValidationError."""
    puppet = getattr(request.user, "puppet", None)  # noqa: GETATTR_LITERAL
    sheet = getattr(puppet, "sheet_data", None) if puppet is not None else None  # noqa: GETATTR_LITERAL
    if puppet is None or sheet is None:
        msg = "You must be playing a character to view or purchase unlocks."
        raise serializers.ValidationError(msg)
    return puppet, sheet


class UnlockTypeFilterBackend(BaseFilterBackend):
    """Filter ``ProgressionUnlockViewSet.list`` by ``unlock_type``.

    The list is assembled in Python, so this backend performs plain list
    filtering rather than queryset mutation.
    """

    def filter_queryset(self, request: Request, queryset: Any, view: Any) -> Any:
        """Return items matching the requested ``unlock_type``, if any."""
        unlock_type = request.query_params.get("unlock_type")
        if unlock_type is None:
            return queryset
        return [item for item in queryset if item.get("unlock_type") == unlock_type]


class ProgressionUnlockViewSet(viewsets.GenericViewSet):
    """Unlock shop: list available unlocks and purchase them with XP.

    GET /api/progression/unlocks/ — list class-level and thread XP-lock items.
    POST /api/progression/unlocks/purchase/ — buy an unlock via PurchaseUnlockAction.
    """

    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination
    filter_backends = [UnlockTypeFilterBackend]
    serializer_class = ProgressionUnlockItemSerializer
    queryset = []

    @extend_schema(
        responses={200: ProgressionUnlockItemSerializer(many=True)},
    )
    def list(self, request: Request) -> Response:
        """Return a paginated list of purchasable progression unlocks."""
        puppet, sheet = _resolve_puppet_sheet(request)
        character = puppet

        available_unlocks = get_available_unlocks_for_character(character)
        items: list[dict[str, Any]] = []

        for entry in available_unlocks["available"] + available_unlocks["locked"]:
            unlock = entry["unlock"]
            failed = entry.get("failed_requirements", [])
            items.append(
                {
                    "unlock_type": "class_level",
                    "display_name": str(unlock),
                    "xp_cost": entry["xp_cost"],
                    "requirements_met": entry["requirements_met"],
                    "locked_reason": "; ".join(failed) if failed else None,
                    "class_level_unlock_id": unlock.pk,
                    "class_name": unlock.character_class.name,
                    "target_level": unlock.target_level,
                    "thread_id": None,
                    "boundary_level": None,
                    "thread_name": None,
                    "thread_level": None,
                    "thread_resonance_id": None,
                    "thread_resonance_name": None,
                    "thread_target_kind": None,
                    "dev_points_to_boundary": None,
                },
            )

        for prospect in near_xp_lock_threads(sheet):
            thread = prospect.thread
            resonance = thread.resonance
            items.append(
                {
                    "unlock_type": "thread_xp_lock",
                    "display_name": (
                        f"{thread.name or 'Unnamed Thread'} Level {prospect.boundary_level}"
                    ),
                    "xp_cost": prospect.xp_cost,
                    "requirements_met": True,
                    "locked_reason": None,
                    "class_level_unlock_id": None,
                    "class_name": None,
                    "target_level": None,
                    "thread_id": thread.pk,
                    "boundary_level": prospect.boundary_level,
                    "thread_name": thread.name or None,
                    "thread_level": thread.level,
                    "thread_resonance_id": resonance.pk if resonance is not None else None,
                    "thread_resonance_name": resonance.name if resonance is not None else None,
                    "thread_target_kind": thread.target_kind,
                    "dev_points_to_boundary": prospect.dev_points_to_boundary,
                },
            )

        items = cast(list[dict[str, Any]], self.filter_queryset(cast(Any, items)))
        page = self.paginate_queryset(items)
        serializer = ProgressionUnlockItemSerializer(page, many=True)
        return self.get_paginated_response(serializer.data)

    @extend_schema(
        request=PurchaseUnlockSerializer,
        responses={200: PurchaseUnlockResponseSerializer},
    )
    @action(detail=False, methods=[HTTPMethod.POST])
    def purchase(self, request: Request) -> Response:
        """Purchase an unlock by dispatching PurchaseUnlockAction."""
        puppet, _sheet = _resolve_puppet_sheet(request)

        input_serializer = PurchaseUnlockSerializer(data=request.data)
        input_serializer.is_valid(raise_exception=True)
        data = input_serializer.validated_data

        action_kwargs: dict[str, Any] = {"unlock_type": data["unlock_type"]}
        if data["unlock_type"] == PurchaseUnlockSerializer.UNLOCK_TYPE_CLASS_LEVEL:
            action_kwargs["class_level_unlock_id"] = data["class_level_unlock_id"]
        else:
            action_kwargs["thread_id"] = data["thread_id"]
            action_kwargs["boundary_level"] = data["boundary_level"]

        ref = ActionRef(backend=ActionBackend.REGISTRY, registry_key="purchase_unlock")
        result = dispatch_player_action(puppet, ref, action_kwargs)
        detail = result.detail
        if not detail.success:
            raise serializers.ValidationError(detail.message)

        return Response(detail.data)
