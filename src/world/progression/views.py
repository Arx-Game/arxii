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

from django.core.exceptions import ObjectDoesNotExist
from django.shortcuts import get_object_or_404
import django_filters
from django_filters.rest_framework import DjangoFilterBackend
from evennia.accounts.models import AccountDB
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.pagination import LimitOffsetPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from world.journals.models import JournalEntry
from world.progression.constants import VoteTargetType
from world.progression.models import (
    ExperiencePointsData,
    KudosClaimCategory,
    KudosPointsData,
    KudosTransaction,
    RandomSceneTarget,
    WeeklyVote,
    WeeklyVoteBudget,
    XPTransaction,
)
from world.progression.serializers import (
    AccountProgressionSerializer,
    CastVoteResponseSerializer,
    CastVoteSerializer,
    RandomSceneTargetSerializer,
    VoteBudgetSerializer,
    WeeklyVoteSerializer,
)
from world.progression.services.kudos import InsufficientKudosError, claim_kudos_for_xp
from world.progression.services.random_scene import (
    claim_random_scene,
    reroll_random_scene_target,
)
from world.progression.services.voting import (
    cast_vote,
    get_current_week_start,
    get_or_create_vote_budget,
    get_votes_by_voter,
    remove_vote,
)
from world.progression.types import ProgressionError
from world.scenes.models import Interaction, SceneParticipation
from world.stories.pagination import StandardResultsSetPagination

