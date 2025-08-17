"""Custom django-allauth adapters for Arx II."""

from allauth.account.adapter import DefaultAccountAdapter

from evennia_extensions.models import PlayerData


class ArxAccountAdapter(DefaultAccountAdapter):
    """Custom account adapter for Arx II that creates PlayerData on signup."""

    def save_user(self, request, user, form, commit=True):
        """Save user and create associated PlayerData."""
        # Call parent method to save the user
        user = super().save_user(request, user, form, commit)

        if commit:
            # Create PlayerData for the new user
            PlayerData.objects.get_or_create(account=user)

        return user
