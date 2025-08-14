from django.conf import settings
from django.contrib.auth import login as auth_login, logout as auth_logout
from django.contrib.auth.forms import AuthenticationForm
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
                character__db_account__isnull=False,
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
