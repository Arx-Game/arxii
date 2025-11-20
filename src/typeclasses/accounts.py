"""
Account

The Account represents the game "account" and each login has only one
Account object. An Account is what chats on default channels but has no
other in-game-world existence. Rather the Account puppets Objects (such
as Characters) in order to actually participate in the game world.


Guest

Guest accounts are simple low-level accounts that are created/deleted
on the fly and allows users to test the game without the commitment
of a full registration. Guest accounts are deactivated by default; to
activate them, add the following line to your settings file:

    GUEST_ENABLED = True

You will also need to modify the connection screen to reflect the
possibility to connect with a guest account. The setting file accepts
several more options for customizing the Guest account system.

"""

from functools import cached_property

from evennia.accounts.accounts import DefaultAccount, DefaultGuest

from commands.utils import serialize_cmdset


class CharacterList:
    """
    A list wrapper that provides Django manager-like interface for account.characters.

    This is needed because Evennia's object creation code expects account.characters
    to have an add() method, but we want to return a list of available characters.
    """

    def __init__(self, account):
        self.account = account

    def add(self, character):
        """
        Django manager-style add method.

        In our case, we don't actually maintain a list of characters on the account
        since characters are managed through the roster system. This method is
        mainly called during character creation and we handle the association
        through PlayerData and roster entries.
        """
        # Clear any cached characters to force refresh
        if hasattr(self.account, "_characters_cache"):
            delattr(self.account, "_characters_cache")

    def all(self):
        """Return all available characters as a QuerySet-like interface."""
        return self.account.get_available_characters()

    def __iter__(self):
        """Allow iteration over characters."""
        return iter(self.account.get_available_characters())

    def __len__(self):
        """Return count of available characters."""
        return len(self.account.get_available_characters())

    def __contains__(self, character):
        """Check if character is in available characters."""
        return character in self.account.get_available_characters()

    def __eq__(self, other):
        """Allow comparison with lists and other CharacterList objects."""
        if isinstance(other, CharacterList):
            return (
                self.account.get_available_characters()
                == other.account.get_available_characters()
            )
        if isinstance(other, list):
            return self.account.get_available_characters() == other
        return False

    __hash__ = None


class Account(DefaultAccount):
    """
    ArxII Account implementation that uses PlayerData model instead of attributes.

    This Account represents one real player who can control multiple characters
    simultaneously through different sessions. Each session can puppet a different
    character from the player's available roster.

    Key differences from ArxI:
    - One account per real player (not per character)
    - Multisession support - multiple sessions can puppet different characters
    - All data stored in PlayerData model (no self.db usage)
    - Player anonymity maintained across characters
    """

    @property
    def player_data(self):
        """Get or create the PlayerData associated with this account."""
        from evennia_extensions.models import PlayerData

        # Use get_or_create to handle both existing and new accounts
        player_data, created = PlayerData.objects.get_or_create(account=self)
        if created:
            # Set initial display name to username if creating new PlayerData
            player_data.display_name = self.username
            player_data.save()
        return player_data

    @cached_property
    def characters(self):
        """Return characters actively played by this account."""
        return CharacterList(self)

    def get_available_characters(self):
        """Returns characters this player can currently control."""
        return self.player_data.get_available_characters()

    def get_puppeted_characters(self):
        """Returns list of characters currently being puppeted by any session."""
        return [session.puppet for session in self.sessions.all() if session.puppet]

    def get_available_sessions(self):
        """Returns sessions not currently puppeting any character."""
        return [session for session in self.sessions.all() if not session.puppet]

    def can_puppet_character(self, character):
        """Check if this account can puppet the given character."""
        # Must be one of their available characters
        if character not in self.get_available_characters():
            return False, "You don't have access to that character."

        # Character can't already be puppeted by this account
        if character in self.get_puppeted_characters():
            return (
                False,
                "You are already controlling that character in another session.",
            )

        return True, ""

    def puppet_character_in_session(self, character, session):
        """Puppet a character in a specific session."""
        can_puppet, reason = self.can_puppet_character(character)
        if not can_puppet:
            return False, reason

        # If session is already puppeting something, unpuppet first
        if session.puppet:
            session.msg(f"Switching from {session.puppet.name} to {character.name}.")
            self.unpuppet_object(session)

        # Puppet the new character
        self.puppet_object(session, character)
        return True, f"Now controlling {character.name}."

    def at_account_creation(self):
        """Called when account is first created."""
        super().at_account_creation()
        # PlayerData will be created automatically via the property

    def at_post_login(self, session=None):
        """Called after successful login."""
        super().at_post_login(session)

        # Store webclient authentication info for autologin
        if session and hasattr(session, "at_login"):
            session.uid = self.id  # Set the uid manually
            session.at_login()  # Then call standard at_login

        payload = serialize_cmdset(self)
        for sess in self.sessions.all():
            sess.msg(commands=(payload, {}))

        # Don't auto-puppet anything - let player choose via @ic command
        # Show available characters if they have any
        available_chars = self.get_available_characters()
        if available_chars:
            char_list = ", ".join([char.name for char in available_chars])
            session.msg(f"Available characters: {char_list}")
            session.msg("Use '@ic <character>' to control a character.")
        else:
            session.msg(
                "You have no available characters. Contact staff for character access.",
            )

    def at_post_create_character(self, character, **kwargs):
        """
        Handle character creation completion.

        Override the base method because our characters property returns a list,
        not a manager with an add() method.
        """
        # The base implementation tries to call self.characters.add(character)
        # but our characters property returns a list, so we need to handle this
        # differently

        # Clear the cached characters property to force refresh
        if hasattr(self, "_characters_cache"):
            delattr(self, "_characters_cache")

        # Set up locks (copied from base implementation)
        character.locks.add(
            f"puppet:id({character.id}) or pid({self.id}) or perm(Developer) or"
            f" pperm(Developer);delete:id({self.id}) or perm(Admin)",
        )

        # Log the creation (copied from base implementation)
        from evennia.utils import logger

        logger.log_sec(
            f"Character Created: {character} (Caller: {self}, IP: {kwargs.get('ip')}).",
        )

    def at_disconnect(self, reason=None):
        """Called when account disconnects."""
        # Update last seen information
        from django.utils import timezone

        self.player_data.account.last_login = timezone.now()
        self.player_data.account.save()
        super().at_disconnect(reason)


class Guest(DefaultGuest):
    """
    This class is used for guest logins. Unlike Accounts, Guests and their
    characters are deleted after disconnection.
    """
