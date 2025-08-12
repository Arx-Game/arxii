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
        return list(self.get_available_characters())

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
                "You have no available characters. Contact staff for character access."
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

    pass