# Default and maximum transaction limit for pagination
DEFAULT_TRANSACTION_LIMIT = 50
MAX_TRANSACTION_LIMIT = 200


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

        try:
            claim_kudos_for_xp(
                account=cast(AccountDB, request.user),
                amount=amount,
                claim_category=claim_category,
            )
        except InsufficientKudosError:
            return Response(
                {"detail": "Insufficient kudos for this conversion."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except ValueError:
            return Response(
                {"detail": "Invalid amount for this conversion rate."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return _build_progression_response(request)


# --- Voting views ---


def _get_author_account_for_target(
    target_type: str,
    target_id: int,
) -> AccountDB | None:
    """Derive the author account from a vote target.

    Follows the FK chain from the target object to the account that authored it.
    Returns None if the chain is broken (e.g. no roster entry or no active tenure).
    """
    if target_type == VoteTargetType.INTERACTION:
        interaction = get_object_or_404(Interaction, pk=target_id)
        try:
            entry = interaction.persona.character.roster_entry
            tenure = entry.current_tenure
            return tenure.player_data.account if tenure else None
        except (AttributeError, ObjectDoesNotExist):
            return None
    elif target_type == VoteTargetType.SCENE_PARTICIPATION:
        participation = get_object_or_404(SceneParticipation, pk=target_id)
        return participation.account
    elif target_type == VoteTargetType.JOURNAL:
        journal = get_object_or_404(JournalEntry, pk=target_id)
        try:
            entry = journal.author.character.roster_entry
            tenure = entry.current_tenure
            return tenure.player_data.account if tenure else None
        except (AttributeError, ObjectDoesNotExist):
            return None
    return None


class WeeklyVoteFilter(django_filters.FilterSet):
    """Filter for WeeklyVote list views."""

    target_type = django_filters.ChoiceFilter(choices=VoteTargetType.choices)

    class Meta:
        model = WeeklyVote
        fields = ["target_type"]


class VoteViewSet(viewsets.ViewSet):
    """ViewSet for casting, removing, and listing weekly votes.

    POST /votes/ — Cast a vote
    DELETE /votes/<id>/ — Unvote
    GET /votes/ — List current week's votes for the requesting user
    GET /votes/budget/ — Return current vote budget
    """

    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination
    filter_backends = [DjangoFilterBackend]
    filterset_class = WeeklyVoteFilter

    def list(self, request: Request) -> Response:
        """List current week's unprocessed votes for the requesting user."""
        account = cast(AccountDB, request.user)
        votes = get_votes_by_voter(account)
        serializer = WeeklyVoteSerializer(votes, many=True)
        return Response(serializer.data)

    def create(self, request: Request) -> Response:
        """Cast a vote on a piece of content."""
        serializer = CastVoteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        target_type = serializer.validated_data["target_type"]
        target_id = serializer.validated_data["target_id"]
        voter = cast(AccountDB, request.user)

        author_account = _get_author_account_for_target(target_type, target_id)
        if author_account is None:
            return Response(
                {"detail": "Could not determine author for the specified target."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            vote = cast_vote(
                voter_account=voter,
                target_type=target_type,
                target_id=target_id,
                author_account=author_account,
            )
        except ProgressionError as exc:
            return Response(
                {"detail": exc.user_message},
                status=status.HTTP_400_BAD_REQUEST,
            )

        WeeklyVoteBudget.flush_instance_cache()
        budget = get_or_create_vote_budget(voter)
        response_serializer = CastVoteResponseSerializer(
            {"vote": vote, "budget": budget},
        )
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)

    def destroy(self, request: Request, pk: Any = None) -> Response:
        """Remove (unvote) an existing vote by ID."""
        voter = cast(AccountDB, request.user)
        vote = get_object_or_404(WeeklyVote, pk=pk, voter=voter)

        try:
            remove_vote(
                voter_account=voter,
                target_type=vote.target_type,
                target_id=vote.target_id,
            )
        except ProgressionError as exc:
            return Response(
                {"detail": exc.user_message},
                status=status.HTTP_400_BAD_REQUEST,
            )

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


class RandomSceneViewSet(viewsets.ViewSet):
    """ViewSet for listing, claiming, and rerolling weekly random scene targets.

    GET /random-scenes/ — List current week's targets for the requesting user
    POST /random-scenes/<id>/claim/ — Claim a target
    POST /random-scenes/<id>/reroll/ — Reroll a target
    """

    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination

    def list(self, request: Request) -> Response:
        """List current week's random scene targets for the requesting user."""
        account = cast(AccountDB, request.user)
        week_start = get_current_week_start()
        RandomSceneTarget.flush_instance_cache()
        targets = (
            RandomSceneTarget.objects.filter(
                account=account,
                week_start=week_start,
            )
            .select_related("target_character")
            .order_by("slot_number")
        )
        serializer = RandomSceneTargetSerializer(targets, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=[HTTPMethod.POST])
    def claim(self, request: Request, pk: Any = None) -> Response:
        """Claim a random scene target, awarding XP."""
        account = cast(AccountDB, request.user)
        try:
            target = claim_random_scene(account=account, target_id=pk)
        except ProgressionError as exc:
            return Response(
                {"detail": exc.user_message},
                status=status.HTTP_400_BAD_REQUEST,
            )
        RandomSceneTarget.flush_instance_cache()
        serializer = RandomSceneTargetSerializer(target)
        return Response(serializer.data)

    @action(detail=True, methods=[HTTPMethod.POST])
    def reroll(self, request: Request, pk: Any = None) -> Response:
        """Reroll a random scene target slot."""
        account = cast(AccountDB, request.user)
        week_start = get_current_week_start()

        # Look up the target to get the slot_number
        target = RandomSceneTarget.objects.filter(
            pk=pk,
            account=account,
            week_start=week_start,
        ).first()
        if target is None:
            return Response(
                {"detail": "Random scene target not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        try:
            updated_target = reroll_random_scene_target(
                account=account,
                slot_number=target.slot_number,
                week_start=week_start,
            )
        except ProgressionError as exc:
            return Response(
                {"detail": exc.user_message},
                status=status.HTTP_400_BAD_REQUEST,
            )
        RandomSceneTarget.flush_instance_cache()
        serializer = RandomSceneTargetSerializer(updated_target)
        return Response(serializer.data)
