from django.conf import settings
from django.contrib.auth import login as auth_login, logout as auth_logout
from django.contrib.auth.forms import AuthenticationForm
from django.db import IntegrityError
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.utils.timesince import timesince
from django.views.decorators.csrf import ensure_csrf_cookie
from evennia import SESSION_HANDLER
from evennia.accounts.models import AccountDB
from evennia.objects.models import ObjectDB
from evennia.utils import class_from_module
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from web.api.serializers import AccountPlayerSerializer
from world.roster.models import RosterEntry


class HomePageAPIView(APIView):
    """Return context for the Evennia home page."""

    permission_classes = [AllowAny]

    def get(self, request, *args, **kwargs):
        """Return basic game statistics.

        Args:
            request: DRF request.
            *args: Additional positional arguments.
            **kwargs: Additional keyword arguments.

        Returns:
            Response: JSON data for the homepage statistics.
        """

        recent_accounts = list(AccountDB.objects.get_recently_connected_accounts())
        account_limit = 4
        accounts_data = []
        for account in recent_accounts[:account_limit]:
            last_login = ""
            if account.last_login:
                last_login = timesince(account.last_login, timezone.now())
            accounts_data.append(
                {"username": account.username, "last_login": last_login}
            )

        character_cls = class_from_module(
            settings.BASE_CHARACTER_TYPECLASS,
            fallback=settings.FALLBACK_CHARACTER_TYPECLASS,
        )
        room_cls = class_from_module(
            settings.BASE_ROOM_TYPECLASS, fallback=settings.FALLBACK_ROOM_TYPECLASS
        )
        exit_cls = class_from_module(
            settings.BASE_EXIT_TYPECLASS, fallback=settings.FALLBACK_EXIT_TYPECLASS
        )

        num_characters = character_cls.objects.all_family().count()
        num_rooms = room_cls.objects.all_family().count()
        num_exits = exit_cls.objects.all_family().count()
        num_objects = ObjectDB.objects.count()

        context = {
            "num_accounts_connected": SESSION_HANDLER.account_count(),
            "num_accounts_registered": AccountDB.objects.count(),
            "num_accounts_registered_recent": (
                AccountDB.objects.get_recently_created_accounts().count()
            ),
            "num_accounts_connected_recent": len(recent_accounts),
            "num_characters": num_characters,
            "num_rooms": num_rooms,
            "num_exits": num_exits,
            "num_others": num_objects - num_characters - num_rooms - num_exits,
            "page_title": "Arx II",
            "accounts_connected_recent": accounts_data,
        }
        return Response(context)


class ServerStatusAPIView(APIView):
    """Return overall game status."""

    permission_classes = [AllowAny]

    def get(self, request, *args, **kwargs):
        """Return game statistics and recent activity.

        Args:
            request: DRF request.
            *args: Additional positional arguments.
            **kwargs: Additional keyword arguments.

        Returns:
            Response: JSON data with player counts, recent players and news.
        """
        character_cls = class_from_module(
            settings.BASE_CHARACTER_TYPECLASS,
            fallback=settings.FALLBACK_CHARACTER_TYPECLASS,
        )
        room_cls = class_from_module(
            settings.BASE_ROOM_TYPECLASS, fallback=settings.FALLBACK_ROOM_TYPECLASS
        )

        recent_entries = (
            RosterEntry.objects.filter(
                roster__is_active=True,
                last_puppeted__isnull=False,
            )
            .select_related("character")
            .order_by("-last_puppeted")[:4]
        )
        recent_players = [
            {"id": entry.id, "name": entry.character.key} for entry in recent_entries
        ]

        data = {
            "online": SESSION_HANDLER.account_count(),
            "accounts": AccountDB.objects.count(),
            "characters": character_cls.objects.all_family().count(),
            "rooms": room_cls.objects.all_family().count(),
            "recentPlayers": recent_players,
            "news": [],
        }
        return Response(data)


@method_decorator(ensure_csrf_cookie, name="dispatch")
class LoginAPIView(APIView):
    """Return account data for the current session and handle authentication."""

    permission_classes = [AllowAny]

    def get(self, request, *args, **kwargs):
        """Return the current account.

        Args:
            request: DRF request.
            *args: Additional positional arguments.
            **kwargs: Additional keyword arguments.

        Returns:
            Response: Serialized account or ``None``.
        """
        data = None
        if request.user.is_authenticated:
            data = AccountPlayerSerializer(request.user).data
        return Response(data)

    def post(self, request, *args, **kwargs):
        """Authenticate the user and return the account.

        Args:
            request: DRF request.
            *args: Additional positional arguments.
            **kwargs: Additional keyword arguments.

        Returns:
            Response: Serialized account on success or form errors.
        """
        form = AuthenticationForm(request=request, data=request.data)
        if not form.is_valid():
            return Response(form.errors, status=status.HTTP_400_BAD_REQUEST)
        auth_login(request, form.get_user())
        data = AccountPlayerSerializer(form.get_user()).data
        return Response(data)


class RegisterAPIView(APIView):
    """Create a new user account."""

    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        """Handle registration requests.

        Args:
            request: DRF request containing username, password and email.

        Returns:
            Response: Serialized account on success or form errors.
        """
        username = request.data.get("username", "").strip()
        password = request.data.get("password", "")
        email = request.data.get("email", "").strip()

        errors = {}
        if not username:
            errors["username"] = ["This field is required."]
        elif AccountDB.objects.filter(username__iexact=username).exists():
            errors["username"] = ["A user with that username already exists."]

        if not email:
            errors["email"] = ["This field is required."]
        elif AccountDB.objects.filter(email__iexact=email).exists():
            errors["email"] = ["A user with that email already exists."]

        if not password:
            errors["password"] = ["This field is required."]

        if errors:
            return Response(errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            account = AccountDB.objects.create_user(
                username=username, email=email, password=password
            )
        except IntegrityError:
            return Response(
                {"detail": "Account could not be created."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        data = AccountPlayerSerializer(account).data
        return Response(data, status=status.HTTP_201_CREATED)


class RegisterAvailabilityAPIView(APIView):
    """Check if a username or email is available for registration."""

    permission_classes = [AllowAny]

    def get(self, request, *args, **kwargs):
        """Return availability of requested credentials.

        Args:
            request: DRF request with optional ``username`` or ``email`` query params.

        Returns:
            Response: Boolean flags keyed by provided parameters.
        """

        username = request.query_params.get("username")
        email = request.query_params.get("email")
        if username is None and email is None:
            return Response(
                {"detail": "username or email parameter required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        data = {}
        if username is not None:
            data["username"] = not AccountDB.objects.filter(
                username__iexact=username
            ).exists()
        if email is not None:
            data["email"] = not AccountDB.objects.filter(email__iexact=email).exists()
        return Response(data)


class LogoutAPIView(APIView):
    """Log out the current user."""

    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        """Handle POST requests to log out the user.

        Args:
            request: DRF request.
            *args: Additional positional arguments.
            **kwargs: Additional keyword arguments.

        Returns:
            Response: Empty response with status 204.
        """
        auth_logout(request)
        return Response(status=status.HTTP_204_NO_CONTENT)
