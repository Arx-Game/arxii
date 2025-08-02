from django.contrib.auth import login as auth_login
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.sites.shortcuts import get_current_site
from evennia.web.website.views.index import _gamestats
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from web.api.serializers import AccountPlayerSerializer


class HomePageAPIView(APIView):
    """Return context for the Evennia home page."""

    def get(self, request, *args, **kwargs):
        """Handle GET requests."""
        context = _gamestats()
        return Response(context)


class LoginAPIView(APIView):
    """Provide login context and authenticate users."""

    def get(self, request, *args, **kwargs):
        """Return basic login context."""
        current_site = get_current_site(request)
        context = {
            "site_name": current_site.name,
            "next": request.GET.get("next", ""),
        }
        if request.user.is_authenticated:
            context["user"] = AccountPlayerSerializer(request.user).data
        return Response(context)

    def post(self, request, *args, **kwargs):
        """Attempt to authenticate and log the user in."""
        form = AuthenticationForm(request=request, data=request.data)
        if form.is_valid():
            auth_login(request, form.get_user())
            data = {
                "success": True,
                "user": AccountPlayerSerializer(form.get_user()).data,
            }
            return Response(data)
        return Response(
            {"success": False, "errors": form.errors},
            status=status.HTTP_400_BAD_REQUEST,
        )
